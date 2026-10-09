"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Suspense } from "react";
import { api, cellState, type HotelRow, type OverviewOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { dateRange, num, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { HOTEL_LINE_COLORS, OWN_LINE_COLOR, bookablePrice, cellOn, distanceKm, rowName, selfRow } from "@/lib/market-metrics";
import { ButtonLink, EmptyState, ErrorBox, SkeletonBlock, cx } from "@/components/ui";
import { PageStrip } from "@/components/page-strip";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { DataUpdated } from "@/components/freshness";
import { HolidayChips } from "@/components/holiday-mark";
import { ListingChips } from "@/components/listing-chip";
import { exactShade, useMarks } from "@/components/marks";
import { Sparkline } from "@/components/trend-chart";
import { ScanHotelButton } from "@/components/scan-hotel-button";
import { COMPETITOR_TABS, SubTabs } from "@/components/sub-tabs";
import { IconBuilding, IconChevronRight, IconPlus, IconStar } from "@/components/icons";
import { ReputationCard, VisibilityCard } from "./reputation-cards";

/**
 * Đối thủ: mỗi khách sạn một thẻ (trang Booking.com đang theo dõi, phòng còn và giá đêm đầu kỳ, giá đối thủ so với giá
 * bạn, xu hướng giá trong kỳ). Kỳ xem chọn được (mặc định 14 đêm từ hôm nay).
 * Quy ước dấu "so với bạn" (chung với Giá & định giá): (+) đối thủ đắt hơn bạn, (−) rẻ hơn; màu trung tính.
 */

const DEFAULT_DAYS = 14;

function RoomsBadge({ row, date }: { row: HotelRow; date: string }) {
  const t = useTranslations("competitors.rooms");
  const c = cellOn(row, date);
  const state = cellState(c);
  if (!c || state === null) return <span className="text-sm text-faint">{t("notScanned")}</span>;
  const stale = c.stale && "sb-stale";
  if (state === "sold_out") return <span className={cx("sb-heat-0 shrink-0 rounded-md px-2 py-0.5 text-sm font-bold", stale)}>{t("soldOut")}</span>;
  // Hạn chế (min-stay, đóng ngày đến): hổ phách, không đỏ — vẫn bán ở điều kiện khác.
  if (state === "restricted")
    return (
      <span className={cx("sb-mark-restricted shrink-0 rounded-md px-2 py-0.5 text-sm font-bold", stale)}>
        {(c.min_stay ?? 1) > 1 ? t("minStay", { count: c.min_stay ?? 2 }) : t("restricted")}
      </span>
    );
  if (state === "no_price") return <span className={cx("sb-mark-no_price shrink-0 rounded-md px-2 py-0.5 text-sm font-semibold", stale)}>{t("noPrice")}</span>;
  if (state === "error") return <span className="text-sm text-muted">{t("unknown")}</span>;
  if (c.exact_rooms_left === null) return <span className={cx("shrink-0 text-sm font-semibold text-body", stale)}>{t("available")}</span>;
  return <span className={cx("shrink-0 rounded-md px-2 py-0.5 text-sm font-bold tabular", exactShade(c.exact_rooms_left), stale)}>{t("left", { count: c.exact_rooms_left })}</span>;
}

function HotelCard({ row, o, color, ownPrice, km, isToday }: { row: HotelRow; o: OverviewOut; color: string; ownPrice: number | null; km: number | null; isToday: boolean }) {
  const t = useTranslations("competitors.card");
  const { fmtAgo, fmtMoney, fmtNight, fmtNum, fmtPct } = useFmt();
  const { promoText } = useMarks();
  const self = row.role === "self";
  const c = cellOn(row, o.start);
  const price = bookablePrice(c);
  // Đêm hạn chế số đêm vẫn có giá (giá/đêm khi ở từ N đêm): hiện kèm ghi chú, không so với giá 1 đêm.
  const restrictedPrice = price === null && cellState(c) === "restricted" ? num(c?.min_price) : null;
  const promo = promoText(c);
  const vsOwn = !self && price !== null && ownPrice ? ((price - ownPrice) / ownPrice) * 100 : null;
  const change7 = num(c?.price_change_7d_pct);
  const stars = num(row.hotel.star_rating);
  const nights = dateRange(o.start, o.end);
  const spark = nights.map((d) => bookablePrice(cellOn(row, d)));
  return (
    <article className={cx("flex min-w-0 flex-col rounded-[10px] border bg-surface p-5 shadow-card", self ? "border-brand/40 ring-1 ring-brand/20" : "border-line")}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-md font-bold text-ink">
            <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
            <span className="truncate" title={rowName(row)}>
              {rowName(row)}
            </span>
          </h2>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-muted">
            {self && <span className="font-semibold text-brand">{t("yourHotel")}</span>}
            {stars !== null && stars > 0 && (
              <span className="inline-flex items-center gap-0.5 text-[#f59e0b]" aria-label={t("stars", { count: stars })}>
                {Array.from({ length: Math.round(stars) }, (_, i) => (
                  <IconStar key={i} size={12} fill="currentColor" />
                ))}
              </span>
            )}
            {km !== null && <span className="font-medium text-body">{t("distance", { km: fmtNum(km, 1) })}</span>}
            {row.hotel.city && <span className="truncate">{row.hotel.city}</span>}
          </div>
        </div>
        <RoomsBadge row={row} date={o.start} />
      </header>
      <dl className="mt-4 grid grid-cols-3 gap-3 border-y border-line py-3 text-center">
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint">{isToday ? t("tonightRate") : t("nightRate", { night: fmtNight(o.start) })}</dt>
          <dd className={cx("mt-0.5 text-base font-bold tabular", self ? "text-brand" : "text-ink")}>
            {price !== null ? fmtMoney(price, c?.currency) : restrictedPrice !== null ? fmtMoney(restrictedPrice, c?.currency) : "—"}
          </dd>
          {restrictedPrice !== null && <dd className="text-2xs text-warning-deep">{t("minStayPrice", { count: c?.min_stay ?? 2 })}</dd>}
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint" title={t("vsYoursTitle")}>
            {t("vsYours")}
          </dt>
          <dd className={cx("mt-0.5 text-base font-bold tabular", vsOwn === null ? "text-faint" : "text-ink")}>
            {vsOwn === null ? "—" : fmtPct(vsOwn, { signed: true, digits: 0 })}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint">{t("change7d")}</dt>
          <dd className={cx("mt-0.5 text-base font-bold tabular", change7 === null ? "text-faint" : "text-ink")}>
            {change7 === null ? "—" : fmtPct(change7, { signed: true, digits: 0 })}
          </dd>
        </div>
      </dl>
      {(promo || c?.stale) && (
        <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
          {promo && (
            <span className="inline-flex items-center gap-1 rounded-full bg-[#fce7f3] px-2 py-0.5 font-semibold text-[#9d174d]" title={promo}>
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#db2777]" />
              <span className="max-w-[240px] truncate">{t("promo", { promos: promo })}</span>
            </span>
          )}
          {c?.stale && (
            <span className="rounded-full bg-sunken px-2 py-0.5 font-semibold text-muted" title={t("staleTitle")}>
              {t("stale", { ago: fmtAgo(c.last_observed_at) })}
            </span>
          )}
        </div>
      )}
      <div className="mt-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint">{t("nextNights", { count: nights.length })}</div>
        <Sparkline values={spark} color={color} />
      </div>
      <ListingChips listings={row.hotel.listings} className="mt-3" />
      <div className="mt-auto flex items-center justify-between gap-2 pt-3">
        <ScanHotelButton hotelId={row.hotel.id} className="-ml-2.5" />
        <Link href={`/hotels/${row.hotel.id}`} className="ml-auto inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline">
          {t("details")} <IconChevronRight size={15} />
        </Link>
      </div>
    </article>
  );
}

function CompetitorsView() {
  const { start, end, today, ready } = useDateRange(DEFAULT_DAYS);
  const { canWrite } = useSession();
  const t = useTranslations("competitors.page");
  const overview = useApi(ready ? `comp:${start}:${end}` : null, () => api.overview({ start, end }));
  const o = overview.data;
  const fresh = useDataFreshness();
  const rows = o ? [...o.hotels].sort((a, b) => (a.role === "self" ? -1 : b.role === "self" ? 1 : 0)) : [];
  const ownPrice = o ? bookablePrice(cellOn(selfRow(o), o.start)) : null;
  const selfHotel = o ? (selfRow(o)?.hotel ?? null) : null;
  // Màu cố định theo thứ tự, khớp với biểu đồ ở tab Giá.
  const colors = rows.map((r, i) => (r.role === "self" ? OWN_LINE_COLOR : HOTEL_LINE_COLORS[(rows[0]?.role === "self" ? i - 1 : i) % HOTEL_LINE_COLORS.length]));

  return (
    <>
      <SubTabs items={COMPETITOR_TABS} />
      <PageStrip
        title={t("title")}
        meta={
          o && (
            <>
              <span>{t("count", { count: o.hotels.filter((h) => h.role !== "self").length })}</span>
              <HolidayChips holidays={o.holidays} start={o.start} end={o.end} />
            </>
          )
        }
        aside={fresh.loaded && <DataUpdated f={fresh} />}
        actions={
          <>
            <DateRangePicker defaultDays={DEFAULT_DAYS} />
            {canWrite && (
              <ButtonLink href="/settings?tab=watchlist" variant="primary" size="sm" icon={<IconPlus size={15} />}>
                {t("addHotel")}
              </ButtonLink>
            )}
          </>
        }
      />
      <ErrorBox error={overview.error} className="mb-4" />
      {!o && !overview.error && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <SkeletonBlock key={i} className="h-[300px] rounded-[10px]" />
          ))}
        </div>
      )}
      {o && o.hotels.length === 0 && (
        <EmptyState icon={<IconBuilding />} title={t("emptyTitle")} className="border border-line bg-surface">
          {t("emptyBody")}
        </EmptyState>
      )}
      {o && o.hotels.length > 0 && (
        <>
          <div className={cx("grid gap-4 transition-opacity md:grid-cols-2 xl:grid-cols-3", overview.loading && "opacity-60")}>
            {rows.map((r, i) => (
              <HotelCard key={r.hotel.id} row={r} o={o} ownPrice={ownPrice} color={colors[i]} isToday={o.start === today} km={r.role === "self" || !selfHotel ? null : distanceKm(selfHotel, r.hotel)} />
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">{t("signLegend")}</p>
          <div className="mt-6 space-y-4">
            <ReputationCard />
            <VisibilityCard />
          </div>
        </>
      )}
    </>
  );
}

export default function CompetitorsPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[300px] w-full rounded-[10px]" />}>
      <CompetitorsView />
    </Suspense>
  );
}
