# Orchestration Protocol

## Task Approach
- Simple bug/change: fix directly, run lint + the affected tests.
- Medium feature: outline steps, implement sequentially, verify each step with tests.
- Large feature: break into phases under `plans/<date>-<slug>/`, implement one phase at a time.

## File Organization
- Plans and implementation reports go in `./plans/`.
- Project documentation goes in `./docs/`.
- Do NOT create markdown files outside these directories unless requested.

## Quality Checks
After any code change, always:
1. Backend: `uv run ruff check . && uv run ruff format . && uv run mypy app` (inside `backend/`).
2. Dashboard: `npm run lint && npm run typecheck` (inside `dashboard/`).
3. Run the tests covering the change; add tests for new behaviour.
4. Verify the change works with existing code (no broken imports, migrations apply, OpenAPI snapshot current).
