"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Fragment } from "react";
import { cellState, type CalibrationOut, type DateCell, type HotelRow, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { num, useFmt, type Fmt } from "@/lib/format";
import { roomsLeftOf } from "@/lib/rooms-left";
import { useLabel } from "@/lib/labels";
import { DEMAND_TEXT, demandLevel, fillReading, rowName } from "@/lib/market-metrics";
import { useFillText } from "@/components/fill";
import { HEAT_LEVELS, MarkSwatch, PromoDot, isWordMark, useMarks, type Mark } from "@/components/marks";
import { cx } from "@/components/ui";
import { NightHeadCells, STICKY_COL, colBg, type NightCol } from "./grid-parts";

/**
 * Lưới "Phòng còn" kiểu OTARadar: khách sạn × đêm, ô màu theo số phòng còn (đỏ hết → xanh nhiều),
 * mũi tên là thay đổi trong 24 giờ (▼ phòng còn giảm, ▲ tăng). Khách sạn của bạn ở trên cùng, ngay
 * dưới là hàng "Công suất của bạn (PMS)" khi đã nhập PMS. Cột và dòng tổng là "còn ít nhất", dòng
 * chỉ báo lấp đầy ≈ ẩn khi không đêm nào có số. Ô cũ hơn 48 giờ giữ màu, có sọc ở góc (`sb-stale`).
 */

type RoomsTranslator = ReturnType<typeof useTranslations<"calendar.rooms">>;

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
 * Tổng số phòng còn của một nhóm ô. Ô hết phòng góp 0; ô "≥N"/"N–M" góp N (phần chắc chắn); ô không
 * lộ số, không đọc được hoặc chưa quét là "thiếu số". Nhãn dòng/cột đã ghi "ít nhất" nên số không
 * kèm "≥"; không ô nào có số thì "—".
 */
type Sum = { value: number; known: number; missing: number; inexact: number };

function sumCells(cells: Array<DateCell | undefined>): Sum {
  const out: Sum = { value: 0, known: 0, missing: 0, inexact: 0 };
  for (const c of cells) {
    if (cellState(c) === "sold_out") {
      out.known += 1;
      continue;
    }
    const r = roomsLeftOf(c);
    if (r === null) {
      out.missing += 1;
      continue;
    }
    out.value += r.min;
    out.known += 1;
    if (r.exact === null) out.inexact += 1;
  }
  return out;
}

function fmtSum(s: Sum, fmtInt: Fmt["fmtInt"]): string {
  return s.known === 0 ? "—" : fmtInt(s.value);
}

function sumTitle(s: Sum, t: RoomsTranslator): string {
  return s.missing + s.inexact > 0 ? t("sumPartial", { known: s.known - s.inexact, missing: s.missing + s.inexact }) : t("sumFull", { known: s.known });
}

/** Màu chữ chỉ báo lấp đầy theo thang mức chung (lib/market-metrics.ts: cao ≥ 75, vừa ≥ 50). */
function occTone(pct: number): string {
  return DEMAND_TEXT[demandLevel(pct)];
}

function pctOf(v: string | null | undefined): number | null {
  const n = num(v);
  return n === null ? null : Math.round(n * 100);
}

export function RoomsGrid({
  data,
  cols,
  nights,
  calibration,
  pmsHotelId,
}: {
  data: OverviewOut;
  cols: NightCol[];
  nights: PaceNightOut[];
  calibration: CalibrationOut | undefined;
  /** Khách sạn của bạn mà số PMS trong `nights` thuộc về. */
  pmsHotelId: number | null;
}) {
  const t = useTranslations("calendar.rooms");
  const th = useTranslations("calendar.head");
  const { fmtInt } = useFmt();
  const { cellMark } = useMarks();
  const { fillText, hiddenText } = useFillText();
  const dates = cols.map((c) => c.date);
  const rows: HotelRow[] = [...data.hotels].sort((a, b) => (a.role === "self" ? -1 : b.role === "self" ? 1 : 0));
  const byNight = new Map(nights.map((n) => [n.stay_date, n]));

  const cellAt = (r: HotelRow, d: string) => r.cells.find((x) => x.stay_date === d);
  const rowTotal = (r: HotelRow) => sumCells(dates.map((d) => cellAt(r, d)));
  const marketTotal = (d: string) => sumCells(rows.map((r) => cellAt(r, d)));
  const grand = sumCells(rows.flatMap((r) => dates.map((d) => cellAt(r, d))));
  const readings = dates.map((d) => fillReading(byNight.get(d), calibration));
  const occs = readings.map((r) => (r.value === null ? null : Math.round(r.value * 100)));
  const known = occs.filter((v): v is number => v !== null);
  const avgOcc = known.length ? Math.round(known.reduce((a, b) => a + b, 0) / known.length) : null;
  const showOcc = known.length > 0 || readings.some((r) => r.hidden);
  // Công suất PMS thật của khách sạn bạn (khi đã nhập), cùng đêm với lưới.
  const pms = dates.map((d) => pctOf(byNight.get(d)?.own_pms_occ));
  const pmsKnown = pms.filter((v): v is number => v !== null);
  const pmsAvg = pmsKnown.length ? Math.round(pmsKnown.reduce((a, b) => a + b, 0) / pmsKnown.length) : null;
  const pmsRow = pmsHotelId !== null && pmsKnown.length > 0 ? pmsHotelId : null;

  return (
    <div className="sb-scroll overflow-x-auto">
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className={cx(STICKY_COL, "bg-subtle px-3 py-2 text-left text-sm font-medium text-muted sm:px-4")}>
              {th("hotel")}
            </th>
            <NightHeadCells cols={cols} />
            <th scope="col" title={t("roomNightsTitle", { count: dates.length })} className="border-l border-line bg-subtle px-3 py-2 text-center text-xs font-medium text-muted">
              <span className="block whitespace-nowrap">{t("roomNights", { count: dates.length })}</span>
              <span className="block font-normal">{t("roomNightsSub")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const self = r.role === "self";
            return (
              <Fragment key={r.hotel.id}>
              <tr className={cx("border-b border-line", self && "bg-brand-softer")}>
                <th scope="row" className={cx(STICKY_COL, "px-3 py-1.5 text-left font-normal sm:px-4", self ? "bg-brand-softer" : "bg-surface")}>
                  <Link href={`/hotels/${r.hotel.id}`} className={cx("flex items-center gap-1.5 hover:text-brand", self ? "font-bold text-ink" : "text-body")} title={rowName(r)}>
                    {self && <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />}
                    <span className="truncate">{rowName(r)}</span>
                  </Link>
                </th>
                {cols.map((col) => {
                  const c = cellAt(r, col.date);
                  const v = cellMark(c, col.date > data.horizon_end);
                  return (
                    <td key={col.date} className={cx("px-[3px] py-1.5", colBg(col))}>
                      <Link
                        href={`/hotels/${r.hotel.id}/dates/${col.date}`}
                        title={t("cellTitle", { hotel: rowName(r), weekday: col.wd, date: col.label, status: v.label })}
                        aria-label={t("cellAria", { hotel: rowName(r), date: col.label, status: v.label })}
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
              {r.hotel.id === pmsRow && (
                <tr className="border-b border-line bg-brand-softer/50">
                  <th scope="row" title={t("pmsTitle")} className={cx(STICKY_COL, "bg-brand-softer px-3 py-1.5 text-left text-xs font-semibold text-brand sm:px-4")}>
                    <span className="block leading-tight">{t("pms")}</span>
                  </th>
                  {cols.map((col, i) => (
                    <td key={col.date} title={t("pmsTitle")} className={cx("px-1 py-1.5 text-center text-xs font-semibold text-ink tabular", colBg(col))}>
                      {pms[i] === null ? <span className="text-faint">—</span> : `${pms[i]}%`}
                    </td>
                  ))}
                  <td className="border-l border-line px-3 py-1.5 text-center text-xs font-bold text-ink tabular">{pmsAvg === null ? "—" : `${pmsAvg}%`}</td>
                </tr>
              )}
              </Fragment>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-b border-line bg-subtle">
            <th scope="row" title={t("marketTotalTitle")} className={cx(STICKY_COL, "bg-subtle px-3 py-2.5 text-left text-xs font-bold text-ink sm:px-4")}>
              {t("marketTotal")}
            </th>
            {cols.map((col) => {
              const total = marketTotal(col.date);
              return (
                <td key={col.date} title={sumTitle(total, t)} className={cx("px-1 py-2.5 text-center font-bold text-ink tabular", colBg(col))}>
                  {fmtSum(total, fmtInt)}
                </td>
              );
            })}
            <td title={sumTitle(grand, t)} className="border-l border-line px-3 py-2.5 text-center font-bold text-brand tabular">
              {fmtSum(grand, fmtInt)}
            </td>
          </tr>
          {showOcc && (
            <tr className="bg-subtle">
              <th scope="row" className={cx(STICKY_COL, "bg-subtle px-3 py-2 text-left text-sm font-medium text-muted sm:px-4")} title={t("occTitle")}>
                {t("occ")}
              </th>
              {occs.map((v, i) => (
                <td
                  key={dates[i]}
                  title={readings[i].hidden ? hiddenText(readings[i]) : (fillText(readings[i]) ?? undefined)}
                  className={cx("px-1 py-2 text-center text-xs font-semibold tabular", colBg(cols[i]), v === null ? "text-faint" : occTone(v))}
                >
                  {readings[i].hidden ? t("occHidden") : v === null ? "—" : `${v}%`}
                </td>
              ))}
              <td className={cx("border-l border-line px-3 py-2 text-center text-xs font-bold tabular", avgOcc === null ? "text-faint" : occTone(avgOcc))}>{avgOcc === null ? "—" : `${avgOcc}%`}</td>
            </tr>
          )}
        </tfoot>
      </table>
    </div>
  );
}

const SWATCH = "h-3 w-3 shrink-0 rounded-[3px]";

/** Ô mẫu cho chú giải chi tiết (chữ trong ô điền lúc render). */
const DETAIL_MARKS: Array<{ mark: Mark; key: "hotelFloor" | "restricted" | "noPrice" | "error" | "stale" | "notScanned" }> = [
  { mark: { kind: "capped", cls: "sb-mark-capped", text: "≥", label: "" }, key: "hotelFloor" },
  { mark: { kind: "restricted", cls: "sb-mark-restricted", text: "", label: "" }, key: "restricted" },
  { mark: { kind: "no_price", cls: "sb-mark-no_price", text: "–", label: "" }, key: "noPrice" },
  { mark: { kind: "error", cls: "sb-mark-error", text: "", label: "" }, key: "error" },
  { mark: { kind: "exact", cls: "sb-heat-4 sb-stale", text: "9", label: "" }, key: "stale" },
  { mark: { kind: "nodata", cls: "sb-mark-nodata", text: "", label: "" }, key: "notScanned" },
];

/**
 * Chú giải chính chỉ 5 mục (Hết · Rất ít · Ít · Còn nhiều · Còn, không lộ số); phần còn lại (thang
 * đủ 6 mức, "ít nhất N", hạn chế, không giá, lỗi, số cũ, khuyến mãi, ngày lễ, mũi tên, chấm gợi ý)
 * nằm trong "Cách đọc ô".
 */
export function HeatLegend({ className }: { className?: string }) {
  const t = useTranslations("calendar.legend");
  const tm = useTranslations("components.marks");
  const label = useLabel();
  const filled = (m: Mark): Mark => (m.kind === "restricted" ? { ...m, text: tm("minStayShort", { count: 2 }) } : m.kind === "error" ? { ...m, text: tm("errorShort") } : m);
  return (
    <div className={cx("flex flex-wrap items-start gap-x-6 gap-y-2 text-xs text-muted", className)}>
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <li className="font-medium">{t("title")}</li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className={cx(SWATCH, "sb-heat-0")} />
          {t("soldOut")}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className={cx(SWATCH, "sb-heat-1")} />
          {t("veryFew")}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className={cx(SWATCH, "sb-heat-2")} />
          {t("few")}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="flex h-3 w-6 shrink-0 overflow-hidden rounded-[3px]">
            <span className="sb-heat-3 flex-1" />
            <span className="sb-heat-4 flex-1" />
            <span className="sb-heat-5 flex-1" />
          </span>
          {t("plenty")}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className={cx(SWATCH, "sb-mark-hidden")} />
          {t("hidden")}
        </li>
      </ul>
      <details className="group min-w-0">
        <summary className="cursor-pointer list-none font-semibold text-brand hover:underline [&::-webkit-details-marker]:hidden">{t("howToRead")}</summary>
        <ul className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {HEAT_LEVELS.map((h) => (
            <li key={h.cls} className="flex items-center gap-1.5">
              <span aria-hidden className={cx(SWATCH, h.cls)} />
              {label("heatLevel", h.key)}
            </li>
          ))}
        </ul>
        <ul className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {DETAIL_MARKS.map((it) => (
            <li key={it.key} className="flex items-center gap-1.5">
              <MarkSwatch mark={filled(it.mark)} size={16} />
              {tm(`legend.${it.key}`)}
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#db2777]" />
            {tm("legend.promo")}
          </li>
          <li>{t("trend")}</li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-ink" />
            {t("holiday")}
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#7c3aed]" />
            {t("pending")}
          </li>
        </ul>
      </details>
    </div>
  );
}
