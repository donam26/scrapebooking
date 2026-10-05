# Phase 1: Định vị giá, thứ hạng, ngày lễ, câu giải thích từng đêm

Trạng thái: done · Effort: S–M

## Backend
- `app/analytics/compset.py` `CompsetDay` thêm:
  - `own_rank: int | None`: hạng giá của bạn trong các khách sạn có giá đêm đó (1 = rẻ nhất; bằng giá thì cùng hạng).
  - `priced_hotels: int`: số khách sạn có giá (gồm bạn).
- `OverviewOut.holidays: list[HolidayOut]` (`date`, `name`) theo `tenant.country_code` trong khoảng xem (dùng `holidays_between`).
- `DayDetailOut` thêm `compset: CompsetDayOut | None` và `holiday: str | None` cho đêm đó.
- `make openapi` → `npm run gen:api`.

## Dashboard
- `lib/night-reason.ts` (mới, thuần): `nightReason(c, holiday)` → câu sự thật, ví dụ
  "4/6 đối thủ đã hết phòng · giá bạn thấp hơn trung vị 12% (rẻ thứ 2/6) · trùng Quốc khánh". `null` khi không có gì để nói.
- `overview/board.tsx`:
  - Thẻ Thị trường: hàng "Giá bạn so trung vị (%)" theo lưới cột chung; số có dấu (−12, +8, 0) 11px/700 thẳng cột; |Δ| ≥ 15 dùng chip tông chú ý (nâu trên vàng cảnh báo), còn lại chữ phụ. Chỉ hiện khi có khách sạn của bạn. Cột đang dò nền tím phớt như thước đo hết phòng.
  - Trục: ngày lễ có chấm mực 4px dưới số ngày, `title` = tên lễ; chú giải "Ngày lễ" trong hàng chú giải.
  - Bảng đọc: tên lễ dưới đầu; thêm dòng "Hạng giá của bạn: rẻ thứ k/n"; câu giải thích 13px ở cuối.
- `overview/page.tsx` dải số đo: ô "Giá của bạn so với trung vị đối thủ" thêm hạng đêm đầu kỳ vào gợi ý.
- `hotels/[id]/dates/[date]/page.tsx`: ghi chú thông tin đầu trang với câu giải thích + ngày lễ (chỉ khi có).

## Kiểm thử
- Unit: rank (bằng giá, thiếu giá của bạn, không đối thủ), holidays trong overview.
- Integration: `/overview` trả `holidays`, `own_rank`; `/hotels/{id}/dates/{d}` trả `compset`.
- UI: typecheck, lint, ảnh chụp.

## Tiêu chí xong
Rê một đêm thấy hạng + câu giải thích + lễ; hàng % thẳng cột với dải; không phá bốn dấu.
