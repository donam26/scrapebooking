"use client";

import { useTranslations } from "next-intl";
import type { CalibrationOut, MarketOccupancyOut, PaceNightOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { DEMAND_TEXT, MARKET_LINE_COLOR, demandLevel, fillHidden, fillIndicator } from "@/lib/market-metrics";
import { CalibrationNote } from "@/components/fill";
import { Card, cx } from "@/components/ui";
import { TrendChart, type TrendRow, type TrendSeries } from "@/components/trend-chart";

/**
 * CHỈ BÁO LẤP ĐẦY (thử nghiệm, không phải công suất): mỗi khách sạn một đường ước tính từ số phòng
 * còn, trung vị compset nét đứt, khách sạn của bạn đậm; công suất PMS thật khi đã nhập. Bốn ô: TB,
 * cao nhất, thấp nhất, số KS ≈≥90% đêm đầu. Màu theo thang mức chung.
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

export function OccupancyAnalysis({
  nights,
  calibration,
  perHotel,
  colors,
}: {
  nights: PaceNightOut[];
  /** Nhóm lead time sai số quá ngưỡng so PMS: ẩn chỉ báo của đêm đó. */
  calibration: CalibrationOut | undefined;
  perHotel: MarketOccupancyOut | undefined;
  colors: Map<number, string>;
}) {
  const t = useTranslations("availability.occupancy");
  const { fmtNight } = useFmt();
  const hiddenNights = nights.filter((n) => n.comp_occ !== null && fillHidden(calibration, n.days_to_arrival)).length;
  const hide = new Set(nights.filter((n) => fillHidden(calibration, n.days_to_arrival)).map((n) => n.stay_date));
  const comp = nights.map((n) => ({ d: n.stay_date, v: pct(fillIndicator(n, calibration)) })).filter((x): x is { d: string; v: number } => x.v !== null);
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
    const row: TrendRow = { x: n.stay_date, comp: pct(fillIndicator(n, calibration)), pms: pct(n.own_pms_occ) };
    for (const h of hotels) row[`h${h.hotel_id}`] = hide.has(n.stay_date) ? null : (occBy.get(h.hotel_id)?.get(n.stay_date) ?? null);
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
    <Card title={t("title")} info={t("info")} description={t("source")}>
      <p className="mb-3 text-xs">
        <CalibrationNote calibration={calibration} />
        {hiddenNights > 0 && <span className="text-muted"> · {t("hiddenNights", { count: hiddenNights })}</span>}
      </p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatBox value={avg === null ? "—" : `≈${avg}%`} label={t("avg", { count: comp.length })} tone={avg === null ? "text-faint" : DEMAND_TEXT[demandLevel(avg)]} />
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
