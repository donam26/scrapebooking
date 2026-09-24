"use client";

import Link from "next/link";
import { useState } from "react";
import type { CompsetDayOut, DateCell, HotelRow, OverviewOut } from "@/lib/api";
import { dateRange, fmtCompact, fmtDateShort, fmtDateTime, fmtInt, fmtMoney, fmtNum, fmtPct, fmtShare, fmtWeekday, isWeekend, num } from "@/lib/format";
import { AVAILABILITY_LABEL, AVAILABILITY_TONE, WATCH_ROLE_LABEL } from "@/lib/labels";
import { Badge, Stat, cx } from "@/components/ui";

/** Màu ô theo trạng thái; chữ trong ô luôn mang nghĩa để không phụ thuộc màu. */
function cellStyle(cell: DateCell | undefined): { className: string; text: string; title: string } {
  if (!cell || cell.availability_status === null) return { className: "cell-nodata text-transparent", text: "·", title: "Chưa có dữ liệu" };
  switch (cell.availability_status) {
    case "sold_out":
      return { className: "bg-red-800 text-white", text: "Hết", title: "Hết phòng" };
    case "unknown":
      return { className: "bg-slate-200 text-slate-500", text: "?", title: "Không rõ (bị chặn/lỗi)" };
    default: {
      const n = cell.exact_rooms_left;
      if (n === null) return { className: "bg-emerald-100 text-emerald-900", text: "✓", title: "Còn phòng, chưa rõ số lượng" };
      if (n <= 3) return { className: "bg-rose-300 text-rose-950 font-semibold", text: String(n), title: `Sắp hết: còn ${n} phòng` };
      if (n <= 10) return { className: "bg-amber-200 text-amber-950", text: String(n), title: `Còn ${n} phòng` };
      return { className: "bg-emerald-300 text-emerald-950", text: String(n), title: `Còn ${n} phòng` };
    }
  }
}

function shareClass(share: string | null): string {
  const s = num(share);
  if (s === null || s <= 0) return "";
  if (s < 0.25) return "bg-sky-100";
  if (s < 0.5) return "bg-sky-200";
  if (s < 0.75) return "bg-sky-300";
  return "bg-sky-400";
}

type Hover = { hotel: HotelRow; cell: DateCell; x: number; y: number };

const DATE_COL = "min-w-[42px] w-[42px]";

export function Heatmap({ data }: { data: OverviewOut }) {
  const [hover, setHover] = useState<Hover | null>(null);
  const dates = dateRange(data.start, data.end);
  const compsetByDate = new Map<string, CompsetDayOut>(data.compset.map((c) => [c.stay_date, c]));

  return (
    <div className="relative overflow-x-auto" onMouseLeave={() => setHover(null)}>
      <table className="border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 min-w-[180px] max-w-[240px] border-b border-line bg-surface px-2 py-1 text-left font-medium text-slate-500">Khách sạn</th>
            {dates.map((d) => (
              <th key={d} className={cx("border-b border-line px-0.5 py-1 text-center font-normal text-slate-500", DATE_COL, isWeekend(d) && "bg-slate-100")}>
                <div className="text-[10px] leading-tight">{fmtWeekday(d)}</div>
                <div className="font-medium leading-tight text-slate-800">{fmtDateShort(d)}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.hotels.map((row) => {
            const byDate = new Map(row.cells.map((c) => [c.stay_date, c]));
            const name = row.label || row.hotel.name || row.hotel.booking_slug;
            return (
              <tr key={row.hotel.id}>
                <th scope="row" className={cx("sticky left-0 z-10 max-w-[240px] border-b border-line bg-surface px-2 py-0.5 text-left font-normal", row.role === "self" && "bg-sky-50")}>
                  <div className="flex items-center gap-1.5 overflow-hidden">
                    <Link href={`/hotels/${row.hotel.id}`} className="truncate font-medium text-sky-800 hover:underline" title={row.hotel.name ?? undefined}>
                      {name}
                    </Link>
                    {row.role === "self" && <Badge tone="blue">{WATCH_ROLE_LABEL.self}</Badge>}
                  </div>
                </th>
                {dates.map((d) => {
                  const cell = byDate.get(d);
                  const st = cellStyle(cell);
                  return (
                    <td key={d} className={cx("border-b border-line p-[2px]", DATE_COL)}>
                      <Link
                        href={`/hotels/${row.hotel.id}/dates/${d}`}
                        aria-label={`${name} ${fmtDateShort(d)}: ${st.title}`}
                        className={cx("flex h-7 items-center justify-center rounded-sm tabular hover:ring-2 hover:ring-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500", st.className)}
                        onMouseEnter={(e) => cell && setHover({ hotel: row, cell, x: e.clientX, y: e.clientY })}
                        onFocus={(e) => {
                          if (!cell) return;
                          const r = e.currentTarget.getBoundingClientRect();
                          setHover({ hotel: row, cell, x: r.left + r.width / 2, y: r.top });
                        }}
                        onBlur={() => setHover(null)}
                      >
                        {st.text}
                      </Link>
                    </td>
                  );
                })}
              </tr>
            );
          })}
          {data.hotels.length === 0 && (
            <tr>
              <td colSpan={dates.length + 1} className="px-2 py-6 text-center text-sm text-slate-500">
                Watchlist trống. Thêm khách sạn ở mục Cài đặt.
              </td>
            </tr>
          )}
          <CompsetRow label="Đối thủ hết phòng" dates={dates} render={(c) => `${c.competitors_sold_out}/${c.competitors_observed}`} cls={(c) => shareClass(c.sold_out_share)} byDate={compsetByDate} title={(c) => `Tỷ lệ hết phòng ${fmtShare(c.sold_out_share)}`} first />
          <CompsetRow label="Giá trung vị đối thủ" dates={dates} render={(c) => fmtCompact(c.median_price)} byDate={compsetByDate} title={(c) => fmtMoney(c.median_price, c.currency)} />
          <CompsetRow label="Giá thấp nhất đối thủ" dates={dates} render={(c) => fmtCompact(c.min_price)} byDate={compsetByDate} title={(c) => fmtMoney(c.min_price, c.currency)} />
          <CompsetRow label="Chỉ số giá của bạn" dates={dates} render={(c) => fmtNum(c.price_index, 0)} byDate={compsetByDate} cls={(c) => priceIndexClass(c.price_index)} title={(c) => `Giá của bạn ${fmtMoney(c.own_min_price, c.currency)} so với trung vị (100 = bằng trung vị)`} />
          <CompsetRow label="Công suất của bạn (PMS)" dates={dates} render={(c) => fmtPct(c.own_occupancy_pct, { digits: 0 })} byDate={compsetByDate} title={(c) => `Còn ${fmtInt(c.own_rooms_available)} phòng theo PMS`} />
        </tbody>
      </table>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-600">
        <LegendSwatch cls="bg-rose-300" label="≤ 3 phòng (sắp hết)" />
        <LegendSwatch cls="bg-amber-200" label="4–10 phòng" />
        <LegendSwatch cls="bg-emerald-300" label="> 10 phòng" />
        <LegendSwatch cls="bg-emerald-100" label="Còn phòng, số ẩn" />
        <LegendSwatch cls="bg-red-800" label="Hết phòng" />
        <LegendSwatch cls="bg-slate-200" label="Không rõ" />
        <LegendSwatch cls="cell-nodata" label="Chưa có dữ liệu" />
      </div>

      {hover && <HoverPanel hover={hover} />}
    </div>
  );
}

function priceIndexClass(v: string | null): string {
  const n = num(v);
  if (n === null) return "";
  if (n >= 110) return "bg-sky-200";
  if (n <= 90) return "bg-orange-100";
  return "";
}

function CompsetRow({
  label,
  dates,
  byDate,
  render,
  cls,
  title,
  first,
}: {
  label: string;
  dates: string[];
  byDate: Map<string, CompsetDayOut>;
  render: (c: CompsetDayOut) => string;
  cls?: (c: CompsetDayOut) => string;
  title?: (c: CompsetDayOut) => string;
  first?: boolean;
}) {
  return (
    <tr className={cx(first && "[&>*]:border-t-2 [&>*]:border-t-slate-300")}>
      <th scope="row" className="sticky left-0 z-10 border-b border-line bg-slate-50 px-2 py-1 text-left font-medium text-slate-600">
        {label}
      </th>
      {dates.map((d) => {
        const c = byDate.get(d);
        return (
          <td key={d} className={cx("border-b border-line text-center tabular text-slate-800", DATE_COL, c && cls?.(c))} title={c ? title?.(c) : undefined}>
            {c ? render(c) : "—"}
          </td>
        );
      })}
    </tr>
  );
}

function LegendSwatch({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={cx("inline-block h-3 w-4 rounded-sm", cls)} /> {label}
    </span>
  );
}

function HoverPanel({ hover }: { hover: Hover }) {
  const { hotel, cell } = hover;
  const status = cell.availability_status;
  // Định vị cố định theo con trỏ, tránh tràn mép phải/dưới.
  const style = {
    left: Math.min(hover.x + 12, (typeof window !== "undefined" ? window.innerWidth : 1200) - 300),
    top: hover.y + 14,
  };
  return (
    <div role="tooltip" className="pointer-events-none fixed z-50 w-[280px] rounded-md border border-line bg-white p-3 text-xs shadow-lg" style={style}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="truncate font-semibold text-slate-900">{hotel.label || hotel.hotel.name || hotel.hotel.booking_slug}</span>
        <span className="whitespace-nowrap text-slate-500">
          {fmtWeekday(cell.stay_date)} {fmtDateShort(cell.stay_date)}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-2">
        <Stat label="Trạng thái" value={<Badge tone={AVAILABILITY_TONE[status ?? ""] ?? "gray"}>{AVAILABILITY_LABEL[status ?? ""] ?? "—"}</Badge>} />
        <Stat label="Phòng còn (chính xác)" value={fmtInt(cell.exact_rooms_left)} />
        <Stat label="Giá thấp nhất" value={fmtMoney(cell.min_price, cell.currency)} />
        <Stat label="Pickup 24h" value={fmtInt(cell.pickup_24h)} />
        <Stat label="Giá đổi 7 ngày" value={fmtPct(cell.price_change_7d_pct, { signed: true })} />
        <Stat label="Tỷ lệ quan sát chính xác" value={fmtShare(cell.exact_share)} />
        <Stat label="Quan sát gần nhất" value={fmtDateTime(cell.last_observed_at)} className="col-span-2" />
      </div>
    </div>
  );
}
