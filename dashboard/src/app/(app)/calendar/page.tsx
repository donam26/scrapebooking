"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { api, apiUrl, type OverviewOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { isoDate, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { hotelColors, selfRow } from "@/lib/market-metrics";
import { EmptyState, ErrorBox, Note, Segmented, SkeletonBlock, cx } from "@/components/ui";
import { PageStrip } from "@/components/page-strip";
import { DataUpdated } from "@/components/freshness";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { PriceBasisPicker, usePriceBasis } from "@/components/price-basis";
import { HolidayChips } from "@/components/holiday-mark";
import { ExportMenu } from "@/components/export-menu";
import { IconBuilding } from "@/components/icons";
import { Collapsible, useNightCols } from "./grid-parts";
import { HeatLegend, RoomsGrid } from "./rooms-grid";
import { RateGrid, RateTrends } from "./rate-grid";
import { OccupancyAnalysis } from "./occupancy-analysis";

/**
 * Lịch giá & phòng: một lưới khách sạn × đêm với ba cách xem (Phòng còn, Giá, Chênh với bạn), chọn
 * ngày + 14/30/60 đêm (mặc định 14), cơ sở giá cho hai cách xem giá. Đầu cột có chấm tím khi đêm có
 * gợi ý giá chưa xử lý; bấm ô mở chi tiết đêm. Dưới lưới (thu gọn): xu hướng giá, chỉ báo lấp đầy ≈.
 * URL: `/calendar?view=rooms|rates|gap&start=&days=&basis=` (gộp /availability, /rates, /overview).
 */

const DEFAULT_DAYS = 14;
const VIEWS = ["rooms", "rates", "gap"] as const;
type View = (typeof VIEWS)[number];

function useView(): [View, (v: View) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("view");
  const view = VIEWS.find((v) => v === raw) ?? "rooms";
  function set(next: View) {
    const q = new URLSearchParams(params.toString());
    if (next === "rooms") q.delete("view");
    else q.set("view", next);
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }
  return [view, set];
}

/** Ô cũ hơn 48 giờ trong kỳ đang xem: tất cả (chip "Số từ 16/10") hay một phần. */
function staleCells(o: OverviewOut): { stale: number; observed: number; oldest: string | null; newest: string | null } {
  let stale = 0;
  let observed = 0;
  let oldest: string | null = null;
  let newest: string | null = null;
  for (const h of o.hotels) {
    for (const c of h.cells) {
      if (!c.last_observed_at) continue;
      observed += 1;
      if (newest === null || c.last_observed_at > newest) newest = c.last_observed_at;
      if (!c.stale) continue;
      stale += 1;
      if (oldest === null || c.last_observed_at < oldest) oldest = c.last_observed_at;
    }
  }
  return { stale, observed, oldest, newest };
}

function StaleChip({ o }: { o: OverviewOut }) {
  const t = useTranslations("calendar.page");
  const { fmtDateShort, fmtWhen } = useFmt();
  const s = staleCells(o);
  if (s.stale === 0) return null;
  const day = (iso: string) => fmtDateShort(isoDate(new Date(iso)));
  const all = s.stale === s.observed;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-warning-soft px-2.5 py-0.5 text-xs font-semibold text-warning-deep"
      title={all ? t("staleAllTitle", { when: fmtWhen(s.newest) }) : t("stalePartTitle", { when: fmtWhen(s.oldest) })}
    >
      <span aria-hidden className="sb-heat-4 sb-stale relative inline-block h-2.5 w-2.5 rounded-[2px]" />
      {all ? t("staleAll", { date: day(s.newest!) }) : t("stalePart", { count: s.stale, date: day(s.oldest!) })}
    </span>
  );
}

/** Chỉ báo lấp đầy ≈: dữ liệu theo khách sạn chỉ tải khi mở khối. */
function FillSection({ o, start, end, pace }: { o: OverviewOut; start: string; end: string; pace: ReturnType<typeof usePace> }) {
  const occupancy = useApi(`cal:occ:${start}:${end}`, () => api.market.occupancy({ start, end }));
  const p = pace.data;
  if (occupancy.error || pace.error) return <ErrorBox error={occupancy.error ?? pace.error} />;
  if (!occupancy.data || !p) return <SkeletonBlock className="h-24 w-full" />;
  return <OccupancyAnalysis nights={p.nights} calibration={p.calibration} perHotel={occupancy.data} colors={hotelColors(o)} />;
}

function usePace(ready: boolean, start: string, end: string) {
  return useApi(ready ? `cal:pace:${start}:${end}` : null, () => api.market.pace({ start, end }));
}

function CalendarView() {
  const t = useTranslations("calendar.page");
  const { fmtNight } = useFmt();
  const { start, end, days, today, ready } = useDateRange(DEFAULT_DAYS);
  const basis = usePriceBasis();
  const [view, setView] = useView();
  const overview = useApi(ready ? `cal:ov:${start}:${end}:${basis}` : null, () => api.overview({ start, end, price_basis: basis }));
  const pace = usePace(ready, start, end);
  const fresh = useDataFreshness();
  const o = overview.data;
  const nights = pace.data?.nights ?? [];
  // Đêm có gợi ý giá chưa xử lý (không tính "giữ giá"); dữ liệu cũ thì không nhắc việc (như Hôm nay).
  const pending = new Set(fresh.stale ? [] : nights.filter((n) => n.suggestion && n.suggestion.kind !== "hold" && !n.suggestion.decision).map((n) => n.stay_date));
  const priceView = view !== "rooms";

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={
          o && (
            <>
              <span>{t("nights", { count: days, start: fmtNight(o.start) })}</span>
              <HolidayChips holidays={o.holidays} start={o.start} end={o.end} />
            </>
          )
        }
        aside={fresh.loaded && <DataUpdated f={fresh} />}
        actions={
          <>
            <DateRangePicker defaultDays={DEFAULT_DAYS} />
            <ExportMenu csvHref={apiUrl("/export/overview.csv", { start, end })} start={start} end={end} priceBasis={priceView ? basis : undefined} month={today.slice(0, 7)} />
          </>
        }
      />
      <ErrorBox error={overview.error} className="mb-4" />
      {!o && !overview.error && <SkeletonBlock className="h-[460px] w-full rounded-[10px]" />}
      {o && o.hotels.length === 0 && (
        <EmptyState icon={<IconBuilding />} title={t("emptyTitle")} className="border border-line bg-surface">
          {t.rich("emptyBody", {
            link: (c) => (
              <Link href="/settings?tab=watchlist" className="font-semibold text-brand hover:underline">
                {c}
              </Link>
            ),
          })}
        </EmptyState>
      )}
      {o && o.hotels.length > 0 && (
        <CalendarBody o={o} view={view} setView={setView} pending={pending} today={today} loading={overview.loading} pace={pace} start={start} end={end} />
      )}
    </>
  );
}

function CalendarBody({
  o,
  view,
  setView,
  pending,
  today,
  loading,
  pace,
  start,
  end,
}: {
  o: OverviewOut;
  view: View;
  setView: (v: View) => void;
  pending: Set<string>;
  today: string;
  loading: boolean;
  pace: ReturnType<typeof usePace>;
  start: string;
  end: string;
}) {
  const t = useTranslations("calendar.page");
  const tg = useTranslations("calendar.gap");
  const tr = useTranslations("calendar.rates");
  const cols = useNightCols(o, today, pending);
  const noOwn = view === "gap" && !selfRow(o);
  return (
    <div className="space-y-4">
      <section className={cx("min-w-0 overflow-hidden rounded-[10px] border border-line bg-surface shadow-card transition-opacity", loading && "opacity-60")}>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-5 py-3 max-sm:px-3">
          <Segmented
            label={t("view")}
            value={view}
            onChange={setView}
            items={[
              { value: "rooms", label: t("views.rooms") },
              { value: "rates", label: t("views.rates") },
              { value: "gap", label: t("views.gap") },
            ]}
          />
          {view !== "rooms" && <PriceBasisPicker />}
          <StaleChip o={o} />
          <span className="ml-auto text-xs text-muted max-sm:hidden">{t("clickHint")}</span>
        </div>
        {noOwn ? (
          <div className="p-5">
            <Note tone="info">
              {tg.rich("noOwn", {
                link: (c) => (
                  <Link href="/settings?tab=watchlist" className="font-semibold text-brand hover:underline">
                    {c}
                  </Link>
                ),
              })}
            </Note>
          </div>
        ) : view === "rooms" ? (
          <RoomsGrid data={o} cols={cols} nights={pace.data?.nights ?? []} calibration={pace.data?.calibration} pmsHotelId={pace.data?.own_hotel_id ?? null} />
        ) : (
          <RateGrid o={o} cols={cols} mode={view} />
        )}
        <div className="border-t border-line px-5 py-3 max-sm:px-3">
          {view === "rooms" ? <HeatLegend /> : <p className="text-xs text-muted">{view === "gap" ? tg("note") : tr("note")}</p>}
        </div>
      </section>
      <Collapsible title={t("trendsTitle")}>{() => <RateTrends o={o} />}</Collapsible>
      <Collapsible title={t("fillTitle")}>{() => <FillSection o={o} start={start} end={end} pace={pace} />}</Collapsible>
    </div>
  );
}

export default function CalendarPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[460px] w-full rounded-[10px]" />}>
      <CalendarView />
    </Suspense>
  );
}
