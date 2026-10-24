# Cải tiến UX cho tenant_admin: từ "nhiều bảng số" sang "quyết định buổi sáng"

**Nguồn:** audit `plans/reports/ux-audit-261024-0007-tenant-admin.md`. Mã vấn đề D/S/N/E/L/C/M/F dưới đây trỏ về mục 4 của báo cáo. Ảnh bằng chứng nằm ở `plans/reports/assets/ux-261024/`.

**Mục tiêu:** quản lý khách sạn mở app mỗi sáng và trong 10–15 phút biết:
1. dữ liệu có đáng tin không;
2. đêm nào cần đổi giá, đổi bao nhiêu VND, vì sao (nói bằng lời);
3. đối thủ nào vừa hết phòng hoặc đổi giá.

Họ ghi lại quyết định mà không phải đi qua quá 3 màn.

**Trạng thái:** đã triển khai (24/10), chưa commit. Migration 0019 mới chỉ áp vào DB bản sao `scrapebooking_ux` và DB test. DB dev thật `scrapebooking` vẫn ở 0018: chạy `alembic upgrade head` trước khi chạy API/worker bằng code mới. Người dùng giao: "tự nghiên cứu và làm hoàn thiện toàn bộ các phase".

## Quyết định Q1–Q9 (24/10, người dùng giao cho tôi quyết theo đề xuất trong báo cáo)
| # | Quyết định |
|---|---|
| Q1 | 5 tab theo công việc, giữ nhận diện OTARadar (thanh xanh, tab ngang trên desktop). Mobile dùng thanh đáy 5 mục. Tab đầu giữ tên **"Hôm nay"**, không dùng "Sáng nay", vì app mở cả ngày. Cập nhật DESIGN.md và PRODUCT.md. |
| Q2 | Hướng (b). Khi khách sạn chưa đặt chiến lược, "tăng giá" phải có tín hiệu cầu, giống "giảm giá" đang bắt buộc. Nếu chỉ lệch ≥10 điểm so với mức thường của chính khách sạn thì vẫn gợi ý, nhưng ghi rõ "giá đêm này thấp hơn mức thường của bạn" và tin cậy thấp. Lệch <10 điểm thì giữ giá. |
| Q3 | Một ngưỡng duy nhất là cờ `stale` sẵn có (quá một chu kỳ quét, `stale_after_hours`). Khi `stale`: không hiện việc cần làm, khoá nút ghi quyết định. |
| Q4 | Có. Cảnh báo khi giá giữa nhóm đối thủ ≥1,6 lần giá của bạn, ở thẻ Thiết lập và ở Cài đặt › Khách sạn & đối thủ. |
| Q5 | Bỏ tên "Terminal+". Phần thị trường khu vực, mức căng 14 đêm và lịch sự kiện chuyển sang "Thị trường". Nhịp/OTB/doanh thu chuyển sang "Báo cáo › Nhịp đặt phòng". Kết quả gợi ý chuyển sang "Báo cáo › Kết quả gợi ý". |
| Q6 | Kênh gửi chưa cấu hình thì ẩn với tenant. Nếu không còn kênh nào, ghi một câu "Đơn vị vận hành chưa bật gửi tin; cảnh báo vẫn có trong chuông". |
| Q7 | Bỏ "Lịch sử quét" khỏi tab. Pill độ mới trên thanh trên mở ngăn "Tình trạng dữ liệu", có link tới `/runs` bản rút gọn (tenant không thấy cột kỹ thuật và mã lượt). |
| Q8 | Ẩn thẻ Thời tiết với tenant khi chưa có `OPENWEATHER_API_KEY`. Tính năng giữ nguyên. |
| Q9 | Giữ `scrapebooking_ux` làm DB thử tới khi xong toàn bộ. Không xoá. |

## Cấu trúc điều hướng chốt (dùng cho mọi phần việc)
| Tab (vi / en) | Route | Gom từ | URL cũ chuyển hướng |
|---|---|---|---|
| Hôm nay / Today | `/today` | Hôm nay + Bảng điều khiển | `/dashboard` → `/today` |
| Lịch giá & phòng / Rate calendar | `/calendar?view=rooms\|rates&start=&days=&basis=` | Phòng trống + Giá & định giá | `/availability`, `/overview` → `?view=rooms`; `/rates` → `?view=rates` (giữ query) |
| Đối thủ / Competitors | `/competitors` (+ `/competitors/radar`, `/competitors/market`, `/hotels/*`) | như cũ | |
| Thị trường / Market | `/market` | phần thị trường của Terminal+ | `/terminal` → `/market` (`#pace` → `/reports/pace`) |
| Báo cáo / Reports | `/insights`, `/events`, `/reports/pace`, `/reports/outcomes` | Bản tin, Thay đổi, phần nhịp/OTB/kết quả của Terminal+ | `/pace` → `/reports/pace`; `/reports` → `/insights` |
| ⚙ Cài đặt (thanh trên) | `/settings` | | |
| (không nằm trên tab) | `/runs` | Lịch sử quét bản rút gọn, mở từ ngăn Tình trạng dữ liệu | |

Gợi ý giá chỉ có ở hai nơi:
- danh sách "Việc cần làm" trên Hôm nay (14 đêm, nút ghi quyết định ngay trên thẻ);
- thẻ gợi ý ở đầu chi tiết đêm của khách sạn bạn.

Lịch và Hôm nay chỉ đánh dấu đêm có gợi ý, không lặp thẻ. Bấm ô trên Lịch thì mở trang chi tiết đêm, không làm ngăn kéo (KISS). Trang đêm có thẻ "Cùng đêm trên Booking.com" ở đầu, nên T2 vẫn ≤2 click.

## Ràng buộc giữ nguyên
- Booking.com là kênh duy nhất. VND cố định. Không bịa số, không thêm tính năng cần dữ liệu ta không có.
- Tên chỉ số theo PRODUCT.md: giá niêm yết ≠ ADR; chỉ báo lấp đầy ≈ ≠ occupancy; ADR, RevPAR và công suất chỉ dùng cho số PMS.
- Nhận diện OTARadar theo DESIGN.md (thanh xanh #0062ff, thang nhiệt, "≈", thẻ bo 10–12px). Mọi chữ mới đi qua catalog vi/en và qua `npm run i18n:check`.
- Không chạm dữ liệu thật của tenant 9. Mọi thử nghiệm làm trên bản sao DB (`scrapebooking_ux` hoặc bản sao mới).

## Pha
| Pha | Nội dung | Vấn đề xử lý | Công sức | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| [1](phase-01-quick-wins-copy-empty-states-bugs.md) | Quick wins: chặn gợi ý khi dữ liệu cũ, sửa chữ, ẩn thẻ rỗng, sửa lỗi hiển thị, tràn ngang, tương phản | D1 D3 D4 D5 D6 D7 D9 · S1(câu chữ) S2 S4 · E1–E4 · L2 L4 L5 · C5 C6 · M1 M4 · F2 F4 · N7 | 2 ngày (1 FE + ½ BE) | không | xong 24/10 |
| [2](phase-02-navigation-and-core-screens.md) | Tái cấu trúc điều hướng: Sáng nay, Lịch giá & phòng, Đối thủ "7 ngày qua", tách Terminal+, lớp tin cậy dữ liệu chung, logic gợi ý | N1–N6 N8 · D2 D8 · S1(logic) S3 S5 S6 · F1 F3 · L1 L3 L6 · M2 M3 M5 · C4(hàng PMS) | 8–10 ngày | Q1 Q2 Q3 Q5 Q7 | xong 24/10 |
| [3](phase-03-onboarding-settings-alerts.md) | Onboarding 5 bước, Cài đặt gọn, "Ai nhận gì", chiến lược có xem trước, email sáng = Sáng nay | C1 C2 C3 C4(luồng nhập) C7 · cảnh báo nhóm đối thủ lệch giá (Q4) | 5–7 ngày | Phase 2, Q4 Q6 Q8 | xong 24/10 (trừ mời qua email, cột lần đăng nhập cuối) |

## Chỉ số nghiệm thu toàn dự án
Đo lại bằng đúng kịch bản của audit (Playwright, 1440px và 375px, vi/en), chạy trên bản sao DB ở hai chế độ "thực tế" và "vừa quét".

| Tác vụ | Hiện tại | Đích sau Phase 2 | Đích sau Phase 3 |
|---|---|---|---|
| T1 việc sáng nay (thấy + hiểu + ghi quyết định một đêm) | 0 click để thấy, ngõ cụt khi bấm, 2–3 phút | ≤3 click, ≤30 giây, không cuộn quá 1 màn hình | như Phase 2 |
| T2 một đêm: giá tôi vs đối thủ, ai hết, còn bao nhiêu | 2 click (6 click cho dịp lễ) | ≤2 click cho mọi đêm trong 90 ngày (có bộ chọn ngày), ≤20 giây | như Phase 2 |
| T3 một đối thủ đổi gì 7 ngày | 4 click, 200 dòng nhiễu | ≤2 click, một thẻ tóm tắt ≤6 dòng | như Phase 2 |
| T4 thị trường 14 đêm | 1 click + cuộn 830px, 6/14 đêm | ≤1 click, thấy ngay đầu tab Thị trường | như Phase 2 |
| T5 thêm đối thủ / đổi giờ quét | 3 / 4 click | ≤3 / ≤4 click | như Phase 2 |
| T6 cảnh báo hết phòng + thêm viewer | bị chặn (email chưa cấu hình), 2 nơi thêm người nhận | không đổi | ≤4 click mỗi việc, một nơi thêm người nhận |
| T7 nhập PMS, xem cạnh compset | heatmap không có hàng PMS; chỉ là một đường ở biểu đồ cuối Phòng trống, trùng màu Park Hyatt, kèm dòng "chưa có PMS" | hàng PMS trên Lịch giá & phòng | một luồng nhập, ≤3 click |
| T8 dữ liệu mới không, tin tới đâu | chữ đỏ ở một số màn, Lịch sử quét xanh sai | Phase 1: mọi màn có số Booking báo tuổi dữ liệu. Phase 2: pill trên thanh trên, 1 click ra "Tình trạng dữ liệu" | như Phase 2 |
| T9 áp dụng/bỏ qua và kiểm tra | 2 click + cuộn 1.600px, không hoàn tác tại chỗ | Phase 1: toast có Hoàn tác. Phase 2: ≤2 click, kết quả ở Báo cáo ≤2 click | như Phase 2 |

Kiểm tra tự động (thêm ở Phase 1, chạy lại mỗi pha):
- Tràn ngang = 0px trên mọi route tenant ở 375px, cả vi và en.
- Không chuỗi nào trong giao diện tenant chứa `API_KEY`, `#<số lượt>`, `OPENROUTER`, `request`.
- Khi `/data-status.stale = true`: không có nút Áp dụng nào bấm được, và mọi màn có số Booking đều hiện tuổi dữ liệu.
- Tương phản chữ ≥4,5:1 (kiểm `--sb-faint`, ô cũ và chữ trong ô heatmap).
- `npm run i18n:check` 0 lỗi. `npm run lint`, `npm run typecheck` và pytest phần chạm tới đều xanh.

## Rủi ro chung
- **Đổi điều hướng làm người dùng hiện tại lạc đường.** Giữ redirect cho mọi URL cũ (`/dashboard`, `/availability`, `/rates`, `/terminal`, `/pace`, `/overview`, `/insights`, `/events`, `/runs`). Thêm dòng "Bảng điều khiển nay là Sáng nay" trong 2 tuần.
- **Lệch DESIGN.md (8 tab theo mẫu khách hàng).** Cần Q1 trước Phase 2. Cập nhật DESIGN.md và PRODUCT.md cùng lúc với code.
- **Đổi logic gợi ý làm thay đổi số người dùng đã quen.** Ghi rõ trong changelog. Chạy `suggestions/backtest` trước và sau.
- **Working tree đang có nhiều thay đổi chưa commit** (market ladder 16/10). Làm mỗi pha trên nhánh riêng sau khi phần đó đã commit.
