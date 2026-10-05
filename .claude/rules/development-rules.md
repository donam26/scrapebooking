# Development Rules

Follow YAGNI, KISS, DRY principles. Stack: **Python 3.12 (FastAPI, SQLAlchemy 2 async, arq, Alembic, uv)** in
`backend/`, **Next.js 16 + TypeScript + Tailwind + next-intl** in `dashboard/`, Docker Compose in `infra/`.
There is no PHP/Laravel code in this repo.

## Backend (backend/)
- Package `app/`, one subpackage per domain: `collector/<channel>/`, `scheduler/`, `worker/`, `analytics/`,
  `insight/`, `notify/`, `market/`, `marketscan/`, `pms/`, `api/routers/`, `repo/`, `db/`, `domain/`, `ops/`.
- Pure logic (rules, parsers, planning) lives in modules with no I/O and has unit tests; I/O lives in
  `repo/`, services and routers. Keep routers thin: validation in Pydantic schemas (`api/schemas.py`),
  business logic in services/repos.
- Models in `app/db/models.py` (and `app/market/models.py`, `app/marketscan/models.py`); every schema change
  needs an Alembic migration in `backend/alembic/versions/` with a working `downgrade`.
- Enums are `StrEnum` in `app/domain/models.py`; status columns use their string values.
- Use typed signatures everywhere (`mypy --strict` runs in CI). Settings come from `app/config.py`
  (pydantic-settings), never read `os.environ` directly.
- Wrap multi-write operations in one session transaction; commit explicitly. Keep jobs idempotent.
- Text shown to users goes through `app/i18n` (`t(locale, key)`), with keys in `app/i18n/locales/{vi,en}.json`.

## Dashboard (dashboard/)
- App Router under `src/app/`; shared UI in `src/components/`; helpers in `src/lib/`.
- API calls only through `src/lib/api.ts`; types come from `src/lib/api-types.ts` which is generated
  (`npm run gen:api` from `docs/api/openapi.json`). Never edit `api-types.ts` by hand.
- Every user-visible string goes through next-intl messages in `src/messages/{vi,en}/<namespace>.json`.
  `npm run i18n:check` must pass.
- No hard-coded hex colours in app pages: use the `--sb-*` tokens in `globals.css`.

## Code quality (run before every commit)
- Backend: `cd backend && uv run ruff check . && uv run ruff format . && uv run mypy app && uv run pytest -q`
  (integration tests need Postgres/Redis from `make infra-up`).
- Dashboard: `cd dashboard && npm run lint && npm run typecheck && npm run i18n:check && npm run build`.
- When the API changes: `make openapi` then `cd dashboard && npm run gen:api` and commit both files.
- Do NOT create new "enhanced"/"v2" versions of files; update existing files directly.

## Commits
- Conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`; scope optional
  (`feat(collector): ...`). Never commit placeholder messages such as `123` or `wip`.
- Do NOT commit `.env`, API keys, proxy credentials, or database dumps.
