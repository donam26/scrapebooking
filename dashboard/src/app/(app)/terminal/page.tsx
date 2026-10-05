"use client";

import { useLocale, useTranslations } from "next-intl";
import { Suspense, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi, useInterval, useTenantToday } from "@/lib/hooks";
import { INTL_LOCALE } from "@/i18n/config";
import { addDays, daysBetween, useFmt } from "@/lib/format";
import { channelName } from "@/lib/channels";
import { rowName, selfRow } from "@/lib/market-metrics";
import { ErrorBox, SkeletonBlock } from "@/components/ui";
import { PageStrip, StripDivider } from "@/components/page-strip";
import { PaceView } from "../pace/pace-view";
import { CityMarketCard } from "./city-market-card";
import { EventsCalendar } from "./events-calendar";
import { BookingSignalsCard, MarketIndicator, RevenueCard, WeatherCard } from "./terminal-cards";

/**
 * Terminal+: bảng tin thị trường một màn hình (chỉ báo thị trường, thời tiết, tín hiệu đặt phòng,
 * doanh thu PMS, lịch sự kiện 12 tháng), bên dưới là nhịp đặt phòng và gợi ý giá.
 */

function TerminalView() {
  const t = useTranslations("terminal.strip");
  const locale = useLocale();
  const { fmtAgo } = useFmt();
  const longDate = useMemo(() => new Intl.DateTimeFormat(INTL_LOCALE[locale], { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }), [locale]);
  const clock = useMemo(() => new Intl.DateTimeFormat(INTL_LOCALE[locale], { hour: "2-digit", minute: "2-digit" }), [locale]);
  const today = useTenantToday();
  const [now, setNow] = useState(() => new Date());
  useInterval(() => setNow(new Date()), 30_000);

  const overview = useApi(today && `term:ov:${today}`, () => api.overview({ start: today!, end: today! }));
  const pace = useApi(today && `term:pace:${today}`, () => api.market.pace({ start: today!, end: addDays(today!, 13) }));
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
  const self = o ? selfRow(o) : null;
  const ids = o ? o.hotels.map((h) => h.hotel.id).join(",") : null;
  // Mỗi khách sạn một lượt gọi chi tiết; khách sạn lỗi thì bỏ qua, lỗi hết thì báo lỗi.
  const signals = useApi(ids === null || !o || !today ? null : `term:signals:${ids}:${today}`, async () => {
    const results = await Promise.allSettled(
      o!.hotels.map(async (h) => ({
        name: rowName(h),
        self: h.role === "self",
        items: (await api.hotel(h.hotel.id, { start: today!, end: today!, event_limit: 1 })).demand_signals,
      })),
    );
    const ok = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
    const failed = results.find((r): r is PromiseRejectedResult => r.status === "rejected");
    if (!ok.length && failed) throw failed.reason;
    return ok;
  });
  const pms = useApi(self ? `term:pms:${self.hotel.id}` : null, () => api.pms.daily(self!.hotel.id, 200));

  if (!today) return <SkeletonBlock className="h-[400px] w-full rounded-[10px]" />;
  const next = (holidays.data ?? []).find((h) => h.date >= today);
  // Mùa đang diễn ra (sự kiện loại "Mùa" do tenant nhập), như chip "Season" của mẫu.
  const season = (localEvents.data ?? []).find((e) => e.category === "season" && e.start_date <= today && e.end_date >= today);
  const run = o?.last_run;

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
              <span>{run ? t("updated", { ago: fmtAgo(run.finished_at ?? run.started_at) }) : t("noScan")}</span>
              <StripDivider />
              <span>{t("channel", { name: channelName(o.channel) })}</span>
            </>
          )
        }
      />
      <ErrorBox error={overview.error} className="mb-4" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {city.data ? (
          <CityMarketCard city={city.data} />
        ) : o && (city.data === null || city.error) ? (
          <MarketIndicator o={o} tonight={pace.data?.nights[0]} />
        ) : (
          <SkeletonBlock className="h-[360px] rounded-[10px]" />
        )}
        <WeatherCard data={weather.data} error={weather.error} />
        <BookingSignalsCard signals={signals.data ?? []} loading={!signals.data && !signals.error} error={signals.error} />
        <RevenueCard rows={pms.data ?? []} nights={pace.data?.nights ?? []} today={today} loading={(self !== null && !pms.data && !pms.error) || (!pace.data && !pace.error)} />
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

