"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { addDays, todayIso } from "@/lib/format";
import { Field, Input, Select } from "./ui";

export const DAY_OPTIONS = [14, 30, 60] as const;

/** Đọc `?start=&days=` từ URL; mặc định hôm nay + 30 ngày. */
export function useDateRange(): { start: string; days: number; end: string } {
  const params = useSearchParams();
  const [today] = useState(todayIso);
  const rawStart = params.get("start");
  const start = rawStart && /^\d{4}-\d{2}-\d{2}$/.test(rawStart) ? rawStart : today;
  const rawDays = Number(params.get("days"));
  const days = (DAY_OPTIONS as readonly number[]).includes(rawDays) ? rawDays : 30;
  return { start, days, end: addDays(start, days - 1) };
}

export function DateRangePicker() {
  const { start, days } = useDateRange();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function update(next: { start?: string; days?: number }) {
    const q = new URLSearchParams(params.toString());
    q.set("start", next.start ?? start);
    q.set("days", String(next.days ?? days));
    router.replace(`${pathname}?${q.toString()}`);
  }

  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field label="Từ ngày">
        <Input type="date" value={start} onChange={(e) => e.target.value && update({ start: e.target.value })} />
      </Field>
      <Field label="Số ngày">
        <Select value={days} onChange={(e) => update({ days: Number(e.target.value) })}>
          {DAY_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d} ngày
            </option>
          ))}
        </Select>
      </Field>
    </div>
  );
}
