# Phase 2: So giá cùng điều kiện (giá hoàn huỷ)

Trạng thái: done · Effort: S–M

## Vấn đề
Compset so `min_price` (rẻ nhất mọi rate plan). Đối thủ có giá không hoàn huỷ rẻ hơn 15–20% làm trung vị lệch, khách sạn tưởng mình đắt. Parser đã có `refundable` từng rate plan và `room_snapshots.min_refundable_price`, nhưng tầng khách sạn/đêm chưa giữ.

## Backend
- Migration `0005_refundable_price`: thêm `min_refundable_price NUMERIC(14,2)` vào `hotel_date_snapshots` và `hotel_date_metrics`.
- `analytics/rules.py`: `RoomObs.min_refundable_price`; `HotelDateObs.min_refundable_price`; `MetricsDraft.min_refundable_price`.
- `analytics/service.py`: đọc từ `RoomSnapshot.min_refundable_price` (cả hiện tại và lịch sử), ghi vào hai bảng.
- `PriceBasis(StrEnum)`: `any` | `refundable` (đặt trong `app/analytics/compset.py`).
- `compset_by_day(..., basis)`; `/overview?price_basis=refundable` đổi cả `DateCell.min_price` lẫn compset. Mặc định `any` (không đổi hành vi cũ, bản tin AI giữ `any`).
- Dữ liệu cũ: cột mới NULL tới lượt quét kế tiếp (mỗi lượt cập nhật metrics cho mọi đêm trong horizon). Không cần reanalyze.

## Dashboard
- Nhóm chọn (segmented) "Mọi giá | Giá hoàn huỷ" cạnh chọn khoảng đêm, lưu trong URL `?basis=refundable` để chia sẻ.
- Khi `refundable` mà chưa đêm nào có giá: ghi chú thông tin "Giá hoàn huỷ có từ lượt quét kế tiếp".
- Chú giải đường giá đổi chữ: "Giá hoàn huỷ thấp nhất…".

## Kiểm thử
- Unit: `HotelDateObs.min_refundable_price` (None khi không phòng nào có).
- Integration: analytics ghi cột mới; `/overview?price_basis=refundable` dùng giá hoàn huỷ; migration up/down.

## Tiêu chí xong
Bật "Giá hoàn huỷ" → dải giá, trung vị, chỉ số, hạng đều tính lại theo giá hoàn huỷ.
