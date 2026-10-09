# Plan: Chuẩn hoá theo nghề revenue và lấp khoảng trống chức năng (góc nhìn quản lý khách sạn)

Ngày: 2026-10-09. Trạng thái: **đã triển khai phần code Phase 0–7 (09/10/2026)**; phần cần tài khoản
bên ngoài còn chờ — xem mục "Tình trạng triển khai" cuối file.
Nghiên cứu nền: `plans/reports/research-261009-1106-hotel-manager-business-audit.md` (gọi tắt **BC**;
mã C1–C22 là chức năng chưa chuẩn, N1–N19 là chức năng cần bổ sung).

## Mục tiêu đo được (sau 8–10 tuần)

| # | Kết quả | Cách đo |
|---|---|---|
| O1 | Khách sạn **tin dữ liệu** | Booking và Agoda ≥95% probe thành công mỗi lượt, 7 ngày liên tiếp. Mọi sự cố kéo dài hơn một lượt có cảnh báo operator trong ≤15 phút. 0 thông báo `skipped` do thiếu cấu hình |
| O2 | **Không chỉ số nào mang tên sai nghề** | Không còn "ADR compset", "RevPAR compset", "Dự báo cầu", "so cùng kỳ" (khi không phải năm trước) trong `dashboard/src/messages`. Mọi ước tính có "≈", nguồn và n/N |
| O3 | **Cảnh báo đáng tin** | Trên dữ liệu 7 ngày: ≥90% sự kiện đổi giá là cùng loại phòng/gói. Sự kiện `room_type_*` giảm ≥70%. Parity có nhãn nguyên nhân |
| O4 | **Tin đến đúng chỗ** | Cảnh báo tới Zalo (email dự phòng) ≤5 phút sau analytics. Người nhận tự chọn loại tin và giờ im lặng. Có đo lượt nhấn và "Đã xử lý" |
| O5 | **Quyết định giá có đủ hai nửa** | Khách sạn có OTB hằng ngày thấy pickup 1/7 ngày và pace của mình cạnh đối thủ; gợi ý giá dùng OTB, sàn/trần và định vị mục tiêu |

## Nguyên tắc

1. **Phase 0 chặn release của mọi phase khác.** Không đưa tính năng mới cho khách khi dữ liệu còn đứt.
2. Chỉ dùng tên chuẩn nghề (ADR, RevPAR, occupancy, STLY, forecast) khi đúng định nghĩa.
3. **Dùng hết dữ liệu đã thu trước khi thêm request.** N1–N3, N6 không tốn request mới.
4. Hàm tính là hàm thuần có test (giữ kiểu `analytics/rules.py`, `market/pacing.py`). Mỗi phase có tiêu
   chí xong đo được.
5. Đổi API thì cập nhật `docs/api/openapi.json` và `dashboard/src/lib/api-types.ts`; đổi chữ thì cập
   nhật cả `vi` và `en` (`npm run i18n:check`).

## Tổng quan phase

| Phase | Nội dung | Mức | Effort | Phụ thuộc | Mã trong BC |
|---|---|---|---|---|---|
| 0 | Dữ liệu liên tục, giao tin thật, sửa lỗi giá nhiều đêm, lịch nghỉ | P0 | ~1–1,5 tuần + quyết định ngân sách proxy | – | C1–C4, C14, C15 |
| 1 | Chuẩn hoá tên chỉ số, ngưỡng cỡ mẫu, nhất quán giao diện, đưa quyết định lên trước | P0 | ~1,5 tuần | – (song song Phase 0) | mục 5.2, C16–C22 |
| 2 | Rate shopping cùng điều kiện, lọc nhiễu sự kiện | P0–P1 | 1,5–2 tuần | – | C5–C8 |
| 3 | Cảnh báo hành động được qua Zalo | P1 | ~2 tuần | 0, 2 | C13, N12 |
| 4 | Radar cạnh tranh từ dữ liệu sẵn có | P1 | ~1,5 tuần | 2 | N1–N3, N6 |
| 5 | OTB của khách sạn, KPI thật, nhiều khách sạn | P1 | 2–3 tuần | – | C10, C11, N7, N8, N11 |
| 6 | RMS-lite có giải thích, đo kết quả | P2 | ~3 tuần | 5 | C12, N9 |
| 7 | Uy tín, hiển thị, compset, báo cáo, lịch cầu | P2 | ~3 tuần | 4 | N4, N5, N10, N13, N14 |
| 8 | Thương mại hoá: dùng thử, gói giá, thanh toán, đối tác | P3 | L | 0–3 | N19, BC mục 7 |
| 9 | Dài hạn: hỏi đáp AI, parity brand.com, biến thể LOS, benchmark cộng đồng | P3 | L | 5–7 | N15–N18 |

Lộ trình gợi ý cho 1–2 dev:
- **Tuần 1–2:** Phase 0 và Phase 1 song song. Riêng 0.1 (khôi phục proxy) làm **ngay hôm nay**.
- **Tuần 2–3:** Phase 2.
- **Tuần 4–5:** Phase 3 và Phase 4. Hồ sơ Zalo nộp từ tuần 1.
- **Tuần 6–8:** Phase 5.
- **Tuần 9–11:** Phase 6.
- Sau đó: Phase 7–9 theo phản hồi khách.

---

## Phase 0: Dữ liệu liên tục và giao tin thật (P0)

**Vì sao:**
- Từ 22:00 ngày 08/10 mọi kênh không thu được dữ liệu; 03–06/10 cũng đứt.
- Chỉ có 1 proxy template (dạng IP tĩnh), không có SMTP, không có `OPS_ALERT_EMAILS`, nên cảnh báo vận
  hành rơi về `LogAlerter` (`backend/app/ops/alerts.py:63-71`). Xem BC C1–C4.

| # | Việc | Chạm vào | Xong khi |
|---|---|---|---|
| 0.1 | **Khôi phục ngay:** proxy duy nhất đang trả `407 Proxy Authentication Required` (`uv run sb check-proxy`, 09/10 khoảng 11:45). Gia hạn hoặc sửa thông tin xác thực, hoặc đổi sang nhà cung cấp residential có xoay IP; kiểm lại bằng `sb check-proxy`; chạy "Quét tất cả ngay" | `.env` (`PROXY_URL_TEMPLATE`), `backend/app/cli.py` (`check-proxy`) | `sb check-proxy` OK; lượt kế tiếp có probe `ok` trên Booking và Agoda |
| 0.2 | **≥2 nhà cung cấp proxy, chọn theo sức khoẻ:** bỏ qua template đang lỗi (ngắt mạch theo template), không xoay vòng mù | `backend/app/collector/proxy.py` (`StaticProxyProvider`), `scheduler/service.py` | Test: một template chết không làm lỗi lượt quét |
| 0.3 | **Kiểm tra proxy trước mỗi lượt**; lỗi thì hoãn lượt và báo, không tạo run rỗng | `scheduler/service.py`, `ops/proxy_check.py` | Không còn run `partial` với 0 probe do proxy |
| 0.4 | **Cảnh báo operator thật:** đặt `OPS_ALERT_EMAILS` (đã có `EmailAlerter`), thêm `WebhookAlerter` (Slack/Discord/Google Chat, tuỳ đội vận hành dùng gì), sau này Zalo OA. **Không dùng Telegram:** bị chặn ở Việt Nam từ 21/05/2025. Điều kiện báo: kênh 0 dữ liệu trong 1 lượt, tỷ lệ thành công <80% trong 24h, run quá hạn | `backend/app/ops/alerts.py:63-71`, `config.py` | Tắt proxy thử → có cảnh báo trong ≤15 phút |
| 0.5 | **Cấu hình SMTP thật**, gửi thử, kiểm tra SPF/DKIM tên miền gửi | `.env`, `notify/email_sender.py` | `notifications.status = sent`; email không vào spam |
| 0.6 | **"Dữ liệu mới nhất lúc …" theo kênh:** API trả `last_success_at` mỗi kênh (quan sát thành công cuối cùng, không phải lượt kết thúc cuối cùng); giao diện dùng nó ở Hôm nay, Bảng điều khiển, Tổng quan | `backend/app/api/routers/data.py:304`, `schemas.py`, `today/page.tsx:45,75`, `dashboard/side-cards.tsx` | Lượt 0 dữ liệu không còn hiện "Quét lúc 06:00". Màn Hôm nay dùng ngày của tenant |
| 0.7 | **SLA cho tenant:** % lượt thành công 7 ngày theo kênh trong "Trạng thái dữ liệu"; báo tenant (email, sau là Zalo) khi dữ liệu cũ hơn một chu kỳ | `api/routers/health.py` hoặc `data.py`, `side-cards.tsx`, `notify/` | Tenant thấy "Booking 98% · Agoda 31% (7 ngày)" |
| 0.8 | **Canary và runbook:** một khách sạn cố định mỗi kênh, kiểm số trường parse được hằng ngày; ghi runbook sự cố proxy/chặn | `ops/`, `docs/operations.md` | Parser trôi được báo trước khi khách thấy |
| 0.9 | **Sửa lỗi tiềm ẩn giá nhiều đêm (BC C15):** khi probe N>1 đêm (min-stay), chuẩn hoá giá Booking về **giá/đêm** (chia N, hoặc đọc giá theo đêm nếu trang có); lưu `nights` cạnh mỗi snapshot; kiểm tra Agoda, iVIVU, Mytour cùng điều kiện | `backend/app/worker/jobs.py:168-170`, `collector/booking/parser.py`, `repo/snapshots.py`, fixture 2 đêm | Fixture 2 đêm cho giá/đêm đúng; không còn sự kiện "+100%" khi min-stay đổi. **Phải xong trước 24/11 và mùa Tết** |
| 0.10 | **Cập nhật lịch nghỉ chính thức (BC C14):** 24/11 "Ngày Văn hóa Việt Nam" (xác minh 1 hay 4 ngày năm 2026); Tết 2027 nghỉ 04–10/02; kỳ nghỉ 2/9 năm 2026 (5 ngày) cho dữ liệu lịch sử. Thêm quy trình cập nhật mỗi năm (theo thông báo của Bộ Nội vụ) | `backend/app/holidays/data.py`, i18n `holiday.*` | Lịch Terminal+ và bản tin có 24/11 |

**Quyết định cần chủ dự án:** ngân sách proxy/tháng và nhà cung cấp thứ hai (BC mục 9).

---

## Phase 1: Chuẩn hoá chỉ số, nhất quán giao diện, đưa quyết định lên trước (P0, song song Phase 0)

**Vì sao:** tên sai nghề làm mất uy tín với revenue manager (BC mục 5.2); một màn trộn kênh, nhiều màn
cho kết luận khác nhau, và quyết định chính bị chôn (BC mục 5.8).

Đường dẫn giao diện tính từ `dashboard/src/app/(app)/` khi không ghi đầy đủ. Nên làm 1.1–1.11 trước
(chủ yếu đổi chữ, 3–4 ngày), rồi 1.12–1.16 (khoảng 1 tuần).

| # | Việc | Chạm vào | Xong khi |
|---|---|---|---|
| 1.1 | "ADR compset" → **"Giá niêm yết TB đối thủ"**. Chuỗi xu hướng "ADR" → "Giá TB đối thủ". Chỉ dùng "ADR" cho số PMS | `dashboard/src/app/(app)/dashboard/page.tsx:156-161,180-206`, `messages/{vi,en}/dashboard.json` | grep "ADR compset" = 0 |
| 1.2 | **Bỏ "RevPAR compset"** khỏi KPI và biểu đồ xu hướng (thay ô KPI bằng "Đối thủ hết/sắp hết") | `page.tsx:147,162-168,189,204` | grep "RevPAR compset" = 0 |
| 1.3 | "Công suất compset ≈" → **"Chỉ báo lấp đầy trên <kênh> (thử nghiệm) ≈"**, luôn hiện khoảng [thấp, cao]; hiện sai số hiệu chỉnh PMS (`PaceReport.calibration` đã có); chưa có PMS thì ghi "chưa hiệu chỉnh" | `page.tsx:169-175`, `market/pace_report.py`, schema `/market/pace` | Có dòng "sai số so PMS ±x điểm (n đêm)" hoặc "chưa hiệu chỉnh" |
| 1.4 | "Dự báo cầu" → **"Mức căng thị trường (hiện tại)"**; tách 2 nguồn (lấp đầy ước tính / tỷ lệ đối thủ hết phòng) thành 2 ký hiệu, không trộn vào một thang 0–100 | `dashboard/demand-forecast.tsx`, `lib/market-metrics.ts:30-35`, messages | Chú thích nêu rõ đây không phải dự báo |
| 1.5 | "Mức nén" → **"Đối thủ hết/sắp hết x/N"**; không tính khi dưới 4 đối thủ quan sát | `lib/market-metrics.ts:69-126`, messages | n/N luôn hiện |
| 1.6 | **Ẩn "Doanh thu 14 ngày" khi chưa có PMS** | `terminal/terminal-cards.tsx`, `messages/*/terminal.json:66` | Chưa có PMS thì hiện hướng dẫn nhập PMS |
| 1.7 | "So cùng kỳ" → **"So các tuần trước (cùng thứ)"**; dành "cùng kỳ năm trước" cho STLY thật (Phase 5) | `messages/*/pace.json`, `helpers.json`, i18n backend nếu có | grep "cùng kỳ" chỉ còn ở STLY |
| 1.8 | **Vị trí giá trung tính theo ngữ cảnh:** rẻ hơn khi thị trường căng thì là "cơ hội tăng giá", không tô xanh mặc định | `lib/market-metrics.ts:175-180`, `side-cards.tsx` | Test các trường hợp căng/không căng |
| 1.9 | **"Vị trí giá k/N (1 = rẻ nhất)"** và **"chỉ số giá niêm yết"** (không gọi ARI/RPI). **Ngưỡng cỡ mẫu theo CoStar STR:** trung vị, chỉ số, hạng, gợi ý giá cần ≥4 đối thủ có giá cùng điều kiện; 3 thì hiện mờ "mẫu nhỏ"; dưới 3 thì ẩn | `analytics/compset.py:50-160`, `market/price_suggest.py:68`, UI | Unit test: 2 đối thủ → `None`, lý do "chưa đủ mẫu"; 3 đối thủ → cờ `small_sample` |
| 1.10 | **Năng lực từng kênh rõ ràng:** Booking/Agoda = "phòng còn + giá"; iVIVU/Trip.com/Mytour = "giá + parity" (theo phân bố tin cậy thật); bộ chọn kênh và trang Cài đặt hiện điều này | `channels/registry.py` (capabilities), `components/channels.tsx` | Chọn iVIVU không hiện ô "phòng còn" |
| 1.11 | "Toàn cảnh thị trường" → **"Toàn cảnh compset"**; cập nhật `PRODUCT.md` (mục Operating Context, Positioning) | messages, `PRODUCT.md` | |
| 1.12 | **Một màn hình, một kênh (BC C16):** `/market/pace` và `/market/occupancy` nhận `?channel=`; giao diện truyền kênh đang chọn; ô dựa trên tồn phòng ghi rõ kênh, và ẩn khi kênh đó không lộ tồn phòng | `api/routers/market.py`, `market/pace_report.py:229`, `lib/api.ts:276`, `dashboard/page.tsx:54`, `availability/page.tsx:41-43`, `dashboard/side-cards.tsx` | Chọn Agoda thì mọi ô trên màn là số Agoda |
| 1.13 | **Chặn dữ liệu cũ (BC C17):** compset chỉ dùng quan sát ≤48 giờ; hiện tuổi dữ liệu từng đối thủ cho mọi vai trò (hiện chỉ operator thấy) | `analytics/compset.py:124`, `hotels/[id]/page.tsx:121-126` | Listing tạm dừng không còn góp vào trung vị |
| 1.14 | **Một khái niệm, một cách tính (BC C18):** trung vị ở mọi nơi; một thang mức cầu chung; "đêm cuối tuần" = đêm T6, T7; quy ước dấu/màu "so với bạn" thống nhất; heatmap giá hiện đủ đơn vị; "Cập nhật" dùng chung định nghĩa ở 0.6 | `lib/market-metrics.ts`, `terminal/terminal-cards.tsx:19-24`, `availability/heatmap-table.tsx:67-71`, `lib/format.ts:69-72`, `competitors/page.tsx`, `rates/rate-views.tsx` | Test: cùng dữ liệu, mọi màn cho cùng kết luận |
| 1.15 | **Đưa quyết định lên trước (BC C19):** thẻ "Việc cần làm hôm nay" (gợi ý giá, đêm căng, KM đối thủ mới) ở đầu Bảng điều khiển và Hôm nay; gợi ý hiện **giá mục tiêu VND** và cơ sở giá; "Hôm nay" vào thanh điều hướng chính; chọn khoảng ngày tuỳ ý (xem trước Tết) | `dashboard/page.tsx`, `today/page.tsx`, `components/market-suggestion.tsx:55-57`, `components/app-shell.tsx:147-149`, `rates/page.tsx:21` | Mở app buổi sáng thấy ngay việc cần làm, không phải cuộn |
| 1.16 | **Dấu lễ/sự kiện trên màn ra quyết định (BC C20)** và **đổi nhãn ước tính (BC C21, C22):** "≈ phòng còn giảm" thay "Pickup/đã bán"; "Tín hiệu đặt phòng" liệt kê theo khách sạn kèm nguồn; "Sự kiện" (nhật ký) → "Thay đổi" | `hotels/[id]/page.tsx:204`, `terminal/terminal-cards.tsx:176-188`, messages | grep "đã bán" chỉ còn ở số PMS |

---

## Phase 2: Rate shopping cùng điều kiện và lọc nhiễu (P0–P1)

**Vì sao:**
- 83% sự kiện tăng giá mức khách sạn trên Booking là do loại phòng xuất hiện/biến mất.
- iVIVU sinh ~6.000 sự kiện loại phòng mới/mất.
- Parity Mytour bị mã KM của kênh làm nhiễu (BC C5–C8).

| # | Việc | Chạm vào | Xong khi |
|---|---|---|---|
| 2.1 | **Tách đổi giá thật và đổi cơ cấu.** `PRICE_UP/DOWN` mức khách sạn chỉ khi loại phòng rẻ nhất ở hai lượt là cùng một loại (cùng `room_type_id`, cùng khoá gói). Còn lại sinh sự kiện mới `lowest_rate_shift` kèm lý do (phòng rẻ nhất hết / mở lại) và đưa vào tín hiệu cầu | `backend/app/analytics/rules.py:152-264`, `EventType`, migration nếu cần, `insight/prompt.py` (quy tắc mới), `messages/*/labels.json` | Chạy lại trên fixture: ≥90% price_up/down là cùng loại phòng |
| 2.2 | **Giá đổi 7 ngày cùng điều kiện** (so cùng loại phòng rẻ nhất, hoặc trung vị đổi giá các loại phòng còn ở cả hai lượt) | `rules.py:317-365` (`compute_metrics`) | Unit test có ca "phòng rẻ nhất hết" |
| 2.3 | **Chống nhấp nháy loại phòng:** chỉ `room_type_gone` khi vắng ≥2 lượt liên tiếp; không đưa `room_type_new/gone` vào cảnh báo; chuẩn hoá khoá phòng iVIVU/Mytour (tên chuẩn hoá + sức chứa, bỏ mã nhà cung cấp) | `rules.py`, `collector/ivivu/parser.py`, `collector/mytour/parser.py`, `analytics/service.py` | Sự kiện `room_type_*` 7 ngày giảm ≥70% |
| 2.4 | **Cơ sở giá "có bữa sáng" / "chỉ phòng":** parser Booking nhận "no meals", "breakfast not included", "breakfast ... (extra)"; `PriceBasis` thêm `breakfast`, `room_only`; cột `min_breakfast_price` hoặc tính từ `rates` | `collector/booking/parser.py:103-120`, `analytics/compset.py:18-27`, `db/models.py`, migration, `components/price-basis.tsx` | `breakfast=false` xuất hiện trong dữ liệu Booking; bộ chọn có 4 cơ sở |
| 2.5 | **Parity có nguyên nhân:** so từng cặp cùng điều kiện (hoàn huỷ, bữa sáng); gắn nhãn *KM kênh tự áp* (coupon/flash sale của kênh), *KM khách sạn bật* (Late Escape, Early Bird…), *nguồn bán lại* (`source_supplier`), *giá thường*; hiện cả giá trước KM | `analytics/cross_channel.py:54-93`, `notify/alert_rules.py:225-295`, email template, chi tiết đêm | Email parity ghi "do mã CHAMTHU26 của Mytour" khi đúng |
| 2.6 | **Đánh dấu giá thành viên/Genius hiển thị cho khách chưa đăng nhập** (Booking cho phép ở APAC): cờ `loyalty`, mặc định không đem so | `collector/booking/parser.py`, `selectors.py`, `RatePlan` | Fixture có giá Genius được gắn cờ |
| 2.7 | **Năm trạng thái thay cho ba:** còn bán / hết mọi loại phòng / **bị hạn chế** (bán được ở số đêm khác hoặc đóng ngày đến) / không có giá / lỗi. Hiện nay `SKIPPED_CALENDAR` bị tính là hết phòng và `NO_ROOMS_1N` là "unknown" (`analytics/rules.py:39-46`). "% đối thủ hết phòng" chỉ đếm hết phòng thật; hạn chế hiện riêng | `analytics/rules.py`, `domain/models.py`, `analytics/compset.py`, UI heatmap | Đêm min-stay hiện "hạn chế", không tô đỏ "hết phòng" |
| 2.8 | **Parity theo Win/Meet/Loss** cho khách sạn của bạn: dung sai cấu hình được (mặc định "Meet" trong ±1%), tách mốc công khai và mốc thành viên | `analytics/cross_channel.py`, API, chi tiết đêm | Báo cáo % đêm Win/Meet/Loss mỗi kênh |
| 2.9 | **Đo trước/sau:** script đếm sự kiện mỗi khách sạn-đêm, tỷ lệ cùng loại phòng; ghi vào report | `backend/scripts/` | Có bảng trước/sau trong report |

---

## Phase 3: Cảnh báo hành động được qua Zalo (P1)

**Vì sao:**
- Khách sạn Việt Nam làm việc trên Zalo (81,3 triệu người dùng/tháng).
- Email hiện chưa gửi được (BC C13, N12).
- Không chọn Telegram: bị chặn ở Việt Nam từ 21/05/2025.

**Chi phí Zalo** (BC mục 3.2):
- ZNS (nay gọi "ZBS Template Message"): 200–300₫/tin gửi thành công. Khoảng 20–30 nghìn ₫ mỗi người
  nhận mỗi tháng với 3 tin/ngày.
- Cần **OA doanh nghiệp đã xác thực** (tên trùng đăng ký kinh doanh) và tài khoản Zalo Cloud nạp trước.
- Mỗi template phải được duyệt trước. Link phải đặt trong nút, không trong nội dung.
- Gói OA Growth (khoảng 1,4 triệu ₫/6 tháng) nếu cần API OA.

| # | Việc | Chạm vào | Xong khi |
|---|---|---|---|
| 3.1 | **Tách kênh gửi** khỏi email: interface `Notifier` (email, zalo_zns, webhook); outbox `notifications` thêm cột `channel` | `backend/app/notify/service.py`, `email_sender.py`, `db/models.py`, migration | Một sự kiện gửi được qua nhiều kênh, không trùng (giữ `dedupe_key` + channel) |
| 3.2 | **Thủ tục Zalo (việc giấy tờ, bắt đầu ngay tuần 1):** xác thực OA doanh nghiệp, mở Zalo Cloud, soạn và nộp duyệt 3–4 template: cảnh báo gom theo lượt, bản tin sáng, dữ liệu cũ, báo cáo tuần | Tài liệu nội bộ | Template được duyệt |
| 3.3 | **Gửi ZNS** theo số điện thoại người nhận; nút "Xem chi tiết" mở link sâu tới đêm hoặc bản tin; theo dõi trạng thái gửi và chi phí mỗi tin | `notify/zalo.py` mới, cấu hình | Tin tới số thử từ lượt quét thật; chi phí ghi vào log |
| 3.4 | **Đăng ký theo người:** loại tin × kênh × giờ im lặng × tối đa N tin/ngày (vượt thì gom digest) | bảng `notification_subscriptions`, API `/notifications/*`, `settings/notifications-tab.tsx` | Viewer cũng tự chọn được tin cho mình |
| 3.5 | **Loại cảnh báo mới:** đêm căng (≥N đối thủ hết/sắp hết, hoặc chỉ số khu vực giảm nhanh); đối thủ **tăng** giá cùng điều kiện; bạn lệch định vị mục tiêu >X%; bạn hết/đóng trên một kênh; dữ liệu cũ | `notify/kinds.py`, `notify/alert_rules.py` | Mỗi loại có test và tham số trong miền |
| 3.6 | **Tin có hành động:** link sâu tới đêm; nút "Đã xử lý" ghi nhận (dùng để đo O4) | `notify/render.py`, endpoint ghi nhận | Có số liệu lượt nhấn/đã xử lý theo tuần |

---

## Phase 4: Radar cạnh tranh từ dữ liệu sẵn có (P1)

**Vì sao:** dữ liệu đã thu nhưng chưa dùng (BC N1–N3, N6): `promo_label`, `price_original`,
`min_length_of_stay`, `refundable`, `properties_found`.

| # | Việc | Chạm vào | Xong khi |
|---|---|---|---|
| 4.1 | **Radar khuyến mãi:** theo đối thủ × đêm: nhãn, độ sâu (so giá gạch), ngày bật/tắt; sự kiện `promo_start`/`promo_end`; tab con trong "Giá & định giá"; đưa vào bản tin AI và cảnh báo "đối thủ bật KM sâu ≥X%" | `analytics/` (hàm thuần mới), API `/market/promotions`, `rates/rate-views.tsx` | Thấy được dòng kiểu "Đối thủ A: Late Escape −40%, 12 đêm, từ 14/10" |
| 4.2 | **Radar hạn chế:** chip "tối thiểu N đêm" trên heatmap; sự kiện `min_stay_change`; đóng kênh đã có | `analytics/service.py`, `overview/board.tsx` | Đêm lễ có min-stay hiện chip |
| 4.3 | **Chính sách huỷ:** % gói hoàn huỷ và mức giảm non-refundable so với flex, mỗi đối thủ | API + thẻ ở "Đối thủ" | Có số cho mỗi đối thủ trên kênh tham chiếu |
| 4.4 | **Chỉ số khan phòng khu vực theo lead time:** số chỗ ở còn phòng theo đêm, đường theo số ngày trước khi đến, so tuần trước | `marketscan/city.py`, API `/market/city`, `terminal/city-market-card.tsx` | Đường "còn N KS trống" cho 30 đêm tới |

---

## Phase 5: OTB của khách sạn, KPI thật, nhiều khách sạn (P1)

**Vì sao:** không có OTB theo ngày thì không có pickup/pace của mình; tenant "Group" đang bị tính như
một khách sạn (BC C10, C11).

| # | Việc | Chạm vào | Xong khi |
|---|---|---|---|
| 5.1 | **Bảng `otb_snapshots`**: (`tenant_id, hotel_id, as_of_date, stay_date, rooms_otb, revenue_otb, rooms_available`; tuỳ chọn `cancellations`, `group_block`, `group_pickup`, `segment`, `channel`, `room_type`). Hai cách nhập: (a) báo cáo OTB theo ngày, `as_of_date` mặc định là ngày tải lên; (b) **file đặt phòng chi tiết** (ngày đặt, ngày đến/đi, ngày huỷ, trạng thái, doanh thu), từ đó tự dựng snapshot cho cả quá khứ. Giữ `own_hotel_daily` cho số thực tế đã qua | `db/models.py`, migration, `pms/base.py`, `pms/csv_adapter.py`, `api/routers/pms.py` | Nhập 2 ngày liên tiếp không ghi đè; một file đặt phòng 12 tháng dựng được pace và STLY ngay |
| 5.2 | **Mẫu ánh xạ cho báo cáo "phòng đã đặt theo ngày"** của các PMS phổ biến (ezCloud trước); tuỳ chọn nhận file qua email riêng mỗi tenant | `pms/`, docs | File xuất ezCloud nhập không cần sửa tay |
| 5.3 | **Hàm thuần:** pickup 1/7 ngày; pace so 4 tuần trước và STLY (khi có); dự báo cộng pickup lịch sử theo thứ và lead time | `market/` (module mới), test | Khớp tính tay trên bộ dữ liệu mẫu |
| 5.4 | **KPI thật của bạn** (Occ/ADR/RevPAR, OTB, pickup) trên Bảng điều khiển và Hôm nay; **chỉ số giá niêm yết** có n/N và hạng; MPI/RGI chỉ hiện khi có số thật của compset (Phase 9) | `dashboard/page.tsx`, `today/page.tsx`, `pace/pace-view.tsx` | Quyết định buổi sáng có cả hai nửa |
| 5.5 | **Nhiều khách sạn:** compset riêng cho từng khách sạn của bạn (`compsets` hoặc cột `compset_of` trong `tenant_hotels`); bộ chọn khách sạn ở thanh trên; màn danh mục | `analytics/compset.py`, `market/pace_report.py:239`, watchlist API/UI | Tenant 2 khách sạn thấy 2 compset, 2 pace |
| 5.6 | **Sửa gốc chỉ báo lấp đầy:** tổng phòng lấy từ số công bố hoặc người dùng nhập (`hotels.rooms_total`), không lấy số lớn nhất từng thấy (`market/occupancy.py:66-73`), vì cách đó làm công suất ra cao (Suzuki 2023). Hiệu chỉnh bằng khách sạn của bạn: **MAPE và độ lệch theo nhóm lead time**; chỉ báo nào sai số quá ngưỡng thì ẩn | `market/occupancy.py`, `market/pacing.py:86-94`, `db/models.py` | Màn chỉ báo hiện "sai số ±x điểm ở 0–7 / 8–30 / 31–90 ngày" |

---

## Phase 6: RMS-lite có giải thích (P2, sau Phase 5)

**Vì sao:** gợi ý giá hiện chỉ nhìn đối thủ, chưa có sàn/trần/định vị, chưa đo kết quả (BC C12, N9).

| # | Việc | Xong khi |
|---|---|---|
| 6.1 | **Chiến lược giá:** giá gốc theo mùa/thứ, sàn/trần, định vị mục tiêu so compset (VD "+5% trên trung vị"), bước làm tròn, mức đổi tối đa mỗi ngày | Không gợi ý nào vượt sàn/trần (test) |
| 6.2 | **Điều chỉnh có giải thích, cộng dồn:** OTB/pickup so pace, mức căng (compset + khu vực), thứ, lead time, sự kiện/lễ (Phase 7.5); mỗi điều chỉnh là một dòng lý do có số | Mỗi gợi ý có lý do có số, bấm được tới dữ liệu gốc |
| 6.3 | **Gợi ý hạn chế:** min-stay đêm cao điểm, tắt KM/đóng giá không hoàn huỷ khi căng | Có ít nhất 2 loại gợi ý ngoài giá |
| 6.4 | **Nhật ký và đo kết quả:** sau đêm lưu trú so OTB/ADR thực tế với gợi ý; báo cáo tháng "gợi ý đã áp dụng → kết quả" | Backtest 60 ngày; tỷ lệ áp dụng đo được |

Không làm: tự đẩy giá vào channel manager (giữ quyết định ở người dùng, như báo cáo 01/10).

---

## Phase 7: Uy tín, hiển thị, compset, báo cáo, lịch cầu (P2)

| # | Việc | Ghi chú |
|---|---|---|
| 7.1 | **Uy tín theo thời gian (N4):** bảng `hotel_review_snapshots` (điểm, số review, kênh, ngày); tốc độ review/tháng; chỉ số giá trị = vị trí giá so với vị trí điểm; bản đồ giá–chất lượng | Nguồn: thẻ kết quả tìm kiếm (đã quét); không thêm request |
| 7.2 | **Vị trí hiển thị (N5):** lưu thứ hạng trang 1 theo đêm (chuỗi thời gian, không chỉ `best_rank`); huy hiệu Preferred/Genius/Ad/deal/"Free cancellation" trên thẻ | `marketscan/parser.py`, `upsert.py`, bảng mới |
| 7.3 | **Compset chính/phụ, trọng số (N10):** compset chính 5–10 khách sạn, compset phụ (theo mùa, tham vọng); ghi tiêu chí chọn; cảnh báo khi một khách sạn chiếm >50% số phòng compset (quy tắc CoStar STR); nhắc rà soát ít nhất 2 lần/năm (đối thủ lệch hạng sao/điểm/giá) | `tenant_hotels` thêm `tier`, `weight`; cần `hotels.rooms_total` (5.6) |
| 7.4 | **Báo cáo (N13):** Excel "rate shop" (khách sạn × đêm: giá, trạng thái, KM, hạn chế, n/N); PDF báo cáo tháng cho chủ đầu tư; báo cáo tuần gửi Zalo dạng ảnh/link | `export/`, `notify/weekly.py` |
| 7.5 | **Lịch cầu (N14):** lễ thị trường nguồn (Hàn, Trung, Nhật, Đài Loan…), nghỉ hè Việt Nam, sự kiện lớn; tenant chọn thị trường nguồn của mình; dải "năm trước dịp này" | `holidays/data.py` (thêm `source_markets`), Cài đặt › Sự kiện |

---

## Phase 8: Thương mại hoá (P3)

| # | Việc | Ghi chú |
|---|---|---|
| 8.1 | **Gói và giá** theo khách sạn/tháng (số đối thủ × số kênh × horizon), bản group | Đề xuất cụ thể ở BC mục 7 |
| 8.2 | **Dùng thử tự phục vụ 14 ngày:** dán URL khách sạn → gợi ý compset từ khám phá thị trường → quét thử ngay → bản tin đầu tiên trong ngày | Tái dùng `market/city/hotels`, `scan-now` |
| 8.3 | **Thanh toán** (chuyển khoản/VNPay), hoá đơn điện tử | |
| 8.4 | **Bản miễn phí có giới hạn** (báo cáo compset tuần, 1 kênh) làm phễu, cạnh tranh trực tiếp với dashboard miễn phí của Lighthouse | Giới hạn để kiểm soát chi phí proxy |
| 8.5 | **Kênh đối tác:** PMS/channel manager nội địa, công ty quản lý khách sạn, tư vấn revenue | Hợp đồng chia sẻ doanh thu |

## Phase 9: Dài hạn (P3)

- **N17 Hỏi đáp tiếng Việt** trên dữ liệu ("đêm 30/4 đối thủ nào còn phòng?"), trả lời bằng truy vấn có
  kiểm chứng và link bằng chứng; không cho mô hình tự bịa số.
- **N15 Parity với website trực tiếp và Google Hotels** theo mẫu, có ảnh chụp.
- **N16 Biến thể tìm kiếm** (2 đêm, 1 khách, mobile) với ngân sách request riêng.
- **N18 Benchmark cộng đồng:** khách sạn góp OTB/kết quả ẩn danh → MPI/ARI/RGI thật theo khu vực
  (cần ≥5 khách sạn/khu vực và điều khoản dữ liệu).

---

## Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Đổi tên/bỏ chỉ số làm khách quen giao diện mẫu bị hụt | Đổi một lần, ghi chú "đã đổi tên vì…" trong tooltip 2 tuần |
| Proxy tốn tiền hơn dự kiến | Quét theo tầng (đã có), ưu tiên kênh có tín hiệu phòng (Booking, Agoda); kênh chỉ giá quét thưa hơn |
| Zalo duyệt template chậm / OA cần xác thực doanh nghiệp | Nộp hồ sơ từ tuần 1 (song song Phase 0–2); email làm dự phòng; PWA push (đã có PWA) là phương án phụ |
| Khách không có OTB hằng ngày | Bắt đầu bằng upload tay 1 lần/ngày; tìm đối tác PMS cho API |
| ToS kênh, chống bot siết | Giữ nguyên tắc lịch sự; tư vấn pháp lý trước khi bán rộng (spec gốc đã yêu cầu) |
| Đối thủ miễn phí (Lighthouse Market Alerts, tool extranet OTA) | Tập trung vào thứ họ không có: phòng còn đích danh, OTA nội địa, tiếng Việt, Zalo, radar KM/hạn chế |

## Câu hỏi mở

Xem BC mục 9. Các câu chặn Phase 0, 3 và 5:
1. Ngân sách proxy và nhà cung cấp thứ hai?
2. Công ty đã có Zalo OA xác thực chưa?
3. Khách hiện tại dùng PMS nào, có xuất được báo cáo OTB hằng ngày không?


---

## Tình trạng triển khai (09/10/2026)

Ký hiệu: ✅ xong (code + test) · 🟡 xong phần code, chờ tài khoản/việc bên ngoài · ⏭ không làm đợt này.

| # | Tình trạng | Ghi chú / nơi sửa |
|---|---|---|
| 0.1 | 🟡 | Proxy vẫn trả `407` (`sb check-proxy` 09/10 13:2x): cần gia hạn/sửa thông tin nhà cung cấp. Runbook `docs/operations.md` 7a |
| 0.2 | ✅ | `collector/proxy.py` (chọn theo sức khoẻ, ngắt template lỗi 3 lần/10 phút, đọc `proxy:health` từ Redis); cần ≥2 template trong `.env` |
| 0.3 | ✅ | `scheduler/service.py`: kiểm tra proxy trước mốc, mọi proxy hỏng → hoãn mốc (tối đa 4 giờ) + báo; quét bù đợi proxy |
| 0.4 | ✅/🟡 | `ops/alerts.py` (`WebhookAlerter`, `CompositeAlerter`), `ops/health_checks.py` (kênh <80%/24h, kênh không có dữ liệu >10h, run quá hạn); cần đặt `OPS_ALERT_EMAILS`/`OPS_ALERT_WEBHOOK_URLS` (`sb check-ops`) |
| 0.5 | 🟡 | Chưa có SMTP thật (SPF/DKIM). Đường gửi đã kiểm bằng SMTP giả |
| 0.6 | ✅ | `GET /data-status`; `last_run` chỉ tính lượt có dữ liệu; dashboard `lib/freshness.ts` |
| 0.7 | ✅ | SLA 7 ngày theo kênh trên thẻ Trạng thái dữ liệu; tin `data_stale` cho tenant |
| 0.8 | ✅ | `ops/canary.py`, `sb canary`, cron 08:15; runbook 7a/7b |
| 0.9 | ✅ | `collector/booking/results.py` chia giá/đêm khi probe N>1 đêm; `min_stay` lưu cạnh snapshot/metric |
| 0.10 | ✅ | 24/11/2026 (1 ngày), Tết 2027 04–10/02, 2/9/2026 29/8–2/9, 2/9/2027 02–05/09 (VPCP 10065/VPCP-KGVX) |
| 1.1–1.8, 1.11, 1.14–1.16 | ✅ | dashboard (đổi tên, trung vị, một thang mức cầu, đêm cuối tuần T6–T7, Việc cần làm hôm nay, Hôm nay trên thanh điều hướng, nhãn "≈ phòng còn giảm", dấu lễ) |
| 1.3 | ✅ | khoảng [thấp, cao] + sai số so PMS theo lead time (`market/pacing.calibrate_by_lead`) |
| 1.9 | ✅ | `analytics/compset.py` (≥4 / 3 mẫu nhỏ / <3 ẩn; n/N) |
| 1.10 | ✅ | `channels/registry.channel_capability`; giao diện ẩn ô phòng còn với kênh "giá + parity" |
| 1.12 | ✅ | `/market/pace`, `/market/occupancy` nhận `channel` |
| 1.13 | ✅ | quan sát >48 giờ (so với quan sát mới nhất của đêm) không vào trung vị; ô ghi "cũ" |
| 2.1–2.3 | ✅ | `analytics/rules.py`; đo trên 10 ngày dữ liệu thật: đổi giá mức KS 100% cùng phòng + gói, `room_type_*` −96% |
| 2.4 | ✅ | parser Booking nhận bữa sáng trả thêm/không bữa (chữ + data-block-id); cơ sở giá có bữa sáng/chỉ phòng |
| 2.5, 2.8 | ✅ | `analytics/cross_channel.py` (so cùng khoá gói, nguyên nhân, Win/Meet/Loss ±1%) |
| 2.6 | ✅ | cờ `loyalty` (Genius) — chưa có fixture có Genius thật |
| 2.7 | ✅ | trạng thái `restricted` (lịch không nhận khách, min-stay) tách khỏi hết phòng |
| 2.9 | ✅ | `backend/scripts/measure_event_noise.py` |
| 3.1, 3.3–3.6 | ✅/🟡 | `notify/channels.py`, outbox theo kênh, đăng ký theo người, loại cảnh báo mới, link theo dõi + "Đã xử lý", `/notifications/engagement`. Zalo ZNS chờ OA xác thực + template (3.2) |
| 3.2 | 🟡 | việc giấy tờ của công ty |
| 4.1–4.4 | ✅ | `market/radar.py`, `/market/radar/*`, sự kiện `promo_start/end`, `min_stay_change`, cảnh báo KM sâu |
| 5.1, 5.3, 5.4 | ✅ | `otb_snapshots`, `pms/otb.py`, `/pms/otb/import`, `/market/otb` |
| 5.2 | 🟡 | ánh xạ cột tự nhận tên tiếng Việt/Anh phổ biến; mẫu riêng ezCloud cần file xuất thật để đối chiếu |
| 5.5 | ✅ | `tenant_hotels.compset_of`, `own_hotel_id` trên overview/pace/otb/strategy |
| 5.6 | ✅ | `hotels.rooms_total` làm mẫu số; MAE/MAPE theo lead time, nhóm sai số >20 điểm `usable=false` |
| 6.1–6.4 | ✅ | `market/price_suggest.py` (RMS-lite), `/market/strategy`, `/market/suggestions/{outcomes,backtest}` |
| 7.1, 7.2 | ✅ | `hotel_review_snapshots`, huy hiệu/quảng cáo trên `market_list_prices`, `/market/reputation`, `/market/visibility` (cần khu vực thị trường đang quét) |
| 7.3 | ✅ | compset chính/phụ, trọng số, `/watchlist/compset-review` (≥4, 50% số phòng, rà soát 6 tháng) |
| 7.4 | ✅ | `/export/rate-shop.xlsx`, `/export/monthly-report.html` (in PDF từ trình duyệt; báo cáo tuần qua Zalo theo template) |
| 7.5 | ✅ | lễ thị trường nguồn (cn, kr, jp, tw, ru, in, us, au), nghỉ hè VN, `tenants.source_markets` |
| 8, 9 | ⏭ | thương mại hoá và dài hạn: theo phản hồi khách |

Migration: `0012`–`0014`. Đo trước/sau: `plans/reports/selftest-261009-rm-standards.md`.

### Cập nhật 09/10/2026 chiều: chỉ giữ Booking.com

Theo quyết định của chủ sản phẩm, bỏ mọi kênh khác (Agoda, iVIVU, Trip.com, Mytour, Traveloka,
Expedia) và các tính năng chéo kênh: 1.10 (năng lực kênh), 1.12 (chọn kênh), 2.5 + 2.8 (parity,
Win/Meet/Loss), cảnh báo `own_parity_gap`, "đóng bán trên kênh", tín hiệu cầu của kênh, gợi ý cùng
khách sạn trên kênh khác. Migration `0015_booking_only` xoá dữ liệu các kênh đó (backup
`/tmp/sb_backup/scrapebooking_pre_booking_only_*.dump`). Các mục còn lại của Phase 0–7 giữ nguyên,
chạy trên dữ liệu Booking.com.
