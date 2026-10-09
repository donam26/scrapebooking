"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { api, apiUrl } from "@/lib/api";
import { ExportMenu } from "@/components/export-menu";
import { useApi, useTenantToday } from "@/lib/hooks";
import { addDays, parseDate } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { EmptyState, ErrorBox, SkeletonBlock, cx } from "@/components/ui";
import { PageStrip } from "@/components/page-strip";
import { DataUpdated } from "@/components/freshness";
import { IconBuilding, IconChevronLeft, IconChevronRight } from "@/components/icons";
import { hotelColors } from "@/lib/market-metrics";
import { HeatLegend, HeatmapTable } from "./heatmap-table";
import { OccupancyAnalysis } from "./occupancy-analysis";

/** Phòng trống: heatmap 16 đêm (Trước/Sau, dấu ngày lễ), dòng tổng và chỉ báo lấp đầy ≈ 30 đêm. */

const WINDOW = 16;
const ANALYSIS_DAYS = 30;

function monthParts(iso: string): { month: number; year: number } {
  const d = parseDate(iso);
  return { month: d.getMonth() + 1, year: d.getFullYear() };
}

function AvailabilityView() {
  const today = useTenantToday();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("start");
  const start = raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : today;
  const end = start ? addDays(start, WINDOW - 1) : "";
  const t = useTranslations("availability.page");

  const overview = useApi(start && `avail:ov:${start}`, () => api.overview({ start: start!, end }));
  const o = overview.data;
  const pace = useApi(start && `avail:pace:${start}`, () => api.market.pace({ start: start!, end: addDays(start!, ANALYSIS_DAYS - 1) }));
  const occupancy = useApi(start && `avail:occ:${start}`, () => api.market.occupancy({ start: start!, end: addDays(start!, ANALYSIS_DAYS - 1) }));
  const fresh = useDataFreshness();
  const nights = pace.data?.nights ?? [];

  function go(nextStart: string) {
    const q = new URLSearchParams(params.toString());
    if (nextStart === today) q.delete("start");
    else q.set("start", nextStart);
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }
  // Chờ biết "hôm nay" của tenant (mọi hook đã gọi ở trên).
  if (!start || !today) return <SkeletonBlock className="h-[460px] w-full rounded-[10px]" />;
  const prev = addDays(start, -WINDOW) < today ? today : addDays(start, -WINDOW);
  const startLabel = t("month", monthParts(start));
  const endLabel = t("month", monthParts(end));

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={o && <span>{t("subtitle")}</span>}
        aside={fresh.loaded && <DataUpdated f={fresh} />}
        actions={<ExportMenu csvHref={apiUrl("/export/overview.csv", { start, end })} start={start} end={end} month={today.slice(0, 7)} />}
      />
      <ErrorBox error={overview.error} className="mb-4" />
      {!o && !overview.error && <SkeletonBlock className="h-[460px] w-full rounded-[10px]" />}
      {o && o.hotels.length === 0 && (
        <EmptyState icon={<IconBuilding />} title={t("emptyTitle")} className="border border-line bg-surface">
          {t.rich("emptyBody", {
            link: (c) => (
              <Link href="/settings?tab=watchlist" className="font-semibold text-brand hover:underline">
                {c}
              </Link>
            ),
          })}
        </EmptyState>
      )}
      {o && o.hotels.length > 0 && (
        <div className="space-y-4">
          <section className={cx("overflow-hidden rounded-[10px] border border-line bg-surface shadow-card transition-opacity", overview.loading && "opacity-60")}>
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <button
                type="button"
                onClick={() => go(prev)}
                disabled={start <= today}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-brand hover:bg-brand-softer disabled:cursor-not-allowed disabled:text-faint disabled:hover:bg-transparent"
              >
                <IconChevronLeft size={15} /> {t("prev")}
              </button>
              <div className="text-base font-semibold text-ink">{startLabel === endLabel ? startLabel : t("monthRange", { start: startLabel, end: endLabel })}</div>
              <button type="button" onClick={() => go(addDays(start, WINDOW))} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-brand hover:bg-brand-softer">
                {t("next")} <IconChevronRight size={15} />
              </button>
            </div>
            <HeatmapTable data={o} nights={nights} calibration={pace.data?.calibration} today={today} />
            <div className="border-t border-line px-5 py-3">
              <HeatLegend />
            </div>
          </section>
          <OccupancyAnalysis nights={nights} calibration={pace.data?.calibration} perHotel={occupancy.data} colors={hotelColors(o)} />
        </div>
      )}
    </>
  );
}

export default function AvailabilityPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[460px] w-full rounded-[10px]" />}>
      <AvailabilityView />
    </Suspense>
  );
}
