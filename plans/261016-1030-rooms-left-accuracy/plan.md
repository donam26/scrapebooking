# Rooms-left accuracy & competitor capacity — Implementation Plan

> For agentic workers: thực thi tuần tự theo phase (inline, có review giữa phase). Checkbox `- [ ]`.

**Goal:** Làm đúng và tốt 2 chức năng sếp chốt: (1) đối thủ có bao nhiêu phòng, (2) số phòng còn lại gần chính xác nhất — trung thực về độ chắc chắn (N / ≥N / khoảng).

**Architecture:** Per loại phòng: dropdown < trần riêng của listing → số chính xác. Mức khách sạn: khoảng [min, max] gộp từ trang (Σ loại phòng) + "thang nbRooms" trên lịch GraphQL (đã kiểm live: lịch tính TỔNG khách sạn, nhận N tới ≥50, 120 lỗi). Đêm lịch báo đóng → probe trang (+ probe bắc cầu D-1) để tách hết phòng / đóng nhận khách. Tổng phòng công bố lưu kèm nguồn; "Booking mở bán tối đa" suy từ dữ liệu.

**Tech Stack:** Python 3.12, SQLAlchemy async, Alembic, arq, curl_cffi/Playwright; Next.js 16 + next-intl; Postgres 16.

Nguồn: `plans/reports/audit-261016-0952-rooms-left-and-competitor-capacity.md`.

## Bằng chứng đã có (không làm lại)
- 19.816 quan sát: badge (N=1–7) = dropdown 100%; dropdown 8–9 không badge; trần 10; Park Hyatt trần 9.
- Live 16/10: `no_rooms=30` trên trang không phá trần/loại. Lịch `nbRooms=N, nbAdults=N`: Reverie 30/10 trang (2 người) Σ=14 (max/loại 4) nhưng lịch còn ở N=15 → lịch tính tổng khách sạn (kể cả loại phòng không hiện với 2 người). Caravelle N=50 còn 31/31 đêm; N=120 → lỗi 500.

## Hợp đồng dữ liệu (khoá thiết kế)
| Chỗ | Trường | Nghĩa |
|---|---|---|
| `listings` | `dropdown_cap_seen` int null | dropdown lớn nhất từng thấy (trần riêng; ≤ 10) |
| `hotel_calendars` | `rooms_min`, `rooms_max` int null | kết quả thang nbRooms của run: còn ≥ rooms_min; ≤ rooms_max |
| `hotel_date_snapshots`, `hotel_date_metrics` | `rooms_left_min`, `rooms_left_max` int null | khoảng phòng còn cả khách sạn trên Booking; `exact_rooms_left` = min khi min = max, ngược lại null |
| `hotels` | `rooms_total_source` text, `rooms_total_updated_at` tz | nguồn số phòng công bố |
| API `DateCell`, `RateDetailOut`, `HotelDateSnapshotOut` | `rooms_left_min`, `rooms_left_max` | như trên |
| Settings | `capacity_ladder` "2,3,4,5,10,15,20,25,30,40,50,60,80,100" | các nấc N; rỗng = tắt |

Quy tắc per loại phòng (`derive_stock`): badge → exact; dropdown 0 → sold_out; dropdown ≥ min(10, cap listing) → capped "≥dd"; dropdown < cap → exact; không dropdown → hidden.

Quy tắc mức khách sạn (`analytics/rooms_left_bounds.py`):
- loại phòng: exact → [n, n]; capped → [n, ∞); hidden → [1, ∞); sold_out → [0, 0].
- trang: floor = Σ lo; ceiling = Σ hi nếu mọi hi hữu hạn.
- min = max(floor, cal_min); max = cal_max nếu có (và ≥ min) else ceiling; sold_out → [0,0]; restricted/unknown → None.
- exact = min nếu max == min.

## Phase 1 — Trần dropdown theo listing + tính lại
- [x] `domain/stock.py`: thêm `listing_cap`; dd < cap → EXACT. Test `tests/unit/test_stock.py` (đổi ca (None,4)→EXACT; thêm Park Hyatt 9/8; listing mới).
- [x] `repo/snapshots.py`: `write_probe` cập nhật `listings.dropdown_cap_seen = max(cũ, max dd trang)` rồi derive với cap đó. Test integration snapshot repo.
- [x] Migration 0016 (mọi cột ở bảng trên) + backfill `dropdown_cap_seen` từ room_snapshots.
- [x] CLI `rederive-stock` (tính lại rooms_left/confidence từ badge/dropdown đã lưu, không cần HTML) + `--reanalyze`.

## Phase 2 — Khoảng phòng còn mức khách sạn (backend)
- [x] `analytics/rooms_left_bounds.py` (thuần) + unit test bảng ca.
- [x] `rules.py`: `HotelDateObs.calendar_min/max`, `rooms_left_min/max`, `exact_rooms_left` theo khoảng; `MetricsDraft` + `exact_share` = tỉ lệ quan sát có tổng chính xác.
- [x] `service.py`: đọc `hotel_calendars.rooms_min/max` của run; ghi cột mới; lịch sử dựng lại bounds từ snapshot; **không ghi đè metric tốt bằng quan sát unknown** (P0-3).
- [x] Consumers: `compset.competitors_low`, `market.py` (own/comp low), `pace_report.py`, `insight/input_builder.py` (+min/max), export CSV/báo cáo (+cột min/max).
- [x] API schemas + `data.py`; regenerate `docs/api/openapi.json` + `dashboard/src/lib/api-types.ts`; test API.

## Phase 3 — Dashboard
- [x] `components/marks.tsx`: exact "N"; khoảng "min–max"; sàn "≥min"; nhãn trung thực.
- [x] `availability/heatmap-table.tsx` tổng (≥ khi có ô không chính xác), `lib/market-metrics.ts` (độ căng dùng max ≤ 3), `dashboard/side-cards.tsx`, `competitors/page.tsx`, `hotels/[id]/page.tsx`, `today/page.tsx`, `overview/board.tsx`, `hotels/[id]/dates/[date]/page.tsx`, `insights/insight-view.tsx`.
- [x] i18n vi/en; `npm run typecheck && npm run lint && npm run i18n:check`.

## Phase 4 — Hết phòng trong cửa sổ lịch
- [x] `worker/jobs.py`: đêm lịch báo đóng → probe trang 1 đêm; trang hết phòng → probe bắc cầu (D-1, max(2, minLOS(D-1)) đêm); bắc cầu có phòng → restricted; không → sold_out; D = hôm nay → sold_out; lỗi → restricted như cũ. Test integration worker với fake collector.

## Phase 5 — Thang nbRooms
- [x] Collector `fetch_calendar(..., rooms=1)`; `build_calendar_request` nhận `rooms`.
- [x] `worker/capacity_ladder.py`: sau vòng probe, nấc tăng dần, bỏ nấc khi mọi đêm đã ≥ N hoặc đã có trần; ghi `hotel_calendars.rooms_min/max`. Unit test thuần + integration với fake collector.
- [x] Dò nấc tối đa (live): 60/80/100 nhận, 120 lỗi 500 → mặc định `2,3,4,5,10,15,20,25,30,40,50,60,80,100` (nấc 2–4 thêm sau review).

## Phase 6 — Sức chứa đối thủ
- [x] API watchlist/hotel: `rooms_total_source`, `rooms_total_updated_at`, `booking_rooms_max_seen` (max rooms_left_min 365 ngày) + `…_at`; PATCH nhận nguồn.
- [x] UI: Cài đặt › Watchlist nhập "Số phòng" + "Nguồn"; thẻ sức chứa ở trang khách sạn & thẻ đối thủ; cảnh báo khi số công bố < Booking từng mở bán.

## Phase 7 — Vận hành & dữ liệu thật
- [x] Dev DB: `alembic upgrade head`, `sb rederive-stock --reanalyze` (đã backup `~/scrapebooking-backups/scrapebooking-before-rooms-left-261016.dump`); đo lại tỉ lệ.
- [x] Build lại image backend (nền).
- [ ] Proxy mới + `OPS_ALERT_EMAILS`: cần người dùng cung cấp (proxy hiện tại 407 từ 08/10).

## Phase 8 — Kiểm thử & review
- [x] `pytest` toàn bộ: 538 pass (mốc 492), ruff, mypy; dashboard typecheck/lint/i18n.
- [x] Review độc lập (subagent code-reviewer); sửa phát hiện:
  - must-fix: nấc nhỏ 2–4 cho thang (ô "2" không thành "2–4"); tỷ lệ thành công run = 1 − (chặn+lỗi)/tổng; 0016 xoá exact cũ + `rederive-stock` phân tích lại mọi run.
  - should-fix: chỉ kết luận hết phòng khi bắc cầu xác nhận; thang bỏ đêm lịch báo đóng; chữ en "offered"; chặn tenant ghi đè số phòng dùng chung; nấc lỗi giữ kết quả từng phần; cột CSV mới ở cuối.
  - kiểm live thêm: Meander nấc 30 còn 31/31, nấc 60 còn 22/31 đêm → lịch có xét nbRooms; đơn vị là đơn vị bán (giường dorm).
  - để lại có chủ đích: "chính xác" của trang (đêm 62–90, không thang) chỉ tính loại phòng cho 2 người lớn (ghi ở PRODUCT.md).
- [x] Cập nhật `docs/user-flows.md`/`docs/operations.md` + báo cáo audit.

## Ngoài phạm vi (ghi lại)
Occupancy "≈%" (mẫu số/độ phủ), probe 1 người lớn, Demand API, tự đăng ký cho bản free.

## Kết quả (16/10)
- Backend: 0016 + rederive + phân tích lại trên DB dev (backup `~/scrapebooking-backups/scrapebooking-before-rooms-left-261016.dump`).
- Loại phòng: exact 49,7% → 55,8%, hidden 14,2% → 0%. Ô khách sạn: 0 ô tổng thiếu hiển thị như chính xác (trước 437/509); 0 ô "≤3" sai (trước 16).
- Số phòng công bố đã nhập kèm nguồn: Rex 286, Caravelle 335, Reverie 286, Park Hyatt 245, Meander 42 (Booking bán giường dorm: từng mở ≥54 → cảnh báo).
- Chỉ báo "≈% lấp đầy" của khách sạn lớn giờ ẩn (độ phủ tính trên tổng phòng công bố): trước đây coi phòng không thấy trên Booking là đã bán.
