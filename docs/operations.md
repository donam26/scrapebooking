# Tài liệu vận hành (giai đoạn 1–5)

## 1. Thành phần và tiến trình

| Tiến trình | Lệnh | Việc làm |
|---|---|---|
| `migrate` | `alembic upgrade head` | Tạo/cập nhật schema (migration 0001–0011; 0007 = đa kênh, 0008 = thị trường/occupancy, 0010 = sự kiện địa phương, 0011 = thị trường khu vực). |
| `scheduler` | `python -m app.scheduler` | Mỗi 60 giây: tạo scan run cho mốc giờ quét của tenant (**một run mỗi kênh**), đẩy job `probe_hotel` vào hàng đợi của kênh, đẩy lại job kẹt, chốt run quá hạn 90 phút, cảnh báo block rate theo kênh và **tự ngắt kênh** bị chặn >20%/15 phút (30 phút), kiểm tra proxy mỗi 15 phút, tạo partition tháng. |
| `worker`, `worker-agoda`, `worker-ivivu`, `worker-tripcom` | `arq app.worker.settings.WorkerSettings` với `WORKER_CHANNEL=<kênh>` | Collector của một kênh: mỗi job = 1 listing (khách sạn × kênh), lấy calendar (nếu kênh có) rồi probe từng đêm theo tầng (0–14 đêm mọi lượt, xa hơn chỉ khi dữ liệu cũ), ghi snapshot + tín hiệu cầu, payload thô lên MinIO. Cũng chạy `verify_listing` (URL người dùng dán trỏ khách sạn nào) và `discover_listing` (tìm cùng khách sạn trên kênh này → gợi ý). Ngân sách request/phút toàn hệ thống theo kênh (`CHANNEL_BUDGETS`). Scale từng kênh: `--scale worker-agoda=N`. |
| `jobs` | `arq app.jobs.settings.JobsWorkerSettings` | Analytics sau mỗi run (+ catch-up mỗi 30 phút), insight hằng ngày theo `insight_hour` của tenant (Batch API), insight theo yêu cầu (đồng bộ), poll batch mỗi 10 phút, backup Postgres 02:30 giờ VN, dọn partition >24 tháng ngày 1 hằng tháng. |
| `api` | `uvicorn app.api.asgi:app` | FastAPI cho dashboard và import PMS. OpenAPI tại `/docs`, Prometheus tại `/metrics`. |
| `dashboard` | Next.js | Giao diện tenant và operator; gọi API qua rewrite `/api/*`. |

Hạ tầng: Postgres 16, Redis 7 (hàng đợi arq), MinIO (HTML thô 30 ngày, backup), Prometheus + Grafana (profile monitoring).

Hàng đợi arq tách riêng theo worker: `arq:queue:collector:<kênh>` (`probe_hotel`, `verify_listing`,
`discover_listing` của kênh đó) và `arq:queue:jobs` (analytics, bản tin, cron, tiến trình `jobs`).
Hai worker không được dùng chung một hàng đợi: job của hàm mà worker không có sẽ bị bỏ ("function
not found"). Kênh không có worker chạy thì listing của kênh đó đứng ở "đang kiểm tra".

**Nâng cấp lên đa kênh (0007):** migration bỏ `hotels.booking_*` (chuyển sang `listings`), nên dừng
mọi container cũ trước khi `migrate`, rồi khởi động bản mới cùng lúc. Hàng đợi cũ
`arq:queue:collector` không còn ai nghe: job còn `queued` được scheduler đẩy lại vào hàng đợi mới sau
5 phút.

**Proxy:** `PROXY_URL_TEMPLATE` nhận nhiều proxy cách nhau dấu phẩy (xoay vòng mỗi session mới). Dạng
`host:port:user:pass` của nhà cung cấp viết thành `http://user:pass@host:port`. Kiểm tra:
`uv run sb check-proxy`. Scheduler tự kiểm tra 15 phút/lần và gửi cảnh báo (email tới
`OPS_ALERT_EMAILS` nếu đã cấu hình SMTP, luôn ghi log `ops_alert`).

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

Sau đó vào dashboard http://localhost:3000, đăng nhập operator, tạo tenant, thêm khách sạn bằng URL trang khách sạn trên Booking.com, Agoda, iVIVU hoặc Trip.com (hệ thống tự kiểm tra URL rồi gợi ý cùng khách sạn trên các kênh còn lại để xác nhận), tạo tài khoản `tenant_admin` cho khách hàng.

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

## 5b. Thông báo email

- Cấu hình ở `.env` (worker `jobs` và `api`): `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY` (`starttls` | `ssl` | `none`), `APP_BASE_URL` (gốc dashboard cho liên kết trong email). Để trống `SMTP_HOST` thì không gửi; nhật ký ghi `skipped` / `smtp_not_configured`. Đổi `.env` xong phải tạo lại container (`up -d --force-recreate jobs api`).
- Cron `dispatch_notifications` (jobs, mỗi 5 phút, idempotent qua bảng `notifications.dedupe_key`):
  - `alerts:{tenant}:{run nhỏ nhất của mốc}`: sự kiện trong **mọi run cùng mốc quét** (mỗi kênh một run; đợi đủ các kênh chốt) đã analytics (24 giờ qua), gộp cùng sự kiện trên nhiều kênh thành một dòng ("trên Booking, Agoda"), lọc theo luật của tenant (`notification_rules`, mặc định bật): hết phòng (N đêm tới, ≥ M đối thủ hết; hết trên một kênh mà kênh khác vẫn bán thì viết "đóng bán trên kênh", không viết hết phòng), sắp hết phòng, giảm giá ≥ X%, **khách sạn của bạn rẻ hơn ≥ X% trên một kênh** (`own_parity_gap`, cùng cơ sở giá đã gồm thuế). Một email gom mọi mục; không có mục thì ghi `skipped`/`no_matches` (ẩn trên dashboard).
  - `insight:{id}`: bản tin daily `completed` trong 36 giờ qua.
  - `weekly:{tenant}:{năm}-W{tuần}`: thứ Hai từ 08:00 giờ tenant (bù trong thứ Ba nếu worker tắt cả thứ Hai).
  - Dòng được chèn ở trạng thái `sending` và commit trước khi gửi. Email lỗi SMTP thử lại sau 5 phút, 30 phút, 2 giờ (tối đa 4 lần); dòng `sending` quá 10 phút (worker chết giữa chừng) cũng được gửi lại. Mỗi lần thử giành dòng bằng UPDATE có điều kiện nên cron chạy chồng không gửi trùng. Email thử không được thử lại.
  - Lỗi của một tenant (dữ liệu lạ, DB) được ghi log `notification_dispatch_failed` và bỏ qua, không chặn tenant khác.
  - Không gửi bù: `skipped` vì chưa cấu hình SMTP hoặc chưa có người nhận là trạng thái cuối (cảnh báo chỉ có giá trị khi kịp thời).
- Người nhận do tenant_admin quản lý ở Cài đặt › Thông báo; mỗi người nhận một email riêng. Nút "Gửi thử" giới hạn 1 lần/phút/tenant.
- Thử cục bộ không gửi ra ngoài: `uv run --with aiosmtpd python -m aiosmtpd -n -l localhost:1025` rồi đặt `SMTP_HOST=localhost SMTP_PORT=1025 SMTP_SECURITY=none`.

## 5c. Ước tính công suất và gợi ý giá (đợt 2)

- Bảng `occupancy_estimates`, `occupancy_estimate_runs` (dấu đã xử lý), `price_suggestion_decisions` (migration 0008, sau 0007 đa kênh).
- Cron `estimate_occupancy_catch_up` (jobs, phút 4/14/…/54): lượt quét đã có `hotel_date_snapshots` mà chưa có dấu → tính, mỗi lượt commit riêng, lỗi một lượt không chặn lượt khác. Tồn phòng nhìn thấy = lớn nhất trong 30 ngày (số chính xác hoặc mức sàn).
- Tính lại toàn bộ: xoá `occupancy_estimate_runs` (và `occupancy_estimates`) rồi để cron chạy.
- PWA: `dashboard/src/app/manifest.ts`, icon trong `public/icons/`, `src/app/icon.svg`, `src/app/apple-icon.png`; `proxy.ts` cho qua manifest/icon không cần cookie.

## 6. Lệnh vận hành (`uv run sb ...`)

| Lệnh | Việc |
|---|---|
| `add-tenant`, `add-hotel`, `add-user` | Onboard bằng CLI (dashboard làm được việc tương tự). `add-hotel <tenant> <url>` nhận URL mọi kênh hỗ trợ; listing thêm qua CLI được quét ngay (không chờ verify). |
| `scan-now [--no-enqueue]` | Tạo scan run thủ công cho mọi tenant (một run mỗi kênh). Trên dashboard: nút "Quét ngay" (tenant, `POST /watchlist/scan-now`) và "Quét tất cả ngay" (operator, `POST /health/scan-now`), chống trùng trong 10 phút theo kênh. |
| `check-proxy` | Gọi thử qua từng proxy, in IP ra (không in mật khẩu); mã thoát 1 nếu có proxy lỗi. |
| `run-status --limit 5` | Trạng thái các đợt quét gần nhất. |
| `analyze [--run-id N] [--all-pending]` | Chạy analytics tay. |
| `insight <tenant_id> [--sync/--batch]` | Sinh bản tin tay. |
| `reparse --since-days 30 [--no-reanalyze]` | Parse lại HTML thô **Booking** sau khi đổi parser, rồi tính lại analytics cho các run bị ảnh hưởng. Kênh khác lưu payload JSON; `parser_version` mỗi probe có dạng `<kênh>:<phiên bản>`. |
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
- Chọn nhà cung cấp SMTP (SES, Postmark, Brevo…), cấu hình SPF/DKIM cho tên miền gửi, điền `SMTP_*` (mục 5b).
