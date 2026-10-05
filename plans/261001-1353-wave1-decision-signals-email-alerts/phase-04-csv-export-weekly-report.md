# Phase 4: Xuất CSV + báo cáo tuần qua email

Trạng thái: done · Effort: S–M · Phụ thuộc phase 3 (hạ tầng email)

## Xuất CSV
- `GET /export/overview.csv?start&end&price_basis`: mỗi hàng một (khách sạn, đêm): khách sạn, vai trò, đêm, thứ, trạng thái, số phòng còn (chỉ khi chính xác), mức tin cậy, giá thấp nhất, tiền tệ, đối thủ hết phòng k/n, trung vị đối thủ, giá bạn so trung vị %, hạng, ngày lễ.
- `GET /export/events.csv`: cùng bộ lọc `/events`, tối đa 5.000 dòng.
- UTF-8 có BOM, dấu phẩy, tiêu đề cột tiếng Việt (Excel VN mở đúng dấu). `Content-Disposition` tên tệp có ngày.
- Dashboard: nút phụ "Tải CSV" ở đầu Tổng quan và Sự kiện (biểu tượng tải xuống, giữ bộ lọc hiện tại).

## Báo cáo tuần
- Cron giờ: tenant đang ở thứ Hai ≥ 08:00 giờ địa phương và chưa có `weekly:{tenant}:{iso_week}` → gửi.
- Nội dung (hàm thuần `build_weekly_report`):
  - 7 ngày qua: số lần đối thủ hết phòng, giảm giá, sắp hết phòng; đối thủ biến động nhiều nhất.
  - 14 đêm tới: các đêm ≥ 50% đối thủ hết phòng; giá bạn so trung vị trung bình; đêm bạn cao/thấp nhất so trung vị; ngày lễ.
  - Liên kết về Tổng quan.
- Không có dữ liệu → không gửi (`skipped`).

## Kiểm thử
- Unit: CSV (BOM, escape dấu phẩy/ngoặc kép), `build_weekly_report`, chọn tenant đến hạn theo múi giờ.
- Integration: hai endpoint CSV (phân quyền tenant, khoảng ngày).

## Tiêu chí xong
Tải CSV mở được trong Excel với dấu tiếng Việt; thứ Hai 08:00 nhận đúng một báo cáo tuần.
