# FE shared components/helpers — API changes (stage 1)

Pattern: text-producing helpers mirror `createFmt`/`useFmt`. In components (client or non-async server) call the `useX()` hook; in async server code / outside React use `createX(await getTranslations("<ns>"), await getFmt())`.

## `@/lib/night-reason`
- REMOVED top-level: `fmtRank`, `fmtVsMedian`, `nightReason` (they also used old top-level `fmtNum`).
- NEW: `useNightReason(): { fmtRank, fmtVsMedian, nightReason }` — same args/returns as before.
  ```ts
  const { nightReason, fmtRank, fmtVsMedian } = useNightReason();
  const reason = nightReason(c0, holidays.get(today));
  const rank = fmtRank(c.own_rank, c.priced_hotels);
  ```
- NEW: `createNightReason(t /* "helpers.nightReason" */, fmt)`; types `NightReasonTranslator`, `NightReasonText`.
- UNCHANGED: `deltaVsMedian(priceIndex)`.
- Note for board.tsx: the aria text `giá bạn ${fmtVsMedian(v + 100)}` needs its own page key (helpers has `yourPrice: "giá bạn {vs}"` but it lives in `helpers.nightReason`; prefer a page key).

## `@/lib/market-metrics`
- REMOVED: `DEMAND_LABEL`, top-level `ratePosition`, top-level `dayHead`.
- NEW: `useMarketMetrics(): { demandLabel(level), ratePosition(own, market), dayHead(iso, today?) }` — `ratePosition` returns `{ text, tone } | null`, `dayHead` returns `{ wd, date, weekend, isToday }` as before.
  ```ts
  const { demandLabel, ratePosition, dayHead } = useMarketMetrics();
  caption={level ? demandLabel(level) : ...}
  const heads = dates.map((d) => dayHead(d, today));
  ```
- NEW: `createMarketMetrics(t /* "helpers.marketMetrics" */, fmt)`; types `MarketMetricsTranslator`, `MarketMetricsText`.
- UNCHANGED: `DemandLevel`, `demandLevel`, `DEMAND_COLOR`, `DEMAND_TEXT`, `demandScore`, `bookablePrice`, `selfRow`, `competitorRows`, `cellOn`, `rowName`, `isTight`, `MarketSnapshot`, `marketSnapshot`, `avgCompRate`, `HOTEL_LINE_COLORS`, `OWN_LINE_COLOR`, `hotelColors`, `MARKET_LINE_COLOR`, `distanceKm`.

## `@/lib/market`
- REMOVED: `SUGGESTION_LABEL`, top-level `fmtPace`, `fmtChange`, `ownOccText`.
- NEW: `useMarketText(): { fmtPace(delta), suggestionLabel(kind), fmtChange(pct), ownOccText(night) }` — same returns as before (`ownOccText` → `{ text, source }`).
  ```ts
  const { suggestionLabel, fmtPace, ownOccText } = useMarketText();
  <Badge tone={SUGGESTION_TONE[sug.kind]}>{suggestionLabel(sug.kind)}</Badge>
  suggestionLabel(first.suggestion!.kind).toLowerCase()
  ```
- NEW: `createMarketText(t /* "helpers.market" */)`; types `MarketTextTranslator`, `MarketText`.
- UNCHANGED: `fmtOcc`, `SUGGESTION_TONE`, `pendingSuggestions`.

## `@/lib/channels`
- REMOVED top-level: `demandText(s)`.
- NEW: `useDemandText(): (s: DemandSignalOut) => string`; `createDemandText(t /* "helpers.channels" */, fmt)`; type `ChannelsTranslator`.
  ```ts
  const demandText = useDemandText();
  demandText(signal);
  ```
  (Only caller was `components/channels.tsx`, already converted.)
- `hotelTitle(hotel, label?)`: signature unchanged; last-resort fallback (hotel with no listings) changed from `Khách sạn #id` to `#id` (only vi behaviour change).
- UNCHANGED: `channelName`, `sortChannels`, `detectChannel`, `listingKeyName`, `activeChannels`, `withChannel`, `shownDemandSignals`.

## `@/lib/local-events`
- CHANGED: `LOCAL_EVENT_CATEGORIES` items no longer have `label` → `{ value, bg, chip }`. `localEventCategory(value)` returns the same (label-less) item.
- NEW: `useLocalEventLabel(): (category: string) => string` (unknown codes → "Khác"/"Other", same fallback as `localEventCategory`).
  ```ts
  const catLabel = useLocalEventLabel();
  {LOCAL_EVENT_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{catLabel(c.value)}</option>)}
  ```
- UNCHANGED: `LocalEventCategory`, `fmtUplift`.

## `@/lib/session`
- No API change (dev-only error message now English).

## `@/components/marks`
- REMOVED: `cellMark`, `roomMark`, `BEYOND_MARK`.
- NEW: `useMarks(): { cellMark(cell, beyond?), roomMark(snapshot), beyondMark }` — same args, same `Mark` shape; `mark.label` / `mark.text` translated.
  ```ts
  const { cellMark, roomMark, beyondMark } = useMarks();
  <MarkSwatch mark={cellMark(tonight)} size={32} />
  <MarkSwatch mark={beyondMark} size={18} />
  ```
- NEW: `createMarks(t /* "components.marks" */)`; types `MarksTranslator`, `Marks`.
- UNCHANGED: `MarkKind`, `Mark`, `exactShade`, `HEAT_LEVELS` (`{ cls, key }`), `MarkSwatch`, `MarkChip`, `MarksLegend` (props unchanged, translate internally).
- Note: pages building their own marks (`heatmap-table.tsx` `Còn ${n} phòng`, `hotels/[id]/dates/[date]/page.tsx` `statusMark`) need their own page keys or can use `useMarks().cellMark(...)`.

## `@/components/price-basis`
- REMOVED: `priceNoun(basis)`.
- NEW: `usePriceNoun(): (basis: PriceBasis) => string` (no current callers).
  ```ts
  const priceNoun = usePriceNoun();
  priceNoun(basis);
  ```
- UNCHANGED: `PriceBasis`, `usePriceBasis`, `PriceBasisPicker`.

## `@/components/channels`
- CHANGED: `listingStatusText(l)` → `listingStatusText(l, t, label)` where `t = useTranslations("components.channels")`, `label = useLabel()` (only used inside `channels.tsx`).
- UNCHANGED props: `useChannelParam`, `ChannelSwitcher`, `ListingChip`, `ChipAction`, `ListingChips`, `DemandSignals` (`title` still optional; default now translated).

## `@/components/sub-tabs`
- CHANGED type: items are `SubTabItem = { href: string; exact?: boolean } & ({ label: string } | { key: "aiBriefs" | "events" | "compset" | "market" })`. Exported `SubTabItem`.
- `BRIEF_TABS`, `COMPETITOR_TABS` now use `key`; call sites `<SubTabs items={BRIEF_TABS} />` need no change. Custom items can still pass an already-translated `label`.

## `@/components/event-table`
- No signature change. `EventTable` `emptyText` still optional (default translated); `EventTypeBadge` unchanged.

## `@/components/line-chart`, `@/components/trend-chart`
- No signature change. `emptyText` still optional (default → `common.status.noData`).

## `@/components/gauge`
- No signature change (`ArcGauge`, `RingGauge`). Now calls `useTranslations` → must be rendered in a component context (client or non-async server), as before for hooks generally.

## `@/components/market-suggestion`
- No signature change (`SuggestionCard`).

## `@/components/run-summary`, `@/components/scan-hotel-button`, `@/components/date-range`
- No signature change (`RunSummary`, `ScanHotelButton`, `DateRangePicker`, `useDateRange`, `DAY_OPTIONS`).

## `@/components/ui`
- No signature change. `InfoTip`, `Breadcrumbs`, `Skeleton` translate their aria labels internally; `ErrorBox` as before.

## Unchanged, no text: `icons.tsx`, `kpi.tsx`, `page-strip.tsx`, `popover-menu.tsx`, `lib/api.ts`.
