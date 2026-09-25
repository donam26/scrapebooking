---
version: 1
slug: "dashboard-src-app-app"
primary_target: "dashboard/src/app/(app)"
related_targets: ["dashboard/src/app/login"]
---

## Scope and mode
Dashboard sau đăng nhập: nhóm route `dashboard/src/app/(app)/` (tenant + operator) và `/login`. Mode: Operate.

## Audience, job, task
Chủ khách sạn / revenue manager mở mỗi sáng để quyết định giá: đêm nào đối thủ sắp kín, giá mình đứng đâu so với trung vị. Operator vận hành nhiều tenant, theo dõi sức khoẻ scraper.

## Decisions (2026-09-25, người dùng chọn)
- Thế giới hình ảnh: nối thương hiệu ScrapeBooking của trang giới thiệu vào app (Be Vietnam Pro, tím hành động, thanh bên tím than, bốn dấu mức tin cậy).
- Thông tin kỹ thuật (token/chi phí/mô hình AI, probe/chặn/lỗi, số lượt quét) chỉ operator thấy.
- Bố cục Tổng quan: "Từng khách sạn một dải" (surface roll seed 2dedb492, ứng viên 6/7), code-led.
- Signature: "dò một đêm" — rê/Tab vào một cột sáng cả chồng, bảng đọc liệt kê mọi khách sạn đêm đó.

## Proof and constraints
Mọi số phòng mang một dấu: vàng (chính xác, đậm dần khi ít phòng), sọc (ít nhất), viền đứt (ẩn số), tím đậm HẾT. Số mức khách sạn là tổng các loại phòng có số chính xác. Giá không quy đổi. Không dùng xanh lá cho đối thủ, không dùng tím để trang trí.

## Open follow-ups
- Backend: DateCell chưa có mức sàn "≥N" ở mức khách sạn nên ô chỉ phân biệt chính xác / ẩn.
- Prompt bản tin: `data_quality_note` còn lộ tên trường (exact_share_7d, unknown).
- Bảng đọc che vài cột bên cạnh cột đang rê.
