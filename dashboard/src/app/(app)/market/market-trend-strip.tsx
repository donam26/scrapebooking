"use client";

import { useTranslations } from "next-intl";
import type { HolidayOut, MarketTrendNightOut, MarketTrendOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { useMarketMetrics } from "@/lib/market-metrics";
import { DEEP_RUNG, SOLD_OUT_STEPS, TIGHTNESS_STYLE, median, rungCount, rungMap, soldOutHeat, tightnessTrend, useMarketAreaText, type TightnessTrend } from "@/lib/market-area";
import { HolidayDot, holidayMap } from "@/components/holiday-mark";
import { Card, ErrorBox, SkeletonBlock, cx } from "@/components/ui";
import { ScanAge } from "./scan-age";

/**
 * Mức căng khu vực 14 đêm tới (đầu tab Thị trường): mỗi đêm % khách sạn trong phân khúc đã hết phòng
 * (con số tối thiểu, tô theo thang nhiệt) và số khách sạn còn ít nhất 10 phòng (tô theo mức căng so
 * trung vị các đêm trong dải). Số của lượt quét gần nhất mỗi đêm, không phải dự báo. Đầu thẻ ghi giờ
 * lượt quét mới nhất của dải và chip "Cũ" khi đã quá 24 giờ.
 */

const CELL = "h-8 rounded-md text-xs font-bold tabular";
const ROW_HEAD = "sticky left-0 z-10 bg-surface pr-2 text-left text-xs font-semibold text-body";

type Night = {
  n: MarketTrendNightOut;
  available: number | null;
  deep: number | null;
  trend: TightnessTrend | null;
  title: string;
};

/** `loading`: đang tải khu vực vừa chọn (số cũ làm mờ). */
export function MarketTrendStrip({ trend, error, holidays, today, loading }: { trend: MarketTrendOut | undefined; error: unknown; holidays: HolidayOut[] | undefined; today: string; loading?: boolean }) {
  const t = useTranslations("marketTab.trend");
  const { fmtInt, fmtNight, fmtPriceShort } = useFmt();
  const { dayHead } = useMarketMetrics();
  const { tightnessLabel } = useMarketAreaText();
  const info = t("info", { deep: DEEP_RUNG });
  if (error) {
    return (
      <Card title={t("title")} info={info}>
        <ErrorBox error={error} />
      </Card>
    );
  }
  if (!trend) return <SkeletonBlock className="h-[196px] rounded-[10px]" />;

  const hol = holidayMap(holidays);
  const base = trend.segment_base;
  // "Thường lệ" của dải = trung vị mức căng c(10)/c(1) các đêm đã quét.
  const usual = median(trend.nights.map((n) => n.tightness).filter((v): v is number => v !== null));
  const nights: Night[] = trend.nights.map((n) => {
    const counts = rungMap(n.ladder);
    // Cùng số backend dùng cho tỉ lệ hết phòng (danh sách = nấc 1).
    const available = n.properties_found ?? rungCount(counts, 1);
    const deep = rungCount(counts, DEEP_RUNG);
    const tt = tightnessTrend(n.tightness, usual);
    const parts = [fmtNight(n.stay_date), hol.get(n.stay_date)?.name];
    if (n.status === null) {
      parts.push(t("nightNoScan"));
    } else {
      const share = n.sold_out_share;
      if (share !== null && base !== null && available !== null) parts.push(t("nightSoldOut", { pct: Math.round(share * 100), available, base }));
      else if (available !== null) parts.push(t("nightAvailable", { available }));
      if (deep !== null) parts.push(t("nightDeep", { count: deep, deep: DEEP_RUNG }));
      if (tt) parts.push(tightnessLabel(tt));
      if (n.unavailability_pct !== null) parts.push(t("nightBooking", { pct: n.unavailability_pct }));
      const med = num(n.median_price);
      if (med !== null) parts.push(t("nightMedian", { price: fmtPriceShort(med, "VND") }));
    }
    return { n, available, deep, trend: tt, title: parts.filter(Boolean).join(" · ") };
  });
  const scanned = nights.some((x) => x.n.status !== null);
  // Tuổi số của dải: lượt quét mới nhất trong 14 đêm.
  const latest = trend.nights.reduce<string | null>((a, n) => (n.scanned_at && (!a || n.scanned_at > a) ? n.scanned_at : a), null);

  return (
    <Card title={t("title")} info={info} description={<ScanAge at={latest} />}>
      {!scanned ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <>
          <div aria-busy={loading || undefined} className={cx("sb-scroll -mx-1 overflow-x-auto px-1 pb-1 transition-opacity duration-150", loading && "opacity-60")}>
            <table className="w-full min-w-[680px] table-fixed border-separate border-spacing-[3px] text-center">
              <thead>
                <tr>
                  <th scope="col" className={cx(ROW_HEAD, "w-[112px]")}>
                    <span className="sr-only">{t("night")}</span>
                  </th>
                  {nights.map(({ n, title }) => {
                    const h = dayHead(n.stay_date, today);
                    const tone = h.isToday ? "text-brand" : h.weekend ? "text-danger" : "text-muted";
                    return (
                      <th key={n.stay_date} scope="col" title={title} className={cx("rounded-md px-0.5 pb-1 pt-0.5 font-normal", h.isToday && "bg-brand-softer")}>
                        <div className={cx("text-[11px] font-semibold uppercase", tone)}>{h.isToday ? t("today") : h.wd}</div>
                        <div className={cx("text-[11px] tabular", tone)}>{h.date}</div>
                        <HolidayDot holiday={hol.get(n.stay_date)} className="mt-0.5" />
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row" title={t("soldOutTitle")} className={ROW_HEAD}>
                    {t("soldOut")}
                  </th>
                  {nights.map(({ n, title }) => {
                    const share = n.sold_out_share;
                    return (
                      <td key={n.stay_date} title={title} className={cx(CELL, n.status === null ? "sb-mark-nodata font-normal" : share === null ? "bg-sunken text-faint" : soldOutHeat(share))}>
                        {share === null ? "—" : `${Math.round(share * 100)}%`}
                      </td>
                    );
                  })}
                </tr>
                <tr>
                  <th scope="row" title={t("deepTitle", { deep: DEEP_RUNG })} className={ROW_HEAD}>
                    {t("deep", { deep: DEEP_RUNG })}
                  </th>
                  {nights.map(({ n, deep, trend: tt, title }) => (
                    <td key={n.stay_date} title={title} className={cx(CELL, n.status === null ? "sb-mark-nodata font-normal" : deep === null ? "bg-sunken text-faint" : TIGHTNESS_STYLE[tt ?? "usual"].chip)}>
                      {deep === null ? "—" : fmtInt(deep)}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <ul className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t border-line pt-2.5 text-xs text-muted">
            <li className="flex flex-wrap items-center gap-1.5">
              <span>{t("legendSoldOut")}</span>
              <span className="tabular">{t("legendLow", { pct: Math.round(SOLD_OUT_STEPS[SOLD_OUT_STEPS.length - 1] * 100) })}</span>
              <span aria-hidden className="flex gap-0.5">
                {[5, 4, 3, 2, 1, 0].map((i) => (
                  <span key={i} className={`sb-heat-${i} h-3 w-4 rounded-[3px]`} />
                ))}
              </span>
              <span className="tabular">{t("legendHigh", { pct: Math.round(SOLD_OUT_STEPS[0] * 100) })}</span>
            </li>
            <li className="flex flex-wrap items-center gap-1.5">
              <span>{t("legendDeep", { deep: DEEP_RUNG })}</span>
              {(["tighter", "usual", "looser"] as const).map((k) => (
                <span key={k} className={cx("rounded px-1.5 py-px text-[11px] font-semibold", TIGHTNESS_STYLE[k].chip)}>
                  {tightnessLabel(k)}
                </span>
              ))}
            </li>
          </ul>
        </>
      )}
    </Card>
  );
}
