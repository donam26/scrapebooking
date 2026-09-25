# Thiết kế hệ thống theo dõi đối thủ khách sạn qua Booking.com

Ngày: 2026-09-24
Trạng thái: chờ duyệt
Nghiên cứu nền: `docs/research/2026-09-24-booking-scraping-research.md`

## 1. Mục tiêu

Dịch vụ do một operator vận hành cho nhiều khách sạn khách hàng (tenant). Với mỗi tenant,
hệ thống quét trang Booking.com của các khách sạn đối thủ và của chính khách hàng 3 lần
mỗi ngày, lưu snapshot số phòng còn lại và giá theo từng ngày lưu trú trong 30 ngày tới,
tính biến động giữa các lần quét, và dùng GPT-6 Luna sinh insight hằng ngày. Tất cả hiển
thị trên một dashboard web. Dữ liệu occupancy thật của khách hàng được nạp từ PMS để so sánh.

Tiêu chí thành công của bản đầu:
- Snapshot đổ về đúng lịch cho mọi khách sạn trong watchlist, tỷ lệ probe thành công trên 90%
  mỗi đợt quét.
- Sự kiện hết phòng, có phòng lại, giảm phòng, đổi giá được phát hiện đúng giữa hai đợt quét.
- Insight hằng ngày chỉ nêu điều có bằng chứng trong dữ liệu, mọi điểm nổi bật bấm được
  tới số liệu gốc.
- Thêm một tenant mới hoặc một khách sạn mới chỉ cần thao tác trên dashboard, không sửa code.

## 2. Các quyết định đã chốt

| Trục | Quyết định |
|---|---|
| Mô hình triển khai | Operator vận hành cho nhiều tenant, mỗi tenant có watchlist riêng. Chưa self-serve, chưa billing. |
| Scraper | Tự viết. Cơ chế session lai: Playwright giải challenge, HTTP client giả lập Chrome tải trang. |
| Ngôn ngữ | Python cho scraper, analytics, AI, API. TypeScript cho dashboard. |
| Horizon | 30 ngày chi tiết theo loại phòng, cấu hình được theo tenant. |
| Quy mô năm đầu | Vài chục tenant, 100 đến 300 khách sạn đối thủ duy nhất, 10.000 đến 27.000 probe mỗi ngày. |
| Hạ tầng | Docker Compose trên VPS, thêm máy worker khi cần. |
| Dữ liệu khách hàng | Tích hợp PMS. Adapter đầu tiên là import CSV/Excel. Adapter API cho ezCloud, Newway, Hotel Link, Smile làm khi được cấp quyền. |
| AI | OpenAI `gpt-6-luna`, Responses API, Structured Outputs, Batch API cho chạy hằng ngày. |

## 3. Ràng buộc từ nguồn dữ liệu

- Booking.com hiển thị số phòng còn lại theo **loại phòng** cho **một kỳ lưu trú**, không có
  số chung cho khách sạn. Muốn có số theo ngày phải probe từng ngày.
- Số phòng bị kiểm duyệt: chỉ có con số chính xác khi tồn kho thấp qua badge "Only X rooms
  left". Khi nhiều phòng, chỉ biết "ít nhất N" qua giới hạn của dropdown chọn số phòng.
- Ràng buộc số đêm tối thiểu làm probe 1 đêm trông như hết phòng dù không phải. Phải đọc
  calendar để biết số đêm tối thiểu trước khi probe.
- Anti-bot: AWS WAF Bot Control, fingerprint trình duyệt, chặn IP datacenter ở mọi endpoint.
  Bắt buộc residential proxy và session đã vượt challenge.
- Giá và thuế hiển thị đổi theo nước của IP. Cố định nước proxy theo nước của khách sạn.
- Pháp lý: scrape trang công khai nhìn chung không bị luật cấm nhưng vi phạm điều khoản của
  Booking.com. Không đăng nhập, không lấy dữ liệu cá nhân, chỉ lấy trường cần, giữ nhịp độ
  lịch sự. Cần tư vấn pháp lý trước khi bán cho khách hàng.

## 4. Kiến trúc tổng thể

Một repo, hai code base: `backend/` là một package Python với nhiều entrypoint, `dashboard/`
là ứng dụng Next.js.

Tiến trình chạy:

| Tiến trình | Việc làm | Đọc | Ghi |
|---|---|---|---|
| scheduler | Chạy ở mọi mốc giờ quét của bất kỳ tenant nào. Mỗi mốc tạo một scan run gồm khách sạn duy nhất của các tenant có mốc giờ đó, horizon của mỗi khách sạn là horizon lớn nhất trong các tenant đang theo dõi nó. | tenants, tenant_hotels | scan_runs, hàng đợi |
| collector worker | Lấy job, lấy calendar, probe trang theo ngày, parse, lưu HTML thô vào MinIO, ghi snapshot. | hàng đợi | probes, hotel_calendars, room_types, room_snapshots, MinIO |
| analytics job | Khi scan run chốt: gộp, so đợt trước, sinh sự kiện, cập nhật chỉ số. | room_snapshots | hotel_date_snapshots, availability_events, hotel_date_metrics |
| insight job | Hằng ngày theo tenant và theo yêu cầu: gom JSON, gọi GPT-6 Luna, kiểm tra bằng chứng, lưu. | metrics, events, own_hotel_daily | insights |
| api | FastAPI phục vụ dashboard, nhận import PMS. | mọi bảng qua lọc tenant | tenants, users, tenant_hotels, own_hotel_daily, pms_imports |
| dashboard | Next.js gọi API. | | |

Hạ tầng trong Compose: Postgres, Redis, MinIO, Prometheus, Grafana. Hàng đợi dùng `arq`
vì chạy asyncio, hợp với Playwright async và HTTP client async.

Luồng dữ liệu một chiều: scheduler tạo job, worker ghi snapshot, analytics tính biến động,
insight gọi AI, API cấp cho dashboard. Mỗi bước chỉ đọc bảng của bước trước và ghi bảng
của mình, có thể chạy lại độc lập.

Cấu trúc thư mục dự kiến:

```
backend/
  app/
    config.py            # pydantic-settings
    db/                  # SQLAlchemy models, Alembic migrations
    domain/              # dataclass/pydantic cho ProbeResult, RoomOffer, Event...
    collector/
      base.py            # interface Collector
      booking/
        session.py       # SessionManager: Playwright + proxy + cookie
        http.py          # curl_cffi fetch
        calendar.py      # lấy calendar 30 ngày
        parser.py        # parse HTML -> RoomOffer, có PARSER_VERSION
        hybrid.py        # provider chính
        browser.py       # provider dự phòng
      storage.py         # ghi/đọc HTML thô MinIO
    scheduler/
    analytics/
    insight/
      schema.py          # JSON schema đầu ra
      prompt.py          # prompt có phiên bản
      client.py          # OpenAI Responses + Batch
    pms/
      base.py            # interface PmsAdapter
      csv_adapter.py
    api/
      routers/
      auth/
    holidays/            # bảng ngày lễ tĩnh theo nước
  tests/
    fixtures/html/       # trang Booking thật đã lưu
dashboard/
infra/
  docker-compose.yml
  docker-compose.collector.yml
  docker-compose.monitoring.yml
docs/
```

## 5. Mô hình dữ liệu

Nguyên tắc: dữ liệu thu thập dùng chung toàn hệ thống, quyền xem theo tenant. API luôn
lọc qua `tenant_hotels`.

### 5.1 Bảng theo tenant

- `tenants`: id, name, timezone, scan_times (mảng giờ trong ngày, mặc định 06:00, 14:00, 22:00),
  horizon_days (mặc định 30), insight_language (mặc định `vi`),
  insight_hour, country_code, created_at.
- `users`: id, tenant_id (null nếu operator), email, password_hash, role (`operator`,
  `tenant_admin`, `viewer`), created_at.
- `tenant_hotels`: tenant_id, hotel_id, role (`self`, `competitor`), label, active, added_at.
  Khoá chính (tenant_id, hotel_id).
- `own_hotel_daily`: tenant_id, hotel_id, stay_date, rooms_total, rooms_sold, rooms_available,
  occupancy_pct, adr, revenue, source (`csv`, `api`), imported_at. Khoá (tenant_id, hotel_id,
  stay_date).
- `pms_imports`: id, tenant_id, filename, adapter, row_count, ok_count, errors (jsonb),
  status, created_at.
- `insights`: id, tenant_id, period_start, period_end, generated_at, trigger (`daily`,
  `on_demand`), model, prompt_version, input_json, output_json, dropped_highlights (jsonb),
  tokens_in, tokens_out, cost_usd.

### 5.2 Bảng dùng chung

- `hotels`: id, booking_url, booking_slug, booking_hotel_id, name, city, country_code,
  star_rating, created_at. Unique theo booking_slug.
- `room_types`: id, hotel_id, booking_room_id, name, max_occupancy, first_seen_at,
  last_seen_at. Unique (hotel_id, booking_room_id).
- `scan_runs`: id, scheduled_at, started_at, finished_at, status (`running`, `completed`,
  `partial`, `failed`), total_jobs, ok_count, sold_out_count, blocked_count, error_count.
- `probes`: id, scan_run_id, hotel_id, stay_date, checkin, checkout, nights, adults,
  status (`ok`, `sold_out`, `no_rooms_1n`, `blocked`, `error`, `skipped_calendar`),
  method (`http`, `browser`, `calendar`), proxy_country, session_id, http_status,
  raw_object_key, parser_version, error, fetched_at, duration_ms.
  Unique (scan_run_id, hotel_id, stay_date).
- `hotel_calendars`: hotel_id, scan_run_id, stay_date, available (bool),
  min_length_of_stay, avg_price, fetched_at.
- `room_snapshots`: id, probe_id, hotel_id, room_type_id, stay_date, scanned_at,
  rooms_left (int, null nếu không suy ra được), stock_confidence (`exact`, `capped`,
  `hidden`, `sold_out`), badge_count (int null), dropdown_max (int null), min_price,
  min_refundable_price, currency, rates (jsonb: mảng rate plan gồm tên, giá, hoàn huỷ,
  bữa sáng). Phân vùng theo tháng của scanned_at.
- `hotel_date_snapshots`: hotel_id, stay_date, scan_run_id, scanned_at,
  status (`available`, `sold_out`, `unknown`), exact_rooms_left (tổng rooms_left của các
  loại phòng `exact`), room_types_available, room_types_sold_out, min_price, currency.
  Khoá (hotel_id, stay_date, scan_run_id).
- `availability_events`: id, hotel_id, room_type_id (null nếu mức khách sạn), stay_date,
  event_type (`sold_out`, `restock`, `rooms_decrease`, `rooms_increase`, `low_stock_enter`,
  `price_up`, `price_down`, `room_type_new`, `room_type_gone`), from_value, to_value,
  delta, confidence, previous_scan_run_id, scan_run_id, observed_at.
- `hotel_date_metrics`: hotel_id, stay_date, as_of_scan_run_id, days_to_arrival,
  pickup_24h, velocity_3d, sold_out_at, restocked_at, min_price, price_change_7d_pct,
  availability_status, exact_share (tỷ lệ quan sát `exact` trong 7 ngày), last_observed_at.
  Khoá (hotel_id, stay_date).
- `scrape_sessions`: id, worker_id, proxy_id, proxy_country, created_at, expires_at,
  request_count, block_count, status.

### 5.3 Ngữ nghĩa rooms_left

| stock_confidence | Điều kiện | rooms_left nghĩa là |
|---|---|---|
| `exact` | Có badge "Only X rooms left" | Đúng X |
| `capped` | Không badge, dropdown chạm trần trang | Ít nhất bằng dropdown_max |
| `hidden` | Không badge, dropdown chưa chạm trần, không tín hiệu khác | null, chỉ biết còn phòng |
| `sold_out` | Loại phòng không xuất hiện hoặc đánh dấu hết | 0 |

Phép tính pickup và velocity chỉ dùng cặp snapshot cùng `exact`. Mọi thứ khác dùng chuyển
trạng thái.

### 5.4 Lưu trữ

HTML thô trong MinIO giữ 30 ngày. `room_snapshots` giữ 24 tháng. Sự kiện và chỉ số giữ
vô hạn. Ở 300 khách sạn: khoảng 108.000 dòng room_snapshots mỗi ngày.

## 6. Collector

### 6.1 Interface

```python
class Collector(Protocol):
    async def fetch_calendar(self, hotel: Hotel, start: date, days: int) -> CalendarResult: ...
    async def probe(self, hotel: Hotel, checkin: date, nights: int, adults: int) -> ProbeResult: ...
```

`ProbeResult` gồm status, method, danh sách `RoomOffer` (booking_room_id, name,
max_occupancy, badge_count, dropdown_max, rates), raw_html, http_status, session_id,
duration_ms. Suy ra rooms_left và stock_confidence là việc của một hàm thuần trong
`domain/`, có test riêng.

Provider chính `HybridCollector`. Provider dự phòng `BrowserCollector` render toàn phần
bằng Playwright, dùng cho từng probe bị chặn.

### 6.2 SessionManager

- Mỗi worker giữ một session: IP residential sticky, cookie, user agent, client hints lấy
  từ Playwright sau khi mở trang Booking và vượt challenge AWS WAF.
- Session hết hạn theo thời gian (mặc định 20 phút) hoặc số request (mặc định 400), hoặc
  ngay khi bị chặn. Làm mới bằng IP mới.
- Nước proxy theo `hotels.country_code`. Nhà cung cấp proxy cấu hình qua biến môi trường,
  interface `ProxyProvider` để đổi nhà cung cấp.

### 6.3 Tải trang và phát hiện chặn

- `curl_cffi` với `impersonate` Chrome mới nhất, HTTP/2, header và cookie của session.
- URL trang khách sạn kèm checkin, checkout, group_adults=2, no_rooms=1, selected_currency
  cố định theo tiền tệ của nước khách sạn. Bản đầu hiển thị giá đúng tiền tệ đã lưu, không
  quy đổi.
- Probe với 2 người lớn nên loại phòng chỉ dành cho 1 người sẽ không xuất hiện. Chấp nhận
  giới hạn này ở bản đầu.
- Bị chặn khi: HTTP 403 hoặc 429, HTTP 202 kèm trang challenge, có dấu hiệu captcha, hoặc
  HTML không có bảng phòng trong khi calendar nói còn phòng.
- Khi bị chặn: thu hồi session, chuyển probe sang `BrowserCollector`, tối đa 2 lần thử
  lại với backoff. Vẫn thất bại thì probe ghi `blocked`.

### 6.4 Calendar trước, probe sau

Đầu mỗi đợt quét cho một khách sạn, worker gọi `fetch_calendar` 30 ngày qua cùng session,
1 request. Từ calendar:
- Ngày `available = false` ghi probe `skipped_calendar`, không tải trang. Analytics sẽ
  suy ra trạng thái `sold_out` cho ngày đó từ probe này.
- Ngày có `min_length_of_stay > 1` probe với đúng số đêm đó.
- Calendar thất bại: probe đủ 30 ngày với 1 đêm, kết quả không phòng ghi `no_rooms_1n`,
  analytics coi là `unknown` chứ không phải `sold_out`.

### 6.5 Parser

- Ưu tiên JSON nhúng trong HTML, dự phòng DOM selector.
- `PARSER_VERSION` ghi vào mỗi probe. Fixture HTML thật lưu trong `tests/fixtures/html/`.
- Lệnh `reparse --since 30d` đọc lại HTML từ MinIO và ghi đè snapshot khi parser đổi.

### 6.6 Nhịp độ và idempotent

- Mỗi khách sạn tối đa 1 request đồng thời. Mỗi IP tối đa 1 request mỗi 2 giây có jitter.
- Job có khoá (scan_run_id, hotel_id, stay_date). Chạy lại không tạo trùng.
- Đợt quét có hạn chót 90 phút, quá hạn chốt `partial`, ghi nhận job thiếu.
- Ước tính 300 khách sạn: khoảng 9.300 request mỗi đợt, 8 worker xong dưới 1 giờ.

### 6.7 Sức khoẻ

Prometheus: probe theo status, độ trễ, block rate theo proxy, tuổi session. Cảnh báo
(log `ops_alert`) khi block rate vượt 20% trong 15 phút hoặc đợt quét dưới 90% thành công.

## 7. Analytics

Chạy khi scan run chốt, idempotent theo scan_run_id.

1. Gộp `room_snapshots` thành `hotel_date_snapshots`. Trạng thái theo probe: `ok` là
   `available`, `sold_out` và `skipped_calendar` là `sold_out`, còn `no_rooms_1n`, `blocked`,
   `error` là `unknown`.
2. So với **lần quan sát dùng được gần nhất** cùng (hotel, room_type, stay_date), tức
   probe gần nhất có trạng thái `available` hoặc `sold_out`, không phải đơn thuần đợt liền
   trước. Sinh `availability_events`:
   - `sold_out`: còn sang hết. `restock`: hết sang còn.
   - `rooms_decrease`, `rooms_increase`: cả hai `exact`, delta khác 0.
   - `low_stock_enter`: hiện tại `exact` và rooms_left từ 3 trở xuống, còn lần quan sát
     trước không thoả điều kiện đó.
   - `price_up`, `price_down`: min_price đổi từ 3% trở lên.
   - `room_type_new`, `room_type_gone`.
   - Probe `blocked`, `error`, `unknown`: không sinh sự kiện.
   Ngưỡng 3 phòng và 3% cấu hình được.
3. Cập nhật `hotel_date_metrics`.
4. Chỉ số compset theo tenant tính tại chỗ bằng hàm dùng chung cho API và insight job:
   giá thấp nhất và trung vị của đối thủ theo ngày, tỷ lệ đối thủ hết phòng, so với
   occupancy từ `own_hotel_daily`.

## 8. AI insight

- Chạy hằng ngày lúc `insight_hour` của tenant (mặc định 07:30, sau mốc quét 06:00) trên
  scan run đã chốt gần nhất, và theo yêu cầu từ dashboard.
- Đầu vào là JSON gọn: bảng 30 ngày, mỗi đối thủ có trạng thái, rooms_left kèm mức tin cậy,
  min_price, price_change_7d_pct, sold_out_at; khách sạn của khách hàng cùng dữ liệu cộng
  occupancy PMS; sự kiện nổi bật 24 giờ và 7 ngày; chỉ số compset; ngày lễ theo nước.
- Không đưa HTML thô. Không để AI tự tính delta.
- Đầu ra Structured Outputs theo schema:

```json
{
  "summary": "string",
  "highlights": [{
    "title": "string", "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD",
    "hotel_ids": [1], "evidence": [{"kind": "event|metric", "ref": "string"}],
    "confidence": "high|medium|low", "recommendation": "string"
  }],
  "demand_signals": [{"date": "YYYY-MM-DD", "level": "high|medium|low", "reason": "string"}],
  "pricing_opportunities": [{"date_from": "", "date_to": "", "rationale": "", "evidence": []}],
  "risks": [{"title": "", "rationale": "", "evidence": []}],
  "data_quality_note": "string"
}
```

- Sau khi nhận: kiểm tra mọi `evidence.ref` tồn tại trong đầu vào, loại highlight nào không
  hợp lệ và ghi vào `dropped_highlights`.
- Gọi: Responses API, model `gpt-6-luna`, reasoning effort medium, prompt hệ thống cố định
  để prompt caching, ngôn ngữ theo `insight_language`. Chạy hằng ngày qua Batch API, theo
  yêu cầu thì gọi đồng bộ.
- Chi phí ước tính mỗi tenant mỗi ngày: 20.000 token vào, 2.000 token ra, dưới 1 cent.
- Kiểm thử: 10 kịch bản fixture với kỳ vọng xác định. Prompt có phiên bản, đổi thì chạy
  lại bộ kịch bản.

## 9. API và dashboard

### 9.1 API

FastAPI, OpenAPI, dashboard sinh TypeScript client từ OpenAPI. JWT trong cookie httpOnly,
argon2. Vai trò `operator`, `tenant_admin`, `viewer`. Mọi endpoint dữ liệu lấy tenant từ
token và lọc qua `tenant_hotels`.

Nhóm endpoint: auth, tenants (operator), users, watchlist, snapshots, metrics, events,
insights, pms imports, health (operator).

### 9.2 Dashboard

Next.js App Router, TypeScript. Sáu màn hình cho tenant:

1. Tổng quan: heatmap khách sạn × 30 ngày, khách sạn của khách hàng ở trên cùng.
2. Chi tiết ngày: từng loại phòng của từng đối thủ, lịch sử rooms_left và giá.
3. Chi tiết khách sạn: dòng thời gian sự kiện, chỉ số theo ngày.
4. Insight: bản tin hằng ngày, điểm nổi bật bấm tới bằng chứng.
5. Sự kiện: lọc theo loại, khách sạn, ngày.
6. Cài đặt: thêm khách sạn bằng URL Booking, giờ quét, import PMS có template và lỗi từng dòng.

Màn hình operator: tenant, người dùng, sức khoẻ scraper, liên kết Grafana.

Thiết kế giao diện chi tiết làm ở giai đoạn 2, có thể dùng mockup khi đó.

## 10. Import PMS

Interface `PmsAdapter` với `parse(source) -> list[OwnHotelDailyRow]` và
`validate(rows) -> list[RowError]`. Adapter đầu tiên `CsvAdapter` đọc CSV và Excel theo
template: stay_date, rooms_total, rooms_sold, rooms_available, adr, revenue. Giao diện có
bước ánh xạ cột để khớp file xuất từ ezCloud hay Newway, lưu ánh xạ theo tenant. Upsert theo
(tenant_id, hotel_id, stay_date). Adapter API sau này chạy theo lịch, cùng interface.

## 11. Vận hành

- Compose ba profile: `core`, `collector`, `monitoring`. Worker collector scale bằng
  `--scale` hoặc chạy trên máy khác với `docker-compose.collector.yml` trỏ về Redis,
  Postgres, MinIO trung tâm.
- Alembic migration. Cấu hình pydantic-settings từ biến môi trường. Log JSON.
- Backup Postgres hằng đêm lên MinIO, giữ 14 bản.
- CI: ruff, mypy, pytest cho backend; lint, typecheck, build cho dashboard.

## 12. Kiểm thử

- Unit: parser trên fixture, hàm suy ra rooms_left, quy tắc sinh sự kiện, tính chỉ số,
  kiểm tra bằng chứng insight, CsvAdapter.
- Contract: Collector và PmsAdapter với provider giả.
- Tích hợp: scheduler → worker giả → analytics trên Postgres thật trong CI.
- Live: 1 probe thật lên Booking, chạy tay hoặc theo lịch đêm, không trong CI.
- Insight: bộ 10 kịch bản với kỳ vọng xác định.

## 13. Lộ trình

| Giai đoạn | Nội dung | Kết quả |
|---|---|---|
| 1 | Nền tảng và Collector: repo, schema, scheduler, worker, session, parser, MinIO, health | Snapshot đổ về 3 lần mỗi ngày cho vài khách sạn thật trong nhiều ngày liên tục |
| 2 | Analytics, API cơ bản, heatmap tối thiểu | Sự kiện và chỉ số đúng, xem được trên web |
| 3 | AI insight và màn hình insight | Bản tin hằng ngày có bằng chứng |
| 4 | Import PMS, so sánh compset | Occupancy thật đặt cạnh đối thủ |
| 5 | Quản trị tenant, cảnh báo, backup, tài liệu vận hành, onboard khách đầu tiên | Chạy dịch vụ |

Mỗi giai đoạn có kế hoạch triển khai riêng. Kế hoạch đầu tiên chỉ bao gồm giai đoạn 1.
Giai đoạn 1 phải chạy thật vài ngày trước khi bắt đầu giai đoạn 2.

## 14. Ngoài phạm vi bản đầu

- Self-serve đăng ký và billing.
- Nguồn ngoài Booking.com như Agoda, Expedia.
- Horizon dài hơn 30 ngày bằng calendar, để dành nếu cần.
- Adapter API cho PMS cụ thể, làm khi có quyền truy cập.
- Cảnh báo thời gian thực tới khách hàng, làm sau bản tin hằng ngày.

## 15. Rủi ro và cách giảm

| Rủi ro | Giảm thiểu |
|---|---|
| Booking đổi giao diện làm parser hỏng | HTML thô lưu 30 ngày, parser có phiên bản, lệnh reparse, cảnh báo khi tỷ lệ parse lỗi tăng |
| Booking siết anti-bot, block rate tăng | Provider dự phòng render toàn phần, đổi nhà cung cấp proxy qua interface, giữ interface Collector để cắm dịch vụ scraping ngoài nếu cần |
| Dữ liệu kiểm duyệt làm insight yếu | Chỉ số nhấn vào thời điểm hết phòng và chuyển ngưỡng, AI nhận mức tin cậy và bị buộc trích bằng chứng |
| Pháp lý khi bán dịch vụ | Tư vấn pháp lý, không lấy dữ liệu cá nhân, nhịp độ lịch sự |
| PMS không cấp API | Import CSV chạy trước, liên hệ ezCloud và Newway sớm |
