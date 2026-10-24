# Nghiên cứu: quét thị trường theo quận + bộ lọc Booking.com

Thời điểm: 16/10/2026 17:22–18:30 (Asia/Saigon).
Yêu cầu: "Sửa thành quét theo quận — crawl khu vực theo filter từ booking.com ⇒ thị trường khu vực, lượng trống phòng của khách sạn mình" (ảnh: trang kết quả Vũng Tàu, 932 chỗ nghỉ, các bộ lọc Căn hộ / 5 sao / Giáp biển / Khách sạn…).

Kiểm chứng bằng:
- Code: `backend/app/marketscan/*`, `collector/booking/calendar.py`, `worker/capacity_ladder.py`, fixture `tests/fixtures/html/searchresults_hcmc_2026-10-09.html.gz`. DB dev: `market_areas` 0 dòng → khung khu vực chưa từng chạy trên dữ liệu thật.
- Test live Booking.com qua trình duyệt trong app (IP máy, ~35 request, 17:30–18:20): Vũng Tàu (city −3733750), Q1 TP.HCM (district 2088), Bãi Sau (district 16195, landmark 258614), Bãi Trước (landmark 258615), một toạ độ (LATLONG); đêm T7 17/10 và T4 18/11; 1 phòng 2 người lớn trừ khi ghi khác.
- 4 lượt tìm web (mục 8). Không tìm thấy tài liệu công khai nào về `unavailabilityPercent` hay `FullSearch` → số liệu mục 2 là nguồn chính.

Mục lục: 0 Kết luận · 1 Hệ thống hiện tại · 2 Bằng chứng live · 3 Đề xuất · 4 Chi phí · 5 Rủi ro · 6 Không làm được · 7 Lộ trình · 8 Nguồn · Câu hỏi mở

## 0. Kết luận nhanh

**Có — cải tiến lớn, và rẻ hơn cách đang làm.** Một lượt tìm kiếm Booking chứa sẵn dữ liệu đo "thị trường khu vực" theo quận/bán kính + phân khúc, không cần mở từng trang khách sạn:

| Tín hiệu (kiểm live) | Cho biết gì | Hệ thống hiện tại |
|---|---|---|
| `searchMeta.availabilityInfo.unavailabilityPercent` | % chỗ nghỉ của khu vực đã kín đêm đó, Booking tự tính (VT T7 17/10: 32%; Q1: 43%; Q1 T4 18/11: 21%) | có trong trang tải mỗi đêm nhưng bỏ |
| Facet ~20 nhóm bộ lọc kèm số đếm | số chỗ còn phòng theo loại hình, hạng sao, quận, khoảng cách, giáp biển, địa danh… trong 1 request | chỉ dùng chia lát, không lưu |
| Histogram thanh "Ngân sách" | phân bố giá 50 cột của **mọi** chỗ còn phòng khớp bộ lọc | không đọc |
| GraphQL `FullSearch` | 100 kết quả/request; đổi khu vực/ngày/bộ lọc/số phòng ngay trong 1 phiên | SSR 25 thẻ, `offset` bị bỏ qua → 25 request mới thấy 63% |
| `nbRooms = N` (≤ 30) | số KS còn bán được ≥ N phòng đêm đó → **thang phòng trống của cả thị trường** | không có |

Điểm mấu chốt: với khách sạn, "N chỗ còn phòng" (thứ hệ thống đang đo) gần như đứng yên giữa T7 và ngày thường (VT, chỉ KS: 208 vs 210), còn thang nbRooms đổi rõ (≥ 10 phòng: 122 vs 150; ≥ 20: 79 vs 104). Chỉ báo thị trường hiện tại đang đo đúng thứ ít biến động nhất.

"Lượng trống phòng của KS mình": tìm kiếm khu vực **không** thay được phép đo KS mình (trần 30 phòng, mỗi request 1 đêm). Giữ probe trang + thang lịch hiện có (tới 100 phòng, 1 request/nấc cho cả cửa sổ). Cái mới là đặt số đó **cạnh** thị trường: KS mình còn X phòng, giá ở phân vị P, trong khi chỉ Y% KS cùng phân khúc trong 3 km còn bán được ≥ 10 phòng.

Khuyến nghị: giữ khung `market_areas`, thay lõi đo theo 3 pha (mục 7). Pha 0 không tốn request thêm. Điều kiện chạy thật: proxy mới (proxy hiện tại 407 từ 08/10).

## 1. Hệ thống hiện tại

Khung "thị trường khu vực" có từ 02/10 (`app/marketscan/`, migration 0011), tenant chọn city/district qua autocomplete. Mỗi ngày:
1. Danh sách 14 đêm: 1 request SSR/đêm → "N properties found" + giá 25 thẻ đầu (`service.py:135`).
2. Đêm khám phá: chia lát bộ lọc × thứ tự tới khi thấy ≥ 98% (`slices.py:31`), trần 60–100 request. Live 02/10: 25 request → 234/370 KS (63%).
3. Chi tiết: top 300 KS (theo số review) × horizon 30 đêm bằng probe trang KS (`scheduling.py`, tầng `worker/jobs.py:51`): ~30 trang/KS/ngày ≈ **9.000 request/ngày/khu vực**.

Lỗi/thiếu trong code, đúng bất kể có làm đề xuất hay không:

| # | Chỗ | Vấn đề | Hậu quả |
|---|---|---|---|
| 1 | `parser.py:212` | `total` lấy `pagination.nbResultsTotal` trước. Số này gồm KS **ngoài khu vực** Booking tự nới thêm khi khu vực sắp kín (`totalAutoextendedAvailable`) | Đêm căng nhất lại báo còn phòng cao hơn thật. Live: VT KS 4★ T7: tiêu đề "13", `nbResultsTotal` 14 (thêm 1 KS ở Long Hải) |
| 2 | `parser.py:156` (`_apollo_card`) | không đọc `persuasion.autoextended` của thẻ | KS ngoài khu vực bị ghi vào `market_area_hotels` |
| 3 | `parser.py:127`, `_from_apollo` | `unavailabilityPercent` và facet có trong mỗi trang nhưng bị bỏ | mất chỉ báo thị trường miễn phí |
| 4 | `stats.py` | thống kê giá tính trên mẫu khi độ phủ < 98% | giá khu vực lệch về KS phổ biến |

## 2. Bằng chứng live (16/10/2026)

### 2.1 `availabilityInfo`

| Truy vấn | Còn phòng (trong khu vực) | Nới thêm | unavailability % | Tổng suy ra |
|---|---|---|---|---|
| TP.HCM, T6 9/10 (fixture) | 3.944 | 0 | 21 | ≈ 4.990 |
| Vũng Tàu, T7 17/10 | 668 | 0 | 32 | ≈ 982 |
| Q1 (district 2088), T7 17/10 | 819 | 0 | 43 | ≈ 1.437 |
| Q1, T4 18/11 | 1.123 | 0 | 21 | ≈ 1.420 |
| VT + lọc KS (`ht_id=204`), T7 | 208 | 0 | 79 | — |
| VT + KS 4★, T7 | 13 | 1 | 98 (`hasLowAvailability` = true) | — |

- `unavailabilityPercent` = 1 − còn phòng / tổng **toàn khu vực**. Có bộ lọc thì % vẫn chia cho tổng cả khu vực (208/0,21 ≈ 990), nên không phải % của phân khúc. Dùng giá trị không lọc làm chỉ báo khu vực; phân khúc phải tự có mẫu số (2.2).
- Trường này nằm trong cùng object `searchMeta.availabilityInfo` mà parser hiện tại đã đọc (`parser.py:215`) → Pha 0 làm được với cách tải hiện tại.

### 2.2 Facet (số đếm theo từng lựa chọn bộ lọc)

- VT T7 17/10 (trang trình duyệt): 22 nhóm. Ví dụ: KS 208, căn hộ 366, biệt thự 33; 4★ 148, 5★ 60 (mọi loại hình); giáp biển 330; cách tâm < 1 km 38, < 3 km 608; gần Tượng Chúa 87, Bãi Trước 24; ăn sáng, hoàn huỷ, tiện nghi, chuỗi.
- Facet có điều kiện theo bộ lọc khác: thêm `ht_id=204` thì facet `class` cho ngay số KS còn phòng theo hạng sao (1★ 18, 2★ 43, 3★ 47, 4★ 13, 5★ 13). Không cần request riêng cho từng hạng sao.
- Tìm cả TP.HCM: facet `di` cho số còn phòng của 25 quận trong 1 request (Q1 = 1.107 đêm 9/10). Số đếm facet không bị giới hạn 1.000.
- Fixture TP.HCM trong repo chỉ còn 6 nhóm vì kho Apollo đã được rút gọn khi lưu (`tests/fixtures/html/README.md`). Kho Apollo nhúng trong trang SSR thật (đọc từ thẻ script) có đủ 22 nhóm, gồm histogram.
- Khi `hasLowAvailability` = true, facet có thể đếm cả vùng nới thêm (VT KS 4★: facet `class` 20/50/55/14/18 so với 18/43/47/13/13 khi chỉ lọc KS) → lúc đó facet chỉ là xấp xỉ.

Mẫu số phân khúc: trang không chọn ngày (ảnh của anh) cho tổng từng phân khúc: VT 932; KS 269; căn hộ 423; biệt thự 152; 5★ 123; giáp biển 458. Ước tỉ lệ kín T7 17/10 (ảnh chụp lúc khác nên chỉ minh hoạ): KS ≈ 23%, căn hộ ≈ 13%, 5★ ≈ 51%, giáp biển ≈ 28%, **biệt thự ≈ 78%** (T4 18/11 còn 158 biệt thự, T7 chỉ 33 → khách nhóm cuối tuần dồn vào biệt thự).

### 2.3 Histogram giá

- `filters[price].sliderOptions { min, max, histogram[50] }`. Min/max tự co giãn: VT KS 100k–2tr; Q1 200k–4tr.
- Cột là chiều cao tương đối (cột cao nhất = 100). VT KS: bước 6,25 → cột cao nhất = 16 KS; tổng ≈ 187/208 KS, phần còn lại nằm trên max (cột cuối không gom "2tr+").
- Áp theo bộ lọc. Dùng làm phân bố giá cả phân khúc cho đêm xa (1 request). Đêm gần lấy giá đầy đủ từ liệt kê.

### 2.4 GraphQL `FullSearch`

- Cùng endpoint `/dml/graphql` với lịch (`collector/booking/calendar.py:7`). Header: csrf token của trang, `x-booking-context-action-name: searchresults_irene`, `x-booking-topic: capla_browser_b-search-web-searchresults`, `apollographql-client-name: b-search-web-searchresults`. Chưa thử bớt header.
- Nút "Load more results" của Booking gửi chính query này với `pagination { rowsPerPage: 25, offset: 100 }`.
- Query tối giản (chỉ trường cần) được chấp nhận. `rowsPerPage` 100 chạy; 250 → bị hạ về 100. `rowsPerPage: 1` → chỉ lấy số đếm + facet + histogram.
- Trong 1 phiên đổi được `location` (CITY / DISTRICT / LANDMARK / LATLONG), `dates`, `filters.selectedFilters` ("ht_id=204;class=4"), `nbRooms`/`nbAdults`, với `useSearchParamsFromSession: false`.
- Booking cắt 1.000 kết quả/truy vấn (tài liệu Apify) → liệt kê theo quận/phân khúc; số đếm thì không bị cắt.

```graphql
query FullSearch($input: SearchQueryInput!) {
  searchQueries { search(input: $input) { ... on SearchQueryOutput {
    pagination { nbResultsPerPage nbResultsTotal }
    searchMeta { availabilityInfo { hasLowAvailability unavailabilityPercent
                 totalAvailableNotAutoextended totalAutoextendedAvailable } }
    filters { field options { urlId count } sliderOptions { min max histogram } }
    results { basicPropertyData { id pageName starRating { value } }
              blocks { finalPrice { amount currency } onlyXLeftMessage { translation } }
              soldOutInfo { isSoldOut } persuasion { autoextended } }
  } } }
}
```

### 2.5 Thang nbRooms cấp thị trường

| Vũng Tàu, chỉ KS (`ht_id=204`) | T7 17/10 | T4 18/11 |
|---|---|---|
| còn bán được ≥ 1 phòng | 208 | 210 |
| ≥ 5 phòng | 170 | 183 |
| ≥ 10 phòng | 122 | 150 |
| ≥ 20 phòng\* | 79 | 104 |
| Sàn tổng phòng còn (Σ theo nấc) | ≥ 2.288 | ≥ 2.732 |
| Theo hạng sao, ≥ 10 phòng | 3★ 29 · 4★ 7 · 5★ 12 | 3★ 46 · 4★ 11 · 5★ 14 |

\*Test dùng 2 người lớn/phòng nên nấc 20 bị kẹp ở 30 người lớn. Booking kẹp `nbRooms` và `nbAdults` ≤ 30 (gửi 50 → nhận 30).

Q1 T7 17/10: mọi loại hình ≥ 1: 819, ≥ 5: 439, ≥ 10: 259; chỉ KS ≥ 1: 393, ≥ 5: 263, ≥ 10: 166, ≥ 30: 109.

### 2.6 "Quận" trên Booking

| Kiểu | Ví dụ | Kết quả |
|---|---|---|
| district (TP.HCM) | Q1 = 2088; facet `di` có 25 quận | dùng tốt. Quận chồng lấn ("City Centre" 6750 với Q1) → không cộng dồn |
| district (Vũng Tàu) | "Back Beach" 16195 | **0 KS trong quận, 845 KS "nới thêm"** → không dùng được. Tìm cả TP VT không có facet `di` |
| landmark | Bãi Sau 258614: 736 còn phòng, facet khoảng cách tính từ địa danh (< 1 km 355, < 3 km 637); Bãi Trước 258615 | dùng được |
| LATLONG | một toạ độ (vd KS mình) → thẻ ghi "200 m from map centre", facet < 1 / < 3 / < 5 km | dùng được: bán kính quanh KS mình |
| hotel | tìm theo id KS | Booking quay về tìm cả TP → không dùng |

Từ 1/7/2025 VN bỏ cấp quận/huyện và Bà Rịa–Vũng Tàu nhập TP.HCM, nhưng Booking vẫn dùng địa lý cũ ("District 1", "Ba Ria - Vung Tau"). "Quận" trong hệ thống = thực thể district của Booking (dest_id), không phải phường mới.

### 2.7 Tín hiệu trên từng thẻ kết quả

`blocks[].onlyXLeftMessage` ("We have 3 left at this price", chỉ cho gói rẻ nhất), `finalPrice`, `freeCancellationUntil`, bữa sáng, `soldOutInfo`, `persuasion.autoextended / preferred`, `showAdLabel`, `visibilityBoosterEnabled`, `isNewlyOpened`, giảm giá/Genius. Which? (2019) cho thấy câu "chỉ còn X phòng" không luôn đúng → chỉ là tín hiệu phụ.

### 2.8 Chống bot

Lần tải đầu đi qua challenge JS (`chal_t` trên URL). Autocomplete trả HTML (bị chặn) sau ~4 lượt cách 0,6 s. ~20 lượt GraphQL cách 1,2–2 s đều 200. Chưa thử GraphQL tìm kiếm bằng curl_cffi (lịch GraphQL hiện chạy được theo cách này).

## 3. Đề xuất

### 3.1 Khu vực = quận hoặc bán kính
`market_areas` thêm `geo_mode`:
- `district`: dest_id Booking (TP.HCM, Hà Nội).
- `landmark`: dest_id địa danh + `distance=1000|3000|5000`.
- `radius`: LATLONG = toạ độ KS self (đã có `hotels.lat/lng`) + `distance=…`. Mặc định cho nơi Booking không có quận dùng được (Vũng Tàu).
- `city`: như hiện tại.

### 3.2 Phân khúc bằng bộ lọc
Thêm `segment_nflt`, ví dụ `ht_id=204` (khách sạn). Gộp resort/aparthotel bằng `ht_id=204;ht_id=206;ht_id=219` (giả định các lựa chọn cùng nhóm là OR, cần kiểm). Hạng sao không cần request riêng: facet `class` trong cùng request đủ 1–5★.

### 3.3 Chỉ số mỗi đêm
Mỗi đêm, mỗi khu vực: nấc N ∈ {1, 2, 3, 5, 10, 20, 30}, `rowsPerPage = 1` → 7 request nhỏ.
- `c(N)` = `totalAvailableNotAutoextended` (theo phân khúc; theo từng hạng sao/quận lấy từ facet).
- Tỉ lệ kín khu vực (Booking): `unavailabilityPercent` của nấc 1, không lọc.
- Tỉ lệ kín phân khúc: 1 − c(1) / mẫu số. Mẫu số = max c(1) trong 60 đêm tới (không tốn request, là cận dưới nên tỉ lệ kín ra cận dưới), hoặc trang không chọn ngày 1 lần/ngày.
- Mức căng: c(10) / c(1), so với cùng thứ của 4 tuần trước (VT KS: T7 17/10 59%, T4 18/11 71%).
- Phòng trống thị trường (sàn): Σ (c(N_k) − c(N_k+1)) · N_k + c(30) · 30.
- Giá: histogram (mọi đêm) + giá đầy đủ từ liệt kê (đêm gần).

Tuỳ chọn: liệt kê id ở mỗi nấc (`rowsPerPage = 100`) cho 14 đêm gần → mọi KS trong khu vực có khoảng phòng còn [N_k, N_k+1 − 1], đủ để thay quét chi tiết top 300.

Tên chỉ số theo PRODUCT.md: "mức căng thị trường trên Booking.com", không gọi là occupancy.

### 3.4 KS mình đặt cạnh thị trường
- Giữ: probe trang (chính xác ≤ 10/loại phòng) + thang lịch (≤ 100 phòng).
- Thêm: phân vị phòng còn của KS mình trong thang phân khúc; phân vị giá trong phân bố giá; hạng hiển thị trong khu vực; Booking có gắn "We have N left" cho KS mình không.
- Ví dụ một dòng: "T7 17/10 · KS 3–5★ trong 3 km: 59% còn bán ≥ 10 phòng (thường 71%) · Bạn còn ≈ 25 phòng · Giá bạn ở P62."

## 4. Chi phí request (1 khu vực, horizon 30 đêm)

| Việc | Hiện tại | Đề xuất |
|---|---|---|
| Chỉ báo thị trường | 14 SSR/ngày, 1 số/đêm | 7 GraphQL nhỏ × 30 đêm = 210/ngày |
| Danh sách + giá đầy đủ | 14 SSR + ≤ 60 lát (63% sau 25 lát) | ⌈n/100⌉ × 14 đêm: VT KS 3 → 42/ngày; Q1 mọi loại hình 9 → 126/ngày; độ phủ 100% |
| Phòng còn từng KS khu vực | top 300 × ~30 trang ≈ 9.000/ngày | tuỳ chọn: id ở các nấc ~13 (VT KS) – ~21 (Q1 KS)/đêm × 14 ≈ 180–300/ngày, mọi KS |
| Tổng | ≈ 9.100 trang/ngày | ≈ 430–640 request nhỏ/ngày (ít hơn ~15–20 lần, nhẹ hơn nhiều về dung lượng qua proxy) |

Ngân sách kênh mặc định 40 request/phút. Request `rowsPerPage = 1` chỉ vài KB, trang KS ~1 MB.

## 5. Rủi ro, giới hạn

1. API nội bộ, không công bố: schema đổi thì trả lỗi validation rõ ràng → cần canary và giữ SSR làm dự phòng. Thang lịch đã phụ thuộc cùng endpoint.
2. Chống bot: giữ budget/limiter/tạm dừng sẵn có; mỗi phiên cần 1 trang SSR để lấy csrf + cookie.
3. Ngữ nghĩa nấc: `nbRooms = N` của tìm kiếm có trả lời giống thang lịch (`capacity_ladder.py`, 1 người lớn/phòng) không → đối chiếu trên 5 KS đã biết (Rex, Caravelle, Reverie, Park Hyatt, Meander). Trần 30.
4. `unavailabilityPercent`: không công bố định nghĩa, làm tròn số nguyên, tính cả căn hộ/biệt thự (VT: căn hộ còn phòng nhiều hơn KS) → không dùng thay chỉ số phân khúc.
5. Quận Booking: tốt ở TP.HCM, hỏng ở Vũng Tàu; quận chồng lấn ở TP.HCM.
6. Histogram tương đối và cắt ở max → số đếm là ước; KS cao cấp có thể rơi ra ngoài max.
7. Phân trang theo thứ tự "phổ biến" có thể xáo giữa các trang → dùng `sorters` cố định (giá/khoảng cách), khử trùng theo id, đối chiếu tổng với c(N).
8. Điều khoản Booking hạn chế truy cập tự động (sản phẩm vốn đã quét Booking; đề xuất giảm tải). Booking Demand API chính thức cần hợp đồng đối tác; chưa rõ có các tín hiệu này không.
9. Proxy 407 từ 08/10 → chưa chạy thật được tới khi có proxy mới.

## 6. Điều KHÔNG làm được

- Tổng số phòng (tồn kho) của thị trường: Booking không công bố; chỉ có phòng Booking còn bán, trần 30/KS ở tìm kiếm.
- Số phòng trống chính xác của từng KS trong khu vực: chỉ ra khoảng theo nấc.
- Occupancy thật: vẫn là chỉ báo trên Booking.com.

## 7. Lộ trình

| Pha | Việc | Request thêm | Ước lượng |
|---|---|---|---|
| 0 | Sửa lỗi #1–#2; mỗi đêm lưu `unavailability_pct`, số nới, facet, histogram (migration 0018); Terminal+ hiện "Booking: X% chỗ nghỉ đã kín" + KS còn phòng theo hạng sao | 0 | ~1 ngày |
| 1 | Client GraphQL `FullSearch` (tái dùng csrf/phiên của lịch); `geo_mode` district/landmark/radius + `segment_nflt`; liệt kê 100/request thay chia lát | ít hơn hiện tại | 2–3 ngày |
| 2 | Thang nấc thị trường, mức căng, KS mình cạnh thị trường (API + Terminal+/Bảng điều khiển) | +210/ngày/khu vực | 2–3 ngày |
| 3 | Đối chiếu nấc tìm kiếm với thang lịch trên 5 KS đã biết (2 tuần); đạt thì bỏ quét chi tiết top 300 (giữ compset) | −8.000+/ngày | 2 tuần dữ liệu |

## 8. Nguồn

- Test live Booking.com (mục 2): nguồn chính.
- Apify Booking Scraper changelog, giới hạn 1.000 kết quả, chia theo bộ lọc: https://apify.com/voyager/booking-scraper/changelog
- Booking Demand API, phân trang (`rows`, `next_page`): https://developers.booking.com/demand/docs/development-guide/pagination
- Lighthouse (OTA Insight) Market Insight, đo cầu theo tình trạng còn/hết phòng: https://hoteltechreport.com/reviews/z9yx4p6j6x8e
- Which? về "only X rooms left": https://www.which.co.uk/news/2019/09/booking-com-still-misleading-holidaymakers-with-1-room-left-claims/
- Booking chặn khi request dày: https://webscraping.ai/faq/booking-com-scraping/what-challenges-can-i-face-when-scraping-booking-com-and-how-to-overcome-them

## Câu hỏi mở

1. "KS mình" trong trường hợp Vũng Tàu là KS nào (tenant mới?). Tenant thật hiện là Rex (TP.HCM).
2. Phân khúc cạnh tranh: chỉ "Khách sạn" hay gồm resort/aparthotel/biệt thự? Hạng sao nào?
3. Khu vực: quận Booking (TP.HCM) hay bán kính 1/3/5 km quanh KS mình?
4. Nấc dùng 1 người lớn/phòng (tới 30 phòng, khớp thang lịch) hay 2 người lớn/phòng (tới 15 phòng, khớp giá probe)?
5. Có cần khoảng phòng còn cho mọi KS khu vực (thay quét chi tiết top 300) không?
6. Khi nào có proxy mới (và nhà cung cấp thứ hai)?
