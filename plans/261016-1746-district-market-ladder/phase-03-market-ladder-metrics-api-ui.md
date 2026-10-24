# Pha 3 — Thang phòng trống thị trường, chỉ số, KS mình cạnh thị trường (API + dashboard)

## Bối cảnh (kiểm live 16/10)
VT chỉ KS, T7 17/10 vs T4 18/11: ≥1 phòng 208/210 (đứng yên), ≥10: 122/150, ≥20: 79/104. Facet `class` trong cùng request cho đủ 1–5★. `nbRooms`, `nbAdults` ≤ 30.

## Việc — backend
1. Service: sau danh sách, mỗi nấc N ∈ `MARKET_LADDER_RUNGS` (mặc định 2,3,5,10,20,30; 1 NL/phòng, sắp theo giá):
   - đêm gần (`index < MARKET_ENUMERATE_NIGHTS`, mặc định 14): rows=100, lật đủ id → `rooms_min = N` (GREATEST) cho từng KS; đêm xa: rows=1 (chỉ đếm);
   - c(N) = 0 → dừng nấc cao hơn; lưu `ladder` JSON `{N: {available, autoextended, class}}`, `enumerated`.
2. `app/marketscan/ladder.py` (thuần): làm đơn điệu c(N), sàn phòng còn Σ (c(N_k) − c(N_k+1))·N_k + c(N_max)·N_max, mức căng c(10)/c(1), tỉ lệ hết phòng 1 − c(1)/mẫu số, khoảng phòng còn từng KS [N_k, N_k+1 − 1], phân vị giá.
3. Mẫu số phân khúc = max `properties_found` của khu vực trong 30 ngày quét gần nhất (cận dưới → tỉ lệ hết phòng là cận dưới).
4. API:
   - `GET /market/city`: `list_scan` + `source, autoextended, low_availability, unavailability_pct, market_available, segment_base, sold_out_share, ladder[], rooms_left_floor, tightness, tightness_median (trung vị các đêm của vòng gần nhất), booking_histogram, composition (loại hình của thị trường), classes (hạng sao còn phòng), enumerated`; `self_hotel` (KS self: có trong khu vực, hạng, giá, phân vị giá, rooms_min tìm kiếm, phòng còn min/max của phân tích hiện có, tỉ lệ KS khu vực còn nhiều phòng hơn).
   - `GET /market/city/trend?start&nights` (≤30): mỗi đêm: c(N), tỉ lệ hết phòng, mức căng, sàn phòng, trung vị giá, % Booking.
   - `GET /market/city/hotels`: + `rooms_min`, `rooms_max`, `only_left`.
5. Export openapi + `npm run gen:api`.

## Việc — dashboard (OTARadar, vi/en)
1. Cài đặt › Thị trường: tạo khu vực "Tìm thành phố/quận/địa danh" hoặc "Quanh khách sạn của bạn" (1/3/5 km); chọn phân khúc; hàng khu vực hiện loại, bán kính, phân khúc; nhãn `landmark`/`latlong`.
2. Terminal+ thẻ thị trường: % KS hết phòng (phân khúc) + % Booking (khi có); thang ≥1/≥5/≥10/≥20/≥30; mức căng so trung vị ("căng hơn thường lệ"); sàn phòng còn; histogram Booking/giá liệt kê; dòng KS mình.
3. Terminal+ dải 14 đêm (`/market/city/trend`): mỗi đêm % hết phòng + số KS còn ≥10 phòng, tô nhiệt.
4. Đối thủ › Thị trường: cột "Phòng còn" (≥N / N–M) + "Còn N ở giá này".
5. i18n vi/en, `npm run i18n:check`.

## Test
Unit ladder; integration service (thang, liệt kê id, dừng khi 0); API city/trend/hotels; dashboard typecheck/lint/build + Playwright ảnh chụp.
