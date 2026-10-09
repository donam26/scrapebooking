"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { cellState, type CalibrationOut, type DateCell, type HotelRow, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { dateRange, useFmt, type Fmt } from "@/lib/format";
import { useLabel } from "@/lib/labels";
import { DEMAND_TEXT, demandLevel, fillReading, rowName, useMarketMetrics } from "@/lib/market-metrics";
import { useFillText } from "@/components/fill";
import { HolidayDot, holidayMap } from "@/components/holiday-mark";
import { HEAT_LEVELS, PromoDot, isWordMark, useMarks } from "@/components/marks";
import { cx } from "@/components/ui";

/**
 * Heatmap phòng còn kiểu OTARadar: khách sạn × đêm, ô màu theo số phòng còn (đỏ hết → xanh nhiều),
 * mũi tên là thay đổi trong 24 giờ (▼ phòng còn giảm, ▲ tăng), cột Tổng, dòng Tổng và chỉ báo lấp đầy ≈.
 * Năm trạng thái ô (còn bán / hết / hạn chế — hổ phách, không đỏ / không giá / lỗi), ô cũ hơn 48 giờ
 * làm xám, chấm hồng khi đang khuyến mãi. Đầu cột có chấm ngày lễ.
 */

type HeatmapTranslator = ReturnType<typeof useTranslations<"availability.heatmap">>;

/** Mũi tên thay đổi 24 giờ: pickup > 0 là số phòng còn giảm. */
function Trend({ pickup }: { pickup: number | null }) {
  if (pickup === null || pickup === 0) return null;
  return (
    <span aria-hidden className="block text-[8px] leading-[8px] opacity-80">
      {pickup > 0 ? "▼" : "▲"}
    </span>
  );
}

/**
 * Tổng số phòng còn của một nhóm ô. Ô hết phòng góp 0; ô còn phòng mà không lộ số, không đọc được
 * hoặc chưa quét là "thiếu số": khi có ô thiếu, tổng chỉ là mức sàn (≥N); không ô nào có số thì "—".
 */
type Sum = { value: number; known: number; missing: number };

function sumCells(cells: Array<DateCell | undefined>): Sum {
  const out: Sum = { value: 0, known: 0, missing: 0 };
  for (const c of cells) {
    if (cellState(c) === "sold_out") out.known += 1;
    else if (c?.exact_rooms_left !== null && c?.exact_rooms_left !== undefined) {
      out.value += c.exact_rooms_left;
      out.known += 1;
    } else out.missing += 1;
  }
  return out;
}

function fmtSum(s: Sum, fmtInt: Fmt["fmtInt"]): string {
  if (s.known === 0) return "—";
  return s.missing > 0 ? `≥${fmtInt(s.value)}` : fmtInt(s.value);
}

function sumTitle(s: Sum, t: HeatmapTranslator): string {
  return s.missing > 0 ? t("sumPartial", { known: s.known, missing: s.missing }) : t("sumFull", { known: s.known });
}

/** Màu chữ chỉ báo lấp đầy theo thang mức chung (lib/market-metrics.ts: cao ≥ 75, vừa ≥ 50). */
function occTone(pct: number): string {
  return DEMAND_TEXT[demandLevel(pct)];
}

export function HeatmapTable({ data, nights, calibration, today }: { data: OverviewOut; nights: PaceNightOut[]; calibration: CalibrationOut | undefined; today: string }) {
  const t = useTranslations("availability.heatmap");
  const { fmtInt } = useFmt();
  const { dayHead } = useMarketMetrics();
  const { cellMark } = useMarks();
  const { fillText, hiddenText } = useFillText();
  const dates = dateRange(data.start, data.end);
  const rows: HotelRow[] = [...data.hotels].sort((a, b) => (a.role === "self" ? -1 : b.role === "self" ? 1 : 0));
  const byNight = new Map(nights.map((n) => [n.stay_date, n]));
  const heads = dates.map((d) => dayHead(d, today));
  const holidays = holidayMap(data.holidays);

  const cellAt = (r: HotelRow, d: string) => r.cells.find((x) => x.stay_date === d);
  const rowTotal = (r: HotelRow) => sumCells(dates.map((d) => cellAt(r, d)));
  const marketTotal = (d: string) => sumCells(rows.map((r) => cellAt(r, d)));
  const grand = sumCells(rows.flatMap((r) => dates.map((d) => cellAt(r, d))));
  const readings = dates.map((d) => fillReading(byNight.get(d), calibration));
  const occs = readings.map((r) => (r.value === null ? null : Math.round(r.value * 100)));
  const known = occs.filter((v): v is number => v !== null);
  const avgOcc = known.length ? Math.round(known.reduce((a, b) => a + b, 0) / known.length) : null;

  const headCls = (i: number) => cx(heads[i].isToday ? "bg-brand-soft/60" : heads[i].weekend ? "bg-danger-soft/50" : "");

  return (
    <div className="sb-scroll overflow-x-auto">
      <table className="w-full min-w-[1100px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className="sticky left-0 z-10 w-[220px] bg-subtle px-4 py-2 text-left text-sm font-medium text-muted">
              {t("hotel")}
            </th>
            {dates.map((d, i) => (
              <th key={d} scope="col" title={holidays.get(d)?.name} className={cx("px-1 py-2 text-center font-normal", headCls(i))}>
                <div className={cx("text-[11px] font-semibold uppercase", heads[i].isToday ? "text-brand" : heads[i].weekend ? "text-danger" : "text-muted")}>
                  {heads[i].isToday ? t("today") : heads[i].wd}
                </div>
                <div className={cx("text-xs tabular", heads[i].isToday ? "text-brand" : heads[i].weekend ? "text-danger" : "text-muted")}>{heads[i].date}</div>
                <HolidayDot holiday={holidays.get(d)} className="mt-0.5" />
              </th>
            ))}
            <th scope="col" title={t("roomNightsTitle", { count: dates.length })} className="border-l border-line bg-subtle px-3 py-2 text-center text-sm font-medium text-muted">
              {t("roomNights")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const self = r.role === "self";
            return (
              <tr key={r.hotel.id} className={cx("border-b border-line", self && "bg-brand-softer")}>
                <th scope="row" className={cx("sticky left-0 z-10 max-w-[220px] px-4 py-1.5 text-left font-normal", self ? "bg-brand-softer" : "bg-surface")}>
                  <Link href={`/hotels/${r.hotel.id}`} className={cx("flex items-center gap-1.5 truncate hover:text-brand", self ? "font-bold text-ink" : "text-body")} title={rowName(r)}>
                    {self && <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />}
                    <span className="truncate">{rowName(r)}</span>
                  </Link>
                </th>
                {dates.map((d, i) => {
                  const c = r.cells.find((x) => x.stay_date === d);
                  const v = cellMark(c, d > data.horizon_end);
                  return (
                    <td key={d} className={cx("px-[3px] py-1.5", headCls(i))}>
                      <Link
                        href={`/hotels/${r.hotel.id}/dates/${d}`}
                        title={t("cellTitle", { hotel: rowName(r), weekday: heads[i].wd, date: heads[i].date, status: v.label })}
                        aria-label={t("cellAria", { hotel: rowName(r), date: heads[i].date, status: v.label })}
                        className={cx(
                          "sb-cell relative flex h-[30px] flex-col items-center justify-center rounded-[4px] font-bold leading-none tabular",
                          isWordMark(v.kind) ? "text-[9px] tracking-[0.02em]" : "text-[13px]",
                          v.cls,
                        )}
                      >
                        {v.text}
                        <Trend pickup={c?.pickup_24h ?? null} />
                        <PromoDot promo={v.promo} />
                      </Link>
                    </td>
                  );
                })}
                <td title={sumTitle(rowTotal(r), t)} className="border-l border-line px-3 py-1.5 text-center font-bold text-ink tabular">
                  {fmtSum(rowTotal(r), fmtInt)}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-b border-line bg-subtle">
            <th scope="row" title={t("marketTotalTitle")} className="sticky left-0 z-10 bg-subtle px-4 py-2.5 text-left text-xs font-bold uppercase tracking-[0.05em] text-ink">
              {t("marketTotal")}
            </th>
            {dates.map((d, i) => {
              const total = marketTotal(d);
              return (
                <td key={d} title={sumTitle(total, t)} className={cx("px-1 py-2.5 text-center font-bold text-ink tabular", headCls(i))}>
                  {fmtSum(total, fmtInt)}
                </td>
              );
            })}
            <td title={sumTitle(grand, t)} className="border-l border-line px-3 py-2.5 text-center font-bold text-brand tabular">
              {fmtSum(grand, fmtInt)}
            </td>
          </tr>
          <tr className="bg-subtle">
            <th scope="row" className="sticky left-0 z-10 bg-subtle px-4 py-2 text-left text-sm font-medium text-muted" title={t("occTitle")}>
              {t("occ")}
            </th>
            {occs.map((v, i) => (
              <td
                key={dates[i]}
                title={readings[i].hidden ? hiddenText(readings[i]) : (fillText(readings[i]) ?? undefined)}
                className={cx("px-1 py-2 text-center text-xs font-semibold tabular", headCls(i), v === null ? "text-faint" : occTone(v))}
              >
                {readings[i].hidden ? t("occHidden") : v === null ? "—" : `${v}%`}
              </td>
            ))}
            <td className={cx("border-l border-line px-3 py-2 text-center text-xs font-bold tabular", avgOcc === null ? "text-faint" : occTone(avgOcc))}>{avgOcc === null ? "—" : `${avgOcc}%`}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

export function HeatLegend({ className }: { className?: string }) {
  const t = useTranslations("availability.legend");
  const tm = useTranslations("components.marks.legend");
  const label = useLabel();
  return (
    <ul className={cx("flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted", className)}>
      <li className="font-medium">{t("title")}</li>
      {HEAT_LEVELS.map((h) => (
        <li key={h.cls} className="flex items-center gap-1.5">
          <span aria-hidden className={cx("h-3 w-3 rounded-[3px]", h.cls)} />
          {label("heatLevel", h.key)}
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="sb-mark-hidden h-3 w-3 rounded-[3px]" />
        {t("hidden")}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="sb-mark-restricted h-3 w-3 rounded-[3px]" />
        {tm("restricted")}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="sb-mark-no_price h-3 w-3 rounded-[3px]" />
        {tm("noPrice")}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="sb-mark-error h-3 w-3 rounded-[3px]" />
        {tm("error")}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="sb-heat-4 sb-stale h-3 w-3 rounded-[3px]" />
        {tm("stale")}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#db2777]" />
        {tm("promo")}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="sb-mark-nodata h-3 w-3 rounded-[3px]" />
        {t("notScanned")}
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-ink" />
        {t("holiday")}
      </li>
      <li>{t("trend")}</li>
    </ul>
  );
}
