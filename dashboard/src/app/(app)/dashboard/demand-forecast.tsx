"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { CompsetDayOut, PaceNightOut } from "@/lib/api";
import { dateRange } from "@/lib/format";
import { DEMAND_COLOR, DEMAND_TEXT, demandLevel, demandScore, useMarketMetrics } from "@/lib/market-metrics";
import { Card, cx } from "@/components/ui";

/**
 * DỰ BÁO CẦU: mỗi đêm một cột (thứ, ngày, ô cao có phần màu theo điểm, điểm, mức).
 * Điểm = công suất ước tính của compset (hoặc tỷ lệ đối thủ hết phòng khi chưa ước tính được).
 */
export function DemandForecast({
  start,
  end,
  today,
  nights,
  compset,
  channel,
}: {
  start: string;
  end: string;
  today: string;
  nights: PaceNightOut[];
  compset: CompsetDayOut[];
  channel: string | null;
}) {
  const t = useTranslations("dashboard.forecast");
  const { demandLabel, dayHead } = useMarketMetrics();
  const byNight = new Map(nights.map((n) => [n.stay_date, n]));
  const byComp = new Map(compset.map((c) => [c.stay_date, c]));
  const dates = dateRange(start, end);
  return (
    <Card
      title={t("title")}
      info={t("info")}
    >
      <div className="sb-scroll -mx-1 overflow-x-auto pb-1">
        <ol className="grid min-w-[760px] px-1" style={{ gridTemplateColumns: `repeat(${dates.length}, minmax(0, 1fr))` }}>
          {dates.map((d, i) => {
            const h = dayHead(d, today);
            const ds = demandScore(byNight.get(d), byComp.get(d));
            const score = ds?.score ?? null;
            const level = score === null ? null : demandLevel(score);
            const fill = score === null ? 0 : Math.max(10, Math.min(100, score));
            return (
              <li key={d} className={cx("min-w-0", i > 0 && "border-l border-line")}>
                <Link
                  href={`/availability?start=${d}${channel ? `&channel=${channel}` : ""}`}
                  className="flex flex-col items-center rounded-md px-1 py-1 text-center transition-colors hover:bg-subtle"
                  title={score === null ? t("cellNoData") : t("cellTitle", { score, source: ds?.source === "occ" ? "occ" : "soldOut", level: demandLabel(level!) })}
                >
                  <span className={cx("text-[11px] font-semibold uppercase", h.isToday ? "text-brand" : h.weekend ? "text-danger" : "text-muted")}>
                    {h.isToday ? t("today") : h.wd}
                  </span>
                  <span className="text-[11px] text-muted tabular">{h.date}</span>
                  <span className="relative mt-2 h-11 w-6 overflow-hidden rounded-[5px] bg-sunken">
                    {level && (
                      <span
                        aria-hidden
                        className="absolute inset-x-0 bottom-0 rounded-[5px]"
                        style={{ height: `${fill}%`, background: DEMAND_COLOR[level] }}
                      />
                    )}
                  </span>
                  <span className={cx("mt-1.5 text-md font-bold tabular", level ? DEMAND_TEXT[level] : "text-faint")}>{score === null ? "—" : ds?.source === "occ" ? `≈${score}` : <span className="underline decoration-dotted underline-offset-2">{score}</span>}</span>
                  <span className="text-[11px] text-muted">{level ? demandLabel(level) : t("noData")}</span>
                </Link>
              </li>
            );
          })}
        </ol>
      </div>
    </Card>
  );
}
