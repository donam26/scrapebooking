# Pha 1 — Sửa lỗi + lưu tín hiệu đang bỏ (0 request thêm)

## Bối cảnh
- `app/marketscan/parser.py:212` lấy `pagination.nbResultsTotal` (gồm KS ngoài khu vực Booking nới thêm khi sắp kín) → đêm căng báo còn phòng cao hơn thật. Thẻ `persuasion.autoextended` không được đọc → KS ngoài khu vực vào `market_area_hotels`.
- Mỗi trang đã có `searchMeta.availabilityInfo` (unavailabilityPercent, totalAvailableNotAutoextended, totalAutoextendedAvailable, hasLowAvailability), ~20 nhóm facet, histogram thanh ngân sách, `blocks[].onlyXLeftMessage` — đang bỏ.
- Badge cấp thẻ: `name` là chuỗi / `caption.translation` (không phải `name.translation`) → code cũ sẽ lỗi nếu có badge.

## Việc
1. `SearchCard`: + `autoextended: bool`, `only_left: int | None` ("We have N left at this price").
2. `SearchPage`: + `autoextended`, `low_availability`, `unavailability_pct`, `histogram: PriceHistogram | None` (min, max, bars; toàn 0 → None), `rooms`, `adults` (echo của kênh).
3. Tách `parse_search_entry(entry, deref)` dùng chung cho kho Apollo (SSR) và JSON GraphQL (pha 2): total = `totalAvailableNotAutoextended` (dự phòng `nbResultsTotal`); thẻ nới thêm bị loại khỏi `cards`, chỉ đếm.
4. Facet: mọi nhóm trừ `popular`, `popular_sticky`, `used_filters` (trùng/nhiễu).
5. Migration `0018_market_ladder` (down_revision 0017):
   - `market_areas`: `lat`, `lng` (float), `radius_m` (int, CHECK ∈ 1000/3000/5000), `segment_nflt` (varchar 200).
   - `market_list_scans`: `source` (graphql|ssr), `autoextended`, `low_availability`, `unavailability_pct` (smallint), `market_available`, `facets`, `market_facets`, `price_histogram`, `ladder` (JSONB), `enumerated` (bool, default false).
   - `market_list_prices`: `rank` → nullable; + `rooms_min`, `only_left` (smallint).
6. Service ghi các trường mới (đường SSR hiện tại).

## Test
- Unit parser: fixture SSR TP.HCM (unavailability 21, facet `di`), thẻ nới thêm bị loại (dựng biến thể), only_left, histogram 0 → None, badge chuỗi.
- Migration up/down trên DB test.

## Xong khi
Parser + service + migration qua test; không đổi số request.
