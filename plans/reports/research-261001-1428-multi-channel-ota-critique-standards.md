# Nghiên cứu + phản biện: chuẩn đa kênh cho ScrapeBooking

Ngày: 2026-10-01 14:28–15:10. Tiếp nối `analysis-261001-1421-business-flow-multi-channel-scale.md` (gọi tắt **BC1**); báo cáo này **sửa và thay** các mục 3–6 của BC1 ở chỗ mâu thuẫn.
Chốt từ người dùng: ivivu là **nhu cầu thật**; **chưa tính ngân sách**; tiền tệ **VND**.
Phương pháp: 5 lượt WebSearch (thị phần VN, chuẩn rate shopping, parity, Agoda, ivivu) + **tự kiểm chứng trực tiếp** bằng curl_cffi/Playwright headless từ IP dân cư (khoảng 15 request, không đăng nhập) trên ivivu, Agoda, Trip.com, Traveloka, Mytour; đọc HTML Booking đã lưu.

---

## 0. Kết luận (12 quyết định chuẩn)

| # | Quyết định | Bằng chứng chính |
|---|---|---|
| D1 | Tách **Khách sạn (property)** ↔ **Listing (property × kênh)**. Mọi quan sát theo listing. | BC1 §2.2 |
| D2 | **Chuẩn tìm kiếm cố định**: 2 người lớn, 1 phòng, số đêm = min LOS, **VND**, POS VN, không đăng nhập. | Chuẩn rate shopper: "lowest available rate for base occupancy" |
| D3 | **Chuẩn giá**: VND, **đã gồm thuế phí, theo phòng/đêm**. Lưu **2 giá**: *hiển thị* (sau KM OTA tự áp) và *gốc* (trước KM). Kèm cờ hoàn huỷ, bữa sáng, nhãn KM. **Loại bỏ giá combo/gói.** | Agoda trả cả `exclusive`/`inclusive`, `crossedOutPrice`, `pseudoCouponPrice`, nhãn "NOON FLASH"; Booking VN "Includes taxes and charges" |
| D4 | **Chuẩn tồn phòng** = mức tin cậy hiện có **+ phạm vi** (`room_type` / `rate` / `property`). **Không cộng giữa kênh.** | Trip.com: "Chỉ còn 1 phòng **có giá này**" (theo giá, không theo loại phòng); Agoda: số phòng chỉ là của Agoda |
| D5 | **Tín hiệu cầu do kênh công bố** — họ tín hiệu mới, độ tin cậy thấp, luôn ghi nguồn. | Agoda "đặt 13 lần trong 24 giờ qua", `urgencyScore`; ivivu "Đã bán 2 phòng trong 24 giờ", `bookingInMonth: 17` |
| D6 | **Hai chế độ thu thập** mỗi kênh: *list* (1 request → nhiều khách sạn, giá thấp nhất + khan hiếm) và *property* (theo loại phòng). **Ưu tiên API JSON** hơn HTML. | Agoda `citySearch` trả `availableRooms`/`soldOut`/giá cho cả trang kết quả; ivivu, Agoda, Trip.com đều có API JSON |
| D7 | **Adapter theo kênh**, chiến lược phiên cắm được: `http` / `browser-bootstrap + http` / `browser`. | Mức chặn khác hẳn nhau giữa các kênh (bảng §1) |
| D8 | **Tự tìm listing ở kênh khác** qua API gợi ý của kênh, khớp theo tên + toạ độ, **người dùng xác nhận**. | Agoda suggest → id 1985199; ivivu `searchhotel` → id 377594 + lat/lng, không cần token |
| D9 | Vận hành: run = **(mốc giờ × kênh)**, hàng đợi theo kênh, **ngân sách request toàn cục theo kênh**, tự ngắt kênh khi bị chặn nhiều, khách sạn canary cho mỗi kênh. **Giới hạn thật là ngưỡng chống bot, không phải tiền.** | Traveloka trả trang trắng với headless; ivivu có token riêng |
| D10 | **Thứ tự kênh**: Agoda → ivivu → Trip.com → Traveloka → Mytour/Expedia. **Bỏ Google Hotels.** | Thị phần VN: Booking ~40%, Agoda ~25%, Traveloka ~15%, OTA nội địa ~20% (nguồn thứ 3) |
| D11 | Cảnh báo/bản tin **gộp theo khách sạn** ("hết phòng trên 2/3 kênh"). Thêm **parity cho khách sạn của bạn**: phát hiện kênh bán lại rẻ hơn. | ivivu gộp nguồn Agoda, Hotelbeds, Vinpearl HMS… → nơi lộ giá bán sỉ |
| D12 | **Tần suất theo tầng, nới horizon lên 90**: đêm 0–14 quét 3 lần/ngày, 15–60 quét 1 lần/ngày, 61–90 cách 3 ngày quét 1 lần ≈ 101 probe/listing/ngày (hiện 90 probe chỉ cho 30 đêm). | Horizon gấp 3, số request gần như không đổi |

---

## 1. Bằng chứng tự kiểm chứng (01/10/2026, cùng 1 khách sạn: Melia Vinpearl Phú Quốc)

| Kênh | Truy cập | Định danh | Giá | Tồn phòng | Tín hiệu cầu | Chống bot quan sát được |
|---|---|---|---|---|---|---|
| **Booking** (đang chạy) | curl_cffi + cookie Playwright | slug + `hotel_id` | VND, **đã gồm thuế** (`b_is_all_included: 1`) — parser hiện **chưa lưu cờ này** | badge + dropdown (trần 10) | chưa thu | AWS WAF |
| **Agoda** | Playwright OK; `GetSecondaryData` gọi được bằng curl_cffi trần | `propertyId` 1985199, URL `/vi-vn/<slug>/hotel/<city>-vn.html` | `currencyCode=VND`; trả `perRoomPerNight.exclusive/inclusive`, `crossedOutPrice`, coupon tự áp, nhãn flash sale | `room-grid`: dropdown `availableRooms`, `isSoldOut`; list: `availableRooms` (thấy cả 13), "Chỉ còn N phòng" | "đặt 13 lần trong 24 giờ qua", `urgencyScore`, lịch `showHeavyDemand` | chưa thấy chặn ở ~6 request |
| **ivivu** | Trang + API phụ: OK. **API giá** `POST /web_prot/pay/api/contracting/HotelSearchReqContractAppV2` → **403 `Invalid_token_ivv`** khi headless | `hotelId` 377594, `hotelCode` slug, lat/lng qua `searchhotel` | VND gốc | chưa thấy (giá bị chặn token) | `TopSale24hByHotel` (đã bán N phòng/24h), `bookingInMonth` — **public, không cần token** | Cloudflare Turnstile + challenge riêng `gatewaycrm/get-session` |
| **Trip.com** | Playwright OK | id + URL | `curr=VND` | "Chỉ còn N phòng **có giá này**" (phạm vi rate) | chưa xem | chưa thấy chặn |
| **Traveloka** | curl trang chủ OK; **Playwright headless: trang trắng, 0 XHR** | — | — | — | — | Mạnh nhất trong nhóm |
| **Mytour** | Trang chủ OK, API `apis.tripi.vn` (Tripi) | — (URL đoán sai → 404) | — | — | — | chưa đánh giá |

**ivivu không chỉ là OTA tự ký hợp đồng.** Request giá của nó gửi cờ `supplier:"IVIVU"`, `getVinHms`, `isAgoda`, `getRateHBED` (Hotelbeds), `getRateHLS`, `getRateExtranet`, `getRateMGB`, `getSMD`. Tức ivivu **gộp nhiều nguồn**: hợp đồng riêng, kết nối thẳng Vinpearl, **bán lại Agoda và bedbank**. Hệ quả nghiệp vụ:
- Với **khách sạn của bạn**: ivivu là nơi giá bán sỉ (Hotelbeds/Agoda) lộ ra rẻ hơn giá công bố → **tính năng parity có giá trị thật**, đúng thứ khách sạn cần biết.
- Với **đối thủ**: giá ivivu = giá khách nội địa nhìn thấy, nhưng có thể chỉ là Agoda cộng biên → khi so phải biết **nguồn**. Spike cần kiểm tra response có trường supplier theo từng giá không.
- ivivu bán **combo** ("Giá combo cho 1 khách", "3N2Đ VMB…") → adapter phải lấy giá phòng lẻ (`isPackageRate:false`), loại combo.

---

## 2. Phản biện BC1 (giữ / sửa / bỏ)

| Đề xuất BC1 | Kết luận | Lý do |
|---|---|---|
| Tách property/listing | **Giữ** | Không có cách nào khác tránh ghi đè. |
| Run theo (mốc × kênh), hàng đợi theo kênh | **Giữ** | Traveloka/ivivu sẽ chậm/chặn; không được kéo trễ Booking. |
| Không map loại phòng giữa kênh ở MVP | **Giữ**, nói rõ hơn | Chuẩn ngành so **giá thấp nhất cho 2 người**, không theo loại phòng; map phòng chỉ cần cho parity của khách sạn bạn → để phase sau. |
| Cờ giá `per_night`, `taxes_included`, `member_only` | **Sửa** | Thiếu cái quan trọng nhất: **giá hiển thị vs giá gốc trước KM của OTA** (coupon Agoda tự áp ~300k ₫, flash sale). Không tách thì "đối thủ giảm giá" thực ra là Agoda tự trợ giá → báo động giả. |
| Bảng `channels` trong DB | **Bỏ** | Năng lực kênh là code. Registry trong code + trạng thái tạm dừng (do tự ngắt khi bị chặn nhiều) trong Redis là đủ (KISS). |
| `tenant_channels` (gói, giới hạn kênh) | **Bỏ lúc này** | Chưa tính ngân sách/billing → YAGNI. Thay bằng 1 cột `tenants.reference_channel`. |
| Bảng `property_date_metrics` | **Bỏ** | Tính tại chỗ từ metric listing như `compset.py` đang làm; chỉ tạo bảng khi đo thấy chậm. |
| Quét theo tầng để **giảm chi phí** | **Sửa mục đích** | Tiền không phải giới hạn; **chống bot** mới là giới hạn → dùng tầng để **nới horizon 30→90** mà không tăng request (D12). |
| Google Hotels (chỉ giá) | **Bỏ** | Không có tồn phòng (lõi giá trị của sản phẩm), ToS rủi ro; 4 kênh đầu đã phủ ~80%+ thị trường VN. |
| Thứ tự Agoda → Traveloka → Trip/Expedia → ivivu | **Sửa**: Agoda → **ivivu** → Trip.com → Traveloka | ivivu là nhu cầu thật + có giá trị parity; Trip.com dễ truy cập; Traveloka chặn mạnh nhất, cần spike dài hơn. |
| Verify listing ngay khi thêm | **Giữ, mở rộng** | Verify + **tự gợi ý listing ở kênh khác** (D8) vì API gợi ý của các kênh trả id + toạ độ. |

---

## 3. Phản biện hệ thống hiện tại (độc lập với đa kênh)

| # | Vấn đề | Mức | Đề xuất |
|---|---|---|---|
| 1 | Proxy là điểm hỏng đơn; run 24, 25 (01/10) **0 probe** vì lỗi 407 | Cao | ≥2 nhà cung cấp, kiểm tra proxy trước khi mở run, báo operator qua kênh thật. |
| 2 | Parser Booking **không lưu** cờ "đã gồm thuế" (`b_is_all_included`), chỉ đang mặc định là có | TB | Lưu cờ vào rate; khi so đa kênh phải có cờ này. |
| 3 | Không thu **tín hiệu cầu** mà kênh công khai (Booking cũng có thông điệp kiểu nhu cầu cao, cần xác minh) | TB | D5. Lấy cùng request, không tốn thêm request. |
| 4 | Mô hình tồn phòng không có **phạm vi** (badge của Booking là theo loại phòng; Trip.com là theo giá) | TB | D4: thêm `stock_scope`. |
| 5 | Mỗi đêm × khách sạn = 1 trang HTML đầy đủ (~440 KB nén) | TB | D6: chế độ list + API JSON cho kênh hỗ trợ; raw lưu JSON nhỏ hơn. |
| 6 | Horizon 30 đêm (ngành: tới 365). Khách resort/lễ Tết cần xa hơn (Agoda đã gắn sẵn Tết 2027 vào lịch) | TB | D12. |
| 7 | `compset.load_watchlist` chạy 1 query 2 lần | Thấp | Gộp. |

---

## 4. Chi tiết chuẩn

### 4.1 Chuẩn tìm kiếm (D2) — `SearchSpec`
`adults=2, children=0, rooms=1, nights=min_los (calendar nếu kênh có, mặc định 1), currency=VND, pos_country=vn, locale=vi|en, logged_out=true, device=desktop`.
Adapter **phải** ép được VND; response khác VND → probe `error: currency_mismatch` (**không quy đổi**). Đã kiểm: Booking `selected_currency=VND`, Agoda `currencyCode=VND`, Trip.com `curr=VND`, ivivu mặc định VND.

### 4.2 Chuẩn giá (D3) — mỗi rate lưu
```
price_display      VND, gồm thuế phí, /phòng/đêm, sau KM OTA tự áp (giá khách thấy)
price_original     trước KM của OTA (crossedOut/originalPrice), None nếu kênh không có
taxes_included     bool (bắt buộc; không chắc → None, và không đem so)
refundable, breakfast, max_persons   (đã có)
promo_label        "NOON FLASH", "Mùa thu vàng", coupon…
member_only        luôn false vì không đăng nhập; giữ để khẳng định
source_supplier    ivivu: IVIVU/AGODA/HBED…  (None nếu kênh không lộ)
```
Compset/so sánh: dùng `price_display` cùng cơ sở thuế. Parity của khách sạn bạn: so **`price_original`** (loại phần OTA tự trợ giá) và hiện cả hai.

### 4.3 Chuẩn tồn phòng (D4)
`rooms_left, confidence (exact|capped|hidden|sold_out), scope (room_type|rate|property), source (badge|dropdown|api_field)`.
Tầng khách sạn (tính tại chỗ): `hết trên k/n kênh quan sát được`. k = n → tín hiệu mạnh; k < n → **có thể chỉ là đóng kênh** (sự kiện `channel_closed`).

### 4.4 Tín hiệu cầu (D5) — bảng mới nhỏ
`listing_demand_signals(listing_id, observed_at, kind, value, window, raw_text)`; kind: `bookings_24h`, `rooms_sold_24h`, `bookings_month`, `urgency_score`, `high_demand_date`.
Hiện kèm nguồn ("theo Agoda"), **không** đưa vào chỉ số giá; bản tin AI chỉ được nhắc khi có giá trị (giữ nguyên tắc 1: chỉ nói điều có bằng chứng). Đây là câu trả lời cho điểm yếu "không có dữ liệu nhu cầu" trong research 01/10.

### 4.5 Adapter (D6, D7)
```python
class ChannelAdapter(Protocol):
    code: str
    session_strategy: Literal["http", "bootstrap_http", "browser"]
    capabilities: Capabilities   # list_mode, calendar, stock_scope, taxes_split, original_price, demand_signals
    def parse_url(self, url: str) -> ListingUrl: ...
    async def suggest(self, name: str, city: str) -> list[ListingCandidate]: ...  # D8
    async def verify(self, listing) -> ListingIdentity: ...                         # tên, toạ độ, id
    async def fetch_calendar(self, listing, start, days, spec) -> CalendarResult | None: ...
    async def probe(self, listing, checkin, spec) -> ProbeResult: ...               # chế độ property
    async def probe_list(self, area, checkin, spec, wanted_ids) -> dict[str, ProbeResult]: ...  # chế độ list, tuỳ chọn
```
- Chế độ list ghi **nhiều probe dùng chung 1 `raw_object_key`** → không cần bảng mới.
- Raw lưu nguyên payload (HTML hoặc JSON) + `parser_version` theo adapter.
- `HybridCollector` hiện tại chính là chiến lược `bootstrap_http` → tổng quát hoá, không viết lại.

### 4.6 Định danh & thêm khách sạn (D8)
1. Dán URL bất kỳ kênh → nhận diện kênh → verify (tên, toạ độ, id).
2. Hệ thống gọi `suggest` ở các kênh còn lại theo tên + thành phố → ứng viên có điểm (độ giống tên + khoảng cách toạ độ < ~200 m).
3. Người dùng tick xác nhận listing nào là cùng khách sạn. **Không tự gắn khi chưa xác nhận** (sai định danh làm hỏng compset).
4. Listing chưa có ở kênh nào → hiện "chưa bán trên Traveloka" (cũng là một thông tin).

### 4.7 Vận hành (D9)
- Run key `"<phút UTC>:<channel>"`; hàng đợi `collector:<channel>`; số worker riêng mỗi kênh.
- Token bucket Redis theo kênh (request/phút toàn hệ thống) **trên** rate limiter theo session hiện có.
- Ngắt kênh tự động: tỉ lệ chặn > 20% trong 15 phút → dừng kênh 30 phút, báo operator; kênh khác chạy tiếp.
- Canary: 1 khách sạn cố định mỗi kênh, so số trường parse được hằng ngày → phát hiện parser trôi.
- Email cảnh báo: gom theo **mốc giờ**, chờ các run cùng mốc xong hoặc tới hạn chót.

### 4.8 Mô hình dữ liệu (bản gọn, thay BC1 §4)
```
hotels            property (giữ bảng; bỏ dần booking_*)
listings   NEW    id, hotel_id, channel, external_id, url, slug, lat, lng, status, verified_at
                  UNIQUE(channel, external_id)
tenants           + reference_channel (mặc định 'booking'), + currency 'VND'
room_types        listing_id, external_room_id
scan_jobs         PK (scan_run_id, listing_id)
probes            UNIQUE(scan_run_id, listing_id, stay_date), + channel, method thêm 'list'
room_snapshots    listing_id, + stock_scope, rates JSON thêm price_original/taxes_included/promo_label/source_supplier
hotel_date_*      → theo listing_id
availability_events  listing_id (+ channel); thêm channel_closed, parity_gap
listing_demand_signals NEW (D5)
```

---

## 5. Lộ trình (thay BC1 §6)

| Phase | Nội dung | Điều kiện xong |
|---|---|---|
| 0 | Proxy ≥2 nhà cung cấp + kiểm tra trước run + cảnh báo operator thật; Booking lưu cờ thuế | Run có probe trở lại; cờ thuế có trong rate |
| 1 | Adapter + registry, dời Booking vào adapter (không đổi hành vi); `SearchSpec`; session key `(channel, country)` | Toàn bộ test hiện có pass |
| 2 | Schema expand + backfill listing `booking`; chuyển đọc/ghi sang `listing_id`; run theo (mốc × kênh) | Dashboard Booking y như cũ |
| 3 | **Spike song song 3 kênh** (2–3 ngày mỗi kênh, ~100 probe): Agoda (room-grid + citySearch), ivivu (lấy token qua browser bootstrap → gọi API giá; kiểm tra trường supplier), Trip.com | Bảng: tỉ lệ ok, trường lấy được, tồn phòng/phạm vi, tín hiệu cầu |
| 4 | API/UI đa kênh: dán URL mọi kênh, verify, gợi ý listing chéo kênh, cột Kênh, kênh tham chiếu, chi tiết đêm nhiều kênh | Thêm Melia qua URL ivivu → tự gợi ý Agoda/Booking |
| 5 | Adapter Agoda → ivivu → Trip.com (mỗi kênh: fixture + canary + mở cho tenant 9 trước) | Tỉ lệ ok ≥ 95% trong 7 ngày |
| 6 | Tín hiệu cầu, `channel_closed`, parity cho khách sạn bạn; đưa vào email/bản tin | Email gộp theo khách sạn |
| 7 | Tần suất theo tầng + horizon 90; chế độ list cho kênh hỗ trợ | Horizon 90, số request/listing không tăng quá 15% |
| 8 | Traveloka (spike riêng, chống bot mạnh), Mytour, Expedia | — |
| 9 | Contract: bỏ `booking_*` khỏi schema + API | — |

---

## 6. Rủi ro
- **ToS/pháp lý**: mọi kênh đều cấm scrape trong điều khoản. Giữ nguyên tắc: không đăng nhập, không dữ liệu cá nhân, tốc độ lịch sự, chỉ dữ liệu công khai. ivivu có challenge riêng → vượt nó là vùng xám hơn Booking; cân nhắc **đề nghị hợp tác/API chính thức với ivivu** (OTA nội địa, có PMS miễn phí cho khách sạn → có thể là đối tác).
- **Thông điệp khan hiếm là marketing** (Quora/thetraveler: Agoda dùng luật + dữ liệu thật để tạo cảm giác gấp) → tín hiệu cầu luôn là "theo kênh", không phải sự thật về khách sạn.
- **API nội bộ đổi không báo** (tên có V2, V3) → canary + `parser_version` + raw payload là bắt buộc.
- Số thị phần lấy từ nguồn thứ ba (daytripsvietnam) → độ tin cậy trung bình.

---

## 7. Câu hỏi chưa giải quyết
1. Response giá của ivivu (khi có token) có ghi nhà cung cấp theo từng giá không? → quyết định có làm được parity "ai bán lại rẻ hơn" hay không.
2. `availableRooms` của Agoda (list) là số phòng của offer rẻ nhất hay của cả khách sạn? Dropdown `room-grid` có trần như Booking (10) không?
3. Booking có thông điệp nhu cầu/lượt đặt 24h trên trang không (chưa kiểm trong HTML đã lưu)?
4. Agoda `citySearch` lọc được đúng danh sách id khách sạn compset không, hay phải phân trang?
5. Traveloka: chặn do headless hay do IP? Cần spike với trình duyệt có giao diện + proxy dân cư.
6. Muốn tiếp cận ivivu theo hướng hợp tác (API chính thức) song song với scrape không?

---

## Nguồn
- Thị phần OTA VN: https://daytripsvietnam.com/research/vietnam-online-travel-market-research/ ; https://vietnamnews.vn/economy/1527704/foreign-otas-dominate-viet-nam-s-lucrative-online-travel-market.html ; https://baodautu.vn/thi-truong-du-lich-truc-tuyen-viet-nam-ota-ngoai-lan-at-chu-nha-d166929.html
- ivivu: https://www.ivivu.com/blog/gioi-thieu/ ; https://ezcloud.vn/dang-ky-ban-phong-tren-ivivu.html
- Chuẩn rate shopping/parity: https://www.mylighthouse.com/resources/blog/hotel-rate-shopper ; https://rategain.com/blog/how-hotel-competitor-rate-shopping-software-works-2027-buying-guide/ ; https://hoteltechreport.com/news/rate-parity ; https://www.mews.com/en/blog/hotel-rate-parity-issues ; https://academy.hsmai.org/wp-content/uploads/sites/11/2018/07/2018-white_paper_rate_parity-incl-strategies.pdf ; https://stayapi.com/blog/hotel-rate-parity
- Agoda thuế/khan hiếm: https://jontotheworld.com/agoda-hidden-fees-taxes-service-charges-and-final-price-explained/ ; https://www.quora.com/Are-the-x-rooms-left-in-Agoda-real ; https://www.thetraveler.org/the-agoda-fees-and-policies-most-travelers-miss/
- Tự kiểm chứng: script + payload trong scratchpad phiên (`probe/net.py`, `*.calls.json`), không commit.
