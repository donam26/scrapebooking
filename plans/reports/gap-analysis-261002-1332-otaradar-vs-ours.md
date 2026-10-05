# So sánh tính năng: OTARadar (khách hàng) vs hệ thống hiện tại

Nguồn bên kia: 4 ảnh giao diện `job/*.jpg` + crawler `job/` (repo promvn-job). Không có frontend/backend của họ; tính năng suy từ API crawler gọi và số trên ảnh.

## Bên kia có, bên mình thiếu hoặc yếu hơn

| # | Tính năng (bên kia) | Bên mình | Đánh giá | Hướng |
|---|---|---|---|---|
| 1 | **Thị trường toàn thành phố**: `hotel-list-all` quét danh sách mọi khách sạn theo địa điểm (tự thêm quận), `hotel-scan-all` quét 90 ngày cho mọi khách sạn → "395/549 KS còn phòng", "còn 2.406/3.344 phòng", phân bố giá | Chỉ compset (5 KS) | Thiếu lớn nhất | Cần quyết định: tốn proxy/request gấp ~100 lần, dễ bị chặn |
| 2 | **Chọn đối thủ từ danh sách KS đã quét** (user_hotels chọn từ bảng hotels, có điểm đánh giá, số review, khoảng cách, ảnh) | Thêm bằng URL + gợi ý cùng KS trên kênh khác | Yếu hơn về khám phá | Phụ thuộc #1; trước mắt: hiện khoảng cách tới KS của bạn |
| 3 | **Điểm đánh giá / số review / ảnh** trên thẻ đối thủ | Chỉ hạng sao | Thiếu | Cần sửa parser từng kênh |
| 4 | **Quét ngay một khách sạn** (hàng đợi ưu tiên khi người dùng bấm) | Chỉ quét ngay cả watchlist | Thiếu | Làm ngay (mở rộng scan-now theo hotel_id) |
| 5 | **Crawl History theo từng khách sạn** (job tổng + job từng KS, lỗi từng KS) | Chỉ số tổng mỗi lượt | Thiếu chi tiết | Làm ngay (`scan_jobs` đã có trong DB) |
| 6 | **Phân tích công suất từng khách sạn** (mỗi KS một đường, "KS >90%") | Chỉ trung vị compset + của bạn | Thiếu | Làm ngay (`occupancy_estimates` đã có theo KS) |
| 7 | **Dự báo doanh thu 14 ngày** khi không có PMS | Chỉ khi có PMS | Thiếu | Làm ngay: giá bạn × công suất ước tính × tồn kho, ghi "≈" |
| 8 | **Lịch sự kiện có phân loại** (Tết/Lễ/Major/MICE/Thể thao) và **% tăng cầu** | Chỉ ngày lễ tĩnh | Thiếu | Làm ngay: sự kiện địa phương do tenant nhập + % giá thị trường thực đo |
| 9 | **Mùa** ("Spring Business Season") trên Terminal+ | Không | Thiếu nhỏ | Gộp vào #8 (loại "Mùa") |
| 10 | Chuyến bay đến | Không | Không có nguồn thật | Bỏ (đã thay bằng tín hiệu đặt phòng) |
| 11 | Hiển thị USD | VND cố định | Quyết định cũ: VND | Giữ |

## Bên mình đã hơn (giữ nguyên)
Mức tin cậy số phòng (exact/≥N/ẩn/hết), đa kênh (Booking, Agoda, iVIVU, Trip.com, Mytour) + so kênh + đóng bán trên kênh, giá hoàn huỷ, bản tin AI có bằng chứng, email cảnh báo, nhập PMS, gợi ý giá có lý do, quét bù khi lỡ lịch, tự ngắt kênh bị chặn, phân quyền viewer/admin/operator.

Ghi chú chất lượng dữ liệu bên kia (không nên bê sang): mỗi dòng rate plan bị cộng như loại phòng (đếm thừa phòng), tiền tệ theo IP proxy, trang danh sách 2 người lớn còn trang chi tiết 1 người lớn (giá không cùng điều kiện), có code đăng nhập Booking qua mã email (trái nguyên tắc không đăng nhập kênh).

## Câu hỏi mở
- #1 thị trường toàn thành phố: làm không, phạm vi (1 quận / cả thành phố), tần suất (1 lần/ngày?), chỉ trang danh sách (rẻ) hay cả trang chi tiết (đắt)?
- #3 điểm đánh giá: lấy từ kênh nào trước (Booking)?
