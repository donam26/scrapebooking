#!/usr/bin/env bash
# Diễn tập khôi phục (phase 2.4, docs/operations.md §8): tải bản backup mới nhất từ bucket, restore
# vào một Postgres tạm trong container, đếm dòng 5 bảng chính, in tóm tắt rồi dọn dẹp.
#
#   BACKUP_ENDPOINT=http://localhost:9000 BACKUP_ACCESS_KEY=… BACKUP_SECRET_KEY=… \
#     infra/scripts/restore-drill.sh [--keep] [--key postgres/scrapebooking-<ts>.dump.gz]
#
# Biến (mặc định lấy từ MINIO_* trong môi trường nếu đã `set -a; . .env`):
#   BACKUP_ENDPOINT, BACKUP_ACCESS_KEY, BACKUP_SECRET_KEY, BACKUP_BUCKET (pg-backups)
#   PG_IMAGE (postgres:16.9-alpine)   DRILL_DIR (thư mục tạm)   --keep: giữ container + file để xem
# Cần: docker, và `mc` (MinIO client) hoặc `aws` CLI để tải từ bucket.
set -euo pipefail

ENDPOINT="${BACKUP_ENDPOINT:-${MINIO_ENDPOINT:-http://localhost:9000}}"
ACCESS_KEY="${BACKUP_ACCESS_KEY:-${MINIO_ACCESS_KEY:-${MINIO_ROOT_USER:-minioadmin}}}"
SECRET_KEY="${BACKUP_SECRET_KEY:-${MINIO_SECRET_KEY:-${MINIO_ROOT_PASSWORD:-}}}"
BUCKET="${BACKUP_BUCKET:-pg-backups}"
PREFIX="postgres/"
PG_IMAGE="${PG_IMAGE:-postgres:16.9-alpine}"
CONTAINER="sb-restore-drill-$$"
TABLES=(tenants hotels listings scan_runs probes)
KEEP=0
KEY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --key) KEY="$2"; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "tham số lạ: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$SECRET_KEY" ]; then
  echo "thiếu BACKUP_SECRET_KEY (hoặc MINIO_SECRET_KEY / MINIO_ROOT_PASSWORD)" >&2
  exit 2
fi

DRILL_DIR="${DRILL_DIR:-$(mktemp -d -t sb-restore-drill.XXXXXX)}"
LOG="$DRILL_DIR/restore.log"
started=$(date +%s)

cleanup() {
  if [ "$KEEP" -eq 1 ]; then
    echo "giữ lại: container $CONTAINER, thư mục $DRILL_DIR"
    return
  fi
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$DRILL_DIR"
}
trap cleanup EXIT

# ---- 1. Tìm và tải bản mới nhất ------------------------------------------------------------------
if command -v mc >/dev/null 2>&1; then
  ALIAS="sbdrill$$"
  mc alias set "$ALIAS" "$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" >/dev/null
  if [ -z "$KEY" ]; then
    KEY="$PREFIX$(mc ls "$ALIAS/$BUCKET/$PREFIX" | awk '{print $NF}' | grep -E '\.(dump|sql)\.gz$' | sort | tail -n1)"
  fi
  [ "$KEY" != "$PREFIX" ] || { echo "không có backup nào trong $BUCKET/$PREFIX" >&2; exit 1; }
  mc cp "$ALIAS/$BUCKET/$KEY" "$DRILL_DIR/backup.gz" >/dev/null
  mc alias remove "$ALIAS" >/dev/null
elif command -v aws >/dev/null 2>&1; then
  export AWS_ACCESS_KEY_ID="$ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$SECRET_KEY" AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
  if [ -z "$KEY" ]; then
    KEY=$(aws --endpoint-url "$ENDPOINT" s3 ls "s3://$BUCKET/$PREFIX" | awk '{print $NF}' | grep -E '\.(dump|sql)\.gz$' | sort | tail -n1)
    [ -n "$KEY" ] || { echo "không có backup nào trong $BUCKET/$PREFIX" >&2; exit 1; }
    KEY="$PREFIX$KEY"
  fi
  aws --endpoint-url "$ENDPOINT" s3 cp "s3://$BUCKET/$KEY" "$DRILL_DIR/backup.gz" >/dev/null
else
  echo "cần mc (MinIO client) hoặc aws CLI để tải backup" >&2
  exit 2
fi
size=$(wc -c < "$DRILL_DIR/backup.gz")
echo "backup: $KEY ($size byte)"

# ---- 2. Postgres tạm ----------------------------------------------------------------------------
docker run -d --rm --name "$CONTAINER" -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=drill "$PG_IMAGE" >/dev/null
for _ in $(seq 1 30); do
  docker exec "$CONTAINER" pg_isready -U postgres -d drill >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$CONTAINER" pg_isready -U postgres -d drill >/dev/null

# ---- 3. Restore ---------------------------------------------------------------------------------
docker cp "$DRILL_DIR/backup.gz" "$CONTAINER:/tmp/backup.gz"
case "$KEY" in
  *.dump.gz)
    # pg_dump -Fc (bản mới): pg_restore; --no-owner vì role gốc không tồn tại ở đây.
    docker exec "$CONTAINER" sh -c 'gunzip -c /tmp/backup.gz | pg_restore --no-owner --no-privileges -U postgres -d drill' >"$LOG" 2>&1 \
      || { echo "pg_restore lỗi, xem $LOG:"; tail -n 20 "$LOG"; KEEP=1; exit 1; }
    ;;
  *.sql.gz)
    # Bản plain cũ (trước phase 2.4): psql.
    docker exec "$CONTAINER" sh -c 'gunzip -c /tmp/backup.gz | psql -v ON_ERROR_STOP=1 -q -U postgres -d drill' >"$LOG" 2>&1 \
      || { echo "psql lỗi, xem $LOG:"; tail -n 20 "$LOG"; KEEP=1; exit 1; }
    ;;
  *) echo "đuôi file lạ: $KEY" >&2; exit 1 ;;
esac

# ---- 4. Đếm dòng --------------------------------------------------------------------------------
echo "---- restore drill $(date -u +%Y-%m-%dT%H:%M:%SZ) ----"
printf '%-16s %12s\n' "bảng" "số dòng"
total_ok=1
for t in "${TABLES[@]}"; do
  n=$(docker exec "$CONTAINER" psql -U postgres -d drill -Atc "SELECT count(*) FROM $t" 2>/dev/null || echo "LỖI")
  [ "$n" != "LỖI" ] || total_ok=0
  printf '%-16s %12s\n' "$t" "$n"
done
latest_run=$(docker exec "$CONTAINER" psql -U postgres -d drill -Atc "SELECT coalesce(max(finished_at)::text, '-') FROM scan_runs" 2>/dev/null || echo "-")
elapsed=$(( $(date +%s) - started ))
echo "run gần nhất trong backup: $latest_run"
echo "thời gian: ${elapsed}s  (mục tiêu < 30 phút)"
if [ "$total_ok" -eq 1 ]; then
  echo "KẾT QUẢ: OK — ghi vào docs/operations.md §8 (ngày, key, số dòng, thời gian)"
else
  echo "KẾT QUẢ: THẤT BẠI — có bảng không đếm được, xem $LOG"
  KEEP=1
  exit 1
fi
