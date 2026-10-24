# Pha 3: Onboarding, Cài đặt, Cảnh báo (5–7 ngày)

**Cần trước:** Phase 2 (vị trí ⚙ Cài đặt, Sáng nay), Q4 (cảnh báo nhóm đối thủ lệch giá), Q6 (SMTP/Zalo), Q8 (thời tiết).

## Mục tiêu
Một quản lý mới, được operator cấp tài khoản, tự làm được trong ≤10 phút, không cần hỏi:
- khai báo khách sạn mình và ≥4 đối thủ;
- chọn vị trí giá;
- chọn ai nhận cảnh báo gì;
- (tuỳ chọn) nhập PMS.

Cảnh báo đến đúng người, đúng loại, và chỉ cấu hình ở một nơi.

## Việc cụ thể

### 1. Thiết lập 5 bước (C1)
Thẻ cột phụ ở Sáng nay, tự ẩn khi xong (lưu trạng thái ở backend, không dùng localStorage). Mỗi bước 1 click mở đúng form, xong thì có dấu ✓:
1. Khách sạn của bạn (URL Booking).
2. ≥4 đối thủ: dán URL, hoặc chọn từ "Khách sạn cùng tầm giá quanh bạn" (lấy từ Khám phá thị trường sẵn có: cùng hạng sao ±1, giá ±30%, ≤2 km).
3. Vị trí giá (mục 4).
4. Ai nhận cảnh báo (mục 2).
5. Nhập PMS (tuỳ chọn, ghi rõ "để thấy công suất thật cạnh đối thủ").

Bước 2 có kiểm tra Q4: nếu giá giữa nhóm đối thủ ≥1,6 lần giá bạn (Rex: ~2 lần), hiện ghi chú "Nhóm đối thủ đắt hơn bạn nhiều. Gợi ý: thêm 2–3 khách sạn cùng tầm giá" kèm danh sách gợi ý.

### 2. Cảnh báo: "Ai nhận gì" (C2)
- Bỏ khối "Người nhận email" riêng. Chỉ còn một bảng: mỗi người (email hoặc Zalo) một hàng, ba cột công tắc "Cảnh báo tức thì · Bản tin sáng · Báo cáo tuần". Có thêm cột "Giờ im lặng" (mặc định 22:00–06:00) và nút "Gửi thử".
- Quy tắc cảnh báo (tenant): ba mức sẵn.
  - **Ít:** đối thủ hết phòng đêm ≤7 ngày tới; bạn hết phòng; dữ liệu cũ.
  - **Vừa (mặc định):** thêm đối thủ giảm giá ≥10% đêm ≤14 ngày; đêm căng.
  - **Nhiều:** mọi loại.

  "Tuỳ chỉnh" mở 10 hàng quy tắc như hiện nay.
- Theo Access RMS: thêm quy tắc "Đối thủ rẻ hơn / đắt hơn giá giữa nhóm X% hoặc X VND". Luật lên và xuống riêng.
- Kênh chưa cấu hình (Q6) thì ẩn hẳn với tenant. Nếu không còn kênh nào, hiện một câu "Đơn vị vận hành chưa bật gửi tin. Bạn vẫn xem được mọi cảnh báo trong chuông 🔔". Không dùng thuật ngữ SMTP.
- **Email sáng = Sáng nay** (RoomPriceGenie, Lighthouse): bản tin sáng gửi đúng ≤5 việc của Sáng nay + dải 14 đêm dạng bảng nhỏ, mỗi việc có link mở app tại ngăn "Đêm này".

### 3. Cài đặt gọn (C3, C6)
Thứ tự tab trong ⚙: Khách sạn & đối thủ · Cảnh báo · Người dùng · Dữ liệu PMS · Chiến lược giá · Nâng cao.
- **Nâng cao:** Lịch quét, Khu vực thị trường, Sự kiện địa phương.
- **Khu vực thị trường** cho tenant chỉ còn: tìm khu vực hoặc quanh khách sạn, bán kính, phân khúc. Các tham số "Số KS quét chi tiết", "Số đêm quét chi tiết", "Giới hạn request mỗi đêm" và "Quét danh sách ngay" chuyển sang `/admin` (API kiểm vai trò).
- **Khách sạn & đối thủ:**
  - mỗi hàng gồm tên, vai trò (Của bạn / Đối thủ chính / phụ), trạng thái (Đang quét / Đang kiểm tra / Lỗi URL / Tạm dừng);
  - menu ⋯ gồm Đổi URL · Tạm dừng · Xoá khỏi nhóm (giữ lịch sử);
  - số phòng và nguồn nằm trong "Chi tiết";
  - đổi tiêu đề "Rà soát compset (chuẩn CoStar STR)" thành "Nhóm đối thủ có cân không?".

### 4. Chiến lược giá có xem trước (C7, S1)
- Bước 1 chọn vị trí bằng 4 thẻ: "Giữ như hiện nay (≈{index}% giá giữa)" · "Rẻ hơn đối thủ ~10%" · "Ngang đối thủ" · "Cao hơn ~10%".
- Bước 2 (tuỳ chọn): sàn, trần, đổi tối đa mỗi ngày.
- Mục "Nâng cao": điều chỉnh theo thứ, dịp lễ, sát ngày.
- Khung **Xem trước** bên phải: 7 đêm tới với giá bạn, giá gợi ý theo lựa chọn hiện tại và chênh. Gọi `/market/pace` với chiến lược nháp, chưa lưu (thêm tham số `strategy_preview`).

### 5. Dữ liệu PMS một luồng (C4)
- Một ô kéo thả. Hệ thống tự nhận loại tệp (báo cáo công suất theo ngày / OTB theo ngày / danh sách đặt phòng) theo cột. Cho người dùng đổi loại nếu nhận sai.
- Ánh xạ cột chỉ hiện khi không tự nhận đủ. Bước xem trước giữ nguyên (đang tốt).
- Kết quả: "45/45 dòng. Công suất 10/10–23/11 đã có trên Lịch giá & phòng [Xem]". Link mở Lịch với hàng PMS (Phase 2).
- Lịch sử nhập: tên tệp, loại, số dòng, người nhập, thời điểm.

### 6. Người dùng (C5 phần còn lại)
- "Mời bằng email" khi có kênh email: gửi link đặt mật khẩu, không cần admin tự đặt.
- Chưa có email thì giữ cách hiện nay, cộng nút "Tạo mật khẩu" của Phase 1.
- Bảng có cột "Lần đăng nhập cuối" để quản lý biết ai thực sự dùng.

## File bị ảnh hưởng
- `dashboard/src/app/(app)/settings/*`: `page.tsx`, `watchlist-tab.tsx`, `notifications-tab.tsx`, `notification-subscriptions.tsx`, `market-tab.tsx`, `pms-tab.tsx`, `otb-import.tsx`, `strategy-tab.tsx`, `users-tab.tsx`, `schedule-tab.tsx`, `events-tab.tsx`
- Thẻ thiết lập mới: `dashboard/src/components/setup-checklist.tsx`, dùng trong trang Sáng nay
- `dashboard/src/app/(app)/admin/*`: nhận tham số quét thị trường
- `dashboard/src/messages/{vi,en}/settings.json`, `rms.json`, `otb.json`
- Backend:
  - `api/routers/notifications.py` (một mô hình người nhận; migrate `notification_recipients` sang `notification_subscriptions`; mức sẵn);
  - `api/routers/market.py` (strategy preview, typical_index);
  - `api/routers/market_city.py` (chặn tham số vận hành cho tenant);
  - `api/routers/pms.py`, `api/routers/otb.py` (tự nhận loại tệp);
  - `api/routers/tenants.py` hoặc bảng mới cho trạng thái onboarding;
  - `app/notify/` (email sáng theo việc Sáng nay, quy tắc chênh giá).
- Migration: trạng thái thiết lập (`tenants.setup_state` JSONB), quy tắc chênh giá nếu cần cột mới, gộp recipients.
- Tài liệu: `docs/user-flows.md` (B, E, H), `PRODUCT.md`, `DESIGN.md` (Cài đặt, email).

## Tiêu chí nghiệm thu (đo được)
- **Onboarding:** trên tenant mới tạo trong bản sao DB, một người chưa dùng app (hoặc kịch bản Playwright mô phỏng) xong 4 bước bắt buộc trong ≤10 phút và ≤25 click. Thẻ thiết lập tự ẩn.
- **T6:** bật cảnh báo đối thủ hết phòng cho một người ≤4 click (⚙ → Cảnh báo → thêm người → công tắc "Cảnh báo tức thì"). Thêm viewer ≤4 click, vai trò mặc định "Chỉ xem". Chỉ còn một nơi thêm người nhận.
- **T7:** nhập PMS ≤3 click (⚙ → Dữ liệu PMS → thả tệp → Nhập) cho tệp có tên cột tiếng Việt. Link kết quả mở Lịch có hàng PMS.
- **Chiến lược:** đổi vị trí giá thì khung xem trước cập nhật ≤1 giây. Sau khi lưu, gợi ý ở Sáng nay khớp xem trước.
- Tenant không thấy tham số vận hành thị trường nào (API trả 403 khi tenant PATCH các trường đó).
- Email sáng (gửi thử trên môi trường có SMTP thử) có ≤5 việc và mỗi việc có link mở đúng ngăn Đêm này.
- `docs/user-flows.md` cập nhật B, E, H. Test integration cho notifications, pms, market strategy xanh.

## Rủi ro
- **Gộp hai bảng người nhận cần migration dữ liệu.** Có thể có tenant đang dùng cả hai. Viết migration giữ mọi người nhận và test downgrade.
- **Tự nhận loại tệp PMS có thể nhận sai.** Luôn hiện loại đã nhận kèm nút đổi. Không nhập trước khi xem trước.
- **"Xem trước chiến lược" gọi tính gợi ý nhiều lần.** Debounce 400ms, giới hạn 7 đêm.
- **Gợi ý "khách sạn cùng tầm giá" phụ thuộc dữ liệu Khám phá thị trường** (lượt quét danh sách 03:00). Khi chưa có khu vực thị trường thì chỉ hiện ô dán URL.
- **Email/Zalo phụ thuộc operator (Q6).** Nếu chưa có kênh nào, T6 chỉ đạt phần cấu hình. Phải ghi rõ trong nghiệm thu.

## Trạng thái triển khai (24/10, fe-settings)
- [x] 1. Thiết lập 5 bước: `components/setup-checklist.tsx` (`SetupChecklist`, `BalanceNote`), `GET/PUT /settings/setup`, `tenants.setup_state` (migration 0019). Cảnh báo nhóm đối thủ đắt ≥1,6× ở thẻ và ở Khách sạn & đối thủ (`compset-review.balance`). Chờ gắn vào Hôm nay.
- [x] 2. Cảnh báo "Ai nhận gì": một bảng (đăng ký), người nhận cũ gộp vào (0019, có downgrade), mức Ít/Vừa/Nhiều (Vừa = mặc định backend), luật mới rẻ/đắt hơn giá giữa nhóm (% hoặc VND), "Gửi thử" từng hàng, ẩn kênh chưa bật với khách sạn, lọc bản tin giả.
- [x] 3. Cài đặt gọn: 6 tab, "Nâng cao" (alias `?tab=schedule|market|events`), tham số vận hành thị trường chỉ operator, hàng khách sạn gọn + menu ⋯, chip URL chỉ xanh khi là trang khách sạn, Người dùng mặc định "Chỉ xem" + "Tạo mật khẩu".
- [x] 4. Chiến lược giá: 4 thẻ + giới hạn + Nâng cao + "Xem trước 7 đêm tới" (debounce 400ms).
- [x] 5. Dữ liệu PMS một luồng: tự nhận loại tệp (server, `PreviewOut.kind/detected_kind/missing`), kết quả có link Lịch giá & phòng.
- [x] 6. Email sáng: ≤5 việc cần làm (link `/hotels/{own}/dates/{d}`), bỏ bản tin giả.
- [ ] Còn: "Mời bằng email", cột "Lần đăng nhập cuối", người nhập trong lịch sử PMS, `docs/user-flows.md` B/E/H.
