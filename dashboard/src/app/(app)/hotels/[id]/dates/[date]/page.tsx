"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useState } from "react";
import { api, type ChannelDayOut, type DayDetailOut, type RoomSnapshotOut, type ScanRunOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, num, useFmt } from "@/lib/format";
import { parseDateParam, parseIdParam } from "@/lib/params";
import { useLabel } from "@/lib/labels";
import { channelName, hotelTitle, sortChannels, withChannel } from "@/lib/channels";
import { Button, ButtonLink, Card, EmptyState, ErrorBox, Note, PageHeader, ROW_CLASS, Segmented, SkeletonBlock, Table, Tabs, Td, Th, cx } from "@/components/ui";
import { DemandSignals, useChannelParam } from "@/components/channels";
import { EventTable } from "@/components/event-table";
import { LineChart, type Series } from "@/components/line-chart";
import { MarkChip, MarkSwatch, MarksLegend, useMarks, type Mark, type Marks } from "@/components/marks";
import { IconBed, IconCheck, IconChevronLeft, IconChevronRight, IconInfo, IconRefresh } from "@/components/icons";
import { useNightReason } from "@/lib/night-reason";

const HISTORY_OPTIONS = [7, 14, 30, 60] as const;

/** Gói giá trong `rates` (jsonb): name, price (chuỗi), currency, refundable, breakfast. */
type Rate = { name?: unknown; price?: unknown; currency?: unknown; refundable?: unknown; breakfast?: unknown };

type ShortMarkTranslator = ReturnType<typeof useTranslations<"hotels.day.shortMark">>;

function RateList({ rates, currency, minPrice }: { rates: Record<string, unknown>[]; currency: string | null; minPrice: string | null }) {
  const t = useTranslations("hotels.day.rates");
  const { fmtMoney } = useFmt();
  if (rates.length === 0) return <span className="text-faint">—</span>;
  // Một gói duy nhất cùng giá thấp nhất: không lặp lại giá.
  const single = rates.length === 1 && num((rates[0] as Rate).price as string) === num(minPrice);
  return (
    <ul className="space-y-1">
      {rates.map((raw, i) => {
        const r = raw as Rate;
        const price = typeof r.price === "string" || typeof r.price === "number" ? r.price : null;
        const cur = typeof r.currency === "string" ? r.currency : currency;
        const tags = [r.refundable === true ? t("refundable") : r.refundable === false ? t("nonRefundable") : null, r.breakfast === true ? t("breakfast") : null].filter(Boolean);
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

function statusMark(cellMark: Marks["cellMark"], status: string, exact: number | null): Mark {
  return cellMark({
    availability_status: status,
    exact_rooms_left: exact,
  } as Parameters<typeof cellMark>[0]);
}

function shortMark(t: ShortMarkTranslator, m: Mark): string {
  if (m.kind === "exact") return t("exact", { count: Number(m.text) });
  if (m.kind === "hidden") return t("hidden");
  if (m.kind === "sold_out") return t("soldOut");
  if (m.kind === "unknown") return t("unknown");
  return m.label; // "Chưa có dữ liệu" hoặc "Ngoài phạm vi quét"
}

/**
 * Đêm chưa từng có quan sát nào: nói rõ vì sao thay vì chỉ báo "không có dữ liệu".
 * Hôm nay (giờ tenant) = horizon_end - horizon_days + 1.
 */
function NoDataReason({ data }: { data: DayDetailOut }) {
  const t = useTranslations("hotels.day.noData");
  const { fmtDate, fmtNight, fmtWhen } = useFmt();
  const { canWrite } = useSession();
  // Đang có lượt quét chạy (theo lịch, quét bù hay "Quét ngay"): không mời quét thêm lần nữa.
  const last = useApi(canWrite ? "day:runs" : null, () => api.runs(1));
  const [started, setStarted] = useState<ScanRunOut[] | null>(null);
  const scan = useMutation(async () => setStarted(await api.watchlist.scanNow()));
  const running = (started !== null && started.length > 0) || last.data?.[0]?.status === "running";
  const date = data.stay_date;
  const today = addDays(data.horizon_end, 1 - data.horizon_days);

  if (date > data.horizon_end) {
    return (
      <EmptyState
        icon={<IconBed />}
        compact
        title={t("beyondTitle")}
        action={
          canWrite && (
            <ButtonLink href="/settings?tab=schedule" size="sm">
              {t("changeHorizon")}
            </ButtonLink>
          )
        }
      >
        {t("beyondBody", {
          days: data.horizon_days,
          horizonEnd: fmtNight(data.horizon_end),
          night: fmtNight(date),
          startsOn: fmtDate(addDays(date, 1 - data.horizon_days)),
        })}
      </EmptyState>
    );
  }
  if (date < today) {
    return (
      <EmptyState icon={<IconBed />} compact title={t("pastTitle")}>
        {t("pastBody")}
      </EmptyState>
    );
  }
  // Lượt quét gần nhất dừng trước đêm này (đêm vào phạm vi quét sau lượt đó).
  const endedBefore = data.last_scan_through && data.last_scan_through < date;
  return (
    <EmptyState
      icon={<IconBed />}
      compact
      title={t("notCoveredTitle")}
      action={
        canWrite &&
        last.data &&
        (running ? (
          <Note tone="info" icon={<IconCheck size={16} />}>
            {t("scanning")}
          </Note>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <Button size="sm" busy={scan.busy} icon={<IconRefresh size={15} />} onClick={() => void scan.run()}>
              {t("scanNow")}
            </Button>
            {scan.error && <span className="text-sm text-danger">{scan.error}</span>}
          </div>
        ))
      }
    >
      {!data.last_scan_at
        ? t("neverScanned")
        : endedBefore
          ? t("endedBefore", { when: fmtWhen(data.last_scan_at), through: fmtNight(data.last_scan_through!) })
          : t("notRecorded", { when: fmtWhen(data.last_scan_at) })}
    </EmptyState>
  );
}

/** Cùng đêm trên thị trường: mọi khách sạn trong watchlist, khách sạn đang xem được đánh dấu. */
function SameNight({ date, hotelId, channel }: { date: string; hotelId: number; channel: string }) {
  const t = useTranslations("hotels.day.sameNight");
  const tMark = useTranslations("hotels.day.shortMark");
  const { fmtMoney } = useFmt();
  const { cellMark } = useMarks();
  const market = useApi(`market:${date}:${channel}`, () => api.overview({ start: date, end: date, channel }));
  const d = market.data;
  const c = d?.compset.find((x) => x.stay_date === date);
  return (
    <Card
      title={t("title", { channel: channelName(channel) })}
      description={
        !d
          ? undefined
          : c && c.competitors_observed > 0
            ? t("summary", { soldOut: c.competitors_sold_out, observed: c.competitors_observed, median: fmtMoney(c.median_price, c.currency) })
            : t("noCompetitors")
      }
      padded={false}
    >
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
            const mark = cellMark(cell, date > d.horizon_end);
            const current = h.hotel.id === hotelId;
            const name = hotelTitle(h.hotel, h.label);
            return (
              <li key={h.hotel.id}>
                <Link
                  href={withChannel(`/hotels/${h.hotel.id}/dates/${date}`, channel)}
                  aria-current={current ? "page" : undefined}
                  className={cx("flex items-center gap-3 px-5 py-2.5 transition-colors", current ? "bg-brand-softer" : "hover:bg-subtle")}
                >
                  <MarkSwatch mark={mark} size={26} />
                  <span className="min-w-0 flex-1">
                    <span className={cx("block truncate text-base", h.role === "self" ? "font-bold text-yours-deep" : current ? "font-bold text-ink" : "font-medium text-body")}>
                      {name}
                      {h.role === "self" && <span className="ml-1.5 text-xs font-semibold text-yours-deep">{t("yours")}</span>}
                    </span>
                    <span className="block text-xs text-muted">{shortMark(tMark, mark)}</span>
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

/**
 * "So kênh": mỗi kênh một cột cho đêm này (tình trạng, số phòng chính xác, giá thấp nhất).
 * Mỗi kênh có quota phòng riêng nên không bao giờ cộng số phòng giữa các kênh.
 */
function ChannelCompare({ rows, channels, current }: { rows: ChannelDayOut[]; channels: string[]; current: string }) {
  const t = useTranslations("hotels.day.compare");
  const tMark = useTranslations("hotels.day.shortMark");
  const { fmtMoney, fmtWhen } = useFmt();
  const { cellMark } = useMarks();
  const byChannel = new Map(rows.map((r) => [r.channel, r]));
  // Chỉ so giá giữa các kênh cùng cơ sở (đã gồm thuế phí, theo phòng/đêm) và đang còn phòng.
  const comparable = rows.filter((r) => r.tax_inclusive && r.availability_status === "available" && num(r.min_price) !== null);
  const cheapest = comparable.length >= 2 ? Math.min(...comparable.map((r) => num(r.min_price)!)) : null;
  return (
    <section aria-label={t("aria")} className="rounded-xl border border-line bg-surface shadow-card">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 pt-3.5">
        <h2 className="text-md font-bold text-ink">{t("title")}</h2>
        <span className="text-xs text-muted">{t("hint")}</span>
      </header>
      <ul className="sb-scroll mt-2.5 flex flex-col border-t border-line sm:flex-row sm:overflow-x-auto">
        {channels.map((c) => {
          const r = byChannel.get(c);
          const mark = r?.availability_status ? statusMark(cellMark, r.availability_status, r.exact_rooms_left) : cellMark(undefined);
          const on = c === current;
          const refundDiffers = r?.min_refundable_price && r.min_refundable_price !== r.min_price;
          const isCheapest = cheapest !== null && r !== undefined && comparable.includes(r) && num(r.min_price) === cheapest;
          return (
            <li
              key={c}
              aria-current={on ? "true" : undefined}
              className={cx(
                "flex items-start justify-between gap-3 border-t border-line px-4 py-3 first:border-t-0 sm:block sm:min-w-[170px] sm:flex-1 sm:border-l sm:border-t-0 sm:px-5 sm:first:border-l-0",
                on && "bg-brand-softer",
              )}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-1.5 text-sm font-semibold text-ink">
                  {channelName(c)}
                  {on && <span className="whitespace-nowrap text-xs font-semibold text-brand-hover">{t("viewing")}</span>}
                </div>
                <div className="mt-1.5 flex items-center gap-2 sm:mt-2" title={mark.label}>
                  <MarkSwatch mark={mark} size={24} />
                  <span className="text-sm text-body">{shortMark(tMark, mark)}</span>
                </div>
              </div>
              <div className="shrink-0 text-right sm:mt-1.5 sm:text-left">
                <div className="flex items-center justify-end gap-1.5 sm:justify-start">
                  <span className="text-base font-semibold text-ink tabular">{r?.min_price ? fmtMoney(r.min_price, r.currency) : <span className="font-normal text-faint">{t("noPrice")}</span>}</span>
                  {isCheapest && (
                    <span className="rounded-full bg-sunken px-1.5 text-xs font-semibold text-ink" title={t("cheapestHint")}>
                      {t("cheapest")}
                    </span>
                  )}
                </div>
                {r?.min_price && !r.tax_inclusive && <div className="text-xs text-muted">{t("taxExclusive")}</div>}
                {refundDiffers && <div className="text-xs text-muted tabular">{t("refundableFrom", { price: fmtMoney(r.min_refundable_price, r.currency) })}</div>}
                <div className="mt-1 text-xs text-muted">{r?.last_observed_at ? t("scannedAt", { when: fmtWhen(r.last_observed_at) }) : t("notScanned")}</div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function DayDetailPage() {
  const t = useTranslations("hotels.day");
  const { fmtCompact, fmtDate, fmtDayTime, fmtInt, fmtMoney, fmtNight, fmtWeekday, fmtWhen } = useFmt();
  const label = useLabel();
  const { cellMark, roomMark } = useMarks();
  const { nightReason } = useNightReason();
  const { id, date: dateParam } = useParams<{ id: string; date: string }>();
  const hotelId = parseIdParam(id);
  const date = parseDateParam(dateParam);
  const [historyDays, setHistoryDays] = useState<number>(14);
  const [channelParam, setChannel] = useChannelParam();
  const { isOperator } = useSession();
  const { data, error, loading } = useApi(hotelId === null || date === null ? null : `day:${hotelId}:${date}:${historyDays}:${channelParam ?? ""}`, () =>
    api.day(hotelId!, date!, historyDays, channelParam),
  );
  // id/ngày sai định dạng: trang 404 thay vì skeleton xoay mãi (gọi sau mọi hook để thứ tự hook không đổi).
  if (hotelId === null || date === null) notFound();
  const channel = data?.channel ?? channelParam ?? "";
  // Kênh của khách sạn: có số liệu đêm này, hoặc đang/đã quét (kể cả tạm dừng, đường dẫn lỗi).
  const hotelChannels = data
    ? sortChannels([
        ...data.channels.map((c) => c.channel),
        ...data.hotel.listings.filter((l) => l.status === "active" || l.status === "paused" || l.status === "broken").map((l) => l.channel),
        data.channel,
      ])
    : [];

  const roomName = (rtId: number) => data?.room_types.find((r) => r.id === rtId)?.name ?? t("roomTypeFallback", { id: rtId });

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
        // Số phòng còn của một mức giá: với cả loại phòng chỉ là mức sàn.
        if (s.stock_scope === "rate" && s.rooms_left !== null) return [{ x, y: s.rooms_left, floor: true }];
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
  const title = data ? hotelTitle(data.hotel, data.label) : t("fallbackTitle");
  const rateScoped = data?.latest.some((s) => s.stock_scope === "rate") ?? false;
  const market = data ? nightReason(data.compset, data.holiday) : null;
  const prev = addDays(date, -1);
  const next = addDays(date, 1);

  return (
    <>
      <PageHeader
        crumbs={[
          { href: "/competitors", label: t("crumb") },
          { href: withChannel(`/hotels/${hotelId}`, channelParam), label: title },
          { label: t("nightCrumb", { night: fmtNight(date) }) },
        ]}
        title={t("title", { weekday: fmtWeekday(date), date: fmtDate(date) })}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold text-body">{title}</span>
            {channel && <span>{t("onChannel", { channel: channelName(channel) })}</span>}
            {latestAt && (
              <span className="inline-flex items-center gap-2">
                {t("lastScan", { when: fmtWhen(latestAt) })}
                {latestStatus && (
                  <span className="inline-flex items-center gap-1.5 text-body">
                    <MarkSwatch mark={statusMark(cellMark, latestStatus, null)} size={14} className="rounded-[3px]" />
                    {label("availability", latestStatus)}
                  </span>
                )}
              </span>
            )}
          </span>
        }
        actions={
          <div className="flex items-center gap-1">
            <ButtonLink href={withChannel(`/hotels/${hotelId}/dates/${prev}`, channelParam)} variant="ghost" size="sm" icon={<IconChevronLeft size={15} />}>
              {fmtNight(prev)}
            </ButtonLink>
            <ButtonLink href={withChannel(`/hotels/${hotelId}/dates/${next}`, channelParam)} variant="ghost" size="sm">
              {fmtNight(next)} <IconChevronRight size={15} />
            </ButtonLink>
          </div>
        }
      />
      <ErrorBox error={error} className="mb-4" />
      {data && market && (
        <Note tone="info" icon={<IconInfo size={16} />} className="mb-4">
          <span className="font-semibold text-ink">{hotelChannels.length > 1 ? t("marketOn", { channel: channelName(channel) }) : t("market")}</span> {market}
        </Note>
      )}
      {!data && !error && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]" aria-busy>
          <SkeletonBlock className="h-[420px] rounded-xl" />
          <SkeletonBlock className="h-[320px] rounded-xl" />
        </div>
      )}
      {data && (
        <div className={cx("space-y-5 transition-opacity duration-200", loading && "opacity-60")}>
          {hotelChannels.length > 1 && <ChannelCompare rows={data.channels} channels={hotelChannels} current={data.channel} />}
          <DemandSignals signals={data.demand_signals} isOperator={isOperator} />
          {hotelChannels.length > 1 && (
            <Tabs
              className="!mb-0"
              value={data.channel}
              onChange={setChannel}
              items={hotelChannels.map((c) => ({ key: c, label: t("detailOn", { channel: channelName(c) }) }))}
            />
          )}
          <div role={hotelChannels.length > 1 ? "tabpanel" : undefined} id={hotelChannels.length > 1 ? `panel-${data.channel}` : undefined} aria-labelledby={hotelChannels.length > 1 ? `tab-${data.channel}` : undefined} className="space-y-5">
            <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
              <Card
                title={t("latest.title")}
                description={data.latest.length ? t("latest.description", { count: data.latest.length, channel: channelName(data.channel) }) : undefined}
                padded={false}
              >
                {data.latest.length === 0 ? (
                  <div className="p-5">
                    {latestStatus === null ? (
                      <NoDataReason key={date} data={data} />
                    ) : (
                      <EmptyState icon={<IconBed />} compact>
                        {latestStatus === "sold_out"
                          ? t("latest.soldOut", { when: fmtWhen(latestAt) })
                          : latestStatus === "unknown"
                            ? t("latest.unknown", { when: fmtWhen(latestAt) })
                            : t("latest.empty", { when: fmtWhen(latestAt) })}
                      </EmptyState>
                    )}
                  </div>
                ) : (
                  <>
                    <Table>
                      <thead>
                        <tr>
                          <Th className="pl-5">{t("cols.roomType")}</Th>
                          <Th>{t("cols.roomsLeft")}</Th>
                          <Th right>{t("cols.lowestPrice")}</Th>
                          <Th className="hidden md:table-cell">{t("cols.rates")}</Th>
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
                                {rt?.max_occupancy ? <div className="text-xs text-muted">{t("latest.maxGuests", { count: rt.max_occupancy })}</div> : null}
                                <div className="mt-1.5 md:hidden">
                                  <RateList rates={s.rates} currency={s.currency} minPrice={s.min_price} />
                                </div>
                              </Td>
                              <Td>
                                <MarkChip mark={mark} />
                              </Td>
                              <Td right className="whitespace-nowrap">
                                <div className="font-semibold text-ink">{fmtMoney(s.min_price, s.currency)}</div>
                                {refundDiffers && <div className="text-xs text-muted">{t("latest.refundableFrom", { price: fmtMoney(s.min_refundable_price, s.currency) })}</div>}
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
                      <MarksLegend variant="room">
                        {rateScoped && <li className="text-faint">{t("latest.rateScoped")}</li>}
                      </MarksLegend>
                    </div>
                  </>
                )}
              </Card>
              <SameNight date={date} hotelId={hotelId} channel={data.channel} />
            </div>

            {/* Đêm chưa từng được quét: không có lịch sử nào để vẽ, phần giải thích ở trên là đủ. */}
            {latestStatus !== null && (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                  <h2 className="text-lg font-bold text-ink">{t("history.title")}</h2>
                  <div className="flex items-center gap-2 text-sm text-muted">
                    {t("history.lookBack")}
                    <Segmented label={t("history.range")} size="sm" value={historyDays} onChange={setHistoryDays} items={HISTORY_OPTIONS.map((d) => ({ value: d, label: t("history.days", { count: d }) }))} />
                  </div>
                </div>

                <div className="grid gap-5 lg:grid-cols-2">
                  <Card title={t("history.roomsChart")}>
                    {onlyFloor ? (
                      <div className="flex h-[220px] flex-col items-center justify-center gap-2 rounded-lg bg-subtle px-6 text-center">
                        <MarkSwatch mark={{ kind: "capped", cls: "sb-mark-capped", text: `≥${floorMax}`, label: "" }} size={34} className="!w-auto px-1.5" />
                        <p className="max-w-sm text-base text-body">
                          {t.rich("history.onlyFloor", { count: floorMax, channel: channelName(data.channel), b: (c) => <span className="font-semibold">{c}</span> })}
                        </p>
                      </div>
                    ) : (
                      <LineChart series={roomsSeries} zeroBased formatY={(v) => fmtInt(Math.round(v))} formatX={(v) => fmtDayTime(new Date(v).toISOString())} emptyText={t("history.roomsEmpty")} />
                    )}
                  </Card>
                  <Card title={currency ? t("history.priceChartCurrency", { currency }) : t("history.priceChart")}>
                    <LineChart series={priceSeries} formatY={(v) => fmtCompact(v)} formatX={(v) => fmtDayTime(new Date(v).toISOString())} emptyText={t("history.priceEmpty")} />
                  </Card>
                </div>

                <Card title={t("observations.title")} description={t("observations.description", { count: data.observations.length, days: historyDays })} padded={false}>
                  {data.observations.length === 0 ? (
                    <div className="p-5">
                      <EmptyState compact>{t("observations.empty", { days: historyDays })}</EmptyState>
                    </div>
                  ) : (
                    <Table dense>
                      <thead>
                        <tr>
                          <Th className="pl-5">{t("cols.scannedAt")}</Th>
                          <Th>{t("cols.status")}</Th>
                          <Th right>{t("cols.exactRooms")}</Th>
                          <Th right>{t("cols.roomTypesOpenSold")}</Th>
                          <Th right>{t("cols.lowestPrice")}</Th>
                          <Th right className="pr-5">
                            {t("cols.run")}
                          </Th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...data.observations].reverse().map((o) => (
                          <tr key={`${o.scan_run_id}-${o.scanned_at}`} className={ROW_CLASS}>
                            <Td className="whitespace-nowrap pl-5 font-medium text-ink">{fmtWhen(o.scanned_at)}</Td>
                            <Td>
                              <span className="inline-flex items-center gap-2">
                                <MarkSwatch mark={statusMark(cellMark, o.status, o.exact_rooms_left)} size={20} />
                                {label("availability", o.status)}
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
                      {t.rich("roomHistory.title", { count: data.history.length, muted: (c) => <span className="font-normal text-muted">{c}</span> })}
                    </span>
                    <IconChevronRight size={16} className="text-muted transition-transform group-open:rotate-90" />
                  </summary>
                  <div className="border-t border-line">
                    <Table dense>
                      <thead>
                        <tr>
                          <Th className="pl-5">{t("cols.scannedAt")}</Th>
                          <Th>{t("cols.roomType")}</Th>
                          <Th>{t("cols.roomsLeft")}</Th>
                          <Th right>{t("cols.lowestPrice")}</Th>
                          <Th right className="pr-5">
                            {t("cols.refundablePrice")}
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
                                  <span className="text-xs text-muted">{label("stockConfidence", s.stock_confidence)}</span>
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

                <Card title={t("events.title")} description={t("events.description", { count: data.events.length })} padded={false}>
                  <EventTable events={data.events} showHotel={false} emptyText={t("events.empty")} />
                </Card>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
