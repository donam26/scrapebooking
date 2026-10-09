"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { addDays, todayIso } from "@/lib/format";
import { useTenantToday } from "@/lib/hooks";
import { IconCalendar } from "./icons";
import { Segmented, cx } from "./ui";

export const DAY_OPTIONS = [14, 30, 60] as const;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Đọc `?start=&days=` từ URL; mặc định hôm nay (theo múi giờ tenant) + `defaultDays` đêm.
 * Chọn được đêm bắt đầu bất kỳ (VD xem trước Tết). `ready`: đã biết "hôm nay" của tenant (trước đó
 * tạm dùng ngày của trình duyệt).
 */
export function useDateRange(defaultDays: number = 30): { start: string; days: number; end: string; today: string; ready: boolean } {
  const params = useSearchParams();
  const tenantToday = useTenantToday();
  const [browserToday] = useState(todayIso);
  const today = tenantToday ?? browserToday;
  const rawStart = params.get("start");
  const start = rawStart && ISO_DATE.test(rawStart) ? rawStart : today;
  const rawDays = Number(params.get("days"));
  const days = (DAY_OPTIONS as readonly number[]).includes(rawDays) ? rawDays : defaultDays;
  return { start, days, end: addDays(start, days - 1), today, ready: tenantToday !== null };
}

/** Kỳ xem: số đêm (14/30/60) + đêm bắt đầu; ghi vào URL để chia sẻ và tải lại được. */
export function DateRangePicker({ className, defaultDays = 30 }: { className?: string; defaultDays?: number }) {
  const t = useTranslations("components.dateRange");
  const { start, days, today } = useDateRange(defaultDays);
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function update(next: { start?: string; days?: number }) {
    const q = new URLSearchParams(params.toString());
    const s = next.start ?? start;
    const d = next.days ?? days;
    if (s === today) q.delete("start");
    else q.set("start", s);
    if (d === defaultDays) q.delete("days");
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
          aria-label={t("start")}
          value={start}
          onChange={(e) => e.target.value && update({ start: e.target.value })}
          className="h-9 rounded-lg border border-line-strong bg-surface pl-8 pr-2 text-base text-ink tabular transition-[border-color,box-shadow] hover:border-[#b7bfcc] focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15"
        />
      </div>
      {start !== today && (
        <button
          type="button"
          onClick={() => update({ start: today })}
          className="h-9 rounded-lg px-2.5 text-sm font-semibold text-brand hover:bg-brand-softer"
        >
          {t("today")}
        </button>
      )}
      <Segmented
        label={t("nightsLabel")}
        value={days}
        onChange={(d) => update({ days: d })}
        items={DAY_OPTIONS.map((d) => ({ value: d, label: t("nights", { count: d }) }))}
      />
    </div>
  );
}
