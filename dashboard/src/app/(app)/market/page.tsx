"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useMemo, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { INTL_LOCALE } from "@/i18n/config";
import { daysBetween, parseDate } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { useMarketAreaChoice } from "@/lib/market-area-choice";
import { useSession } from "@/lib/session";
import { AreaSelect } from "@/components/area-select";
import { DataUpdated } from "@/components/freshness";
import { PageStrip } from "@/components/page-strip";
import { EmptyState, ErrorBox, SkeletonBlock, cx } from "@/components/ui";
import { IconPin } from "@/components/icons";
import { AreaTodayCard } from "./area-today-card";
import { EventsCalendar } from "./events-calendar";
import { MarketTrendStrip } from "./market-trend-strip";
import { WeatherCard } from "./weather-card";

/**
 * Thị trường (N3, N5, Q5): phần khu vực của Terminal+ cũ, theo thứ tự
 * 1. Mức căng khu vực 14 đêm tới (có tuổi số của lượt quét khu vực);
 * 2. Hôm nay trong khu vực (một câu chính, khách sạn của bạn, "Chi tiết") cạnh thẻ thời tiết (chỉ khi
 *    có dự báo, Q8);
 * 3. Lịch sự kiện & ngày lễ 12 tháng.
 * Nhịp đặt phòng, phòng đã đặt và doanh thu PMS nằm ở Báo cáo › Nhịp đặt phòng.
 */

function MarketView() {
  const t = useTranslations("marketTab");
  const locale = useLocale();
  const { canWrite } = useSession();
  const today = useTenantToday();
  const longDate = useMemo(() => new Intl.DateTimeFormat(INTL_LOCALE[locale], { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }), [locale]);
  const fresh = useDataFreshness();
  const holidays = useApi("market:holidays", () => api.market.holidays());
  const weather = useApi("market:weather", () => api.market.weather());
  const localEvents = useApi("market:local-events", () => api.market.events.list());
  // Khu vực đang xem (lưu theo trình duyệt), dùng chung cho dải 14 đêm và thẻ hôm nay.
  const choice = useMarketAreaChoice();
  // Chưa có khu vực (404) thì mời chọn khu vực ở Cài đặt › Thị trường.
  const city = useApi(today && choice.ready ? `market:city:${today}:${choice.areaId ?? ""}` : null, () =>
    api.market.city({ date: today!, area_id: choice.areaId }).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
  );
  const areaId = choice.areaId ?? city.data?.area.id;
  const trend = useApi(today && areaId ? `market:trend:${today}:${areaId}` : null, () => api.market.cityTrend({ area_id: areaId, start: today!, nights: 14 }));

  if (!today) return <SkeletonBlock className="h-[400px] w-full rounded-[10px]" />;
  const next = (holidays.data ?? []).find((h) => h.date >= today);
  // Mùa đang diễn ra (sự kiện loại "Mùa" do tenant nhập).
  const season = (localEvents.data ?? []).find((e) => e.category === "season" && e.start_date <= today && e.end_date >= today);
  const noArea = city.data === null;
  const weatherShown = !!(weather.data?.configured && !weather.data.error && weather.data.current);
  const link = (c: ReactNode) => (
    <Link href="/settings?tab=market" className="font-semibold text-brand hover:underline">
      {c}
    </Link>
  );

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={
          <>
            <span className="first-letter:uppercase">{longDate.format(parseDate(today))}</span>
            {season && <span className="rounded-full bg-[#e0f2fe] px-2.5 py-0.5 text-sm font-medium text-[#0369a1]">{t("strip.season", { name: season.name })}</span>}
            {next && (
              <span className="rounded-full bg-[#f3e8ff] px-2.5 py-0.5 text-sm font-medium text-[#6d28d9]">
                {t("strip.nextHoliday", { name: next.name, days: daysBetween(today, next.date) })}
              </span>
            )}
          </>
        }
        aside={fresh.loaded && <DataUpdated f={fresh} />}
        actions={
          choice.active.length >= 2 ? (
            <AreaSelect areas={choice.active} value={choice.areaId ?? city.data?.area.id} onChange={choice.select} className="max-w-[220px]" />
          ) : choice.area ? (
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-body">
              <IconPin size={14} className="text-muted" />
              {choice.area.name}
            </span>
          ) : undefined
        }
      />
      <ErrorBox error={city.error} className="mb-4" />
      {noArea ? (
        <EmptyState icon={<IconPin />} title={t("noArea.title")} className="mb-4 border border-line bg-surface">
          {canWrite ? t.rich("noArea.body", { link }) : t("noArea.viewer")}
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {/* 1. Mức căng khu vực 14 đêm tới */}
          {areaId ? (
            <MarketTrendStrip trend={trend.data} error={trend.error} holidays={holidays.data} today={today} loading={trend.loading} />
          ) : (
            !city.error && <SkeletonBlock className="h-[196px] rounded-[10px]" />
          )}
          {/* 2. Hôm nay trong khu vực (+ thời tiết khi có dự báo) */}
          <div className={cx("grid gap-4", weatherShown && "lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]")}>
            {city.data ? <AreaTodayCard city={city.data} loading={city.loading} /> : !city.error && <SkeletonBlock className="h-[260px] rounded-[10px]" />}
            {weatherShown && <WeatherCard data={weather.data} />}
          </div>
        </div>
      )}
      {/* 3. Lịch sự kiện & ngày lễ 12 tháng */}
      <div className="mt-4">
        <ErrorBox error={holidays.error} className="mb-4" />
        {holidays.data ? <EventsCalendar holidays={holidays.data} localEvents={localEvents.data ?? []} today={today} /> : <SkeletonBlock className="h-[300px] rounded-[10px]" />}
      </div>
    </>
  );
}

/**
 * Link cũ "/terminal#pace" (email, dấu trang): chuyển hướng phía máy chủ không đọc được phần "#…",
 * nên tới đây với hash còn nguyên; chuyển tiếp sang Báo cáo › Nhịp đặt phòng.
 */
function LegacyPaceHash() {
  const router = useRouter();
  useEffect(() => {
    if (window.location.hash === "#pace") router.replace(`/reports/pace${window.location.search}`);
  }, [router]);
  return null;
}

export default function MarketPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[400px] w-full rounded-[10px]" />}>
      <LegacyPaceHash />
      <MarketView />
    </Suspense>
  );
}
