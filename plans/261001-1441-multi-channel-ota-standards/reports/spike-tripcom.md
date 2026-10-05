# Spike + adapter Trip.com

Ngày: 2026-10-01. Code: `backend/app/collector/tripcom/` (`urls.py`, `parser.py`, `browser.py`, `collector.py`; `PARSER_VERSION="tripcom-2"`, `DROPDOWN_CAP=10`), fixture `backend/tests/fixtures/tripcom/` (JSON/HTML thật đã rút gọn, không cookie/token/trace id), test `backend/tests/unit/test_tripcom_{urls,parser,collector}.py` (56 test, pass; ruff + mypy sạch). Proxy VN (`PROXY_URL_TEMPLATE`, IP xoay), không đăng nhập, POS `vn.trip.com`, `curr=VND`, locale vi-VN.

Lưu lượng tới Trip.com trong cả spike: khoảng 13 request curl lẻ + 27 lần mở trang bằng Playwright khi dò API + smoke (6 lần mở trang, 2 verify, 2 suggest). Mỗi lần mở trang, JS của trang tự gọi thêm khoảng 30–40 XHR tới trip.com (config, UBT, gợi ý…), nên tính theo XHR là khoảng 1.000 request. Con số này vượt mức ~150 nếu đếm từng XHR. Giãn cách luôn ≥ 2,5 s giữa các lần mở trang, không đăng nhập.

## 1. Kết luận
- **Bảng phòng cần trình duyệt.** API `getHotelRoomListOversea` đòi header `phantom-token` do JS chống bot (hàm `window.signature`, mã đã làm rối) sinh **riêng cho từng request**. Gọi bằng curl, gọi `fetch` trong trang, hay dùng lại token đã bắt (cùng body, cùng cookie) đều nhận `{"data":{"htlSpiderActionErrorCode":4030}}`. Không dịch ngược token (dễ vỡ, và là né chống bot sâu hơn mức "trình duyệt như người dùng").
- **Chiến lược `browser` có giữ session:** một Chromium sống cho mỗi session proxy (20 phút / 400 lượt, quản lý bằng `SessionManager` có sẵn nên listener DB/metrics dùng lại được). Mỗi probe mở trang chi tiết với ngày cần quét và bắt response API của chính trang. `ProbeMethod.BROWSER`.
- **verify + suggest không cần trình duyệt:** trang chi tiết SSR (Next.js RSC) qua curl_cffi có đủ tên, sao, địa chỉ, toạ độ. API gợi ý `getHotelKeywords` gọi bằng curl_cffi được, không cần cookie hay chữ ký.
- **Dữ liệu tốt hơn mong đợi:** giá gồm thuế phí (tổng kỳ ở), giá gạch, tên KM, hoàn huỷ, bữa ăn, số khách, và **số phòng còn chính xác cho từng mức giá** (`remainRoomQuantity`, chính là con số "Chỉ còn N phòng có giá này"), kể cả khi trang không hiện nhãn.
- **Smoke thật: 6/6 probe ok (100%)**, trung vị 21,7 s, max 44,6 s. verify + suggest đúng cho Melia và Caravelle.
- **Điểm yếu là chi phí mỗi probe:** 1,1–2,4 MB qua proxy và 30–40 XHR mỗi lần. Thời gian 4–13 s khi proxy rảnh, 33–58 s khi proxy đang tải (các agent khác chạy song song). Không thấy captcha/slider/403.

## 2. Endpoint
| Việc | Endpoint | Cách gọi |
|---|---|---|
| Bảng phòng (probe) | `POST https://vn.trip.com/restapi/soa2/33269/getHotelRoomListOversea` | Do trang `https://vn.trip.com/hotels/detail/?hotelId=<id>&checkIn=YYYY-MM-DD&checkOut=…&adult=2&crn=1&children=0&curr=VND` tự gọi (kèm `phantom-token`). Body: `search.{hotelId, checkIn:"YYYYMMDD", checkOut, adult, roomQuantity:1}` + `head.{locale:"vi-VN", currency:"VND", region:"VN"}` |
| Định danh (verify) | `GET https://vn.trip.com/hotels/detail/?hotelId=<id>` (SSR) | curl_cffi. Dữ liệu trong `self.__next_f.push([1,"…"])` → `hotelDetailResponse.{hotelBaseInfo, hotelPositionInfo}` |
| Gợi ý (suggest) | `POST https://vn.trip.com/restapi/soa2/34951/getHotelKeywords` body `{"queryInfo":{"keyword":…,"actionType":"destination"},"head":{…}}` | curl_cffi, không cookie. Trang thật gửi kèm `w-payload-source` (chữ ký) nhưng server không bắt buộc |
| Danh sách theo thành phố (list mode, chưa dùng) | `GET https://vn.trip.com/hotels/list?city=<cityId>&checkin=…&checkout=…&adult=2&crn=1&curr=VND` (SSR) | Xem §7 |
| Không có | Lịch min-LOS | `fetch_calendar` trả `CalendarResult(ok=False, error="unsupported")` |

Id: `hotelId` (= `masterHotelId`). Melia Vinpearl Phú Quốc = **7047736** (cityId 5649 "Đảo Phú Quốc"), Caravelle Saigon = **839839**, Rex = **758751**. URL nhận dạng: `/hotels/detail/?hotelId=`, `/hotels/v2/detail/`, link chia sẻ `/hotels/w/detail/?hotelid=`, URL SEO `/hotels/<city>-hotel-detail-<id>/<slug>/`, mọi subdomain `*.trip.com`. Link rút gọn `trip.com/w/<code>` bị từ chối (cần link đầy đủ).

## 3. Chống bot quan sát được
| Cách truy cập | Kết quả |
|---|---|
| curl_cffi (impersonate chrome): trang chủ, trang chi tiết SSR, trang danh sách SSR, `getHotelKeywords` | 200, có dữ liệu |
| curl_cffi gọi `getHotelRoomListOversea` (không token, hoặc token dùng lại kèm cookie của trình duyệt) | 200 nhưng body `htlSpiderActionErrorCode: 4030` |
| Playwright mặc định (headless shell, chỉ đổi UA) | API trả 4030, trang chuyển sang `/account/signin?backurl=…`. Lộ ra vì `sec-ch-ua` vẫn ghi "HeadlessChrome" v153 trong khi UA ghi Chrome/140 |
| Chromium đầy đủ (`channel="chromium"`, headless mới) + `--disable-blink-features=AutomationControlled` + UA và client hints khớp nhau qua CDP `Network.setUserAgentOverride` + ẩn `navigator.webdriver` | **OK ở mọi lần thử** (~20 lần mở trang chi tiết, 6 khách sạn, cả trang danh sách) |
| `fetch`/XHR tự gọi từ trong trang | 4030 (thư viện request của trang mới gắn token) |
| Id khách sạn không tồn tại | Chuyển về trang chủ `/?locale=vi-vn` → `error="not_found"` |

Lưu ý vận hành:
- **Không dùng `page.route()`** để chặn ảnh: route tắt HTTP cache của Chromium, khiến mỗi probe tải lại toàn bộ JS (3–5 MB). Thay bằng `--blink-settings=imagesEnabled=false`, giữ cache trong context, còn 1,1–1,7 MB/probe từ lần thứ hai.
- Docker đã `playwright install --with-deps chromium` (có cả Chromium đầy đủ) nên `channel="chromium"` chạy được.
- Chụp màn hình bị treo khi font không tải; adapter không chụp.

## 4. Ánh xạ về chuẩn
| Trường chuẩn | Nguồn Trip.com | Ghi chú |
|---|---|---|
| `RatePlan.price` | `comparingAmount / nights` | `comparingAmount` = tổng (1 phòng × N đêm) **đã gồm thuế phí** ("Tổng giá … bao gồm thuế & phí"). Đã kiểm 2 đêm: 9.240.000 / 2 = 4.620.000. Trang hiện to giá **chưa thuế** `priceInfo.price` (VD Melia 4.074.074 so với 4.620.000 gồm VAT 8% + phí dịch vụ 5%) |
| `taxes_included` | `True` khi có `comparingAmount`; `False` nếu phải lấy `priceInfo.price` | Thanh toán tại khách sạn cũng có `comparingAmount` gồm thuế |
| `price_original` | `priceInfo.deletePricewithOutCurrency` (giá gạch, **chưa thuế**) × (giá gồm thuế / giá chưa thuế) | `deletePrice − price` = tổng `promotionTagList[].amount`. Thuế VN tính theo %, nên quy đổi tỉ lệ là chính xác (làm tròn 1 ₫) |
| `promo_label` | Tên gói khách sạn nếu có; không thì `totalPriceInfo.promotionTagList[]` có `amount > 0` → `title` ("Ưu đãi đặt phòng sớm", "Ưu Đãi Giới Hạn Thời Gian", "Giảm Giá Đặc Biệt") | Wyndham gắn nhãn "Ưu Đãi Giới Hạn Thời Gian" với số tiền **0 ₫**, nên không tính là KM |
| `refundable` | `totalPriceInfo.isFreeCancel`; dự phòng `cancelInfo.type` (5 = không hoàn; 1/2/3 = huỷ miễn phí) | |
| `breakfast` | `mealInfo.mealFlag==0` → False; `mealType` 4 (sáng), 5 (sáng + tối), 7 (ba bữa) → True | `mealType 0` = "bữa sáng X ₫ (không bắt buộc)" |
| `max_persons` | `guestCountInfo.guestCount` | Trip.com trả giá theo số khách (1–6 khách, giá khác nhau). Bỏ mức < `adults`. Mức 1 khách nằm ở `compensatedRooms`, không có trong `roomList` |
| Gói / combo (quyết định của lead) | **"Gói Khách Sạn"** (`xProOption.pkType=2`: phòng + quyền lợi của chính khách sạn như lounge, spa, bữa ăn) **được tính**, `promo_label="Gói khách sạn: <tên thành phần>"` (VD "Gói khách sạn: Đặc quyền Signature Lounge (Mỗi ngày 2)"). **Loại** combo: `pkType` khác 0/2, hoặc thành phần có vé máy bay/chuyến bay/đưa đón/transfer/shuttle/tour | Caravelle: 5 loại phòng chỉ bán theo gói (Signature…) nay đều có giá. Đọc lại bản lưu 15/10: 11/11 loại phòng có giá, 17 mức. Chỉ mới gặp `pkType=2` |
| Lọc khác | chỉ lấy mức trong `roomList` (đang hiển thị) và đặt được (`isBooking`, không `isFullRoom`) | |
| `RoomOffer.external_room_id` / `name` | `roomList[].key` = `physicalRoomId` / `physicRoomMap[id].name` | |
| `max_occupancy` | max `guestCount` của các mức hiển thị | |
| `badge_count` | **max** `bookingStatusInfo.remainRoomQuantity` của các mức đặt được trong loại phòng (bỏ 9999 = không giới hạn) | Số này **có sẵn trong API cho mọi mức giá**, không chỉ khi trang hiện nhãn. Đã đối chiếu: Mường Thanh Luxury PQ, mức 1.166.667 ₫ còn 3 ↔ thẻ trang danh sách "Chỉ còn 3 phòng có giá này" (cùng giá gạch 3.906.667). Lấy **max** vì là cận dưới chặt nhất cho loại phòng. Tính trên mọi mức đặt được, kể cả gói (cùng phòng vật lý) |
| `dropdown_max` | max `ruleInfo.maxQuantity` (ô chọn số phòng, **trần 10**) | Caravelle: còn 17/29 nhưng ô chọn dừng ở 10 → `DROPDOWN_CAP=10` |
| `stock_scope` | `"rate"` | `derive_stock` → CAPPED, `rooms_left` = số còn của mức giá lớn nhất |
| `ProbeStatus` | `htlSpiderActionErrorCode` hoặc trang chuyển sang `/account/signin` → BLOCKED (thu hồi session, thử lại 1 lần); `roomList` rỗng + `isRoomListSoldOut` → SOLD_OUT; rỗng mà không có cờ → NO_ROOMS_1N; có loại phòng nhưng không mức nào đặt được → SOLD_OUT; tiền tệ ≠ VND → ERROR `currency_mismatch:<cur>`; `searchBoxInfo` khác ngày/số khách đã hỏi → ERROR; về trang chủ → ERROR `not_found`; không bắt được API trong 90 s → ERROR `timeout` | |
| `raw_html` | `{"tripcom":1,"page":{hotelId,name,lastBooking},"roomList":<JSON API nguyên văn>}` | Đọc lại bằng `parser.parse_probe_payload()`. JSON API khoảng 170–470 KB |
| Giá thành viên | Mỗi mức có `toLoginButton: "Xem Giá Thấp Hơn"`: đăng nhập thì rẻ hơn. Cũng có coupon người dùng mới ("Giảm đến 140.000 ₫", áp ở bước thanh toán) | Adapter lấy **giá khách chưa đăng nhập thấy**, không tính coupon ở bước thanh toán. Chưa thấy giá chỉ có trên app |

## 5. Tín hiệu cầu
- Trang chi tiết (SSR `hotelBaseInfo.lastBooking`, cũng hiện trên trang): **"Lần đặt gần nhất cách đây 18 phút"**. Trang danh sách có thẻ "Được đặt lần gần nhất 15 giờ trước". `DemandKind` chưa có loại này.
- **Đã phát:** `DemandSignal(kind=LAST_BOOKED_MINUTES, value=<số phút>, window_hours=None, stay_date=None, raw_text=<nhãn>)`. `last_booked_minutes()` đổi phút/giờ/ngày ra phút. Mỗi probe ok có 1 signal (trang chi tiết luôn có nhãn này trong smoke). Chuỗi gốc cũng nằm trong raw payload (`page.lastBooking`) để đọc lại.
- Bảng phòng không có "đặt N lần hôm nay" hay điểm độ hot. Nhãn `inspireInfo` ("Giá tốt nhất với 2 bữa sáng") là nhãn giá, không phải tín hiệu cầu.

## 6. Smoke thật (`scratchpad/tripcom/smoke.py`, `build_collector("tripcom", deps)`, `StaticProxyProvider(PROXY_URL_TEMPLATE)`, `RateLimiter(2,1)`, headless, session 20 phút/400)
| Việc | Kết quả |
|---|---|
| verify Melia (curl SSR) | id 7047736, "Meliá Vinpearl Phu Quoc", 5★, Đảo Phú Quốc, vn, (10.357969, 103.849616), "Bãi Dài, Đảo Phú Quốc, An Giang", 1,3 s |
| verify Caravelle | id 839839, "Caravelle Saigon", 5★, TP. Hồ Chí Minh, (10.776262, 106.703613), "19 - 23 Công trường Lam Sơn, Q.1…", 2,9 s |
| suggest Melia / Caravelle | đúng khách sạn ở kết quả đầu, score 1.0 (tên + toạ độ ≤150 m), 1,7 s / 2,4 s, 1 request mỗi khách sạn |
| probe Melia 08/10, 17/10, 24/10 | **ok ×3**, 21,0 / 20,1 / 19,1 s. 5 loại phòng, 41–72 mức. Rẻ nhất 4.620.000 ₫ gồm thuế (không hoàn, có bữa sáng, 2 khách). Villa còn 1–2, villa 1 PN còn 9 |
| probe Caravelle 08/10, 17/10, 24/10 | **ok ×3**, 22,3 / 36,1 / 44,6 s. 11 loại phòng, 12 mức (bản `tripcom-1`, lúc đó chưa tính gói). Rẻ nhất 6.035.169 → 5.303.809 → 5.299.173 ₫ (huỷ miễn phí, không bữa sáng). Số còn theo mức 3–63, ô chọn dừng ở 10. 2 loại phòng chỉ bán gói → `rates=()` |
| Tổng | **6/6 ok (100%)**, trung bình 27,2 s, trung vị 21,7 s, max 44,6 s/probe (không tính ~3 s khởi động Chromium lần đầu). Raw payload 330–773 KB. Tín hiệu "lần đặt gần nhất" bắt được ở cả 6 probe ("47 phút", "1 giờ"). Smoke chạy với `tripcom-1`, trước khi có kind (§5) và trước khi tính gói khách sạn, nên lúc đó `demand_signals=()` và Caravelle có 2 loại phòng `rates=()`. Hai điểm này đã kiểm lại offline bằng unit test và bằng cách đọc lại bản lưu |

Trước smoke, ~20 lần mở trang chi tiết khi dò (6 khách sạn) cũng đều lấy được bảng phòng sau khi bật cấu hình headless ở §3. Thời gian 4–13 s khi proxy rảnh, 33–58 s khi proxy tải nặng.

## 7. List mode (D6, chưa làm)
Trang danh sách (`/hotels/list?city=5649…`), khi mở bằng trình duyệt, có cho mỗi khách sạn mức giá rẻ nhất: `priceInfo.price` (chưa thuế), `deletePrice`, "Tổng giá … bao gồm thuế & phí", `roomTags.promotionTags`, **`encourageTags` "Chỉ còn N phòng có giá này"** (tagId 12213) và "Được đặt lần gần nhất N giờ trước". Mỗi trang 10 khách sạn, cuộn để tải thêm. **Gọi bằng curl_cffi thì HTML (357 KB) không có `hotelList`** (danh sách tải phía client), nên list mode cũng cần trình duyệt. Để phase 7.

## 8. Hạn chế
- Mỗi probe là một lần tải trang đầy đủ: 30–40 XHR tới trip.com, 1,1–2,4 MB qua proxy, 4–58 s. Với D12 (≈101 probe/listing/ngày) thì khoảng 150–240 MB/listing/ngày qua proxy dân cư. **Lead đã chấp nhận** (ngân sách không phải giới hạn).
- **Việc tiếp theo** (nếu bị chặn nhiều hoặc run trễ hạn): đổi ngày ngay trong trang (SPA) thay vì tải lại, để trang chỉ gọi lại API bảng phòng (bớt request và thời gian). Thêm: list mode (§7), chặn XHR không cần (bình luận, khách sạn lân cận, quảng cáo) bằng CDP `Network.setBlockedURLs` (giữ được cache).
- Phụ thuộc vào việc headless không bị nhận ra. Nếu Trip.com siết thêm (đổi `phantom-token`/kiểm fingerprint), probe sẽ BLOCKED hàng loạt. Cần canary.
- Nhận diện combo dựa vào `pkType` và từ khoá trong tên thành phần gói. Mới chỉ gặp `pkType=2`, nên các loại gói khác bị loại cho chắc.
- `remainRoomQuantity` là tồn phòng **theo nguồn/hợp đồng của mức giá** trên Trip.com, không phải tồn phòng của cả khách sạn. Các mức cùng loại phòng thường cùng số (Melia 9/9/9…, Caravelle 17/17).
- `ProbeMethod.BROWSER` dù dữ liệu là JSON API (contract chưa có kiểu "browser + API").
- Không có lịch min-LOS. Nếu khách sạn đòi ở tối thiểu 2 đêm, chưa rõ API trả gì (chưa gặp) → sẽ rơi vào NO_ROOMS_1N.

## 9. Contract change requests
1. ~~Thêm `DemandKind.LAST_BOOKED_MINUTES`~~: **đã có**, adapter đã phát signal.
2. (Tuỳ chọn) `RatePlan.member_price_hidden: bool`: Trip.com (và có thể Agoda) báo "đăng nhập để xem giá thấp hơn". Giúp giải thích chênh lệch giá khi so kênh.
3. (Tuỳ chọn) `reparse` trong `app/cli.py` hiện chỉ cho Booking: cần tra parser theo kênh (Trip.com: `app.collector.tripcom.parser.parse_probe_payload`).
4. (Tuỳ chọn, D6) `probe_list(area, checkin, spec, wanted_ids)` trong Collector protocol: trang danh sách Trip.com cho giá + "Chỉ còn N" của 10+ khách sạn mỗi request.

## 10. Câu hỏi chưa giải quyết
Quyết định của lead (01/10): gói khách sạn **tính** và gắn nhãn gói, combo vé máy bay/đưa đón/tour **loại**. Tồn phòng **giữ nguyên** (max theo mức, scope "rate" → lưu dạng cận dưới, bỏ 9999, không ngưỡng). Chi phí mỗi probe **chấp nhận**.
1. Trang danh sách hiện nhãn "Chỉ còn N" từ ngưỡng nào? Mới thấy N ≤ 3 (thấy 1, 2, 3). Chỉ cần biết nếu làm list mode.
2. API trả gì khi khách sạn đòi ở tối thiểu 2 đêm mà hỏi 1 đêm? Chưa gặp. Hiện sẽ ra NO_ROOMS_1N.
