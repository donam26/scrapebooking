# Competitor Analysis: ENTERPRISE rate intelligence / parity / RMS / benchmarking

Date: 2026-10-01. Nguồn: ~12 search/fetch calls. LƯU Ý: 2 trang help-center (IDeaS help, HotelBusiness/Duetto) trả 403 -> phần IDeaS/Duetto chỉ dựa snippet search, độ tin cậy trung bình. Nhiều chi tiết flow (onboarding step-by-step) KHÔNG public (sau login/demo) -> đánh dấu [suy luận] khi không có nguồn.

## 0. Tóm tắt nhanh
- Cả 5 đều bán cho chain/mid-large hotel, giá "request demo", không public.
- Điểm khác biệt chính so với ScrapeBooking: (a) multi-channel (OTA + brand.com + metasearch), (b) shop theo LOS/occupancy/device/POS, (c) room-type mapping + normalization (breakfast/refundable), (d) parity + screenshot proof, (e) alert theo threshold + daily email, (f) events calendar + demand, (g) forecasting/recommendation.
- ScrapeBooking có điểm mà họ ít nhấn: **rooms-left / sold-out inventory signal** (supply-side) + AI briefing có evidence. Rate shopper truyền thống chủ yếu chỉ có giá + (một số) OTB occupancy từ PMS. Đây là moat nhỏ, giữ.

## 1. Lighthouse (ex OTA Insight)
Nguồn: https://hoteltechreport.com/revenue-management/market-intelligence-tools/lighthouse-rate-insight ; https://www.mylighthouse.com/resources/blog/how-to-get-most-out-of-lighthouse-rate-insight ; https://www.mylighthouse.com/platform/benchmark-insight ; https://hoteltechreport.com/revenue-management/channel-managers/lighthouse-cm

**Positioning**: nền tảng "commercial platform" all-in-one cho revenue/sales/marketing/distribution; 85k properties, 185 nước (https://hoteltechnologynews.com/2025/09/lighthouse-launches-smart-distribution-to-automate-pricing-and-channel-management-for-independent-hotels/). Từ indie tới chain.

**Data/shop**: nhiều OTA, brand.com, short-term rental, mobile + member rate tiers, desktop/mobile; filter room type + LOS; refresh "gần real-time", "one-click live shop trong vài giây" (review HTR); lịch sử rate 365 ngày; parity nhìn trước tới 12 tháng.

**Products**
- Rate Insight: rate shop, calendar view (highlight rate + % chênh vs compset), rate evolution graph, Pace view (pickup vs lead time vs kỳ trước), Rate Strategy view (mobile/member/discount), table view, OTB occupancy (từ PMS), events/holiday calendar (tới 365 ngày), hover ngày để xem occupancy + market demand, rankings & reviews OTA/TripAdvisor.
- Parity Insight: OTA/metasearch undercut brand.com, desktop vs mobile, screenshot + landing page verification, tự discover & giải quyết parity ở cấp portfolio.
- Market Insight: demand (booking intent/search) theo location/segment.
- Benchmark Insight: market share vs compset; **Smart Compset** (AI, forward-looking ADR/RevPAR; compset động theo "properties traveler thực sự so sánh" dựa location, review, giá real-time) https://www.mylighthouse.com/resources/blog/lighthouse-launches-smart-compset-enhancing-competitive-intelligence-for-hoteliers
- Pricing Manager + Business Intelligence (Revenue Insight), Performance. 2025: **Smart Distribution** (AI auto chỉnh giá/phân phối cho indie) + Lighthouse Channel Manager.
- Có public API https://api.mylighthouse.com/ ; tích hợp PMS (Cloudbeds, Stayntouch...).

**Flows**
- Compset setup: primary compset (đối thủ trực tiếp) + secondary compset (tín hiệu thị trường); AI gợi ý; cập nhật tức thì.
- Room mapping: auto-map theo compset, cho sửa tay; mapping để so like-for-like.
- Daily review: email report buổi sáng -> mở tab Rate/Parity -> drill room type/ngày/kênh -> quyết định giá same-day.
- Alerts: threshold-based (vd compset undercut > €10) [snippet search, chưa xác minh kênh]; parity alert tự động.
- Reports: daily email market overview, custom report lọc date/room/channel, export Excel.
- Integrations: PMS/RMS/channel manager, API.

**UX patterns**: calendar heat/% delta, 3 view (calendar/graph/table), hover tooltip demand, mobile + desktop.

**Giá**: không public.
**Complaint** (HTR reviews): cần report customizable hơn + refresh nhanh hơn; setup phức tạp ban đầu; thỉnh thoảng data sai.

## 2. RateGain (Navigator, Optima, UNO, Demand.AI)
Nguồn: https://hoteltechreport.com/revenue-management/market-intelligence-tools/rateshopper-by-rategain ; https://rategain.com/press-release/navigator-rate-intelligence-platform-launched/ ; https://www.prnewswire.com/news-releases/rategain-launches-the-ultimate-hotel-online-competitiveness-tool---optima-598303901.html

- Positioning: travel-tech rộng (data, distribution, marketing), rate intelligence cho hotel/chain; cạnh tranh trực diện Lighthouse. Navigator = rate shop + parity + demand; Optima = bản cũ/SMB (OTA rank + parity check + promo tracking).
- Data: OTA, metasearch, GDS; desktop/mobile device tracking; parity view 12 tháng; demand forecast từ airline search + events. "Lightning refresh" live rate ~15s (review); scheduled + on-demand.
- Room mapping: "room mapping intelligence" + keyword-based room type mapping (điểm khác biệt vs suite khác).
- Alerts: email + push notification điện thoại; "Narratives" (câu chữ tóm tắt khi competitor đổi giá); parity "Buzz" reports; daily morning report.
- Integrations: PMS/CRS, open API, RMS.
- Complaint: loading chậm; đôi khi rate disparity; mobile app còn hạn chế (user xin push, personalized dashboard, offline); thiếu auto test booking.
- Giá: "average for category", không công khai.
- Demand.AI / UNO / Revenue AI: chưa fetch được trang product -> không có chi tiết xác minh.

## 3. Fornova (DI, CI, RI, EC)
Nguồn: https://hoteltechreport.com/revenue-management/hotel-rate-parity/fornova-distribution-intelligence ; https://hoteltechreport.com/revenue-management/market-intelligence-tools/fornova-competitive-intelligence

- Positioning: chain/large hotel, mạnh parity & distribution health. FornovaDI (parity+rate shop), CI (competitive), RI (revenue intelligence BI), EC (e-commerce optimizer).
- Data: brand.com, OTA, metasearch, **POS shopping** (undercut theo point-of-sale/country), **test booking**; shop 2x/ngày + daily feed; screenshot làm bằng chứng.
- Parity workflow: daily "distribution health score" theo kênh -> root cause analysis -> xác định "worst offender" OTA -> screenshot/test-booking proof -> gửi partner xử lý (Distribution Partner Management, workflow automation, auto prioritization).
- Integrations: Mews, IDeaS, Duetto, BEONx, Oracle Hospitality, Google Hotel Ads.
- Complaint: filter nhiều + data lớn -> report chậm; filter chưa trực quan; CI module "work in progress", kém thân thiện.
- Giá: theo size property, không public.

## 4. Duetto & IDeaS (chỉ phần dùng compset rate)
Nguồn: https://hoteltechreport.com/revenue-management/revenue-management-systems/duetto ; https://www.duettocloud.com/products/gamechanger ; https://ideas.com/improvements-innovations-whats-new-in-g3-rms-august-2025/ ; https://help.ideasrms.com/g3rms_rp/Content/Rate-Shopping/Rate-Shopping-Competitor.htm (403 khi fetch, chỉ snippet)

- Duetto GameChanger: không tự shop rate (nhận từ rate-shopper đối tác, vd Fornova/Lighthouse) -> hiển thị "competitor rates overview", pricing recommendation, **pricing restriction theo competitor** (vd không vượt/dưới X so với compset). Release mới: toggle **autopilot vs override**, thông tin competitor đầy đủ + filter nhanh, rate-push failure notice + audit trail, real-time decision support. ScoreBoard = reporting/BI. OpenSpace = pricing meetings/events (không liên quan).
- IDeaS G3: user tick "Use in Rate Shopping" cho competitor thật; **Rate Adjustment** (bù chênh breakfast/tax để so like-for-like); loại trừ kênh dữ liệu xấu (Channel Settings); rate shop mới hiển thị ngay nhưng chỉ ảnh hưởng forecast/recommendation sau lần xử lý tiếp theo (hoặc What-If). Khuyến cáo: chỉ đưa competitor thật vào, đối thủ giá khác biệt làm lệch forecast.
- Pattern: pricing grid theo ngày với cột recommended rate + approve/override + dải giá competitor bên cạnh; [suy luận từ mô tả, chưa xem UI].

## 5. CoStar / STR
Nguồn: https://www.mylighthouse.com/resources/blog/star-report-hotels ; https://www.viqal.com/glossary/star-report

- Positioning: benchmarking dựa dữ liệu **actual** từ hotel đóng góp (không scrape). Compset 4-6+ hotel ẩn danh (min contributors để bảo mật).
- STAR report: Occ, ADR, RevPAR của bạn vs compset (avg) + 3 index: MPI (occ), ARI (ADR), RGI (RevPAR) = bạn/compset x100; 100 = fair share; >100 thắng. Daily/weekly/monthly; so với kỳ trước/YoY; rank trong compset (vị trí 1..N).
- Presentation: bảng cột Current Month / YTD / Running 3,12 tháng, Index + Rank. Đơn giản, 1 con số dễ đọc.
- Hạn chế: trễ (T+1/T+7), ẩn danh, không có forward-looking rate.

## 6. Gap vs ScrapeBooking
| Họ có | Ta | Ghi chú |
|---|---|---|
| Multi-OTA/brand.com/metasearch | chỉ Booking | cần source mới |
| LOS/occupancy/device/POS | 2 adult/1 night | scraper param mở rộng |
| Room mapping + normalization | chưa | ta có room_type_new/gone sẵn |
| Alert threshold email/push | không | event đã có -> thiếu delivery |
| Daily email report | không (có AI briefing trên web) | dễ ghép |
| Parity | không | cần brand.com + OTA khác |
| Events calendar/demand | không | |
| Forecast/recommendation | không | |
| Mobile app | không | |
| Rooms-left/sold-out signal | CÓ | lợi thế |

## 7. Ideas to port (rank theo value/effort, team nhỏ)
1. **Email/Zalo/Telegram daily briefing + alert push** (S-M). Gửi AI briefing 7h sáng + alert sold_out/price_down compset. Ref: Lighthouse daily email, RateGain email+push+"Narratives". Fit: Booking-only OK. Với VN, Zalo/Telegram hợp lý hơn Slack.
2. **Alert rules theo threshold user cấu hình** (S-M). vd "compset rẻ hơn mình >X VND", "N đối thủ sold_out cùng ngày" (đây là signal demand riêng của ta). Ref: Lighthouse threshold alerts. Fit: Booking-only OK.
3. **Rate position ranking + index** (S). Hạng giá của mình trong compset từng ngày + price index (đã có median/min), thêm "rank 2/6". Ref: STR rank/ARI, Lighthouse % delta calendar. Fit OK.
4. **Calendar % delta vs compset median** (S). Heatmap có sẵn; thêm chế độ màu theo % chênh giá + hover tooltip (occupancy PMS, sold-out count). Ref: Lighthouse Rate Insight calendar + hover. Fit OK.
5. **Occupancy index MPI/RGI từ PMS import** (S-M). Có PMS occupancy; thêm rooms-sold-out-proxy compset vs occupancy mình; ARI = ADR mình/compset. Ref: STR. Fit OK (PMS CSV).
6. **Export Excel/CSV + scheduled report** (S). Ref: Lighthouse Excel export, daily report. Fit OK.
7. **Room mapping/normalization UI** (M). Cho map room type đối thủ <-> room mình, flag breakfast/refundable, rate adjustment bù chênh (kiểu IDeaS Rate Adjustment). Hiện chỉ so theo hotel-level median -> sai nếu khác hạng phòng. Fit OK nhưng cần parse thêm meal/cancel từ Booking.
8. **On-demand "shop now" + hiển thị freshness** (S, đã có scan-now). Thêm timestamp "cập nhật X phút trước" mọi view; Ref: Lighthouse/RateGain live shop. 
9. **Events/holiday calendar VN layer** (S-M). Static list lễ VN + sự kiện, overlay lên heatmap; giải thích spike sold_out. Ref: Lighthouse events 365d. Fit OK, data tự biên soạn.
10. **Pace/pickup vs lead time view** (M). Dựa PMS import + history; Ref: Lighthouse Pace view. Fit partial (cần PMS data đều).
11. **Compset suggestion tự động** (M). Gợi ý đối thủ từ Booking "similar properties"/cùng khu vực+sao+giá; Ref: Lighthouse Smart Compset. Fit Booking-only OK. Giảm friction onboarding.
12. **Pricing recommendation đơn giản (rule-based)** (L). "Giá gợi ý = median compset x hệ số + uplift khi >=N đối thủ sold_out", approve/override như Duetto/IDeaS, có audit. Làm sau khi có alert + mapping. Fit OK nhưng rủi ro niềm tin; để dạng "gợi ý" không auto-push.
13. **Parity/brand.com + Agoda** (L, source mới). Ref: Lighthouse/Fornova parity. Làm khi có yêu cầu khách; screenshot proof khi violation.
14. **Screenshot evidence lưu kèm scan** (M). Fornova/Lighthouse dùng screenshot làm bằng chứng; ta có "evidence clickable" -> thêm snapshot ảnh/HTML. Fit Booking OK.
15. **Mobile/PWA push** (M-L). RateGain user đòi; PWA đủ, ưu tiên sau email/Zalo.

Bỏ qua (YAGNI): Market Insight demand data (cần dữ liệu search bên thứ 3), STR actual data, GDS, POS shopping, test booking, channel manager.

## 8. Điểm yếu đối thủ -> cơ hội định vị
- Giá ẩn, enterprise, setup phức tạp -> ta: self-serve, setup 5 phút bằng URL Booking (cần signup/billing).
- Refresh/report chậm, report ít custom -> ta: nhanh, briefing AI giải thích "vì sao".
- Mobile yếu -> email/Zalo/PWA tốt là khác biệt.
- Chủ yếu giá, ít inventory signal -> ta: rooms-left/sold-out + confidence.

## Unresolved
- IDeaS & Duetto UI thật (403) -> chưa xác minh grid layout.
- RateGain Demand.AI/UNO/Revenue AI: chưa có dữ liệu.
- Kênh alert chính xác của Lighthouse (Slack? SMS?) chưa xác minh.
- Giá thực tế mọi đối thủ: không public.
- Onboarding step-by-step của tất cả: gated sau demo; flow trong báo cáo là tổng hợp từ blog/review.
