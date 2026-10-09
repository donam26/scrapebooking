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

Quét trang công khai trên **Booking.com** (kênh duy nhất) của khách sạn khách hàng và đối thủ 3 lần mỗi ngày (06:00, 14:00, 22:00 mặc định, cấu hình 1–8 mốc), lưu số phòng còn lại theo loại phòng (kèm mức tin cậy và phạm vi) và giá theo từng ngày lưu trú trong 90 ngày tới (quét theo tầng: 14 đêm gần mọi lượt, xa hơn thưa dần), phát hiện sự kiện hết phòng / có phòng lại / giảm phòng / đổi giá cùng phòng + gói / không nhận khách ngày đến / số đêm tối thiểu / khuyến mãi, sinh bản tin AI hằng ngày có bằng chứng bấm được, gửi email cảnh báo, và đặt occupancy thật từ PMS cạnh đối thủ.

Thành công: khách sạn ra quyết định giá mỗi sáng dựa trên dữ liệu thị trường thật thay vì đoán.

## Positioning

- Đo **số phòng còn lại** của đối thủ trên Booking.com, không chỉ giá. Minh bạch mức tin cậy: `exact` (kênh báo số chính xác), `capped` (ít nhất N, gồm "còn N phòng có giá này"), `hidden`, `sold_out`. Không đoán số khi không có.
- Đọc calendar trước để biết số đêm tối thiểu, tránh báo "hết phòng" sai.
- Bản tin AI chỉ nêu điều có bằng chứng trong dữ liệu; điểm nổi bật không có bằng chứng bị loại và ghi lại.
- Occupancy PMS (CSV/Excel từ ezCloud, Newway…) đặt cạnh compset.
- Thứ chúng tôi bán là **tín hiệu theo từng đối thủ**, không phải một chỉ số tổng: còn/hết/sắp hết phòng, khuyến mãi, hạn chế (số đêm tối thiểu, không nhận khách ngày đến) của từng khách sạn trên Booking.com; giao diện và bản tin tiếng Việt; tin cảnh báo qua email, Zalo ZNS, webhook.
- Tên chỉ số theo chuẩn nghề revenue: **giá niêm yết** (advertised rate, giá chào bán thấp nhất) ≠ ADR; **chỉ báo lấp đầy ≈ trên Booking.com** (thử nghiệm, kèm sai số so PMS) ≠ occupancy; "so các tuần trước (cùng thứ)" ≠ cùng kỳ năm trước. ADR, RevPAR, công suất chỉ dùng cho số PMS của chính khách sạn. Giá đối thủ luôn là trung vị; dưới 4 đối thủ quan sát được thì chỉ hiện x/N kèm "mẫu nhỏ". "Thị trường" dành cho số liệu cả khu vực; nhóm đối thủ gọi là compset.

## Operating Context

Dashboard tenant theo giao diện OTARadar (thanh trên xanh, tab ngang; dữ liệu Booking.com; Bảng điều khiển, Đối thủ, Giá chọn được đêm bắt đầu bất kỳ và 14/30/60 đêm để xem trước dịp lễ, Tết). Quyết định lên trước: tab đầu là **Hôm nay**, đầu Hôm nay và Bảng điều khiển là thẻ "Việc cần làm hôm nay" (gợi ý giá kèm giá mục tiêu bằng VND và cơ sở giá, đối thủ hết phòng đêm nay, đêm căng trong 14 đêm). Bảng điều khiển: toàn cảnh compset, đối thủ hết/sắp hết x/N, giá niêm yết TB (trung vị) đối thủ, chỉ báo lấp đầy kèm sai số so PMS, mức căng thị trường hiện tại (hai nguồn tách riêng, không phải dự báo), xu hướng compset, cảnh báo, khách sạn của bạn, trạng thái dữ liệu. Đối thủ (thẻ từng khách sạn, giá đối thủ so với giá bạn theo quy ước (+) đắt hơn/(−) rẻ hơn; chi tiết khách sạn: ≈ phòng còn giảm, giá đổi 7 ngày, dòng thời gian thay đổi; chi tiết đêm: giá Booking.com và điều kiện gói, từng loại phòng, lịch sử), Phòng trống (heatmap khách sạn × 16 đêm, dấu ngày lễ, thay đổi 24 giờ, chỉ báo lấp đầy; tải CSV), Giá & định giá (xu hướng từng khách sạn và trung vị đối thủ, vị trí giá so trung vị, heatmap giá có đơn vị, tình báo cạnh tranh; mọi giá hoặc giá hoàn huỷ), Terminal+ (chỉ báo khu vực hoặc compset, thời tiết OpenWeather, doanh thu PMS 14 ngày khi đã nhập PMS, lịch ngày lễ 12 tháng, nhịp đặt phòng và gợi ý giá có lý do với "Đã áp dụng/Bỏ qua"), Bản tin (bản tin AI và nhật ký thay đổi, tải CSV), Lịch sử quét, Cài đặt (thêm khách sạn bằng URL Booking.com, giờ quét, sự kiện địa phương, thông báo email, nhập PMS, người dùng). "Cập nhật lúc" ở mọi màn là lượt quét compset gần nhất đã xong và có dữ liệu; lượt mới nhất không thu được gì thì cờ đỏ/vàng. Operator onboard từng tenant; chưa có self-serve đăng ký, chưa có billing.

## Capabilities and Constraints

- Thị trường cả khu vực (từ 02/10, chỉ Booking.com): tenant chọn thành phố/quận; mỗi ngày đọc số khách sạn còn phòng từng đêm, ghép dần danh sách mọi khách sạn (điểm, số đánh giá, hạng sao, quận, giá) và quét chi tiết top N khách sạn để ước tính phòng còn/công suất cả khu vực. Booking không cho phân trang trang kết quả nên danh sách được ghép qua nhiều lát cắt; giá khu vực là mẫu cho tới khi phủ ≥98%.
- Kênh quét: **chỉ Booking.com** (từ 09/10/2026 bỏ Agoda, iVIVU, Trip.com, Mytour, Traveloka, Expedia cùng mọi tính năng chéo kênh: parity, đóng bán trên một kênh, tín hiệu cầu của kênh). Số phòng còn là phần Booking.com hiển thị, không phải tổng phòng khách sạn.
- Giá chuẩn hoá: VND cố định toàn hệ thống (không quy đổi), theo phòng/đêm, đã gồm thuế phí, sau khuyến mãi kênh tự áp (mã phải tự nhập thì không trừ); lưu kèm giá gốc, nhãn khuyến mãi, điều kiện gói (hoàn huỷ, bữa sáng).
- Probe với 2 người lớn; loại phòng chỉ cho 1 người không xuất hiện.
- Thông báo qua email (SMTP), Zalo ZNS (cần OA xác thực + template duyệt) và webhook; đăng ký theo người, giờ im lặng, trần tin/ngày: cảnh báo gom một tin mỗi mốc quét, bản tin sáng, báo cáo tuần thứ Hai 08:00, báo dữ liệu cũ.
- PMS: import CSV/Excel có ánh xạ cột; adapter API cho ezCloud, Newway, Hotel Link, Smile chưa có.
- Không đăng nhập kênh nào, không lấy dữ liệu cá nhân, chỉ trường cần thiết (payload thô cắt bớt thông tin đối tác), nhịp độ lịch sự với ngân sách request/phút và tự ngắt khi bị chặn.

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
