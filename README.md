# scrapebooking — theo dõi đối thủ khách sạn qua Booking.com

Dịch vụ cho nhiều khách sạn (tenant): quét trang Booking.com của khách sạn khách hàng và
đối thủ 3 lần mỗi ngày, lưu số phòng còn lại (kèm mức tin cậy) và giá theo từng ngày lưu trú
trong 30 ngày tới, phát hiện sự kiện hết phòng/giảm phòng/đổi giá, sinh bản tin hằng ngày
bằng GPT-6 Luna có bằng chứng, hiển thị trên dashboard và so với occupancy thật từ PMS.

Tài liệu:
- Thiết kế: `docs/superpowers/specs/2026-09-24-hotel-competitor-monitor-design.md`
- Kế hoạch giai đoạn 1: `docs/superpowers/plans/2026-09-24-phase1-foundation-collector.md`
- Runbook giai đoạn 1: `docs/runbook-phase1.md`
- Vận hành toàn hệ thống: `docs/operations.md`
- Flow người dùng từng chức năng: `docs/user-flows.md`
- OpenAPI: `docs/api/openapi.json` (sinh từ FastAPI)

## Cấu trúc

```
backend/   Python 3.12: collector, scheduler, worker, analytics, insight, API, CLI (uv)
dashboard/ Next.js 15 + TypeScript
infra/     Dockerfile, docker-compose (core / collector / monitoring), Prometheus, Grafana
docs/
```

## Chạy nhanh

```bash
cp .env.example .env   # bắt buộc: POSTGRES_PASSWORD, REDIS_PASSWORD, MINIO_ROOT_PASSWORD, JWT_SECRET; điền PROXY_URL_TEMPLATE
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
cd backend && uv run sb add-user ops@congty.vn --role operator
# dashboard: http://localhost (Caddy, cổng 80/443 duy nhất publish). Phát triển cần :3000/:8000/:5432…
# trên localhost: thêm -f infra/docker-compose.dev.yml. API docs: http://localhost:8000/docs (dev override)
```

Phát triển cục bộ (Postgres + Redis + MinIO từ compose):

```bash
make infra-up && make migrate
cd backend && uv sync && uv run playwright install chromium
uv run python scripts/seed_demo.py          # dữ liệu demo, admin@demo.vn / demo-pass-123
make api                                    # http://localhost:8000
cd dashboard && npm install && npm run dev  # http://localhost:3000
```

Kiểm thử: `make lint typecheck test-int`.
