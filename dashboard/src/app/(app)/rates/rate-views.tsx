"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import type { HotelRow, OverviewOut } from "@/lib/api";
import { dateRange, num, useFmt } from "@/lib/format";
import { withChannel } from "@/lib/channels";
import { useNightReason } from "@/lib/night-reason";
import { MARKET_LINE_COLOR, OWN_LINE_COLOR, avgCompRate, hotelColors, bookablePrice, cellOn, rowName, useMarketMetrics } from "@/lib/market-metrics";
import { Card, cx } from "@/components/ui";
import { TrendChart, type TrendRow, type TrendSeries } from "@/components/trend-chart";

/** Ba cách xem giá của tab Giá & định giá: Xu hướng, Vị trí, Heatmap. */

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
  const { fmtCompact, fmtMoney, fmtNight } = useFmt();
  const hotels = orderedRows(o);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const dates = dateRange(o.start, o.end);
  const currency = o.compset.find((c) => c.currency)?.currency ?? "VND";

  const rows: TrendRow[] = dates.map((d) => {
    const row: TrendRow = { x: d, market: null };
    const avg = avgCompRate(o, d);
    row.market = avg === null ? null : Math.round(avg);
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
        formatLeft={(v) => fmtCompact(v)}
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

/** VỊ TRÍ GIÁ: chỉ số giá của bạn so trung vị đối thủ (=100) và hạng giá từng đêm. */
export function RatePositioning({ o, channelParam }: { o: OverviewOut; channelParam: string | null }) {
  const t = useTranslations("rates.positioning");
  const { fmtMoney, fmtNight } = useFmt();
  const { dayHead } = useMarketMetrics();
  const { fmtRank } = useNightReason();
  const self = o.hotels.find((h) => h.role === "self");
  const rows: TrendRow[] = o.compset.map((c) => ({ x: c.stay_date, idx: num(c.price_index) === null ? null : Math.round(num(c.price_index)!), base: 100 }));
  return (
    <div className="space-y-4">
      <Card title={t("indexTitle")} info={t("indexInfo")}>
        <TrendChart
          data={rows}
          height={260}
          formatX={(x) => fmtNight(x)}
          formatLeft={(v) => String(v)}
          formatValue={(v) => String(v)}
          series={[
            { key: "base", name: t("base"), color: MARKET_LINE_COLOR, dashed: true },
            { key: "idx", name: t("index"), color: OWN_LINE_COLOR, width: 3 },
          ]}
          emptyText={self ? t("emptyPrices") : t("emptyOwn")}
        />
      </Card>
      <Card title={t("rankTitle")} padded={false}>
        <div className="sb-scroll overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-y border-line bg-subtle text-xs text-muted">
                <th className="px-5 py-2 text-left font-medium">{t("night")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("yourRate")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("compMedian")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("compLowest")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("diff")}</th>
                <th className="px-5 py-2 text-left font-medium">{t("rank")}</th>
              </tr>
            </thead>
            <tbody>
              {o.compset.map((c) => {
                const idx = num(c.price_index);
                const delta = idx === null ? null : Math.round(idx - 100);
                const h = dayHead(c.stay_date);
                return (
                  <tr key={c.stay_date} className="border-b border-line last:border-b-0 hover:bg-subtle">
                    <td className={cx("px-5 py-2 font-medium", h.weekend ? "text-danger" : "text-ink")}>
                      {self ? (
                        <Link href={withChannel(`/hotels/${self.hotel.id}/dates/${c.stay_date}`, channelParam)} className="hover:underline">
                          {fmtNight(c.stay_date)}
                        </Link>
                      ) : (
                        fmtNight(c.stay_date)
                      )}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold text-brand tabular">{c.own_status === "sold_out" ? t("soldOut") : fmtMoney(c.own_min_price, c.currency)}</td>
                    <td className="px-3 py-2 text-right tabular">{fmtMoney(c.median_price, c.currency)}</td>
                    <td className="px-3 py-2 text-right tabular">{fmtMoney(c.min_price, c.currency)}</td>
                    <td className={cx("px-3 py-2 text-right font-semibold tabular", delta === null ? "text-faint" : delta < 0 ? "text-yours" : delta > 0 ? "text-hot" : "text-ink")}>
                      {delta === null ? "—" : delta === 0 ? "0%" : delta > 0 ? `+${delta}%` : `−${-delta}%`}
                    </td>
                    <td className="px-5 py-2 text-body">{fmtRank(c.own_rank, c.priced_hotels) ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/** Màu ô heatmap giá theo chênh so với giá TB thị trường đêm đó: rẻ hơn xanh, đắt hơn cam/đỏ. */
function priceTone(price: number, avg: number | null): string {
  if (avg === null || avg === 0) return "bg-sunken text-body";
  const d = (price - avg) / avg;
  if (d <= -0.15) return "bg-[#4ade80] text-[#14532d]";
  if (d <= -0.05) return "bg-[#bbf7d0] text-[#14532d]";
  if (d < 0.05) return "bg-[#fde68a] text-[#713f12]";
  if (d < 0.15) return "bg-[#fbbf24] text-[#422006]";
  return "bg-[#f97316] text-white";
}

/** HEATMAP GIÁ: khách sạn × đêm, ô màu theo giá rẻ/đắt so với thị trường đêm đó. */
export function RateHeatmap({ o, channelParam }: { o: OverviewOut; channelParam: string | null }) {
  const t = useTranslations("rates.heatmap");
  const { fmtCompact, fmtMoney } = useFmt();
  const { dayHead } = useMarketMetrics();
  const hotels = orderedRows(o);
  const dates = dateRange(o.start, o.end);
  const avgs = new Map(dates.map((d) => [d, avgCompRate(o, d)]));
  return (
    <Card title={t("title")} info={t("info")} padded={false}>
      <div className="sb-scroll mt-3 overflow-x-auto">
        <table className="w-full min-w-[1100px] border-collapse text-xs">
          <thead>
            <tr className="border-y border-line bg-subtle">
              <th className="sticky left-0 z-10 w-[200px] bg-subtle px-4 py-2 text-left text-sm font-medium text-muted">{t("hotel")}</th>
              {dates.map((d) => {
                const h = dayHead(d);
                return (
                  <th key={d} className={cx("px-0.5 py-2 text-center font-semibold", h.weekend ? "text-danger" : "text-muted")}>
                    <div className="text-[10px] uppercase">{h.wd}</div>
                    <div className="text-[10px] font-normal tabular">{h.date}</div>
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
                  const sold = c?.availability_status === "sold_out";
                  return (
                    <td key={d} className="px-[2px] py-1">
                      <Link
                        href={withChannel(`/hotels/${row.hotel.id}/dates/${d}`, channelParam)}
                        title={sold ? t("soldOut") : p === null ? t("noPrice") : fmtMoney(p, c?.currency)}
                        className={cx(
                          "sb-cell grid h-7 place-items-center rounded-[4px] font-semibold tabular",
                          sold ? "sb-heat-0" : p === null ? "sb-mark-nodata" : priceTone(p, avgs.get(d) ?? null),
                        )}
                      >
                        {sold ? t("soldOutShort") : p === null ? "" : fmtCompact(p).replace(/\s*(Tr|M)$/u, "")}
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
