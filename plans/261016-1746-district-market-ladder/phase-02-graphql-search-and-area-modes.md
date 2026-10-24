# Pha 2 — GraphQL FullSearch + khu vực quận/địa danh/bán kính + phân khúc

## Bối cảnh (kiểm live 16/10)
- `POST /dml/graphql` operation `FullSearch`, cùng endpoint/csrf với lịch (`collector/booking/calendar.py`). Query tối giản được chấp nhận (`tests/fixtures/booking/fullsearch_vungtau_hotels_2026-11-18.json`).
- `rowsPerPage` ≤ 100; `filters.selectedFilters` = chuỗi nflt; `location` CITY/DISTRICT/REGION/LANDMARK/LATLONG (`latitude`, `longitude`); `sorters.selectedSorter="price"` ổn định khi lật trang; `useSearchParamsFromSession=false` để không dính tham số phiên.
- Booking cắt 1.000 kết quả/truy vấn; số đếm/facet không bị cắt.
- Header: csrf, `x-booking-context-action-name: searchresults_irene`, `x-booking-topic: capla_browser_b-search-web-searchresults`, `apollographql-client-name: b-search-web-searchresults`, `x-booking-site-type-id: 1`, Origin/Referer.

## Việc
1. `app/marketscan/graphql.py` (thuần): `SEARCH_QUERY`, `search_location(area)`, `combine_nflt(segment, radius)`, `build_search_request(location, night, adults, rooms, nflt, rows, offset, sorter)`, `search_headers(csrf, referer)`, `parse_search_response(text)` → `SearchPage` (lỗi schema → `SearchSchemaError`).
2. `BookingCollector.search_graphql(payload, referer) -> str`: session/ngân sách/giãn cách/proxy như `fetch_calendar`; thiếu csrf → tải 1 trang SSR (referer) lấy `b_csrf_token`; bị chặn → thu hồi session, `ListingBlocked`; 5xx → lỗi tạm thời.
3. `MarketListService.scan_night` viết lại:
   - truy vấn thị trường (rows=1, chỉ bán kính, 2NL) → `market_available`, `unavailability_pct` (khi không lọc), `market_facets`;
   - danh sách: trang 1 "phổ biến" (hạng 1..100), còn thiếu thì các trang sắp theo giá tới đủ `min(c(1), 1.000)`; khử trùng theo slug/id;
   - trần request mỗi đêm = `max_pages`; hết trần → `capped`, giữ phần đã có;
   - lỗi schema → dự phòng SSR trang đầu (`source=ssr`).
4. Bỏ `slices.py`, đêm khám phá, `market_discovery_night`; `max_pages` = trần request/đêm.
5. Khu vực: API nhận `landmark`, `latlong` (+ `lat`, `lng`, bắt buộc `radius_m`), `radius_m`, `segment_nflt` (regex `^[a-z_]+=[0-9]+(;[a-z_]+=[0-9]+)*$`); `dest_id` của latlong = "lat,lng" (5 số lẻ). Autocomplete nhận thêm `landmark`. `GET /market/areas/self-location` → toạ độ KS self cho nút "quanh khách sạn của bạn".

## Test
- Unit: build request (location từng kiểu, nflt ghép, trần rows), parse response fixture thật (thẻ, only_left, facet, histogram 0 → None, total), lỗi schema.
- Integration service: nguồn GraphQL giả theo (đêm, nflt, phòng, offset, sorter) → liệt kê đủ, khử trùng, trần request, dự phòng SSR, bị chặn → dừng chuỗi.
- API: tạo khu vực latlong/landmark/segment, validate lỗi, self-location.

## Xong khi
Một đêm quét = 1 + ⌈c(1)/100⌉ (+1 trang phổ biến) request, độ phủ 100% khi c(1) ≤ 1.000.
