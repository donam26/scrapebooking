# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Khách sạn khách hàng (tenant):** chủ khách sạn, giám đốc kinh doanh, revenue manager của khách sạn tại Việt Nam. Mỗi sáng họ cần biết đối thủ trong compset còn bao nhiêu phòng, giá bao nhiêu, ngày nào sắp kín, để quyết định giá và phân phối của chính mình.
- **Vai trò trong hệ thống:** `tenant_admin` (cấu hình watchlist, lịch quét, nhập PMS, người dùng), `viewer` (chỉ xem).
- **Operator:** đơn vị vận hành dịch vụ ScrapeBooking cho nhiều tenant; tạo tenant, tài khoản, theo dõi sức khoẻ scraper.
- **Khách vãng lai:** khách sạn chưa dùng hệ thống, đến trang giới thiệu để hiểu dịch vụ và liên hệ.

## Product Purpose

Quét trang công khai của khách sạn khách hàng và đối thủ trên Booking.com 3 lần mỗi ngày (06:00, 14:00, 22:00 mặc định, cấu hình 1–8 mốc), lưu số phòng còn lại theo loại phòng (kèm mức tin cậy) và giá theo từng ngày lưu trú trong 30 ngày tới (horizon 1–90), phát hiện sự kiện hết phòng / có phòng lại / giảm phòng / đổi giá, sinh bản tin AI hằng ngày có bằng chứng bấm được, và đặt occupancy thật từ PMS cạnh đối thủ.

Thành công: khách sạn ra quyết định giá mỗi sáng dựa trên dữ liệu thị trường thật thay vì đoán.

## Positioning

- Đo **số phòng còn lại** của đối thủ, không chỉ giá. Minh bạch mức tin cậy: `exact` (badge "Only X rooms left"), `capped` (ít nhất N), `hidden`, `sold_out`. Không đoán số khi không có.
- Đọc calendar trước để biết số đêm tối thiểu, tránh báo "hết phòng" sai.
- Bản tin AI chỉ nêu điều có bằng chứng trong dữ liệu; điểm nổi bật không có bằng chứng bị loại và ghi lại.
- Occupancy PMS (CSV/Excel từ ezCloud, Newway…) đặt cạnh compset.

## Operating Context

Dashboard 6 màn hình tenant: Tổng quan (heatmap khách sạn × 30 ngày, khách sạn của bạn trên cùng, dải compset), Chi tiết ngày (từng loại phòng, lịch sử phòng còn và giá), Chi tiết khách sạn (chỉ số pickup, tốc độ, giá đổi 7 ngày, dòng thời gian sự kiện), Bản tin, Sự kiện, Cài đặt (thêm khách sạn bằng URL Booking, giờ quét, nhập PMS, người dùng). Operator onboard từng tenant; chưa có self-serve đăng ký, chưa có billing.

## Capabilities and Constraints

- Nguồn dữ liệu duy nhất hiện tại: Booking.com. Chưa có Agoda, Expedia.
- Giá hiển thị theo tiền tệ nước của khách sạn, không quy đổi.
- Probe với 2 người lớn; loại phòng chỉ cho 1 người không xuất hiện.
- Chưa có thông báo email/chat cho tenant; bản tin xem trên dashboard.
- PMS: import CSV/Excel có ánh xạ cột; adapter API cho ezCloud, Newway, Hotel Link, Smile chưa có.
- Không đăng nhập Booking, không lấy dữ liệu cá nhân, chỉ trường cần thiết, nhịp độ lịch sự.

## Brand Commitments

- Tên sản phẩm: **ScrapeBooking**.
- Ngôn ngữ giao diện: tiếng Việt.
- Không dùng logo hay nhận diện của Booking.com; chỉ nhắc tên để mô tả nguồn dữ liệu.
- Phong cách trang giới thiệu: chuẩn landing SaaS theo kiểu Hostinger (người dùng chọn ngày 2026-09-25, sau khi từ chối hướng "tranh in đá Đông Dương"). Không dùng logo, tên hay nội dung của Hostinger; không dùng số đánh giá, cam kết hoàn tiền hay giá khi chưa có thật.

## Evidence on Hand

- Không có khách hàng công khai, testimonial, logo đối tác, số liệu hiệu quả, báo chí. Không được bịa.
- Không hiển thị giá: "Liên hệ báo giá".
- Hành động chính cho khách vãng lai: liên hệ trực tiếp (Zalo / điện thoại / email). Thông tin liên hệ thật: **chưa cung cấp**, dùng placeholder có đánh dấu.
- Ảnh: Unsplash (giấy phép Unsplash), lưu trong `dashboard/public/landing/` kèm nguồn.
- Dữ liệu minh hoạ trên trang giới thiệu là dữ liệu tổng hợp, phải ghi rõ.

## Product Principles

1. Chỉ nói điều dữ liệu chứng minh được; mức tin cậy luôn hiện ra.
2. Phục vụ quyết định buổi sáng của khách sạn, không phải báo cáo cho đẹp.
3. Khách sạn của bạn luôn đứng cạnh đối thủ, không tách rời.
4. Vận hành lịch sự với nguồn dữ liệu công khai.
