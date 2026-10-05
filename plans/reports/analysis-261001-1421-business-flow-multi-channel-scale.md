# Phân tích business, chức năng, flow — chuẩn hoá để scale đa kênh (Booking → Agoda, Traveloka, Expedia, Trip.com, ivivu…)

Ngày: 2026-10-01. Phương pháp: đọc code backend/dashboard, docs (`PRODUCT.md`, `docs/user-flows.md`), research 01/10, số liệu thật trong DB local (tenant 9, run 18–25).
Phạm vi: phân tích + thiết kế đích. Chưa sửa code.

> **Cập nhật 01/10 14:28:** mục 3–6 đã được sửa/thay bởi `research-261001-1428-multi-channel-ota-critique-standards.md` (kiểm chứng thực tế ivivu/Agoda/Trip.com, phản biện). Đọc báo cáo đó trước.

---

## 0. TL;DR

- **Business hiện tại** đúng hướng và có lợi thế thật: đo *số phòng còn / hết phòng của từng đối thủ, từng loại phòng, từng đêm*, 3 lần/ngày, có mức tin cậy, cộng bản tin AI có bằng chứng + occupancy PMS + email cảnh báo. Free tool của OTA không cho cái này.
- **Lõi pipeline đã chuẩn** (idempotent, retry, catch-up, rules thuần, outbox, raw HTML để reparse) → tái dùng được gần hết khi lên đa kênh.
- **Chặn scale đa kênh nằm ở mô hình dữ liệu**: hiện `Khách sạn = 1 trang Booking`. Danh tính (`booking_slug` unique), loại phòng, job, probe, metric, sự kiện đều khoá theo `hotel_id`. Thêm kênh thứ 2 vào schema hiện tại sẽ **ghi đè** dữ liệu kênh 1.
- **Sửa gốc**: tách **Khách sạn (property)** ↔ **Listing (property × kênh)**; quan sát/analytics chạy theo listing; compset/insight có tầng tổng hợp theo property. Collector thành **Channel Adapter** đăng ký theo kênh.
- **Nghiệp vụ phải định nghĩa trước khi code** (nếu không dữ liệu đa kênh sẽ sai): (1) "còn X phòng" trên OTA là *allotment của kênh đó*, không phải tồn kho khách sạn → không cộng giữa kênh; (2) giá giữa kênh khác cơ sở (thuế, member price, theo đêm/tổng) → chỉ so cùng cơ sở; (3) loại phòng không map được 1-1 giữa kênh → MVP không map.
- **Kinh tế**: chi phí tăng tuyến tính theo `listing × kênh × số đêm × số lượt`. Số đo thật: ~4,5 giây worker/probe, ~440 KB HTML nén/probe. Cần quét theo tầng (gần dày, xa thưa) + ngân sách request theo kênh trước khi thêm kênh.
- **Việc gấp không liên quan đa kênh**: 2 lượt quét gần nhất (run 24, 25 ngày 01/10) **0 probe** — proxy trả 407. Khách thật (tenant 9) đang không có dữ liệu mới. Cảnh báo vận hành hiện chỉ ghi log.

---

## 1. Business hiện tại

### 1.1 Khách hàng, giá trị
| Mục | Hiện trạng |
|---|---|
| Khách hàng | Khách sạn VN (chủ, GM, sales, revenue manager). Vai trò `tenant_admin`, `viewer`; `operator` vận hành nhiều tenant. |
| Job-to-be-done | Sáng ra quyết định giá/phân phối: đối thủ còn bao nhiêu phòng, giá bao nhiêu, đêm nào sắp kín. |
| Tín hiệu độc quyền | rooms-left theo đối thủ × loại phòng × đêm (`exact`/`capped`/`hidden`/`sold_out`), sự kiện sold_out/restock/giảm phòng/đổi giá, đọc calendar trước để tránh báo hết phòng sai vì min-stay. |
| Lớp quyết định | Compset theo đêm (trung vị, rẻ nhất, hạng giá, price index, % đối thủ hết phòng, occupancy PMS), câu giải thích từng đêm, bản tin AI có bằng chứng, email cảnh báo theo lượt (đợt 1). |
| Go-to-market | Operator onboard thủ công, "liên hệ báo giá", chưa self-serve, chưa billing. |
| Nguồn dữ liệu | **Chỉ Booking.com.** PMS qua CSV/Excel. |

### 1.2 Đơn vị chi phí (số đo thật, local)
| Chỉ số | Giá trị | Nguồn |
|---|---|---|
| 1 lượt, 5 khách sạn × 30 đêm = 150 probe | 645–798 giây | `scan_runs` 22, 23 |
| Thời gian worker / probe | ~4,5 giây (3,3 s fetch p50, p90 5,2 s + giãn cách 2–3 s) | `probes` 10 ngày |
| HTML nén / probe | ~440 KB (340 MB / 779 probe) | MinIO `raw-html` |
| Giữ HTML thô | 30 ngày (lifecycle MinIO) | `collector/storage.py:57` |
| Phân bố tin cậy | exact 47% · capped 39% · hidden 14% | `room_snapshots` |
| Worker | 1 job/tiến trình, scale bằng số tiến trình | `worker/settings.py` |

**Đơn vị tính chi phí đúng = listing-ngày** (1 khách sạn trên 1 kênh, 1 ngày): `horizon × số lượt` probe = 30 × 3 = **90 probe ≈ 40 MB HTML nén ≈ 6,75 phút worker**.

Ví dụ 100 tenant × 5 khách sạn ≈ 400 khách sạn riêng biệt (đã dùng chung giữa tenant):
| | 1 kênh | 3 kênh |
|---|---|---|
| Probe/ngày | 36.000 | 108.000 |
| Worker song song để mỗi lượt xong trong 90 phút (giả sử mọi tenant cùng giờ quét) | ~10 | ~30 |
| HTML lưu (30 ngày) | ~480 GB | ~1,4 TB |
| Băng thông proxy/tháng (ước theo kích thước nén, chưa đo trên đường truyền) | ~0,5 TB | ~1,5 TB |

→ Thêm kênh nhân chi phí trực tiếp. Giá bán phải tính theo **số khách sạn × số kênh**, và cần giảm probe/listing (mục 5.5).

### 1.3 Rủi ro business
1. Phụ thuộc một nguồn (Booking) + ToS/anti-bot. Đa kênh vừa là tính năng vừa là giảm rủi ro.
2. Proxy là điểm hỏng đơn: một template tĩnh trong `.env`; hỏng là toàn hệ thống ngừng (đang xảy ra từ 01/10).
3. ezCloud (PMS #1 VN, có ezRms) có thể bundle tính năng tương tự (research 01/10).
4. Ở VN/SEA, khách quen Agoda; chỉ có Booking làm thiếu ở mắt khách.

---

## 2. Bản đồ chức năng & flow hiện tại

```
Operator tạo tenant/users ─► tenant_admin dán URL Booking (self | competitor) ─► hotels (dùng chung mọi tenant theo slug)
                                                                                  │
scheduler tick 60s ─► mốc giờ tenant (gom theo phút UTC) ─► scan_run ─► scan_job/khách sạn ─► Redis "collector"
     (catch-up khi lỡ mốc, chốt run quá 90', đẩy lại job kẹt)                     │
worker: calendar GraphQL (available, min LOS) ─► mỗi đêm 1 probe (curl_cffi + cookie Playwright, fallback trình duyệt)
     ─► probes + room_snapshots (rooms_left+confidence, min price, min refundable, rate plans) + HTML thô MinIO
     ─► job cuối chốt run ─► Redis "jobs": analytics
          ─► hotel_date_snapshots ─► availability_events (diff với lần dùng được gần nhất) ─► hotel_date_metrics
          ─► email cảnh báo theo lượt (outbox `notifications`) ; bản tin AI hằng ngày ; PMS CSV ─► own_hotel_daily
dashboard: Tổng quan (heatmap + dải compset) ─► Chi tiết đêm ─► Chi tiết khách sạn ─► Sự kiện ─► Bản tin ─► Cài đặt
```

### 2.1 Điểm đã chuẩn — giữ nguyên khi đa kênh
| Thành phần | Vì sao tốt |
|---|---|
| `Collector` Protocol (`collector/base.py`) | Đã là interface; chỉ cần thêm khái niệm kênh. |
| Rules analytics thuần (`analytics/rules.py`) | Không I/O, không biết Booking → dùng lại 100% theo listing. |
| Run/job idempotent, `terminal_dates`, arq `_job_id`, retry, catch-up, deadline | Chịu lỗi tốt; giữ nguyên ngữ nghĩa. |
| Mô hình tin cậy `exact/capped/hidden/sold_out` | Tổng quát cho mọi OTA có badge "chỉ còn X phòng". |
| HTML thô + `parser_version` + `reparse` | Bắt buộc khi có nhiều parser dễ vỡ. |
| Khách sạn dùng chung giữa tenant | Tiết kiệm chi phí; giữ ở mức listing. |
| Outbox thông báo theo `dedupe_key` | Không gửi trùng; độc lập với kênh dữ liệu. |
| Partition `room_snapshots` theo tháng | Đã sẵn cho khối lượng lớn. |

### 2.2 Điểm gắn chặt Booking (chặn đa kênh)
| Chỗ | Gắn thế nào | Hậu quả khi thêm kênh |
|---|---|---|
| `db/models.py:46-58` `Hotel.booking_url/booking_slug (unique)/booking_hotel_id` | Danh tính khách sạn = slug Booking | 1 khách sạn không thể có nhiều kênh; thêm Agoda = tạo "khách sạn" thứ 2, compset đếm trùng. |
| `db/models.py:71-73` `RoomType(hotel_id, booking_room_id)` | Loại phòng thuộc khách sạn | Id phòng 2 kênh trùng số → đè nhau. |
| `ScanJob` PK (run, hotel) `:101`; `Probe` unique (run, hotel, stay_date) `:117`; `HotelDateSnapshot` `:197`, `HotelDateMetric` `:243` khoá theo hotel | 1 quan sát / khách sạn / đêm / lượt | Kênh 2 ghi đè kênh 1; sự kiện "đổi giá" giả do so giá Booking với Agoda. |
| `domain/booking_url.py`, `api/routers/watchlist.py:45`, `watchlist-tab.tsx:21-33` | Chỉ nhận booking.com | URL ivivu trong ảnh chụp → bị chặn ngay ở trình duyệt / 422. |
| `repo/runs.py:66-67` `load_hotel` | Hardcode `https://www.booking.com/hotel/…` | |
| `worker/settings.py:58-62` | Khởi tạo cứng `HybridCollector` + `BrowserCollector` Booking | 1 worker chỉ quét được Booking. |
| `collector/fetch.py:16` `BLOCK_MARKERS` chung | Dấu hiệu chặn của Booking/AWS WAF | Kênh khác (Akamai, PerimeterX…) bị phân loại sai. |
| `collector/session.py:73,92` session theo `country` | Cookie Booking dùng cho mọi request cùng nước | Kênh khác dùng nhầm cookie/session. |
| `collector/ratelimit.py` | Giãn cách theo session, trong 1 tiến trình | Không có ngân sách toàn cục theo domain: thêm worker = tăng tải lên 1 OTA không kiểm soát. |
| `collector/booking/urls.py` tiền tệ theo nước khách sạn | | Đa kênh cần tiền tệ cố định theo tenant để so được. |
| `api/schemas.py:83-101`, `api-types.ts`, UI hiện `booking_slug` | Contract API lộ field Booking | Đổi contract kéo theo dashboard. |
| `ScanRun` toàn cục, chốt khi job chậm nhất xong | Analytics/cảnh báo chờ job chậm nhất | 1 kênh bị chặn làm trễ dữ liệu mọi kênh. |

Lặt vặt: `analytics/compset.py:57` `load_watchlist` chạy cùng 1 query 2 lần (gộp được thành 1).

---

## 3. Ngữ nghĩa nghiệp vụ đa kênh — phải chốt trước khi code

| # | Vấn đề | Chuẩn đề xuất |
|---|---|---|
| 1 | **"Còn X phòng" là của kênh**, không phải của khách sạn (Agoda thường ghi kiểu "left on our site" — xác minh khi spike). Khách sạn VN thường dùng channel manager pool chung, nhưng có thể đóng riêng 1 kênh (stop-sell). | Lưu rooms-left theo listing. **Không cộng giữa kênh.** Tầng property chỉ suy: *hết trên mọi kênh quan sát được* (tín hiệu mạnh) / *hết trên k/n kênh* (có thể là đóng kênh). Thêm sự kiện `channel_closed`. |
| 2 | **Giá khác cơ sở**: có/không thuế phí, theo đêm vs tổng kỳ, giá thành viên/app/coupon, bữa sáng, hoàn huỷ. | Mỗi giá lưu kèm cờ: `per_night`, `taxes_included`, `member_only`, `refundable`, `breakfast`. Compset trong 1 kênh như hiện nay; so giữa kênh **chỉ khi cùng cơ sở**, không thì hiện "không so được". Bỏ giá member khỏi so sánh mặc định. |
| 3 | **Tham số tìm kiếm** phải giống nhau giữa kênh: 2 người lớn, 1 phòng, số đêm = min LOS, tiền tệ, nước của proxy (POS), không đăng nhập. | Đưa vào `SearchSpec` chung; adapter nào không ép được tham số (VD tiền tệ) thì khai báo trong capabilities. |
| 4 | **Loại phòng không map 1-1** giữa kênh ("Deluxe King" vs "Deluxe Room with King Bed"). | MVP: **không map**; analytics theo listing, tầng property dùng giá thấp nhất + trạng thái. Map phòng (gợi ý fuzzy + người xác nhận) để sau. |
| 5 | **Danh tính khách sạn giữa kênh**: cùng 1 khách sạn trên 4 OTA có tên/địa chỉ khác nhau. | Property do người dùng xác nhận. Gắn listing bằng URL (MVP) → sau thêm gợi ý tự động theo tên + toạ độ, người dùng duyệt. |
| 6 | **Parity** (khách sạn mình rẻ hơn ở đâu) là giá trị mới chỉ có khi đa kênh. | Sự kiện `parity_gap` cho khách sạn "self": chênh giữa kênh > ngưỡng, cùng cơ sở giá. |
| 7 | **Kênh "chỉ giá"** (metasearch như Google Hotels: 1 trang có giá nhiều OTA, không có rooms-left). | Phân 2 loại adapter: *inventory* (rooms-left + giá) và *price-only*. UI không hiện rooms-left cho price-only. Cần xác minh ToS trước khi dùng. |
| 8 | **Ưu tiên kênh** khi heatmap chỉ có 1 ô/đêm. | Tenant chọn **kênh tham chiếu** (mặc định Booking) cho heatmap/compset; có bộ chọn kênh; chi tiết đêm hiện mọi kênh cạnh nhau. |

---

## 4. Mô hình dữ liệu đích

Nguyên tắc: giữ bảng `hotels` làm **property** (giảm đổi tên), tách mọi thứ của kênh sang `listings`.

```
channels         code PK (booking|agoda|traveloka|expedia|tripcom|ivivu|google) · kind (inventory|price_only)
                 enabled · capabilities JSONB · rate_budget (req/phút toàn cục) · max_concurrency · proxy_pool
hotels           (property) id · name · city · country_code · lat/lng · star_rating
listings  NEW    id · hotel_id FK · channel FK · external_id · url · slug · country_code
                 status (unverified|active|broken|paused) · verified_at · last_ok_at
                 UNIQUE(channel, external_id)            ← thay booking_slug unique
tenant_hotels    (giữ) tenant ↔ property, role self|competitor, label
tenant_channels  NEW tenant_id · channel · active · is_reference    ← kênh tenant mua/theo dõi
room_types       listing_id · external_room_id           ← thay hotel_id/booking_room_id
scan_jobs        PK (scan_run_id, listing_id)
probes           UNIQUE(scan_run_id, listing_id, stay_date) · channel (denormalize để lọc nhanh)
room_snapshots   listing_id · + price_flags (per_night, taxes_included, member_only)
listing_date_snapshots / listing_date_metrics / availability_events   ← đổi hotel_id → listing_id (+ channel)
property_date_metrics NEW (tầng tổng hợp, tính lại sau analytics): channels_observed · channels_sold_out
                 · min_price_comparable · parity_gap_pct (chỉ self)
```

Compset (`analytics/compset.py`) giữ logic, đổi input: tập listing của tenant **trên kênh đang xem**. Insight input thêm khoá `channel`.

---

## 5. Kiến trúc & flow đích

### 5.1 Channel Adapter (thay cho collector cứng)

```python
class ChannelAdapter(Protocol):
    code: str                      # "agoda"
    kind: ChannelKind              # inventory | price_only
    capabilities: Capabilities     # rooms_left, calendar, refundable_flag, taxes_included, force_currency, max_horizon
    parser_version: str
    block_markers: tuple[str, ...]

    def parse_url(self, url: str) -> ListingUrl: ...          # raise UnsupportedUrl
    async def verify(self, listing: ListingRef) -> ListingIdentity: ...  # tên, địa chỉ, toạ độ, external_id
    async def fetch_calendar(self, listing, start, days, spec) -> CalendarResult | None: ...  # None = không hỗ trợ
    async def probe(self, listing, checkin, spec: SearchSpec) -> ProbeResult: ...

REGISTRY: dict[str, ChannelAdapter]
def detect_channel(url: str) -> tuple[ChannelAdapter, ListingUrl]: ...
```

- Phần dùng chung tách khỏi Booking: `SessionManager` (key = `(channel, country)`), `Fetcher`, retry/fallback của `HybridCollector`, `classify_response(markers)`.
- Phần riêng mỗi kênh: URL builder, parser, calendar, block markers, bootstrap cookie.
- `RoomOffer.booking_room_id` → `external_room_id`; `ProbeResult.booking_hotel_id` → `external_id`.
- Mỗi kênh có bộ fixture HTML vàng + test parser; canary 1 khách sạn/kênh chạy hằng ngày.

### 5.2 Flow thêm khách sạn (thay form ở ảnh chụp)
1. Dán URL **bất kỳ kênh hỗ trợ** → `detect_channel` → báo ngay "Agoda · Melia Vinpearl Phú Quốc" (field đổi tên thành "Đường dẫn khách sạn", gợi ý các kênh hỗ trợ). Kênh chưa hỗ trợ (VD ivivu khi chưa có adapter) → thông báo rõ "chưa hỗ trợ ivivu", không phải "không phải Booking".
2. Listing đã có trong hệ thống → dùng chung (như hiện nay).
3. Listing mới → **verify ngay** (1 request: tên, địa chỉ, toạ độ, external_id) → `active` hoặc `broken` kèm lý do. Hiện nay URL sai chỉ lộ ra ở lượt quét sau.
4. Gợi ý gắn vào property có sẵn của tenant (cùng tên/toạ độ gần) hoặc tạo property mới; người dùng xác nhận.
5. Danh sách theo dõi: mỗi khách sạn một dòng, cột "Kênh": `Booking ✓ · Agoda ✓ · Traveloka + thêm`; trạng thái theo từng listing.
6. Sau này: gợi ý tự động listing trên kênh khác theo tên + toạ độ (người dùng duyệt).

### 5.3 Flow quét
- Run = **(mốc giờ × kênh)**: `trigger_key = "<phút UTC>:<channel>"`. Kênh bị chặn không làm trễ kênh khác; analytics chạy theo run như hiện tại, không đổi.
- Job = **listing**; hàng đợi riêng theo kênh (`arq:queue:collector:<channel>`) để mỗi kênh có số worker, timeout, max_tries riêng.
- **Ngân sách request toàn cục theo kênh** (token bucket trong Redis) bên trên rate limiter theo session hiện có.
- **Circuit breaker theo kênh**: tỉ lệ chặn > ngưỡng trong 15' → tạm dừng kênh, báo operator, các kênh khác chạy tiếp.
- Email cảnh báo: gom theo **mốc giờ** (chờ các run cùng mốc xong hoặc tới hạn chót) để mỗi tenant vẫn nhận 1 email/lượt.

### 5.4 Analytics 2 tầng
- Tầng listing = code hiện tại, đổi khoá → sự kiện/metric theo kênh.
- Tầng property (mới, rẻ, tính từ metric listing): hết phòng trên k/n kênh, giá thấp nhất so được, parity cho khách sạn self → sự kiện `channel_closed`, `parity_gap`.
- Compset theo kênh tham chiếu; trang chi tiết đêm hiện mọi kênh cạnh nhau.

### 5.5 Giảm chi phí probe (làm trước khi thêm kênh)
| Cách | Hiệu quả ước tính |
|---|---|
| **Quét theo tầng**: đêm 0–7 ngày ×3/ngày, 8–30 ×1/ngày, 31–90 vài ngày 1 lần | 90 → ~47 probe/listing-ngày (−48%) |
| Đêm xa dùng **calendar** (Booking GraphQL đã trả `avgPriceFormatted` cho cả khoảng trong 1 request) làm tín hiệu giá rẻ; chỉ probe trang đầy đủ khi đổi trạng thái/giá | giảm thêm, cần đo |
| HTML thô: chỉ giữ khi parse lỗi/rỗng + mẫu ngẫu nhiên, hoặc giảm còn 7–14 ngày | −50–90% lưu trữ |
| Dùng chung listing giữa tenant (đã có) | giữ |

### 5.6 Vận hành theo kênh
- Health theo kênh: % ok / chặn / rỗng, tỉ lệ có giá, tỉ lệ có tín hiệu phòng (phát hiện parser trôi), độ trễ.
- Nhiều nhà cung cấp proxy + failover; kiểm tra proxy trước khi mở run (sự cố 407 hiện tại cho thấy cần).
- Cảnh báo operator qua kênh thật (email/Telegram), không chỉ `LogAlerter`.
- Rà ToS/robots từng kênh; không đăng nhập; tốc độ lịch sự (giữ nguyên tắc sản phẩm 4).

### 5.7 Thứ tự kênh đề xuất
| Thứ tự | Kênh | Lý do | Ghi chú cần spike |
|---|---|---|---|
| 1 | Agoda | Quan trọng nhất ở VN/SEA sau Booking (research 01/10) | Có hiển thị "chỉ còn X phòng trên trang"? mức anti-bot? endpoint JSON? |
| 2 | Traveloka | Mạnh ở SEA/VN | Như trên |
| 3 | Trip.com / Expedia | Khách quốc tế (Trip.com: khách Trung/Hàn) | Expedia thị phần VN nhỏ hơn |
| 4 | ivivu / Mytour | OTA nội địa; khách sạn resort nội địa (như ảnh: Phú Quốc) | Inventory có phải bán lại từ OTA khác? Nếu có thì giá trị thấp |
| — | Google Hotels (price-only) | 1 request ra giá nhiều kênh → rẻ nhất cho parity | Không có rooms-left; ToS |

Mỗi kênh mới = spike 2–3 ngày (100 probe thử: tỉ lệ chặn, độ phủ trường, tín hiệu phòng) **trước** khi cam kết với khách.

---

## 6. Lộ trình (expand → migrate → contract, không gián đoạn Booking)

| Phase | Nội dung | Kết quả kiểm chứng |
|---|---|---|
| 0. Ổn định | Sửa proxy 407 + kiểm tra proxy trước run; cảnh báo operator thật; quét theo tầng; ngân sách request theo kênh (Redis) | Run có probe; số probe/ngày giảm ~½ |
| 1. Refactor không đổi hành vi | `ChannelAdapter` + registry; dời toàn bộ Booking vào adapter `booking`; `HotelRef` → `ListingRef`; session key `(channel, country)`; block markers theo adapter | Test hiện có pass nguyên; e2e Booking không đổi |
| 2. Schema expand | Thêm `channels`, `listings`, `tenant_channels`, cột `listing_id` (nullable) ở mọi bảng quan sát; backfill: mỗi hotel → 1 listing `booking` | Đếm dòng khớp; API cũ vẫn chạy |
| 3. Chuyển đọc/ghi | Worker/analytics/compset/API dùng `listing_id`; run theo (mốc × kênh); queue theo kênh | Dashboard hiện như cũ với Booking |
| 4. API/UI đa kênh | Form URL đa kênh + verify ngay; cột Kênh; kênh tham chiếu; chi tiết đêm nhiều kênh; OpenAPI + `gen:api` | Thêm/ngừng từng listing |
| 5. Kênh 2 (Agoda) | Spike → adapter → canary → mở cho 1 tenant | Tỉ lệ ok ≥ ngưỡng 7 ngày liền |
| 6. Contract | Bỏ `booking_*` khỏi `hotels`, `room_types`, schema API | |
| 7. Giá trị đa kênh | Tầng property, `parity_gap`, `channel_closed`, đưa vào email/bản tin | |
| 8. Thương mại | Gói theo số khách sạn × số kênh, giới hạn trong `tenant_channels` | |

Phase 0 và 1 có ích ngay cả khi chưa thêm kênh. Không làm phase 5 trước phase 2–3 (dữ liệu sẽ ghi đè nhau).

---

## 7. Câu hỏi chưa giải quyết
1. Kênh nào khách thật (tenant 9 và khách tiềm năng) cần nhất? Ảnh chụp dùng URL ivivu — là nhu cầu thật hay thử?
2. Khách có cần parity khách sạn mình giữa các kênh không, hay chỉ cần thêm đối thủ trên kênh khác?
3. Giá bán dự kiến / ngân sách proxy mỗi tháng? (quyết định số kênh và tần suất quét khả thi)
4. Tiền tệ chuẩn mỗi tenant: VND cố định, hay theo nước khách sạn như hiện nay?
5. Agoda/Traveloka/ivivu có hiển thị số phòng còn ổn định không, mức anti-bot ra sao — cần spike, chưa xác minh.
6. Có muốn tách "kênh thông báo" (Zalo/Telegram) chung lộ trình này không? Hiện ngoài phạm vi.
