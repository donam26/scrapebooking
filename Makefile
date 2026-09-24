.PHONY: infra-up infra-down test test-int lint typecheck migrate api dashboard-dev

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
	cd backend && uv run uvicorn app.api.main:app --reload --port 8000

dashboard-dev:
	cd dashboard && npm run dev
