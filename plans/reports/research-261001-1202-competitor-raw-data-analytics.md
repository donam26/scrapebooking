# Competitive: Data APIs / Market analytics / Demand signals (2026-10-01)

Ghi chú độ tin cậy: ~15 calls, chủ yếu search snippet + 4 fetch. Mục [chưa verify] = chưa đọc trang gốc.

## A. Hotel data scraping APIs / datasets

### Apify actors (Booking.com / Agoda / Expedia)
- Hệ sinh thái actor rất đông, giá pay-per-result: $0.5–$2/1k hotels (listing), detailed/room mode ~$5/1k. voyager/booking-scraper: $2.00/1k "place results", có add-on "room details" trả phí. https://apify.com/voyager/booking-scraper
- Search-result list các actor khác: một số trả per-room rate, `rooms left`/`sold-out rooms`, `units left` (detailed mode), room `mealPlan`, `occupancy`, `freeCancellationUntil`, `urgencyMessage` ("Only X left"). Ví dụ: https://apify.com/fascinating_lentil/booking-com-hotel-scraper , https://apify.com/automation-lab/booking-scraper , https://apify.com/solidcode/booking-scraper [chi tiết field từ snippet, chưa đọc từng actor]
- Delivery: dataset JSON/CSV/Excel/XML, REST API, JS/Python client, MCP; schedule + webhook là tính năng platform Apify (chưa fetch trang doc, kiến thức chung).
- Agoda: ~$5/1k results (https://apify.com/knagymate/fast-agoda-scraper , https://apify.com/datawebot/agoda-hotel-scraper). Expedia: từ $0.5/1k (https://apify.com/mrdoe/expedia-hotel-scraper).
- Google Hotels rate-shopper actors: so sánh 18–31 OTA, "rate parity" (https://apify.com/jhon_snow/google-hotels-rate-shopper/api).
- Anti-bot: do actor/Apify proxy lo; chất lượng không đồng đều, actor nhỏ hay chết khi Booking đổi DOM.
- Gap vs ta: họ là snapshot theo yêu cầu, KHÔNG có time-series + event detection + confidence rooms-left + parser versioning/reparse. Bạn tự schedule & diff.

### Bright Data
- Web Scraper API Booking: submit URL -> JSON; fields: hotel id, title, location, check-in/out, rooms, guests, price, star, rating, review count, amenities, images. Chỉ trả tiền record thành công. Pay-as-you-go ~$1.50/1k, Scale ~$1.30/1k, free 5k/tháng. https://brightdata.com/products/web-scraper/booking
- Dataset Booking sẵn (5.7M+ records, snapshot, không phải availability time-series): https://brightdata.com/products/datasets/booking
- Proxy/unlocker xử lý anti-bot. Đây là "buy" hợp lý nếu muốn bỏ self-host scraper nhưng room-level rooms-left không rõ có (cần test).

### SerpApi Google Hotels API (aggregator nhiều OTA)
- Params: check_in_date, check_out_date, adults (default 2), currency, gl. Response: `prices[]` mỗi OTA (source, rate_per_night, total_rate, before_taxes_fees, free cancellation + deadline), rating, reviews, amenities, GPS. Cache 1h miễn phí, async mode + Searches Archive. https://serpapi.com/google-hotels-api
- Giá: $25/1k searches (gói nhỏ), $275/30k; 250 free. https://serpapi.com/pricing [từ snippet search]
- Hạn chế: không có rooms-left; giá hiển thị là "headline" của property/OTA, room-level hạn chế (Property Details endpoint có thêm: https://serpapi.com/google-hotels-property-details). Rate ladder ít OTA hơn một số actor Apify.
- Alternatives: DataForSEO Google Hotels API (https://dataforseo.com/pricing/business-data/google-hotels-api), MakCorps (claim 200+ OTA, city/hotel-ID, có free tier; https://docs.makcorps.com/), Xotelo (free, dựa TripAdvisor, không SLA).
- Amadeus Self-Service Hotel Search: 150k+ hotel, có VN nhưng là inventory GDS bookable, coverage khách sạn VN độc lập mỏng; không phải compset-monitoring. https://developers.amadeus.com/self-service/category/hotels
- Enterprise (RateGain/OTA Insight/Lighthouse): bán qua sales, không giá công khai; dữ liệu feed thường qua API (https://api.mylighthouse.com/).

### Build-vs-buy: kết luận
- Giữ Booking.com self-built (đã có moat: rooms-left + confidence + raw HTML + reparse). Không ai bán time-series rooms-left theo room type rẻ.
- Agoda (thị trường VN rất quan trọng): mua trước. Apify Agoda actor $5/1k. Tính toán: 1 hotel x 30 ngày x 3 lần/ngày = 90 probes/ngày; 20 hotel (client+compset) ≈ 1.8k/ngày ≈ 54k/tháng ≈ $270/tháng/tenant nếu mỗi probe = 1 result. Đắt -> chỉ chạy 1x/ngày, 14 ngày: 20x14=280/ngày ≈ 8.4k/tháng ≈ $42. Cần đo thực tế.
- Expedia: ít giá trị cho khách sạn VN (inbound châu Á dùng Agoda/Booking nhiều hơn) -> làm sau.
- Google Hotels qua SerpApi: rẻ để có "rate parity + giá nhiều OTA" cho compset, 1 call/hotel/ngày/check-in. Dùng làm lớp price-only (không occupancy), chạy 1x/ngày, horizon ngắn 14–30 ngày. 20 hotels x 30 ngày = 600 searches/ngày = ~18k/tháng ≈ $150-ish; giảm bằng cách lấy mẫu ngày (T+1..7 mỗi ngày, xa hơn mỗi 3 ngày) + cache 1h.
- Rủi ro mua: ToS/phụ thuộc actor nhỏ; thiết kế adapter `OtaSource` + schema chuẩn hoá (room_type, price, availability_confidence=`hidden` cho OTA không lộ rooms-left) để swap nguồn.

## B. Market analytics suy occupancy từ calendar

### AirDNA
- Quét 100% listing Airbnb/Vrbo/Booking.com hằng ngày (giá, calendar, review). https://www.airdna.co/how-it-works
- Occupancy = reserved days / active listing nights (12 tháng). Active listing night = đêm không blocked VÀ (reserved hoặc available) VÀ listing có booking trong 28 ngày gần nhất. https://help.airdna.co/en/articles/8062178-how-does-airdna-calculate-occupancy-rate
- Phân biệt booked vs host-blocked bằng ML với ~16 signals (stay length, lead time, review timestamp, pricing pattern, seasonality). Dự báo demand đến 6 tháng dựa trên forward bookings.
- Không công bố confidence metric (chính họ không nêu) -> cơ hội cho ta hiển thị confidence rõ.
- Lưu ý: ta KHÁC AirDNA: ta không có vấn đề "blocked" nhiều (khách sạn hiếm khi block) nhưng có censoring (capped/hidden) + OTA allotment.

### PriceLabs Market Dashboard / Neighborhood Data
- Metrics: occupancy, ADR, RevPAR, booking curve, lead time, pacing, LOS, booking window, future occupancy. https://hello.pricelabs.co/market-dashboards/
- Forecast: tìm "reference dates" quá khứ (cùng mùa, thứ, holiday/event, similarity theo hình dạng booking curve); pacing = occupancy hiện tại của ngày tương lai so với reference ở cùng booking window. https://hello.pricelabs.co/overview-of-pricelabs-dynamic-pricing-algorithm-part-1/
- UI nổi bật: neighborhood occupancy chart với "green line" = booking mới trong 7 ngày/mỗi check-in date (nhiệt độ ngày), "red line" = cumulative occupancy so với năm trước (ahead/behind). https://www.rakidzich.com/articles/pricelabs-booking-accumulation-green-red-line-reading-2026 (blog bên thứ ba)

### Transparent (OTA Insight/Lighthouse), Key Data, Beyond Insights
- Transparent: 35M listings, multi-OTA (Airbnb, Vrbo, Booking.com) market supply/demand. Key Data/Beyond: STR market data+benchmark [chưa đọc sâu; https://www.keydata.co/blog/are-you-using-the-right-hospitality-market-data , https://beyondpricing.com/products/insights].
- Caveat chung ngành: occupancy scrape bỏ sót direct/walk-in/corporate, bị lệch khi khách sạn block loại phòng. Nên gắn nhãn "OTA-visible occupancy".

### Suy ra phương pháp cho rooms-left deltas (đề xuất, không phải công thức công khai)
- Với mỗi (hotel, room_type, stay_date): chuỗi observation theo thời gian t (3x/ngày). Delta giảm rooms_left = pickup tối thiểu (lower bound), tăng = cancel/restock/allotment release.
- Censoring: `capped` (hiển thị tối đa, ví dụ "≥10"), `hidden` (không hiện số) và `sold_out` => interval-censored. Ước lượng: exact -> điểm; capped -> [cap, ∞); hidden -> unknown; sold_out -> 0 (nhưng có thể do close-out, không phải bán hết).
- Net pickup/ngày = sum(max(0, -delta)) trên các cặp exact-exact liền kề; tách release = sum(max(0, +delta)). Net = pickup - release.
- Occupancy proxy của hotel/ngày: nếu biết total_rooms (khai báo hoặc max rooms_left từng quan sát lịch sử theo room type) thì occ_est = 1 - rooms_left/inventory_est; sold_out -> 1.0 (flag "closed-out possible"). Coverage = % room type có exact.
- Tổng hợp compset: median occupancy proxy + % sold out (đã có) + pickup 7 ngày, kèm "coverage" và bucket confidence (high/med/low) hiển thị ngay cạnh số.
- Calibrate: dùng PMS CSV (đã có import) để hồi quy occ_est vs occ thật của hotel khách -> hệ số hiệu chỉnh/độ lệch, hiển thị MAPE.
- Pacing: lưu "booking curve" = occ_est theo days-before-arrival (D-60..D0) cho mỗi dow; so sánh ngày tương lai với median curve cùng dow/mùa (kiểu PriceLabs reference dates) -> pacing index. Cần ≥ vài tuần lịch sử; tenant 9 đã có runs.

## C. Demand signals

### PredictHQ
- Events API: mỗi event có `phq_attendance`, `rank` 0–100, `rank_level` 1–5, category (concerts, sports, public holidays, school holidays, ...). https://www.predicthq.com/apis/event-api , https://www.predicthq.com/tools/rankings/phq-rank
- Features API: daily aggregates theo location (sum/max, số event theo rank band) để đưa vào forecasting model; Predicted Impact Patterns = ảnh hưởng trước/sau ngày event, khác nhau theo category/industry. https://docs.predicthq.com/getting-started/predicthq-data/impact-patterns , https://docs.predicthq.com/getting-started/guides/features-api-guides/improving-demand-forecasting-models-with-event-features
- Giá: sales-led, không công khai [có free/trial theo web, chưa verify]. Coverage VN (Tết, lễ, concert) chưa verify.
- Trang "Aggregate Event Impact" (docs) 404 khi fetch; không có chi tiết AEI.

### Lighthouse Market Insight
- Kết hợp rate shopping + flight search + hotel search + hotel occupancy + STR availability -> demand indicators; 365-day market demand calendar, demand evolution heatmap theo khu vực; claim correlation search-occupancy; +2.3% RevPAR, +4.7% occupancy (claim vendor). https://www.mylighthouse.com/platform/market-insight , https://www.mylighthouse.com/resources/insights/predictive-market-intelligence-hotel-demand-forecast
- Giá: không công khai.

### Nguồn miễn phí/rẻ khả dụng
- Google Trends (pytrends không chính thức; có Trends API alpha chính thức [chưa verify]) cho query "khách sạn <điểm đến>"; flight data khó (OAG/Cirium trả phí).
- Public holidays: Calendarific / timeanddate. Tết 2027: mùng 1 = 6/2/2027 (Thứ Bảy), nghỉ luật 5–9/2; lịch nghỉ kéo dài chính thức công bố cuối 2026. https://www.timeanddate.com/holidays/vietnam/2027 , https://calendarific.com/holidays/2027/vn

## Ideas to port into ScrapeBooking (xếp theo value/effort)

1. **Pickup & occupancy-proxy từ rooms-left deltas, có confidence (M, value rất cao)**
   - What: bảng `pickup_daily(hotel, room_type, stay_date, obs_date, pickup_min, release, coverage, confidence)` + occ_proxy theo công thức ở mục B. Hiển thị "~72% (±, coverage 60%)", khi capped/hidden thì dải thay vì điểm.
   - Why: bạn đã có data; đối thủ (AirDNA) không công bố confidence -> khác biệt. Đã có pickup/velocity, đây là nâng cấp lên occupancy.
   - Ref: AirDNA calc (link trên), PriceLabs pacing. Calibrate bằng PMS CSV.
   - Cẩn trọng: sold_out != chắc chắn full (close-out/allotment) -> flag.
2. **Booking curve + pacing index vs reference dates (M)**
   - What: occ_proxy theo D-n, so sánh với median cùng dow/mùa/holiday; hiển thị "ahead/behind" + heat strip per date (green/red line kiểu PriceLabs).
   - Why: tái dùng chính data bước 1; trực quan, khách khách sạn hiểu ngay. Cần lịch sử >=4–8 tuần.
   - Ref: https://hello.pricelabs.co/overview-of-pricelabs-dynamic-pricing-algorithm-part-1/
3. **Demand index nhẹ cho VN: calendar lễ + event thủ công + internal signal (S–M)**
   - What: bảng `demand_calendar(date, region, type, weight)` seed từ lịch nghỉ lễ VN (Tết, 30/4–1/5, 2/9, Giỗ Tổ, Noel/NYE) + bridge days + school holiday + weekend; thêm internal signals: compset % sold out, pickup velocity, price index. Index = weighted z-score; hiển thị trên date heatmap và đưa vào AI briefing ("ngày X là Tết, compset 60% sold out").
   - Why: PredictHQ/Lighthouse đắt và coverage VN chưa rõ; calendar + signal nội bộ là 80% giá trị. Tết dùng pre/post window (impact pattern: trước/sau event) như PredictHQ.
   - Ref: https://docs.predicthq.com/getting-started/predicthq-data/impact-patterns ; holidays: Calendarific/timeanddate.
   - Sau: thêm Google Trends interest cho điểm đến (S) và cân nhắc PredictHQ cho event lớn (concert/festival) nếu có khách trả tiền (L).
4. **Alerts (email/Zalo/Telegram) trên events đã detect (S)**
   - Why: bạn đã có event detection nhưng "Missing alerts" -> cơ hội thắng nhanh; chuẩn ngành (rate shopper đều có). Webhook/export CSV/API cho khách cũng S–M.
5. **Google Hotels qua SerpApi làm lớp price-only đa OTA (M)**
   - What: adapter `OtaSource`; 1x/ngày, T+1..30 lấy mẫu; lưu `prices[]` per OTA, flag availability_confidence=hidden; dùng cho rate parity + price index chéo OTA.
   - Why: một call phủ Booking/Agoda/Expedia/direct, ~ $25/1k. Chưa cần self-scrape Agoda.
6. **Agoda: thử Apify actor trước, tự build sau khi chứng minh ROI (M -> L)**
   - What: pilot 2–3 tenant, 1x/ngày, 14 ngày. Chỉ tự build (Playwright) khi cost/tenant > ngưỡng hoặc cần rooms-left. Agoda hay có "Only X rooms left" -> nếu actor không có field này thì tự build mới đáng.
   - Ref: https://apify.com/knagymate/fast-agoda-scraper (kiểm field thực tế bằng 1 run thử).
7. **Public data confidence UX: badge "OTA-visible" + coverage % (S)**
   - Why: ngành thừa nhận scrape thiếu direct/walk-in; minh bạch tăng độ tin cậy. Ref: https://www.keydata.co/blog/are-you-using-the-right-hospitality-market-data (và snippet Hospitality Net).
8. **Forecast demand/occupancy (L, hoãn)**
   - Làm sau khi có curve+pacing và >=1 mùa lịch sử (YAGNI). Dùng reference-date approach thay vì ML nặng.

## Unresolved questions
- Actor Apify nào thực sự trả `rooms left` per room type ổn định cho Booking/Agoda (cần chạy thử, tôi chỉ đọc mô tả).
- Bright Data Booking API có room-level + availability không (chỉ thấy field tổng).
- Giá PredictHQ/Lighthouse & coverage sự kiện VN: không công khai.
- Agoda/Expedia ToS & rủi ro pháp lý khi scrape; chưa nghiên cứu.
- Trends API chính thức của Google, trạng thái hiện tại chưa verify.
- Giá SerpApi chính xác theo gói 2026 (lấy từ snippet).
