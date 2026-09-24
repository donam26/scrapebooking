# Flow người dùng: rà soát chi tiết từng chức năng

Ngày: 2026-09-24. Mỗi flow được đi qua theo ba lớp: màn hình dashboard → endpoint API → xử lý
backend, rồi chạy e2e có thao tác ghi thật bằng Playwright (script trong lịch sử phiên làm việc,
không commit). Kết quả cuối: 16/16 bước e2e các flow A–E đạt, e2e riêng cho "Quét ngay"/"Quét tất cả
ngay" đạt, 211 test backend đạt (1 bỏ qua vì không có MinIO, 2 test live không chạy trong CI).

Ký hiệu: **[sửa]** là lỗi hoặc thiếu sót phát hiện khi rà soát và đã sửa trong đợt này.

## A. Operator onboard khách hàng mới

| Bước | Màn hình | API | Ghi chú |
|---|---|---|---|
| 1 | `/login` | `POST /auth/login` | Cookie httpOnly `sb_session` 12 giờ. Sai mật khẩu: "Email hoặc mật khẩu không đúng". |
| 2 | `/admin/tenants` → "+ Tạo tenant" | `POST /tenants` | Múi giờ, giờ quét, horizon, giờ bản tin, ngôn ngữ, nước. **[sửa]** Múi giờ không hợp lệ bị từ chối 422 (trước đây được nhận và làm scheduler lỗi ở mọi tick cho mọi tenant). Giờ quét được sort và bỏ trùng, mã nước về chữ thường. |
| 3 | `/admin/users` → tạo `tenant_admin` chọn tenant | `POST /users` | Email trùng → 409. Mật khẩu tối thiểu 8 ký tự. |
| 4 | Chọn tenant ở thanh trên hoặc "Xem dashboard" | mọi request theo tenant tự kèm `?tenant_id=` | Chưa chọn tenant → màn hình nhắc chọn. Overview tenant mới: heatmap trống có hướng dẫn thêm khách sạn. |
| 5 | `/admin/health` | `GET /health/summary,runs,sessions` | Tự làm mới 30 giây. **[mới]** nút "Quét tất cả ngay" (`POST /health/scan-now`). |

Ràng buộc bổ sung **[sửa]**: không thể tự khoá hoặc tự đổi vai trò tài khoản đang đăng nhập; không
thể khoá/hạ vai trò operator đang hoạt động cuối cùng.

## B. Tenant admin cấu hình

| Bước | Màn hình | API | Ghi chú |
|---|---|---|---|
| 1 | Cài đặt → Watchlist → thêm URL Booking | `POST /watchlist` | Chấp nhận URL có tham số, hậu tố ngôn ngữ (`.vi.html`); URL không phải trang khách sạn → 422 hiện đúng thông báo. Khách sạn đã tồn tại (tenant khác theo dõi) thì dùng chung, chỉ tạo liên kết. |
| 2 | Sửa nhãn / vai trò; Ngừng quét / Quét lại | `PATCH`, `DELETE /watchlist/{id}` | "Ngừng" = `active=false`, giữ lịch sử; sự kiện cũ vẫn xem được ở `/events`. |
| 3 | **[mới]** "Quét ngay" | `POST /watchlist/scan-now` | Tạo đợt quét thủ công cho watchlist của tenant, đẩy job cho worker; gọi lại trong 10 phút trả về đợt đang chạy. Watchlist rỗng → 422. |
| 4 | Lịch quét | `PATCH /settings` | Giờ quét (1–8 mốc), horizon 1–90, giờ bản tin, ngôn ngữ, múi giờ (**[sửa]** kiểm tra hợp lệ). Tenant không tự tắt được (`active` bị bỏ qua). Thay đổi có hiệu lực từ mốc giờ kế tiếp. |
| 5 | Người dùng | `GET/POST/PATCH /users` | Tạo `tenant_admin`/`viewer`, khoá/mở, đặt lại mật khẩu. **[sửa]** Tài khoản bị khoá mất quyền ngay ở request kế tiếp (không đợi token hết hạn); đổi vai trò cũng áp dụng ngay. |
| 6 | Viewer | | Mọi nút ghi bị ẩn ở giao diện và bị 403 ở API; `/admin/*` chuyển về `/overview`. |

## C. Xem hằng ngày

| Bước | Màn hình | API | Ghi chú |
|---|---|---|---|
| 1 | `/overview` heatmap | `GET /overview?start&end` | Khách sạn của bạn trên cùng; màu theo trạng thái và số phòng `exact`; dải compset (đối thủ hết phòng, giá trung vị/thấp nhất, chỉ số giá, công suất PMS). Khoảng ngày 14/30/60 trong URL nên chia sẻ được. **[sửa]** Ngày mặc định theo múi giờ tenant, và múi giờ hỏng trong dữ liệu cũ không làm sập màn hình. |
| 2 | Bấm ô → `/hotels/{id}/dates/{date}` | `GET /hotels/{id}/dates/{date}?history_days` | Loại phòng ở lần quét gần nhất (phòng còn + độ tin cậy, giá, rate plan), biểu đồ phòng còn và giá theo lần quét, dòng thời gian quan sát, sự kiện của ngày. |
| 3 | Tên khách sạn → `/hotels/{id}` | `GET /hotels/{id}` | Bảng chỉ số theo ngày (pickup, tốc độ, giá đổi 7 ngày, hết phòng lúc, có lại lúc) và dòng thời gian sự kiện. |
| 4 | `/events` | `GET /events` | Lọc khách sạn, loại (nhiều), ngày lưu trú, thời điểm quan sát; phân trang 100; `?highlight=<id>` từ bằng chứng bản tin. |

## D. Bản tin AI

| Bước | Màn hình | API / job | Ghi chú |
|---|---|---|---|
| 1 | `/insights` → "Tạo bản tin ngay" | `POST /insights/generate` → job `generate_insight` | API ghi dòng `pending`, dashboard poll 5 giây. **[sửa]** Dòng `pending` quá 10 phút (jobs worker không chạy) chuyển `failed` với lý do rõ ràng thay vì treo mãi. |
| 2 | Chi tiết `/insights/{id}` | `GET /insights/{id}` | Tóm tắt, điểm nổi bật (mức tin cậy, đề xuất, bằng chứng bấm được tới sự kiện/ngày/compset), tín hiệu cầu, cơ hội giá, rủi ro, ghi chú chất lượng dữ liệu, mục bị loại kèm lý do. |
| 3 | Hằng ngày | cron `dispatch_daily_insights` 5 phút | **[sửa]** Có catch-up: tenant đã qua `insight_hour` mà chưa có bản tin hôm nay thì vẫn được đẩy (trước đây chỉ nhìn cửa sổ 10 phút, jobs worker tắt đúng giờ là mất bản tin). Tối đa 2 lần thất bại mỗi ngày để không tốn token vô hạn. |
| 4 | Không có dữ liệu | | **[sửa]** Tenant chưa có đợt quét/analytics nào trong kỳ → bản tin `failed` ngay với lý do "no scan data", không gọi model. Watchlist rỗng cũng vậy. |

## E. Nhập PMS

| Bước | Màn hình | API | Ghi chú |
|---|---|---|---|
| 1 | Cài đặt → Nhập PMS → "Tải template CSV" | `GET /pms/template` | 7 cột chuẩn; chỉ `stay_date` bắt buộc. |
| 2 | Chọn tệp → xem trước | `POST /pms/preview` | Nhận CSV (tự dò `,` `;` `\t`, nhiều encoding) và `.xlsx`. Gợi ý ánh xạ theo tên cột tiếng Việt/Anh thường gặp. **[sửa]** Ánh xạ đã lưu chỉ áp dụng cho cột có trong tệp, cột thiếu lấy theo gợi ý (trước đây tệp có tên cột khác bị "missing mapping"). **[sửa]** `.xls` cũ báo rõ "lưu lại thành .xlsx". |
| 3 | Sửa ánh xạ → "Lưu ánh xạ và nhập dữ liệu" | `PUT /pms/mapping`, `POST /pms/import` | Chỉ khách sạn vai trò "Khách sạn của bạn". Kết quả: số dòng OK/tổng, bảng lỗi từng dòng (ngày sai, trùng ngày, bán > tổng, công suất ngoài 0–100). Upsert theo ngày nên nhập lại không nhân đôi. |
| 4 | Lịch sử nhập, bảng occupancy | `GET /pms/imports`, `GET /pms/daily` | Occupancy PMS xuất hiện ở dải compset và trong đầu vào bản tin. |

## F. Vận hành scraper (backend)

| Tình huống | Xử lý | Ghi chú |
|---|---|---|
| Tới mốc giờ quét | scheduler tạo run theo `trigger_key` phút UTC, một job mỗi khách sạn duy nhất, horizon lớn nhất giữa các tenant | Idempotent: chạy lại tick không tạo trùng. |
| Thêm/ngừng khách sạn, đổi horizon giữa chừng | Ảnh hưởng từ đợt kế tiếp; đợt đang chạy giữ kế hoạch cũ | Muốn có dữ liệu ngay: "Quét ngay". |
| Job probe lỗi nặng (calendar/DB) | **[sửa]** arq `Retry` sau 60 giây, lần cuối tự chốt run `partial` | Trước đây ngoại lệ không được retry và run treo tới hạn chót 90 phút. |
| Run quá 90 phút | scheduler đánh dấu job còn lại `failed:deadline`, run `partial` | **[sửa]** đẩy analytics ngay cho run vừa chốt (không đợi cron catch-up 30 phút). |
| Job kẹt `queued` >5 phút (Redis mất) | scheduler đẩy lại; arq bỏ qua job trùng id | An toàn khi hàng đợi chỉ đang dài. |
| Worker restart giữa job | arq đẩy lại job dở; probe đã ghi được bỏ qua nhờ `terminal_dates` | |
| Múi giờ tenant sai trong DB cũ | **[sửa]** scheduler và dispatch bản tin bỏ qua tenant đó và log lỗi, không chết cả tick | API đã chặn nhập mới. |
| Booking đổi giao diện | `reparse --since-days 30` **[sửa]** tính lại analytics cho các run bị ảnh hưởng (`--no-reanalyze` để tắt) | Selector đổi thì tăng `PARSER_VERSION`. |
| Quét thủ công trùng đợt theo lịch | Hai run cùng chạy, cùng khách sạn có thể bị probe từ hai job | Chấp nhận cho thao tác tay; tránh bấm "Quét ngay" sát mốc giờ. |

## Điều còn để ngỏ

- Đổi mật khẩu chưa vô hiệu hoá phiên đang đăng nhập ở thiết bị khác (token còn hạn tối đa 12 giờ).
- `/events?highlight=<id>` chỉ đánh dấu khi sự kiện nằm trong trang hiện tại (chưa có endpoint lấy một sự kiện).
- Quét thủ công không chặn trùng với đợt theo lịch đang chạy.
- Chưa có thông báo (Telegram/email) cho tenant khi có bản tin mới; mới có cảnh báo vận hành cho operator.
