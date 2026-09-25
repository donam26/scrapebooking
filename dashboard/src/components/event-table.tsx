"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import type { EventOut } from "@/lib/api";
import { fmtInt, fmtNight, fmtNum, fmtSigned, fmtWhen, num, prettySlug } from "@/lib/format";
import { AVAILABILITY_LABEL, EVENT_TYPE_LABEL, EVENT_TYPE_TONE, LEVEL_LABEL, STOCK_CONFIDENCE_LABEL } from "@/lib/labels";
import { MarkSwatch, roomMark } from "./marks";
import { IconArrowDown, IconArrowUp, IconPulse } from "./icons";
import { Badge, EmptyState, cx } from "./ui";

export function EventTypeBadge({ type }: { type: string }) {
  return <Badge tone={EVENT_TYPE_TONE[type] ?? "gray"}>{EVENT_TYPE_LABEL[type] ?? type}</Badge>;
}

const PRICE_EVENTS = new Set(["price_up", "price_down"]);
const ROOM_EVENTS = new Set(["rooms_decrease", "rooms_increase", "low_stock_enter"]);

/** Giá trị phòng còn: số -> "6 phòng", mức tin cậy -> nhãn. */
function roomsText(v: string | null, floor = false): string | null {
  if (v === null || v === "") return null;
  const n = num(v);
  if (n !== null) return `${floor ? "≥" : ""}${fmtInt(n)} phòng`;
  return STOCK_CONFIDENCE_LABEL[v] ?? AVAILABILITY_LABEL[v] ?? v;
}

/** Thay đổi đọc thành chữ: "7 → 6 phòng", "Còn phòng → Hết", "4,55 Tr → 4,29 Tr". */
function changeText(e: EventOut): { main: string; delta: string | null; dir: "up" | "down" | null } {
  const t = e.event_type;
  const floor = e.confidence === "capped";
  if (t === "sold_out") return { main: "Còn phòng → Hết phòng", delta: null, dir: null };
  if (t === "restock") return { main: "Hết phòng → Còn phòng", delta: null, dir: null };
  if (PRICE_EVENTS.has(t)) {
    const d = num(e.delta);
    return {
      main: `${fmtNum(e.from_value, 0)} → ${fmtNum(e.to_value, 0)}`,
      delta: d === null ? null : `${fmtSigned(Math.round(d * 10) / 10)}%`,
      dir: t === "price_up" ? "up" : "down",
    };
  }
  if (t === "room_type_new") {
    const to = roomsText(e.to_value, floor);
    return { main: to ? `Mở bán, còn ${to}` : "Mở bán", delta: null, dir: null };
  }
  if (t === "room_type_gone") {
    const from = roomsText(e.from_value, floor);
    return { main: from ? `Ngừng bán (trước đó ${from})` : "Ngừng bán", delta: null, dir: null };
  }
  if (ROOM_EVENTS.has(t)) {
    const from = roomsText(e.from_value, floor) ?? "—";
    const to = roomsText(e.to_value, floor) ?? "—";
    const d = num(e.delta);
    const sameUnit = from.endsWith("phòng") && to.endsWith("phòng");
    return {
      main: sameUnit ? `${from.replace(" phòng", "")} → ${to}` : `${from} → ${to}`,
      delta: d === null ? null : fmtSigned(d),
      dir: d === null ? null : d > 0 ? "up" : "down",
    };
  }
  return { main: `${e.from_value ?? "—"} → ${e.to_value ?? "—"}`, delta: e.delta, dir: null };
}

/** Mức tin cậy chỉ hiện khi khác "chính xác" (ít nhất, ẩn, hoặc mức cao/thấp của sự kiện giá). */
function ConfidenceNote({ confidence }: { confidence: string }) {
  // "Ít nhất" đã hiện bằng dấu ≥ ngay trong con số.
  if (confidence === "exact" || confidence === "capped") return null;
  if (confidence === "capped" || confidence === "hidden" || confidence === "sold_out") {
    const mark = roomMark({ stock_confidence: confidence, rooms_left: null, dropdown_max: null });
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted" title="Mức tin cậy của số phòng">
        <MarkSwatch mark={{ ...mark, text: "" }} size={12} className="rounded-[3px]" />
        {STOCK_CONFIDENCE_LABEL[confidence]}
      </span>
    );
  }
  const lv = LEVEL_LABEL[confidence];
  return <span className="text-xs text-muted">Tin cậy {lv ? lv.toLowerCase() : confidence}</span>;
}

function EventRow({
  e,
  showHotel,
  highlighted,
  rowRef,
  labelOf,
}: {
  e: EventOut;
  showHotel: boolean;
  highlighted: boolean;
  rowRef?: React.Ref<HTMLLIElement>;
  labelOf?: (hotelId: number) => string | undefined;
}) {
  const ch = changeText(e);
  const hotel = labelOf?.(e.hotel_id) || e.hotel_name || prettySlug(e.hotel_slug);
  return (
    <li
      ref={rowRef}
      id={`evt-${e.id}`}
      className={cx(
        "grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-5 py-2.5 transition-colors duration-150 md:grid-cols-[136px_minmax(0,1fr)_118px_228px]",
        highlighted ? "bg-brand-softer ring-2 ring-inset ring-brand/40" : "hover:bg-subtle",
      )}
    >
      <div className="md:order-none">
        <EventTypeBadge type={e.event_type} />
      </div>
      <div className="col-span-2 min-w-0 md:col-span-1">
        <div className="truncate text-base">
          {showHotel && (
            <>
              <Link href={`/hotels/${e.hotel_id}`} className="font-semibold text-ink hover:text-brand hover:underline" title={e.hotel_name ?? undefined}>
                {hotel}
              </Link>
              <span className="text-faint"> · </span>
            </>
          )}
          <span className={cx(e.room_type_name ? "text-body" : "text-muted")}>{e.room_type_name ?? "Toàn khách sạn"}</span>
        </div>
        <ConfidenceNote confidence={e.confidence} />
      </div>
      <Link
        href={`/hotels/${e.hotel_id}/dates/${e.stay_date}`}
        className="row-start-1 col-start-2 justify-self-end whitespace-nowrap rounded-md px-1.5 py-0.5 text-sm font-semibold text-brand tabular hover:bg-brand-softer md:col-start-auto md:row-start-auto md:justify-self-start"
        title="Mở chi tiết đêm này"
      >
        Đêm {fmtNight(e.stay_date)}
      </Link>
      <div className="col-span-2 flex items-center gap-2 whitespace-nowrap text-sm tabular md:col-span-1 md:justify-end">
        <span className="text-body">{ch.main}</span>
        {ch.delta && (
          <span
            className={cx(
              "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-bold",
              ch.dir === "down" ? "bg-warning-soft text-warning-deep" : "bg-sunken text-ink",
            )}
          >
            {ch.dir === "up" && <IconArrowUp size={12} />}
            {ch.dir === "down" && <IconArrowDown size={12} />}
            {ch.delta.replace("-", "−")}
          </span>
        )}
      </div>
    </li>
  );
}

/**
 * Dòng sự kiện, nhóm theo lượt quét. Mỗi dòng đọc thành câu:
 * loại · khách sạn · loại phòng · đêm · thay đổi. Mức tin cậy chỉ hiện khi khác "chính xác".
 */
export function EventTable({
  events,
  highlightId,
  showHotel = true,
  emptyText = "Không có sự kiện nào trong khoảng đã chọn.",
  labelOf,
}: {
  events: EventOut[];
  highlightId?: number | null;
  showHotel?: boolean;
  emptyText?: string;
  /** Nhãn ngắn của khách sạn trong watchlist (thay cho tên đầy đủ trên Booking). */
  labelOf?: (hotelId: number) => string | undefined;
}) {
  const highlightRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlightId, events]);

  if (events.length === 0) {
    return (
      <div className="p-5">
        <EmptyState icon={<IconPulse />} compact>
          {emptyText}
        </EmptyState>
      </div>
    );
  }

  // Nhóm liên tiếp theo lượt quét (API đã sắp theo thời điểm mới nhất trước).
  const groups: Array<{ run: number; at: string; items: EventOut[] }> = [];
  for (const e of events) {
    const last = groups[groups.length - 1];
    if (last && last.run === e.scan_run_id) last.items.push(e);
    else groups.push({ run: e.scan_run_id, at: e.observed_at, items: [e] });
  }

  return (
    <div>
      {groups.map((g) => (
        <section key={`${g.run}-${g.at}`} aria-label={`Lượt quét ${fmtWhen(g.at)}`}>
          <h3 className="sticky top-0 z-10 flex items-baseline gap-2 border-y border-line bg-subtle/95 px-5 py-1.5 text-xs font-semibold text-muted backdrop-blur-sm max-lg:top-14 first:border-t-0">
            <span className="text-body">Lượt quét {fmtWhen(g.at)}</span>
            <span>
              · {g.items.length} thay đổi
            </span>
          </h3>
          <ul className="divide-y divide-line/70">
            {g.items.map((e) => {
              const hl = highlightId !== null && highlightId !== undefined && e.id === highlightId;
              return <EventRow key={e.id} e={e} showHotel={showHotel} highlighted={hl} rowRef={hl ? highlightRef : undefined} labelOf={labelOf} />;
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
