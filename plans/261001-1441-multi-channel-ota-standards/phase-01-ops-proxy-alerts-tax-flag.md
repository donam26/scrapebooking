# Phase 1 — Vận hành
- `.env` `PROXY_URL_TEMPLATE` → proxy mới (đã làm, run 26 ok 30/30 đêm/khách sạn).
- `PROXY_URL_TEMPLATE` nhận nhiều proxy cách nhau dấu phẩy; `StaticProxyProvider` xoay vòng.
- `app/ops/proxy_check.py`: gọi ipify qua từng proxy; scheduler kiểm tra mỗi 15 phút, lỗi → cảnh báo (throttle); CLI `check-proxy`.
- `EmailAlerter` (SMTP sẵn có) khi đặt `OPS_ALERT_EMAILS`; vẫn ghi log.
- Parser Booking lưu `taxes_included` (`b_is_all_included` / "Includes taxes and charges").
