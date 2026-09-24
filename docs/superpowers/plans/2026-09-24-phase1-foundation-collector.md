# Giai đoạn 1: Nền tảng và Collector — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Trạng thái 2026-09-24:** đã triển khai toàn bộ code của giai đoạn 1 (và các giai đoạn
> 2–5, xem `docs/superpowers/plans/2026-09-24-phases2-5-implementation-notes.md`). Các bước
> còn để trống là bước cần proxy residential thật, Docker daemon hoặc chạy thật nhiều ngày:
> bắt fixture Booking thật và xác nhận selector, test live, build image và chạy full stack,
> chạy thật 3 ngày. Fixture hiện tại là trang mô phỏng (`backend/tests/fixtures/html/README.md`).

**Goal:** Snapshot số phòng còn lại và giá theo từng ngày lưu trú đổ về Postgres đúng lịch 3 lần mỗi ngày cho mọi khách sạn trong watchlist, HTML thô lưu MinIO, có health metrics và cảnh báo.

**Architecture:** Một package Python `backend/app` với ba entrypoint: `scheduler` tạo scan run và đẩy job vào Redis, `worker` (arq) lấy job theo khách sạn, lấy calendar rồi probe từng ngày qua session lai (Playwright vượt challenge một lần, curl_cffi tải trang), parse và ghi snapshot, `cli` cho thao tác vận hành. Mọi phần dùng interface `Collector`, `ProxyProvider`, `SessionBootstrapper`, `Fetcher`, `RawStore` để test bằng fake.

**Tech Stack:** Python 3.12, uv, SQLAlchemy 2 async + asyncpg, Alembic, arq + Redis, curl_cffi, Playwright, selectolax, boto3 (MinIO), prometheus_client, httpx, structlog, typer, pytest + pytest-asyncio + moto. Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-24-hotel-competitor-monitor-design.md`, mục 4, 5, 6, 11, 12.

**Điều chỉnh so với spec, đã cân nhắc:**
- Job hàng đợi là **một job mỗi khách sạn mỗi đợt quét** (`probe_hotel(scan_run_id, hotel_id)`), bên trong lấy calendar rồi probe tuần tự từng ngày. Điều này tự nhiên đảm bảo mỗi khách sạn tối đa 1 request đồng thời. Idempotent ở hai mức: job id `probe:{run}:{hotel}` trong arq, và unique `(scan_run_id, hotel_id, stay_date)` trong `probes` với upsert. Thêm bảng `scan_jobs` để theo dõi hoàn tất đợt quét.
- Bảng `tenants` và `tenant_hotels` tạo ngay vì scheduler cần. `users`, `own_hotel_daily`, `pms_imports`, `insights`, `hotel_date_snapshots`, `availability_events`, `hotel_date_metrics` để migration ở giai đoạn sau.
- Compose dùng ba file (`docker-compose.yml`, `docker-compose.collector.yml`, `docker-compose.monitoring.yml`) thay cho ba profile trong một file, để máy worker ngoài chỉ cần một file.
- HTML thô tự hết hạn sau 30 ngày bằng lifecycle rule của MinIO (Task 6). Xoá partition `room_snapshots` quá 24 tháng và backup Postgres hằng đêm thuộc giai đoạn 5 theo lộ trình trong spec.

---

## Bản đồ file

```
.gitignore
.env.example
Makefile
backend/
  pyproject.toml
  alembic.ini
  alembic/
    env.py
    script.py.mako
    versions/0001_phase1_tables.py
  app/
    __init__.py
    config.py                 # Settings (pydantic-settings)
    logging.py                # structlog JSON
    clock.py                  # Clock protocol + SystemClock (test dễ)
    db/
      __init__.py
      engine.py               # engine, session factory
      models.py               # SQLAlchemy models giai đoạn 1
      partitions.py           # ensure_room_snapshot_partitions
    domain/
      __init__.py
      models.py               # enums, RoomOffer, ProbeResult, CalendarResult, HotelRef
      stock.py                # derive_stock
      booking_url.py          # parse_booking_url
    collector/
      __init__.py
      base.py                 # Collector Protocol
      fake.py                 # FakeCollector cho test
      proxy.py                # ProxyEndpoint, ProxyProvider, StaticProxyProvider
      session.py              # ScrapeSession, SessionBootstrapper, SessionManager
      ratelimit.py            # RateLimiter
      fetch.py                # Fetcher Protocol, FetchResponse, classify_response, CurlFetcher
      storage.py              # RawStore (MinIO/S3)
      booking/
        __init__.py
        urls.py               # build_hotel_url
        selectors.py          # CSS selectors + regex, PARSER_VERSION
        parser.py             # parse_hotel_page
        calendar.py           # build_calendar_request, parse_calendar_response
        playwright_bootstrap.py  # PlaywrightBootstrapper
        browser.py            # BrowserCollector
        hybrid.py             # HybridCollector
    repo/
      __init__.py
      snapshots.py            # SnapshotRepository
      runs.py                 # ScanRunRepository
    scheduler/
      __init__.py
      planning.py             # due_triggers, build_hotel_plan (pure)
      service.py              # SchedulerService (loop)
      __main__.py
    worker/
      __init__.py
      jobs.py                 # probe_hotel
      settings.py             # arq WorkerSettings
    ops/
      __init__.py
      metrics.py              # prometheus counters
      alerts.py               # TelegramAlerter, block-rate check
    cli.py                    # typer
  scripts/
    explore_fixture.py
  tests/
    conftest.py
    fixtures/html/            # trang Booking thật
    unit/...
    integration/...
    live/...
infra/
  docker-compose.yml
  docker-compose.collector.yml
  docker-compose.monitoring.yml
  prometheus/prometheus.yml
  grafana/provisioning/datasources/datasource.yml
  Dockerfile.backend
.github/workflows/ci.yml
```

Quy ước chạy lệnh: mọi lệnh Python chạy từ `backend/` với `uv run`. Mọi lệnh `git` chạy từ gốc repo.

Đánh dấu test: `unit` (mặc định, không cần dịch vụ), `integration` (cần Postgres, Redis, MinIO từ compose), `live` (gọi Booking thật, không chạy trong CI).

---

### Task 1: Khung dự án backend

**Files:**
- Create: `.gitignore`, `.env.example`, `Makefile`
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/integration/__init__.py`, `backend/tests/live/__init__.py`, `backend/tests/unit/test_smoke.py`

- [x] **Step 1: Tạo `.gitignore` ở gốc repo**

```gitignore
.omc/
.env
__pycache__/
*.pyc
.venv/
.mypy_cache/
.pytest_cache/
.ruff_cache/
backend/tests/fixtures/html/*.tmp.html
node_modules/
dist/
.DS_Store
```

- [x] **Step 2: Tạo `.env.example` ở gốc repo**

```env
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/scrapebooking
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/scrapebooking_test
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=raw-html
PROXY_URL_TEMPLATE=http://USER-country-{country}-session-{session}:PASS@proxy.example.com:7777
SESSION_MAX_AGE_MINUTES=20
SESSION_MAX_REQUESTS=400
REQUEST_MIN_INTERVAL_SECONDS=2.0
REQUEST_JITTER_SECONDS=1.0
PAGE_DROPDOWN_CAP=10
RUN_DEADLINE_MINUTES=90
DEFAULT_ADULTS=2
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
METRICS_PORT=9100
LOG_LEVEL=INFO
PLAYWRIGHT_HEADLESS=true
```

- [x] **Step 3: Tạo `backend/pyproject.toml`**

```toml
[project]
name = "scrapebooking-backend"
version = "0.1.0"
description = "Hotel competitor monitor: Booking.com availability collector"
requires-python = ">=3.12"
dependencies = [
  "sqlalchemy[asyncio]>=2.0.30",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "arq>=0.26",
  "redis>=5.0",
  "curl_cffi>=0.7",
  "playwright>=1.45",
  "selectolax>=0.3.21",
  "boto3>=1.34",
  "prometheus-client>=0.20",
  "httpx>=0.27",
  "structlog>=24.1",
  "typer>=0.12",
]

[dependency-groups]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "moto[s3]>=5.0",
  "ruff>=0.5",
  "mypy>=1.10",
  "types-boto3",
  "respx>=0.21",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
  "integration: cần Postgres/Redis/MinIO từ docker compose",
  "live: gọi Booking.com thật, không chạy trong CI",
]
addopts = "-m 'not live'"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["E501"]
"scripts/**" = ["E501"]
"alembic/**" = ["E501", "UP"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]
```

- [x] **Step 4: Tạo package rỗng và test smoke**

`backend/app/__init__.py`, `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/integration/__init__.py`, `backend/tests/live/__init__.py` đều rỗng.

`backend/tests/unit/test_smoke.py`:

```python
import app


def test_package_importable() -> None:
    assert app is not None
```

- [x] **Step 5: Tạo `Makefile` ở gốc repo**

```makefile
.PHONY: infra-up infra-down test test-int lint typecheck migrate

infra-up:
	docker compose -f infra/docker-compose.yml up -d postgres redis minio

infra-down:
	docker compose -f infra/docker-compose.yml down

test:
	cd backend && uv run pytest -q -m "not integration and not live"

test-int:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

typecheck:
	cd backend && uv run mypy app

migrate:
	cd backend && uv run alembic upgrade head
```

- [x] **Step 6: Cài đặt và chạy smoke test**

Run: `cd backend && uv sync && uv run playwright install chromium && uv run pytest -q`
Expected: `1 passed`

- [x] **Step 7: Commit**

```bash
git add .gitignore .env.example Makefile backend/pyproject.toml backend/uv.lock backend/app backend/tests
git commit -m "chore: scaffold backend package with tooling"
```

---

### Task 2: Settings và logging

**Files:**
- Create: `backend/app/config.py`, `backend/app/logging.py`, `backend/app/clock.py`
- Test: `backend/tests/unit/test_config.py`

- [x] **Step 1: Viết test settings thất bại**

`backend/tests/unit/test_config.py`:

```python
from app.config import Settings


def test_settings_read_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/1")
    monkeypatch.setenv("PROXY_URL_TEMPLATE", "http://a-{country}-{session}:b@p:1")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/db"
    assert s.redis_url == "redis://h:6379/1"
    assert s.session_max_requests == 400
    assert s.page_dropdown_cap == 10
    assert s.request_min_interval_seconds == 2.0


def test_settings_defaults(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/1")
    monkeypatch.setenv("PROXY_URL_TEMPLATE", "http://a-{country}-{session}:b@p:1")
    s = Settings(_env_file=None)
    assert s.default_adults == 2
    assert s.run_deadline_minutes == 90
    assert s.minio_bucket == "raw-html"
```

- [x] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_config.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.config'`

- [x] **Step 3: Viết `backend/app/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str
    test_database_url: str = "postgresql+asyncpg://app:app@localhost:5432/scrapebooking_test"
    redis_url: str

    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "raw-html"

    proxy_url_template: str
    session_max_age_minutes: int = 20
    session_max_requests: int = 400
    request_min_interval_seconds: float = 2.0
    request_jitter_seconds: float = 1.0
    page_dropdown_cap: int = 10
    run_deadline_minutes: int = 90
    default_adults: int = 2

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    metrics_port: int = 9100
    log_level: str = "INFO"
    playwright_headless: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [x] **Step 4: Viết `backend/app/logging.py`**

```python
import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
```

- [x] **Step 5: Viết `backend/app/clock.py`**

```python
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class FixedClock:
    def __init__(self, at: datetime) -> None:
        self._at = at

    def now(self) -> datetime:
        return self._at

    def advance(self, **kwargs: float) -> None:
        from datetime import timedelta

        self._at = self._at + timedelta(**kwargs)
```

- [x] **Step 6: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_config.py -q`
Expected: `2 passed`

- [x] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/logging.py backend/app/clock.py backend/tests/unit/test_config.py
git commit -m "feat: settings, structured logging, clock abstraction"
```

---

### Task 3: Hạ tầng Compose cho Postgres, Redis, MinIO

**Files:**
- Create: `infra/docker-compose.yml`

- [x] **Step 1: Viết `infra/docker-compose.yml` (mới có 3 dịch vụ hạ tầng, các dịch vụ ứng dụng thêm ở Task 19)**

```yaml
name: scrapebooking

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: scrapebooking
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d scrapebooking"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports: ["9000:9000", "9001:9001"]
    volumes: ["miniodata:/data"]
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
  miniodata:
```

- [x] **Step 2: Khởi động và kiểm tra**

Run: `make infra-up && sleep 8 && docker compose -f infra/docker-compose.yml ps`
Expected: ba dịch vụ `postgres`, `redis`, `minio` trạng thái `healthy` (hoặc `running` với minio nếu image không có `mc`; khi đó đổi healthcheck thành `["CMD-SHELL", "curl -f http://localhost:9000/minio/health/live || exit 1"]`).

- [x] **Step 3: Tạo database test**

Run: `docker compose -f infra/docker-compose.yml exec postgres psql -U app -d scrapebooking -c "CREATE DATABASE scrapebooking_test;"`
Expected: `CREATE DATABASE`

- [x] **Step 4: Commit**

```bash
git add infra/docker-compose.yml
git commit -m "infra: compose services for postgres, redis, minio"
```

---

### Task 4: Domain models, derive_stock, parse_booking_url

**Files:**
- Create: `backend/app/domain/__init__.py`, `backend/app/domain/models.py`, `backend/app/domain/stock.py`, `backend/app/domain/booking_url.py`
- Test: `backend/tests/unit/test_stock.py`, `backend/tests/unit/test_booking_url.py`, `backend/tests/unit/test_domain_models.py`

- [x] **Step 1: Viết test derive_stock thất bại**

`backend/tests/unit/test_stock.py`:

```python
import pytest

from app.domain.models import StockConfidence
from app.domain.stock import derive_stock


@pytest.mark.parametrize(
    "badge,dropdown,cap,rooms_left,confidence",
    [
        (3, 3, 10, 3, StockConfidence.EXACT),
        (1, None, 10, 1, StockConfidence.EXACT),
        (None, 10, 10, 10, StockConfidence.CAPPED),
        (None, 12, 10, 12, StockConfidence.CAPPED),
        (None, 4, 10, None, StockConfidence.HIDDEN),
        (None, None, 10, None, StockConfidence.HIDDEN),
        (0, 0, 10, 0, StockConfidence.SOLD_OUT),
        (None, 0, 10, 0, StockConfidence.SOLD_OUT),
    ],
)
def test_derive_stock(badge, dropdown, cap, rooms_left, confidence) -> None:  # type: ignore[no-untyped-def]
    stock = derive_stock(badge_count=badge, dropdown_max=dropdown, page_cap=cap)
    assert stock.rooms_left == rooms_left
    assert stock.confidence == confidence


def test_badge_wins_over_dropdown_when_both_present() -> None:
    stock = derive_stock(badge_count=2, dropdown_max=10, page_cap=10)
    assert stock.rooms_left == 2
    assert stock.confidence == StockConfidence.EXACT
```

- [x] **Step 2: Viết test parse_booking_url thất bại**

`backend/tests/unit/test_booking_url.py`:

```python
import pytest

from app.domain.booking_url import BookingUrlError, parse_booking_url


def test_parse_standard_url() -> None:
    ref = parse_booking_url("https://www.booking.com/hotel/vn/the-reverie-saigon.html?aid=1&x=2")
    assert ref.country_code == "vn"
    assert ref.slug == "vn/the-reverie-saigon"
    assert ref.pagename == "the-reverie-saigon"
    assert ref.canonical_url == "https://www.booking.com/hotel/vn/the-reverie-saigon.html"


def test_parse_localized_domain_and_lang_suffix() -> None:
    ref = parse_booking_url("https://www.booking.com/hotel/vn/the-reverie-saigon.vi.html")
    assert ref.slug == "vn/the-reverie-saigon"
    assert ref.canonical_url == "https://www.booking.com/hotel/vn/the-reverie-saigon.html"


@pytest.mark.parametrize(
    "bad",
    [
        "https://www.booking.com/searchresults.html?ss=hanoi",
        "https://example.com/hotel/vn/x.html",
        "not a url",
    ],
)
def test_reject_non_hotel_urls(bad: str) -> None:
    with pytest.raises(BookingUrlError):
        parse_booking_url(bad)
```

- [x] **Step 3: Viết test cho RoomOffer.min_price thất bại**

`backend/tests/unit/test_domain_models.py`:

```python
from decimal import Decimal

from app.domain.models import RatePlan, RoomOffer


def _offer(*rates: RatePlan) -> RoomOffer:
    return RoomOffer(
        booking_room_id="123",
        name="Deluxe",
        max_occupancy=2,
        badge_count=None,
        dropdown_max=5,
        rates=tuple(rates),
    )


def test_min_price_and_min_refundable_price() -> None:
    offer = _offer(
        RatePlan(name="Non-refundable", price=Decimal("100"), currency="VND", refundable=False, breakfast=False),
        RatePlan(name="Flexible", price=Decimal("120"), currency="VND", refundable=True, breakfast=False),
        RatePlan(name="Flex+BF", price=Decimal("140"), currency="VND", refundable=True, breakfast=True),
    )
    assert offer.min_price == Decimal("100")
    assert offer.min_refundable_price == Decimal("120")
    assert offer.currency == "VND"


def test_min_prices_when_no_rates() -> None:
    offer = _offer()
    assert offer.min_price is None
    assert offer.min_refundable_price is None
    assert offer.currency is None
```

- [x] **Step 4: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_stock.py tests/unit/test_booking_url.py tests/unit/test_domain_models.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.domain'`

- [x] **Step 5: Viết `backend/app/domain/models.py`** (`backend/app/domain/__init__.py` rỗng)

```python
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class StockConfidence(StrEnum):
    EXACT = "exact"
    CAPPED = "capped"
    HIDDEN = "hidden"
    SOLD_OUT = "sold_out"


class ProbeStatus(StrEnum):
    OK = "ok"
    SOLD_OUT = "sold_out"
    NO_ROOMS_1N = "no_rooms_1n"
    BLOCKED = "blocked"
    ERROR = "error"
    SKIPPED_CALENDAR = "skipped_calendar"


class ProbeMethod(StrEnum):
    HTTP = "http"
    BROWSER = "browser"
    CALENDAR = "calendar"


class PageOutcome(StrEnum):
    ROOMS = "rooms"        # có bảng phòng với ít nhất 1 dòng
    SOLD_OUT = "sold_out"  # có thông báo hết phòng rõ ràng
    EMPTY = "empty"        # không có bảng phòng, không có thông báo: nghi bị chặn hoặc min stay


@dataclass(frozen=True)
class HotelRef:
    id: int
    country_code: str
    slug: str            # "vn/the-reverie-saigon"
    canonical_url: str

    @property
    def pagename(self) -> str:
        return self.slug.split("/", 1)[1]


@dataclass(frozen=True)
class RatePlan:
    name: str
    price: Decimal
    currency: str
    refundable: bool | None
    breakfast: bool | None


@dataclass(frozen=True)
class RoomOffer:
    booking_room_id: str
    name: str
    max_occupancy: int | None
    badge_count: int | None
    dropdown_max: int | None
    rates: tuple[RatePlan, ...] = field(default_factory=tuple)

    @property
    def min_price(self) -> Decimal | None:
        return min((r.price for r in self.rates), default=None)

    @property
    def min_refundable_price(self) -> Decimal | None:
        return min((r.price for r in self.rates if r.refundable), default=None)

    @property
    def currency(self) -> str | None:
        return self.rates[0].currency if self.rates else None


@dataclass(frozen=True)
class ParsedPage:
    outcome: PageOutcome
    booking_hotel_id: str | None
    hotel_name: str | None
    csrf_token: str | None
    offers: tuple[RoomOffer, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    method: ProbeMethod
    checkin: date
    checkout: date
    nights: int
    adults: int
    offers: tuple[RoomOffer, ...]
    raw_html: str | None
    http_status: int | None
    session_id: str | None
    duration_ms: int
    error: str | None = None
    booking_hotel_id: str | None = None
    hotel_name: str | None = None


@dataclass(frozen=True)
class CalendarDay:
    checkin: date
    available: bool
    min_length_of_stay: int
    avg_price_display: str | None


@dataclass(frozen=True)
class CalendarResult:
    ok: bool
    days: tuple[CalendarDay, ...] = field(default_factory=tuple)
    error: str | None = None

    def day(self, d: date) -> CalendarDay | None:
        for cd in self.days:
            if cd.checkin == d:
                return cd
        return None
```

- [x] **Step 6: Viết `backend/app/domain/stock.py`**

```python
from dataclasses import dataclass

from app.domain.models import StockConfidence


@dataclass(frozen=True)
class Stock:
    rooms_left: int | None
    confidence: StockConfidence


def derive_stock(badge_count: int | None, dropdown_max: int | None, page_cap: int) -> Stock:
    """Suy ra số phòng còn và mức tin cậy từ hai tín hiệu thô trên trang.

    - badge_count: số trong "Only X rooms left", None nếu không có badge.
    - dropdown_max: giá trị lớn nhất của dropdown chọn số phòng, None nếu không có.
    - page_cap: trần của dropdown trên trang (cấu hình PAGE_DROPDOWN_CAP).
    """
    if badge_count is not None:
        if badge_count == 0:
            return Stock(0, StockConfidence.SOLD_OUT)
        return Stock(badge_count, StockConfidence.EXACT)
    if dropdown_max is None:
        return Stock(None, StockConfidence.HIDDEN)
    if dropdown_max == 0:
        return Stock(0, StockConfidence.SOLD_OUT)
    if dropdown_max >= page_cap:
        return Stock(dropdown_max, StockConfidence.CAPPED)
    return Stock(None, StockConfidence.HIDDEN)
```

- [x] **Step 7: Viết `backend/app/domain/booking_url.py`**

```python
import re
from dataclasses import dataclass
from urllib.parse import urlparse

_PATH_RE = re.compile(r"^/hotel/(?P<cc>[a-z]{2})/(?P<name>[a-z0-9\-]+?)(?:\.[a-z]{2}(?:-[a-z]{2})?)?\.html$")


class BookingUrlError(ValueError):
    pass


@dataclass(frozen=True)
class BookingHotelUrl:
    country_code: str
    slug: str
    canonical_url: str

    @property
    def pagename(self) -> str:
        return self.slug.split("/", 1)[1]


def parse_booking_url(url: str) -> BookingHotelUrl:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc.endswith("booking.com"):
        raise BookingUrlError(f"not a booking.com url: {url}")
    m = _PATH_RE.match(parsed.path)
    if not m:
        raise BookingUrlError(f"not a hotel page url: {url}")
    cc, name = m.group("cc"), m.group("name")
    slug = f"{cc}/{name}"
    return BookingHotelUrl(
        country_code=cc,
        slug=slug,
        canonical_url=f"https://www.booking.com/hotel/{slug}.html",
    )
```

- [x] **Step 8: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_stock.py tests/unit/test_booking_url.py tests/unit/test_domain_models.py -q`
Expected: `16 passed`

- [x] **Step 9: Commit**

```bash
git add backend/app/domain backend/tests/unit/test_stock.py backend/tests/unit/test_booking_url.py backend/tests/unit/test_domain_models.py
git commit -m "feat(domain): core models, derive_stock, booking url parsing"
```

---

### Task 5: Models SQLAlchemy, Alembic, migration đầu tiên, partition

**Files:**
- Create: `backend/app/db/__init__.py`, `backend/app/db/engine.py`, `backend/app/db/models.py`, `backend/app/db/partitions.py`
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_phase1_tables.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/integration/test_migrations.py`, `backend/tests/unit/test_partitions.py`

- [x] **Step 1: Viết test unit cho tên partition (thất bại)**

`backend/tests/unit/test_partitions.py`:

```python
from datetime import date

from app.db.partitions import month_range, partition_name


def test_partition_name() -> None:
    assert partition_name(date(2026, 9, 15)) == "room_snapshots_2026_09"


def test_month_range_crosses_year() -> None:
    assert month_range(date(2026, 12, 3)) == (date(2026, 12, 1), date(2027, 1, 1))
```

- [x] **Step 2: Viết test integration migration (thất bại)**

`backend/tests/integration/test_migrations.py`:

```python
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.partitions import ensure_room_snapshot_partitions

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "tenants", "hotels", "tenant_hotels", "room_types", "scan_runs", "scan_jobs",
    "probes", "hotel_calendars", "room_snapshots", "scrape_sessions",
}


async def test_all_phase1_tables_exist(db: AsyncSession) -> None:
    rows = await db.execute(
        text("select tablename from pg_tables where schemaname='public'")
    )
    names = {r[0] for r in rows}
    assert EXPECTED_TABLES <= names


async def test_room_snapshots_is_partitioned_with_current_months(db: AsyncSession) -> None:
    rows = await db.execute(
        text(
            "select c.relname from pg_inherits i "
            "join pg_class c on c.oid = i.inhrelid "
            "join pg_class p on p.oid = i.inhparent where p.relname='room_snapshots'"
        )
    )
    parts = {r[0] for r in rows}
    assert len(parts) >= 3
    assert any(p.startswith("room_snapshots_") for p in parts)


async def test_ensure_partitions_creates_past_month(db: AsyncSession) -> None:
    conn = await db.connection()
    created = await ensure_room_snapshot_partitions(conn, first_month=date(2020, 1, 10), months=2)
    assert created == ["room_snapshots_2020_01", "room_snapshots_2020_02"]
    again = await ensure_room_snapshot_partitions(conn, first_month=date(2020, 1, 10), months=2)
    assert again == []
    await db.commit()
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_partitions.py tests/integration/test_migrations.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.db'`

- [x] **Step 4: Viết `backend/app/db/engine.py`** (`backend/app/db/__init__.py` rỗng)

```python
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [x] **Step 5: Viết `backend/app/db/models.py`**

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    scan_times: Mapped[list[str]] = mapped_column(
        ARRAY(String(5)), default=lambda: ["06:00", "14:00", "22:00"]
    )
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    insight_language: Mapped[str] = mapped_column(String(8), default="vi")
    insight_hour: Mapped[str] = mapped_column(String(5), default="07:30")
    country_code: Mapped[str] = mapped_column(String(2), default="vn")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_url: Mapped[str] = mapped_column(Text)
    booking_slug: Mapped[str] = mapped_column(String(200), unique=True)
    booking_hotel_id: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2))
    star_rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TenantHotel(Base):
    __tablename__ = "tenant_hotels"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # self | competitor
    label: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (UniqueConstraint("hotel_id", "booking_room_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    booking_room_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(300))
    max_occupancy: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger_key: Mapped[str] = mapped_column(String(32), unique=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    total_probes: Mapped[int] = mapped_column(Integer, default=0)
    ok_count: Mapped[int] = mapped_column(Integer, default=0)
    sold_out_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date)
    horizon_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Probe(Base):
    __tablename__ = "probes"
    __table_args__ = (
        UniqueConstraint("scan_run_id", "hotel_id", "stay_date"),
        Index("ix_probes_hotel_date_fetched", "hotel_id", "stay_date", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    stay_date: Mapped[date] = mapped_column(Date)
    checkin: Mapped[date] = mapped_column(Date)
    checkout: Mapped[date] = mapped_column(Date)
    nights: Mapped[int] = mapped_column(Integer)
    adults: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    method: Mapped[str | None] = mapped_column(String(16))
    proxy_country: Mapped[str | None] = mapped_column(String(2))
    session_id: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)


class HotelCalendar(Base):
    __tablename__ = "hotel_calendars"

    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), primary_key=True)
    stay_date: Mapped[date] = mapped_column(Date, primary_key=True)
    available: Mapped[bool] = mapped_column(Boolean)
    min_length_of_stay: Mapped[int] = mapped_column(Integer, default=1)
    avg_price_display: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoomSnapshot(Base):
    __tablename__ = "room_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("id", "scanned_at"),
        Index("ix_room_snapshots_hotel_date_time", "hotel_id", "stay_date", "scanned_at"),
        {"postgresql_partition_by": "RANGE (scanned_at)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    probe_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("probes.id"))
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"))
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))
    stay_date: Mapped[date] = mapped_column(Date)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rooms_left: Mapped[int | None] = mapped_column(Integer)
    stock_confidence: Mapped[str] = mapped_column(String(16))
    badge_count: Mapped[int | None] = mapped_column(Integer)
    dropdown_max: Mapped[int | None] = mapped_column(Integer)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_refundable_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    rates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class ScrapeSessionRow(Base):
    __tablename__ = "scrape_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    proxy_id: Mapped[str] = mapped_column(String(128))
    proxy_country: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
```

- [x] **Step 6: Viết `backend/app/db/partitions.py`**

```python
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


def month_range(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


def partition_name(d: date) -> str:
    return f"room_snapshots_{d:%Y_%m}"


async def ensure_room_snapshot_partitions(
    conn: AsyncConnection, first_month: date, months: int = 3
) -> list[str]:
    """Tạo partition theo tháng cho room_snapshots, bắt đầu từ tháng của first_month.
    Trả về danh sách partition vừa tạo mới."""
    created: list[str] = []
    start, end = month_range(first_month)
    for _ in range(months):
        name = partition_name(start)
        exists = await conn.execute(
            text("select 1 from pg_class where relname = :n").bindparams(n=name)
        )
        if exists.first() is None:
            await conn.execute(
                text(
                    f"CREATE TABLE {name} PARTITION OF room_snapshots "
                    f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
                )
            )
            created.append(name)
        start, end = month_range(end)
    return created
```

- [x] **Step 7: Viết `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [x] **Step 8: Viết `backend/alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [x] **Step 9: Viết `backend/alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [x] **Step 10: Viết migration `backend/alembic/versions/0001_phase1_tables.py`**

```python
"""phase1 tables

Revision ID: 0001
Revises:
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("scan_times", postgresql.ARRAY(sa.String(5)), nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("insight_language", sa.String(8), nullable=False),
        sa.Column("insight_hour", sa.String(5), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "hotels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("booking_url", sa.Text, nullable=False),
        sa.Column("booking_slug", sa.String(200), nullable=False, unique=True),
        sa.Column("booking_hotel_id", sa.String(32)),
        sa.Column("name", sa.String(300)),
        sa.Column("city", sa.String(120)),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("star_rating", sa.Numeric(2, 1)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tenant_hotels",
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("label", sa.String(120)),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "room_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("booking_room_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("max_occupancy", sa.Integer),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("hotel_id", "booking_room_id"),
    )
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trigger_key", sa.String(32), nullable=False, unique=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_jobs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_probes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ok_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sold_out_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "scan_jobs",
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), primary_key=True),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "probes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), nullable=False),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("stay_date", sa.Date, nullable=False),
        sa.Column("checkin", sa.Date, nullable=False),
        sa.Column("checkout", sa.Date, nullable=False),
        sa.Column("nights", sa.Integer, nullable=False),
        sa.Column("adults", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("method", sa.String(16)),
        sa.Column("proxy_country", sa.String(2)),
        sa.Column("session_id", sa.String(64)),
        sa.Column("http_status", sa.Integer),
        sa.Column("raw_object_key", sa.Text),
        sa.Column("parser_version", sa.String(16)),
        sa.Column("error", sa.Text),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("scan_run_id", "hotel_id", "stay_date"),
    )
    op.create_index("ix_probes_hotel_date_fetched", "probes", ["hotel_id", "stay_date", "fetched_at"])
    op.create_table(
        "hotel_calendars",
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), primary_key=True),
        sa.Column("scan_run_id", sa.Integer, sa.ForeignKey("scan_runs.id"), primary_key=True),
        sa.Column("stay_date", sa.Date, primary_key=True),
        sa.Column("available", sa.Boolean, nullable=False),
        sa.Column("min_length_of_stay", sa.Integer, nullable=False, server_default="1"),
        sa.Column("avg_price_display", sa.String(64)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "room_snapshots",
        sa.Column("id", sa.BigInteger, sa.Identity(), nullable=False),
        sa.Column("probe_id", sa.BigInteger, sa.ForeignKey("probes.id"), nullable=False),
        sa.Column("hotel_id", sa.Integer, sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("room_type_id", sa.Integer, sa.ForeignKey("room_types.id"), nullable=False),
        sa.Column("stay_date", sa.Date, nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rooms_left", sa.Integer),
        sa.Column("stock_confidence", sa.String(16), nullable=False),
        sa.Column("badge_count", sa.Integer),
        sa.Column("dropdown_max", sa.Integer),
        sa.Column("min_price", sa.Numeric(14, 2)),
        sa.Column("min_refundable_price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("rates", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id", "scanned_at"),
        postgresql_partition_by="RANGE (scanned_at)",
    )
    op.create_index(
        "ix_room_snapshots_hotel_date_time",
        "room_snapshots",
        ["hotel_id", "stay_date", "scanned_at"],
    )
    op.execute(
        """
        DO $$
        DECLARE m date := date_trunc('month', now())::date;
        BEGIN
          FOR i IN 0..2 LOOP
            EXECUTE format(
              'CREATE TABLE IF NOT EXISTS room_snapshots_%s PARTITION OF room_snapshots '
              'FOR VALUES FROM (%L) TO (%L)',
              to_char(m + (i || ' month')::interval, 'YYYY_MM'),
              (m + (i || ' month')::interval)::date,
              (m + ((i + 1) || ' month')::interval)::date
            );
          END LOOP;
        END $$;
        """
    )
    op.create_table(
        "scrape_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("worker_id", sa.String(64), nullable=False),
        sa.Column("proxy_id", sa.String(128), nullable=False),
        sa.Column("proxy_country", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("request_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("block_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scrape_sessions")
    op.drop_table("room_snapshots")
    op.drop_table("hotel_calendars")
    op.drop_table("probes")
    op.drop_table("scan_jobs")
    op.drop_table("scan_runs")
    op.drop_table("room_types")
    op.drop_table("tenant_hotels")
    op.drop_table("hotels")
    op.drop_table("tenants")
```

- [x] **Step 11: Viết `backend/tests/conftest.py`**

```python
import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/scrapebooking_test"
)
FIXTURES_DIR = Path(__file__).parent / "fixtures"

ALL_TABLES = (
    "room_snapshots, hotel_calendars, probes, scan_jobs, scan_runs, room_types, "
    "tenant_hotels, hotels, tenants, scrape_sessions"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.fspath)
        if "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        if "/tests/live/" in path:
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def migrated_db_url() -> str:
    async def _ping() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(_ping())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"test database unavailable at {TEST_DB_URL}: {exc}")
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return TEST_DB_URL


@pytest.fixture
async def db(migrated_db_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {ALL_TABLES} RESTART IDENTITY CASCADE"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
```

- [x] **Step 12: Chạy migration thật và test**

Run: `cd backend && uv run alembic upgrade head && uv run pytest tests/unit/test_partitions.py tests/integration/test_migrations.py -q`
Expected: alembic in `Running upgrade  -> 0001, phase1 tables`; pytest `5 passed`

- [x] **Step 13: Commit**

```bash
git add backend/app/db backend/alembic.ini backend/alembic backend/tests/conftest.py backend/tests/unit/test_partitions.py backend/tests/integration/test_migrations.py
git commit -m "feat(db): phase 1 schema, alembic, monthly partitions for room_snapshots"
```

---

### Task 6: RawStore lưu HTML thô vào MinIO

**Files:**
- Create: `backend/app/collector/__init__.py`, `backend/app/collector/storage.py`
- Test: `backend/tests/unit/test_storage.py`, `backend/tests/integration/test_storage_minio.py`

- [x] **Step 1: Viết test unit với moto (thất bại)**

`backend/tests/unit/test_storage.py`:

```python
from datetime import UTC, date, datetime

import pytest
from moto import mock_aws

from app.collector.storage import MemoryRawStore, S3RawStore, raw_key


def test_raw_key_layout() -> None:
    key = raw_key(
        scan_run_id=7,
        hotel_id=42,
        stay_date=date(2026, 10, 5),
        fetched_at=datetime(2026, 9, 24, 6, 5, tzinfo=UTC),
    )
    assert key == "2026/09/24/run7/hotel42/2026-10-05.html.gz"


async def test_memory_store_roundtrip() -> None:
    store = MemoryRawStore()
    await store.put_html("a/b.html.gz", "<html>x</html>")
    assert await store.get_html("a/b.html.gz") == "<html>x</html>"
    assert await store.get_html("missing") is None


@pytest.fixture
def aws_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


async def test_s3_store_roundtrip_with_moto(aws_env: None) -> None:
    with mock_aws():
        store = S3RawStore(
            bucket="raw-html", endpoint_url=None, access_key="testing", secret_key="testing"
        )
        await store.ensure_bucket()
        await store.put_html("2026/09/24/run1/hotel1/2026-10-01.html.gz", "<html>hi</html>")
        assert await store.get_html("2026/09/24/run1/hotel1/2026-10-01.html.gz") == "<html>hi</html>"
        assert await store.get_html("nope") is None
        rules = store._client.get_bucket_lifecycle_configuration(Bucket="raw-html")["Rules"]
        assert rules[0]["Expiration"]["Days"] == 30
```

- [x] **Step 2: Viết test integration với MinIO thật**

`backend/tests/integration/test_storage_minio.py`:

```python
import uuid

from app.collector.storage import S3RawStore
from app.config import Settings


async def test_minio_roundtrip() -> None:
    s = Settings(_env_file=None, database_url="x", redis_url="x", proxy_url_template="x")
    store = S3RawStore(
        bucket=s.minio_bucket,
        endpoint_url=s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
    )
    await store.ensure_bucket()
    key = f"test/{uuid.uuid4()}.html.gz"
    await store.put_html(key, "<html>minio</html>")
    assert await store.get_html(key) == "<html>minio</html>"
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_storage.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.collector'`

- [x] **Step 4: Viết `backend/app/collector/storage.py`** (`backend/app/collector/__init__.py` rỗng)

```python
import asyncio
import gzip
from datetime import date, datetime
from typing import Any, Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


def raw_key(scan_run_id: int, hotel_id: int, stay_date: date, fetched_at: datetime) -> str:
    return f"{fetched_at:%Y/%m/%d}/run{scan_run_id}/hotel{hotel_id}/{stay_date.isoformat()}.html.gz"


class RawStore(Protocol):
    async def put_html(self, key: str, html: str) -> None: ...
    async def get_html(self, key: str) -> str | None: ...


class MemoryRawStore:
    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    async def put_html(self, key: str, html: str) -> None:
        self.items[key] = html

    async def get_html(self, key: str) -> str | None:
        return self.items.get(key)


class S3RawStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        retention_days: int = 30,
    ) -> None:
        self._bucket = bucket
        self._retention_days = retention_days
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=BotoConfig(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    def _ensure_bucket_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
        # HTML thô chỉ giữ `retention_days` ngày (spec mục 5.4), MinIO tự xoá.
        self._client.put_bucket_lifecycle_configuration(
            Bucket=self._bucket,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "expire-raw-html",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Expiration": {"Days": self._retention_days},
                    }
                ]
            },
        )

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def put_html(self, key: str, html: str) -> None:
        body = gzip.compress(html.encode("utf-8"))
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="text/html; charset=utf-8",
            ContentEncoding="gzip",
        )

    def _get_sync(self, key: str) -> str | None:
        try:
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return gzip.decompress(obj["Body"].read()).decode("utf-8")

    async def get_html(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_sync, key)
```

- [x] **Step 5: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_storage.py tests/integration/test_storage_minio.py -q`
Expected: `4 passed`

- [x] **Step 6: Commit**

```bash
git add backend/app/collector backend/tests/unit/test_storage.py backend/tests/integration/test_storage_minio.py
git commit -m "feat(collector): raw html store on MinIO with memory fake"
```

---

### Task 7: ProxyProvider

**Files:**
- Create: `backend/app/collector/proxy.py`
- Test: `backend/tests/unit/test_proxy.py`

- [x] **Step 1: Viết test (thất bại)**

`backend/tests/unit/test_proxy.py`:

```python
from app.collector.proxy import StaticProxyProvider


def test_static_provider_builds_sticky_endpoint() -> None:
    provider = StaticProxyProvider(
        "http://u-country-{country}-session-{session}:p@gate.example.com:7777",
        id_factory=lambda: "abc123",
    )
    ep = provider.new_endpoint("vn")
    assert ep.server == "http://gate.example.com:7777"
    assert ep.username == "u-country-vn-session-abc123"
    assert ep.password == "p"
    assert ep.country == "vn"
    assert ep.session_id == "abc123"
    assert ep.url == "http://u-country-vn-session-abc123:p@gate.example.com:7777"
    assert ep.id == "vn:abc123"


def test_new_endpoint_gets_new_session_id_each_time() -> None:
    provider = StaticProxyProvider("http://u-{country}-{session}:p@h:1")
    a = provider.new_endpoint("vn")
    b = provider.new_endpoint("vn")
    assert a.session_id != b.session_id


def test_template_without_credentials() -> None:
    provider = StaticProxyProvider("http://h:1?c={country}&s={session}", id_factory=lambda: "s1")
    ep = provider.new_endpoint("th")
    assert ep.username is None
    assert ep.password is None
    assert ep.url == "http://h:1?c=th&s=s1"
```

- [x] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_proxy.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.collector.proxy'`

- [x] **Step 3: Viết `backend/app/collector/proxy.py`**

```python
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProxyEndpoint:
    server: str  # scheme://host:port, không kèm thông tin đăng nhập
    username: str | None
    password: str | None
    country: str
    session_id: str
    url: str  # URL đầy đủ cho HTTP client

    @property
    def id(self) -> str:
        return f"{self.country}:{self.session_id}"


class ProxyProvider(Protocol):
    def new_endpoint(self, country: str) -> ProxyEndpoint: ...


class StaticProxyProvider:
    """Sinh endpoint từ template có {country} và {session}.

    Ví dụ: http://USER-country-{country}-session-{session}:PASS@gate.provider.com:7777
    Mỗi lần gọi new_endpoint tạo session id mới, nghĩa là IP residential mới (sticky).
    """

    def __init__(
        self, template: str, id_factory: Callable[[], str] = lambda: secrets.token_hex(4)
    ) -> None:
        self._template = template
        self._id_factory = id_factory

    def new_endpoint(self, country: str) -> ProxyEndpoint:
        session_id = self._id_factory()
        url = self._template.format(country=country, session=session_id)
        parsed = urlparse(url)
        port = f":{parsed.port}" if parsed.port else ""
        return ProxyEndpoint(
            server=f"{parsed.scheme}://{parsed.hostname}{port}",
            username=parsed.username,
            password=parsed.password,
            country=country,
            session_id=session_id,
            url=url,
        )
```

- [x] **Step 4: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_proxy.py -q`
Expected: `3 passed`

- [x] **Step 5: Commit**

```bash
git add backend/app/collector/proxy.py backend/tests/unit/test_proxy.py
git commit -m "feat(collector): proxy provider with sticky session endpoints"
```

---

### Task 8: ScrapeSession, SessionManager, PlaywrightBootstrapper

**Files:**
- Create: `backend/app/collector/session.py`, `backend/app/collector/booking/__init__.py`, `backend/app/collector/booking/selectors.py`, `backend/app/collector/booking/playwright_bootstrap.py`
- Test: `backend/tests/unit/test_session.py`, `backend/tests/unit/test_selectors_csrf.py`, `backend/tests/live/test_bootstrap_live.py`

- [x] **Step 1: Viết test SessionManager với bootstrapper giả (thất bại)**

`backend/tests/unit/test_session.py`:

```python
from datetime import UTC, datetime, timedelta

from app.clock import FixedClock
from app.collector.proxy import ProxyEndpoint, StaticProxyProvider
from app.collector.session import (
    BootstrapResult,
    ScrapeSession,
    SessionManager,
)


class FakeBootstrapper:
    def __init__(self) -> None:
        self.calls: list[tuple[ProxyEndpoint, str]] = []

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        self.calls.append((proxy, warmup_url))
        return BootstrapResult(
            cookies={"aws-waf-token": f"tok-{len(self.calls)}"},
            user_agent="Mozilla/5.0 Chrome/128",
            csrf_token="csrf-1",
            html="<html></html>",
        )


class RecordingListener:
    def __init__(self) -> None:
        self.created: list[ScrapeSession] = []
        self.retired: list[tuple[ScrapeSession, str]] = []

    async def session_created(self, session: ScrapeSession) -> None:
        self.created.append(session)

    async def session_retired(self, session: ScrapeSession, reason: str) -> None:
        self.retired.append((session, reason))


def _manager(clock: FixedClock, bootstrapper: FakeBootstrapper, listener: RecordingListener | None = None) -> SessionManager:
    return SessionManager(
        bootstrapper=bootstrapper,
        proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
        max_age=timedelta(minutes=20),
        max_requests=3,
        clock=clock,
        listener=listener,
    )


async def test_get_creates_and_reuses_session() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    a = await mgr.get("vn", "https://www.booking.com/hotel/vn/x.html")
    b = await mgr.get("vn", "https://www.booking.com/hotel/vn/x.html")
    assert a is b
    assert len(boot.calls) == 1
    assert boot.calls[0][0].country == "vn"
    assert a.cookies["aws-waf-token"] == "tok-1"
    assert a.user_agent.startswith("Mozilla")


async def test_sessions_are_per_country() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    vn = await mgr.get("vn", "u")
    th = await mgr.get("th", "u")
    assert vn is not th
    assert len(boot.calls) == 2


async def test_session_rotates_after_max_requests() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    s1 = await mgr.get("vn", "u")
    for _ in range(3):
        mgr.mark_request(s1)
    s2 = await mgr.get("vn", "u")
    assert s2 is not s1
    assert s2.cookies["aws-waf-token"] == "tok-2"


async def test_session_rotates_after_max_age() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    mgr = _manager(clock, boot)
    s1 = await mgr.get("vn", "u")
    clock.advance(minutes=21)
    s2 = await mgr.get("vn", "u")
    assert s2 is not s1


async def test_retire_forces_new_session_and_notifies_listener() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    boot = FakeBootstrapper()
    listener = RecordingListener()
    mgr = _manager(clock, boot, listener)
    s1 = await mgr.get("vn", "u")
    await mgr.retire(s1, reason="blocked")
    assert s1.retired is True
    assert s1.block_count == 1
    s2 = await mgr.get("vn", "u")
    assert s2 is not s1
    assert [s.id for s in listener.created] == [s1.id, s2.id]
    assert listener.retired == [(s1, "blocked")]
```

- [x] **Step 2: Viết test extract_csrf_token (thất bại)**

`backend/tests/unit/test_selectors_csrf.py`:

```python
from app.collector.booking.selectors import extract_csrf_token


def test_extract_csrf_single_quotes() -> None:
    html = "<script>var x = {b_csrf_token: 'abc.def-123'};</script>"
    assert extract_csrf_token(html) == "abc.def-123"


def test_extract_csrf_double_quotes_json_style() -> None:
    html = '<script>{"b_csrf_token": "tok_9"}</script>'
    assert extract_csrf_token(html) == "tok_9"


def test_extract_csrf_missing() -> None:
    assert extract_csrf_token("<html></html>") is None
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_session.py tests/unit/test_selectors_csrf.py -q`
Expected: FAIL với `ModuleNotFoundError`

- [x] **Step 4: Viết `backend/app/collector/booking/selectors.py`** (`backend/app/collector/booking/__init__.py` rỗng). Task 10 sẽ bổ sung thêm hằng số vào file này.

```python
import re

PARSER_VERSION = "1"

# Trang đã sẵn sàng (đã qua challenge) khi có một trong các phần tử này.
READY_SELECTOR = "#hprt-table, #hp_hotel_name, [data-testid='property-page-content'], input[name='ss']"

_CSRF_RE = re.compile(r"""["']?b_csrf_token["']?\s*:\s*["']([^"']+)["']""")


def extract_csrf_token(html: str) -> str | None:
    m = _CSRF_RE.search(html)
    return m.group(1) if m else None
```

- [x] **Step 5: Viết `backend/app/collector/session.py`**

```python
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from app.clock import Clock
from app.collector.proxy import ProxyEndpoint, ProxyProvider


@dataclass(frozen=True)
class BootstrapResult:
    cookies: dict[str, str]
    user_agent: str
    csrf_token: str | None
    html: str


class SessionBootstrapper(Protocol):
    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult: ...


@dataclass
class ScrapeSession:
    id: str
    proxy: ProxyEndpoint
    cookies: dict[str, str]
    user_agent: str
    csrf_token: str | None
    created_at: datetime
    request_count: int = 0
    block_count: int = 0
    retired: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def country(self) -> str:
        return self.proxy.country


class SessionListener(Protocol):
    async def session_created(self, session: ScrapeSession) -> None: ...
    async def session_retired(self, session: ScrapeSession, reason: str) -> None: ...


class SessionManager:
    """Giữ một session còn hạn cho mỗi nước. Làm mới khi hết tuổi, hết số request, hoặc bị thu hồi."""

    def __init__(
        self,
        bootstrapper: SessionBootstrapper,
        proxy_provider: ProxyProvider,
        max_age: timedelta,
        max_requests: int,
        clock: Clock,
        listener: SessionListener | None = None,
    ) -> None:
        self._bootstrapper = bootstrapper
        self._proxies = proxy_provider
        self._max_age = max_age
        self._max_requests = max_requests
        self._clock = clock
        self._listener = listener
        self._sessions: dict[str, ScrapeSession] = {}

    def _expired(self, s: ScrapeSession) -> bool:
        if s.retired:
            return True
        if s.request_count >= self._max_requests:
            return True
        return self._clock.now() - s.created_at > self._max_age

    async def get(self, country: str, warmup_url: str) -> ScrapeSession:
        current = self._sessions.get(country)
        if current is not None and not self._expired(current):
            return current
        if current is not None and not current.retired:
            await self.retire(current, reason="expired")
        return await self._create(country, warmup_url)

    async def _create(self, country: str, warmup_url: str) -> ScrapeSession:
        proxy = self._proxies.new_endpoint(country)
        result = await self._bootstrapper.bootstrap(proxy, warmup_url)
        session = ScrapeSession(
            id=uuid.uuid4().hex[:16],
            proxy=proxy,
            cookies=result.cookies,
            user_agent=result.user_agent,
            csrf_token=result.csrf_token,
            created_at=self._clock.now(),
        )
        self._sessions[country] = session
        if self._listener:
            await self._listener.session_created(session)
        return session

    def mark_request(self, session: ScrapeSession) -> None:
        session.request_count += 1

    async def retire(self, session: ScrapeSession, reason: str) -> None:
        if session.retired:
            return
        session.retired = True
        if reason == "blocked":
            session.block_count += 1
        if self._sessions.get(session.country) is session:
            del self._sessions[session.country]
        if self._listener:
            await self._listener.session_retired(session, reason)

    @property
    def expires_after(self) -> timedelta:
        return self._max_age
```

- [x] **Step 6: Viết `backend/app/collector/booking/playwright_bootstrap.py`**

```python
import asyncio

from playwright.async_api import Page, async_playwright

from app.collector.booking.selectors import READY_SELECTOR, extract_csrf_token
from app.collector.proxy import ProxyEndpoint
from app.collector.session import BootstrapResult
from app.logging import get_logger

log = get_logger(__name__)


class ChallengeNotSolved(RuntimeError):
    pass


async def wait_until_ready(page: Page, timeout_ms: int, poll_ms: int = 1000) -> None:
    waited = 0
    while waited <= timeout_ms:
        if await page.locator(READY_SELECTOR).count() > 0:
            return
        await asyncio.sleep(poll_ms / 1000)
        waited += poll_ms
    raise ChallengeNotSolved(f"page not ready after {timeout_ms}ms: {page.url}")


class PlaywrightBootstrapper:
    """Mở Chromium thật qua proxy, vượt challenge AWS WAF, trả cookie + UA + csrf."""

    def __init__(self, headless: bool = True, challenge_timeout_ms: int = 45_000) -> None:
        self._headless = headless
        self._timeout_ms = challenge_timeout_ms

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self._headless,
                proxy={
                    "server": proxy.server,
                    "username": proxy.username or "",
                    "password": proxy.password or "",
                },
            )
            try:
                context = await browser.new_context(
                    locale="en-GB", viewport={"width": 1366, "height": 850}
                )
                page = await context.new_page()
                await page.goto(warmup_url, wait_until="domcontentloaded", timeout=60_000)
                await wait_until_ready(page, self._timeout_ms)
                html = await page.content()
                cookies = {c["name"]: c["value"] for c in await context.cookies()}
                user_agent: str = await page.evaluate("() => navigator.userAgent")
                log.info("session_bootstrapped", proxy=proxy.id, cookies=len(cookies))
                return BootstrapResult(
                    cookies=cookies,
                    user_agent=user_agent,
                    csrf_token=extract_csrf_token(html),
                    html=html,
                )
            finally:
                await browser.close()
```

- [x] **Step 7: Viết test live**

`backend/tests/live/test_bootstrap_live.py`:

```python
import pytest

from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.proxy import StaticProxyProvider
from app.config import get_settings


@pytest.mark.live
async def test_bootstrap_real_booking() -> None:
    s = get_settings()
    proxy = StaticProxyProvider(s.proxy_url_template).new_endpoint("vn")
    result = await PlaywrightBootstrapper(headless=s.playwright_headless).bootstrap(
        proxy, "https://www.booking.com/hotel/vn/the-reverie-saigon.html"
    )
    assert "Chrome" in result.user_agent
    assert len(result.cookies) > 0
    assert "hprt-table" in result.html or "hp_hotel_name" in result.html
```

- [x] **Step 8: Chạy unit test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_session.py tests/unit/test_selectors_csrf.py -q`
Expected: `8 passed`

- [ ] **Step 9: Chạy test live một lần (cần PROXY_URL_TEMPLATE thật trong `.env`)**

Run: `cd backend && uv run pytest tests/live/test_bootstrap_live.py -m live -q -s`
Expected: `1 passed`. Nếu `ChallengeNotSolved`: chạy lại với `PLAYWRIGHT_HEADLESS=false` để xem challenge có đòi captcha không, đổi proxy nếu IP bị đánh dấu.

- [x] **Step 10: Commit**

```bash
git add backend/app/collector/session.py backend/app/collector/booking backend/tests/unit/test_session.py backend/tests/unit/test_selectors_csrf.py backend/tests/live/test_bootstrap_live.py
git commit -m "feat(collector): session manager and playwright bootstrapper"
```

---

### Task 9: Fetcher curl_cffi, phân loại chặn, RateLimiter

**Files:**
- Create: `backend/app/collector/fetch.py`, `backend/app/collector/ratelimit.py`
- Test: `backend/tests/unit/test_fetch_classify.py`, `backend/tests/unit/test_ratelimit.py`

- [x] **Step 1: Viết test classify_response (thất bại)**

`backend/tests/unit/test_fetch_classify.py`:

```python
import pytest

from app.collector.fetch import FetchOutcome, classify_response


@pytest.mark.parametrize(
    "status,text,expected",
    [
        (200, "<html><table id='hprt-table'></table></html>", FetchOutcome.OK),
        (403, "", FetchOutcome.BLOCKED),
        (429, "", FetchOutcome.BLOCKED),
        (503, "", FetchOutcome.BLOCKED),
        (202, "<html>challenge</html>", FetchOutcome.BLOCKED),
        (200, "<script src='https://x.awswaf.com/challenge.js'></script>", FetchOutcome.BLOCKED),
        (200, "<title>Pardon Our Interruption</title>", FetchOutcome.BLOCKED),
        (404, "", FetchOutcome.NOT_FOUND),
        (500, "", FetchOutcome.ERROR),
    ],
)
def test_classify(status: int, text: str, expected: FetchOutcome) -> None:
    assert classify_response(status, text) == expected
```

- [x] **Step 2: Viết test RateLimiter (thất bại)**

`backend/tests/unit/test_ratelimit.py`:

```python
from app.collector.ratelimit import RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


async def test_first_call_does_not_wait() -> None:
    ft = FakeTime()
    rl = RateLimiter(min_interval=2.0, jitter=0.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.0)
    await rl.wait("s1")
    assert ft.sleeps == []


async def test_second_call_waits_remaining_interval() -> None:
    ft = FakeTime()
    rl = RateLimiter(min_interval=2.0, jitter=0.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.0)
    await rl.wait("s1")
    ft.t += 0.5
    await rl.wait("s1")
    assert ft.sleeps == [1.5]


async def test_jitter_added() -> None:
    ft = FakeTime()
    rl = RateLimiter(min_interval=2.0, jitter=1.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.5)
    await rl.wait("s1")
    await rl.wait("s1")
    assert ft.sleeps == [2.5]


async def test_keys_are_independent() -> None:
    ft = FakeTime()
    rl = RateLimiter(min_interval=2.0, jitter=0.0, sleep=ft.sleep, monotonic=ft.monotonic, rng=lambda: 0.0)
    await rl.wait("s1")
    await rl.wait("s2")
    assert ft.sleeps == []
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_fetch_classify.py tests/unit/test_ratelimit.py -q`
Expected: FAIL với `ModuleNotFoundError`

- [x] **Step 4: Viết `backend/app/collector/ratelimit.py`**

```python
import asyncio
import random
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Giữ khoảng cách tối thiểu giữa hai request cùng key (key = session id)."""

    def __init__(
        self,
        min_interval: float,
        jitter: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._min = min_interval
        self._jitter = jitter
        self._sleep = sleep
        self._now = monotonic
        self._rng = rng
        self._last: dict[str, float] = {}

    async def wait(self, key: str) -> None:
        last = self._last.get(key)
        if last is not None:
            due = last + self._min + self._rng() * self._jitter
            remaining = due - self._now()
            if remaining > 0:
                await self._sleep(remaining)
        self._last[key] = self._now()
```

- [x] **Step 5: Viết `backend/app/collector/fetch.py`**

```python
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.collector.session import ScrapeSession


class FetchOutcome(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    ERROR = "error"


BLOCK_MARKERS = (
    "awswaf",
    "aws-waf",
    "challenge.js",
    "captcha-delivery",
    "pardon our interruption",
    "verify you are a human",
    "access denied",
)


def classify_response(status: int, text: str) -> FetchOutcome:
    if status in (403, 429, 503, 202):
        return FetchOutcome.BLOCKED
    if status == 404:
        return FetchOutcome.NOT_FOUND
    head = text[:20_000].lower()
    if any(marker in head for marker in BLOCK_MARKERS):
        return FetchOutcome.BLOCKED
    if status >= 400:
        return FetchOutcome.ERROR
    return FetchOutcome.OK


@dataclass(frozen=True)
class FetchResponse:
    status: int
    text: str
    url: str
    elapsed_ms: int

    @property
    def outcome(self) -> FetchOutcome:
        return classify_response(self.status, self.text)


class Fetcher(Protocol):
    async def get(self, url: str, session: ScrapeSession) -> FetchResponse: ...
    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], session: ScrapeSession
    ) -> FetchResponse: ...
    async def close(self, session_id: str) -> None: ...


class CurlFetcher:
    """HTTP client giả lập TLS fingerprint Chrome, dùng cookie và proxy của ScrapeSession.
    Một AsyncSession curl_cffi cho mỗi ScrapeSession, đóng khi session bị thu hồi."""

    def __init__(self, timeout_s: float = 30.0, impersonate: str = "chrome") -> None:
        self._timeout = timeout_s
        self._impersonate = impersonate
        self._clients: dict[str, Any] = {}

    def _client(self, session: ScrapeSession) -> Any:
        client = self._clients.get(session.id)
        if client is None:
            from curl_cffi.requests import AsyncSession

            client = AsyncSession(
                impersonate=self._impersonate,
                proxies={"http": session.proxy.url, "https": session.proxy.url},
                timeout=self._timeout,
            )
            self._clients[session.id] = client
        return client

    @staticmethod
    def _base_headers(session: ScrapeSession) -> dict[str, str]:
        return {
            "User-Agent": session.user_agent,
            "Accept-Language": "en-GB,en;q=0.9",
        }

    async def get(self, url: str, session: ScrapeSession) -> FetchResponse:
        headers = self._base_headers(session) | {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }
        t0 = time.monotonic()
        r = await self._client(session).get(url, headers=headers, cookies=session.cookies)
        return FetchResponse(
            status=r.status_code,
            text=r.text,
            url=str(r.url),
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], session: ScrapeSession
    ) -> FetchResponse:
        merged = self._base_headers(session) | {"Content-Type": "application/json"} | headers
        t0 = time.monotonic()
        r = await self._client(session).post(
            url, json=payload, headers=merged, cookies=session.cookies
        )
        return FetchResponse(
            status=r.status_code,
            text=r.text,
            url=str(r.url),
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )

    async def close(self, session_id: str) -> None:
        client = self._clients.pop(session_id, None)
        if client is not None:
            await client.close()

    async def close_all(self) -> None:
        for sid in list(self._clients):
            await self.close(sid)
```

- [x] **Step 6: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_fetch_classify.py tests/unit/test_ratelimit.py -q`
Expected: `13 passed`

- [x] **Step 7: Commit**

```bash
git add backend/app/collector/fetch.py backend/app/collector/ratelimit.py backend/tests/unit/test_fetch_classify.py backend/tests/unit/test_ratelimit.py
git commit -m "feat(collector): curl_cffi fetcher, block classification, rate limiter"
```

---

### Task 10: URL trang khách sạn, parser, fixture thật

Đây là task phụ thuộc vào giao diện thật của Booking.com. Selector trong `selectors.py` là điểm xuất phát dựa trên bảng phòng `#hprt-table` mà Booking dùng nhiều năm. Bước 4 dùng script khám phá để xác nhận từng selector trên fixture thật; nếu selector nào cho 0 kết quả thì sửa hằng số trong `selectors.py`, không sửa parser.

**Files:**
- Create: `backend/app/collector/booking/urls.py`, `backend/app/collector/booking/parser.py`
- Modify: `backend/app/collector/booking/selectors.py`
- Create: `backend/scripts/capture_fixture.py`, `backend/scripts/explore_fixture.py`
- Create: `backend/tests/fixtures/html/available_with_badge.html`, `available_no_badge.html`, `sold_out.html` và ba file `.expected.json` tương ứng
- Test: `backend/tests/unit/test_urls.py`, `backend/tests/unit/test_price.py`, `backend/tests/unit/test_parser.py`

- [x] **Step 1: Viết test build_hotel_url và currency_for (thất bại)**

`backend/tests/unit/test_urls.py`:

```python
from datetime import date

from app.collector.booking.urls import build_hotel_url, currency_for
from app.domain.models import HotelRef

HOTEL = HotelRef(id=1, country_code="vn", slug="vn/the-reverie-saigon",
                 canonical_url="https://www.booking.com/hotel/vn/the-reverie-saigon.html")


def test_build_hotel_url() -> None:
    url = build_hotel_url(HOTEL, checkin=date(2026, 10, 5), nights=2, adults=2, currency="VND")
    assert url == (
        "https://www.booking.com/hotel/vn/the-reverie-saigon.en-gb.html"
        "?checkin=2026-10-05&checkout=2026-10-07&group_adults=2&no_rooms=1"
        "&group_children=0&selected_currency=VND&lang=en-gb"
    )


def test_currency_for_known_and_default() -> None:
    assert currency_for("vn") == "VND"
    assert currency_for("th") == "THB"
    assert currency_for("zz") == "USD"
```

- [x] **Step 2: Viết test parse_price (thất bại)**

`backend/tests/unit/test_price.py`:

```python
from decimal import Decimal

import pytest

from app.collector.booking.parser import parse_price


@pytest.mark.parametrize(
    "text,fallback,price,currency",
    [
        ("VND 3,450,000", "VND", Decimal("3450000"), "VND"),
        ("VND\xa03.450.000", "VND", Decimal("3450000"), "VND"),
        ("US$120", "USD", Decimal("120"), "USD"),
        ("€ 1,234.50", "EUR", Decimal("1234.50"), "EUR"),
        ("₫ 950,000", "VND", Decimal("950000"), "VND"),
        ("Price 2,500", "THB", Decimal("2500"), "THB"),
        ("1.234,56 zł", "PLN", Decimal("1234.56"), "PLN"),
    ],
)
def test_parse_price(text: str, fallback: str, price: Decimal, currency: str) -> None:
    assert parse_price(text, fallback_currency=fallback) == (price, currency)


def test_parse_price_no_number() -> None:
    assert parse_price("Sold out", fallback_currency="VND") is None
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_urls.py tests/unit/test_price.py -q`
Expected: FAIL với `ModuleNotFoundError`

- [x] **Step 4: Viết `backend/app/collector/booking/urls.py`**

```python
from datetime import date, timedelta

from app.domain.models import HotelRef

COUNTRY_CURRENCY: dict[str, str] = {
    "vn": "VND", "th": "THB", "sg": "SGD", "my": "MYR", "id": "IDR", "ph": "PHP",
    "kh": "USD", "la": "USD", "jp": "JPY", "kr": "KRW", "cn": "CNY", "hk": "HKD",
    "tw": "TWD", "au": "AUD", "nz": "NZD", "us": "USD", "ca": "CAD", "gb": "GBP",
    "fr": "EUR", "de": "EUR", "it": "EUR", "es": "EUR", "nl": "EUR", "pt": "EUR",
    "ae": "AED", "in": "INR",
}


def currency_for(country_code: str) -> str:
    return COUNTRY_CURRENCY.get(country_code.lower(), "USD")


def build_hotel_url(hotel: HotelRef, checkin: date, nights: int, adults: int, currency: str) -> str:
    checkout = checkin + timedelta(days=nights)
    return (
        f"https://www.booking.com/hotel/{hotel.slug}.en-gb.html"
        f"?checkin={checkin.isoformat()}&checkout={checkout.isoformat()}"
        f"&group_adults={adults}&no_rooms=1&group_children=0"
        f"&selected_currency={currency}&lang=en-gb"
    )
```

- [x] **Step 5: Bổ sung hằng số vào `backend/app/collector/booking/selectors.py`** (giữ nguyên phần đã có từ Task 8, thêm vào cuối)

```python
# ---- Bảng phòng ----
ROOM_TABLE = "#hprt-table"
ROOM_ROWS = "#hprt-table tr[data-block-id]"
ROOM_TYPE_CELL = "td.hprt-table-cell-roomtype"      # chỉ có ở dòng đầu của mỗi loại phòng
ROOM_NAME_LINK = "a.hprt-roomtype-link"             # có data-room-id
ROOM_NAME_TEXT = "span.hprt-roomtype-icon-link"
OCCUPANCY_CELL = "td.hprt-table-cell-occupancy"
PRICE_CELL = "td.hprt-table-cell-price"
PRICE_TEXT = (
    "span.prco-valign-middle-helper, "
    "[data-testid='price-and-discounted-price'], "
    ".bui-price-display__value"
)
CONDITIONS_CELL = "td.hprt-table-cell-conditions"
ONLY_X_LEFT = ".only_x_left, .hprt-table-cell-conditions .urgency_message, [data-testid='availability-scarcity']"
ROOM_SELECT = "select.hprt-nos-select"

# ---- Trang ----
SOLD_OUT_MARKERS = "#no_availability_message, .hprt-no-rooms-available, [data-testid='property-sold-out']"
HOTEL_NAME = "#hp_hotel_name, h2.pp-header__title, [data-testid='property-page-title']"

ONLY_X_LEFT_RE = re.compile(r"only\s+(\d+)\s+(?:rooms?\s+)?left", re.IGNORECASE)
HOTEL_ID_RE = re.compile(r"""b_hotel_id\s*[:=]\s*['"]?(\d+)""")
MAX_PEOPLE_RE = re.compile(r"(\d+)")
```

- [x] **Step 6: Viết `backend/scripts/capture_fixture.py`** (dùng bootstrapper của Task 8 để lấy HTML thật qua trình duyệt)

```python
"""Lưu HTML thật của trang khách sạn Booking làm fixture.

Dùng: uv run python scripts/capture_fixture.py <booking_hotel_url> <checkin YYYY-MM-DD> <nights> <tên_fixture>
Ví dụ: uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/the-reverie-saigon.html 2026-10-10 1 available_no_badge
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.booking.urls import build_hotel_url, currency_for
from app.collector.proxy import StaticProxyProvider
from app.config import get_settings
from app.domain.booking_url import parse_booking_url
from app.domain.models import HotelRef

OUT = Path(__file__).parent.parent / "tests" / "fixtures" / "html"


async def main(url: str, checkin: str, nights: str, name: str) -> None:
    s = get_settings()
    ref = parse_booking_url(url)
    hotel = HotelRef(id=0, country_code=ref.country_code, slug=ref.slug, canonical_url=ref.canonical_url)
    target = build_hotel_url(hotel, date.fromisoformat(checkin), int(nights), s.default_adults, currency_for(ref.country_code))
    proxy = StaticProxyProvider(s.proxy_url_template).new_endpoint(ref.country_code)
    result = await PlaywrightBootstrapper(headless=s.playwright_headless).bootstrap(proxy, target)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.html"
    path.write_text(result.html, encoding="utf-8")
    print(f"saved {path} ({len(result.html)} bytes) from {target}")


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:5]))
```

- [ ] **Step 7: Bắt 3 fixture thật**

Chọn một khách sạn lớn ở Việt Nam có nhiều loại phòng. Chạy ba lần với ngày khác nhau cho tới khi có đủ ba tình huống:

```bash
cd backend
uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/the-reverie-saigon.html 2026-10-10 1 available_no_badge
uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/the-reverie-saigon.html 2026-10-03 1 available_with_badge
uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/the-reverie-saigon.html 2026-12-31 1 sold_out
```

Mở từng file trong trình duyệt (File > Open) để xác nhận bằng mắt: file `available_with_badge` phải có ít nhất một dòng "Only N rooms left", file `sold_out` phải có thông báo hết phòng. Nếu ngày chọn không cho ra tình huống mong muốn, đổi ngày hoặc đổi khách sạn (khách sạn nhỏ dễ có badge và dễ hết phòng).

- [x] **Step 8: Viết `backend/scripts/explore_fixture.py`**

```python
"""In số lượng phần tử khớp từng selector trên một fixture để xác nhận selector còn đúng.

Dùng: uv run python scripts/explore_fixture.py tests/fixtures/html/available_with_badge.html
"""
import sys
from pathlib import Path

from selectolax.parser import HTMLParser

from app.collector.booking import selectors as S

CHECKS = {
    "ROOM_TABLE": S.ROOM_TABLE,
    "ROOM_ROWS": S.ROOM_ROWS,
    "ROOM_TYPE_CELL": S.ROOM_TYPE_CELL,
    "ROOM_NAME_LINK": S.ROOM_NAME_LINK,
    "ROOM_NAME_TEXT": S.ROOM_NAME_TEXT,
    "OCCUPANCY_CELL": S.OCCUPANCY_CELL,
    "PRICE_CELL": S.PRICE_CELL,
    "PRICE_TEXT": S.PRICE_TEXT,
    "CONDITIONS_CELL": S.CONDITIONS_CELL,
    "ONLY_X_LEFT": S.ONLY_X_LEFT,
    "ROOM_SELECT": S.ROOM_SELECT,
    "SOLD_OUT_MARKERS": S.SOLD_OUT_MARKERS,
    "HOTEL_NAME": S.HOTEL_NAME,
}


def main(path: str) -> None:
    html = Path(path).read_text(encoding="utf-8")
    tree = HTMLParser(html)
    print(f"file: {path}  bytes={len(html)}")
    print(f"csrf: {S.extract_csrf_token(html)}")
    m = S.HOTEL_ID_RE.search(html)
    print(f"hotel_id: {m.group(1) if m else None}")
    for name, sel in CHECKS.items():
        nodes = tree.css(sel)
        sample = [n.text(strip=True)[:60] for n in nodes[:3]]
        print(f"{name:18s} {len(nodes):4d}  {sample}")
    for sel in tree.css(S.ROOM_SELECT)[:3]:
        values = [o.attributes.get("value") for o in sel.css("option")]
        print(f"select options: {values}")
    for node in tree.css(S.ONLY_X_LEFT)[:5]:
        print(f"badge text: {node.text(strip=True)!r}")


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 9: Chạy khám phá trên cả 3 fixture, sửa selector nếu cần**

Run: `cd backend && for f in available_with_badge available_no_badge sold_out; do uv run python scripts/explore_fixture.py tests/fixtures/html/$f.html; echo; done`

Kỳ vọng với hai fixture available: `ROOM_ROWS` ≥ 1, `ROOM_TYPE_CELL` ≥ 1, `PRICE_TEXT` ≥ 1, `ROOM_SELECT` ≥ 1, `HOTEL_NAME` = 1, `hotel_id` là số. Với `available_with_badge`: `ONLY_X_LEFT` ≥ 1 và `badge text` có dạng "Only N rooms left". Với `sold_out`: `ROOM_ROWS` = 0 và `SOLD_OUT_MARKERS` ≥ 1.

Nếu một dòng cho 0 mà bằng mắt thấy trang có phần tử đó: mở fixture, tìm phần tử tương ứng, chép selector ổn định nhất (ưu tiên `id`, `data-testid`, rồi class có tên nghĩa) vào hằng số trong `selectors.py`, chạy lại script. Ghi lại giá trị `select options` lớn nhất thấy được trên khách sạn lớn: đó là trần dropdown; nếu khác 10, đặt `PAGE_DROPDOWN_CAP` trong `.env.example` và `config.py` theo giá trị đó.

- [x] **Step 10: Viết test parser (thất bại)**

`backend/tests/unit/test_parser.py`:

```python
import json
from pathlib import Path

import pytest

from app.collector.booking.parser import page_to_dict, parse_hotel_page
from app.domain.models import PageOutcome

FIXTURES = ["available_with_badge", "available_no_badge", "sold_out"]


def _load(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / "html" / f"{name}.html").read_text(encoding="utf-8")


def test_available_with_badge_has_exact_room(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "available_with_badge"), expected_currency="VND")
    assert page.outcome == PageOutcome.ROOMS
    assert page.booking_hotel_id and page.booking_hotel_id.isdigit()
    assert page.hotel_name
    assert page.csrf_token
    assert len(page.offers) >= 1
    assert any(o.badge_count is not None and o.badge_count >= 1 for o in page.offers)
    for offer in page.offers:
        assert offer.booking_room_id
        assert offer.name
        assert len(offer.rates) >= 1
        assert all(r.price > 0 and r.currency == "VND" for r in offer.rates)


def test_available_no_badge_has_dropdowns(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "available_no_badge"), expected_currency="VND")
    assert page.outcome == PageOutcome.ROOMS
    assert all(o.dropdown_max is not None and o.dropdown_max >= 1 for o in page.offers)


def test_sold_out_page(fixtures_dir: Path) -> None:
    page = parse_hotel_page(_load(fixtures_dir, "sold_out"), expected_currency="VND")
    assert page.outcome == PageOutcome.SOLD_OUT
    assert page.offers == ()


def test_empty_html_is_empty_outcome() -> None:
    page = parse_hotel_page("<html><body></body></html>", expected_currency="VND")
    assert page.outcome == PageOutcome.EMPTY


@pytest.mark.parametrize("name", FIXTURES)
def test_golden(fixtures_dir: Path, name: str) -> None:
    expected_path = fixtures_dir / "html" / f"{name}.expected.json"
    page = parse_hotel_page(_load(fixtures_dir, name), expected_currency="VND")
    assert page_to_dict(page) == json.loads(expected_path.read_text(encoding="utf-8"))
```

- [x] **Step 11: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_parser.py -q`
Expected: FAIL với `ImportError: cannot import name 'parse_hotel_page'`

- [x] **Step 12: Viết `backend/app/collector/booking/parser.py`**

```python
import re
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from typing import Any

from selectolax.parser import HTMLParser, Node

from app.collector.booking import selectors as S
from app.domain.models import PageOutcome, ParsedPage, RatePlan, RoomOffer

_SYMBOLS: dict[str, str] = {
    "US$": "USD", "$": "USD", "€": "EUR", "£": "GBP", "₫": "VND", "฿": "THB",
    "¥": "JPY", "₩": "KRW", "zł": "PLN", "S$": "SGD", "RM": "MYR", "Rp": "IDR", "₱": "PHP",
}
_NUMBER_RE = re.compile(r"\d[\d.,\s ]*\d|\d")
_CODE_RE = re.compile(r"\b([A-Z]{3})\b")


def parse_price(text: str, fallback_currency: str) -> tuple[Decimal, str] | None:
    cleaned = text.replace(" ", " ").strip()
    m = _NUMBER_RE.search(cleaned)
    if not m:
        return None
    raw = re.sub(r"\s", "", m.group(0))
    if "," in raw and "." in raw:
        dec_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if dec_sep == "," else ",", "").replace(dec_sep, ".")
    elif "," in raw:
        parts = raw.split(",")
        raw = raw.replace(",", "") if all(len(p) == 3 for p in parts[1:]) else raw.replace(",", ".")
    elif "." in raw:
        parts = raw.split(".")
        raw = raw.replace(".", "") if all(len(p) == 3 for p in parts[1:]) else raw
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    currency = fallback_currency
    code = _CODE_RE.search(cleaned)
    if code:
        currency = code.group(1)
    else:
        for symbol, iso in sorted(_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
            if symbol in cleaned:
                currency = iso
                break
    return value, currency


def _text(node: Node | None) -> str:
    return node.text(separator=" ", strip=True) if node is not None else ""


def _dropdown_max(row: Node) -> int | None:
    select = row.css_first(S.ROOM_SELECT)
    if select is None:
        return None
    values: list[int] = []
    for opt in select.css("option"):
        v = opt.attributes.get("value")
        if v is not None and v.strip().isdigit():
            values.append(int(v))
    return max(values) if values else None


def _badge_count(row: Node) -> int | None:
    for node in row.css(S.ONLY_X_LEFT):
        m = S.ONLY_X_LEFT_RE.search(_text(node))
        if m:
            return int(m.group(1))
    m = S.ONLY_X_LEFT_RE.search(_text(row))
    return int(m.group(1)) if m else None


def _rate_plan(row: Node, expected_currency: str) -> RatePlan | None:
    price_node = row.css_first(S.PRICE_TEXT)
    parsed = parse_price(_text(price_node), expected_currency) if price_node is not None else None
    if parsed is None:
        return None
    price, currency = parsed
    conditions = _text(row.css_first(S.CONDITIONS_CELL)).lower()
    refundable: bool | None
    if "non-refundable" in conditions or "non refundable" in conditions:
        refundable = False
    elif "free cancellation" in conditions:
        refundable = True
    else:
        refundable = None
    breakfast: bool | None = True if "breakfast included" in conditions else None
    name = "Non-refundable" if refundable is False else ("Free cancellation" if refundable else "Standard")
    if breakfast:
        name += " + breakfast"
    return RatePlan(name=name, price=price, currency=currency, refundable=refundable, breakfast=breakfast)


def _room_id(row: Node) -> str | None:
    link = row.css_first(S.ROOM_NAME_LINK)
    if link is not None and link.attributes.get("data-room-id"):
        return str(link.attributes["data-room-id"])
    block = row.attributes.get("data-block-id") or ""
    return block.split("_", 1)[0] or None


def _max_occupancy(row: Node) -> int | None:
    cell = row.css_first(S.OCCUPANCY_CELL)
    if cell is None:
        return None
    attr = cell.attributes.get("data-max-occupancy")
    if attr and attr.isdigit():
        return int(attr)
    m = S.MAX_PEOPLE_RE.search(_text(cell))
    return int(m.group(1)) if m else None


def parse_hotel_page(html: str, expected_currency: str) -> ParsedPage:
    tree = HTMLParser(html)
    hotel_id_match = S.HOTEL_ID_RE.search(html)
    booking_hotel_id = hotel_id_match.group(1) if hotel_id_match else None
    hotel_name = _text(tree.css_first(S.HOTEL_NAME)) or None
    csrf = S.extract_csrf_token(html)

    rows = tree.css(S.ROOM_ROWS)
    if not rows:
        outcome = PageOutcome.SOLD_OUT if tree.css_first(S.SOLD_OUT_MARKERS) else PageOutcome.EMPTY
        return ParsedPage(outcome, booking_hotel_id, hotel_name, csrf, ())

    groups: list[dict[str, Any]] = []
    for row in rows:
        type_cell = row.css_first(S.ROOM_TYPE_CELL)
        if type_cell is not None or not groups:
            groups.append(
                {
                    "id": _room_id(row),
                    "name": _text(row.css_first(S.ROOM_NAME_TEXT)) or _text(type_cell),
                    "occupancy": _max_occupancy(row),
                    "rows": [row],
                }
            )
        else:
            groups[-1]["rows"].append(row)

    offers: list[RoomOffer] = []
    for g in groups:
        if not g["id"] or not g["name"]:
            continue
        rates = tuple(r for r in (_rate_plan(row, expected_currency) for row in g["rows"]) if r)
        badge = next((b for b in (_badge_count(row) for row in g["rows"]) if b is not None), None)
        dropdowns = [d for d in (_dropdown_max(row) for row in g["rows"]) if d is not None]
        offers.append(
            RoomOffer(
                booking_room_id=g["id"],
                name=g["name"],
                max_occupancy=g["occupancy"],
                badge_count=badge,
                dropdown_max=max(dropdowns) if dropdowns else None,
                rates=rates,
            )
        )
    outcome = PageOutcome.ROOMS if offers else PageOutcome.EMPTY
    return ParsedPage(outcome, booking_hotel_id, hotel_name, csrf, tuple(offers))


def page_to_dict(page: ParsedPage) -> dict[str, Any]:
    d = asdict(page)
    d["outcome"] = str(page.outcome)
    for offer in d["offers"]:
        for rate in offer["rates"]:
            rate["price"] = str(rate["price"])
    return d
```

- [ ] **Step 13: Sinh golden file rồi soát bằng mắt**

Thêm vào cuối `backend/scripts/explore_fixture.py` một chế độ emit:

```python
def emit_expected(path: str) -> None:
    import json

    from app.collector.booking.parser import page_to_dict, parse_hotel_page

    html = Path(path).read_text(encoding="utf-8")
    page = parse_hotel_page(html, expected_currency="VND")
    out = Path(path).with_suffix("").with_suffix(".expected.json")
    out.write_text(json.dumps(page_to_dict(page), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}: outcome={page.outcome} offers={len(page.offers)}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--emit-expected":
        emit_expected(sys.argv[2])
    else:
        main(sys.argv[1])
```

Lưu ý khối `if __name__` cũ ở Step 8 phải thay bằng khối này.

Run: `cd backend && for f in available_with_badge available_no_badge sold_out; do uv run python scripts/explore_fixture.py --emit-expected tests/fixtures/html/$f.html; done`

Mở từng `.expected.json`, đối chiếu với trang HTML mở trong trình duyệt: tên phòng, số rate, giá, badge, dropdown. Nếu sai, sửa selector hoặc parser rồi emit lại. Chỉ commit golden khi đã đối chiếu.

- [x] **Step 14: Chạy toàn bộ test parser, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_urls.py tests/unit/test_price.py tests/unit/test_parser.py -q`
Expected: `17 passed`

- [x] **Step 15: Commit**

```bash
git add backend/app/collector/booking backend/scripts backend/tests/fixtures/html backend/tests/unit/test_urls.py backend/tests/unit/test_price.py backend/tests/unit/test_parser.py
git commit -m "feat(collector): booking hotel page parser with real fixtures"
```

---

### Task 11: Calendar GraphQL: dựng request và parse response

**Files:**
- Create: `backend/app/collector/booking/calendar.py`
- Test: `backend/tests/unit/test_calendar.py`

- [x] **Step 1: Viết test (thất bại)**

`backend/tests/unit/test_calendar.py`:

```python
import json
from datetime import date

from app.collector.booking.calendar import (
    GRAPHQL_URL,
    build_calendar_request,
    calendar_headers,
    parse_calendar_response,
)


def test_build_request_shape() -> None:
    req = build_calendar_request("the-reverie-saigon", date(2026, 10, 1), 30, adults=2)
    assert req["operationName"] == "AvailabilityCalendar"
    cfg = req["variables"]["input"]["searchConfig"]
    assert cfg["searchConfigDate"] == {"startDate": "2026-10-01", "amountOfDays": 30}
    assert cfg["nbAdults"] == 2
    assert cfg["nbRooms"] == 1
    assert req["variables"]["input"]["pagename"] == "the-reverie-saigon"
    assert "availabilityCalendar(input: $input)" in req["query"]
    assert GRAPHQL_URL.startswith("https://www.booking.com/dml/graphql")


def test_headers_include_csrf_and_referer() -> None:
    h = calendar_headers("tok", referer="https://www.booking.com/hotel/vn/x.html")
    assert h["x-booking-csrf-token"] == "tok"
    assert h["Referer"] == "https://www.booking.com/hotel/vn/x.html"
    assert h["x-booking-site-type-id"] == "1"


def test_parse_success() -> None:
    body = {
        "data": {
            "availabilityCalendar": {
                "hotelId": 123,
                "days": [
                    {"checkin": "2026-10-01", "available": True, "minLengthOfStay": 1, "avgPriceFormatted": "VND 3,000,000"},
                    {"checkin": "2026-10-02", "available": False, "minLengthOfStay": 0, "avgPriceFormatted": None},
                    {"checkin": "2026-10-03", "available": True, "minLengthOfStay": 2, "avgPriceFormatted": "VND 2,500,000"},
                ],
            }
        }
    }
    res = parse_calendar_response(json.dumps(body))
    assert res.ok
    assert len(res.days) == 3
    d1 = res.day(date(2026, 10, 1))
    assert d1 and d1.available and d1.min_length_of_stay == 1
    d2 = res.day(date(2026, 10, 2))
    assert d2 and not d2.available and d2.min_length_of_stay == 1
    d3 = res.day(date(2026, 10, 3))
    assert d3 and d3.min_length_of_stay == 2 and d3.avg_price_display == "VND 2,500,000"


def test_parse_error_payload() -> None:
    body = {"data": {"availabilityCalendar": {"message": "Hotel not found"}}}
    res = parse_calendar_response(json.dumps(body))
    assert not res.ok
    assert res.error == "Hotel not found"


def test_parse_garbage() -> None:
    res = parse_calendar_response("<html>challenge</html>")
    assert not res.ok
    assert res.error and "json" in res.error.lower()
```

- [x] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_calendar.py -q`
Expected: FAIL với `ModuleNotFoundError`

- [x] **Step 3: Viết `backend/app/collector/booking/calendar.py`**

```python
import json
from datetime import date
from typing import Any

from app.domain.models import CalendarDay, CalendarResult

GRAPHQL_URL = "https://www.booking.com/dml/graphql?lang=en-gb"

CALENDAR_QUERY = (
    "query AvailabilityCalendar($input: AvailabilityCalendarQueryInput!) {\n"
    "  availabilityCalendar(input: $input) {\n"
    "    ... on AvailabilityCalendarQueryResult {\n"
    "      hotelId\n"
    "      days { available avgPriceFormatted checkin minLengthOfStay __typename }\n"
    "      __typename\n"
    "    }\n"
    "    ... on AvailabilityCalendarQueryError { message __typename }\n"
    "    __typename\n"
    "  }\n"
    "}\n"
)


def build_calendar_request(pagename: str, start: date, days: int, adults: int) -> dict[str, Any]:
    return {
        "operationName": "AvailabilityCalendar",
        "variables": {
            "input": {
                "travelPurpose": 2,
                "pagename": pagename,
                "searchConfig": {
                    "searchConfigDate": {"startDate": start.isoformat(), "amountOfDays": days},
                    "nbAdults": adults,
                    "nbRooms": 1,
                },
            }
        },
        "extensions": {},
        "query": CALENDAR_QUERY,
    }


def calendar_headers(csrf_token: str | None, referer: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Origin": "https://www.booking.com",
        "Referer": referer,
        "x-booking-context-action-name": "hotel",
        "x-booking-csrf-token": csrf_token or "",
        "x-booking-site-type-id": "1",
        "x-booking-topic": "capla_browser_b-property-web-property-page",
    }


def parse_calendar_response(text: str) -> CalendarResult:
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return CalendarResult(ok=False, error=f"invalid json: {exc.msg}")
    node = (body.get("data") or {}).get("availabilityCalendar") if isinstance(body, dict) else None
    if not isinstance(node, dict):
        errors = body.get("errors") if isinstance(body, dict) else None
        return CalendarResult(ok=False, error=f"unexpected payload: {errors or text[:200]}")
    if "days" not in node:
        return CalendarResult(ok=False, error=str(node.get("message") or "no days in payload"))
    days: list[CalendarDay] = []
    for d in node["days"]:
        try:
            checkin = date.fromisoformat(d["checkin"])
        except (KeyError, ValueError):
            continue
        mls = d.get("minLengthOfStay") or 1
        days.append(
            CalendarDay(
                checkin=checkin,
                available=bool(d.get("available")),
                min_length_of_stay=max(1, int(mls)),
                avg_price_display=d.get("avgPriceFormatted"),
            )
        )
    return CalendarResult(ok=True, days=tuple(days))
```

- [x] **Step 4: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_calendar.py -q`
Expected: `5 passed`

- [x] **Step 5: Commit**

```bash
git add backend/app/collector/booking/calendar.py backend/tests/unit/test_calendar.py
git commit -m "feat(collector): availability calendar graphql request and parsing"
```

---

### Task 12: Collector interface, FakeCollector, BrowserCollector

**Files:**
- Create: `backend/app/collector/base.py`, `backend/app/collector/fake.py`, `backend/app/collector/booking/results.py`, `backend/app/collector/booking/browser.py`
- Test: `backend/tests/unit/test_results.py`, `backend/tests/unit/test_fake_collector.py`, `backend/tests/live/test_browser_live.py`

- [x] **Step 1: Viết test probe_result_from_page (thất bại)**

`backend/tests/unit/test_results.py`:

```python
from datetime import date
from decimal import Decimal

from app.collector.booking.results import probe_result_from_page
from app.domain.models import (
    PageOutcome,
    ParsedPage,
    ProbeMethod,
    ProbeStatus,
    RatePlan,
    RoomOffer,
)


def _page(outcome: PageOutcome, offers: tuple[RoomOffer, ...] = ()) -> ParsedPage:
    return ParsedPage(outcome, "111", "Hotel X", "csrf", offers)


def test_rooms_outcome_maps_to_ok() -> None:
    offer = RoomOffer("1", "Deluxe", 2, None, 5, (RatePlan("Standard", Decimal("10"), "VND", None, None),))
    r = probe_result_from_page(
        _page(PageOutcome.ROOMS, (offer,)), method=ProbeMethod.HTTP, checkin=date(2026, 10, 1),
        nights=1, adults=2, raw_html="<html/>", http_status=200, session_id="s", duration_ms=5,
    )
    assert r.status == ProbeStatus.OK
    assert r.checkout == date(2026, 10, 2)
    assert r.offers == (offer,)
    assert r.booking_hotel_id == "111"
    assert r.hotel_name == "Hotel X"


def test_sold_out_and_empty_mapping() -> None:
    kw = dict(method=ProbeMethod.BROWSER, checkin=date(2026, 10, 1), nights=2, adults=2,
              raw_html="", http_status=None, session_id=None, duration_ms=0)
    assert probe_result_from_page(_page(PageOutcome.SOLD_OUT), **kw).status == ProbeStatus.SOLD_OUT
    assert probe_result_from_page(_page(PageOutcome.EMPTY), **kw).status == ProbeStatus.NO_ROOMS_1N
```

- [x] **Step 2: Viết test FakeCollector (thất bại)**

`backend/tests/unit/test_fake_collector.py`:

```python
from datetime import date

from app.collector.fake import FakeCollector
from app.domain.models import CalendarDay, CalendarResult, HotelRef, ProbeStatus

HOTEL = HotelRef(1, "vn", "vn/x", "https://www.booking.com/hotel/vn/x.html")


async def test_fake_collector_scripts_and_records() -> None:
    fake = FakeCollector()
    fake.set_calendar(HOTEL.id, CalendarResult(ok=True, days=(CalendarDay(date(2026, 10, 1), True, 1, None),)))
    fake.set_probe(HOTEL.id, date(2026, 10, 1), ProbeStatus.OK)
    cal = await fake.fetch_calendar(HOTEL, date(2026, 10, 1), 30, adults=2)
    assert cal.ok
    r = await fake.probe(HOTEL, date(2026, 10, 1), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert fake.probe_calls == [(1, date(2026, 10, 1), 1, 2)]


async def test_fake_collector_default_is_error() -> None:
    fake = FakeCollector()
    r = await fake.probe(HOTEL, date(2026, 10, 9), nights=1, adults=2)
    assert r.status == ProbeStatus.ERROR
    cal = await fake.fetch_calendar(HOTEL, date(2026, 10, 1), 30, adults=2)
    assert not cal.ok
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_results.py tests/unit/test_fake_collector.py -q`
Expected: FAIL với `ModuleNotFoundError`

- [x] **Step 4: Viết `backend/app/collector/base.py`**

```python
from datetime import date
from typing import Protocol

from app.domain.models import CalendarResult, HotelRef, ProbeResult


class Collector(Protocol):
    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult: ...

    async def probe(self, hotel: HotelRef, checkin: date, nights: int, adults: int) -> ProbeResult: ...
```

- [x] **Step 5: Viết `backend/app/collector/booking/results.py`**

```python
from datetime import date, timedelta

from app.domain.models import PageOutcome, ParsedPage, ProbeMethod, ProbeResult, ProbeStatus

_STATUS_BY_OUTCOME = {
    PageOutcome.ROOMS: ProbeStatus.OK,
    PageOutcome.SOLD_OUT: ProbeStatus.SOLD_OUT,
    PageOutcome.EMPTY: ProbeStatus.NO_ROOMS_1N,
}


def probe_result_from_page(
    page: ParsedPage,
    *,
    method: ProbeMethod,
    checkin: date,
    nights: int,
    adults: int,
    raw_html: str | None,
    http_status: int | None,
    session_id: str | None,
    duration_ms: int,
) -> ProbeResult:
    return ProbeResult(
        status=_STATUS_BY_OUTCOME[page.outcome],
        method=method,
        checkin=checkin,
        checkout=checkin + timedelta(days=nights),
        nights=nights,
        adults=adults,
        offers=page.offers,
        raw_html=raw_html,
        http_status=http_status,
        session_id=session_id,
        duration_ms=duration_ms,
        booking_hotel_id=page.booking_hotel_id,
        hotel_name=page.hotel_name,
    )


def failed_result(
    status: ProbeStatus,
    *,
    method: ProbeMethod,
    checkin: date,
    nights: int,
    adults: int,
    error: str,
    http_status: int | None = None,
    session_id: str | None = None,
    duration_ms: int = 0,
    raw_html: str | None = None,
) -> ProbeResult:
    return ProbeResult(
        status=status,
        method=method,
        checkin=checkin,
        checkout=checkin + timedelta(days=nights),
        nights=nights,
        adults=adults,
        offers=(),
        raw_html=raw_html,
        http_status=http_status,
        session_id=session_id,
        duration_ms=duration_ms,
        error=error,
    )
```

- [x] **Step 6: Viết `backend/app/collector/fake.py`**

```python
from datetime import date, timedelta

from app.domain.models import (
    CalendarResult,
    HotelRef,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RoomOffer,
)


class FakeCollector:
    """Collector kịch bản sẵn cho test worker."""

    def __init__(self) -> None:
        self._calendars: dict[int, CalendarResult] = {}
        self._probes: dict[tuple[int, date], ProbeResult] = {}
        self.probe_calls: list[tuple[int, date, int, int]] = []
        self.calendar_calls: list[tuple[int, date, int]] = []

    def set_calendar(self, hotel_id: int, result: CalendarResult) -> None:
        self._calendars[hotel_id] = result

    def set_probe(
        self,
        hotel_id: int,
        checkin: date,
        status: ProbeStatus,
        offers: tuple[RoomOffer, ...] = (),
        nights: int = 1,
        raw_html: str | None = "<html>fake</html>",
    ) -> None:
        self._probes[(hotel_id, checkin)] = ProbeResult(
            status=status,
            method=ProbeMethod.HTTP,
            checkin=checkin,
            checkout=checkin + timedelta(days=nights),
            nights=nights,
            adults=2,
            offers=offers,
            raw_html=raw_html,
            http_status=200,
            session_id="fake-session",
            duration_ms=1,
            booking_hotel_id="999",
            hotel_name="Fake Hotel",
        )

    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        self.calendar_calls.append((hotel.id, start, days))
        return self._calendars.get(hotel.id, CalendarResult(ok=False, error="not scripted"))

    async def probe(self, hotel: HotelRef, checkin: date, nights: int, adults: int) -> ProbeResult:
        self.probe_calls.append((hotel.id, checkin, nights, adults))
        scripted = self._probes.get((hotel.id, checkin))
        if scripted is None:
            return ProbeResult(
                status=ProbeStatus.ERROR,
                method=ProbeMethod.HTTP,
                checkin=checkin,
                checkout=checkin + timedelta(days=nights),
                nights=nights,
                adults=adults,
                offers=(),
                raw_html=None,
                http_status=None,
                session_id=None,
                duration_ms=0,
                error="not scripted",
            )
        return scripted
```

- [x] **Step 7: Viết `backend/app/collector/booking/browser.py`**

```python
import time
from datetime import date

from playwright.async_api import async_playwright

from app.collector.booking.parser import parse_hotel_page
from app.collector.booking.playwright_bootstrap import ChallengeNotSolved, wait_until_ready
from app.collector.booking.results import failed_result, probe_result_from_page
from app.collector.booking.urls import build_hotel_url, currency_for
from app.collector.proxy import ProxyProvider
from app.domain.models import CalendarResult, HotelRef, ProbeMethod, ProbeResult, ProbeStatus
from app.logging import get_logger

log = get_logger(__name__)


class BrowserCollector:
    """Provider dự phòng: render toàn phần bằng Chromium cho một probe. Mỗi probe một IP mới."""

    def __init__(
        self, proxy_provider: ProxyProvider, headless: bool = True, timeout_ms: int = 45_000
    ) -> None:
        self._proxies = proxy_provider
        self._headless = headless
        self._timeout_ms = timeout_ms

    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        return CalendarResult(ok=False, error="browser collector does not fetch calendars")

    async def probe(self, hotel: HotelRef, checkin: date, nights: int, adults: int) -> ProbeResult:
        currency = currency_for(hotel.country_code)
        url = build_hotel_url(hotel, checkin, nights, adults, currency)
        proxy = self._proxies.new_endpoint(hotel.country_code)
        t0 = time.monotonic()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self._headless,
                proxy={
                    "server": proxy.server,
                    "username": proxy.username or "",
                    "password": proxy.password or "",
                },
            )
            try:
                context = await browser.new_context(locale="en-GB")
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                try:
                    await wait_until_ready(page, self._timeout_ms)
                except ChallengeNotSolved as exc:
                    log.warning("browser_probe_blocked", hotel=hotel.id, checkin=str(checkin))
                    return failed_result(
                        ProbeStatus.BLOCKED,
                        method=ProbeMethod.BROWSER,
                        checkin=checkin,
                        nights=nights,
                        adults=adults,
                        error=str(exc),
                        session_id=f"browser:{proxy.id}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                html = await page.content()
            except Exception as exc:  # noqa: BLE001
                return failed_result(
                    ProbeStatus.ERROR,
                    method=ProbeMethod.BROWSER,
                    checkin=checkin,
                    nights=nights,
                    adults=adults,
                    error=f"{type(exc).__name__}: {exc}",
                    session_id=f"browser:{proxy.id}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            finally:
                await browser.close()
        parsed = parse_hotel_page(html, currency)
        return probe_result_from_page(
            parsed,
            method=ProbeMethod.BROWSER,
            checkin=checkin,
            nights=nights,
            adults=adults,
            raw_html=html,
            http_status=200,
            session_id=f"browser:{proxy.id}",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
```

- [x] **Step 8: Viết test live**

`backend/tests/live/test_browser_live.py`:

```python
from datetime import date, timedelta

import pytest

from app.collector.booking.browser import BrowserCollector
from app.collector.proxy import StaticProxyProvider
from app.config import get_settings
from app.domain.models import HotelRef, ProbeStatus


@pytest.mark.live
async def test_browser_probe_real() -> None:
    s = get_settings()
    hotel = HotelRef(0, "vn", "vn/the-reverie-saigon", "https://www.booking.com/hotel/vn/the-reverie-saigon.html")
    collector = BrowserCollector(StaticProxyProvider(s.proxy_url_template), headless=s.playwright_headless)
    r = await collector.probe(hotel, date.today() + timedelta(days=14), nights=1, adults=2)
    assert r.status in (ProbeStatus.OK, ProbeStatus.SOLD_OUT)
    if r.status == ProbeStatus.OK:
        assert r.offers and r.offers[0].rates
```

- [x] **Step 9: Chạy unit test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_results.py tests/unit/test_fake_collector.py -q`
Expected: `4 passed`

- [ ] **Step 10: Chạy test live**

Run: `cd backend && uv run pytest tests/live/test_browser_live.py -m live -q -s`
Expected: `1 passed`

- [x] **Step 11: Commit**

```bash
git add backend/app/collector/base.py backend/app/collector/fake.py backend/app/collector/booking/results.py backend/app/collector/booking/browser.py backend/tests/unit/test_results.py backend/tests/unit/test_fake_collector.py backend/tests/live/test_browser_live.py
git commit -m "feat(collector): collector protocol, fake collector, browser fallback collector"
```

---

### Task 13: HybridCollector

**Files:**
- Create: `backend/app/collector/booking/hybrid.py`, `backend/tests/fakes.py`
- Test: `backend/tests/unit/test_hybrid.py`

- [x] **Step 1: Viết `backend/tests/fakes.py`** (fake dùng chung cho các test từ đây về sau)

```python
from collections import deque
from datetime import date
from decimal import Decimal
from typing import Any

from app.collector.fetch import FetchResponse
from app.collector.proxy import ProxyEndpoint
from app.collector.session import BootstrapResult, ScrapeSession
from app.domain.models import PageOutcome, ParsedPage, RatePlan, RoomOffer


class FakeBootstrapper:
    def __init__(self) -> None:
        self.calls: list[tuple[ProxyEndpoint, str]] = []

    async def bootstrap(self, proxy: ProxyEndpoint, warmup_url: str) -> BootstrapResult:
        self.calls.append((proxy, warmup_url))
        return BootstrapResult(
            cookies={"aws-waf-token": f"tok-{len(self.calls)}"},
            user_agent="Mozilla/5.0 Chrome/128",
            csrf_token=f"csrf-{len(self.calls)}",
            html="<html></html>",
        )


class FakeFetcher:
    """Trả lần lượt các FetchResponse hoặc ném Exception theo hàng đợi."""

    def __init__(self, *responses: FetchResponse | Exception) -> None:
        self.queue: deque[FetchResponse | Exception] = deque(responses)
        self.get_calls: list[tuple[str, str]] = []  # (url, session_id)
        self.post_calls: list[tuple[str, dict[str, Any], dict[str, str], str]] = []
        self.closed: list[str] = []

    def _next(self) -> FetchResponse:
        item = self.queue.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, url: str, session: ScrapeSession) -> FetchResponse:
        self.get_calls.append((url, session.id))
        return self._next()

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], session: ScrapeSession
    ) -> FetchResponse:
        self.post_calls.append((url, payload, headers, session.id))
        return self._next()

    async def close(self, session_id: str) -> None:
        self.closed.append(session_id)


def resp(status: int, text: str) -> FetchResponse:
    return FetchResponse(status=status, text=text, url="https://www.booking.com/x", elapsed_ms=10)


OFFER = RoomOffer(
    booking_room_id="101",
    name="Deluxe",
    max_occupancy=2,
    badge_count=2,
    dropdown_max=2,
    rates=(RatePlan("Standard", Decimal("1000000"), "VND", True, None),),
)


def fake_parser(html: str, expected_currency: str) -> ParsedPage:
    if "ROOMS" in html:
        return ParsedPage(PageOutcome.ROOMS, "555", "Fake Hotel", "csrf-page", (OFFER,))
    if "SOLDOUT" in html:
        return ParsedPage(PageOutcome.SOLD_OUT, "555", "Fake Hotel", "csrf-page", ())
    return ParsedPage(PageOutcome.EMPTY, "555", "Fake Hotel", None, ())


async def no_sleep(_: float) -> None:
    return None


def any_date() -> date:
    return date(2026, 10, 5)
```

- [x] **Step 2: Viết test HybridCollector (thất bại)**

`backend/tests/unit/test_hybrid.py`:

```python
import json
from datetime import UTC, datetime, timedelta

from app.clock import FixedClock
from app.collector.booking.hybrid import HybridCollector
from app.collector.fake import FakeCollector
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import SessionManager
from app.domain.models import HotelRef, ProbeMethod, ProbeStatus
from tests.fakes import FakeBootstrapper, FakeFetcher, any_date, fake_parser, no_sleep, resp

HOTEL = HotelRef(1, "vn", "vn/x", "https://www.booking.com/hotel/vn/x.html")


def _build(fetcher: FakeFetcher, fallback: FakeCollector | None = None) -> tuple[HybridCollector, FakeBootstrapper]:
    boot = FakeBootstrapper()
    sessions = SessionManager(
        bootstrapper=boot,
        proxy_provider=StaticProxyProvider("http://u-{country}-{session}:p@h:1"),
        max_age=timedelta(minutes=20),
        max_requests=100,
        clock=FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC)),
    )
    limiter = RateLimiter(min_interval=0, jitter=0, sleep=no_sleep)
    collector = HybridCollector(
        sessions=sessions, fetcher=fetcher, limiter=limiter, fallback=fallback,
        parser=fake_parser, backoff=no_sleep, http_retries=1,
    )
    return collector, boot


async def test_ok_page() -> None:
    fetcher = FakeFetcher(resp(200, "<html>ROOMS</html>"))
    collector, boot = _build(fetcher)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert r.method == ProbeMethod.HTTP
    assert r.offers[0].booking_room_id == "101"
    assert r.raw_html == "<html>ROOMS</html>"
    assert r.http_status == 200
    assert r.booking_hotel_id == "555"
    assert len(boot.calls) == 1
    url, _ = fetcher.get_calls[0]
    assert "checkin=2026-10-05&checkout=2026-10-06" in url
    assert "selected_currency=VND" in url


async def test_sold_out_page() -> None:
    collector, _ = _build(FakeFetcher(resp(200, "<html>SOLDOUT</html>")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.SOLD_OUT


async def test_blocked_then_ok_on_fresh_session() -> None:
    fetcher = FakeFetcher(resp(403, ""), resp(200, "<html>ROOMS</html>"))
    collector, boot = _build(fetcher)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert len(boot.calls) == 2
    first_session = fetcher.get_calls[0][1]
    second_session = fetcher.get_calls[1][1]
    assert first_session != second_session
    assert fetcher.closed == [first_session]


async def test_blocked_twice_uses_fallback() -> None:
    fallback = FakeCollector()
    fallback.set_probe(HOTEL.id, any_date(), ProbeStatus.OK)
    fetcher = FakeFetcher(resp(403, ""), resp(429, ""))
    collector, boot = _build(fetcher, fallback)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.OK
    assert fallback.probe_calls == [(1, any_date(), 1, 2)]
    assert len(boot.calls) == 2


async def test_blocked_twice_without_fallback_is_blocked() -> None:
    collector, _ = _build(FakeFetcher(resp(403, ""), resp(403, "")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.BLOCKED
    assert r.http_status == 403


async def test_empty_page_goes_to_fallback() -> None:
    fallback = FakeCollector()
    fallback.set_probe(HOTEL.id, any_date(), ProbeStatus.NO_ROOMS_1N)
    collector, boot = _build(FakeFetcher(resp(200, "<html>nothing</html>")), fallback)
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.NO_ROOMS_1N
    assert len(fallback.probe_calls) == 1
    assert len(boot.calls) == 1  # trang rỗng không thu hồi session


async def test_transport_error() -> None:
    collector, _ = _build(FakeFetcher(ConnectionError("boom")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.ERROR
    assert "boom" in (r.error or "")


async def test_not_found() -> None:
    collector, _ = _build(FakeFetcher(resp(404, "")))
    r = await collector.probe(HOTEL, any_date(), nights=1, adults=2)
    assert r.status == ProbeStatus.ERROR
    assert r.http_status == 404


async def test_calendar_ok_sends_csrf() -> None:
    body = {"data": {"availabilityCalendar": {"hotelId": 1, "days": [
        {"checkin": "2026-10-05", "available": True, "minLengthOfStay": 1, "avgPriceFormatted": "VND 1"}]}}}
    fetcher = FakeFetcher(resp(200, json.dumps(body)))
    collector, _ = _build(fetcher)
    cal = await collector.fetch_calendar(HOTEL, any_date(), 30, adults=2)
    assert cal.ok and cal.day(any_date()) is not None
    url, payload, headers, _ = fetcher.post_calls[0]
    assert url.startswith("https://www.booking.com/dml/graphql")
    assert payload["variables"]["input"]["pagename"] == "x"
    assert headers["x-booking-csrf-token"] == "csrf-1"


async def test_calendar_blocked_retires_session() -> None:
    fetcher = FakeFetcher(resp(403, ""))
    collector, boot = _build(fetcher)
    cal = await collector.fetch_calendar(HOTEL, any_date(), 30, adults=2)
    assert not cal.ok and cal.error == "blocked"
    assert fetcher.closed == [fetcher.post_calls[0][3]]
    assert len(boot.calls) == 1
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_hybrid.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.collector.booking.hybrid'`

- [x] **Step 4: Viết `backend/app/collector/booking/hybrid.py`**

```python
import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import date

from app.collector.base import Collector
from app.collector.booking.calendar import (
    GRAPHQL_URL,
    build_calendar_request,
    calendar_headers,
    parse_calendar_response,
)
from app.collector.booking.parser import parse_hotel_page
from app.collector.booking.results import failed_result, probe_result_from_page
from app.collector.booking.urls import build_hotel_url, currency_for
from app.collector.fetch import Fetcher, FetchOutcome
from app.collector.ratelimit import RateLimiter
from app.collector.session import ScrapeSession, SessionManager
from app.domain.models import (
    CalendarResult,
    HotelRef,
    PageOutcome,
    ParsedPage,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
)
from app.logging import get_logger

log = get_logger(__name__)

Parser = Callable[[str, str], ParsedPage]


class HybridCollector:
    """Session lai: cookie từ Playwright, tải trang bằng curl_cffi.

    Khi bị chặn: thu hồi session, thử lại bằng session mới tối đa `http_retries` lần,
    rồi chuyển sang `fallback` (BrowserCollector). Trang rỗng không có dấu hiệu chặn cũng
    chuyển sang fallback để trình duyệt thật quyết định, nhưng không thu hồi session.
    """

    def __init__(
        self,
        sessions: SessionManager,
        fetcher: Fetcher,
        limiter: RateLimiter,
        fallback: Collector | None,
        parser: Parser = parse_hotel_page,
        backoff: Callable[[float], Awaitable[None]] = asyncio.sleep,
        http_retries: int = 1,
        backoff_seconds: float = 3.0,
    ) -> None:
        self._sessions = sessions
        self._fetcher = fetcher
        self._limiter = limiter
        self._fallback = fallback
        self._parser = parser
        self._backoff = backoff
        self._http_retries = http_retries
        self._backoff_seconds = backoff_seconds

    async def _retire_blocked(self, session: ScrapeSession) -> None:
        await self._sessions.retire(session, reason="blocked")
        await self._fetcher.close(session.id)

    async def fetch_calendar(
        self, hotel: HotelRef, start: date, days: int, adults: int
    ) -> CalendarResult:
        session = await self._sessions.get(hotel.country_code, hotel.canonical_url)
        await self._limiter.wait(session.id)
        payload = build_calendar_request(hotel.pagename, start, days, adults)
        headers = calendar_headers(session.csrf_token, referer=hotel.canonical_url)
        try:
            response = await self._fetcher.post_json(GRAPHQL_URL, payload, headers, session)
        except Exception as exc:  # noqa: BLE001
            return CalendarResult(ok=False, error=f"transport: {type(exc).__name__}: {exc}")
        self._sessions.mark_request(session)
        if response.outcome == FetchOutcome.BLOCKED:
            await self._retire_blocked(session)
            return CalendarResult(ok=False, error="blocked")
        if response.outcome != FetchOutcome.OK:
            return CalendarResult(ok=False, error=f"http {response.status}")
        return parse_calendar_response(response.text)

    async def probe(self, hotel: HotelRef, checkin: date, nights: int, adults: int) -> ProbeResult:
        currency = currency_for(hotel.country_code)
        url = build_hotel_url(hotel, checkin, nights, adults, currency)
        attempts = 0
        last_status: int | None = None
        last_session: str | None = None
        while True:
            session = await self._sessions.get(hotel.country_code, hotel.canonical_url)
            last_session = session.id
            await self._limiter.wait(session.id)
            t0 = time.monotonic()
            try:
                response = await self._fetcher.get(url, session)
            except Exception as exc:  # noqa: BLE001
                return failed_result(
                    ProbeStatus.ERROR, method=ProbeMethod.HTTP, checkin=checkin, nights=nights,
                    adults=adults, error=f"transport: {type(exc).__name__}: {exc}",
                    session_id=session.id, duration_ms=int((time.monotonic() - t0) * 1000),
                )
            self._sessions.mark_request(session)
            duration_ms = int((time.monotonic() - t0) * 1000)
            last_status = response.status
            outcome = response.outcome
            if outcome == FetchOutcome.BLOCKED:
                log.warning("probe_blocked", hotel=hotel.id, checkin=str(checkin), status=response.status, attempt=attempts)
                await self._retire_blocked(session)
                if attempts < self._http_retries:
                    attempts += 1
                    await self._backoff(self._backoff_seconds * attempts)
                    continue
                return await self._fallback_or_blocked(hotel, checkin, nights, adults, last_status, last_session)
            if outcome == FetchOutcome.NOT_FOUND:
                return failed_result(
                    ProbeStatus.ERROR, method=ProbeMethod.HTTP, checkin=checkin, nights=nights,
                    adults=adults, error="not_found", http_status=404, session_id=session.id,
                    duration_ms=duration_ms,
                )
            if outcome == FetchOutcome.ERROR:
                return failed_result(
                    ProbeStatus.ERROR, method=ProbeMethod.HTTP, checkin=checkin, nights=nights,
                    adults=adults, error=f"http {response.status}", http_status=response.status,
                    session_id=session.id, duration_ms=duration_ms, raw_html=response.text,
                )
            parsed = self._parser(response.text, currency)
            if parsed.csrf_token and parsed.csrf_token != session.csrf_token:
                session.csrf_token = parsed.csrf_token
            if parsed.outcome == PageOutcome.EMPTY and self._fallback is not None:
                log.info("probe_empty_page_fallback", hotel=hotel.id, checkin=str(checkin))
                return await self._fallback.probe(hotel, checkin, nights, adults)
            return probe_result_from_page(
                parsed, method=ProbeMethod.HTTP, checkin=checkin, nights=nights, adults=adults,
                raw_html=response.text, http_status=response.status, session_id=session.id,
                duration_ms=duration_ms,
            )

    async def _fallback_or_blocked(
        self, hotel: HotelRef, checkin: date, nights: int, adults: int,
        http_status: int | None, session_id: str | None,
    ) -> ProbeResult:
        if self._fallback is None:
            return failed_result(
                ProbeStatus.BLOCKED, method=ProbeMethod.HTTP, checkin=checkin, nights=nights,
                adults=adults, error="blocked after retries", http_status=http_status,
                session_id=session_id,
            )
        return await self._fallback.probe(hotel, checkin, nights, adults)
```

- [x] **Step 5: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_hybrid.py -q`
Expected: `10 passed`

- [x] **Step 6: Commit**

```bash
git add backend/app/collector/booking/hybrid.py backend/tests/fakes.py backend/tests/unit/test_hybrid.py
git commit -m "feat(collector): hybrid collector with session rotation and browser fallback"
```

---

### Task 14: Repository ghi snapshot và quản lý scan run

**Files:**
- Create: `backend/app/repo/__init__.py`, `backend/app/repo/snapshots.py`, `backend/app/repo/runs.py`
- Test: `backend/tests/integration/test_snapshot_repo.py`, `backend/tests/integration/test_run_repo.py`

- [x] **Step 1: Viết test SnapshotRepository (thất bại)**

`backend/tests/integration/test_snapshot_repo.py`:

```python
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, HotelCalendar, Probe, RoomSnapshot, RoomType, ScanRun
from app.domain.models import (
    CalendarDay,
    CalendarResult,
    ProbeMethod,
    ProbeResult,
    ProbeStatus,
    RatePlan,
    RoomOffer,
)
from app.repo.snapshots import SnapshotRepository

NOW = datetime(2026, 9, 24, 6, 5, tzinfo=UTC)


async def _seed(db: AsyncSession) -> tuple[int, int]:
    hotel = Hotel(booking_url="https://www.booking.com/hotel/vn/x.html", booking_slug="vn/x", country_code="vn")
    run = ScanRun(trigger_key="2026-09-24T06:00", scheduled_at=NOW, status="running")
    db.add_all([hotel, run])
    await db.flush()
    return hotel.id, run.id


def _result(*offers: RoomOffer, status: ProbeStatus = ProbeStatus.OK) -> ProbeResult:
    return ProbeResult(
        status=status, method=ProbeMethod.HTTP, checkin=date(2026, 10, 5), checkout=date(2026, 10, 6),
        nights=1, adults=2, offers=offers, raw_html="<html/>", http_status=200, session_id="s1",
        duration_ms=120, booking_hotel_id="777", hotel_name="Hotel X",
    )


OFFER_A = RoomOffer("101", "Deluxe", 2, 2, 2, (RatePlan("Non-refundable", Decimal("900000"), "VND", False, None),
                                              RatePlan("Free cancellation", Decimal("1000000"), "VND", True, None)))
OFFER_B = RoomOffer("102", "Suite", 3, None, 10, (RatePlan("Standard", Decimal("2500000"), "VND", None, True),))


async def test_write_probe_creates_room_types_and_snapshots(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    probe_id = await repo.write_probe(
        scan_run_id=run_id, hotel_id=hotel_id, stay_date=date(2026, 10, 5), result=_result(OFFER_A, OFFER_B),
        raw_object_key="k1", parser_version="1", proxy_country="vn", fetched_at=NOW,
    )
    await db.commit()

    probe = (await db.execute(select(Probe).where(Probe.id == probe_id))).scalar_one()
    assert probe.status == "ok" and probe.raw_object_key == "k1" and probe.method == "http"

    types = (await db.execute(select(RoomType).order_by(RoomType.booking_room_id))).scalars().all()
    assert [t.booking_room_id for t in types] == ["101", "102"]

    snaps = (await db.execute(select(RoomSnapshot).order_by(RoomSnapshot.room_type_id))).scalars().all()
    assert len(snaps) == 2
    a, b = snaps
    assert a.rooms_left == 2 and a.stock_confidence == "exact" and a.badge_count == 2
    assert a.min_price == Decimal("900000.00") and a.min_refundable_price == Decimal("1000000.00")
    assert a.currency == "VND" and len(a.rates) == 2
    assert b.rooms_left == 10 and b.stock_confidence == "capped" and b.min_refundable_price is None

    hotel = (await db.execute(select(Hotel).where(Hotel.id == hotel_id))).scalar_one()
    assert hotel.booking_hotel_id == "777" and hotel.name == "Hotel X"


async def test_write_probe_is_idempotent_per_run_hotel_date(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    p1 = await repo.write_probe(run_id, hotel_id, date(2026, 10, 5), _result(OFFER_A), "k1", "1", "vn", NOW)
    p2 = await repo.write_probe(run_id, hotel_id, date(2026, 10, 5), _result(OFFER_A, OFFER_B), "k2", "2", "vn", NOW + timedelta(minutes=1))
    await db.commit()
    assert p1 == p2
    probes = (await db.execute(select(Probe))).scalars().all()
    assert len(probes) == 1 and probes[0].raw_object_key == "k2" and probes[0].parser_version == "2"
    snaps = (await db.execute(select(RoomSnapshot))).scalars().all()
    assert len(snaps) == 2


async def test_room_type_last_seen_updates(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_probe(run_id, hotel_id, date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW)
    await repo.write_probe(run_id, hotel_id, date(2026, 10, 6), _result(OFFER_A), None, "1", "vn", NOW + timedelta(hours=1))
    await db.commit()
    rt = (await db.execute(select(RoomType))).scalar_one()
    assert rt.first_seen_at == NOW and rt.last_seen_at == NOW + timedelta(hours=1)


async def test_write_skipped_and_sold_out_have_no_snapshots(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_skipped(run_id, hotel_id, date(2026, 10, 7), nights=1, adults=2, fetched_at=NOW)
    await repo.write_probe(run_id, hotel_id, date(2026, 10, 8), _result(status=ProbeStatus.SOLD_OUT), "k", "1", "vn", NOW)
    await db.commit()
    probes = (await db.execute(select(Probe).order_by(Probe.stay_date))).scalars().all()
    assert [p.status for p in probes] == ["skipped_calendar", "sold_out"]
    assert probes[0].method == "calendar"
    assert (await db.execute(select(RoomSnapshot))).scalars().all() == []


async def test_write_calendar_upserts(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    cal = CalendarResult(ok=True, days=(
        CalendarDay(date(2026, 10, 5), True, 1, "VND 1"),
        CalendarDay(date(2026, 10, 6), False, 1, None),
    ))
    await repo.write_calendar(hotel_id, run_id, cal, fetched_at=NOW)
    await repo.write_calendar(hotel_id, run_id, cal, fetched_at=NOW)
    await db.commit()
    rows = (await db.execute(select(HotelCalendar).order_by(HotelCalendar.stay_date))).scalars().all()
    assert [(r.stay_date, r.available) for r in rows] == [(date(2026, 10, 5), True), (date(2026, 10, 6), False)]


async def test_terminal_dates_for_run(db: AsyncSession) -> None:
    hotel_id, run_id = await _seed(db)
    repo = SnapshotRepository(db, page_cap=10)
    await repo.write_probe(run_id, hotel_id, date(2026, 10, 5), _result(OFFER_A), None, "1", "vn", NOW)
    await repo.write_probe(run_id, hotel_id, date(2026, 10, 6), _result(status=ProbeStatus.BLOCKED), None, "1", "vn", NOW)
    await repo.write_skipped(run_id, hotel_id, date(2026, 10, 7), nights=1, adults=2, fetched_at=NOW)
    await db.commit()
    done = await repo.terminal_dates(run_id, hotel_id)
    assert done == {date(2026, 10, 5), date(2026, 10, 7)}
```

- [x] **Step 2: Viết test ScanRunRepository (thất bại)**

`backend/tests/integration/test_run_repo.py`:

```python
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, Probe, ScanJob, ScanRun
from app.repo.runs import HotelJobPlan, ScanRunRepository

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)


async def _hotels(db: AsyncSession, n: int) -> list[int]:
    hotels = [Hotel(booking_url=f"https://www.booking.com/hotel/vn/h{i}.html", booking_slug=f"vn/h{i}", country_code="vn") for i in range(n)]
    db.add_all(hotels)
    await db.flush()
    return [h.id for h in hotels]


async def test_create_run_with_jobs_and_idempotent_key(db: AsyncSession) -> None:
    ids = await _hotels(db, 2)
    repo = ScanRunRepository(db)
    plans = [HotelJobPlan(ids[0], date(2026, 9, 24), 30), HotelJobPlan(ids[1], date(2026, 9, 24), 45)]
    run = await repo.create_run("2026-09-24T06:00", NOW, plans)
    await db.commit()
    assert run is not None and run.total_jobs == 2
    jobs = (await db.execute(select(ScanJob).order_by(ScanJob.hotel_id))).scalars().all()
    assert [(j.hotel_id, j.horizon_days, j.status) for j in jobs] == [(ids[0], 30, "queued"), (ids[1], 45, "queued")]
    assert await repo.create_run("2026-09-24T06:00", NOW, plans) is None


async def test_load_hotel_ref(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    ref = await ScanRunRepository(db).load_hotel(ids[0])
    assert ref.slug == "vn/h0" and ref.country_code == "vn" and ref.pagename == "h0"


async def test_job_lifecycle_and_run_completion(db: AsyncSession) -> None:
    ids = await _hotels(db, 2)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(i, date(2026, 9, 24), 30) for i in ids])
    assert run is not None
    await db.commit()

    job = await repo.start_job(run.id, ids[0], NOW)
    assert job is not None and job.status == "running" and job.start_date == date(2026, 9, 24)
    assert await repo.try_finish_run(run.id, NOW) is False

    await repo.finish_job(run.id, ids[0], "done", NOW + timedelta(minutes=5))
    await repo.start_job(run.id, ids[1], NOW)
    await repo.finish_job(run.id, ids[1], "failed", NOW + timedelta(minutes=6), error="boom")
    db.add_all([
        Probe(scan_run_id=run.id, hotel_id=ids[0], stay_date=date(2026, 10, 1), checkin=date(2026, 10, 1),
              checkout=date(2026, 10, 2), nights=1, adults=2, status="ok", fetched_at=NOW),
        Probe(scan_run_id=run.id, hotel_id=ids[0], stay_date=date(2026, 10, 2), checkin=date(2026, 10, 2),
              checkout=date(2026, 10, 3), nights=1, adults=2, status="blocked", fetched_at=NOW),
    ])
    await db.flush()
    assert await repo.try_finish_run(run.id, NOW + timedelta(minutes=7)) is True
    await db.commit()
    db.expire_all()

    run_row = (await db.execute(select(ScanRun).where(ScanRun.id == run.id))).scalar_one()
    assert run_row.status == "partial"
    assert run_row.total_probes == 2 and run_row.ok_count == 1 and run_row.blocked_count == 1
    assert run_row.finished_at == NOW + timedelta(minutes=7)


async def test_start_job_is_idempotent_for_done_job(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    await repo.start_job(run.id, ids[0], NOW)
    await repo.finish_job(run.id, ids[0], "done", NOW)
    assert await repo.start_job(run.id, ids[0], NOW) is None


async def test_expire_runs_past_deadline(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    await db.commit()
    expired = await repo.expire_runs(deadline=timedelta(minutes=90), now=NOW + timedelta(minutes=91))
    await db.commit()
    db.expire_all()
    assert expired == [run.id]
    run_row = (await db.execute(select(ScanRun).where(ScanRun.id == run.id))).scalar_one()
    job = (await db.execute(select(ScanJob))).scalar_one()
    assert run_row.status == "partial" and job.status == "failed" and job.error == "deadline"


async def test_probe_stats_since(db: AsyncSession) -> None:
    ids = await _hotels(db, 1)
    repo = ScanRunRepository(db)
    run = await repo.create_run("k", NOW, [HotelJobPlan(ids[0], date(2026, 9, 24), 30)])
    assert run is not None
    for i, status in enumerate(["ok", "ok", "blocked", "skipped_calendar"]):
        db.add(Probe(scan_run_id=run.id, hotel_id=ids[0], stay_date=date(2026, 10, 1) + timedelta(days=i),
                     checkin=date(2026, 10, 1), checkout=date(2026, 10, 2), nights=1, adults=2,
                     status=status, fetched_at=NOW))
    await db.flush()
    total, blocked = await repo.probe_stats_since(NOW - timedelta(minutes=15))
    assert (total, blocked) == (3, 1)  # skipped_calendar không tính vì không phải request
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/integration/test_snapshot_repo.py tests/integration/test_run_repo.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.repo'`

- [x] **Step 4: Viết `backend/app/repo/snapshots.py`** (`backend/app/repo/__init__.py` rỗng)

```python
from dataclasses import asdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, HotelCalendar, Probe, RoomSnapshot, RoomType
from app.domain.models import CalendarResult, ProbeMethod, ProbeResult, ProbeStatus, RoomOffer
from app.domain.stock import derive_stock

TERMINAL_STATUSES = (ProbeStatus.OK, ProbeStatus.SOLD_OUT, ProbeStatus.SKIPPED_CALENDAR)


class SnapshotRepository:
    def __init__(self, session: AsyncSession, page_cap: int) -> None:
        self._s = session
        self._page_cap = page_cap

    async def upsert_room_type(self, hotel_id: int, offer: RoomOffer, seen_at: datetime) -> int:
        stmt = (
            insert(RoomType)
            .values(
                hotel_id=hotel_id,
                booking_room_id=offer.booking_room_id,
                name=offer.name,
                max_occupancy=offer.max_occupancy,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            .on_conflict_do_update(
                index_elements=[RoomType.hotel_id, RoomType.booking_room_id],
                set_={"name": offer.name, "max_occupancy": offer.max_occupancy, "last_seen_at": seen_at},
            )
            .returning(RoomType.id)
        )
        return int((await self._s.execute(stmt)).scalar_one())

    async def _upsert_probe(
        self,
        *,
        scan_run_id: int,
        hotel_id: int,
        stay_date: date,
        checkin: date,
        checkout: date,
        nights: int,
        adults: int,
        status: str,
        method: str | None,
        proxy_country: str | None,
        session_id: str | None,
        http_status: int | None,
        raw_object_key: str | None,
        parser_version: str | None,
        error: str | None,
        fetched_at: datetime,
        duration_ms: int,
    ) -> int:
        values = dict(
            scan_run_id=scan_run_id, hotel_id=hotel_id, stay_date=stay_date, checkin=checkin,
            checkout=checkout, nights=nights, adults=adults, status=status, method=method,
            proxy_country=proxy_country, session_id=session_id, http_status=http_status,
            raw_object_key=raw_object_key, parser_version=parser_version, error=error,
            fetched_at=fetched_at, duration_ms=duration_ms,
        )
        update_cols = {k: v for k, v in values.items() if k not in ("scan_run_id", "hotel_id", "stay_date")}
        stmt = (
            insert(Probe)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Probe.scan_run_id, Probe.hotel_id, Probe.stay_date], set_=update_cols
            )
            .returning(Probe.id)
        )
        return int((await self._s.execute(stmt)).scalar_one())

    async def write_probe(
        self,
        scan_run_id: int,
        hotel_id: int,
        stay_date: date,
        result: ProbeResult,
        raw_object_key: str | None,
        parser_version: str,
        proxy_country: str | None,
        fetched_at: datetime,
    ) -> int:
        probe_id = await self._upsert_probe(
            scan_run_id=scan_run_id, hotel_id=hotel_id, stay_date=stay_date, checkin=result.checkin,
            checkout=result.checkout, nights=result.nights, adults=result.adults,
            status=str(result.status), method=str(result.method), proxy_country=proxy_country,
            session_id=result.session_id, http_status=result.http_status,
            raw_object_key=raw_object_key, parser_version=parser_version, error=result.error,
            fetched_at=fetched_at, duration_ms=result.duration_ms,
        )
        await self._s.execute(delete(RoomSnapshot).where(RoomSnapshot.probe_id == probe_id))
        for offer in result.offers:
            room_type_id = await self.upsert_room_type(hotel_id, offer, fetched_at)
            stock = derive_stock(offer.badge_count, offer.dropdown_max, self._page_cap)
            self._s.add(
                RoomSnapshot(
                    probe_id=probe_id,
                    hotel_id=hotel_id,
                    room_type_id=room_type_id,
                    stay_date=stay_date,
                    scanned_at=fetched_at,
                    rooms_left=stock.rooms_left,
                    stock_confidence=str(stock.confidence),
                    badge_count=offer.badge_count,
                    dropdown_max=offer.dropdown_max,
                    min_price=offer.min_price,
                    min_refundable_price=offer.min_refundable_price,
                    currency=offer.currency,
                    rates=[{**asdict(r), "price": str(r.price)} for r in offer.rates],
                )
            )
        if result.booking_hotel_id or result.hotel_name:
            await self.update_hotel_identity(hotel_id, result.booking_hotel_id, result.hotel_name)
        await self._s.flush()
        return probe_id

    async def write_skipped(
        self, scan_run_id: int, hotel_id: int, stay_date: date, nights: int, adults: int, fetched_at: datetime
    ) -> int:
        probe_id = await self._upsert_probe(
            scan_run_id=scan_run_id, hotel_id=hotel_id, stay_date=stay_date, checkin=stay_date,
            checkout=stay_date + timedelta(days=nights), nights=nights, adults=adults,
            status=str(ProbeStatus.SKIPPED_CALENDAR), method=str(ProbeMethod.CALENDAR),
            proxy_country=None, session_id=None, http_status=None, raw_object_key=None,
            parser_version=None, error=None, fetched_at=fetched_at, duration_ms=0,
        )
        await self._s.execute(delete(RoomSnapshot).where(RoomSnapshot.probe_id == probe_id))
        await self._s.flush()
        return probe_id

    async def write_calendar(
        self, hotel_id: int, scan_run_id: int, result: CalendarResult, fetched_at: datetime
    ) -> None:
        if not result.ok:
            return
        for day in result.days:
            stmt = (
                insert(HotelCalendar)
                .values(
                    hotel_id=hotel_id, scan_run_id=scan_run_id, stay_date=day.checkin,
                    available=day.available, min_length_of_stay=day.min_length_of_stay,
                    avg_price_display=day.avg_price_display, fetched_at=fetched_at,
                )
                .on_conflict_do_update(
                    index_elements=[HotelCalendar.hotel_id, HotelCalendar.scan_run_id, HotelCalendar.stay_date],
                    set_={
                        "available": day.available,
                        "min_length_of_stay": day.min_length_of_stay,
                        "avg_price_display": day.avg_price_display,
                        "fetched_at": fetched_at,
                    },
                )
            )
            await self._s.execute(stmt)
        await self._s.flush()

    async def update_hotel_identity(self, hotel_id: int, booking_hotel_id: str | None, name: str | None) -> None:
        values: dict[str, str] = {}
        if booking_hotel_id:
            values["booking_hotel_id"] = booking_hotel_id
        if name:
            values["name"] = name[:300]
        if values:
            await self._s.execute(update(Hotel).where(Hotel.id == hotel_id).values(**values))

    async def terminal_dates(self, scan_run_id: int, hotel_id: int) -> set[date]:
        rows = await self._s.execute(
            select(Probe.stay_date).where(
                Probe.scan_run_id == scan_run_id,
                Probe.hotel_id == hotel_id,
                Probe.status.in_([str(s) for s in TERMINAL_STATUSES]),
            )
        )
        return {r[0] for r in rows}
```

- [x] **Step 5: Viết `backend/app/repo/runs.py`**

```python
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, Probe, ScanJob, ScanRun
from app.domain.models import HotelRef, ProbeStatus


@dataclass(frozen=True)
class HotelJobPlan:
    hotel_id: int
    start_date: date
    horizon_days: int


class ScanRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_run(
        self, trigger_key: str, scheduled_at: datetime, plans: list[HotelJobPlan]
    ) -> ScanRun | None:
        """Tạo run và job. Trả None nếu trigger_key đã tồn tại (đã tạo trước đó)."""
        existing = await self._s.execute(select(ScanRun.id).where(ScanRun.trigger_key == trigger_key))
        if existing.first() is not None:
            return None
        run = ScanRun(
            trigger_key=trigger_key, scheduled_at=scheduled_at, started_at=scheduled_at,
            status="running", total_jobs=len(plans),
        )
        self._s.add(run)
        try:
            await self._s.flush()
        except IntegrityError:
            await self._s.rollback()
            return None
        for p in plans:
            self._s.add(
                ScanJob(
                    scan_run_id=run.id, hotel_id=p.hotel_id, start_date=p.start_date,
                    horizon_days=p.horizon_days, status="queued",
                )
            )
        await self._s.flush()
        return run

    async def load_hotel(self, hotel_id: int) -> HotelRef:
        hotel = (await self._s.execute(select(Hotel).where(Hotel.id == hotel_id))).scalar_one()
        return HotelRef(
            id=hotel.id, country_code=hotel.country_code, slug=hotel.booking_slug,
            canonical_url=f"https://www.booking.com/hotel/{hotel.booking_slug}.html",
        )

    async def start_job(self, scan_run_id: int, hotel_id: int, now: datetime) -> ScanJob | None:
        """Chuyển job sang running. Trả None nếu job đã done (chạy lại không làm gì)."""
        job = (
            await self._s.execute(
                select(ScanJob).where(ScanJob.scan_run_id == scan_run_id, ScanJob.hotel_id == hotel_id)
            )
        ).scalar_one_or_none()
        if job is None or job.status == "done":
            return None
        job.status = "running"
        job.started_at = job.started_at or now
        job.error = None
        await self._s.flush()
        return job

    async def finish_job(
        self, scan_run_id: int, hotel_id: int, status: str, now: datetime, error: str | None = None
    ) -> None:
        await self._s.execute(
            update(ScanJob)
            .where(ScanJob.scan_run_id == scan_run_id, ScanJob.hotel_id == hotel_id)
            .values(status=status, finished_at=now, error=error)
        )
        await self._s.flush()

    async def try_finish_run(self, scan_run_id: int, now: datetime) -> bool:
        pending = await self._s.execute(
            select(func.count()).select_from(ScanJob).where(
                ScanJob.scan_run_id == scan_run_id, ScanJob.status.in_(["queued", "running"])
            )
        )
        if pending.scalar_one() > 0:
            return False
        failed = await self._s.execute(
            select(func.count()).select_from(ScanJob).where(
                ScanJob.scan_run_id == scan_run_id, ScanJob.status == "failed"
            )
        )
        counts = await self._s.execute(
            select(Probe.status, func.count()).where(Probe.scan_run_id == scan_run_id).group_by(Probe.status)
        )
        by_status = {row[0]: row[1] for row in counts}
        await self._s.execute(
            update(ScanRun)
            .where(ScanRun.id == scan_run_id)
            .values(
                status="partial" if failed.scalar_one() > 0 else "completed",
                finished_at=now,
                total_probes=sum(by_status.values()),
                ok_count=by_status.get(str(ProbeStatus.OK), 0),
                sold_out_count=by_status.get(str(ProbeStatus.SOLD_OUT), 0)
                + by_status.get(str(ProbeStatus.SKIPPED_CALENDAR), 0),
                blocked_count=by_status.get(str(ProbeStatus.BLOCKED), 0),
                error_count=by_status.get(str(ProbeStatus.ERROR), 0),
            )
        )
        await self._s.flush()
        return True

    async def expire_runs(self, deadline: timedelta, now: datetime) -> list[int]:
        cutoff = now - deadline
        rows = await self._s.execute(
            select(ScanRun.id).where(ScanRun.status == "running", ScanRun.started_at < cutoff)
        )
        expired = [r[0] for r in rows]
        for run_id in expired:
            await self._s.execute(
                update(ScanJob)
                .where(ScanJob.scan_run_id == run_id, ScanJob.status.in_(["queued", "running"]))
                .values(status="failed", finished_at=now, error="deadline")
            )
            await self.try_finish_run(run_id, now)
        return expired

    async def get_run(self, scan_run_id: int) -> ScanRun:
        return (await self._s.execute(select(ScanRun).where(ScanRun.id == scan_run_id))).scalar_one()

    async def probe_stats_since(self, since: datetime) -> tuple[int, int]:
        """(tổng probe có request thật, số bị chặn) kể từ `since`."""
        rows = await self._s.execute(
            select(Probe.status, func.count())
            .where(Probe.fetched_at >= since, Probe.status != str(ProbeStatus.SKIPPED_CALENDAR))
            .group_by(Probe.status)
        )
        by_status = {row[0]: row[1] for row in rows}
        return sum(by_status.values()), by_status.get(str(ProbeStatus.BLOCKED), 0)
```

- [x] **Step 6: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/integration/test_snapshot_repo.py tests/integration/test_run_repo.py -q`
Expected: `12 passed`

- [x] **Step 7: Commit**

```bash
git add backend/app/repo backend/tests/integration/test_snapshot_repo.py backend/tests/integration/test_run_repo.py
git commit -m "feat(repo): snapshot writer and scan run lifecycle repositories"
```

---

### Task 15: Metrics Prometheus và cảnh báo Telegram

**Files:**
- Create: `backend/app/ops/__init__.py`, `backend/app/ops/metrics.py`, `backend/app/ops/alerts.py`
- Test: `backend/tests/unit/test_alerts.py`

- [x] **Step 1: Viết test (thất bại)**

`backend/tests/unit/test_alerts.py`:

```python
from datetime import UTC, datetime, timedelta

import httpx
import respx

from app.clock import FixedClock
from app.ops.alerts import (
    AlertThrottle,
    RunStats,
    TelegramAlerter,
    block_rate_alert,
    run_summary_alert,
)


def test_block_rate_alert_thresholds() -> None:
    assert block_rate_alert(total=10, blocked=5) is None  # dưới min_total
    assert block_rate_alert(total=100, blocked=10) is None
    msg = block_rate_alert(total=100, blocked=25)
    assert msg is not None and "25%" in msg


def test_run_summary_alert() -> None:
    ok = RunStats(scan_run_id=1, total_probes=100, ok_count=85, sold_out_count=10, blocked_count=3, error_count=2)
    assert run_summary_alert(ok) is None
    bad = RunStats(scan_run_id=2, total_probes=100, ok_count=60, sold_out_count=10, blocked_count=25, error_count=5)
    msg = run_summary_alert(bad)
    assert msg is not None and "run 2" in msg and "70%" in msg


def test_run_summary_alert_empty_run() -> None:
    assert run_summary_alert(RunStats(3, 0, 0, 0, 0, 0)) is None


def test_throttle() -> None:
    clock = FixedClock(datetime(2026, 9, 24, 6, 0, tzinfo=UTC))
    th = AlertThrottle(clock, min_gap=timedelta(minutes=30))
    assert th.should_send("block_rate") is True
    assert th.should_send("block_rate") is False
    clock.advance(minutes=31)
    assert th.should_send("block_rate") is True
    assert th.should_send("other") is True


@respx.mock
async def test_telegram_sends_message() -> None:
    route = respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    alerter = TelegramAlerter(token="TOKEN", chat_id="42")
    await alerter.send("hello")
    assert route.called
    body = route.calls[0].request.content.decode()
    assert '"chat_id": "42"' in body and "hello" in body


async def test_telegram_disabled_without_token() -> None:
    alerter = TelegramAlerter(token="", chat_id="")
    await alerter.send("ignored")  # không ném lỗi, không gọi mạng
```

- [x] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_alerts.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.ops'`

- [x] **Step 3: Viết `backend/app/ops/metrics.py`** (`backend/app/ops/__init__.py` rỗng)

```python
from prometheus_client import Counter, Gauge, Histogram, start_http_server

PROBES_TOTAL = Counter("sb_probes_total", "Probes by status and method", ["status", "method"])
PROBE_DURATION = Histogram(
    "sb_probe_duration_seconds", "Probe duration", buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60)
)
SESSIONS_CREATED = Counter("sb_sessions_created_total", "Sessions bootstrapped", ["country"])
SESSIONS_RETIRED = Counter("sb_sessions_retired_total", "Sessions retired", ["reason"])
JOBS_TOTAL = Counter("sb_jobs_total", "Hotel jobs by final status", ["status"])
RUNS_CREATED = Counter("sb_runs_created_total", "Scan runs created")
QUEUE_DEPTH = Gauge("sb_scheduler_last_run_jobs", "Jobs enqueued by the last created run")


def start_metrics_server(port: int) -> None:
    start_http_server(port)
```

- [x] **Step 4: Viết `backend/app/ops/alerts.py`**

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import httpx

from app.clock import Clock
from app.logging import get_logger

log = get_logger(__name__)


class Alerter(Protocol):
    async def send(self, text: str) -> None: ...


class NullAlerter:
    async def send(self, text: str) -> None:
        log.info("alert_suppressed", text=text)


class TelegramAlerter:
    def __init__(self, token: str, chat_id: str, client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._chat_id = chat_id
        self._client = client

    async def send(self, text: str) -> None:
        if not self._token or not self._chat_id:
            log.info("alert_no_telegram_config", text=text)
            return
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {"chat_id": self._chat_id, "text": text}
        try:
            if self._client is not None:
                await self._client.post(url, json=payload, timeout=10)
            else:
                async with httpx.AsyncClient() as client:
                    await client.post(url, json=payload, timeout=10)
        except httpx.HTTPError as exc:
            log.warning("alert_send_failed", error=str(exc))


class AlertThrottle:
    def __init__(self, clock: Clock, min_gap: timedelta) -> None:
        self._clock = clock
        self._gap = min_gap
        self._last: dict[str, datetime] = {}

    def should_send(self, key: str) -> bool:
        now = self._clock.now()
        last = self._last.get(key)
        if last is not None and now - last < self._gap:
            return False
        self._last[key] = now
        return True


def block_rate_alert(total: int, blocked: int, min_total: int = 20, threshold: float = 0.2) -> str | None:
    if total < min_total:
        return None
    rate = blocked / total
    if rate <= threshold:
        return None
    return f"⚠️ Block rate {rate:.0%} ({blocked}/{total} probes) in the last 15 minutes"


@dataclass(frozen=True)
class RunStats:
    scan_run_id: int
    total_probes: int
    ok_count: int
    sold_out_count: int
    blocked_count: int
    error_count: int

    @property
    def success_rate(self) -> float:
        if self.total_probes == 0:
            return 0.0
        return (self.ok_count + self.sold_out_count) / self.total_probes


def run_summary_alert(stats: RunStats, threshold: float = 0.9) -> str | None:
    if stats.total_probes == 0 or stats.success_rate >= threshold:
        return None
    return (
        f"⚠️ Scan run {stats.scan_run_id} success {stats.success_rate:.0%}: "
        f"ok={stats.ok_count} sold_out={stats.sold_out_count} "
        f"blocked={stats.blocked_count} error={stats.error_count} of {stats.total_probes}"
    )
```

- [x] **Step 5: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_alerts.py -q`
Expected: `6 passed`

- [x] **Step 6: Commit**

```bash
git add backend/app/ops backend/tests/unit/test_alerts.py
git commit -m "feat(ops): prometheus metrics and telegram alerts with throttle"
```

---

### Task 16: Scheduler

**Files:**
- Create: `backend/app/scheduler/__init__.py`, `backend/app/scheduler/planning.py`, `backend/app/scheduler/queue.py`, `backend/app/scheduler/service.py`, `backend/app/scheduler/__main__.py`
- Modify: `backend/app/repo/runs.py` (thêm `stale_queued_jobs`)
- Test: `backend/tests/unit/test_planning.py`, `backend/tests/integration/test_scheduler_service.py`

- [x] **Step 1: Viết test planning (thất bại)**

`backend/tests/unit/test_planning.py`:

```python
from datetime import UTC, date, datetime, timedelta

from app.repo.runs import HotelJobPlan
from app.scheduler.planning import TenantSchedule, WatchRow, build_hotel_plans, compute_triggers

VN = TenantSchedule(id=1, timezone="Asia/Ho_Chi_Minh", scan_times=("06:00", "14:00", "22:00"), horizon_days=30)
BKK = TenantSchedule(id=2, timezone="Asia/Bangkok", scan_times=("06:00",), horizon_days=45)
LON = TenantSchedule(id=3, timezone="Europe/London", scan_times=("06:00",), horizon_days=30)


def test_trigger_due_within_lookback() -> None:
    now = datetime(2026, 9, 23, 23, 3, tzinfo=UTC)  # 06:03 giờ VN ngày 24/09
    triggers = compute_triggers([VN], now, lookback=timedelta(minutes=10))
    assert len(triggers) == 1
    t = triggers[0]
    assert t.key == "2026-09-23T23:00"
    assert t.at == datetime(2026, 9, 23, 23, 0, tzinfo=UTC)
    assert t.tenant_ids == (1,)


def test_no_trigger_outside_lookback() -> None:
    now = datetime(2026, 9, 23, 23, 15, tzinfo=UTC)
    assert compute_triggers([VN], now, lookback=timedelta(minutes=10)) == []


def test_tenants_in_same_utc_minute_share_trigger() -> None:
    now = datetime(2026, 9, 23, 23, 1, tzinfo=UTC)
    triggers = compute_triggers([VN, BKK], now, lookback=timedelta(minutes=10))
    assert len(triggers) == 1 and triggers[0].tenant_ids == (1, 2)


def test_different_timezones_get_different_triggers() -> None:
    now = datetime(2026, 9, 24, 5, 2, tzinfo=UTC)  # 06:02 London (BST) ngày 24/09
    triggers = compute_triggers([VN, LON], now, lookback=timedelta(minutes=10))
    assert [t.tenant_ids for t in triggers] == [(3,)]


def test_build_hotel_plans_merges_horizon_and_start_date() -> None:
    at = datetime(2026, 9, 23, 23, 0, tzinfo=UTC)
    rows = [
        WatchRow(tenant_id=1, hotel_id=10, horizon_days=30, timezone="Asia/Ho_Chi_Minh"),
        WatchRow(tenant_id=2, hotel_id=10, horizon_days=45, timezone="Asia/Bangkok"),
        WatchRow(tenant_id=2, hotel_id=11, horizon_days=45, timezone="Asia/Bangkok"),
        WatchRow(tenant_id=3, hotel_id=12, horizon_days=30, timezone="America/New_York"),
    ]
    plans = build_hotel_plans(rows, at)
    assert plans == [
        HotelJobPlan(10, date(2026, 9, 24), 45),
        HotelJobPlan(11, date(2026, 9, 24), 45),
        HotelJobPlan(12, date(2026, 9, 23), 30),
    ]
```

- [x] **Step 2: Viết test service (thất bại)**

`backend/tests/integration/test_scheduler_service.py`:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.db.models import Hotel, ScanJob, ScanRun, Tenant, TenantHotel
from app.ops.alerts import NullAlerter
from app.scheduler.service import SchedulerService


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[int, int]] = []

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int) -> None:
        self.enqueued.append((scan_run_id, hotel_id))


async def _seed(db: AsyncSession) -> tuple[int, int, int]:
    t1 = Tenant(name="A", timezone="Asia/Ho_Chi_Minh", scan_times=["06:00"], horizon_days=30,
                insight_language="vi", insight_hour="07:30", country_code="vn", active=True)
    t2 = Tenant(name="B", timezone="Asia/Ho_Chi_Minh", scan_times=["06:00", "14:00"], horizon_days=45,
                insight_language="vi", insight_hour="07:30", country_code="vn", active=True)
    h1 = Hotel(booking_url="u1", booking_slug="vn/h1", country_code="vn")
    h2 = Hotel(booking_url="u2", booking_slug="vn/h2", country_code="vn")
    db.add_all([t1, t2, h1, h2])
    await db.flush()
    db.add_all([
        TenantHotel(tenant_id=t1.id, hotel_id=h1.id, role="self", active=True),
        TenantHotel(tenant_id=t2.id, hotel_id=h1.id, role="competitor", active=True),
        TenantHotel(tenant_id=t2.id, hotel_id=h2.id, role="competitor", active=True),
    ])
    await db.commit()
    return t1.id, h1.id, h2.id


def _service(db: AsyncSession, queue: FakeQueue, clock: FixedClock) -> SchedulerService:
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    return SchedulerService(
        session_factory=factory, queue=queue, clock=clock,
        deadline=timedelta(minutes=90), alerter=NullAlerter(), lookback=timedelta(minutes=10),
    )


async def test_tick_creates_one_run_and_enqueues_unique_hotels(db: AsyncSession) -> None:
    _, h1, h2 = await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))  # 06:02 VN
    report = await _service(db, queue, clock).tick()
    assert len(report.created_runs) == 1
    run_id = report.created_runs[0]
    assert sorted(queue.enqueued) == [(run_id, h1), (run_id, h2)]
    jobs = (await db.execute(select(ScanJob).order_by(ScanJob.hotel_id))).scalars().all()
    assert [(j.hotel_id, j.horizon_days) for j in jobs] == [(h1, 45), (h2, 45)]


async def test_tick_twice_does_not_duplicate(db: AsyncSession) -> None:
    await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))
    svc = _service(db, queue, clock)
    await svc.tick()
    clock.advance(minutes=1)
    report = await svc.tick()
    assert report.created_runs == []
    assert len((await db.execute(select(ScanRun))).scalars().all()) == 1


async def test_tick_expires_old_runs(db: AsyncSession) -> None:
    await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))
    svc = _service(db, queue, clock)
    first = await svc.tick()
    clock.advance(minutes=95)
    report = await svc.tick()
    assert report.expired_runs == first.created_runs


async def test_tick_reenqueues_stale_queued_jobs(db: AsyncSession) -> None:
    await _seed(db)
    queue = FakeQueue()
    clock = FixedClock(datetime(2026, 9, 23, 23, 2, tzinfo=UTC))
    svc = _service(db, queue, clock)
    await svc.tick()
    n = len(queue.enqueued)
    clock.advance(minutes=6)
    await svc.tick()
    assert len(queue.enqueued) == 2 * n
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/unit/test_planning.py tests/integration/test_scheduler_service.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.scheduler'`

- [x] **Step 4: Viết `backend/app/scheduler/planning.py`** (`backend/app/scheduler/__init__.py` rỗng)

```python
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.repo.runs import HotelJobPlan


@dataclass(frozen=True)
class TenantSchedule:
    id: int
    timezone: str
    scan_times: tuple[str, ...]
    horizon_days: int


@dataclass(frozen=True)
class Trigger:
    key: str
    at: datetime
    tenant_ids: tuple[int, ...]


@dataclass(frozen=True)
class WatchRow:
    tenant_id: int
    hotel_id: int
    horizon_days: int
    timezone: str


def trigger_key(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def compute_triggers(
    tenants: Iterable[TenantSchedule], now: datetime, lookback: timedelta
) -> list[Trigger]:
    """Mốc giờ quét của mọi tenant rơi vào (now - lookback, now], gom theo phút UTC."""
    buckets: dict[str, tuple[datetime, set[int]]] = {}
    for tenant in tenants:
        tz = ZoneInfo(tenant.timezone)
        local_today = now.astimezone(tz).date()
        for day_offset in (0, -1):
            local_date = local_today + timedelta(days=day_offset)
            for scan_time in tenant.scan_times:
                hh, mm = (int(x) for x in scan_time.split(":"))
                at = datetime.combine(local_date, time(hh, mm), tzinfo=tz).astimezone(UTC)
                if now - lookback < at <= now:
                    key = trigger_key(at)
                    buckets.setdefault(key, (at, set()))[1].add(tenant.id)
    return sorted(
        (Trigger(key, at, tuple(sorted(ids))) for key, (at, ids) in buckets.items()),
        key=lambda t: t.at,
    )


def build_hotel_plans(rows: Iterable[WatchRow], trigger_at: datetime) -> list[HotelJobPlan]:
    """Một job mỗi khách sạn: start_date là ngày địa phương sớm nhất, horizon là lớn nhất."""
    per_hotel: dict[int, tuple[date, int]] = {}
    for row in rows:
        local_date = trigger_at.astimezone(ZoneInfo(row.timezone)).date()
        current = per_hotel.get(row.hotel_id)
        if current is None:
            per_hotel[row.hotel_id] = (local_date, row.horizon_days)
        else:
            per_hotel[row.hotel_id] = (min(current[0], local_date), max(current[1], row.horizon_days))
    return [HotelJobPlan(h, d, n) for h, (d, n) in sorted(per_hotel.items())]
```

- [x] **Step 5: Viết `backend/app/scheduler/queue.py`**

```python
from typing import Protocol

from arq.connections import ArqRedis, RedisSettings, create_pool


class JobQueue(Protocol):
    async def enqueue_probe(self, scan_run_id: int, hotel_id: int) -> None: ...


def probe_job_id(scan_run_id: int, hotel_id: int) -> str:
    return f"probe:{scan_run_id}:{hotel_id}"


class ArqJobQueue:
    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    @classmethod
    async def connect(cls, redis_url: str) -> "ArqJobQueue":
        return cls(await create_pool(RedisSettings.from_dsn(redis_url)))

    async def enqueue_probe(self, scan_run_id: int, hotel_id: int) -> None:
        # _job_id trùng thì arq bỏ qua: đây là chốt idempotent ở tầng hàng đợi.
        await self._redis.enqueue_job(
            "probe_hotel", scan_run_id, hotel_id, _job_id=probe_job_id(scan_run_id, hotel_id)
        )

    async def close(self) -> None:
        await self._redis.aclose()
```

- [x] **Step 6: Thêm `stale_queued_jobs` vào `backend/app/repo/runs.py`** (thêm method vào cuối class `ScanRunRepository`)

```python
    async def stale_queued_jobs(self, queued_before: datetime) -> list[tuple[int, int]]:
        """Job vẫn 'queued' trong run đang chạy được tạo trước `queued_before`: cần đẩy lại hàng đợi."""
        rows = await self._s.execute(
            select(ScanJob.scan_run_id, ScanJob.hotel_id)
            .join(ScanRun, ScanRun.id == ScanJob.scan_run_id)
            .where(ScanJob.status == "queued", ScanRun.status == "running", ScanRun.started_at < queued_before)
        )
        return [(r[0], r[1]) for r in rows]
```

- [x] **Step 7: Viết `backend/app/scheduler/service.py`**

```python
import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.db.models import Tenant, TenantHotel
from app.db.partitions import ensure_room_snapshot_partitions
from app.logging import get_logger
from app.ops.alerts import Alerter, AlertThrottle, block_rate_alert
from app.ops.metrics import QUEUE_DEPTH, RUNS_CREATED
from app.repo.runs import ScanRunRepository
from app.scheduler.planning import TenantSchedule, WatchRow, build_hotel_plans, compute_triggers
from app.scheduler.queue import JobQueue

log = get_logger(__name__)


@dataclass
class TickReport:
    created_runs: list[int] = field(default_factory=list)
    expired_runs: list[int] = field(default_factory=list)
    reenqueued: int = 0
    alerts: list[str] = field(default_factory=list)


class SchedulerService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        queue: JobQueue,
        clock: Clock,
        deadline: timedelta,
        alerter: Alerter,
        lookback: timedelta = timedelta(minutes=10),
        stale_after: timedelta = timedelta(minutes=5),
    ) -> None:
        self._sf = session_factory
        self._queue = queue
        self._clock = clock
        self._deadline = deadline
        self._alerter = alerter
        self._lookback = lookback
        self._stale_after = stale_after
        self._throttle = AlertThrottle(clock, min_gap=timedelta(minutes=30))
        self._partitions_checked_on: date | None = None

    async def _load_tenants(self, s: AsyncSession) -> list[TenantSchedule]:
        rows = (await s.execute(select(Tenant).where(Tenant.active.is_(True)))).scalars().all()
        return [TenantSchedule(t.id, t.timezone, tuple(t.scan_times), t.horizon_days) for t in rows]

    async def _load_watch_rows(self, s: AsyncSession, tenant_ids: tuple[int, ...]) -> list[WatchRow]:
        rows = await s.execute(
            select(TenantHotel.tenant_id, TenantHotel.hotel_id, Tenant.horizon_days, Tenant.timezone)
            .join(Tenant, Tenant.id == TenantHotel.tenant_id)
            .where(TenantHotel.active.is_(True), TenantHotel.tenant_id.in_(tenant_ids))
        )
        return [WatchRow(r[0], r[1], r[2], r[3]) for r in rows]

    async def tick(self) -> TickReport:
        report = TickReport()
        now = self._clock.now()
        async with self._sf() as s:
            repo = ScanRunRepository(s)
            tenants = await self._load_tenants(s)
            for trigger in compute_triggers(tenants, now, self._lookback):
                plans = build_hotel_plans(await self._load_watch_rows(s, trigger.tenant_ids), trigger.at)
                if not plans:
                    continue
                run = await repo.create_run(trigger.key, trigger.at, plans)
                if run is None:
                    continue
                await s.commit()
                for plan in plans:
                    await self._queue.enqueue_probe(run.id, plan.hotel_id)
                RUNS_CREATED.inc()
                QUEUE_DEPTH.set(len(plans))
                report.created_runs.append(run.id)
                log.info("scan_run_created", run_id=run.id, trigger=trigger.key, jobs=len(plans))

            for run_id, hotel_id in await repo.stale_queued_jobs(now - self._stale_after):
                await self._queue.enqueue_probe(run_id, hotel_id)
                report.reenqueued += 1

            report.expired_runs = await repo.expire_runs(self._deadline, now)
            await s.commit()
            if report.expired_runs:
                log.warning("scan_runs_expired", run_ids=report.expired_runs)

            total, blocked = await repo.probe_stats_since(now - timedelta(minutes=15))
            msg = block_rate_alert(total, blocked)
            if msg and self._throttle.should_send("block_rate"):
                await self._alerter.send(msg)
                report.alerts.append(msg)

            today = now.date()
            if self._partitions_checked_on != today:
                conn = await s.connection()
                created = await ensure_room_snapshot_partitions(conn, today, months=3)
                await s.commit()
                self._partitions_checked_on = today
                if created:
                    log.info("partitions_created", names=created)
        return report

    async def run_forever(self, interval_seconds: float = 60.0) -> None:
        log.info("scheduler_started", interval=interval_seconds)
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("scheduler_tick_failed")
            await asyncio.sleep(interval_seconds)
```

- [x] **Step 8: Viết `backend/app/scheduler/__main__.py`**

```python
import asyncio
from datetime import timedelta

from app.clock import SystemClock
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging
from app.ops.alerts import TelegramAlerter
from app.ops.metrics import start_metrics_server
from app.scheduler.queue import ArqJobQueue
from app.scheduler.service import SchedulerService


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    start_metrics_server(settings.metrics_port)
    engine = make_engine(settings.database_url)
    queue = await ArqJobQueue.connect(settings.redis_url)
    service = SchedulerService(
        session_factory=make_session_factory(engine),
        queue=queue,
        clock=SystemClock(),
        deadline=timedelta(minutes=settings.run_deadline_minutes),
        alerter=TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id),
    )
    try:
        await service.run_forever()
    finally:
        await queue.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [x] **Step 9: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/unit/test_planning.py tests/integration/test_scheduler_service.py -q`
Expected: `9 passed`

- [x] **Step 10: Commit**

```bash
git add backend/app/scheduler backend/app/repo/runs.py backend/tests/unit/test_planning.py backend/tests/integration/test_scheduler_service.py
git commit -m "feat(scheduler): trigger planning, run creation, job enqueue, deadline expiry"
```

---

### Task 17: Worker: job probe_hotel và cấu hình arq

**Files:**
- Create: `backend/app/worker/__init__.py`, `backend/app/worker/jobs.py`, `backend/app/worker/session_listener.py`, `backend/app/worker/settings.py`
- Test: `backend/tests/integration/test_worker_job.py`, `backend/tests/integration/test_session_listener.py`

- [x] **Step 1: Viết test job (thất bại)**

`backend/tests/integration/test_worker_job.py`:

```python
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import FixedClock
from app.collector.fake import FakeCollector
from app.collector.storage import MemoryRawStore
from app.db.models import Hotel, HotelCalendar, Probe, RoomSnapshot, ScanJob, ScanRun
from app.domain.models import CalendarDay, CalendarResult, ProbeStatus
from app.ops.alerts import NullAlerter
from app.repo.runs import HotelJobPlan, ScanRunRepository
from app.worker.jobs import JobFailed, WorkerDeps, run_probe_hotel
from tests.fakes import OFFER

NOW = datetime(2026, 9, 23, 23, 5, tzinfo=UTC)
START = date(2026, 9, 24)


async def _seed(db: AsyncSession, horizon: int = 3) -> tuple[int, int]:
    hotel = Hotel(booking_url="u", booking_slug="vn/h1", country_code="vn")
    db.add(hotel)
    await db.flush()
    run = await ScanRunRepository(db).create_run("k", NOW, [HotelJobPlan(hotel.id, START, horizon)])
    assert run is not None
    await db.commit()
    return run.id, hotel.id


def _deps(db: AsyncSession, collector: FakeCollector, store: MemoryRawStore) -> WorkerDeps:
    return WorkerDeps(
        session_factory=async_sessionmaker(db.bind, expire_on_commit=False),  # type: ignore[arg-type]
        collector=collector, raw_store=store, clock=FixedClock(NOW), page_cap=10,
        default_adults=2, parser_version="1", alerter=NullAlerter(), worker_id="w1",
    )


def _calendar(*days: tuple[date, bool, int]) -> CalendarResult:
    return CalendarResult(ok=True, days=tuple(CalendarDay(d, a, m, None) for d, a, m in days))


async def test_happy_path_probes_skips_and_finishes_run(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=3)
    collector = FakeCollector()
    collector.set_calendar(hotel_id, _calendar((START, True, 1), (START + timedelta(days=1), False, 1), (START + timedelta(days=2), True, 2)))
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    collector.set_probe(hotel_id, START + timedelta(days=2), ProbeStatus.OK, offers=(OFFER,), nights=2)
    store = MemoryRawStore()

    summary = await run_probe_hotel(_deps(db, collector, store), run_id, hotel_id, final_attempt=True)

    assert (summary.probed, summary.skipped, summary.failed, summary.run_finished) == (2, 1, 0, True)
    assert collector.probe_calls == [(hotel_id, START, 1, 2), (hotel_id, START + timedelta(days=2), 2, 2)]
    probes = (await db.execute(select(Probe).order_by(Probe.stay_date))).scalars().all()
    assert [p.status for p in probes] == ["ok", "skipped_calendar", "ok"]
    assert probes[2].nights == 2
    assert probes[0].raw_object_key in store.items
    assert len((await db.execute(select(RoomSnapshot))).scalars().all()) == 2
    assert len((await db.execute(select(HotelCalendar))).scalars().all()) == 3
    job = (await db.execute(select(ScanJob))).scalar_one()
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert job.status == "done" and run.status == "completed"
    assert run.ok_count == 2 and run.sold_out_count == 1


async def test_rerun_is_idempotent(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=2)
    collector = FakeCollector()
    collector.set_calendar(hotel_id, _calendar((START, True, 1), (START + timedelta(days=1), True, 1)))
    collector.set_probe(hotel_id, START, ProbeStatus.OK, offers=(OFFER,))
    collector.set_probe(hotel_id, START + timedelta(days=1), ProbeStatus.OK, offers=(OFFER,))
    deps = _deps(db, collector, MemoryRawStore())
    await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    second = await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    assert second.probed == 0 and len(collector.probe_calls) == 2
    assert len((await db.execute(select(Probe))).scalars().all()) == 2


async def test_calendar_failure_probes_every_day_with_one_night(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=2)
    collector = FakeCollector()  # calendar không kịch bản -> ok=False
    collector.set_probe(hotel_id, START, ProbeStatus.NO_ROOMS_1N)
    collector.set_probe(hotel_id, START + timedelta(days=1), ProbeStatus.OK, offers=(OFFER,))
    await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, final_attempt=True)
    assert [c[2] for c in collector.probe_calls] == [1, 1]
    probes = (await db.execute(select(Probe).order_by(Probe.stay_date))).scalars().all()
    assert [p.status for p in probes] == ["no_rooms_1n", "ok"]


async def test_blocked_probe_is_recorded_and_retried_next_run_only(db: AsyncSession) -> None:
    run_id, hotel_id = await _seed(db, horizon=1)
    collector = FakeCollector()
    collector.set_calendar(hotel_id, _calendar((START, True, 1)))
    collector.set_probe(hotel_id, START, ProbeStatus.BLOCKED, raw_html=None)
    summary = await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, final_attempt=True)
    assert summary.failed == 1 and summary.run_finished
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.status == "completed" and run.blocked_count == 1


async def test_collector_exception_becomes_error_probe(db: AsyncSession) -> None:
    class Exploding(FakeCollector):
        async def probe(self, hotel, checkin, nights, adults):  # type: ignore[no-untyped-def]
            raise RuntimeError("kaboom")

    run_id, hotel_id = await _seed(db, horizon=1)
    collector = Exploding()
    collector.set_calendar(hotel_id, _calendar((START, True, 1)))
    summary = await run_probe_hotel(_deps(db, collector, MemoryRawStore()), run_id, hotel_id, final_attempt=True)
    assert summary.failed == 1
    probe = (await db.execute(select(Probe))).scalar_one()
    assert probe.status == "error" and "kaboom" in (probe.error or "")


async def test_fatal_error_marks_job_failed_and_raises(db: AsyncSession) -> None:
    class BrokenCalendar(FakeCollector):
        async def fetch_calendar(self, hotel, start, days, adults):  # type: ignore[no-untyped-def]
            raise RuntimeError("db gone")

    run_id, hotel_id = await _seed(db, horizon=1)
    deps = _deps(db, BrokenCalendar(), MemoryRawStore())
    try:
        await run_probe_hotel(deps, run_id, hotel_id, final_attempt=False)
    except JobFailed as exc:
        assert "db gone" in str(exc)
    else:
        raise AssertionError("expected JobFailed")
    job = (await db.execute(select(ScanJob))).scalar_one()
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert job.status == "failed" and run.status == "running"  # chưa phải lần cuối, run chờ retry

    try:
        await run_probe_hotel(deps, run_id, hotel_id, final_attempt=True)
    except JobFailed:
        pass
    db.expire_all()
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.status == "partial"
```

- [x] **Step 2: Viết test session listener (thất bại)**

`backend/tests/integration/test_session_listener.py`:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collector.proxy import ProxyEndpoint
from app.collector.session import ScrapeSession
from app.db.models import ScrapeSessionRow
from app.worker.session_listener import DbSessionListener

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)


def _session() -> ScrapeSession:
    proxy = ProxyEndpoint(server="http://h:1", username="u", password="p", country="vn", session_id="abc", url="http://u:p@h:1")
    return ScrapeSession(id="sess1", proxy=proxy, cookies={}, user_agent="ua", csrf_token=None, created_at=NOW)


async def test_listener_persists_created_and_retired(db: AsyncSession) -> None:
    listener = DbSessionListener(async_sessionmaker(db.bind, expire_on_commit=False), worker_id="w1", max_age=timedelta(minutes=20))  # type: ignore[arg-type]
    s = _session()
    await listener.session_created(s)
    s.request_count = 12
    await listener.session_retired(s, "blocked")
    row = (await db.execute(select(ScrapeSessionRow))).scalar_one()
    assert row.id == "sess1" and row.worker_id == "w1" and row.proxy_id == "vn:abc"
    assert row.expires_at == NOW + timedelta(minutes=20)
    assert row.status == "retired:blocked" and row.request_count == 12 and row.retired_at is not None
```

- [x] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/integration/test_worker_job.py tests/integration/test_session_listener.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.worker'`

- [x] **Step 4: Viết `backend/app/worker/session_listener.py`** (`backend/app/worker/__init__.py` rỗng)

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collector.session import ScrapeSession
from app.db.models import ScrapeSessionRow
from app.ops.metrics import SESSIONS_CREATED, SESSIONS_RETIRED


class DbSessionListener:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], worker_id: str, max_age: timedelta
    ) -> None:
        self._sf = session_factory
        self._worker_id = worker_id
        self._max_age = max_age

    async def session_created(self, session: ScrapeSession) -> None:
        SESSIONS_CREATED.labels(session.country).inc()
        async with self._sf() as s:
            s.add(
                ScrapeSessionRow(
                    id=session.id, worker_id=self._worker_id, proxy_id=session.proxy.id,
                    proxy_country=session.country, created_at=session.created_at,
                    expires_at=session.created_at + self._max_age, status="active",
                )
            )
            await s.commit()

    async def session_retired(self, session: ScrapeSession, reason: str) -> None:
        SESSIONS_RETIRED.labels(reason).inc()
        async with self._sf() as s:
            await s.execute(
                update(ScrapeSessionRow)
                .where(ScrapeSessionRow.id == session.id)
                .values(
                    retired_at=datetime.now(tz=UTC), status=f"retired:{reason}",
                    request_count=session.request_count, block_count=session.block_count,
                )
            )
            await s.commit()
```

- [x] **Step 5: Viết `backend/app/worker/jobs.py`**

```python
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.collector.base import Collector
from app.collector.booking.results import failed_result
from app.collector.storage import RawStore, raw_key
from app.domain.models import ProbeMethod, ProbeStatus
from app.logging import get_logger
from app.ops.alerts import Alerter, RunStats, run_summary_alert
from app.ops.metrics import JOBS_TOTAL, PROBE_DURATION, PROBES_TOTAL
from app.repo.runs import ScanRunRepository
from app.repo.snapshots import SnapshotRepository

log = get_logger(__name__)


class JobFailed(RuntimeError):
    pass


@dataclass
class WorkerDeps:
    session_factory: async_sessionmaker[AsyncSession]
    collector: Collector
    raw_store: RawStore
    clock: Clock
    page_cap: int
    default_adults: int
    parser_version: str
    alerter: Alerter
    worker_id: str


@dataclass
class JobSummary:
    scan_run_id: int
    hotel_id: int
    probed: int = 0
    skipped: int = 0
    failed: int = 0
    run_finished: bool = False


async def run_probe_hotel(
    deps: WorkerDeps, scan_run_id: int, hotel_id: int, final_attempt: bool
) -> JobSummary:
    summary = JobSummary(scan_run_id, hotel_id)
    log_ctx = log.bind(run_id=scan_run_id, hotel_id=hotel_id, worker=deps.worker_id)

    async with deps.session_factory() as s:
        runs = ScanRunRepository(s)
        job = await runs.start_job(scan_run_id, hotel_id, deps.clock.now())
        if job is None:
            log_ctx.info("job_already_done")
            return summary
        hotel = await runs.load_hotel(hotel_id)
        start_date, horizon = job.start_date, job.horizon_days
        await s.commit()

    status, error = "done", None
    try:
        calendar = await deps.collector.fetch_calendar(hotel, start_date, horizon, deps.default_adults)
        async with deps.session_factory() as s:
            snaps = SnapshotRepository(s, deps.page_cap)
            await snaps.write_calendar(hotel_id, scan_run_id, calendar, deps.clock.now())
            done_dates = await snaps.terminal_dates(scan_run_id, hotel_id)
            await s.commit()
        if not calendar.ok:
            log_ctx.warning("calendar_unavailable", error=calendar.error)

        for offset in range(horizon):
            stay_date = start_date + timedelta(days=offset)
            if stay_date in done_dates:
                continue
            day = calendar.day(stay_date) if calendar.ok else None
            fetched_at = deps.clock.now()

            if day is not None and not day.available:
                async with deps.session_factory() as s:
                    await SnapshotRepository(s, deps.page_cap).write_skipped(
                        scan_run_id, hotel_id, stay_date, nights=day.min_length_of_stay,
                        adults=deps.default_adults, fetched_at=fetched_at,
                    )
                    await s.commit()
                PROBES_TOTAL.labels(str(ProbeStatus.SKIPPED_CALENDAR), str(ProbeMethod.CALENDAR)).inc()
                summary.skipped += 1
                continue

            nights = day.min_length_of_stay if day is not None else 1
            try:
                result = await deps.collector.probe(hotel, stay_date, nights, deps.default_adults)
            except Exception as exc:  # noqa: BLE001
                log_ctx.exception("probe_raised", stay_date=str(stay_date))
                result = failed_result(
                    ProbeStatus.ERROR, method=ProbeMethod.HTTP, checkin=stay_date, nights=nights,
                    adults=deps.default_adults, error=f"{type(exc).__name__}: {exc}",
                )

            key: str | None = None
            if result.raw_html:
                key = raw_key(scan_run_id, hotel_id, stay_date, fetched_at)
                try:
                    await deps.raw_store.put_html(key, result.raw_html)
                except Exception:  # noqa: BLE001
                    log_ctx.exception("raw_store_failed", key=key)
                    key = None

            async with deps.session_factory() as s:
                await SnapshotRepository(s, deps.page_cap).write_probe(
                    scan_run_id, hotel_id, stay_date, result, key, deps.parser_version,
                    hotel.country_code, fetched_at,
                )
                await s.commit()

            PROBES_TOTAL.labels(str(result.status), str(result.method)).inc()
            PROBE_DURATION.observe(result.duration_ms / 1000)
            summary.probed += 1
            if result.status in (ProbeStatus.BLOCKED, ProbeStatus.ERROR):
                summary.failed += 1
    except Exception as exc:  # noqa: BLE001
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        log_ctx.exception("job_failed")

    now = deps.clock.now()
    async with deps.session_factory() as s:
        runs = ScanRunRepository(s)
        await runs.finish_job(scan_run_id, hotel_id, status, now, error)
        if status == "done" or final_attempt:
            summary.run_finished = await runs.try_finish_run(scan_run_id, now)
        await s.commit()
        if summary.run_finished:
            run = await runs.get_run(scan_run_id)
            msg = run_summary_alert(
                RunStats(run.id, run.total_probes, run.ok_count, run.sold_out_count, run.blocked_count, run.error_count)
            )
            log_ctx.info("scan_run_finished", status=run.status, ok=run.ok_count, blocked=run.blocked_count)
            if msg:
                await deps.alerter.send(msg)

    JOBS_TOTAL.labels(status).inc()
    if status == "failed":
        raise JobFailed(error or "unknown")
    log_ctx.info("job_done", probed=summary.probed, skipped=summary.skipped, failed=summary.failed)
    return summary
```

- [x] **Step 6: Viết `backend/app/worker/settings.py`** (cấu hình arq, lắp ráp mọi thành phần thật)

```python
import socket
from datetime import timedelta
from typing import Any

from arq.connections import RedisSettings

from app.clock import SystemClock
from app.collector.booking.browser import BrowserCollector
from app.collector.booking.hybrid import HybridCollector
from app.collector.booking.playwright_bootstrap import PlaywrightBootstrapper
from app.collector.booking.selectors import PARSER_VERSION
from app.collector.fetch import CurlFetcher
from app.collector.proxy import StaticProxyProvider
from app.collector.ratelimit import RateLimiter
from app.collector.session import SessionManager
from app.collector.storage import S3RawStore
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging, get_logger
from app.ops.alerts import TelegramAlerter
from app.ops.metrics import start_metrics_server
from app.worker.jobs import WorkerDeps, run_probe_hotel
from app.worker.session_listener import DbSessionListener

log = get_logger(__name__)
MAX_TRIES = 2


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    start_metrics_server(settings.metrics_port)
    worker_id = socket.gethostname()

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    raw_store = S3RawStore(
        bucket=settings.minio_bucket, endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key, secret_key=settings.minio_secret_key,
    )
    await raw_store.ensure_bucket()

    proxies = StaticProxyProvider(settings.proxy_url_template)
    max_age = timedelta(minutes=settings.session_max_age_minutes)
    sessions = SessionManager(
        bootstrapper=PlaywrightBootstrapper(headless=settings.playwright_headless),
        proxy_provider=proxies,
        max_age=max_age,
        max_requests=settings.session_max_requests,
        clock=SystemClock(),
        listener=DbSessionListener(session_factory, worker_id, max_age),
    )
    fetcher = CurlFetcher()
    collector = HybridCollector(
        sessions=sessions,
        fetcher=fetcher,
        limiter=RateLimiter(settings.request_min_interval_seconds, settings.request_jitter_seconds),
        fallback=BrowserCollector(proxies, headless=settings.playwright_headless),
    )
    ctx["engine"] = engine
    ctx["fetcher"] = fetcher
    ctx["deps"] = WorkerDeps(
        session_factory=session_factory, collector=collector, raw_store=raw_store,
        clock=SystemClock(), page_cap=settings.page_dropdown_cap,
        default_adults=settings.default_adults, parser_version=PARSER_VERSION,
        alerter=TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id),
        worker_id=worker_id,
    )
    log.info("worker_started", worker=worker_id)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["fetcher"].close_all()
    await ctx["engine"].dispose()


async def probe_hotel(ctx: dict[str, Any], scan_run_id: int, hotel_id: int) -> dict[str, int]:
    final_attempt = int(ctx.get("job_try", 1)) >= MAX_TRIES
    summary = await run_probe_hotel(ctx["deps"], scan_run_id, hotel_id, final_attempt=final_attempt)
    return {"probed": summary.probed, "skipped": summary.skipped, "failed": summary.failed}


class WorkerSettings:
    functions = [probe_hotel]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1          # một khách sạn một lúc mỗi tiến trình; scale bằng số tiến trình
    job_timeout = 3600
    max_tries = MAX_TRIES
    keep_result = 3600
```

- [x] **Step 7: Chạy test, xác nhận đạt**

Run: `cd backend && uv run pytest tests/integration/test_worker_job.py tests/integration/test_session_listener.py -q`
Expected: `7 passed`

- [x] **Step 8: Kiểm tra arq nhận cấu hình**

Run: `cd backend && uv run arq app.worker.settings.WorkerSettings --check`
Expected: in ra thông tin worker hoặc `Health check failed: no health check sentinel value found` (chưa có worker chạy, chấp nhận được). Không được có lỗi import.

- [x] **Step 9: Commit**

```bash
git add backend/app/worker backend/tests/integration/test_worker_job.py backend/tests/integration/test_session_listener.py
git commit -m "feat(worker): probe_hotel job with calendar-first probing and arq wiring"
```

---

### Task 18: CLI vận hành

**Files:**
- Create: `backend/app/cli.py`
- Test: `backend/tests/integration/test_cli.py`

- [x] **Step 1: Viết test CLI (thất bại)**

`backend/tests/integration/test_cli.py`:

```python
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app.cli import app
from app.db.models import Hotel, ScanRun, Tenant, TenantHotel

runner = CliRunner()


@pytest.fixture(autouse=True)
def _point_cli_at_test_db(migrated_db_url: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    monkeypatch.setenv("PROXY_URL_TEMPLATE", "http://u-{country}-{session}:p@h:1")
    from app.config import get_settings

    get_settings.cache_clear()


async def test_add_tenant_and_hotel(db: AsyncSession) -> None:
    r = runner.invoke(app, ["add-tenant", "Khách sạn A", "--timezone", "Asia/Ho_Chi_Minh", "--horizon", "30"])
    assert r.exit_code == 0, r.output
    tenant = (await db.execute(select(Tenant))).scalar_one()
    assert tenant.name == "Khách sạn A" and tenant.scan_times == ["06:00", "14:00", "22:00"]

    r = runner.invoke(app, ["add-hotel", str(tenant.id), "https://www.booking.com/hotel/vn/the-reverie-saigon.html?aid=1", "--role", "competitor", "--label", "Reverie"])
    assert r.exit_code == 0, r.output
    hotel = (await db.execute(select(Hotel))).scalar_one()
    link = (await db.execute(select(TenantHotel))).scalar_one()
    assert hotel.booking_slug == "vn/the-reverie-saigon" and hotel.country_code == "vn"
    assert link.role == "competitor" and link.label == "Reverie"

    r = runner.invoke(app, ["add-hotel", str(tenant.id), "https://www.booking.com/hotel/vn/the-reverie-saigon.html", "--role", "self"])
    assert r.exit_code == 0, r.output
    db.expire_all()  # CLI ghi bằng session khác, buộc đọc lại từ DB
    assert len((await db.execute(select(Hotel))).scalars().all()) == 1
    link = (await db.execute(select(TenantHotel))).scalar_one()
    assert link.role == "self"


async def test_add_hotel_rejects_bad_url(db: AsyncSession) -> None:
    runner.invoke(app, ["add-tenant", "T"])
    tenant = (await db.execute(select(Tenant))).scalar_one()
    r = runner.invoke(app, ["add-hotel", str(tenant.id), "https://www.booking.com/searchresults.html"])
    assert r.exit_code == 1 and "not a hotel page url" in r.output


async def test_scan_now_creates_run_without_queue(db: AsyncSession) -> None:
    runner.invoke(app, ["add-tenant", "T"])
    tenant = (await db.execute(select(Tenant))).scalar_one()
    runner.invoke(app, ["add-hotel", str(tenant.id), "https://www.booking.com/hotel/vn/x.html"])
    r = runner.invoke(app, ["scan-now", "--no-enqueue"])
    assert r.exit_code == 0, r.output
    run = (await db.execute(select(ScanRun))).scalar_one()
    assert run.total_jobs == 1 and run.trigger_key.startswith("manual:")
```

- [x] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && uv run pytest tests/integration/test_cli.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.cli'`

- [x] **Step 3: Viết `backend/app/cli.py`**

```python
import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import SystemClock
from app.collector.booking.parser import parse_hotel_page
from app.collector.booking.selectors import PARSER_VERSION
from app.collector.booking.urls import currency_for
from app.collector.storage import S3RawStore
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.db.models import Hotel, Probe, Tenant, TenantHotel
from app.db.partitions import ensure_room_snapshot_partitions
from app.domain.booking_url import BookingUrlError, parse_booking_url
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus
from app.logging import configure_logging
from app.repo.runs import ScanRunRepository
from app.repo.snapshots import SnapshotRepository
from app.scheduler.planning import WatchRow, build_hotel_plans
from app.scheduler.queue import ArqJobQueue

app = typer.Typer(help="Vận hành hệ thống theo dõi đối thủ khách sạn")
T = TypeVar("T")


def _run(fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def _inner() -> T:
        settings = get_settings()
        configure_logging(settings.log_level)
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as s:
                return await fn(s)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@app.command("add-tenant")
def add_tenant(
    name: str,
    timezone: str = typer.Option("Asia/Ho_Chi_Minh", "--timezone"),
    horizon: int = typer.Option(30, "--horizon"),
    scan_times: str = typer.Option("06:00,14:00,22:00", "--scan-times"),
    country: str = typer.Option("vn", "--country"),
) -> None:
    async def _do(s: AsyncSession) -> int:
        tenant = Tenant(
            name=name, timezone=timezone, horizon_days=horizon,
            scan_times=[t.strip() for t in scan_times.split(",")], country_code=country,
        )
        s.add(tenant)
        await s.commit()
        return tenant.id

    typer.echo(f"tenant created id={_run(_do)}")


@app.command("add-hotel")
def add_hotel(
    tenant_id: int,
    url: str,
    role: str = typer.Option("competitor", "--role"),
    label: str | None = typer.Option(None, "--label"),
) -> None:
    try:
        ref = parse_booking_url(url)
    except BookingUrlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    if role not in ("self", "competitor"):
        typer.echo("role must be self or competitor")
        raise typer.Exit(code=1)

    async def _do(s: AsyncSession) -> int:
        hotel = (await s.execute(select(Hotel).where(Hotel.booking_slug == ref.slug))).scalar_one_or_none()
        if hotel is None:
            hotel = Hotel(booking_url=ref.canonical_url, booking_slug=ref.slug, country_code=ref.country_code)
            s.add(hotel)
            await s.flush()
        link = (
            await s.execute(
                select(TenantHotel).where(TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel.id)
            )
        ).scalar_one_or_none()
        if link is None:
            s.add(TenantHotel(tenant_id=tenant_id, hotel_id=hotel.id, role=role, label=label, active=True))
        else:
            link.role, link.label, link.active = role, label, True
        await s.commit()
        return hotel.id

    typer.echo(f"hotel linked id={_run(_do)} slug={ref.slug}")


@app.command("scan-now")
def scan_now(enqueue: bool = typer.Option(True, "--enqueue/--no-enqueue")) -> None:
    """Tạo một scan run thủ công cho mọi tenant đang hoạt động và đẩy job vào hàng đợi."""

    async def _do(s: AsyncSession) -> tuple[int, int] | None:
        now = datetime.now(tz=UTC)
        rows = await s.execute(
            select(TenantHotel.tenant_id, TenantHotel.hotel_id, Tenant.horizon_days, Tenant.timezone)
            .join(Tenant, Tenant.id == TenantHotel.tenant_id)
            .where(TenantHotel.active.is_(True), Tenant.active.is_(True))
        )
        plans = build_hotel_plans([WatchRow(r[0], r[1], r[2], r[3]) for r in rows], now)
        if not plans:
            return None
        run = await ScanRunRepository(s).create_run(f"manual:{now:%Y%m%dT%H%M%S}", now, plans)
        if run is None:
            return None
        await s.commit()
        if enqueue:
            queue = await ArqJobQueue.connect(get_settings().redis_url)
            try:
                for p in plans:
                    await queue.enqueue_probe(run.id, p.hotel_id)
            finally:
                await queue.close()
        return run.id, len(plans)

    result = _run(_do)
    if result is None:
        typer.echo("nothing to scan")
        raise typer.Exit(code=1)
    typer.echo(f"scan run {result[0]} created with {result[1]} jobs (enqueued={enqueue})")


@app.command("ensure-partitions")
def ensure_partitions(months: int = typer.Option(3, "--months")) -> None:
    async def _do(s: AsyncSession) -> list[str]:
        conn = await s.connection()
        created = await ensure_room_snapshot_partitions(conn, datetime.now(tz=UTC).date(), months)
        await s.commit()
        return created

    typer.echo(f"created: {_run(_do)}")


@app.command("reparse")
def reparse(since_days: int = typer.Option(30, "--since-days")) -> None:
    """Parse lại HTML thô trong MinIO cho probe `ok` gần đây bằng parser hiện tại."""

    async def _do(s: AsyncSession) -> tuple[int, int]:
        settings = get_settings()
        store = S3RawStore(settings.minio_bucket, settings.minio_endpoint, settings.minio_access_key, settings.minio_secret_key)
        cutoff = datetime.now(tz=UTC) - timedelta(days=since_days)
        probes = (
            await s.execute(
                select(Probe, Hotel.country_code)
                .join(Hotel, Hotel.id == Probe.hotel_id)
                .where(Probe.fetched_at >= cutoff, Probe.raw_object_key.is_not(None), Probe.status == str(ProbeStatus.OK))
                .order_by(Probe.id)
            )
        ).all()
        repo = SnapshotRepository(s, settings.page_dropdown_cap)
        done = missing = 0
        for probe, country in probes:
            assert probe.raw_object_key is not None
            html = await store.get_html(probe.raw_object_key)
            if html is None:
                missing += 1
                continue
            page = parse_hotel_page(html, currency_for(country))
            result = ProbeResult(
                status=ProbeStatus.OK if page.offers else ProbeStatus.NO_ROOMS_1N,
                method=ProbeMethod(probe.method or "http"), checkin=probe.checkin, checkout=probe.checkout,
                nights=probe.nights, adults=probe.adults, offers=page.offers, raw_html=None,
                http_status=probe.http_status, session_id=probe.session_id, duration_ms=probe.duration_ms,
                booking_hotel_id=page.booking_hotel_id, hotel_name=page.hotel_name,
            )
            await repo.write_probe(
                probe.scan_run_id, probe.hotel_id, probe.stay_date, result, probe.raw_object_key,
                PARSER_VERSION, probe.proxy_country, probe.fetched_at,
            )
            done += 1
            if done % 200 == 0:
                await s.commit()
        await s.commit()
        return done, missing

    done, missing = _run(_do)
    typer.echo(f"reparsed={done} missing_raw={missing} parser_version={PARSER_VERSION}")


@app.command("run-status")
def run_status(limit: int = typer.Option(5, "--limit")) -> None:
    async def _do(s: AsyncSession) -> list[str]:
        from app.db.models import ScanRun

        runs = (await s.execute(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit))).scalars().all()
        return [
            f"run {r.id} {r.trigger_key} {r.status} jobs={r.total_jobs} probes={r.total_probes} "
            f"ok={r.ok_count} sold_out={r.sold_out_count} blocked={r.blocked_count} error={r.error_count}"
            for r in runs
        ]

    for line in _run(_do):
        typer.echo(line)


if __name__ == "__main__":
    app()
```

Thêm vào `backend/pyproject.toml` dưới `[project]`:

```toml
[project.scripts]
sb = "app.cli:app"
```

- [x] **Step 4: Chạy test, xác nhận đạt**

Run: `cd backend && uv sync && uv run pytest tests/integration/test_cli.py -q`
Expected: `3 passed`

- [x] **Step 5: Commit**

```bash
git add backend/app/cli.py backend/pyproject.toml backend/uv.lock backend/tests/integration/test_cli.py
git commit -m "feat(cli): add-tenant, add-hotel, scan-now, ensure-partitions, reparse, run-status"
```

---

### Task 19: Dockerfile, dịch vụ ứng dụng trong Compose, monitoring, CI

**Files:**
- Create: `infra/Dockerfile.backend`, `infra/docker-compose.collector.yml`, `infra/docker-compose.monitoring.yml`, `infra/prometheus/prometheus.yml`, `infra/grafana/provisioning/datasources/datasource.yml`, `.github/workflows/ci.yml`
- Modify: `infra/docker-compose.yml` (thêm scheduler, worker, migrate)

- [x] **Step 1: Viết `infra/Dockerfile.backend`**

```dockerfile
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

RUN /opt/venv/bin/playwright install --with-deps chromium

COPY backend/ ./
RUN uv sync --frozen --no-dev

ENV PATH="/opt/venv/bin:$PATH"
CMD ["python", "-m", "app.scheduler"]
```

- [x] **Step 2: Thêm dịch vụ ứng dụng vào `infra/docker-compose.yml`** (thêm dưới `minio:`, trước `volumes:`)

```yaml
  migrate:
    build:
      context: ..
      dockerfile: infra/Dockerfile.backend
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/scrapebooking
    command: ["alembic", "upgrade", "head"]
    depends_on:
      postgres: { condition: service_healthy }

  scheduler:
    build:
      context: ..
      dockerfile: infra/Dockerfile.backend
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/scrapebooking
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: http://minio:9000
    command: ["python", "-m", "app.scheduler"]
    depends_on:
      migrate: { condition: service_completed_successfully }
      redis: { condition: service_healthy }
    restart: unless-stopped

  worker:
    build:
      context: ..
      dockerfile: infra/Dockerfile.backend
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/scrapebooking
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: http://minio:9000
    command: ["arq", "app.worker.settings.WorkerSettings"]
    depends_on:
      migrate: { condition: service_completed_successfully }
      redis: { condition: service_healthy }
      minio: { condition: service_healthy }
    deploy:
      resources:
        limits:
          memory: 1500M
    shm_size: "512m"
    restart: unless-stopped
```

- [x] **Step 3: Viết `infra/docker-compose.collector.yml`** (chạy worker trên máy khác, trỏ về hạ tầng trung tâm qua biến môi trường)

```yaml
name: scrapebooking-collector

services:
  worker:
    build:
      context: ..
      dockerfile: infra/Dockerfile.backend
    env_file: ../.env
    command: ["arq", "app.worker.settings.WorkerSettings"]
    deploy:
      resources:
        limits:
          memory: 1500M
    shm_size: "512m"
    restart: unless-stopped
```

Trên máy worker, `.env` phải có `DATABASE_URL`, `REDIS_URL`, `MINIO_ENDPOINT` trỏ về IP hoặc hostname của máy trung tâm.

- [x] **Step 4: Viết `infra/docker-compose.monitoring.yml`**

```yaml
name: scrapebooking

services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - promdata:/prometheus
    ports: ["9090:9090"]
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - grafanadata:/var/lib/grafana
    ports: ["3001:3000"]
    depends_on: [prometheus]
    restart: unless-stopped

volumes:
  promdata:
  grafanadata:
```

- [x] **Step 5: Viết `infra/prometheus/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: scheduler
    static_configs:
      - targets: ["scheduler:9100"]
  - job_name: worker
    dns_sd_configs:
      - names: ["worker"]
        type: A
        port: 9100
```

- [x] **Step 6: Viết `infra/grafana/provisioning/datasources/datasource.yml`**

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

- [x] **Step 7: Viết `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: app
          POSTGRES_PASSWORD: app
          POSTGRES_DB: scrapebooking_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U app -d scrapebooking_test"
          --health-interval 5s --health-timeout 3s --health-retries 10
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
      minio:
        image: bitnami/minio:latest
        env:
          MINIO_ROOT_USER: minioadmin
          MINIO_ROOT_PASSWORD: minioadmin
        ports: ["9000:9000"]
    env:
      DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/scrapebooking_test
      TEST_DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/scrapebooking_test
      REDIS_URL: redis://localhost:6379/0
      MINIO_ENDPOINT: http://localhost:9000
      PROXY_URL_TEMPLATE: http://u-{country}-{session}:p@h:1
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run playwright install --with-deps chromium
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run mypy app
      - run: uv run pytest -q -m "not live"
```

- [ ] **Step 8: Build image và chạy full stack một lần**

Run:

```bash
cp .env.example .env   # rồi điền PROXY_URL_TEMPLATE thật và TELEGRAM_* nếu có
docker compose -f infra/docker-compose.yml build
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs --tail=20 scheduler worker
```

Expected: `migrate` exited 0; `scheduler` log có `scheduler_started`; `worker` log có `worker_started`. Nếu worker báo `ensure_bucket` lỗi, kiểm tra MinIO healthcheck và biến `MINIO_ENDPOINT`.

- [x] **Step 9: Chạy lint và typecheck, sửa cho sạch**

Run: `make lint && make typecheck && make test-int`
Expected: ruff không báo lỗi, mypy `Success: no issues found`, pytest toàn bộ unit và integration đạt.

- [x] **Step 10: Commit**

```bash
git add infra .github
git commit -m "infra: backend image, compose app services, monitoring profile, CI"
```

---

### Task 20: Chạy thật và bàn giao giai đoạn 1

**Files:**
- Create: `docs/runbook-phase1.md`

- [x] **Step 1: Viết `docs/runbook-phase1.md`**

```markdown
# Runbook giai đoạn 1

## Khởi động
1. `cp .env.example .env`, điền `PROXY_URL_TEMPLATE` (residential, sticky session theo `{session}`, chọn nước theo `{country}`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
2. `docker compose -f infra/docker-compose.yml up -d --build`
3. Monitoring: `docker compose -f infra/docker-compose.monitoring.yml up -d`, Grafana tại http://localhost:3001 (admin/admin).

## Thêm tenant và khách sạn
    cd backend
    uv run sb add-tenant "Tên khách hàng" --timezone Asia/Ho_Chi_Minh --horizon 30
    uv run sb add-hotel <tenant_id> https://www.booking.com/hotel/vn/<slug>.html --role self --label "Của tôi"
    uv run sb add-hotel <tenant_id> https://www.booking.com/hotel/vn/<slug-doi-thu>.html --role competitor

## Quét thủ công và theo dõi
    uv run sb scan-now
    uv run sb run-status
    docker compose -f infra/docker-compose.yml logs -f worker

## Tăng công suất
    docker compose -f infra/docker-compose.yml up -d --scale worker=4
Trên máy khác: `docker compose -f infra/docker-compose.collector.yml up -d --scale worker=4` với `.env` trỏ về máy trung tâm.

## Khi Booking đổi giao diện
1. `uv run python scripts/capture_fixture.py <url> <checkin> 1 new_layout`
2. `uv run python scripts/explore_fixture.py tests/fixtures/html/new_layout.html`, sửa `selectors.py`.
3. Tăng `PARSER_VERSION`, chạy `uv run pytest tests/unit/test_parser.py`, emit lại golden.
4. `uv run sb reparse --since-days 30`

## Khi block rate tăng
- Xem Grafana: `sb_probes_total{status="blocked"}` theo thời gian, `sb_sessions_retired_total{reason="blocked"}`.
- Giảm tải: tăng `REQUEST_MIN_INTERVAL_SECONDS`, giảm `SESSION_MAX_REQUESTS`.
- Đổi pool proxy hoặc nhà cung cấp qua `PROXY_URL_TEMPLATE`.
- Kiểm tra tay: `uv run pytest tests/live/test_bootstrap_live.py -m live -s` với `PLAYWRIGHT_HEADLESS=false`.

## Truy vấn kiểm tra dữ liệu
    select h.booking_slug, rs.stay_date, rt.name, rs.rooms_left, rs.stock_confidence, rs.min_price, rs.scanned_at
    from room_snapshots rs join room_types rt on rt.id = rs.room_type_id join hotels h on h.id = rs.hotel_id
    order by rs.scanned_at desc limit 50;
```

- [ ] **Step 2: Chạy thật với 3 khách sạn trong 3 ngày liên tục**

1. Thêm 1 tenant, 1 khách sạn `self`, 2 khách sạn `competitor` thật.
2. `uv run sb scan-now`, chờ xong, `uv run sb run-status` phải cho `completed` với `ok + sold_out >= 90%` tổng probe.
3. Để scheduler tự chạy 3 lần mỗi ngày trong 3 ngày. Mỗi sáng kiểm tra `run-status` và Grafana.
4. Chạy truy vấn trong runbook, xác nhận có đủ 3 snapshot mỗi ngày cho mỗi khách sạn × ngày lưu trú, và `stock_confidence` có cả `exact` lẫn `capped`.

Tiêu chí bàn giao giai đoạn 1: 9 đợt quét liên tiếp đều `completed`, không có đợt nào `partial`, không có cảnh báo block rate, HTML thô tra được trong MinIO cho một probe bất kỳ.

- [x] **Step 3: Commit**

```bash
git add docs/runbook-phase1.md
git commit -m "docs: phase 1 runbook and acceptance checklist"
```
