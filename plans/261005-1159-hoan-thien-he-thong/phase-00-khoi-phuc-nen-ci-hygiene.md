# Phase 0: Khôi phục nền, CI xanh, hygiene repo

Ước lượng: 1–2 ngày. Phụ thuộc: không. Trạng thái: todo.

## Mục tiêu
CI `main` xanh (ruff + mypy + pytest + lint/typecheck/build), script onboarding chạy được, repo không chứa rác tooling,
quy tắc dev đúng stack.

## Việc

### 0.1 Sửa lỗi đang làm CI đỏ và script chết
- `backend/scripts/capture_fixture.py:56-63`: sắp xếp import (ruff I001) và thay `app.domain.booking_url.parse_booking_url`
  (module đã xoá ở `a9f66ff`) bằng `app.collector.booking.urls.parse_url` (trả `ListingUrl`) hoặc
  `app.channels.registry.parse_listing_url`.
- `backend/scripts/seed_demo.py:69-92`: thay `Hotel(booking_url=…, booking_slug=…, booking_hotel_id=…)` bằng
  `Hotel(name, city, country_code)` + `Listing(hotel_id, channel="booking", listing_key, external_id, url, status="active")`
  (schema sau 0007). Thêm test smoke `tests/integration/test_seed_demo.py` chạy script trên DB test.
- Chạy `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q` cục bộ; đẩy.

### 0.2 CI
- `.github/workflows/ci.yml`: thêm `permissions: {contents: read}`, `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}`;
  cache Playwright (`~/.cache/ms-playwright` theo khoá version); pin action theo SHA; nâng `setup-uv`.
- Dashboard job: thêm `npm run i18n:check`; thêm bước drift `npm run gen:api && git diff --exit-code src/lib/api-types.ts`
  (cần `make openapi` chạy trong backend job và upload artifact, hoặc commit `openapi.json` là nguồn sự thật như hiện
  nay và chỉ kiểm `gen:api` không đổi file).
- Thêm job `docker-build` (chỉ build, chưa push) cho `infra/Dockerfile.backend` và `dashboard/Dockerfile` để phát hiện
  image hỏng (plans ghi "image chưa build lại" nhiều lần).

### 0.3 Hygiene repo
- Thêm `.dockerignore` gốc (`.git`, `.env*`, `**/node_modules`, `**/.venv`, `**/.next`, `.claude`, `.omc`, `plans`,
  `docs`, `backend/tests/fixtures`).
- `git rm -r --cached .omc` (đã có trong `.gitignore` nhưng vẫn track ở `44d0ed4`).
- Quyết định với `.claude/` (17 MB, 980 file ClaudeKit): giữ nếu team dùng; nếu giữ, sửa `.claude/rules/*.md` cho đúng
  stack (Python 3.12 + uv + ruff + mypy + pytest; Next 16 + TS + eslint; bỏ `php -l`/pint/Laravel/Form Request/Enum PHP).
- Quy ước commit: cấm message "123"; thêm `commitlint` hoặc ít nhất ghi trong `CONTRIBUTING` (docs/) + hook
  `.claude/hooks` nếu dùng. Khuyến nghị tách commit theo phase từ nay.
- `docs/operations.md` mục 1: ghi migration tới 0011 (hiện ghi 0001–0007).

### 0.4 Chuẩn bị số liệu nền cho các phase sau
- Chạy `uv run python scripts/validate_run.py <run>` trên 1 run Booking thật gần nhất, lưu kết quả vào
  `plans/261005-1159-hoan-thien-he-thong/reports/baseline-validate-run.md`.
- `EXPLAIN ANALYZE` 3 query nóng (ghi probe theo `probe_id`, `probe_stats_since`, `pending_run_ids`) trên DB dev, lưu
  thời gian làm baseline cho phase 3.

## Tiêu chí nghiệm thu
- CI run trên `main` xanh cả 2 job; `make lint typecheck test-int` xanh cục bộ.
- `uv run python scripts/seed_demo.py` trên DB trống tạo tenant demo + 3 listing Booking, login `admin@demo.vn` vào
  được `/dashboard`.
- `docker build` 2 image thành công trong CI; `.dockerignore` làm context build < 50 MB.
- Không còn file `.omc/**` trong `git ls-files`.

## Rủi ro
- Nếu pytest ở HEAD có test đỏ ngoài ruff (CI chưa tới bước đó từ 25/09), thời gian phase 0 có thể tăng; ưu tiên sửa
  test thật, không skip.
