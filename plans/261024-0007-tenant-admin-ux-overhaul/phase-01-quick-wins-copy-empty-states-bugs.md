# Pha 1: Quick wins (2 ngày): chặn gợi ý khi dữ liệu cũ, sửa chữ, thẻ rỗng, lỗi hiển thị

## Mục tiêu
Pha này không đổi điều hướng hay bố cục lớn. Chỉ dừng các chỗ đang làm mất niềm tin: ra lệnh trên dữ liệu cũ, số mâu thuẫn, chuỗi kỹ thuật lộ ra, thẻ rỗng, tràn ngang. Sau pha này, T8 trả lời được ở mọi màn. T1 không còn khuyên tăng giá trên dữ liệu 8 ngày tuổi.

## Việc cụ thể

### A. Dữ liệu cũ (RC1)
1. **D1: Chặn "Việc cần làm" và thẻ gợi ý khi `stale`.** `TodayActions` đọc `useDataFreshness()`. Khi `stale`, khối "Việc cần làm" chỉ còn một thẻ cảnh báo:
   > **Chưa đưa gợi ý giá.** Booking.com chưa có số mới từ 18:36 16/10 (8 ngày). Gợi ý dựa trên giá cũ có thể sai. [Xem tình trạng quét]

   Thẻ `SuggestionCard` khi `stale`: viền xám, thêm dòng "Dựa trên giá ngày 16/10", nút "Đã áp dụng" bị `disabled` kèm `title` giải thích.
2. **D3: Khám phá thị trường.** Tiêu đề cột "Giá đêm nay" đổi thành "Giá đêm {dd/mm}" lấy từ đêm của lượt quét danh sách. Khi đêm ≠ hôm nay của tenant thì thêm chip cảnh báo "cũ". Dòng "Quét danh sách 19:07 16/10" dùng màu cảnh báo khi quá 24 giờ.
3. **D4: Lịch sử quét.** Thay 4 KPI bằng một câu trạng thái lấy từ `/data-status`:
   - xanh: "Đang quét đều: lần đọc cuối 18:36 hôm nay, 7 ngày qua đọc thành công 100%";
   - đỏ: "Không có lượt quét nào từ 18:36 16/10 (8 ngày)".

   "Lượt quét 24 giờ = 0" tô đỏ, không tô xanh. Ẩn các cột "Đọc trang", "Bị chặn", "Lỗi" và mã `#id` với tenant (operator vẫn thấy).
4. **D5: Ô heatmap cũ.** Bỏ `filter: grayscale(1); opacity: .45` ở `.sb-stale`. Thay bằng sọc chéo 45° mảnh trên góc phải ô (6px) và giữ màu nhiệt. Đầu cột có chip "Số từ 16/10". Chữ trong ô phải đạt ≥4,5:1.
5. **D6: Trạng thái rỗng của Thay đổi.** Khi `stale` hoặc không có lượt quét trong khoảng lọc, hiện: "Chưa có lượt quét nào sau 18:36 16/10 nên chưa có thay đổi mới". Câu cũ "Thử nới khoảng thời gian…" chỉ dùng khi có lượt quét.
6. **D7: Tuổi dữ liệu trên mọi màn có số Booking.** Radar, Bản tin AI, Chi tiết đêm và Khám phá dùng `PageStrip`/`freshness` như các màn khác. Bản tin ghi "Bản tin ngày 16/10 · 8 ngày trước" khi bản mới nhất cũ hơn 1 ngày. Radar bỏ câu "Từ dữ liệu đã quét, không tốn thêm lượt quét".
7. **D9: "Còn N ngày" sai.** `hotels/[id]/page.tsx:273` tính khoảng cách từ hôm nay của tenant (`addDays`/`today` như các màn khác), không dùng `m.days_to_arrival`.

### B. Gợi ý giá: chữ và tương tác (RC3, chưa đổi logic)
8. **S1 (câu chữ): Chiến lược giá.** `rms.json:5` (vi/en) đổi thành:
   > Chưa có chiến lược riêng: hệ thống giữ vị trí giá thường ngày của bạn (≈{index}% giá giữa của đối thủ, đo 30 ngày tới). Lưu để đặt vị trí khác.

   `{index}` lấy từ API (thêm `typical_index` vào response của `/market/strategy` khi chưa lưu).
9. **S2: Lý do bằng lời.** `backend/app/i18n/locales/{vi,en}.json` `price.position*`: chuyển sang câu thường, số do frontend định dạng (L4):
   > Đối thủ bán đêm này khoảng {median}; bạn thường bán bằng {target}% giá đó → mức hợp lý {reference}.

   Câu "Đã giới hạn ở mức đổi tối đa mỗi ngày" đổi thành "Mỗi ngày không đổi quá {pct}% (cài ở Chiến lược giá)". Công thức gốc để trong `<details>` "Cách tính".
10. **S4: Ghi quyết định.**
    - Nhãn "Đã áp dụng" → "Tôi đã đổi giá"; "Bỏ qua" giữ nguyên.
    - Ô giá định dạng `3.700.000` khi gõ.
    - Sau khi ghi: toast 8 giây "Đã ghi T2 26/10 → 3.700.000 ₫ · Hoàn tác".
    - Thẻ thu thành một dòng xám "Đã ghi 3.700.000 ₫ · Hoàn tác" ngay tại chỗ, không biến mất.

### C. Thẻ rỗng (RC5)
11. **E1: Bảng điều khiển.**
    - Thẻ "Khách sạn của bạn" lấy số chính là vị trí giá ("Rẻ hơn giá giữa đối thủ 45%", hạng 2/5). "Công suất đêm nay" thành dòng phụ, ẩn khi không có số.
    - "Mức căng thị trường (hiện tại)" ẩn khi <2 đêm có số. Đổi tên thành "Đối thủ hết/sắp hết phòng 14 đêm" (N5 bản nhỏ).
    - Thẻ "Chỉ báo lấp đầy" ẩn khi "chưa đủ số". Chú giải chỉ liệt kê chuỗi có dữ liệu.
12. **E2: Terminal+.**
    - Ẩn "Thời tiết" khi thiếu key. Operator thấy cảnh báo ở `/admin/health`.
    - "Doanh thu của bạn", "OTB", "Gợi ý đã áp dụng → Kết quả" gom thành một thẻ "Nhập PMS để mở: doanh thu 14 ngày, phòng đã đặt, kết quả gợi ý [Nhập PMS]".
    - Bảng "Từng đêm" ẩn cột toàn "—" hoặc "chưa đủ lịch sử".
13. **E3: Phòng trống › Chỉ báo lấp đầy.** Khi <2 khách sạn có ước tính, thu thành một dòng: "Chưa đủ số để ước tính lấp đầy cho đa số đối thủ (Booking.com chỉ lộ ≥N phòng)". Bỏ "0/1 KS ≈≥90% đêm đầu". Khi đã nhập PMS thì bỏ dòng "chưa hiệu chỉnh (chưa có PMS)". Đường "Của bạn (PMS)" dùng màu xanh thương hiệu nét đứt, không trùng màu chuỗi khách sạn nào (hiện trùng xanh lá của Park Hyatt, ev-07b). Câu kết quả nhập PMS ở `settings.json:574` đổi thành "Công suất đã nhập hiện ở biểu đồ Chỉ báo lấp đầy (Phòng trống) và thẻ Khách sạn của bạn", cho tới khi Phase 2 thêm hàng PMS vào lưới.
14. **E4: Radar.** Ẩn biểu đồ "Tỷ lệ đối thủ đang khuyến mãi theo đêm" khi các cột bằng nhau. Tách dòng Rex thành "Khuyến mãi của bạn" dưới đường kẻ.

### D. Ngôn ngữ và chi tiết nội bộ (RC4)
15. **L2: Ẩn chi tiết nội bộ.**
    - Không render `OPENWEATHER_API_KEY` với tenant.
    - API `/insights` lọc bản `failed` hoặc output giả cho vai trò tenant (F4).
    - "Đã gửi gần đây" ẩn nội dung bản tin giả.
    - Bỏ cột "Lượt #id" ở chi tiết đêm (`hotels/[id]/dates/[date]/page.tsx:540-559`).
16. **L4: Số theo locale.** Backend trả số thô trong `params` của lý do. Frontend `fmtMoney` theo locale (`3,700,000 ₫` ở en). Đổi tên tenant 9 thành tên khách sạn thật: đây là thao tác dữ liệu do operator làm qua `/admin/tenants`, không sửa code.
17. **L5:** Một kiểu tiền rút gọn "6,1 tr" / "6.1M" (`lib/format.ts:180` khớp `messages/*/format.json:16`). `dashboard.json:34` "Giá niêm yết TB đối thủ" → "Giá giữa của đối thủ (niêm yết)".
18. **N7:** Breadcrumb chi tiết đêm của khách sạn bạn là "Khách sạn của bạn › Đêm …". Dropdown ở Thay đổi bỏ hậu tố "(của bạn)" khi nhãn đã có "(của tôi)".

### E. Cài đặt nhỏ, mobile, khả năng đọc
19. **C5: Thêm người dùng.** Vai trò mặc định "Chỉ xem". Ô mật khẩu có `aria-label`. Thêm nút "Tạo mật khẩu" (sinh 12 ký tự rồi sao chép).
20. **C6:** Chip "✓ Booking.com" trong ô URL chỉ xanh khi URL khớp mẫu trang khách sạn.
21. **F2:** Chi tiết đêm có <2 lượt quét thì thay hai biểu đồ bằng câu "Mới có 1 lượt quét cho đêm này (18:27 16/10)".
22. **M1: Tràn ngang 375px.** Sửa Radar (bảng Chính sách huỷ và chip KM), Bảng điều khiển, Terminal+, Phòng trống, Khám phá, Cài đặt › Thị trường, Giá, Lịch sử quét: `min-w-0`, `flex-wrap`, bảng cuộn trong khung.
23. **M4: Tương phản.** `--sb-faint` dùng cho chữ đổi sang ≥4,5:1 (ví dụ #6b7280 cho chữ). Giữ #9ca3af cho đường kẻ và biểu tượng: tách token `--sb-faint-line`. Chữ nhỏ nhất 12px.
24. **Kiểm thử hồi quy (RC7).** Đưa script chụp và đo của audit vào repo (`dashboard/scripts/ux-audit-shots.py` hoặc Playwright test) với các kiểm tra tự động ở `plan.md`.

## File bị ảnh hưởng
- `dashboard/src/components/today-actions.tsx`, `market-suggestion.tsx`, `page-strip.tsx`, `freshness.tsx`, `ui.tsx` (toast nếu chưa có)
- `dashboard/src/lib/freshness.ts`, `lib/format.ts`, `lib/market.ts`
- `dashboard/src/app/(app)/today/page.tsx`, `dashboard/page.tsx`, `dashboard/side-cards.tsx`, `dashboard/market-tightness.tsx`
- `dashboard/src/app/(app)/competitors/market/page.tsx`, `competitors/radar/page.tsx`
- `dashboard/src/app/(app)/hotels/[id]/page.tsx`, `hotels/[id]/dates/[date]/page.tsx`
- `dashboard/src/app/(app)/availability/heatmap-table.tsx`, `availability/occupancy-analysis.tsx`
- `dashboard/src/app/(app)/terminal/page.tsx`, `terminal/terminal-cards.tsx`, `pace/pace-view.tsx`
- `dashboard/src/app/(app)/events/page.tsx`, `runs/page.tsx`, `insights/page.tsx`, `insights/insight-view.tsx`
- `dashboard/src/app/(app)/settings/users-tab.tsx`, `settings/watchlist-tab.tsx`, `settings/strategy-tab.tsx`
- `dashboard/src/app/globals.css` (`.sb-stale`, `--sb-faint`)
- `dashboard/src/messages/{vi,en}/` `rms.json`, `components.json`, `today.json`, `dashboard.json`, `events.json`, `runs.json`, `terminal.json`, `format.json`
- `backend/app/i18n/locales/{vi,en}.json`, `backend/app/market/pace_report.py` (params số thô, `typical_index` cho response chiến lược), `backend/app/api/routers/insights.py` (lọc theo vai trò), `backend/app/api/routers/market.py` (strategy response)

## Tiêu chí nghiệm thu (đo được)
- Chế độ thực tế (`stale=true`): Hôm nay và Bảng điều khiển không có nút "Tôi đã đổi giá" nào bấm được. Khối việc cần làm chỉ còn một thẻ cảnh báo. Ảnh so sánh trước/sau đặt trong `plans/reports/assets/`.
- 12/12 màn tenant có số Booking hiện tuổi dữ liệu (đếm bằng script: tìm "Dữ liệu mới nhất" hoặc chip tuổi).
- Lịch sử quét ở chế độ thực tế không có số "0" màu xanh. Câu trạng thái màu đỏ.
- Chi tiết KS ngày 24/10 ghi "Đêm nay", không ghi "Còn 8 ngày".
- Không chuỗi nào chứa `API_KEY`, `đầu ra giả` hay mã `#<số>` trong 24 route tenant (grep DOM qua script).
- Tràn ngang = 0px trên 24 route × 375px × vi/en.
- Tương phản ô heatmap cũ ≥4,5:1. `--sb-faint` cho chữ ≥4,5:1.
- T9: sau khi ghi, thẻ còn trên màn với "Hoàn tác". Bấm Hoàn tác thì gợi ý trở lại (1 click).
- `npm run i18n:check`, `npm run lint`, `npm run typecheck` xanh. Pytest `tests/unit` và `tests/integration` cho market, insights và i18n xanh.

## Rủi ro
- Chặn gợi ý khi `stale` dựa trên định nghĩa `stale_after_hours = 10`. Nếu proxy chập chờn, khối việc cần làm sẽ tắt/bật nhiều lần (Q3: có thể dùng 2 mức, mờ ở 10 giờ và ẩn ở 24 giờ).
- Đổi `.sb-stale` ảnh hưởng mọi nơi dùng lớp này (chi tiết KS, Phòng trống). Cần chụp lại cả hai.
- Đổi chuỗi lý do ở backend ảnh hưởng email cảnh báo và bản tin (`app/notify`, `app/insights`) nếu chúng dùng chung khoá i18n. Grep `price.position` trước khi đổi.
