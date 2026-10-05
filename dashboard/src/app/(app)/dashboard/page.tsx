"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Suspense } from "react";
import { api, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { addDays, dateRange, num, useFmt } from "@/lib/format";
import { channelName } from "@/lib/channels";
import { DEMAND_COLOR, avgCompRate, demandLevel, marketSnapshot, useMarketMetrics } from "@/lib/market-metrics";
import { Card, EmptyState, ErrorBox, SkeletonBlock, cx } from "@/components/ui";
import { KpiCard, SnapshotRow } from "@/components/kpi";
import { ArcGauge } from "@/components/gauge";
import { TrendChart, type TrendRow } from "@/components/trend-chart";
import { PageStrip, StripDivider } from "@/components/page-strip";
import { ChannelSwitcher, useChannelParam } from "@/components/channels";
import { IconBuilding, IconChevronRight } from "@/components/icons";
import { DemandForecast } from "./demand-forecast";
import { DataStatus, SmartAlerts, YourHotel } from "./side-cards";

/** Bảng điều khiển: toàn cảnh compset đêm nay, dự báo cầu 14 đêm, xu hướng, cảnh báo, khách sạn của bạn. */

const DAYS = 14;

function DashboardSkeleton() {
  const tc = useTranslations("common.status");
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]" aria-busy aria-label={tc("loading")}>
      <div className="space-y-4">
        <SkeletonBlock className="h-36 rounded-[10px]" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
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
  const { fmtNight, fmtWhen } = useFmt();
  const today = useTenantToday();
  const end = today ? addDays(today, DAYS - 1) : "";
  const [channelParam, setChannel] = useChannelParam();
  const overview = useApi(today && `dash:ov:${today}:${channelParam ?? ""}`, () => api.overview({ start: today!, end, channel: channelParam }));
  const pace = useApi(today && `dash:pace:${today}`, () => api.market.pace({ start: today!, end }));
  const runs = useApi("dash:runs", () => api.runs(20));
  const settings = useApi("settings", () => api.settings.get());

  const o = overview.data;
  const nights = pace.data?.nights ?? [];
  const byNight = new Map(nights.map((n) => [n.stay_date, n]));
  const lastRun = runs.data?.[0];

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={
          o && (
            <>
              <span>{t("strip.range", { count: DAYS, start: fmtNight(o.start) })}</span>
              <StripDivider />
              <span>{t.rich("strip.channel", { name: channelName(o.channel), b: (c) => <span className="font-semibold text-ink">{c}</span> })}</span>
            </>
          )
        }
        aside={lastRun && <span>{t("strip.updated", { when: fmtWhen(lastRun.finished_at ?? lastRun.started_at) })}</span>}
        actions={o && <ChannelSwitcher channels={o.channels} value={o.channel} onChange={setChannel} />}
      />
      <ErrorBox error={overview.error} className="mb-4" />
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
            <MarketSnapshotCard o={o} channelParam={channelParam} />
            <CompsetKpis o={o} tonight={byNight.get(o.start)} />
            <DemandForecast start={o.start} end={o.end} today={today ?? o.start} nights={nights} compset={o.compset} channel={channelParam} />
            <MarketTrends o={o} byNight={byNight} />
          </div>
          <div className="min-w-0 space-y-4">
            <SmartAlerts overview={o} nights={nights} lastRun={lastRun} />
            <YourHotel overview={o} tonight={byNight.get(o.start)} />
            <DataStatus overview={o} runs={runs.data ?? []} settings={settings.data} />
          </div>
        </div>
      )}
    </>
  );
}

function MarketSnapshotCard({ o, channelParam }: { o: OverviewOut; channelParam: string | null }) {
  const t = useTranslations("dashboard.snapshot");
  const { fmtCompact, fmtInt, fmtMoney } = useFmt();
  const s = marketSnapshot(o);
  return (
    <Card
      title={t("title")}
      info={t("info")}
      actions={
        <Link href={`/availability${channelParam ? `?channel=${channelParam}` : ""}`} className="inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline">
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
            { value: s.roomsKnown ? fmtInt(s.roomsLeft) : "—", label: t("roomsLeft"), title: t("roomsLeftTitle", { known: s.roomsKnown, observed: s.observed }) },
            { value: s.avgRate === null ? "—" : fmtCompact(s.avgRate), label: t("avgRate"), title: s.avgRate === null ? undefined : fmtMoney(Math.round(s.avgRate), s.currency) },
          ]}
        />
      </div>
    </Card>
  );
}

function CompsetKpis({ o, tonight }: { o: OverviewOut; tonight: PaceNightOut | undefined }) {
  const t = useTranslations("dashboard.kpi");
  const { fmtCompact } = useFmt();
  const { demandLabel } = useMarketMetrics();
  const s = marketSnapshot(o);
  const occ = num(tonight?.comp_occ);
  const occPct = occ === null ? null : Math.round(occ * 100);
  const revpar = s.avgRate !== null && occ !== null ? s.avgRate * occ : null;
  const level = s.compression === null ? null : demandLevel(s.compression);
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard title={t("compression.title")} info={t("compression.info")}>
        <div className="mt-2">
          <ArcGauge value={s.compression} color={level ? DEMAND_COLOR[level] : "var(--sb-faint)"} caption={level ? demandLabel(level) : t("compression.noData")} size={116} />
        </div>
      </KpiCard>
      <KpiCard
        title={t("adr.title")}
        info={t("adr.info")}
        value={s.avgRate === null ? "—" : fmtCompact(s.avgRate)}
        sub={t("adr.sub")}
      />
      <KpiCard
        title={t("revpar.title")}
        info={t("revpar.info")}
        value={revpar === null ? "—" : `≈${fmtCompact(revpar)}`}
        sub={t("revpar.sub")}
        tone="brand"
      />
      <KpiCard
        title={t("occ.title")}
        info={t("occ.info", { count: tonight?.comp_occ_hotels ?? 0 })}
        value={occPct === null ? "—" : `≈${occPct}%`}
        sub={s.roomsKnown ? t("occ.roomsLeft", { count: s.roomsLeft }) : t("occ.notEnough")}
        tone="hot"
      />
    </div>
  );
}

function MarketTrends({ o, byNight }: { o: OverviewOut; byNight: Map<string, PaceNightOut> }) {
  const t = useTranslations("dashboard.trends");
  const { fmtCompact, fmtMoney, fmtNight } = useFmt();
  const rows: TrendRow[] = dateRange(o.start, o.end).map((d) => {
    const adr = avgCompRate(o, d);
    const occ = num(byNight.get(d)?.comp_occ);
    return {
      x: d,
      adr: adr === null ? null : Math.round(adr),
      revpar: adr !== null && occ !== null ? Math.round(adr * occ) : null,
      occ: occ === null ? null : Math.round(occ * 100),
    };
  });
  return (
    <Card title={t("title")} info={t("info")}>
      <TrendChart
        data={rows}
        height={280}
        formatX={(x) => fmtNight(x)}
        formatLeft={(v) => fmtCompact(v)}
        formatRight={(v) => `${v}%`}
        formatValue={(v, s) => (s.right ? `≈${v}%` : fmtMoney(v, o.compset[0]?.currency ?? "VND"))}
        series={[
          { key: "adr", name: "ADR", color: "#0062ff" },
          { key: "revpar", name: "RevPAR ≈", color: "#8b5cf6", dashed: true },
          { key: "occ", name: t("occSeries"), color: "#16a34a", right: true },
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
