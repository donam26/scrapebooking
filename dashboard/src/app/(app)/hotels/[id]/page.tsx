"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { api, type DateCell } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtCompact, fmtDayTime, fmtInt, fmtMoney, fmtNight, fmtNightRel, fmtNum, fmtPct, isWeekend, num, prettySlug } from "@/lib/format";
import { WATCH_ROLE_LABEL } from "@/lib/labels";
import { ButtonLink, Card, ErrorBox, PageHeader, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "@/components/ui";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { EventTable } from "@/components/event-table";
import { cellMark, MarkSwatch } from "@/components/marks";
import { Board } from "../../overview/board";
import { IconArrowDown, IconArrowUp, IconExternal, IconStar } from "@/components/icons";

type Col = {
  key: string;
  label: string;
  right?: boolean;
  /** Ẩn cột khi mọi đêm đều trống. */
  optional?: (m: DateCell) => unknown;
  render: (m: DateCell) => ReactNode;
};

function PriceCell({ m, lo, hi }: { m: DateCell; lo: number; hi: number }) {
  const v = num(m.min_price);
  if (v === null) return <span className="text-faint">—</span>;
  const pct = hi > lo ? (v - lo) / (hi - lo) : 0.5;
  return (
    <span className="inline-flex items-center justify-end gap-2.5">
      <span aria-hidden className="relative hidden h-1.5 w-16 rounded-full bg-sunken sm:inline-block">
        <span className="absolute inset-y-0 left-0 rounded-full bg-[#b9b5d6]" style={{ width: `${Math.max(6, pct * 100)}%` }} />
      </span>
      <span className="font-semibold text-ink">{fmtMoney(m.min_price, m.currency)}</span>
    </span>
  );
}

function Change7d({ v }: { v: string | null }) {
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
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const hotelId = Number(id);
  const { isOperator } = useSession();
  const { start, end } = useDateRange();
  const { data, error, loading } = useApi(Number.isFinite(hotelId) ? `hotel:${hotelId}:${start}:${end}` : null, () => api.hotel(hotelId, { start, end }));

  const title = data ? data.label || data.hotel.name || prettySlug(data.hotel.booking_slug) : "Khách sạn";
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
      label: "Phòng còn",
      render: (m) => {
        const mark = cellMark(m);
        return (
          <span className="inline-flex items-center gap-2.5" title={mark.label}>
            <MarkSwatch mark={mark} size={26} />
            <span className="text-sm text-body">
              {m.availability_status === "sold_out"
                ? "Hết phòng"
                : m.availability_status === "unknown"
                  ? "Không đọc được"
                  : m.availability_status === null
                    ? "Chưa có"
                    : m.exact_rooms_left === null
                      ? <><span className="sm:hidden">Ẩn số</span><span className="max-sm:hidden">Còn phòng, ẩn số</span></>
                      : `${m.exact_rooms_left} phòng`}
            </span>
          </span>
        );
      },
    },
    { key: "price", label: "Giá thấp nhất", right: true, render: (m) => <PriceCell m={m} lo={lo} hi={hi} /> },
    { key: "chg", label: "Giá đổi 7 ngày", right: true, optional: (m) => m.price_change_7d_pct, render: (m) => <Change7d v={m.price_change_7d_pct} /> },
    { key: "pickup", label: "Pickup 24h", right: true, optional: (m) => m.pickup_24h, render: (m) => fmtInt(m.pickup_24h) },
    { key: "vel", label: "Tốc độ 3 ngày", right: true, optional: (m) => m.velocity_3d, render: (m) => fmtNum(m.velocity_3d, 2) },
    { key: "sold", label: "Hết phòng lúc", optional: (m) => m.sold_out_at, render: (m) => fmtDayTime(m.sold_out_at) },
    { key: "rest", label: "Có lại lúc", optional: (m) => m.restocked_at, render: (m) => fmtDayTime(m.restocked_at) },
    // Hai cột kỹ thuật chỉ cho operator: người dùng khách sạn đã thấy mức tin cậy qua dấu ô.
    ...(isOperator
      ? [
          { key: "exact", label: "Tỷ lệ số chính xác", right: true, optional: (m: DateCell) => m.exact_share, render: (m: DateCell) => (m.exact_share === null ? "—" : fmtPct(Number(m.exact_share) * 100, { digits: 0 })) },
          { key: "obs", label: "Quan sát lúc", render: (m: DateCell) => <span className="text-muted">{fmtDayTime(m.last_observed_at)}</span> },
        ]
      : []),
  ];
  const visibleCols = cols.filter((c) => !c.optional || metrics.some((m) => c.optional!(m) !== null && c.optional!(m) !== undefined));

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/overview", label: "Tổng quan" }, { label: title }]}
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            {isSelf && <span aria-hidden className="h-3 w-3 rounded-full bg-yours shadow-[0_0_0_3px_rgba(0,176,144,0.18)]" />}
            {title}
            {data && (
              <span className={cx("rounded-full px-2.5 py-0.5 text-sm font-semibold", isSelf ? "bg-yours-soft text-yours-deep" : "bg-sunken text-muted")}>
                {WATCH_ROLE_LABEL[data.role] ?? data.role}
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
                  <IconStar size={14} className="text-[#e0a100]" /> {fmtNum(data.hotel.star_rating, 1)} sao
                </span>
              )}
            </span>
          )
        }
        actions={
          <>
            {data && (
              <ButtonLink href={data.hotel.booking_url} external variant="ghost" icon={<IconExternal size={15} />}>
                Booking.com
              </ButtonLink>
            )}
            <DateRangePicker />
          </>
        }
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
              { label: "Đêm hết phòng", value: `${soldOut} đêm`, hint: `Trong ${metrics.length} đêm đang xem`, tone: soldOut > 0 && !isSelf ? "warn" : "default" },
              { label: "Đêm còn ≤ 3 phòng", value: `${tight} đêm`, hint: "Theo số Booking báo chính xác" },
              {
                label: "Giá thấp nhất mỗi đêm",
                value: prices.length ? `${fmtCompact(lo)} – ${fmtCompact(hi)}` : "—",
                hint: metrics.find((m) => m.currency)?.currency ?? undefined,
              },
              { label: "Quan sát gần nhất", value: lastObs ? fmtDayTime(lastObs) : "—", hint: `${data.events.length} sự kiện gần nhất bên dưới` },
            ]}
          />

          <Board
            market={false}
            data={{ start, end, hotels: [{ hotel: data.hotel, role: data.role, label: data.label, cells: metrics }], compset: [], last_run: null }}
          />

          <Card title="Theo từng đêm" description="Bấm một đêm để xem từng loại phòng và lịch sử quét" padded={false}>
            <Table dense>
              <thead>
                <tr>
                  <Th className="pl-5">Đêm</Th>
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

          <Card title="Sự kiện gần đây" description={`${data.events.length} thay đổi gần nhất của khách sạn này`} padded={false}>
            <EventTable events={data.events} showHotel={false} emptyText="Chưa có biến động nào được ghi nhận cho khách sạn này." />
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
