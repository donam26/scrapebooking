# Competitive analysis: SMB rate shoppers/RMS + công cụ miễn phí của OTA + Vietnam/SEA

Ngày: 2026-10-01. Phương pháp: WebSearch/WebFetch ~17 call. Độ tin cậy: trung bình. Nhiều trang (SiteMinder, Cloudbeds, Hotel Link, Newway, Smile) không fetch được chi tiết; mục nào ghi "chưa xác minh" = không có bằng chứng trực tiếp. Giá lấy từ trang tổng hợp bên thứ ba, có thể lệch.

---
## 1. SMB rate shoppers / RMS cho khách sạn độc lập

### 1.1 RoomPriceGenie (RPG) - RMS tự động cho independent
- Định vị: "set and forget" pricing cho khách sạn nhỏ. Giá: từ ~$119/feature/tháng, free trial; onboarding miễn phí. (Capterra: https://www.capterra.com/p/176568/RommPriceGenie/ ; HTR: https://hoteltechreport.com/revenue-management/revenue-management-systems/roompricegenie)
- Kênh/data: competitor rates nhiều lần/ngày, event calendar, booking pace + forecast occupancy, STR. Giá đề xuất cập nhật 4 lần/ngày, 365 ngày.
- Flow: (1) kết nối PMS/channel manager (~2 giờ setup) -> (2) đặt min/max, chiến lược (day-of-week, tháng, room type, lead time, budget) -> (3) mỗi ngày mở dashboard xem giá đề xuất + giải thích lý do -> (4) approve 1 click hoặc bật auto-upload -> (5) push về PMS/CM -> (6) nhận alert khi có "surge event".
- UX đáng học: price explanation (vì sao giá này), one-click approve, manual override, alert surge. Ghi nhận tiết kiệm "10+ giờ/tuần".
- Điểm yếu: review gần như toàn 5 sao (13 review Capterra) -> ít tín hiệu tiêu cực; cần PMS/CM integration (phụ thuộc connector); giá/feature cộng dồn.

### 1.2 SiteMinder Insights (Rate shopping / market intelligence)
- Định vị: add-on của hệ sinh thái channel manager SiteMinder (450+ distribution partners). Giá ước tính ~$4-6/phòng/tháng (HTR: https://hoteltechreport.com/revenue-management/market-intelligence-tools).
- Tính năng: so sánh giá compset, rate parity, market trend, tích hợp CM + PMS. Review: https://hoteltechreport.com/revenue-management/market-intelligence-tools/siteminder-insights
- Điểm yếu (HTR): lookback chỉ ~1 tháng bị chê ngắn; support phản hồi chậm; mạnh nhất khi đã dùng SiteMinder.
- Chưa xác minh: refresh frequency chính xác, kênh Agoda.

### 1.3 Lighthouse / Price Seeker (Paraty) / RateGain - rate shopper thuần
- Lighthouse ~$0-2/phòng/tháng (khởi điểm), live shop theo OTA, lọc room type. Price Seeker ~$1-3/phòng/tháng: báo cáo hằng ngày kèm **screenshot** làm bằng chứng. RateGain ~$2-4. (https://hoteltechreport.com/revenue-management/market-intelligence-tools ; https://hoteltechreport.com/compare/price-seeker-vs-siteminder-insights)
- Yếu: analytics nâng cao hạn chế với SMB, ít RMS depth.
- Học: screenshot evidence = tương tự "clickable evidence" của ta.

### 1.4 RateTiger Shopper (eRevMax) - mạnh APAC
- ~$69/user/tháng (HTR: https://hoteltechreport.com/revenue-management/market-intelligence-tools/ratetiger-erevmax ; Capterra SG: https://www.capterra.com.sg/software/106890/ratetiger). Phủ OTA chuẩn + kênh khu vực APAC/Middle East.
- Tính năng: BI, rate shopping, price intelligence; bán kèm channel manager RateTiger.
- Chưa xác minh: có Zalo/WhatsApp alert không (không thấy).

### 1.5 Atomize (Mews RMS)
- Từ ~EUR299/tháng; real-time rate shop + auto pricing; push giá tự động (https://hoteltechreport.com/news/atomize-real-time-price-optimization ; https://atomize.com/revenue-management-system-for-hotels/). Hướng tới khách sạn trung bình trở lên, gắn Mews. Quá đắt/quá nặng cho khách sạn nhỏ VN.

### 1.6 Lybra (Zucchetti) / Pricepoint
- Lybra ~EUR180/tháng, "Intelligent Revenue Assistant" gợi ý giá + chiến lược (https://www.capterra.com.sg/software/164592/lybra-tech). Pricepoint $129-199/tháng, hostel/hotel, fully automated dynamic pricing, không phí setup (https://pricepoint.co/dynamic-pricing-for-hostels/).
- Mô hình chung: flat/tháng, giá đề xuất + auto push.

### 1.7 Cloudbeds (Insights / PIE), eZee/Yanolja, myhotelshop, Hotel Rate Shopper, PriceLabs Hotel
- Cloudbeds: có bài/giải pháp market intelligence & rate shopper (https://www.cloudbeds.com/articles/hotel-rate-shopper/) nhưng chưa fetch được chi tiết sản phẩm PIE -> chưa xác minh.
- PriceLabs có "Hotel Rate Shopper - daily competitor data" (https://hotels.pricelabs.co/hotel-rate-shopper/): dữ liệu competitor hằng ngày (tần suất 1x/ngày), gắn dynamic pricing. 
- eZee/Yanolja, myhotelshop: chưa xác minh (không có kết quả đủ tin cậy).

### Pattern chung SMB shopper (tổng hợp)
- Giá: $1-6/phòng/tháng (shopper thuần) hoặc $119-300/tháng flat (RMS).
- Kênh: Booking + Expedia + Agoda + brand.com (rate parity). Ta chỉ có Booking.
- Refresh: 1x/ngày (rẻ) đến 4x/ngày (RPG). Ta 3x/ngày là ngang/tốt hơn bậc entry.
- Điểm khác ta: các tool này dùng **giá** là chính; **rooms-left/sold-out** là tín hiệu hiếm (Lighthouse có "availability" tuỳ gói, chưa xác minh chi tiết).
- Alert: email là chuẩn; không tìm thấy Zalo/LINE/WhatsApp native ở nhóm này (chưa xác minh toàn diện).

---
## 2. Công cụ MIỄN PHÍ của OTA (đối thủ thực sự)

### 2.1 Booking.com Extranet Analytics
Nguồn: https://partner.booking.com/en-us/learn-more/new-partner/improving-your-performance ; https://news.booking.com/en/bookingcoms-analytics-and-opportunity-centre/
- Pace report: forward-looking, so với năm trước + peer group / compset / market (compset = tối đa 10 property do chủ chọn; peer group = cùng loại/hạng sao trong điểm đến; market = toàn điểm đến). So sánh là **dữ liệu tổng hợp ẩn danh**, không thấy từng đối thủ cụ thể.
- Sales statistics, Book window, Booker insights (nguồn khách), Market insights (nhu cầu tìm kiếm khu vực), Opportunity Centre (gợi ý hành động), Genius.
- Price Performance / "compare your rates with similar properties": đo giá mình vs nhóm tương đương.
- **RateIntelligence** (Booking suite): update hằng ngày, 360 ngày forward, demand spike + rate của competitor (https://hostelmanagement.com/industry-news/booking%E2%80%99s-new-rateintelligence-tool-track-competitor-rates-and-market-demands). Chưa xác minh: hiện còn khả dụng/được mở cho khách sạn VN không và có hiển thị tên đối thủ không.
- Flow: login extranet -> Analytics -> Pace/Market -> chọn So sánh với (năm trước/peer/compset/market) -> đọc biểu đồ -> điều chỉnh giá thủ công trong Rates & Availability.
- Giới hạn: chỉ Booking; không cảnh báo sold-out/restock từng đối thủ; không per-room-type; không event timeline; không briefing; phải tự vào xem.

### 2.2 Expedia Partner Central - Rev+
Nguồn: https://www.siteminder.com/r/expedia-partner-central/ ; https://partner.expediagroup.com/en-us/industries/hotels
- Rev+: dashboard ADR/occupancy, so sánh giá với competitor đã chọn, gợi ý giá theo thị trường, demand insight (sự kiện, peak), alert chênh lệch giá. Compset 5-19 property do Expedia gán.
- Giới hạn: chỉ Expedia (thị phần VN nhỏ so với Booking/Agoda).

### 2.3 Agoda YCS / Partner Hub (rất liên quan VN)
Nguồn: https://partnerhub.agoda.com/how-do-i-manage-my-competitor-set/ ; https://partnerhub.agoda.com/what-is-the-ycs-dashboard/
- Flow compset: Partner Portal > Performance > Competitor set > Edit > + Add a competitor (cùng quốc gia) > tối thiểu 5 > Save. **Chỉ sửa 1 lần/quý**.
- Dashboard: "Your property vs competitor set" (ranking, room nights, revenue, visitors, bookings, 30 ngày), "Lowest upcoming competitor rates" so giá với nearby.
- Có app mobile YCS (https://apps.apple.com/us/app/agoda-partner-portal-ycs/id1334645772).
- Giới hạn: compset khoá theo quý; chỉ Agoda; metric tổng hợp.

### 2.4 Google Hotel Center / Hotel Insights
- Không tìm được tài liệu xác minh trong lượt này -> chưa xác minh. (Kiến thức chung: có price competitiveness/demand miễn phí cho property có feed Google; cần verify trước khi trích dẫn.)

---
## 3. Vietnam / SEA

- **ezCloud** (https://ezcloud.vn/en/) - "#1 market share in Vietnam" PMS. Sản phẩm: ezCloudhotel (PMS, app mobile), **ezRms** (https://ezcloud.vn/en/product/ezrms), ezCms (channel manager OTA/GDS).
  - ezRms: tự động điều chỉnh giá theo occupancy (theo room type hoặc toàn khách sạn), competitor rates, nhu cầu thị trường (theo mô tả marketing); rate-level template theo giai đoạn; master-child rate sync lên OTA; mở/đóng phòng theo luật; 24/7; app mobile + web. Có trang "Optimize OTA room sales revenue".
  - Một bài VN nói ezCloud Hotel có "Dynamic Pricing... và theo dõi giá qua kênh OTA đối thủ" (https://www.kiotviet.vn/top-5-phan-mem-quan-ly-khach-san-vua-va-nho-pho-bien-tai-viet-nam/ - nguồn thứ ba, chưa xác minh trên trang ezCloud).
  - Giá: không công khai. Chưa xác minh: rate shopper riêng, nguồn dữ liệu đối thủ (scrape hay không), có rooms-left không.
  - **Ý nghĩa**: ezCloud là PMS ta đang import CSV; họ có thể tự thêm competitor monitoring bất cứ lúc nào -> rủi ro chiến lược #1 ở VN. Cũng là kênh partner/integration tiềm năng.
- **Hotel Link Solutions** (https://www.hotellinksolutions.com/ota-pms-integrations): channel manager giá rẻ, 2-way OTA, parity theo OTA, tích hợp Smile PMS, Cloudbeds. Chưa xác minh: có module rate shopper.
- **Smile PMS, Newway, Aharooms, SCO Vietnam**: PMS/CM nội địa; Aharooms đồng bộ giá OTA và chỉnh giá trong PMS. Chưa thấy rate shopper chuyên dụng của họ.
- **STAAH** (https://www.staah.com/channel-manager/): CM + dynamic pricing theo luật mùa/nhu cầu, auto update lên OTA; không phải rate shopper.
- **eRevMax/RateTiger**: xem 1.4, có mặt APAC.
- Tìm tiếng Việt "phần mềm theo dõi giá đối thủ khách sạn": kết quả chỉ ra bài top PMS, **không có sản phẩm rate shopper chuyên biệt nào cho SMB VN nổi lên**. Gợi ý: khoảng trống thị trường thật, hoặc chỉ là SEO yếu (chưa xác minh).
- Thái/Indonesia: chưa nghiên cứu đủ (ngoài ngân sách) -> chưa xác minh.
- Zalo: ZNS (Zalo Notification Service) tính phí theo tin ~200-300 VND/tin (https://www.infobip.com/zalo ; nguồn thứ ba) và cần OA + template duyệt trước.

---
## 4. Ideas to port into ScrapeBooking (xếp hạng value/effort)

| # | Idea | Why | Tham chiếu | Effort | Data |
|---|------|-----|-----------|--------|------|
| 1 | Email digest hằng ngày + alert sold_out/restock/price_down của compset (đã có AI briefing -> gửi email, link deep vào evidence) | Khách không mở dashboard hằng ngày; mọi tool đối thủ đều có alert; free OTA tool phải tự vào xem | RPG surge alerts, Lighthouse/SiteMinder alerts | S | Booking-only OK |
| 2 | Zalo alert (ZNS hoặc Zalo OA) cho event quan trọng | Khác biệt tại VN, không đối thủ SEA nào thấy làm; chủ khách sạn VN dùng Zalo hơn email | Không có tham chiếu trực tiếp; ZNS pricing ~200-300đ/tin | M (OA duyệt, template, chi phí/tin) | Booking-only OK |
| 3 | "Price index" nhấn mạnh + price explanation 1 dòng ("Hơn 3/5 đối thủ đã sold out, median +8%") | RPG hiển thị lý do; ta đã có data sẵn | RPG price explanation | S | Booking-only OK |
| 4 | Gợi ý giá đơn giản dạng "rule-based suggestion" (nếu >=60% compset sold_out và giá mình < median -> đề xuất tăng X%) hiển thị, **không push**, chỉ copy/ghi nhận "đã áp dụng" | Cầu nối sang RMS mà không cần PMS API; one-click approve là UX được yêu thích | RPG, Lybra, Pricepoint | M | Booking-only OK (sold_out là tín hiệu độc nhất) |
| 5 | Screenshot/snapshot evidence kèm mỗi event | Chống tranh cãi "giá này có thật không"; Price Seeker làm | Price Seeker | S-M (đã có evidence, thêm ảnh) | Booking-only OK |
| 6 | Weekly report PDF/email cho chủ (tuần: sold-out đối thủ, giá, pickup) | Chủ khách sạn đọc báo cáo, ít mở dashboard | SiteMinder/Lighthouse reports | S-M | OK |
| 7 | Mobile-first/PWA cho view "hôm nay" + push | YCS app, ezCloud app: chủ khách sạn VN dùng điện thoại | Agoda YCS app, ezCloudhotel | M | OK |
| 8 | Compset do khách tự đổi tự do (khác Agoda khoá 1 lần/quý) | Điểm bán: linh hoạt hơn free tool; ta đã cho thêm bằng URL | Agoda 1 lần/quý | S (đã có) -> chỉ cần marketing | OK |
| 9 | Compset gợi ý tự động (cùng khu vực/hạng sao) khi onboarding | Giảm friction setup; Booking/Expedia gán sẵn compset | Expedia auto compset 5-19 | M | Cần scrape trang kết quả tìm kiếm Booking |
| 10 | Mở rộng Agoda | Thị phần Agoda cao ở VN/SEA; mọi shopper chuẩn đều có Agoda | RateTiger, Lighthouse | L (parser mới, anti-bot) | Cần nguồn mới |
| 11 | Parity brand.com vs OTA | Tính năng chuẩn của shopper | SiteMinder | L | Nguồn mới |
| 12 | PMS API adapter ezCloud (thay CSV) | Giảm friction, có occupancy tự động; cũng rủi ro nếu ezCloud tự làm | ezCloud | L (phụ thuộc đối tác) | Nguồn mới |
| 13 | LOS/occupancy variations | Giá nhóm gia đình/2 đêm khác | Lighthouse (filter) | M-L (nhân scrape) | Booking OK, tốn chi phí scrape |

Ưu tiên đề xuất cho team nhỏ: 1 -> 3 -> 6 -> 5 -> 2 -> 4 -> 7. Hoãn 10-13 cho tới khi có khách trả tiền.

---
## 5. Free OTA tool cho gì vs ScrapeBooking độc quyền (thành thật)

Free tools ĐÃ cho khách sạn:
- So sánh hiệu suất vs compset/peer/market (Booking Pace, Agoda YCS, Expedia Rev+), miễn phí, dữ liệu **thật từ nội bộ OTA** (booking/revenue/pickup thật của đối thủ ở mức tổng hợp - ta KHÔNG có).
- Demand/market insights, forward 360 ngày (RateIntelligence), gợi ý hành động (Opportunity Centre).
- Giá đối thủ "lowest upcoming rates" (Agoda), rate shop (Rev+).
- Mobile app (Agoda YCS).
- Không cần setup, đã đăng nhập sẵn, tin cậy.

ScrapeBooking độc quyền (với bằng chứng ở mức hợp lý, cần giữ kiểm chứng):
- **Per-competitor, per-room-type, per-date**: tên đối thủ cụ thể, không ẩn danh/tổng hợp.
- **Rooms-left & sold-out detection + restock/decrease events** theo từng đối thủ, 3x/ngày. Không thấy free tool nào cung cấp (xác minh một phần: tài liệu Booking mô tả compset là dữ liệu tổng hợp).
- **Event timeline + daily AI briefing có evidence click được** (chủ động đẩy, không phải tự vào đọc).
- **Compset tự chọn linh hoạt, theo dõi cả khi OTA từ chối** (Agoda khoá 1 lần/quý, Booking tối đa 10).
- Gắn **PMS occupancy của chính khách sạn** cạnh compset (OTA tool chỉ biết kênh của họ).
- Tiếng Việt, giá hợp lý cho SMB VN (chưa có giá nhưng đối thủ SEA bán $69-299/tháng).

Điểm yếu thật của ta:
- Chỉ Booking.com, không brand.com/Agoda -> khách VN phụ thuộc Agoda sẽ thấy thiếu.
- Dữ liệu scrape "rooms left" chỉ là suy luận (capped/hidden) - cần minh bạch confidence.
- Không có demand data thật (search volume) như Booking Market insights -> không thể nói "nhu cầu".
- Rủi ro pháp lý/ToS khi scrape; rủi ro bị chặn.
- Chưa có alert ngoài dashboard, chưa signup/billing.
- ezCloud/OTA có thể bundle tính năng tương tự.

---
## Câu hỏi chưa giải quyết
- Google Hotel Center/Insights: chưa xác minh tính năng và độ khả dụng.
- Booking RateIntelligence còn bán/miễn phí cho khách sạn VN? Có hiển thị tên đối thủ? (Chưa xác minh.)
- ezCloud có rate shopper/competitor tracking thật không, nguồn dữ liệu, giá? (Chỉ có mô tả marketing + bài bên thứ ba.)
- Hotel Link, Newway, Smile PMS, eZee/Yanolja, myhotelshop, Cloudbeds PIE: không lấy được chi tiết sản phẩm.
- Review tiêu cực thực tế (HotelTechReport/Capterra) còn mỏng: RPG gần như toàn 5 sao; SiteMinder chỉ có 1-2 điểm yếu. Nên đọc trực tiếp review 1-3 sao trước khi dùng làm positioning.
- Thái/Indonesia chưa nghiên cứu.
- Giá VND/USD tại VN của các tool: chưa có (giá trên là USD/EUR toàn cầu từ bên thứ ba).
- Chi phí/quy trình Zalo ZNS thực tế (OA verification, template) cần xác minh với nhà cung cấp.
