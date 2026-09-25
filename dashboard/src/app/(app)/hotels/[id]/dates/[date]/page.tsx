"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, type RoomSnapshotOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { addDays, prettySlug, fmtCompact, fmtDate, fmtDayTime, fmtInt, fmtMoney, fmtNight, fmtWeekday, fmtWhen, num } from "@/lib/format";
import { AVAILABILITY_LABEL, STOCK_CONFIDENCE_LABEL } from "@/lib/labels";
import { ButtonLink, Card, EmptyState, ErrorBox, PageHeader, ROW_CLASS, Segmented, SkeletonBlock, Table, Td, Th, cx } from "@/components/ui";
import { EventTable } from "@/components/event-table";
import { LineChart, type Series } from "@/components/line-chart";
import { cellMark, MarkChip, MarkSwatch, MarksLegend, roomMark, type Mark } from "@/components/marks";
import { IconBed, IconChevronLeft, IconChevronRight } from "@/components/icons";

const HISTORY_OPTIONS = [7, 14, 30, 60] as const;

/** Gói giá trong `rates` (jsonb): name, price (chuỗi), currency, refundable, breakfast. */
type Rate = { name?: unknown; price?: unknown; currency?: unknown; refundable?: unknown; breakfast?: unknown };

function RateList({ rates, currency, minPrice }: { rates: Record<string, unknown>[]; currency: string | null; minPrice: string | null }) {
  if (rates.length === 0) return <span className="text-faint">—</span>;
  // Một gói duy nhất cùng giá thấp nhất: không lặp lại giá.
  const single = rates.length === 1 && num((rates[0] as Rate).price as string) === num(minPrice);
  return (
    <ul className="space-y-1">
      {rates.map((raw, i) => {
        const r = raw as Rate;
        const price = typeof r.price === "string" || typeof r.price === "number" ? r.price : null;
        const cur = typeof r.currency === "string" ? r.currency : currency;
        const tags = [r.refundable === true ? "Hoàn huỷ" : r.refundable === false ? "Không hoàn" : null, r.breakfast === true ? "Bữa sáng" : null].filter(Boolean);
        return (
          <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
            {!single && <span className="font-semibold text-ink tabular">{fmtMoney(price, cur)}</span>}
            <span className="text-muted">
              {typeof r.name === "string" ? r.name : ""}
              {tags.length > 0 && <span className="text-body"> · {tags.join(" · ")}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function statusMark(status: string, exact: number | null): Mark {
  return cellMark({
    availability_status: status,
    exact_rooms_left: exact,
  } as Parameters<typeof cellMark>[0]);
}

function shortMark(m: Mark): string {
  if (m.kind === "exact") return `Còn ${m.text} phòng`;
  if (m.kind === "hidden") return "Còn phòng, ẩn số";
  if (m.kind === "sold_out") return "Hết phòng";
  if (m.kind === "unknown") return "Không đọc được";
  return "Chưa có dữ liệu";
}

/** Cùng đêm trên thị trường: mọi khách sạn trong watchlist, khách sạn đang xem được đánh dấu. */
function SameNight({ date, hotelId }: { date: string; hotelId: number }) {
  const market = useApi(`market:${date}`, () => api.overview({ start: date, end: date }));
  const d = market.data;
  const c = d?.compset.find((x) => x.stay_date === date);
  return (
    <Card title="Cùng đêm trên thị trường" description={c ? `${c.competitors_sold_out}/${c.competitors_observed} đối thủ hết phòng · trung vị ${fmtMoney(c.median_price, c.currency)}` : undefined} padded={false}>
      {!d ? (
        <div className="space-y-2 p-5">
          {[0, 1, 2, 3].map((i) => (
            <SkeletonBlock key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {d.hotels.map((h) => {
            const cell = h.cells.find((x) => x.stay_date === date);
            const mark = cellMark(cell);
            const current = h.hotel.id === hotelId;
            const name = h.label || h.hotel.name || prettySlug(h.hotel.booking_slug);
            return (
              <li key={h.hotel.id}>
                <Link
                  href={`/hotels/${h.hotel.id}/dates/${date}`}
                  aria-current={current ? "page" : undefined}
                  className={cx("flex items-center gap-3 px-5 py-2.5 transition-colors", current ? "bg-brand-softer" : "hover:bg-subtle")}
                >
                  <MarkSwatch mark={mark} size={26} />
                  <span className="min-w-0 flex-1">
                    <span className={cx("block truncate text-base", h.role === "self" ? "font-bold text-yours-deep" : current ? "font-bold text-ink" : "font-medium text-body")}>
                      {name}
                      {h.role === "self" && <span className="ml-1.5 text-xs font-semibold text-yours-deep">· của bạn</span>}
                    </span>
                    <span className="block text-xs text-muted">{shortMark(mark)}</span>
                  </span>
                  <span className="shrink-0 text-base font-semibold text-ink tabular">{fmtMoney(cell?.min_price, cell?.currency)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export default function DayDetailPage() {
  const { id, date } = useParams<{ id: string; date: string }>();
  const hotelId = Number(id);
  const valid = Number.isFinite(hotelId) && /^\d{4}-\d{2}-\d{2}$/.test(date);
  const [historyDays, setHistoryDays] = useState<number>(14);
  const { data, error, loading } = useApi(valid ? `day:${hotelId}:${date}:${historyDays}` : null, () => api.day(hotelId, date, historyDays));

  const roomName = (rtId: number) => data?.room_types.find((r) => r.id === rtId)?.name ?? `Loại phòng #${rtId}`;

  // Lịch sử theo loại phòng -> hai biểu đồ (mỗi biểu đồ một trục).
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
      points: snaps.flatMap((s) => {
        const x = Date.parse(s.scanned_at);
        if (s.stock_confidence === "sold_out") return [{ x, y: 0 }];
        if (s.stock_confidence === "capped") {
          const y = s.rooms_left ?? s.dropdown_max;
          return y === null ? [] : [{ x, y, floor: true }];
        }
        return s.rooms_left === null ? [] : [{ x, y: s.rooms_left }];
      }),
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
  // Mọi điểm đều là mức sàn "≥N": không vẽ đường giả phẳng, nói thẳng điều dữ liệu cho biết.
  const roomPts = roomsSeries.flatMap((s) => s.points);
  const onlyFloor = roomPts.length > 0 && roomPts.every((p) => p.floor);
  const floorMax = onlyFloor ? Math.max(...roomPts.map((p) => p.y)) : 0;
  const currency = data?.latest[0]?.currency ?? data?.history[0]?.currency ?? null;
  const latestAt = data?.latest_scanned_at ?? null;
  const latestStatus = data?.latest_status ?? null;
  const hotelTitle = data ? data.hotel.name || prettySlug(data.hotel.booking_slug) : "Khách sạn";
  const prev = valid ? addDays(date, -1) : null;
  const next = valid ? addDays(date, 1) : null;

  return (
    <>
      <PageHeader
        crumbs={[
          { href: "/overview", label: "Tổng quan" },
          { href: `/hotels/${hotelId}`, label: hotelTitle },
          { label: valid ? `Đêm ${fmtNight(date)}` : "Ngày không hợp lệ" },
        ]}
        title={valid ? `${fmtWeekday(date)}, ${fmtDate(date)}` : "Ngày không hợp lệ"}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold text-body">{hotelTitle}</span>
            {latestAt && (
              <span className="inline-flex items-center gap-2">
                Quét gần nhất {fmtWhen(latestAt)}
                {latestStatus && (
                  <span className="inline-flex items-center gap-1.5 text-body">
                    <MarkSwatch mark={statusMark(latestStatus, null)} size={14} className="rounded-[3px]" />
                    {AVAILABILITY_LABEL[latestStatus] ?? latestStatus}
                  </span>
                )}
              </span>
            )}
          </span>
        }
        actions={
          valid && (
            <div className="flex items-center gap-1">
              <ButtonLink href={`/hotels/${hotelId}/dates/${prev}`} variant="ghost" size="sm" icon={<IconChevronLeft size={15} />}>
                {fmtNight(prev!)}
              </ButtonLink>
              <ButtonLink href={`/hotels/${hotelId}/dates/${next}`} variant="ghost" size="sm">
                {fmtNight(next!)} <IconChevronRight size={15} />
              </ButtonLink>
            </div>
          )
        }
      />
      <ErrorBox error={error} className="mb-4" />
      {!data && !error && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]" aria-busy>
          <SkeletonBlock className="h-[420px] rounded-xl" />
          <SkeletonBlock className="h-[320px] rounded-xl" />
        </div>
      )}
      {data && (
        <div className={cx("space-y-5 transition-opacity duration-200", loading && "opacity-60")}>
          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
            <Card title="Từng loại phòng ở lượt quét gần nhất" description={data.latest.length ? `${data.latest.length} loại phòng đang mở bán cho 2 người lớn` : undefined} padded={false}>
              {data.latest.length === 0 ? (
                <div className="p-5">
                  <EmptyState icon={<IconBed />} compact>
                    {latestStatus === "sold_out"
                      ? `Lượt quét ${fmtWhen(latestAt)} ghi nhận hết phòng: không còn loại phòng nào mở bán. Xem lịch sử bên dưới.`
                      : latestStatus === "unknown"
                        ? `Lượt quét ${fmtWhen(latestAt)} không đọc được trang (bị chặn hoặc lỗi). Xem lịch sử bên dưới.`
                        : `Không có dữ liệu loại phòng trong ${historyDays} ngày qua.`}
                  </EmptyState>
                </div>
              ) : (
                <>
                  <Table>
                    <thead>
                      <tr>
                        <Th className="pl-5">Loại phòng</Th>
                        <Th>Phòng còn</Th>
                        <Th right>Giá thấp nhất</Th>
                        <Th className="hidden md:table-cell">Gói giá</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.latest.map((s) => {
                        const rt = data.room_types.find((r) => r.id === s.room_type_id);
                        const mark = roomMark(s);
                        const refundDiffers = s.min_refundable_price !== null && s.min_refundable_price !== s.min_price;
                        return (
                          <tr key={s.id} className={cx(ROW_CLASS, s.stock_confidence === "sold_out" && "opacity-60")}>
                            <Td className="min-w-[150px] pl-5 sm:min-w-[180px]">
                              <div className="font-semibold text-ink">{roomName(s.room_type_id)}</div>
                              {rt?.max_occupancy ? <div className="text-xs text-muted">Tối đa {rt.max_occupancy} khách</div> : null}
                              <div className="mt-1.5 md:hidden">
                                <RateList rates={s.rates} currency={s.currency} minPrice={s.min_price} />
                              </div>
                            </Td>
                            <Td>
                              <MarkChip mark={mark} />
                            </Td>
                            <Td right className="whitespace-nowrap">
                              <div className="font-semibold text-ink">{fmtMoney(s.min_price, s.currency)}</div>
                              {refundDiffers && <div className="text-xs text-muted">Hoàn huỷ từ {fmtMoney(s.min_refundable_price, s.currency)}</div>}
                            </Td>
                            <Td className="hidden md:table-cell">
                              <RateList rates={s.rates} currency={s.currency} minPrice={s.min_price} />
                            </Td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </Table>
                  <div className="border-t border-line px-5 py-3">
                    <MarksLegend variant="room" />
                  </div>
                </>
              )}
            </Card>
            <SameNight date={date} hotelId={hotelId} />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <h2 className="text-lg font-bold text-ink">Diễn biến qua các lượt quét</h2>
            <div className="flex items-center gap-2 text-sm text-muted">
              Xem lại
              <Segmented label="Khoảng lịch sử" size="sm" value={historyDays} onChange={setHistoryDays} items={HISTORY_OPTIONS.map((d) => ({ value: d, label: `${d} ngày` }))} />
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Số phòng còn theo lượt quét">
              {onlyFloor ? (
                <div className="flex h-[220px] flex-col items-center justify-center gap-2 rounded-lg bg-subtle px-6 text-center">
                  <MarkSwatch mark={{ kind: "capped", cls: "sb-mark-capped", text: `≥${floorMax}`, label: "" }} size={34} className="!w-auto px-1.5" />
                  <p className="max-w-sm text-base text-body">
                    Mọi loại phòng đều báo <span className="font-semibold">còn ít nhất {floorMax} phòng</span> ở mọi lượt quét. Booking không lộ số chính xác nên không có đường để vẽ.
                  </p>
                </div>
              ) : (
                <LineChart series={roomsSeries} zeroBased formatY={(v) => fmtInt(Math.round(v))} formatX={(v) => fmtDayTime(new Date(v).toISOString())} emptyText="Chưa có số phòng đếm được trong khoảng này" />
              )}
            </Card>
            <Card title={`Giá thấp nhất theo lượt quét${currency ? ` (${currency})` : ""}`}>
              <LineChart series={priceSeries} formatY={(v) => fmtCompact(v)} formatX={(v) => fmtDayTime(new Date(v).toISOString())} emptyText="Chưa có giá trong khoảng này" />
            </Card>
          </div>

          <Card title="Các lượt quét đêm này" description={`${data.observations.length} lượt trong ${historyDays} ngày qua`} padded={false}>
            {data.observations.length === 0 ? (
              <div className="p-5">
                <EmptyState compact>Chưa có lượt quét nào cho đêm này.</EmptyState>
              </div>
            ) : (
              <Table dense>
                <thead>
                  <tr>
                    <Th className="pl-5">Thời điểm quét</Th>
                    <Th>Tình trạng</Th>
                    <Th right>Phòng đếm chính xác</Th>
                    <Th right>Loại phòng còn / hết</Th>
                    <Th right>Giá thấp nhất</Th>
                    <Th right className="pr-5">
                      Lượt
                    </Th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.observations].reverse().map((o) => (
                    <tr key={`${o.scan_run_id}-${o.scanned_at}`} className={ROW_CLASS}>
                      <Td className="whitespace-nowrap pl-5 font-medium text-ink">{fmtWhen(o.scanned_at)}</Td>
                      <Td>
                        <span className="inline-flex items-center gap-2">
                          <MarkSwatch mark={statusMark(o.status, o.exact_rooms_left)} size={20} />
                          {AVAILABILITY_LABEL[o.status] ?? o.status}
                        </span>
                      </Td>
                      <Td right>{fmtInt(o.exact_rooms_left)}</Td>
                      <Td right>
                        {fmtInt(o.room_types_available)} / {fmtInt(o.room_types_sold_out)}
                      </Td>
                      <Td right className="whitespace-nowrap font-semibold text-ink">
                        {fmtMoney(o.min_price, o.currency)}
                      </Td>
                      <Td right className="pr-5 text-muted">
                        #{o.scan_run_id}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <details className="group rounded-xl border border-line bg-surface shadow-card">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3.5 text-md font-bold text-ink [&::-webkit-details-marker]:hidden">
              <span>
                Lịch sử từng loại phòng <span className="font-normal text-muted">({data.history.length} bản ghi)</span>
              </span>
              <IconChevronRight size={16} className="text-muted transition-transform group-open:rotate-90" />
            </summary>
            <div className="border-t border-line">
              <Table dense>
                <thead>
                  <tr>
                    <Th className="pl-5">Thời điểm quét</Th>
                    <Th>Loại phòng</Th>
                    <Th>Phòng còn</Th>
                    <Th right>Giá thấp nhất</Th>
                    <Th right className="pr-5">
                      Giá hoàn huỷ
                    </Th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.history].reverse().map((s) => {
                    const mark = roomMark(s);
                    return (
                      <tr key={s.id} className={ROW_CLASS}>
                        <Td className="whitespace-nowrap pl-5">{fmtWhen(s.scanned_at)}</Td>
                        <Td>{roomName(s.room_type_id)}</Td>
                        <Td>
                          <span className="inline-flex items-center gap-2" title={mark.label}>
                            <MarkSwatch mark={mark} size={20} className={mark.kind === "capped" ? "!w-auto min-w-[26px] px-1" : undefined} />
                            <span className="text-xs text-muted">{STOCK_CONFIDENCE_LABEL[s.stock_confidence] ?? s.stock_confidence}</span>
                          </span>
                        </Td>
                        <Td right className="whitespace-nowrap">
                          {fmtMoney(s.min_price, s.currency)}
                        </Td>
                        <Td right className="whitespace-nowrap pr-5">
                          {fmtMoney(s.min_refundable_price, s.currency)}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </div>
          </details>

          <Card title="Sự kiện của đêm này" description={`${data.events.length} thay đổi`} padded={false}>
            <EventTable events={data.events} showHotel={false} emptyText="Chưa có biến động nào cho đêm này trong khoảng đã chọn." />
          </Card>
        </div>
      )}
    </>
  );
}
