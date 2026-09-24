# Giai đoạn 2–5: ghi chú triển khai

Ngày: 2026-09-24. Spec: `docs/superpowers/specs/2026-09-24-hotel-competitor-monitor-design.md`
mục 5, 7, 8, 9, 10, 11. Không có kế hoạch từng bước riêng cho các giai đoạn này nên tài liệu
này ghi lại các quyết định đã chốt khi viết code, để review và để làm cơ sở cho kế hoạch
chạy thật.

## Giai đoạn 2: Analytics và API cơ bản

**Bảng** (migration `0002`): `hotel_date_snapshots`, `availability_events`
(unique `(scan_run_id, hotel_id, room_type_id, stay_date, event_type)` với `NULLS NOT DISTINCT`
để chạy lại không trùng), `hotel_date_metrics`, `users`.

**Analytics** (`app/analytics/`):
- `rules.py` thuần, không I/O, test đơn vị đầy đủ. `service.py` chạy theo scan run, xử lý
  từng khách sạn: nạp probe + room_snapshots của run, nạp lịch sử 8 ngày của
  `hotel_date_snapshots` và `room_snapshots` (khoá theo `(stay_date, scanned_at)`), rồi
  gộp → so sánh → chỉ số.
- "Lần quan sát dùng được gần nhất" = `hotel_date_snapshots` có status `available`/`sold_out`
  và `scanned_at` nhỏ hơn lần hiện tại, không phụ thuộc thứ tự run.
- Sự kiện mức khách sạn: `sold_out`, `restock`, `price_up/down` theo `min_price` khách sạn.
  Mức loại phòng: `rooms_decrease/increase` (cả hai `exact`), `low_stock_enter`,
  `price_up/down`, `room_type_new/gone`. Probe `ok` mà không parse được phòng nào coi là
  `unknown` (không sinh sự kiện).
- `pickup_24h` và `velocity_3d` (phòng/ngày) so với lần quan sát dùng được gần nhất ở mốc
  24h/72h trước, chỉ cộng loại phòng `exact` ở cả hai lần; loại phòng `exact` biến mất tính
  là bán hết. `price_change_7d_pct` so với mốc 7 ngày. `exact_share` = tỷ lệ quan sát có ít
  nhất một loại phòng `exact` trong 7 ngày. `sold_out_at`/`restocked_at` = thời điểm sự kiện
  gần nhất tương ứng.
- `room_types_sold_out` = số loại phòng thấy trong 30 ngày qua nhưng vắng ở probe hiện tại.
- Chỉ số compset (`compset.py`) tính tại chỗ, dùng chung cho API và insight: giá thấp nhất
  và trung vị đối thủ, tỷ lệ đối thủ hết phòng, giá và occupancy PMS của khách sạn khách hàng,
  `price_index = own_min_price / median * 100`.
- Kích hoạt: worker collector đẩy job `run_analytics` khi run chốt; jobs worker có cron
  catch-up 30 phút cho run chưa tính (`pending_run_ids`).

**API** (`app/api/`, FastAPI): JWT HS256 trong cookie httpOnly `sb_session` (12 giờ), argon2.
Vai trò: `operator` (không tenant, phải truyền `?tenant_id=`), `tenant_admin` (ghi), `viewer`
(đọc). Mọi endpoint dữ liệu lọc qua `tenant_hotels`. Xoá khỏi watchlist = `active=false`
để giữ lịch sử. `docs/api/openapi.json` sinh từ app; dashboard sinh type TypeScript từ file này.

## Giai đoạn 3: AI insight

- `insights` (migration `0003`) thêm `status` (`pending`, `batch_pending`, `completed`,
  `failed`), `batch_id`, `error`, `scan_run_id`.
- Đầu vào (`input_builder.py`): mỗi ô ngày có `ref = metric:<hotel_id>:<date>`, sự kiện
  `evt:<id>` (24h tối đa 120, 7 ngày tối đa 200, chỉ loại ưu tiên), compset `compset:<date>`,
  PMS occupancy gắn vào ngày của khách sạn `self`, ngày lễ theo nước (`app/holidays/data.py`,
  bảng tĩnh VN/TH/SG/US/GB), thống kê chất lượng dữ liệu. Không có HTML thô.
- Đầu ra: Structured Outputs `strict`, schema trong `schema.py` đúng spec mục 8. Kiểm tra
  sau khi nhận (`validation.py`): ref không tồn tại, không có bằng chứng, hotel_id lạ, ngày
  ngoài kỳ → loại và ghi `dropped_highlights` kèm lý do.
- Gọi model: Responses API, `reasoning.effort=medium`, prompt hệ thống cố định
  (`PROMPT_VERSION`). Hằng ngày qua Batch API (giảm 50% chi phí), poll mỗi 10 phút. Theo
  yêu cầu: API tạo dòng `pending`, đẩy job, job gọi đồng bộ và điền dòng đó; dashboard poll.
- Idempotent hằng ngày theo `(tenant, ngày địa phương)`; job id `insight:<tenant>:<key>`.
- Chi phí ước tính theo giá research ($0.10/1M vào, $0.50/1M ra) lưu `cost_usd`.
- Không có `OPENAI_API_KEY`: dùng `FakeInsightClient` để pipeline vẫn chạy được (đầu ra ghi rõ
  là giả). Bộ 11 kịch bản xác định trong `backend/tests/fixtures/insight/`.

## Giai đoạn 4: Import PMS

- Bảng (migration `0004`): `own_hotel_daily`, `pms_imports`, `pms_column_mappings` (ánh xạ
  theo tenant + adapter).
- `PmsAdapter` (`app/pms/base.py`) với `read_table`, `suggest_mapping`, `parse`. `CsvAdapter`
  đọc CSV (tự dò dấu phân cách, nhiều encoding) và Excel (`openpyxl`), gợi ý ánh xạ theo tên
  cột thường gặp (ezCloud, Newway, tiếng Việt có dấu/không dấu), suy ra `rooms_available`,
  `rooms_sold`, `occupancy_pct` khi thiếu, lỗi từng dòng (ngày sai, trùng ngày, sold > total,
  occupancy ngoài 0–100).
- Luồng dashboard: tải template → upload preview (cột, mẫu, ánh xạ gợi ý, lỗi) → lưu ánh xạ →
  import (chỉ khách sạn `role=self`) → lịch sử import. Upsert theo `(tenant, hotel, stay_date)`.
- Adapter API cho từng PMS: chưa làm (spec: khi được cấp quyền), cùng interface.

## Giai đoạn 5: Quản trị, cảnh báo, backup, tài liệu

- Quản trị tenant/người dùng: endpoint operator + màn hình `/admin/*` trên dashboard, CLI
  `add-tenant`, `add-user`.
- Cảnh báo Telegram: block rate (scheduler), đợt quét dưới 90% (worker), insight thất bại và
  backup thất bại (jobs).
- Backup: `app/ops/backup.py` pg_dump → gzip → MinIO bucket `BACKUP_BUCKET`, giữ
  `BACKUP_KEEP` bản, cron 19:30 UTC trong jobs worker, CLI `backup-db`. Image backend cài
  `postgresql-client-16`.
- Lưu trữ: partition `room_snapshots` cũ hơn 24 tháng bị xoá ngày 1 hằng tháng
  (`prune_partitions`), HTML thô hết hạn 30 ngày bằng lifecycle MinIO.
- Tài liệu: `docs/operations.md`, `docs/runbook-phase1.md`, `README.md`.

## Điều chưa làm được trong môi trường dựng code

- Không có proxy residential và Docker daemon: chưa bắt fixture Booking thật, chưa chạy test
  live, chưa build image. Fixture HTML hiện là trang mô phỏng theo cấu trúc `#hprt-table`;
  selector phải được xác nhận trên trang thật trước khi chạy (xem README trong thư mục fixture).
- Chưa gọi GPT-6 Luna thật; client viết theo SDK `openai` (Responses + Batch), cần kiểm tra
  một lần với API key thật (`uv run sb insight <tenant_id> --sync`).
