"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { notFound, useParams, useRouter } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { api, type DateCell } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { isWeekend, num, useFmt } from "@/lib/format";
import { parseIdParam } from "@/lib/params";
import { useLabel } from "@/lib/labels";
import { channelName, hotelTitle, sortChannels, withChannel } from "@/lib/channels";
import { Card, ErrorBox, PageHeader, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "@/components/ui";
import { ChannelSwitcher, DemandSignals, ListingChips, useChannelParam } from "@/components/channels";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { EventTable } from "@/components/event-table";
import { MarkSwatch, useMarks } from "@/components/marks";
import { Board } from "../../overview/board";
import { ScanHotelButton } from "@/components/scan-hotel-button";
import { IconArrowDown, IconArrowUp, IconStar } from "@/components/icons";

/** Kênh xem được của khách sạn: listing đã kiểm tra (kể cả đang tạm dừng, có lịch sử), theo thứ tự cố định. */
function viewableChannels(listings: Array<{ channel: string; status: string }>, current: string): string[] {
  return sortChannels([...listings.filter((l) => l.status !== "suggested" && l.status !== "unverified").map((l) => l.channel), current]);
}

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
  const { cellMark } = useMarks();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const hotelId = parseIdParam(id);
  const { isOperator } = useSession();
  const { start, end } = useDateRange();
  const [channelParam, setChannel] = useChannelParam();
  const { data, error, loading } = useApi(hotelId === null ? null : `hotel:${hotelId}:${start}:${end}:${channelParam ?? ""}`, () =>
    api.hotel(hotelId!, { start, end, channel: channelParam }),
  );
  // id không phải số nguyên dương: trang 404 thay vì skeleton xoay mãi (gọi sau mọi hook để thứ tự hook không đổi).
  if (hotelId === null) notFound();

  const title = data ? hotelTitle(data.hotel, data.label) : t("fallbackTitle");
  const channel = data?.channel ?? null;
  const isSelf = data?.role === "self";
  const metrics = data?.metrics ?? [];
  const prices = metrics.map((m) => num(m.min_price)).filter((v): v is number => v !== null);
  const lo = prices.length ? Math.min(...prices) : 0;
  const hi = prices.length ? Math.max(...prices) : 0;
  const soldOut = metrics.filter((m) => m.availability_status === "sold_out").length;
  const tight = metrics.filter((m) => m.exact_rooms_left !== null && m.exact_rooms_left <= 3).length;
  const lastObs = metrics.reduce<string | null>((acc, m) => (m.last_observed_at && (!acc || m.last_observed_at > acc) ? m.last_observed_at : acc), null);

  const cols: Col[] = [
    {
      key: "rooms",
      label: t("cols.rooms"),
      render: (m) => {
        const mark = cellMark(m, !!data && m.stay_date > data.horizon_end);
        return (
          <span className="inline-flex items-center gap-2.5" title={mark.label}>
            <MarkSwatch mark={mark} size={26} />
            <span className="text-sm text-body">
              {m.availability_status === "sold_out"
                ? t("rooms.soldOut")
                : m.availability_status === "unknown"
                  ? t("rooms.unreadable")
                  : m.availability_status === null
                    ? t("rooms.none")
                    : m.exact_rooms_left === null
                      ? <><span className="sm:hidden">{t("rooms.hiddenShort")}</span><span className="max-sm:hidden">{t("rooms.hidden")}</span></>
                      : t("rooms.count", { count: m.exact_rooms_left })}
            </span>
          </span>
        );
      },
    },
    { key: "price", label: t("cols.price"), right: true, render: (m) => <PriceCell m={m} lo={lo} hi={hi} /> },
    { key: "chg", label: t("cols.change7d"), right: true, optional: (m) => m.price_change_7d_pct, render: (m) => <Change7d v={m.price_change_7d_pct} /> },
    { key: "pickup", label: t("cols.pickup24h"), right: true, optional: (m) => m.pickup_24h, render: (m) => fmtInt(m.pickup_24h) },
    { key: "vel", label: t("cols.velocity3d"), right: true, optional: (m) => m.velocity_3d, render: (m) => fmtNum(m.velocity_3d, 2) },
    { key: "sold", label: t("cols.soldOutAt"), optional: (m) => m.sold_out_at, render: (m) => fmtDayTime(m.sold_out_at) },
    { key: "rest", label: t("cols.restockedAt"), optional: (m) => m.restocked_at, render: (m) => fmtDayTime(m.restocked_at) },
    // Hai cột kỹ thuật chỉ cho operator: người dùng khách sạn đã thấy mức tin cậy qua dấu ô.
    ...(isOperator
      ? [
          { key: "exact", label: t("cols.exactShare"), right: true, optional: (m: DateCell) => m.exact_share, render: (m: DateCell) => (m.exact_share === null ? "—" : fmtPct(Number(m.exact_share) * 100, { digits: 0 })) },
          { key: "obs", label: t("cols.observedAt"), render: (m: DateCell) => <span className="text-muted">{fmtDayTime(m.last_observed_at)}</span> },
        ]
      : []),
  ];
  const visibleCols = cols.filter((c) => !c.optional || metrics.some((m) => c.optional!(m) !== null && c.optional!(m) !== undefined));

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/competitors", label: t("crumb") }, { label: title }]}
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
              {data.hotel.city && <span>{data.hotel.city}</span>}
              {data.hotel.star_rating && (
                <span className="inline-flex items-center gap-1">
                  <IconStar size={14} className="text-[#e0a100]" /> {t("stars", { stars: fmtNum(data.hotel.star_rating, 1) })}
                </span>
              )}
              <span>
                {t.rich("dataOn", { channel: channelName(data.channel), b: (c) => <span className="font-semibold text-body">{c}</span> })}
              </span>
            </span>
          )
        }
        actions={
          <>
            {data && <ChannelSwitcher channels={viewableChannels(data.hotel.listings, data.channel)} value={data.channel} onChange={setChannel} />}
            <DateRangePicker />
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
          <StatStrip
            items={[
              { label: t("stats.soldOut"), value: t("stats.nights", { count: soldOut }), hint: t("stats.soldOutHint", { count: metrics.length }), tone: soldOut > 0 && !isSelf ? "warn" : "default" },
              { label: t("stats.tight"), value: t("stats.nights", { count: tight }), hint: t("stats.tightHint", { channel: channelName(channel) }) },
              {
                label: t("stats.priceRange"),
                value: prices.length ? `${fmtCompact(lo)} – ${fmtCompact(hi)}` : "—",
                hint: metrics.find((m) => m.currency)?.currency ?? undefined,
              },
              { label: t("stats.lastObserved"), value: lastObs ? fmtDayTime(lastObs) : "—", hint: t("stats.lastObservedHint", { count: data.events.length }) },
            ]}
          />

          <DemandSignals signals={data.demand_signals} isOperator={isOperator} />

          <Board
            market={false}
            data={{
              start,
              end,
              channel: data.channel,
              channels: [data.channel],
              horizon_end: data.horizon_end,
              hotels: [{ hotel: data.hotel, role: data.role, label: data.label, cells: metrics }],
              compset: [],
              holidays: [],
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
                  const href = withChannel(`/hotels/${hotelId}/dates/${m.stay_date}`, channel);
                  return (
                    <tr key={m.stay_date} className={cx(ROW_CLASS, "cursor-pointer", isWeekend(m.stay_date) && "bg-subtle")} onClick={() => router.push(href)}>
                      <Td className="whitespace-nowrap pl-5">
                        <Link href={href} onClick={(e) => e.stopPropagation()} className={cx("text-ink hover:text-brand hover:underline", isWeekend(m.stay_date) ? "font-extrabold" : "font-semibold")}>
                          {fmtNight(m.stay_date)}
                        </Link>
                        <span className="text-xs text-muted max-sm:block sm:ml-2">{fmtNightRel(m.days_to_arrival)}</span>
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

          <Card title={t("events.title")} description={t("events.description", { count: data.events.length })} padded={false}>
            <EventTable events={data.events} showHotel={false} emptyText={t("events.empty")} />
          </Card>
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
