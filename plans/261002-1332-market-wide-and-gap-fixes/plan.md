# Thị trường toàn thành phố + bù các khoảng thiếu so với OTARadar

Nguồn: `plans/reports/gap-analysis-261002-1332-otaradar-vs-ours.md`. Quyết định 2026-10-02: làm **đầy đủ như bên kia** (danh sách mọi KS trong thành phố + quét chi tiết từng KS), ngân sách proxy không phải giới hạn (giới hạn thật là ngưỡng chống bot của kênh).

## Pha A — Bù khoảng thiếu bằng dữ liệu sẵn có (main session)
1. [x] Quét ngay một khách sạn: `POST /watchlist/{hotel_id}/scan-now` (mở rộng `create_manual_run` theo hotel_id).
2. [x] Lịch sử quét theo khách sạn: `GET /runs/{run_id}/jobs` (job từng KS + đếm probe theo trạng thái), mở rộng dòng ở `/runs`.
3. [x] Công suất từng khách sạn: `GET /market/occupancy?start&end` (ước tính mới nhất đủ tin cậy), biểu đồ từng KS + "KS ≈≥90%".
4. [x] Dự báo doanh thu ≈ khi chưa có PMS: giá bạn × công suất ước tính × tồn kho (frontend).
5. [x] Sự kiện địa phương: bảng `local_events` (migration 0010), CRUD `/market/events`, tab Cài đặt › Sự kiện, lịch Terminal+ (loại Lễ hội/MICE/Thể thao/Mùa/Khác, % tăng cầu dự kiến), chip "Mùa" ở đầu Terminal+.

Pha A xong 2026-10-02: test `test_scan_one_hotel_now_and_list_run_jobs`, `test_occupancy_per_hotel_lists_watchlist_hotels`, `test_local_events_crud_and_permissions` + 28 test liên quan pass; sửa lỗi chống trùng (quét cả watchlist bị coi trùng với quét một KS). UI kiểm tra trên DB nhân bản `scrapebooking_ui` (đã lên 0010, có 2 sự kiện mẫu), DB dev chưa đổi.

## Pha B — Thị trường toàn thành phố, backend (agent)
Kênh Booking trước. Migration 0011 (down_revision 0010).
- `market_areas` (tenant, kênh, tên, dest_id, dest_type, list_nights=14, detail_horizon_days=30 (≤90), detail_max_hotels=300, active, mốc quét gần nhất).
- `hotels` thêm `review_score`, `review_count`, `image_url`, `district`.
- `market_area_hotels` (area, hotel, first/last_seen, best_rank).
- `market_list_scans` (area, đêm, lúc quét, properties_found, pages, hotels_seen, status, error) + `market_list_prices` (scan, hotel, giá VND).
- Tìm địa điểm qua autocomplete.json (dest_id thành phố/quận); trang kết quả `searchresults.en-gb.html` (25 KS/trang, `offset`), 2 người lớn, VND, đi qua session/proxy/budget sẵn có của kênh booking.
- Job `scan_market_list(area_id)` (hàng đợi booking): mỗi đêm trong list_nights, lật trang tới hết; upsert hotel + listing booking `active` + market_area_hotels + giá.
- Lịch: 03:00 giờ tenant quét danh sách; 05:00 tạo run `market:<area>:<ngày>` quét chi tiết top `detail_max_hotels` KS (theo số review) với planner tầng sẵn có → analytics + occupancy_estimates chạy như mọi run.
- API: CRUD `/market/areas` (tenant_admin ghi), `GET /market/city?date=` (danh sách: properties_found, priced, avg/median/p25/p75, histogram; chi tiết: KS có dữ liệu, KS còn phòng, phòng còn/tồn kho ≈, công suất ≈, độ phủ), `GET /market/city/hotels?date&sort&limit&offset` (điểm, review, sao, quận, khoảng cách tới KS của bạn, giá đêm đó, đã theo dõi chưa, url).
- Test: parser với fixture thật, API, job với fetcher giả, tổng hợp. DB test riêng `scrapebooking_test_mkt`.

Pha B xong (agent): migration 0011, `app/marketscan/`, router `market_city.py`, scheduler 03:00/05:00. Booking bỏ qua `offset` → đổi sang 1 request/đêm + lượt khám phá "lát cắt" 1 lần/ngày. Chạy thật 02/10 quận Trung tâm: 25 request → 234/370 KS (63%). 653 test backend pass.

## Pha C — Thị trường toàn thành phố, frontend (main session)
- Cài đặt › Thị trường: tìm thành phố/quận, cấu hình số đêm, horizon, số KS quét chi tiết, trạng thái lượt quét.
- Terminal+: chỉ báo thị trường cả thành phố (X/Y KS còn phòng, phòng còn/tổng ≈, giá TB, histogram giá).
- Đối thủ › Khám phá thị trường: bảng KS thành phố (điểm, review, sao, quận, khoảng cách, giá) + "Theo dõi".
- Bảng điều khiển: thẻ thị trường thành phố.

Pha C xong: Cài đặt › Thị trường, Terminal+ thẻ thị trường khu vực (fallback compset), Đối thủ › Khám phá thị trường (+ Theo dõi). Bảng điều khiển chưa thêm thẻ khu vực (để sau).

## Pha D — Kiểm tra, triển khai
pytest phần mới, tsc/lint/build, chạy thử 1 lượt danh sách thật (giới hạn trang), chụp màn hình; migration lên dev DB khi người dùng đồng ý build lại Docker.

## Review (2026-10-02) — đã sửa
4 High + Medium từ code-reviewer: chuỗi quét danh sách bền hơn (bỏ qua đêm lỗi, khôi phục chuỗi kẹt, job id cố định, không chạy chồng), trần tải (≤500 KS chi tiết, ≤100 request khám phá, ≤30 đêm, ≤3 khu vực/tenant), run thị trường không thành "lượt quét gần nhất" và không gửi email tenant, lỗi cho tenant là mã ngắn, bị chặn ở trang danh sách tạm dừng quét danh sách, xoá dữ liệu danh sách >120 ngày, FK ondelete 0010/0011, retry theo từng job. 662 test backend pass; `npm run build` OK (24 route).

Còn lại: chưa migrate DB dev thật (0010, 0011) và chưa build lại Docker; Bảng điều khiển chưa có thẻ thị trường khu vực.
