"use client";

import Link from "next/link";
import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { CompsetDayOut, DateCell, HotelRow, OverviewOut } from "@/lib/api";
import { dateRange, fmtCompact, fmtDateShort, fmtInt, fmtMoney, fmtNight, fmtNum, fmtPct, fmtWeekday, isWeekend, num, parseDate, prettySlug } from "@/lib/format";
import { useElementWidth } from "@/lib/use-width";
import { cellMark, MarkSwatch, MarksLegend } from "@/components/marks";
import { IconArrowRight } from "@/components/icons";
import { cx } from "@/components/ui";

/* Hình học dùng chung: mọi dải cùng số cột, cùng khe, nên cột thẳng hàng qua cả chồng. */
const GAP = 3;
const COL_MIN = 28;
const PAD_X = 20; // px-5 trong thẻ
const INK = "#36344d";
const YOURS = "#008a70";
const REF = "#8a89a0";

type Active = { idx: number; x: number; y: number } | null;

export function hotelName(row: HotelRow): string {
  return row.label || row.hotel.name || prettySlug(row.hotel.booking_slug);
}

// ---------------------------------------------------------------------------

/** Chồng dải khách sạn × đêm. `market=false` bỏ thẻ thị trường (trang một khách sạn). */
export function Board({ data, market = true }: { data: OverviewOut; market?: boolean }) {
  const dates = useMemo(() => dateRange(data.start, data.end), [data.start, data.end]);
  const n = dates.length;
  const compset = useMemo(() => new Map<string, CompsetDayOut>(data.compset.map((c) => [c.stay_date, c])), [data.compset]);
  const selfRows = data.hotels.filter((h) => h.role === "self");
  const compRows = data.hotels.filter((h) => h.role !== "self");
  const self = selfRows[0] ?? null;
  const currency = data.compset.find((c) => c.currency)?.currency ?? data.hotels.flatMap((h) => h.cells).find((c) => c.currency)?.currency ?? null;

  const outerRef = useRef<HTMLDivElement>(null);
  const outerW = useElementWidth(outerRef);
  const required = n * COL_MIN + (n - 1) * GAP + PAD_X * 2 + 2;
  const fits = outerW === 0 || outerW >= required;

  const [active, setActive] = useState<Active>(null);
  const activate = useCallback((idx: number, el: Element) => {
    const r = el.getBoundingClientRect();
    setActive({ idx, x: r.right, y: r.top });
  }, []);

  const ctx: StripCtx = { dates, n, active: active?.idx ?? null, activate, fits };

  return (
    <div onMouseLeave={() => setActive(null)} className="relative">
      <MarksLegend className="mb-3" />
      <div ref={outerRef} className={cx(!fits && "sb-scroll -mx-4 overflow-x-auto px-4 pb-3 sm:mx-0 sm:px-0")}>
        <div className="space-y-3" style={fits ? undefined : { width: required }}>
          <Axis ctx={ctx} sticky={fits} />
          {market && <MarketCard ctx={ctx} data={data} compset={compset} self={self} currency={currency} />}
          {selfRows.map((row) => (
            <HotelCard key={row.hotel.id} ctx={ctx} row={row} self={self} compset={compset} />
          ))}
          {compRows.map((row) => (
            <HotelCard key={row.hotel.id} ctx={ctx} row={row} self={self} compset={compset} />
          ))}
        </div>
      </div>

      <div className="mt-4">
        <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
          {market ? (
            <>
              <li className="flex items-center gap-2">
                <LineKey color={YOURS} /> Giá thấp nhất của bạn
              </li>
              <li className="flex items-center gap-2">
                <LineKey color={INK} /> Giá thấp nhất của khách sạn đó
              </li>
              <li className="flex items-center gap-2">
                <LineKey color={INK} dashed /> Trung vị đối thủ (trong dải của bạn)
              </li>
              <li className="text-faint">Rê chuột hoặc Tab vào một đêm để so cả chồng; bấm ô để mở chi tiết đêm.</li>
            </>
          ) : (
            <>
              <li className="flex items-center gap-2">
                <LineKey color={self ? YOURS : INK} /> Giá thấp nhất mỗi đêm
              </li>
              <li className="text-faint">Rê chuột hoặc Tab vào một đêm để xem số liệu; bấm ô để mở chi tiết đêm.</li>
            </>
          )}
        </ul>
      </div>

      {active && <Readout active={active} dates={dates} data={data} compset={compset} currency={currency} />}
    </div>
  );
}

type StripCtx = {
  dates: string[];
  n: number;
  active: number | null;
  activate: (idx: number, el: Element) => void;
  /** Cả chồng vừa màn hình (không cuộn ngang). */
  fits: boolean;
};

function gridStyle(n: number) {
  return { gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`, columnGap: GAP };
}

// ---------------------------------------------------------------------------
// Trục ngày

function Axis({ ctx, sticky }: { ctx: StripCtx; sticky: boolean }) {
  const { dates, n, active } = ctx;
  return (
    <div className={cx("z-20 -mx-1 rounded-lg bg-canvas/95 px-1 pt-1 backdrop-blur-sm", sticky && "sticky top-0 lg:top-0 max-lg:top-14")}>
      <div className="grid pb-1.5" style={{ ...gridStyle(n), paddingInline: PAD_X + 1 }} aria-hidden>
        {dates.map((d, i) => {
          const day = parseDate(d).getDate();
          const monthStart = i === 0 || day === 1;
          const we = isWeekend(d);
          const on = active === i;
          return (
            <div key={d} className="relative flex flex-col items-center">
              <span className={cx("h-4 self-start whitespace-nowrap text-2xs font-semibold text-muted", !monthStart && "invisible")}>
                {monthStart ? `Th ${parseDate(d).getMonth() + 1}` : "·"}
              </span>
              <span
                className={cx(
                  "flex w-full flex-col items-center rounded-md py-0.5 leading-tight transition-colors duration-100",
                  on ? "bg-brand text-white" : we ? "bg-sunken text-ink" : "text-muted",
                )}
              >
                <span className={cx("text-2xs", we && !on && "font-semibold")}>{fmtWeekday(d).replace("Thứ ", "T")}</span>
                <span className={cx("text-sm tabular", on ? "font-bold text-white" : we ? "font-extrabold text-ink" : "font-bold text-ink")}>{day}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Thẻ thị trường (compset)

function MarketCard({
  ctx,
  data,
  compset,
  self,
  currency,
}: {
  ctx: StripCtx;
  data: OverviewOut;
  compset: Map<string, CompsetDayOut>;
  self: HotelRow | null;
  currency: string | null;
}) {
  const { dates, n } = ctx;
  const observed = Math.max(0, ...data.compset.map((c) => c.competitors_observed));
  const anySold = dates.some((d) => (compset.get(d)?.competitors_sold_out ?? 0) > 0);
  const lines: Line[] = [
    { key: "median", color: INK, width: 2, values: dates.map((d) => num(compset.get(d)?.median_price)) },
    { key: "min", color: REF, width: 1.5, dash: "3 3", values: dates.map((d) => num(compset.get(d)?.min_price)) },
  ];
  if (self) lines.push({ key: "own", color: YOURS, width: 2, values: dates.map((d) => num(compset.get(d)?.own_min_price)) });

  return (
    <section className="rounded-xl border border-line bg-surface shadow-card" aria-label="Thị trường">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 pt-4">
        <div className="sticky left-5 flex items-baseline gap-2">
          <h2 className="text-md font-bold text-ink">Thị trường</h2>
          <span className="text-sm text-muted">{observed > 0 ? `${observed} đối thủ đang theo dõi` : "Chưa có đối thủ nào có dữ liệu"}</span>
        </div>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          {self && (
            <li className="flex items-center gap-1.5">
              <LineKey color={YOURS} /> Giá của bạn
            </li>
          )}
          <li className="flex items-center gap-1.5">
            <LineKey color={INK} /> Trung vị đối thủ
          </li>
          <li className="flex items-center gap-1.5">
            <LineKey color={REF} dashed /> Thấp nhất đối thủ
          </li>
        </ul>
      </header>

      <div className="px-5 pb-4 pt-3">
        <div className="mb-1 flex items-baseline gap-2 text-xs">
          <span className="font-semibold text-muted">Đối thủ hết phòng mỗi đêm</span>
          {!anySold && <span className="text-faint">chưa đối thủ nào hết phòng trong {n} đêm này</span>}
        </div>
        <div className={cx("grid items-end", anySold ? "h-9" : "h-1.5")} style={gridStyle(n)}>
          {dates.map((d, i) => {
            const c = compset.get(d);
            const share = num(c?.sold_out_share) ?? 0;
            const sold = c?.competitors_sold_out ?? 0;
            const on = ctx.active === i;
            return (
              <div
                key={d}
                className={cx("relative flex h-full flex-col items-center justify-end rounded-[4px]", on && "bg-brand-softer")}
                onMouseEnter={(e) => ctx.activate(i, e.currentTarget)}
              >
                {sold > 0 && <span className="mb-0.5 text-2xs font-bold text-ink tabular">{`${sold}/${c?.competitors_observed ?? 0}`}</span>}
                <span
                  className={cx("w-full max-w-[22px] rounded-t-[3px]", sold > 0 ? "bg-plum" : "bg-line")}
                  style={{ height: sold > 0 ? `${Math.max(6, share * 22)}px` : "2px" }}
                />
              </div>
            );
          })}
        </div>

        <div className="mb-1 mt-4 text-xs font-semibold text-muted">
          Giá thấp nhất mỗi đêm{currency ? ` (${currency})` : ""}
        </div>
        <PriceLines ctx={ctx} lines={lines} height={96} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Thẻ một khách sạn: dải 30 ô + đường giá cùng trục

function HotelCard({
  ctx,
  row,
  self,
  compset,
}: {
  ctx: StripCtx;
  row: HotelRow;
  self: HotelRow | null;
  compset: Map<string, CompsetDayOut>;
}) {
  const { dates, n } = ctx;
  const isSelf = row.role === "self";
  const byDate = new Map<string, DateCell>(row.cells.map((c) => [c.stay_date, c]));
  const name = hotelName(row);
  const hasData = row.cells.some((c) => c.availability_status !== null);
  const first = byDate.get(dates[0]);
  const firstMark = cellMark(first);

  const prices = row.cells.map((c) => num(c.min_price)).filter((v): v is number => v !== null);
  const priceRange = prices.length ? [Math.min(...prices), Math.max(...prices)] : null;

  const lines: Line[] = [];
  if (isSelf) {
    lines.push({ key: "median", color: INK, width: 1.25, dash: "3 3", values: dates.map((d) => num(compset.get(d)?.median_price)) });
    lines.push({ key: "own", color: YOURS, width: 2, values: dates.map((d) => num(byDate.get(d)?.min_price)) });
  } else {
    if (self) {
      const selfBy = new Map(self.cells.map((c) => [c.stay_date, c]));
      lines.push({ key: "own", color: YOURS, width: 1.25, dash: "3 3", values: dates.map((d) => num(selfBy.get(d)?.min_price)) });
    }
    lines.push({ key: "hotel", color: INK, width: 2, values: dates.map((d) => num(byDate.get(d)?.min_price)) });
  }

  const statusText = (
    <>
      {hasData ? (
        <span className="flex items-center gap-1.5 text-muted" title={firstMark.label}>
          {first?.days_to_arrival === 0 ? "Đêm nay" : fmtNight(dates[0])}
          <span className="font-semibold text-ink tabular">{shortStatus(first)}</span>
          {first?.min_price && <span className="tabular text-body">· {fmtMoney(first.min_price, first.currency)}</span>}
        </span>
      ) : (
        <span className="text-muted">Đang chờ lượt quét đầu tiên</span>
      )}
    </>
  );
  const detailsLink = (
    <>
      <Link
        href={`/hotels/${row.hotel.id}`}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-sm font-semibold text-brand hover:bg-brand-softer"
        aria-label={`Chi tiết ${name}`}
      >
        Chi tiết <IconArrowRight size={14} />
      </Link>
    </>
  );

  const occ = isSelf ? dates.map((d) => num(compset.get(d)?.own_occupancy_pct)) : [];
  const hasOcc = occ.some((v) => v !== null);

  return (
    <section
      aria-label={name}
      className={cx("rounded-xl border bg-surface shadow-card", isSelf ? "border-yours/35 ring-1 ring-yours/10" : "border-line")}
    >
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 px-5 pt-3.5">
        <div className="sticky left-5 flex min-w-0 max-w-[calc(100vw-5rem)] items-start gap-2.5">
          {isSelf && <span aria-hidden className="mt-[7px] h-2.5 w-2.5 shrink-0 rounded-full bg-yours shadow-[0_0_0_3px_rgba(0,176,144,0.18)]" />}
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <Link href={`/hotels/${row.hotel.id}`} className="truncate text-md font-bold text-ink hover:text-brand hover:underline" title={row.hotel.name ?? undefined}>
                {name}
              </Link>
              {isSelf && <span className="shrink-0 rounded-full bg-yours-soft px-2 py-px text-xs font-semibold text-yours-deep">Của bạn</span>}
            </div>
            {ctx.fits ? (
              row.label && row.hotel.name && row.hotel.name !== row.label && <div className="truncate text-xs text-muted">{row.hotel.name}</div>
            ) : (
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-muted">
                {statusText}
                {detailsLink}
              </div>
            )}
          </div>
        </div>
        {ctx.fits && (
          <div className="flex items-center gap-4 text-sm">
            {statusText}
            {hasData && priceRange && (
              <span className="hidden text-muted xl:inline tabular" title="Giá thấp nhất mỗi đêm trong kỳ">
                Giá kỳ này {fmtCompact(priceRange[0])}–{fmtCompact(priceRange[1])}
              </span>
            )}
            {detailsLink}
          </div>
        )}
      </header>

      <div className="px-5 pb-3.5 pt-3">
        {!ctx.fits && (
          <div className="mb-1 grid" style={gridStyle(n)} aria-hidden>
            {dates.map((d) => (
              <span key={d} className={cx("text-center text-2xs tabular", isWeekend(d) ? "font-bold text-ink" : "text-muted")}>
                {parseDate(d).getDate()}
              </span>
            ))}
          </div>
        )}
        <div className="grid" style={gridStyle(n)}>
          {dates.map((d, i) => {
            const cell = byDate.get(d);
            const mark = cellMark(cell);
            const on = ctx.active === i;
            return (
              <Link
                key={d}
                href={`/hotels/${row.hotel.id}/dates/${d}`}
                aria-label={`${name}, ${fmtWeekday(d)} ${fmtDateShort(d)}: ${mark.label}${cell?.min_price ? `, giá ${fmtMoney(cell.min_price, cell.currency)}` : ""}`}
                onMouseEnter={(e) => ctx.activate(i, e.currentTarget)}
                onFocus={(e) => ctx.activate(i, e.currentTarget)}
                className={cx(
                  "sb-cell grid h-8 place-items-center rounded-[6px] font-bold tabular leading-none focus-visible:outline-offset-1",
                  mark.cls,
                  mark.kind === "sold_out" ? "text-[9px] tracking-[0.02em]" : "text-sm",
                  on && "outline-2 outline-offset-1 outline-brand",
                )}
              >
                {mark.text}
              </Link>
            );
          })}
        </div>
        {hasData && <PriceLines ctx={ctx} lines={lines} height={60} className="mt-2" />}
        {hasOcc && (
          <>
            <div className="mb-1 mt-2 text-xs font-semibold text-muted">Công suất theo PMS</div>
            <div className="grid" style={gridStyle(n)}>
              {occ.map((v, i) => (
                <span key={dates[i]} className="text-center text-2xs font-semibold text-body tabular">
                  {v === null ? "·" : fmtPct(v, { digits: 0 })}
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function shortStatus(cell: DateCell | undefined): string {
  if (!cell || cell.availability_status === null) return "Chưa có";
  if (cell.availability_status === "sold_out") return "Hết phòng";
  if (cell.availability_status === "unknown") return "Không rõ";
  return cell.exact_rooms_left === null ? "Còn phòng" : `Còn ${cell.exact_rooms_left} phòng`;
}

// ---------------------------------------------------------------------------
// Đường giá (SVG đo theo chiều rộng thật để điểm rơi đúng tâm cột)

type Line = { key: string; color: string; width: number; dash?: string; values: Array<number | null> };

/** Thang y riêng của từng biểu đồ (theo các đường của chính nó), có nhãn mức giá. */
function PriceLines({ ctx, lines, height, className }: { ctx: StripCtx; lines: Line[]; height: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const w = useElementWidth(ref);
  const { n, active } = ctx;
  const own = lines.flatMap((l) => l.values).filter((v): v is number => v !== null);
  const yDomain: readonly [number, number] | null = own.length
    ? (() => {
        const lo = Math.min(...own);
        const hi = Math.max(...own);
        const pad = (hi - lo || hi || 1) * 0.18;
        return [Math.max(0, lo - pad), hi + pad] as const;
      })()
    : null;
  const colW = w > 0 ? (w - (n - 1) * GAP) / n : 0;
  const xAt = (i: number) => i * (colW + GAP) + colW / 2;
  const pad = 5;
  const yAt = (v: number) => {
    if (!yDomain) return height / 2;
    const [lo, hi] = yDomain;
    return pad + (1 - (v - lo) / (hi - lo || 1)) * (height - pad * 2);
  };

  function path(values: Array<number | null>): string {
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (v === null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  }

  return (
    <div ref={ref} className={cx("relative", className)} style={{ height }}>
      {w > 0 && yDomain && (
        <svg width={w} height={height} className="absolute inset-0 overflow-visible" aria-hidden>
          <line x1={0} x2={w} y1={height - 0.5} y2={height - 0.5} stroke="var(--sb-line)" />
          {[0.25, 0.75].map((f) => {
            const v = yDomain[0] + (yDomain[1] - yDomain[0]) * (1 - f);
            return <line key={f} x1={0} x2={w} y1={yAt(v)} y2={yAt(v)} stroke="#ece9f7" />;
          })}
          {active !== null && <line x1={xAt(active)} x2={xAt(active)} y1={0} y2={height} stroke="var(--sb-brand)" strokeOpacity={0.12} strokeWidth={colW} />}
          {lines.map((l) => (
            <path key={l.key} d={path(l.values)} fill="none" stroke={l.color} strokeWidth={l.width} strokeDasharray={l.dash} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {/* Nhãn mức giá nằm trên đường, có nền riêng để không bị nét đè */}
          {[0.25, 0.75].map((f) => {
            const v = yDomain[0] + (yDomain[1] - yDomain[0]) * (1 - f);
            const label = fmtCompact(v);
            const tw = label.length * 6 + 8;
            return (
              <g key={`l-${f}`}>
                <rect x={0} y={yAt(v) - 8} width={tw} height={15} rx={4} fill="#fff" stroke="#ece9f7" />
                <text x={4} y={yAt(v) + 3.5} fontSize={10.5} fontWeight={600} fill="#5e6072" style={{ fontVariantNumeric: "tabular-nums" }}>
                  {label}
                </text>
              </g>
            );
          })}
          {/* Điểm lẻ (không có hàng xóm) vẫn phải thấy được */}
          {lines.map((l) =>
            l.values.map((v, i) =>
              v !== null && l.values[i - 1] == null && l.values[i + 1] == null ? (
                <circle key={`${l.key}-${i}`} cx={xAt(i)} cy={yAt(v)} r={2.5} fill={l.color} />
              ) : null,
            ),
          )}
          {active !== null &&
            lines.map((l) => {
              const v = l.values[active];
              return v === null || v === undefined ? null : (
                <circle key={`a-${l.key}`} cx={xAt(active)} cy={yAt(v)} r={4} fill={l.color} stroke="#fff" strokeWidth={2} />
              );
            })}
        </svg>
      )}
      {/* Vùng rê theo cột */}
      <div className="absolute inset-0 grid" style={gridStyle(n)}>
        {Array.from({ length: n }, (_, i) => (
          <span key={i} onMouseEnter={(e) => ctx.activate(i, e.currentTarget)} />
        ))}
      </div>
    </div>
  );
}

function LineKey({ color, dashed }: { color: string; dashed?: boolean }) {
  return (
    <svg width="18" height="8" aria-hidden className="shrink-0">
      <line x1="1" x2="17" y1="4" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dashed ? "3 3" : undefined} strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Bảng đọc một đêm: mọi khách sạn + thị trường

function Readout({
  active,
  dates,
  data,
  compset,
  currency,
}: {
  active: NonNullable<Active>;
  dates: string[];
  data: OverviewOut;
  compset: Map<string, CompsetDayOut>;
  currency: string | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [h, setH] = useState(0);
  useLayoutEffect(() => {
    if (ref.current) setH(ref.current.offsetHeight);
  }, [active.idx]);
  const d = dates[active.idx];
  if (!d) return null;
  const c = compset.get(d);
  const W = 300;
  const vw = typeof window !== "undefined" ? window.innerWidth : 1400;
  const vh = typeof window !== "undefined" ? window.innerHeight : 900;
  const left = active.x + 14 + W > vw - 8 ? active.x - W - 44 : active.x + 14;
  const top = Math.max(8, Math.min(active.y - 20, vh - (h || 320) - 8));
  const idx = num(c?.price_index);

  return (
    <div
      ref={ref}
      role="tooltip"
      className="pointer-events-none fixed z-50 rounded-xl border border-line bg-surface p-3.5 shadow-float [animation:sb-fade-in_.12s_var(--sb-ease)]"
      style={{ left: Math.max(8, left), top, width: W }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-md font-bold text-ink">
          {fmtWeekday(d)} {fmtDateShort(d)}
        </span>
        <span className="text-xs text-muted">{relNight(data.hotels, d)}</span>
      </div>
      <ul className="mt-2.5 space-y-1.5">
        {data.hotels.map((h) => {
          const cell = h.cells.find((x) => x.stay_date === d);
          const mark = cellMark(cell);
          return (
            <li key={h.hotel.id} className="flex items-center gap-2 text-sm">
              <MarkSwatch mark={mark} size={20} />
              <span className={cx("min-w-0 flex-1 truncate", h.role === "self" ? "font-bold text-yours-deep" : "text-body")}>{hotelName(h)}</span>
              <span className="shrink-0 font-semibold text-ink tabular">{fmtCompact(cell?.min_price)}</span>
            </li>
          );
        })}
      </ul>
      {c && (
        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t border-line pt-2.5 text-xs">
          <dt className="text-muted">Đối thủ hết phòng</dt>
          <dd className="text-right font-semibold text-ink tabular">
            {c.competitors_sold_out}/{c.competitors_observed}
          </dd>
          <dt className="text-muted">Trung vị đối thủ</dt>
          <dd className="text-right font-semibold text-ink tabular">{fmtMoney(c.median_price, c.currency ?? currency)}</dd>
          {idx !== null && (
            <>
              <dt className="text-muted">Giá bạn so trung vị</dt>
              <dd className="text-right font-semibold text-ink tabular">{fmtPct(idx - 100, { signed: true, digits: 0 })}</dd>
            </>
          )}
          {c.own_occupancy_pct !== null && (
            <>
              <dt className="text-muted">Công suất PMS</dt>
              <dd className="text-right font-semibold text-ink tabular">
                {fmtPct(c.own_occupancy_pct, { digits: 0 })}
                {c.own_rooms_available !== null && <span className="font-normal text-muted"> · còn {fmtInt(c.own_rooms_available)}</span>}
              </dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}

function relNight(hotels: HotelRow[], d: string): ReactNode {
  const dta = hotels.flatMap((h) => h.cells).find((c) => c.stay_date === d)?.days_to_arrival;
  if (dta === null || dta === undefined) return null;
  if (dta === 0) return "Đêm nay";
  if (dta === 1) return "Đêm mai";
  return `${fmtNum(dta)} ngày nữa`;
}
