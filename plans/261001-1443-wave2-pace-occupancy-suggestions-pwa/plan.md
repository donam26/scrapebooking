# Đợt 2: ước tính công suất, nhịp đặt phòng, gợi ý giá, PWA "Hôm nay"

Ngày: 2026-10-01. Nguồn: `plans/reports/research-261001-1202-competitor-hotel-rate-intelligence.md` (mục 7, đợt 2).
Người dùng: "làm chuẩn hết các đợt, chưa commit". Cấu hình email tạm bỏ qua.

## Phối hợp với phiên f7 (đa kênh, `plans/261001-1441-multi-channel-ota-standards/`)
- Đợt 3 (đa kênh, parity, tín hiệu cầu, dashboard đa kênh) **thuộc f7**, không làm trùng.
- Đợt 2 viết **file mới** (`app/market/`, router `market.py`, migration `0008_market.py` sau `0007` của f7, route `/pace`, `/today`). File dùng chung chỉ sửa 1–3 dòng: `api/main.py`, `jobs/settings.py`, `app-shell.tsx`, `lib/api.ts`.
- Dùng cột `channel` của f7 (`room_snapshots`, `hotel_date_snapshots`, `scan_runs`, `hotel_date_metrics`) và `tenants.reference_channel`.
- Integration test chạy trên DB riêng `scrapebooking_test_de`.

## Phase
| # | Phase | Trạng thái |
|---|---|---|
| 1 | Ước tính công suất OTA từ số phòng còn (bảng `occupancy_estimates`, cron bù) | done |
| 2 | Nhịp đặt phòng so cùng kỳ + đối chiếu PMS | done |
| 3 | Gợi ý giá theo luật + ghi nhận "Đã áp dụng / Bỏ qua" | done |
| 4 | API `/market/*` + màn "Nhịp đặt phòng" | done |
| 5 | PWA: manifest, icon, màn "Hôm nay" cho điện thoại | done |

## Cách tính (công khai trong UI)
- **Tồn phòng nhìn thấy (inventory)** mỗi loại phòng = lớn nhất từng thấy trong 30 ngày (số chính xác hoặc mức sàn "ít nhất"). Là cận dưới của phân bổ trên OTA, không phải tổng phòng khách sạn.
- **Phòng còn** mỗi lần quét: chính xác = điểm; "ít nhất N" = [N, inventory]; ẩn số = [1, inventory]; loại phòng không còn bán = 0; khách sạn hết phòng = 0 (có thể là đóng bán).
- **Công suất ước tính** = 1 − phòng còn / inventory, dạng khoảng [thấp, cao]. **Độ phủ** = phần inventory biết chắc (chính xác hoặc 0). Chỉ hiện con số khi độ phủ ≥ 50%; dưới đó ghi "Booking không lộ đủ số".
- **Nhịp so cùng kỳ** ở cùng số ngày trước khi đến: công suất hiện tại − trung vị các đêm tham chiếu (cùng thứ, 1–8 tuần trước, cùng loại lễ/không lễ, ≥ 2 đêm).
- **Đối chiếu PMS**: với khách sạn của bạn, sai số tuyệt đối trung bình giữa ước tính và công suất PMS.
- **Gợi ý giá**: luật cố định, mỗi gợi ý kèm lý do là số liệu; không tự đẩy giá.

## Ngoài phạm vi (ghi rõ lý do)
- Ảnh chụp trang làm bằng chứng: trái cam kết thương hiệu (không dùng nhận diện Booking.com) và rủi ro ToS; thay bằng trích đoạn văn bản sau khi f7 xong adapter.
- Gợi ý compset khi onboarding: cần chức năng tìm kiếm của adapter (f7 phase 4/6).
- Web push: cần khoá VAPID và hạ tầng như SMTP (người dùng tạm hoãn cấu hình).

## Kiểm thử
Unit cho hàm thuần (ước tính, nhịp, đối chiếu, gợi ý); integration API trên DB riêng; dashboard typecheck/lint + ảnh chụp desktop/mobile.
