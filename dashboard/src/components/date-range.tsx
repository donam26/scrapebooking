"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { addDays, todayIso } from "@/lib/format";
import { IconCalendar } from "./icons";
import { Segmented, cx } from "./ui";

export const DAY_OPTIONS = [14, 30, 60] as const;

/** Đọc `?start=&days=` từ URL; mặc định hôm nay + 30 đêm. */
export function useDateRange(): { start: string; days: number; end: string; today: string } {
  const params = useSearchParams();
  const [today] = useState(todayIso);
  const rawStart = params.get("start");
  const start = rawStart && /^\d{4}-\d{2}-\d{2}$/.test(rawStart) ? rawStart : today;
  const rawDays = Number(params.get("days"));
  const days = (DAY_OPTIONS as readonly number[]).includes(rawDays) ? rawDays : 30;
  return { start, days, end: addDays(start, days - 1), today };
}

/** Kỳ xem: số đêm (14/30/60) + đêm bắt đầu; ghi vào URL để chia sẻ và tải lại được. */
export function DateRangePicker({ className }: { className?: string }) {
  const { start, days, today } = useDateRange();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function update(next: { start?: string; days?: number }) {
    const q = new URLSearchParams(params.toString());
    const s = next.start ?? start;
    const d = next.days ?? days;
    if (s === today) q.delete("start");
    else q.set("start", s);
    if (d === 30) q.delete("days");
    else q.set("days", String(d));
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  return (
    <div className={cx("flex flex-wrap items-center gap-2", className)}>
      <div className="relative">
        <IconCalendar size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
        <input
          type="date"
          aria-label="Đêm bắt đầu"
          value={start}
          onChange={(e) => e.target.value && update({ start: e.target.value })}
          className="h-9 rounded-lg border border-line-strong bg-surface pl-8 pr-2 text-base text-ink tabular transition-[border-color,box-shadow] hover:border-[#b9b5d6] focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15"
        />
      </div>
      {start !== today && (
        <button
          type="button"
          onClick={() => update({ start: today })}
          className="h-9 rounded-lg px-2.5 text-sm font-semibold text-brand hover:bg-brand-softer"
        >
          Về hôm nay
        </button>
      )}
      <Segmented
        label="Số đêm"
        value={days}
        onChange={(d) => update({ days: d })}
        items={DAY_OPTIONS.map((d) => ({ value: d, label: `${d} đêm` }))}
      />
    </div>
  );
}
