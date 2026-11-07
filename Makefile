.PHONY: infra-up infra-down test test-int lint typecheck migrate api dashboard-dev demo-video-db

# Database riêng cho video demo (không đụng database dev). Đổi cổng/container qua biến nếu khác.
DEMO_PG_CONTAINER ?= scrapebooking-postgres-1
DEMO_DATABASE_URL ?= postgresql+asyncpg://app:app@localhost:55432/scrapebooking_demo

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

api:
	cd backend && uv run uvicorn app.api.asgi:app --reload --port 8000

dashboard-dev:
	cd dashboard && npm run dev

openapi:
	cd backend && uv run python scripts/export_openapi.py

demo-video-db:
	docker exec $(DEMO_PG_CONTAINER) dropdb -U app --if-exists --force scrapebooking_demo
	docker exec $(DEMO_PG_CONTAINER) createdb -U app scrapebooking_demo
	cd backend && DATABASE_URL=$(DEMO_DATABASE_URL) uv run alembic upgrade head
	cd backend && DATABASE_URL=$(DEMO_DATABASE_URL) REDIS_URL=redis://localhost:6380/3 uv run python scripts/seed_video_demo.py
