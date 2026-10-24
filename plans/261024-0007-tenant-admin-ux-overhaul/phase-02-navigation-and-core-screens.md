# Pha 2: Tái cấu trúc điều hướng và các màn chính (8–10 ngày)

**Cần trước:** Q1 (5 tab hay giữ 8), Q2 (logic gợi ý khi chưa có chiến lược), Q3 (ngưỡng cũ), Q5 (bỏ tên Terminal+), Q7 (Lịch sử quét). Nếu Q1 = giữ 8 tab: vẫn làm mục 2, 3, 4, 6, 7, 8, 9. Mục 1 thì chỉ gộp Hôm nay với Bảng điều khiển và đổi tên tab.

## Mục tiêu
Mỗi câu hỏi buổi sáng có đúng một chỗ trả lời:
- Sáng nay làm gì → **Sáng nay**
- Một đêm cụ thể → **Lịch giá & phòng**
- Một đối thủ → **Đối thủ**
- Khu vực → **Thị trường**
- Nhìn lại → **Báo cáo**

Số tin cậy dữ liệu hiển thị cùng một cách ở mọi nơi.

## Việc cụ thể

### 1. Khung app và tên tab (N1, N4, M2)
- `TENANT_NAV` (`components/app-shell.tsx:28-38`) có 5 mục: Sáng nay `/sang-nay` · Lịch giá & phòng `/lich` · Đối thủ `/competitors` · Thị trường `/thi-truong` · Báo cáo `/bao-cao`. Slug cuối cùng chốt theo DESIGN.md, có thể giữ slug tiếng Anh.
- Cài đặt chuyển thành nút ⚙ trên thanh trên.
- Đăng nhập, `manifest.start_url` và logo đều vào Sáng nay (`login/page.tsx:13`, `manifest.ts:16`, `app-shell.tsx:244`).
- Redirect mọi URL cũ, giữ query: `/today`, `/dashboard` → Sáng nay; `/availability`, `/overview`, `/rates` → Lịch; `/terminal`, `/pace` → Thị trường hoặc Báo cáo theo hash; `/insights`, `/events` → Báo cáo; `/runs` → ngăn Tình trạng dữ liệu.
- Mobile <768px: thanh đáy cố định 5 mục (biểu tượng 22px + nhãn 11px, cao 56px). Thanh trên chỉ còn logo, pill dữ liệu, chuông và tài khoản.

### 2. Lớp tin cậy dữ liệu chung (D2, D8)
- Component `DataAge` (`components/freshness.tsx`): chip "16/10 · 8 ngày trước" (cảnh báo khi >10 giờ, đỏ khi >24 giờ). Dùng cho mọi số giá hoặc phòng có quan sát >48 giờ.
- Quy tắc duy nhất: luôn hiện giá trị cuối kèm chip. Không màn nào hiện "—" cho số mà màn khác đang hiện. Riêng trung vị thì loại quan sát >48 giờ và ghi "giá giữa tính trên 3/4 đối thủ, 1 đối thủ số cũ".
- Pill trên thanh trên: "● Cập nhật 18:36" / "● Dữ liệu dừng 8 ngày". Bấm mở ngăn phải "Tình trạng dữ liệu":
  - lần đọc cuối, lượt kế tiếp;
  - dải 7 ngày (mỗi mốc quét một ô xanh/đỏ);
  - tỉ lệ đọc thành công;
  - "Cách đọc số": 5 dòng cho Chính xác / Ít nhất N / N–M / Còn nhưng không lộ số / ≈ ước tính;
  - nút "Báo đơn vị vận hành" (mailto hoặc Zalo nếu có cấu hình).
- Trang `/runs` cho tenant thay bằng ngăn này (Q7).

### 3. Sáng nay: gộp Hôm nay và Bảng điều khiển (N2, S3, S5)
Thứ tự từ trên xuống, desktop 1 cột chính 760px + cột phụ 360px, mobile 1 cột:
1. **Dải tin cậy** (1 dòng): "Số Booking.com lúc 18:36 · 5/5 khách sạn đọc được". Khi cũ thì dùng thẻ cảnh báo của Phase 1.
2. **Việc cần làm** (≤5 thẻ, chỉ đêm có việc thật theo Q2). Mỗi thẻ gồm:
   - đêm (link);
   - nhãn Tăng / Giảm / Đối thủ hết phòng / Đêm căng;
   - giá mục tiêu VND to;
   - một câu lý do (Phase 1, S2);
   - nút "Tôi đã đổi giá" và "Bỏ qua" tại chỗ.

   Đã xử lý thì thu thành dòng xám có "Hoàn tác". Hết việc thì hiện "Không có đêm nào cần đổi giá trong 14 đêm tới. Giá của bạn đang ở mức thường so với đối thủ."
3. **14 đêm của bạn vs đối thủ**: một dải ngang. Mỗi đêm có:
   - ô phòng còn của bạn (màu nhiệt);
   - giá bạn;
   - chênh với giá giữa đối thủ (±%, đỏ khi bạn đắt hơn ≥10%, xanh khi rẻ hơn ≥10%, theo SiteMinder);
   - "x/N hết";
   - chấm nếu có gợi ý.

   Bấm mở ngăn "Đêm này" (mục 4).
4. **Đối thủ đổi gì 24 giờ** gom theo khách sạn: "Caravelle: hết phòng 31/10; giá ↑ 3 đêm (+5%)". Tối đa 5 dòng, link "Nhật ký".
5. **Bản tin**: 3 ý hành động (L6), link "Đọc bản tin".

Cột phụ: Khách sạn của bạn đêm nay (vị trí giá làm số chính), Thiết lập 5 bước (Phase 3).

Gợi ý giá chỉ còn ở đây và trong ngăn "Đêm này". Terminal+ và Bảng điều khiển bỏ các bản sao (S5).

### 4. Lịch giá & phòng: gộp Phòng trống và Giá (N6, C4 hàng PMS, M5)
- Một lưới khách sạn × đêm. Khách sạn của bạn ở trên cùng, có hàng "Công suất PMS" ngay dưới khi đã nhập. Công tắc `Phòng còn | Giá | Chênh với bạn`. Bộ chọn ngày + 14/30/60 (mặc định 14 ở mọi màn). Cơ sở giá `Mọi giá | Hoàn huỷ | Có bữa sáng | Chỉ phòng`. Xuất Excel.
- Bấm ô mở **ngăn "Đêm này"** (drawer phải 420px, mobile toàn màn):
  - câu thị trường;
  - mọi khách sạn: phòng còn, giá, gói, hết/hạn chế;
  - gợi ý của đêm và nút ghi quyết định;
  - link "Chi tiết loại phòng" tới trang đêm hiện có.
- Chú giải còn 5 mục (Hết · Rất ít ≤3 · Ít 4–10 · Còn nhiều · Còn, không lộ số). Phần còn lại trong "Cách đọc ô".
- Biểu đồ xu hướng giá (từ Giá) đặt dưới lưới, thu gọn mặc định.

### 5. Đối thủ: "7 ngày qua" (F1, N8, L3)
- Thẻ đối thủ thêm dòng "7 ngày: giá ↑3 đêm · hết phòng 2 đêm · bật KM".
- Trang đối thủ, đầu trang có thẻ **7 ngày qua**: giá đổi bao nhiêu đêm (min/max %), đêm hết phòng, KM bật/tắt, hạn chế mới.
- Nhật ký bên dưới gom theo đêm, ẩn ±1 phòng mặc định ("Hiện cả thay đổi nhỏ"), không sinh hai dòng cho một biến động.
- Nút "Thêm đối thủ" mở ngăn kéo ngay tại trang (dán URL, hoặc chọn từ danh sách Khám phá cùng tầm giá).
- Tab con: Nhóm đối thủ · Khuyến mãi & hạn chế (Radar cũ) · Tìm khách sạn để theo dõi (Khám phá cũ).
- Gói giá chỉ hiện thẻ tiếng Việt. Quận và thành phố dịch sang tiếng Việt.

### 6. Thị trường: tách từ Terminal+ (N3, N5, F3)
Thứ tự:
1. **Mức căng khu vực 14 đêm** (`market-trend-strip.tsx`) có tuổi dữ liệu.
2. **Hôm nay khu vực**: một câu chính (F3) + "Khách sạn của bạn trên thị trường".
3. **Lịch sự kiện & ngày lễ**.

Thang ≥1/5/10/20/30, phân bố giá và thành phần loại chỗ ở đặt trong "Chi tiết". Bỏ thẻ Thời tiết nếu Q8 = bỏ.

### 7. Báo cáo (N3, L6)
- Tab con: Bản tin AI · Nhật ký thay đổi · Kết quả gợi ý · Nhịp đặt phòng & OTB (chỉ hiện khi có PMS) · Xuất file.
- Prompt bản tin (`backend/app/insights/` prompt version mới):
  - ≤3 ý, mỗi ý theo mẫu "đêm nào → làm gì → vì sao";
  - cấm các từ trong danh sách L1;
  - câu miễn trừ để vào trường `data_notes`, không nằm trong tóm tắt.

### 8. Logic gợi ý (S1 logic, S6), theo quyết định Q2
Đề xuất (b), sửa trong `backend/app/market/pace_report.py` và `market/suggest*`:
- Một đêm chỉ thành "việc" khi có ít nhất một tín hiệu thị trường (đối thủ hết ≥50%, mức căng khu vực ≥ thường lệ, nhịp phòng còn giảm nhanh, ngày lễ) **hoặc** chỉ số giá lệch vị trí thường ngày ≥10 điểm.
- Trường hợp chỉ "lệch vị trí thường ngày" thì nhãn là "Xem lại giá", không phải "Có thể tăng giá".
- Thẻ hiện "Tin cậy thấp" kèm lý do khi <4 đối thủ có giá hoặc dữ liệu >10 giờ. Không hiện nhãn khi tin cậy bình thường.
- Chạy `/market/suggestions/backtest` trước và sau trên bản sao DB. Ghi kết quả vào `reports/`.

### 9. Từ ngữ (L1)
Bảng thay, áp cho mọi catalog vi. en dùng từ tương ứng của nghề.

| Hiện | Thay bằng | Ghi chú |
|---|---|---|
| compset | nhóm đối thủ | ⓘ: "compset" trong ngoặc một lần ở Cài đặt |
| trung vị | giá giữa (của đối thủ) | ⓘ: "một nửa đối thủ rẻ hơn, một nửa đắt hơn" |
| ≥N / cận dưới / mức sàn | còn ít nhất N | |
| OTB | phòng đã đặt (từ PMS) | |
| pickup | đặt thêm 1/7 ngày | |
| pace, STLY | so với các tuần trước / cùng kỳ năm trước | đã có quy tắc trong PRODUCT.md |
| chuẩn CoStar STR | nhóm đối thủ có cân không | link nguồn trong ⓘ |
| KS bật / Booking tự áp | khách sạn tự bật / Booking.com tự giảm | |
| định vị 50 | bạn thường bán bằng ~½ giá đối thủ | |

Mỗi ⓘ tối đa 40 từ. Chuỗi dài nhất của `terminal.json` (119 từ) và `pace.json` (64 từ) tách thành câu ngắn hoặc chuyển vào `<details>`.

### 10. Mobile (M3)
- Thẻ việc gọn (đêm · giá mục tiêu · một câu · nút) ≤140px cao.
- Nhật ký gom theo đêm, sau 20 dòng có "Xem thêm".
- Trang đối thủ trên mobile ≤5.000px.

## File bị ảnh hưởng
- Khung: `components/app-shell.tsx`, `components/sub-tabs.tsx`, `app/login/page.tsx`, `app/manifest.ts`, `src/proxy.ts` (redirect), route mới `app/(app)/sang-nay`, `lich`, `thi-truong`, `bao-cao` (hoặc đổi tên thư mục hiện có), redirect ở `today/`, `dashboard/`, `availability/`, `rates/`, `terminal/`, `pace/`, `overview/`, `insights/`, `events/`, `runs/`.
- Màn: `today/page.tsx` + `dashboard/*` (gộp), `availability/heatmap-table.tsx` + `rates/rate-views.tsx` (gộp lưới), `hotels/[id]/page.tsx`, `hotels/[id]/dates/[date]/page.tsx` (ngăn Đêm này dùng lại phần "Cùng đêm"), `competitors/*`, `terminal/*` (tách), `pace/pace-view.tsx`, `insights/*`, `events/page.tsx`.
- Dùng chung: `components/freshness.tsx`, `page-strip.tsx`, `today-actions.tsx`, `market-suggestion.tsx`, `marks.tsx` (chú giải), `lib/freshness.ts`, `lib/market-metrics.ts`.
- Backend: `app/market/pace_report.py` và module gợi ý (Q2), `app/insights/` (prompt), API tóm tắt "7 ngày qua" cho đối thủ (gộp từ `availability_events` sẵn có, không cần quét thêm) trong `api/routers/data.py` hoặc `market.py`.
- Tài liệu: `DESIGN.md` (mục App OTARadar: tab, Sáng nay, Lịch, ngăn Đêm này), `PRODUCT.md` (Operating Context), `docs/user-flows.md` (C, I, J).

## Tiêu chí nghiệm thu (đo được, Playwright trên bản sao DB, chế độ "vừa quét")
- **T1** ≤3 click và ≤30 giây: mở app → đọc thẻ việc đầu → "Tôi đã đổi giá" → xác nhận. Không cuộn quá một màn hình 1440×900. Trên 375×812 thẻ việc đầu nằm trong màn hình đầu.
- **T2** ≤2 click cho 31/10 và cho 24/12 (Lịch → chọn ngày → ô). Ngăn "Đêm này" liệt kê đủ 5 khách sạn với phòng còn, giá và trạng thái hết/hạn chế.
- **T3** ≤2 click (Đối thủ → thẻ). Thẻ "7 ngày qua" ≤6 dòng, không có dòng ±1 phòng mặc định.
- **T4** ≤1 click (Thị trường). Mức căng 14 đêm nằm trong màn hình đầu và có tuổi dữ liệu.
- **T7** hàng "Công suất PMS" xuất hiện trên Lịch ngay sau khi nhập.
- **T8** 1 click từ mọi màn (pill) ra ngăn Tình trạng dữ liệu.
- **T9** xem kết quả gợi ý ≤2 click (Báo cáo → Kết quả gợi ý).
- Số tab cấp 1 ≤5 (hoặc theo Q1). Không còn khái niệm nào xuất hiện ở hơn 2 màn (đếm theo bảng ở mục 2.1 báo cáo).
- Giá Rex đêm nay giống nhau ở mọi màn (script so DOM giữa Sáng nay, Lịch, Đối thủ, ngăn Đêm này).
- Không trang tenant nào dài quá 4.000px ở 1440px hoặc 8.000px ở 375px.
- Mọi URL cũ redirect đúng (test từng URL).
- Backtest gợi ý: số đêm "việc cần làm" trong 14 đêm của tenant 9 (bản sao) giảm từ 7 xuống chỉ những đêm có tín hiệu. Báo cáo có số trước/sau.

## Rủi ro
- **Khối lượng lớn, chạm nhiều file.** Chia thành 3 PR: (a) khung + redirect + Sáng nay, (b) Lịch + ngăn Đêm này + Đối thủ, (c) Thị trường + Báo cáo + logic gợi ý. Mỗi PR có ảnh trước/sau.
- **Gộp lưới Phòng trống + Giá** là phần UI phức tạp nhất (dò một đêm, trục dính, nhiều chế độ). Dùng lại `heatmap-table.tsx` và thêm chế độ hiển thị, không viết lại.
- **Đổi logic gợi ý** làm đổi số trong email và bản tin đã gửi. Ghi changelog và thông báo trong app.
- **Người dùng quen 8 tab.** Redirect cộng một dòng thông báo 2 tuần. Có thể bật bằng cờ cho từng tenant (`tenants.ui_v2`) nếu cần chạy song song.
