# Spike + adapter Agoda

Ngày: 2026-10-01. Code: `backend/app/collector/agoda/` (`urls.py`, `parser.py`, `collector.py`; `PARSER_VERSION="2"`, `DROPDOWN_CAP=99`), fixture `backend/tests/fixtures/agoda/`, test `backend/tests/unit/test_agoda_{urls,parser,collector}.py` (55 test, pass). Proxy VN (`PROXY_URL_TEMPLATE`), không đăng nhập. Tổng khoảng 127 request tới agoda.com: 2 lần mở trang bằng Playwright để bắt XHR, khoảng 20 lệnh curl lẻ, 2 lần chạy smoke (mỗi lần 13 request), 1 lần smoke verify/suggest (khoảng 7 request).

## 1. Kết luận
- **Không cần trình duyệt.** Mọi thứ chạy bằng `curl_cffi` (impersonate chrome), không cookie, không token. `ProbeMethod.API`.
- **1 probe = 1 GET `GetSecondaryData`.** Request này trả cả bảng phòng: giá **đã gồm thuế phí theo phòng/đêm**, giá gạch, chiến dịch KM, hoàn huỷ, bữa sáng, số người, **số phòng còn theo loại phòng** và tín hiệu cầu. Thời gian mạng 0,6–2,9 s. Payload 0,9–2,2 MB JSON, nén gzip còn khoảng 160 KB, nhỏ hơn HTML Booking.
- **Bẫy tiền tệ:** tham số URL `currencyCode=VND` bị bỏ qua và Agoda trả **USD**. Phải gửi header **`cr-currency-code: VND`**. Adapter vẫn kiểm `hotelSearchCriteria.currencyCode` và trả `currency_mismatch:<cur>` nếu lệch.
- **Hết phòng cả khách sạn:** `GetSecondaryData` trả bảng rỗng, không có cờ nào. Khi đó adapter gọi thêm 1 POST `room-grid` (`isSoldOut: true`) để phân biệt `SOLD_OUT` với `NO_ROOMS_1N`.
- Không gặp lần chặn nào (0/120). Lịch min-LOS: không có, nên `fetch_calendar` trả `unsupported`.

## 2. Endpoint
| Mục đích | Request | Ghi chú |
|---|---|---|
| Probe | `GET /api/cronos/property/BelowFoldParams/GetSecondaryData?checkIn=&los=&rooms=1&adults=&children=0&currencyCode=VND&hotel_id=<id>&all=false&isHostPropertiesEnabled=true&price_view=2&pagetypeid=7` + header `cr-currency-code`, `ag-language-locale: vi-vn`, `x-requested-with` | `price_view=2` = gồm thuế/phòng/đêm (enum: 1 chưa thuế, 2 gồm thuế/đêm, 3 gồm thuế/cả kỳ) |
| Verify / thông tin | Cùng URL **không kèm ngày** (360 KB) | tên, sao, địa chỉ, `mapParams.latlng`, `searchbox.config.defaultSearchURL` (slug chuẩn) |
| slug → propertyId | `GET` trang HTML khách sạn (350 KB), regex `propertyId:(\d+)` | Chỉ chạy khi `ListingRef.external_id` trống; có cache trong collector |
| Hết phòng? | `POST /api/v1/property/room-grid` (payload tối thiểu + `ag-user-id`, `x-gate-meta` = base64 `ms\|user\|path`, `ag-initiator-api-key` public) | Chỉ gọi khi bảng phòng rỗng; 27 KB |
| Gợi ý (D8) | `GET /api/cronos/search/GetUnifiedSuggestResult/3/24/24/0/vi-vn/?searchText=…` | Có `ObjectId`, `CityName`, `CountryISO`, **không có toạ độ** → tra thêm bản không kèm ngày cho 3 ứng viên đầu |
| Không dùng | `cronos/seo/property` (canonical sai nếu không có Referer trang), `partnersearch.aspx?hid=` (302 về trang search), `graphql/property` (payload 18 KB) | |

## 3. Chống bot quan sát được
- Khoảng 120 request, giãn cách 2–3 s, IP VN xoay: **không có 403/429/captcha**. Không cần cookie: tự gọi API trần đều nhận 200.
- Adapter vẫn phòng sẵn: 403/429/503/202, hoặc 200 mà body không phải JSON → coi là `BLOCKED`, thu hồi session (proxy mới, cookie jar mới) và thử lại 1 lần. Lỗi mạng hoặc 5xx → thử lại 1 lần trên cùng session. Mỗi request đều gọi `budget.acquire()` và `limiter.wait(session)`.
- Tên hotel không tồn tại: API vẫn 200 nhưng `hotelInfo.name` trống → `ERROR not_found`. Slug sai: HTML 404 → `ERROR not_found`.

## 4. Ánh xạ về chuẩn
| Chuẩn | Trường Agoda | Ghi chú |
|---|---|---|
| `price` | `rooms[].inclusivePricePerNightWithoutExtraBed.display` | **Gồm thuế phí** (VN: phí DV 5% + VAT 8% = ×1,134). Mỗi phòng mỗi đêm, đã kiểm với 2 đêm: perBook/2. Sau KM/coupon Agoda tự áp. `taxes_included=True`. Nếu thiếu thì lấy `exclusivePrice` với `taxes_included=False` |
| `price_original` | **Giá trước coupon + chiến dịch Agoda tự áp**: `couponCrossedOut` (nếu lớn hơn `price`) cộng các mục `corBreakdown.agodaPromotions` lớp `pulse-promo` (VD "Mùa thu vàng" 694.959). Chỉ cộng khi `priceSummaries.final-price` khớp `price`. Bằng `price` thì để None | Quyết định của lead: **không** dùng giá gạch `crossedOut` (COR "giá cao nhất ±30 ngày", hiện -75%; Caravelle để cứng 10.000.000). KM của chính khách sạn (`promotion`, VD "Giảm giá phút chót") không tính. Mẫu: 2.606.097 − 694.959 (Agoda) − 799.203 (khách sạn) = 1.111.935, nên `price_original` = 1.806.894 |
| `promo_label` | `pulseCampaignInfo.campaignBadgeText` ("Mùa thu vàng") > "Coupon" > `promotion.title` ("Ưu đãi đặc biệt!") | |
| `refundable` | `isFreeCancellation` → True; `cancellation` "Không hoàn tiền"/`non-refund` → False; còn lại None | |
| `breakfast` | `isBreakfastIncluded` | |
| `max_persons` | `occupancy` | Bỏ giá có `adults` < số người tìm (Agoda trả cả giá cho 1 người). **Giữ** giá cho 4–6 người: khách 2 người thấy và đặt được, có khi rẻ hơn |
| Loại bỏ gói | `stayPackageType`≠0, `bundleType`≠0, `numberOfFixRoom`>1, master `isMultiRoomSuggestion/Bundle` | |
| `external_room_id` / `name` / `max_occupancy` | `masterRooms[].id` / `.name` / `.maxOccupancy` | |
| `badge_count` | `rooms[].availability` (max trong loại phòng) | **Số chính xác từ API, có ở mọi loại phòng** (thấy từ 1 đến 64). Bằng đúng con số trên nhãn "Chỉ còn lại N phòng!" / "Phòng cuối cùng" khi Agoda hiện nhãn. Map vào `badge_count` nên `derive_stock` ra EXACT. Xem CR-2 |
| `dropdown_max` | None | Bản desktop không có dropdown trong API. Dropdown của `room-grid` (mobile) **bị chặn trần 2** ("1 phòng", "2 phòng") kể cả khi còn 10–35 phòng nên vô dụng |
| `stock_scope` | `room_type` | Mọi giá trong một loại phòng có cùng `availability` |
| Loại phòng hết | `soldOutRooms[]` → `RoomOffer(badge_count=0, rates=())` | Khác Booking: hết phòng theo **loại phòng** được ghi lại |
| Status | Có master room → OK; chỉ có `soldOutRooms` → SOLD_OUT; rỗng → room-grid `isSoldOut` ? SOLD_OUT : NO_ROOMS_1N | Lệch ngày hoặc lệch số đêm → ERROR "agoda showed other dates" |
| `raw_html` | Body `GetSecondaryData`; riêng SOLD_OUT xác nhận qua room-grid thì lưu body room-grid (bằng chứng) | |
| POS | `origin: "VN"` trong response | Khớp proxy VN |

Câu hỏi §7.2 của báo cáo nghiên cứu: số phòng **theo loại phòng**, không theo khách sạn. Dropdown room-grid có trần **2**, không phải 10. `availableRooms` của `citySearch` chưa đối chiếu được, vì list mode đã hoãn.

## 5. Tín hiệu cầu
- `hotelInfo.engagement.visitorCount` "13 du khách đã đặt hôm nay." → `BOOKINGS_24H` (window 24, kèm `raw_text`). Đây cùng số với `graphql bookingCount{count:13,timeFrame:PastTwentyFourHours}` và dòng "Được đặt 13 lần trong vòng 24 giờ qua" trên trang. **Lúc có lúc không**: với Melia, 2/4 lần gọi tay không có trường này, đi kèm `hasBookingHistory:false`. Ở smoke thì 8/8 probe OK đều có.
- `engagement.todayBooking` "Đã được đặt 11 lần hôm nay" luôn có, kể cả Camia lúc hết phòng → `BOOKINGS_TODAY` (window None).
- Không thu: `lastBooked` "Mới đặt 5 tiếng trước" (theo loại phòng); `GetCalendarExtrasAsync.inDemandDates` (rỗng ở mọi mẫu, chưa rõ định dạng → chưa làm `HIGH_DEMAND`); `urgencyScore` (chỉ có ở `citySearch`).

## 6. Smoke thật (`scratchpad/agoda/smoke.py`, `build(deps)`, `RateLimiter(2,1)`, proxy VN)
Chạy 2 lần với kết quả giống nhau. Lần 2, với code cuối:

| Gọi | Kết quả | Mạng | Ghi chú |
|---|---|---|---|
| probe Melia 08/10 (slug, chưa có id) | OK, 7 offer, min 4.619.882 ₫ | 1,0 s | +1 GET HTML để lấy id 1985199. Badge [8,13,18,35,2,1,0] |
| probe Melia 17/10 | OK | 2,9 s | badge [9,14,20,35,2,2,0] |
| probe Melia 25/10 | OK | 1,8 s | payload 2,2 MB |
| verify Melia | id 1985199, 5★, toạ độ, URL chuẩn `vinpearl-discovery-2-phu-quoc_2/…` | 1 request | Slug "melia-vinpearl-phu-quoc" chuyển hướng về slug cũ |
| suggest "Melia Vinpearl Phu Quoc" + toạ độ | 1,0 Melia (1985199); "Phòng tại Mélia…" (listing bán lại, cách 800 m); Melia Huế | 4 request | Cần người dùng xác nhận (D8). Sau khi chuyển sang `matching.match_score` dùng chung, smoke với tên "Khu nghỉ dưỡng Melia Vinpearl Phú Quốc": 1,0 / 0,569 / 0,38 |
| probe Caravelle 11/10, 2 đêm | OK, 11 offer, min 6.035.169 ₫ | 0,9 s | |
| probe Camia 03/10 (đã hết phòng) | SOLD_OUT qua room-grid | 0,66 s (2 request) | |

Tỉ lệ thành công **10/10 probe** qua 2 lần chạy, **0 lần bị chặn**. Một lần chạy: 13 request, khoảng 30 s (chủ yếu do giãn cách 2–3 s). Ước lượng 1 probe tốn khoảng 1 request và 1–3 s mạng.

## 7. List mode (D6, hoãn)
`POST /graphql/search` operationName `citySearch`: request có `filterRequest.idsFilters` và **`extraHotels.extraHotelIds`**, tức có thể lọc theo hoặc ghép thêm danh sách propertyId compset (chưa thử). Mỗi khách sạn có `availableRooms`, `soldOut{soldOutPrice}`, giá `exclusive/inclusive` + `crossedOutPrice` + `pseudoCouponPrice`, `pulseCampaignMetadata.campaignBadgeText`, `urgencyDetail.urgencyScore`, `propertyLinks.propertyPage`. Một trang trả 45 khách sạn, khoảng 720 KB. Query GraphQL dài 31 KB (đã lưu `scratchpad/agoda/citysearch_post.json`).

## 8. Hạn chế
- `price_original` chỉ có khi Agoda tự áp coupon hoặc chiến dịch `pulse-promo`. Chưa bắt được mẫu có coupon thật (`couponCrossedOut` > 0), nên chưa rõ coupon áp trước hay sau chiến dịch (đang cộng dồn).
- Hết phòng cả khách sạn tốn thêm 1 request. Payload room-grid tối thiểu tự dựng theo web (`x-gate-meta`) nên có thể vỡ khi Agoda đổi.
- `listing_key` lấy theo slug của URL người dán. Cùng khách sạn có thể có nhiều slug (Melia → `vinpearl-discovery-2-phu-quoc_2`), còn URL chỉ có id thì key là `id/<propertyId>`. Phải khử trùng bằng `external_id` (CR-5).
- `availability` có thể là allotment Agoda giữ cho kênh, không phải tồn của khách sạn (D4: không cộng giữa kênh). Chưa biết có trần hay không; số lớn nhất từng thấy là 64.
- Ngưỡng chặn thật chưa biết: chưa thử ở tốc độ production (khoảng 100 probe/listing/ngày).

## 9. Contract change requests
1. ~~CR-1~~ Đã xong: lead thêm `BOOKINGS_TODAY`, parser đã thu.
2. CR-2 `RoomOffer.stock_source`: lead **từ chối (YAGNI)**. `availability` vẫn đi vào `badge_count`, `DROPDOWN_CAP=99`.
3. ~~CR-3~~ Đã xong theo cách khác: `price_original` = giá trước coupon/chiến dịch Agoda (xem §4).
4. CR-4 `CurlFetcher.get` header: lead **từ chối**, giữ `AgodaHttp`.
5. CR-5 khử trùng theo `external_id`: lead làm ở verify job (phía core).
6. ~~CR-6~~ Đã xong: `suggest` dùng `app.collector.matching.search_names` (thử lần lượt các biến thể tên) và `match_score`; đã xoá `agoda/match.py`. `verify` raise `ListingNotFound` (404, id không có khách sạn) và `ListingBlocked` (chặn hoặc lỗi mạng/HTTP); `suggest` raise `ListingBlocked`.

## 10. Câu hỏi chưa giải quyết
1. Coupon và chiến dịch Agoda áp theo thứ tự nào? Cần một mẫu có `couponCrossedOut` > 0.
2. `availability` của Agoda có trần không? Cần quan sát vài ngày ở khách sạn lớn.
3. `inDemandDates` (HIGH_DEMAND) có dữ liệu vào dịp lễ Tết không? Cần kiểm lại gần Tết 2027.
