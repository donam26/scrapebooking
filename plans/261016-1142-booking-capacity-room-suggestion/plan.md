# Gợi ý "Số phòng" đối thủ — chỉ đo trên Booking.com

**Mục tiêu:** tenant bản free không phải tự gõ "Số phòng" của đối thủ: hệ thống đề xuất một con số kèm nguồn, người dùng bấm xác nhận. Không ghi đè số đã xác nhận.

**Quyết định của người dùng (16/10):** không dùng Trip.com, chỉ dùng Booking.com. Booking không công bố tổng số phòng (đã soát trang đầy đủ của 5 khách sạn: không có trường nào, mô tả của khách sạn cũng không nhắc), nên gợi ý = **số phòng nhiều nhất Booking bán được trong một đêm**, đo bằng lịch GraphQL `nbRooms` trên các đêm xa (ít người đặt).

## Bằng chứng (kiểm live 16/10, IP trực tiếp, ~16 request lịch)
| Khách sạn | Công bố | Đo trên Booking (cửa sổ 15/12/2026 → 13/02/2027, 61 đêm) |
|---|---|---|
| Meander | 42 phòng + giường dorm | còn ở N=90 (26/61 đêm), N=100 → 0 đêm ⇒ 90–99 **đơn vị bán** (giường dorm) |
| Reverie | 286 | còn ở N=100 (46/61 đêm) ⇒ "≥100" |
| Caravelle | 335 | N=110 → lỗi 500 (trần lịch = 100; 120 cũng lỗi) |
- Số đêm còn giảm dần theo N (Meander 61/61/58/55/51/51/49/44/26/0 ở N=1/62/68/71/73/75/76/80/90/100) ⇒ tìm nhị phân được.
- Lỗi 500 có thể **tạm thời** (Meander N=75 lỗi, gọi lại → 51 đêm) ⇒ lỗi = chưa biết, thử lại 1 lần, không coi là "hết".
- Tên loại phòng Booking lộ giường dorm ("Bed in 8-Bed Mixed Dormitory Room") ⇒ cờ "đếm cả giường".
- Nguồn khác đã thử rồi bỏ theo quyết định trên: Trip.com "Number of Rooms" (3/5 khớp, Caravelle 327, Park Hyatt 253), Wikipedia infobox (Rex 286, Caravelle 335).

## Thiết kế
- `listings.capacity_max` int, `capacity_capped` bool, `capacity_checked_at` tz, `capacity_next_at` tz (migration 0017): kết quả đo lớn nhất (≤100), có chạm trần 100 không, lần đo xong gần nhất, lúc đo lại.
- `app/worker/capacity_probe.py`: `search_capacity()` thuần (nhị phân N∈[1,100], N=1 trước để biết cửa sổ có hàng, rồi 100, lỗi thử lại 1 lần, dừng giữa chừng vẫn giữ cận dưới); `run_measure_capacity()` (cửa sổ = hôm nay+60, 61 đêm; ghi max đơn điệu; chỉ chốt `checked_at` khi đo xong); `due_capacity_listings()`.
- Lịch đo: ngay sau verify listing thành công + cron hằng ngày ở worker `jobs` (chưa đo hoặc đo >30 ngày). Job `measure_capacity` chạy ở worker Booking (dùng session/proxy/ngân sách/giãn cách sẵn có), bỏ qua khi kênh đang tạm dừng.
- `app/domain/capacity.py`: `sells_beds()` theo tên loại phòng; `rooms_suggestion()` = max(capacity_max, rooms_max_seen), `capped` khi chạm trần ⇒ không cho xác nhận.
- API: `HotelOut.rooms_suggestion {rooms, capped, includes_beds, measured_at, source_url}`; `POST /watchlist/{hotel_id}/rooms-suggestion/confirm {rooms}` → ghi `rooms_total` + nguồn = URL Booking; 409 khi đã có số / không có gợi ý / chỉ là cận dưới / gợi ý đã đổi.
- UI Cài đặt › Watchlist cạnh "Số phòng": "Booking bán tối đa N phòng/đêm · [Dùng N]", cảnh báo giường dorm, "≥100: nhập số công bố"; i18n vi/en + errors.ts.
- CLI `sb measure-capacity [--hotel-id] [--force]` (đẩy job).

## Việc
- [x] Domain + search thuần + unit test
- [x] Migration 0017 + model + job + verify hook + cron + CLI + integration test
- [x] API schema/view/confirm + test API; openapi + api-types
- [x] Dashboard UI + i18n + errors
- [x] docs/operations.md
- [x] pytest toàn bộ, ruff, mypy; dashboard typecheck/lint/i18n:check

## Kết quả (16/10)
- Đo thật bằng job (collector Booking, IP trực tiếp, DB clone): Meander **94** đơn vị (9 request, 42 phòng + giường dorm), Reverie **≥100** (2 request).
- Giao diện kiểm bằng Playwright (desktop + 390 px, vi/en): gợi ý + nút "Dùng 94", cảnh báo dorm, "≥100 → nhập số công bố"; bấm dùng → ô "Số phòng" = 94, nguồn = URL Booking.
- `pytest` 583 pass; ruff, mypy sạch; dashboard typecheck/lint/i18n:check sạch.
- Review độc lập (subagent code-reviewer), đã sửa: gợi ý chỉ khi đo xong VÀ cửa sổ xa có phòng (không dựa sàn đêm gần); trả lời lịch rỗng = chưa biết; nút "Dùng N" chỉ khi số đo chính xác, không cận dưới (trần 100, hoặc quét thường thấy nhiều hơn), không đếm giường dorm; số lấy từ gợi ý (nguồn = URL Booking) là ước tính, tenant khác thay được; đổi URL Booking xoá số đo cũ; chỉ hỏi lại lỗi GraphQL/5xx, bị chặn/lỗi mạng thì dừng; `capacity_next_at` (xong +30 ngày, không có phòng +7, dở +1); cron/CLI chỉ đo khách sạn chưa có số phòng, ≤20 listing, giãn 2 phút; ghi nguyên tử (GREATEST), `--force` thay kết quả cũ; regex dorm chặt hơn; UI: ngày đo theo giờ địa phương, dòng gợi ý xuống dòng được (360 px), lỗi hiện riêng, tải lại khi xác nhận lỗi.
- DB dev `scrapebooking` vẫn ở 0016 (chưa commit tính năng này); chạy `alembic upgrade head` trước khi khởi động lại API/worker với code mới.

## Câu hỏi mở
- Khách sạn >100 phòng chỉ ra "≥100" (trần lịch Booking): vẫn phải nhập tay số công bố.
- Đơn vị bán ≠ phòng khi có giường dorm; số gợi ý có thể lớn hơn số phòng thật.
