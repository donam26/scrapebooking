# Phase 1: Đúng dữ liệu (collector → analytics → insight)

Ước lượng: 1–1,5 tuần. Phụ thuộc: phase 0. Trạng thái: todo.
Làm sớm vì HTML thô chỉ giữ 30 ngày: sửa xong phải `sb reparse --since-days 30` để tính lại lịch sử.

## Mục tiêu
Giá theo đêm, cùng tiền tệ, cùng cơ sở; tồn kho không bị ném đi; soft-block không giết listing; sự kiện/chỉ số không
nhiễu vì probe lỗi; bản tin sáng không drop bằng chứng.

## Việc

### 1.1 Booking: giá theo đêm + tiền tệ + thuế (ưu tiên 1)
- Bắt 1 fixture thật 2 đêm (`scripts/capture_fixture.py` sau phase 0) → xác nhận trang hiện tổng kỳ.
- `collector/booking/parser.py`: `parse_hotel_page(html, *, nights, expected_currency)`; giá rate plan = tổng / `nights`
  (ưu tiên đọc per-night từ JSON nhúng nếu có); `hybrid.py:96-99` và `browser.py` truyền `nights`.
- Reject khi mã tiền tệ parse được ≠ `SCAN_CURRENCY` → `ProbeStatus.ERROR, error="currency_mismatch"` như 4 kênh kia;
  siết `_CODE_RE` về danh sách mã hợp lệ.
- Thuế: khi `+VND X taxes` parse được → cộng vào giá và `taxes_included=True`; không parse được → giữ cờ False và
  **loại** khỏi so kênh/parity (xem 1.5).
- Test: `tests/unit/test_parser.py` thêm fixture 2 đêm + expected; test currency mismatch; `tests/unit/test_hybrid.py`
  truyền `nights=2`.
- Sau deploy: `uv run sb reparse --since-days 30` (có reanalyze) rồi `scripts/validate_run.py`.

### 1.2 Soft-block ≠ not_found; `broken` phải khó hơn
- Định nghĩa trong `collector/base.py`: `ListingNotFound` chỉ khi HTTP 404 thật hoặc kênh trả mã "không tồn tại" rõ
  ràng (Mytour 4103, Agoda `hotelInfo` null kèm `errorCode`); mọi "200 nhưng không có dữ liệu mong đợi" →
  `ListingBlocked`/`ProbeStatus.BLOCKED` (Agoda thiếu name `agoda/collector.py:352`, iVIVU thiếu `ng-state`
  `ivivu/collector.py:255`, Trip.com redirect `tripcom/collector.py:165`, Booking verify không marker
  `booking/collector.py:100-103`).
- `worker/jobs.py:210` + `listing_jobs.py:64`: `mark_listing_broken` chỉ sau **N=3 not_found liên tiếp qua ≥2 session khác
  nhau** (đếm trong `listings.last_error` hoặc cột mới `not_found_streak`); ghi `ops_alert`.
- Bắt exception bootstrap session ở `booking/hybrid.py:105`, `tripcom/collector.py:109` → BLOCKED + retire session.
- `fetch.py:28`: 503 = ERROR có retry, không phải BLOCKED; chỉ quét marker chặn trên body `text/html`.
- Test: mỗi kênh 1 test "200 trang challenge → BLOCKED, listing không broken"; test streak.

### 1.3 iVIVU, Mytour, Agoda
- iVIVU `parser.py:130`: dùng `AvailableNo` → `badge_count` (exact) hoặc `dropdown_max` (capped theo quy ước kênh);
  `ExcludeVAT` thiếu → `taxes_included=None`; `Hotels` rỗng do lỗi API → ERROR, chỉ SOLD_OUT khi payload hợp lệ nói
  hết; wrap `parse_price_response` để lỗi cấu trúc → ERROR không nổ job.
- Mytour `collector.py:255-257`: `api 3004` (appHash đổi) → BLOCKED + `ops_alert "mytour_secret_rotated"`; hết
  `max_polls` → kết quả `partial=True`, không ghi OK.
- Agoda: spike 1 ngày đo trần `availability` (so với room-grid); nếu có trần → CAPPED tại trần. Đưa `INITIATOR_API_KEY`,
  `ag-initiator-version`, Mytour `_WEB_SECRET`, iVIVU `SITE_KEY` vào `Settings` có default (đổi không cần build lại).
- Đóng client HTTP khi session hết hạn (`session.py:77-78` gọi hook `on_retire` cho mọi fetcher); dọn `ratelimit._last`
  theo session retired.

### 1.4 Analytics: không mất dữ liệu khi probe lỗi, đúng ngày, đúng tiền tệ
- `analytics/rules.py:357-362` + `service.py:353-363`: khi `cur` không dùng được → giữ `min_price/currency/exact_rooms_left`
  của bản metric hiện có, chỉ cập nhật `availability_status=unknown` + cột mới `stale_since`; `compset_by_day` dùng
  giá còn `stale_since` ≤ 24 h, bỏ qua lâu hơn (đóng luôn lỗi "đối thủ paused đóng góp giá 2 tuần").
- `_upsert_metrics`: upsert với `WHERE excluded.last_observed_at >= hotel_date_metrics.last_observed_at` (hết race 2 job).
- `days_to_arrival`: tính theo ngày địa phương tenant (truyền `tz` vào `AnalyticsService.run` và
  `occupancy_service.py:138`); migration backfill 1 lần.
- Kiểm `currency` bằng nhau ở `_price_events`, `pct_change`, `compset_by_day`, `parity_gap`; khác → bỏ qua + log.
- `new_sold_out` (`service.py:477-487`) giới hạn trong mốc hiện tại (`FRESH_FOR`); sửa docstring 12h→3h.
- `parity_gap`: so `min_refundable_price` khi cả hai kênh có, else `min_price` chỉ khi cả hai `taxes_included=True`
  thật (sửa `TAX_INCLUSIVE_CHANNELS` thành đọc cờ từ snapshot).
- Pickup: cửa sổ 24h/7d lấy quan sát **gần mốc nhất trong ±2 h**, không "≤ mốc"; loại phòng biến mất không tính là bán
  hết nếu `room_type_gone` cùng run.
- Insight input: loại sự kiện giá mức loại phòng khỏi `PRIORITY_EVENTS` (giữ mức khách sạn).

### 1.5 Insight
- `insight/service.py:282-294`: thêm `demand_signals` vào `_rebuild_from_stored` + test batch có demand ref.
- Bỏ lớp batch giả lập (`INSIGHT_USE_BATCH`, `submit_batch/poll_batch`, trạng thái `batch_pending`): OpenRouter không
  có batch, không chiết khấu; daily gọi đồng bộ trong job (đã có retry/cap 2 lần). Migration: `batch_pending` →
  `failed:batch_removed`. Giảm ~150 dòng + 1 cron.
- `client.py`: `max_tokens` (ước 4k), `timeout=120 s`, `max_retries=1`; ước lượng token đầu vào, cap số khách sạn
  (ví dụ 25) + bỏ `events_24h` trùng `events_7d` (đánh dấu `in_24h: true` thay vì gửi 2 lần).
- Validation: `evidence.kind` khớp prefix, `date_from ≤ date_to`, `hotel_ids` không rỗng.
- `/insights/generate`: khoá theo tenant (SELECT … FOR UPDATE hoặc unique partial index `status='pending'`) → không
  còn `MultipleResultsFound`.

### 1.6 Pace / gợi ý giá
- `market/models.py` `price_suggestion_decisions` thêm `hotel_id`; `pace_report.py:231-239` ORDER BY + hỗ trợ nhiều KS
  `self` (mỗi KS một bộ gợi ý) hoặc chốt "1 KS self/tenant" bằng CHECK — chọn theo câu hỏi 7 audit.
- So `min_refundable_price` khi có; kiểm tiền tệ; đưa ngưỡng vào `Settings` (chưa cần UI).

## Tiêu chí nghiệm thu
- Fixture Booking 2 đêm: `min_price` = tổng/2; `validate_run.py` 0 sai lệch trên run thật sau reparse.
- Chạy 3 ngày: 0 sự kiện `price_up/down` ≥ 50% trên đêm min-LOS>1 (trước đây có); 0 listing `broken` mới do trang
  challenge (kiểm `last_error`).
- iVIVU có `stock_confidence` ≠ hidden trên ≥ 50% snapshot.
- Heatmap không mất giá khi 1 probe blocked (test tích hợp mới `test_metrics_keep_last_price_on_block`).
- Bản tin daily có highlight dẫn `demand:` không bị drop (test).

## Rủi ro
- Reparse 30 ngày tốn thời gian worker; chạy ngoài giờ quét. Mất HTML >30 ngày = không sửa được lịch sử cũ hơn.
