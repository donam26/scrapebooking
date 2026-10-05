"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useRef } from "react";
import type { EventOut } from "@/lib/api";
import { num, useFmt, type Fmt } from "@/lib/format";
import { channelName, withChannel } from "@/lib/channels";
import { EVENT_TYPE_TONE, useLabel, type LabelFn } from "@/lib/labels";
import { MarkSwatch, useMarks } from "./marks";
import { IconArrowDown, IconArrowUp, IconPulse } from "./icons";
import { Badge, EmptyState, cx } from "./ui";

type EventTableTranslator = ReturnType<typeof useTranslations<"components.eventTable">>;

export function EventTypeBadge({ type }: { type: string }) {
  const label = useLabel();
  return <Badge tone={EVENT_TYPE_TONE[type] ?? "gray"}>{label("eventType", type)}</Badge>;
}

const PRICE_EVENTS = new Set(["price_up", "price_down"]);
const ROOM_EVENTS = new Set(["rooms_decrease", "rooms_increase", "low_stock_enter"]);

/** Giá trị phòng còn: số (`n`: đã định dạng, kèm "≥" khi là mức sàn) hoặc nhãn mức tin cậy. */
function roomsValue(v: string | null, floor: boolean, fmt: Fmt, label: LabelFn): { n: string; count: number } | { text: string } | null {
  if (v === null || v === "") return null;
  const n = num(v);
  if (n !== null) return { n: `${floor ? "≥" : ""}${fmt.fmtInt(n)}`, count: n };
  const confidence = label("stockConfidence", v);
  return { text: confidence !== v ? confidence : label("availability", v) };
}

/** Giá trị phòng còn thành chữ: số -> "6 phòng", mức tin cậy -> nhãn. */
function roomsText(r: ReturnType<typeof roomsValue>, floor: boolean, t: EventTableTranslator): string | null {
  if (r === null) return null;
  if ("text" in r) return r.text;
  return t(floor ? "roomsFloor" : "rooms", { count: r.count });
}

/** Thay đổi đọc thành chữ: "7 → 6 phòng", "Còn phòng → Hết", "4,55 Tr → 4,29 Tr". */
function changeText(e: EventOut, t: EventTableTranslator, fmt: Fmt, label: LabelFn): { main: string; delta: string | null; dir: "up" | "down" | null } {
  const type = e.event_type;
  const floor = e.confidence === "capped";
  if (type === "sold_out") return { main: t("soldOut"), delta: null, dir: null };
  if (type === "channel_closed") {
    // from_value = các kênh khác vẫn bán, ngăn bằng dấu phẩy.
    const open = (e.from_value ?? "").split(",").filter(Boolean).map(channelName);
    return { main: open.length ? t("stillSelling", { channels: open.join(", ") }) : t("otherChannelsSelling"), delta: null, dir: null };
  }
  if (type === "parity_gap") {
    // from_value = "<kênh rẻ nhất còn lại>:<giá>", to_value = giá ở kênh này, delta = % chênh (âm).
    const otherPrice = (e.from_value ?? "").split(":")[1];
    const d = num(e.delta);
    return {
      main: `${fmt.fmtNum(otherPrice, 0)} → ${fmt.fmtNum(e.to_value, 0)}`,
      delta: d === null ? null : `${fmt.fmtSigned(Math.round(d * 10) / 10)}%`,
      dir: "down",
    };
  }
  if (type === "restock") return { main: t("restock"), delta: null, dir: null };
  if (PRICE_EVENTS.has(type)) {
    const d = num(e.delta);
    return {
      main: `${fmt.fmtNum(e.from_value, 0)} → ${fmt.fmtNum(e.to_value, 0)}`,
      delta: d === null ? null : `${fmt.fmtSigned(Math.round(d * 10) / 10)}%`,
      dir: type === "price_up" ? "up" : "down",
    };
  }
  if (type === "room_type_new") {
    const to = roomsText(roomsValue(e.to_value, floor, fmt, label), floor, t);
    return { main: to ? t("roomTypeNewRooms", { rooms: to }) : t("roomTypeNew"), delta: null, dir: null };
  }
  if (type === "room_type_gone") {
    const from = roomsText(roomsValue(e.from_value, floor, fmt, label), floor, t);
    return { main: from ? t("roomTypeGoneRooms", { rooms: from }) : t("roomTypeGone"), delta: null, dir: null };
  }
  if (ROOM_EVENTS.has(type)) {
    const fromV = roomsValue(e.from_value, floor, fmt, label);
    const toV = roomsValue(e.to_value, floor, fmt, label);
    const d = num(e.delta);
    // Cùng là số: "7 → 6 phòng" (đơn vị một lần ở cuối).
    const main =
      fromV && toV && "n" in fromV && "n" in toV
        ? t("roomsChange", { from: fromV.n, to: toV.n, count: toV.count })
        : `${roomsText(fromV, floor, t) ?? "—"} → ${roomsText(toV, floor, t) ?? "—"}`;
    return {
      main,
      delta: d === null ? null : fmt.fmtSigned(d),
      dir: d === null ? null : d > 0 ? "up" : "down",
    };
  }
  return { main: `${e.from_value ?? "—"} → ${e.to_value ?? "—"}`, delta: e.delta, dir: null };
}

/** Mức tin cậy chỉ hiện khi khác "chính xác" (ít nhất, ẩn, hoặc mức cao/thấp của sự kiện giá). */
function ConfidenceNote({ confidence }: { confidence: string }) {
  const t = useTranslations("components.eventTable");
  const label = useLabel();
  const { roomMark } = useMarks();
  // "Ít nhất" đã hiện bằng dấu ≥ ngay trong con số.
  if (confidence === "exact" || confidence === "capped") return null;
  if (confidence === "capped" || confidence === "hidden" || confidence === "sold_out") {
    const mark = roomMark({ stock_confidence: confidence, rooms_left: null, dropdown_max: null });
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted" title={t("confidenceTitle")}>
        <MarkSwatch mark={{ ...mark, text: "" }} size={12} className="rounded-[3px]" />
        {label("stockConfidence", confidence)}
      </span>
    );
  }
  return <span className="text-xs text-muted">{t("confidenceLevel", { level: label("level", confidence).toLowerCase() })}</span>;
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
  const t = useTranslations("components.eventTable");
  const fmt = useFmt();
  const label = useLabel();
  const ch = changeText(e, t, fmt, label);
  const hotel = labelOf?.(e.hotel_id) || e.hotel_name || t("hotelFallback", { id: e.hotel_id });
  const channel = channelName(e.channel);
  // Chênh giá giữa kênh: thay "loại phòng" bằng kênh đem so (giá bên trái của thay đổi).
  const scope = e.event_type === "parity_gap" ? t("vsChannel", { channel: channelName((e.from_value ?? "").split(":")[0]) }) : (e.room_type_name ?? t("wholeHotel"));
  return (
    <li
      ref={rowRef}
      id={`evt-${e.id}`}
      className={cx(
        "grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-5 py-2.5 transition-colors duration-150 md:grid-cols-[150px_minmax(0,1fr)_92px_118px_228px]",
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
              <Link href={withChannel(`/hotels/${e.hotel_id}`, e.channel)} className="font-semibold text-ink hover:text-brand hover:underline" title={e.hotel_name ?? undefined}>
                {hotel}
              </Link>
              <span className="text-faint"> · </span>
            </>
          )}
          <span className={cx(e.room_type_name ? "text-body" : "text-muted")}>{scope}</span>
          <span className="text-muted md:hidden"> · {channel}</span>
        </div>
        <ConfidenceNote confidence={e.confidence} />
      </div>
      <span className="hidden truncate text-sm text-body md:block" title={t("observedOn", { channel })}>
        {channel}
      </span>
      <Link
        href={withChannel(`/hotels/${e.hotel_id}/dates/${e.stay_date}`, e.channel)}
        className="row-start-1 col-start-2 justify-self-end whitespace-nowrap rounded-md px-1.5 py-0.5 text-sm font-semibold text-brand tabular hover:bg-brand-softer md:col-start-auto md:row-start-auto md:justify-self-start"
        title={t("openNight")}
      >
        {t("night", { night: fmt.fmtNight(e.stay_date) })}
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
  emptyText,
  labelOf,
}: {
  events: EventOut[];
  highlightId?: number | null;
  showHotel?: boolean;
  emptyText?: string;
  /** Nhãn ngắn của khách sạn trong watchlist (thay cho tên đầy đủ trên kênh). */
  labelOf?: (hotelId: number) => string | undefined;
}) {
  const t = useTranslations("components.eventTable");
  const { fmtWhen } = useFmt();
  const highlightRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlightId, events]);

  if (events.length === 0) {
    return (
      <div className="p-5">
        <EmptyState icon={<IconPulse />} compact>
          {emptyText ?? t("empty")}
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
        <section key={`${g.run}-${g.at}`} aria-label={t("run", { when: fmtWhen(g.at) })}>
          <h3 className="sticky top-0 z-10 flex items-baseline gap-2 border-y border-line bg-subtle/95 px-5 py-1.5 text-xs font-semibold text-muted backdrop-blur-sm max-lg:top-14 first:border-t-0">
            <span className="text-body">{t("run", { when: fmtWhen(g.at) })}</span>
            <span>· {t("changes", { count: g.items.length })}</span>
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
