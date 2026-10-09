"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { CalibrationOut, HolidayOut, OverviewOut, PaceNightOut } from "@/lib/api";
import { dateRange } from "@/lib/format";
import { DEMAND_COLOR, DEMAND_TEXT, DEMAND_THRESHOLDS, MIN_SAMPLE, TIGHT_SHARE, compsetTightness, demandLevel, fillReading, useMarketMetrics } from "@/lib/market-metrics";
import { CalibrationNote, useFillText } from "@/components/fill";
import { HolidayDot, holidayMap } from "@/components/holiday-mark";
import { Card, cx } from "@/components/ui";

/**
 * MỨC CĂNG THỊ TRƯỜNG (HIỆN TẠI), không phải dự báo: mỗi đêm một cột với HAI nguồn tách riêng, không
 * trộn vào một thang:
 * - cột màu + "≈72": chỉ báo lấp đầy ≈ của compset trên Booking.com (thang mức chung 75/50);
 * - hình thoi + "3/5": số đối thủ hết hoặc còn ≤3 phòng / số đối thủ quan sát được.
 */
export function MarketTightness({
  o,
  nights,
  calibration,
  today,
}: {
  o: OverviewOut;
  nights: PaceNightOut[];
  /** Hiệu chỉnh theo lead time: nhóm sai số quá ngưỡng thì ẩn chỉ báo của đêm. */
  calibration: CalibrationOut | undefined;
  today: string;
}) {
  const t = useTranslations("dashboard.tightness");
  const tm = useTranslations("helpers.marketMetrics");
  const { demandLabel, dayHead } = useMarketMetrics();
  const { fillText, hiddenText } = useFillText();
  const byNight = new Map(nights.map((n) => [n.stay_date, n]));
  const holidays = holidayMap(o.holidays);
  const dates = dateRange(o.start, o.end);
  return (
    <Card title={t("title")} info={t("info", { high: DEMAND_THRESHOLDS.high, moderate: DEMAND_THRESHOLDS.moderate, min: MIN_SAMPLE })}>
      <div className="sb-scroll -mx-1 overflow-x-auto pb-1">
        <ol className="grid px-1" style={{ gridTemplateColumns: `repeat(${dates.length}, minmax(52px, 1fr))` }}>
          {dates.map((d, i) => {
            const h = dayHead(d, today);
            const holiday: HolidayOut | undefined = holidays.get(d);
            const reading = fillReading(byNight.get(d), calibration);
            const fill = reading.value;
            const pct = fill === null ? null : Math.round(fill * 100);
            const level = pct === null ? null : demandLevel(pct);
            const tn = compsetTightness(o, d);
            const tightRule = tn.observed >= 2 && tn.tight / tn.observed >= TIGHT_SHARE;
            const title = [
              holiday?.name,
              reading.hidden ? hiddenText(reading) : pct === null ? t("fillNone") : t("fillTitle", { pct: fillText(reading) ?? "", level: demandLabel(level!) }),
              tn.observed ? t("tightTitle", { tight: tn.tight, observed: tn.observed }) + (tn.smallSample ? ` (${tm("smallSample")})` : "") : t("tightNone"),
              tn.restricted ? t("restrictedTitle", { count: tn.restricted }) : null,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <li key={d} className={cx("min-w-0", i > 0 && "border-l border-line")}>
                <Link
                  href={`/availability?start=${d}`}
                  className={cx("flex flex-col items-center rounded-md px-1 py-1 text-center transition-colors hover:bg-subtle", holiday && "bg-subtle")}
                  title={title}
                >
                  <span className={cx("text-[11px] font-semibold uppercase", h.isToday ? "text-brand" : h.weekend ? "text-danger" : "text-muted")}>{h.isToday ? t("today") : h.wd}</span>
                  <span className="text-[11px] text-muted tabular">{h.date}</span>
                  <HolidayDot holiday={holiday} className="mt-0.5" />
                  <span className="relative mt-1.5 h-11 w-6 overflow-hidden rounded-[5px] bg-sunken">
                    {level && pct !== null && (
                      <span aria-hidden className="absolute inset-x-0 bottom-0 rounded-[5px]" style={{ height: `${Math.max(10, Math.min(100, pct))}%`, background: DEMAND_COLOR[level] }} />
                    )}
                  </span>
                  <span className={cx("mt-1.5 text-md font-bold tabular", level ? DEMAND_TEXT[level] : "text-faint")}>{pct === null ? "—" : `≈${pct}`}</span>
                  <span className="text-[11px] text-muted">{level ? demandLabel(level) : reading.hidden ? t("fillHidden") : t("noFill")}</span>
                  <span className="mt-1.5 flex items-center gap-1 border-t border-line pt-1.5 text-xs tabular">
                    <span aria-hidden className={cx("h-2 w-2 rotate-45 rounded-[1px]", tightRule ? "bg-hot" : tn.tight ? "bg-ink" : "bg-line-strong")} />
                    <span className={cx(tightRule ? "font-bold text-hot" : "font-semibold text-body", tn.smallSample && "opacity-60")}>{tn.observed ? `${tn.tight}/${tn.observed}` : "—"}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </div>
      <ul className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-line pt-3 text-xs text-muted">
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="h-3 w-2 rounded-[2px] bg-brand" />
          {t("legendFill")}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="h-2 w-2 rotate-45 rounded-[1px] bg-hot" />
          {t("legendTight", { min: MIN_SAMPLE })}
        </li>
        {o.holidays.length > 0 && (
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-ink" />
            {t("legendHoliday")}
          </li>
        )}
      </ul>
      <p className="mt-1.5 text-xs font-medium text-body">
        {t("notForecast")} <CalibrationNote calibration={calibration} className="font-normal" />
      </p>
    </Card>
  );
}
