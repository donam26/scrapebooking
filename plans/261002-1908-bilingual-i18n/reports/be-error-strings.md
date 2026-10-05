# Backend error strings with no rule in `dashboard/src/lib/errors.ts`

I collected these by walking the AST of `backend/app/api` and `backend/app/notify` (plus `app/pms` as a check), taking every string literal or f-string passed to `HTTPException(...)`, `ValueError(...)` or `InvalidParams(...)`. I filled each placeholder with a sample value and tested it against the current `RULES`. These are the ones nothing matched. Placeholders are shown as `{name}` with the value they currently take.

## HTTP `detail` (plain string)

| Status | Exact text | Source |
|---|---|---|
| 404 | `run not found` | `api/routers/data.py:642`, `:662` |
| 422 | `range must be 1–{max} nights` (max = 60) | `api/routers/market.py:269`, `:408` (`/market/pace`, `/market/occupancy`) |
| 422 | `range must be 1–{max} days` (max = 400) | `api/routers/market.py:351`, `:477` (`/market/holidays`, `/market/events`) |
| 409 | `no such suggestion for this night anymore` | `api/routers/market.py:293` |
| 404 | `event not found` | `api/routers/market.py:461` (local events) |
| 404 | `market area not found` | `api/routers/market_city.py:96` |
| 422 | `at most {max} recipients` (max = 20) | `api/routers/notifications.py:82` |
| 409 | `recipient already exists` | `api/routers/notifications.py:91` |
| 404 | `recipient not found` | `api/routers/notifications.py:107` |
| 429 | `test email sent less than a minute ago` | `api/routers/notifications.py:164` |
| 409 | `only broken listings can be retried` | `api/routers/watchlist.py:326` |
| 422 | `hotel has no active listing` | `api/scan_now.py:39` |

The range strings use an en dash (`1–60`), not a hyphen.

## HTTP `detail` from `str(exc)` (`PUT /notifications/rules/{kind}`, 422)

From `notify/kinds.py` (`InvalidParams`):

- `unknown params for {kind}: {keys}`, e.g. `unknown params for competitor_low_stock: min_pct` (keys comma-separated, sorted)
- `{key} must be an integer`, e.g. `min_pct must be an integer`
- `{key} must be between {lo} and {hi}`, e.g. `within_days must be between 1 and 90`. Possible keys and bounds: `within_days` 1–90, `min_sold_out` 1–50, `min_pct` 3–90.

## Pydantic validation `msg` (inside the `detail` array, `loc` = field name)

Pydantic adds `Value error, ` in front of these:

- `Value error, insight_language must be one of vi, en`. **New**, from `api/schemas.py` (TenantCreate/TenantUpdate), loc `["body", "insight_language"]`. The list is `LOCALES` joined with `, `.
- `Value error, end_date before start_date`, from `api/routers/market.py:169` (LocalEventIn)
- `Value error, event longer than {max} days` (max = 120), from `api/routers/market.py:171`

## Not in this list

- The watchlist URL error (422 from `_parse`) is already translated by the backend (`url.*` catalog).
- `app/pms` messages (`not a number '…'`, `duplicate date …`, `sold … > total …`, `out of range …`) already match existing rules.
