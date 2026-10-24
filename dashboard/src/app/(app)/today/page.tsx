"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { api } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { rowName } from "@/lib/market-metrics";
import { ChangeSummaryLine } from "@/components/change-summary";
import { DataUpdated } from "@/components/freshness";
import { PageStrip } from "@/components/page-strip";
import { HolidayChips } from "@/components/holiday-mark";
import { OwnHotelSwitcher, useOwnHotelParam, useOwnHotels } from "@/components/own-hotel";
import { ACTION_NIGHTS, TodayActions } from "@/components/today-actions";
import { OtbCompact } from "@/components/otb-panel";
import { SetupChecklist } from "@/components/setup-checklist";
import { ButtonLink, Card, EmptyState, ErrorBox, SkeletonBlock } from "@/components/ui";
import { IconArrowRight, IconBrief, IconBuilding, IconCheck, IconPlus } from "@/components/icons";
import { NightStrip } from "./night-strip";
import { YourHotelTonight } from "./your-hotel-tonight";

/**
 * Hôm nay (trang mở đầu, gộp Hôm nay + Bảng điều khiển cũ): việc cần làm 14 đêm tới, 14 đêm của bạn
 * so với đối thủ, thay đổi 24 giờ, bản tin; cột phụ là khách sạn của bạn đêm nay.
 */

/** Mở từ nút "Đã xử lý" trong tin (Zalo/email): backend ghi nhận rồi chuyển về `/today?resolved=1`. */
function ResolvedNotice() {
  const t = useTranslations("today");
  const params = useSearchParams();
  if (params.get("resolved") !== "1") return null;
  return (
    <p role="status" className="mb-4 flex items-center gap-2 rounded-lg border border-yours/30 bg-yours-soft px-3.5 py-2.5 text-sm font-semibold text-yours-deep">
      <IconCheck size={16} className="shrink-0" /> {t("resolvedNotice")}
    </p>
  );
}

function TodayView() {
  const t = useTranslations("today");
  const { fmtDateShort, fmtWeekday, fmtWhen } = useFmt();
  const today = useTenantToday();
  const end = today ? addDays(today, ACTION_NIGHTS - 1) : "";
  const { canWrite } = useSession();
  const [hotelParam, setHotel] = useOwnHotelParam();
  const ownHotels = useOwnHotels();
  const overview = useApi(today && `today:overview:${today}:${hotelParam ?? ""}`, () => api.overview({ start: today!, end, own_hotel_id: hotelParam }));
  const pace = useApi(today && `today:pace:${today}:${hotelParam ?? ""}`, () => api.market.pace({ start: today!, end, own_hotel_id: hotelParam }));
  // Thay đổi 24 giờ gom theo khách sạn (backend đếm theo đêm, không theo sự kiện từng loại phòng).
  const changes = useApi(today && `today:changes:${today}`, () => api.eventsSummary({ days: 1 }));
  const insights = useApi("today:insights", () => api.insights.list(1));
  const settings = useApi("settings", () => api.settings.get());
  const fresh = useDataFreshness(settings.data?.scan_times);
  const o = overview.data;

  const labels = new Map((o?.hotels ?? []).map((h) => [h.hotel.id, rowName(h)]));
  const changed = (changes.data ?? []).filter((c) => c.total_events > 0).sort((a, b) => Number(a.role === "self") - Number(b.role === "self"));
  const insight = insights.data?.find((i) => i.status === "completed");
  const summary = typeof insight?.output_json?.summary === "string" ? insight.output_json.summary : null;
  const tonightPace = today ? pace.data?.nights.find((n) => n.stay_date === today) : undefined;

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={
          today && (
            <>
              <span>
                {fmtWeekday(today)} {fmtDateShort(today)}
              </span>
              {o && <HolidayChips holidays={o.holidays} start={o.start} end={o.end} />}
            </>
          )
        }
        aside={fresh.loaded && <DataUpdated f={fresh} />}
        actions={<OwnHotelSwitcher hotels={ownHotels} value={hotelParam ?? pace.data?.own_hotel_id ?? null} onChange={setHotel} />}
      />
      <Suspense fallback={null}>
        <ResolvedNotice />
      </Suspense>
      <ErrorBox error={overview.error} className="mb-4" />
      {(!o || !today) && !overview.error && (
        <div aria-busy className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-4">
            <SkeletonBlock className="h-56 w-full rounded-xl" />
            <SkeletonBlock className="h-48 w-full rounded-xl" />
          </div>
          <SkeletonBlock className="h-72 w-full rounded-xl" />
        </div>
      )}
      {o && o.hotels.length === 0 && (
        <EmptyState
          icon={<IconBuilding />}
          title={t("empty.title")}
          className="border border-line bg-surface"
          action={
            <ButtonLink href="/settings?tab=watchlist" variant="primary" icon={<IconPlus size={16} />}>
              {t("empty.add")}
            </ButtonLink>
          }
        >
          {t("empty.body")}
        </EmptyState>
      )}
      {o && today && o.hotels.length > 0 && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0 space-y-4">
            <TodayActions today={today} overview={o} pace={pace.data} error={pace.error} fresh={fresh} canWrite={canWrite} onChanged={pace.reload} />
            <NightStrip o={o} pace={pace.data} today={today} stale={fresh.stale} />
            <Card
              title={t("changes.title")}
              padded={false}
              actions={
                <Link href="/events" className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
                  {t("changes.allEvents")} <IconArrowRight size={14} />
                </Link>
              }
            >
              <ErrorBox error={changes.error} className="m-4" />
              {changes.data &&
                (changed.length === 0 ? (
                  <p className="px-5 py-4 text-sm text-muted">{fresh.stale && fresh.updatedAt ? t("changes.emptyStale") : t("changes.empty")}</p>
                ) : (
                  <ul className="divide-y divide-line">
                    {changed.map((c) => (
                      <li key={c.hotel_id} className="px-5 py-3">
                        <Link href={`/hotels/${c.hotel_id}`} className="block hover:text-brand">
                          <ChangeSummaryLine summary={c} days={1} label={labels.get(c.hotel_id) ?? c.hotel_name} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                ))}
            </Card>
            {insight && (
              <Card
                title={t("brief.title")}
                actions={
                  <Link href={`/insights/${insight.id}`} className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
                    {t("brief.read")} <IconArrowRight size={14} />
                  </Link>
                }
              >
                <div className="flex gap-3">
                  <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">
                    <IconBrief size={18} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-muted">{t("brief.dated", { when: fmtWhen(insight.generated_at) })}</p>
                    <p className="mt-0.5 line-clamp-4 text-base text-body">{summary ?? t("brief.noSummary")}</p>
                  </div>
                </div>
              </Card>
            )}
          </div>
          <div className="min-w-0 space-y-4">
            <SetupChecklist />
            <YourHotelTonight o={o} night={tonightPace} today={today} />
            <OtbCompact today={today} ownHotelId={hotelParam} />
          </div>
        </div>
      )}
    </>
  );
}

export default function TodayPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-64 w-full rounded-xl" />}>
      <TodayView />
    </Suspense>
  );
}
