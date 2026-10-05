# Nghiên cứu đối thủ: theo dõi giá/phòng đối thủ khách sạn qua OTA

Ngày: 2026-10-01 12:02 (Asia/Saigon). Mục tiêu: hiểu giải pháp, tính năng và flow của đối thủ, chọn ra tính năng nên đưa về ScrapeBooking.

Ghi chép chi tiết từng đối thủ (kèm toàn bộ link nguồn) nằm ở 3 file cùng thư mục:
- `research-261001-1202-competitor-raw-enterprise.md`: Lighthouse, RateGain, Fornova, Duetto, IDeaS, STR
- `research-261001-1202-competitor-raw-smb-ota-sea.md`: RMS/rate shopper cho khách sạn nhỏ, tool miễn phí của OTA, Việt Nam/SEA
- `research-261001-1202-competitor-raw-data-analytics.md`: API/dataset scraping, AirDNA/PriceLabs, tín hiệu nhu cầu

## Mục lục
1. Tóm tắt
2. Phương pháp và độ tin cậy
3. Bản đồ đối thủ
4. Flow chuẩn ngành so với ScrapeBooking
5. Ma trận tính năng
6. Vị thế: lợi thế, điểm yếu, mối đe doạ
7. Backlog tính năng đề xuất (3 đợt)
8. Không nên làm (YAGNI)
9. Câu hỏi còn mở
10. Nguồn chính

---

## 1. Tóm tắt

- **Đối thủ nguy hiểm nhất ở Việt Nam không phải Lighthouse/RateGain** (đắt, bán cho chuỗi, ẩn giá, phải demo). Hai đối thủ thật là:
  - **Tool miễn phí trong extranet OTA**: Booking (Pace report, Market insights, so giá với khách sạn tương tự), Agoda YCS (compset, "lowest upcoming competitor rates", app), Expedia Rev+. Miễn phí, dữ liệu booking thật từ nội bộ OTA, nhưng **chỉ là số tổng hợp ẩn danh**, chỉ một kênh, và phải tự đăng nhập vào xem.
  - **ezCloud** (PMS thị phần lớn nhất VN, chính là nguồn CSV ta đang nhập): trang ezRms ghi tối ưu giá theo "competitor rates and market demand" nhưng không mô tả nguồn hay tính năng (đã tự kiểm trang sản phẩm 01/10). Họ có thể đóng gói thêm tính năng theo dõi đối thủ bất cứ lúc nào.
- **Lợi thế thật của ta (moat):** số phòng còn lại / hết phòng **đích danh từng đối thủ, từng loại phòng, từng đêm**, 3 lần/ngày, có mức tin cậy, cộng dòng thời gian sự kiện và bản tin AI có bằng chứng. Không thấy tool SMB nào hay tool OTA miễn phí nào cung cấp. Các rate shopper chủ yếu bán **giá**, không bán **tồn phòng**.
- **Khoảng trống lớn nhất: không có kênh đẩy.** Mọi đối thủ đều gửi email sáng hoặc alert (RateGain có cả push, RoomPriceGenie báo "surge"). Ta đã phát hiện sự kiện và sinh bản tin, nhưng khách phải tự mở dashboard. Repo hiện không có code gửi thông báo. Đây là việc **giá trị cao nhất, công sức thấp nhất**.
- Khoảng trống thứ hai: **chưa biến tín hiệu thành quyết định**. Chưa có xếp hạng giá, chưa so like-for-like, chưa có gợi ý giá kèm lý do. Khoảng trống thứ ba: **chỉ có Booking.com**. Agoda rất quan trọng ở VN, có thể bù rẻ bằng Google Hotels qua SerpApi trước khi tự scrape.
- **Câu định vị đề xuất:** "Extranet cho bạn con số tổng hợp. ScrapeBooking cho biết đích danh đối thủ nào sắp kín phòng, loại phòng nào, từ lúc nào, và nhắn bạn mỗi sáng."

## 2. Phương pháp và độ tin cậy

- 3 agent nghiên cứu song song (khoảng 48 lượt search/fetch) cộng 2 lượt tự kiểm (ezRms, Booking extranet).
- Nguồn: trang sản phẩm, help center, blog vendor, HotelTechReport, Capterra, tài liệu API (Apify, Bright Data, SerpApi, AirDNA, PredictHQ, PriceLabs).
- **Giới hạn:**
  - Flow onboarding của đối thủ enterprise hầu hết nằm sau demo/đăng nhập, nên flow ở mục 4 là tổng hợp từ help center, blog và review.
  - Help center IDeaS/Duetto trả 403.
  - Giá lấy từ trang tổng hợp bên thứ ba, có thể lệch.
  - Review tiêu cực mỏng (RoomPriceGenie gần như toàn 5 sao).
  - Thái Lan/Indonesia chưa nghiên cứu.
  - Mục nào chưa kiểm chứng đều ghi rõ.

## 3. Bản đồ đối thủ

| Nhóm | Sản phẩm | Khách mục tiêu | Kênh dữ liệu | Tần suất | Tồn phòng / hết phòng đối thủ | Giá (tham khảo) |
|---|---|---|---|---|---|---|
| Rate intelligence enterprise | **Lighthouse** (ex OTA Insight): Rate / Parity / Market / Benchmark Insight, Pricing Manager, Smart Compset, Smart Distribution (2025) | Độc lập tới chuỗi, khoảng 85k KS | OTA, brand.com, metasearch, giá mobile/member, LOS, room type | Gần real-time, live shop vài giây | "availability" tuỳ gói, chưa kiểm chứng | Không công khai (HTR: từ ~$0–2/phòng/tháng) |
| | **RateGain** Navigator / Optima | Chuỗi | OTA, meta, GDS, desktop/mobile | Lịch + live shop ~15 giây | Không thấy | Không công khai |
| | **Fornova** DI/CI | Chuỗi lớn | brand.com, OTA, meta, theo POS, test booking | 2 lần/ngày | Không | Theo quy mô |
| RMS dùng giá đối thủ | **Duetto**, **IDeaS G3** | Chuỗi | Nhận rate từ shopper đối tác | n/a | n/a | Không công khai |
| Benchmark dữ liệu thật | **STR / CoStar** | Mọi hạng | KS tự đóng góp số thật, ẩn danh | T+1 / T+7 | Không (chỉ quá khứ) | Thuê bao |
| RMS / shopper cho KS nhỏ | **RoomPriceGenie** | Độc lập nhỏ | Giá đối thủ, sự kiện, pace, STR | Giá đề xuất 4 lần/ngày | Không thấy | ~$119/tháng/tính năng |
| | SiteMinder Insights, Price Seeker, RateTiger (APAC), PriceLabs Hotel Rate Shopper | Nhỏ–vừa | OTA + parity | 1 lần/ngày tới nhiều lần/ngày | Không thấy | $1–6/phòng/tháng; RateTiger ~$69/user/tháng |
| | Atomize (Mews), Lybra, Pricepoint | Vừa | Rate shop + tự đẩy giá | Real-time | Không thấy | ~€180–300/tháng |
| **Tool miễn phí của OTA** | Booking extranet (Pace, Market insights, so giá với KS tương tự) | Mọi KS trên Booking | Chỉ Booking, **tổng hợp ẩn danh**, compset tối đa 10 | Hằng ngày | Không | Miễn phí |
| | Agoda YCS | Mọi KS trên Agoda | Chỉ Agoda; compset tối thiểu 5, **đổi 1 lần/quý**; có app | Hằng ngày | Không | Miễn phí |
| | Expedia Rev+ | KS trên Expedia | Chỉ Expedia; compset 5–19 do Expedia gán | Hằng ngày | Không | Miễn phí |
| Việt Nam / SEA | **ezCloud ezRms** | KS VN | Ghi "competitor rates and market demand", không chi tiết | ? | ? | Không công khai |
| | Hotel Link, STAAH, Smile, Newway, Aharooms | KS VN/SEA | Channel manager / PMS, không thấy rate shopper | | | |
| API / dataset | Apify actors (Booking, Agoda, Expedia, Google Hotels) | Dev | Snapshot theo yêu cầu, một số có "Only X left" | Theo lịch của mình | Có ở vài actor (chưa chạy thử) | $0.5–5/1k kết quả |
| | Bright Data, SerpApi Google Hotels, MakCorps, DataForSEO, Xotelo | Dev | SerpApi: giá theo từng OTA, thuế/phí, huỷ miễn phí | Theo lịch | Không | Bright Data ~$1.3–1.5/1k; SerpApi ~$25/1k |
| Market analytics (căn hộ ngắn hạn) | AirDNA, PriceLabs Market Dashboard, Key Data, Transparent | Chủ căn hộ, nhà đầu tư | Quét calendar → suy occupancy | Hằng ngày | **Đây là phương pháp ta học được** | Thuê bao |
| Tín hiệu nhu cầu | PredictHQ, Lighthouse Market Insight | RMS, chuỗi | Sự kiện (rank 0–100), flight/hotel search | Hằng ngày | n/a | Bán qua sales |

**Nhận xét:**
- Không thấy rate shopper chuyên cho SMB Việt Nam (tìm bằng tiếng Việt chỉ ra các bài top PMS). Đây có thể là khoảng trống thị trường thật, cũng có thể chỉ là SEO yếu.
- Không đối thủ nào có alert Zalo/LINE/WhatsApp native. Email là chuẩn.

## 4. Flow chuẩn ngành so với ScrapeBooking

### F1. Onboarding và chọn compset
- **Đối thủ:**
  - Lighthouse: compset chính (đối thủ trực tiếp) cộng compset phụ (tín hiệu thị trường rộng). AI gợi ý ("Smart Compset" theo vị trí, review, giá, những KS khách thật sự so sánh).
  - Expedia gán sẵn 5–19 KS. Agoda cho tự chọn tối thiểu 5 nhưng **khoá 1 lần/quý**. Booking compset tối đa 10, chỉ thấy số tổng hợp.
  - IDeaS khuyến cáo chỉ đưa đối thủ thật vào, vì đối thủ lệch hạng làm sai forecast.
- **Ta:** operator tạo tenant, admin dán URL Booking, đổi compset tự do (flow A, B).
- **Khoảng trống:** chưa gợi ý compset, chưa có compset phụ, chưa self-serve. Việc đổi compset tự do là điểm bán so với Agoda, nên đưa vào marketing.

### F2. Map loại phòng / chuẩn hoá giá (so like-for-like)
- **Đối thủ:** Lighthouse tự map loại phòng theo compset và cho sửa tay. RateGain map theo keyword. IDeaS có "Rate Adjustment" để bù chênh bữa sáng/thuế.
- **Ta:**
  - Parser **đã tách** `refundable` / `breakfast` cho từng rate plan (`backend/app/collector/booking/parser.py:75-104`).
  - DB có `min_refundable_price` (`backend/app/db/models.py:172`).
  - Nhưng compset vẫn so `min_price` ở mức khách sạn (`backend/app/analytics/compset.py:18`).
- **Khoảng trống:** chưa có bộ lọc "chỉ giá hoàn huỷ / có bữa sáng" và chưa map loại phòng. Đây là việc rẻ vì dữ liệu đã có.

### F3. Xem số liệu buổi sáng
- **Đối thủ:**
  - Lighthouse: email sáng → calendar (giá kèm % chênh so với compset, hover xem nhu cầu/occupancy/sự kiện) → đổi qua graph/table → drill theo loại phòng/ngày/kênh → chỉnh giá trong ngày.
  - RoomPriceGenie: mở dashboard → giá đề xuất **kèm câu giải thích** → approve 1 click hoặc bật auto-upload.
- **Ta:** heatmap, dải compset (hết phòng, median/min, price index, PMS), chi tiết ngày, bản tin AI. **Tất cả đều trên web, khách phải tự vào xem.**
- **Khoảng trống:** chưa đẩy tin, chưa xếp hạng giá, chưa có chế độ màu % chênh, chưa có tooltip tổng hợp, chưa có lý do một dòng.

### F4. Cảnh báo (alert)
- **Đối thủ:**
  - Lighthouse: ngưỡng do user đặt (ví dụ compset rẻ hơn €10), cộng alert parity.
  - RateGain: email kèm push trên điện thoại, cộng "Narratives" (câu chữ tóm tắt khi đối thủ đổi giá).
  - RoomPriceGenie: báo khi nhu cầu tăng đột biến.
  - Expedia Rev+: báo chênh giá.
- **Ta:** 9 loại sự kiện đã phát hiện (`backend/app/analytics/rules.py:22`) nhưng chỉ xem được ở `/events`.
- **Khoảng trống:** chưa có rule do user đặt, chưa có kênh gửi, chưa có cơ chế gộp tin chống spam.

### F5. Báo cáo / xuất dữ liệu
- **Đối thủ:** Lighthouse có báo cáo email hằng ngày, báo cáo tuỳ chỉnh và xuất Excel. Price Seeker gửi báo cáo hằng ngày **kèm screenshot làm bằng chứng**. Fornova dùng screenshot và test booking làm bằng chứng parity.
- **Ta:** chưa xuất CSV/Excel, chưa có báo cáo tuần. Có "bằng chứng bấm được" dạng dữ liệu, chưa có ảnh.

### F6. Parity (giá OTA thấp hơn brand.com)
- **Đối thủ:** Fornova: điểm "distribution health" theo kênh → tìm nguyên nhân → xác định "worst offender" → screenshot/test booking → gửi đối tác xử lý.
- **Ta:** chưa có. Cần dữ liệu brand.com và OTA khác (xem đợt 3).

### F7. Ra quyết định giá
- **Đối thủ:**
  - Duetto: autopilot hoặc override, ràng buộc giá theo đối thủ (không thấp/cao hơn X so với compset), có audit trail.
  - RoomPriceGenie: approve hoặc auto-upload.
  - IDeaS: tick chọn đối thủ được dùng vào "Use in Rate Shopping".
- **Ta:** chưa có.

### F8. Benchmark
- **Đối thủ:** STR dùng MPI (occupancy) / ARI (ADR) / RGI (RevPAR) = của bạn / compset × 100, kèm thứ hạng 1..N, theo ngày/tuần/tháng/YTD. Một con số, dễ đọc.
- **Ta:** có `price_index` (tương đương ARI tính theo giá niêm yết) và occupancy PMS.
- **Khoảng trống:** chưa có thứ hạng, chưa có occupancy ước tính của compset để làm chỉ số tương đương MPI (xem đợt 2, mục 8).

## 5. Ma trận tính năng

Ký hiệu: ✅ có · ◐ một phần hoặc chỉ tổng hợp · – không thấy trong nguồn · ❌ không có

| Tính năng | Lighthouse | RateGain | RoomPriceGenie | Booking extranet | Agoda YCS | **ScrapeBooking** |
|---|---|---|---|---|---|---|
| Giá đối thủ đích danh | ✅ | ✅ | ✅ | ◐ tổng hợp | ◐ | ✅ |
| **Tồn phòng / hết phòng đối thủ theo loại phòng** | – | – | – | ❌ | ❌ | ✅ **duy nhất** |
| Nhiều OTA / brand.com | ✅ | ✅ | – | ❌ | ❌ | ❌ |
| LOS / số khách / thiết bị | ✅ | ✅ | – | ❌ | ❌ | ❌ (2 người lớn, 1 đêm) |
| Map loại phòng / chuẩn hoá | ✅ | ✅ | – | ❌ | ❌ | ◐ (đã parse, chưa dùng) |
| Alert đẩy | ✅ | ✅ email + push | ✅ surge | – | ◐ app | ❌ |
| Email hằng ngày / tuần | ✅ | ✅ | – | – | – | ❌ |
| Tóm tắt bằng lời / AI | ◐ | ✅ Narratives | ◐ lý do giá | ◐ Opportunity Centre | – | ✅ bản tin có bằng chứng |
| Lịch sự kiện / lễ | ✅ 365 ngày | ✅ | ✅ | – | – | ◐ (chỉ vào bản tin) |
| Pace / booking curve | ✅ | – | ✅ | ✅ (số thật, tổng hợp) | ◐ | ◐ (pickup, velocity) |
| Gợi ý giá | ✅ | ◐ | ✅ + auto push | ◐ | – | ❌ |
| Parity | ✅ | ✅ | – | ❌ | ❌ | ❌ |
| Tích hợp PMS | ✅ API | ✅ | ✅ | n/a | n/a | ◐ CSV/Excel |
| Mobile | ✅ | ◐ (bị chê) | – | ✅ app | ✅ app | ❌ |
| Giá công khai / tự đăng ký | ❌ | ❌ | ✅ trial | miễn phí | miễn phí | ❌ (operator onboard) |
| Tiếng Việt | – | – | – | ✅ | ✅ | ✅ |

## 6. Vị thế

**Lợi thế (giữ và khuếch đại):**
- Tồn phòng / hết phòng / có phòng lại đích danh từng đối thủ, từng loại phòng, 3 lần/ngày, có mức tin cậy (`exact` / `capped` / `hidden` / `sold_out`). AirDNA cũng suy occupancy nhưng **không công bố độ tin cậy**. Ta công bố được, và đó là điểm khác biệt.
- Bản tin AI chỉ nêu điều có bằng chứng (RateGain "Narratives" là thứ gần nhất).
- Compset đổi tự do, xem tên đối thủ thật (Agoda khoá theo quý, Booking chỉ có số tổng hợp).
- Occupancy PMS của chính khách sạn đặt cạnh compset (tool của OTA chỉ biết kênh của họ).

**Điểm yếu thật:**
- Chỉ có Booking, trong khi khách VN phụ thuộc Agoda.
- Không có dữ liệu nhu cầu thật (search, booking) như extranet có.
- Tồn phòng chỉ là suy luận: OTA allotment, close-out và đặt trực tiếp không nhìn thấy.
- Chưa có kênh đẩy, chưa tự đăng ký/billing, chưa có mobile.

**Mối đe doạ:**
- ezCloud đóng gói thêm tính năng theo dõi đối thủ vào PMS.
- OTA mở rộng tool miễn phí.
- Booking siết anti-bot hoặc ToS.
- Rủi ro vận hành (theo ghi chú ngày 01/10): proxy tĩnh đang trả 407. Các tính năng cần lịch sử liên tục (pacing, occupancy ước tính) phụ thuộc vào việc quét không bị đứt.

**Cơ hội:**
- Không thấy rate shopper chuyên cho SMB VN.
- Chưa ai có alert qua Zalo.
- Đối thủ enterprise ẩn giá, setup phức tạp, báo cáo chậm, mobile yếu (theo review HTR).

## 7. Backlog tính năng đề xuất

Effort: S ≤ 3 ngày · M ≈ 1–2 tuần · L > 2 tuần (ước lượng thô cho 1 dev).

### Đợt 1: Đẩy tin và biến dữ liệu sẵn có thành quyết định (dùng dữ liệu Booking hiện có)

| # | Tính năng | Vì sao | Tham chiếu | Effort | Chạm vào |
|---|---|---|---|---|---|
| 1 | **Kênh đẩy:** email bản tin buổi sáng (link sâu tới bằng chứng) cộng alert sự kiện compset. Kênh: email trước, Telegram bot (miễn phí, làm nhanh), Zalo OA/ZNS sau (~200–300đ/tin, cần OA và duyệt template, chưa kiểm chứng) | Khách không mở dashboard mỗi ngày; mọi đối thủ đều có; không ai có Zalo | Lighthouse daily email, RateGain push, RPG surge | S–M | Module `notify/` mới; gọi sau job `generate_insight` và sau analytics của mỗi run; bảng tuỳ chọn nhận tin theo user |
| 2 | **Rule alert do user đặt:** "≥N đối thủ hết phòng đêm D", "đối thủ X rẻ hơn mình >Y%", "đối thủ vào low_stock", "giá mình lệch median >Z%". Có giờ im lặng và gộp tin (digest) chống spam | Biến 9 loại sự kiện đã có thành hành động; "N đối thủ hết phòng" là tín hiệu nhu cầu chỉ ta có | Lighthouse threshold alerts | S–M | Bảng `alert_rule`; đánh giá trên `EventType` (`analytics/rules.py`) và `CompsetDay` |
| 3 | **Xếp hạng giá + chế độ màu "% chênh so với median" trên heatmap**, kèm tooltip (hạng 2/6, số đối thủ hết, occupancy PMS, ngày lễ) | Đọc nhanh hơn price index; tương đương STR rank và calendar của Lighthouse | STR rank, Lighthouse calendar | S | Thêm `rank`, `delta_pct` vào `CompsetDay`; `overview/board.tsx` |
| 4 | **So like-for-like:** công tắc "chỉ giá hoàn huỷ" / "có bữa sáng" khi tính compset | Hiện so `min_price` có thể đặt giá không hoàn huỷ cạnh giá có bữa sáng, dẫn tới kết luận sai | IDeaS Rate Adjustment, Lighthouse filter | S–M | `min_refundable_price` đã có; thêm cờ breakfast vào aggregate |
| 5 | **Câu giải thích một dòng** cạnh mỗi đêm ("4/6 đối thủ hết phòng, median +8% trong 7 ngày, mình rẻ hơn 12%") | RoomPriceGenie được thích vì luôn có lý do; dữ liệu có sẵn, không cần LLM | RPG price explanation | S | Hàm thuần sinh câu từ `CompsetDay` |
| 6 | **Lớp lịch lễ/sự kiện trên heatmap**, kèm cửa sổ trước/sau Tết và sự kiện địa phương do tenant nhập tay | `holidays/data.py` đã có nhưng chỉ vào input bản tin; giúp giải thích các đợt hết phòng | Lighthouse events 365 ngày, PredictHQ impact patterns | S | API overview trả holiday; UI vẽ marker |
| 7 | **Xuất CSV/Excel** (overview, events, chi tiết ngày) cộng **báo cáo tuần qua email** | Chủ khách sạn đọc báo cáo, ít khi mở dashboard | Lighthouse export, SiteMinder reports | S | Endpoint export; dùng chung template với mục 1 |
| 8 | **Độ mới dữ liệu ở mọi màn hình** ("cập nhật 2 giờ trước, lần quét kế tiếp 14:00") | Lighthouse/RateGain bán tốc độ; ta đã có cảnh báo lỡ lịch, chỉ cần hiện thống nhất | Lighthouse live shop | S | Dashboard |

### Đợt 2: Khuếch đại tín hiệu độc quyền (vẫn chỉ dùng Booking)

| # | Tính năng | Vì sao | Tham chiếu | Effort |
|---|---|---|---|---|
| 9 | **Pickup và occupancy ước tính của đối thủ, có độ tin cậy** (cách tính ngay dưới bảng) | Nâng moat từ "còn mấy phòng" lên "đối thủ bán được bao nhiêu"; dùng làm chỉ số tương đương MPI | AirDNA (không công bố confidence), PriceLabs | M |
| 10 | **Booking curve + pacing index:** occupancy ước tính theo số ngày trước khi đến (D-60..D0), so với các ngày tham chiếu cùng thứ/mùa/lễ để báo "đi trước/đi sau" | Học PriceLabs (đường xanh = đặt mới 7 ngày, đường đỏ = tích luỹ so với kỳ trước). Cần ≥4–8 tuần lịch sử liên tục | PriceLabs, Lighthouse Pace | M |
| 11 | **Ảnh bằng chứng cho sự kiện:** render HTML thô đã lưu trong MinIO thành ảnh vùng bảng phòng, khi user bấm; lưu cố định ảnh cho các sự kiện được dùng trong bản tin (vì HTML chỉ giữ 30 ngày) | Chặn câu hỏi "giá này có thật không" | Price Seeker, Fornova | S–M |
| 12 | **Gợi ý giá theo luật, không tự đẩy:** "≥60% compset hết phòng và giá mình < median → cân nhắc +X%", kèm lý do (mục 5), nút "Đã áp dụng / Bỏ qua" lưu audit để sau này đo hiệu quả | Cầu nối sang RMS mà không cần PMS API; one-click approve là UX được thích. Rủi ro về niềm tin nên gắn nhãn "gợi ý" | RPG, Duetto override + audit | M |
| 13 | **Gợi ý compset khi onboarding** (từ trang tìm kiếm Booking cùng khu vực/hạng sao/khoảng giá), cộng compset phụ "thị trường" | Giảm ma sát setup; mở đường cho tự đăng ký | Lighthouse Smart Compset, Expedia auto compset | M (cần parser trang search) |
| 14 | **PWA màn "Hôm nay" + web push** | Chủ khách sạn VN dùng điện thoại (ezCloud, Agoda YCS đều có app) | Agoda YCS app | M |

**Cách tính cho mục 9** (đề xuất của agent nghiên cứu, không phải công thức công khai của đối thủ):
- Với mỗi bộ (hotel, room_type, stay_date), trên chuỗi quan sát 3 lần/ngày:
  - Lấy các cặp quan sát liền kề mà cả hai đều `exact`. Nếu số phòng còn giảm thì đó là **pickup tối thiểu**; nếu tăng thì là release (huỷ, mở thêm allotment).
  - `rules.paired_exact_pickup` đã làm phần lõi này.
- Dữ liệu bị che (censored):
  - `capped`: chỉ biết "ít nhất N phòng", nên hiện **dải** thay vì một con số.
  - `hidden`: không biết.
  - `sold_out` = 100%, nhưng gắn cờ "có thể là close-out" (khách sạn đóng bán chứ không hẳn bán hết).
- Tổng số phòng ước tính (`inventory_est`): số phòng còn lớn nhất từng thấy theo loại phòng, hoặc khách khai báo. Occupancy ước tính = 1 − rooms_left / inventory_est. Coverage = % loại phòng có quan sát `exact`. Mức tin cậy cao/vừa/thấp lấy theo coverage.
- **Hiệu chỉnh bằng chính khách hàng:** chạy cùng công thức cho khách sạn của khách, so với occupancy PMS đã nhập, rồi hiện sai số (MAPE). Đây là điều AirDNA không làm được.
- Gắn nhãn "occupancy nhìn thấy trên OTA", vì không thấy được đặt trực tiếp, walk-in và khách đoàn.

### Đợt 3: Nguồn dữ liệu mới (chỉ làm khi có khách trả tiền và đòi)

| # | Tính năng | Ghi chú | Effort |
|---|---|---|---|
| 15 | **Google Hotels qua SerpApi:** lớp chỉ có giá, đa OTA (Booking, Agoda, Expedia, giá trực tiếp), 1 lần/ngày, lấy mẫu đêm (T+1..7 mỗi ngày, xa hơn thì cách 3 ngày) | Một call cho giá Agoda và parity cơ bản, không phải tự scrape. Ước tính thô: 20 KS × 30 đêm ≈ 18k search/tháng ≈ $150+/tháng trước khi lấy mẫu. Interface `OtaSource`, lưu availability_confidence=`hidden` | M |
| 16 | **Pilot Agoda qua Apify actor** (~$5/1k), 1 lần/ngày, 14 đêm, 2–3 tenant. Chỉ tự build bằng Playwright khi actor không trả "Only X left" hoặc chi phí/tenant vượt ngưỡng | Agoda rất quan trọng ở VN; chạy thử 1 run để kiểm field | M → L |
| 17 | **Parity brand.com với OTA**, điểm sức khoẻ, "worst offender", ảnh bằng chứng | Tính năng chuẩn của shopper nhưng cần mục 15/16 trước | L |
| 18 | **Biến thể LOS / số khách** (2 đêm, 1 người, gia đình) | Số probe nhân lên theo số biến thể | M–L |
| 19 | **Adapter API ezCloud** thay cho CSV | Phụ thuộc đối tác; đồng thời là kênh hợp tác (hoặc phòng thủ) với ezCloud | L |
| 20 | **Tự đăng ký + giá công khai + dùng thử** | Đối thủ enterprise ẩn giá và bắt demo, đây là điểm yếu bị chê. Nằm ngoài phạm vi kỹ thuật nghiên cứu này | L |

**Thứ tự đề xuất:** 1 → 2 → 3 → 5 → 4 → 6 → 7 → 8, rồi 9 → 10 → 11 → 12. Đợt 3 chỉ làm theo yêu cầu khách.

## 8. Không nên làm (YAGNI)

- Mua dữ liệu nhu cầu từ search/flight (Lighthouse Market Insight, OAG): đắt, độ phủ VN chưa rõ. Lịch lễ cộng tín hiệu nội bộ (tỷ lệ hết phòng, pickup) đã cho phần lớn giá trị.
- PredictHQ: chỉ cân nhắc khi khách cần sự kiện lớn (concert, festival). Giá bán qua sales, độ phủ VN chưa kiểm chứng.
- Dữ liệu STR thật, GDS, theo POS/quốc gia, test booking.
- Tự đẩy giá vào channel manager.
- Forecast bằng ML: chờ có pacing và ≥1 mùa dữ liệu, sau đó dùng cách "ngày tham chiếu" của PriceLabs trước.
- Expedia: thị phần VN nhỏ so với Booking/Agoda.

## 9. Câu hỏi còn mở

1. ezCloud ezRms lấy "competitor rates" từ đâu, có tồn phòng không, giá bao nhiêu? Nên đăng ký demo để biết; đây là rủi ro chiến lược số 1.
2. Booking "RateIntelligence" (thuộc BookingSuite, ra mắt khoảng 2016) còn hoạt động không? Agent không kiểm chứng được. Tôi nhớ là BookingSuite đã đóng nhưng **chưa kiểm chứng**. Hiện extranet có "so giá với khách sạn tương tự" dạng tổng hợp.
3. Google Hotel Center / Hotel Insights miễn phí cho KS VN đến đâu? Chưa kiểm chứng.
4. Apify actor nào thật sự trả "Only X left" theo loại phòng cho Booking/Agoda? Cần chạy thử 1 run.
5. Quy trình và chi phí Zalo OA/ZNS thực tế (xác minh OA, duyệt template).
6. ToS Agoda/Expedia khi scrape; giá SerpApi 2026 (mới lấy từ snippet).
7. Lighthouse có bán dữ liệu "availability" đối thủ không, alert gửi qua kênh nào?
8. Thái Lan/Indonesia chưa nghiên cứu, cần nếu muốn mở rộng SEA.
9. Pacing (mục 10) cần ≥4–8 tuần lịch sử liên tục của tenant thật. Cần chắc proxy ổn định trước khi bắt đầu đếm.

## 10. Nguồn chính

- Lighthouse Rate Insight: https://www.mylighthouse.com/resources/blog/how-to-get-most-out-of-lighthouse-rate-insight · Smart Compset: https://www.mylighthouse.com/resources/blog/lighthouse-launches-smart-compset-enhancing-competitive-intelligence-for-hoteliers · Market Insight: https://www.mylighthouse.com/platform/market-insight · HTR: https://hoteltechreport.com/revenue-management/market-intelligence-tools/lighthouse-rate-insight
- RateGain HTR: https://hoteltechreport.com/revenue-management/market-intelligence-tools/rateshopper-by-rategain
- Fornova DI: https://hoteltechreport.com/revenue-management/hotel-rate-parity/fornova-distribution-intelligence
- Duetto GameChanger: https://www.duettocloud.com/products/gamechanger · IDeaS G3 (08/2025): https://ideas.com/improvements-innovations-whats-new-in-g3-rms-august-2025/
- STR/STAR report: https://www.mylighthouse.com/resources/blog/star-report-hotels
- RoomPriceGenie: https://hoteltechreport.com/revenue-management/revenue-management-systems/roompricegenie · Bảng giá shopper: https://hoteltechreport.com/revenue-management/market-intelligence-tools
- Booking Partner Hub: https://partner.booking.com/en-gb/learn-more/new-partner/improving-your-performance · Analytics & Opportunity Centre: https://news.booking.com/en/bookingcoms-analytics-and-opportunity-centre/
- Agoda compset: https://partnerhub.agoda.com/how-do-i-manage-my-competitor-set/ · YCS dashboard: https://partnerhub.agoda.com/what-is-the-ycs-dashboard/
- ezCloud ezRms: https://ezcloud.vn/en/product/ezrms
- Apify Booking: https://apify.com/voyager/booking-scraper · Bright Data: https://brightdata.com/products/web-scraper/booking · SerpApi Google Hotels: https://serpapi.com/google-hotels-api
- AirDNA occupancy: https://help.airdna.co/en/articles/8062178-how-does-airdna-calculate-occupancy-rate · PriceLabs: https://hello.pricelabs.co/overview-of-pricelabs-dynamic-pricing-algorithm-part-1/
- PredictHQ impact patterns: https://docs.predicthq.com/getting-started/predicthq-data/impact-patterns
