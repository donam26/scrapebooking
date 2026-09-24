# Nghiên cứu: Theo dõi đối thủ khách sạn qua Booking.com

Ngày: 2026-09-24

## 1. AI provider: GPT-6 Luna (OpenAI)

- Ra mắt 22/09/2026 cùng GPT-6 Sol, cùng dòng với GPT-6 Astra (flagship).
- Model ID: `gpt-6-luna` (một snapshot duy nhất).
- Context 1.050.000 tokens, output tối đa 128.000 tokens.
- Hỗ trợ: Structured Outputs (JSON schema), function calling (khuyến nghị Responses API),
  Batch API, prompt caching, reasoning effort: none/low/medium/high/xhigh/max.
- Giá: $0.10 / 1M input, $0.50 / 1M output, cached input $0.01.
- Knowledge cutoff 18/05/2026.
- Kết luận: rất phù hợp cho tầng "AI insight" (input là bảng biến động đã tính sẵn, output JSON
  insight có schema). Chi phí gần như không đáng kể so với chi phí scraping.

Nguồn:
- https://developers.openai.com/api/docs/models/gpt-6-luna
- https://techcrunch.com/2026/09/22/openai-launches-gpt-6-sol-and-luna/

## 2. Dữ liệu "số phòng còn lại" trên Booking.com thực tế hoạt động thế nào

### 2.1 Đơn vị dữ liệu
- "Rooms left" là theo **từng loại phòng (room type)** cho **một kỳ lưu trú cụ thể**
  (check-in / check-out / số khách). Không có một con số "phòng còn lại của khách sạn" chung.
- Muốn có snapshot theo từng ngày tương lai, phải probe **từng ngày** (thường stay 1 đêm):
  URL `https://www.booking.com/hotel/<cc>/<slug>.html?checkin=YYYY-MM-DD&checkout=YYYY-MM-DD&group_adults=2&no_rooms=1`
- Số request/ngày = số khách sạn × số ngày horizon × số lần scan/ngày.

### 2.2 Dữ liệu bị "kiểm duyệt" (censored)
- Booking chỉ hiện con số chính xác khi tồn kho thấp: badge "Only X rooms left on our site".
- Khi nhiều phòng, không có badge; dropdown chọn số phòng bị cap (giới hạn trang) →
  chỉ biết "≥ N", không biết số thật.
- Các scraper thương mại (Apify aurith_labs) mô hình hoá bằng `stock_confidence`:
  `exact` | `capped` | `hidden` | `conflicting`, và `availability_status`:
  `available` (>5) | `low_availability` (2–5) | `low_availability_urgent` (1) | `sold_out`.
- Hệ quả thiết kế: schema snapshot PHẢI lưu kèm confidence; phân tích xu hướng chủ yếu quan sát
  được ở pha "N phòng cuối" và trạng thái sold-out, cộng thêm tín hiệu giá.

### 2.3 Hai đường lấy dữ liệu
| Đường | Cho gì | Chi phí request | Ghi chú |
|---|---|---|---|
| GraphQL `AvailabilityCalendar` (`/dml/graphql`) | per-date: available/sold-out, minLengthOfStay, avgPrice | ~6 request / khách sạn / 365 ngày | KHÔNG có rooms_left |
| Trang khách sạn theo ngày (HTML/embedded JSON) | per room type: rooms_left (+confidence), giá, huỷ miễn phí, occupancy | 1 request / khách sạn / ngày probe | Cần browser thật hoặc anti-bot bypass |

Chiến lược hợp lý: dùng calendar (rẻ) để quét horizon dài + phát hiện sold-out, dùng trang
khách sạn (đắt) cho horizon ngắn/ngày quan trọng để lấy rooms_left.

### 2.4 Anti-bot
- AWS WAF Bot Control + fingerprinting kiểu Akamai; IP datacenter bị chặn ở mọi endpoint,
  kể cả GraphQL. CAPTCHA sau vài request.
- Cần: residential proxy + trình duyệt thật (Playwright) hoặc HTTP/2 + header thật + session
  đã giải challenge (1 session/run, tái dùng).
- Giá theo IP (geo-pricing) thay đổi thuế hiển thị → cố định proxy country.

### 2.5 Lựa chọn triển khai scraper
| Lựa chọn | Ưu | Nhược |
|---|---|---|
| A. Managed actor (Apify `aurith_labs/booking-availability`, `bovi/booking-rate-monitor`, Bright Data, Scrapfly) | Không lo anti-bot, có sẵn rooms_left + confidence, chạy ngay | ~$4 / 1.000 kết quả (offers mode); phụ thuộc bên thứ 3; single-thread/run |
| B. Tự viết Playwright + residential proxy | Chủ động, rẻ hơn ở scale lớn | Tốn công bảo trì khi Booking đổi DOM/WAF; cần đội vận hành |
| C. Hybrid: interface `Collector` chuẩn hoá, provider đầu = Apify, provider 2 = self-hosted | Đi nhanh, giữ đường lui | Cần thiết kế interface kỹ từ đầu |

### 2.6 Ước tính chi phí ví dụ (10 khách sạn, 3 scan/ngày)
| Horizon | Probe/ngày | Probe/tháng | Apify offers (~4 offer/probe, $4/1k) | Tự scrape (proxy residential ~1.5MB/trang, ~$5/GB) |
|---|---|---|---|---|
| 30 ngày | 900 | 27.000 | ~$430/tháng | ~$200/tháng + công bảo trì |
| 90 ngày | 2.700 | 81.000 | ~$1.300/tháng | ~$600/tháng + công bảo trì |
Con số là ước lượng thô để so sánh bậc độ lớn, chưa tính retry/lỗi.

## 3. Pháp lý
- Scrape trang công khai nhìn chung không bị cấm theo luật, nhưng vi phạm ToS của Booking.com;
  dùng thương mại và bán cho khách hàng nên có tư vấn pháp lý.
- Không đăng nhập, không lấy dữ liệu cá nhân, chỉ lấy đúng trường cần, tôn trọng tốc độ.
- Các công cụ rate-shopping thương mại (Lighthouse/OTA Insight, RateGain) làm việc này ở quy mô
  lớn; đây là ngành có sẵn.

## 4. Phân rã hệ thống (đề xuất)
1. Collector + Scheduler: lấy snapshot theo lịch, chuẩn hoá, lưu raw.
2. Snapshot Store + Diff Engine: bảng snapshot theo (tenant, hotel, room_type, stay_date,
   scanned_at); tính delta, tốc độ giảm, sold-out event, price change.
3. AI Insight (GPT-6 Luna): nhận bảng biến động đã tổng hợp, trả JSON insight theo schema.
4. Dashboard: web app hiển thị heatmap ngày × khách sạn, timeline, insight.
5. Multi-tenant / khách hàng / billing: tenant_id từ ngày đầu, self-serve sau.

Nguồn bổ sung:
- https://scrapfly.io/blog/posts/how-to-scrape-bookingcom
- https://apify.com/aurith_labs/booking-availability
- https://apify.com/bovi/booking-rate-monitor
- https://dev.to/agenthustler/how-to-scrape-bookingcom-in-2026-hotel-data-prices-and-reviews-3ge5
- https://outscraper.com/hotel-price-scraping-legal/
- https://www.which.co.uk/news/article/booking-com-still-misleading-holidaymakers-with-1-room-left-claims-aSNln2j8gkGl
