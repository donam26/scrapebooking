"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Suspense } from "react";
import { api, type CalibrationOut, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateRange, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { DEMAND_COLOR, MIN_SAMPLE, demandLevel, fillIndicator, fillReading, marketSnapshot, medianCompRate, useMarketMetrics } from "@/lib/market-metrics";
import { Card, EmptyState, ErrorBox, SkeletonBlock, cx } from "@/components/ui";
import { KpiCard, SnapshotRow } from "@/components/kpi";
import { ArcGauge } from "@/components/gauge";
import { TrendChart, type TrendRow } from "@/components/trend-chart";
import { PageStrip } from "@/components/page-strip";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { DataUpdated, StaleBanner } from "@/components/freshness";
import { CalibrationNote, FillValue, useFillText } from "@/components/fill";
import { SampleTag, sampleFade, useSampleText } from "@/components/compset-sample";
import { OwnHotelSwitcher, useOwnHotelParam, useOwnHotels } from "@/components/own-hotel";
import { HolidayChips } from "@/components/holiday-mark";
import { ACTION_NIGHTS, TodayActions } from "@/components/today-actions";
import { IconBuilding, IconChevronRight } from "@/components/icons";
import { MarketTightness } from "./market-tightness";
import { DataStatus, SmartAlerts, YourHotel } from "./side-cards";

/**
 * Bảng điều khiển: việc cần làm hôm nay, toàn cảnh compset đêm đầu kỳ, mức căng hiện tại theo đêm,
 * xu hướng, cảnh báo, khách sạn của bạn. Kỳ xem chọn được (mặc định 14 đêm từ hôm nay).
 */

const DEFAULT_DAYS = 14;

function DashboardSkeleton() {
  const tc = useTranslations("common.status");
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]" aria-busy aria-label={tc("loading")}>
      <div className="space-y-4">
        <SkeletonBlock className="h-36 rounded-[10px]" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <SkeletonBlock key={i} className="h-32 rounded-[10px]" />
          ))}
        </div>
        <SkeletonBlock className="h-48 rounded-[10px]" />
        <SkeletonBlock className="h-80 rounded-[10px]" />
      </div>
      <div className="space-y-4">
        <SkeletonBlock className="h-32 rounded-[10px]" />
        <SkeletonBlock className="h-72 rounded-[10px]" />
      </div>
    </div>
  );
}

function DashboardView() {
  const t = useTranslations("dashboard");
  const { fmtNight } = useFmt();
  const { start, end, days, today, ready } = useDateRange(DEFAULT_DAYS);
  const [hotelParam, setHotel] = useOwnHotelParam();
  const ownHotels = useOwnHotels();
  // Mọi ô trên màn cùng một khách sạn của bạn (roadmap 5.5).
  const overview = useApi(ready ? `dash:ov:${start}:${end}:${hotelParam ?? ""}` : null, () => api.overview({ start, end, own_hotel_id: hotelParam }));
  const pace = useApi(ready ? `dash:pace:${start}:${end}:${hotelParam ?? ""}` : null, () => api.market.pace({ start, end, own_hotel_id: hotelParam }));
  const settings = useApi("settings", () => api.settings.get());
  const o = overview.data;
  const fresh = useDataFreshness(settings.data?.scan_times);

  const nights = pace.data?.nights ?? [];
  const byNight = new Map(nights.map((n) => [n.stay_date, n]));
  const isToday = o?.start === today;
  const calibration = pace.data?.calibration;

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={
          o && (
            <>
              <span>{t("strip.range", { count: days, start: fmtNight(o.start) })}</span>
              <HolidayChips holidays={o.holidays} start={o.start} end={o.end} />
            </>
          )
        }
        aside={fresh.loaded && <DataUpdated f={fresh} />}
        actions={
          <>
            <OwnHotelSwitcher hotels={ownHotels} value={hotelParam ?? pace.data?.own_hotel_id ?? null} onChange={setHotel} />
            <DateRangePicker defaultDays={DEFAULT_DAYS} />
          </>
        }
      />
      <ErrorBox error={overview.error} className="mb-4" />
      {fresh.loaded && <StaleBanner f={fresh} className="mb-4" />}
      {!o && !overview.error && <DashboardSkeleton />}
      {o && o.hotels.length === 0 && (
        <EmptyState icon={<IconBuilding />} title={t("empty.title")} className="border border-line bg-surface">
          {t.rich("empty.body", {
            link: (c) => (
              <Link href="/settings?tab=watchlist" className="font-semibold text-brand hover:underline">
                {c}
              </Link>
            ),
          })}
        </EmptyState>
      )}
      {o && o.hotels.length > 0 && (
        <div className={cx("grid gap-4 transition-opacity xl:grid-cols-[minmax(0,1fr)_340px]", overview.loading && "opacity-60")}>
          <div className="min-w-0 space-y-4">
            {ready && (
              <TodayActions
                today={today}
                ownHotelId={hotelParam}
                fromParent={start === today && days >= ACTION_NIGHTS}
                overview={o}
                pace={pace.data}
                error={pace.error}
              />
            )}
            <MarketSnapshotCard o={o} isToday={isToday} />
            <CompsetKpis o={o} night={byNight.get(o.start)} calibration={calibration} />
            <MarketTightness o={o} nights={nights} calibration={calibration} today={today} />
            <MarketTrends o={o} byNight={byNight} calibration={calibration} />
          </div>
          <div className="min-w-0 space-y-4">
            <SmartAlerts overview={o} fresh={fresh} today={today} />
            <YourHotel overview={o} night={byNight.get(o.start)} calibration={calibration} isToday={isToday} />
            <DataStatus overview={o} fresh={fresh} settings={settings.data} />
          </div>
        </div>
      )}
    </>
  );
}

function MarketSnapshotCard({ o, isToday }: { o: OverviewOut; isToday: boolean }) {
  const t = useTranslations("dashboard.snapshot");
  const sample = useSampleText();
  const { fmtInt, fmtMoney, fmtNight, fmtPriceShort } = useFmt();
  const s = marketSnapshot(o);
  const c = s.compset;
  const qs = isToday ? "" : new URLSearchParams({ start: o.start }).toString();
  const median = {
    value:
      s.medianRate === null ? (
        "—"
      ) : (
        <span className={sampleFade(c)}>{fmtPriceShort(s.medianRate, s.currency)}</span>
      ),
    label: (
      <>
        {t("medianRate")}
        {c && (
          <span className="block">
            <SampleTag c={c} short />
          </span>
        )}
      </>
    ),
    title: s.medianRate === null ? (c ? sample.title(c) : undefined) : t("medianRateTitle", { price: fmtMoney(Math.round(s.medianRate), s.currency), count: s.priced }),
  };
  return (
    <Card
      title={isToday ? t("title") : t("titleNight", { night: fmtNight(o.start) })}
      info={t("info")}
      actions={
        <Link href={`/availability${qs ? `?${qs}` : ""}`} className="inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline">
          {t("viewAvailability")} <IconChevronRight size={15} />
        </Link>
      }
    >
      <div className="border-t border-line pt-4">
        <SnapshotRow
          items={[
            { value: s.competitors, label: t("competitors") },
            { value: s.soldOut, label: t("soldOut"), tone: s.soldOut ? "bad" : "default" },
            { value: s.low, label: t("low"), tone: s.low ? "hot" : "default" },
            ...(s.restricted ? [{ value: s.restricted, label: t("restricted"), tone: "default" as const, title: t("restrictedTitle") }] : []),
            { value: s.roomsKnown ? fmtInt(s.roomsLeft) : "—", label: t("roomsLeft"), title: t("roomsLeftTitle", { known: s.roomsKnown, observed: s.observed }) },
            median,
          ]}
        />
      </div>
    </Card>
  );
}

/** Ô "Giá niêm yết TB đối thủ" (trung vị, kèm n/N và cờ cỡ mẫu). */
function AdvertisedKpi({ o, className }: { o: OverviewOut; className?: string }) {
  const t = useTranslations("dashboard.kpi");
  const { fmtMoney } = useFmt();
  const s = marketSnapshot(o);
  const c = s.compset;
  return (
    <KpiCard
      className={className}
      title={t("advertised.title")}
      info={t("advertised.info")}
      value={s.medianRate === null ? "—" : <span className={sampleFade(c)}>{fmtMoney(Math.round(s.medianRate), s.currency)}</span>}
      sub={
        c ? (
          <span className="flex flex-col items-center gap-0.5">
            {s.medianRate !== null && <span>{t("advertised.sub", { count: c.competitors_priced })}</span>}
            <SampleTag c={c} />
          </span>
        ) : s.medianRate === null ? (
          t("advertised.none")
        ) : (
          t("advertised.sub", { count: s.priced })
        )
      }
      tone={c?.sample === "insufficient" ? "muted" : "default"}
    />
  );
}

function CompsetKpis({ o, night, calibration }: { o: OverviewOut; night: PaceNightOut | undefined; calibration: CalibrationOut | undefined }) {
  const t = useTranslations("dashboard.kpi");
  const tm = useTranslations("helpers.marketMetrics");
  const { demandLabel } = useMarketMetrics();
  const { hiddenText } = useFillText();
  const s = marketSnapshot(o);
  const tn = s.tightness;
  const level = tn.share === null ? null : demandLevel(tn.share);
  const fill = fillReading(night, calibration);
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <KpiCard title={t("tight.title")} info={t("tight.info", { min: MIN_SAMPLE })}>
        {level !== null && tn.share !== null ? (
          <div className="mt-2">
            <ArcGauge value={tn.share} color={DEMAND_COLOR[level]} caption={t("tight.caption", { tight: tn.tight, observed: tn.observed, level: demandLabel(level) })} size={116} />
            {tn.restricted > 0 && <div className="mt-1 text-xs text-muted">{t("tight.restricted", { count: tn.restricted })}</div>}
          </div>
        ) : (
          <>
            <div className={cx("mt-2 text-[28px] font-bold leading-tight tabular", tn.observed ? "text-ink" : "text-faint")}>{tn.observed ? `${tn.tight}/${tn.observed}` : "—"}</div>
            <div className="mt-0.5 text-sm text-muted" title={tn.smallSample ? tm("smallSampleTitle", { min: MIN_SAMPLE }) : undefined}>
              {tn.observed ? tm("smallSample") : t("tight.noData")}
            </div>
            {tn.restricted > 0 && <div className="text-xs text-muted">{t("tight.restricted", { count: tn.restricted })}</div>}
          </>
        )}
      </KpiCard>
      <AdvertisedKpi o={o} />
      <KpiCard
        title={t("fill.title")}
        info={t("fill.info", { count: fill.hotels })}
        value={<FillValue reading={fill} />}
        sub={
          <span className="flex flex-col">
            <CalibrationNote calibration={calibration} />
            {fill.hidden ? <span>{hiddenText(fill)}</span> : fill.value === null && <span>{t("fill.notEnough")}</span>}
          </span>
        }
        tone="hot"
      />
    </div>
  );
}

function MarketTrends({ o, byNight, calibration }: { o: OverviewOut; byNight: Map<string, PaceNightOut>; calibration: CalibrationOut | undefined }) {
  const t = useTranslations("dashboard.trends");
  const { fmtMoney, fmtNight, fmtPriceShort } = useFmt();
  const currency = o.compset.find((c) => c.currency)?.currency ?? "VND";
  const rows: TrendRow[] = dateRange(o.start, o.end).map((d) => {
    const rate = medianCompRate(o, d);
    const fill = fillIndicator(byNight.get(d), calibration);
    return { x: d, rate: rate === null ? null : Math.round(rate), fill: fill === null ? null : Math.round(fill * 100) };
  });
  return (
    <Card title={t("title")} info={t("info")}>
      <TrendChart
        data={rows}
        height={280}
        formatX={(x) => fmtNight(x)}
        formatLeft={(v) => fmtPriceShort(v, currency)}
        formatRight={(v) => `${v}%`}
        formatValue={(v, s) => (s.right ? `≈${v}%` : fmtMoney(v, currency))}
        series={[
          { key: "rate", name: t("rateSeries"), color: "#0062ff" },
          { key: "fill", name: t("fillSeries"), color: "#16a34a", right: true, dashed: true },
        ]}
      />
    </Card>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardView />
    </Suspense>
  );
}
