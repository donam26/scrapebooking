# Primary Workflow

## Before Coding
- Read the existing code in the area you are modifying to understand patterns.
- Check `PRODUCT.md`, `docs/operations.md`, `docs/user-flows.md` and the relevant `plans/` directory.
- For large features: write a plan in `plans/` before implementing.

## During Implementation
- Follow existing patterns (see `development-rules.md`).
- After editing Python: `cd backend && uv run ruff check <file> && uv run ruff format <file>`.
- After editing TypeScript: `cd dashboard && npm run lint && npm run typecheck`.
- Add or update tests next to the change: `backend/tests/unit` for pure logic, `backend/tests/integration`
  for DB/API flows, `dashboard/src/**/*.test.tsx` for UI.

## After Implementation
- Backend: `make lint typecheck test-int` (or `uv run pytest -q` inside `backend/`).
- Dashboard: `npm run lint && npm run typecheck && npm run i18n:check && npm run build`.
- API changed → `make openapi` + `npm run gen:api`.
- Review the diff for consistency with existing code before committing.

## Debugging
- Backend logs are JSON on stdout (`docker compose -f infra/docker-compose.yml logs -f <service>`).
- `uv run sb run-status`, `uv run sb analyze`, `uv run sb reparse` for pipeline checks (see `docs/operations.md`).
- API docs at `http://localhost:8000/docs` in dev; Grafana "Collector health" for scraper metrics.
