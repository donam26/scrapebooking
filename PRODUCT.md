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

- Đo **số phòng còn lại** của đối thủ trên Booking.com, không chỉ giá. Minh bạch mức tin cậy: `exact` (badge hoặc dropdown dưới trần), `capped` (ít nhất N: dropdown chạm trần 10/loại phòng), `hidden`, `sold_out`. Cả khách sạn: "N" chỉ khi biết chắc, còn lại "N–M" hoặc "≥N" (thang nbRooms của lịch Booking đo tổng tới 100 phòng). Không đoán số khi không có.
- **Đối thủ có bao nhiêu phòng**: số phòng công bố lưu kèm nguồn (URL, thời điểm) và "Booking từng mở bán ≥N phòng/đêm" suy từ dữ liệu; hai số tách nhãn, cảnh báo khi mâu thuẫn.
- Đọc calendar trước để biết số đêm tối thiểu, tránh báo "hết phòng" sai.
- Bản tin AI chỉ nêu điều có bằng chứng trong dữ liệu; điểm nổi bật không có bằng chứng bị loại và ghi lại.
- Occupancy PMS (CSV/Excel từ ezCloud, Newway…) đặt cạnh compset.
- Thứ chúng tôi bán là **tín hiệu theo từng đối thủ**, không phải một chỉ số tổng: còn/hết/sắp hết phòng, khuyến mãi, hạn chế (số đêm tối thiểu, không nhận khách ngày đến) của từng khách sạn trên Booking.com; giao diện và bản tin tiếng Việt; tin cảnh báo qua email, Zalo ZNS, webhook.
- Tên chỉ số theo chuẩn nghề revenue: **giá niêm yết** (advertised rate, giá chào bán thấp nhất) ≠ ADR; **chỉ báo lấp đầy ≈ trên Booking.com** (thử nghiệm, kèm sai số so PMS) ≠ occupancy; "so các tuần trước (cùng thứ)" ≠ cùng kỳ năm trước. ADR, RevPAR, công suất chỉ dùng cho số PMS của chính khách sạn. Giá đối thủ luôn là trung vị; dưới 4 đối thủ quan sát được thì chỉ hiện x/N kèm "mẫu nhỏ". "Thị trường" dành cho số liệu cả khu vực; nhóm đối thủ gọi là compset.

## Operating Context

Dashboard tenant theo giao diện OTARadar (thanh trên xanh; từ 24/10 có **5 tab theo công việc**, trên điện thoại là thanh đáy). Dữ liệu lấy từ Booking.com. Chi tiết trong DESIGN.md và `plans/261024-0007-tenant-admin-ux-overhaul/`.

1. **Hôm nay** (trang mở đầu, gộp Bảng điều khiển cũ):
   - "Việc cần làm hôm nay": tối đa 5 việc trong 14 đêm. Gồm gợi ý giá có giá mục tiêu VND, một câu lý do bằng lời và nút "Tôi đã đổi giá"/"Bỏ qua" ngay trên thẻ; đối thủ hết phòng đêm nay; đêm căng.
   - Dải 14 đêm bạn so với đối thủ, thay đổi 24 giờ, bản tin, khách sạn của bạn đêm nay.
2. **Lịch giá & phòng:** một lưới khách sạn × đêm, chuyển Phòng còn / Giá / Chênh với bạn. Có bộ chọn đêm bắt đầu và 14/30/60 đêm để xem trước dịp lễ, Tết; chọn cơ sở giá; hàng công suất PMS khi đã nhập. Bấm ô mở chi tiết đêm: cùng đêm của mọi khách sạn, gợi ý của đêm, từng loại phòng, lịch sử.
3. **Đối thủ:**
   - thẻ từng khách sạn với quy ước (+) đắt hơn / (−) rẻ hơn bạn, kèm "7 ngày qua";
   - Khuyến mãi & hạn chế;
   - Tìm khách sạn để theo dõi;
   - trang đối thủ có tóm tắt 7 ngày và nhật ký.
4. **Thị trường:** mức căng khu vực 14 đêm, hôm nay trong khu vực, lịch sự kiện và ngày lễ 12 tháng.
5. **Báo cáo:** Bản tin AI, Nhật ký thay đổi (tải CSV), Kết quả gợi ý, Nhịp đặt phòng (PMS/OTB).

**⚙ Cài đặt:** khách sạn và đối thủ bằng URL Booking.com, cảnh báo và người nhận, người dùng, PMS, chiến lược giá; phần Nâng cao gồm giờ quét, khu vực thị trường, sự kiện địa phương.

**Độ mới dữ liệu** nằm trên thanh trên ở mọi màn: lần đọc Booking.com thành công cuối. Dữ liệu cũ quá một chu kỳ quét thì app tạm dừng gợi ý giá và khoá nút ghi quyết định.

Operator onboard từng tenant; chưa có self-serve đăng ký, chưa có billing.

## Capabilities and Constraints

- Thị trường khu vực (từ 02/10, chỉ Booking.com; bản quận/bán kính từ 16/10): tenant chọn thành phố/quận/địa danh của Booking hoặc bán kính 1/3/5 km quanh khách sạn của mình, lọc theo phân khúc (loại chỗ ở như khách sạn/resort/căn hộ khách sạn). Mỗi ngày, từng đêm: số chỗ còn phòng, % đã kín Booking tự tính (khi không lọc), danh sách đủ mọi khách sạn còn phòng (tới 1.000) với giá và hạng hiển thị, và **thang phòng trống**: số khách sạn còn bán được ≥1/5/10/20/30 phòng cùng lúc (cận dưới phòng Booking còn bán, không phải tồn kho), khoảng phòng còn của từng khách sạn ở 14 đêm gần; khách sạn của bạn đặt cạnh thị trường (phòng còn, phân vị giá, hạng). Quét chi tiết top N khách sạn vẫn có, tuỳ chọn.
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
