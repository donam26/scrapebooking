"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { HolidayKind, HolidayOut, LocalEventOut } from "@/lib/api";
import { HOLIDAY_KIND_STYLE as KIND_STYLE } from "@/components/holiday-mark";
import { addDays, parseDate, useFmt } from "@/lib/format";
import { fmtUplift, localEventCategory, useLocalEventLabel } from "@/lib/local-events";
import { Card, cx } from "@/components/ui";
import { IconCalendar } from "@/components/icons";

/**
 * SỰ KIỆN SẮP TỚI: 12 tháng, mỗi tháng một cột, mỗi kỳ lễ một thẻ màu (Tết đỏ, ngày lễ cam,
 * cầu du lịch tím, lễ thị trường nguồn xanh ngọc, mùa nghỉ xanh lá) theo `kind` của backend. Ngày lễ liền nhau cùng `group` gộp thành một kỳ ("Tết Nguyên đán 16/02–20/02").
 */

type Kind = HolidayKind;

/** Tên hiển thị của cả kỳ: bỏ phần ngoặc của từng ngày, "Tết Nguyên đán (Mùng 1)" → "Tết Nguyên đán". */
function baseName(name: string): string {
  return name.replace(/\s*\(.*\)\s*$/, "");
}

/** Một kỳ trên lịch: ngày lễ (bảng tĩnh) hoặc sự kiện địa phương do tenant nhập. */
type Period = { start: string; end: string; name: string; bg: string; group?: string; uplift?: number | null; note?: string | null };

function groupPeriods(holidays: HolidayOut[]): Period[] {
  const out: Period[] = [];
  for (const h of [...holidays].sort((a, b) => a.date.localeCompare(b.date))) {
    const last = out[out.length - 1];
    // Gộp theo mã kỳ ổn định của backend (`group`), không theo tên đã dịch.
    if (last && last.group === h.group && addDays(last.end, 1) === h.date) {
      last.end = h.date;
      last.name = baseName(h.name);
    } else {
      out.push({ start: h.date, end: h.date, name: h.name, group: h.group, bg: (KIND_STYLE[h.kind] ?? KIND_STYLE.holiday).bg }); // ?? : backend cũ chưa trả `kind`
    }
  }
  return out;
}

export function EventsCalendar({ holidays, localEvents, today }: { holidays: HolidayOut[]; localEvents: LocalEventOut[]; today: string }) {
  const t = useTranslations("terminal.calendar");
  const { fmtDateShort } = useFmt();
  const catLabel = useLocalEventLabel();
  const first = parseDate(today);
  const months = Array.from({ length: 12 }, (_, i) => new Date(first.getFullYear(), first.getMonth() + i, 1));
  const local: Period[] = localEvents.map((e) => ({
    start: e.start_date < today && e.end_date >= today ? today : e.start_date,
    end: e.end_date,
    name: e.name,
    bg: localEventCategory(e.category).bg,
    uplift: e.expected_uplift_pct,
    note: e.note,
  }));
  // Chú giải chỉ liệt kê Tết/lễ/cầu du lịch luôn có, cộng các loại khác khi lịch có.
  const shownKinds = new Set<Kind>(["tet", "holiday", "travel", ...holidays.map((h) => h.kind)]);
  const periods = [...groupPeriods(holidays), ...local].sort((a, b) => a.start.localeCompare(b.start));
  const localCats = [...new Set(localEvents.map((e) => e.category))].map(localEventCategory);
  const key = (d: Date) => `${d.getFullYear()}-${d.getMonth()}`;
  const byMonth = new Map<string, Period[]>();
  for (const p of periods) {
    const k = key(parseDate(p.start));
    byMonth.set(k, [...(byMonth.get(k) ?? []), p]);
  }
  return (
    <Card
      title={t("title")}
      icon={<IconCalendar size={16} />}
      info={t("info")}
      actions={
        <ul className="flex flex-wrap gap-1.5">
          {(Object.keys(KIND_STYLE) as Kind[]).filter((k) => shownKinds.has(k)).map((k) => (
            <li key={k} className={cx("rounded-md px-2 py-0.5 text-xs font-semibold", KIND_STYLE[k].chip)}>
              {t(`kind.${k}`)}
            </li>
          ))}
          {localCats.map((c) => (
            <li key={c.value} className={cx("rounded-md px-2 py-0.5 text-xs font-semibold", c.chip)}>
              {catLabel(c.value)}
            </li>
          ))}
          <li>
            <Link href="/settings?tab=events" className="rounded-md px-2 py-0.5 text-xs font-semibold text-brand hover:underline">
              {t("addEvent")}
            </Link>
          </li>
        </ul>
      }
    >
      <div className="sb-scroll overflow-x-auto pb-2">
        <div className="grid min-w-[1680px] grid-cols-12 divide-x divide-line">
          {months.map((m) => {
            const items = byMonth.get(key(m)) ?? [];
            return (
              <div key={key(m)} className="min-w-0 px-1.5">
                <div className="mb-2 rounded-md bg-brand-softer py-1 text-center text-sm font-semibold text-brand">
                  {t("month", { month: m.getMonth() + 1 })}
                  {m.getMonth() === 0 && <span className="ml-1 text-xs font-normal text-muted">{m.getFullYear()}</span>}
                </div>
                {items.length === 0 ? (
                  <div className="pt-1 text-center text-faint">—</div>
                ) : (
                  <ul className="space-y-1.5">
                    {items.map((p) => {
                      const past = p.end < today;
                      const body = (
                        <>
                          <span className="flex items-center gap-1.5 text-[11px] font-bold tabular">
                            <span className="opacity-90">
                              {fmtDateShort(p.start)}
                              {p.end !== p.start && `–${fmtDateShort(p.end)}`}
                            </span>
                            {fmtUplift(p.uplift) && <span className="rounded bg-white/25 px-1 py-px text-[10px]">{fmtUplift(p.uplift)}</span>}
                          </span>
                          <span className="line-clamp-2 text-xs font-bold leading-snug">{p.name}</span>
                        </>
                      );
                      const cls = "flex h-[84px] flex-col justify-between rounded-lg p-2.5 text-white shadow-sm";
                      return (
                        <li key={`${p.start}-${p.name}`}>
                          {past ? (
                            <div title={t("past", { name: p.name })} className={cx(cls, "opacity-45")} style={{ background: p.bg }}>
                              {body}
                            </div>
                          ) : (
                            <Link
                              href={`/availability?start=${p.start < today ? today : p.start}`}
                              title={p.note ? `${p.name}: ${p.note}` : p.name}
                              className={cx(cls, "transition-transform hover:-translate-y-px")}
                              style={{ background: p.bg }}
                            >
                              {body}
                            </Link>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
