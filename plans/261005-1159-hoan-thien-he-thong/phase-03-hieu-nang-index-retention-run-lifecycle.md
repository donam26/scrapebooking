# Phase 3: Hiệu năng, index, retention, vòng đời run

Ước lượng: 1 tuần. Phụ thuộc: phase 1 (schema analytics), phase 2 (Redis bền). Trạng thái: todo.
Phải xong trước khi vượt ~10 tenant / 100 khách sạn.

## Mục tiêu
Ghi probe O(1) theo index, analytics < 2 phút/run, run không mất probe muộn, kênh pause được quét bù, bảng lớn có
retention, budget ưu tiên tenant trước thị trường.

## Việc

### 3.1 Index và ràng buộc (migration 0013, `CREATE INDEX CONCURRENTLY` ngoài transaction cho bảng lớn)
- `room_snapshots(probe_id)` (trên bảng partition: index cục bộ mỗi partition, alembic tạo trên cha).
- `probes(channel, fetched_at)`; `probes(scan_run_id, hotel_id)` nếu chưa có cho `_tenant_runs`.
- `scan_jobs(hotel_id, scan_run_id)`.
- Dọn trùng rồi `UNIQUE (channel, external_id) WHERE external_id IS NOT NULL` trên `listings`.
- `listing_demand_signals(scan_run_id, hotel_id, channel, kind, stay_date)`.
- `availability_events(hotel_id, channel, stay_date, event_type, observed_at DESC)`.
- Index FK: `room_snapshots.room_type_id`, `hotel_calendars.scan_run_id`, `hotel_date_metrics.as_of_scan_run_id`,
  `occupancy_estimates.scan_run_id`.
- CHECK: `scan_runs.status`, `scan_jobs.status`, `probes.status`, `listings.status/channel`, `users.role`,
  `tenants.horizon_days BETWEEN 1 AND 90`, `array_length(scan_times) BETWEEN 1 AND 8`; CLI `add-tenant` validate như API.
- Thêm `ix_hotel_date_snapshots_run` vào `models.py`; `alembic/env.py` import `app.market.models`, `app.marketscan.models`;
  test `test_migrations.py` thêm "autogenerate không đề nghị thay đổi".

### 3.2 Vòng đời run kín
- `worker/jobs.py` vòng đêm: mỗi N đêm (hoặc mỗi đêm, 1 query nhẹ) đọc `scan_runs.status`; `!= running` → dừng,
  job `failed:run_closed`, không ghi thêm.
- `repo/runs.py.finish_job`: `WHERE status IN ('running','retrying')` → không lật `failed:deadline` thành `done`.
- Analytics idempotent đã có → khi run `partial` nhận probe muộn (trước khi 3.2 deploy xong), cron `analytics_catch_up`
  dùng cột mới `scan_runs.analyzed_at` + `last_probe_at` thay `NOT IN (SELECT DISTINCT …)`: run có `last_probe_at >
  analyzed_at` → chạy lại.
- Kênh pause: khi pause hết hạn, scheduler tạo run `catchup:<phút>:<kênh>` cho khách sạn có job `failed:channel_paused`
  trong mốc gần nhất (mở rộng `hotels_scanned_since`).
- Scan-now tenant: nếu có run theo lịch/`manual:all` đang `running` cùng kênh chứa khách sạn đó → trả run đó (409 kèm
  id) thay vì tạo run mới; thêm `scan_runs.tenant_id` (nullable) thay cho parse `trigger_key`.
- arq: bắt `asyncio.CancelledError` ở `probe_hotel` để chốt job `failed:timeout`; `keep_result` 24 h; ghi job fail cuối
  vào bảng `job_failures` (dead-letter đơn giản) để `/admin/health` hiển thị.

### 3.3 Analytics và API ít query hơn
- `analytics/service.py`: nạp `existing` metrics + `max(observed_at)` sold_out/restock cho **cả khách sạn** một lần
  (dict theo stay_date) thay vì mỗi đêm; `executemany` cho events/snapshots → mục tiêu ≤ 50 query/khách sạn/run.
- `data.py` overview: nạp `HotelDateMetric` một lần dùng cho cả compset; thêm `GZipMiddleware(minimum_size=1024)`;
  `Cache-Control: private, max-age=60` + ETag theo `max(last_observed_at)` cho `/overview`, `/market/pace`.
- Endpoint mới `GET /hotels/demand-signals?hours=24` (gộp cho Terminal+) và `GET /events/{id}` (cho highlight bản tin,
  đóng mục "còn để ngỏ" trong user-flows).
- Pace: cache kết quả `/market/pace` trong Redis 10 phút theo (tenant, kênh, range), invalidate khi occupancy mới.
- Occupancy: thay vòng lặp bậc hai bằng dict theo khoá; bulk insert; lỗi tạm → đánh dấu `retry_after` không `rows=-1`
  vĩnh viễn; `sb analyze --run-id` xoá dấu occupancy để tính lại.

### 3.4 Retention và partition
- Policy (docs/operations.md §9): `probes` 6 tháng, `hotel_calendars` 3 tháng, `scrape_sessions` 1 tháng, `scan_jobs`
  12 tháng, `listing_demand_signals` 12 tháng, `occupancy_estimates` 24 tháng; `hotel_date_snapshots`,
  `availability_events`, `hotel_date_metrics` giữ (nhỏ hơn nhiều).
- Partition tháng cho `probes` và `hotel_calendars` (migration tạo bảng mới + copy + rename, chạy ngoài giờ quét) hoặc
  cron `DELETE … WHERE fetched_at < now() - interval` theo lô 10k nếu chưa cần partition.
- DEFAULT partition cho `room_snapshots`; `ensure_partitions` chạy trong `migrate` và cron jobs hằng ngày, không chỉ
  scheduler.
- MinIO lifecycle HTML thô: giữ 30 ngày cho probe `ok`; 90 ngày cho probe `error/blocked/empty` (phục vụ debug parser).

### 3.5 Budget và thông lượng
- `collector/budget.py`: sliding window (ZSET theo timestamp) thay fixed window; waiter ngủ ngẫu nhiên 0–1 s.
- Ưu tiên: 2 lớp budget mỗi kênh `tenant` (70%) / `market` (30%), job thị trường chỉ dùng lớp market + phần dư.
- Chia sẻ danh sách thị trường: unique `market_list_scans` theo (kênh, dest_id, đêm, ngày) không theo tenant; area của
  tenant chỉ tham chiếu.
- Gom khách sạn chung giữa tenant khác phút UTC: planner dùng "khách sạn đã có job trong ±30 phút" để bỏ qua (mở rộng
  tiering sang mọi đêm, không chỉ xa).
- Scheduler: pipeline Redis khi enqueue/re-enqueue; `report.reenqueued` đếm đúng.
- Proxy: `ProxyProvider` ghi điểm sức khoẻ theo endpoint (Redis), bỏ qua endpoint lỗi ≥3 lần trong 15 phút; percent-decode
  mật khẩu; backoff mũ + jitter + `Retry-After` ở `fetch.py` (tối đa 3 lần, 2→8→30 s).

## Tiêu chí nghiệm thu
- `EXPLAIN` 3 query baseline (phase 0.4): index scan, thời gian giảm ≥ 10× trên DB dev có 3 tháng dữ liệu.
- Giả lập run quá hạn khi worker còn ghi (test tích hợp): job không thành `done`, probe muộn được analytics ở lần catch-up.
- Pause kênh 30 phút giữa mốc → sau pause có run `catchup:` cho đúng khách sạn (test).
- Analytics 20 KS × 90 đêm: ≤ 1.000 query (đếm bằng event listener SQLAlchemy trong test), < 2 phút trên dev.
- Tải 7 ngày với 100 KS × 5 kênh: không run `partial` vì deadline; run thị trường không làm run tenant trượt.
- Bảng `probes` không tăng quá 6 tháng dữ liệu.

## Rủi ro
- `CREATE INDEX CONCURRENTLY` trên partition cha không hỗ trợ: tạo trên từng partition rồi `ATTACH`; cần script.
- Chuyển `probes` sang partition cần downtime ngắn ngoài giờ quét.
