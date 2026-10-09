"use client";

import { useLocale, useTranslations } from "next-intl";
import { Suspense, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi, useInterval, useTenantToday } from "@/lib/hooks";
import { INTL_LOCALE } from "@/i18n/config";
import { daysBetween } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { selfRow } from "@/lib/market-metrics";
import { ErrorBox, SkeletonBlock } from "@/components/ui";
import { PageStrip, StripDivider } from "@/components/page-strip";
import { DataUpdated } from "@/components/freshness";
import { PaceView } from "../pace/pace-view";
import { CityMarketCard } from "./city-market-card";
import { EventsCalendar } from "./events-calendar";
import { MarketIndicator, RevenueCard, WeatherCard } from "./terminal-cards";

/**
 * Terminal+: bảng tin một màn hình (chỉ báo thị trường khu vực hoặc compset, thời tiết, doanh thu
 * PMS, lịch sự kiện 12 tháng), bên dưới là nhịp đặt phòng và gợi ý giá.
 */

function TerminalView() {
  const t = useTranslations("terminal.strip");
  const locale = useLocale();
  const longDate = useMemo(() => new Intl.DateTimeFormat(INTL_LOCALE[locale], { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }), [locale]);
  const clock = useMemo(() => new Intl.DateTimeFormat(INTL_LOCALE[locale], { hour: "2-digit", minute: "2-digit" }), [locale]);
  const today = useTenantToday();
  const [now, setNow] = useState(() => new Date());
  useInterval(() => setNow(new Date()), 30_000);

  const overview = useApi(today && `term:ov:${today}`, () => api.overview({ start: today!, end: today! }));
  // Chỉ báo lấp đầy của đêm nay cho thẻ chỉ báo compset.
  const pace = useApi(today && `term:pace:${today}`, () => api.market.pace({ start: today!, end: today! }));
  const holidays = useApi("term:holidays", () => api.market.holidays());
  const weather = useApi("term:weather", () => api.market.weather());
  const localEvents = useApi("term:local-events", () => api.market.events.list());
  // Thị trường cả khu vực (Cài đặt › Thị trường); chưa có khu vực (404) thì dùng chỉ báo compset.
  const city = useApi(today && `term:city:${today}`, () =>
    api.market.city({ date: today! }).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
  );
  const o = overview.data;
  const fresh = useDataFreshness();
  const self = o ? selfRow(o) : null;
  const pms = useApi(self ? `term:pms:${self.hotel.id}` : null, () => api.pms.daily(self!.hotel.id, 200));

  if (!today) return <SkeletonBlock className="h-[400px] w-full rounded-[10px]" />;
  const next = (holidays.data ?? []).find((h) => h.date >= today);
  // Mùa đang diễn ra (sự kiện loại "Mùa" do tenant nhập), như chip "Season" của mẫu.
  const season = (localEvents.data ?? []).find((e) => e.category === "season" && e.start_date <= today && e.end_date >= today);

  return (
    <>
      <PageStrip
        title="Terminal+"
        meta={
          <>
            <span className="first-letter:uppercase">{longDate.format(now)}</span>
            <span className="tabular">{clock.format(now)}</span>
            {season && <span className="rounded-full bg-[#e0f2fe] px-2.5 py-0.5 text-sm font-medium text-[#0369a1]">{t("season", { name: season.name })}</span>}
            {next && (
              <span className="rounded-full bg-[#f3e8ff] px-2.5 py-0.5 text-sm font-medium text-[#6d28d9]">
                {t("nextHoliday", { name: next.name, days: daysBetween(today, next.date) })}
              </span>
            )}
          </>
        }
        aside={
          o && (
            <>
              <span>{t("hotelsTracked", { count: o.hotels.length })}</span>
              <StripDivider />
              {fresh.loaded && <DataUpdated f={fresh} />}
            </>
          )
        }
      />
      <ErrorBox error={overview.error} className="mb-4" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {city.data ? (
          <CityMarketCard city={city.data} />
        ) : o && (city.data === null || city.error) ? (
          <MarketIndicator o={o} tonight={pace.data?.nights.find((n) => n.stay_date === today)} calibration={pace.data?.calibration} fresh={fresh} />
        ) : (
          <SkeletonBlock className="h-[360px] rounded-[10px]" />
        )}
        <WeatherCard data={weather.data} error={weather.error} />
        <RevenueCard rows={pms.data ?? []} today={today} loading={self !== null && !pms.data && !pms.error} />
      </div>
      <div className="mt-4">
        <ErrorBox error={holidays.error} className="mb-4" />
        {holidays.data ? <EventsCalendar holidays={holidays.data} localEvents={localEvents.data ?? []} today={today} /> : <SkeletonBlock className="h-[300px] rounded-[10px]" />}
      </div>
      <div className="mt-8">
        <PaceView embedded />
      </div>
    </>
  );
}

export default function TerminalPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[400px] w-full rounded-[10px]" />}>
      <TerminalView />
    </Suspense>
  );
}

