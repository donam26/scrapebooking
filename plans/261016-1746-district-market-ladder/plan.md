# Thị trường theo quận/bán kính + bộ lọc Booking + thang phòng trống

**Mục tiêu:** quét thị trường khu vực theo quận (Booking district) hoặc bán kính quanh KS mình, lọc theo phân khúc (loại hình, hạng sao), đo **lượng phòng trống của thị trường** (thang `nbRooms`) và đặt **KS mình cạnh thị trường**. Rẻ hơn ~15–20 lần so với quét chi tiết top 300 KS hiện nay.

Nghiên cứu + bằng chứng live: `reports/research-261016-1722-district-market-scan-booking-filters.md`.

## Quyết định (người dùng 16/10: "làm plan chuẩn và làm luôn", không trả lời câu hỏi mở → chọn mặc định, chỉnh được)
| # | Vấn đề | Chọn | Lý do |
|---|---|---|---|
| D1 | Khu vực | `dest_type` ∈ city/district/region/**landmark**/**latlong**; `radius_m` ∈ {1000, 3000, 5000} (bộ lọc `distance` của Booking). latlong bắt buộc có bán kính | Quận Booking tốt ở TP.HCM, hỏng ở Vũng Tàu |
| D2 | Phân khúc | `segment_nflt` tự do theo cú pháp Booking; UI có 3 mẫu: mọi loại / Khách sạn (`ht_id=204`) / KS + resort + căn hộ KS (`ht_id=204;ht_id=206;ht_id=219`) | OR trong cùng nhóm đã kiểm live (247 = 210 + 8 + 29) |
| D3 | Thang | nấc **3,5,10,20,30** phòng, **1 người lớn/phòng** (như thang lịch); nấc 1 = truy vấn danh sách 2 người lớn (chuẩn giá của sản phẩm); số đếm kẹp xuống nấc dưới (nấc 1 luôn = số còn phòng) | Booking kẹp `nbRooms`, `nbAdults` ≤ 30. Bỏ nấc 2 sau quét thật 16/10: c(2) ≈ c(1) (428/428, 463/464, 565/566, 605/604) mà tốn ~5 request/đêm |
| D4 | Liệt kê id | 14 đêm gần (`MARKET_ENUMERATE_NIGHTS`): liệt kê đủ (100/request, trần 1.000) ở danh sách + mọi nấc → khoảng phòng còn từng KS. Đêm xa: chỉ số đếm (`rowsPerPage=1`) | Cân chi phí |
| D5 | Thứ tự | trang 1 theo "phổ biến" (hạng hiển thị), các trang sau `sorters.selectedSorter="price"` (ổn định khi lật trang, đã kiểm) | Tránh xáo trùng giữa trang |
| D6 | Quét chi tiết top N | giữ nguyên mặc định; khu vực live của tenant 9 đặt `detail_max_hotels=0`; bỏ hẳn sau khi đối chiếu (pha 4) | Chưa đủ 2 tuần dữ liệu đối chiếu |
| D7 | Chia lát SSR + đêm khám phá | **bỏ** (GraphQL liệt kê đủ tới 1.000). SSR chỉ còn làm dự phòng khi GraphQL lỗi schema | YAGNI |
| D8 | % kín của Booking | lưu từ truy vấn "thị trường" (không lọc phân khúc); chỉ hiện khi truy vấn đó không có bộ lọc nào (không bán kính) | % có lọc là chia cho tổng cả khu vực → sai nghĩa |
| D9 | Tên chỉ số | "mức căng thị trường trên Booking.com", "phòng còn bán (sàn)", không gọi occupancy | PRODUCT.md |

## Kiến trúc
```
scheduler 03:00 → scan_market_list(area, night i) ─┐ (chuỗi đêm, như cũ)
                                                    ▼
MarketListService.scan_night
 ├ thị trường: FullSearch(khu vực + bán kính, 2NL, rows=1)        → unavailability%, thành phần loại hình
 ├ danh sách : FullSearch(+phân khúc, 2NL, rows=100, phổ biến→giá) → thẻ, giá, hạng, "We have N left", facet, histogram
 └ thang     : FullSearch(+phân khúc, N phòng/N NL, N∈rungs)         → c(N) theo hạng sao; đêm gần: id → rooms_min từng KS
      transport: BookingCollector.search_graphql (session/csrf/proxy/ngân sách như lịch GraphQL)
      dự phòng : trang SSR (parse_search_page) khi GraphQL lỗi schema
                                                    ▼
market_list_scans(+ladder, facets, histogram, market_*) · market_list_prices(+rooms_min, only_left)
                                                    ▼
API /market/city (+ladder, mức căng, KS mình) · /market/city/trend · /market/city/hotels(+phòng còn)
                                                    ▼
Dashboard: Cài đặt › Thị trường (bán kính, phân khúc) · Terminal+ (thẻ thị trường + dải 14 đêm) · Đối thủ › Thị trường
```

## Pha
| Pha | Nội dung | Trạng thái |
|---|---|---|
| [1](phase-01-parser-fixes-and-stored-signals.md) | Sửa lỗi KS nới thêm; parser đọc unavailability%, facet, histogram, "We have N left"; migration 0018 | ✅ |
| [2](phase-02-graphql-search-and-area-modes.md) | Client GraphQL FullSearch; khu vực landmark/latlong + bán kính + phân khúc; liệt kê 100/request thay chia lát | ✅ |
| [3](phase-03-market-ladder-metrics-api-ui.md) | Thang nấc, chỉ số thị trường, KS mình cạnh thị trường; API + dashboard (+ chọn khu vực) | ✅ |
| [4](phase-04-live-run-and-validation.md) | Proxy mới, migrate DB dev, quét thật tenant 9, đối chiếu 15/15, review độc lập + sửa, docs | ✅ |

## Tiêu chí xong
- pytest backend, ruff, mypy sạch; dashboard typecheck/lint/i18n:check/build sạch.
- Quét thật qua proxy mới: ≥1 khu vực quận + 1 khu vực bán kính cho tenant 9, đủ 14 đêm, không bị chặn; API trả thang + KS mình; ảnh chụp UI vi/en, desktop + 390 px.
- Báo cáo đối chiếu thang tìm kiếm vs thang lịch trên compset (5 KS).
- Review độc lập (code-reviewer), sửa hết High/Medium.

## Rủi ro
API nội bộ đổi schema (→ dự phòng SSR + log lỗi rõ); chống bot (ngân sách 40 req/phút dùng chung probe; tạm dừng khi bị chặn); proxy đơn lẻ (check-proxy 15 phút); histogram có lúc toàn 0 (→ coi là không có); `nbRooms` tìm kiếm có thể khác thang lịch (→ pha 4 đo).

## Kết quả (16/10/2026)
- Báo cáo chạy thật + đối chiếu: `reports/live-run-261016-1900-validation-and-results.md`.
- Backend: pytest 610+ pass (thêm test parser/GraphQL/thang/service/API/collector), ruff, mypy sạch;
  openapi + `api-types.ts` sinh lại. Dashboard: typecheck, lint, i18n:check, build sạch; kiểm bằng
  trình duyệt với dữ liệu thật (desktop + 390 px, đổi khu vực).
- Quét thật qua proxy mới: 2 khu vực tenant 9 (Quận 1, 3 km quanh Rex), 14 đêm, không bị chặn;
  ~35–45 request, ~90–110 giây mỗi đêm. Đối chiếu thang tìm kiếm với thang lịch compset: khớp 15/15.
- Review độc lập (code-reviewer): 2 High + 3 Medium + Low đã sửa (xem báo cáo).
- Chưa commit. DB dev ở 0018 (+ ALTER tay cột `nflt`). Stack Docker chưa chạy lại (image cũ).

## Câu hỏi mở (đang dùng mặc định ở trên)
1. KS "của mình" ở Vũng Tàu (tenant mới?) — hiện chỉ tenant 9 (Rex, Q1) có dữ liệu thật.
2. Phân khúc cạnh tranh thật của từng tenant.
3. Bỏ quét chi tiết top N sau đối chiếu?
