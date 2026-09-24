# Runbook giai đoạn 1: Collector

## Khởi động
1. `cp .env.example .env`, điền `PROXY_URL_TEMPLATE` (residential, sticky session theo `{session}`,
   chọn nước theo `{country}`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `JWT_SECRET`.
2. `docker compose -f infra/docker-compose.yml up -d --build`
3. Monitoring: `docker compose -f infra/docker-compose.monitoring.yml up -d`, Grafana tại
   http://localhost:3001 (admin/admin), dashboard "Collector health" được provision sẵn.

## Thêm tenant và khách sạn
    cd backend
    uv run sb add-tenant "Tên khách hàng" --timezone Asia/Ho_Chi_Minh --horizon 30
    uv run sb add-hotel <tenant_id> https://www.booking.com/hotel/vn/<slug>.html --role self --label "Của tôi"
    uv run sb add-hotel <tenant_id> https://www.booking.com/hotel/vn/<slug-doi-thu>.html --role competitor
    uv run sb add-user admin@khachhang.vn --role tenant_admin --tenant-id <tenant_id>
    uv run sb add-user ops@congty.vn --role operator

Hoặc dùng dashboard (màn hình Cài đặt) sau khi đăng nhập bằng tài khoản `tenant_admin`.

## Quét thủ công và theo dõi
    uv run sb scan-now
    uv run sb run-status
    docker compose -f infra/docker-compose.yml logs -f worker

## Tăng công suất
    docker compose -f infra/docker-compose.yml up -d --scale worker=4
Trên máy khác: `docker compose -f infra/docker-compose.collector.yml up -d --scale worker=4`
với `.env` trỏ về máy trung tâm.

## Fixture trang Booking
Ba fixture trong `backend/tests/fixtures/html/` hiện là trang mô phỏng. Trước khi chạy thật,
bắt trang thật theo hướng dẫn trong `backend/tests/fixtures/html/README.md` và xác nhận
selector bằng `scripts/explore_fixture.py`.

## Khi Booking đổi giao diện
1. `uv run python scripts/capture_fixture.py <url> <checkin> 1 new_layout`
2. `uv run python scripts/explore_fixture.py tests/fixtures/html/new_layout.html`, sửa `selectors.py`.
3. Tăng `PARSER_VERSION`, chạy `uv run pytest tests/unit/test_parser.py`, emit lại golden.
4. `uv run sb reparse --since-days 30`, sau đó `uv run sb analyze --all-pending` nếu cần tính lại.

## Khi block rate tăng
- Xem Grafana: `sb_probes_total{status="blocked"}` theo thời gian,
  `sb_sessions_retired_total{reason="blocked"}`.
- Giảm tải: tăng `REQUEST_MIN_INTERVAL_SECONDS`, giảm `SESSION_MAX_REQUESTS`.
- Đổi pool proxy hoặc nhà cung cấp qua `PROXY_URL_TEMPLATE`.
- Kiểm tra tay: `uv run pytest tests/live/test_bootstrap_live.py -m live -s` với
  `PLAYWRIGHT_HEADLESS=false`.

## Truy vấn kiểm tra dữ liệu
    select h.booking_slug, rs.stay_date, rt.name, rs.rooms_left, rs.stock_confidence, rs.min_price, rs.scanned_at
    from room_snapshots rs join room_types rt on rt.id = rs.room_type_id join hotels h on h.id = rs.hotel_id
    order by rs.scanned_at desc limit 50;

## Tiêu chí bàn giao giai đoạn 1
Chạy thật với 1 tenant, 1 khách sạn `self`, 2 khách sạn `competitor` trong 3 ngày:
9 đợt quét liên tiếp đều `completed`, không có đợt nào `partial`, không có cảnh báo block
rate, HTML thô tra được trong MinIO cho một probe bất kỳ, `stock_confidence` có cả `exact`
lẫn `capped`.
