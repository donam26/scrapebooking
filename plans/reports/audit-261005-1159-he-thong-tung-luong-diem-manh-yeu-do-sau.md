# Audit toàn hệ thống OTARadar: từng luồng, điểm mạnh, điểm yếu, độ sâu

Ngày: 2026-10-05. HEAD `cbadf0d` (main). Phương pháp: đọc code backend/dashboard/infra theo từng luồng
(4 agent audit song song + kiểm chứng tay các phát hiện nặng), đối chiếu docs/plans, đọc log CI GitHub.
Kèm plan hoàn thiện: `plans/261005-1159-hoan-thien-he-thong/plan.md`.

Giới hạn: môi trường cloud này chặn PyPI/npm (403) nên **không chạy được ruff/mypy/pytest/tsc tại chỗ**.
Số test là đếm tĩnh (388 unit + 178 integration backend, 0 test dashboard). CI `main` hiện **đỏ** (mục 1.1)
nên không có bằng chứng máy móc nào rằng bộ test pass ở HEAD; số "662 pass" trong plans là của 02/10.

Thang độ sâu: 1 = khung/stub · 2 = chạy được demo · 3 = dùng được, còn lỗ hổng rõ · 4 = vững, thiếu
vài góc · 5 = production-hardened.

## 0. Kết luận ngắn

Hệ thống **không phải MVP**: ~22k dòng backend, ~16,5k dòng dashboard, 11 migration, 5 kênh OTA, pipeline
một chiều idempotent (scheduler → worker → analytics → insight → API → dashboard), bản tin AI có kiểm
chứng bằng chứng, email outbox có retry, quét bù khi lỡ lịch, tự ngắt kênh bị chặn, thị trường cả khu vực.
Độ sâu trung bình **3/5**: lõi nghiệp vụ tốt hơn hẳn phần "vỏ" (bảo mật vận hành, hạ tầng, test FE, hygiene repo).

Năm việc phải làm trước mọi tính năng mới (chi tiết ở từng mục):

| # | Vấn đề | Hệ quả | Nơi |
|---|---|---|---|
| 1 | CI `main` đỏ từ commit "123" (ruff), mypy + pytest bị skip; `seed_demo.py` và `capture_fixture.py` gọi cột/module đã xoá | Không ai biết test có pass; README hướng dẫn chạy script chết | 1.1 |
| 2 | Giá Booking khi probe nhiều đêm (min-LOS > 1) lưu **giá cả kỳ**, không chia theo đêm; Booking không kiểm tra tiền tệ | Sự kiện `price_up/down` giả, trung vị compset, parity, gợi ý giá sai đúng vào các đêm lễ/Tết | 2.1 |
| 3 | `jwt_secret` mặc định `change-me` không chặn khi khởi động; login không giới hạn thử; không có password reset; đổi mật khẩu không huỷ phiên | Brute-force, chiếm phiên khi secret mặc định lọt ra production | 2.8 |
| 4 | Postgres/Redis/MinIO mật khẩu mặc định và mở cổng ra host; không reverse proxy/TLS; backup nằm cùng máy | Mất máy = mất dữ liệu + backup; cổng DB lộ ra Internet nếu VPS không firewall | 2.10 |
| 5 | Phản hồi "soft block" (200 nhưng là trang chặn/đổi schema) bị coi là `not_found` → listing bị đánh `broken` vĩnh viễn, tenant phải dán lại URL | Mất dữ liệu kênh đó cho tới khi có người để ý | 2.1 |

## 1. Nền tảng repo, CI, tài liệu

### 1.1 Sự thật đã kiểm chứng
- 4 commit tên `123` (`44d0ed4`, `904fa7b`, `7f70433`, `cbadf0d`): `cbadf0d` gộp **toàn bộ** wave1 + wave2 + đa kênh + restyle + thị trường + i18n (429 file, +57k dòng) vào một commit không mô tả. `7f70433` thêm 1.111 file trong đó 980 file là `.claude/` (17 MB skill/command/hook của tooling) được track trong git; `.omc/state` cũng bị track dù `.gitignore` có `.omc/`.
- CI run #4 (`cbadf0d`, 05/10 11:52): job backend **fail** ở `ruff` (I001 `scripts/capture_fixture.py:56`), mypy và pytest **skipped**. Job dashboard pass. Run #3 (25/09) là lần cuối backend xanh.
- `backend/scripts/capture_fixture.py:62` import `app.domain.booking_url` đã xoá ở `a9f66ff` → `ImportError`.
- `backend/scripts/seed_demo.py:69-92` tạo `Hotel(booking_url=…, booking_slug=…, booking_hotel_id=…)`: 3 cột đã bỏ ở migration 0007 → `TypeError`. README mục "Chạy nhanh" hướng dẫn chạy script này.
- `tests/unit/test_openapi_snapshot.py` tồn tại nhưng CI chưa chạy tới; không kiểm chứng được `docs/api/openapi.json` và `dashboard/src/lib/api-types.ts` (4.900 dòng sinh tự động) còn khớp app.
- Tài liệu rất đầy đủ và trung thực (`PRODUCT.md`, `docs/operations.md`, `docs/user-flows.md`, 6 plan, 8 report nghiên cứu). Điểm mạnh hiếm có. Nhưng plans ghi "done" cho mọi phase trong khi: DB dev chưa migrate 0010/0011, image Docker chưa build lại, email còn thương hiệu ScrapeBooking, icon PWA cũ, Bảng điều khiển chưa có thẻ thị trường khu vực.
- `.claude/rules/*.md` nói về PHP/Laravel/`php -l`/pint: không đúng stack (Python/TS). Rule sai làm agent/dev mới tốn thời gian.

### 1.2 Đánh giá
Độ sâu **2/5** (hygiene). Code tốt nhưng quy trình giao hàng (commit, CI xanh, script onboarding) đang hỏng.

## 2. Từng luồng

### 2.1 Thu thập dữ liệu (collector, 5 kênh)

**Luồng chung:** URL listing → `SessionManager` (proxy sticky theo session, xoay theo tuổi/số request/bị chặn) →
fetch (curl_cffi giả Chrome, hoặc Chromium cho Trip.com/iVIVU token) → `classify_response` (403/429/503/202 =
blocked, 404 = not_found, quét 20 KB đầu tìm marker chặn) → parser kênh → `RoomOffer` + `RatePlan` →
`domain/stock.py` suy `rooms_left` + `stock_confidence` → payload thô gzip lên MinIO (30 ngày) → `room_snapshots`.

**Điểm mạnh**
- Booking: loại "Booking Basic/partner offer" (`booking/parser.py:134-135,208`), bỏ giá cho ít khách hơn (`:215`), badge + dropdown → exact/capped (`:217-227`), phát hiện trang trả về sai ngày (`hybrid.py:135-150`), soft-block `dates_dropped` (`selectors.py:38-40`), calendar GraphQL đọc min-LOS trước (`calendar.py:24-87`), fallback Playwright khi rỗng/bị chặn 2 lần (`hybrid.py:160-166,200-202`), golden fixture HTML thật + expected JSON, 19 test hybrid.
- Agoda: ưu tiên giá gồm thuế theo đêm và gắn cờ khi phải fallback (`agoda/parser.py:160-194`), tách khuyến mãi tự áp vs mã (`:135-157`), loại gói/nhiều phòng (`:197-203`), tín hiệu cầu 24h (`:247-261`), ~20 test collector.
- iVIVU: ghi `source_supplier` từng giá (lộ giá sỉ qua đại lý) (`ivivu/parser.py:183-185`), cắt payload 3 MB → trường cần (`:188-217`), allowlist route cho Chromium mint token (`token_minter.py:159-172`).
- Trip.com: phân biệt combo/gói (`tripcom/parser.py:203-216`), kiểm checkin + adults so với yêu cầu (`:335-341`).
- Mytour: loại giá ẩn/member/giả (`mytour/parser.py:109-116`), lưu phút thật của "đặt N giờ trước" thay vì số bị chia 5 (`:86-98`), kiểm tồn tại khi rỗng để tách not_found/sold_out (`mytour/collector.py:280-311`).
- Ngân sách request/phút theo kênh dùng Redis INCR+EXPIRE nguyên tử (`budget.py:33-36`).

**Điểm yếu (đã kiểm chứng tay các mục đánh dấu ★)**
- ★ **Giá Booking đa đêm = giá cả kỳ.** Worker probe với `nights = min_length_of_stay` (`worker/jobs.py:168`), nhưng `parse_hotel_page` không nhận `nights` (`booking/parser.py`, `hybrid.py:96-99` chỉ dùng để build URL) và không chỗ nào ở `repo/snapshots.py`, `analytics/service.py` chia theo đêm. Agoda/Trip.com/Mytour có test "giá theo đêm" riêng; Booking chỉ test `nights=1`. Cần 1 fixture Booking 2 đêm để chốt, nhưng theo giao diện Booking (hiện "Price for N nights") gần như chắc chắn sai.
- ★ **Booking không kiểm tra tiền tệ**: `parse_price` lấy mã từ text, regex nhận mọi 3 chữ hoa (`booking/parser.py:16,38-46`); 4 kênh kia đều reject khi lệch (`agoda/collector.py:354`, `ivivu/parser.py:105`, `tripcom/parser.py:358`, `mytour/collector.py:275`). Thuế: Booking chỉ gắn cờ `taxes_included=False`, giá vẫn trước thuế (`booking/parser.py:75-81`) → so kênh "cùng cơ sở" chỉ đúng khi loại các dòng này.
- ★ **Soft block → listing `broken`**: `worker/jobs.py:210` gọi `mark_listing_broken` khi lỗi là chuỗi `"not_found"`; chuỗi này sinh ra từ Agoda thiếu `hotelInfo.name` (`agoda/collector.py:352`), iVIVU thiếu `ng-state` (`ivivu/collector.py:255,147`), Trip.com redirect (`tripcom/collector.py:165`), Booking verify không có marker chặn (`listing_jobs.py:64`, `booking/collector.py:100-103`). Trang challenge trả 200 = listing hỏng vĩnh viễn.
- Bootstrap session ném exception không được bắt ở `hybrid.py:105` và `tripcom/collector.py:109` → probe ghi ERROR/HTTP thay vì BLOCKED, fallback browser của Booking không chạy.
- iVIVU bỏ phí số phòng: `AvailableNo` có trong payload (`ivivu/parser.py:46,61`) nhưng `badge_count=None` (`:130`) → luôn `hidden`. Thiếu `ExcludeVAT` → mặc định gồm thuế (`:97,301-305`). `Hotels` rỗng/lọc hết → SOLD_OUT (`:91-92,115-116`): một lỗi API thành "hết phòng".
- Mytour: `_WEB_SECRET` cứng (`mytour/api.py:21`); khi họ xoay → `api 3004` ghi ERROR, không BLOCKED, không pause kênh, không alert (`mytour/collector.py:255-257`). Hết `max_polls` vẫn chấp nhận kết quả dở là OK (`:265-269`).
- Agoda: `availability` coi là EXACT (`agoda/parser.py:232-235`) dù chưa xác minh Agoda có trần (thấy 64); `INITIATOR_API_KEY`, `ag-initiator-version` cứng (`agoda/urls.py:16`, `collector.py:229-230`); `CURRENCY_IDS` chỉ VND (`urls.py:17,115`).
- Trip.com: 20–90 s/probe, khoá tuần tự (`collector.py:80`, `browser.py:138`); không kiểm LOS trả về nhưng vẫn chia giá theo `nights` yêu cầu (`parser.py:189,275`); client hints cứng (`browser.py:59-70`).
- Chung: 503 luôn coi là chặn (`fetch.py:28`) → sự cố thật đốt session/proxy; quét marker chặn cả trên JSON API (iVIVU, Mytour) → mô tả khách sạn chứa "access denied" = false block; UA Playwright gửi cùng impersonate `"chrome"` chung chung (`fetch.py:64,83-87`) lệch fingerprint; `Accept-Language` cứng `en-GB`; session hết hạn không đóng client HTTP → rò 1 `AsyncSession`/lần xoay (`session.py:77-78` + `hybrid.py:71-73`, `agoda/collector.py:209-210`, `mytour/collector.py:170-172`); `ratelimit._last` lớn vô hạn (`ratelimit.py:23,32`); budget fixed-window cho burst 2× ở biên + thundering herd (`budget.py:39`); proxy không theo dõi sức khoẻ/ban, password không percent-decode (`proxy.py:61`); key MinIO không có kênh, JSON lưu `.html.gz` `text/html` (`storage.py:11-12,82`).
- Booking proxy theo nước khách sạn (`hybrid.py:78,105`) còn verify/search theo `deps.country` (`collector.py:73`) → 2 pool session, lệch point-of-sale. `BrowserCollector` mở Chromium mới mỗi probe + 1 context chỉ để đọc UA (`browser.py:49-61`), không stealth.
- `matching.py` stopword chỉ cho TP.HCM (`:9-12`), không dùng địa chỉ/sao; **không có map loại phòng chéo kênh** ở bất kỳ đâu.
- Registry: Protocol không runtime-check, không contract test (test chỉ Booking); `ImportError` trong `urls.py` kênh làm kênh biến mất im lặng (`registry.py:94-97`); `WORKER_CHANNEL=traveloka` → `ModuleNotFoundError` thô (`factory.py:46`); host Expedia `.com.vn` không nhận (`registry.py:69-72`). 4 wrapper curl riêng, 5 result builder viết tay.
- Hardcode 1 phòng, 0 trẻ em ở cả 5 kênh (`booking/urls.py:50`, `agoda/urls.py:87`, `ivivu/api.py:37-44`, `tripcom/urls.py:60`, `mytour/api.py:56-58`).
- Không test: `budget.py`, `token_minter.py` (0 test, phụ thuộc JS nội bộ `_myBotWidgetGlobal` + `SITE_KEY` cứng), Booking `verify/suggest/search_page`, Trip.com `verify/suggest/load_detail`, nhánh Mytour partial, xoay nhiều proxy.

**Thiếu so với scraper đa OTA sản xuất:** backoff mũ + jitter + Retry-After; circuit breaker theo proxy; captcha (không có, chỉ đợi WAF); fingerprint xoay (viewport 1366×850 cứng, timezone chỉ Trip.com); cảnh báo drift parser (tỷ lệ ROOMS→EMPTY tăng); đa occupancy/LOS; map loại phòng; calendar min-LOS chỉ Booking.

**Độ sâu:** Booking 4 · Agoda 4 · Mytour 3,5 · iVIVU 3 · Trip.com 3 · Traveloka/Expedia 1 · shared (fetch/session/proxy/budget/storage) 3 · proxy 2. **Trung bình 3,2.**

### 2.2 Lập lịch, hàng đợi, worker, vòng đời run

**Luồng:** `scheduler/__main__.py` một tiến trình, tick 60 s (`scheduler/service.py:297-304`) → gom mốc giờ tenant
theo phút UTC, nhìn lùi 10 phút (`planning.py:60-87`) → một run mỗi (mốc × kênh) khoá `trigger_key` duy nhất
(`repo/runs.py:29-67`) → một job `probe_hotel` mỗi khách sạn, job id cố định (`scheduler/queue.py:56-64`) →
worker: calendar → bỏ đêm đã có/đủ mới theo tầng (`worker/jobs.py:36-50,79-97`) → probe từng đêm, commit từng đêm →
`finish_job` → `try_finish_run` dưới row lock (`runs.py:133-176`) → đẩy analytics. Scheduler còn: chốt run quá 90
phút, đẩy lại job kẹt >5 phút, quét bù sau khi scheduler tắt (`planning.py:90-101`, `runs.py:232-252`), tự ngắt kênh
bị chặn, kiểm proxy 15 phút, tạo partition tháng.

**Điểm mạnh:** chống trùng 3 lớp (unique key + check-then-insert có fallback IntegrityError + arq job id); chốt run
đúng một lần; job retry/restart tiếp tục từ đêm chưa ghi (`jobs.py:136,145`, upsert `snapshots.py:107-115`); expire run
trước khi đẩy lại job kẹt (`service.py:153-155`); run thị trường có deadline riêng; test tích hợp phủ idempotency,
chốt run đồng thời, quét bù, pause kênh, retry.

**Điểm yếu (★ đã kiểm chứng)**
- ★ **Thiếu index nghiêm trọng.** `room_snapshots` chỉ có index `(hotel_id, stay_date, scanned_at)` (`db/models.py:200`),
  không migration nào thêm index `probe_id`; nhưng ghi probe (`repo/snapshots.py:150,253`), analytics nạp run
  (`analytics/service.py:138`), occupancy (`market/occupancy_service.py:86`) đều lọc theo `probe_id` không kèm
  `scanned_at` → quét mọi partition (tới 24 tháng) mỗi lần ghi. `probes` 2 index đều bắt đầu bằng `hotel_id`
  (`models.py:159-160`) nhưng block-rate check mỗi 60 s lọc `fetched_at >= since` (`runs.py:206-209`) → full scan
  mỗi tick. `scan_jobs(hotel_id)` không index (quét bù, dedupe thị trường). `listings(channel, external_id)` không
  index, không unique → check-then-act ở verify/discover (`listing_jobs.py:79-89`) có race tạo trùng.
- ★ **Probe ghi sau khi run hết hạn bị mất.** Worker không kiểm trạng thái run giữa các đêm (`worker/jobs.py:143-212`);
  tới hạn 90 phút scheduler đẩy analytics ngay (`service.py:159-162`) khi worker còn ghi; `finish_job` không có guard
  trạng thái (`runs.py:123-130`) nên lật job `failed:deadline` thành `done`; `pending_run_ids` coi run đã phân tích →
  probe muộn không bao giờ vào analytics.
- Kênh bị pause mất trọn mốc: job bị fail ngay (`worker/settings.py:145-148`) nhưng quét bù chỉ chạy sau khi scheduler
  tắt (`service.py:174`), comment nói ngược lại.
- Một tick giữ transaction mở trong khi gửi SMTP (20 s/người nhận, `ops/alerts.py:45-49`) và kiểm proxy tuần tự
  (20 s/proxy, `ops/proxy_check.py:42-43`); không `statement_timeout`/`idle_in_transaction` (`db/engine.py:10`).
- Một tenant `scan_times` hỏng (CLI `add-tenant` không validate, `cli.py:58`, không CHECK) → `ValueError` ở
  `planning.py:70` chết cả tick cho mọi tenant (API đã chặn, DB chưa).
- Đẩy lại job kẹt: 1 lệnh Redis/job/tick không pipeline (`service.py:164-166`); `QUEUE_DEPTH` thực ra là kích thước run
  vừa tạo (`service.py:257`, `ops/metrics.py:11`). Không dead-letter (arq giữ kết quả 1 giờ); arq timeout 3600 s không
  bị `except Exception` bắt (`jobs.py:213`) → job "running" tới deadline.
- Scan-now tenant không nhìn run theo lịch/`manual:all` → cùng khách sạn bị probe 2 lần (14 đêm gần không có tầng để
  đỡ). Quyền sở hữu run chỉ nằm trong chuỗi `trigger_key` (`manual:t{id}:`), `scan_runs` không có `tenant_id`.
- `enqueue_verify` không job id (`queue.py:66-69`) → bấm `retry`/`resume` nhiều lần = nhiều verify.
- **Công suất:** budget mặc định 40 req/phút/kênh; ~34 request/khách sạn/lượt (theo tầng) → **≈100 khách sạn riêng
  biệt/kênh/mốc** trong 90 phút, thêm worker không giúp. Khách sạn chỉ dùng chung giữa tenant cùng phút UTC
  (`planning.py:82-83`). Run thị trường (≤500 KS × ~20 req ≈ 10k req/khu vực/ngày ≈ 4 giờ budget Booking) dùng chung
  budget với run tenant, chỉ giữ 4 job trong hàng đợi chứ không dành riêng budget → run tenant trượt deadline khi có
  thị trường.
- Scheduler 1 tiến trình, không leader election; throttle alert trong bộ nhớ (`alerts.py:74-86`); state thị trường
  trong bộ nhớ (`marketscan/scheduling.py:110-112`). Redis không volume → mất hàng đợi/pause/budget khi recreate.

**Độ sâu:** 4/5 cho logic điều phối; 2/5 cho index/HA/vận hành. **Chung 3,5.**

### 2.3 Analytics và sự kiện

**Luồng:** `AnalyticsService.run` (`analytics/service.py:84-119`): xoá sự kiện của run → mỗi (khách sạn, đêm): upsert
`hotel_date_snapshots`, `diff_events` so với **lần quan sát dùng được gần nhất** (cửa sổ 8 ngày), upsert
`hotel_date_metrics` nếu mới hơn → pass chéo kênh `channel_closed`, `parity_gap`.

**Điểm mạnh:** `rules.py` thuần, 15 unit test; `unknown` không sinh sự kiện; probe OK mà không parse được phòng = unknown
(`service.py:160-162`); low_stock chỉ khi vào vùng và chỉ `exact`; idempotent theo run; test tích hợp pipeline 3 run,
đa kênh, parity, channel_closed.

**Điểm yếu (★ đã kiểm chứng)**
- So giá không kiểm tiền tệ ở `_price_events`, `pct_change`, `parity_gap`, `compset_by_day` (`rules.py:128-149`,
  `cross_channel.py:80`, `compset.py:127-128` lấy currency đầu tiên gặp). Kết hợp với 2.1 (Booking không reject tiền tệ)
  → sự kiện giá giả khi proxy trả trang USD.
- ★ **Một probe bị chặn xoá ô heatmap**: `compute_metrics` ghi `min_price=None`, `status=unknown` khi probe không dùng
  được (`rules.py:357-362`); `_upsert_metrics` chỉ bỏ qua khi bản cũ **mới hơn** (`service.py:362`) → giá cuối cùng
  biến mất tới lượt thành công kế; `compset_by_day` loại đối thủ đó (`compset.py:124`) → trung vị thị trường dao động
  theo block rate.
- `days_to_arrival` theo ngày UTC (`service.py:364`, `occupancy_service.py:138`): mốc 06:00 VN = 23:00 UTC hôm trước →
  lệch +1 so với mốc 14:00/22:00 cùng ngày; làm méo pickup/pace, bị dung sai 1 ngày (`pacing.py:17`) che đi.
- "24h" pickup thực tế tới 32 h (`rules.py:334`), `ref7d` có thể hàng tuần (`:343-345`); `paired_exact_pickup` coi loại
  phòng biến mất là bán hết (`:293-295`) → drift parser thổi phồng pickup.
- `channel_closed` lặp mỗi 24 h: `new_sold_out` nạp mọi sự kiện sold_out từ trước tới nay (`service.py:477-487`),
  docstring "≤12h" nhưng `FRESH_FOR=3h` (`cross_channel.py:16,36`).
- `parity_gap` so `min_price` mọi loại giá (`service.py:514-517`); `TAX_INCLUSIVE_CHANNELS` chứa mọi kênh
  (`cross_channel.py:12`) nên bộ lọc vô nghĩa → giá không hoàn huỷ rẻ trên một kênh = "parity gap".
- Sự kiện giá sinh cả mức khách sạn lẫn loại phòng; `PRIORITY_EVENTS` của insight gồm cả mức loại phòng
  (`insight/input_builder.py:37-46`) → 120/200 slot sự kiện đầy nhiễu.
- Compset: không lọc `last_observed_at` cũ (đối thủ paused/broken vẫn đóng góp giá 2 tuần tuổi); nhiều khách sạn
  `self` → `own_daily` ghi đè theo ngày (`compset.py:114`), `owns[0]` tuỳ ý (`:132`).
- `HotelDateMetric` check-then-write không `WHERE last_observed_at <= excluded` (`service.py:353-363`), jobs worker
  chạy 2 job song song (`jobs/settings.py:185`) → run cũ có thể đè run mới.
- Hiệu năng N+1: ~5 round-trip × 20 KS × 90 đêm ≈ **9.000 query/run/kênh** (`service.py:255-272,353-418`);
  `pending_run_ids` = `NOT IN (SELECT DISTINCT scan_run_id FROM hotel_date_snapshots)` (`:72-82`) chạy mỗi 30 phút
  và mỗi lần gọi `/health/summary`.

**Độ sâu:** 3,5/5.

### 2.4 Bản tin AI (insight)

**Luồng:** cron 5 phút chọn tenant qua `insight_hour`, tối đa 2 lần fail/ngày (`jobs/settings.py:87-120`) →
`build_input` (bảng 30 ngày/KS, sự kiện 24h ≤120 + 7 ngày ≤200, compset, PMS, lễ, tín hiệu cầu) → OpenRouter chat
completion với `json_schema` strict (`insight/client.py:57-66`, `schema.py`) → `validate_output` loại mục không có
bằng chứng → lưu. Theo yêu cầu: API ghi `pending`, worker gọi đồng bộ, dashboard poll 5 s.

**Điểm mạnh:** prompt có phiên bản; mọi highlight/pricing/risk phải có `evidence.ref` tồn tại trong đầu vào, mục sai
ghi `dropped_highlights` (`validation.py:37-112`); ref chỉ sinh cho ô đã quan sát; idempotent theo (tenant, ngày địa
phương); 11 kịch bản fixture; fail nhanh khi không có dữ liệu; `FakeInsightClient` khi không có key.

**Điểm yếu (★ đã kiểm chứng)**
- ★ **Chế độ batch (mặc định hằng ngày) loại nhầm bằng chứng tín hiệu cầu**: `_rebuild_from_stored` chỉ nạp ref từ
  `hotels/events_24h/events_7d/compset`, không `demand_signals` (`insight/service.py:282-294`), trong khi `build_input`
  tạo `demand:<id>` (`input_builder.py:262-263`) → mọi highlight dẫn tín hiệu cầu bị drop ở bản tin sáng. Test batch
  không có demand ref nên không phát hiện.
- Batch là giả lập: `submit_batch` chạy đồng bộ rồi cache Redis TTL 48 h (`client.py:222-228`); Redis flush/hết TTL →
  `poll_batch` trả `in_progress` mãi (`:231-234`), không có timeout cho `batch_pending` (sweep 10 phút chỉ cho
  `pending`, `routers/insights.py:53-61`). Không có chiết khấu nên lớp này chỉ thêm độ trễ và trạng thái treo.
- Không giới hạn đầu vào (không cap số KS/token; `events_24h` ⊂ `events_7d` gửi 2 lần, `input_builder.py:239-240`),
  không `max_tokens`, không timeout client (SDK mặc định 600 s × 2 retry) với `job_timeout=1800`, `max_tries=2` →
  một provider treo giữ worker tới 1 giờ.
- `raw_text` tín hiệu cầu, tên khách sạn OTA, nhãn tenant vào prompt nguyên văn (`input_builder.py:193-194,273`);
  `summary`/`recommendation` tự do không được kiểm.
- Validation chưa kiểm `evidence.kind` khớp prefix ref, `date_from ≤ date_to`, `hotel_ids` rỗng; `demand_signals`
  không cần bằng chứng. Chi phí tính theo giá cứng (`client.py:25-34`), không ngân sách/tenant, không cap on-demand/ngày.
- `/insights/generate` đồng thời → 2 dòng pending → `MultipleResultsFound` 500 ở lần sau (`routers/insights.py:62-70`).

**Độ sâu:** 3/5.

### 2.5 Thông báo email

**Luồng:** cron 5 phút `dispatch_due` (`notify/service.py:671-678`): retry → cảnh báo gom theo mốc quét (đợi mọi kênh
của mốc chốt + có analytics, ân hạn 2 h, `:332-381`) → bản tin sáng → báo cáo tuần (thứ Hai 08:00, bù thứ Ba). Outbox:
`dedupe_key` unique, insert-on-conflict, commit `sending` trước khi gửi (`:229-319`), retry giành dòng bằng UPDATE điều
kiện, backoff 5 phút/30 phút/2 giờ (`:618-669`), lỗi từng tenant cô lập (`:321-328`), tham số luật có biên
(`kinds.py:57-72`), HTML escape mọi giá trị (`render.py`), tiêu đề gộp xuống dòng.

**Điểm yếu**
- Gửi thành công một phần = `sent`, người nhận lỗi không retry (`service.py:302-307`); retry dòng `sending` treo gửi lại
  tất cả (at-least-once, chưa ghi docs).
- `_run_tenants` cảnh báo mọi tenant có khách sạn trong run bất kể ai kích hoạt (`:383-397`) → tenant A bấm "Quét ngay"
  10 phút/lần làm tenant B nhận email mỗi lần.
- `send_test` chặn request HTTP tới 20 người × 20 s (`routers/notifications.py:162`, `email_sender.py:29-30`); mỗi lần
  gửi mở kết nối SMTP mới.
- Không `List-Unsubscribe`/link huỷ (`email_sender.py:32-40`); không xác thực người nhận (bất kỳ writer thêm email lạ +
  gửi thử 1 phút/lần, `routers/notifications.py:70-93`).
- `weekly.busiest` đếm cả sự kiện giá mức loại phòng mà `counts` loại (`weekly.py:52,54`); fallback `NightMarket(1,0)`
  chỉ đúng khi `min_sold_out=1` (`alert_rules.py:117`); `fmt_money` mặc định VND khi currency None (`fmt.py:42`).
- Email còn thương hiệu "ScrapeBooking" (`SMTP_FROM` mẫu, template).

**Độ sâu:** 4/5 (phần chín nhất của backend).

### 2.6 Nhập PMS

**Luồng:** đọc CSV/XLSX → gợi ý ánh xạ theo alias VI/EN → gộp với ánh xạ đã lưu (chỉ cột có trong tệp,
`routers/pms.py:64-75`) → parse → upsert `own_hotel_daily` từng dòng (`:204-234`), chỉ khách sạn `self`.

**Điểm mạnh:** số VI/EN (dò nghìn/thập phân, `pms/csv_adapter.py:90-124`), chặn NaN/Inf, kiểm trùng ngày/sold>total/
occupancy 0–100, 13 unit test, template tải về, lỗi từng dòng hiển thị.

**Điểm yếu**
- Thứ tự decode sai cho tệp Windows tiếng Việt: thử UTF-16 **trước** cp1258 (`csv_adapter.py:185`); UTF-16 không BOM
  nhận gần như mọi chuỗi byte chẵn → header rác → "missing mapping". `latin-1` không bao giờ fail nên lỗi "cannot
  decode" (`:191-192`) không bao giờ tới.
- Không giới hạn kích thước/số dòng/số cột/số lỗi lưu: `await file.read()` toàn bộ (`routers/pms.py:149,191`),
  `_read_excel` materialize mọi dòng (`csv_adapter.py:226-230`), lỗi lưu JSONB (`pms.py:243`); XLSX bomb = OOM.
- Thiếu kiểm: số âm, `available > total`, `total ≠ sold + available`, năm 1900/2100, Excel serial date; Sniffer chỉ 4 KB.
- 1 INSERT/dòng; workbook không đóng; chỉ `csv` đăng ký, chưa adapter API nào (`pms/base.py:22`).

**Độ sâu:** 2,5/5.

### 2.7 Thị trường: ước tính công suất, nhịp, gợi ý giá, cả khu vực

**Luồng:** cron 10 phút tính `occupancy_estimates` cho run đã có snapshot mà chưa có dấu (20 run/lần,
`market/occupancy_service.py`); tồn kho = max exact/capped 30 ngày; kết quả là khoảng [thấp, cao] + độ phủ, chỉ hiện
khi phủ ≥ 0,5 và khoảng ≤ 20 điểm (`occupancy.py:16-22`). Pace so cùng thứ, cùng lễ, ≥2 đêm tham chiếu
(`pacing.py:36-59`), đối chiếu PMS. Gợi ý giá luật cố định có lý do mã hoá, ghi quyết định (`pace_report.py:210-213`).
Thị trường khu vực: round/ngày khoá dòng (`marketscan/rounds.py:58-81`), mỗi đêm một job nối đuôi, job id cố định,
chuỗi kẹt 2 h được khôi phục, run chi tiết `market:<area>:<date>` ≤500 KS, giữ 4 job trong hàng đợi.

**Điểm mạnh:** minh bạch độ tin cậy; lỗi một run không chặn hàng (`occupancy_service.py:100-106`); thị trường cô lập
từng khu vực, mã lỗi cho tenant được làm sạch (`marketscan/service.py:53-60`); test tích hợp tốt.

**Điểm yếu**
- Occupancy: exception bất kỳ ghi `rows=-1` vĩnh viễn, không alert, không retry (`market/jobs.py:22-26`); vòng lặp
  bậc hai (`occupancy_service.py:125`) + 1 INSERT/dòng + 1 query tồn kho/KS; reparse/analyze lại không tính lại
  occupancy (dấu đã có); tồn kho max 30 ngày → KS cắt allotment trông đầy hơn thật 30 ngày.
- Pace/gợi ý: `own_ids[0]` từ query không ORDER BY (`pace_report.py:231-239`) → tenant nhiều cơ sở lúc được KS này lúc
  KS kia; `price_suggestion_decisions` không có `hotel_id` (`market/models.py:70-72`); so `min_price` thay vì
  `min_refundable_price` (`pace_report.py:332`, `price_suggest.py:70`), không kiểm tiền tệ; ngưỡng cứng 97/110/120…
  (`price_suggest.py:17-19,87-126`); mỗi request nạp ~270k dòng estimate 123 ngày (`pace_report.py:245-246`), DISTINCT ON
  phải sort, không cache.
- Thị trường: hai tenant cùng thành phố quét 2 lần (unique key có `tenant_id`, `marketscan/models.py:34-36`); mọi KS
  tìm thấy thành listing `active`, `verified_at=now` không verify (`upsert.py:67-78`); chuỗi đứt sau nửa đêm không khôi
  phục (`rounds.py:145-146`); tìm KS `ilike` không escape `%`/`_`, không trigram (`city.py:247`); phủ danh sách 63%
  (234/370) vì Booking bỏ `offset`.

**Độ sâu:** occupancy 3,5 · pace/gợi ý 3,5 · khu vực 4. **Chung 3,5.**

### 2.8 API, xác thực, phân quyền, bảo mật

**Luồng:** cookie httpOnly `sb_session` (JWT HS256, 12 h, SameSite=Lax) hoặc `Authorization: Bearer` →
`get_principal` decode rồi **đọc lại** `active/role/tenant_id` từ DB mỗi request (`api/deps.py:51-73`) →
`current_tenant_id`: operator phải `?tenant_id=`, tenant user truyền tenant khác → 403 (`:95-108`) → mọi endpoint dữ
liệu lọc qua `tenant_hotels`. 70 route, 11 router. Vai trò: `operator` / `tenant_admin` (ghi) / `viewer` (đọc).

**Điểm mạnh:** cách ly tenant nhất quán, không tìm thấy endpoint nào tenant_admin đọc được tenant khác qua
`tenant_id`/path/body; khoá tài khoản/đổi role có hiệu lực ngay; không SQL thô (chỉ DDL partition nội bộ); argon2id;
CSV chống chèn công thức (`export/csv_tables.py:66-73`); HTML email escape; `run` của tenant khác bị che trigger_key;
test `test_tenant_scoping_and_roles`, `test_api_hardening`.

**Điểm yếu (★ đã kiểm chứng)**
| Mức | Phát hiện |
|---|---|
| ★ Nghiêm trọng (deploy) | `jwt_secret` mặc định `"change-me"` (`config.py:71`), không guard khởi động; `cookie_secure=False` mặc định (`:73`). Biết secret mặc định = giả token `{"sub":"1","role":"operator"}`; vì role đọc lại từ DB nên chỉ cần user 1 là operator (CLI tạo operator đầu tiên). |
| ★ Cao | Không rate-limit/lockout login (`routers/auth.py:14-35`, không limiter nào trong `api/`); argon2 chạy **đồng bộ trong handler async** (`api/auth.py:22-28`; `tenants.py:169,208` hash cũng vậy): 64 MiB/lần, chặn event loop → brute-force kiêm DoS. |
| Cao | CSRF chỉ dựa SameSite=Lax: không token, không kiểm Origin/Referer; POST không body (`/watchlist/scan-now`, `/insights/generate`, `/notifications/test`) và multipart (`/pms/import`) không cần preflight; GET `/market/areas/search` có side effect (gọi Booking qua proxy, tốn budget, `market_city.py:106-128`). Nguy hiểm khi dashboard chia domain cha với site khác. |
| Trung bình | Không thu hồi token: logout chỉ xoá cookie; đổi mật khẩu không huỷ phiên (không `jti`/token_version, `api/auth.py:47-59`); tự đổi mật khẩu không cần mật khẩu cũ (`tenants.py:207-208`) → phiên bị trộm tự làm bền. Enumeration theo thời gian (`routers/auth.py:21` short-circuit trước `verify_password`). |
| Trung bình | `Tenant.active=False` không khoá người dùng tenant đó (`routers/auth.py:21`, `deps.py:69`) → offboarding/ngừng trả tiền không chặn truy cập. |
| ★ Trung bình | **Đầu độc dữ liệu chéo tenant qua listing dùng chung**: `add_listing` bỏ qua `_ensure_sole_tracker` khi listing hiện tại là `suggested/broken/rejected` (`routers/watchlist.py:293-296`); verify không so danh tính trả về với tên/toạ độ khách sạn (`worker/listing_jobs.py:91-106`) → tenant A trỏ kênh của khách sạn chung sang cơ sở khác, thành `active` cho mọi tenant. `confirm/reject/retry` cũng không guard (chỉ pause/resume có, `:323-324`). |
| Trung bình | Không giới hạn upload (2.6); không quota: số KS/tenant, scan-now ~144 lần/ngày + per-hotel, `/insights/generate` không cap, `retry/resume` verify không dedupe. |
| Thấp–TB | `/metrics` công khai (`api/main.py:95-97`) và tới được qua proxy `/api/metrics`; `/docs`, `/openapi.json` bật; `/channels` không auth; 502 của proxy lộ `API_INTERNAL_URL`. `/healthz` trả hằng, không ping DB (`main.py:91`). |
| Thấp | `ListingOut.last_error` lộ lỗi proxy cho tenant (`schemas.py:117`); `InsightOut.error` lộ exception SDK; `CORS_ORIGINS=*` sẽ reflect origin kèm credentials (không guard); người nhận email không xác thực; `create_user` với `tenant_id` không tồn tại → 500; email unique check race. |

**Thiếu:** password reset, MFA, xác thực email, audit log, request-id, GZip/ETag/Cache-Control (overview 60 đêm × 20 KS
≈ 0,3–0,5 MB JSON mỗi lần, cùng dải `HotelDateMetric` nạp 2 lần), API versioning, quota theo gói.

**Độ sâu:** 3/5 (cách ly tốt, hardening thiếu).

### 2.9 Dashboard (Next.js 16, React 19)

**Kiến trúc:** 42/48 file `.tsx` là client component; không RSC fetch, không server action (trừ `setLocale`). Hook tự
viết `useApi` (`lib/hooks.ts:24`): fetch on mount, key `${key}#${tenantId}#${locale}#${tick}`, không AbortController,
không dedupe/cache chéo trang/retry/refetch-on-focus; `useInterval` tiếp tục poll khi tab ẩn. `useTenantToday` gọi
`/settings` ở mọi component dùng nó → 3 lần `/settings` mỗi lần mở Bảng điều khiển + waterfall. `lib/api.ts` đường dẫn
chuỗi tay, cast không validate; tenant đang chọn là biến module mutable (`:87`). Auth gate `proxy.ts` chỉ kiểm có cookie.
Proxy `/api/[...path]` chuyển tiếp mọi header, đọc cả body vào RAM không cap, không timeout, lộ URL nội bộ khi lỗi,
**proxy mọi path**. Types sinh từ OpenAPI (57 path, tất cả đều được dùng) nhưng CI không kiểm drift `api-types.ts`.

**Điểm mạnh:** ~20 route phủ đủ 8 tab OTARadar; i18n next-intl khoá có kiểu, vi/en đủ 1.793 khoá, lỗi API dịch bằng
rule (`lib/errors.ts`), `i18n-check` bắt ICU; state trong URL ở Sự kiện/Cài đặt/Phòng trống; empty/loading/error nhất
quán; `canWrite` ẩn nút ghi; a11y popover/`aria-*`/`role=alert` tốt; Dockerfile multi-stage non-root standalone.

**Điểm yếu (★ đã kiểm chứng)**
- ★ **0 test FE** (không vitest/playwright config, không `*.test.*`).
- ★ **Không security header**: `next.config.ts` không `headers()` → không CSP, X-Frame-Options, HSTS, Referrer-Policy.
- ★ `safeNext` (`login/page.tsx:12-14`) chặn `//` nhưng không chặn `/\evil.com` (trình duyệt chuẩn hoá `\`→`/`) → ứng
  viên open redirect; sửa rẻ.
- ★ Proxy lộ `/api/metrics`, `/api/docs`, `/api/openapi.json` ra công khai; không forward `X-Forwarded-For/Proto` → backend
  không biết IP thật (rate-limit theo IP sau này cần sửa proxy).
- Múi giờ không nhất quán: `useTenantToday` theo tenant nhưng `useDateRange` (`components/date-range.tsx:15`),
  `today/page.tsx:45`, `fmtWhen/fmtDateTime/fmtTime` (`lib/format.ts:236,267-272`) theo trình duyệt; `i18n/request.ts:18`
  ghim `Asia/Ho_Chi_Minh` → operator ngoài VN thấy "đêm nay" sai.
- N+1: Terminal+ gọi `GET /hotels/{id}` cho **mỗi** khách sạn chỉ để lấy `demand_signals` (`terminal/page.tsx:49-61`);
  pace fetch 2 lần; chi tiết bản tin nạp `events?limit=2000` để gắn nhãn bằng chứng (`insights/[id]/page.tsx:26`).
- Render nặng: `Board` giữ hover state ở root và rebuild `ctx` mỗi render (`overview/board.tsx:52,58`) → mỗi
  `onMouseEnter` re-render mọi thẻ × mọi đêm; không `React.memo` nào trong `src/`; heatmap `cellAt` linear `.find`
  mỗi ô (`availability/heatmap-table.tsx:82,128`); bảng lịch sử không phân trang/ảo hoá.
- File >500 dòng: `board.tsx` 735 (nằm trong `overview/` chỉ còn redirect, chỉ `hotels/[id]` import), `components/ui.tsx`
  670, `hotels/[id]/dates/[date]/page.tsx` 616, `watchlist-tab.tsx` 588, `pms-tab.tsx` 532, `landing.css` 2.247.
- Trùng lặp: helper cập nhật URL param 5 nơi, fallback city 404 2 nơi, `marketMood` 2 nơi, `StatBox/IntelBox` 2 nơi, 2
  hệ chart (recharts + SVG tay); 123 mã hex ngoài design token; `"VND"`, `"Booking.com"` cứng.
- UX: id/date sai → skeleton xoay mãi (không `notFound()`); tạm dừng/xoá khách sạn, "Quét tất cả" không confirm;
  `Segmented`/`Tabs` không điều hướng phím mũi tên; poll bản tin: list dừng ở `status !== "pending"` nhưng detail coi
  `batch_pending` là pending; chuông "mới 24h" đóng băng lúc mount (`app-shell.tsx:164`); `/today` trùng `/dashboard`;
  runs cố định 100 không phân trang; users-tab nạp mọi user rồi lọc ở client.
- `(marketing)/layout.tsx:26`, `(app)/layout.tsx:16` chèn ghi chú thiết kế nội bộ bằng `dangerouslySetInnerHTML` (tĩnh,
  không XSS, nhưng ship ra mọi khách). `NEXT_PUBLIC_API_URL` build arg không dùng.

**Độ sâu:** 3/5 (rộng và đa ngữ tốt; engineering hardening yếu).

### 2.10 Hạ tầng, CI/CD, vận hành

**Hiện trạng:** compose một máy: postgres, redis, minio, migrate, scheduler, 5 worker theo kênh, jobs, api, dashboard;
monitoring tách file (Prometheus + Grafana, 1 dashboard collector); collector từ xa có file riêng. CI: backend ruff +
mypy + pytest (Postgres/Redis/MinIO service), dashboard lint + typecheck + build.

**Điểm yếu (★ đã kiểm chứng)**
- ★ Mật khẩu mặc định cứng trong compose: Postgres `app/app`, MinIO `minioadmin`, Grafana `admin/admin`; **mọi cổng
  publish ra host**: 5432, 6379 (Redis không auth), 9000/9001, 8000 (bỏ qua dashboard), 3000, 9090, 3001.
- ★ Không reverse proxy/TLS; `COOKIE_SECURE=false` mẫu. Secrets qua `.env` phẳng.
- ★ `infra/Dockerfile.backend` một stage, **chạy root**, `uv:latest` không pin, cài Chromium + deps vào image dùng chung
  cho api/scheduler/jobs; không `HEALTHCHECK`; **không `.dockerignore` gốc** trong khi build context là `..` → gửi cả
  `.git`, `.env`, `dashboard/node_modules`, `backend/.venv` cho daemon.
- Postgres/Redis/MinIO không `restart`; Redis không volume/AOF (mất hàng đợi, pause, budget); api/dashboard/scheduler/
  worker/jobs không healthcheck; `dashboard depends_on: [api]` không điều kiện; resource limit chỉ cho collector.
- Log json-file không rotate, không gom; cảnh báo vận hành = `grep ops_alert`; Prometheus không `rule_files`, không
  Alertmanager; image `latest` không pin; collector từ xa không được scrape; Redis/Postgres/MinIO qua mạng không TLS.
- Backup: `pg_dump` giữ toàn bộ trong RAM rồi `gzip.compress` chặn event loop (`ops/backup.py:46,76`), bị `job_timeout`
  1800 s giết khi DB lớn; lên MinIO **cùng máy**; không WAL/PITR; chưa từng test restore. Partition: không DEFAULT,
  chỉ scheduler tạo trước 3 tháng; drop partition khoá exclusive bảng cha.
- `scrape_sessions.status` String(16) nhưng ghi `retired:{reason}` (`retired:blocked` = 15 ký tự) → reason dài hơn sẽ làm
  probe fail (`worker/session_listener.py:19-48`).
- CI: không chạy `i18n:check`, không kiểm drift `api-types.ts`, không build/scan image, không deploy, không FE/e2e test,
  không `permissions:`/`concurrency:`, action pin theo tag; cài lại Playwright mỗi run không cache.
- Retention: `probes`, `hotel_calendars`, `hotel_date_snapshots`, `availability_events`, `occupancy_estimates`,
  `listing_demand_signals`, `scrape_sessions`, `scan_jobs` không partition, không prune (100 KS × 5 kênh × 3 lượt ≈
  135k probe + 135k calendar/ngày ≈ 50M dòng/năm mỗi bảng).

**Độ sâu:** 2/5.

### 2.11 Dữ liệu và schema

- Thiếu index/unique (2.2). Thiếu index FK: `room_snapshots.room_type_id`, `hotel_calendars.scan_run_id`,
  `hotel_date_metrics.as_of_scan_run_id`, `occupancy_estimates.scan_run_id`, `listing_demand_signals.scan_run_id`.
  `listing_demand_signals` xoá theo (run, hotel, channel, kind, date) nhưng index là `(hotel_id, channel, observed_at)`
  (`repo/snapshots.py:198-208`); `availability_events` 2 query `max(observed_at)`/đêm (~180 query/KS/run).
- Cột trạng thái/role/kênh là text tự do không CHECK (`models.py:88,133,149,172,100,324`); `tenants.scan_times`,
  `horizon_days` không CHECK (trong khi `market_areas` có); không ràng buộc chống 2 insight daily/ngày.
- Không RLS; cách ly tenant hoàn toàn ở tầng ứng dụng (thiết kế: hotels/listings/probes/snapshots dùng chung).
- Soft-delete chỉ là `active`/status; không `deleted_at`, không audit (chỉ `decided_by`, `created_by`).
- Drift: `ix_hotel_date_snapshots_run` có ở migration 0002 nhưng không có trong `models.py`; `alembic/env.py:10` chỉ import
  `app.db.models` → autogenerate sẽ đề nghị **drop** các bảng market/marketscan.
- Lễ tĩnh: VN tới 2027-09-02, TH/SG/US/GB chỉ tới 2027-01-01 (`holidays/data.py:45-116`) → hết dữ liệu trong ~3 tháng
  cho tenant không phải VN; âm lịch nhập tay.

**Độ sâu:** 2,5/5.

## 3. Bảng tổng hợp

| Luồng | Độ sâu | Mạnh nhất | Yếu nhất |
|---|---|---|---|
| Collector 5 kênh | 3,2 | Booking/Agoda parser có fixture thật, soft-block, calendar min-LOS | Giá Booking đa đêm; soft-block → broken; iVIVU bỏ số phòng; secret kênh cứng |
| Lập lịch/worker | 3,5 | Idempotent 3 lớp, chốt run một lần, quét bù | Thiếu index hot path; probe muộn mất; pause mất mốc |
| Analytics | 3,5 | Rule thuần có test, so "lần dùng được gần nhất" | Probe chặn xoá ô; không kiểm tiền tệ; UTC off-by-one; parity sai cơ sở |
| Bản tin AI | 3 | Bằng chứng bắt buộc, prompt có phiên bản | Batch giả lập drop demand ref, treo vô hạn; không cap token/timeout |
| Email | 4 | Outbox + retry nguyên tử + gom theo mốc | Gửi chéo tenant khi scan-now; partial = sent |
| PMS | 2,5 | Ánh xạ VI/EN, lỗi từng dòng | Decode sai cp1258; không giới hạn; thiếu kiểm miền |
| Thị trường | 3,5 | Khoảng tin cậy trung thực; chuỗi job bền | Tenant nhiều KS; so sai cơ sở giá; budget chung với run tenant |
| API/bảo mật | 3 | Cách ly tenant chặt, khoá tức thì | Secret mặc định; không rate-limit; CSRF; listing chung bị đầu độc |
| Dashboard | 3 | 8 tab đủ, i18n chuẩn, state URL | 0 test; no CSP; TZ lệch; N+1; render nặng |
| Hạ tầng/CI | 2 | Compose tách worker theo kênh; CI lint+type+test | Mật khẩu mặc định + cổng mở; không TLS; root image; backup cùng máy; CI đỏ |
| Schema | 2,5 | Partition snapshot; unique đúng chỗ | Thiếu index; không retention; không CHECK; env.py thiếu model |
| Docs/quy trình | 2 (hygiene) / 4 (nội dung) | Docs trung thực, chi tiết | Commit "123"; .claude 17 MB; rules Laravel sai stack; scripts hỏng |

**Trung bình: 3,0/5.** Lõi dữ liệu và nghiệp vụ ở mức 3,5; vỏ (bảo mật vận hành, hạ tầng, test FE, hygiene) ở mức 2.

## 4. Câu hỏi chưa giải quyết (cần người dùng trả lời để chốt plan)

1. Booking: xác nhận trang khách sạn khi `nights>1` hiện tổng kỳ (cần 1 fixture 2 đêm từ proxy thật). Proxy theo nước
   khách sạn là chủ ý (point-of-sale theo điểm đến) hay nên theo `deps.country` như 4 kênh kia?
2. Agoda `availability` có trần không (thấy 64)? Nếu có, EXACT phải thành CAPPED.
3. Dashboard có chạy trên domain cha dùng chung với site khác không (quyết định mức khẩn CSRF)? Operator có làm việc
   ngoài múi giờ VN không?
4. Mục tiêu triển khai: VPS đơn (hardening compose) hay k8s? Nhà cung cấp proxy/SMTP/offsite backup đã chọn chưa?
5. Có giữ `.claude/` (17 MB ClaudeKit) trong repo không? Có giữ `/today` song song `/dashboard` không?
6. Tư vấn pháp lý ToS đã có chưa (điều kiện trước khi bán, theo `docs/operations.md` mục 12)?
7. Tenant có nhiều khách sạn `self` (chuỗi) có trong phạm vi không? Nếu có, pace/gợi ý/compset phải sửa theo `hotel_id`.
8. Ngân sách proxy/tháng và giá bán dự kiến: quyết định số kênh × tần suất × thị trường khu vực khả thi.
