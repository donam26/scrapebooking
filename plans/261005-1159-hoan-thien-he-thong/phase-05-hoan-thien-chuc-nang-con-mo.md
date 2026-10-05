# Phase 5: Hoàn thiện chức năng còn mở

Ước lượng: 2–4 tuần, chọn theo quyết định nghiệp vụ. Phụ thuộc: phase 1–4. Trạng thái: todo.
Nguồn: `docs/user-flows.md` "Điều còn để ngỏ", `PRODUCT.md` "chưa có", plans ghi "còn lại", research đợt 3.

## 5.1 Đóng các mục docs đã thừa nhận còn mở (bắt buộc, ~3 ngày)
| Mục | Việc | Nơi |
|---|---|---|
| Đổi mật khẩu không huỷ phiên | xong ở phase 2.1 (token_version) | — |
| `/events?highlight=` chỉ trong trang | `GET /events/{id}` (phase 3.3) + trang nhảy tới đúng trang/đêm | `routers/data.py`, `events/page.tsx` |
| Quét tay trùng run lịch | xong ở phase 3.2 | — |
| Cảnh báo vận hành chỉ log | Alertmanager (phase 2.5) + `OPS_ALERT_EMAILS` đã có | — |
| Bảng điều khiển chưa có thẻ thị trường khu vực | thêm `city-market-card` vào `/dashboard` khi tenant có area | `dashboard/page.tsx` |
| Email còn thương hiệu ScrapeBooking, icon PWA cũ | đổi template/`SMTP_FROM`, vẽ lại `public/icons/*`, `apple-icon.png` | `notify/render.py`, `public/` |
| DB dev chưa 0010/0011, image chưa rebuild | thuộc quy trình deploy phase 2; thêm bước "migrate + rebuild" vào runbook | `docs/operations.md` |
| Lễ hết hạn 2027 | mở rộng `holidays/data.py` tới 2029 (VN âm lịch: Tết, Giỗ Tổ, kiểm tra nguồn chính phủ), test "có dữ liệu ≥ 18 tháng tới" | `holidays/data.py` |
| Thông báo cho tenant khi có bản tin mới | đã có email `insight:{id}`; thêm chuông trong app đọc `/insights?since=` | `app-shell.tsx` |

## 5.2 Cảnh báo tốt hơn (S, ~1 tuần)
- Giờ im lặng theo tenant (`notification_rules.params.quiet_hours`) + gom digest: ngoài giờ cho phép thì giữ lại, gửi
  một email lúc mở cửa sổ.
- Chỉ gửi cảnh báo cho tenant **khởi tạo** run thủ công; run theo lịch gửi mọi tenant (sửa `_run_tenants`).
- Retry từng người nhận (lưu `recipients_done`), `List-Unsubscribe` + link huỷ theo người nhận có token.
- Telegram bot (miễn phí, 1–2 ngày): `notify/telegram_sender.py` cùng interface email; tenant dán chat id. Zalo OA/ZNS
  để sau khi có OA được duyệt.

## 5.3 PMS (phụ thuộc đối tác, M–L)
- Giữ CSV. Thêm "nhập theo lịch" từ URL/SFTP do PMS xuất tự động (nhiều PMS VN hỗ trợ xuất định kỳ) qua `PmsAdapter`
  mới `scheduled_file` — chỉ khi ≥1 khách yêu cầu.
- ezCloud/Newway API: viết adapter khi được cấp key; interface `PmsAdapter` đã có.

## 5.4 Onboarding và thương mại (L, quyết định của người dùng)
- Mời người dùng qua email (operator/tenant_admin tạo user không cần đặt mật khẩu; link đặt mật khẩu lần đầu dùng flow
  reset ở phase 2.1).
- Gói dịch vụ: `tenants.limits` (phase 2.1) thành bảng `plans`; màn operator đặt gói; chưa thanh toán tự động.
- Self-serve đăng ký + thanh toán (SePay/Polar): **chỉ** khi đã có ≥5 khách trả tiền thủ công; nằm ngoài plan này.

## 5.5 Thu thập (theo nhu cầu khách)
- Traveloka: cần proxy uy tín cao hoặc đối tác dữ liệu; chỉ spike lại khi khách đòi và chấp nhận chi phí.
- Đa occupancy/LOS (1 người, 2 đêm): nhân số probe; làm khi có khách có loại phòng 1 người hoặc chính sách LOS.
- Map loại phòng chéo kênh: cần dữ liệu label vài tuần; bắt đầu bằng gợi ý theo tên + occupancy, người dùng xác nhận.
- Chế độ list (1 request nhiều KS) cho Booking: giảm probe khi bị chặn; đã có parser trang kết quả từ thị trường.

## 5.6 Tài liệu
- Cập nhật `docs/operations.md` (migration tới mới nhất, retention, backup offsite, restore drill, alert), `docs/user-flows.md`
  (đóng mục còn mở, thêm flow quên mật khẩu, quota), `PRODUCT.md` (giới hạn gói), `README` (seed demo chạy lại được).
- Viết `docs/architecture.md` ngắn (sơ đồ pipeline + bảng, thay cho spec 24/09 đã lệch: spec nói Responses API/Batch/
  OpenAI, thực tế OpenRouter chat; spec nói Telegram alert, thực tế email).

## Tiêu chí nghiệm thu
- Mục "Điều còn để ngỏ" trong `docs/user-flows.md` rỗng hoặc mỗi dòng có lý do hoãn + ngày.
- Tenant đặt giờ im lặng 22:00–07:00 → không email trong khung đó, nhận digest 07:00 (test).
- Lễ VN có tới hết 2029; test fail khi còn < 18 tháng dữ liệu.
