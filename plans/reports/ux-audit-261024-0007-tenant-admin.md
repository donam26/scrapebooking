# Audit UX: OTARadar cho vai trò tenant_admin

Ngày: 24/10/2026. Người đọc: chủ sản phẩm. Plan cải tiến đi kèm: `plans/261024-0007-tenant-admin-ux-overhaul/plan.md`.

**Cách làm.** Tôi chạy app thật với dữ liệu thật của tenant 9 (Rex Hotel Saigon, compset Caravelle, The Reverie, Park Hyatt, Meander). Đăng nhập bằng cookie JWT tự tạo cho `quanly@rexhotel.vn` (tenant_admin), dashboard dev ở :3100, API ở :8001. API chạy trên **bản sao** `scrapebooking_ux` của DB dev, dùng Redis db 2 không có worker nào đọc. Vì vậy mọi thao tác ghi (thêm đối thủ, đổi giờ quét, tạo viewer, nhập PMS, áp dụng gợi ý) không chạm vào DB thật và không gọi tới Booking.com.

Có hai chế độ xem:
- **Thực tế (24/10).** Lượt quét cuối là 18:36 16/10, tức dữ liệu đã cũ 8 ngày (`GET /data-status` → `stale:true`). Đây đúng là thứ quản lý khách sạn thấy sáng nay.
- **Mô phỏng "vừa quét" (16/10 21:30).** Đồng hồ API được đóng băng bằng time-machine, đồng hồ trình duyệt bằng Playwright `clock`. Chế độ này cho thấy màn hình khi dữ liệu mới.

Tôi chụp 96 ảnh ở chế độ thực tế (24 màn × 1440/375 × vi/en), thêm 24 ảnh mô phỏng (12 màn × 1440/375, tiếng Việt). Ảnh nằm trong `plans/reports/assets/ux-261024/`. Ảnh mô phỏng nằm trong `fresh/`. Ảnh bằng chứng đã cắt sẵn có tên `ev-*.jpg`. Số đo tải trang, tràn ngang, lỗi console và lỗi API nằm trong `_shots.json` và `fresh/_shots-fresh.json`. Benchmark lấy từ trang sản phẩm và help center công khai (danh sách nguồn ở mục 6).

Trong git chỉ có ảnh bằng chứng (`ev-*`, `final/task-*`, `final/extra-*`) và file số đo `_*.json`. Bộ ảnh chụp đầy đủ (`vi-*`/`en-*`, ~54MB) chỉ lưu trên máy chạy audit; chạy lại script chụp để tạo lại.

---

## 1. Tóm tắt (1 trang)

Sau 8 ngày không có lượt quét, sáng 24/10 quản lý mở app và thấy hai thứ ngược nhau. Phía trên là một banner đỏ báo dữ liệu đã cũ. Ngay dưới là 7 việc cần làm, việc nào cũng là "tăng giá" (+7% đến +15%). Họ không có cách nào biết nên tin bên nào. Nếu đi tiếp, họ còn gặp 9 tab, 5 nơi có gợi ý giá, 3 thẻ cùng tên "mức căng" mang 3 nghĩa khác nhau, và một trang Terminal+ dài 5.232px. Dưới đây là 10 vấn đề lớn nhất.

| # | Vấn đề | Vì sao quản lý thấy khó | Mức |
|---|---|---|---|
| 1 | **Gợi ý giá chạy trên dữ liệu cũ và tự mâu thuẫn.** Khi dữ liệu cũ 8 ngày, "Việc cần làm" vẫn ra 7 lệnh tăng giá, phần lớn +15% (ev-01). Màn Chiến lược ghi "đang dùng mặc định định vị 100", trong khi gợi ý dùng "định vị thường ngày 50" (ev-03). Cả 12/30 đêm có gợi ý đều là "tăng", lý do là một công thức. | Không biết có nên làm theo không. Dễ tăng giá sai đúng lúc thị trường "không căng" (chính thẻ ghi vậy). | Nghiêm trọng |
| 2 | **Mỗi màn xử lý dữ liệu cũ một kiểu.** Đối thủ hiện "—", Hôm nay hiện giá, Khám phá gọi giá ngày 16/10 là "giá đêm nay". Lịch sử quét tô xanh "0 lượt không có dữ liệu". Heatmap xám mờ, tương phản khoảng 1,8:1. | Cùng một con số lúc có lúc không, nên mất niềm tin vào cả hệ thống. | Nghiêm trọng |
| 3 | **Đường từ gợi ý tới hành động bị đứt.** Bấm một việc trong "Việc cần làm" dẫn tới chi tiết đêm, nơi không có gợi ý và không có nút. Áp dụng xong thì thẻ biến mất, không có xác nhận hay hoàn tác. Kết quả nằm cuối Terminal+. | T1 và T9 không đi hết được trên một luồng. | Cao |
| 4 | **Điều hướng theo tính năng, không theo việc.** 9 tab, 5 tab con, 8 tab cài đặt. Đăng nhập vào Bảng điều khiển nhưng tab đầu là Hôm nay, và hai màn này trùng nhau. Terminal+ có 11 khối và hai bộ chọn ngày. | Không biết vào đâu để làm việc gì. Mỗi sáng phải mở 3–4 tab. | Cao |
| 5 | **Thẻ rỗng chiếm chỗ ngay cả khi dữ liệu tốt.** Ở chế độ vừa quét, chữ to nhất Bảng điều khiển là "Không đủ số". "Mức căng thị trường (hiện tại)" có 14 cột "Chưa có". Thời tiết hiện "Cần cấu hình OPENWEATHER_API_KEY". | Nửa màn hình là chỗ trống, nên app trông như hỏng. | Cao |
| 6 | **Số liệu mâu thuẫn giữa các màn.** Giá Rex đêm nay là 3.600.814 (Hôm nay), "—" (Bảng điều khiển), 4.243.817 (Khám phá) và 4,2tr (Terminal+). Cùng Bảng điều khiển ghi "0 hết phòng" ở một chỗ, "Chưa có dữ liệu" ở chỗ khác. Thẻ "TB" nhưng số là trung vị. Đêm nay ghi "Còn 8 ngày". | Phải tự đối chiếu, và không biết số nào đúng. | Cao |
| 7 | **Ngôn ngữ kỹ thuật lộ ra.** "Giá tham chiếu = trung vị 4 đối thủ 7.905.345 ₫ × định vị thường ngày của bạn 50", compset (~38 chuỗi), OTB/pickup/STLY/ADR/RevPAR, "cận dưới", "chuẩn CoStar STR", "#194", "OPENROUTER_API_KEY … đầu ra giả". | Người không rành kỹ thuật không hiểu, và không dám quyết. | Cao |
| 8 | **Nhập PMS xong khó thấy, và màn tự mâu thuẫn.** Màn báo "45/45 dòng thành công" và nói công suất sẽ hiện "trong dải khách sạn của bạn" trên Phòng trống. Heatmap không có hàng PMS (ev-07). Công suất PMS chỉ là một đường nét đứt ở biểu đồ cuối trang, cùng màu xanh lá với Park Hyatt, và ngay trên biểu đồ vẫn ghi "chưa hiệu chỉnh (chưa có PMS)" (ev-07b). | Tốn công nhập mà không thấy giá trị ở chỗ cần nhìn. | Trung bình |
| 9 | **Cài đặt là bảng điều khiển của operator.** 8 tab, 498 chuỗi, 3.822 từ. Lộ tham số như "Giới hạn request mỗi đêm". Thông báo có hai cơ chế người nhận. Email chưa cấu hình nên tenant không tự xử lý được. Không có hướng dẫn cho người mới. | Người mới không tự cấu hình được. T6 bị chặn. | Cao |
| 10 | **Mobile và khả năng đọc.** Trang tràn ngang (Radar 408px). 9 tab cuộn ngang mà không có dấu hiệu còn tab. Chi tiết khách sạn dài 23.587px trên điện thoại. 96% chữ ở Phòng trống chỉ 11–13px. `text-faint` (2,5:1) được dùng ở 92 chỗ. | Quản lý xem trên điện thoại buổi sáng thì đọc không nổi. | Cao |

**Nguyên nhân gốc** (mỗi vấn đề ở mục 4 gắn một mã):
- **RC1. Không có một lớp "độ tin cậy dữ liệu" chung.** `lib/freshness.ts` chỉ dùng cho banner. Mỗi màn tự quyết khi nào ẩn, làm xám hay vẫn hiện.
- **RC2. Cấu trúc theo nguồn dữ liệu và tính năng, không theo việc buổi sáng.** Mỗi đợt phát triển (wave1, wave2, RM standards, market ladder) thêm một khối hoặc một tab, không gộp lại.
- **RC3. Gợi ý giá thiếu điều kiện chặn và hiển thị công thức thay cho lý do.** Không chặn khi dữ liệu cũ. Logic "kéo về vị trí thường ngày" bị trình bày như tín hiệu thị trường.
- **RC4. Chuỗi hiển thị không lọc theo vai trò.** Từ chuyên môn, tên biến môi trường, mã lượt quét và chữ tiếng Anh thô của Booking đi thẳng ra giao diện tenant.
- **RC5. Khối luôn hiện bất kể có dữ liệu.** Không có cơ chế "chỉ hiện khi đủ điều kiện".
- **RC6. Thiết lập của operator lẫn vào tenant, và không có onboarding.**
- **RC7. Không có kiểm thử hồi quy giao diện.** Không kiểm tràn ngang, tương phản hay độ nhất quán số liệu giữa các màn.

---

## 2. Sitemap

### 2.1 Hiện tại (tenant_admin)

```
/login ──► /dashboard (login/page.tsx:13, manifest.ts:16, logo app-shell.tsx:244)
Thanh tab (app-shell.tsx:28-38), 9 tab:
├─ Hôm nay /today ............ Việc cần làm · Đêm nay · Gợi ý giá (3/7 đêm, có Áp dụng) · 7 đêm tới · Thay đổi 24h · Bản tin
├─ Bảng điều khiển /dashboard . Việc cần làm (trùng) · Toàn cảnh compset · 3 KPI · Mức căng thị trường (hiện tại) · Xu hướng compset
│                               cột phải: Cảnh báo · Khách sạn của bạn · Trạng thái dữ liệu
├─ Đối thủ /competitors ....... 3 tab con: Compset của bạn | Radar cạnh tranh | Khám phá thị trường
│   ├─ /hotels/[id] ........... KPI · dải 30 đêm · bảng từng đêm · 200 thay đổi (12.378px)
│   └─ /hotels/[id]/dates/[d] . Giá Booking · từng loại phòng · Cùng đêm · biểu đồ · lượt quét #id · thay đổi
├─ Phòng trống /availability .. heatmap 16 đêm (chỉ Trước/Sau) · Chỉ báo lấp đầy  (/overview → đây)
├─ Giá & định giá /rates ...... 4 KPI · Xu hướng|Vị trí|Heatmap · Tình báo cạnh tranh
├─ Terminal+ /terminal ........ Thị trường khu vực · Thời tiết · Doanh thu · Mức căng 14 đêm · Sự kiện 12 tháng ·
│                               Nhịp & gợi ý (bộ chọn ngày thứ 2) · OTB · Gợi ý giá (12 thẻ) · Kết quả · Từng đêm  (/pace → #pace)
├─ Bản tin /insights .......... 2 tab con: Bản tin AI | Thay đổi (/events, 15 chip lọc)
├─ Lịch sử quét /runs ......... 4 KPI · 91 lượt quét (mã #, đọc trang, bị chặn, lỗi)
└─ Cài đặt /settings .......... 8 tab: Khách sạn · Thị trường · Lịch quét · Sự kiện · Thông báo · Người dùng · Nhập PMS · Chiến lược giá
Thanh trên: tên tenant · ⓘ (độ mới + chú giải màu) · chuông (8 thay đổi) · tài khoản (ngôn ngữ, đăng xuất)
```

Số chỗ cùng một khái niệm xuất hiện:

| Khái niệm | Xuất hiện ở |
|---|---|
| Gợi ý giá | Hôm nay ×2, Bảng điều khiển, Terminal+ ×2: 5 chỗ |
| Mức căng / khan phòng | Bảng điều khiển ("hiện tại", compset), Terminal+ (khu vực, 14 đêm), Radar ("Khan phòng khu vực"): 3 nghĩa |
| Chỉ báo lấp đầy | Bảng điều khiển, Phòng trống (thẻ và hàng), Terminal+ (cột): 4 chỗ |
| Khách sạn của bạn đêm nay | Hôm nay, Bảng điều khiển, thẻ Đối thủ, thẻ Thị trường của Terminal+: 4 chỗ, 3 giá khác nhau |
| Độ mới dữ liệu | dải đầu trang, banner, thẻ Trạng thái dữ liệu, menu ⓘ, Lịch sử quét: 5 chỗ, 3 cách hiển thị |

### 2.2 Đề xuất: 5 tab theo công việc, giữ nhận diện OTARadar

```
/login ──► /sang-nay (PWA, logo, đăng nhập đều vào đây)
Thanh trên: [● Cập nhật 18:36 hôm nay | ● Dữ liệu dừng 8 ngày] (bấm → ngăn "Tình trạng dữ liệu") · chuông · ⚙ Cài đặt · tài khoản
├─ 1 Sáng nay ............ Dải tin cậy dữ liệu → Việc cần làm (≤5, Áp dụng/Bỏ qua/Hoàn tác ngay trên thẻ)
│                          → 14 đêm của bạn vs đối thủ (giá chênh %, đối thủ hết x/N, đêm căng) → Đối thủ đổi gì 24h (gom theo KS) → 3 ý bản tin
├─ 2 Lịch giá & phòng .... MỘT lưới KS × đêm, chuyển "Phòng còn | Giá | Chênh với bạn", chọn ngày + 14/30/60, lọc gói giá
│                          → bấm ô mở ngăn "Đêm này" (tất cả KS, giá, phòng, ai hết, gợi ý của đêm)
├─ 3 Đối thủ ............. thẻ từng đối thủ → trang đối thủ có "7 ngày qua: giá ↑3 đêm, hết phòng 2 đêm…"
│                          tab con: Khuyến mãi & hạn chế (Radar cũ) · Tìm khách sạn để theo dõi (Khám phá cũ)
├─ 4 Thị trường .......... Mức căng khu vực 14 đêm · khách sạn của bạn trên thị trường · lịch sự kiện & ngày lễ
└─ 5 Báo cáo ............. Bản tin AI · Nhật ký thay đổi · Kết quả gợi ý · Nhịp đặt phòng/OTB (khi có PMS) · Xuất Excel/PDF
⚙ Cài đặt (ngoài thanh tab): Khách sạn & đối thủ · Cảnh báo & người nhận · Người dùng · Dữ liệu PMS · Chiến lược giá · Nâng cao (lịch quét, khu vực thị trường, sự kiện địa phương)
Chuyển sang operator: tham số quét thị trường, mã lượt quét, cột kỹ thuật của Lịch sử quét.
```

Lưu ý: DESIGN.md (mục "App OTARadar", quyết định 02/10) chốt 8 tab theo giao diện mẫu của khách hàng. Gom 5 tab là đổi quyết định đó. Câu hỏi Q1 ở mục 7.

---

## 3. Kết quả tác vụ T1–T9 (đóng vai quản lý, chế độ thực tế 24/10)

Số click tính từ màn mở sau đăng nhập (`/dashboard`). Không tính gõ phím. Thời gian là ước lượng, gồm thời gian đọc và cuộn.

| Tác vụ | Xong? | Click | Ước lượng | Điểm khựng / phải đoán |
|---|---|---|---|---|
| **T1** Sáng nay làm gì, đêm nào tăng/giảm, bao nhiêu VND, vì sao | Một phần, kết quả không tin được | 0 click để thấy. 1 click thì vào ngõ cụt. Để hành động cần 2 click + cuộn ~1.700px (Hôm nay) hoặc ~2.500px (Terminal+) | 2–3 phút | Banner đỏ "dữ liệu cũ" nằm ngay trên 7 lệnh tăng giá (+7% đến +15%) (ev-01). Lý do là công thức "trung vị × định vị 50". Bấm mục thì tới chi tiết đêm, không có gợi ý hay nút (`today-actions.tsx:69`). Không có việc "giảm giá" hay "đối thủ hết phòng" nào. Danh sách chỉ là kéo giá về vị trí thường ngày. |
| **T2** Đêm 31/10 (thứ Bảy) và một dịp lễ: giá tôi vs đối thủ, ai hết, ai còn bao nhiêu | Có | 31/10: 2 (Phòng trống → ô). 24/12: 6 (Phòng trống không có bộ chọn ngày, phải bấm "Sau" ×4 → ô) | 40–60 giây | Câu trả lời nằm trong thẻ "Cùng đêm trên Booking.com" ở chi tiết đêm của *một* khách sạn. Bảng không có ô đọc khi rê chuột. Ô xám mờ khi dữ liệu cũ. Phải tự cộng: Rex "Còn ≥100", Reverie "50–59". |
| **T3** Một đối thủ đã đổi gì trong 7 ngày | Một phần | 4 (Bản tin → Thay đổi → chọn KS → 7 ngày) | 1–2 phút | Nhật ký thay đổi nằm trong tab "Bản tin". Chi tiết khách sạn có 200 dòng cấp loại phòng, không lọc theo thời gian, và một biến động 4→1 sinh hai dòng "Giảm phòng" + "Sắp hết phòng" (ev-08). Không có tóm tắt theo đối thủ. Khi rỗng thì báo "Thử nới khoảng thời gian" thay vì "chưa quét từ 16/10". |
| **T4** Thị trường khu vực 14 đêm tới căng hay lỏng | Một phần | 1 (Terminal+) + cuộn ~830px | 1 phút | Chỉ 6/14 đêm có số, lấy từ lượt quét danh sách 16/10, và thẻ không ghi là cũ. Thẻ ghi "≥5% hết phòng" nhưng cũng ghi "Booking: 25% đã kín". "Mức căng thị trường (hiện tại)" ở Bảng điều khiển là chỉ số khác, 14 cột "Chưa có". |
| **T5** Thêm/bớt đối thủ bằng URL, đổi giờ quét | Có | Thêm: 3 (Đối thủ → Thêm khách sạn → Thêm). Bớt: 2. Giờ quét: 4 (Cài đặt → Lịch quét → Thêm mốc → Lưu) | 1 phút | URL sai báo lỗi rõ kèm mẫu, nhưng chip "✓ Booking.com" xanh vẫn hiện trong ô. "Thêm khách sạn" ở Đối thủ nhảy sang Cài đặt nên mất ngữ cảnh. Chỉ có "Ngừng quét", không có "Xoá". Đổi giờ quét có báo "Đã lưu". |
| **T6** Bật email khi đối thủ hết phòng, thêm viewer | Một phần, bị chặn | Viewer: 4 + nhập. Cảnh báo: 5 (Cài đặt → Thông báo → Thêm đăng ký → Cảnh báo → Lưu) | 3 phút | Vai trò mặc định là "Quản trị", phải tự gửi mật khẩu cho người mới, ô mật khẩu không có nhãn cho trình đọc màn hình. Thông báo có hai nơi thêm người nhận ("Đăng ký nhận tin" và "Người nhận email"). Không chọn được riêng "đối thủ hết phòng" trong form đăng ký. **Email chưa cấu hình nên không gửi được.** Tenant chỉ được bảo "liên hệ đơn vị vận hành". |
| **T7** Nhập file PMS, xem occupancy cạnh compset | Một phần | 1 + chọn tệp | 1 phút | Tự nhận cột tiếng Việt và ngày dd/mm/yyyy, báo 45/45 dòng (tốt). Màn hứa công suất hiện "trong dải khách sạn của bạn" trên Phòng trống, nhưng heatmap không có hàng PMS (`settings.json:574` so với `heatmap-table.tsx`, ev-07). Công suất PMS chỉ là một đường ở biểu đồ cuối trang, trùng màu Park Hyatt, ngay dưới dòng "chưa hiệu chỉnh (chưa có PMS)" (ev-07b). Bảng điều khiển hiện "87% công suất (PMS)". OTB là một form thứ hai trên cùng tab, dùng template khác. |
| **T8** Dữ liệu có mới không, lần quét cuối, lỗi, tin số tới đâu | Một phần | 0 để thấy chữ đỏ. 1–2 để hiểu (Lịch sử quét hoặc menu ⓘ) | 1–2 phút | Thanh trên không báo độ mới. Radar, Bản tin, chi tiết đêm và Khám phá không báo cũ. Lịch sử quét tô xanh "0 lượt không có dữ liệu" và liệt kê 91 dòng kỹ thuật (ev-04). Mức tin cậy giải thích trong chú giải 15 mục. "≥100", "60–79", "≈" đúng nhưng mỗi màn giải thích một kiểu. |
| **T9** Áp dụng/bỏ qua một gợi ý, kiểm tra kết quả | Một phần | Áp dụng: 2 + cuộn ~1.600px. Kiểm tra: 3 (Terminal+ → cuộn → mở "Đã xử lý (1)") | 2 phút | Ô giá hiện "3700000", không có dấu phân cách. Áp dụng xong thẻ biến mất, không có thông báo hay "Hoàn tác" trên Hôm nay. Chữ "Đã áp dụng" dễ hiểu nhầm là hệ thống tự đổi giá trên Booking. Kết quả cần số PMS sau đêm lưu trú. |

Tóm lại: 2/9 xong trọn (T2, T5), 7/9 xong một phần hoặc bị chặn. Không tác vụ buổi sáng nào (T1, T2, T4, T8) xong trong 3 click và 30 giây kèm câu trả lời đáng tin.

---

## 4. Danh sách vấn đề

Mức: **NT** = Nghiêm trọng, **C** = Cao, **TB** = Trung bình, **T** = Thấp. Công sức: S (≤½ ngày), M (1–3 ngày), L (>3 ngày). Ảnh nằm trong `assets/ux-261024/`. "Thực tế" là chế độ 24/10, "fresh/" là chế độ vừa quét.

### RC1: Độ tin cậy dữ liệu

| ID | Màn | Vấn đề | Bằng chứng | Mức | CS | Đề xuất cụ thể |
|---|---|---|---|---|---|---|
| D1 | Hôm nay, Bảng điều khiển | Dữ liệu cũ 8 ngày vẫn ra 7 lệnh tăng giá (+7% đến +15%), nằm ngay dưới banner đỏ. `TodayActions` không đọc `data-status`. | [ev-01](assets/ux-261024/ev-01-today-stale-but-raise-15pct.jpg), `components/today-actions.tsx:37-140`, `GET /data-status` → `stale:true` | NT | S | Khi `stale`, thay toàn bộ khối bằng một thẻ: "Chưa đưa gợi ý: Booking.com chưa có số mới từ 18:36 16/10 (8 ngày). [Xem tình trạng quét]". Thẻ gợi ý (nếu vẫn hiện) bị làm mờ, ghi "dựa trên giá 16/10", và nút Áp dụng bị khoá. |
| D2 | Đối thủ, Giá, Bảng điều khiển, Hôm nay | Cùng một số, mỗi màn xử lý "cũ" một kiểu. Thẻ Đối thủ hiện "—" vì quan sát >48 giờ. Hôm nay vẫn hiện 3.600.814. Bảng điều khiển ghi "Giá của bạn —". Giá có trung vị 6.129.423 nhưng thấp nhất/cao nhất "—". | [ev-11](assets/ux-261024/ev-11-competitors-stale-dashes-vs-today-prices.jpg), `vi-desktop-rates.jpg`, `vi-desktop-dashboard.jpg` | NT | M | Một quy tắc chung (component `DataAge`): luôn hiện giá trị cuối kèm chip tuổi "16/10 · 8 ngày trước" màu cảnh báo. Không màn nào để trống một số mà màn khác đang hiện. Riêng trung vị thì loại quan sát >48 giờ và ghi rõ lý do. |
| D3 | Đối thủ › Khám phá thị trường | Cột "Giá đêm nay" thực ra là giá đêm 16/10 từ lượt quét danh sách 16/10. Caravelle 5.087.615, trong khi chi tiết đêm 24/10 ghi 5.277.942. Rex ở đây là 4.243.817, ở Hôm nay là 3.600.814. | [ev-12](assets/ux-261024/ev-12-market-explore-tonight-price-from-16-10.jpg) | C | S | Đổi tiêu đề cột theo đêm thật ("Giá đêm 16/10"). Khi đêm quét khác hôm nay thì thêm chip "cũ". Đầu trang ghi "Danh sách quét 19:07 16/10" màu cảnh báo. |
| D4 | Lịch sử quét | KPI "Lượt không có dữ liệu 0" tô xanh ("tốt"), "Lượt quét 24 giờ 0" và "Bị chặn 0" màu thường, trong khi 8 ngày không quét (`runs/page.tsx:83-84`). Bảng 91 dòng có mã, "Đọc trang", "Bị chặn", "Lỗi". | [ev-04](assets/ux-261024/ev-04-runs-green-zeros-while-stale.jpg) | C | S | Thay 4 KPI bằng một câu trạng thái ("Không có lượt quét nào từ 18:36 16/10. Đã báo đơn vị vận hành.") và một dải 7 ngày (mỗi ngày một ô xanh/đỏ). 0 lượt trong 24 giờ thì tô đỏ. Bảng kỹ thuật chỉ operator thấy. |
| D5 | Phòng trống, Chi tiết KS | Ô >48 giờ dùng `.sb-stale` (grayscale + opacity 0,45), làm cả heatmap thành xám. Tương phản đo được khoảng 1,8:1. | [ev-06](assets/ux-261024/ev-06-heatmap-stale-grey-unreadable.jpg), `app/globals.css:266-269` | C | S | Giữ màu nhiệt, thêm góc sọc chéo 6px trên ô và chip "Số từ 16/10" ở đầu cột. Chữ trong ô đạt ≥4,5:1. |
| D6 | Bản tin › Thay đổi | Lọc 7 ngày ra "0 thay đổi… Thử nới khoảng thời gian hoặc bỏ bớt lọc", trong khi nguyên nhân là không có lượt quét. | `events/page.tsx` (trạng thái rỗng), duyệt thử 24/10 | TB | S | Trạng thái rỗng đọc `data-status`: "Chưa có lượt quét nào sau 16/10 nên chưa có thay đổi mới". |
| D7 | Radar, Bản tin AI, Chi tiết đêm, Khám phá | Không có cảnh báo cũ (chi tiết đêm và Khám phá chỉ có giờ quét màu xám). Radar ghi "Từ dữ liệu đã quét, không tốn thêm lượt quét" (thông tin vô ích). Bản tin "mới nhất" ngày 16/10 không ghi tuổi. | `vi-desktop-competitors-radar.jpg`, [ev-09](assets/ux-261024/ev-09-insights-stale-and-fake-brief.jpg) | TB | S | Mọi màn có số Booking dùng chung `PageStrip` với "Dữ liệu mới nhất…". Bản tin ghi "Bản tin ngày 16/10 (8 ngày trước)". |
| D8 | Thanh trên | Độ mới dữ liệu chỉ nằm trong menu ⓘ. | `components/app-shell.tsx:96-141` | TB | S | Đặt pill trên thanh trên: "● Cập nhật 18:36" (xanh) hoặc "● Dữ liệu dừng 8 ngày" (đỏ). Bấm mở ngăn "Tình trạng dữ liệu" (lần đọc cuối, tỉ lệ thành công 7 ngày, lượt kế tiếp, cách đọc ≥N/N–M/≈). |
| D9 | Chi tiết KS | Đêm 24/10 ghi "Còn 8 ngày" vì dùng `days_to_arrival` tại lúc quan sát (16/10). | `vi-desktop-hotel-caravelle.jpg`, `app/(app)/hotels/[id]/page.tsx:273` | C | S | Tính khoảng cách từ ngày hôm nay của tenant, không dùng giá trị lưu trong metric. |

### RC3: Gợi ý giá

| ID | Màn | Vấn đề | Bằng chứng | Mức | CS | Đề xuất cụ thể |
|---|---|---|---|---|---|---|
| S1 | Cài đặt › Chiến lược giá, mọi thẻ gợi ý | Màn Chiến lược ghi "Đang dùng mặc định (định vị 100, đổi tối đa 15%/ngày)". Engine thật dùng "định vị thường ngày" của Rex = 50 (đo lại: trung vị 50,4, khoảng 32–84) khi chưa lưu chiến lược. Kết quả là 12/30 đêm đều "Có thể tăng giá", 7 đêm chạm trần +15%, không đêm nào "giảm". Lý do chỉ là "đêm này bạn rẻ hơn mức thường của chính bạn". Cùng thẻ 26/10 ghi "thị trường không căng −5%" mà vẫn +15%. | [ev-03](assets/ux-261024/ev-03-strategy-says-default-100.jpg), `messages/vi/rms.json:5`, `backend/app/market/pace_report.py:138-173, 389-395`, `vi-desktop-terminal.jpg` | NT | M | (1) Sửa câu ở màn Chiến lược: "Chưa có chiến lược: hệ thống giữ vị trí giá thường ngày của bạn (~50% trung vị đối thủ)". (2) Tách hai loại lý do: "giá đêm này lệch mức thường của bạn" khác "thị trường đang căng/lỏng", và chỉ gọi là "Việc cần làm" khi có tín hiệu thị trường hoặc lệch ≥10 điểm. (3) Ngưỡng và hướng xử lý cần chủ sản phẩm chốt (Q2). |
| S2 | Mọi thẻ gợi ý | Lý do là công thức: "Giá tham chiếu = trung vị 4 đối thủ 7.905.345 ₫ × định vị thường ngày của bạn 50 (chưa đặt chiến lược giá)", "Đã giới hạn ở mức đổi tối đa mỗi ngày". | ev-01, `backend/app/i18n/locales/vi.json:26-27` | C | S | Viết bằng lời: "Đối thủ bán đêm này khoảng 7,9 tr. Bạn thường bán bằng khoảng ½ giá họ, tức 3,95 tr. Hôm nay bạn 3,2 tr. Gợi ý lên 3,7 tr (mỗi ngày không đổi quá 15%)." Công thức đầy đủ để trong `<details>` "Cách tính". |
| S3 | Hôm nay, Bảng điều khiển → Chi tiết đêm | Bấm một mục "Việc cần làm" dẫn tới `/hotels/{own}/dates/{d}`, nơi không có gợi ý, giá mục tiêu hay nút. | `components/today-actions.tsx:69`, duyệt thử: `hasApply:false` trên `/hotels/4/dates/2026-10-26` | C | S | Mỗi mục có nút "Tôi đã đổi giá" / "Bỏ qua" ngay trên thẻ. Chi tiết đêm của khách sạn bạn hiện `SuggestionCard` trên cùng khi đêm đó có gợi ý. |
| S4 | Hôm nay, Terminal+ | Áp dụng xong thẻ biến mất, không có thông báo hay Hoàn tác. Hoàn tác chỉ có trong `<details>` "Đã xử lý" ở Terminal+. Ô giá hiện "3700000". Chữ "Đã áp dụng" dễ hiểu nhầm là app tự đổi giá. | duyệt thử T9, `components/market-suggestion.tsx:48-78` | TB | S | Đổi nhãn thành "Tôi đã đổi giá" và "Bỏ qua". Hiện toast "Đã ghi: 26/10 → 3.700.000 ₫ · Hoàn tác" trong 8 giây. Ô giá định dạng 3.700.000 khi gõ. Thẻ đã xử lý thu thành một dòng xám kèm "Hoàn tác" tại chỗ. |
| S5 | Hôm nay, Bảng điều khiển, Terminal+ | Gợi ý giá ở 5 nơi, số đếm khác nhau: "Còn 2 việc khác" (14 đêm), "3 đêm trong 7 đêm tới", "Gợi ý giá đang chờ 12 đêm" (30 đêm). | `today/page.tsx:142,171`, `dashboard/page.tsx:112`, `pace/pace-view.tsx` | TB | M | Một danh sách duy nhất ở Sáng nay. Các nơi khác chỉ hiện nhãn "Có gợi ý" trên ô đêm và link tới danh sách. |
| S6 | Thẻ gợi ý | Mọi thẻ đều "Tin cậy vừa" nên nhãn không giúp phân biệt. | `vi-desktop-terminal.jpg` | T | S | Chỉ hiện nhãn tin cậy khi thấp, kèm lý do ("chỉ 3 đối thủ có giá"). |

### RC2: Kiến trúc thông tin và điều hướng

| ID | Màn | Vấn đề | Bằng chứng | Mức | CS | Đề xuất cụ thể |
|---|---|---|---|---|---|---|
| N1 | Khung app | 9 tab + 5 tab con + 8 tab cài đặt + 3 chế độ xem Giá. Đăng nhập, PWA và logo đều vào `/dashboard`, nhưng tab đầu là Hôm nay (PRODUCT.md: "tab đầu là Hôm nay"). | `login/page.tsx:13`, `manifest.ts:16`, `app-shell.tsx:28-38,244` | C | M | 5 tab theo sitemap 2.2. Cài đặt chuyển sang biểu tượng ⚙ trên thanh trên. Một trang đích duy nhất là "Sáng nay". |
| N2 | Hôm nay vs Bảng điều khiển | Trùng "Việc cần làm", trùng "khách sạn của bạn đêm nay", nhưng giá đêm nay khác nhau (3.600.814 và "—"). | `today/page.tsx:142`, `dashboard/page.tsx:112`, ev-01 | C | M | Gộp thành "Sáng nay": dải tin cậy → việc cần làm → 14 đêm bạn vs đối thủ → thay đổi 24h → bản tin. Xu hướng compset chuyển sang Lịch giá & phòng. |
| N3 | Terminal+ | Trang 5.232px (mobile 9.191px), 11 khối, 38 request API khi mở. Có bộ chọn ngày thứ hai riêng (30 đêm) giữa trang. Trộn thị trường khu vực, thời tiết, PMS, sự kiện, nhịp, OTB, gợi ý, kết quả, bảng từng đêm. | `vi-desktop-terminal.jpg`, `_shots.json` (api_calls 38) | C | L | Tách ra: thị trường khu vực và sự kiện sang "Thị trường", gợi ý sang "Sáng nay", nhịp/OTB/kết quả sang "Báo cáo". Bỏ tên "Terminal+" (Q5). |
| N4 | Tên tab | "Terminal+", "Bản tin" (chứa Thay đổi), "Radar cạnh tranh", "Compset của bạn", "Khám phá thị trường", "Phòng trống" (của ai?), "Giá & định giá" đều không nói việc người dùng làm. | `messages/vi/shell.json`, `components.json` subTabs | TB | S | Đổi thành "Sáng nay", "Lịch giá & phòng", "Đối thủ", "Thị trường", "Báo cáo". Tab con: "Khuyến mãi & hạn chế", "Tìm khách sạn để theo dõi", "Nhật ký thay đổi". |
| N5 | Bảng điều khiển, Terminal+, Radar | Ba thẻ "mức căng/khan phòng" mang ba nghĩa: compset fill (hiện tại), khu vực 14 đêm, khan phòng khu vực so tuần trước. | `vi-desktop-dashboard.jpg`, `vi-desktop-terminal.jpg`, `vi-desktop-competitors-radar.jpg` | TB | S | Chỉ giữ "Mức căng khu vực" (Thị trường). Thẻ compset đổi thành "Đối thủ hết/sắp hết phòng". Khan phòng tuần trước gộp vào Thị trường. |
| N6 | Phòng trống, Giá | So một đêm phải xem hai màn. Phòng trống không có bộ chọn ngày (chỉ Trước/Sau 16 đêm). Mặc định 14 đêm ở Bảng điều khiển/Đối thủ, 30 đêm ở Giá/Radar/Terminal+. | `vi-desktop-availability.jpg`, `vi-desktop-rates.jpg` | TB | M | Một lưới "Lịch giá & phòng" với công tắc Phòng còn / Giá / Chênh với bạn, chọn ngày và 14/30/60. Mặc định 14 ở mọi nơi. |
| N7 | Chi tiết đêm, Thay đổi | Khách sạn của bạn nằm dưới breadcrumb "Đối thủ › Rex (của tôi)". Dropdown ghi "Rex (của tôi) (của bạn)". | `vi-desktop-night-rex-3110.jpg`, duyệt `/events` | T | S | Breadcrumb "Khách sạn của bạn › Đêm …". Bỏ hậu tố trùng. |
| N8 | Đối thủ | Nút "Thêm khách sạn" là link sang `/settings?tab=watchlist`, nên mất ngữ cảnh. | duyệt thử T5 | T | S | Mở ngăn kéo "Thêm đối thủ" ngay tại Đối thủ (dán URL hoặc chọn từ Khám phá). |

### RC5: Thẻ rỗng và trạng thái thiếu dữ liệu

| ID | Màn | Vấn đề | Bằng chứng | Mức | CS | Đề xuất cụ thể |
|---|---|---|---|---|---|---|
| E1 | Bảng điều khiển (cả khi vừa quét) | Chữ to nhất trang là "Không đủ số" (28px, xanh). "Mức căng thị trường (hiện tại)" có 14 cột "Chưa có". "Chỉ báo lấp đầy" hiện "—". Chú giải có "Lấp đầy ≈ %" nhưng không có đường. | [ev-02](assets/ux-261024/ev-02-dashboard-fresh-empty-cards.jpg) | C | S | Thẻ "Khách sạn của bạn" lấy vị trí giá làm số chính ("Rẻ hơn trung vị 45%", hạng 2/5). Công suất thành dòng phụ. Ẩn thẻ hoặc đường khi không có số, chỉ giữ một dòng "Mở thêm khi nhập PMS". |
| E2 | Terminal+ | Thời tiết "Cần cấu hình OPENWEATHER_API_KEY". "Doanh thu của bạn", "OTB", "Kết quả gợi ý" trống. Bảng Từng đêm có 30 dòng "Không đủ số", "—", "chưa đủ lịch sử". | [ev-10](assets/ux-261024/ev-10-terminal-env-var-empty-cards.jpg), `messages/vi/terminal.json:105` | C | S | Không hiện thẻ khi thiếu cấu hình (operator thấy ở trang sức khoẻ). Các khối cần PMS gom thành một thẻ "Nhập PMS để mở: doanh thu, OTB, kết quả gợi ý". Ẩn cột toàn "—". |
| E3 | Phòng trống | Thẻ "Chỉ báo lấp đầy" ghi "0 đêm", "—", "0/1 KS ≈≥90% đêm đầu". Biểu đồ có 1 đường (Meander) nhưng chú giải 6 mục. Hàng "Lấp đầy ≈ %" toàn "—". | `vi-desktop-availability.jpg`, `fresh/vi-desktop-availability.jpg` | TB | S | Khi <2 khách sạn có ước tính thì thu thẻ thành một dòng giải thích. Chú giải chỉ liệt kê đường có dữ liệu. |
| E4 | Radar | "Tỷ lệ đối thủ đang khuyến mãi theo đêm" có 30 cột cao bằng nhau nên không mang thông tin. Rex nằm trong "Khuyến mãi đối thủ". | `vi-desktop-competitors-radar.jpg` | TB | S | Bỏ biểu đồ khi các giá trị bằng nhau. Tách "KM của bạn" khỏi đối thủ. |

### RC4: Ngôn ngữ

| ID | Màn | Vấn đề | Bằng chứng | Mức | CS | Đề xuất cụ thể |
|---|---|---|---|---|---|---|
| L1 | Toàn app | Từ chuyên môn trong chuỗi vi: "compset" ~38 (không phân biệt hoa thường), "trung vị" 46, OTB 23, pickup/pace/STLY/ADR/RevPAR, "cận dưới" 8, "mức sàn" 17, "chuẩn CoStar STR" 3, "lead time". Catalog vi có 2.533 chuỗi, 17.209 từ. Settings 3.822 từ, Terminal 1.061 từ, một chuỗi dài 119 từ. | quét `messages/vi/*.json` | C | M | Bảng thay từ (cụ thể ở phase 2): compset → "nhóm đối thủ", trung vị → "giá giữa của đối thủ" (ⓘ giải thích), OTB → "phòng đã đặt", pickup → "đặt thêm", "≥N" → "còn ít nhất N", "cận dưới" → "ít nhất". Giới hạn mỗi ⓘ ≤40 từ. |
| L2 | Terminal+, Bản tin, Cài đặt › Thông báo, Chi tiết đêm, Lịch sử quét | Lộ chi tiết nội bộ: `OPENWEATHER_API_KEY`. Bản tin và "Đã gửi gần đây" ghi "OPENROUTER_API_KEY chưa cấu hình; đây là đầu ra giả". Mã lượt "#194". DESIGN.md: "Không cho tenant thấy … mã lượt quét". | ev-09, ev-10, `hotels/[id]/dates/[date]/page.tsx:559`, `vi-desktop-settings-notifications.jpg` | C | S | Ẩn bản tin lỗi hoặc giả khỏi tenant. Bỏ cột "Lượt" và mã #. Lỗi cấu hình chỉ operator thấy. |
| L3 | Chi tiết đêm, Đối thủ, Khám phá | Chữ tiếng Anh thô từ Booking: "Free cancellation + breakfast · Hoàn huỷ · Bữa sáng" (nói hai lần), "District 1", "Ho Chi Minh Municipality/City", "Preferred", "47% off". | `vi-desktop-night-caravelle-3110.jpg`, ev-12 | TB | S | Gói giá chỉ hiện thẻ tiếng Việt (tên gốc trong `title`). Map quận/thành phố sang tiếng Việt. Huy hiệu có nhãn tiếng Việt ("Đối tác ưu tiên"). |
| L4 | Bản EN | Lý do gợi ý trong câu tiếng Anh dùng số kiểu Việt "median of 4 competitors 7.905.345 ₫". Tên tenant "(dữ liệu thật)" hiện ra. | `backend/app/i18n/locales/en.json:26-27`, `en-desktop-dashboard.jpg` | TB | S | Backend trả số thô, frontend định dạng theo locale. Đổi tên tenant (dữ liệu, không phải code). |
| L5 | Toàn app | Hai cách viết tiền rút gọn: "6,1tr" (`messages/vi/format.json:16`) và "5,3 Tr" (`lib/format.ts:180`). Thẻ "Giá niêm yết **TB** đối thủ" nhưng số là trung vị (`messages/vi/dashboard.json:34`). | `vi-desktop-dashboard.jpg`, `vi-desktop-hotel-caravelle.jpg` | T | S | Dùng một dạng "6,1 tr". Đổi "TB" thành "giá giữa". |
| L6 | Bản tin AI, Hôm nay | Bản tin viết "Pickup nổi bật…", "median compset", "không phải ADR". Tóm tắt 4 dòng ở Hôm nay toàn là câu miễn trừ, không có việc nào để làm. | ev-09, `vi-desktop-today.jpg` | TB | M | Prompt bắt buộc: ≤3 ý, mỗi ý "đêm nào, làm gì, vì sao" bằng lời thường. Không dùng từ trong danh sách cấm (L1). Câu miễn trừ để trong ⓘ. |

### RC6: Cài đặt và onboarding

| ID | Màn | Vấn đề | Bằng chứng | Mức | CS | Đề xuất cụ thể |
|---|---|---|---|---|---|---|
| C1 | Toàn app | Không có onboarding. Người mới gặp ngay 9 tab, chưa có chiến lược, chưa có người nhận cảnh báo, chưa có PMS, và không được nhắc. | duyệt toàn bộ | C | M | Thẻ "Thiết lập 5 bước" trên Sáng nay, ẩn khi xong: ① khách sạn của bạn ② ≥4 đối thủ ③ vị trí giá mong muốn ④ ai nhận cảnh báo ⑤ nhập PMS (tuỳ chọn). Mỗi bước 1 click tới đúng form. |
| C2 | Cài đặt › Thông báo | Hai cơ chế người nhận: "Đăng ký nhận tin" (kênh × loại × giờ im lặng) và "Người nhận email". 10 quy tắc bật sẵn. Email chưa cấu hình nên tenant không làm được gì. Form đăng ký không chọn được loại cảnh báo cụ thể. | `vi-desktop-settings-notifications.jpg`, `messages/vi/settings.json:380,432` | C | M | Gộp thành một bảng "Ai nhận gì": mỗi người một hàng, cột Cảnh báo tức thì / Bản tin sáng / Báo cáo tuần, mỗi ô một công tắc. Quy tắc là 3 mức sẵn (Ít / Vừa / Nhiều) với "Tuỳ chỉnh" để mở. Khi kênh chưa cấu hình thì ẩn kênh đó với tenant. |
| C3 | Cài đặt › Thị trường | Lộ tham số vận hành: "Số KS quét chi tiết", "Số đêm quét chi tiết", "Giới hạn request mỗi đêm", "Quét danh sách ngay". | `vi-desktop-settings-market.jpg`, `messages/vi/settings.json:169` | TB | S | Tenant chỉ chọn khu vực, bán kính và phân khúc. Phần còn lại chuyển cho operator. |
| C4 | Cài đặt › Nhập PMS, Phòng trống | Hai form (Công suất và OTB) cùng tab, khác template. Nhập xong được hứa hiện "trong dải khách sạn của bạn" nhưng heatmap không đọc PMS. Công suất PMS chỉ có ở biểu đồ cuối trang (`occupancy-analysis.tsx:51,73`), trùng màu Park Hyatt, và dòng "chưa hiệu chỉnh (chưa có PMS)" vẫn hiện. | [ev-07](assets/ux-261024/ev-07-pms-imported-but-not-on-availability.jpg), [ev-07b](assets/ux-261024/ev-07b-pms-line-only-in-chart-note-still-says-no-pms.jpg), `messages/vi/settings.json:574,588,621`, `availability/heatmap-table.tsx` | TB | M | Một luồng nhập, tự nhận loại tệp. Thêm hàng "Công suất của bạn (PMS)" dưới hàng khách sạn của bạn trên lưới. Thông báo kết quả có link "Xem trên Lịch". |
| C5 | Cài đặt › Người dùng | Vai trò mặc định "Quản trị" (`users-tab.tsx:35`). Ô mật khẩu không có accessible name. Phải tự gửi mật khẩu. | `vi-desktop-settings-users.jpg`, read_page (`textbox [ref_43]` không có nhãn) | TB | S | Mặc định "Chỉ xem". Thêm `aria-label`. Nút "Tạo mật khẩu ngẫu nhiên + Sao chép". |
| C6 | Cài đặt › Khách sạn | Ô "Nguồn" số phòng là URL (Wikipedia/Trip.com). "Rà soát compset (chuẩn CoStar STR)". Chỉ có "Ngừng quét". URL sai vẫn hiện chip "✓ Booking.com" xanh. | `vi-desktop-settings-watchlist.jpg`, duyệt T5 | T | S | Gom số phòng và nguồn vào "Chi tiết". Đổi tiêu đề thành "Nhóm đối thủ có cân không?". Chip chỉ xanh khi URL hợp lệ. |
| C7 | Cài đặt › Chiến lược giá | 13 ô số mà không thấy tác động. | [ev-03](assets/ux-261024/ev-03-strategy-says-default-100.jpg) | TB | M | Chọn định vị bằng 3 thẻ ("Rẻ hơn đối thủ ~10%", "Ngang", "Cao hơn ~10%", hoặc "Giữ như hiện nay"). Thêm xem trước "Với lựa chọn này, 7 đêm tới: …". Ô số nằm trong "Nâng cao". |

### RC7: Mobile, khả năng đọc, chức năng

| ID | Màn | Vấn đề | Bằng chứng | Mức | CS | Đề xuất cụ thể |
|---|---|---|---|---|---|---|
| M1 | Radar, Bảng điều khiển, Terminal+, Phòng trống, Khám phá, Cài đặt › Thị trường, Giá, Lịch sử quét | Trang tràn ngang ở 375px: 408 (EN 446), 84, 57 (EN 71), 33 (EN 35), 19 (EN 37), 27, 11, 11 và 2 px (Cài đặt › Sự kiện). DESIGN.md: "Không để trang cuộn ngang". | [ev-05](assets/ux-261024/ev-05-mobile-today-dashboard-availability-radar.jpg), `_shots.json` (`overflow_px`) | C | S | Sửa từng khối (`min-w-0`, xuống dòng chip, bảng cuộn trong khung). Thêm kiểm tra tự động: `scrollWidth - innerWidth == 0` cho 24 route. |
| M2 | Khung app (mobile) | 9 tab cuộn ngang, "Phòng trống" bị cắt, không có dấu hiệu còn tab. Cài đặt nằm ngoài màn hình. | ev-05 | TB | M | Thanh đáy 5 mục trên mobile (theo sitemap 2.2). |
| M3 | Chi tiết KS, Thay đổi, Terminal+, Hôm nay (mobile) | Trang dài 23.587px, 11.379px, 9.191px và 3.861px. "Việc cần làm" 5 mục chiếm 2 màn hình. | `_shots.json` (height) | TB | M | Thẻ việc gọn (đêm · giá mục tiêu · một câu lý do · nút). Nhật ký gom theo đêm, "Xem thêm" sau 20 dòng. |
| M4 | Toàn app | 96% chữ ở Phòng trống chỉ 11–13px (159/166 lá chữ: 34 lá 11px, 38 lá 12px, 87 lá 13px). `--sb-faint` #9ca3af trên nền trắng 2,5:1, dùng 92 chỗ. Ô cũ khoảng 1,8:1. | đo bằng JS trên `/availability`, `app/globals.css:27-28` | TB | S | Chữ thân tối thiểu 13px, số liệu chính 14px. Đổi `--sb-faint` sang ≥4,5:1 cho chữ (giữ màu cũ cho đường kẻ). |
| M5 | Phòng trống | Chú giải 15 mục, chiếm nửa màn hình mobile. | `vi-mobile-availability.jpg` | T | S | Chỉ 5 mục chính, phần còn lại trong "Cách đọc ô". |
| F1 | Chi tiết KS | 200 thay đổi cấp loại phòng, ±1 phòng chiếm đa số. Một biến động 4→1 sinh hai dòng ("Giảm phòng" và "Sắp hết phòng"). Không có tóm tắt 7 ngày. | [ev-08](assets/ux-261024/ev-08-hotel-detail-room-type-noise.jpg) | C | M | Đầu trang thêm thẻ "7 ngày qua": giá ↑/↓ bao nhiêu đêm (±%), hết phòng đêm nào, KM bật/tắt. Nhật ký gom theo đêm, ẩn ±1 phòng mặc định, không sinh hai dòng cho cùng một biến động. |
| F2 | Chi tiết đêm | Chỉ có 1 lượt quét mà trục x lặp "18:27 16/10" ×5. Biểu đồ chỉ là chấm rời. | `vi-desktop-night-caravelle-3110.jpg` | T | S | Dưới 2 lượt quét thì thay biểu đồ bằng một câu. |
| F3 | Terminal+ › Thị trường | "≥5% HẾT PHÒNG" và "Booking: 25% đã kín" đứng cạnh nhau. "Thang ≥1/5/10/20/30 phòng" là thuật ngữ. | `vi-desktop-terminal.jpg` | TB | S | Một câu chính: "Khu vực còn 563/593 KS có phòng. 217 KS còn ≥30 phòng: thị trường lỏng như thường lệ". Thang để trong "Chi tiết". |
| F4 | Bản tin AI | Danh sách bản tin trước còn bản lỗi và bản giả. | ev-09 | TB | S | Lọc `status != completed` hoặc output giả khỏi tenant. |

Không thấy lỗi console hay request API lỗi (4xx/5xx) ở 120 lượt chụp. Thời gian tải trên dev server là 0,7–2,0 giây mỗi màn. Terminal+ gọi 38 request API khi mở, nhiều nhất trong các màn (Bản tin chỉ 9).

---

## 5. Điểm làm tốt (giữ lại)

- Báo lỗi URL Booking rõ, kèm mẫu đúng. Thêm đối thủ chỉ 3 click.
- Nhập PMS tự nhận tên cột tiếng Việt và ngày dd/mm/yyyy, báo kết quả theo dòng.
- Bộ chọn "Mọi giá | Hoàn huỷ | Có bữa sáng | Chỉ phòng" ở Giá và quy ước dấu (+)/(−) ở Đối thủ đúng chuẩn rate shopping (SiteMinder, Access RMS cũng làm vậy).
- Thẻ "Cùng đêm trên Booking.com" ở chi tiết đêm trả lời gần trọn T2.
- Không hiện số bịa: "≥N", "N–M", "≈", "mẫu nhỏ" nhất quán với PRODUCT.md. Vấn đề chỉ là cách nói, không phải số sai.
- Catalog vi/en khớp nhau (`npm run i18n:check`: 0 lỗi, 2.533 khoá).

---

## 6. Benchmark: luồng buổi sáng, rate shopping, cảnh báo

Help center của Lighthouse, Duetto và RateGain cần đăng nhập. Phần về ba hãng này dựa trên trang sản phẩm, Hotel Tech Report, báo chí và blog của hãng. Chi tiết màn hình lấy từ help center công khai của các công cụ nhẹ hơn (RoomPriceGenie, Mews/Atomize, SiteMinder, Access RMS, Cloudbeds, RevControl).

| Mẫu | Ai làm | Áp vào OTARadar |
|---|---|---|
| Banner "N ngày cần xử lý" kèm danh sách 10 ngày giá trị nhất, chấp nhận từng ngày, nhiều ngày hoặc cả khoảng | Atomize [S16][S18] | Sáng nay: "3 đêm cần xem" + danh sách ≤5 (S5, N2) |
| Ba trạng thái màu cho giá gợi ý: tăng (xanh) / giảm (đỏ) / trong ±4% thì đậm đen nghĩa là không cần làm | RoomPriceGenie [S13] | Ô đêm trên Lịch: nhãn "Có gợi ý" chỉ khi lệch đủ lớn (S1) |
| Mỗi ngày một câu lý do bằng lời, nói rõ khi bị chặn bởi sàn/trần của chính khách sạn | RoomPriceGenie [S14], Duetto (độ tin cậy + kịch bản) [S7] | S2 |
| Email buổi sáng là "trang chủ thật", tối đa 5 ngày nên tăng giá | RoomPriceGenie GenieIntelligence [S15], Lighthouse Smart Summaries [S6] | Phase 3: bản tin sáng = 5 việc của Sáng nay |
| Ô lịch ghi % chênh giữa giá thấp nhất của bạn và đối thủ, đỏ/xanh theo ngưỡng chỉnh được. Nhãn SOLD / MLOS / Unavailable, không để trống | SiteMinder [S19], Cloudbeds [S22] | Lịch giá & phòng chế độ "Chênh với bạn" (N6) |
| Đường giá của bạn vs trung vị/min/max, huy hiệu hạng (1 = rẻ nhất), cờ "cùng điều kiện" và giờ cập nhật | Access RMS [S20] | Đã có phần lớn. Thêm giờ cập nhật trên mọi màn (D7, D8) |
| Lịch / Biểu đồ / Bảng, compset chính và phụ, "rate evolution" 7/30/90 ngày một click | Lighthouse Rate Insight [S2][S4] | Trang đối thủ: "7 ngày qua" (F1) |
| Cảnh báo một form: "đối thủ rẻ/đắt hơn trung bình X% hoặc X VND", luật lên và xuống riêng, giờ gửi, từng người tự bật | Access RMS [S21], Duetto Notification Center [S8] | C2 |
| Gợi ý có "More info" giải thích, ghi đè giá bị khoá kèm biểu tượng và ghi chú | Atomize [S16][S17] | S3, S4 |

Không tìm thấy tài liệu công khai nào về cảnh báo "đối thủ hết phòng" ở các sản phẩm trên. Đây là điểm khác biệt OTARadar nên giữ và làm rõ.

Nguồn: [S2] mylighthouse.com/resources/blog/how-to-get-most-out-of-lighthouse-rate-insight · [S4] hospitalitynet.org/news/4126743.html · [S6] hoteltechnologynews.com/2024/02/lighthouse-unlocks-the-power-of-generative-ai-with-launch-of-smart-summaries-for-hotels · [S7] duettocloud.com/en-us/buyer-faq · [S8] hoteltechreport.com/news/duetto-tools-optimize-hotel-revenue · [S13] help.roompricegenie.com/knowledge/calendar-color-scheme · [S14] roompricegenie.com/hotel-price-explanations-dynamic-pricing · [S15] hotelspeak.com/2021/02/roompricegenie-launches-genieintelligence-revenue-management-by-email · [S16] help.mews.com/s/article/How-to-accept-price-recommendations-in-Mews-RMS · [S17] help.mews.com/s/article/Making-Overrides · [S18] help.mews.com/s/article/Navigating-in-Atomize · [S19] help-platform.siteminder.com/en/articles/8692392-competitor-rates-report · [S20] help-rms.theaccessgroup.com/en/articles/11880938-view-and-compare-competitor-pricing · [S21] help-rms.theaccessgroup.com/en/articles/12066203-create-and-manage-automated-alerts · [S22] myfrontdesk.cloudbeds.com/hc/articles/115002822894-PIE-Rate-Shopper (chỉ đọc được đoạn trích từ kết quả tìm kiếm). Chưa kiểm chứng được: số tab cấp 1 của từng sản phẩm, cách Lighthouse vẽ ô hết phòng, cách RateGain Navigator bố trí lưới.

---

## 7. Câu hỏi cần anh/chị quyết

1. **Số tab.** DESIGN.md chốt 8 tab theo giao diện mẫu của khách hàng (02/10). Có đồng ý gom thành 5 tab theo công việc (sitemap 2.2), giữ màu sắc và nhận diện OTARadar không? Hay giữ 8 tab và chỉ gộp Hôm nay với Bảng điều khiển?
2. **Gợi ý giá khi chưa có chiến lược.** Có ba hướng. (a) Không gợi ý cho tới khi chọn vị trí giá. (b) Giữ "vị trí thường ngày" nhưng chỉ đưa vào "Việc cần làm" khi có tín hiệu thị trường hoặc lệch ≥10 điểm. (c) Giữ như hiện nay, chỉ sửa câu chữ. Tôi đề xuất (b).
3. **Ngưỡng "dữ liệu cũ" để khoá gợi ý.** Đề xuất: quá một chu kỳ quét (10 giờ) thì làm mờ gợi ý, quá 24 giờ thì ẩn. Có đồng ý không?
4. **Compset của Rex.** Cả 4 đối thủ đắt gấp khoảng 2 lần Rex (Rex 32–84% trung vị, thường quanh 50%). Có muốn app cảnh báo khi nhóm đối thủ lệch giá hơn 40% (gợi ý thêm đối thủ cùng tầm giá từ Khám phá) không?
5. **Tên "Terminal+".** Đây là tên trong giao diện mẫu. Có được đổi (đề xuất tách thành "Thị trường" và "Báo cáo") không?
6. **Email và Zalo.** Operator có cấu hình SMTP trước khi giao cho tenant không? Nếu chưa, có ẩn hẳn kênh email/Zalo với tenant (chỉ còn webhook) không?
7. **Lịch sử quét.** Có được chuyển bảng kỹ thuật sang operator, tenant chỉ còn ngăn "Tình trạng dữ liệu" không?
8. **Thẻ Thời tiết.** Có cấp `OPENWEATHER_API_KEY`, hay bỏ thẻ khỏi giao diện tenant?
9. **Bản sao DB `scrapebooking_ux`.** DB này đang chứa thao tác thử của audit: thêm Hotel Majestic Saigon, thêm mốc quét 12:00, viewer `uxaudit-viewer@rexhotel.vn`, 45 dòng PMS giả, một quyết định "đã áp dụng" cho 26/10. Xoá sau khi anh/chị duyệt báo cáo, hay giữ lại để làm môi trường thử cho phase 1?

---

## 8. Kết quả sau cải tiến (24/10, đã triển khai, chưa commit)

Người dùng giao toàn bộ ba phase. Quyết định Q1–Q9 ghi ở `plans/261024-0007-tenant-admin-ux-overhaul/plan.md`.

**Đo lại tác vụ**
- Môi trường: Playwright trên DB bản sao, chế độ "vừa quét" (đồng hồ 16/10 21:30). Số đo nằm trong `assets/ux-261024/final/_tasks-after.json`. T5–T7 do agent Phase 3 đo trên cùng bản sao.
- Bản sao có 45 dòng PMS thử nhập từ T7, nên các gợi ý "giảm giá" trên ảnh dựa vào công suất PMS thử, không phải số thật của Rex.

| Tác vụ | Trước | Sau |
|---|---|---|
| T1 việc sáng nay → ghi quyết định một đêm | Ngõ cụt khi bấm; cần 2 click + cuộn 1.700px; gợi ý +15% cả khi dữ liệu cũ | **2 click**, việc đầu nằm trong màn hình đầu (desktop; mobile ở y=408/812). Dữ liệu cũ thì không đưa gợi ý. |
| T2 một đêm: giá vs đối thủ, ai hết | 2 click (dịp lễ 6) | **2 click**; thẻ "Cùng đêm" ở y=306px. Dịp lễ: 3 thao tác (chọn ngày → ô) |
| T3 đối thủ đổi gì 7 ngày | 4 click, 200 dòng nhiễu | **1 click**: dòng "7 ngày qua" trên mỗi thẻ đối thủ, đếm theo đêm |
| T4 thị trường 14 đêm | 1 click + cuộn 830px | **1 click**, dải mức căng ở y=220px, có tuổi dữ liệu |
| T5 thêm đối thủ / đổi giờ quét | 3 / 4 | 2–3 (hộp thoại ngay tại Đối thủ) / 4 (⚙ → Nâng cao) |
| T6 cảnh báo + viewer | Bị chặn; 2 nơi thêm người nhận | 3 click thêm người nhận (một bảng "Ai nhận gì"); 4 click thêm viewer (mặc định Chỉ xem). Kênh chưa cấu hình ẩn với tenant. |
| T7 nhập PMS, xem cạnh compset | Không thấy ở Phòng trống | 3 click + thả tệp, tự nhận loại tệp. Hàng "Công suất của bạn (PMS)" nằm trên Lịch giá & phòng. |
| T8 dữ liệu mới không | Chữ đỏ ở một số màn; Lịch sử quét tô xanh "0" sai | **1 click** từ mọi màn (pill trên thanh trên → Tình trạng dữ liệu) |
| T9 kiểm tra kết quả gợi ý | 3 click + cuộn dài | **2 click** (Báo cáo → Kết quả gợi ý); hoàn tác ngay trên thẻ |

**Số đo chung** (100 ảnh: 25 route × vi/en × 1440/375, `assets/ux-261024/final/_shots-final.json`)

| Chỉ số | Trước | Sau |
|---|---|---|
| Tràn ngang trên 375px | 8 route, tới 408px (en 446px) | 0 route |
| Lỗi console / request lỗi | 0 / 0 | 0 / 0 |
| Chiều cao trên mobile | Chi tiết KS 23.587px · Nhật ký 11.379px · Terminal+ 9.191px · Hôm nay 3.861px | 4.576 · 1.082 · Thị trường 1.635 + Nhịp 2.257 · 2.522 |
| Tab cấp 1 | 9 | 5 (+ ⚙). Gợi ý giá từ 5 nơi còn 2. |
| Ô dữ liệu cũ | Xám, mờ 45%, tương phản ~1,8:1 | Giữ màu, sọc góc; `--sb-faint` 4,8:1 |

**Kiểm thử:** backend 636 test đạt (2 test live bỏ qua). Dashboard typecheck, lint và `i18n:check` (2.636 khoá vi/en) không lỗi.

**Thay đổi logic đáng chú ý**
- **Tăng giá khi chưa đặt chiến lược phải có tín hiệu cầu.** Với dữ liệu Rex, 7 đêm "+15%" thành "giữ giá".
- **"Giữ như hiện nay" lưu thành chế độ `follow_typical`** (migration 0020), để vẫn áp quy tắc trên.
- **Lý do viết bằng lời.** Gợi ý giảm giá nói rõ "giá cao hơn mức thường N điểm" và "công suất mới X%".
- **Mặc định cảnh báo đổi sang mức "Vừa".** Sắp hết phòng, đối thủ tăng giá và khuyến mãi tắt mặc định với tenant chưa lưu quy tắc.
- **Bỏ bảng `notification_recipients`** (migration 0019). Người nhận cũ thành đăng ký nhận đủ 4 loại tin.

**Làm nốt sau đó (24/10, migration 0021)**
- Mời người dùng qua email, link dùng một lần, luôn có link sao chép khi email chưa bật. Mời một viewer mất 4 click.
- Cột "Lần đăng nhập cuối" và cột "Người nhập" trong lịch sử PMS.
- Trang của chính khách sạn bạn làm sáng đúng tab "Lịch giá & phòng".
- Link cũ `#pace` chuyển tới Báo cáo › Nhịp đặt phòng.
- Link trong email trỏ về route mới.

**Còn lại**
- **Còn "≥N" trong ô:** ô và chip phòng còn vẫn viết "≥100". Cách đọc nằm trong bảng Tình trạng dữ liệu và chú giải.
- **Bản tin cũ còn từ chuyên môn:** bản tin tạo trước 24/10 vẫn có "pickup/compset/trung vị". Prompt v4 chỉ áp cho bản tin mới.
- **Bỏ khỏi Lịch giá & phòng:** các thẻ KPI cũ và "Tình báo cạnh tranh" của tab Giá. Hàng cuối ở chế độ "Chênh với bạn" thay phần so sánh theo đêm.
- **Production:** cần đặt `APP_BASE_URL` (đường dẫn dashboard) để link mời và link trong email đúng.
