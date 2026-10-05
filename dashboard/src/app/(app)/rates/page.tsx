"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Suspense, useState } from "react";
import { api, type OverviewOut } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { addDays, dateRange, num, useFmt } from "@/lib/format";
import { channelName } from "@/lib/channels";
import { avgCompRate, bookablePrice, cellOn, marketSnapshot, selfRow, useMarketMetrics } from "@/lib/market-metrics";
import { Card, EmptyState, ErrorBox, PanelTitle, Segmented, SkeletonBlock, cx } from "@/components/ui";
import { KpiCard } from "@/components/kpi";
import { PageStrip, StripDivider } from "@/components/page-strip";
import { ChannelSwitcher, useChannelParam } from "@/components/channels";
import { PriceBasisPicker, usePriceBasis } from "@/components/price-basis";
import { IconBuilding } from "@/components/icons";
import { RateHeatmap, RatePositioning, RateTrends } from "./rate-views";

/** Giá & định giá: bốn thẻ giá đêm nay, ba cách xem (Xu hướng, Vị trí, Heatmap), tình báo cạnh tranh. */

const DAYS = 30;
type View = "trends" | "positioning" | "heatmap";

function RateKpis({ o }: { o: OverviewOut }) {
  const t = useTranslations("rates.kpi");
  const { fmtMoney } = useFmt();
  const { ratePosition } = useMarketMetrics();
  const s = marketSnapshot(o);
  const own = num(cellOn(selfRow(o), o.start)?.min_price);
  const pos = ratePosition(own, s.avgRate);
  const money = (v: number | null) => (v === null ? "—" : fmtMoney(Math.round(v), s.currency));
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard align="left" title={t("marketAvg")} value={money(s.avgRate)} sub={t("marketAvgSub")} />
      <KpiCard align="left" title={t("lowest")} value={money(s.minRate?.value ?? null)} sub={s.minRate?.name ?? "—"} />
      <KpiCard align="left" title={t("highest")} value={money(s.maxRate?.value ?? null)} sub={s.maxRate?.name ?? "—"} />
      <KpiCard align="left" title={t("yourRate")} value={money(own)} sub={pos?.text ?? (selfRow(o) ? t("notComparable") : t("noOwnHotel"))} tone="brand" />
    </div>
  );
}

function IntelBox({ value, label, tone = "text-ink" }: { value: string; label: string; tone?: string }) {
  return (
    <div className="rounded-lg bg-subtle px-4 py-3.5 text-center">
      <div className={cx("text-[26px] font-bold leading-tight tabular", tone)}>{value}</div>
      <div className="mt-0.5 text-sm text-muted">{label}</div>
    </div>
  );
}

/** TÌNH BÁO CẠNH TRANH: tỷ lệ đêm bạn rẻ hơn thị trường, số đối thủ rẻ hơn đêm nay, biên độ giá, hạng giá. */
function CompetitiveIntel({ o }: { o: OverviewOut }) {
  const t = useTranslations("rates.intel");
  const { fmtCompact } = useFmt();
  const self = selfRow(o);
  const dates = dateRange(o.start, o.end);
  let compared = 0;
  let cheaper = 0;
  for (const d of dates) {
    const own = bookablePrice(cellOn(self, d));
    const avg = avgCompRate(o, d);
    if (own === null || avg === null) continue;
    compared += 1;
    if (own < avg) cheaper += 1;
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
    <Card title={t("title")} info={t("info", { channel: channelName(o.channel) })}>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <IntelBox value={compared ? `${Math.round((cheaper / compared) * 100)}%` : "—"} label={t("cheaperNights", { count: compared })} />
        <IntelBox value={undercut === null ? "—" : String(undercut)} label={t("undercut")} tone={undercut ? "text-danger" : "text-ink"} />
        <IntelBox value={spread === null ? "—" : fmtCompact(spread)} label={t("spread")} />
        <IntelBox value={c0?.own_rank ? `${c0.own_rank}/${c0.priced_hotels}` : "—"} label={t("rank")} tone="text-brand" />
      </div>
    </Card>
  );
}

function RatesView() {
  const t = useTranslations("rates.page");
  const { fmtWhen } = useFmt();
  const today = useTenantToday();
  const end = today ? addDays(today, DAYS - 1) : "";
  const [channelParam, setChannel] = useChannelParam();
  const basis = usePriceBasis();
  const [view, setView] = useState<View>("trends");
  const overview = useApi(today && `rates:${today}:${channelParam ?? ""}:${basis}`, () => api.overview({ start: today!, end, channel: channelParam, price_basis: basis }));
  const o = overview.data;

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={
          o && (
            <>
              <span>{t("nights", { count: DAYS })}</span>
              <StripDivider />
              <span>{t.rich("channel", { channel: channelName(o.channel), b: (c) => <span className="font-semibold text-ink">{c}</span> })}</span>
            </>
          )
        }
        aside={o?.last_run && <span>{t("scannedAt", { when: fmtWhen(o.last_run.finished_at ?? o.last_run.started_at) })}</span>}
        actions={
          <>
            {o && <ChannelSwitcher channels={o.channels} value={o.channel} onChange={setChannel} />}
            <PriceBasisPicker />
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
          <RateKpis o={o} />
          {view === "trends" && <RateTrends o={o} />}
          {view === "positioning" && <RatePositioning o={o} channelParam={channelParam} />}
          {view === "heatmap" && <RateHeatmap o={o} channelParam={channelParam} />}
          <CompetitiveIntel o={o} />
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
