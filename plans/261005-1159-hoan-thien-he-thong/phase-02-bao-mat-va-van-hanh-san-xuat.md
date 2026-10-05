# Phase 2: Bảo mật và vận hành sản xuất

Ước lượng: 1,5–2 tuần. Phụ thuộc: phase 0. Trạng thái: todo. Điều kiện bắt buộc trước khi bán cho khách thật.

## Mục tiêu
Không secret mặc định, không cổng dịch vụ nội bộ mở ra Internet, TLS, phiên thu hồi được, không brute-force, backup
khôi phục được từ máy khác, có cảnh báo tự động, scheduler không single point of failure về logic.

## Việc

### 2.1 Backend auth hardening
- `config.py`: thêm `app_env: Literal["dev","staging","prod"]`; `create_app` và scheduler/worker từ chối khởi động khi
  `app_env=prod` và (`jwt_secret == "change-me"` hoặc `len < 32` hoặc `cookie_secure=False` hoặc `cors_origins` chứa `*`).
- `api/auth.py`: `verify_password`/`hash_password` chạy `await asyncio.to_thread(...)`; login luôn chạy một lần
  verify (dummy hash) khi email không tồn tại (chống enumeration theo thời gian).
- Rate-limit login: Redis sliding window theo IP (từ `X-Forwarded-For` đã tin cậy) và theo email: 5 lần/phút, 20/giờ;
  lockout tạm 15 phút → 429 + `Retry-After`. Dùng chung helper với throttle `market_city` hiện có.
- Thu hồi phiên: `users.token_version` (migration 0012); đưa vào JWT; `get_principal` so sánh; tăng khi đổi mật khẩu,
  khoá, đổi role, "đăng xuất mọi thiết bị". Tự đổi mật khẩu phải gửi mật khẩu hiện tại.
- `get_principal`/login kiểm `Tenant.active` → 403 `tenant_disabled`.
- CSRF: middleware kiểm `Origin` (hoặc `Referer`) khớp `APP_BASE_URL` cho mọi request không phải GET/HEAD/OPTIONS có
  cookie; `GET /market/areas/search` đổi thành POST (hoặc giữ GET nhưng bỏ side effect: chỉ đọc cache).
- Password reset qua email (SMTP đã có): `POST /auth/forgot` (luôn 204), token một lần 30 phút trong Redis,
  `POST /auth/reset`. Màn `/forgot`, `/reset` ở dashboard (phase 4 làm UI).
- Listing dùng chung (S7): `add_listing`, `confirm`, `reject`, `retry` đều qua `_ensure_sole_tracker` trừ khi listing
  `suggested` do chính tenant này được gợi ý; `run_verify_listing` so tên (matching.py) + khoảng cách ≤ 2 km với
  `hotels.name/lat/lng`, lệch → `broken:identity_mismatch` không `active`.
- Upload: `MAX_UPLOAD_BYTES=5MB`, `MAX_ROWS=5000`, cắt lỗi lưu ≤ 200 dòng; stream `file.read()` theo chunk; đổi thứ tự
  decode `utf-8-sig → cp1258 → utf-16 (chỉ khi có BOM) → latin-1`.
- Quota theo tenant (cột `tenants.limits` JSONB, default): `max_hotels=25`, `manual_scans_per_day=6`,
  `insights_per_day=5`, `max_areas=3` (đã có); vượt → 429/422 có thông điệp. Dedupe `enqueue_verify` bằng job id.
- `/metrics`: chỉ cho IP nội bộ hoặc token `METRICS_TOKEN`; `/docs`, `/openapi.json` tắt khi `app_env=prod`
  (OpenAPI vẫn export qua script); `/healthz` ping DB + Redis, trả 503 khi lỗi.
- Che `ListingOut.last_error` thành mã ngắn cho non-operator (như `RunJobOut`); `InsightOut.error` chỉ mã.
- Audit log tối thiểu: bảng `audit_events(tenant_id, user_id, action, target, payload, at)` ghi ở login, đổi mật khẩu,
  tạo/khoá user, đổi settings, thêm/xoá/sửa listing, xoá khu vực.

### 2.2 Dashboard (phần bảo mật, phần UX ở phase 4)
- `src/app/api/[...path]/route.ts`: allowlist prefix (`auth, tenants, settings, users, watchlist, channels, overview,
  hotels, events, runs, insights, pms, notifications, export, market, health`) → mọi path khác 404; thêm
  `AbortSignal.timeout(30s)`; cap body 6 MB; set `X-Forwarded-For/Proto/Host`; lỗi 502 không in URL nội bộ.
- `login/page.tsx` `safeNext`: chỉ chấp nhận `^/[A-Za-z0-9_\-/?=&%.]*$` và không bắt đầu bằng `//` hay `/\`.
- `next.config.ts` `headers()`: CSP (`default-src 'self'; img-src 'self' data: https:; connect-src 'self'; frame-ancestors
  'none'`), `X-Content-Type-Options`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`,
  HSTS (chỉ khi có TLS). Kiểm Recharts/next-intl không cần `unsafe-inline` script; style có thể cần nonce.
- Bỏ 2 `dangerouslySetInnerHTML` ghi chú thiết kế ở `(marketing)/layout.tsx:26`, `(app)/layout.tsx:16` (chuyển vào DESIGN.md).

### 2.3 Hạ tầng (VPS đơn, compose; nếu câu 4 audit trả lời k8s thì viết lại mục này)
- `infra/docker-compose.yml`: mạng `internal` cho postgres/redis/minio/api/jobs/scheduler/worker; **không `ports:`** cho
  5432/6379/9000/9001/8000; chỉ reverse proxy publish 80/443. Thêm `caddy` (hoặc traefik) với TLS tự động, proxy
  `/` → dashboard; dashboard vẫn proxy `/api` → api nội bộ. `COOKIE_SECURE=true`, `APP_BASE_URL=https://…`.
- Secrets: `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`, `GF_SECURITY_ADMIN_PASSWORD` từ
  `.env` (bắt buộc, compose fail nếu thiếu: `${VAR:?}`); Redis `--requirepass` + `appendonly yes` + volume.
- `restart: unless-stopped` cho postgres/redis/minio/caddy; healthcheck cho api (`/healthz`), dashboard (`GET /login`),
  scheduler/worker/jobs (`arq --check` hoặc heartbeat file); `depends_on` có `condition: service_healthy`.
- Resource limit cho postgres (`shared_buffers` theo RAM), api, jobs, scheduler; `logging: {driver: json-file,
  options: {max-size: 50m, max-file: 5}}` mọi service.
- `infra/Dockerfile.backend` tách 2 target: `base` (slim, non-root `app`, không Chromium) cho api/jobs/scheduler;
  `collector` (base + Playwright Chromium) cho 5 worker. Pin `uv` version, `python:3.12.x-slim` theo digest.
- Pin image Prometheus/Grafana/MinIO/Postgres/Redis theo tag cụ thể.

### 2.4 Backup và khôi phục
- Thay `ops/backup.py` đọc toàn bộ vào RAM bằng `pg_dump -Fc | gzip` stream (subprocess pipe → upload multipart);
  hoặc chuyển sang `pgbackrest`/`wal-g` container (full hằng đêm + WAL liên tục, PITR).
- Đích offsite: bucket S3-compatible ở nhà cung cấp khác (B2/Wasabi/S3) thay MinIO cùng máy; giữ MinIO cho HTML thô.
- Script `infra/scripts/restore-drill.sh`: tải bản mới nhất, restore vào Postgres tạm, chạy `SELECT count(*)` 5 bảng,
  so với số ghi lúc backup; cron tháng + ghi kết quả vào `docs/operations.md`.

### 2.5 Giám sát và cảnh báo
- `ops/metrics.py`: thêm `scheduler_tick_seconds`, `scheduler_last_tick_timestamp`, `arq_queue_depth{queue}`
  (đọc ZCARD), `runs_expired_total`, `analytics_lag_seconds` (run chốt → analytics xong), sửa `QUEUE_DEPTH` sai nghĩa.
- Prometheus `rule_files` + Alertmanager (email qua SMTP đã có, Telegram tuỳ chọn): scheduler không tick 5 phút; run
  thành công < 90%; block rate > 20%; queue depth tăng 30 phút; analytics lag > 30 phút; disk > 80%; backup fail;
  Postgres/Redis down; cert hết hạn 14 ngày.
- Grafana: dashboard "API" (p95 latency theo route, 5xx) và "Jobs" (insight/notify/occupancy) ngoài "Collector".
- Scrape collector từ xa (`docker-compose.collector.yml` publish `METRICS_PORT` qua mạng nội bộ/WireGuard).

### 2.6 Scheduler HA tối thiểu và độ bền tick
- `scheduler/service.py`: `pg_try_advisory_lock(hash("scheduler"))` đầu mỗi tick; không lấy được → bỏ tick (cho phép
  chạy 2 bản sao an toàn).
- Tách SMTP alert và proxy check ra khỏi transaction tick (chạy `asyncio.create_task` sau commit, hoặc đẩy vào jobs
  worker); `db/engine.py` đặt `statement_timeout=30s`, `idle_in_transaction_session_timeout=60s` cho scheduler/api.
- Throttle alert chuyển sang Redis (`SET NX EX`); state thị trường (`_idle_until`…) sang Redis.
- `scrape_sessions.status` → String(32) (migration), hoặc tách `retire_reason`.

### 2.7 Pháp lý và thương hiệu
- Checklist trước bán: tư vấn ToS (docs/operations.md §12), trang điều khoản dịch vụ + chính sách dữ liệu trên landing
  (nội dung do người dùng cung cấp), `SMTP_FROM`/template email đổi OTARadar, `List-Unsubscribe` header.

## Tiêu chí nghiệm thu
- `APP_ENV=prod JWT_SECRET=change-me` → api không khởi động, log lý do rõ.
- 6 lần login sai/phút → 429; argon2 không chặn event loop (test: 20 login song song, p95 `/healthz` < 100 ms).
- Đổi mật khẩu → cookie cũ 401 ngay. `Tenant.active=false` → 403.
- POST từ origin lạ có cookie → 403. `curl https://host/api/metrics` → 404; `https://host/api/docs` → 404.
- `nmap` VPS: chỉ 22 (giới hạn IP), 80, 443. Redis yêu cầu mật khẩu.
- Restore drill từ offsite trên máy sạch < 30 phút, đếm dòng khớp.
- Tắt scheduler 10 phút → Alertmanager gửi email. Chạy 2 scheduler song song 1 giờ → không run trùng, không alert đôi.
- Tenant A dán URL vào kênh `broken` của khách sạn chung → 403 nếu tenant B cũng theo dõi.

## Rủi ro
- CSP có thể vỡ Recharts/inline style: bật ở chế độ `Content-Security-Policy-Report-Only` 1 tuần trước.
- Đổi mạng compose làm collector từ xa mất kết nối: cập nhật `docker-compose.collector.yml` + WireGuard cùng lúc.
