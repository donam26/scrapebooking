# Đợt 1: tín hiệu quyết định + cảnh báo email

Ngày: 2026-10-01. Nguồn: `plans/reports/research-261001-1202-competitor-hotel-rate-intelligence.md` (mục 7, đợt 1).
Chốt với người dùng: chỉ kênh **Email** (Telegram/Zalo để sau); làm **toàn bộ đợt 1**; làm chồng lên working tree, **không commit**.

## Mục tiêu
Biến dữ liệu đang có thành quyết định buổi sáng và **đẩy** tới khách sạn, không bắt họ mở dashboard.

## Phase

| # | Phase | Trạng thái | File |
|---|---|---|---|
| 1 | Định vị giá, thứ hạng, ngày lễ, câu giải thích từng đêm | done | [phase-01](phase-01-price-position-holidays-night-reason.md) |
| 2 | So giá cùng điều kiện (giá hoàn huỷ) | done | [phase-02](phase-02-refundable-price-basis.md) |
| 3 | Rule cảnh báo + gửi email + màn Thông báo | done | [phase-03](phase-03-email-alerts-notification-settings.md) |
| 4 | Xuất CSV + báo cáo tuần qua email | done | [phase-04](phase-04-csv-export-weekly-report.md) |

Phụ thuộc: 4 dùng hạ tầng email của 3. 1 và 2 độc lập.

## Nguyên tắc UX (chuyển thể mẫu đối thủ vào design system hiện có)
- **Lighthouse tô màu ô lịch theo % chênh giá** → KHÔNG tô lại ô dải (vi phạm Quy tắc Bốn dấu: màu ô = mức tin cậy phòng còn). Thay bằng một **hàng số "Giá bạn so trung vị"** trong thẻ Thị trường, cùng lưới cột, để "dò một đêm" vẫn sáng đúng một cột.
- **STR rank / Lighthouse hover** → thứ hạng "rẻ thứ k/n" đưa vào bảng đọc và dải số đo, không thêm hàng thứ hai (giữ mật độ).
- **Lighthouse events calendar** → chấm mực 4px dưới ngày trên trục + tên lễ ở đầu bảng đọc và chi tiết đêm. Không dùng tím (tím = bấm/chọn), không dùng vàng (vàng = chính xác).
- **RoomPriceGenie "vì sao giá này"** → một câu sự thật ghép từ số liệu (không phải gợi ý giá) ở bảng đọc và đầu chi tiết đêm. Nguyên tắc sản phẩm 1: chỉ nói điều dữ liệu chứng minh.
- **Email digest/alert** → gom theo lượt quét (một email/lượt/tenant), mỗi dòng đọc thành câu như Dòng sự kiện, có liên kết sâu tới đêm/sự kiện.
- Nhãn viết thường, số thẳng cột, không hex rời trong app (màu mới thành biến `--sb-*`).

## Kiểm thử
- Backend: unit cho hàm thuần (rank, rule cảnh báo, render email, báo cáo tuần), integration cho API mới (Postgres test ở :55432). `ruff`, `mypy`, `php -l` không áp dụng (Python/TS).
- Dashboard: `npm run typecheck`, `npm run lint`, ảnh chụp Playwright desktop + mobile.
- OpenAPI: `make openapi` + `npm run gen:api` khi schema đổi.

## Ngoài phạm vi (đợt sau)
Telegram/Zalo, giờ im lặng, occupancy ước tính, pacing, gợi ý giá, đa OTA.

## Review (code-reviewer, 01/10) và đã sửa
- Thử lại email: giành dòng bằng UPDATE có điều kiện (cron chạy chồng không gửi trùng), chờ 5 phút → 30 phút → 2 giờ (tối đa 4 lần), dòng `sending` treo quá 10 phút được gửi lại, email thử không thử lại.
- Lỗi của một tenant chỉ ghi log, không chặn tenant khác. Gửi song song tới người nhận.
- Tiêu đề email gộp khoảng trắng (tên có xuống dòng) và cắt ≤ 200 ký tự.
- CSV: ô chữ bắt đầu `= + - @` được thêm `'` (chống chèn công thức); CSV sự kiện báo rõ khi bị cắt ở 2.000 dòng.
- Báo cáo tuần bù trong thứ Ba; thêm người nhận kiểm tenant tồn tại (404 thay vì 409 sai).
- A11y: hàng % so trung vị có nhãn cho trình đọc màn hình; công tắc không mất focus khi đang lưu.
- Giữ nguyên: không gửi bù thông báo `skipped` (đã ghi trong docs/operations.md mục 5b).
- Kết quả: 317 test backend qua; ruff, mypy, tsc, eslint sạch.
