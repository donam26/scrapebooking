"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, type RoomSnapshotOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { fmtCompact, fmtDate, fmtDateTime, fmtDayTime, fmtInt, fmtMoney, fmtWeekday, num } from "@/lib/format";
import { AVAILABILITY_LABEL, AVAILABILITY_TONE, STOCK_CONFIDENCE_LABEL, STOCK_CONFIDENCE_TONE } from "@/lib/labels";
import { Badge, Card, EmptyState, ErrorBox, Field, PageHeader, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { EventTable } from "@/components/event-table";
import { LineChart, type Series } from "@/components/line-chart";

const HISTORY_OPTIONS = [7, 14, 30, 60] as const;

/** Rate plan trong `rates` (jsonb): name, price (chuỗi), currency, refundable, breakfast. */
type Rate = { name?: unknown; price?: unknown; currency?: unknown; refundable?: unknown; breakfast?: unknown };

function RateList({ rates, currency }: { rates: Record<string, unknown>[]; currency: string | null }) {
  if (rates.length === 0) return <span className="text-slate-400">—</span>;
  return (
    <ul className="space-y-0.5 text-xs">
      {rates.map((raw, i) => {
        const r = raw as Rate;
        const price = typeof r.price === "string" || typeof r.price === "number" ? r.price : null;
        const cur = typeof r.currency === "string" ? r.currency : currency;
        return (
          <li key={i} className="flex flex-wrap items-center gap-1.5">
            <span className="tabular font-medium text-slate-800">{fmtMoney(price, cur)}</span>
            <span className="text-slate-600">{typeof r.name === "string" ? r.name : ""}</span>
            {r.refundable === true && <Badge tone="green">Hoàn huỷ</Badge>}
            {r.refundable === false && <Badge tone="gray">Không hoàn</Badge>}
            {r.breakfast === true && <Badge tone="amber">Bữa sáng</Badge>}
          </li>
        );
      })}
    </ul>
  );
}

function roomsLeftText(s: RoomSnapshotOut): string {
  if (s.stock_confidence === "sold_out") return "0";
  if (s.stock_confidence === "capped") return `≥ ${fmtInt(s.rooms_left ?? s.dropdown_max)}`;
  if (s.stock_confidence === "hidden") return "còn phòng";
  return fmtInt(s.rooms_left);
}

export default function DayDetailPage() {
  const { id, date } = useParams<{ id: string; date: string }>();
  const hotelId = Number(id);
  const valid = Number.isFinite(hotelId) && /^\d{4}-\d{2}-\d{2}$/.test(date);
  const [historyDays, setHistoryDays] = useState<number>(14);
  const { data, error, loading } = useApi(valid ? `day:${hotelId}:${date}:${historyDays}` : null, () => api.day(hotelId, date, historyDays));

  const roomName = (rtId: number) => data?.room_types.find((r) => r.id === rtId)?.name ?? `Loại phòng #${rtId}`;

  // Lịch sử theo loại phòng -> hai biểu đồ (một trục mỗi biểu đồ).
  const byRoom = new Map<number, RoomSnapshotOut[]>();
  for (const s of data?.history ?? []) {
    const arr = byRoom.get(s.room_type_id);
    if (arr) arr.push(s);
    else byRoom.set(s.room_type_id, [s]);
  }
  const roomsSeries: Series[] = [];
  const priceSeries: Series[] = [];
  for (const [rtId, snaps] of byRoom) {
    roomsSeries.push({
      id: rtId,
      name: roomName(rtId),
      points: snaps.flatMap((s) => (s.rooms_left === null ? [] : [{ x: Date.parse(s.scanned_at), y: s.rooms_left }])),
    });
    priceSeries.push({
      id: rtId,
      name: roomName(rtId),
      points: snaps.flatMap((s) => {
        const p = num(s.min_price);
        return p === null ? [] : [{ x: Date.parse(s.scanned_at), y: p }];
      }),
    });
  }
  const currency = data?.latest[0]?.currency ?? data?.history[0]?.currency ?? null;
  const latestAt = data?.latest[0]?.scanned_at ?? null;
  const hotelTitle = data ? data.hotel.name || data.hotel.booking_slug : "Khách sạn";

  return (
    <>
      <PageHeader
        title={valid ? `${fmtWeekday(date)} ${fmtDate(date)}` : "Ngày không hợp lệ"}
        subtitle={
          <span className="flex flex-wrap gap-x-3">
            <Link href={`/hotels/${hotelId}`} className="text-sky-700 hover:underline">
              ← {hotelTitle}
            </Link>
            {data?.hotel.city && <span>{data.hotel.city}</span>}
            {latestAt && <span>Quét gần nhất: {fmtDateTime(latestAt)}</span>}
          </span>
        }
        actions={
          <Field label="Lịch sử">
            <Select value={historyDays} onChange={(e) => setHistoryDays(Number(e.target.value))}>
              {HISTORY_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d} ngày
                </option>
              ))}
            </Select>
          </Field>
        }
      />
      <ErrorBox error={error} className="mb-4" />
      {!data && !error && <Skeleton rows={10} />}
      {data && (
        <div className={cx("space-y-4 transition-opacity", loading && "opacity-60")}>
          <Card title="Loại phòng ở lần quét gần nhất" padded={false}>
            {data.latest.length === 0 ? (
              <div className="p-4">
                <EmptyState>Không có snapshot nào trong {historyDays} ngày qua.</EmptyState>
              </div>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Loại phòng</Th>
                    <Th right>Phòng còn</Th>
                    <Th>Độ tin cậy</Th>
                    <Th right>Giá thấp nhất</Th>
                    <Th right>Giá hoàn huỷ thấp nhất</Th>
                    <Th>Rate plan</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.latest.map((s) => (
                    <tr key={s.id} className="hover:bg-slate-50">
                      <Td>
                        <div className="font-medium">{roomName(s.room_type_id)}</div>
                        {(() => {
                          const rt = data.room_types.find((r) => r.id === s.room_type_id);
                          return rt?.max_occupancy ? <div className="text-xs text-slate-500">Tối đa {rt.max_occupancy} khách</div> : null;
                        })()}
                      </Td>
                      <Td right className="font-medium">
                        {roomsLeftText(s)}
                      </Td>
                      <Td>
                        <Badge tone={STOCK_CONFIDENCE_TONE[s.stock_confidence] ?? "gray"} title={s.badge_count !== null ? `Badge: ${s.badge_count}` : s.dropdown_max !== null ? `Dropdown tối đa ${s.dropdown_max}` : undefined}>
                          {STOCK_CONFIDENCE_LABEL[s.stock_confidence] ?? s.stock_confidence}
                        </Badge>
                      </Td>
                      <Td right className="whitespace-nowrap">
                        {fmtMoney(s.min_price, s.currency)}
                      </Td>
                      <Td right className="whitespace-nowrap">
                        {fmtMoney(s.min_refundable_price, s.currency)}
                      </Td>
                      <Td>
                        <RateList rates={s.rates} currency={s.currency} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Số phòng còn theo lần quét">
              <LineChart series={roomsSeries} zeroBased formatY={(v) => fmtInt(Math.round(v))} formatX={(v) => fmtDayTime(new Date(v).toISOString())} emptyText="Chưa có số phòng chính xác trong khoảng này" />
            </Card>
            <Card title={`Giá thấp nhất theo lần quét${currency ? ` (${currency})` : ""}`}>
              <LineChart series={priceSeries} formatY={(v) => fmtCompact(v)} formatX={(v) => fmtDayTime(new Date(v).toISOString())} emptyText="Chưa có giá trong khoảng này" />
            </Card>
          </div>

          <Card title={`Dòng thời gian quan sát (${data.observations.length})`} padded={false}>
            {data.observations.length === 0 ? (
              <div className="p-4">
                <EmptyState>Chưa có quan sát nào.</EmptyState>
              </div>
            ) : (
              <Table dense>
                <thead>
                  <tr>
                    <Th>Thời điểm quét</Th>
                    <Th>Đợt</Th>
                    <Th>Trạng thái</Th>
                    <Th right>Phòng còn (chính xác)</Th>
                    <Th right>Loại phòng còn</Th>
                    <Th right>Loại phòng hết</Th>
                    <Th right>Giá thấp nhất</Th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.observations].reverse().map((o) => (
                    <tr key={`${o.scan_run_id}-${o.scanned_at}`} className="hover:bg-slate-50">
                      <Td className="whitespace-nowrap">{fmtDateTime(o.scanned_at)}</Td>
                      <Td className="text-slate-500">#{o.scan_run_id}</Td>
                      <Td>
                        <Badge tone={AVAILABILITY_TONE[o.status] ?? "gray"}>{AVAILABILITY_LABEL[o.status] ?? o.status}</Badge>
                      </Td>
                      <Td right>{fmtInt(o.exact_rooms_left)}</Td>
                      <Td right>{fmtInt(o.room_types_available)}</Td>
                      <Td right>{fmtInt(o.room_types_sold_out)}</Td>
                      <Td right className="whitespace-nowrap">
                        {fmtMoney(o.min_price, o.currency)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <details className="rounded-lg border border-line bg-surface shadow-xs">
            <summary className="cursor-pointer px-4 py-2.5 text-sm font-semibold text-slate-700">Bảng lịch sử theo loại phòng ({data.history.length} snapshot)</summary>
            <div className="border-t border-line">
              <Table dense>
                <thead>
                  <tr>
                    <Th>Thời điểm quét</Th>
                    <Th>Loại phòng</Th>
                    <Th right>Phòng còn</Th>
                    <Th>Độ tin cậy</Th>
                    <Th right>Giá thấp nhất</Th>
                    <Th right>Giá hoàn huỷ</Th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.history].reverse().map((s) => (
                    <tr key={s.id}>
                      <Td className="whitespace-nowrap">{fmtDateTime(s.scanned_at)}</Td>
                      <Td>{roomName(s.room_type_id)}</Td>
                      <Td right>{roomsLeftText(s)}</Td>
                      <Td>{STOCK_CONFIDENCE_LABEL[s.stock_confidence] ?? s.stock_confidence}</Td>
                      <Td right className="whitespace-nowrap">
                        {fmtMoney(s.min_price, s.currency)}
                      </Td>
                      <Td right className="whitespace-nowrap">
                        {fmtMoney(s.min_refundable_price, s.currency)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          </details>

          <Card title={`Sự kiện của ngày này (${data.events.length})`} padded={false}>
            <EventTable events={data.events} showHotel={false} />
          </Card>
        </div>
      )}
    </>
  );
}
