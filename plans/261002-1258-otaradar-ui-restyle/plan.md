# Restyle dashboard theo giao diện mẫu OTARadar

Nguồn mẫu: `job/a744199ff3377d692426.jpg` (Terminal+), `job/hoteil.jpeg` (Dashboard), `job/hotel2.jpeg` (Availability), `job/hotel3.jpeg` (Rates).
Quyết định (2026-10-02): nhãn tiếng Việt, thương hiệu **OTARadar**, đủ 8 tab, tiền VND, biểu đồ dùng Recharts.

## Design tokens
- Thanh trên `#0062FF`, chữ trắng; hàng tab trắng, tab active gạch chân xanh.
- Nền `#F5F6FA`, thẻ trắng viền `#E6E8EF` bo 10px, tiêu đề thẻ IN HOA 12px + icon ⓘ.
- Trạng thái: xanh lá `#16A34A` (thấp/tốt), cam `#EA7317` (cao), xanh dương `#0062FF` (vừa), đỏ `#DC2626` (hết).
- Heatmap phòng còn: Hết `#DC2626` · Rất ít `#F97316` · Ít `#FBBF24` · Vừa `#FDE68A` · Khá `#BBF7D0` · Nhiều `#4ADE80`.
- Font Inter (latin + vietnamese).

## Tab → route → dữ liệu
| Tab | Route | Dữ liệu |
|---|---|---|
| Bảng điều khiển | `/dashboard` | overview 14 đêm, market/pace, runs, events |
| Đối thủ | `/competitors` (+ `/hotels/[id]`) | watchlist, overview hôm nay |
| Phòng trống | `/availability` (`/overview` chuyển hướng) | overview 16 đêm, market/pace |
| Giá & định giá | `/rates` | overview 30 đêm (compset) |
| Terminal+ | `/terminal` (+ nội dung `/pace`) | pace, PMS, `/market/holidays`, `/market/weather` |
| Bản tin | `/insights`, `/events` | insights, events |
| Lịch sử quét | `/runs` | runs |
| Cài đặt | `/settings` | giữ nguyên |

Khác mẫu (không bịa số): thẻ Chuyến bay → Tín hiệu đặt phòng từ kênh; ADR/RevPAR/công suất compset ghi "ước tính"; lịch sự kiện chỉ có ngày lễ.

## Pha
1. [x] Tokens + font + khung (TopBar, TabNav, menu người dùng, chuông, chọn tenant) + đổi tên OTARadar + components dùng chung (Panel, Kpi, Gauge, InfoTip, HeatCell, MultiLine chart)
2. [x] Bảng điều khiển
3. [x] Phòng trống (heatmap + phân tích công suất)
4. [x] Giá & định giá (Xu hướng / Vị trí / Heatmap + tình báo cạnh tranh)
5. [x] Backend `/market/holidays`, `/market/weather` (+ test) + Terminal+
6. [x] Đối thủ, Lịch sử quét, Bản tin (tab con)
7. [x] Kiểm tra: typecheck, lint, build, pytest endpoint mới, chụp màn hình từng tab; cập nhật DESIGN.md

## Trạng thái (2026-10-02)
Xong cả 7 pha. Kiểm tra: `tsc --noEmit`, `npm run lint`, `npm run build` sạch; pytest `tests/unit/test_weather.py` (3) + `tests/integration/test_market_api.py` (4) pass; chụp màn hình từng tab trên dữ liệu thật tenant 9.

Chưa làm / cần quyết:
- Thẻ thời tiết cần `OPENWEATHER_API_KEY` trong `.env` rồi tạo lại container api.
- Image Docker (`api`, `dashboard`) chưa build lại: localhost:3000 vẫn là giao diện cũ.
- Icon PWA PNG (`public/icons/*.png`, `apple-icon.png`) vẫn là logo cũ.
- Email backend còn tên ScrapeBooking.

## Review (code-reviewer, 2026-10-02) — đã sửa
- Log lỗi OpenWeather không còn chứa URL có API key; lỗi nhớ 2 phút (`WeatherUnavailable`), thêm test.
- Tín hiệu đặt phòng: chỉ tín hiệu trong 24 giờ, một kênh; lỗi từng khách sạn không làm hỏng thẻ (`allSettled`).
- Heatmap: tổng hiện "≥N" khi thiếu số, "—" khi chưa có; cột "Phòng-đêm".
- Điểm cầu: "≈" khi là công suất ước tính, gạch chấm khi là tỷ lệ hết phòng; ô phân tích công suất có "≈".
- "Hôm nay" theo múi giờ tenant (`useTenantToday`), tự sang ngày.
- Giá chỉ lấy ô còn bán (`bookablePrice`); biểu đồ không nối qua đêm thiếu số.
- Bàn phím: popover focus vào trong/trả về nút, ⓘ là button có `aria-describedby`, thẻ lễ đã qua không còn là link.
