# Brief cho agent chuyển trang (đợt 2)

You are converting part of a Next.js 16 dashboard to bilingual Vietnamese/English with next-intl v4 (cookie-based locale, no URL prefix). Repo: /Users/hnam/code/scrapebooking, dashboard in dashboard/. Environment: macOS (zsh, BSD sed — prefer Python or the Edit tool for edits), Node 22, date 2026-10-02. Four other page agents convert OTHER route folders concurrently.

Foundation + shared components/helpers are DONE. READ FIRST:
- docs/i18n.md — the standard (key naming, ICU, plurals, helpers outside React, i18n-ignore, English style: concise, sentence case, British spelling, hotel revenue-management terms: occupancy, ADR, rooms left, sold out, pickup, pace, comp set, rate parity, stay date, lead time).
- plans/261002-1908-bilingual-i18n/reports/fe-shared-api-changes.md — new signatures of shared helpers/components (useNightReason, useMarketMetrics, useMarketText, useMarks, useLocalEventLabel, SubTabs items…).
- Reference conversion: dashboard/src/components/app-shell.tsx + src/messages/{vi,en}/shell.json.
- Core APIs: src/lib/format.ts (`useFmt()`; locale-dependent fmt* are no longer top-level exports; pure helpers like num/parseDate/addDays/dateRange/isWeekend/todayIn/scanOverdue/scanCollectedNothing/prettySlug still are), src/i18n/server.ts (`getFmt()`), src/lib/labels.ts (`useLabel()`: `label("eventType", code)`; text maps and `label()` removed; groups = keys of src/messages/vi/labels.json; CHANNEL_LABEL and *_TONE unchanged; HEAT_LEVELS is `{cls,key}` → `label("heatLevel", h.key)`), src/lib/errors.ts (`useErrorMessage()`; `errorMessage` and one-arg `translateError` removed; `useMutation().error` is already translated; `<ErrorBox error>` takes anything).

Task: convert ALL user-visible Vietnamese text in YOUR files to translations and fix every tsc error in your files caused by the API changes. JSX text, attributes (aria-label, title, placeholder, alt), constants/config arrays (tabs, columns, options → keep a `key`, translate at render), template literals, confirm/toast text, `metadata` (→ `generateMetadata` with getTranslations). Write BOTH src/messages/vi/<ns>.json (exact original Vietnamese wording) and src/messages/en/<ns>.json (natural professional English for hotel revenue managers). Nest keys by component/section.

Rules:
- Only edit your files and your namespace JSON files (they exist as `{}`). Never touch common/format/labels/errors/shell/components/helpers JSON, src/components/**, src/lib/**, or other route folders. You MAY read shared keys (e.g. common.actions.save) via useTranslations("common…"). If you need a shared change, finish your work and report it.
- Comments stay as they are. No refactors/restyling beyond i18n; vi output identical to before (except unavoidable formatter changes from the shared layer).
- Full sentences with params, ICU plurals in en (`{count, plural, one {# room} other {# rooms}}`, vi just `{count} phòng`), never concatenate translated fragments.
- Dev-only thrown errors → plain English, untranslated. Intentionally Vietnamese proper nouns → `// i18n-ignore`.
- next-intl parses `<tag>` in messages (use t.rich for markup); `'` next to `{` must be doubled.
- Typed keys: dynamic keys need a typed union or `t.has()`.
- Text coming from the backend API (hotel names, AI brief content, price-suggestion reasons, holiday names) is data — don't translate it client-side; the backend localizes it by Accept-Language.

Verify before reporting (must pass for your files):
- `cd /Users/hnam/code/scrapebooking/dashboard && npm run i18n:check -- --files <your files...>` → 0 hardcoded in your files; 0 parity/ICU errors in your namespaces.
- `npx tsc --noEmit 2>&1 | grep -F "src/app/(app)/<your folder>"` (repeat per folder) → no errors.
- `npx eslint <your files>` clean.
Do NOT run `next build`, `next dev`, or any git command. Don't create markdown files.

Final report (concise): files changed, key counts per namespace, shared changes you need, translations you were unsure about.
