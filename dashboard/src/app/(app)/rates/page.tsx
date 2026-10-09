"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Suspense, useState } from "react";
import { api, type CalibrationOut, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { dateRange, num, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { bookablePrice, cellOn, fillIndicator, isTightNight, marketSnapshot, medianCompRate, selfRow, useMarketMetrics } from "@/lib/market-metrics";
import { Card, EmptyState, ErrorBox, PanelTitle, Segmented, SkeletonBlock, cx } from "@/components/ui";
import { KpiCard } from "@/components/kpi";
import { PageStrip } from "@/components/page-strip";
import { PriceBasisPicker, usePriceBasis } from "@/components/price-basis";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { DataUpdated } from "@/components/freshness";
import { HolidayChips } from "@/components/holiday-mark";
import { SampleTag, sampleFade, useCompsetLabels, useSampleText } from "@/components/compset-sample";
import { IconBuilding } from "@/components/icons";
import { ExportMenu } from "@/components/export-menu";
import { RateHeatmap, RatePositioning, RateTrends } from "./rate-views";

/**
 * Giá & định giá: bốn thẻ giá của đêm đầu kỳ, ba cách xem (Xu hướng, Vị trí, Heatmap), tình báo cạnh
 * tranh. Kỳ xem chọn được (mặc định 30 đêm từ hôm nay), VD xem trước vị trí giá dịp Tết.
 */

const DEFAULT_DAYS = 30;
type View = "trends" | "positioning" | "heatmap";

function RateKpis({ o, night, calibration, isToday }: { o: OverviewOut; night: PaceNightOut | undefined; calibration: CalibrationOut | undefined; isToday: boolean }) {
  const t = useTranslations("rates.kpi");
  const { fmtMoney, fmtNight } = useFmt();
  const { ratePosition } = useMarketMetrics();
  const s = marketSnapshot(o);
  const own = num(cellOn(selfRow(o), o.start)?.min_price);
  const pos = ratePosition(own, s.medianRate, isTightNight(s.tightness, fillIndicator(night, calibration)));
  const money = (v: number | null) => (v === null ? "—" : fmtMoney(Math.round(v), s.currency));
  const when = { when: isToday ? "tonight" : "other", night: fmtNight(o.start) };
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        align="left"
        title={t("compMedian")}
        value={<span className={sampleFade(s.compset)}>{money(s.medianRate)}</span>}
        sub={
          <span className="flex flex-col gap-0.5">
            <span>{t("compMedianSub", { ...when, count: s.priced })}</span>
            {s.compset && <SampleTag c={s.compset} />}
          </span>
        }
      />
      <KpiCard align="left" title={t("lowest")} value={money(s.minRate?.value ?? null)} sub={s.minRate?.name ?? "—"} />
      <KpiCard align="left" title={t("highest")} value={money(s.maxRate?.value ?? null)} sub={s.maxRate?.name ?? "—"} />
      <KpiCard
        align="left"
        title={t("yourRate")}
        value={money(own)}
        sub={pos ? <span className={pos.tone === "warn" ? "font-semibold text-warning-deep" : undefined}>{pos.text}</span> : selfRow(o) ? t("notComparable") : t("noOwnHotel")}
        tone="brand"
      />
    </div>
  );
}

function IntelBox({ value, label, title, tone = "text-ink" }: { value: string; label: string; title?: string; tone?: string }) {
  return (
    <div className="rounded-lg bg-subtle px-4 py-3.5 text-center" title={title}>
      <div className={cx("text-[26px] font-bold leading-tight tabular", tone)}>{value}</div>
      <div className="mt-0.5 text-sm text-muted">{label}</div>
    </div>
  );
}

/** TÌNH BÁO CẠNH TRANH: tỷ lệ đêm bạn rẻ hơn trung vị đối thủ, số đối thủ rẻ hơn đêm đầu kỳ, biên độ giá, hạng giá. */
function CompetitiveIntel({ o, isToday }: { o: OverviewOut; isToday: boolean }) {
  const t = useTranslations("rates.intel");
  const { fmtNight, fmtPriceShort } = useFmt();
  const labels = useCompsetLabels();
  const sample = useSampleText();
  const when = { when: isToday ? "tonight" : "other", night: fmtNight(o.start) };
  const self = selfRow(o);
  const dates = dateRange(o.start, o.end);
  let compared = 0;
  let cheaper = 0;
  for (const d of dates) {
    const own = bookablePrice(cellOn(self, d));
    const med = medianCompRate(o, d);
    if (own === null || med === null) continue;
    compared += 1;
    if (own < med) cheaper += 1;
  }
  const s = marketSnapshot(o);
  const own0 = bookablePrice(cellOn(self, o.start));
  const undercut =
    own0 === null
      ? null
      : o.hotels.filter((h) => h.role !== "self").filter((h) => {
          const p = bookablePrice(cellOn(h, o.start));
          return p !== null && p < own0;
        }).length;
  const c0 = o.compset.find((c) => c.stay_date === o.start);
  const spread = s.maxRate && s.minRate ? s.maxRate.value - s.minRate.value : null;
  return (
    <Card title={t("title")} info={t("info")}>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <IntelBox value={compared ? `${Math.round((cheaper / compared) * 100)}%` : "—"} label={t("cheaperNights", { count: compared })} />
        <IntelBox value={undercut === null ? "—" : String(undercut)} label={t("undercut", when)} />
        <IntelBox value={spread === null ? "—" : fmtPriceShort(spread, s.currency)} label={t("spread", when)} />
        <IntelBox
          value={c0?.own_rank ? `${c0.own_rank}/${c0.priced_hotels}` : "—"}
          label={c0 && c0.sample === "insufficient" ? `${t("rank", when)} · ${sample.status(c0)}` : c0?.sample === "small" ? `${t("rank", when)} · ${sample.status(c0)}` : t("rank", when)}
          title={c0 ? `${labels.rankLabel}: ${sample.title(c0)}` : undefined}
          tone={cx("text-brand", sampleFade(c0))}
        />
      </div>
    </Card>
  );
}

function RatesView() {
  const t = useTranslations("rates.page");
  const { fmtNight } = useFmt();
  const { start, end, days, today, ready } = useDateRange(DEFAULT_DAYS);
  const basis = usePriceBasis();
  const [view, setView] = useState<View>("trends");
  const overview = useApi(ready ? `rates:${start}:${end}:${basis}` : null, () => api.overview({ start, end, price_basis: basis }));
  // Chỉ báo lấp đầy của đêm đầu kỳ, để biết đêm đó có căng không (vị trí giá theo ngữ cảnh).
  const pace = useApi(ready ? `rates:pace:${start}` : null, () => api.market.pace({ start, end: start }));
  const o = overview.data;
  const fresh = useDataFreshness();
  const isToday = o?.start === today;

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
            <PriceBasisPicker />
            <ExportMenu start={start} end={end} priceBasis={basis} month={today.slice(0, 7)} />
          </>
        }
      />
      <ErrorBox error={overview.error} className="mb-4" />
      {!o && !overview.error && <SkeletonBlock className="h-[520px] w-full rounded-[10px]" />}
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
        <div className={cx("space-y-4 transition-opacity", overview.loading && "opacity-60")}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <PanelTitle info={t("analysisInfo")}>{t("analysis")}</PanelTitle>
            <Segmented
              label={t("view")}
              value={view}
              onChange={setView}
              items={[
                { value: "trends", label: t("views.trends") },
                { value: "positioning", label: t("views.positioning") },
                { value: "heatmap", label: t("views.heatmap") },
              ]}
            />
          </div>
          <RateKpis o={o} night={pace.data?.nights.find((n) => n.stay_date === o.start)} calibration={pace.data?.calibration} isToday={isToday} />
          {view === "trends" && <RateTrends o={o} />}
          {view === "positioning" && <RatePositioning o={o} />}
          {view === "heatmap" && <RateHeatmap o={o} />}
          <CompetitiveIntel o={o} isToday={isToday} />
        </div>
      )}
    </>
  );
}

export default function RatesPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[520px] w-full rounded-[10px]" />}>
      <RatesView />
    </Suspense>
  );
}
