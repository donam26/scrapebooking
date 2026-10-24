"use client";

import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import type { HolidayOut, OverviewOut } from "@/lib/api";
import { dateRange } from "@/lib/format";
import { useMarketMetrics } from "@/lib/market-metrics";
import { HolidayDot, holidayMap } from "@/components/holiday-mark";
import { IconChevronRight } from "@/components/icons";
import { cx } from "@/components/ui";

/**
 * Phần dùng chung của ba lưới trên Lịch giá & phòng (Phòng còn, Giá, Chênh với bạn): cột đêm
 * (thứ, ngày, hôm nay, cuối tuần, ngày lễ, chấm tím khi đêm có gợi ý giá chưa xử lý), cột tên
 * khách sạn dính bên trái, và khối thu gọn dưới lưới.
 */

/** Cột tên khách sạn dính trái: hẹp trên mobile để còn chỗ cho ô đêm. */
export const STICKY_COL = "sticky left-0 z-10 w-[132px] min-w-[132px] max-w-[132px] sm:w-[200px] sm:min-w-[200px] sm:max-w-[200px]";

export type NightCol = { date: string; wd: string; label: string; weekend: boolean; isToday: boolean; holiday: HolidayOut | undefined; pending: boolean };

/** Các cột đêm của kỳ xem. `pending`: đêm có gợi ý giá (không phải "giữ giá") chưa xử lý. */
export function useNightCols(o: OverviewOut, today: string, pending: Set<string>): NightCol[] {
  const { dayHead } = useMarketMetrics();
  const holidays = holidayMap(o.holidays);
  return dateRange(o.start, o.end).map((d) => {
    const h = dayHead(d, today);
    return { date: d, wd: h.wd, label: h.date, weekend: h.weekend, isToday: h.isToday, holiday: holidays.get(d), pending: pending.has(d) };
  });
}

/** Nền cột: hôm nay xanh nhạt, cuối tuần đỏ nhạt. */
export function colBg(c: NightCol): string {
  return c.isToday ? "bg-brand-soft/60" : c.weekend ? "bg-danger-soft/50" : "";
}

export function NightHeadCells({ cols }: { cols: NightCol[] }) {
  const t = useTranslations("calendar.head");
  return (
    <>
      {cols.map((c) => {
        const tone = c.isToday ? "text-brand" : c.weekend ? "text-danger" : "text-muted";
        return (
          <th key={c.date} scope="col" title={c.holiday?.name} className={cx("min-w-[58px] px-0.5 pb-1.5 pt-1 text-center font-normal", colBg(c))}>
            <span className="flex h-2 items-center justify-center">
              {c.pending && <span title={t("pending")} className="h-1.5 w-1.5 rounded-full bg-[#7c3aed]" />}
              {c.pending && <span className="sr-only">{t("pending")}</span>}
            </span>
            <div className={cx("text-[11px] font-semibold uppercase", tone)}>{c.isToday ? t("today") : c.wd}</div>
            <div className={cx("text-xs tabular", tone)}>{c.label}</div>
            <HolidayDot holiday={c.holiday} className="mt-0.5" />
          </th>
        );
      })}
    </>
  );
}

/**
 * Khối thu gọn mặc định dưới lưới. Nội dung chỉ dựng khi mở (biểu đồ cần bề rộng thật, và dữ liệu
 * riêng của khối chỉ tải khi cần).
 */
export function Collapsible({ title, aside, children }: { title: ReactNode; aside?: ReactNode; children: () => ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="group rounded-[10px] border border-line bg-surface shadow-card" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3.5 [&::-webkit-details-marker]:hidden">
        <IconChevronRight size={16} className="shrink-0 text-muted transition-transform group-open:rotate-90" />
        <span className="text-md font-bold text-ink">{title}</span>
        {aside && <span className="min-w-0 text-sm text-muted">{aside}</span>}
      </summary>
      {open && <div className="min-w-0 border-t border-line p-5 max-sm:px-3">{children()}</div>}
    </details>
  );
}
