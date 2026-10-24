"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, cheapestRate, type DayDetailOut, type OverviewOut, type RateDetailOut, type RoomSnapshotOut, type ScanRunOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, isoDate, num, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { useLabel } from "@/lib/labels";
import { useRateText } from "@/lib/rate-text";
import { hotelTitle } from "@/lib/hotels";
import { roomsLeftOf, roomsLeftText } from "@/lib/rooms-left";
import { Button, ButtonLink, Card, EmptyState, ErrorBox, Note, PageHeader, ROW_CLASS, Segmented, SkeletonBlock, Table, Td, Th, cx } from "@/components/ui";
import { SampleTag, sampleFade, useSampleText } from "@/components/compset-sample";
import { EventTable } from "@/components/event-table";
import { LineChart, type Series } from "@/components/line-chart";
import { MarkChip, MarkSwatch, MarksLegend, PromoDot, useMarks, type Mark, type Marks } from "@/components/marks";
import { IconBed, IconCheck, IconChevronLeft, IconChevronRight, IconInfo, IconRefresh } from "@/components/icons";
import { useNightReason } from "@/lib/night-reason";
import { SuggestionCard } from "@/components/market-suggestion";

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
        // Chỉ thẻ điều kiện tiếng Việt; tên gói gốc của Booking.com (tiếng Anh) để trong tooltip.
        const tags = [
          r.refundable === true ? t("refundable") : r.refundable === false ? t("nonRefundable") : null,
          r.breakfast === true ? t("breakfast") : r.breakfast === false ? t("roomOnly") : null,
        ].filter(Boolean);
        return (
          <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
            {!single && <span className="font-semibold text-ink tabular">{fmtMoney(price, cur)}</span>}
            <span className={tags.length ? "text-body" : "text-muted"} title={typeof r.name === "string" ? r.name : undefined}>
              {tags.length ? tags.join(" · ") : t("unknown")}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

type RoomsFields = { exact_rooms_left: number | null; rooms_left_min?: number | null; rooms_left_max?: number | null };

function statusMark(cellMark: Marks["cellMark"], status: string, rooms: RoomsFields | null, minStay: number | null = null): Mark {
  // Còn bán nhưng chỉ từ N đêm = bị hạn chế (không phải hết phòng), như `DateCell.state` của backend.
  const state = status === "available" && (minStay ?? 1) > 1 ? "restricted" : null;
  return cellMark({
    availability_status: status,
    exact_rooms_left: rooms?.exact_rooms_left ?? null,
    rooms_left_min: rooms?.rooms_left_min ?? null,
    rooms_left_max: rooms?.rooms_left_max ?? null,
    min_stay: minStay,
    state,
    stale: false,
  } as Parameters<typeof cellMark>[0]);
}

function shortMark(t: ShortMarkTranslator, m: Mark, minStay?: number | null): string {
  if (m.kind === "exact") return t("exact", { count: Number(m.text) });
  if (m.kind === "capped") return t("roomsText", { rooms: m.text });
  if (m.kind === "hidden") return t("hidden");
  if (m.kind === "sold_out") return t("soldOut");
  if (m.kind === "restricted") return (minStay ?? 1) > 1 ? t("minStay", { count: minStay ?? 2 }) : t("restricted");
  if (m.kind === "no_price") return t("noPrice");
  if (m.kind === "unknown" || m.kind === "error") return t("unknown");
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
function SameNight({ date, hotelId, d }: { date: string; hotelId: number; d: OverviewOut | undefined }) {
  const t = useTranslations("hotels.day.sameNight");
  const tMark = useTranslations("hotels.day.shortMark");
  const { fmtMoney } = useFmt();
  const { cellMark } = useMarks();
  const sample = useSampleText();
  const c = d?.compset.find((x) => x.stay_date === date);
  return (
    <Card
      title={t("title")}
      description={
        !d ? undefined : c && c.competitors_observed > 0 ? (
          <span className="flex flex-col gap-0.5">
            <span>
              {t("soldOut", { soldOut: c.competitors_sold_out, observed: c.competitors_observed })}
              {c.competitors_restricted > 0 && ` · ${t("restricted", { count: c.competitors_restricted })}`}
            </span>
            <span className={sampleFade(c)} title={sample.title(c)}>
              {c.sample === "insufficient" ? sample.status(c) : t("median", { median: fmtMoney(c.median_price, c.currency) })}{" "}
              {c.sample !== "insufficient" && <SampleTag c={c} short />}
            </span>
          </span>
        ) : (
          t("noCompetitors")
        )
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
                  href={`/hotels/${h.hotel.id}/dates/${date}`}
                  aria-current={current ? "page" : undefined}
                  className={cx("flex items-center gap-3 px-5 py-2.5 transition-colors", current ? "bg-brand-softer" : "hover:bg-subtle")}
                >
                  <span className="relative">
                    <MarkSwatch mark={mark} size={26} className="!w-[46px]" />
                    <PromoDot promo={mark.promo} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={cx("block truncate text-base", h.role === "self" ? "font-bold text-yours-deep" : current ? "font-bold text-ink" : "font-medium text-body")}>
                      {name}
                      {h.role === "self" && <span className="ml-1.5 text-xs font-semibold text-yours-deep">{t("yours")}</span>}
                    </span>
                    <span className="block text-xs text-muted" title={mark.label}>
                      {shortMark(tMark, mark, cell?.min_stay)}
                      {mark.stale && ` · ${tMark("stale")}`}
                    </span>
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
 * Giá Booking.com của khách sạn đêm này ở lần quét gần nhất: tình trạng, giá thấp nhất (kèm giá gạch
 * và nhãn KM của gói rẻ nhất), điều kiện gói, giá có bữa sáng / chỉ phòng / hoàn huỷ, số đêm tối thiểu.
 */
function NightRate({ rate }: { rate: RateDetailOut }) {
  const t = useTranslations("hotels.day.nightRate");
  const tMark = useTranslations("hotels.day.shortMark");
  const { fmtMoney, fmtWhen } = useFmt();
  const { cellMark } = useMarks();
  const { rateConditions } = useRateText();
  const mark = rate.availability_status ? statusMark(cellMark, rate.availability_status, rate, rate.min_stay ?? null) : cellMark(undefined);
  const cr = cheapestRate(rate);
  const original = num(cr?.price_original);
  const price = num(rate.min_price);
  const promoed = original !== null && price !== null && original > price;
  const conditions = rate.min_price ? rateConditions(cr?.key) : null;
  const refundDiffers = rate.min_refundable_price && rate.min_refundable_price !== rate.min_price;
  const extras = [
    refundDiffers ? t("refundableFrom", { price: fmtMoney(rate.min_refundable_price, rate.currency) }) : null,
    rate.min_breakfast_price ? t("breakfastFrom", { price: fmtMoney(rate.min_breakfast_price, rate.currency) }) : null,
    rate.min_room_only_price ? t("roomOnlyFrom", { price: fmtMoney(rate.min_room_only_price, rate.currency) }) : null,
  ].filter((x): x is string => x !== null);
  return (
    <section aria-label={t("title")} className="rounded-xl border border-line bg-surface px-5 py-3.5 shadow-card">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-md font-bold text-ink">{t("title")}</h2>
        <span className="text-xs text-muted">{rate.last_observed_at ? t("scannedAt", { when: fmtWhen(rate.last_observed_at) }) : t("notScanned")}</span>
      </header>
      <div className="mt-2.5 flex flex-wrap items-start gap-x-8 gap-y-3">
        <div className="flex items-center gap-2" title={mark.label}>
          <MarkSwatch mark={mark} size={28} className={mark.kind === "capped" ? "!w-auto min-w-[28px] px-1.5" : undefined} />
          <span className="text-sm text-body">{shortMark(tMark, mark, rate.min_stay)}</span>
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="text-lg font-bold text-ink tabular">{rate.min_price ? fmtMoney(rate.min_price, rate.currency) : <span className="text-base font-normal text-faint">{t("noPrice")}</span>}</span>
            {promoed && (
              <span className="text-sm text-muted line-through tabular" title={t("priceBeforePromo")}>
                {fmtMoney(original, rate.currency)}
              </span>
            )}
            {cr?.promo_label && <span className="rounded bg-[#fce7f3] px-1.5 text-xs font-semibold text-[#9d174d]">{cr.promo_label}</span>}
          </div>
          {conditions && (
            <div className="mt-0.5 text-xs text-muted" title={t("conditionsTitle")}>
              {conditions}
            </div>
          )}
          {cr?.source_supplier && <div className="text-xs text-muted">{t("supplier", { supplier: cr.source_supplier })}</div>}
          {rate.min_price && cr?.taxes_included === false && <div className="text-xs text-muted">{t("taxExclusive")}</div>}
        </div>
        {(extras.length > 0 || (rate.min_stay ?? 1) > 1) && (
          <ul className="space-y-0.5 text-sm text-body tabular">
            {extras.map((x) => (
              <li key={x}>{x}</li>
            ))}
            {(rate.min_stay ?? 1) > 1 && <li className="font-semibold text-warning-deep">{t("minStay", { count: rate.min_stay ?? 2 })}</li>}
          </ul>
        )}
      </div>
    </section>
  );
}

export default function DayDetailPage() {
  const t = useTranslations("hotels.day");
  const { fmtAgo, fmtCompact, fmtDate, fmtDateShort, fmtDayTime, fmtInt, fmtMoney, fmtNight, fmtWeekday, fmtWhen } = useFmt();
  const { canWrite } = useSession();
  const fresh = useDataFreshness();
  const label = useLabel();
  const { cellMark, roomMark } = useMarks();
  const { nightReason } = useNightReason();
  const { id, date } = useParams<{ id: string; date: string }>();
  const hotelId = Number(id);
  const valid = Number.isFinite(hotelId) && /^\d{4}-\d{2}-\d{2}$/.test(date);
  const [historyDays, setHistoryDays] = useState<number>(14);
  const { data, error, loading } = useApi(valid ? `day:${hotelId}:${date}:${historyDays}` : null, () => api.day(hotelId, date, historyDays));
  // Cùng đêm của mọi khách sạn (thẻ "Cùng đêm trên Booking.com"), cũng cho biết đây có phải khách sạn của bạn.
  const market = useApi(valid ? `market:${date}` : null, () => api.overview({ start: date, end: date }));
  const row = market.data?.hotels.find((h) => h.hotel.id === hotelId);
  const own = row?.role === "self";
  // Gợi ý giá của đêm (chỉ khách sạn của bạn, bỏ "giữ giá").
  const pace = useApi(own ? `day:pace:${hotelId}:${date}` : null, () => api.market.pace({ start: date, end: date, own_hotel_id: hotelId }));
  const night = pace.data?.own_hotel_id === hotelId ? pace.data.nights.find((n) => n.stay_date === date) : undefined;
  const suggestion = night?.suggestion && night.suggestion.kind !== "hold" ? night : undefined;
  // Quan sát mới nhất của đêm này cũ hơn 48 giờ: chip "Số từ 16/10 · 8 ngày trước".
  const staleCell = row?.cells.find((c) => c.stay_date === date && c.stale);

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
  const marketText = data ? nightReason(data.compset, data.holiday) : null;
  const prev = valid ? addDays(date, -1) : null;
  const next = valid ? addDays(date, 1) : null;

  return (
    <>
      <PageHeader
        crumbs={[
          own ? { href: "/today", label: t("crumbOwn") } : { href: "/competitors", label: t("crumb") },
          { href: `/hotels/${hotelId}`, label: title },
          { label: valid ? t("nightCrumb", { night: fmtNight(date) }) : t("invalidDate") },
        ]}
        title={valid ? t("title", { weekday: fmtWeekday(date), date: fmtDate(date) }) : t("invalidDate")}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold text-body">{title}</span>
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
            {staleCell?.last_observed_at && (
              <span className="rounded-full bg-warning-soft px-2.5 py-0.5 text-xs font-semibold text-warning-deep" title={t("staleTitle")}>
                {t("staleChip", { date: fmtDateShort(isoDate(new Date(staleCell.last_observed_at))), ago: fmtAgo(staleCell.last_observed_at) })}
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
      {suggestion && (
        <div className="mb-4">
          <SuggestionCard
            night={suggestion}
            ownHotelId={hotelId}
            canWrite={canWrite}
            onChanged={pace.reload}
            staleSince={fresh.stale ? (fresh.updatedAt ?? "") : null}
            title={t("suggestionTitle")}
          />
        </div>
      )}
      {data && marketText && (
        <Note tone="info" icon={<IconInfo size={16} />} className="mb-4">
          <span className="font-semibold text-ink">{t("market")}</span> {marketText}
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
          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
            {/* Mobile: cùng đêm của mọi khách sạn lên đầu; desktop: cột phải, ngang hàng giá đêm này. */}
            <div className="order-first min-w-0 xl:order-none xl:col-start-2 xl:row-start-1">
              <SameNight date={date} hotelId={hotelId} d={market.data} />
            </div>
            <div className="min-w-0 space-y-5 xl:col-start-1 xl:row-start-1">
              {data.rate && <NightRate rate={data.rate} />}
              <Card
                title={t("latest.title")}
                description={data.latest.length ? t("latest.description", { count: data.latest.length }) : undefined}
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
                          : latestStatus === "restricted"
                            ? t("latest.restricted", { when: fmtWhen(latestAt) })
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
            </div>
          </div>

          {/* Đêm chưa từng được quét: không có lịch sử nào để vẽ, phần giải thích ở trên là đủ. */}
          {latestStatus !== null && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <h2 className="text-lg font-bold text-ink">{t("history.title")}</h2>
                <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
                  {t("history.lookBack")}
                  <Segmented label={t("history.range")} size="sm" value={historyDays} onChange={setHistoryDays} items={HISTORY_OPTIONS.map((d) => ({ value: d, label: t("history.days", { count: d }) }))} />
                </div>
              </div>

              {/* Dưới 2 lượt quét thì không có diễn biến để vẽ: một câu thay hai biểu đồ (bảng lượt quét bên dưới tự nói khi trống). */}
              {data.observations.length < 2 ? (
                data.observations.length === 1 && <Note tone="neutral">{t("history.single", { when: fmtWhen(data.observations[0].scanned_at) })}</Note>
              ) : (
                <div className="grid gap-5 lg:grid-cols-2">
                  <Card title={t("history.roomsChart")}>
                    {onlyFloor ? (
                      <div className="flex h-[220px] flex-col items-center justify-center gap-2 rounded-lg bg-subtle px-6 text-center">
                        <MarkSwatch mark={{ kind: "capped", cls: "sb-mark-capped", text: `≥${floorMax}`, label: "" }} size={34} className="!w-auto px-1.5" />
                        <p className="max-w-sm text-base text-body">
                          {t.rich("history.onlyFloor", { count: floorMax, b: (c) => <span className="font-semibold">{c}</span> })}
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
              )}

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
                        <Th right className="pr-5">
                          {t("cols.lowestPrice")}
                        </Th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...data.observations].reverse().map((o) => (
                        <tr key={`${o.scan_run_id}-${o.scanned_at}`} className={ROW_CLASS}>
                          <Td className="whitespace-nowrap pl-5 font-medium text-ink">{fmtWhen(o.scanned_at)}</Td>
                          <Td>
                            <span className="inline-flex items-center gap-2">
                              {(() => {
                                const m = statusMark(cellMark, o.status, o);
                                return <MarkSwatch mark={m} size={20} className={m.kind === "capped" ? "!w-auto min-w-[20px] px-1" : undefined} />;
                              })()}
                              {label("availability", o.status)}
                            </span>
                          </Td>
                          <Td right>{(() => {
                            const r = roomsLeftOf(o);
                            return r === null ? fmtInt(null) : roomsLeftText(r, fmtInt);
                          })()}</Td>
                          <Td right>
                            {fmtInt(o.room_types_available)} / {fmtInt(o.room_types_sold_out)}
                          </Td>
                          <Td right className="whitespace-nowrap pr-5 font-semibold text-ink">
                            {fmtMoney(o.min_price, o.currency)}
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
      )}
    </>
  );
}
