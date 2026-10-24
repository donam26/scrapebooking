"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { ReactNode } from "react";
import type { CityListOut, LadderRungOut, MarketCityOut, SelfMarketOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { roomsLeftText } from "@/lib/rooms-left";
import { DEEP_RUNG, LADDER_RUNGS, compositionGroups, roomsRange, rungCount, rungMap, tightnessTrend, useMarketAreaText } from "@/lib/market-area";
import { Card, EmptyState, cx } from "@/components/ui";
import { IconPin } from "@/components/icons";
import { ScanAge } from "./scan-age";

/**
 * HÔM NAY TRONG KHU VỰC (tab Thị trường, F3): một câu chính bằng lời thường ("Khu vực còn 563/593
 * khách sạn có phòng; 217 khách sạn còn ít nhất 30 phòng — thị trường lỏng như thường lệ"), khách sạn
 * của bạn trên thị trường, rồi "Chi tiết" (thu gọn): hai tỉ lệ hết phòng có giải thích, mức phòng
 * còn bán, tổng phòng còn, giá giữa, loại chỗ ở và phân bố giá. Mọi số là mức tối thiểu Booking.com
 * cho thấy, không phải công suất.
 */

const MICRO = "text-xs font-semibold text-muted";

/** Màu cột phân bố giá: rẻ xanh lá → đắt tím (như dải màu của mẫu). */
const BAR_COLORS = ["#16a34a", "#4ade80", "#a3e635", "#facc15", "#f59e0b", "#ea7317", "#ef4444", "#8b5cf6"];

function barColor(i: number, n: number): string {
  return BAR_COLORS[Math.min(BAR_COLORS.length - 1, Math.floor((i / Math.max(1, n)) * BAR_COLORS.length))];
}

/** Mức thị trường theo phần khách sạn đã hết phòng: lỏng < 10% ≤ vừa phải < 50% ≤ căng. */
function marketLevel(share: number | null | undefined): "loose" | "moderate" | "tight" | null {
  if (share === null || share === undefined) return null;
  return share >= 0.5 ? "tight" : share >= 0.1 ? "moderate" : "loose";
}

const BOLD = (c: ReactNode) => <b className="font-bold text-ink tabular">{c}</b>;

/** `loading`: đang tải khu vực vừa chọn (số cũ làm mờ). */
export function AreaTodayCard({ city, loading }: { city: MarketCityOut; loading?: boolean }) {
  const t = useTranslations("marketTab.today");
  const { list_scan: list, detail } = city;
  const hasData = list.scan_id !== null && list.properties_found !== null;
  const occ = num(detail.occupancy_est);
  return (
    <Card className="h-full" title={t("title")} icon={<IconPin size={15} />} info={t("info")} description={<ScanAge at={list.scanned_at} />}>
      <div aria-busy={loading || undefined} className={cx("transition-opacity duration-150", loading && "opacity-60")}>
        {hasData ? (
          <>
            <Headline list={list} />
            {city.self_hotel && <SelfLine me={city.self_hotel} />}
            <details className="group mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-sm font-semibold text-body hover:text-ink">{t("details")}</summary>
              <div className="mt-3 grid gap-x-8 gap-y-5 md:grid-cols-2">
                <div className="min-w-0 space-y-4">
                  <SoldOutExplained list={list} />
                  <Ladder ladder={list.ladder} />
                </div>
                <div className="min-w-0 space-y-4">
                  <Facts list={list} />
                  <Composition list={list} />
                  <PriceDistribution list={list} me={city.self_hotel ?? null} />
                </div>
              </div>
              {occ !== null && (
                <p className="mt-3 text-xs text-muted" title={t("fillTitle", { coverage: detail.coverage_hotels })}>
                  {t("fill", { pct: Math.round(occ * 100) })}
                </p>
              )}
            </details>
          </>
        ) : (
          <NoData status={list.status} />
        )}
        <p className="mt-3 text-sm">
          <Link href="/competitors/market" className="font-semibold text-brand hover:underline">
            {t("explore")}
          </Link>
        </p>
      </div>
    </Card>
  );
}

/** Câu chính: còn phòng / mẫu số, số khách sạn ở mức phòng cao nhất đã quét, mức thị trường so thường lệ. */
function Headline({ list }: { list: CityListOut }) {
  const t = useTranslations("marketTab.today");
  const available = list.properties_found ?? 0;
  const base = list.segment_base ?? null;
  const counts = rungMap(list.ladder);
  // Mức phòng cao nhất có số (thường là 30): "217 khách sạn còn ít nhất 30 phòng".
  const rooms = [...LADDER_RUNGS].reverse().find((n) => n > 1 && rungCount(counts, n) !== null) ?? null;
  const deep = rooms === null ? null : rungCount(counts, rooms);
  const level = marketLevel(list.sold_out_share);
  const trend = tightnessTrend(list.tightness, list.tightness_median);
  return (
    <p className="text-lg leading-relaxed text-body">
      {base !== null ? t.rich("available", { available, base, b: BOLD }) : t.rich("availableNoBase", { available, b: BOLD })}
      {deep !== null && rooms !== null && (
        <>
          {"; "}
          {t.rich("deep", { count: deep, rooms, b: BOLD })}
        </>
      )}
      {level && (
        <>
          {" — "}
          <span className="font-semibold text-ink" title={t("moodTitle", { deep: DEEP_RUNG })}>
            {t("mood", { level, trend: trend ?? "none" })}
          </span>
        </>
      )}
      .
    </p>
  );
}

/** Hai tỉ lệ "hết phòng" khác nhau, mỗi số kèm câu nói nó tính trên gì. */
function SoldOutExplained({ list }: { list: CityListOut }) {
  const t = useTranslations("marketTab.today");
  const share = list.sold_out_share;
  const available = list.properties_found;
  const base = list.segment_base ?? null;
  const booking = list.unavailability_pct ?? null;
  const lines: ReactNode[] = [];
  if (share !== null && share !== undefined && available !== null && base !== null) {
    const pct = Math.round(share * 100);
    // Mẫu số là số còn phòng nhiều nhất từng thấy nên tỉ lệ là mức tối thiểu, trừ 0% và 100%.
    lines.push(t.rich("soldOutLine", { pct, bound: pct > 0 && pct < 100 ? "floor" : "exact", available, base, b: BOLD }));
  }
  if (booking !== null) lines.push(t.rich("bookingLine", { pct: booking, b: BOLD }));
  else if (list.low_availability) lines.push(t("bookingLow"));
  if (lines.length === 0) return null;
  return (
    <ul className="space-y-1.5 text-sm text-body">
      {lines.map((l, i) => (
        <li key={i}>{l}</li>
      ))}
    </ul>
  );
}

/** Số khách sạn còn bán được ít nhất 1/5/10/20/30 phòng; rê chuột xem theo hạng sao. */
function Ladder({ ladder }: { ladder: LadderRungOut[] }) {
  const t = useTranslations("marketTab.today");
  const { fmtInt } = useFmt();
  const counts = rungMap(ladder);
  const base = counts.get(1);
  if (base === undefined || counts.size < 2) return <p className="text-xs text-muted">{t("ladderMissing")}</p>;
  return (
    <div className="min-w-0">
      <div className={MICRO}>{t("ladder")}</div>
      <ul className="mt-1.5 space-y-1.5">
        {LADDER_RUNGS.map((n) => {
          const count = rungCount(counts, n);
          const byClass = Object.entries(ladder.find((r) => r.rooms === n)?.by_class ?? {})
            .filter(([stars, c]) => /^[1-5]$/.test(stars) && c > 0)
            .sort(([a], [b]) => Number(b) - Number(a))
            .map(([stars, c]) => t("classItem", { stars, count: c }))
            .join(" · ");
          const title = count === null ? t("ladderUnknown", { rooms: n }) : [t("ladderTitle", { count, rooms: n }), byClass].filter(Boolean).join(" · ");
          return (
            <li key={n} title={title} className="flex items-center gap-2 text-xs">
              <span className="w-[104px] shrink-0 whitespace-nowrap text-muted">{t("ladderRow", { rooms: n })}</span>
              <span aria-hidden className="relative h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-sunken">
                {count !== null && count > 0 && base > 0 && (
                  <span className="absolute inset-y-0 left-0 rounded-full bg-brand" style={{ width: `${Math.max(3, Math.min(100, (count / base) * 100))}%` }} />
                )}
              </span>
              <span className="w-9 shrink-0 text-right font-semibold text-ink tabular">{count === null ? "—" : fmtInt(count)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Fact({ label, value, title }: { label: string; value: ReactNode; title?: string }) {
  return (
    <div title={title} className="min-w-0">
      <dt className={MICRO}>{label}</dt>
      <dd className="text-md font-bold leading-snug text-ink tabular">{value}</dd>
    </div>
  );
}

/** Tổng phòng còn bán (mức tối thiểu) và giá giữa của khu vực. */
function Facts({ list }: { list: CityListOut }) {
  const t = useTranslations("marketTab.today");
  const { fmtPriceShort } = useFmt();
  const floor = list.rooms_left_floor ?? null;
  const med = num(list.median);
  if (floor === null && med === null) return null;
  return (
    <dl className="grid grid-cols-2 gap-3">
      {floor !== null && <Fact label={t("floor")} title={t("floorTitle")} value={t("floorValue", { count: floor })} />}
      {med !== null && <Fact label={t("median")} title={t("medianTitle", { priced: list.priced })} value={fmtPriceShort(med, list.currency)} />}
    </dl>
  );
}

/** Cả thị trường (mọi loại chỗ ở, không lọc phân khúc): số còn phòng và các loại chỗ ở nhiều nhất. */
function Composition({ list }: { list: CityListOut }) {
  const t = useTranslations("marketTab.today");
  const { propertyTypeLabel } = useMarketAreaText();
  const total = list.market_available ?? null;
  const items = compositionGroups(list.composition).map((g) => t("compositionItem", { type: propertyTypeLabel(g.type), count: g.count }));
  if (total === null && items.length === 0) return null;
  return (
    <p className="text-xs text-muted">
      {total !== null && t.rich("composition", { count: total, b: (c) => <span className="font-semibold text-body tabular">{c}</span> })}
      {total !== null && items.length > 0 ? " · " : null}
      {items.slice(0, 4).join(" · ")}
    </p>
  );
}

type Bar = { height: number; title: string };

/** Phân bố giá: ưu tiên biểu đồ ngân sách của Booking (50 cột), không có thì nhóm giá của danh sách. */
function PriceDistribution({ list, me }: { list: CityListOut; me: SelfMarketOut | null }) {
  const t = useTranslations("marketTab.today");
  const { fmtPriceShort } = useFmt();
  const currency = list.currency;
  const own = me?.in_area ? num(me.price) : null;
  const hist = list.booking_histogram ?? null;
  const lo = num(hist?.min);
  const hi = num(hist?.max);
  if (hist && lo !== null && hi !== null && hi > lo && hist.bars.some((b) => b > 0)) {
    const step = (hi - lo) / hist.bars.length;
    const bars = hist.bars.map((b, i) => ({ height: b, title: `${fmtPriceShort(lo + i * step, currency)}–${fmtPriceShort(lo + (i + 1) * step, currency)}` }));
    return (
      <Histogram
        caption={t("priceBooking")}
        bars={bars}
        // Giá của bạn trên trục min–max; đắt hơn max thì sát mép phải.
        mark={own === null ? null : Math.max(0, Math.min(1, (own - lo) / (hi - lo)))}
        left={fmtPriceShort(lo, currency)}
        right={fmtPriceShort(hi, currency)}
        note={t("priceBookingNote", { max: fmtPriceShort(hi, currency) })}
      />
    );
  }
  const buckets = list.histogram;
  if (buckets.length === 0) return null;
  const top = Math.max(1, ...buckets.map((b) => b.count));
  const bars = buckets.map((b) => ({
    height: (b.count / top) * 100,
    title: t("barTitle", { range: `${fmtPriceShort(b.lo, currency)}${b.hi ? `–${fmtPriceShort(b.hi, currency)}` : "+"}`, count: b.count }),
  }));
  const at = own === null ? -1 : buckets.findIndex((b, i) => (i === 0 || own >= (num(b.lo) ?? 0)) && (b.hi === null || own < (num(b.hi) ?? Infinity)));
  return (
    <Histogram
      caption={list.sample ? t("histogramSample", { priced: list.priced, found: list.properties_found ?? list.priced }) : t("histogramAll", { priced: list.priced })}
      captionTitle={list.sample ? t("sampleTitle") : undefined}
      bars={bars}
      mark={at < 0 ? null : (at + 0.5) / buckets.length}
      left={`<${fmtPriceShort(buckets[0].hi, currency)}`}
      right={`${fmtPriceShort(buckets[buckets.length - 1].lo, currency)}+`}
    />
  );
}

function Histogram({ caption, captionTitle, bars, mark, left, right, note }: { caption: string; captionTitle?: string; bars: Bar[]; mark: number | null; left: string; right: string; note?: string }) {
  const t = useTranslations("marketTab.today");
  return (
    <div>
      <div className={MICRO} title={captionTitle}>
        {caption}
      </div>
      <div className={cx("mt-1.5 flex h-10 items-end border-b border-line", bars.length > 20 ? "gap-px" : "gap-0.5")}>
        {bars.map((b, i) => (
          <span key={i} title={b.title} className="min-w-0 flex-1 rounded-t-[2px]" style={{ height: `${b.height > 0 ? Math.max(4, b.height) : 0}%`, background: barColor(i, bars.length) }} />
        ))}
      </div>
      {mark !== null && (
        <div aria-hidden className="relative h-2.5">
          <span className="absolute top-0.5 h-2 w-2 -translate-x-1/2 rounded-full bg-brand ring-2 ring-surface" style={{ left: `${mark * 100}%` }} />
        </div>
      )}
      <div className="mt-0.5 flex justify-between gap-2 text-[11px] text-muted tabular">
        <span>{left}</span>
        {mark !== null && (
          <span className="flex items-center gap-1">
            <span aria-hidden className="h-2 w-2 rounded-full bg-brand" /> {t("yoursMark")}
          </span>
        )}
        <span>{right}</span>
      </div>
      {note && <p className="mt-0.5 text-[11px] text-muted">{note}</p>}
    </div>
  );
}

/** Khách sạn của bạn trên thị trường: phòng còn, giá và vị trí giá, vị trí trên Booking.com. */
function SelfLine({ me }: { me: SelfMarketOut }) {
  const t = useTranslations("marketTab.today");
  const { fmtInt, fmtPriceShort } = useFmt();
  // Quét trang khách sạn chính xác hơn (tới 100 phòng) → ưu tiên; không có thì kết quả tìm kiếm.
  const page = roomsRange(me.rooms_left_min, me.rooms_left_max);
  const rooms = page ?? roomsRange(me.rooms_min, me.rooms_max);
  const facts: Array<{ text: string; title?: string }> = [];
  if (!me.in_area) facts.push({ text: t("selfNotInArea"), title: t("selfNotInAreaTitle") });
  if (rooms) {
    const source = page ? t("selfRoomsPage") : t("selfRoomsSearch");
    facts.push({
      // "còn ít nhất 30 phòng" thay cho "≥30" (L1).
      text: rooms.max === 0 ? t("selfSoldOut") : rooms.max === null ? t("selfRoomsAtLeast", { count: rooms.min }) : t("selfRooms", { rooms: roomsLeftText(rooms, fmtInt) }),
      title: me.rooms_percentile !== null ? `${source} · ${t("selfRoomsPercentile", { pct: me.rooms_percentile })}` : source,
    });
  }
  const price = me.in_area ? num(me.price) : null;
  if (price !== null) {
    const p = me.price_percentile;
    const text = fmtPriceShort(price, me.currency);
    facts.push({ text: p === null ? text : p >= 50 ? t("selfPricier", { price: text, pct: p }) : t("selfCheaper", { price: text, pct: 100 - p }) });
  }
  if (me.in_area && me.rank !== null) facts.push({ text: t("selfRank", { rank: me.rank }), title: t("selfRankTitle") });
  return (
    <div className="mt-3 rounded-lg bg-brand-softer px-3 py-2.5 text-sm">
      <div className="flex min-w-0 flex-wrap items-center gap-x-1.5">
        <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-brand" />
        <span className="font-semibold text-ink">{t("yours")}</span>
        {me.name && <span className="min-w-0 truncate text-muted">· {me.name}</span>}
      </div>
      {facts.length > 0 && (
        <p className="mt-0.5 text-body">
          {facts.map((f, i) => (
            <span key={i} title={f.title}>
              {i > 0 && " · "}
              {f.text}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

/** Chưa có lượt quét đêm nay, đang quét, hoặc lượt quét không đọc được số. */
function NoData({ status }: { status: string | null }) {
  const t = useTranslations("marketTab.today");
  const kind = status === "running" ? "running" : status === "blocked" || status === "error" ? "failed" : "empty";
  const link = (c: ReactNode) => (
    <Link href="/settings?tab=market" className="font-semibold text-brand hover:underline">
      {c}
    </Link>
  );
  return (
    <EmptyState compact icon={<IconPin size={18} />} title={t(`${kind}Title`)} className="min-h-[200px]">
      <span className="text-sm">{t.rich(`${kind}Body`, { link })}</span>
    </EmptyState>
  );
}
