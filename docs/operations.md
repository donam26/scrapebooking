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

Hàng đợi arq tách riêng theo worker: `arq:queue:collector` (`probe_hotel`, tiến trình `worker`) và
`arq:queue:jobs` (analytics, bản tin, cron, tiến trình `jobs`). Hai worker không được dùng chung một
hàng đợi: job của hàm mà worker không có sẽ bị bỏ ("function not found").

**Nâng cấp từ bản dùng hàng đợi mặc định `arq:queue`:** dừng `scheduler` và `api`, chờ
`redis-cli ZCARD arq:queue` về 0 (kể cả job retry hoãn 60 giây), rồi mới deploy bản mới cho cả máy
trung tâm và máy collector (`docker-compose.collector.yml`) trong cùng một lần.

## 2. Khởi động lần đầu

```bash
cp .env.example .env            # điền PROXY_URL_TEMPLATE, JWT_SECRET, OPENROUTER_API_KEY
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

- Nhà cung cấp: **OpenRouter** (Chat Completions, OpenAI-compatible). `OPENROUTER_MODEL=openai/gpt-6-luna`, `OPENROUTER_REASONING_EFFORT=medium`, `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`, prompt hệ thống cố định (`app/insight/prompt.py`, `PROMPT_VERSION`).
- Hằng ngày: `INSIGHT_USE_BATCH=true`. OpenRouter **không có** Batch API server-side nên đây là giả lập: `submit_batch` chạy song song ngay bằng Chat Completions và cache kết quả vào Redis (key `insight:batch:*`, TTL 48h), `jobs` poll mỗi 10 phút materialize vào DB; luồng `pending`/`batch_pending` → `completed`/`failed` giữ nguyên. **Không có chiết khấu batch** (cost batch = cost đồng bộ). Theo yêu cầu từ dashboard: gọi đồng bộ.
- Mọi highlight/pricing_opportunity/risk phải có `evidence.ref` tồn tại trong đầu vào (`evt:<id>`, `metric:<hotel_id>:<date>`, `compset:<date>`); mục sai bị loại vào `dropped_highlights`.
- Không có `OPENROUTER_API_KEY` thì dùng client giả (đầu ra rỗng có ghi chú) để hệ thống vẫn chạy.
- Đổi prompt: tăng `PROMPT_VERSION`, chạy `uv run pytest tests/unit/test_insight_scenarios.py`.

## 6. Lệnh vận hành (`uv run sb ...`)

| Lệnh | Việc |
|---|---|
| `add-tenant`, `add-hotel`, `add-user` | Onboard bằng CLI (dashboard làm được việc tương tự). |
| `scan-now [--no-enqueue]` | Tạo scan run thủ công cho mọi tenant. Trên dashboard: nút "Quét ngay" (tenant, `POST /watchlist/scan-now`) và "Quét tất cả ngay" (operator, `POST /health/scan-now`), chống trùng trong 10 phút. |
| `run-status --limit 5` | Trạng thái các đợt quét gần nhất. |
| `analyze [--run-id N] [--all-pending]` | Chạy analytics tay. |
| `insight <tenant_id> [--sync/--batch]` | Sinh bản tin tay. |
| `reparse --since-days 30 [--no-reanalyze]` | Parse lại HTML thô sau khi đổi parser, rồi tính lại analytics cho các run bị ảnh hưởng. |
| `ensure-partitions`, `prune-partitions --keep-months 24` | Partition `room_snapshots`. |
| `backup-db` | pg_dump → gzip → MinIO bucket `BACKUP_BUCKET`, giữ `BACKUP_KEEP` bản. |

## 7. Giám sát và cảnh báo

- Grafana dashboard "Collector health": probe theo status, block rate 15 phút, session thu hồi, thời gian probe, job, analytics/insight.
- Cảnh báo vận hành ghi log mức warning với event `ops_alert` (lọc bằng `docker compose logs | grep ops_alert`): block rate >20% trong 15 phút (throttle 30 phút), đợt quét dưới 90% thành công, insight thất bại, backup thất bại.
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

Kiểm chứng dữ liệu một đợt quét thật với HTML thô trong MinIO (trích độc lập, không dùng parser):

```bash
cd backend && uv run python scripts/validate_run.py <scan_run_id>   # exit 1 nếu có sai lệch
```

Chạy sau mỗi lần Booking đổi giao diện hoặc sửa parser (kèm `sb reparse`). Lần kiểm chứng đầu
(2026-09-25, 4 khách sạn Q1 × 30 ngày, 3 đợt): 2.957/2.957 snapshot loại phòng khớp.

Ghi chú về dữ liệu Booking (đối chiếu trang thật 2026-09):
- Chromium headless phải dùng UA không có "HeadlessChrome", nếu không Booking 301 về trang không có
  ngày; collector coi trang có `checkin` khác ngày đã yêu cầu là bị chặn (đổi session).
- Dòng "Booking Basic" (`data-block-id` chứa `bbasic`, "Partner offer") là giá đối tác bán lại,
  không tính vào giá/tồn kho của khách sạn.
- Giá thấp nhất chỉ tính dòng giá cho đủ số người lớn đã tìm (bỏ "Only for 1 guest").
- Số phòng mức khách sạn trên heatmap là tổng các loại phòng biết chính xác (cận dưới khi có loại
  phòng "≥10" hoặc ẩn).

## 11. Rà soát flow người dùng

Chi tiết từng flow (operator, tenant admin, xem hằng ngày, bản tin, PMS, vận hành) và các
ràng buộc đã bổ sung: `docs/user-flows.md`.

## 12. Việc còn lại trước khi bán dịch vụ

- ~~Thay fixture HTML mô phỏng bằng trang Booking thật~~ (xong 2026-09-25, xem `backend/tests/fixtures/html/README.md`).
- Chạy thật giai đoạn 1 vài ngày (tiêu chí trong `docs/runbook-phase1.md`); đã chạy 3 đợt đầu với proxy dân dụng VN: 359/360 probe OK (1 lỗi 502 tạm thời, nay tự thử lại), 0 bị chặn.
- Tư vấn pháp lý về ToS Booking.com trước khi bán cho khách hàng.
- Adapter API cho ezCloud / Newway / Hotel Link / Smile khi được cấp quyền (interface `PmsAdapter` đã có).
