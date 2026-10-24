"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import type { EventOut } from "@/lib/api";
import { daysBetween, useFmt } from "@/lib/format";
import { useLabel } from "@/lib/labels";
import { useRateText } from "@/lib/rate-text";
import { EventTypeBadge, changeText, noteText } from "./event-table";
import { Button, Card, EmptyState, Switch, cx } from "./ui";
import { IconArrowDown, IconArrowUp, IconPulse } from "./icons";

/**
 * Nhật ký thay đổi của một khách sạn, gom theo đêm (F1):
 * - "Giảm phòng" và "Sắp hết phòng" của cùng lượt quét, cùng đêm, cùng loại phòng thành một dòng;
 * - thay đổi ±1 phòng ẩn mặc định ("Hiện cả thay đổi nhỏ");
 * - đêm sắp tới trước (gần nhất trước), đêm đã qua sau; 20 đêm đầu, "Xem thêm" cho phần còn lại;
 * - mỗi đêm hiện 2 dòng mới nhất, phần còn lại mở bằng "+N thay đổi" (đêm đổi giá cả chục loại phòng).
 */

const PAGE = 20;
const LINES_PER_NIGHT = 2;
const ROOM_MOVES = new Set(["rooms_increase", "rooms_decrease"]);
/** Đổi giá: mobile viết gọn "4,8tr → 5,8tr" để cả dòng nằm một hàng. */
const PRICE_MOVES = new Set(["price_up", "price_down", "lowest_rate_shift"]);

type Line = { e: EventOut; lowStock: EventOut | null; minor: boolean };
type Group = { night: string; lines: Line[] };

const keyOf = (e: EventOut) => `${e.scan_run_id}|${e.stay_date}|${e.room_type_id ?? "-"}`;

function isMinor(e: EventOut): boolean {
  if (!ROOM_MOVES.has(e.event_type)) return false;
  const d = Number(e.delta);
  return Number.isFinite(d) && Math.abs(d) <= 1;
}

/** Dòng nhật ký: ghép "Giảm phòng" + "Sắp hết phòng" của cùng một biến động. */
export function buildLines(events: EventOut[]): Line[] {
  const low = new Map<string, EventOut>();
  for (const e of events) if (e.event_type === "low_stock_enter") low.set(keyOf(e), e);
  const merged = new Set<number>();
  const lines: Line[] = [];
  for (const e of events) {
    if (e.event_type !== "rooms_decrease") continue;
    const l = low.get(keyOf(e)) ?? null;
    if (l) merged.add(l.id);
    lines.push({ e, lowStock: l, minor: !l && isMinor(e) });
  }
  for (const e of events) {
    if (e.event_type === "rooms_decrease" || merged.has(e.id)) continue;
    lines.push({ e, lowStock: null, minor: isMinor(e) });
  }
  return lines.sort((a, b) => b.e.observed_at.localeCompare(a.e.observed_at) || b.e.id - a.e.id);
}

function groupByNight(lines: Line[], today: string | null): { upcoming: Group[]; past: Group[] } {
  const by = new Map<string, Line[]>();
  for (const l of lines) {
    const g = by.get(l.e.stay_date);
    if (g) g.push(l);
    else by.set(l.e.stay_date, [l]);
  }
  const groups = [...by.entries()].map(([night, ls]) => ({ night, lines: ls }));
  const upcoming = groups.filter((g) => !today || g.night >= today).sort((a, b) => a.night.localeCompare(b.night));
  const past = today ? groups.filter((g) => g.night < today).sort((a, b) => b.night.localeCompare(a.night)) : [];
  return { upcoming, past };
}

function LogLine({ line }: { line: Line }) {
  const t = useTranslations("components.eventTable");
  const tl = useTranslations("components.nightLog");
  const fmt = useFmt();
  const label = useLabel();
  const rt = useRateText();
  const { e, lowStock } = line;
  const ch = changeText(e, t, fmt, label);
  const note = noteText(e, t, rt);
  const scope = e.room_type_name ?? t("wholeHotel");
  const short = PRICE_MOVES.has(e.event_type) && e.from_value !== null && e.to_value !== null ? `${fmt.fmtCompact(e.from_value)} → ${fmt.fmtCompact(e.to_value)}` : null;
  // Mobile: hàng 1 = loại thay đổi + con số, hàng 2 = loại phòng + giờ thấy (hai hàng flex).
  // Desktop: `md:contents` thả 4 phần vào lưới 4 cột của dòng, sắp lại bằng `order`.
  return (
    <li className="px-5 py-1 hover:bg-subtle md:grid md:grid-cols-[auto_minmax(0,1fr)_auto_88px] md:items-center md:gap-x-3 md:py-1.5">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 md:contents">
        <div className="flex shrink-0 flex-wrap items-center gap-1 md:order-1">
          <EventTypeBadge type={e.event_type} />
          {lowStock && <EventTypeBadge type={lowStock.event_type} />}
        </div>
        <div className="ml-auto flex shrink-0 items-center justify-end gap-1.5 whitespace-nowrap text-sm tabular md:order-3" title={note ?? undefined}>
          {short ? (
            <>
              <span className="text-body md:hidden" title={ch.main}>
                {short}
              </span>
              <span className="text-body max-md:hidden">{ch.main}</span>
            </>
          ) : (
            <span className="text-body">{ch.main}</span>
          )}
          {ch.delta && (
            <span className={cx("inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-bold", ch.dir === "down" ? "bg-warning-soft text-warning-deep" : "bg-sunken text-ink")}>
              {ch.dir === "up" && <IconArrowUp size={12} />}
              {ch.dir === "down" && <IconArrowDown size={12} />}
              {ch.delta.replace("-", "−")}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between gap-2 md:contents">
        <span className={cx("min-w-0 truncate text-xs md:order-2 md:text-sm", e.room_type_name ? "text-body" : "text-muted")} title={scope}>
          {scope}
        </span>
        <span className="shrink-0 text-right text-xs text-muted tabular md:order-4" title={tl("seenAt", { when: fmt.fmtDateTime(e.observed_at) })}>
          {fmt.fmtWhen(e.observed_at)}
        </span>
      </div>
    </li>
  );
}

function NightGroup({ g, hotelId, today }: { g: Group; hotelId: number; today: string | null }) {
  const tl = useTranslations("components.nightLog");
  const { fmtNight, fmtNightRel } = useFmt();
  const [open, setOpen] = useState(false);
  const rel = today && g.night >= today ? fmtNightRel(daysBetween(today, g.night)) : null;
  const lines = open ? g.lines : g.lines.slice(0, LINES_PER_NIGHT);
  const hidden = g.lines.length - lines.length;
  return (
    <section aria-label={fmtNight(g.night)}>
      <h3 className="flex flex-wrap items-baseline gap-x-2 border-y border-line bg-subtle px-5 py-1 text-xs text-muted">
        <Link href={`/hotels/${hotelId}/dates/${g.night}`} className="text-sm font-bold text-ink hover:text-brand hover:underline">
          {fmtNight(g.night)}
        </Link>
        {rel && <span>{rel}</span>}
        <span>· {tl("changes", { count: g.lines.length })}</span>
      </h3>
      <ul className="divide-y divide-line/70">
        {lines.map((l) => (
          <LogLine key={l.e.id} line={l} />
        ))}
      </ul>
      {(hidden > 0 || (open && g.lines.length > LINES_PER_NIGHT)) && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="w-full border-t border-line/70 px-5 py-1 text-left text-xs font-semibold text-brand hover:bg-subtle">
          {open ? tl("fewer") : tl("moreLines", { count: hidden })}
        </button>
      )}
    </section>
  );
}

export function NightChangeLog({ events, hotelId, today, className }: { events: EventOut[]; hotelId: number; today: string | null; className?: string }) {
  const tl = useTranslations("components.nightLog");
  const [showMinor, setShowMinor] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const lines = buildLines(events);
  const minorCount = lines.filter((l) => l.minor).length;
  const { upcoming, past } = groupByNight(
    lines.filter((l) => showMinor || !l.minor),
    today,
  );
  const all = [...upcoming, ...past];
  const shown = all.slice(0, limit);
  const firstPast = upcoming.length;
  const rest = all.length - shown.length;
  return (
    <Card
      title={tl("title")}
      description={tl("description", { count: events.length, nights: all.length })}
      padded={false}
      className={className}
      actions={
        minorCount > 0 ? (
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-body">
            <Switch checked={showMinor} onChange={setShowMinor} label={tl("showMinor")} />
            <span>
              {tl("showMinor")} <span className="text-muted tabular">({minorCount})</span>
            </span>
          </label>
        ) : undefined
      }
    >
      {all.length === 0 ? (
        <div className="p-5">
          <EmptyState icon={<IconPulse />} compact>
            {events.length === 0 ? tl("empty") : tl("onlyMinor", { count: minorCount })}
          </EmptyState>
        </div>
      ) : (
        <div>
          {shown.map((g, i) => (
            <div key={g.night}>
              {i === firstPast && past.length > 0 && <div className={cx("px-5 pb-1 pt-3 text-xs font-semibold uppercase tracking-[0.05em] text-muted", i > 0 && "border-t border-line")}>{tl("past")}</div>}
              <NightGroup g={g} hotelId={hotelId} today={today} />
            </div>
          ))}
          {rest > 0 && (
            <div className="border-t border-line px-5 py-3">
              <Button size="sm" onClick={() => setLimit((n) => n + PAGE)}>
                {tl("more", { count: Math.min(rest, PAGE) })}
              </Button>
              <span className="ml-3 text-xs text-muted">{tl("remaining", { count: rest })}</span>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
