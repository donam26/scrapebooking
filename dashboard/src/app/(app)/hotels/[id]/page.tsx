"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { fmtDate, fmtDateShort, fmtDayTime, fmtInt, fmtMoney, fmtNum, fmtPct, fmtWeekday, isWeekend } from "@/lib/format";
import { AVAILABILITY_LABEL, AVAILABILITY_TONE, WATCH_ROLE_LABEL } from "@/lib/labels";
import { Badge, Card, ErrorBox, PageHeader, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { EventTable } from "@/components/event-table";

function HotelView() {
  const { id } = useParams<{ id: string }>();
  const hotelId = Number(id);
  const { start, end } = useDateRange();
  const { data, error, loading } = useApi(Number.isFinite(hotelId) ? `hotel:${hotelId}:${start}:${end}` : null, () => api.hotel(hotelId, { start, end }));

  const title = data ? data.label || data.hotel.name || data.hotel.booking_slug : "Khách sạn";
  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {title}
            {data && <Badge tone={data.role === "self" ? "blue" : "gray"}>{WATCH_ROLE_LABEL[data.role] ?? data.role}</Badge>}
          </span>
        }
        subtitle={
          data && (
            <span className="flex flex-wrap gap-x-3">
              {data.hotel.name && data.label && <span>{data.hotel.name}</span>}
              {data.hotel.city && <span>{data.hotel.city}</span>}
              {data.hotel.star_rating && <span>{fmtNum(data.hotel.star_rating, 1)} sao</span>}
              <a href={data.hotel.booking_url} target="_blank" rel="noreferrer" className="text-sky-700 hover:underline">
                Trang Booking ↗
              </a>
              <Link href="/overview" className="text-sky-700 hover:underline">
                ← Tổng quan
              </Link>
            </span>
          )
        }
        actions={<DateRangePicker />}
      />
      <ErrorBox error={error} className="mb-4" />
      {!data && !error && <Skeleton rows={10} />}
      {data && (
        <div className={cx("space-y-4 transition-opacity", loading && "opacity-60")}>
          <Card title={`Chỉ số theo ngày (${fmtDate(start)} – ${fmtDate(end)})`} padded={false}>
            <Table dense>
              <thead>
                <tr>
                  <Th>Ngày lưu trú</Th>
                  <Th>Trạng thái</Th>
                  <Th right>Phòng còn</Th>
                  <Th right>Giá thấp nhất</Th>
                  <Th right>Pickup 24h</Th>
                  <Th right>Tốc độ 3 ngày</Th>
                  <Th right>Giá đổi 7 ngày</Th>
                  <Th right>Quan sát chính xác</Th>
                  <Th>Hết phòng lúc</Th>
                  <Th>Có lại lúc</Th>
                  <Th>Quan sát gần nhất</Th>
                </tr>
              </thead>
              <tbody>
                {data.metrics.map((m) => {
                  const st = m.availability_status;
                  return (
                    <tr key={m.stay_date} className={cx("hover:bg-slate-50", isWeekend(m.stay_date) && "bg-slate-50/60")}>
                      <Td className="whitespace-nowrap">
                        <Link href={`/hotels/${hotelId}/dates/${m.stay_date}`} className="text-sky-700 hover:underline">
                          {fmtWeekday(m.stay_date)} {fmtDateShort(m.stay_date)}
                        </Link>
                        {m.days_to_arrival !== null && <span className="ml-1 text-xs text-slate-400">D-{m.days_to_arrival}</span>}
                      </Td>
                      <Td>{st ? <Badge tone={AVAILABILITY_TONE[st] ?? "gray"}>{AVAILABILITY_LABEL[st] ?? st}</Badge> : <span className="text-slate-400">Chưa có</span>}</Td>
                      <Td right>{fmtInt(m.exact_rooms_left)}</Td>
                      <Td right className="whitespace-nowrap">
                        {fmtMoney(m.min_price, m.currency)}
                      </Td>
                      <Td right>{fmtInt(m.pickup_24h)}</Td>
                      <Td right>{fmtNum(m.velocity_3d, 2)}</Td>
                      <Td right className={cx((m.price_change_7d_pct ?? "").startsWith("-") ? "text-violet-700" : Number(m.price_change_7d_pct) > 0 ? "text-sky-700" : "")}>
                        {fmtPct(m.price_change_7d_pct, { signed: true })}
                      </Td>
                      <Td right>{m.exact_share === null ? "—" : fmtPct(Number(m.exact_share) * 100, { digits: 0 })}</Td>
                      <Td className="whitespace-nowrap text-slate-600">{fmtDayTime(m.sold_out_at)}</Td>
                      <Td className="whitespace-nowrap text-slate-600">{fmtDayTime(m.restocked_at)}</Td>
                      <Td className="whitespace-nowrap text-slate-600">{fmtDayTime(m.last_observed_at)}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </Card>
          <Card title={`Dòng thời gian sự kiện (${data.events.length} gần nhất)`} padded={false}>
            <EventTable events={data.events} showHotel={false} />
          </Card>
        </div>
      )}
    </>
  );
}

export default function HotelPage() {
  return (
    <Suspense fallback={<Skeleton rows={10} />}>
      <HotelView />
    </Suspense>
  );
}
