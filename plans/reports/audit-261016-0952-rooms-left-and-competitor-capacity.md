# Audit: "soi số phòng còn lại" & "đối thủ có bao nhiêu phòng" (16/10/2026)

Phạm vi: đúng 2 chức năng sếp chốt — (1) tìm được tối đa đối thủ có bao nhiêu phòng, (2) scrape số phòng còn lại gần chính xác nhất. Các tính năng khác (AI brief, PMS, gợi ý giá, thị trường khu vực…) không đánh giá, chỉ nhắc khi chúng ăn theo số sai.

Kiểm chứng bằng:
- Đọc code collector → domain → repo → analytics → API → dashboard.
- DB thật (volume `scrapebooking_pgdata`, tenant 9 Rex): 19.816 room snapshot, 2.494 probe, 5 khách sạn (Rex = self; Reverie, Park Hyatt, Caravelle, Meander), 25/09 → 08/10.
- HTML thô đầy đủ trong MinIO (5 trang, run 176) + 5 fixture HTML thật.
- Test live 16/10: 3 request (proxy cấu hình trả 407 nên đi thẳng IP máy): trang Caravelle `no_rooms=30`; lịch GraphQL Reverie `nbRooms=30` và `nbRooms=10`.
- Nghiên cứu web (mục 6).

## 0. Kết luận nhanh

| Chức năng | Hoàn thiện | Ý chính |
|---|---|---|
| (1) Đối thủ có bao nhiêu phòng | **~15%** | Không có nguồn tự động; chỉ ô nhập tay "Số phòng" (cả 5 khách sạn đang trống); ước tính nội bộ bị trần ~10/loại phòng và không hiện cho đối thủ |
| (2) Số phòng còn lại chính xác | **~40%** | Thu tín hiệu đúng (badge = dropdown 100%), nhưng bỏ mất 14% số chính xác và **số cấp khách sạn hiển thị sai ở 86% ô heatmap** |
| Vận hành | **đang dừng** | Không có dữ liệu mới từ 08/10 07:10 UTC: proxy 407, image backend đã bị xoá, Docker tắt lúc bắt đầu kiểm tra |

Ba việc đem lại nhiều nhất, theo thứ tự:
1. Sửa nghĩa số cấp khách sạn: "N" chỉ khi mọi loại phòng chính xác, còn lại "≥N". Không tốn request.
2. Coi dropdown dưới trần là số chính xác, với trần riêng từng khách sạn; reparse lịch sử. Dữ liệu thô đã có sẵn; hết 14% quan sát bị ẩn số.
3. Thêm "thang nbRooms" trên lịch GraphQL để đo tổng phòng còn của cả khách sạn vượt trần 10/loại. Test live đã cho thấy Booking có xét nbRooms.

## 1. Luồng hiện tại

```
scheduler 06:00/14:00/22:00 → worker run_probe_hotel (backend/app/worker/jobs.py:103)
 ├ lịch GraphQL AvailabilityCalendar nbRooms=1, nbAdults=2 → 61 đêm: available, minLOS (collector/booking/calendar.py:24)
 ├ đêm available=false → KHÔNG probe, ghi skipped_calendar (jobs.py:158) → UI "H.CHẾ"
 ├ tầng quét: <14 đêm mọi lượt; 14–60 mỗi 20h; 60–90 mỗi 66h (jobs.py:39)
 └ trang khách sạn ?group_adults=2&no_rooms=1 (collector/booking/urls.py:43), curl_cffi + cookie Playwright, bị chặn → Chromium
    └ parser: mỗi loại phòng → badge "We have N left" + max(dropdown chọn số phòng) (parser.py:54-72, 261-271)
       └ derive_stock(badge, dd, cap=10) (domain/stock.py:12): badge→exact; dd≥10→capped "≥10"; dd 1–9 không badge→hidden (None)
          └ room_snapshots, lưu cả badge_count/dropdown_max thô (repo/snapshots.py:149)
analytics: exact_rooms_left = Σ rooms_left của loại phòng exact (analytics/rules.py:233) → hotel_date_metrics
 → API DateCell.exact_rooms_left → heatmap, thẻ đối thủ, cảnh báo, độ căng, gợi ý giá, AI brief (dashboard/src/components/marks.tsx:111)
occupancy cron: inventory = max sàn 30 ngày mỗi loại phòng, chỉ exact+capped (market/occupancy_service.py:46) → "≈% lấp đầy"
hotels.rooms_total ← nhập tay ở Cài đặt › Watchlist "Số phòng" (api/routers/watchlist.py:278)
```

## 2. Booking thực sự lộ gì (đo trên 19.816 quan sát thật)

| Dropdown max | Quan sát | Có badge | Badge = dropdown | Hệ thống gắn |
|---|---|---|---|---|
| 1–7 | 9.849 | 100% | 100% (0 lệch) | exact |
| 8 | 657 | 0 | – | **hidden (bỏ số)** |
| 9 | 2.163 | 0 | – | **hidden (bỏ số)** |
| 10 | 7.147 | 0 | – | capped "≥10" |
| >10 | 0 | – | – | – |

- Dropdown chính là số phòng còn của loại phòng, tính đến trần; badge chỉ là bản sao của dropdown khi ≤7.
- Trần là 10: cả 5 khách sạn có `<input name="maxrooms" value="10">`. JSON nhúng `b_rooms_available_and_soldout[].b_blocks[].b_nr_stays` và Apollo `termsOfSale.quantity` cho đúng giá trị dropdown. Trên trang không có nguồn nào vượt trần.
- Park Hyatt chưa bao giờ hiện quá 9; 43% quan sát dồn ở 9, trong khi `maxrooms=10`. Nhiều khả năng đây là trần riêng do khách sạn tự giới hạn phân bổ lên Booking (suy luận từ việc dữ liệu dồn ở 9, chưa có xác nhận). Dù nguyên nhân là gì, cũng phải dò trần theo từng khách sạn chứ không dùng hằng số 10.
- Live 16/10, `no_rooms=30`: Booking nhận là group search (`b_is_group_search=1`, `b_nr_rooms_needed=30`) nhưng mỗi loại phòng vẫn dừng ở 10. Không phá được trần qua trang khách sạn.
- Live 16/10, lịch GraphQL `nbRooms=30` so với `nbRooms=10` (Reverie, 31 đêm): 9 đêm chuyển từ còn sang hết. Một request lịch trả lời "khách sạn còn ≥N phòng đêm D?" cho cả tháng. Chưa kiểm: nbRooms tối đa được nhận, và Booking ghép loại phòng ra sao.

Theo khách sạn:

| Khách sạn | Loại phòng | Quan sát | Trần thấy | % hidden | % capped ≥trần |
|---|---|---|---|---|---|
| Caravelle | 11 | 5.427 | 10 | 13,5 | 56,3 |
| Reverie | 10 | 3.831 | 10 | 3,3 | 10,0 |
| Rex (self) | 10 | 3.775 | 10 | 3,3 | 78,9 |
| Park Hyatt | 10 | 3.753 | **9** | 45,2 | 0 (thực ra 9 = trần) |
| Meander | 9 | 3.030 | 10 | 4,6 | 24,2 |

## 3. Chức năng (2): số phòng còn lại

### Đang làm tốt
- Parser khớp trang thật: chọn đúng dòng giá của khách sạn (bỏ "Booking Basic" của đối tác), lọc dòng chỉ cho 1 khách, phát hiện chặn mềm (ô checkin rỗng) và trang hiện sai ngày, có fallback sang Chromium.
- Lưu thô badge_count + dropdown_max + HTML (MinIO). Sửa luật xong là tính lại được lịch sử (`sb reparse`).
- Trang chi tiết đêm theo loại phòng hiển thị đúng: số chính xác / "≥N" / ẩn.
- Sự kiện tăng/giảm phòng chỉ so cặp exact–exact, nên không báo nhiễu khi capped↔hidden.

### Lỗ hổng (theo mức độ)
1. **[Nghiêm trọng] Số cấp khách sạn là tổng riêng các loại phòng exact, nhưng hiển thị như số chính xác** (analytics/rules.py:233; marks.tsx:111, nhãn "Còn N phòng (Booking.com báo chính xác)").
   - Trong 509 ô mới nhất: 49 (10%) đủ exact; 437 (86%) là tổng thiếu.
   - Trung bình ô hiện 14,3 phòng, trong khi sàn thật là 49,9; 16 ô báo ≤3 phòng sai.
   - Ví dụ: Rex 12/12 (run 157) có 7 loại "≥10" và 1 loại còn 2, ô hiện "2" với màu "sắp hết", sàn thật ≥72.
   - Số này nuôi cảnh báo "đối thủ chỉ còn N phòng", độ căng, gợi ý giá, AI brief.
   - `exact_share` trung bình 93,4% (515 ô) nhưng chỉ đếm "có ít nhất 1 loại phòng exact", nên nhãn "tỷ lệ số chính xác" trên UI càng làm người dùng tin số sai.
2. **[Cao] Bỏ số chính xác 8–9.**
   - 2.820 quan sát (14,2%) bị gắn hidden với rooms_left=None, dù dropdown chính là tồn phòng. Occupancy cũng loại hidden.
   - Cách sửa: trần theo listing (giá trị lớn nhất hay gặp, kèm `maxrooms`). dd < trần → exact; dd = trần → "≥trần".
   - Mô phỏng trên dữ liệu thật: quan sát exact 49,7% → 55,8%, hidden 14,2% → 0%, capped 36,1% → 44,2% (số 9 của Park Hyatt thành "≥9").
   - Nhưng ô "đủ exact" chỉ tăng 9,6% → 11,2%, vì hầu hết ô có ít nhất 1 loại phòng chạm trần. Đòn bẩy thật ở cấp khách sạn là mục 1 (hiển thị khoảng) và thang nbRooms (P1).
3. **[Cao] Trần 10 mỗi loại phòng.** 36% quan sát chỉ biết "≥10" (Rex 79%, Caravelle 56%). Khách sạn lớn vào ngày thường gần như không đo được. Hướng xử lý ở mục 5, P1.
4. **[Cao] Không bao giờ thấy "hết phòng" trong 61 ngày tới.**
   - Đêm lịch báo không còn thì bị bỏ qua và gắn "H.CHẾ (không phải hết phòng)" (jobs.py:158, rules.py:63).
   - Dữ liệu: cả 7 sold_out đều nằm ở 84–90 ngày tới (ngoài tầm lịch).
   - Đây là tín hiệu đắt giá nhất của việc "soi phòng".
5. **[Trung bình] Probe lỗi xoá trạng thái tốt gần nhất** (analytics/service.py:274, 371). Ô thành "LỖI" thay vì giữ số cũ kèm cờ "dữ liệu cũ".
6. **[Trung bình] Chỉ tìm 2 người lớn, 1 phòng.** Loại phòng chỉ cho 1 khách không bao giờ thấy, nên cả tổng lẫn inventory đều thiếu.
7. **[Thấp] Nhãn và chi tiết.**
   - pickup_24h ở đêm xa thực ra là 66–74h.
   - CSV thiếu nhãn "restricted".
   - `room_types_sold_out` phình lên khi Booking đổi ID loại phòng.

### Vận hành (ảnh hưởng trực tiếp tới "scrape được số liệu")
- Trong 22 ngày (25/09 → 16/10) chỉ **5 ngày có dữ liệu** (25/09, 01/10, 02/10, 07/10, 08/10). Lý do: proxy chết, và stack chạy trên máy dev nên không chạy liên tục. Không có chuỗi liên tục thì không tính được pickup và nhịp giảm phòng của đối thủ.
- Không có probe thành công từ 08/10 07:10 UTC; run 181–190 đều 0 ok. Khi chạy đủ: ~106 request trang/khách sạn/ngày (07/10).
- `check-proxy` hôm nay: 160.250.166.88:20084 trả 407. Đây là lần chết thứ 3 trong 2 tuần (01/10, 02/10, 08/10), hệ thống chỉ có 1 proxy, và `OPS_ALERT_EMAILS` chưa đặt nên không ai được báo.
- Image backend (api/worker/scheduler) không còn trong Docker; muốn chạy lại phải build lại.

### Chấm điểm (2)

| Phần | Điểm | Lý do |
|---|---|---|
| Thu tín hiệu thô từ trang | 85% | Đúng, bền, có fallback |
| Diễn giải theo loại phòng | 60% | Bỏ 8–9; trần 10 cố định |
| Tổng hợp cấp khách sạn & hiển thị | 20% | 86% ô sai nghĩa |
| Độ phủ (hết phòng, 1 khách, >10/loại) | 35% | Hết phòng ≤61 ngày không thấy |
| Vận hành liên tục | 20% | 1 proxy, chết không báo |
| **Tổng** | **~40%** | |

## 4. Chức năng (1): đối thủ có bao nhiêu phòng

Hiện có:
- `hotels.rooms_total` nhập tay ở Cài đặt › Watchlist "Số phòng" (1–5000). DB: cả 5 khách sạn đều NULL. Giá trị này chỉ dùng cho quy tắc compset 50% và làm mẫu số "≈% lấp đầy".
- Ước tính nội bộ `inventory` (market/occupancy_service.py:46): max sàn trong 30 ngày của từng loại phòng, chỉ lấy exact và capped, nên bị trần 10 mỗi loại. Park Hyatt còn tệ hơn: không bao giờ có capped, 8–9 lại bị loại, nên mỗi loại phòng tối đa chỉ 7.
  - So với số phòng công bố (mục 6; trích từ kết quả tìm kiếm, cần kiểm lại trước khi lưu):

    | Khách sạn | Ước tính hệ thống (`occupancy_estimates`, lượt mới nhất) | Công bố | Tỷ lệ |
    |---|---|---|---|
    | Rex | 94 | 286 | 33% |
    | Caravelle | 93 | 333–335 | 28% |
    | Reverie | 64 | 286 (224 phòng + 62 suite) | 22% |
    | Park Hyatt | 63 | 245 | 26% |
    | Meander | 54 | 42 phòng + giường dorm | **129%** |

  - Meander bị đếm vượt vì Booking bán giường dorm như một loại phòng. Cộng theo loại phòng có thể ra *nhiều hơn* số phòng thật, nên mọi con số ước tính phải ghi rõ đơn vị bán (phòng / giường).
  - Tỷ lệ ô đủ tin để hiện "≈%": Reverie 96%, Meander 53%, Park Hyatt 33%, Rex 21%, Caravelle 7,5%.
- Không có chỗ nào hiện con số này cho đối thủ. Nó chỉ làm mẫu số, và UI chỉ vẽ occ_mid.

Lỗ hổng:
1. Không có nguồn tự động cho tổng phòng công bố. Roadmap 5.6 đánh ✅ nhưng chỉ làm phần nhập tay.
2. Ước tính sai theo nhiều cách cùng lúc:
   - bị trần 10 mỗi loại phòng;
   - bỏ qua hidden;
   - cửa sổ 30 ngày nên co lại vào mùa cao điểm;
   - khi Booking đổi ID loại phòng thì bị cộng trùng hoặc coi là đã bán hết.
3. Mẫu số và độ phủ lệch nhau: `denom = max(Σinventory, rooms_total)` nhưng `coverage = known/Σinventory` (market/occupancy.py:94, 116). Vì vậy nhập rooms_total làm "≈%" nhảy thành "đáng tin" dù không có thêm thông tin.
4. `rooms_total` dùng chung cho mọi tenant (ai cũng ghi đè được) và không lưu nguồn, người nhập.

Chấm điểm: ~15% (lưu trữ + nhập tay ~10, ước tính ~5, nguồn tự động 0, hiển thị cho đối thủ 0).

## 5. Đề xuất "làm 1 function thật tốt" (chưa code, theo thứ tự)

**P0 — sửa nghĩa số (2–3 ngày, không thêm request; `exact_rooms_left` có 25 chỗ dùng ở backend và 13 file dashboard; test `tests/unit/test_stock.py:14` đang khoá luật cũ (None, 4) → HIDDEN)**
1. Số cấp khách sạn thành khoảng: sàn = Σ exact + Σ "≥". Hiện "N" khi mọi loại phòng exact, còn lại "≥N". Cảnh báo, độ căng, gợi ý giá dùng sàn hoặc chỉ dùng khi đủ exact.
2. `derive_stock` theo trần từng listing, rồi reparse lịch sử: 14% quan sát hết bị ẩn số (exact 49,7% → 55,8%).
3. Giữ trạng thái tốt gần nhất khi probe lỗi.
4. Vận hành: proxy mới, ≥2 nhà cung cấp, `OPS_ALERT_EMAILS`, build lại image.

**P1 — tăng độ chính xác (3–5 ngày)**
5. Thang nbRooms trên lịch GraphQL: mỗi lượt quét 5–8 request/khách sạn (N = 5, 10, 15, 20, 30…). Kết quả là tổng phòng còn của cả khách sạn theo bậc cho 61 đêm, kết hợp với sàn lấy từ trang. Chi phí: 15–24 request/khách sạn/ngày, tức +15–25% so với ~106 request trang hiện nay. Trước đó cần thử: nbRooms tối đa, và so với Σ loại phòng ở những đêm đã đủ exact.
6. Probe các đêm "lịch báo không còn" trong 14–30 ngày tới để tách hết phòng / đóng nhận khách / min-stay.
7. (Tuỳ chọn) Mỗi ngày probe thêm 1 người lớn cho đêm gần, để thấy loại phòng 1 khách.

**P2 — chức năng (1)**
8. "Booking mở bán tối đa" = max dài hạn (90–365 ngày) của tổng còn cấp khách sạn (thang nbRooms + Σ loại phòng). Hiển thị cho từng đối thủ dạng "≥N phòng trên Booking".
9. Tổng phòng công bố: lấy bán tự động từ nguồn công khai (mục 6). Thứ tự nguồn: web chính thức của khách sạn/chuỗi → trường "Number of Rooms" có cấu trúc của Trip.com → danh bạ MICE (Northstar, TTG MICE) → Wikipedia/thông cáo báo chí. Lưu kèm URL nguồn, ngày, người xác nhận; cần 2 nguồn khớp nhau; không ghi đè chung giữa các tenant. Số phòng gần như không đổi, chỉ cần lấy một lần rồi rà soát định kỳ.
10. Một màn hình cho mỗi đối thủ: Tổng phòng (kèm nguồn) · Booking mở bán tối đa · Còn đêm nay (N / ≥N) · heatmap 30 đêm.

## 6. Nghiên cứu web (16/10)

Nhãn: [CHƯA XÁC MINH] = chỉ có trích đoạn kết quả tìm kiếm hoặc là suy luận; [cũ] = trước 2023.

**Dropdown và trần 10**
- Booking lưu tồn phòng theo *loại phòng × ngày*, dùng chung cho mọi gói giá ([Connectivity API: availability](https://developers.booking.com/connectivity/docs/b_xml-availability)). Điều này khớp dữ liệu: mọi dòng giá của một loại phòng có cùng dropdown.
- Không tìm thấy tài liệu công khai nào nêu trần 10. Các loại hạn chế chính thức chỉ gồm độ dài lưu trú, không nhận khách/trả phòng, đặt trước ([Partner Help](https://partner.booking.com/en-us/help/reservations/restrictions/setting-reservation-restrictions-your-property)). Vậy `maxrooms=10` trên trang là bằng chứng tốt nhất; 2 scraper thương mại (Apify crawlio, aurith) cũng gắn "capped" tại giá trị tối đa của trang.
- Dropdown = min(số phòng Booking *được phép bán* của loại phòng, 10). Đó là **phần phân bổ (allotment) cho Booking, không phải phòng vật lý**; channel manager thường giới hạn số phòng đẩy lên từng kênh ([Sirvoy](https://help.sirvoy.com/en_US/limit-how-many-rooms-are-shared-with-a-booking-channel)). Trần 9 của Park Hyatt nhiều khả năng là allotment [CHƯA XÁC MINH].

**Badge "We have N left"**
- Không có tài liệu về ngưỡng; dữ liệu của ta cho thấy N = 1–7.
- Câu chữ "on our site" / "at this price" xuất phát từ cam kết của Booking với CMA Anh năm 2019 ([PDF](https://assets.publishing.service.gov.uk/media/5c5ab0e140f0b676b3222ab9/Booking.com_B_V_undertakings.pdf)) [cũ, vẫn hiệu lực].
- Which? năm 2019 từng thấy "1 room left" trong khi khách sạn vẫn bán được 34 phòng [cũ]. Đây là thêm một lý do để luôn ghi rõ đây là "số trên Booking".

**Tín hiệu khác**
- JSON nhúng trên trang và các scraper mã nguồn mở đều chỉ cho số theo từng gói, không bao giờ vượt trần.
- Schema công khai của lịch GraphQL không có số đếm ([Scrapfly 2026](https://scrapfly.io/blog/posts/how-to-scrape-bookingcom)). Việc lịch có xét `nbRooms` là phát hiện riêng của ta. Còn phải kiểm: N phòng là tính trong một loại phòng hay cộng nhiều loại.
- Booking Demand API (affiliate) có trường `number_available_at_this_price` ([docs](https://developers.booking.com/demand/docs/open-api/demand-api/accommodations/accommodations/availability)). Đây là nguồn chính thức, không dính anti-bot, nhưng cần được duyệt affiliate; chưa rõ có bị trần không.

**Công cụ thương mại**
- Không hãng nào công khai cam kết đếm đúng số phòng còn của đối thủ. Họ bán cờ hết phòng/hạn chế, so giá, và chỉ số cầu (Lighthouse, Atomize, SiteMinder).
- Công suất thật của đối thủ chỉ có từ dữ liệu khách sạn tự đóng góp, ví dụ STR/CoStar (chỉ số gộp, tối thiểu 4 khách sạn).
- Smartness viết thẳng rằng ước tính công suất đối thủ là "Not exactly".
- → Nếu làm đúng (số chính xác khi ≤ trần, "≥N" khi chạm trần, phát hiện hết phòng, tổng phòng có nguồn), đây là điểm khác biệt thật cho bản free.

**Kỹ thuật xếp hạng**
- Phòng còn: badge (N ≤ 7) ≈ dropdown 1–9 (miễn phí) > thang `nbRooms` trên lịch (~5 request/khách sạn/tháng, cần kiểm cách ghép loại phòng) > badge "at this price" ở trang kết quả tìm kiếm (rẻ, quét cả thị trường, chỉ gói rẻ nhất) > Demand API (cần duyệt) > suy từ mức giảm theo thời gian.
- Không dùng được: `no_rooms=N` trên trang khách sạn; số của OTA khác (allotment khác).
- Tổng phòng: web chính thức > Trip.com "Number of Rooms" > danh bạ MICE > Wikipedia/thông cáo > Agoda/Tripadvisor/Expedia/Booking (chưa xác minh có trường này, anti-bot cao) > cận dưới từ chính dữ liệu của ta (chỉ đo allotment Booking).

## 7. Đã triển khai (16/10, chưa commit)

Kế hoạch: `plans/261016-1030-rooms-left-accuracy/plan.md`. Dữ liệu dev đã migrate 0016, tính lại tồn phòng và phân tích lại.

| | Trước | Sau |
|---|---|---|
| Loại phòng exact / capped / hidden | 49,7 / 36,1 / 14,2% | 55,8 / 44,2 / 0% |
| Ô khách sạn hiện tổng thiếu như số chính xác | 437/509 | 0 ("≥N" khi chưa biết trần) |
| Ô báo "≤3 phòng" sai | 16 | 0 |
| Hết phòng trong 61 ngày tới | không bao giờ phát hiện | probe trang + bắc cầu D-1 |
| Tổng phòng còn > 10/loại | không đo được | thang nbRooms tới 100 (live: Caravelle ≥100/đêm) |
| Số phòng đối thủ | trống | công bố + nguồn (5/5) và "Booking từng mở bán ≥N" |

Kiểm live thêm: lịch `nbRooms` tính tổng khách sạn (Reverie 30/10 trang Σ 14, lịch còn ở 15); nhận N tới 100, 120 lỗi 500.

## Câu hỏi chưa giải quyết
1. "Có bao nhiêu phòng" sếp muốn là tổng phòng vật lý (công bố) hay số đối thủ mở bán trên Booking? Đề xuất làm cả hai, tách nhãn.
2. Lịch GraphQL nhận nbRooms tối đa bao nhiêu (scraper thương mại cho 1–30, khớp với form)? Khi nbRooms>1, Booking ghép nhiều loại phòng thế nào? Cần thử bằng cách so với Σ loại phòng ở những đêm đã đủ exact.
3. Trần 9 của Park Hyatt có đúng là allotment không? Có khách sạn nào trần <9 không? Ngưỡng badge (7) có giống ở thị trường khác không? Cần thêm mẫu ngoài 5 khách sạn này.
4. Có nên xin Booking Demand API (affiliate) để lấy `number_available_at_this_price` chính thức không?
5. Proxy và ngân sách cho bản free (nhiều user thì nhiều khách sạn)?
6. Bản free có cần tự đăng ký không? Hiện operator phải tạo tenant thủ công.
