"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { api, cellState, type DateCell } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { daysBetween, isWeekend, num, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { useLabel } from "@/lib/labels";
import { hotelTitle } from "@/lib/hotels";
import { usePlaceName } from "@/lib/place-names";
import { LOW_ROOMS } from "@/lib/market-metrics";
import { definitelyAtMost, roomsLeftOf, roomsLeftText } from "@/lib/rooms-left";
import { Card, ErrorBox, PageHeader, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "@/components/ui";
import { ListingChips } from "@/components/listing-chip";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { NightChangeLog } from "@/components/night-change-log";
import { ChangeSummaryCard } from "@/components/change-summary";
import { MarkSwatch, PromoDot, useMarks } from "@/components/marks";
import { holidayMap } from "@/components/holiday-mark";
import { Board } from "../../overview/board";
import { ScanHotelButton } from "@/components/scan-hotel-button";
import { IconArrowDown, IconArrowUp, IconStar } from "@/components/icons";

/** Kỳ xem mặc định (như mọi màn) và cửa sổ thẻ "7 ngày qua". */
const DEFAULT_DAYS = 14;
const SUMMARY_DAYS = 7;

type Col = {
  key: string;
  label: string;
  right?: boolean;
  /** Ẩn cột khi mọi đêm đều trống. */
  optional?: (m: DateCell) => unknown;
  render: (m: DateCell) => ReactNode;
};

function PriceCell({ m, lo, hi }: { m: DateCell; lo: number; hi: number }) {
  const { fmtMoney } = useFmt();
  const v = num(m.min_price);
  if (v === null) return <span className="text-faint">—</span>;
  const pct = hi > lo ? (v - lo) / (hi - lo) : 0.5;
  return (
    <span className="inline-flex items-center justify-end gap-2.5">
      <span aria-hidden className="relative hidden h-1.5 w-16 rounded-full bg-sunken sm:inline-block">
        <span className="absolute inset-y-0 left-0 rounded-full bg-[#b7bfcc]" style={{ width: `${Math.max(6, pct * 100)}%` }} />
      </span>
      <span className="font-semibold text-ink">{fmtMoney(m.min_price, m.currency)}</span>
    </span>
  );
}

function Change7d({ v }: { v: string | null }) {
  const { fmtPct } = useFmt();
  const n = num(v);
  if (n === null) return <span className="text-faint">—</span>;
  if (n === 0) return <span className="text-muted">0%</span>;
  return (
    <span className={cx("inline-flex items-center gap-0.5 font-semibold", n < 0 ? "text-warning-deep" : "text-ink")}>
      {n > 0 ? <IconArrowUp size={13} /> : <IconArrowDown size={13} />}
      {fmtPct(Math.abs(n))}
    </span>
  );
}

function HotelView() {
  const t = useTranslations("hotels.detail");
  const { fmtCompact, fmtDayTime, fmtInt, fmtNight, fmtNightRel, fmtNum, fmtPct } = useFmt();
  const label = useLabel();
  const place = usePlaceName();
  const { cellMark, promoText } = useMarks();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const hotelId = Number(id);
  const { isOperator } = useSession();
  const { start, end } = useDateRange(DEFAULT_DAYS);
  const today = useTenantToday();
  const fresh = useDataFreshness();
  const { data, error, loading } = useApi(Number.isFinite(hotelId) ? `hotel:${hotelId}:${start}:${end}` : null, () => api.hotel(hotelId, { start, end }));
  const summary = useApi(Number.isFinite(hotelId) ? `events:summary:${SUMMARY_DAYS}:${hotelId}` : null, () => api.eventsSummary({ days: SUMMARY_DAYS, hotel_id: hotelId }));
  // Ngày lễ của kỳ đang xem (theo nước của tenant) để đánh dấu trên dải ô.
  const holidays = useApi(`hotel:holidays:${start}:${end}`, () => api.market.holidays({ start, end }));
  const holidayOn = holidayMap(holidays.data);

  const title = data ? hotelTitle(data.hotel, data.label) : t("fallbackTitle");
  const isSelf = data?.role === "self";
  const metrics = data?.metrics ?? [];
  const prices = metrics.map((m) => num(m.min_price)).filter((v): v is number => v !== null);
  const lo = prices.length ? Math.min(...prices) : 0;
  const hi = prices.length ? Math.max(...prices) : 0;
  // Hết phòng chỉ đếm `sold_out`; hạn chế (min-stay, đóng ngày đến) đếm riêng.
  const soldOut = metrics.filter((m) => cellState(m) === "sold_out").length;
  const restricted = metrics.filter((m) => cellState(m) === "restricted").length;
  const tight = metrics.filter((m) => cellState(m) === "available" && definitelyAtMost(m, LOW_ROOMS)).length;
  // "Đêm nay / Còn N ngày" tính từ hôm nay của tenant, không dùng `days_to_arrival` lưu lúc quan sát (D9).
  const relOf = (m: DateCell) => {
    const d = today ? daysBetween(today, m.stay_date) : m.days_to_arrival;
    return d !== null && d >= 0 ? fmtNightRel(d) : null;
  };
  const lastObs = metrics.reduce<string | null>((acc, m) => (m.last_observed_at && (!acc || m.last_observed_at > acc) ? m.last_observed_at : acc), null);

  const cols: Col[] = [
    {
      key: "rooms",
      label: t("cols.rooms"),
      render: (m) => {
        const mark = cellMark(m, !!data && m.stay_date > data.horizon_end);
        const state = cellState(m);
        const left = roomsLeftOf(m);
        return (
          <span className="inline-flex items-center gap-2.5" title={mark.label}>
            <span className="relative">
              {/* Số đã ghi ngay bên cạnh: ô chỉ giữ màu, không nhồi "80–99" vào ô 26px. */}
              <MarkSwatch mark={{ ...mark, text: "" }} size={26} />
              <PromoDot promo={mark.promo} />
            </span>
            <span className={cx("text-sm", state === "restricted" ? "font-semibold text-warning-deep" : "text-body", m.stale && "text-faint")}>
              {state === "sold_out"
                ? t("rooms.soldOut")
                : state === "restricted"
                  ? (m.min_stay ?? 1) > 1
                    ? t("rooms.minStay", { count: m.min_stay ?? 2 })
                    : t("rooms.restricted")
                  : state === "no_price"
                    ? t("rooms.noPrice")
                    : state === "error"
                      ? t("rooms.unreadable")
                      : state === null
                        ? t("rooms.none")
                        : left === null
                          ? <><span className="sm:hidden">{t("rooms.hiddenShort")}</span><span className="max-sm:hidden">{t("rooms.hidden")}</span></>
                          : left.exact !== null
                            ? t("rooms.count", { count: left.exact })
                            : t("rooms.countText", { rooms: roomsLeftText(left) })}
              {m.stale && <span className="block text-2xs font-normal text-muted max-sm:hidden">{t("rooms.stale")}</span>}
            </span>
          </span>
        );
      },
    },
    { key: "price", label: t("cols.price"), right: true, render: (m) => <PriceCell m={m} lo={lo} hi={hi} /> },
    {
      key: "promo",
      label: t("cols.promo"),
      optional: (m) => promoText(m),
      render: (m) => {
        const p = promoText(m);
        return p ? (
          <span className="inline-block max-w-[220px] truncate rounded-full bg-[#fce7f3] px-2 py-0.5 text-xs font-semibold text-[#9d174d]" title={p}>
            {p}
          </span>
        ) : (
          <span className="text-faint">—</span>
        );
      },
    },
    { key: "chg", label: t("cols.change7d"), right: true, optional: (m) => m.price_change_7d_pct, render: (m) => <Change7d v={m.price_change_7d_pct} /> },
    { key: "pickup", label: t("cols.pickup24h"), right: true, optional: (m) => m.pickup_24h, render: (m) => fmtInt(m.pickup_24h) },
    { key: "vel", label: t("cols.velocity3d"), right: true, optional: (m) => m.velocity_3d, render: (m) => fmtNum(m.velocity_3d, 2) },
    { key: "sold", label: t("cols.soldOutAt"), optional: (m) => m.sold_out_at, render: (m) => fmtDayTime(m.sold_out_at) },
    { key: "rest", label: t("cols.restockedAt"), optional: (m) => m.restocked_at, render: (m) => fmtDayTime(m.restocked_at) },
    // Cột kỹ thuật chỉ cho operator: người dùng khách sạn đã thấy mức tin cậy qua dấu ô.
    ...(isOperator
      ? [{ key: "exact", label: t("cols.exactShare"), right: true, optional: (m: DateCell) => m.exact_share, render: (m: DateCell) => (m.exact_share === null ? "—" : fmtPct(Number(m.exact_share) * 100, { digits: 0 })) }]
      : []),
    // Tuổi dữ liệu cho mọi vai trò (roadmap 1.13): quan sát cũ hơn 48 giờ tô đỏ, không vào trung vị compset.
    {
      key: "obs",
      label: t("cols.observedAt"),
      render: (m: DateCell) => (
        <span className={m.stale ? "font-semibold text-danger" : "text-muted"} title={m.stale ? t("rooms.stale") : undefined}>
          {fmtDayTime(m.last_observed_at)}
        </span>
      ),
    },
  ];
  const visibleCols = cols.filter((c) => !c.optional || metrics.some((m) => c.optional!(m) !== null && c.optional!(m) !== undefined));

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/competitors", label: isSelf ? t("crumbSelf") : t("crumb") }, { label: title }]}
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            {isSelf && <span aria-hidden className="h-3 w-3 rounded-full bg-yours shadow-[0_0_0_3px_rgba(0,176,144,0.18)]" />}
            {title}
            {data && (
              <span className={cx("rounded-full px-2.5 py-0.5 text-sm font-semibold", isSelf ? "bg-yours-soft text-yours-deep" : "bg-sunken text-muted")}>
                {label("watchRole", data.role)}
              </span>
            )}
          </span>
        }
        subtitle={
          data && (
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {data.hotel.name && data.label && data.hotel.name !== data.label && <span>{data.hotel.name}</span>}
              {data.hotel.city && <span>{place(data.hotel.city)}</span>}
              {data.hotel.star_rating && (
                <span className="inline-flex items-center gap-1">
                  <IconStar size={14} className="text-[#e0a100]" /> {t("stars", { stars: fmtNum(data.hotel.star_rating, 1) })}
                </span>
              )}
            </span>
          )
        }
        actions={
          <>
            <DateRangePicker defaultDays={DEFAULT_DAYS} />
            {data && <ScanHotelButton hotelId={data.hotel.id} />}
          </>
        }
        meta={data && <ListingChips listings={data.hotel.listings} />}
      />
      <ErrorBox error={error} className="mb-4" />
      {!data && !error && (
        <div className="space-y-4" aria-busy>
          <SkeletonBlock className="h-[92px] w-full rounded-xl" />
          <SkeletonBlock className="h-[520px] w-full rounded-xl" />
        </div>
      )}
      {data && (
        <div className={cx("space-y-5 transition-opacity duration-200", loading && "opacity-60")}>
          <ChangeSummaryCard summary={summary.data?.[0] ?? null} days={SUMMARY_DAYS} stale={fresh.stale} error={summary.error} loading={summary.loading} />
          <StatStrip
            items={[
              {
                label: t("stats.soldOut"),
                value: t("stats.nights", { count: soldOut }),
                hint: restricted > 0 ? `${t("stats.soldOutHint", { count: metrics.length })} · ${t("stats.restricted", { count: restricted })}` : t("stats.soldOutHint", { count: metrics.length }),
                tone: soldOut > 0 && !isSelf ? "warn" : "default",
              },
              { label: t("stats.tight"), value: t("stats.nights", { count: tight }), hint: t("stats.tightHint") },
              {
                label: t("stats.priceRange"),
                value: prices.length ? `${fmtCompact(lo)} – ${fmtCompact(hi)}` : "—",
                hint: metrics.find((m) => m.currency)?.currency ?? undefined,
              },
              { label: t("stats.lastObserved"), value: lastObs ? fmtDayTime(lastObs) : "—", hint: t("stats.lastObservedHint", { count: data.events.length }) },
              {
                label: t("stats.capacity"),
                value: data.hotel.rooms_total ? t("stats.roomsTotal", { count: data.hotel.rooms_total }) : "—",
                hint: [
                  data.hotel.booking_rooms_max_seen ? t("stats.bookingMax", { count: data.hotel.booking_rooms_max_seen }) : null,
                  data.hotel.rooms_total ? (data.hotel.rooms_total_source ? t("stats.sourced") : t("stats.unsourced")) : t("stats.enterRooms"),
                ]
                  .filter(Boolean)
                  .join(" · "),
              },
            ]}
          />

          <Board
            market={false}
            data={{
              start,
              end,
              channel: data.channel,
              horizon_end: data.horizon_end,
              hotels: [{ hotel: data.hotel, role: data.role, label: data.label, cells: metrics }],
              compset: [],
              holidays: holidays.data ?? [],
              last_run: null,
            }}
          />

          <Card title={t("nights.title")} description={t("nights.description")} padded={false}>
            <Table dense>
              <thead>
                <tr>
                  <Th className="pl-5">{t("nights.night")}</Th>
                  {visibleCols.map((c) => (
                    <Th key={c.key} right={c.right}>
                      {c.label}
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => {
                  const href = `/hotels/${hotelId}/dates/${m.stay_date}`;
                  return (
                    <tr key={m.stay_date} className={cx(ROW_CLASS, "cursor-pointer", isWeekend(m.stay_date) && "bg-subtle")} onClick={() => router.push(href)}>
                      <Td className="whitespace-nowrap pl-5">
                        <Link href={href} onClick={(e) => e.stopPropagation()} className={cx("text-ink hover:text-brand hover:underline", isWeekend(m.stay_date) ? "font-extrabold" : "font-semibold")}>
                          {fmtNight(m.stay_date)}
                        </Link>
                        <span className="text-xs text-muted max-sm:block sm:ml-2">{relOf(m)}</span>
                        {holidayOn.get(m.stay_date) && <span className="block text-2xs font-semibold text-ink">{holidayOn.get(m.stay_date)?.name}</span>}
                      </Td>
                      {visibleCols.map((c) => (
                        <Td key={c.key} right={c.right} className="whitespace-nowrap">
                          {c.render(m)}
                        </Td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </Card>

          <NightChangeLog events={data.events} hotelId={data.hotel.id} today={today} />
        </div>
      )}
    </>
  );
}

export default function HotelPage() {
  return (
    <Suspense fallback={null}>
      <HotelView />
    </Suspense>
  );
}
