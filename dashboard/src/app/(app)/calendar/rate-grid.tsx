"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { cellState, type DateCell, type HotelRow, type OverviewOut } from "@/lib/api";
import { dateRange, num, useFmt } from "@/lib/format";
import { MARKET_LINE_COLOR, cellOn, compsetDay, hotelColors, lastPrice, medianCompRate, rowName, selfRow } from "@/lib/market-metrics";
import { PromoDot, useMarks } from "@/components/marks";
import { cx } from "@/components/ui";
import { TrendChart, type TrendRow, type TrendSeries } from "@/components/trend-chart";
import { NightHeadCells, STICKY_COL, colBg, type NightCol } from "./grid-parts";

/**
 * Lưới giá của Lịch giá & phòng, hai cách xem trên cùng một lưới khách sạn × đêm:
 * - "Giá": giá niêm yết thấp nhất, luôn có đơn vị; ô càng đậm càng đắt so với giá giữa của đối thủ.
 * - "Chênh với bạn": giá đối thủ so với giá của bạn cùng đêm (%), đỏ khi đối thủ rẻ hơn bạn từ 10%.
 * Quy ước dấu: (+) đối thủ đắt hơn bạn, (−) rẻ hơn. Giá cũ hơn 48 giờ vẫn hiện (sọc ở góc), nhưng
 * giá giữa của đối thủ chỉ tính trên số ≤48 giờ (backend).
 */

export type RateMode = "rates" | "gap";

/** Đối thủ rẻ hơn bạn từ mức này (%) thì tô đỏ. */
const UNDERCUT_PCT = -10;

/** Khách sạn của bạn lên đầu, đối thủ theo thứ tự watchlist; mỗi khách sạn một màu cố định. */
function orderedRows(o: OverviewOut): Array<{ row: HotelRow; color: string; key: string }> {
  const colors = hotelColors(o);
  return [...o.hotels]
    .sort((a, b) => (a.role === "self" ? -1 : b.role === "self" ? 1 : 0))
    .map((row) => ({ row, key: `h${row.hotel.id}`, color: colors.get(row.hotel.id) ?? MARKET_LINE_COLOR }));
}

/** "+8%" / "−12%" / "0%" với dấu trừ thật. */
function signedPct(v: number): string {
  return v > 0 ? `+${v}%` : v < 0 ? `−${-v}%` : "0%";
}

/** Chênh % của `price` so với `base`, làm tròn. */
function diffPct(price: number, base: number): number {
  return Math.round(((price - base) / base) * 100);
}

/**
 * Màu ô giá theo chênh so với giá giữa của đối thủ đêm đó, thang xám-xanh trung tính: càng đậm càng
 * đắt. Rẻ hơn không mặc nhiên là tốt nên không dùng xanh lá/cam.
 */
function priceTone(price: number, med: number | null): string {
  if (med === null || med === 0) return "bg-sunken text-body";
  const d = (price - med) / med;
  if (d <= -0.15) return "bg-[#f1f5f9] text-[#334155]";
  if (d <= -0.05) return "bg-[#e2e8f0] text-[#1e293b]";
  if (d < 0.05) return "bg-[#cbd5e1] text-[#0f172a]";
  if (d < 0.15) return "bg-[#94a3b8] text-[#0f172a]";
  return "bg-[#475569] text-white";
}

const CELL = "sb-cell relative grid h-7 place-items-center rounded-[4px] font-semibold tabular";

export function RateGrid({ o, cols, mode }: { o: OverviewOut; cols: NightCol[]; mode: RateMode }) {
  const t = useTranslations("calendar.rates");
  const tg = useTranslations("calendar.gap");
  const th = useTranslations("calendar.head");
  const { fmtMoney, fmtPriceShort } = useFmt();
  const { cellMark } = useMarks();
  const hotels = orderedRows(o);
  const self = selfRow(o);
  const medians = new Map(cols.map((c) => [c.date, medianCompRate(o, c.date)]));
  const gap = mode === "gap";

  /** Ô không có giá đem so (hết, hạn chế không giá, chưa quét…): dùng dấu chung của ô. */
  function markCell(c: DateCell | undefined, d: string) {
    const mark = cellMark(c, d > o.horizon_end);
    return { mark, text: cellState(c) === "sold_out" ? t("soldOutShort") : mark.text, cls: cx(mark.cls, "text-[9px] font-bold") };
  }

  function rateCell(row: HotelRow, col: NightCol) {
    const d = col.date;
    const c = cellOn(row, d);
    const p = num(c?.min_price);
    const state = cellState(c);
    const mark = cellMark(c, d > o.horizon_end);
    // Ô có giá (còn bán, hoặc hạn chế số đêm có giá) tô theo giá; trạng thái khác dùng dấu chung.
    const priced = p !== null && (state === "available" || state === "restricted");
    const minStay = state === "restricted" && c && (c.min_stay ?? 1) > 1 ? (c.min_stay ?? null) : null;
    const title = priced
      ? [fmtMoney(p, c?.currency), mark.kind !== "exact" && mark.kind !== "hidden" ? mark.label : null, mark.promo && !mark.label.includes(mark.promo) ? mark.promo : null].filter(Boolean).join(" · ")
      : mark.label;
    const fallback = markCell(c, d);
    return (
      <Link
        href={`/hotels/${row.hotel.id}/dates/${d}`}
        title={c?.stale && priced ? `${title} · ${mark.label}` : title}
        className={cx(CELL, priced ? priceTone(p, medians.get(d) ?? null) : fallback.cls, priced && minStay !== null && "ring-2 ring-inset ring-[#fcd34d]", priced && c?.stale && "sb-stale")}
      >
        {priced ? fmtPriceShort(p, c?.currency) : fallback.text}
        {minStay !== null && <span className="absolute -top-1 left-0.5 rounded-sm bg-warning-soft px-0.5 text-[8px] font-bold leading-[10px] text-warning-deep">{t("minStayShort", { count: minStay })}</span>}
        <PromoDot promo={mark.promo} />
      </Link>
    );
  }

  /** Ô "Chênh với bạn": đối thủ so với giá của bạn cùng đêm; hàng của bạn ghi giá của bạn. */
  function gapCell(row: HotelRow, col: NightCol) {
    const d = col.date;
    const c = cellOn(row, d);
    const href = `/hotels/${row.hotel.id}/dates/${d}`;
    if (row.role === "self") return rateCell(row, col);
    const comp = lastPrice(c);
    if (comp === null) {
      const f = markCell(c, d);
      return (
        <Link href={href} title={f.mark.label} className={cx(CELL, f.cls)}>
          {f.text}
        </Link>
      );
    }
    const ownCell = cellOn(self, d);
    const own = lastPrice(ownCell);
    const stale = comp.stale || !!own?.stale;
    if (own === null) {
      return (
        <Link href={href} title={`${fmtMoney(comp.value, c?.currency)} · ${tg("noOwnPrice")}`} className={cx(CELL, "bg-subtle text-muted", stale && "sb-stale")}>
          {fmtPriceShort(comp.value, c?.currency)}
        </Link>
      );
    }
    const diff = diffPct(comp.value, own.value);
    const title = tg("cellTitle", { hotel: rowName(row), price: fmtMoney(comp.value, c?.currency), diff: signedPct(diff), own: fmtMoney(own.value, ownCell?.currency) });
    return (
      <Link href={href} title={stale ? `${title} · ${cellMark(c).label}` : title} className={cx(CELL, diff <= UNDERCUT_PCT ? "bg-danger-soft font-bold text-danger-deep" : "bg-subtle text-ink", stale && "sb-stale")}>
        {signedPct(diff)}
      </Link>
    );
  }

  // Cùng giá của bạn như hàng của bạn (giá cuối đọc được); giá giữa thì backend chỉ tính số ≤48 giờ.
  const ownOn = (d: string) => lastPrice(cellOn(self, d))?.value ?? null;

  return (
    <div className="sb-scroll overflow-x-auto">
      <table className="w-full min-w-max border-collapse text-xs">
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className={cx(STICKY_COL, "bg-subtle px-3 py-2 text-left text-sm font-medium text-muted sm:px-4")}>
              {th("hotel")}
            </th>
            <NightHeadCells cols={cols} />
          </tr>
        </thead>
        <tbody>
          {hotels.map(({ row, key }) => (
            <tr key={key} className={cx("border-b border-line", row.role === "self" && "bg-brand-softer")}>
              <th scope="row" className={cx(STICKY_COL, "px-3 py-1.5 text-left text-sm font-normal sm:px-4", row.role === "self" ? "bg-brand-softer font-bold text-ink" : "bg-surface text-body")}>
                <Link href={`/hotels/${row.hotel.id}`} className="flex items-center gap-1.5 hover:text-brand" title={rowName(row)}>
                  {row.role === "self" && <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />}
                  <span className="truncate">{rowName(row)}</span>
                </Link>
              </th>
              {cols.map((col) => (
                <td key={col.date} className={cx("px-[2px] py-1", colBg(col))}>
                  {gap ? gapCell(row, col) : rateCell(row, col)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-b border-line bg-subtle">
            <th scope="row" className={cx(STICKY_COL, "bg-subtle px-3 py-2 text-left text-xs font-bold text-ink sm:px-4")}>
              <span className="block truncate" title={t("median")}>
                {t("median")}
              </span>
            </th>
            {cols.map((col) => {
              const cs = compsetDay(o, col.date);
              const med = medians.get(col.date) ?? null;
              const own = ownOn(col.date);
              const title = cs ? t("medianTitle", { priced: cs.competitors_priced, total: cs.competitors_total }) : undefined;
              return (
                <td key={col.date} title={title} className={cx("px-1 py-2 text-center font-semibold text-ink tabular", colBg(col))}>
                  {med === null ? <span className="text-faint">—</span> : gap && own !== null ? signedPct(diffPct(med, own)) : fmtPriceShort(med, cs?.currency)}
                </td>
              );
            })}
          </tr>
          {gap && (
            <tr className="bg-subtle">
              <th scope="row" title={tg("rankTitle")} className={cx(STICKY_COL, "bg-subtle px-3 py-2 text-left text-xs font-medium text-muted sm:px-4")}>
                <span className="block truncate">{tg("rank")}</span>
              </th>
              {cols.map((col) => {
                const cs = compsetDay(o, col.date);
                const ok = cs && cs.own_rank && cs.priced_hotels >= 2;
                return (
                  <td key={col.date} title={tg("rankTitle")} className={cx("px-1 py-2 text-center font-semibold tabular", ok ? "text-brand" : "text-faint", colBg(col))}>
                    {ok ? `${cs.own_rank}/${cs.priced_hotels}` : "—"}
                  </td>
                );
              })}
            </tr>
          )}
        </tfoot>
      </table>
    </div>
  );
}

/** XU HƯỚNG GIÁ: mỗi khách sạn một đường, giá giữa của đối thủ nét đứt, chip bật/tắt từng đường. */
export function RateTrends({ o }: { o: OverviewOut }) {
  const t = useTranslations("calendar.trends");
  const { fmtMoney, fmtNight, fmtPriceShort } = useFmt();
  const hotels = orderedRows(o);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const dates = dateRange(o.start, o.end);
  const currency = o.compset.find((c) => c.currency)?.currency ?? "VND";

  const rows: TrendRow[] = dates.map((d) => {
    const row: TrendRow = { x: d, market: null };
    const med = medianCompRate(o, d);
    row.market = med === null ? null : Math.round(med);
    // Giá cuối đọc được (kể cả cũ hơn 48 giờ), cùng số với lưới; giá giữa thì chỉ tính số mới.
    for (const h of hotels) row[h.key] = lastPrice(cellOn(h.row, d))?.value ?? null;
    return row;
  });
  const all: TrendSeries[] = [
    { key: "market", name: t("market"), color: MARKET_LINE_COLOR, dashed: true, width: 2.4 },
    ...hotels.map((h) => ({ key: h.key, name: rowName(h.row), color: h.color, width: h.row.role === "self" ? 3 : 1.6 })),
  ];
  const shown = all.filter((s) => !hidden.has(s.key));
  const toggle = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div>
      <p className="mb-3 text-xs text-muted">{t("info")}</p>
      <TrendChart
        data={rows}
        series={shown}
        height={340}
        legend={false}
        formatX={(x) => fmtNight(x)}
        formatLeft={(v) => fmtPriceShort(v, currency)}
        formatValue={(v) => fmtMoney(v, currency)}
        emptyText={t("empty")}
      />
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setHidden(new Set())} className={cx("h-7 rounded-md px-3 text-xs font-semibold ring-1 ring-inset", hidden.size === 0 ? "bg-brand-soft text-brand ring-brand/30" : "text-body ring-line-strong hover:bg-subtle")}>
          {t("all")}
        </button>
        <button type="button" onClick={() => setHidden(new Set(all.map((s) => s.key)))} className={cx("h-7 rounded-md px-3 text-xs font-semibold ring-1 ring-inset", hidden.size === all.length ? "bg-brand-soft text-brand ring-brand/30" : "text-body ring-line-strong hover:bg-subtle")}>
          {t("none")}
        </button>
        <span aria-hidden className="mx-1 h-5 w-px bg-line" />
        {all.map((s) => {
          const off = hidden.has(s.key);
          const self = s.key !== "market" && hotels.find((h) => h.key === s.key)?.row.role === "self";
          return (
            <button
              key={s.key}
              type="button"
              aria-pressed={!off}
              onClick={() => toggle(s.key)}
              title={s.name}
              className={cx("inline-flex h-7 max-w-[200px] items-center gap-1.5 rounded-full px-3 text-xs font-semibold transition-opacity", off ? "bg-sunken text-faint" : "text-white")}
              style={off ? undefined : { background: s.color }}
            >
              {s.key === "market" && <span aria-hidden className="h-0.5 w-3 rounded bg-current" />}
              {self && <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />}
              <span className="truncate">{s.name}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
