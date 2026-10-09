"use client";

import { useTranslations } from "next-intl";
import { Suspense, useState } from "react";
import {
  ApiError,
  api,
  type AreaNightOut,
  type CancellationOut,
  type HotelPromosOut,
  type HotelRestrictionsOut,
  type PromoNightOut,
  type PromoRunOut,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, useFmt } from "@/lib/format";
import { ButtonLink, Card, EmptyState, ErrorBox, ROW_CLASS, Skeleton, SkeletonBlock, Table, Td, Th, cx } from "@/components/ui";
import { PageStrip } from "@/components/page-strip";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { COMPETITOR_TABS, SubTabs } from "@/components/sub-tabs";
import { IconPin, IconTag } from "@/components/icons";

/**
 * Đối thủ › Radar cạnh tranh (roadmap Phase 4): khuyến mãi, hạn chế bán, chính sách huỷ của từng
 * đối thủ trên Booking.com, và mức khan phòng của cả khu vực — đọc từ dữ liệu đã quét.
 */

const DEFAULT_DAYS = 30;
/** Giảm từ chừng này % so tuần trước thì coi là khu vực đang kín dần nhanh. */
const DROP_PCT = -10;
const RESTRICTION_PREVIEW = 6;

type RadarHotel = { hotel_id: number; name: string | null; role: string };

function useHotelName() {
  const t = useTranslations("radar.page");
  return (h: RadarHotel) => h.name ?? t("hotelFallback", { id: h.hotel_id });
}

/** Đối thủ trước, khách sạn của bạn sau cùng (để đọc đối thủ trước). */
function competitorsFirst<T extends RadarHotel>(hotels: T[]): T[] {
  return [...hotels].sort((a, b) => Number(a.role === "self") - Number(b.role === "self"));
}

function YourTag() {
  const t = useTranslations("radar.page");
  return <span className="rounded-full bg-brand-soft px-2 py-0.5 text-2xs font-semibold text-brand-hover">{t("yourHotel")}</span>;
}

// ---- 4.1 Khuyến mãi ----

function PromoStrip({ nights }: { nights: PromoNightOut[] }) {
  const t = useTranslations("radar.promos");
  const { fmtDateShort, fmtNight } = useFmt();
  if (nights.length === 0) return null;
  return (
    <div className="mb-4 rounded-lg bg-subtle px-4 pb-2 pt-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{t("stripLabel")}</span>
        <span className="text-xs text-muted">{t("stripHint")}</span>
      </div>
      <div role="img" aria-label={t("stripLabel")} className="mt-2 flex h-14 items-end gap-px">
        {nights.map((n) => {
          const share = n.observed ? n.running / n.observed : null;
          const title = share === null ? t("nightNoData", { night: fmtNight(n.stay_date) }) : t("nightTitle", { night: fmtNight(n.stay_date), running: n.running, observed: n.observed });
          return (
            <span key={n.stay_date} title={title} className="flex h-full min-w-[3px] flex-1 items-end">
              {share === null ? (
                <span className="h-1 w-full rounded-sm bg-line" />
              ) : (
                <span className="w-full rounded-t-sm bg-[#db2777]" style={{ height: `${Math.max(share * 100, n.running ? 8 : 3)}%`, opacity: n.running ? 0.35 + share * 0.65 : 0.25 }} />
              )}
            </span>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-2xs text-muted tabular">
        <span>{fmtDateShort(nights[0].stay_date)}</span>
        {nights.length > 2 && <span>{fmtDateShort(nights[Math.floor(nights.length / 2)].stay_date)}</span>}
        <span>{fmtDateShort(nights[nights.length - 1].stay_date)}</span>
      </div>
    </div>
  );
}

function PromoLine({ p }: { p: PromoRunOut }) {
  const t = useTranslations("radar.promos");
  const { fmtDateShort, fmtDayTime, fmtPct } = useFmt();
  const depth = num(p.max_depth_pct);
  const nights = [...p.nights].sort();
  const when = p.started_at
    ? t("since", { date: fmtDateShort(p.started_at.slice(0, 10)) })
    : nights.length > 1
      ? t("range", { first: fmtDateShort(nights[0]), last: fmtDateShort(nights[nights.length - 1]) })
      : nights.length === 1
        ? t("rangeOne", { first: fmtDateShort(nights[0]) })
        : null;
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 py-1 text-sm">
      <span className="inline-flex items-center gap-1 font-semibold text-ink">
        <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#db2777]" />
        {p.label}
      </span>
      {depth !== null && depth > 0 && <span className="rounded bg-[#fce7f3] px-1.5 font-bold text-[#9d174d] tabular">{fmtPct(-depth, { digits: 0 })}</span>}
      <span className="text-muted tabular">· {t("nights", { count: nights.length })}</span>
      {when && (
        <span className="text-muted tabular" title={p.started_at ? t("sinceTitle", { time: fmtDayTime(p.started_at) }) : undefined}>
          · {when}
        </span>
      )}
      {p.origin === "channel" && (
        <span className="rounded-full bg-sunken px-2 py-0.5 text-2xs font-semibold text-body" title={t("origin.channelTitle")}>
          {t("origin.channel")}
        </span>
      )}
      {p.origin === "hotel" && (
        <span className="rounded-full bg-brand-softer px-2 py-0.5 text-2xs font-semibold text-brand-hover" title={t("origin.hotelTitle")}>
          {t("origin.hotel")}
        </span>
      )}
    </li>
  );
}

function PromotionsCard({ start, end }: { start: string; end: string }) {
  const t = useTranslations("radar.promos");
  const name = useHotelName();
  const q = useApi(`radar:promos:${start}:${end}`, () => api.market.radar.promotions({ start, end }));
  const d = q.data;
  const hotels: HotelPromosOut[] = d ? competitorsFirst(d.hotels) : [];
  const any = hotels.some((h) => h.promos.length > 0);
  return (
    <Card title={t("title")} info={t("info")} icon={<IconTag size={15} />}>
      <ErrorBox error={q.error} />
      {!d && !q.error && <Skeleton rows={4} />}
      {d && (
        <div className={cx("transition-opacity", q.loading && "opacity-60")}>
          <PromoStrip nights={d.nights} />
          {!any ? (
            <EmptyState title={t("emptyTitle")} compact>
              {t("emptyBody")}
            </EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {hotels.map((h) => (
                <li key={h.hotel_id} className="grid gap-x-4 gap-y-1 py-3 sm:grid-cols-[minmax(160px,220px)_minmax(0,1fr)]">
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <span className="truncate font-semibold text-ink" title={name(h)}>
                      {name(h)}
                    </span>
                    {h.role === "self" && <YourTag />}
                  </div>
                  {h.promos.length === 0 ? (
                    <span className="py-1 text-sm text-faint">{t("none")}</span>
                  ) : (
                    <ul>
                      {h.promos.map((p) => (
                        <PromoLine key={p.label} p={p} />
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}

// ---- 4.2 Hạn chế bán ----

function RestrictionRow({ h }: { h: HotelRestrictionsOut }) {
  const t = useTranslations("radar.restrictions");
  const name = useHotelName();
  const { fmtNight } = useFmt();
  const [all, setAll] = useState(false);
  const nights = [...h.nights].sort((a, b) => (a.stay_date < b.stay_date ? -1 : 1));
  const shown = all ? nights : nights.slice(0, RESTRICTION_PREVIEW);
  return (
    <li className="grid gap-x-4 gap-y-1.5 py-3 sm:grid-cols-[minmax(160px,220px)_minmax(0,1fr)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="truncate font-semibold text-ink" title={name(h)}>
            {name(h)}
          </span>
          {h.role === "self" && <YourTag />}
        </div>
        <div className="text-xs text-muted">{t("count", { count: nights.length })}</div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {shown.map((n) => (
          <span key={n.stay_date} className="inline-flex flex-wrap items-center gap-1">
            <span className="text-sm font-semibold text-ink tabular">{fmtNight(n.stay_date)}</span>
            {n.min_stay > 1 && (
              <span className="sb-mark-restricted rounded-md px-1.5 py-0.5 text-xs font-semibold" title={t("minStayTitle", { count: n.min_stay })}>
                {t("minStay", { count: n.min_stay })}
              </span>
            )}
            {n.closed_to_arrival && (
              <span className="sb-mark-restricted rounded-md px-1.5 py-0.5 text-xs font-semibold" title={t("ctaTitle")}>
                {t("cta")}
              </span>
            )}
          </span>
        ))}
        {nights.length > RESTRICTION_PREVIEW && (
          <button type="button" onClick={() => setAll((v) => !v)} className="text-sm font-semibold text-brand hover:underline">
            {all ? t("less") : t("more", { count: nights.length - RESTRICTION_PREVIEW })}
          </button>
        )}
      </div>
    </li>
  );
}

function RestrictionsCard({ start, end }: { start: string; end: string }) {
  const t = useTranslations("radar.restrictions");
  const q = useApi(`radar:restr:${start}:${end}`, () => api.market.radar.restrictions({ start, end }));
  const hotels = q.data ? competitorsFirst(q.data.hotels).filter((h) => h.nights.length > 0) : [];
  return (
    <Card title={t("title")} info={t("info")}>
      <ErrorBox error={q.error} />
      {!q.data && !q.error && <Skeleton rows={3} />}
      {q.data && hotels.length === 0 && (
        <EmptyState title={t("emptyTitle")} compact>
          {t("emptyBody")}
        </EmptyState>
      )}
      {hotels.length > 0 && (
        <ul className={cx("divide-y divide-line transition-opacity", q.loading && "opacity-60")}>
          {hotels.map((h) => (
            <RestrictionRow key={h.hotel_id} h={h} />
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---- 4.3 Chính sách huỷ ----

function CancellationCard({ start, end }: { start: string; end: string }) {
  const t = useTranslations("radar.cancellation");
  const name = useHotelName();
  const { fmtInt, fmtPct, fmtShare } = useFmt();
  const q = useApi(`radar:cxl:${start}:${end}`, () => api.market.radar.cancellation({ start, end }));
  const hotels: CancellationOut[] = q.data ? [...q.data.hotels].sort((a, b) => Number(b.role === "self") - Number(a.role === "self")) : [];
  const priced = hotels.some((h) => h.nights_priced > 0);
  return (
    <Card title={t("title")} info={t("info")} padded={false}>
      <ErrorBox error={q.error} className="m-5" />
      {!q.data && !q.error && <Skeleton rows={4} className="p-5" />}
      {q.data && !priced && (
        <div className="p-5">
          <EmptyState title={t("emptyTitle")} compact>
            {t("emptyBody")}
          </EmptyState>
        </div>
      )}
      {q.data && priced && (
        <Table dense className={cx("transition-opacity", q.loading && "opacity-60")}>
          <thead>
            <tr>
              <Th className="pl-5">{t("col.hotel")}</Th>
              <Th right>{t("col.refundable")}</Th>
              <Th right>{t("col.nrNights")}</Th>
              <Th right className="pr-5">
                {t("col.nrDiscount")}
              </Th>
            </tr>
          </thead>
          <tbody>
            {hotels.map((h) => (
              <tr key={h.hotel_id} className={cx(ROW_CLASS, h.role === "self" && "bg-brand-softer/40")}>
                <Td className="max-w-[260px] pl-5">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate font-semibold text-ink" title={name(h)}>
                      {name(h)}
                    </span>
                    {h.role === "self" && <YourTag />}
                  </span>
                </Td>
                <Td right className="whitespace-nowrap">
                  <span className="font-semibold text-ink">{h.refundable_share === null ? "—" : fmtShare(h.refundable_share)}</span>
                  {h.nights_priced > 0 && <span className="ml-1 text-xs text-muted">{t("nightsPriced", { count: h.nights_priced })}</span>}
                </Td>
                <Td right>{h.nights_priced > 0 ? fmtInt(h.nonrefundable_nights) : "—"}</Td>
                <Td right className="whitespace-nowrap pr-5">
                  <span className="font-semibold text-ink">{h.nr_discount_pct === null ? "—" : fmtPct(h.nr_discount_pct, { digits: 0 })}</span>
                  {h.pairs > 0 && <span className="ml-1 text-xs text-muted">{t("pairs", { count: h.pairs })}</span>}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

// ---- 4.4 Khan phòng khu vực ----

function ScarcityCard({ start, end }: { start: string; end: string }) {
  const t = useTranslations("radar.scarcity");
  const { fmtInt, fmtNight, fmtDateShort, fmtPct } = useFmt();
  const q = useApi(`radar:area:${start}:${end}`, () =>
    api.market.radar.areaScarcity({ start, end }).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
  );
  if (q.data === null) {
    return (
      <Card title={t("title")} info={t("info")} icon={<IconPin size={15} />}>
        <EmptyState
          icon={<IconPin />}
          title={t("noAreaTitle")}
          compact
          action={
            <ButtonLink href="/settings?tab=market" size="sm" variant="primary">
              {t("noAreaAction")}
            </ButtonLink>
          }
        >
          {t("noAreaBody")}
        </EmptyState>
      </Card>
    );
  }
  const d = q.data;
  const nights: AreaNightOut[] = d?.nights ?? [];
  const max = Math.max(1, ...nights.map((n) => n.properties ?? 0));
  const scanned = nights.some((n) => n.properties !== null);
  const drops = nights
    .map((n) => ({ n, pct: num(n.change_pct) }))
    .filter((x): x is { n: AreaNightOut; pct: number } => x.pct !== null && x.pct < 0)
    .sort((a, b) => a.pct - b.pct)
    .slice(0, 5);
  return (
    <Card title={t("title")} description={d ? t("description", { area: d.area_name }) : undefined} info={t("info")} icon={<IconPin size={15} />}>
      <ErrorBox error={q.error} />
      {q.data === undefined && !q.error && <SkeletonBlock className="h-32 rounded-lg" />}
      {d && !scanned && (
        <EmptyState compact title={d.area_name}>
          {t("emptyBody")}
        </EmptyState>
      )}
      {d && scanned && (
        <div className={cx("transition-opacity", q.loading && "opacity-60")}>
          <div role="img" aria-label={t("title")} className="flex h-28 items-end gap-px">
            {nights.map((n) => {
              const pct = num(n.change_pct);
              const drop = pct !== null && pct <= DROP_PCT;
              const title =
                n.properties === null
                  ? t("nightNoData", { night: fmtNight(n.stay_date) })
                  : `${t("nightTitle", { night: fmtNight(n.stay_date), count: n.properties })}${pct !== null && n.week_ago !== null ? ` · ${t("nightChange", { pct: fmtPct(pct, { signed: true, digits: 0 }), before: fmtInt(n.week_ago) })}` : ""}`;
              return (
                <span key={n.stay_date} title={title} className="flex h-full min-w-[3px] flex-1 items-end">
                  {n.properties === null ? (
                    <span className="h-1 w-full rounded-sm bg-line" />
                  ) : (
                    <span className={cx("w-full rounded-t-sm", drop ? "bg-warning-deep/80" : "bg-brand/45")} style={{ height: `${Math.max((n.properties / max) * 100, 3)}%` }} />
                  )}
                </span>
              );
            })}
          </div>
          <div className="mt-1 flex justify-between text-2xs text-muted tabular">
            <span>{fmtDateShort(nights[0].stay_date)}</span>
            {nights.length > 2 && <span>{fmtDateShort(nights[Math.floor(nights.length / 2)].stay_date)}</span>}
            <span>{fmtDateShort(nights[nights.length - 1].stay_date)}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className="h-2.5 w-2.5 rounded-sm bg-warning-deep/80" />
              {t("legendDrop")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className="h-2.5 w-2.5 rounded-sm bg-brand/45" />
              {t("legendOther")}
            </span>
          </div>
          <div className="mt-4 border-t border-line pt-3">
            <div className="text-xs font-semibold uppercase tracking-[0.05em] text-muted">{t("tightening")}</div>
            {drops.length === 0 ? (
              <p className="mt-1.5 text-sm text-muted">{t("noTightening")}</p>
            ) : (
              <ul className="mt-1.5 divide-y divide-line">
                {drops.map(({ n, pct }) => (
                  <li key={n.stay_date} className="flex flex-wrap items-baseline gap-x-3 py-1.5 text-sm">
                    <span className="w-[76px] font-semibold text-ink tabular">{fmtNight(n.stay_date)}</span>
                    <span className="text-body">{t("left", { count: n.properties ?? 0 })}</span>
                    <span className={cx("tabular", pct <= DROP_PCT ? "font-semibold text-warning-deep" : "text-muted")}>{t("change", { pct: fmtPct(pct, { signed: true, digits: 0 }) })}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

// ---- Trang ----

function RadarView() {
  const t = useTranslations("radar.page");
  const { fmtNight } = useFmt();
  const { start, end, days, ready } = useDateRange(DEFAULT_DAYS);

  return (
    <>
      <SubTabs items={COMPETITOR_TABS} />
      <PageStrip
        title={t("title")}
        meta={<span>{t("nights", { count: days, start: fmtNight(start) })}</span>}
        aside={<span>{t("source")}</span>}
        actions={<DateRangePicker defaultDays={DEFAULT_DAYS} />}
      />
      {!ready ? (
        <SkeletonBlock className="h-[420px] w-full rounded-[10px]" />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="xl:col-span-2">
            <PromotionsCard start={start} end={end} />
          </div>
          <RestrictionsCard start={start} end={end} />
          <ScarcityCard start={start} end={end} />
          <div className="xl:col-span-2">
            <CancellationCard start={start} end={end} />
          </div>
        </div>
      )}
    </>
  );
}

export default function RadarPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[420px] w-full rounded-[10px]" />}>
      <RadarView />
    </Suspense>
  );
}
