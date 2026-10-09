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
| 1 | `/overview` heatmap | `GET /overview?start&end` | **[sửa 01/10]** Đêm sau `horizon_end` (hôm nay + số đêm quét tới) hiện sọc xám "Ngoài phạm vi quét", khác ô "Chưa quét". Sidebar và đầu trang báo vàng "lỡ lịch quét" khi lượt quét gần nhất cũ hơn một chu kỳ lịch. Khách sạn của bạn trên cùng; màu theo trạng thái và số phòng `exact`; dải compset (đối thủ hết phòng, giá trung vị/thấp nhất, chỉ số giá, công suất PMS). Khoảng ngày 14/30/60 trong URL nên chia sẻ được. **[sửa]** Ngày mặc định theo múi giờ tenant, và múi giờ hỏng trong dữ liệu cũ không làm sập màn hình. |
| 2 | Bấm ô → `/hotels/{id}/dates/{date}` | `GET /hotels/{id}/dates/{date}?history_days` | Loại phòng ở lần quét gần nhất (phòng còn + độ tin cậy, giá, rate plan), biểu đồ phòng còn và giá theo lần quét, dòng thời gian quan sát, sự kiện của ngày. **[sửa 01/10]** "Lần quét gần nhất" không còn bị lọc theo `history_days` (lâu không quét vẫn thấy dữ liệu cuối). Đêm chưa từng được quét thì nói rõ lý do thay vì "không có dữ liệu": ngoài phạm vi quét (`horizon_end`, kèm ngày bắt đầu được quét), đêm đã qua, hoặc chưa có lượt nào phủ tới (`last_scan_at`/`last_scan_through`, kèm nút "Quét ngay" cho quản trị). |
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
| Scheduler/máy tắt lúc tới mốc | **[sửa 01/10]** Tick đầu sau khởi động (hoặc sau quãng tick lỗi dài hơn cửa sổ 10 phút) quét bù một lần: khách sạn chưa được quét kể từ mốc gần nhất của tenant gom vào run `catchup:<phút UTC>`, phạm vi tính từ hôm nay | Trước đây mốc lỡ bị bỏ, dữ liệu đứng yên tới mốc kế tiếp (sự cố 26/09–01/10: 5 ngày không quét, đêm 26/10 chưa từng vào lượt quét nào). Khách sạn đã có job không thất bại (xong hoặc đang chờ) trong run bắt đầu từ mốc đó (theo lịch, "Quét ngay") thì không quét lại; job thất bại (proxy lỗi, run chết quá hạn chót) thì được quét bù. Run quá hạn được chốt trước khi xét quét bù và job dở của nó không bị đẩy lại hàng đợi. Có cảnh báo `ops_alert`. |
| Thêm/ngừng khách sạn, đổi horizon giữa chừng | Ảnh hưởng từ đợt kế tiếp; đợt đang chạy giữ kế hoạch cũ | Muốn có dữ liệu ngay: "Quét ngay". |
| Job probe lỗi nặng (calendar/DB) | **[sửa]** arq `Retry` sau 60 giây, lần cuối tự chốt run `partial` | Trước đây ngoại lệ không được retry và run treo tới hạn chót 90 phút. |
| Run quá 90 phút | scheduler đánh dấu job còn lại `failed:deadline`, run `partial` | **[sửa]** đẩy analytics ngay cho run vừa chốt (không đợi cron catch-up 30 phút). |
| Job kẹt `queued` >5 phút (Redis mất) | scheduler đẩy lại; arq bỏ qua job trùng id | An toàn khi hàng đợi chỉ đang dài. |
| Worker restart giữa job | arq đẩy lại job dở; probe đã ghi được bỏ qua nhờ `terminal_dates` | |
| Múi giờ tenant sai trong DB cũ | **[sửa]** scheduler và dispatch bản tin bỏ qua tenant đó và log lỗi, không chết cả tick | API đã chặn nhập mới. |
| Booking đổi giao diện | `reparse --since-days 30` **[sửa]** tính lại analytics cho các run bị ảnh hưởng (`--no-reanalyze` để tắt) | Selector đổi thì tăng `PARSER_VERSION`. |
| Quét thủ công trùng đợt theo lịch | Hai run cùng chạy, cùng khách sạn có thể bị probe từ hai job | Chấp nhận cho thao tác tay; tránh bấm "Quét ngay" sát mốc giờ. |

## G. Tín hiệu quyết định trên Tổng quan (đợt 01/10, sau nghiên cứu đối thủ)

| Bước | Màn hình | API | Ghi chú |
|---|---|---|---|
| 1 | `/overview` thẻ Thị trường | `GET /overview` (`compset[].own_rank`, `priced_hotels`, `holidays[]`) | Hàng "Giá bạn so trung vị đối thủ (%)" cùng cột với dải; đêm lệch khỏi mức thường của bạn từ 10 điểm in nâu. Chấm mực dưới ngày lễ. Bảng đọc thêm hạng giá và tên lễ. |
| 2 | Nhóm chọn "Mọi giá / Giá hoàn huỷ" (`?basis=refundable`) | `GET /overview?price_basis=refundable` | So cùng điều kiện huỷ miễn phí: dải giá, trung vị, chỉ số, hạng đều tính lại. Cột `min_refundable_price` có từ lượt quét đầu tiên sau migration 0005 (mỗi lượt cập nhật mọi đêm trong horizon); chưa có thì ghi chú hướng dẫn. |
| 3 | `/hotels/{id}/dates/{d}` | `GET …/dates/{d}` (`compset`, `holiday`) | Ghi chú "Thị trường đêm này: …" (đối thủ hết phòng, giá so trung vị, hạng, ngày lễ). |
| 4 | "Tải CSV" ở Tổng quan và Sự kiện | `GET /export/overview.csv`, `GET /export/events.csv` | Cùng bộ lọc màn hình; UTF-8 có BOM, cột tiếng Việt; sự kiện theo giờ địa phương, tối đa 2.000 dòng. |

## H. Thông báo email

| Bước | Màn hình | API / job | Ghi chú |
|---|---|---|---|
| 1 | Cài đặt › Thông báo | `GET /notifications/settings` | Ghi chú cảnh báo khi máy chủ email chưa cấu hình (operator thấy tên biến cần đặt). |
| 2 | Thêm/xoá người nhận | `POST`, `DELETE /notifications/recipients` | Email trùng (không phân biệt hoa thường) → 409; tối đa 20; viewer 403. |
| 3 | Bật/tắt và sửa ngưỡng từng loại | `PUT /notifications/rules/{kind}` | Tham số ngoài miền → 422 (số đêm 1–90, mức giảm 3–90%, số đối thủ 1–50). Chưa lưu = mặc định bật. |
| 4 | "Gửi thử" | `POST /notifications/test` | Tối đa 1 lần/phút (429). Kết quả hiện ngay dưới tiêu đề thẻ. |
| 5 | Sau mỗi lượt quét / bản tin / thứ Hai 08:00 | cron `dispatch_notifications` (5 phút) | Một email gom mỗi lượt quét; không gửi trùng khi chạy lại; lỗi SMTP thử lại tối đa 3 lần. |
| 6 | "Đã gửi gần đây" | `GET /notifications/log` | Ẩn dòng "không có gì để báo"; lý do không gửi bằng lời; lỗi SMTP chỉ operator thấy. |

## I. Nhịp đặt phòng, gợi ý giá, Hôm nay (đợt 2)

| Bước | Màn hình | API / job | Ghi chú |
|---|---|---|---|
| 1 | Sau mỗi lượt quét | cron `estimate_occupancy_catch_up` (jobs, 10 phút) | Ghi `occupancy_estimates` cho mỗi (khách sạn, đêm): khoảng phòng còn, công suất [thấp, cao], độ phủ. Lượt cũ được tính bù dần (20 lượt/lần). |
| 2 | `/pace` "Nhịp đặt phòng" | `GET /market/pace?start&end` (≤ 60 đêm) | Dữ liệu Booking.com. Công suất chỉ hiện khi độ phủ ≥ 50%; nhịp so cùng kỳ cần ≥ 2 đêm cùng thứ 1–8 tuần trước; đối chiếu PMS cho khách sạn của bạn. |
| 3 | Thẻ gợi ý giá | `PUT/DELETE /market/suggestions/{đêm}/{raise\|hold\|lower}` | Luật cố định, lý do bằng số liệu; không tự đổi giá. "Đã áp dụng"/"Bỏ qua" tính lại gợi ý tại chỗ (409 nếu không còn), viewer 403, "Hoàn tác" xoá ghi nhận. |
| 4 | `/today` "Hôm nay" (PWA mở vào đây) | `/overview`, `/market/pace`, `/events`, `/insights` | Đêm nay của bạn + câu thị trường, gợi ý 7 đêm, 7 đêm tới, thay đổi 24 giờ, bản tin mới nhất. Cài lên màn hình điện thoại qua `manifest.webmanifest`. |

## G. Listing Booking.com (từ 09/10/2026 chỉ còn Booking.com)

Đa kênh (Agoda, iVIVU, Trip.com, Mytour; plan `plans/261001-1441-multi-channel-ota-standards/`) đã
bỏ ngày 09/10/2026 cùng các tính năng chéo kênh (so kênh, đóng bán trên một kênh, parity, tín hiệu cầu
của kênh, gợi ý cùng khách sạn trên kênh khác). Migration 0015 xoá dữ liệu các kênh đó.

| Bước | Màn hình | API / job | Ghi chú |
|---|---|---|---|
| 1 | Cài đặt › Khách sạn: dán URL trang khách sạn trên Booking.com | `POST /watchlist {url, role, label}` | URL kênh khác → "Chỉ hỗ trợ trang khách sạn trên Booking.com."; URL không phải trang khách sạn → thông báo kèm ví dụ. Listing đã có (tenant khác theo dõi) dùng chung khách sạn. |
| 2 | Chip "đang kiểm tra" | job `verify_listing` | Booking trả tên, id, địa chỉ, toạ độ → `active` hoặc `broken` (404, hoặc **trùng**: URL khác cùng id với khách sạn đã có). Giao diện tự tải lại 5 giây/lần khi còn listing đang kiểm tra. |
| 3 | Sửa URL / tạm dừng | `POST /watchlist/{id}/listings {url}`, `PATCH …/listings/{id} {pause\|resume\|retry}` | Thay URL khi listing hỏng; 409 nếu URL đã gắn khách sạn khác. |
| 4 | Quét | scheduler: một run mỗi mốc giờ | Bị chặn >20%/15 phút tự dừng 30 phút; mọi proxy hỏng thì hoãn mốc. |

Ràng buộc: listing dùng chung giữa tenant (tạm dừng ảnh hưởng mọi tenant theo dõi khách sạn đó).

## J. Giao diện OTARadar và bù khoảng thiếu (02/10, plan `plans/261002-1332-market-wide-and-gap-fixes/`)

| Bước | Màn hình | API | Ghi chú |
|---|---|---|---|
| 1 | Đối thủ (thẻ) / Chi tiết khách sạn → "Quét ngay" | `POST /watchlist/{hotel_id}/scan-now` | Một run nhỏ cho một khách sạn; trùng trong 10 phút trả run đang chạy. **[sửa]** Quét cả watchlist không còn coi run một khách sạn là trùng. |
| 2 | Lịch sử quét → bấm một lượt | `GET /runs/{run_id}/jobs` | Từng khách sạn của tenant: trạng thái job, số trang đọc/có dữ liệu/bị chặn/lỗi; chi tiết lỗi chỉ operator thấy. Mã lượt quét thủ công/thị trường của tenant khác bị che. |
| 3 | Phòng trống › Phân tích công suất | `GET /market/occupancy?start&end` | Mỗi khách sạn một đường công suất ước tính (chỉ đêm đủ tin cậy), "KS ≈≥90% đêm đầu". |
| 4 | Terminal+ › Doanh thu 14 ngày | `GET /market/pace`, `GET /pms/daily` | PMS nếu có; không thì ≈ giá × công suất ước tính × tồn kho. |
| 5 | Cài đặt › Sự kiện | `GET/POST/PUT/DELETE /market/events` | Lễ hội, MICE, thể thao, mùa, khác; % tăng cầu dự kiến (người dùng nhập). Hiện trên lịch Terminal+; loại "Mùa" thành chip đầu trang. Viewer 403. |
| 6 | Terminal+ › Thời tiết / ngày lễ | `GET /market/weather`, `GET /market/holidays` | OpenWeather theo toạ độ khách sạn của bạn (cần `OPENWEATHER_API_KEY`, cache 30 phút, lỗi nhớ 2 phút, không ghi URL có key vào log). |

## K. Thị trường cả khu vực (02/10)

| Bước | Màn hình | API / job | Ghi chú |
|---|---|---|---|
| 1 | Cài đặt › Thị trường → tìm thành phố/quận | `GET /market/areas/search?q=` → `POST /market/areas` | Autocomplete Booking (thành phố/quận/vùng, kèm số chỗ ở). Cấu hình: số đêm danh sách, số KS quét chi tiết, số đêm chi tiết (≤90), trần request khám phá. |
| 2 | 03:00 giờ tenant (hoặc "Quét danh sách ngay") | job `scan_market_list` (hàng đợi booking, mỗi job một đêm, nối đuôi) | Mỗi đêm 1 request đọc "N properties found" + giá trang 1. Một đêm mỗi lượt là đêm khám phá: ghép trang 1 của các "lát cắt" (lọc hạng sao/loại hình/điểm/quận × kiểu sắp xếp) tới khi thấy ≥98% hoặc hết trần request. Booking bỏ qua `offset` nên không phân trang được. Bị chặn: thử lại một lần với phiên mới rồi dừng. |
| 3 | 05:00 | run `market:<area>:<ngày>` | Quét chi tiết top N khách sạn theo số đánh giá bằng pipeline probe sẵn có (phòng còn, công suất ước tính); tối đa 4 job thị trường chờ cùng lúc để không chặn run của tenant; hạn chót 20 giờ. Không lẫn vào tổng quan/compset của tenant. |
| 4 | Terminal+ › Thị trường <khu vực> | `GET /market/city?date=` | Công suất ≈ từ KS quét chi tiết, phòng còn/tồn kho ≈, số KS còn phòng (Booking báo), giá TB, phân bố giá (ghi "mẫu N/M" khi chưa phủ ≥98%). Chưa có khu vực → chỉ báo compset. |
| 5 | Đối thủ › Khám phá thị trường | `GET /market/city/hotels?sort&q&limit&offset` → `POST /watchlist` | Điểm/số đánh giá, hạng sao, quận, khoảng cách tới KS của bạn, giá đêm nay, còn/hết; "Theo dõi" thêm vào compset. |

Kết quả chạy thật 02/10 (quận Trung tâm TP.HCM, 1 đêm): Booking báo 370 KS còn phòng; một lượt khám phá 25 request ghép được 234 (63%). Trước đó phân trang bằng `offset` chỉ được 25.

## L. Chuẩn nghề revenue (09/10, plan `plans/261009-1106-rm-standards-roadmap/`)

| Bước | Màn hình | API / job | Ghi chú |
|---|---|---|---|
| 1 | Mọi màn: "Dữ liệu mới nhất lúc…", dải cảnh báo dữ liệu cũ, thẻ Trạng thái dữ liệu | `GET /data-status` | Quan sát Booking.com thành công cuối (không phải lượt kết thúc cuối), % thành công 7 ngày, cũ quá một chu kỳ quét. Lượt 0 dữ liệu không còn là "Cập nhật lúc". |
| 2 | Bảng điều khiển, Phòng trống, Giá, Đối thủ | `GET /overview?price_basis&own_hotel_id` | Trung vị/chỉ số giá niêm yết/vị trí giá chỉ khi ≥4 đối thủ có giá cùng điều kiện (3 = mẫu nhỏ, <3 = chưa đủ mẫu); quan sát cũ >48 giờ không vào trung vị; 5 trạng thái ô (còn bán, hết phòng, hạn chế, không có giá, lỗi); KM trên ô; cơ sở giá: mọi gói / huỷ miễn phí / có bữa sáng / chỉ phòng. |
| 3 | Chỉ báo lấp đầy, nhịp | `GET /market/pace?own_hotel_id`, `/market/occupancy` | Chỉ báo lấp đầy (thử nghiệm) ≈ khoảng [thấp, cao], sai số so PMS theo nhóm lead time. "So các tuần trước (cùng thứ)", không gọi là cùng kỳ. |
| 4 | Thay đổi (nhật ký) | `GET /events` | Đổi giá chỉ khi cùng loại phòng + cùng gói; phòng/gói rẻ nhất hết hoặc mở lại là `lowest_rate_shift`; loại phòng mất khi vắng ≥2 lượt; hạn chế, số đêm tối thiểu, KM bật/tắt. |
| 5 | Chi tiết đêm | `GET /hotels/{id}/dates/{d}` | Giá Booking.com (`rate`): giá trước KM + nhãn KM, bữa sáng/chỉ phòng, số đêm tối thiểu, điều kiện gói rẻ nhất. |
| 6 | Radar | `GET /market/radar/{promotions,restrictions,cancellation,area-scarcity}` | KM từng đối thủ (nhãn, độ sâu, số đêm, từ khi nào, Booking tự áp hay KS bật), hạn chế, chính sách huỷ, khan phòng khu vực so 7 ngày trước. |
| 7 | Cài đặt › Thông báo | `/notifications/subscriptions`, `/notifications/engagement` | Đăng ký theo người: email/Zalo/webhook × loại tin × giờ im lặng × trần/ngày; loại cảnh báo mới; lượt nhấn và "Đã xử lý". |
| 8 | Cài đặt › PMS › OTB; Terminal+ › OTB | `POST /pms/otb/import`, `GET /market/otb` | Báo cáo OTB theo ngày hoặc file đặt phòng chi tiết; pickup 1/7 ngày, pace 4 tuần, STLY, dự báo, KPI thật. |
| 9 | Chiến lược giá, gợi ý | `GET/PUT /market/strategy`, `GET /market/pace`, `PUT /market/suggestions/{d}/{kind}`, `/market/suggestions/{outcomes,backtest}` | Giá mục tiêu VND có giải thích, sàn/trần, định vị, gợi ý hạn chế; ghi giá đã áp dụng; đo kết quả. |
| 10 | Đối thủ › Uy tín, Hiển thị; Danh sách theo dõi | `GET /market/reputation`, `/market/visibility`, `/watchlist/compset-review`, `PATCH /watchlist/{id}` | Điểm/review theo thời gian, mốc 7,0/7,5/8,0/9,0, giá–chất lượng; thứ hạng tự nhiên vs quảng cáo, Preferred/deal; compset chính/phụ, tổng phòng, cảnh báo quy tắc CoStar. |
| 11 | Tải về | `GET /export/rate-shop.xlsx`, `/export/monthly-report.html` | Excel rate shop (khách sạn × đêm, compset, thay đổi); báo cáo tháng in PDF cho chủ đầu tư. |

## Điều còn để ngỏ

- Đổi mật khẩu chưa vô hiệu hoá phiên đang đăng nhập ở thiết bị khác (token còn hạn tối đa 12 giờ).
- `/events?highlight=<id>` chỉ đánh dấu khi sự kiện nằm trong trang hiện tại (chưa có endpoint lấy một sự kiện).
- Quét thủ công không chặn trùng với đợt theo lịch đang chạy.
- Zalo ZNS và SMTP cần tài khoản thật (OA doanh nghiệp xác thực, template duyệt; nhà cung cấp SMTP + SPF/DKIM); khi chưa cấu hình, tin ghi `skipped` và cảnh báo vận hành chỉ ghi log — `sb check-ops` báo rõ.
