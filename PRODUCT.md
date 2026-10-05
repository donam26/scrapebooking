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

Quét trang công khai của khách sạn khách hàng và đối thủ trên nhiều kênh OTA (Booking.com, Agoda, iVIVU, Trip.com, Mytour) 3 lần mỗi ngày (06:00, 14:00, 22:00 mặc định, cấu hình 1–8 mốc), lưu số phòng còn lại theo loại phòng (kèm mức tin cậy và phạm vi) và giá theo từng ngày lưu trú trong 90 ngày tới (quét theo tầng: 14 đêm gần mọi lượt, xa hơn thưa dần), phát hiện sự kiện hết phòng / có phòng lại / giảm phòng / đổi giá / đóng bán trên một kênh / khách sạn rẻ hơn trên một kênh, sinh bản tin AI hằng ngày có bằng chứng bấm được, gửi email cảnh báo, và đặt occupancy thật từ PMS cạnh đối thủ.

Thành công: khách sạn ra quyết định giá mỗi sáng dựa trên dữ liệu thị trường thật thay vì đoán.

## Positioning

- Đo **số phòng còn lại** của đối thủ trên từng kênh, không chỉ giá. Minh bạch mức tin cậy: `exact` (kênh báo số chính xác), `capped` (ít nhất N, gồm "còn N phòng có giá này"), `hidden`, `sold_out`. Không đoán số khi không có.
- So cùng một khách sạn giữa các kênh: phát hiện đóng bán trên một kênh, và giá khách sạn của bạn bị bán rẻ hơn ở kênh nào (lộ giá bán sỉ qua kênh bán lại như iVIVU, Mytour).
- Đọc calendar trước để biết số đêm tối thiểu, tránh báo "hết phòng" sai.
- Bản tin AI chỉ nêu điều có bằng chứng trong dữ liệu; điểm nổi bật không có bằng chứng bị loại và ghi lại.
- Occupancy PMS (CSV/Excel từ ezCloud, Newway…) đặt cạnh compset.

## Operating Context

Dashboard tenant theo giao diện OTARadar (thanh trên xanh, 8 tab ngang; mọi màn hình dữ liệu có bộ chọn kênh, mặc định kênh tham chiếu của tenant): Bảng điều khiển (toàn cảnh compset đêm nay, mức nén, ADR/RevPAR/công suất compset ước tính, dự báo cầu 14 đêm, xu hướng thị trường, cảnh báo, khách sạn của bạn, trạng thái dữ liệu), Đối thủ (thẻ từng khách sạn; bấm vào chi tiết khách sạn: pickup, tốc độ, giá đổi 7 ngày, dòng thời gian sự kiện; chi tiết đêm: so kênh, tín hiệu cầu, từng loại phòng, lịch sử), Phòng trống (heatmap khách sạn × 16 đêm đỏ→xanh, thay đổi 24 giờ, tổng thị trường, phân tích công suất; tải CSV), Giá & định giá (xu hướng 30 đêm từng khách sạn, vị trí giá so trung vị, heatmap giá, tình báo cạnh tranh; mọi giá hoặc giá hoàn huỷ), Terminal+ (chỉ báo thị trường, thời tiết OpenWeather, tín hiệu đặt phòng kênh công bố, doanh thu PMS 14 ngày, lịch ngày lễ 12 tháng, nhịp đặt phòng và gợi ý giá có lý do với "Đã áp dụng/Bỏ qua"), Bản tin (bản tin AI và sự kiện thay đổi, tải CSV), Lịch sử quét, Cài đặt (thêm khách sạn bằng URL của bất kỳ kênh hỗ trợ, xác nhận gợi ý cùng khách sạn trên kênh khác, kênh tham chiếu, giờ quét, thông báo email, nhập PMS, người dùng). Màn "Hôm nay" cho điện thoại vẫn còn (mở từ menu trợ giúp). Operator onboard từng tenant; chưa có self-serve đăng ký, chưa có billing.

## Capabilities and Constraints

- Thị trường cả khu vực (từ 02/10, chỉ Booking.com): tenant chọn thành phố/quận; mỗi ngày đọc số khách sạn còn phòng từng đêm, ghép dần danh sách mọi khách sạn (điểm, số đánh giá, hạng sao, quận, giá) và quét chi tiết top N khách sạn để ước tính phòng còn/công suất cả khu vực. Booking không cho phân trang trang kết quả nên danh sách được ghép qua nhiều lát cắt; giá khu vực là mẫu cho tới khi phủ ≥98%.
- Kênh quét được: Booking.com, Agoda, iVIVU, Trip.com, Mytour (mỗi kênh một listing của khách sạn). Traveloka và Expedia chặn bot mạnh (DataDome, Akamai): nhận diện URL nhưng chưa quét.
- Số phòng còn là của từng kênh, không cộng giữa kênh. iVIVU không công bố số phòng (chỉ còn/hết); Trip.com và Mytour báo theo mức giá (ít nhất N).
- Giá chuẩn hoá: VND cố định toàn hệ thống (không quy đổi), theo phòng/đêm, đã gồm thuế phí, sau khuyến mãi kênh tự áp (mã phải tự nhập thì không trừ); lưu kèm giá gốc, nhãn khuyến mãi, nguồn bán. Heatmap/compset theo một kênh; không trộn giá các kênh vào một trung vị.
- Tín hiệu cầu do kênh công bố ("đặt 13 lần trong 24 giờ", "đã bán 2 phòng/24h", "lần đặt gần nhất cách đây N phút") là thông điệp marketing (Mytour còn chia thời gian cho 5 khi hiển thị): luôn hiện kèm nguồn, không coi là số đặt phòng thật.
- Probe với 2 người lớn; loại phòng chỉ cho 1 người không xuất hiện.
- Thông báo chỉ qua email (SMTP): cảnh báo gom một email mỗi mốc quét (mọi kênh), gồm khách sạn của bạn rẻ hơn hẳn trên một kênh, bản tin sáng, báo cáo tuần thứ Hai 08:00. Chưa có Zalo/Telegram, chưa có giờ im lặng.
- PMS: import CSV/Excel có ánh xạ cột; adapter API cho ezCloud, Newway, Hotel Link, Smile chưa có.
- Không đăng nhập kênh nào, không lấy dữ liệu cá nhân, chỉ trường cần thiết (payload thô cắt bớt thông tin đối tác), nhịp độ lịch sự với ngân sách request/phút theo kênh và tự ngắt kênh khi bị chặn.

## Brand Commitments

- Tên sản phẩm: **OTARadar** (đổi từ ScrapeBooking ngày 2026-10-02, theo giao diện mẫu khách hàng chọn trong `job/*.jpg`). Mã nguồn, package và tên service vẫn giữ "scrapebooking".
- Ngôn ngữ giao diện: tiếng Việt.
- Không dùng logo hay nhận diện của Booking.com hay kênh OTA nào; chỉ nhắc tên để mô tả nguồn dữ liệu.
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
