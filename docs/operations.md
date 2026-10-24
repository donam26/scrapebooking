# Tài liệu vận hành (giai đoạn 1–5, roadmap chuẩn RM 10/2026)

## 1. Thành phần và tiến trình

| Tiến trình | Lệnh | Việc làm |
|---|---|---|
| `migrate` | `alembic upgrade head` | Tạo/cập nhật schema (migration 0001–0017; 0015 = chỉ giữ Booking.com, xoá dữ liệu kênh khác; 0017 = cột đo sức chứa `listings.capacity_*`). |
| `scheduler` | `python -m app.scheduler` | Mỗi 60 giây: tạo scan run Booking.com cho mốc giờ quét của tenant, đẩy job `probe_hotel`, đẩy lại job kẹt, chốt run quá hạn 90 phút, cảnh báo block rate và **tự ngắt** khi bị chặn >20%/15 phút (30 phút), hoãn mốc khi mọi proxy hỏng, kiểm tra proxy mỗi 15 phút, tạo partition tháng. |
| `worker` | `arq app.worker.settings.WorkerSettings` (`WORKER_CHANNEL=booking`) | Collector Booking.com: mỗi job = 1 khách sạn, lấy calendar rồi probe từng đêm theo tầng (0–14 đêm mọi lượt, xa hơn chỉ khi dữ liệu cũ), ghi snapshot, HTML thô lên MinIO. Cũng chạy `verify_listing` (URL người dùng dán trỏ khách sạn nào), `measure_capacity` (đo số phòng Booking bán tối đa một đêm, gợi ý "Số phòng") và `scan_market_list`. Ngân sách request/phút `CHANNEL_BUDGETS=booking=40`. Scale: `--scale worker=N`. |
| `jobs` | `arq app.jobs.settings.JobsWorkerSettings` | Analytics sau mỗi run (+ catch-up mỗi 30 phút), insight hằng ngày theo `insight_hour` của tenant (Batch API), insight theo yêu cầu (đồng bộ), poll batch mỗi 10 phút, đẩy job đo sức chứa Booking còn thiếu/cũ 09:20 giờ VN (`capacity_catch_up`), backup Postgres 02:30 giờ VN, dọn partition >24 tháng ngày 1 hằng tháng. |
| `api` | `uvicorn app.api.asgi:app` | FastAPI cho dashboard và import PMS. OpenAPI tại `/docs`, Prometheus tại `/metrics`. |
| `dashboard` | Next.js | Giao diện tenant và operator; gọi API qua rewrite `/api/*`. |

Hạ tầng: Postgres 16, Redis 7 (hàng đợi arq), MinIO (HTML thô 30 ngày, backup), Prometheus + Grafana (profile monitoring).

Hàng đợi arq tách riêng theo worker: `arq:queue:collector:booking` (`probe_hotel`, `verify_listing`,
`measure_capacity`, `scan_market_list`) và `arq:queue:jobs` (analytics, bản tin, cron, tiến trình `jobs`). Hai worker
không được dùng chung một hàng đợi: job của hàm mà worker không có sẽ bị bỏ ("function not found").

**Chỉ Booking.com (0015, 09/10/2026):** đã bỏ Agoda, iVIVU, Trip.com, Mytour, Traveloka, Expedia và
mọi tính năng chéo kênh (parity, đóng bán trên một kênh, tín hiệu cầu của kênh, tìm cùng khách sạn
trên kênh khác). Migration 0015 xoá dữ liệu các kênh đó (backup trước: `sb backup-db`) và bảng
`listing_demand_signals`. Khi nâng cấp: `docker compose up -d --remove-orphans` để bỏ container
`worker-agoda`, `worker-ivivu`, `worker-tripcom`, `worker-mytour`; xoá hàng đợi Redis cũ
`arq:queue:collector:{agoda,ivivu,tripcom,mytour}*`.

**Proxy:** `PROXY_URL_TEMPLATE` nhận nhiều proxy cách nhau dấu phẩy (xoay vòng mỗi session mới). Dạng
`host:port:user:pass` của nhà cung cấp viết thành `http://user:pass@host:port`. Kiểm tra:
`uv run sb check-proxy`. Scheduler tự kiểm tra 15 phút/lần và gửi cảnh báo (email tới
`OPS_ALERT_EMAILS` nếu đã cấu hình SMTP, luôn ghi log `ops_alert`).

**Nâng cấp từ bản dùng hàng đợi mặc định `arq:queue`:** dừng `scheduler` và `api`, chờ
`redis-cli ZCARD arq:queue` về 0 (kể cả job retry hoãn 60 giây), rồi mới deploy bản mới cho cả máy
trung tâm và máy collector (`docker-compose.collector.yml`) trong cùng một lần.

## 2. Khởi động lần đầu

```bash
cp .env.example .env            # điền PROXY_URL_TEMPLATE, JWT_SECRET, OPENROUTER_API_KEY
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.monitoring.yml up -d
cd backend
uv run sb add-user ops@congty.vn --role operator          # tài khoản operator đầu tiên
```

Sau đó vào dashboard http://localhost:3000, đăng nhập operator, tạo tenant, thêm khách sạn bằng URL trang khách sạn trên Booking.com (hệ thống tự kiểm tra URL: tên, toạ độ), tạo tài khoản `tenant_admin` cho khách hàng.

Dữ liệu demo để thử giao diện không cần scrape: `uv run python scripts/seed_demo.py`.

## 3. Luồng dữ liệu và bảng

`scheduler` → `scan_runs`, `scan_jobs` → `worker` → `probes`, `hotel_calendars`, `room_types`, `room_snapshots` (partition tháng), MinIO → `jobs/analytics` → `hotel_date_snapshots`, `availability_events`, `hotel_date_metrics` → `jobs/insight` → `insights` → `api` → dashboard. PMS: `pms_column_mappings`, `pms_imports`, `own_hotel_daily`.

Mọi bước idempotent: run theo `trigger_key`, probe theo `(scan_run_id, hotel_id, stay_date)`, analytics xoá và tính lại sự kiện của run, insight hằng ngày theo `(tenant, ngày địa phương)`.

## 4. Quy tắc analytics (cấu hình qua `.env`)

- Trạng thái ngày theo probe: `ok` → available; `sold_out` → sold_out; `skipped_calendar` → restricted (không nhận khách ngày đó, không phải hết phòng); `no_rooms_1n`, `blocked`, `error` → unknown. Lượt unknown không ghi đè số tốt gần nhất của ô (ô thành "cũ" sau 48 giờ).
- Đêm lịch báo không nhận khách vẫn được probe trang 1 đêm; trang báo hết thì probe "bắc cầu" (nhận phòng hôm trước, ở 2 đêm qua đêm đó): bắc cầu cũng hết → sold_out; còn phòng → restricted. Chỉ kết luận hết phòng khi có bằng chứng: đêm nay (giờ cắt đặt trong ngày), hôm trước cũng đóng (khối đêm đóng bán), hoặc hôm trước cần ≥3 đêm → giữ restricted (`worker/jobs.py` `_probe_closed_night`).
- Tỷ lệ thành công của run = 1 − (bị chặn + lỗi)/tổng: đêm hạn chế là quan sát hợp lệ, không tính vào "hết phòng" (`sold_out_count`).
- Số phòng công bố nằm ở hàng khách sạn dùng chung giữa tenant: nhập lần đầu thì ai cũng được; sửa số đã có cần là tenant duy nhất theo dõi hoặc operator.
- Số phòng còn mỗi loại phòng (`domain/stock.py`): badge "We have N left" hoặc dropdown dưới trần → `exact`; dropdown chạm trần (10, hoặc trần riêng `listings.dropdown_cap_seen`, VD Park Hyatt 9) → `capped` "≥N".
- Cả khách sạn (`analytics/rooms_left_bounds.py`): khoảng `[rooms_left_min, rooms_left_max]` từ trang (Σ loại phòng) và thang nbRooms của lịch; `exact_rooms_left` chỉ có khi min = max. Giao diện: "N", "N–M" hoặc "≥N"; "sắp hết" chỉ khi chắc chắn ≤ 3.
- Thang nbRooms (`worker/capacity_ladder.py`, `CAPACITY_LADDER`, mặc định `5,10,…,100`, rỗng = tắt): sau vòng probe, mỗi nấc N là một request lịch `nbRooms=N` cho cả cửa sổ đêm ("còn bán được N phòng?", tính trên tổng loại phòng; Booking nhận tới 100). Kết quả ở `hotel_calendars.rooms_min/rooms_max`. Đơn vị là đơn vị Booking bán: khách sạn có phòng dorm thì mỗi giường là một đơn vị (Meander: 42 phòng công bố, lịch vẫn còn ở N = 60 nhiều đêm). Chỉ đo đêm lịch báo còn nhận khách; nấc lỗi giữa chừng vẫn giữ các nấc đã đo.
- So sánh với **lần quan sát dùng được gần nhất** (available/sold_out), không phải đợt liền trước.
- `LOW_STOCK_THRESHOLD` (mặc định 3), `PRICE_CHANGE_THRESHOLD_PCT` (mặc định 3).
- pickup/velocity chỉ dùng cặp loại phòng `exact` ở cả hai lần.
- Sức chứa đối thủ: `hotels.rooms_total` + `rooms_total_source`/`rooms_total_updated_at` (nhập ở Cài đặt › Theo dõi, kèm URL nguồn); `listings.rooms_max_seen` = Booking từng mở bán tối đa (sàn lớn nhất từng thấy, analytics và lần đo đêm xa cập nhật).
- Gợi ý "Số phòng" (chỉ dùng Booking.com; Booking **không công bố** tổng số phòng): `worker/capacity_probe.py` tìm nhị phân trên lịch `nbRooms` số N lớn nhất mà ít nhất một đêm trong cửa sổ **hôm nay + 60, 61 đêm** còn bán (N = 1 trước để biết cửa sổ có phòng, rồi N = 100; ~9 request lịch/khách sạn khi không lỗi). Lỗi GraphQL/5xx (có thể tạm thời) được hỏi lại 1 lần; bị chặn, lỗi mạng, hết ngân sách thì dừng ngay, không gửi thêm request; trả lời rỗng = chưa biết. Ghi `listings.capacity_max` (giữ số lớn nhất, cập nhật nguyên tử), `capacity_capped` (còn bán ở trần 100), `capacity_checked_at` (lần đo xong), `capacity_next_at` (đo lại: xong +30 ngày, cửa sổ chưa có phòng +7 ngày, đo dở +1 ngày) và nâng `rooms_max_seen`. Đo ngay sau khi verify listing thành công và cron `capacity_catch_up` 09:20 giờ VN (khách sạn **chưa có số phòng** mà tới lịch đo, tối đa 20 listing, giãn 2 phút một job); job bỏ qua khi kênh đang tạm dừng. Đổi URL Booking của khách sạn thì xoá mọi số đo theo trang cũ (`capacity_*`, `rooms_max_seen`, `dropdown_cap_seen`).
  - Gợi ý = max(`capacity_max`, `rooms_max_seen`), chỉ có khi đã đo xong các đêm xa **và** cửa sổ đó có phòng (sàn các đêm gần một mình có thể thấp xa số thật). Chỉ là cận dưới ("≥N", không có nút dùng) khi chạm trần 100 hoặc lượt quét thường từng thấy nhiều hơn số đo (VD khách sạn giới hạn số phòng mỗi lần đặt). Có loại phòng giường dorm (`domain/capacity.py`: "Dormitory"/"Dorm", "Capsule"…) thì hiện số kèm cảnh báo đếm cả giường, không có nút dùng. Live 16/10/2026: Meander 94 đơn vị (42 phòng + giường dorm), Reverie ≥ 100 (286 phòng).
  - API: `HotelOut.rooms_suggestion {rooms, lower_bound, capped, includes_beds, confirmable, measured_at, source_url}` (`GET /watchlist`, `/hotels/{id}`); `POST /watchlist/{hotel_id}/rooms-suggestion/confirm {"rooms": N}` ghi `rooms_total` + nguồn = URL Booking của khách sạn, chỉ khi chưa có số (cập nhật có điều kiện, không ghi đè số đã nhập); 409 khi đã có số / chưa có gợi ý / gợi ý chỉ là cận dưới / đếm giường dorm / gợi ý vừa đổi. Số lấy từ gợi ý (nguồn = URL Booking) là ước tính: tenant nào theo dõi cũng thay được bằng số công bố qua `PATCH /watchlist/{id}`; số nhập tay vẫn theo quy tắc chỉ người theo dõi duy nhất/operator sửa.

## 5. AI insight

- Nhà cung cấp: **OpenRouter** (Chat Completions, OpenAI-compatible). `OPENROUTER_MODEL=openai/gpt-6-luna`, `OPENROUTER_REASONING_EFFORT=medium`, `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`, prompt hệ thống cố định (`app/insight/prompt.py`, `PROMPT_VERSION`).
- Hằng ngày: `INSIGHT_USE_BATCH=true`. OpenRouter **không có** Batch API server-side nên đây là giả lập: `submit_batch` chạy song song ngay bằng Chat Completions và cache kết quả vào Redis (key `insight:batch:*`, TTL 48h), `jobs` poll mỗi 10 phút materialize vào DB; luồng `pending`/`batch_pending` → `completed`/`failed` giữ nguyên. **Không có chiết khấu batch** (cost batch = cost đồng bộ). Theo yêu cầu từ dashboard: gọi đồng bộ.
- Mọi highlight/pricing_opportunity/risk phải có `evidence.ref` tồn tại trong đầu vào (`evt:<id>`, `metric:<hotel_id>:<date>`, `compset:<date>`); mục sai bị loại vào `dropped_highlights`.
- Không có `OPENROUTER_API_KEY` thì dùng client giả (đầu ra rỗng có ghi chú) để hệ thống vẫn chạy.
- Đổi prompt: tăng `PROMPT_VERSION`, chạy `uv run pytest tests/unit/test_insight_scenarios.py`.

## 5b. Thông báo email

- Cấu hình ở `.env` (worker `jobs` và `api`): `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY` (`starttls` | `ssl` | `none`), `APP_BASE_URL` (gốc dashboard cho liên kết trong email). Để trống `SMTP_HOST` thì không gửi; nhật ký ghi `skipped` / `smtp_not_configured`. Đổi `.env` xong phải tạo lại container (`up -d --force-recreate jobs api`).
- Cron `dispatch_notifications` (jobs, mỗi 5 phút, idempotent qua bảng `notifications.dedupe_key`):
  - `alerts:{tenant}:{run nhỏ nhất của mốc}`: sự kiện của run Booking.com của mốc quét đã analytics (24 giờ qua), lọc theo luật của tenant (`notification_rules`): hết phòng (N đêm tới, ≥ M đối thủ hết), sắp hết phòng, giảm/tăng giá ≥ X% (cùng phòng + gói), đêm căng, KM sâu, lệch định vị, khách sạn của bạn hết phòng/không nhận khách. Một email gom mọi mục; không có mục thì ghi `skipped`/`no_matches` (ẩn trên dashboard).
  - `insight:{id}`: bản tin daily `completed` trong 36 giờ qua.
  - `weekly:{tenant}:{năm}-W{tuần}`: thứ Hai từ 08:00 giờ tenant (bù trong thứ Ba nếu worker tắt cả thứ Hai).
  - Dòng được chèn ở trạng thái `sending` và commit trước khi gửi. Email lỗi SMTP thử lại sau 5 phút, 30 phút, 2 giờ (tối đa 4 lần); dòng `sending` quá 10 phút (worker chết giữa chừng) cũng được gửi lại. Mỗi lần thử giành dòng bằng UPDATE có điều kiện nên cron chạy chồng không gửi trùng. Email thử không được thử lại.
  - Lỗi của một tenant (dữ liệu lạ, DB) được ghi log `notification_dispatch_failed` và bỏ qua, không chặn tenant khác.
  - Không gửi bù: `skipped` vì chưa cấu hình SMTP hoặc chưa có người nhận là trạng thái cuối (cảnh báo chỉ có giá trị khi kịp thời).
- Người nhận do tenant_admin quản lý ở Cài đặt › Thông báo; mỗi người nhận một email riêng. Nút "Gửi thử" giới hạn 1 lần/phút/tenant.
- Thử cục bộ không gửi ra ngoài: `uv run --with aiosmtpd python -m aiosmtpd -n -l localhost:1025` rồi đặt `SMTP_HOST=localhost SMTP_PORT=1025 SMTP_SECURITY=none`.

## 5b2. Kênh gửi ngoài email, đăng ký theo người, đo hành động (roadmap Phase 3)

- Mỗi khoá outbox gửi email trước (người nhận cũ + đăng ký email), rồi **một dòng riêng mỗi kênh**
  `<khoá>:zalo`, `<khoá>:webhook` (cột `notifications.channel`) khi tenant có người đăng ký kênh đó.
  Mỗi người nhận một dòng `notification_deliveries` (trạng thái, mã tin Zalo, chi phí, token).
- Đăng ký (`/notifications/subscriptions`, người xem tự quản lý đăng ký của mình): kênh × loại tin
  (`alerts`, `daily_insight`, `weekly_report`, `data_stale`; rỗng = mọi loại) × giờ im lặng (giờ
  tenant, qua nửa đêm được) × trần tin/ngày. Tin rơi vào giờ im lặng/vượt trần ghi `skipped_quiet` /
  `skipped_limit`, không gửi bù.
- **Zalo ZNS**: cần OA doanh nghiệp xác thực (tên trùng đăng ký kinh doanh), Zalo Cloud nạp trước,
  template duyệt trước. Mọi template dùng tham số `title, summary, count, date, url, resolve_url`
  (link đặt trong nút). `.env`: `ZALO_ZNS_TEMPLATES=alerts=…,daily_insight=…,weekly_report=…,
  data_stale=…,test=…`, token: `ZALO_APP_ID/ZALO_APP_SECRET/ZALO_REFRESH_TOKEN` (tự làm mới) hoặc
  `ZALO_ZNS_ACCESS_TOKEN`. Đơn giá ghi sổ: `ZALO_ZNS_COST_VND` (mặc định 300). Không dùng Telegram
  (bị chặn ở Việt Nam từ 21/05/2025).
- Link trong tin đi qua `/api/notifications/t/<token>?to=/…` (ghi lượt nhấn, chỉ chuyển hướng
  trong dashboard) và nút "Đã xử lý" `/api/notifications/t/<token>/resolve`. Số liệu theo tuần, theo
  kênh: `GET /notifications/engagement` (gửi/lỗi/bỏ qua/nhấn/đã xử lý/chi phí — chỉ số O4).
- Loại cảnh báo mới (gom vào email cảnh báo mỗi mốc): đêm căng (≥x% đối thủ hết/≤3 phòng, chỉ khi
  lượt này có biến động), đối thủ **tăng** giá cùng phòng + gói, đối thủ bật KM sâu ≥x%, giá bạn
  lệch định vị mục tiêu (mặc định tắt), khách sạn của bạn hết phòng/không nhận khách trên Booking.com.
- **Dữ liệu cũ** (`data_stale:{tenant}:{ngày}`): quan sát Booking.com thành công cuối cũ hơn một chu
  kỳ quét (khoảng cách lớn nhất giữa hai mốc + 2 giờ) → tối đa một tin/ngày.

## 5c. Ước tính công suất và gợi ý giá (đợt 2)

- Bảng `occupancy_estimates`, `occupancy_estimate_runs` (dấu đã xử lý), `price_suggestion_decisions` (migration 0008).
- Cron `estimate_occupancy_catch_up` (jobs, phút 4/14/…/54): lượt quét đã có `hotel_date_snapshots` mà chưa có dấu → tính, mỗi lượt commit riêng, lỗi một lượt không chặn lượt khác. Tồn phòng nhìn thấy = lớn nhất trong 30 ngày (số chính xác hoặc mức sàn).
- Tính lại toàn bộ: xoá `occupancy_estimate_runs` (và `occupancy_estimates`) rồi để cron chạy.
- Tổng phòng công bố (`hotels.rooms_total`, nhập ở Cài đặt › Danh sách theo dõi) là mẫu số của
  chỉ báo lấp đầy khi lớn hơn phần kênh từng mở bán. `/market/pace` trả sai số so PMS theo nhóm lead
  time 0–7 / 8–30 / 31–90 ngày (MAE, độ lệch, MAPE); nhóm sai số > 20 điểm bị đánh dấu `usable=false`.
- **OTB (Phase 5)**: `POST /pms/otb/import` (`kind=otb_report`: báo cáo phòng đã đặt theo ngày, ngày
  chụp mặc định hôm nay; `kind=bookings`: file đặt phòng chi tiết, tự dựng bản chụp 0–120 ngày trước
  khi đến cho cả quá khứ). Bảng `otb_snapshots` khoá (tenant, khách sạn, ngày chụp, đêm), nhập lại
  không ghi đè ngày khác. `GET /market/otb`: pickup 1/7 ngày, pace so 4 tuần trước và STLY (364
  ngày), dự báo cộng pickup lịch sử cùng thứ, KPI thật 30 ngày (Occ/ADR/RevPAR từ PMS).
- **RMS-lite (Phase 6)**: chiến lược `GET/PUT /market/strategy` (giá gốc, sàn/trần, định vị mục tiêu,
  làm tròn, đổi tối đa/ngày, điều chỉnh theo thứ/lễ/sát ngày). Gợi ý có giá mục tiêu VND, từng điều
  chỉnh có số, gợi ý hạn chế (min-stay, tắt KM, KM giờ chót); không bao giờ gợi ý giảm cho đêm
  căng. `GET /market/suggestions/outcomes` (đã áp dụng → kết quả), `/market/suggestions/backtest`
  (chạy lại luật trên quan sát ~7 ngày trước đêm, chấm theo công suất thật).
- PWA: `dashboard/src/app/manifest.ts`, icon trong `public/icons/`, `src/app/icon.svg`, `src/app/apple-icon.png`; `proxy.ts` cho qua manifest/icon không cần cookie.

## 5d. Thị trường khu vực: quận/bán kính + thang phòng trống (16/10/2026, migration 0018)

Khu vực (`market_areas`, Cài đặt › Thị trường) = điểm đến Booking (`city`/`district`/`region`/`landmark`,
dest_id lấy từ autocomplete) hoặc bán kính quanh khách sạn của tenant (`latlong` + `radius_m`
1000/3000/5000 = bộ lọc `distance` của Booking), tuỳ chọn phân khúc `segment_nflt` (cú pháp nflt của
Booking, các lựa chọn cùng nhóm là OR: `ht_id=204;ht_id=206;ht_id=219` = khách sạn + resort + căn hộ
khách sạn). Quận của Booking dùng tốt ở TP.HCM (`di` 2088 = Quận 1); ở Vũng Tàu quận "Back Beach"
(16195) trả 0 khách sạn trong quận → dùng địa danh (Bãi Sau 258614, Bãi Trước 258615) hoặc bán kính.

Job `scan_market_list` (03:00 giờ tenant, một job mỗi đêm, `list_nights` đêm) gọi GraphQL `FullSearch`
của Booking (`app/marketscan/graphql.py`, cùng endpoint/csrf/session/proxy/ngân sách với lịch):
1. thị trường: khu vực (+ bán kính), không lọc phân khúc, 1 kết quả → số còn phòng, % đã kín Booking tự
   tính (`unavailability_pct`, chỉ lưu khi không có bộ lọc nào), thành phần loại hình;
2. danh sách: + phân khúc, 1 phòng 2 người lớn, 100 kết quả/request (Booking cắt ở 1.000) → khách sạn,
   giá, hạng hiển thị, "We have N left"; khách sạn Booking "nới thêm" ngoài khu vực bị loại;
3. thang: nấc `MARKET_LADDER_RUNGS` (mặc định 3,5,10,20,30; 1 người lớn/phòng, Booking kẹp ≤ 30) →
   số khách sạn còn bán được ≥ N phòng. Trang đầu của mọi nấc được hỏi ngay sau trang danh sách đầu,
   nên hết trần giữa chừng vẫn có thang đủ nấc (thang chỉ được lưu khi đủ nấc; nấc trên một nấc 0
   điền 0). `MARKET_ENUMERATE_NIGHTS` (14) đêm đầu lật đủ id ở mọi nấc → `market_list_prices.rooms_min`
   (khoảng phòng còn từng khách sạn); `enumerated` chỉ bật khi danh sách và mọi nấc đủ ≥ 98% và không
   nấc nào vượt trần 1.000 của Booking (khu vực lớn hơn: chỉ có số đếm, không có khoảng từng KS).
Trần request mỗi đêm = `max_pages` (≤ `MARKET_MAX_PAGES`); hết trần → `capped`, giữ phần đã có. Lỗi
GraphQL hỏi lại 1 lần; vẫn lỗi (đổi schema) → dự phòng trang SSR đầu (`source=ssr`, không thang). Chặn
thật (403/429, challenge, 200 không phải JSON, thiếu csrf) → thử lại 1 lần với phiên mới rồi tạm dừng
quét danh sách của kênh (`booking:market`); HTTP 4xx khác/5xx chỉ là lỗi của đêm đó. Mỗi lượt quét ghi
bộ lọc đã dùng (`market_list_scans.nflt`); đổi phân khúc/bán kính thì lượt cũ ẩn khỏi API và danh
sách khách sạn của khu vực được dựng lại. Phân khúc chỉ nhận trường `ht_id`, `class`, `review_score`,
`ht_beach`, `hotelfacility`, `mealplan`, `fc`, `chaincode`.

Chi phí đo thật (16/10, Quận 1, phân khúc khách sạn + resort + căn hộ khách sạn): ~30 request,
~80 giây mỗi đêm liệt kê đủ (428–464 khách sạn còn phòng), so với ~30 trang × 300 khách sạn mỗi ngày
của quét chi tiết top N (`detail_max_hotels`, giữ mặc định 300; đặt 0 để tắt).

API: `GET /market/city?date&area_id` (thêm `ladder`, `rooms_left_floor`, `tightness`,
`tightness_median`, `sold_out_share`/`segment_base`, `unavailability_pct`, `composition`, `classes`,
`booking_histogram`, `self_hotel`), `GET /market/city/trend?start&nights` (≤ 30 đêm),
`GET /market/areas/self-location`. Đối chiếu thang tìm kiếm với thang lịch của compset:
`uv run python scripts/validate_market_ladder.py <area_id> [đêm]` (cần một lượt quét compset cùng ngày).

## 6. Lệnh vận hành (`uv run sb ...`)

| Lệnh | Việc |
|---|---|
| `add-tenant`, `add-hotel`, `add-user` | Onboard bằng CLI (dashboard làm được việc tương tự). `add-hotel <tenant> <url>` nhận URL mọi kênh hỗ trợ; listing thêm qua CLI được quét ngay (không chờ verify). |
| `scan-now [--no-enqueue]` | Tạo scan run Booking.com thủ công cho mọi tenant. Trên dashboard: nút "Quét ngay" (tenant, `POST /watchlist/scan-now`) và "Quét tất cả ngay" (operator, `POST /health/scan-now`), chống trùng trong 10 phút. |
| `check-proxy` | Gọi thử qua từng proxy, in IP ra (không in mật khẩu); mã thoát 1 nếu có proxy lỗi. |
| `check-ops` | Kiểm tra cấu hình cảnh báo vận hành và giao tin: số template proxy (nên ≥2), SMTP, `OPS_ALERT_EMAILS`, webhook, Zalo ZNS. Mã thoát 1 nếu cảnh báo vận hành chỉ ghi log. |
| `canary` | Độ phủ trường parse (phòng, giá, tồn phòng, cờ thuế, bữa sáng) 24 giờ qua so với 7 ngày trước; mã thoát 1 nếu một trường tụt dưới 70% mức nền (cron `parser_canary` 08:15 hằng ngày báo operator). |
| `analyze --reanalyze-days N` | Tính lại analytics mọi run đã chốt trong N ngày (theo thứ tự) sau khi đổi quy tắc sự kiện. |
| `run-status --limit 5` | Trạng thái các đợt quét gần nhất. |
| `analyze [--run-id N] [--all-pending]` | Chạy analytics tay. |
| `insight <tenant_id> [--sync/--batch]` | Sinh bản tin tay. |
| `rederive-stock [--no-reanalyze]` | Tính lại `rooms_left`/`stock_confidence` mọi room snapshot từ `badge_count`/`dropdown_max` đã lưu (không cần HTML thô) sau khi đổi `domain/stock.py`, cập nhật trần riêng listing, rồi tính lại analytics các run bị đổi. Sau migration 0016 chạy thêm `analyze --reanalyze-days 30` để điền khoảng phòng còn cho mọi run. |
| `measure-capacity [--hotel-id N] [--force] [--limit 20]` | Đẩy job đo số phòng Booking bán tối đa một đêm (gợi ý "Số phòng") cho khách sạn chưa có số phòng mà tới lịch đo, giãn 2 phút một job; `--force` đo cả listing chưa tới lịch và thay kết quả cũ (VD gỡ cờ chạm trần đo nhầm); `--hotel-id` đo lại ngay một khách sạn (kể cả đã có số). Cần worker Booking và proxy sống. |
| `reparse --since-days 30 [--no-reanalyze]` | Parse lại HTML thô **Booking** sau khi đổi parser, rồi tính lại analytics cho các run bị ảnh hưởng. Kênh khác lưu payload JSON; `parser_version` mỗi probe có dạng `<kênh>:<phiên bản>`. |
| `ensure-partitions`, `prune-partitions --keep-months 24` | Partition `room_snapshots`. |
| `backup-db` | pg_dump → gzip → MinIO bucket `BACKUP_BUCKET`, giữ `BACKUP_KEEP` bản. |

## 7. Giám sát và cảnh báo

- Grafana dashboard "Collector health": probe theo status, block rate 15 phút, session thu hồi, thời gian probe, job, analytics/insight.
- Cảnh báo vận hành luôn ghi log warning `ops_alert`, và gửi tới **email** (`SMTP_*` + `OPS_ALERT_EMAILS`) và/hoặc **webhook chat** (`OPS_ALERT_WEBHOOK_URLS`: Slack/Google Chat nhận `{"text"}`, Discord `{"content"}`). Không cấu hình kênh nào thì chỉ có log — `sb check-ops` báo lỗi.
- Điều kiện báo: block rate >20%/15 phút (throttle 30 phút); lượt quét 0 dữ liệu hoặc dưới 90% thành công; **mọi proxy hỏng** (mốc quét bị hoãn, tối đa 4 giờ, rồi bỏ và báo); Booking.com **dưới 80% thành công trong 24 giờ**; **không có dữ liệu mới quá 10 giờ**; run quá hạn chót; trôi parser (canary); insight/backup thất bại. Điều kiện theo giờ throttle 6 giờ.
- Tenant thấy độ tin cậy dữ liệu Booking.com: `GET /data-status` (quan sát thành công cuối, % thành công 7 ngày, cũ hay chưa) và tin `data_stale`.
- Operator xem `/admin/health` trên dashboard hoặc `GET /health/summary`.

### 7a. Runbook: sự cố proxy (như 01/10 và 08–09/10/2026: `407 Proxy Authentication Required`)

1. `uv run sb check-proxy` (từ máy có `.env`): template nào `FAIL http 407` = hết hạn/sai thông tin xác thực; `ProxyError`/`CONNECT` = nhà cung cấp lỗi.
2. Gia hạn hoặc sửa user/pass trong `PROXY_URL_TEMPLATE`; nên luôn có **≥2 nhà cung cấp** (cách nhau dấu phẩy). Worker bỏ qua template mà lần kiểm tra gần nhất của scheduler báo hỏng (Redis `proxy:health`) và tự ngắt 10 phút template lỗi 3 lần liền khi mở phiên.
3. `docker compose up -d --force-recreate scheduler worker jobs api` để nạp `.env`.
4. Scheduler tự kiểm tra lại proxy trước mốc kế tiếp; mốc đang hoãn được tạo ngay khi có proxy chạy, lỡ lâu hơn thì quét bù. Có thể bấm "Quét tất cả ngay" ở `/admin/health`.
5. Xác nhận: `sb run-status`, `GET /data-status` (last_success_at mới), `sb canary`.

### 7b. Runbook: parser trôi (canary báo)

1. `sb canary` để xem kênh/trường tụt; mở HTML/payload thô trong MinIO của lượt gần nhất.
2. Cập nhật selector/parser, tăng `PARSER_VERSION`, thêm fixture thật vào `tests/fixtures`, chạy `make test`.
3. Booking: `sb reparse --since-days N`; kênh khác: chờ lượt sau. Rồi `sb analyze --reanalyze-days N`.

## 8. Khôi phục

```bash
# liệt kê backup
mc alias set local http://localhost:9000 minioadmin minioadmin
mc ls local/pg-backups/postgres/
mc cp local/pg-backups/postgres/scrapebooking-<ts>.sql.gz . && gunzip scrapebooking-<ts>.sql.gz
psql postgresql://app:app@localhost:5432/scrapebooking < scrapebooking-<ts>.sql
```

## 9. Lưu trữ

- HTML thô: lifecycle rule 30 ngày trên bucket `raw-html`.
- `room_snapshots`: partition tháng, xoá partition cũ hơn 24 tháng (job tháng hoặc `prune-partitions`).
- Sự kiện, chỉ số, insight: giữ vô hạn.

## 10. Kiểm thử

```bash
make lint && make typecheck
make test        # unit
make test-int    # unit + integration (cần Postgres, Redis; MinIO tuỳ chọn)
cd backend && uv run pytest tests/live -m live -s   # gọi Booking thật, cần proxy thật
cd dashboard && npm run lint && npm run typecheck && npm run build
```

Kiểm chứng dữ liệu một đợt quét thật với HTML thô trong MinIO (trích độc lập, không dùng parser):

```bash
cd backend && uv run python scripts/validate_run.py <scan_run_id>   # exit 1 nếu có sai lệch
```

Chạy sau mỗi lần Booking đổi giao diện hoặc sửa parser (kèm `sb reparse`). Lần kiểm chứng đầu
(2026-09-25, 4 khách sạn Q1 × 30 ngày, 3 đợt): 2.957/2.957 snapshot loại phòng khớp.

Ghi chú về dữ liệu Booking (đối chiếu trang thật 2026-09):
- Chromium headless phải dùng UA không có "HeadlessChrome", nếu không Booking 301 về trang không có
  ngày; collector coi trang có `checkin` khác ngày đã yêu cầu là bị chặn (đổi session).
- Dòng "Booking Basic" (`data-block-id` chứa `bbasic`, "Partner offer") là giá đối tác bán lại,
  không tính vào giá/tồn kho của khách sạn.
- Giá thấp nhất chỉ tính dòng giá cho đủ số người lớn đã tìm (bỏ "Only for 1 guest").
- Số phòng mức khách sạn trên heatmap là tổng các loại phòng biết chính xác (cận dưới khi có loại
  phòng "≥10" hoặc ẩn).

## 11. Rà soát flow người dùng

Chi tiết từng flow (operator, tenant admin, xem hằng ngày, bản tin, PMS, vận hành) và các
ràng buộc đã bổ sung: `docs/user-flows.md`.

## 12. Việc còn lại trước khi bán dịch vụ

- ~~Thay fixture HTML mô phỏng bằng trang Booking thật~~ (xong 2026-09-25, xem `backend/tests/fixtures/html/README.md`).
- Chạy thật giai đoạn 1 vài ngày (tiêu chí trong `docs/runbook-phase1.md`); đã chạy 3 đợt đầu với proxy dân dụng VN: 359/360 probe OK (1 lỗi 502 tạm thời, nay tự thử lại), 0 bị chặn.
- Tư vấn pháp lý về ToS Booking.com trước khi bán cho khách hàng.
- Adapter API cho ezCloud / Newway / Hotel Link / Smile khi được cấp quyền (interface `PmsAdapter` đã có).
- Chọn nhà cung cấp SMTP (SES, Postmark, Brevo…), cấu hình SPF/DKIM cho tên miền gửi, điền `SMTP_*` (mục 5b).
- Proxy thứ hai và gia hạn proxy hiện tại (mục 7a); đặt `OPS_ALERT_EMAILS` / `OPS_ALERT_WEBHOOK_URLS`.
- Hồ sơ Zalo OA doanh nghiệp + duyệt template ZNS (mục 5b2).
