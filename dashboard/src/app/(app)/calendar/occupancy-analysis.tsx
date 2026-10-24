"use client";

import { useTranslations } from "next-intl";
import type { CalibrationOut, MarketOccupancyOut, PaceNightOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { DEMAND_TEXT, MARKET_LINE_COLOR, OWN_LINE_COLOR, demandLevel, fillHidden, fillIndicator } from "@/lib/market-metrics";
import { CalibrationNote, useFillText } from "@/components/fill";
import { cx } from "@/components/ui";
import { TrendChart, type TrendRow, type TrendSeries } from "@/components/trend-chart";

/**
 * CHỈ BÁO LẤP ĐẦY (thử nghiệm, không phải công suất): mỗi khách sạn một đường ước tính từ số phòng
 * còn, mức giữa nhóm đối thủ nét đứt đen, khách sạn của bạn đậm; công suất PMS thật (xanh thương
 * hiệu, nét đứt) khi đã nhập. Dưới 2 khách sạn có ước tính thì chỉ còn một câu giải thích; ô số và
 * chú giải chỉ hiện phần có dữ liệu.
 */

/** Cần ít nhất chừng này khách sạn có ước tính thì biểu đồ mới có nghĩa. */
const MIN_HOTELS = 2;

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

/** Dòng độ tin: đã có PMS mà chưa hiệu chỉnh được thì nói vì sao (chưa đủ đêm trùng), không nói "chưa có PMS". */
function Calibration({ calibration, hasPms }: { calibration: CalibrationOut | undefined; hasPms: boolean }) {
  const t = useTranslations("calendar.fill");
  const { calibrationText, calibrationTitle } = useFillText();
  if (hasPms && !calibrationText(calibration).calibrated) {
    return (
      <span className="text-warning-deep" title={calibrationTitle(calibration)}>
        {t("noOverlap")}
      </span>
    );
  }
  return <CalibrationNote calibration={calibration} />;
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
  perHotel: MarketOccupancyOut;
  colors: Map<number, string>;
}) {
  const t = useTranslations("calendar.fill");
  const { fmtNight } = useFmt();
  const hiddenNights = nights.filter((n) => n.comp_occ !== null && fillHidden(calibration, n.days_to_arrival)).length;
  const hide = new Set(nights.filter((n) => fillHidden(calibration, n.days_to_arrival)).map((n) => n.stay_date));
  const comp = nights.map((n) => ({ d: n.stay_date, v: pct(fillIndicator(n, calibration)) })).filter((x): x is { d: string; v: number } => x.v !== null);
  const avg = comp.length ? Math.round(comp.reduce((a, b) => a + b.v, 0) / comp.length) : null;
  const peak = comp.reduce<{ d: string; v: number } | null>((m, x) => (!m || x.v > m.v ? x : m), null);
  const low = comp.reduce<{ d: string; v: number } | null>((m, x) => (!m || x.v < m.v ? x : m), null);
  const hasPms = nights.some((n) => n.own_pms_occ !== null);
  const hotels = perHotel.hotels;
  const estimated = hotels.filter((h) => h.nights.some((n) => n.occ_mid !== null));

  const note = (
    <p className="text-xs">
      <Calibration calibration={calibration} hasPms={hasPms} />
      {hiddenNights > 0 && <span className="text-muted"> · {t("hiddenNights", { count: hiddenNights })}</span>}
    </p>
  );

  // Chưa đủ khách sạn có ước tính: một câu giải thích thay cho ô số và biểu đồ gần như trống.
  if (estimated.length < MIN_HOTELS) {
    return (
      <div className="space-y-1.5">
        <p className="text-sm text-body">{t("notEnough", { count: estimated.length, total: hotels.length })}</p>
        {note}
      </div>
    );
  }

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
    // Công suất PMS: xanh thương hiệu nét đứt, không trùng màu đường khách sạn nào.
    { key: "pms", name: t("pms"), color: OWN_LINE_COLOR, width: 2, dashed: true },
  ];
  // Chú giải (và đường) chỉ gồm chuỗi có dữ liệu.
  const withData = series.filter((s) => rows.some((r) => r[s.key] !== null && r[s.key] !== undefined));

  return (
    <div>
      <p className="mb-3 text-xs text-muted">{t("source")}</p>
      <div className="mb-3">{note}</div>
      {comp.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatBox value={`≈${avg}%`} label={t("avg", { count: comp.length })} tone={DEMAND_TEXT[demandLevel(avg!)]} />
          {peak && <StatBox value={`≈${peak.v}%`} label={t("peakOn", { night: fmtNight(peak.d) })} tone="text-danger" />}
          {low && <StatBox value={`≈${low.v}%`} label={t("lowOn", { night: fmtNight(low.d) })} tone="text-yours" />}
        </div>
      )}
      <TrendChart
        className="mt-4"
        data={rows}
        series={withData}
        height={300}
        leftDomain={[0, 100]}
        formatX={(x) => fmtNight(x)}
        formatLeft={(v) => `${v}%`}
        formatValue={(v) => `${v}%`}
      />
    </div>
  );
}
