"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { cellState, type HotelRow, type OverviewOut } from "@/lib/api";
import { dateRange, num, useFmt } from "@/lib/format";
import { MARKET_LINE_COLOR, OWN_LINE_COLOR, bookablePrice, cellOn, hotelColors, medianCompRate, rowName, useMarketMetrics } from "@/lib/market-metrics";
import { HolidayDot, holidayMap } from "@/components/holiday-mark";
import { SampleTag, sampleFade, useCompsetLabels } from "@/components/compset-sample";
import { PromoDot, useMarks } from "@/components/marks";
import { Card, cx } from "@/components/ui";
import { TrendChart, type TrendRow, type TrendSeries } from "@/components/trend-chart";

/**
 * Ba cách xem giá của tab Giá & định giá: Xu hướng, Vị trí, Heatmap.
 * "Thị trường" ở đây là trung vị giá đối thủ (cùng cách tính mọi màn). Quy ước dấu "so với bạn":
 * (+) đối thủ đắt hơn bạn, (−) rẻ hơn; màu trung tính, không tô xanh cho rẻ hơn.
 */

/** Khách sạn của bạn lên đầu, đối thủ theo thứ tự watchlist; mỗi khách sạn một màu cố định. */
export function orderedRows(o: OverviewOut): Array<{ row: HotelRow; color: string; key: string }> {
  const colors = hotelColors(o);
  return [...o.hotels]
    .sort((a, b) => (a.role === "self" ? -1 : b.role === "self" ? 1 : 0))
    .map((row) => ({ row, key: `h${row.hotel.id}`, color: colors.get(row.hotel.id) ?? MARKET_LINE_COLOR }));
}

/** XU HƯỚNG GIÁ: mỗi khách sạn một đường, thị trường nét đứt, chip bật/tắt từng đường. */
export function RateTrends({ o }: { o: OverviewOut }) {
  const t = useTranslations("rates.trends");
  const { fmtMoney, fmtNight, fmtPriceShort } = useFmt();
  const hotels = orderedRows(o);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const dates = dateRange(o.start, o.end);
  const currency = o.compset.find((c) => c.currency)?.currency ?? "VND";

  const rows: TrendRow[] = dates.map((d) => {
    const row: TrendRow = { x: d, market: null };
    const med = medianCompRate(o, d);
    row.market = med === null ? null : Math.round(med);
    for (const h of hotels) row[h.key] = bookablePrice(cellOn(h.row, d));
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
    <Card title={t("title", { count: dates.length })} info={t("info")}>
      <TrendChart
        data={rows}
        series={shown}
        height={360}
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
    </Card>
  );
}

/** VỊ TRÍ GIÁ: chỉ số giá của bạn so trung vị đối thủ (=100), trung vị đối thủ so với giá bạn và hạng giá từng đêm. */
export function RatePositioning({ o }: { o: OverviewOut }) {
  const t = useTranslations("rates.positioning");
  const { fmtMoney, fmtNight } = useFmt();
  const { dayHead } = useMarketMetrics();
  const labels = useCompsetLabels();
  const self = o.hotels.find((h) => h.role === "self");
  const holidays = holidayMap(o.holidays);
  const rows: TrendRow[] = o.compset.map((c) => ({ x: c.stay_date, idx: num(c.price_index) === null ? null : Math.round(num(c.price_index)!), base: 100 }));
  return (
    <div className="space-y-4">
      <Card title={labels.index} info={labels.indexTitle}>
        <TrendChart
          data={rows}
          height={260}
          formatX={(x) => fmtNight(x)}
          formatLeft={(v) => String(v)}
          formatValue={(v) => String(v)}
          series={[
            { key: "base", name: t("base"), color: MARKET_LINE_COLOR, dashed: true },
            { key: "idx", name: labels.index, color: OWN_LINE_COLOR, width: 3 },
          ]}
          emptyText={self ? t("emptyPrices") : t("emptyOwn")}
        />
      </Card>
      <Card title={t("rankTitle")} padded={false}>
        <div className="sb-scroll overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead>
              <tr className="border-y border-line bg-subtle text-xs text-muted">
                <th className="px-5 py-2 text-left font-medium">{t("night")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("yourRate")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("compMedian")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("compLowest")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("diff")}</th>
                <th className="px-3 py-2 text-left font-medium">{labels.rankLabel}</th>
                <th className="px-5 py-2 text-left font-medium">{t("sample")}</th>
              </tr>
            </thead>
            <tbody>
              {o.compset.map((c) => {
                // Trung vị đối thủ so với giá của bạn: (+) đối thủ đắt hơn bạn, (−) rẻ hơn.
                const own = c.own_status === "sold_out" ? null : num(c.own_min_price);
                const med = num(c.median_price);
                const delta = own && med !== null ? Math.round(((med - own) / own) * 100) : null;
                const h = dayHead(c.stay_date);
                const holiday = holidays.get(c.stay_date);
                return (
                  <tr key={c.stay_date} className="border-b border-line last:border-b-0 hover:bg-subtle">
                    <td className={cx("px-5 py-2 font-medium", h.weekend ? "text-danger" : "text-ink")}>
                      {self ? (
                        <Link href={`/hotels/${self.hotel.id}/dates/${c.stay_date}`} className="hover:underline">
                          {fmtNight(c.stay_date)}
                        </Link>
                      ) : (
                        fmtNight(c.stay_date)
                      )}
                      {holiday && <span className="block text-2xs font-semibold text-ink">{holiday.name}</span>}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold text-brand tabular">{c.own_status === "sold_out" ? t("soldOut") : fmtMoney(c.own_min_price, c.currency)}</td>
                    <td className={cx("px-3 py-2 text-right tabular", sampleFade(c))}>{fmtMoney(c.median_price, c.currency)}</td>
                    <td className="px-3 py-2 text-right tabular">{fmtMoney(c.min_price, c.currency)}</td>
                    <td className={cx("px-3 py-2 text-right font-semibold tabular", delta === null ? "text-faint" : "text-ink", sampleFade(c))}>
                      {delta === null ? "—" : delta === 0 ? "0%" : delta > 0 ? `+${delta}%` : `−${-delta}%`}
                    </td>
                    <td className={cx("px-3 py-2 text-body", sampleFade(c))}>{(c.priced_hotels >= 2 && labels.rank(c.own_rank, c.priced_hotels)) || "—"}</td>
                    <td className="px-5 py-2 text-xs">
                      <SampleTag c={c} short />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="border-t border-line px-5 py-3 text-xs text-muted">{t("signLegend")}</p>
      </Card>
    </div>
  );
}

/**
 * Màu ô heatmap giá theo chênh so với trung vị đối thủ đêm đó, thang xám-xanh trung tính: càng đậm
 * càng đắt. Rẻ hơn không phải mặc nhiên là tốt nên không dùng xanh lá/cam.
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

/** HEATMAP GIÁ: khách sạn × đêm, ô màu theo giá so với trung vị đối thủ đêm đó; giá luôn có đơn vị. */
export function RateHeatmap({ o }: { o: OverviewOut }) {
  const t = useTranslations("rates.heatmap");
  const { fmtMoney, fmtPriceShort } = useFmt();
  const { dayHead } = useMarketMetrics();
  const { cellMark } = useMarks();
  const hotels = orderedRows(o);
  const dates = dateRange(o.start, o.end);
  const medians = new Map(dates.map((d) => [d, medianCompRate(o, d)]));
  const holidays = holidayMap(o.holidays);
  return (
    <Card title={t("title")} info={t("info")} padded={false}>
      <div className="sb-scroll mt-3 overflow-x-auto">
        <table className="w-full min-w-[1100px] border-collapse text-xs">
          <thead>
            <tr className="border-y border-line bg-subtle">
              <th className="sticky left-0 z-10 w-[200px] bg-subtle px-4 py-2 text-left text-sm font-medium text-muted">{t("hotel")}</th>
              {dates.map((d) => {
                const h = dayHead(d);
                const holiday = holidays.get(d);
                return (
                  <th key={d} title={holiday?.name} className={cx("px-0.5 py-2 text-center font-semibold", h.weekend ? "text-danger" : "text-muted", holiday && "bg-sunken")}>
                    <div className="text-[10px] uppercase">{h.wd}</div>
                    <div className="text-[10px] font-normal tabular">{h.date}</div>
                    <HolidayDot holiday={holiday} className="mt-0.5" />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {hotels.map(({ row, key }) => (
              <tr key={key} className={cx("border-b border-line", row.role === "self" && "bg-brand-softer")}>
                <th scope="row" className={cx("sticky left-0 z-10 max-w-[200px] truncate px-4 py-1.5 text-left text-sm font-normal", row.role === "self" ? "bg-brand-softer font-bold text-ink" : "bg-surface text-body")} title={rowName(row)}>
                  {rowName(row)}
                </th>
                {dates.map((d) => {
                  const c = cellOn(row, d);
                  const p = num(c?.min_price);
                  const state = cellState(c);
                  const mark = cellMark(c, d > o.horizon_end);
                  // Ô có giá (còn bán, hoặc hạn chế số đêm có giá) tô theo giá; trạng thái khác dùng dấu chung.
                  const priced = p !== null && (state === "available" || state === "restricted");
                  const minStay = state === "restricted" && c && (c.min_stay ?? 1) > 1 ? (c.min_stay ?? null) : null;
                  const title = priced ? [fmtMoney(p, c?.currency), mark.kind !== "exact" && mark.kind !== "hidden" ? mark.label : null, mark.promo && !mark.label.includes(mark.promo) ? mark.promo : null].filter(Boolean).join(" · ") : mark.label;
                  return (
                    <td key={d} className="px-[2px] py-1">
                      <Link
                        href={`/hotels/${row.hotel.id}/dates/${d}`}
                        title={c?.stale && priced ? `${title} · ${mark.label}` : title}
                        className={cx(
                          "sb-cell relative grid h-7 place-items-center rounded-[4px] font-semibold tabular",
                          priced ? priceTone(p, medians.get(d) ?? null) : cx(mark.cls, "text-[9px] font-bold"),
                          priced && minStay !== null && "ring-2 ring-inset ring-[#fcd34d]",
                          priced && c?.stale && "sb-stale",
                        )}
                      >
                        {priced ? fmtPriceShort(p, c?.currency) : state === "sold_out" ? t("soldOutShort") : mark.text}
                        {minStay !== null && <span className="absolute -top-1 left-0.5 rounded-sm bg-warning-soft px-0.5 text-[8px] font-bold leading-[10px] text-warning-deep">{t("minStayShort", { count: minStay })}</span>}
                        <PromoDot promo={mark.promo} />
                      </Link>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-3 text-xs text-muted">{t("note")}</p>
    </Card>
  );
}
