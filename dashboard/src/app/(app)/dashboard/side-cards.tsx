"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { cellState, type CalibrationOut, type OverviewOut, type PaceNightOut, type TenantOut } from "@/lib/api";
import { useFmt } from "@/lib/format";
import { successPct, type DataFreshness, type FreshnessState } from "@/lib/freshness";
import { bookablePrice, cellOn, compsetDay, compsetTightness, competitorRows, fillIndicator, isTightNight, medianCompRate, rowName, selfRow, useMarketMetrics } from "@/lib/market-metrics";
import { useMarketText } from "@/lib/market";
import { Card, cx } from "@/components/ui";
import { KeyValueRow } from "@/components/kpi";
import { SampleTag, sampleFade } from "@/components/compset-sample";
import { IconCheck, IconClock } from "@/components/icons";

type Alert = { key: string; text: string; tone: "warn" | "bad" | "info"; href?: string };
type AlertsTranslator = ReturnType<typeof useTranslations<"dashboard.alerts">>;

const ALERT_CLASS = {
  warn: "border-l-[#f59e0b] bg-[#fef6dc] text-[#b45309]",
  bad: "border-l-danger bg-danger-soft text-danger-deep",
  info: "border-l-brand bg-brand-softer text-brand-hover",
};

/**
 * Cảnh báo còn lại sau thẻ "Việc cần làm hôm nay" (gợi ý giá, đêm căng, đối thủ hết phòng nằm ở đó):
 * lượt quét gần nhất không thu được dữ liệu, khách sạn của bạn hết/sắp hết, đối thủ còn ≤3 phòng.
 */
function buildAlerts(o: OverviewOut, fresh: DataFreshness, isToday: boolean, night: string, t: AlertsTranslator): Alert[] {
  const out: Alert[] = [];
  const when = isToday ? "tonight" : "other";
  if (fresh.latestEmpty && fresh.latest) {
    out.push({ key: "run", tone: "bad", text: t("runFailed"), href: "/runs" });
  }
  const own = cellOn(selfRow(o), o.start);
  if (cellState(own) === "sold_out") out.push({ key: "own", tone: "info", text: t("ownSoldOut", { when, night }) });
  else if (own?.exact_rooms_left !== null && own?.exact_rooms_left !== undefined && own.exact_rooms_left <= 3)
    out.push({ key: "own", tone: "info", text: t("ownLow", { count: own.exact_rooms_left, when, night }) });
  for (const r of competitorRows(o)) {
    const c = cellOn(r, o.start);
    if (cellState(c) === "sold_out" && !isToday) out.push({ key: `so${r.hotel.id}`, tone: "bad", text: t("compSoldOut", { name: rowName(r), when, night }), href: `/hotels/${r.hotel.id}` });
    else if (cellState(c) === "available" && c?.exact_rooms_left !== null && c?.exact_rooms_left !== undefined && c.exact_rooms_left <= 3)
      out.push({ key: `low${r.hotel.id}`, tone: "warn", text: t("compLow", { name: rowName(r), count: c.exact_rooms_left, when, night }), href: `/hotels/${r.hotel.id}` });
  }
  return out;
}

export function SmartAlerts({ overview, fresh, today }: { overview: OverviewOut; fresh: DataFreshness; today: string }) {
  const t = useTranslations("dashboard.alerts");
  const { fmtNight } = useFmt();
  const isToday = overview.start === today;
  const alerts = buildAlerts(overview, fresh, isToday, fmtNight(overview.start), t);
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

export function YourHotel({ overview, night, calibration, isToday }: { overview: OverviewOut; night: PaceNightOut | undefined; calibration?: CalibrationOut; isToday: boolean }) {
  const t = useTranslations("dashboard.yourHotel");
  const { fmtMoney, fmtNight } = useFmt();
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
  const market = medianCompRate(overview, overview.start);
  const c0 = compsetDay(overview, overview.start);
  const tight = isTightNight(compsetTightness(overview, overview.start), fillIndicator(night, calibration));
  const pos = ratePosition(own, market, tight);
  const occ = night ? ownOccText(night) : null;
  const inventory = night?.own_occ?.inventory ?? null;
  const roomsLeft = cellState(cell) === "sold_out" ? 0 : (cell?.exact_rooms_left ?? null);
  const currency = cell?.currency ?? null;
  const when = isToday ? "tonight" : "other";
  return (
    <Card title={t("title")} info={t("info")}>
      <div className="border-b border-line pb-4 text-center">
        <div className="text-[34px] font-bold leading-tight text-brand tabular">{occ?.text ?? "—"}</div>
        <div className="text-sm text-muted">{t("occCaption", { source: occ?.source ?? "none", when, night: fmtNight(overview.start) })}</div>
      </div>
      <div className="divide-y divide-line">
        <KeyValueRow label={t("yourRate")} value={own === null ? "—" : fmtMoney(own, currency)} />
        <KeyValueRow
          label={t("marketRate")}
          value={
            <span className="flex flex-col items-end">
              <span className={sampleFade(c0)}>{market === null ? "—" : fmtMoney(Math.round(market), currency)}</span>
              {c0 && <SampleTag c={c0} short className="text-xs font-normal" />}
            </span>
          }
        />
        <KeyValueRow label={t("roomsLeft")} value={roomsLeft === null ? (cell?.availability_status ? t("hidden") : "—") : inventory ? `${roomsLeft} / ${inventory}` : String(roomsLeft)} />
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-line pt-2.5 text-base">
        <span className="text-body">{t("position")}</span>
        <span className={cx("text-right font-semibold", pos?.tone === "warn" ? "text-warning-deep" : "text-ink")}>{pos?.text ?? "—"}</span>
      </div>
    </Card>
  );
}

export function DataStatus({ overview, fresh, settings }: { overview: OverviewOut; fresh: FreshnessState; settings: TenantOut | undefined }) {
  const t = useTranslations("dashboard.dataStatus");
  const { fmtAgo, fmtWhen, nextScanLabel } = useFmt();
  const next = settings ? nextScanLabel(settings.scan_times, settings.timezone) : null;
  const tone = fresh.tone === "bad" ? "bad" : fresh.tone === "warn" ? "hot" : "default";
  // Tỷ lệ đọc trang Booking.com thành công 7 ngày (gồm hết phòng; không gồm bị chặn, lỗi).
  const status = fresh.status;
  const pct = status ? successPct(status) : null;
  return (
    <Card title={t("title")} info={t("info")}>
      <div className="divide-y divide-line">
        <KeyValueRow icon={<IconClock size={16} />} label={t("updated")} value={fresh.updatedAt ? fmtWhen(fresh.updatedAt) : t("none")} tone={tone} />
        {fresh.running && <KeyValueRow icon={<IconClock size={16} />} label={t("now")} value={t("scanning")} />}
        <KeyValueRow icon={<IconClock size={16} />} label={t("nextScan")} value={next ?? t("notScheduled")} />
        {status && (
          <KeyValueRow
            icon={<IconCheck size={16} />}
            label={t("successRate")}
            value={
              <span title={status.probes_7d ? t("successProbes", { ok: status.probes_7d - status.failed_7d, total: status.probes_7d }) : undefined}>
                {pct === null ? "—" : `${pct}%`}
              </span>
            }
            tone={pct === null ? "default" : pct >= 90 ? "good" : pct >= 80 ? "hot" : "bad"}
          />
        )}
        <KeyValueRow icon={<IconCheck size={16} />} label={t("hotels")} value={String(overview.hotels.length)} tone="good" />
      </div>
      {fresh.stale && <p className="mt-2 text-xs font-semibold text-danger">{t("stale", { hours: fresh.staleAfterHours ?? 24 })}</p>}
      {!fresh.stale && fresh.latestEmpty && fresh.latest && (
        <p className={cx("mt-2 text-xs font-semibold", fresh.tone === "bad" ? "text-danger" : "text-warning-deep")}>{t("latestEmpty", { when: fmtWhen(fresh.latest.finished_at) })}</p>
      )}
      {fresh.overdue && <p className="mt-2 text-xs font-semibold text-warning-deep">{t("overdue", { ago: fmtAgo(fresh.updatedAt) })}</p>}
    </Card>
  );
}
