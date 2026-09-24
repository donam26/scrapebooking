# Tài liệu vận hành (giai đoạn 1–5)

## 1. Thành phần và tiến trình

| Tiến trình | Lệnh | Việc làm |
|---|---|---|
| `migrate` | `alembic upgrade head` | Tạo/cập nhật schema (migration 0001–0004). |
| `scheduler` | `python -m app.scheduler` | Mỗi 60 giây: tạo scan run cho mốc giờ quét của tenant, đẩy job `probe_hotel`, đẩy lại job kẹt, chốt run quá hạn 90 phút, cảnh báo block rate, tạo partition tháng. |
| `worker` | `arq app.worker.settings.WorkerSettings` | Collector: mỗi job = 1 khách sạn, lấy calendar rồi probe từng ngày (session lai Playwright + curl_cffi, fallback trình duyệt), ghi snapshot, HTML thô lên MinIO. Khi run chốt thì đẩy job analytics. Scale bằng `--scale worker=N`. |
| `jobs` | `arq app.jobs.settings.JobsWorkerSettings` | Analytics sau mỗi run (+ catch-up mỗi 30 phút), insight hằng ngày theo `insight_hour` của tenant (Batch API), insight theo yêu cầu (đồng bộ), poll batch mỗi 10 phút, backup Postgres 02:30 giờ VN, dọn partition >24 tháng ngày 1 hằng tháng. |
| `api` | `uvicorn app.api.asgi:app` | FastAPI cho dashboard và import PMS. OpenAPI tại `/docs`, Prometheus tại `/metrics`. |
| `dashboard` | Next.js | Giao diện tenant và operator; gọi API qua rewrite `/api/*`. |

Hạ tầng: Postgres 16, Redis 7 (hàng đợi arq), MinIO (HTML thô 30 ngày, backup), Prometheus + Grafana (profile monitoring).

## 2. Khởi động lần đầu

```bash
cp .env.example .env            # điền PROXY_URL_TEMPLATE, JWT_SECRET, OPENAI_API_KEY, TELEGRAM_*
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.monitoring.yml up -d
cd backend
uv run sb add-user ops@congty.vn --role operator          # tài khoản operator đầu tiên
```

Sau đó vào dashboard http://localhost:3000, đăng nhập operator, tạo tenant, thêm khách sạn bằng URL Booking, tạo tài khoản `tenant_admin` cho khách hàng.

Dữ liệu demo để thử giao diện không cần scrape: `uv run python scripts/seed_demo.py`.

## 3. Luồng dữ liệu và bảng

`scheduler` → `scan_runs`, `scan_jobs` → `worker` → `probes`, `hotel_calendars`, `room_types`, `room_snapshots` (partition tháng), MinIO → `jobs/analytics` → `hotel_date_snapshots`, `availability_events`, `hotel_date_metrics` → `jobs/insight` → `insights` → `api` → dashboard. PMS: `pms_column_mappings`, `pms_imports`, `own_hotel_daily`.

Mọi bước idempotent: run theo `trigger_key`, probe theo `(scan_run_id, hotel_id, stay_date)`, analytics xoá và tính lại sự kiện của run, insight hằng ngày theo `(tenant, ngày địa phương)`.

## 4. Quy tắc analytics (cấu hình qua `.env`)

- Trạng thái ngày theo probe: `ok` → available; `sold_out`, `skipped_calendar` → sold_out; `no_rooms_1n`, `blocked`, `error` → unknown.
- So sánh với **lần quan sát dùng được gần nhất** (available/sold_out), không phải đợt liền trước.
- `LOW_STOCK_THRESHOLD` (mặc định 3), `PRICE_CHANGE_THRESHOLD_PCT` (mặc định 3).
- pickup/velocity chỉ dùng cặp loại phòng `exact` ở cả hai lần.

## 5. AI insight

- Model `OPENAI_MODEL=gpt-6-luna`, `OPENAI_REASONING_EFFORT=medium`, prompt hệ thống cố định (`app/insight/prompt.py`, `PROMPT_VERSION`).
- Hằng ngày: `INSIGHT_USE_BATCH=true` → Batch API, kết quả về trong vòng 24h, `jobs` poll mỗi 10 phút. Theo yêu cầu từ dashboard: gọi đồng bộ, dòng `insights` chuyển `pending` → `completed`/`failed`.
- Mọi highlight/pricing_opportunity/risk phải có `evidence.ref` tồn tại trong đầu vào (`evt:<id>`, `metric:<hotel_id>:<date>`, `compset:<date>`); mục sai bị loại vào `dropped_highlights`.
- Không có `OPENAI_API_KEY` thì dùng client giả (đầu ra rỗng có ghi chú) để hệ thống vẫn chạy.
- Đổi prompt: tăng `PROMPT_VERSION`, chạy `uv run pytest tests/unit/test_insight_scenarios.py`.

## 6. Lệnh vận hành (`uv run sb ...`)

| Lệnh | Việc |
|---|---|
| `add-tenant`, `add-hotel`, `add-user` | Onboard bằng CLI (dashboard làm được việc tương tự). |
| `scan-now [--no-enqueue]` | Tạo scan run thủ công cho mọi tenant. |
| `run-status --limit 5` | Trạng thái các đợt quét gần nhất. |
| `analyze [--run-id N] [--all-pending]` | Chạy analytics tay. |
| `insight <tenant_id> [--sync/--batch]` | Sinh bản tin tay. |
| `reparse --since-days 30` | Parse lại HTML thô sau khi đổi parser. |
| `ensure-partitions`, `prune-partitions --keep-months 24` | Partition `room_snapshots`. |
| `backup-db` | pg_dump → gzip → MinIO bucket `BACKUP_BUCKET`, giữ `BACKUP_KEEP` bản. |

## 7. Giám sát và cảnh báo

- Grafana dashboard "Collector health": probe theo status, block rate 15 phút, session thu hồi, thời gian probe, job, analytics/insight.
- Telegram: block rate >20% trong 15 phút (throttle 30 phút), đợt quét dưới 90% thành công, insight thất bại, backup thất bại.
- Operator xem `/admin/health` trên dashboard hoặc `GET /health/summary`.

## 8. Khôi phục

```bash
# liệt kê backup
mc alias set local http://localhost:9000 minioadmin minioadmin
mc ls local/pg-backups/postgres/
mc cp local/pg-backups/postgres/scrapebooking-<ts>.sql.gz . && gunzip scrapebooking-<ts>.sql.gz
psql postgresql://app:app@localhost:5432/scrapebooking < scrapebooking-<ts>.sql
```

## 9. Lưu trữ

- HTML thô: lifecycle rule 30 ngày trên bucket `raw-html`.
- `room_snapshots`: partition tháng, xoá partition cũ hơn 24 tháng (job tháng hoặc `prune-partitions`).
- Sự kiện, chỉ số, insight: giữ vô hạn.

## 10. Kiểm thử

```bash
make lint && make typecheck
make test        # unit
make test-int    # unit + integration (cần Postgres, Redis; MinIO tuỳ chọn)
cd backend && uv run pytest tests/live -m live -s   # gọi Booking thật, cần proxy thật
cd dashboard && npm run lint && npm run typecheck && npm run build
```

## 11. Việc còn lại trước khi bán dịch vụ

- Thay 3 fixture HTML mô phỏng bằng trang Booking thật và xác nhận selector (xem `backend/tests/fixtures/html/README.md`).
- Chạy thật giai đoạn 1 vài ngày (tiêu chí trong `docs/runbook-phase1.md`).
- Tư vấn pháp lý về ToS Booking.com trước khi bán cho khách hàng.
- Adapter API cho ezCloud / Newway / Hotel Link / Smile khi được cấp quyền (interface `PmsAdapter` đã có).
