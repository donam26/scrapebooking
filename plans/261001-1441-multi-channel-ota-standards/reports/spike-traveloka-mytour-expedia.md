# Spike: Traveloka, Mytour, Expedia

Ngày: 2026-10-01, khoảng 14:50–15:40. Máy macOS, IP thẳng (CMC, Hà Nội) và proxy VN trong `.env` (IP thoát xoay vòng: VNPT/Viettel). Không đăng nhập, không gửi dữ liệu cá nhân, các request cách nhau ≥2,5 s.
Script và payload thô nằm trong scratchpad của phiên (`hard-otas/`), không commit.

## 0. Kết luận

| Kênh | Kết luận | Cách thu | Bằng chứng chính |
|---|---|---|---|
| **Mytour** | **Làm được, đã có adapter** | HTTP thuần (curl_cffi) gọi API JSON `apis.tripi.vn`, không cần trình duyệt | Chạy thật qua proxy VN: **6/6 probe OK** (Rex Sài Gòn + Melia Vinpearl PQ × 3 ngày), verify + suggest OK, VND, giá đã gồm thuế |
| **Traveloka** | **Chưa làm được** | — | DataDome: curl qua proxy bị 403 ngay trang chủ; trình duyệt (headless mới, có giao diện, cả Chrome thật) đều trượt bước kiểm tra thiết bị rồi bị **chặn theo IP** ("Truy cập tạm thời bị hạn chế"). Chỉ có `urls.py` |
| **Expedia** | **Chưa làm** (chỉ chạy được bằng trình duyệt, mong manh) | — | Akamai Bot Manager: proxy bị 429 "Phần mềm tự động?"; IP thẳng tải được trang và GraphQL giá, nhưng sau khoảng 20 lệnh GraphQL thì bị 429 "Provisioned request rate has been exceeded"; gọi lại bằng curl cũng 429. Chỉ có `urls.py` |

Số request: Mytour khoảng 42 lệnh API + 7 lần mở trang (cộng 45 file JS tĩnh tải một lần để tìm endpoint); Traveloka khoảng 14 lần mở trang; Expedia khoảng 8 lần mở trang (kèm các XHR GraphQL do trang tự gọi).

---

## 1. Mytour (mytour.vn, nền tảng Tripi)

### 1.1 Định danh
- Trang khách sạn: `https://mytour.vn/khach-san/<hotelId>-<slug>.html` (VD `23812-sol-by-melia-phu-quoc.html`). Mytour chỉ đọc id, slug sai thì tự chuyển hướng về slug đúng. Trang tỉnh/quận có dạng `/khach-san/tp2/...`, `/khach-san/td446/...`; trang lọc có dạng `/khach-san/khach-san-gia-tot/...`. URL đoán trước đây `tp1067-...` là trang tỉnh nên trả 404.
- Trang là Next.js. `__NEXT_DATA__` của trang chi tiết có `hotelDetail` nhưng **không có giá**. Trang danh sách hiển thị "Xem giá" với `price: -1`. Giá được tải bằng XHR.

### 1.2 Endpoint (đều là `https://apis.tripi.vn/hotels…`)
| Mục đích | Request | Ghi chú |
|---|---|---|
| Giá theo phòng (probe) | `POST /v3/rooms/availability` `{"checkIn":"15-10-2026","checkOut":"16-10-2026","adults":2,"children":0,"rooms":1,"hotelId":23812,"isSeo":false,"useBasePrice":false,"includeD2cRoom":true,"allowAffiliate":true}` | **Phải gọi lặp**: lần đầu trả `completed:false, items:[]`, lần 2–3 trả `completed:true`. Mỗi lần gọi mất khoảng 5 s khi giãn cách 2,5 s |
| Verify | `POST /v3/hotels/detail` `{"hotelId":…}` | Có tên, sao, địa chỉ, `countryCode`, toạ độ, slug. Id không tồn tại trả `code 4103 "Khách sạn không tồn tại."` |
| Gợi ý (D8) | `GET /v3/suggestions/auto-complete?term=<tên>` | Mục `type=HOTEL` có `hotelId`, toạ độ, slug |
| Chế độ danh sách (chưa dùng) | `POST /v3/hotels/availability` | Có trong JS, chưa thử (YAGNI) |

**Header bắt buộc**: `appId: mytour-web` và `appHash = base64(sha256("<unix giây làm tròn xuống 300>:<khoá web>"))`. Khoá web là chuỗi tĩnh trong `_app-*.js`. Hash tự tính khớp từng byte với header trình duyệt gửi. Thiếu `appHash` thì trả `3004 "Hash không tồn tại"`; thiếu cả `appId` thì trả `3005 "Partner không tồn tại"`. Không cần cookie hay token phiên. Các header khác (`deviceId`, `currency: VND`, `lang: vi`, `countryCode: VN`, `caid: 17`, `platform: website`) chép y như web gửi.

### 1.3 Chống bot
- `mytour.vn` có Cloudflare nhưng không hiện challenge. `apis.tripi.vn` không thấy chặn ở khoảng 42 request, cả IP thẳng lẫn proxy.
- Rủi ro chính: **khoá web có thể đổi khi Mytour deploy**. Khi đó mọi probe trả `error="api 3004: Hash không tồn tại"`, canary sẽ bắt được. Cách sửa: grep `appHash` trong `_app-*.js` rồi cập nhật `_WEB_SECRET` ở `app/collector/mytour/api.py`.

### 1.4 Ánh xạ trường (chuẩn D3/D4)
Mytour là **chợ nhiều nguồn**: mỗi loại phòng có nhiều giá, mỗi giá thuộc một nguồn (`rateCode` + `agencyId`).

| Chuẩn | Trường Mytour | Đã kiểm chứng |
|---|---|---|
| `RatePlan.price` | `rate.price`: giá/phòng/**đêm**, VND, **đã gồm thuế phí**, sau KM tự áp | 1.585.888 (giá chưa thuế hiện trên trang) + 222.112 thuế = 1.808.000 = `price`. Đặt 2 đêm: `price` vẫn là giá 1 đêm (tổng 2 đêm 7.562.000 = 2 × 3.781.000) |
| `price_original` | `promotionInfo.priceBeforePromotion` | Giá gạch "-9%" trên trang |
| `taxes_included` | `includedVAT` (true ở mọi giá đã thấy) | Như trên; trang ghi "Giá đã bao gồm: Thuế và phí dịch vụ khách sạn" |
| `promo_label` | `promotions[].code` (VD `CHAMTHU26`) | Trang hiện "Nhập mã: CHAMTHU26". **Không trừ vào `price`** vì người dùng phải tự nhập mã. Giá sau mã nằm ở `priceAfterPromotionCode` (không lưu) |
| `refundable` / `breakfast` | `freeCancellation` / `freeBreakfast` | `refundable` (true cả khi "Hoàn huỷ một phần") **không** dùng |
| `max_persons`, `max_occupancy` | `room.maxGuests` | |
| `source_supplier` | `"<rateCode>:<agencyId>"`, VD `ta:27`, `ota:4`, `ota:32` | Không lưu `supplierName` vì có link nhóm Zalo của đại lý |
| `RatePlan.name` | `shortCancelPolicy` (+ " · Bữa sáng") | Ba giá trị đã thấy: "Miễn phí hoàn huỷ", "Hoàn huỷ một phần", "Không hỗ trợ hoàn huỷ" |
| `badge_count` | max(`availableAllotment`) trong các giá của phòng | Trang hiện "Chỉ còn 5 phòng trống" đúng với allotment 5. Các nguồn **không cộng được** với nhau, nên lấy max làm cận dưới |
| `stock_scope` | `rate` | Allotment là số phòng của riêng từng nguồn/giá. Mỗi nguồn có trần riêng (đã gặp 10 và 37) |
| `dropdown_max` | None | Mytour không có dropdown số phòng |
| `currency_mismatch` | Đuôi `formattedPrice` ("1.808.000 VND") | Response không có trường tiền tệ riêng |
| Bị loại | `hiddenPrice` ("Đăng nhập để giảm…", giá phải đăng nhập), `memberOnly`, `fake`, giá ≤ 0, phòng `outOfRoom`, phòng hoặc giá cho ít người hơn `adults` | Sol by Melia có 6 giá ẩn bị loại |
| Trạng thái | Có giá → OK; `completed` mà 0 giá → gọi `hotels/detail`: id có thật thì SOLD_OUT, `4103` thì ERROR `not_found` (id có thật được nhớ trong collector, không gọi lại) | |
| Lịch | Không có API lịch → `CalendarResult(ok=False, error="unsupported")` | |
| Tín hiệu cầu | `lastBookedTime` (ms, giống nhau ở mọi phòng nên là của cả khách sạn) → `DemandSignal(LAST_BOOKED_MINUTES, value=số phút thật, raw_text="Vừa được đặt N giờ trước")` (PARSER_VERSION 2) | Web hiển thị `dayjs(t/5).from(now/5)`, tức là **chia 5 khoảng thời gian** (63 giờ thật hiện thành "13 giờ trước"), và chỉ hiện khi lần đặt cuối trong 5 ngày. `value` lưu thời gian thật; `raw_text` lưu đúng chữ web hiện; quá 5 ngày thì không phát tín hiệu |

### 1.5 Phát hiện quan trọng: hai loại giá
| | `ta:27` (giá đại lý, "Xác nhận trong 15 phút") | `ota:4/32/35/41/44/46` (xác nhận ngay) |
|---|---|---|
| `requestPrice` | true | false |
| `availableAllotment` | 0 (không có tín hiệu tồn phòng) | 1…37 |
| Giá theo ngày | **Không đổi**: Rex luôn 3.781.000 và Melia Vinpearl luôn 3.236.000 ở cả 3 ngày | Đổi theo ngày: Rex 4.104.000 / 4.216.000 / 4.196.000 |
| Thường là giá rẻ nhất | Có | Không |

Hệ quả: nếu lấy "giá thấp nhất" mà gộp cả `ta:*` thì giá Mytour gần như phẳng. Melia Vinpearl trên Mytour **chỉ có** giá `ta:27`, tức là không có tồn phòng và giá không đổi. Adapter vẫn giữ cả hai loại vì cả hai đều là giá khách thấy, và gắn `source_supplier` để phân tích lọc được. Cần quyết định ở tầng phân tích (xem câu hỏi 1).

### 1.6 Kết quả chạy thật bằng adapter (`build_collector("mytour", deps)`, qua proxy VN, giãn cách 2,5 s)
| Khách sạn | 03/10 | 17/10 | 30/10 |
|---|---|---|---|
| Rex Sài Gòn (239) | OK, 19 phòng / 39 giá, badge {1,5,10} | OK, 20 / 47, {1,2,10} | OK, 17 / 43, {1,4,5,10} |
| Melia Vinpearl PQ (40668) | OK, 6 / 36, không badge | OK, 6 / 36 | OK, 6 / 36 |

`suggest("Rex Hotel Saigon")` trả 239 với điểm 1.0. `verify` trả tên, tỉnh và toạ độ. Payload thô khoảng 200–250 KB JSON mỗi probe.

---

## 2. Traveloka

### 2.1 Định danh (đủ cho `urls.py`)
- Khách sạn: `https://www.traveloka.com/<locale>/hotel/<quốc gia>/<slug>-<id>`, với id 10–13 chữ số (VD `.../vietnam/an-lam-retreats-saigon-river-1000000393505`, `...-3000020014046`, `...-9000006991513`).
- Không phải khách sạn: `/hotel/vietnam/region/...-10010231`, `/city/...`, `/area/...`, `/hotel/singapore/cheap-hotels-in-singapore`.

### 2.2 Những gì đã thử
| # | Cách | IP | Kết quả |
|---|---|---|---|
| 1 | curl_cffi `impersonate=chrome`, trang chủ `/vi-vn/hotel` | thẳng | 200 (907 KB) |
| 2 | như trên, trang vùng Phú Quốc | thẳng | **403** DataDome (`rt:'i'` = interstitial kiểm tra thiết bị, cookie `datadome`) |
| 3 | curl_cffi, trang chủ và trang vùng | proxy VN | **403** interstitial ở cả hai |
| 4 | Playwright headless mới (`channel="chromium"`), UA bỏ chữ "Headless", vi-VN | thẳng | Trang chủ 200 và gọi được `/api/v2/hotel/searchForm/complementaryDisplay` (200). Trang vùng **403**, rồi trang "Truy cập tạm thời bị hạn chế … (IP 101.99.23.225)" |
| 5 | như 4 | proxy | interstitial, **trượt**, bị chặn ngay trang chủ |
| 6 | Chromium **có giao diện** | proxy | trượt, bị chặn |
| 7 | **Chrome thật** có giao diện, `--disable-blink-features=AutomationControlled`, bỏ `--enable-automation` | proxy | trượt, bị chặn |
| 8 | như 7 | thẳng (vài phút sau bước 4) | **trang chủ cũng bị chặn**: IP đã bị DataDome nâng mức |

### 2.3 Chẩn đoán
- **Bị chặn theo IP/uy tín, và chặn leo thang theo hành vi.** Trình duyệt gần như thật (Chrome có giao diện) vẫn bị chặn qua proxy. IP thẳng ban đầu qua được trang chủ, nhưng sau vài lần chạm trang được bảo vệ thì bị khoá cả trang chủ. Trang vùng, trang khách sạn và API hotel được bảo vệ chặt hơn trang chủ.
- Ngoài DataDome còn có **AWS WAF token** (`aws-waf-token`, `mp_verify`) và header chống giả mạo `t-a-v`, `x-did`, `tv-mcc-id`, `www-app-version` trên mọi `/api/v2/*`. Kể cả qua được DataDome, phải lấy token bằng trình duyệt rồi dùng lại (bootstrap + http). Đây là mức khó nhất trong các kênh đã thử.
- API giá có dạng `www.traveloka.com/api/v2/hotel/...` (trang chủ gọi `searchForm/complementaryDisplay`, `experiment/getBulk`). Endpoint giá theo phòng **chưa xác định** vì không mở được trang khách sạn.

### 2.4 Cần gì để mở khoá
1. Proxy **dân cư/di động VN uy tín cao**, phiên bám dính (sticky) lâu, tốc độ rất thấp (ví dụ 1 trang/phút/IP). Proxy hiện tại đã bị DataDome đánh dấu.
2. Trình duyệt chống phát hiện (Camoufox / Patchright, hoặc Chrome thật có giao diện chạy trên Xvfb trong Docker), làm nóng phiên trên trang chủ trước, rồi gọi `/api/v2/hotel/*` bằng `fetch` trong trang thay vì mở trang.
3. Hoặc hướng chính thức: Traveloka không có API giá công khai cho bên thứ ba. Có thể dùng nhà cung cấp dữ liệu giá đã có Traveloka (OTA Insight/Lighthouse, RateGain), hoặc hợp tác.
4. Ước lượng: spike riêng 2–3 ngày, rủi ro cao, kết quả không chắc.

---

## 3. Expedia (kiểm tra nhanh)

| # | Cách | Kết quả |
|---|---|---|
| 1 | curl_cffi `expedia.com.vn` trang chủ, IP thẳng | 200; có cookie Akamai `_abck`, `bm_sz`, `bm_s`, `ak_bmsc` |
| 2 | như trên, qua proxy | **429**, trang "Phần mềm tự động?" (bot-or-not) |
| 3 | `GET /api/v4/typeahead/Rex Hotel Saigon?...siteid=300000041`, IP thẳng | 200; `hotelId 481670`, toạ độ, địa chỉ (gợi ý D8 dùng được) |
| 4 | Trang `...Rex-Hotel-Saigon.h481670.Hotel-Information?chkin&chkout&rm1=a2`, IP thẳng | 200 (1,4 MB), **không có giá trong HTML** |
| 5 | Playwright headless mới, IP thẳng | GraphQL `RoomsAndRatesPropertyOffersQuery` (persisted query) **200, 262 KB**: VND, "bao gồm thuế & phí". Sau khoảng 20 lệnh GraphQL, các lệnh tiếp theo bị **429 "Provisioned request rate has been exceeded"** |
| 6 | Gọi lại lệnh offers bằng curl_cffi với cookie từ trình duyệt, đổi ngày | **429** như trên |
| 7 | Playwright qua proxy | HTML 200 nhưng quá 60 s chưa tải xong, chưa thấy lệnh offers |

**Kết luận**: chỉ làm được bằng trình duyệt, từ IP sạch, rất ít probe mỗi phiên. Giới hạn GraphQL theo client chạm rất nhanh, và mã hash persisted query đổi theo mỗi lần deploy. Thị phần VN nhỏ nên **không làm lúc này**.
Để mở khoá: (a) Expedia **Rapid API** (chương trình đối tác chính thức, có giá và tồn phòng), (b) chiến lược `browser` với 1 lệnh offers mỗi phiên + proxy uy tín, (c) mua dữ liệu từ nhà cung cấp rate-shopping.

---

## 4. File đã tạo

| File | Nội dung |
|---|---|
| `backend/app/collector/mytour/urls.py` | `parse_url`, `canonical_url` (thuần) |
| `backend/app/collector/mytour/api.py` | `app_hash`, header, body (thuần) |
| `backend/app/collector/mytour/parser.py` | `parse_availability`, `parse_identity`, `parse_suggestions`, `PARSER_VERSION="1"` |
| `backend/app/collector/mytour/collector.py` | `MytourCollector` (probe gọi lặp tới `completed`, chặn → đổi session thử lại 1 lần → BLOCKED, lỗi mạng/5xx thử lại 1 lần, kiểm tra tiền tệ, verify/suggest), `CurlTransport`, `build(deps)` |
| `backend/app/collector/traveloka/urls.py`, `backend/app/collector/expedia/urls.py` | Chỉ nhận diện URL; registry báo "Chưa hỗ trợ quét Traveloka/Expedia." |
| `backend/tests/fixtures/mytour/*.json` | Payload thật đã cắt gọn (bỏ `supplierName` có link Zalo, bỏ khoá Google Maps trong `staticMap`) |
| `backend/tests/unit/test_{mytour_urls,mytour_parser,mytour_collector,traveloka_urls,expedia_urls}.py` | 43 test |

Kiểm tra: `ruff check` + `ruff format` + `mypy` (strict) trên các thư mục và test trên đều sạch. `pytest`: 43 test mới pass, toàn bộ `tests/unit` 380 test pass. Registry: `mytour` tự bật `collectable=True`, `traveloka`/`expedia` là `False`.

Adapter Mytour dùng `SessionManager` với bootstrapper không cần trình duyệt (session = 1 IP proxy + `deviceId`), nên vẫn có xoay session, thu hồi khi bị chặn và listener như Booking. Trước mỗi request đều gọi `budget.acquire()` và `limiter.wait(session.id)`. `appHash` tính từ `deps.clock`.

---

## 5. Câu hỏi chưa giải quyết
1. ~~Giá đại lý `ta:*` của Mytour~~ **Đã chốt (team lead, 01/10):** giữ cả `ta:*` lẫn `ota:*` kèm `source_supplier`. Đều là giá công khai đặt được trên Mytour; giá đại lý chính là chỗ lộ giá parity cần hiện ra. Phân tích dùng mọi giá.
2. ~~Mã giảm giá công khai~~ **Đã chốt:** giữ `price` là giá trước mã phải tự nhập (theo D3, không phải KM tự áp); mã nằm ở `promo_label`.
3. ~~`DemandKind` cho `lastBookedTime`~~ **Đã làm:** `LAST_BOOKED_MINUTES` (xem bảng 1.4).
4. Allotment mỗi nguồn có trần riêng (10, 37…): tầng tồn phòng có cần cờ `capped` theo nguồn không, hay chấp nhận cận dưới?
5. Traveloka và Expedia: muốn đầu tư proxy dân cư cao cấp + trình duyệt chống phát hiện, đi hướng đối tác hoặc mua dữ liệu, hay tạm bỏ?
6. Proxy hiện tại đã bị DataDome (Traveloka) và Akamai (Expedia) đánh dấu. Có thể chính các kênh khác (Agoda, Trip.com) cũng sẽ gặp khi tăng tải; nên theo dõi tỉ lệ chặn theo kênh.
