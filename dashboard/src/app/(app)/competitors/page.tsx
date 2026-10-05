"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Suspense } from "react";
import { api, type HotelRow, type OverviewOut } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, dateRange, num, useFmt } from "@/lib/format";
import { channelName, withChannel } from "@/lib/channels";
import { HOTEL_LINE_COLORS, OWN_LINE_COLOR, bookablePrice, cellOn, distanceKm, rowName, selfRow } from "@/lib/market-metrics";
import { ButtonLink, EmptyState, ErrorBox, SkeletonBlock, cx } from "@/components/ui";
import { PageStrip, StripDivider } from "@/components/page-strip";
import { ChannelSwitcher, ListingChips, useChannelParam } from "@/components/channels";
import { exactShade } from "@/components/marks";
import { Sparkline } from "@/components/trend-chart";
import { ScanHotelButton } from "@/components/scan-hotel-button";
import { COMPETITOR_TABS, SubTabs } from "@/components/sub-tabs";
import { IconBuilding, IconChevronRight, IconPlus, IconStar } from "@/components/icons";

/** Đối thủ: mỗi khách sạn một thẻ (kênh theo dõi, phòng còn và giá đêm nay, so giá bạn, xu hướng 14 đêm). */

const DAYS = 14;

function RoomsBadge({ row, date }: { row: HotelRow; date: string }) {
  const t = useTranslations("competitors.rooms");
  const c = cellOn(row, date);
  if (!c || c.availability_status === null) return <span className="text-sm text-faint">{t("notScanned")}</span>;
  if (c.availability_status === "sold_out") return <span className="sb-heat-0 shrink-0 rounded-md px-2 py-0.5 text-sm font-bold">{t("soldOut")}</span>;
  if (c.availability_status === "unknown") return <span className="text-sm text-muted">{t("unknown")}</span>;
  if (c.exact_rooms_left === null) return <span className="shrink-0 text-sm font-semibold text-body">{t("available")}</span>;
  return <span className={cx("shrink-0 rounded-md px-2 py-0.5 text-sm font-bold tabular", exactShade(c.exact_rooms_left))}>{t("left", { count: c.exact_rooms_left })}</span>;
}

function HotelCard({ row, o, color, ownPrice, channelParam, km }: { row: HotelRow; o: OverviewOut; color: string; ownPrice: number | null; channelParam: string | null; km: number | null }) {
  const t = useTranslations("competitors.card");
  const { fmtMoney, fmtNum, fmtPct } = useFmt();
  const self = row.role === "self";
  const c = cellOn(row, o.start);
  const price = bookablePrice(c);
  const vsOwn = !self && price !== null && ownPrice ? ((price - ownPrice) / ownPrice) * 100 : null;
  const change7 = num(c?.price_change_7d_pct);
  const stars = num(row.hotel.star_rating);
  const spark = dateRange(o.start, o.end).map((d) => bookablePrice(cellOn(row, d)));
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
          <dt className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint">{t("tonightRate")}</dt>
          <dd className={cx("mt-0.5 text-base font-bold tabular", self ? "text-brand" : "text-ink")}>{price === null ? "—" : fmtMoney(price, c?.currency)}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint">{t("vsYours")}</dt>
          <dd className={cx("mt-0.5 text-base font-bold tabular", vsOwn === null ? "text-faint" : vsOwn < 0 ? "text-danger" : "text-yours")}>
            {vsOwn === null ? "—" : fmtPct(vsOwn, { signed: true, digits: 0 })}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint">{t("change7d")}</dt>
          <dd className={cx("mt-0.5 text-base font-bold tabular", change7 === null ? "text-faint" : change7 > 0 ? "text-hot" : change7 < 0 ? "text-yours" : "text-ink")}>
            {change7 === null ? "—" : fmtPct(change7, { signed: true, digits: 0 })}
          </dd>
        </div>
      </dl>
      <div className="mt-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.04em] text-faint">{t("nextNights", { count: DAYS })}</div>
        <Sparkline values={spark} color={color} />
      </div>
      <ListingChips listings={row.hotel.listings} className="mt-3" />
      <div className="mt-auto flex items-center justify-between gap-2 pt-3">
        <ScanHotelButton hotelId={row.hotel.id} className="-ml-2.5" />
        <Link href={withChannel(`/hotels/${row.hotel.id}`, channelParam)} className="ml-auto inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline">
          {t("details")} <IconChevronRight size={15} />
        </Link>
      </div>
    </article>
  );
}

function CompetitorsView() {
  const today = useTenantToday();
  const [channelParam, setChannel] = useChannelParam();
  const { canWrite } = useSession();
  const t = useTranslations("competitors.page");
  const { fmtWhen } = useFmt();
  const overview = useApi(today && `comp:${today}:${channelParam ?? ""}`, () => api.overview({ start: today!, end: addDays(today!, DAYS - 1), channel: channelParam }));
  const o = overview.data;
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
              <StripDivider />
              <span>{t.rich("channel", { channel: channelName(o.channel), b: (c) => <span className="font-semibold text-ink">{c}</span> })}</span>
            </>
          )
        }
        aside={o?.last_run && <span>{t("scannedAt", { when: fmtWhen(o.last_run.finished_at ?? o.last_run.started_at) })}</span>}
        actions={
          <>
            {o && <ChannelSwitcher channels={o.channels} value={o.channel} onChange={setChannel} />}
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
        <div className={cx("grid gap-4 transition-opacity md:grid-cols-2 xl:grid-cols-3", overview.loading && "opacity-60")}>
          {rows.map((r, i) => (
            <HotelCard key={r.hotel.id} row={r} o={o} ownPrice={ownPrice} channelParam={channelParam} color={colors[i]} km={r.role === "self" || !selfHotel ? null : distanceKm(selfHotel, r.hotel)} />
          ))}
        </div>
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
