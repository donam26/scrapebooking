"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import type { OverviewOut, PaceNightOut, ScanRunOut, TenantOut } from "@/lib/api";
import { channelName } from "@/lib/channels";
import { scanCollectedNothing, scanOverdue, useFmt, type Fmt } from "@/lib/format";
import { avgCompRate, bookablePrice, cellOn, competitorRows, rowName, selfRow, useMarketMetrics } from "@/lib/market-metrics";
import { pendingSuggestions, useMarketText } from "@/lib/market";
import { Card, cx } from "@/components/ui";
import { KeyValueRow } from "@/components/kpi";
import { IconCheck, IconClock } from "@/components/icons";

type Alert = { key: string; text: string; tone: "warn" | "bad" | "info"; href?: string };
type AlertsTranslator = ReturnType<typeof useTranslations<"dashboard.alerts">>;

const ALERT_CLASS = {
  warn: "border-l-[#f59e0b] bg-[#fef6dc] text-[#b45309]",
  bad: "border-l-danger bg-danger-soft text-danger-deep",
  info: "border-l-brand bg-brand-softer text-brand-hover",
};

/** Cảnh báo đáng chú ý: đối thủ hết/sắp hết đêm nay, đêm compset căng trong 7 đêm, gợi ý giá đang chờ, lượt quét lỗi. */
function buildAlerts(o: OverviewOut, nights: PaceNightOut[], lastRun: ScanRunOut | undefined, t: AlertsTranslator, fmt: Fmt): Alert[] {
  const out: Alert[] = [];
  if (lastRun && scanCollectedNothing(lastRun)) {
    out.push({ key: "run", tone: "bad", text: t("runFailed", { channel: channelName(lastRun.channel) }), href: "/runs" });
  }
  const self = selfRow(o);
  const own = cellOn(self, o.start);
  if (own?.availability_status === "sold_out") out.push({ key: "own", tone: "info", text: t("ownSoldOut") });
  else if (own?.exact_rooms_left !== null && own?.exact_rooms_left !== undefined && own.exact_rooms_left <= 3)
    out.push({ key: "own", tone: "info", text: t("ownLow", { count: own.exact_rooms_left }) });
  for (const r of competitorRows(o)) {
    const c = cellOn(r, o.start);
    if (c?.availability_status === "sold_out") out.push({ key: `so${r.hotel.id}`, tone: "bad", text: t("compSoldOut", { name: rowName(r) }), href: `/hotels/${r.hotel.id}` });
    else if (c?.exact_rooms_left !== null && c?.exact_rooms_left !== undefined && c.exact_rooms_left <= 3)
      out.push({ key: `low${r.hotel.id}`, tone: "warn", text: t("compLow", { name: rowName(r), count: c.exact_rooms_left }), href: `/hotels/${r.hotel.id}` });
  }
  for (const c of o.compset.slice(1, 8)) {
    if (c.competitors_observed > 1 && c.competitors_sold_out / c.competitors_observed >= 0.5) {
      out.push({ key: `night${c.stay_date}`, tone: "warn", text: t("tightNight", { night: fmt.fmtNight(c.stay_date), soldOut: c.competitors_sold_out, observed: c.competitors_observed }), href: `/availability?start=${c.stay_date}` });
    }
  }
  const pending = pendingSuggestions(nights).length;
  if (pending) out.push({ key: "sugg", tone: "info", text: t("suggestions", { count: pending }), href: "/terminal#pace" });
  return out;
}

export function SmartAlerts({ overview, nights, lastRun }: { overview: OverviewOut; nights: PaceNightOut[]; lastRun: ScanRunOut | undefined }) {
  const t = useTranslations("dashboard.alerts");
  const fmt = useFmt();
  const alerts = buildAlerts(overview, nights, lastRun, t, fmt);
  const shown = alerts.slice(0, 5);
  return (
    <Card title={t("title")} info={t("info")}>
      {shown.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="space-y-2">
          {shown.map((a) => {
            const cls = cx("block rounded-md border-l-[3px] px-3 py-2.5 text-sm font-medium", ALERT_CLASS[a.tone]);
            return (
              <li key={a.key}>
                {a.href ? (
                  <Link href={a.href} className={cx(cls, "hover:brightness-[0.98]")}>
                    {a.text}
                  </Link>
                ) : (
                  <div className={cls}>{a.text}</div>
                )}
              </li>
            );
          })}
          {alerts.length > shown.length && <li className="text-xs text-muted">{t("more", { count: alerts.length - shown.length })}</li>}
        </ul>
      )}
    </Card>
  );
}

export function YourHotel({ overview, tonight }: { overview: OverviewOut; tonight: PaceNightOut | undefined }) {
  const t = useTranslations("dashboard.yourHotel");
  const { fmtMoney } = useFmt();
  const { ratePosition } = useMarketMetrics();
  const { ownOccText } = useMarketText();
  const self = selfRow(overview);
  if (!self) {
    return (
      <Card title={t("title")}>
        <p className="text-sm text-muted">
          {t.rich("empty", {
            link: (c) => (
              <Link href="/settings?tab=watchlist" className="font-semibold text-brand hover:underline">
                {c}
              </Link>
            ),
          })}
        </p>
      </Card>
    );
  }
  const cell = cellOn(self, overview.start);
  const own = bookablePrice(cell);
  const market = avgCompRate(overview, overview.start);
  const pos = ratePosition(own, market);
  const occ = tonight ? ownOccText(tonight) : null;
  const inventory = tonight?.own_occ?.inventory ?? null;
  const roomsLeft = cell?.availability_status === "sold_out" ? 0 : (cell?.exact_rooms_left ?? null);
  const currency = cell?.currency ?? null;
  return (
    <Card
      title={t("title")}
      info={t("info")}
    >
      <div className="border-b border-line pb-4 text-center">
        <div className="text-[34px] font-bold leading-tight text-brand tabular">{occ?.text ?? "—"}</div>
        <div className="text-sm text-muted">{t("occCaption", { source: occ?.source ?? "none" })}</div>
      </div>
      <div className="divide-y divide-line">
        <KeyValueRow label={t("yourRate")} value={own === null ? "—" : fmtMoney(own, currency)} />
        <KeyValueRow label={t("marketRate")} value={market === null ? "—" : fmtMoney(Math.round(market), currency)} />
        <KeyValueRow label={t("roomsLeft")} value={roomsLeft === null ? (cell?.availability_status ? t("hidden") : "—") : inventory ? `${roomsLeft} / ${inventory}` : String(roomsLeft)} />
        <KeyValueRow label={t("position")} value={pos?.text ?? "—"} tone={pos ? (pos.tone === "good" ? "good" : pos.tone === "warn" ? "hot" : "default") : "default"} />
      </div>
    </Card>
  );
}

export function DataStatus({ overview, runs, settings }: { overview: OverviewOut; runs: ScanRunOut[]; settings: TenantOut | undefined }) {
  const t = useTranslations("dashboard.dataStatus");
  const { fmtAgo, fmtWhen, nextScanLabel } = useFmt();
  const last = runs[0];
  const lastAt = last ? (last.finished_at ?? last.started_at) : null;
  const failed = last ? scanCollectedNothing(last) : false;
  const overdue = !failed && settings !== undefined && scanOverdue(lastAt, settings.scan_times);
  const next = settings ? nextScanLabel(settings.scan_times, settings.timezone) : null;
  // Kênh có lượt quét thu được dữ liệu trong 24 giờ qua.
  const [dayAgo] = useState(() => Date.now() - 24 * 3600 * 1000);
  const liveChannels = new Set(
    runs.filter((r) => new Date(r.started_at ?? r.scheduled_at).getTime() > dayAgo && !scanCollectedNothing(r)).map((r) => r.channel),
  );
  return (
    <Card title={t("title")} info={t("info")}>
      <div className="divide-y divide-line">
        <KeyValueRow
          icon={<IconClock size={16} />}
          label={t("lastScan")}
          value={last ? (last.status === "running" ? t("scanning") : fmtWhen(lastAt)) : t("none")}
          tone={failed ? "bad" : overdue ? "hot" : "default"}
        />
        <KeyValueRow icon={<IconClock size={16} />} label={t("nextScan")} value={next ?? t("notScheduled")} />
        <KeyValueRow icon={<IconCheck size={16} />} label={t("liveChannels")} value={t("liveChannelsValue", { live: liveChannels.size, total: overview.channels.length })} tone={liveChannels.size ? "good" : "bad"} />
        <KeyValueRow icon={<IconCheck size={16} />} label={t("hotels")} value={String(overview.hotels.length)} tone="good" />
      </div>
      {overdue && <p className="mt-2 text-xs font-semibold text-warning-deep">{t("overdue", { ago: fmtAgo(lastAt) })}</p>}
    </Card>
  );
}
