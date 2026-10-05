"use client";

import { useTranslations } from "next-intl";
import type { MarketOccupancyOut, PaceNightOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { MARKET_LINE_COLOR } from "@/lib/market-metrics";
import { Card, cx } from "@/components/ui";
import { TrendChart, type TrendRow, type TrendSeries } from "@/components/trend-chart";

/**
 * PHÂN TÍCH CÔNG SUẤT (như mẫu): mỗi khách sạn một đường công suất ước tính, trung vị compset nét đứt,
 * khách sạn của bạn đậm; công suất PMS khi đã nhập. Bốn ô: TB, cao nhất, thấp nhất, số KS ≈≥90% đêm đầu.
 */

function pct(v: string | number | null | undefined): number | null {
  const n = num(v);
  return n === null ? null : Math.round(n * 100);
}

function StatBox({ value, label, tone }: { value: string; label: string; tone: string }) {
  return (
    <div className="rounded-lg bg-subtle px-4 py-3 text-center">
      <div className={cx("text-[26px] font-bold leading-tight tabular", tone)}>{value}</div>
      <div className="mt-0.5 text-sm text-muted">{label}</div>
    </div>
  );
}

export function OccupancyAnalysis({ nights, perHotel, colors }: { nights: PaceNightOut[]; perHotel: MarketOccupancyOut | undefined; colors: Map<number, string> }) {
  const t = useTranslations("availability.occupancy");
  const { fmtNight } = useFmt();
  const comp = nights.map((n) => ({ d: n.stay_date, v: pct(n.comp_occ) })).filter((x): x is { d: string; v: number } => x.v !== null);
  const avg = comp.length ? Math.round(comp.reduce((a, b) => a + b.v, 0) / comp.length) : null;
  const peak = comp.reduce<{ d: string; v: number } | null>((m, x) => (!m || x.v > m.v ? x : m), null);
  const low = comp.reduce<{ d: string; v: number } | null>((m, x) => (!m || x.v < m.v ? x : m), null);
  const hasPms = nights.some((n) => n.own_pms_occ !== null);
  const first = nights[0]?.stay_date;
  const hotels = perHotel?.hotels ?? [];
  // Khách sạn có ước tính đủ tin cậy cho đêm đầu và từ 90% trở lên.
  const firstKnown = hotels.filter((h) => h.nights.some((n) => n.stay_date === first && n.occ_mid !== null));
  const hot = firstKnown.filter((h) => (pct(h.nights.find((n) => n.stay_date === first)?.occ_mid) ?? 0) >= 90).length;

  const occBy = new Map(hotels.map((h) => [h.hotel_id, new Map(h.nights.map((n) => [n.stay_date, pct(n.occ_mid)]))]));
  const rows: TrendRow[] = nights.map((n) => {
    const row: TrendRow = { x: n.stay_date, comp: pct(n.comp_occ), pms: pct(n.own_pms_occ) };
    for (const h of hotels) row[`h${h.hotel_id}`] = occBy.get(h.hotel_id)?.get(n.stay_date) ?? null;
    return row;
  });
  const series: TrendSeries[] = [
    { key: "comp", name: t("compMedian"), color: MARKET_LINE_COLOR, dashed: true, area: true, width: 2.4 },
    ...hotels.map((h) => ({
      key: `h${h.hotel_id}`,
      name: t("hotelSeries", { name: h.name ?? `#${h.hotel_id}` }),
      color: colors.get(h.hotel_id) ?? "#9ca3af",
      width: h.role === "self" ? 3 : 1.5,
    })),
  ];
  if (hasPms) series.push({ key: "pms", name: t("pms"), color: "#16a34a", width: 2, dashed: true });

  return (
    <Card
      title={t("title")}
      info={t("info")}
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatBox value={avg === null ? "—" : `≈${avg}%`} label={t("avg", { count: comp.length })} tone={avg === null ? "text-faint" : avg >= 75 ? "text-hot" : "text-yours"} />
        <StatBox value={peak ? `≈${peak.v}%` : "—"} label={peak ? t("peakOn", { night: fmtNight(peak.d) }) : t("peak")} tone="text-danger" />
        <StatBox value={low ? `≈${low.v}%` : "—"} label={low ? t("lowOn", { night: fmtNight(low.d) }) : t("low")} tone="text-yours" />
        <StatBox value={firstKnown.length ? `${hot}/${firstKnown.length}` : "—"} label={t("hotFirstNight")} tone="text-brand" />
      </div>
      <TrendChart
        className="mt-4"
        data={rows}
        series={series}
        height={320}
        leftDomain={[0, 100]}
        formatX={(x) => fmtNight(x)}
        formatLeft={(v) => `${v}%`}
        formatValue={(v) => `${v}%`}
        emptyText={t("empty")}
      />
    </Card>
  );
}
