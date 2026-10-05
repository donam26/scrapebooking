# Spike ivivu.com: API giá, token X-ivv-key, adapter

Ngày 01/10/2026 · proxy VN xoay IP · khách sạn mẫu: Melia Vinpearl Phú Quốc (hotelId 377594), Vintage Saigon Hotel & Spa (962567), Rex Sài Gòn (12148, chỉ suggest).

**Kết luận:** API giá chạy được **headless**. Live: 12/12 probe OK (2 lượt chạy), token không bị từ chối lần nào. Có `source_supplier` cho từng giá. Adapter nằm ở `backend/app/collector/ivivu/`, 36 unit test pass, ruff + mypy sạch.

---

## 1. Endpoint

| Mục đích | Request | Token? |
|---|---|---|
| Cờ chống bot | `GET apiportal.ivivu.com/web_prot/config/FlagSetting?clientType=hotel` → `{"flagOn":2}` | không |
| Giá phòng | `POST …/web_prot/pay/api/contracting/HotelSearchReqContractAppV2` (payload y như web, xem `api.price_request`) | **có**, header `X-ivv-key` |
| Lấy token | `POST …/gatewaycrm/get-session/challenge` rồi `POST …/gatewaycrm/get-session/<site key mã hoá>` | không |
| Định danh (verify) | `GET www.ivivu.com/<khach-san-vung>/<slug>`: HTML SSR, `<script id="ng-state">` chứa `GetHotelDetailV3` | không |
| Gợi ý listing | `GET …/web_prot/gate/search/searchhotel?keyword=…` (id, slug, toạ độ, sao, `bookingInMonth`, `countryCode`) | không |
| Tín hiệu cầu 24h | `GET …/web_prot/gate/mobile/OliviaApis/TopSale24hByHotel?hotelId=…` → `{"list":[…],"total":2}` | không |
| Combo (bỏ) | `POST …/ms01/api/HotelDetail/GetComboDetailListV2` | không |

`HotelSuggestDaily` trả `daily` / `notSuggestDaily` (danh sách ngày). Đây không phải lịch min-stay, nên `fetch_calendar` trả `unsupported`.

## 2. Token `X-ivv-key`: cách hoạt động

- `FlagSetting.flagOn`: 0 = Off, 1 = Cloudflare Turnstile (header `cf-turnstile-response`), **2 = BotDetection, là chế độ hiện tại**. Tên header lấy từ bundle web: `botDetection:"X-ivv-key"`.
- ivivu tự viết một widget giống Turnstile: `res.ivivu.com/js/ivv-btw-ob.js?v=7`. Widget nạp thêm `ivv-fgp-ob.js` (một thư viện kiểu BotD). Site key `NgwAEb2WMZ4e9DF7zGu3ChqLH6`. Tôi đã gỡ mã rối để đọc luồng xử lý:
  1. `POST challenge {"m": Date.now()}` trả `"<ts1>..<ts2>..<ES module>"`. Module JS sinh mới và làm rối khác nhau mỗi lần, nhưng thực chất chỉ chèn ký tự vào `location.href`.
  2. Widget dựng dấu vân tay JSON: `u`=UA, `w`=`navigator.webdriver || BotD.bot`, `s`=`WxH`, `v`=`1.0.3`, `t<ddhhmm>`=ts2, `l<rand>`=href đã biến đổi, cộng 14–15 khoá nhiễu ngẫu nhiên. Chuỗi được mã hoá hex với mỗi byte cộng `12 + ngày UTC`. Sau đó `POST get-session/<id> {"m": …}` trả `{"s": "<token base64>"}`.
- **Token dùng một lần**: một token chưa dùng gọi được đúng 1 lần bằng curl_cffi, từ IP khác, khoảng 4 phút sau khi cấp; gọi lại lần hai thì 403. Token **không gắn với IP, TLS hay cookie**.
- Lý do bị 403 `Invalid_token_ivv` trước đây: headless kiểu cũ gửi UA `HeadlessChrome` và `webdriver=true`, nên server cấp token nhưng API giá từ chối. Cách sửa: `chromium.launch(channel="chromium")` (headless mới), thêm `--disable-blink-features=AutomationControlled`, và UA bỏ chữ "Headless" (dùng `browser_user_agent` của Booking).
- **Cách adapter lấy token** (`token_minter.py`): mỗi session mở một trang ivivu và giữ nó mở. Adapter tạo một `.ivv-s-widget` riêng, gọi `initWidgets()` lần đầu và `refreshWidget(id)` các lần sau, rồi nhận token qua callback. Mỗi token tốn 2 request nhỏ, mất 0,4–2 s. Request giá (nặng) đi bằng curl_cffi, cùng UA và proxy với trình duyệt.
  - Trang được chặn bớt bằng route allowlist: chỉ cho tải HTML, JS/CSS của `res.ivivu.com`, `FlagSetting` và `gatewaycrm`. Bị chặn: ảnh, font, analytics, và mọi API khác của trang, kể cả lần trang tự gọi giá (3 MB). Mở trang mất khoảng 8 s (goto 3 s, chờ widget 3 s).
  - Gặp `Invalid_token_ivv` hoặc 403/429/503: bỏ session (đóng trình duyệt, lấy proxy mới), thử lại 1 lần, rồi trả **BLOCKED** (`invalid_token` / `http N`). Mint thất bại: thử lại tương tự, rồi trả BLOCKED `token_unavailable`. `flagOn=1` (Turnstile): BLOCKED `bootstrap: TokenUnavailable … (flagOn=1)`. `flagOn=0`: gọi không cần header.
  - Không làm bộ giải challenge thuần Python. Làm được, nhưng phải giả mạo dấu vân tay, dễ vỡ khi họ đổi và nằm ở vùng xám hơn. Adapter chạy đúng JS của ivivu trong trình duyệt thật.
- Ngày ở trang web: `?ci/co` bị bỏ qua. Ngày lấy từ cookie `dateRangeBooked=["2026-10-12","2026-10-13"]`, số khách từ cookie `roomPicker`. Adapter gọi API trực tiếp nên không dùng đến.

## 3. Ánh xạ trường (`parser.py`)

`Hotels[0].RoomClasses[]` → `RoomOffer`; `RoomClasses[].MealTypeRates[]` → `RatePlan`. Web hiện mỗi gói ăn một giá, phần còn lại nằm sau "Xem thêm N lựa chọn khác". Khách vẫn thấy và đặt được các giá này, nên **giữ tất cả** (Melia: 280–466 giá, 19–29 hạng phòng mỗi đêm).

| Trường | Nguồn | Đã kiểm? |
|---|---|---|
| `price` | `PriceAvgPlusTA` (đã đối chiếu web: "Giá 1 đêm / 1 villa **3.120.500**"); làm tròn VND | ✔ trên trang |
| `taxes_included` | `ExcludeVAT == 0` ở cấp khách sạn và hạng phòng. Web ghi "Đã bao gồm thuế & phí"; giá Agoda ghi "Giá đã bao gồm: Sales tax …, Service charge …" | ✔ Melia |
| `price_original` | `price + PriceDiscount` khi > 0 (giá hợp đồng ivivu "Ưu Đãi Giới Hạn") | ✘ chưa thấy giá gạch trên trang |
| `promo_label` | `PromotionNote` (VD "Ưu Đãi Mùa Hè…", Agoda: "Giá phòng đã có giảm giá 40%!") | ✔ |
| `refundable` | `Penaltys[0].IsPenaltyFree` ("Sau 12:00 PM ngày … sẽ bị tính phí" = True; "Không hoàn huỷ" hoặc "Bây giờ đến …" = False) | ✔ |
| `breakfast` | `Code`: RO = False; BB/HB/FB/FI/AI = True | ✔ |
| `max_persons` | `Adults` (0 = nguồn không ghi, thường là Agoda → None) | ✔ |
| **`source_supplier`** | `Supplier` từng giá: `B2B` (giá sỉ đối tác qua IVIVU), `AGD`→`AGODA`, `Internal`→`IVIVU`, `MGB`, `HBED`. Chưa thấy VINHMS/HLS/SMD/EXTRANET ở 2 khách sạn đã thử | ✔ |
| `external_room_id` | `ClassID` dương (hạng phòng của ivivu, ổn định). **ClassID âm** là phòng nguồn ngoài chưa ghép và bị đánh số lại mỗi lần gọi, nên dùng `name:<slug tên>` | ✔ (so 2 response) |
| `max_occupancy` | `Rooms[0].MaxAdults` | ✔ |
| `badge_count` / `dropdown_max` | None: web không hiện "còn N phòng", không có dropdown | ✔ |

Lọc bỏ: `IsPackageRate`, `IsComboFlight`, `Isshowprices == 0`, `0 < Adults < adults`. Giá villa ghi `Adults=4` vẫn giữ (giá theo căn, áp được cho 2 khách). Combo vé máy bay nằm ở endpoint riêng, không lấy.

Trạng thái probe:
- OK: có ít nhất 1 giá hợp lệ.
- SOLD_OUT: `Hotels` rỗng, hoặc không còn giá nào sau khi lọc.
- ERROR `currency_mismatch:<cur>`: `CurrencyCode` khác VND.
- ERROR `not_found`: trang khách sạn 404 hoặc không có ng-state.
- BLOCKED: như ở §2.
- `method=API`.
- `raw_html` = **payload đã cắt gọn** (xem §6).

## 4. Tín hiệu cầu

- `ROOMS_SOLD_24H` = `TopSale24hByHotel.total`, window 24h. Web hiện "Đã bán 2 phòng trong 24 giờ qua" khi giá trị > 0; adapter lưu cả giá trị 0.
- `BOOKINGS_MONTH` = `searchhotel[].bookingInMonth` (Melia 17), lấy theo đúng hotelId. Vintage Saigon không trả trường này trong lần chạy smoke.
- Đây là tín hiệu cả khách sạn (`stay_date=None`). Mỗi khách sạn gọi 2 request, cache 30 phút, gắn vào mọi probe (repo đã khử trùng theo run).

## 5. Verify / suggest

- `verify`: một lần GET trang khách sạn (không cần token). Từ ng-state lấy: id, tên, địa chỉ, city (breadcrumb cuối, VD "Phú Quốc", "Hồ Chí Minh"), countryCode, lat/lng, sao (`rating/10`). 404 hoặc trang không có khách sạn → `ListingNotFound`; non-200 khác → `ListingBlocked`.
- `suggest`: thử lần lượt các biến thể tên `matching.search_names(name)`, cuối cùng là tên riêng không dấu `normalize_name(name)` (ví dụ "rex"). Kết quả các lần được gộp, lọc theo `country_code`, chấm bằng `match_score`, trả top 5. Dừng sớm khi đã có ứng viên ≥ 0,9.
  - Lý do: tên trên ivivu là tiếng Việt, "Rex Hotel Saigon" chỉ ra các khách sạn "Saigon" khác, còn "rex" thì ra Rex Sài Gòn đứng đầu.
  - Live: "Meliá Vinpearl Phu Quoc" → 377594, score 1.0, 1 lần search; "Rex Hotel" → 12148 Rex Sài Gòn, score 1.0, 2 lần search; "Rex Hotel Saigon" → 12148, score 1.0.
- `DROPDOWN_CAP = 99`: ivivu không có ô chọn số phòng.

## 6. Dữ liệu nhạy cảm trong response giá

Payload thô (~2,8 MB với Melia) chứa:
- **email đối tác B2B** (`JsonData.B2BPartnerEmail`) và tên đối tác (`NoteForSupplier`);
- **giá net / giá vốn của ivivu** (`PriceAvgPlusNet`, `TotalPrice`), `SaleNote`;
- token đặt phòng (`HotelCheckDetailToken*`).

`trim_price_payload` chỉ giữ các trường parser cần: còn khoảng 200 KB với Melia, 3–8 KB với khách sạn nhỏ. Parse lại payload đã cắt cho kết quả giống hệt (có test). Fixture không chứa token, cookie hay email (đã kiểm).

## 7. Smoke live (`scratchpad/ivivu/smoke.py`, `build(deps)` đúng như đề bài)

| Lượt | Thao tác | Kết quả | Thời gian |
|---|---|---|---|
| 2 | suggest Melia / verify Melia / verify slug sai | 377594 score 1.0 / đủ trường / `ListingNotFound` | 0,5 s / 3,2 s / ~2 s |
| 2 | probe Melia +3/+10/+24 ngày | OK ×3: 19–27 hạng phòng, 283–459 giá, min 3.120.500, nguồn AGODA/B2B/HBED/IVIVU/MGB | 23,6 s (gồm mở trình duyệt ~8 s + trang + cầu), 16,6 s, 19,2 s |
| 2 | probe Vintage Saigon ×3 | OK ×3: 4 phòng, chỉ có giá Agoda, min 470.000–481.500 | 4,2 s, 1,2 s, 2,2 s |
| 2+ | suggest "Rex Hotel Saigon" (sau khi sửa) | Khách sạn Rex Sài Gòn [12148] score 1.0 | 2,8 s (2 lần search) |
| 1 | probe Melia ×3; "Hotel Rex" ×3 (lượt này suggest cũ ghép nhầm khách sạn ở Ý) | OK ×6 | Melia 111 s (lần mở trình duyệt đầu ~80 s, proxy chậm, không có retry), 12,6 s, 14,1 s; Rex IT 3–5 s |

- Tỉ lệ thành công: **12/12 probe OK**, 0 token bị từ chối, 0 retry.
- Thời gian mỗi lần gọi giá: resort lớn 12–19 s (server mất ~8,6 s: `RequestTime` 3,8 + `BindDataTime` 4,8; payload 2,8 MB); khách sạn nhỏ 1–4 s.
- Mở trình duyệt: ~8 s mỗi session (20 phút / 400 request).

## 8. Giới hạn / rủi ro

- Phải giữ một Chromium mở suốt session (khoảng 300 MB RAM mỗi worker). `max_jobs=1` nên an toàn.
- Docker dùng `playwright install --with-deps chromium`, có bản Chromium đầy đủ nên `channel="chromium"` dùng được. **Chưa chạy thử trong container Linux.**
- Resort lớn tốn ~15 s mỗi đêm. Với D12 (~101 probe/listing/ngày), mỗi resort tốn khoảng 25 phút worker mỗi ngày.
- ivivu có thể bật Turnstile (`flagOn=1`) bất cứ lúc nào. Khi đó adapter trả BLOCKED với lý do rõ ràng, chưa có cách vượt.
- API và widget là nội bộ: tên endpoint có V2/V3, `?v=7` của widget, site key. Cần canary và lưu raw.
- `price_original` chưa đối chiếu được trên trang. Giá Agoda có "giảm 40%" trong `promo_label` nhưng không có giá gốc.
- Trạng thái `AL` (xác nhận ngay) / `RQ` (yêu cầu đặt, xác nhận trong 60') chưa được ánh xạ. `AvailableNo` (allotment của nguồn: Agoda 15/35, HBED 8, MGB luôn 1, RQ là 0) chỉ giữ trong raw, không đưa lên vì web không hiện.
- Pháp lý: vượt challenge riêng là vùng xám hơn Booking. Hiện giữ nguyên tắc: không đăng nhập, không lưu dữ liệu cá nhân, giãn cách 2–3 s. Vẫn nên cân nhắc hợp tác hoặc API chính thức với ivivu.

## 9. Đề xuất thay đổi contract

1. `ListingIdentity.cross_refs: dict[str, str] | None`. `GetHotelDetailV3` có sẵn `agodaCode` (Melia **1985199**, trùng id Agoda trong D8), `hbedcode`, `mgbcode`. Có trường này thì ghép listing chéo kênh chắc chắn, không cần đoán theo tên.
2. `RatePlan.instant_confirm: bool | None` (AL/RQ). Giá "yêu cầu đặt" của B2B/ivivu thường rẻ nhất (VD 3.120.500 RQ so với 3.319.500 Agoda xác nhận ngay).
3. Chuyển `browser_user_agent` / `normalize_user_agent` từ `booking/playwright_bootstrap.py` sang module dùng chung. Hiện ivivu import từ module của Booking.
4. `SessionManager` chưa giữ được trình duyệt sống. ivivu đang tự giữ session (~40 dòng, vẫn gọi `session_listener`). Nên tổng quát hoá nếu Traveloka cũng cần.
5. `ProbeResult.raw_html` nên đổi tên thành `raw_payload` (kênh API lưu JSON).

## 10. Lưu lượng đã dùng

Khoảng 155 request trang/API tới ivivu (www + apiportal), gồm 6 lần mở trang, 18 lần gọi giá, khoảng 26 lần lấy token (52 request), search/verify/cầu. Ngoài ra có JS/CSS tĩnh từ `res.ivivu.com` mỗi lần mở trang. Giãn cách 2–3 s, không đăng nhập.

## File

- `backend/app/collector/ivivu/`: `urls.py`, `api.py`, `parser.py` (`PARSER_VERSION="1"`), `token_minter.py`, `collector.py` (`build`, `PARSER_VERSION`)
- `backend/tests/fixtures/ivivu/`: response giá Melia đã cắt (3 hạng phòng, 122 giá), trang SSR đã cắt, searchhotel, TopSale24h, body 403 invalid token
- `backend/tests/unit/test_ivivu_{urls,parser,collector}.py`: 36 test

## Quyết định (team lead, 01/10/2026)

1. **Giữ giá RQ** (yêu cầu đặt): đây là giá công khai, khách đặt được trên ivivu. Cách làm giống Mytour, nơi đang giữ giá đại lý.
2. **Giá B2B/MGB/HBED/AGODA tính là giá ivivu khi so parity.** Đây chính là chỗ lộ giá mà khách sạn cần thấy. `source_supplier` vẫn ghi trên từng giá.
3. Các đề xuất contract ở §9 (`cross_refs`, `instant_confirm`, helper UA dùng chung, SessionManager giữ trình duyệt sống): **hoãn** theo YAGNI, đã ghi lại để làm sau.
4. Team lead sẽ kiểm Chromium headless mới trong image Docker Linux khi deploy.

## Câu hỏi còn mở

1. Chưa gặp response thật nào của trường hợp hết phòng. Giả định hiện tại: `Hotels` rỗng hoặc không còn giá hợp lệ thì là SOLD_OUT.
2. Thời hạn của token chưa dùng: tối thiểu ~4 phút, chưa đo thêm. Thiết kế hiện tại không phụ thuộc vào giá trị này.
3. `price_original` (lấy từ `PriceDiscount`) chưa đối chiếu được với giá gạch trên trang.
