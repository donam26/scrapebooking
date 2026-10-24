"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { MarketPaceOut, OverviewOut } from "@/lib/api";
import { dateRange, isWeekend, useFmt } from "@/lib/format";
import { cellOn, compsetDay, lastPrice, selfRow } from "@/lib/market-metrics";
import { deltaVsMedian } from "@/lib/night-reason";
import { holidayMap, HolidayDot } from "@/components/holiday-mark";
import { MarkSwatch, useMarks } from "@/components/marks";
import { Card, cx } from "@/components/ui";

/** "−41%" / "+8%" / "0%" với dấu trừ thật. */
function signedPct(v: number): string {
  return v > 0 ? `+${v}%` : v < 0 ? `−${-v}%` : "0%";
}

/**
 * 14 đêm tới của bạn so với đối thủ, một cột mỗi đêm: phòng còn của bạn (dấu màu), giá của bạn,
 * giá bạn so giá giữa đối thủ, số đối thủ hết phòng, chấm tím khi đêm đó có gợi ý giá chưa xử lý.
 * Bấm cột mở chi tiết đêm của khách sạn bạn.
 */
export function NightStrip({ o, pace, today, stale }: { o: OverviewOut; pace: MarketPaceOut | undefined; today: string; stale: boolean }) {
  const t = useTranslations("today.strip");
  const { fmtWeekday, fmtDateShort, fmtPriceShort } = useFmt();
  const { cellMark } = useMarks();
  const self = selfRow(o);
  const holidays = holidayMap(o.holidays);
  const sugByNight = new Map((pace?.nights ?? []).map((n) => [n.stay_date, n.suggestion]));
  const nights = dateRange(o.start, o.end).slice(0, 14);
  return (
    <Card title={t("title")} info={t("info")} padded={false}>
      <div className="sb-scroll overflow-x-auto px-3 pb-3 pt-1">
        <ol className="grid min-w-[880px] grid-cols-14 gap-1.5">
          {nights.map((d) => {
            const cell = cellOn(self, d);
            const price = lastPrice(cell);
            const c = compsetDay(o, d);
            const delta = deltaVsMedian(c?.price_index);
            const sug = sugByNight.get(d);
            const pending = !stale && !!sug && sug.kind !== "hold" && !sug.decision;
            const body = (
              <div
                className={cx(
                  "flex h-full flex-col items-center gap-1 rounded-lg border px-1 py-2 text-center transition-colors",
                  d === today ? "border-brand/40 bg-brand-softer" : "border-line bg-surface",
                  self && "hover:border-brand/50 hover:bg-subtle",
                )}
              >
                <div className={cx("text-xs font-semibold", isWeekend(d) ? "text-danger" : "text-muted")}>{d === today ? t("tonight") : fmtWeekday(d)}</div>
                <div className="flex items-center gap-1 text-sm font-bold text-ink tabular">
                  {fmtDateShort(d)}
                  <HolidayDot holiday={holidays.get(d)} />
                </div>
                <MarkSwatch mark={cellMark(cell)} size={36} />
                <div className={cx("text-sm font-semibold tabular", price?.stale ? "text-muted" : "text-ink")} title={price?.stale ? t("staleTitle") : undefined}>
                  {price === null ? "—" : fmtPriceShort(price.value, cell?.currency)}
                </div>
                <div className="text-xs text-body tabular" title={t("deltaTitle")}>
                  {delta === null ? "—" : signedPct(delta)}
                </div>
                <div className={cx("text-xs tabular", c && c.competitors_sold_out > 0 ? "font-semibold text-danger" : "text-muted")} title={t("soldOutTitle")}>
                  {c && c.competitors_observed ? `${c.competitors_sold_out}/${c.competitors_observed}` : "—"}
                </div>
                <span aria-hidden className={cx("h-1.5 w-1.5 rounded-full", pending ? "bg-[#7c3aed]" : "bg-transparent")} />
                {pending && <span className="sr-only">{t("hasSuggestion")}</span>}
              </div>
            );
            return (
              <li key={d}>
                {self ? (
                  <Link href={`/hotels/${self.hotel.id}/dates/${d}`} className="block h-full rounded-lg">
                    {body}
                  </Link>
                ) : (
                  body
                )}
              </li>
            );
          })}
        </ol>
      </div>
      <p className="border-t border-line px-5 py-2.5 text-xs text-muted">{t("legend")}</p>
    </Card>
  );
}
