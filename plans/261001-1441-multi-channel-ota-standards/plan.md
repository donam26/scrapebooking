# Đa kênh OTA theo chuẩn D1–D12

Ngày: 2026-10-01. Nguồn: `plans/reports/research-261001-1428-multi-channel-ota-critique-standards.md`.
Chốt với người dùng: làm **toàn bộ**; proxy `160.250.166.88:20789` (VN, xoay IP); ivivu là nhu cầu thật; chưa tính ngân sách; **VND cố định**. Làm chồng lên working tree, không commit (giống wave1).

## Quyết định thiết kế khi triển khai
- **Khoá listing = (hotel_id, channel)**, không thêm `listing_id` vào bảng quan sát. Mỗi run thuộc **một kênh** (`scan_runs.channel`) nên `scan_jobs`/`probes`/`hotel_date_snapshots` giữ nguyên khoá; bảng cần khoá theo kênh thêm cột `channel` (`room_types`, `hotel_date_metrics`, `availability_events`, `room_snapshots`). Ít đổi code/API (route vẫn theo `hotel_id`), tương đương listing_id vì `listings` UNIQUE(hotel_id, channel).
- `listings` giữ URL/định danh mỗi kênh; `hotels.booking_*` chuyển sang `listings` rồi bỏ cột.
- Tiền tệ là **cấu hình toàn cục** `SCAN_CURRENCY=VND` (listing dùng chung giữa tenant nên không thể theo tenant).
- Năng lực kênh nằm trong code (`app/channels/registry.py`); tạm dừng kênh (tự ngắt) nằm trong Redis.
- Chế độ list (D6) **hoãn**: chưa cần khi chưa bị chặn; property mode cho mọi kênh trước.

## Phase
| # | Phase | Trạng thái |
|---|---|---|
| 1 | Vận hành: proxy mới, nhiều proxy, kiểm tra proxy, cảnh báo operator qua email, cờ thuế Booking | done |
| 2 | Hợp đồng kênh + registry + dời Booking vào adapter | done |
| 3 | Schema 0007 (listings, channel, demand signals, reference_channel, horizon 90) + chuyển toàn bộ backend | done (deploy 01/10 15:43) |
| 4 | Adapter Agoda, ivivu, Trip.com (+ spike Traveloka, Mytour, Expedia) | done: Agoda, iVIVU, Trip.com, Mytour; Traveloka/Expedia chỉ urls.py (chặn bot) |
| 5 | Worker theo kênh: hàng đợi, ngân sách Redis, tự ngắt, docker compose | done |
| 6 | Vòng đời listing: verify, gợi ý chéo kênh, API | done |
| 7 | Phân tích chéo kênh: channel_closed, parity_gap, tín hiệu cầu → email/bản tin | done |
| 8 | Dashboard đa kênh | done |
| 9 | Quét theo tầng + horizon 90 | done |
| 10 | Kiểm thử, chạy thật tenant 9 đa kênh, cập nhật docs, review độc lập | done |

Chi tiết từng phase: `phase-XX-*.md`. Báo cáo spike: `reports/`.

## Kiểm thử
`uv run pytest` (unit + integration, Postgres :55432), `ruff`, `mypy`; dashboard `npm run typecheck && npm run lint`; `make openapi` + `npm run gen:api`; chạy thật qua docker sau khi rebuild image.
