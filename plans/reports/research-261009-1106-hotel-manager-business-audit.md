# Nghiên cứu business và audit chức năng OTARadar dưới góc nhìn quản lý khách sạn

Ngày: 2026-10-09 (Asia/Saigon). Vai người đánh giá: **GM / Revenue Manager của một khách sạn độc lập
3–5★ ở Việt Nam** dùng OTARadar để nghiên cứu đối thủ mỗi ngày.

Báo cáo này **không lặp lại** các nghiên cứu đã có (`research-261001-1202-*` về đối thủ,
`research-261001-1428-*` về chuẩn đa kênh, `gap-analysis-261002-1332-*` về giao diện mẫu). Nó trả lời
ba câu hỏi:
1. Chức năng nào đang **chưa đúng chuẩn nghề revenue** (tên chỉ số, công thức, phương pháp, độ tin cậy)?
2. Chức năng nào **còn thiếu** so với cách một quản lý khách sạn thật sự làm việc?
3. Ý tưởng business: định vị, gói bán, kênh bán, lợi thế dài hạn.

Plan triển khai: `plans/261009-1106-rm-standards-roadmap/plan.md`.

## Mục lục
0. Tóm tắt
1. Phương pháp
2. Quản lý khách sạn cần gì khi nghiên cứu đối thủ
3. Thị trường và chuẩn ngành 2026
4. Điểm mạnh nên giữ
5. Chức năng chưa chuẩn (kèm bằng chứng)
6. Chức năng cần bổ sung
7. Ý tưởng business
8. Thứ tự ưu tiên
9. Câu hỏi cần chủ dự án quyết
10. Nguồn

---

## 0. Tóm tắt

1. **Lõi sản phẩm có khác biệt thật, nên giữ:**
   - Phòng còn / hết phòng **đích danh** từng đối thủ, có mức tin cậy.
   - Nhiều kênh, gồm OTA nội địa.
   - Bản tin AI chỉ nói điều có bằng chứng.

   Nghiên cứu 2026 không tìm thấy công cụ nào hiện số phòng còn của đối thủ: Cloudbeds gộp hết phòng /
   không bán / có hạn chế thành một nét đứt.
2. **Vấn đề số 1 là độ tin cậy dữ liệu, chưa phải tính năng:**
   - Từ 22:00 ngày 08/10 **mọi kênh không thu được dữ liệu**; 03–06/10 cũng đứt.
   - 7 ngày qua các kênh ngoài Booking chỉ 17–31% probe thành công.
   - **Nguyên nhân gốc:** proxy duy nhất trả `407 Proxy Authentication Required` (tài khoản proxy hết
     hạn hoặc sai xác thực), lặp lại sự cố 01/10.
   - **39/39 thông báo ở trạng thái `skipped`:** chưa email nào tới tay khách. Không có cảnh báo vận
     hành.
   - Spec gốc đặt ngưỡng ≥90%.
3. **Nhiều chỉ số dùng sai tên nghề:**

   | Tên trên giao diện | Thực chất |
   |---|---|
   | "ADR compset" | Giá niêm yết thấp nhất trung bình |
   | "RevPAR compset" | Giá niêm yết × ước tính |
   | "Dự báo cầu" | Mức căng hiện tại |
   | "So cùng kỳ" | So 1–8 tuần trước |
   | "Công suất đối thủ" | Mức lấp đầy allotment một kênh (cùng nhóm khách sạn: Agoda ≈50%, Booking ≈33–43%) |

   Thêm vào đó, một màn hình có thể **trộn giá kênh này với công suất kênh khác**.
4. **Cảnh báo đổi giá nhiễu:**
   - 83% sự kiện "tăng giá" mức khách sạn trên Booking xảy ra cùng lúc loại phòng xuất hiện/biến mất.
     44% không có loại phòng nào thật sự tăng giá: đó là phòng rẻ nhất bán hết.
   - Parity Mytour bị mã KM của kênh làm nhiễu (160 sự kiện).
   - **Lỗi tiềm ẩn:** đêm có số đêm tối thiểu >1 thì giá Booking sẽ là giá tổng nhiều đêm. Lỗi này sẽ
     lộ đúng dịp lễ.
5. **Thiếu nửa còn lại của quyết định giá.** PMS chỉ lưu một con số cuối mỗi đêm (ghi đè), nên không có
   OTB / pickup / pace / STLY của chính khách sạn. Gợi ý giá chưa có sàn/trần, định vị mục tiêu, giải
   thích chuẩn, đo kết quả. Tenant "Group" bị tính như một khách sạn.
6. **Có những thứ đáng giá đã nằm sẵn trong dữ liệu đang quét mà chưa dùng:**
   - khuyến mãi đối thủ (nhãn và giá gạch);
   - số đêm tối thiểu;
   - chính sách huỷ;
   - điểm và số review;
   - thứ hạng và huy hiệu Preferred/Genius/Ad trên trang kết quả;
   - số khách sạn còn phòng cả khu vực.

   Gần như không tốn thêm request.
7. **Thị trường 2026 đã đổi:**
   - Lighthouse cho **dashboard thị trường miễn phí** và gói €99 cho khách sạn độc lập.
   - Agoda cho **gợi ý giá 90 ngày miễn phí**.
   - Ở Việt Nam, **TravelOpen** bán "competitor tracking" từ $0–59. Khachsanso khuyên khách tự ghi tay
     đối thủ.
   - Giá đối thủ đơn thuần không còn bán được tiền. Thứ bán được: phòng còn, KM và hạn chế **theo từng
     đối thủ**, Zalo, tiếng Việt, giá Việt.
8. **Kênh nhận tin phải là Zalo ZNS** (200–300₫/tin, cần OA doanh nghiệp xác thực). Telegram bị chặn ở
   Việt Nam từ 05/2025.
9. **Business:**
   - Bán cho khách sạn độc lập 3–4★ ở thành phố du lịch đang dò giá tay bằng Excel.
   - Giá đề xuất 490–690 nghìn (Cơ bản) và 1,2–1,9 triệu (Chuyên nghiệp) ₫/tháng.
   - Có gói miễn phí làm phễu, dùng thử tự phục vụ, kênh qua PMS nội địa và tư vấn OTA.
   - Biên lợi nhuận phụ thuộc chia sẻ listing giữa tenant, vì băng thông proxy ước tính 60–150 nghìn ₫ mỗi
     listing Booking mỗi tháng ở horizon 90 đêm.
10. **Lộ trình:**
    - Tuần 1: cầm máu dữ liệu.
    - Tuần 1–3: nói đúng nghề, cảnh báo đúng.
    - Tuần 4–5: Zalo, radar từ dữ liệu sẵn có.
    - Tuần 6–11: OTB/pace và gợi ý giá có giải thích.

    Chi tiết: `plans/261009-1106-rm-standards-roadmap/plan.md`.

## 1. Phương pháp

- **Đọc code** backend và dashboard; mọi nhận định có `file:dòng`.
- **Truy vấn chỉ đọc DB đang chạy** (container `scrapebooking-postgres-1`, khoảng 11:10 ngày 09/10):
  `probes`, `scan_runs`, `scan_jobs`, `room_snapshots`, `availability_events`, `occupancy_estimates`,
  `notifications`, `hotel_calendars`.
- **4 nghiên cứu web song song** (đối thủ toàn cầu 2025–2026, thị trường Việt Nam, chuẩn revenue
  management, tín hiệu cạnh tranh ngoài giá) và **1 audit dashboard độc lập**. Nguồn ở mục 10.
- **Giới hạn:**
  - DB local chỉ có 5 khách sạn thật (tenant 9: Rex và 4 đối thủ ở quận 1), các tenant còn lại là dữ
    liệu e2e. Số liệu dùng để chỉ ra **kiểu lỗi**, không đại diện cho thị trường.
  - `web_search` của môi trường bị lỗi; subagent tìm qua DuckDuckGo HTML bằng `web_fetch`.
  - Giá công cụ đối thủ lấy từ trang công khai hoặc trang tổng hợp, có thể lệch.

## 2. Quản lý khách sạn cần gì khi nghiên cứu đối thủ

Công việc thật của một revenue manager, theo nhịp, đối chiếu với OTARadar hiện nay:

| Nhịp | Câu hỏi | Quyết định đi kèm | Dữ liệu cần | OTARadar hiện nay |
|---|---|---|---|---|
| **Mỗi sáng** (5–10 phút) | Đêm nào sắp căng? Đêm qua đối thủ đổi gì? Mình đang đứng ở đâu? | Chỉnh giá, tắt/bật khuyến mãi, đặt số đêm tối thiểu | Giá đối thủ 30–90 đêm so cùng điều kiện, mức căng, thay đổi 24h đã lọc nhiễu, **phòng đã bán (OTB) và pickup của mình** | Có phần đối thủ; thiếu OTB/pickup của mình; thay đổi còn nhiễu |
| **Trong ngày** (đẩy tin) | Có gì bất thường phải phản ứng ngay? | Phản ứng giá/KM trong vài giờ | Cảnh báo có ngưỡng, gom tin, tới đúng người | Chỉ email; thực tế chưa gửi được thư nào |
| **Hằng tuần** (họp doanh thu) | Nhịp đặt phòng 30/60/90 ngày ra sao? Đối thủ chạy KM gì? Giá mình có lệch giữa các kênh? | Kế hoạch giá và KM tuần tới | Pace của mình và thị trường, radar KM, parity có nguyên nhân | Pace thị trường ước tính; chưa có radar KM; parity chưa nói nguyên nhân |
| **Hằng tháng** (báo cáo chủ đầu tư) | Mình so với compset thế nào? Review, thứ hạng hiển thị ra sao? | Giải trình kết quả, điều chỉnh chiến lược | Chỉ số kiểu STR, review, vị trí trên OTA, lịch sử quyết định | Chưa có báo cáo tháng, chưa có review/thứ hạng theo thời gian |
| **Theo mùa / năm** | Dịp lễ, sự kiện, thị trường nguồn (Hàn, Trung, Nhật…) sắp tới? Năm trước dịp này thị trường ra sao? | Chiến lược mùa, ngân sách | Lịch cầu đầy đủ, dữ liệu cùng kỳ năm trước | Chỉ ngày lễ chính thức của Việt Nam |
| **Khi xem lại compset** (quý) | Đối thủ nào thật sự cạnh tranh với mình? | Đổi compset, chia compset chính/phụ | Khám phá thị trường, điểm review, giá, khoảng cách, mức trùng khách | Có khám phá thị trường; chưa có compset chính/phụ, trọng số, gợi ý rà soát |

**Kết luận mục 2:** OTARadar đang trả lời tốt câu hỏi "đối thủ đang làm gì", nhưng một quyết định giá
cần **hai nửa**: đối thủ **và** nhịp đặt phòng của chính mình. Nửa thứ hai gần như chưa có.

## 3. Thị trường và chuẩn ngành 2026

Chỉ ghi điều **mới hoặc thay đổi** so với nghiên cứu 01/10. Nguồn đầy đủ ở mục 10; "(trích đoạn)" là
thông tin chỉ thấy trong đoạn trích kết quả tìm kiếm, chưa mở trang gốc.

### 3.1 Đối thủ toàn cầu: chuyện gì đã đổi trong 2025–2026

| Sự kiện | Ý nghĩa với OTARadar |
|---|---|
| **Lighthouse "Market Alerts" miễn phí** cho mọi khách sạn: xu hướng cầu 90 ngày, giá đối thủ, sự kiện địa phương, email tóm tắt hằng tuần | Trùng trực tiếp với báo cáo tuần và quét thị trường của ta. "Có giá đối thủ" không còn bán được tiền |
| **Lighthouse công khai giá cho khách sạn độc lập**: Starter €99/tháng, Plus €129, Complete €189, có dùng thử. Một chuyên gia (06/2026) nhận xét giá khó biện minh với khách sạn dưới ~30 phòng chỉ cần xem compset cơ bản | Mốc giá trần cho phân khúc nhỏ. Ở Việt Nam phải rẻ hơn nhiều |
| **Lighthouse "Ernest"**: trợ lý AI chuẩn bị phân tích qua đêm, mọi câu trả lời link tới dữ liệu gốc, chỉ hành động trong giới hạn khách sạn đặt; GA 07/10/2026 cho chuỗi | Cùng triết lý "chỉ nói điều có bằng chứng" với bản tin AI của ta. Bản tin có bằng chứng không còn là khác biệt riêng |
| **Giải thích giá là chủ đề ra mắt năm 2026**: RoomPriceGenie Price Explanations (06/2026), Lybra Zenit (05/2026), Duetto "AI Storytelling" (07/2026), PriceLabs giải thích từng mức giá | Gợi ý giá không kèm lý do có số là dưới chuẩn |
| **Hợp nhất thị trường**: Duetto mua FLYR (Pace) 08/10/2026; Mews ra RMS và bản tin sáng AI (05/2026); Cloudbeds ra RMS (09/2026); RateGain mua Sojern | PMS lớn tự đóng gói RMS. Ở Việt Nam, ezCloud có thể làm tương tự |
| **PriceLabs hotel rate shopper mới (08/10/2026)**: so "Deluxe của bạn với Deluxe của họ", không khớp được thì quay về giá tiêu chuẩn và gắn cờ; chỉ dùng giá công khai Booking, làm mới 24 giờ | So theo hạng phòng tương đương đã thành chuẩn, kể cả ở công cụ rẻ |
| **Agoda đổi YCS thành Agoda Partner Portal (08/2026)**: compset do **Agoda chọn**; "Agoda Intelligence" gợi ý giá tới 90 ngày (khách sạn đủ điều kiện); cảnh báo qua KakaoTalk/WhatsApp, **không có Zalo** | Gợi ý giá miễn phí từ OTA làm "gợi ý giá" của ta khó bán riêng. Lợi thế còn lại: đích danh đối thủ, nhiều kênh, Zalo |
| **Booking extranet**: "peer group" ≥25 khách sạn do máy chọn; "competitive set" đúng 10 khách sạn tự chọn (30 ngày mới đổi được); ADR, room nights, doanh thu tổng hợp; bảng so giá với kênh khác | Chỉ số tổng hợp ẩn danh, một kênh, không có giá tương lai hay phòng còn từng đối thủ |
| **Cloudbeds PIE** vẽ đối thủ "đóng" bằng một nét đứt chung cho hết phòng / không bán / có hạn chế, không phân biệt | Bốn trạng thái có mức tin cậy của ta (`exact/capped/hidden/sold_out`) là khác biệt thật |

**Chuẩn bắt buộc (table stakes) năm 2026, theo nghiên cứu:**
- Quét giá nhiều OTA hằng ngày, có ghép hạng phòng.
- Gợi ý hoặc tự đặt giá có giới hạn và có giải thích.
- Cảnh báo email và báo cáo định kỳ.
- Tín hiệu cầu từ sự kiện và lượt tìm kiếm.
- Dùng thử tự phục vụ cho khách sạn nhỏ (PriceLabs 30 ngày, không cần thẻ).

**Khác biệt:**
- Trợ lý AI hành động được.
- Số OTB thật của thị trường (Amadeus Demand360).
- Horizon 365 ngày.
- Cưỡng chế parity (test booking, gỡ đại lý trái phép).
- Push trên điện thoại.

**Không công cụ nào có** (theo nghiên cứu, chưa kiểm chứng tuyệt đối):
- Số phòng còn của từng đối thủ, có nhãn tin cậy.
- Cảnh báo Zalo.
- Phủ iVIVU/Mytour.

**Người dùng phàn nàn nhiều nhất:**
- Đắt với khách sạn nhỏ.
- Gợi ý giá "hộp đen": hơn 50% gợi ý AI bị người dùng sửa lại (trích nguồn ngành).
- Dữ liệu giá sai, so lệch hạng phòng.
- Compset mặc định tệ: một ví dụ GM bỏ công cụ sau khi nó gợi ý giảm giá cho một tối thứ Bảy đã kín phòng.
- Quá nhiều bảng biểu.

**Người dùng đánh giá cao:**
- Tiết kiệm thời gian.
- Thấy giá và trạng thái hết phòng của đối thủ ở một chỗ.
- Có lý do cho từng mức giá.
- Việc đã sẵn sàng trước khi ngày làm việc bắt đầu.

### 3.2 Việt Nam

**Đối thủ và công cụ gần kề:**

| Sản phẩm | Liên quan | Giá công khai |
|---|---|---|
| **TravelOpen** (PMS AI, khách sạn ở Hà Nội, Đà Nẵng) | Quảng cáo "competitor tracking… tự định giá lại từng phòng". **Đối thủ mới gần nhất** | Miễn phí tới 10 phòng; $9 / $29 / $59/tháng; Enterprise từ $149; channel manager +$99 |
| **ezCloud** (PMS thị phần số 1, "9.000+ khách sạn") | ezRms định giá theo luật công suất, đẩy giá lên OTA; ghi "competitor rates" nhưng không mô tả nguồn | PMS 18k / 48k / 66k ₫ mỗi phòng/tháng (0–2★); ezRms không công khai |
| **Khachsanso.vn** (PMS mới) | Bài blog 02/09/2026 khuyên khách sạn **tự ghi tay** 3–5 đối thủ, 2–3 lần/tuần. Có ZNS từ gói 799k, "yield management" từ gói 1,399 triệu | 419k – 3,499 triệu ₫/tháng (10–100 phòng), dùng thử 14 ngày |
| SiteMinder Plus | "Competitor rates insights", "Rate parity insights" | Theo số phòng |
| Hotel Link | "Smart Rates", "Yield Management" | Qua sales |
| VinHMS CiHMS | Từng có trang "Kiểm soát & so sánh giá" (2021) | – |

**Cách khách sạn Việt Nam đang làm:**
- Mô tả công việc OTA/Revenue (hoteljob.vn, nhansu.vn, Joboko) yêu cầu "theo dõi occupancy, ADR, RevPAR
  hằng ngày", "điều chỉnh giá theo mùa, sự kiện, đối thủ", báo cáo ngày/tuần/tháng, thành thạo
  Excel/Google Sheets.
- **Không tin tuyển dụng nào nhắc tên công cụ rate shopping hay STR.** Suy luận: phần lớn đang dò tay và
  ghi Excel. Đây là khoảng trống thị trường và cũng là mẫu báo cáo cần bắt chước.
- Cộng đồng: các nhóm Facebook "Cộng Đồng OTA", "Cộng đồng sales OTAs Việt Nam".

**Kênh bán phòng:**
- Thị trường du lịch trực tuyến khoảng 3,12 tỷ USD năm 2026; Booking, Agoda, Traveloka chiếm khoảng 80%
  doanh thu.
- Phía khách sạn (STAAH 2025): Agoda và Booking đứng đầu, rồi Trip.com, Expedia, Traveloka.
- iVIVU/Mytour nhỏ: nên coi là kênh "parity và giá nội địa", không phải nguồn tồn phòng chính.

**Nguồn khách (9 tháng 2026: 17,7 triệu lượt quốc tế, +14,5%):**

| Thị trường | Lượt khách | Biến động |
|---|---|---|
| Trung Quốc | 3,9 triệu | |
| Hàn Quốc | 3,0 triệu | −5,5% |
| Nga | 1,1 triệu | +161% |
| Đài Loan | 964 nghìn | |
| Mỹ | 764 nghìn | |
| Nhật | 674 nghìn | |
| Ấn Độ | 671 nghìn | +33% |

- Lễ của các nước này dịch chuyển cầu theo điểm đến: Chuseok → Đà Nẵng, Nha Trang; mùa đông Nga → Nha
  Trang, Phú Quốc; đám cưới Ấn Độ → khối phòng lớn ở Phú Quốc, Đà Nẵng.
- Ngày nghỉ mới **24/11** và Tết 2027 (nghỉ 04–10/02) đã nêu ở C14.

**Kênh nhận tin:**
- Zalo: 81,3 triệu người dùng/tháng, khoảng 30.000 OA trả phí (06/2026).
- ZNS: 200–300₫/tin gửi thành công, mỗi nút thêm 100₫. Cần OA doanh nghiệp đã xác thực, tài khoản
  Zalo Cloud nạp trước, template duyệt trước; link phải đặt trong nút.
- Gói OA Growth (có API) khoảng 1,4 triệu ₫/6 tháng.
- **Telegram bị yêu cầu chặn ở Việt Nam từ 21/05/2025.** Agoda cũng chưa hỗ trợ Zalo. Zalo là khoảng
  trống thật.

**Thuế và cách niêm yết giá:**
- VAT 8% tới 31/12/2026, phí phục vụ 5%. 1.000.000₫++ = 1.134.000₫ NET (VAT 8%), hoặc 1.155.000₫ nếu
  VAT về 10%.
- Agoda có thể hiện giá chưa thuế ở trang danh sách/khuyến mãi (trích đoạn). Tầng chuẩn hoá thuế theo
  kênh là bắt buộc.

**Mức giá phần mềm khách sạn ở Việt Nam 2026 (VND/tháng):**

| Phân khúc / sản phẩm | Giá |
|---|---|
| Khách sạn nhỏ | 300–800 nghìn |
| Khách sạn vừa | 800 nghìn – 2,5 triệu |
| 3–5★ | 2,5–6 triệu+ |
| Công cụ quốc tế cho khách sạn vừa | khoảng 5–10 triệu |
| Bizkasa | 199 nghìn |
| ezCloud, khách sạn 20 phòng | khoảng 360 nghìn – 1,32 triệu |

### 3.3 Chuẩn nghề revenue management

**Định nghĩa** (CoStar/STR glossary, HSMAI):
- **Công suất (Occupancy)** = phòng bán / phòng sẵn có.
- **ADR** = doanh thu phòng / phòng bán.
- **RevPAR** = doanh thu phòng / phòng sẵn có.
- **MPI, ARI, RGI** = chỉ số của bạn / chỉ số **gộp** của compset × 100; 100 là "fair share".
- **Hạng STR** so giá trị tuyệt đối: hạng 1 = ADR/RevPAR cao nhất.
- **BAR** là giá công khai, không điều kiện, dùng làm mốc so.
- Lighthouse gọi giá quét được là **"advertised rates"** (giá niêm yết).
- HSMAI dùng "RPI" cho RevPAR Index, nên chỉ số giá của ta **không được** đặt tên ARI hay RPI.

**Quy tắc compset của CoStar STR hiện hành:**
- **≥4 đối thủ** (không tính khách sạn của bạn), trong đó ≥3 không cùng chủ/đơn vị vận hành.
- Không khách sạn hay thương hiệu nào chiếm quá 50% số phòng của compset.
- Amadeus Demand360 cũng yêu cầu ≥4 khách sạn; ≥30 ngày mới được đổi compset.
- Lighthouse khuyên compset chính 5–10 khách sạn, cộng compset phụ (theo mùa, tham vọng), và rà soát ít
  nhất 2 lần/năm.

**So giá cùng điều kiện:**
- Khớp loại giá và điều kiện huỷ, số đêm, hạng phòng, bữa ăn, POS, thiết bị, giá thành viên.
- "Ghép hạng phòng là nền móng."
- **Hạn chế đi kèm giá:** "đối thủ giá thấp nhưng tối thiểu 3 đêm thì không cạnh tranh với bạn ở khách
  1 đêm".
- Access RMS dùng trung vị/min/max, hạng 1 = rẻ nhất, tô đỏ giá không khớp hạng phòng/điều kiện.
- Gói không hoàn huỷ thường rẻ hơn 10–20% (RoomPriceGenie).
- Nên tách trạng thái: **còn bán / hết mọi loại phòng / bị hạn chế (bán được ở số đêm khác) / không có
  giá / lỗi**.

**Parity:**
- Là so **cùng khách sạn** giữa các kênh, theo cùng phòng/giá/điều kiện/POS.
- Báo dạng **Win/Meet/Loss** so với website trực tiếp, có dung sai (ví dụ "Meet" trong ±0,5%; báo động
  khi lệch trên 1–2%).
- Nguyên nhân phổ biến:
  - wholesaler/bedbank bán lại;
  - giảm giá thành viên của OTA (Genius);
  - KM theo POS/mobile bị lộ;
  - cache.

**OTB, pickup, pace:**
- **Pickup** = thay đổi ròng của OTB giữa hai lần đo.
- **Pace** = OTB "tính đến ngày" so với kỳ tham chiếu ở **cùng số ngày trước khi đến** (thường là STLY).
- Bắt buộc phải có snapshot theo `as_of_date`. PMS như OPERA lưu OTB theo ngày.
- Dữ liệu nhập tối thiểu: (as_of_date, stay_date, rooms_otb, revenue_otb, rooms_available, huỷ, khối
  phòng đoàn, [segment, kênh, hạng phòng]). Hoặc **file đặt phòng chi tiết** (ngày đặt, ngày đến/đi, ngày
  huỷ, trạng thái, doanh thu) để tự dựng lại snapshot.

**Dự báo và gợi ý giá:**
- Phương pháp đơn giản, chính xác tốt: additive/multiplicative pickup theo cùng thứ trong tuần
  (Weatherford & Kimes, Cornell).
- RoomPriceGenie: **giá gốc** → hệ số thị trường (giá thị trường, sự kiện) → hệ số công suất ("còn bao
  nhiêu phòng, còn bao nhiêu thời gian") → điều chỉnh theo thứ, tháng, lead time → chặn bởi **giá sàn/trần**.
- Atomize thêm luật sát ngày đến (đóng băng, chỉ tăng, chỉ giảm).
- Chuẩn là **dựa vào OTB/pace của chính khách sạn trước**, compset là đầu vào phụ.
- **Compression** = công suất thị trường trên 90–95%.

**Ước tính công suất từ tồn phòng OTA:**
- "Còn X phòng" là **phần phòng kênh được bán** (Booking `roomstosell`), khách sạn có thể đóng từng loại
  phòng hoặc từng giá.
- Thông điệp khan hiếm hay sai: Which? thấy 5/10 câu "chỉ còn X phòng" không đúng, có khách sạn còn 34
  phòng.
- Nghiên cứu gần nhất (Suzuki 2023, OTA Jalan, Nhật):
  - Coi "10+" là 10 làm **đánh giá thấp số phòng trống nên công suất ra cao**.
  - Dùng sức chứa từng hạng phòng thì chính xác hơn.
  - Chỉ kiểm chứng được ở cấp tỉnh; tác giả nói "không có chuẩn tuyệt đối để đánh giá độ chính xác".
- Benchmark thật (STR, Demand360, Lighthouse Benchmark) đều dùng **số liệu khách sạn đóng góp**.
- Khuyến nghị:
  - gọi là **"chỉ báo công suất từ tồn phòng (thử nghiệm)"**;
  - coi "≥N" là dữ liệu bị cắt;
  - lấy tổng phòng từ số công bố hoặc người dùng nhập, không lấy số lớn nhất từng thấy;
  - hiệu chỉnh bằng chính khách sạn của bạn so với PMS, báo **MAPE và độ lệch theo lead time**.

**Đối chiếu nhanh với OTARadar:**

| Hạng mục | Chuẩn | OTARadar | Sửa (Phase) |
|---|---|---|---|
| Giá thấp nhất mỗi đêm | Rate shop, gọi là "giá niêm yết", kèm điều kiện tìm kiếm | Gọi là "ADR" ở Bảng điều khiển | Đổi tên; lưu đủ điều kiện (1) |
| Giá hoàn huỷ thấp nhất | Gần BAR nhất ("giá linh hoạt thấp nhất") | Có | Thêm khớp hạng phòng, bữa ăn (2) |
| Trung vị compset, chỉ số giá | Cùng điều kiện, n ≥4 | Tính cả khi chỉ có 1 đối thủ | Ngưỡng n≥4; tên "chỉ số giá niêm yết" (1) |
| Hạng giá | Ghi rõ chiều | 1 = rẻ nhất, không ghi | "Vị trí giá k/N (1 = rẻ nhất)" (1) |
| % đối thủ hết phòng | Proxy | Gộp hết phòng / hạn chế / đóng kênh | Tách 5 trạng thái (2) |
| Công suất đối thủ | Chỉ có thật khi khách sạn đóng góp số | "Công suất compset ≈" | Đổi tên thành chỉ báo thử nghiệm; tổng phòng công bố; MAPE theo lead time (1, 5) |
| Pickup giữa hai lượt quét | Pickup là thay đổi OTB trong PMS | Gọi là "Pickup 24h" | "≈ phòng còn giảm trên kênh" (1) |
| Pace | OTB so STLY từ snapshot | So 1–8 tuần trước, gọi "cùng kỳ" | Đổi tên; OTB snapshot và STLY (1, 5) |
| ADR/RevPAR compset | Cần số đóng góp | Ghép từ giá niêm yết × ước tính | Bỏ (1) |
| Compression | Công suất thị trường >90–95% | % đối thủ hết hoặc ≤3 phòng | "Tín hiệu căng", hiệu chỉnh theo công suất của bạn (1, 4) |
| Gợi ý giá | OTB/pace trước, có sàn/trần, giải thích, backtest | Chỉ nhìn đối thủ | RMS-lite (6) |
| Nhập PMS | Snapshot as-of hoặc file đặt phòng chi tiết | Một dòng mỗi đêm, ghi đè | Bảng snapshot (5) |

### 3.4 Tín hiệu cạnh tranh ngoài giá (hiển thị, khuyến mãi, uy tín)

**Booking xếp hạng thế nào (nguồn chính thức):**
- Thứ tự mặc định "Our top picks" dựa trên tỷ lệ nhấp, số đặt và số đặt ròng. Các yếu tố này phụ thuộc
  điểm review, tình trạng còn phòng, chính sách, giá, chất lượng nội dung.
- Ngoài ra còn mức hoa hồng, Genius, Preferred, Visibility Booster và cá nhân hoá.

| Chương trình | Hiệu quả trung bình (Booking công bố) | Điều kiện |
|---|---|---|
| Preferred | +65% lượt xem, +20% lượt đặt | Điểm hiệu suất ≥70% và review ≥7,0 |
| Genius | +30% lượt xem, +45% lượt đặt | ≥3 review và điểm ≥7,5 |

- **Ở APAC, khách chưa đăng nhập cũng thấy giảm giá Genius 10% và huy hiệu Genius.** Hệ quả: giá ta quét
  được có thể đã gồm Genius. Đây là một điểm "so cùng điều kiện" cần gắn cờ (Phase 2.6).

**Quan sát thật trên trang kết quả Booking, chưa đăng nhập (09/10/2026, Nha Trang, TP.HCM, Đà Nẵng, Hội An):**
- Huy hiệu `preferred-badge` có `aria-label` phân biệt "Preferred Plus Programme" và "Preferred Partner
  Programme". Ví dụ Nha Trang: 15/18 thẻ có huy hiệu (10 Plus, 5 Partner).
- Nhãn **"Ad"** ở vị trí 2, 4, 6. Thứ hạng cần tách **tự nhiên** và **trả tiền**.
- Nhãn deal ghi rõ điều kiện, VD "Late Escape Deal… stays between 1 Oct 2026–7 Jan 2027",
  "Limited-time Deal… only last up to 48 hours".
- "Free cancellation", "Breakfast included", "No prepayment", "We have 7 left at this price", diện tích
  phòng (m²), giá gạch cạnh giá cuối, "New to Booking".
- "Mobile-only price" chỉ hiện với user agent điện thoại.
- **Không thấy khi chưa đăng nhập:** Secret Deals, Genius trên 10%, giá theo nước (phụ thuộc IP).

**Agoda:**
- Các chương trình trả tiền: AGX (đấu giá thứ hạng), AGP (logo Preferred, ước tính +10% chuyển đổi),
  Sponsored Listings.
- Agoda công bố 90% lượt đặt từ trang tìm kiếm đến từ trang 1; 4 vị trí đầu nhận tới 6 lần lượt xem.
- "Insider Deals" chỉ cho thành viên đã đăng nhập.

**Công cụ theo dõi:**

| Mảng | Công cụ có | Ghi chú |
|---|---|---|
| Thứ hạng OTA | Lighthouse "Rankings & reviews" (theo tuần/tháng), HotelAI Ranker, TravelScrape, Otamiser | Lighthouse mua Hotelrank.ai (05/2026) để đo thứ hạng trong ChatGPT/Gemini |
| Khuyến mãi | Lighthouse "Rate Strategy" (tỷ lệ khách sạn chạy KM và độ sâu), RateGain Optima (KM, mobile, thành viên) | **Chưa thấy công cụ nào báo theo từng đối thủ đang tham gia chiến dịch nào** (Late Escape, Getaway, Black Friday, Agoda Mega Sale). Thẻ Booking lại lộ tên chiến dịch cho khách chưa đăng nhập |
| Review | TrustYou từ €75/khách sạn/tháng; GuestRevu có bản miễn phí (3 nguồn, có đối thủ) | Benchmark đối thủ |

**Bằng chứng review quyết định sức định giá:**
- Anderson 2012 (Cornell): tăng 1 điểm trên thang 5 cho phép tăng giá 11,2% mà công suất giữ nguyên.
  Tăng 1% chỉ số review đi kèm tới +0,89% ADR, +0,54% công suất, +1,42% RevPAR.
- Viglia và cộng sự 2016: +1 điểm review ≈ +7,5 điểm % công suất.
- Mốc điểm Booking cần theo dõi: 7,0 (điều kiện Preferred), 7,5 (Genius), 8,0 (giải Traveller Review
  Award), nhãn 9+ "Superb".

### 3.5 Hệ quả cho OTARadar

1. **Dữ liệu giá đối thủ không còn là thứ bán được tiền.** Lighthouse cho miễn phí, Agoda cho gợi ý giá
   miễn phí, Booking cho ADR compset miễn phí. Thứ còn bán được:
   - phòng còn / hết phòng **đích danh** từng đối thủ, có mức tin cậy;
   - nhiều kênh, có OTA nội địa;
   - radar khuyến mãi và hạn chế **theo từng đối thủ**;
   - tiếng Việt, Zalo, rẻ.
2. **Chuẩn tối thiểu 2026 ta còn thiếu:** so theo hạng phòng tương đương, giải thích từng gợi ý, dùng
   thử tự phục vụ, dữ liệu liên tục.
3. **Đối thủ thật ở Việt Nam** không phải Lighthouse mà là **tự làm tay + Excel**, PMS nội địa đóng gói
   tính năng (TravelOpen, ezCloud, Khachsanso) và công cụ miễn phí của OTA.
4. **Mức giá phải theo mặt bằng Việt Nam** (mục 7.2), không theo €99.

## 4. Điểm mạnh nên giữ

| Điểm mạnh | Bằng chứng |
|---|---|
| Phòng còn / hết phòng đích danh từng đối thủ, từng loại phòng, có mức tin cậy `exact/capped/hidden/sold_out` và phạm vi `room_type/rate/property` | `backend/app/domain/models.py:7-34` |
| Đọc calendar số đêm tối thiểu trước khi probe để không báo "hết phòng" sai | `docs/user-flows.md`, bảng `hotel_calendars` |
| So 2 người lớn: bỏ dòng giá chỉ cho 1 khách và dòng giá của đối tác bán lại trên Booking | `backend/app/collector/booking/parser.py:207-216` |
| Compset theo một kênh, không trộn giá các kênh vào một trung vị; có cơ sở giá "hoàn huỷ" | `backend/app/analytics/compset.py:18-27,79` |
| Đóng bán trên một kênh khác với hết phòng thật (`channel_closed`) | `backend/app/analytics/cross_channel.py:33-51` |
| Bản tin AI bắt buộc có bằng chứng, mục không có bằng chứng bị loại và ghi lại | `backend/app/insight/prompt.py` |
| Đã có hàm hiệu chỉnh ước tính bằng PMS (sai số tuyệt đối trung bình, độ lệch) | `backend/app/market/pacing.py:79-94` |
| Quét bù khi lỡ lịch, tự ngắt kênh khi bị chặn, job idempotent | `docs/user-flows.md` mục F |

Các điểm này **đúng hoặc vượt chuẩn** của rate shopper phổ thông; không nên đánh đổi chúng để chạy
theo tính năng mới.

## 5. Chức năng chưa chuẩn

Mức: **P0** sửa ngay (mất niềm tin hoặc dẫn tới quyết định sai), **P1** trong đợt kế tiếp, **P2** sau.

### 5.1 Độ tin cậy và độ mới dữ liệu (P0)

Với người làm giá, công cụ hỏng một buổi sáng là mất niềm tin cả tuần. Đây là việc quan trọng hơn mọi
tính năng mới.

**C1. Dữ liệu đứt kéo dài mà không ai được báo.**

Probe theo ngày (giờ Việt Nam), số thành công / tổng:

| Ngày | Booking | Agoda | iVIVU | Trip.com | Mytour |
|---|---|---|---|---|---|
| 01/10 | 659/660 | 472/472 | 368/418 | 456/472 | 354/354 |
| 02/10 | 375/375 | 300/356 | **0/616** | 294/361 | 225/267 |
| 03/10 | **không chạy** | **0/548** | **0/679** | **0/557** | **0/414** |
| 04/10 | **không chạy** | **0/685** | **0/876** | **0/604** | **0/453** |
| 05–06/10 | **không có lượt quét nào** | | | | |
| 07/10 | 520/520 | 416/416 | 414/419 | 415/419 | 312/312 |
| 08/10 | 155/159 | 116/356 | 129/310 | 128/370 | 91/281 |
| 09/10 (tới 11:10) | **0 probe** | **0/244** | **0/244** | **0/244** | **0/183** |

- Từ lượt 22:00 ngày 08/10, **mọi kênh không thu được dữ liệu**:
  - Booking: 5/5 job lỗi `Page.goto: Timeout 60000ms` ở bước khởi tạo phiên (run 181, 185, 190).
  - Agoda, Mytour: `Proxy CONNECT aborted`, `CONNECT tunnel failed`.
  - iVIVU, Trip.com: `ERR_EMPTY_RESPONSE`.
- **Nguyên nhân gốc đã xác nhận:** `uv run sb check-proxy` lúc khoảng 11:45 ngày 09/10 cho kết quả proxy
  duy nhất trả **`407 Proxy Authentication Required`**. Tài khoản proxy hết hạn hoặc sai thông tin xác
  thực, giống hệt sự cố ngày 01/10.
- 7 ngày qua: Booking 98% thành công khi chạy được, các kênh còn lại **17–31%**.
- Spec gốc đặt tiêu chí thành công **≥90% probe thành công mỗi lượt**
  (`docs/superpowers/specs/2026-09-24-hotel-competitor-monitor-design.md` mục 1). Hiện không đạt.
- Cảnh báo vận hành chỉ ghi log (`docs/user-flows.md:147`), nên không ai biết.
- Báo cáo 01/10 đã cảnh báo proxy là điểm hỏng đơn. Code đã hỗ trợ nhiều template proxy
  (`backend/app/collector/proxy.py:26-50`), nhưng `.env` chỉ có **1 template (dạng IP tĩnh)**, chưa có
  `SMTP_HOST` và `OPS_ALERT_EMAILS`, nên cảnh báo vận hành rơi về `LogAlerter`
  (`backend/app/ops/alerts.py:63-71`). Xoay vòng template hiện là xoay mù, chưa bỏ qua template đang lỗi.

**Cách sửa:**
- Proxy ≥2 nhà cung cấp, kiểm tra trước mỗi lượt và tự chuyển khi lỗi.
- Báo operator qua email và webhook (Slack/Discord/Google Chat; sau này Zalo) trong 15 phút khi một kênh
  không có dữ liệu. Không dùng Telegram: bị chặn ở Việt Nam từ 21/05/2025 (mục 3.2).
- Hiện cho khách sạn một chỉ số SLA: % lượt quét thành công 7 ngày, theo kênh.
- Tự báo khách sạn khi dữ liệu cũ hơn một chu kỳ quét.

**C2. "Cập nhật lúc…" có thể nói sai.**
- `last_run` lấy lượt quét đã kết thúc gần nhất, kể cả lượt thu 0 dữ liệu
  (`backend/app/api/routers/data.py:304`).
- Màn "Hôm nay" hiện "Quét lúc 06:00" dù lượt đó không đọc được trang nào
  (`dashboard/src/app/(app)/today/page.tsx:75`).
- Màn này còn tính "hôm nay" theo giờ trình duyệt, không theo múi giờ tenant
  (`today/page.tsx:45`; Bảng điều khiển thì dùng `useTenantToday`).
- Bảng điều khiển có tô đỏ lượt quét rỗng (`dashboard/src/app/(app)/dashboard/side-cards.tsx:136`), nhưng
  các màn khác không.

**Cách sửa:** hiện "dữ liệu mới nhất lúc …" theo **quan sát thành công cuối cùng của từng kênh**; mỗi
giá có tuổi dữ liệu; quá ngưỡng thì gạch xám.

**C3. Email chưa từng tới tay khách.** 39/39 dòng `notifications` ở trạng thái `skipped` (máy chủ email
chưa cấu hình). Cảnh báo và bản tin đang chỉ nằm trong DB.

**C4. Một số kênh không cho tín hiệu tồn phòng, nhưng giao diện chưa nói rõ.**

| Kênh | exact | capped (ít nhất N) | hidden | sold_out |
|---|---|---|---|---|
| Booking | 49,7% | 36,1% | 14,2% | – |
| Agoda | 77,6% | – | – | 22,4% |
| iVIVU | – | – | **100%** | – |
| Trip.com | – | **100%** | – | – |
| Mytour | – | 88,4% | 11,6% | – |

Chỉ Booking và Agoda cho tín hiệu phòng còn dùng được. iVIVU, Trip.com, Mytour nên được trình bày là
kênh **"giá và parity"**, không phải kênh **"phòng còn"**, cả trong giao diện lẫn tài liệu bán hàng.

### 5.2 Tên và định nghĩa chỉ số (P0: rẻ, ảnh hưởng uy tín lớn)

Người làm revenue đọc "ADR", "RevPAR", "cùng kỳ" theo định nghĩa của nghề. Dùng sai tên là lỗi uy tín,
kể cả khi đã có chú thích nhỏ.

| Chỉ số trên giao diện | Thực chất đang tính | Chuẩn nghề | Đề xuất |
|---|---|---|---|
| **"ADR compset"** (`dashboard/src/app/(app)/dashboard/page.tsx:156-161`, `messages/vi/dashboard.json:29-33`) | Trung bình **giá niêm yết thấp nhất** của đối thủ | ADR = doanh thu phòng / số phòng đã bán (giá **thực thu**) | Đổi thành "Giá niêm yết TB đối thủ" (hoặc "BAR TB compset"). Chỉ dùng "ADR" cho số PMS của bạn |
| **"RevPAR compset ≈"** (`page.tsx:147,189`; `vi/dashboard.json:34-38`) | Giá niêm yết TB × công suất ước tính | RevPAR = doanh thu phòng / số phòng sẵn có | Bỏ khỏi KPI chính. Nếu giữ thì để ở mục nâng cao, tên "Chỉ số doanh thu ước tính (không phải RevPAR)" |
| **"Công suất compset ≈"** (`backend/app/market/occupancy.py:66-73`) | 1 − phòng còn / **số phòng lớn nhất từng thấy trên kênh**, tức tỷ lệ lấp đầy phần phòng kênh mở bán. Cùng nhóm khách sạn: trung bình Agoda ≈50%, Booking ≈33–43% | Occupancy = phòng bán / tổng phòng của khách sạn | Đổi thành "Chỉ báo lấp đầy trên <kênh> (thử nghiệm) ≈", hiện khoảng [thấp, cao]. Luôn hiện sai số hiệu chỉnh PMS (hàm `calibrate` đã có); chưa có PMS thì ghi "chưa hiệu chỉnh". Về gốc: lấy tổng phòng từ số công bố hoặc người dùng nhập (mục 3.3) |
| **"Dự báo cầu"** 14 đêm (`dashboard/demand-forecast.tsx`; `lib/market-metrics.ts:30-35`) | Mức căng **hiện tại**. Trộn hai thang đo khác nhau (công suất ước tính, hoặc tỷ lệ đối thủ hết phòng) vào cùng một điểm 0–100 | Forecast là dự báo kết quả cuối kỳ, có phương pháp | Đổi thành "Mức căng thị trường hiện tại". Chỉ gọi là dự báo khi có pace và lịch sử, và nêu phương pháp |
| **"Mức nén compset"** (`lib/market-metrics.ts:124`) | % đối thủ hết hoặc còn ≤3 phòng. Với 4 đối thủ chỉ có 5 mức 0/25/50/75/100 | Compression: thị trường gần kín (công suất khu vực rất cao) | Hiện thẳng "3/4 đối thủ hết hoặc sắp hết". Không tính khi dưới 4 đối thủ quan sát. Ghép với chỉ số khu vực (số chỗ ở còn phòng Booking báo) |
| **"Doanh thu 14 ngày"** khi chưa có PMS (`messages/vi/terminal.json:66`) | Giá thấp nhất của bạn × công suất ước tính × số phòng thấy trên kênh | Doanh thu đã đặt (on the books) lấy từ PMS | Ẩn khi chưa có PMS |
| **"So cùng kỳ"** (`messages/vi/pace.json:10,51`; `backend/app/market/pacing.py:15`) | So với cùng thứ trong tuần, **1–8 tuần trước** | Ở Việt Nam "cùng kỳ" là **năm trước** (STLY) | Đổi thành "So các tuần trước (cùng thứ)". Thêm STLY khi đủ 1 năm dữ liệu |
| **Vị trí giá** (`lib/market-metrics.ts:175-180`) | "Dưới thị trường" tô xanh (tốt), "Trên thị trường" tô cam (cảnh báo) | Rẻ hơn không mặc nhiên là tốt: đêm thị trường căng mà mình rẻ hơn là **đang để mất tiền** | Màu trung tính; tô theo ngữ cảnh (rẻ hơn khi thị trường căng = cơ hội tăng giá) |
| **Hạng giá** (`backend/app/analytics/compset.py:50-54`) | 1 = rẻ nhất | Theo STR, hạng 1 = tốt nhất (ADR/RevPAR cao nhất) | Ghi rõ "Vị trí giá k/N (1 = rẻ nhất)", tách khỏi khái niệm hạng của STR |
| **Trung vị, chỉ số giá** (`compset.py:133-139`); gợi ý giá (`backend/app/market/price_suggest.py:68`) | Tính cả khi chỉ có 1 đối thủ có giá; gợi ý giá chạy khi có 2 đối thủ | CoStar STR: compset **≥4 đối thủ**, không khách sạn nào quá 50% số phòng (mục 3.3) | Hiện chỉ số khi ≥4 đối thủ có giá cùng điều kiện; 3 đối thủ thì hiện mờ, ghi "mẫu nhỏ"; dưới 3 thì ẩn. Luôn hiện n/N. Đổi tên thành "chỉ số giá niêm yết" (không dùng ARI/RPI) |
| **"Toàn cảnh thị trường đêm nay"** (`messages/vi/dashboard.json:13`) | Chỉ là compset 4–5 khách sạn | "Thị trường" là khu vực | Đổi thành "Toàn cảnh compset". Dành chữ "thị trường" cho số liệu khu vực |

### 5.3 Phương pháp rate shopping (P0–P1)

**C5. "Đổi giá" ở mức khách sạn đang lẫn "đổi giá" với "đổi cơ cấu phòng".**
- Sự kiện giá mức khách sạn so **giá thấp nhất của mọi loại phòng** giữa hai lượt
  (`backend/app/analytics/rules.py:197`). Giá đổi 7 ngày cũng vậy (`rules.py:345`).
- Khi loại phòng rẻ nhất bán hết, giá thấp nhất nhảy lên và hệ thống báo "đối thủ tăng giá", dù không ai
  đổi giá.
- Số liệu thật:

| Kênh | Sự kiện mức KS | Tổng | Cùng lượt có loại phòng xuất hiện/biến mất | Không có loại phòng nào đổi giá cùng chiều |
|---|---|---|---|---|
| Booking | price_up | 127 | 105 (83%) | 56 (44%) |
| Booking | price_down | 247 | 74 (30%) | 48 (19%) |
| iVIVU | price_up | 77 | 77 (100%) | 0 |
| Trip.com | price_down | 325 | 87 (27%) | 8 |

- Cảnh báo "đối thủ giảm giá" dùng đúng loại sự kiện mức khách sạn này
  (`backend/app/notify/alert_rules.py:186-223`).
- Chuẩn rate shopping: so cùng loại phòng và cùng gói giá. Phòng rẻ nhất hết là **tín hiệu cầu**, không
  phải đổi giá.

**Cách sửa:** tách hai loại sự kiện.
- **Đổi giá thật:** cùng loại phòng, cùng gói. Dùng cho cảnh báo và cho "giá đổi 7 ngày".
- **Đổi giá thấp nhất do cơ cấu:** phòng rẻ nhất hết hoặc mở lại. Đưa vào tín hiệu cầu.

**C6. Nhiễu loại phòng.**
- iVIVU: 3.410 `room_type_gone` và 2.668 `room_type_new`; Mytour 836/580; Booking 440/220.
- Nguyên nhân có thể: id phòng không ổn định, hoặc nguồn bán lại thay đổi giữa các lượt.
- Một quản lý khách sạn sẽ tắt thông báo nếu dòng sự kiện toàn nhiễu.

**Cách sửa:**
- Chỉ báo "mất loại phòng" khi vắng ≥2 lượt liên tiếp.
- Chuẩn hoá khoá loại phòng theo kênh.
- Không đưa `room_type_new`/`room_type_gone` vào cảnh báo.

**C7. Cơ sở so sánh chưa đủ.**
- Hiện chỉ có "mọi giá" và "hoàn huỷ".
- Ở Việt Nam, giá gồm bữa sáng rất phổ biến; đặt giá chỉ phòng cạnh giá có bữa sáng là so lệch.
- Parser Booking **không bao giờ** trả `breakfast=false`: 0/24.731 dòng giá trong 10 ngày
  (`backend/app/collector/booking/parser.py:113` chỉ nhận "breakfast included").
- 8,7% dòng giá Booking không rõ đã gồm thuế hay chưa.

**Cách sửa:**
- Thêm cơ sở "có bữa sáng" và "chỉ phòng".
- Nhận diện "no meals" / "breakfast not included".
- Dòng giá không rõ thuế: không đem so chéo kênh.

**C8. Parity chưa so cùng điều kiện và chưa nói nguyên nhân.**
- Parity so giá thấp nhất của **bất kỳ gói nào** giữa các kênh
  (`backend/app/analytics/cross_channel.py:54-93`), và không phân biệt KM do kênh tự áp với giá khách sạn
  tự đặt.
- **Mytour:** mã `CHAMTHU26` gắn trên **100%** giá trong 10 ngày, giảm trung bình 18,6% so với giá gốc.
  Có **160 sự kiện parity trên Mytour**, chênh trung bình 22,1%: phần lớn nhiều khả năng do mã của kênh,
  không phải khách sạn bán rẻ.
- **Booking:** 6.186 dòng giá có giá gạch, phần lớn mang nhãn "Late Escape Deal" (4.440 dòng; KM do khách
  sạn tự bật), giảm trung bình 44,6% so với giá gạch. 75 sự kiện parity trên Booking (chênh TB 17,8%) có
  thể chính là KM do khách sạn tự bật.
- Chưa có **website đặt phòng trực tiếp** (brand.com) làm mốc. Theo chuẩn, parity là so với giá công bố
  trên kênh trực tiếp.

**Cách sửa:**
- So từng cặp cùng điều kiện (hạng phòng tương đương, cùng hoàn huỷ, cùng bữa sáng).
- Gắn nguyên nhân cho mỗi cảnh báo: KM kênh tự áp / KM khách sạn bật / nguồn bán lại (`source_supplier`)
  / giá thường.
- Hiện cả giá trước KM.
- Báo dạng Win/Meet/Loss có dung sai (mục 3.3).
- Thêm website trực tiếp làm mốc (mục N15).

**C9. Chỉ một cấu hình tìm kiếm.**
- Hiện chỉ có: 2 người lớn, 1 đêm (hoặc số đêm tối thiểu), desktop, POS Việt Nam, không đăng nhập.
- Rate shopper chuẩn cho chọn số đêm (1/2/3/7), số khách (1/2/gia đình), thiết bị (mobile), POS.
- Resort cần giá 2 đêm; khách sạn công tác cần giá 1 người.

**Cách sửa:** thêm biến thể theo mẫu (một số đêm, một số khách sạn), có ngân sách request riêng (P2).

### 5.4 Dữ liệu của chính khách sạn (P1)

**C10. PMS không lưu "tính đến ngày nào".**
- `own_hotel_daily` chỉ có `stay_date`, nhập lại thì ghi đè (`backend/app/db/models.py:363-376`).
- Vì vậy **không tính được** pickup (phòng mới đặt thêm 1/7 ngày qua), pace (so với cùng thời điểm các
  tuần trước) hay STLY của chính khách sạn. Đây là xương sống của mọi quyết định giá.
- Chỉ số thật của mình (Occ/ADR/RevPAR) chỉ có khi khách nhập file, và không có lịch sử.

**Cách sửa:**
- Thêm bảng `otb_snapshots(as_of_date, stay_date, rooms_otb, revenue_otb, rooms_available, [huỷ, khối
  phòng đoàn, segment, kênh])`.
- Hoặc nhận **file đặt phòng chi tiết** rồi tự dựng lại snapshot cho cả quá khứ. Cách này cho pace và STLY
  ngay từ ngày đầu.
- Nhập hằng ngày: upload, gửi email đính kèm, sau này API ezCloud.
- Tính pickup 1/7 ngày, pace so 4 tuần trước và STLY, dự báo đơn giản (cộng pickup lịch sử theo thứ
  và lead time).

**C11. Mỗi tenant được giả định chỉ có một khách sạn của bạn, nhưng tenant thật là "Group".**
- Pace lấy `own_ids[0]` (`backend/app/market/pace_report.py:239`).
- Compset lấy giá thấp nhất của **mọi** khách sạn "của bạn" (`compset.py:129-132`).
- Tenant mẫu tên "Saigon Boutique Group", "Demo Hotel Group".
- Chuỗi hoặc công ty quản lý có 2+ khách sạn sẽ thấy số sai.

**Cách sửa:** compset riêng cho từng khách sạn của bạn, và một màn danh mục (portfolio).

### 5.5 Gợi ý giá (P1–P2)

**C12. Luật gợi ý chỉ nhìn đối thủ** (`backend/app/market/price_suggest.py`). Còn thiếu:
- **Giá sàn và giá trần** của khách sạn.
- **Mục tiêu định vị:** khách sạn review 9,2 cố ý đắt hơn trung vị 10% vẫn có thể bị gợi ý "giảm" khi
  đêm gần.
- **OTB và pickup của mình:** mới chỉ dùng công suất PMS nếu có.
- **Thứ trong tuần, lead time:** chỉ có quy tắc "≤7 ngày thì có thể giảm".
- **Đòn bẩy ngoài giá:** số đêm tối thiểu, tắt KM, đóng gói không hoàn huỷ.
- **Đo kết quả:** bảng `price_suggestion_decisions` có 0 dòng.

Chuẩn RMS cho khách sạn nhỏ: giá gốc, sàn/trần, định vị so compset, điều chỉnh theo công suất/pickup/
thứ/lead time/sự kiện, và giải thích từng điều chỉnh (xem mục 3).

### 5.6 Cảnh báo (P1)

**C13. Cảnh báo chưa hợp với cách khách sạn Việt Nam làm việc.**
- Chỉ có email. Chưa có giờ im lặng, chưa chọn được theo từng người nhận.
- Các loại cảnh báo nghiêng về "đối thủ" (hết phòng, sắp hết, giảm giá, parity;
  `backend/app/notify/kinds.py:12-37`). Còn thiếu:
  - đêm căng / cơ hội tăng giá;
  - đối thủ **tăng** giá (cùng điều kiện);
  - giá của bạn lệch khỏi mục tiêu định vị;
  - bạn hết phòng hoặc bị đóng trên một kênh;
  - dữ liệu đã cũ.

### 5.7 Lịch cầu (P2)

**C14. Lịch cầu thiếu và đã lệch thực tế** (`backend/app/holidays/data.py:44-67`).
- **Sai so với lịch nghỉ chính thức đã công bố:**
  - **24/11 "Ngày Văn hóa Việt Nam"** là ngày nghỉ hưởng lương mới từ 2026 (đã xác nhận trên
    chinhphu.vn). Ngày này nằm trong horizon 90 ngày (còn 46 ngày) nhưng chưa có trong dữ liệu. Số ngày
    nghỉ năm 2026 (1 hay 4 ngày) cần xác minh.
  - **Tết 2027:** nghỉ chính thức 04–10/02/2027; code chỉ đánh dấu 05–09/02.
  - **2/9/2026:** nghỉ 5 ngày; code chỉ có 02–03/09.
- Chỉ có ngày lễ của nước tenant. Thiếu lễ của **thị trường nguồn**, trong khi 9 tháng 2026 có Trung Quốc
  3,9 triệu lượt, Hàn 3,0 triệu, Nga 1,1 triệu (+161%), Đài Loan 964 nghìn, Nhật 674 nghìn, Ấn 671
  nghìn (+33%):
  - Hàn: Seollal, Chuseok. Đà Nẵng làm KM riêng cho khách Hàn dịp Chuseok 21–27/09/2026.
  - Trung: Xuân Tiết, Quốc khánh 1–7/10.
  - Nhật: Golden Week.
  - Mùa đông của khách Nga (Nha Trang, Phú Quốc), mùa cưới Ấn Độ (Phú Quốc, Đà Nẵng).
- Thiếu nghỉ hè học sinh Việt Nam và sự kiện lớn có lịch công khai.
- Định nghĩa "cuối tuần" không thống nhất: T6–CN (`dashboard/src/lib/market-metrics.ts:185`) và
  T7–CN (`dashboard/src/lib/format.ts:69-72`, `holidays/data.py` `is_weekend`). Với khách sạn, đêm cuối
  tuần là **đêm thứ Sáu và thứ Bảy**.
- **Thuế:** VAT 8% áp dụng tới 31/12/2026. Horizon 90 ngày đã vượt qua 01/01/2027; nếu VAT trở lại
  10%, giá đã gồm thuế tăng khoảng 1,9% (1,05 × 1,10 so với 1,05 × 1,08) mà không ai đổi giá. So sánh
  qua mốc này (pace, cùng kỳ) phải biết điều đó.

### 5.8 Lỗi tiềm ẩn và giao diện thiếu nhất quán (từ audit dashboard)

Đường dẫn giao diện dạng `dashboard/…`, `competitors/…`, `rates/…`, `terminal/…`, `availability/…`,
`hotels/…` trong mục này tính từ `dashboard/src/app/(app)/`.

**C15 (P0, lỗi tiềm ẩn). Giá Booking của đêm có số đêm tối thiểu >1 không chia theo đêm.**
- Khi calendar báo số đêm tối thiểu N >1, worker probe N đêm (`backend/app/worker/jobs.py:168-170`).
- Parser Booking lưu giá đang hiển thị, tức **giá tổng N đêm** (`backend/app/collector/booking/parser.py:97-131`).
  Trip.com thì có chia theo đêm (`backend/app/collector/tripcom/parser.py:274-275`).
- DB hiện 100% probe là 1 đêm nên chưa thấy. Nhưng đúng vào dịp lễ (Tết, 30/4, 2/9), khi khách sạn đặt
  min-stay 2–3 đêm, giá Booking sẽ gấp 2–3 lần. Hệ quả: sự kiện "tăng giá +100%", cảnh báo sai, chỉ số
  giá sai **đúng lúc quan trọng nhất**.

**C16 (P0). Trộn kênh trên cùng một màn hình.**
- `/market/pace` và `/market/occupancy` không nhận tham số kênh, luôn dùng kênh tham chiếu
  (`backend/app/market/pace_report.py:229`; `dashboard/src/lib/api.ts:276`).
- Trong khi đó `/overview` đi theo bộ chọn kênh. Chọn Agoda thì "RevPAR", thẻ "Khách sạn của bạn", hàng
  công suất trên heatmap lấy **giá Agoda nhân công suất Booking**
  (`dashboard/src/app/(app)/dashboard/page.tsx:54`, `availability/page.tsx:41-43`,
  `dashboard/side-cards.tsx:105-124`).

**C17 (P1). Không chặn dữ liệu cũ trong compset.**
- Compset lấy chỉ số mới nhất của mỗi đối thủ, không xét tuổi dữ liệu (`backend/app/analytics/compset.py:124`).
- Listing đã tạm dừng hoặc bị chặn nhiều ngày vẫn góp giá cũ vào trung vị.
- **Cách sửa:** chỉ dùng quan sát ≤48 giờ, và hiện tuổi dữ liệu từng đối thủ.

**C18 (P1). Cùng một khái niệm, nhiều cách tính.**
- **Trung bình và trung vị lẫn nhau:** "giá TB thị trường" và "Vị trí giá" dùng trung bình
  (`dashboard/src/lib/market-metrics.ts:120,175-180`), chỉ số giá và gợi ý giá dùng trung vị. Cùng một
  trang có thể ra hai kết luận ngược nhau.
- **Ba thang "cầu cao/vừa/thấp" khác nhau:**
  - 60/40 (`market-metrics.ts:20`);
  - 75/50 (`dashboard/src/app/(app)/terminal/terminal-cards.tsx:19-24`);
  - 90/75 (`dashboard/src/app/(app)/availability/heatmap-table.tsx:67-71`).
  - Hệ quả: 65% đọc là "Cao" ở Bảng điều khiển nhưng "cân bằng" ở Terminal+.
- **Cùng dấu, khác nghĩa:** "−10%" màu đỏ ở trang Đối thủ nghĩa là đối thủ rẻ hơn
  (`competitors/page.tsx:41,77`); "−10%" màu xanh ở Giá & định giá nghĩa là bạn rẻ hơn
  (`rates/rate-views.tsx:137,153`).
- **Đơn vị heatmap giá:** bỏ hậu tố "Tr" nhưng ghi chú "Đơn vị: triệu đồng"; giá 850.000 hiện "850 N"
  cạnh "1,3" (`rates/rate-views.tsx:225`, `messages/vi/rates.json:66`).
- **"Cập nhật" mỗi tab một nghĩa:** Bảng điều khiển lấy lượt mới nhất bất kỳ, kể cả lượt đang chạy và
  lượt thị trường (`backend/app/api/routers/data.py:611-615`); tab khác lấy lượt đã kết thúc
  (`data.py:304`).

**C19 (P1). Quyết định chính bị chôn.**
- Gợi ý giá nằm cuối tab "Terminal+", dưới 4 thẻ và lịch 12 tháng (`terminal/page.tsx:99-117`). Tên tab
  không nói lên nội dung.
- Gợi ý chỉ ghi "+10%", không ra **giá mục tiêu bằng VND**, không nói loại phòng/gói nào
  (`dashboard/src/components/market-suggestion.tsx:55-57`).
- "Hôm nay", màn dành cho buổi sáng, chỉ mở được từ menu Trợ giúp (`components/app-shell.tsx:147-149`).
- Khung ngày cố định: 14 đêm (Bảng điều khiển, Đối thủ), 30 đêm (Giá). Không xem trước vị trí giá dịp
  Tết được.

**C20 (P2). Ngày lễ và sự kiện không hiện ở nơi ra quyết định.**
- Không có dấu lễ/sự kiện ở Bảng điều khiển, Phòng trống, Giá & định giá, Đối thủ.
- Chi tiết khách sạn truyền `holidays: []` (`hotels/[id]/page.tsx:204`).
- Sự kiện người dùng nhập (kèm "% tăng cầu dự kiến") không đi vào chỉ số hay gợi ý nào.

**C21 (P2). Thông điệp marketing của kênh thành số tiêu đề.**
- "Tín hiệu đặt phòng" cộng các câu "đặt N lần hôm nay" của mọi khách sạn thành một con số lớn
  (`terminal/terminal-cards.tsx:176-188`).
- **Cách sửa:** liệt kê theo từng khách sạn, kèm nguồn kênh.

**C22 (P2). Ước tính trình bày như số bán thật, và một từ hai nghĩa.**
- "Pickup 24h", "Tốc độ 3 ngày", "Đối thủ đã bán/bán thêm" thực chất là **số phòng còn giảm đi**:
  đóng bán hay hạn chế cũng làm số này giảm (`messages/vi/hotels.json:11-12`, `messages/vi/pace.json:48-50`).
  Nên ghi "≈ phòng còn giảm".
- "Sự kiện" vừa là nhật ký thay đổi (`messages/vi/events.json:2`) vừa là lễ hội/MICE
  (`messages/vi/settings.json:11`).

## 6. Chức năng cần bổ sung

Cột "Dữ liệu": **Có** = đã thu, chỉ cần tính và hiển thị · **Một phần** = cần sửa parser hoặc lưu thêm ·
**Mới** = cần nguồn hoặc request mới. Effort: S ≤ 3 ngày · M ≈ 1–2 tuần · L > 2 tuần (1 dev).

### 6.1 Nhóm "dữ liệu đã thu nhưng chưa dùng" (giá trị cao, gần như 0 request thêm)

| ID | Tính năng | Câu hỏi của quản lý khách sạn | Dữ liệu | Effort |
|---|---|---|---|---|
| **N1** | **Radar khuyến mãi đối thủ.** Loại KM và tên chiến dịch (Late Escape, Limited-time, Getaway, Black Friday, Flash Sale…), độ sâu (so giá gạch), số đêm áp dụng, ngày bật/tắt. VD (giả định): "Đối thủ A bật Late Escape Deal −40% cho 12 đêm từ 14/10". Chưa công cụ nào báo theo từng đối thủ (mục 3.4) | "Đối thủ đang chạy KM gì, sâu bao nhiêu, từ bao giờ?" | **Có.** Trong 10 ngày: `promo_label` trên 6.186 dòng giá Booking (kèm giá gạch), 5.932 dòng Agoda ("Ưu đãi Chớp nhoáng"), Trip.com, iVIVU ("Early Bird"), Mytour (mã kênh). API và giao diện chưa hiện (`grep promo_label` trong `backend/app/api` = 0) | S |
| **N2** | **Radar hạn chế bán.** Số đêm tối thiểu, đóng bán, đóng một kênh của đối thủ theo đêm. VD (giả định): "Đối thủ B đặt tối thiểu 2 đêm cho 30/4". Giá kèm hạn chế không đem so với giá 1 đêm (mục 3.3) | "Đối thủ có khoá min-stay dịp lễ không?" (một đòn bẩy revenue phổ biến) | **Có.** `hotel_calendars.min_length_of_stay` đã lưu; `channel_closed` đã có | S |
| **N3** | **Chính sách huỷ của đối thủ.** % gói hoàn huỷ, mức giảm của gói không hoàn huỷ so với gói linh hoạt | "Đối thủ giảm bao nhiêu cho non-refundable? Mình có đang giảm quá tay?" | **Có.** Cờ `refundable` trên mọi dòng giá | S |
| **N4** | **Uy tín đối thủ theo thời gian.** Điểm, số review, **tốc độ review/tháng** (xấp xỉ lượng khách lưu trú), khoảng cách tới các mốc 7,0 / 7,5 / 8,0 / 9,0 của Booking; bản đồ giá–chất lượng (chỉ số giá niêm yết so với chỉ số điểm, cùng một nền tảng, trình bày là tương quan chứ không phải nhân quả) | "Mình có đủ điểm để bán đắt hơn đối thủ không?" | **Một phần.** Thẻ kết quả tìm kiếm có điểm và số review (đang ghi đè vào `hotels.review_score`). Cần bảng chuỗi thời gian | S–M |
| **N5** | **Vị trí hiển thị trên Booking.** Thứ hạng trang 1 (thứ tự mặc định) theo đêm cho bạn và đối thủ; huy hiệu trên thẻ: Preferred, Genius, Ad, deal, "Free cancellation", "Breakfast included" | "Khách tìm quận 1 có thấy mình không? Đối thủ nào đang mua hiển thị?" | **Một phần.** `market_area_hotels.best_rank` chỉ giữ giá trị mới nhất; HTML thẻ có "Preferred Partner", "Genius", "Late Escape Deal" (đã kiểm trong fixture `searchresults_hcmc_2026-10-09.html.gz`) | M |
| **N6** | **Chỉ số khan phòng khu vực theo lead time.** Số chỗ ở còn phòng Booking báo, theo đêm và theo số ngày trước khi đến; so với tuần trước, sau này với năm trước | "Cả quận còn bao nhiêu khách sạn trống cho đêm 30/4, giảm nhanh hơn năm ngoái không?" | **Có.** `market_list_scans.properties_found` mỗi đêm | S–M |

### 6.2 Nhóm "ra quyết định" (cần dữ liệu của chính khách sạn)

| ID | Tính năng | Câu hỏi của quản lý khách sạn | Dữ liệu | Effort |
|---|---|---|---|---|
| **N7** | **OTB, pickup và pace của bạn.** Snapshot "tính đến ngày" hằng ngày; pickup 1/7 ngày; pace so 4 tuần trước và năm trước; dự báo đơn giản (cộng pickup lịch sử) | "Đêm 20/10 mình đã bán bao nhiêu, nhanh hay chậm hơn bình thường?" | **Mới** (bảng + luồng nhập hằng ngày) | M |
| **N8** | **KPI thật và chỉ số kiểu STR.** Occ/ADR/RevPAR từ PMS; chỉ số giá niêm yết (cách tính giống ARI nhưng trên giá niêm yết, không đặt tên ARI) có cỡ mẫu và vị trí; MPI/ARI/RGI thật chỉ khi có số thật của compset (N18) | "Báo cáo tháng cho chủ đầu tư" | Một phần | S–M |
| **N9** | **RMS-lite có giải thích.** Giá gốc, sàn/trần, định vị mục tiêu so compset (VD "+5% trên trung vị vì điểm 9,1"); điều chỉnh theo OTB/pickup, thứ, lead time, sự kiện; gợi ý cả **hạn chế** (min-stay, tắt KM); nhật ký "đã áp dụng" và **đo kết quả** sau đêm lưu trú | "Hôm nay nên đặt giá bao nhiêu cho 14 đêm tới, vì sao?" | Cần N7 | M–L |
| **N10** | **Compset chính/phụ, trọng số, rà soát định kỳ.** Gợi ý thay đối thủ đã lệch hạng/giá/điểm | "Compset của mình còn đúng không?" | Có (khám phá thị trường) | S–M |
| **N11** | **Nhiều khách sạn (portfolio).** Compset riêng cho từng khách sạn của bạn; màn tổng cho chuỗi/công ty quản lý | "Tôi quản lý 3 khách sạn" | Sửa mô hình | M–L |

### 6.3 Nhóm "đến đúng người, đúng lúc"

| ID | Tính năng | Ghi chú | Effort |
|---|---|---|---|
| **N12** | **Zalo ZNS** (email dự phòng, PWA push là phương án phụ). Giờ im lặng, chọn loại tin theo từng người, nút "Xem chi tiết" và "Đã xử lý" trong tin | Zalo: 81,3 triệu người dùng/tháng; 200–300₫/tin; cần OA doanh nghiệp xác thực và template được duyệt. Không chọn Telegram vì bị chặn ở Việt Nam từ 05/2025 | M |
| **N13** | **Báo cáo đúng mẫu khách sạn dùng.** File Excel "rate shop" (khách sạn × đêm: giá, trạng thái, KM, hạn chế); báo cáo tháng PDF cho chủ đầu tư; nhật ký quyết định giá và kết quả | Chủ đầu tư đọc báo cáo, không mở dashboard | M |
| **N14** | **Lịch cầu đầy đủ.** Lễ thị trường nguồn (Hàn, Trung, Nhật, Đài Loan, Ấn…), nghỉ hè, sự kiện lớn có lịch công khai; dải "năm trước dịp này" | Nhập sẵn mỗi năm, người dùng thêm sự kiện địa phương (đã có) | S–M |

### 6.4 Nhóm mở rộng (làm khi có khách trả tiền yêu cầu)

| ID | Tính năng | Ghi chú | Effort |
|---|---|---|---|
| **N15** | **Parity với website trực tiếp** (booking engine của khách sạn) và Google Hotels theo mẫu, có ảnh chụp làm bằng chứng | Mốc parity chuẩn là kênh trực tiếp | M–L |
| **N16** | **Biến thể tìm kiếm** (2 đêm, 1 khách, mobile) theo mẫu đêm và khách sạn | Ngân sách request riêng | M–L |
| **N17** | **Hỏi đáp dữ liệu bằng tiếng Việt** ("đêm 30/4 đối thủ nào còn phòng, giá bao nhiêu?"): trả lời bằng truy vấn có kiểm chứng, kèm link tới số gốc | Theo xu hướng "AI teammate" 2026; giữ nguyên tắc chỉ nói điều có bằng chứng | M |
| **N18** | **Benchmark cộng đồng.** Khách sạn góp OTB/kết quả thật ẩn danh → MPI/ARI/RGI thật theo khu vực | Lợi thế dài hạn; cần ≥5 khách sạn mỗi khu vực, có điều khoản dữ liệu | L |
| **N19** | **Tự đăng ký, dùng thử, thanh toán** (chuyển khoản/VNPay, hoá đơn điện tử) | Điều kiện để bán số lượng | L |

## 7. Ý tưởng business

### 7.1 Định vị

**Khách hàng mục tiêu, theo thứ tự đề xuất:**
1. **Khách sạn độc lập 3–4★, 30–150 phòng, ở thành phố du lịch** (quận 1, Hoàn Kiếm, Đà Nẵng, Nha
   Trang, Phú Quốc, Hội An). Có một người làm OTA/sales/revenue đang dò giá tay và ghi Excel.
2. **Công ty quản lý / chuỗi nhỏ (2–10 khách sạn):** cần màn danh mục và báo cáo cho chủ đầu tư.
3. **Resort 4–5★:** cần giá 2 đêm, lịch lễ thị trường nguồn, khối phòng đoàn.

**Câu định vị đề xuất:**
> "Mỗi sáng biết đối thủ nào sắp kín, đang giảm giá hay khoá số đêm tối thiểu, trên Booking, Agoda và
> OTA nội địa. Báo qua Zalo, tiếng Việt, mỗi con số có bằng chứng."

**Không cạnh tranh ở:**
- Tự đặt giá / RMS đầy đủ: Agoda cho miễn phí; Lighthouse, TravelOpen, ezRms đã làm.
- Dữ liệu giá đơn thuần: đã miễn phí ở nhiều nơi (mục 3.1).

**Lợi thế dài hạn, xếp theo độ khó sao chép:**
1. **Lịch sử phòng còn và giá theo từng đối thủ, từng đêm**, nhiều năm. Có lịch sử mới làm được pace,
   cùng kỳ năm trước và mẫu mùa vụ của từng khu vực. Càng chạy lâu càng khó bắt kịp, với điều kiện dữ
   liệu **không đứt**.
2. **Radar khuyến mãi và hạn chế theo từng đối thủ:** chưa công cụ nào báo theo từng đối thủ đang chạy
   chiến dịch gì.
3. **OTA nội địa và parity giá bán sỉ** (iVIVU, Mytour lộ giá Agoda/Hotelbeds bán lại).
4. **Zalo, tiếng Việt, giá Việt.**
5. **Dài hạn: benchmark cộng đồng** (N18). Thứ STR làm, nhưng phủ khách sạn độc lập Việt Nam mỏng.

### 7.2 Gói và giá (đề xuất, cần kiểm chứng bằng 10–15 cuộc phỏng vấn khách sạn)

**Mốc tham chiếu:**
- Phần mềm khách sạn Việt Nam: 300–800 nghìn (nhỏ), 0,8–2,5 triệu (vừa), 2,5–6 triệu (3–5★).
- TravelOpen: $9–59.
- Khachsanso: 419 nghìn – 3,5 triệu.
- Lighthouse: €99 (khoảng 2,8 triệu ₫).
- Chi phí Zalo ZNS: khoảng 20–30 nghìn ₫ mỗi người nhận mỗi tháng.

| Gói | Cho ai | Nội dung | Giá đề xuất (₫/tháng/khách sạn) |
|---|---|---|---|
| **Miễn phí** (phễu) | Mọi khách sạn | Booking, 3 đối thủ, 14 đêm, 1 lượt/ngày, báo cáo tuần qua email/Zalo | 0 |
| **Cơ bản** | Độc lập 2–3★ | 5 đối thủ, Booking + Agoda, 30 đêm, 3 lượt/ngày, cảnh báo Zalo, radar KM/hạn chế, Excel | 490–690 nghìn |
| **Chuyên nghiệp** | 3–5★ có người làm revenue | 10 đối thủ, mọi kênh, 90 đêm, OTB/pace của bạn, gợi ý giá có giải thích, parity có nguyên nhân, báo cáo tháng PDF | 1,2–1,9 triệu |
| **Group** | Chuỗi / công ty quản lý | Như Chuyên nghiệp, thêm màn danh mục, phân quyền theo khách sạn, giảm theo số lượng | 0,9–1,5 triệu mỗi khách sạn |
| Thêm | Thị trường khu vực (quét cả quận/thành phố) | Chỉ số khan phòng, khám phá đối thủ, thứ hạng hiển thị | 0,5–1 triệu mỗi khu vực |

**Ước tính chi phí biến đổi.** Đây là giả định, phải đo lại bằng số thật trước khi chốt giá:
- **Đơn vị chi phí chính là băng thông proxy.** Một probe Booking khoảng 0,4 MB HTML nén (đo 01/10).
  Horizon 90 đêm theo tầng là khoảng 100 probe mỗi listing mỗi ngày, tức **khoảng 1,2 GB mỗi listing
  Booking mỗi tháng**.
- Với proxy dân cư giả định $2–5/GB, chi phí là **khoảng 60–150 nghìn ₫ mỗi listing Booking mỗi tháng**.
  Horizon 30 đêm thì khoảng một nửa. Agoda dùng API JSON nên nhỏ hơn nhiều.
- **Hệ quả 1:** gói Cơ bản (6 khách sạn × 2 kênh, 30 đêm) có chi phí proxy riêng phần Booking cỡ
  0,2–0,5 triệu ₫ nếu không chia sẻ. Biên lợi nhuận phụ thuộc vào việc **dùng chung listing giữa các tenant** (đã có) và
  vào việc tập trung khách theo khu vực.
- **Hệ quả 2:** bán theo khu vực (nhiều khách sạn cùng quận theo dõi chung đối thủ) có lợi hơn bán rải
  rác. Gói miễn phí phải giới hạn chặt (1 lượt/ngày, 14 đêm).

### 7.3 Kênh bán

- **Phễu "báo cáo đối thủ miễn phí":** dán URL khách sạn → hệ thống gợi ý 5 đối thủ từ khám phá thị
  trường → quét ngay → gửi báo cáo 14 đêm qua Zalo trong 1 giờ. Tái dùng `market/city/hotels` và
  `scan-now`.
- **Nội dung theo mùa bằng tiếng Việt,** dựa trên dữ liệu khu vực. VD "quận 1 còn 18% khách sạn trống
  đêm 24/11", "đối thủ khoá tối thiểu 2 đêm dịp Tết". Đăng ở nhóm Facebook OTA/sales và hoteljob.vn.
- **Người bán lại:** tư vấn OTA/revenue tự do và công ty quản lý khách sạn (hoa hồng định kỳ). Hiệp hội
  du lịch, khách sạn địa phương.
- **Đối tác PMS nội địa** (ezCloud, Khachsanso, Newway…): họ có OTB, ta có dữ liệu đối thủ. Tích hợp hai
  chiều biến mối đe doạ "PMS tự làm" thành kênh phân phối.
- **Bán hàng:** dùng thử 14 ngày không cần thẻ; onboarding tự động; chăm sóc khách qua Zalo OA.

### 7.4 Rủi ro chiến lược và cách phản ứng

| Rủi ro | Phản ứng |
|---|---|
| Công cụ miễn phí (Lighthouse Market Alerts, Agoda Intelligence, Booking compset) | Không bán "giá đối thủ". Bán phòng còn đích danh, radar KM/hạn chế, nhiều kênh, Zalo, báo cáo đúng mẫu Việt Nam |
| PMS nội địa đóng gói tính năng (TravelOpen, ezCloud, Khachsanso) | Làm lớp quan sát trung lập, tích hợp OTB của họ; đề nghị hợp tác trước khi họ tự làm |
| Điều khoản sử dụng và chống bot của OTA | Tư vấn pháp lý trước khi bán rộng (spec gốc đã yêu cầu). Giữ nguyên tắc không đăng nhập, không dữ liệu cá nhân, nhịp lịch sự. Cân nhắc hợp tác chính thức với OTA nội địa |
| Dữ liệu đứt làm mất niềm tin | Phase 0: SLA công khai cho khách, nhiều nhà cung cấp proxy, cảnh báo sớm |
| Chi phí proxy vượt giá bán | Tầng quét, chia sẻ listing, tập trung khu vực, giới hạn gói rẻ |

### 7.5 Chỉ số đo sản phẩm

- **North star:** số buổi sáng mỗi tuần khách sạn **có hành động** dựa trên OTARadar. Đo bằng lượt nhấn
  tin Zalo, nút "Đã xử lý", gợi ý được áp dụng.
- **Chỉ số chặn (guardrail):**
  - % lượt quét thành công theo kênh (mục tiêu ≥95% cho Booking, Agoda).
  - Độ chính xác cảnh báo (≥90% là đổi giá thật).
  - Sai số ước tính so PMS.
  - Chi phí proxy mỗi khách sạn trả tiền.
- **Thương mại:** tỷ lệ dùng thử → trả tiền, churn 90 ngày, số khách sạn mỗi khu vực.

## 8. Thứ tự ưu tiên

Nguyên tắc: **niềm tin trước, tính năng sau.** Một quản lý khách sạn bỏ công cụ vì một buổi sáng dữ liệu
sai, không phải vì thiếu một biểu đồ.

| Đợt | Thời gian (1–2 dev) | Việc | Vì sao ở vị trí này | Phase |
|---|---|---|---|---|
| **1. Cầm máu** | Tuần 1 | Khôi phục proxy và thêm nhà cung cấp thứ hai, cảnh báo operator, SMTP; sửa lỗi giá nhiều đêm (C15); thêm 24/11 và Tết 2027 vào lịch; nộp hồ sơ Zalo OA | Dữ liệu đang đứt; 24/11 còn 46 ngày; xác thực OA mất khoảng 2–3 ngày làm việc (trích đoạn), duyệt template thêm thời gian | 0 |
| **2. Nói đúng nghề** | Tuần 1–2 | Đổi tên ADR/RevPAR/dự báo/cùng kỳ; ngưỡng cỡ mẫu và tuổi dữ liệu; một màn một kênh; một khái niệm một cách tính; "Việc cần làm hôm nay" lên đầu | Chủ yếu đổi chữ, rẻ, tăng uy tín ngay | 1 |
| **3. Cảnh báo đáng tin** | Tuần 2–3 | Tách đổi giá thật và đổi cơ cấu; chống nhấp nháy loại phòng; cơ sở giá bữa sáng; parity có nguyên nhân; cờ Genius | Trước khi đẩy tin qua Zalo, tin phải đúng. Gửi tin nhiễu qua Zalo còn tệ hơn không gửi | 2 |
| **4. Đến đúng người** | Tuần 4–5 | Zalo ZNS, đăng ký theo người, loại cảnh báo mới (đêm căng, đối thủ tăng giá, lệch định vị, dữ liệu cũ) | Khác biệt rõ nhất ở thị trường Việt Nam | 3 |
| **5. Radar miễn phí request** | Tuần 4–5 (song song) | Radar KM, hạn chế, chính sách huỷ, chỉ số khan phòng khu vực | Dữ liệu đã có sẵn; là thứ công cụ miễn phí không có | 4 |
| **6. Nửa còn lại của quyết định** | Tuần 6–8 | OTB theo ngày, pickup, pace, STLY; KPI thật; nhiều khách sạn | Không có OTB thì gợi ý giá mãi là "nhìn đối thủ đoán" | 5 |
| **7. Gợi ý có trách nhiệm** | Tuần 9–11 | RMS-lite: sàn/trần, định vị mục tiêu, giải thích, gợi ý hạn chế, đo kết quả | Theo chuẩn "giải thích được" năm 2026 | 6 |
| **8. Mở rộng** | Sau tuần 11 | Uy tín, thứ hạng, compset chính/phụ, báo cáo tháng, lịch thị trường nguồn; rồi thương mại hoá và các mục dài hạn | Theo phản hồi khách trả tiền | 7–9 |

## 9. Câu hỏi cần chủ dự án quyết

1. **Khách hàng mục tiêu số 1** là khách sạn độc lập 3–4★ ở thành phố, resort, hay chuỗi/công ty quản
   lý? Câu trả lời quyết định thứ tự giữa N11 (nhiều khách sạn), N16 (giá 2 đêm) và N14 (lễ thị trường
   nguồn).
2. **Ngân sách proxy mỗi tháng** và nhà cung cấp thứ hai? (chặn Phase 0)
3. Công ty đã có **Zalo OA doanh nghiệp xác thực** chưa? Tên OA phải trùng đăng ký kinh doanh. (chặn
   Phase 3)
4. Khách hiện tại dùng **PMS nào**, có xuất được báo cáo phòng đã đặt theo ngày không? Có quan hệ với
   ezCloud/Khachsanso để xin API? (chặn Phase 5)
5. Đồng ý **bỏ "RevPAR compset"** khỏi giao diện không? (khuyến nghị: bỏ)
6. Có làm **gói miễn phí** làm phễu không, chấp nhận chi phí proxy của nó?
7. **Pháp lý:** đã tư vấn về điều khoản sử dụng của các OTA trước khi bán rộng chưa (spec gốc yêu cầu)?
8. iVIVU/Mytour: giữ quét như hiện nay để làm parity, hay giảm tần suất để tiết kiệm proxy? (chúng
   không lộ số phòng: iVIVU 100% `hidden`, Mytour 88% `capped`)
9. Có muốn theo hướng **benchmark cộng đồng** (N18) không? Cần điều khoản dữ liệu và ≥5 khách sạn mỗi
   khu vực.
10. **Ngày nghỉ 24/11/2026** là 1 hay 4 ngày? Cần đọc văn bản chính thức trước khi nhập lịch (Phase 0.10).

## 10. Nguồn

**Nội bộ:**
- Code: các `file:dòng` trong bài.
- Truy vấn chỉ đọc trên DB đang chạy, ngày 09/10/2026, khoảng 11:10: phân bố trạng thái probe theo
  kênh và ngày, `scan_jobs.error` của run 181/185/190, sự kiện theo loại, sự kiện giá mức khách sạn đối
  chiếu với `room_type_new/gone` cùng lượt, `stock_confidence` theo kênh, `occupancy_estimates`,
  `promo_label`/`price_original`/`breakfast`/`taxes_included` trong `room_snapshots.rates`,
  `notifications.status`.

**Đối thủ toàn cầu:**
- Lighthouse Market Alerts: https://data-tools.mylighthouse.com/market-alerts/
- Giá Lighthouse cho khách sạn độc lập: https://www.hotelminder.com/partner=Lighthouse
- Ernest: https://hoteltechnologynews.com/2026/06/lighthouse-launches-ernest-to-help-hotel-commercial-teams-transform-ai-insights-into-revenue-growth/ ·
  https://www.newswire.com/news/ernest-lighthouses-ai-teammate-for-hotel-commercial-teams-is-now-22871630
- Duetto mua FLYR: https://www.flyrhospitality.com/resources/duetto-acquires-flyr-hospitality
- Duetto Advance: https://www.guestex.io/insights/signals/duetto-advance-ai-storytelling/
- Mews RMS và bản tin sáng: https://revpargenius.com/insights/mews-rms-siteminder-unfold-2026
- RoomPriceGenie Price Explanations (trích đoạn): https://hospitalitytech.com/roompricegenie-launches-price-explanations-unbox-opaque-revenue-algorithms
- PriceLabs hotel rate shopper: https://hotels.pricelabs.co/hotel-rate-shopper/ ·
  https://lodgingmagazine.com/pricelabs-announces-launch-of-updated-hotel-rate-shopper/
- Cloudbeds PIE (trích đoạn): https://myfrontdesk.cloudbeds.com/hc/en-us/articles/115002822894-PIE-Rate-Shopper
- Mức độ người dùng không tin gợi ý AI: https://hoteltech.news/digest/ai-distrust-revenue-management-hotels
- Agoda Partner Portal: https://www.agoda.com/press/agoda-unveils-agoda-partner-portal-as-the-refreshed-platforms-role-in-property-management-expands/
- Booking peer group và competitive set: https://partner.booking.com/en-gb/help/performance/analytics/using-peer-group-and-competitive-set

**Việt Nam:**
- TravelOpen: https://travelopen.ai/vi · https://travelopen.ai/pricing
- ezCloud: https://ezcloud.vn/bang-bao-gia-phan-mem-khach-san · https://ezcloud.vn/en/product/ezrms-en
- Khachsanso: https://khachsanso.vn/bang-gia · https://www.khachsanso.vn/blog/ai-theo-doi-gia-doi-thu-tu-dong-rate-intelligence
- Mô tả công việc OTA/Revenue: https://www.hoteljob.vn/viec-lam/352670-ota-sales-revenue-executive
- Thị trường OTA: https://cafebiz.vn/mieng-banh-dat-ve-du-lich-truc-tuyen-huong-toi-quy-mo-gan-5-ty-usd-doanh-nghiep-ngoai-tiep-tuc-ap-dao-17626062511365651.chn ·
  https://www.staah.com/news/staah-announces-southeast-asias-top-booking-channels-for-2025/
- Khách quốc tế 9 tháng 2026: https://vnexpress.net/top-10-thi-truong-khach-quoc-te-den-viet-nam-trong-9-thang-5127940.html ·
  https://mekongasean.vn/trung-quoc-han-quoc-dan-dau-nguon-khach-quoc-te-den-viet-nam-trong-9-thang-60416.html
- Ngày nghỉ 24/11: https://xaydungchinhsach.chinhphu.vn/ngay-24-11-hang-nam-la-ngay-van-hoa-viet-nam-nguoi-lao-dong-duoc-nghi-huong-nguyen-luong-119260113152642414.htm
- Lịch nghỉ Tết 2027 (trích đoạn): https://dantri.com.vn/noi-vu/chinh-thuc-chot-nghi-tet-nguyen-dan-2027-keo-dai-7-ngay-lien-tiep-20260919232245866.htm
- Zalo ZNS: https://zalo.cloud/zns/pricing · gói OA: https://zalo.solutions/oa/pricing ·
  người dùng Zalo (trích đoạn): https://vng.com.vn/news/press-release/bctc-q2-2026.html
- Telegram bị chặn (trích đoạn): https://vinahost.vn/telegram-bi-chan/
- VAT 8% (trích đoạn): https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Nghi-quyet-204-2025-QH15-giam-thue-gia-tri-gia-tang-662685.aspx
- Mặt bằng giá phần mềm khách sạn: https://monamedia.co/gia-phan-mem-quan-ly-khach-san/

**Chuẩn revenue management:**
- CoStar/STR glossary: https://www.costar.com/products/str-benchmark/resources/glossary
- CoStar/STR compset guidelines: https://www.costar.com/products/str-benchmark/resources/guidelines/competitive-set-guidelines
- HSMAI glossary:
  - BAR: https://academy.hsmai.org/glossary/bar/
  - Pickup: https://academy.hsmai.org/glossary/pick-up-or-pace-report/
  - Parity: https://academy.hsmai.org/glossary/rate-parity/
- Lighthouse:
  - So cùng điều kiện: https://www.mylighthouse.com/resources/blog/how-to-get-a-fuller-picture-of-your-competitors-room-rates
  - Parity Win/Meet/Loss: https://www.mylighthouse.com/resources/blog/parity-system-for-hotels
  - Chọn compset: https://www.mylighthouse.com/resources/blog/hotel-competitive-set-find-yours
- Revfine (lỗi dữ liệu rate shopping): https://www.revfine.com/hotel-rate-shopping-8-reasons-competitor-rate-data-is-wrong/
- Access RMS: https://help-rms.theaccessgroup.com/en/articles/11880938-view-and-compare-competitor-pricing
- Booking `roomstosell`: https://developers.booking.com/connectivity/docs/b_xml-availability
- Which? (thông điệp "còn 1 phòng"): https://www.which.co.uk/news/article/booking-com-still-misleading-holidaymakers-with-1-room-left-claims-aSNln2j8gkGl
- Suzuki 2023 (ước tính công suất từ OTA): https://www.jstage.jst.go.jp/article/jgtr/8/1/8_61/_article/-char/en
- Weatherford & Kimes (dự báo pickup): https://hdl.handle.net/1813/72130
- OPERA pace: https://docs.oracle.com/en/industries/hospitality/opera-cloud/23.1/ocsuh/c_reports_reservation_booking_pace_reservation_pace.htm
- RoomPriceGenie (cấu trúc gợi ý giá): https://help.roompricegenie.com/en/knowledge/understand-price-suggestion
- Atomize (giới hạn giá): https://help.atomize.com/migration/pricing-controls-and-price-hierarchy
- Compression nights: https://revenue-hub.com/hotel-compression-nights-trend/

**Tín hiệu ngoài giá:**
- Booking "How we work": https://www.booking.com/content/how_we_work.html
- Booking xếp hạng: https://partner.booking.com/en-us/help/growing-your-business/analytics-reports/search-results-ranking-and-visibility
- Genius: https://partner.booking.com/en-us/help/growing-your-business/tools-programs/understanding-genius-marketing-program
- Preferred: https://partner.booking.com/en-us/help/growing-your-business/tools-programs/understanding-preferred-partner-program
- Deal Booking: https://partner.booking.com/en-us/help/rates-availability/rates-special-offers/setting-deals-or-promotions
- Agoda Sponsored Listings: https://agodapartnerhub.zendesk.com/hc/en-us/articles/360055391753-Sponsored-Listings
- Lighthouse "Rankings & reviews", "Rate Strategy": https://www.mylighthouse.com/resources/blog/how-to-get-most-out-of-lighthouse-rate-insight
- Lighthouse mua Hotelrank.ai: https://www.mylighthouse.com/resources/blog/lighthouse-acquires-hotelrank-ai
- RateGain Optima: https://rategain.com/hotel-rate-shopping-optima/
- TrustYou: https://www.trustyou.com/pricing/cxp/
- GuestRevu: https://www.guestrevu.com/packages-pricing
- Anderson 2012 (Cornell): https://hdl.handle.net/1813/71194
- Viglia và cộng sự 2016: https://doi.org/10.1108/ijchm-05-2015-0238
- Traveller Review Awards: https://partner.booking.com/en-us/click-magazine/bookingcom-news/traveller-review-awards-2026-guide
