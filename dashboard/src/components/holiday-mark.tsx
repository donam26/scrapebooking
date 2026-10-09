"use client";

import { useTranslations } from "next-intl";
import type { HolidayKind, HolidayOut } from "@/lib/api";
import { daysBetween, useFmt } from "@/lib/format";
import { cx } from "./ui";

/**
 * Dấu ngày lễ trên các màn ra quyết định (Bảng điều khiển, Phòng trống, Giá, Đối thủ). Dữ liệu từ
 * `OverviewOut.holidays` hoặc `api.market.holidays` (tên đã dịch ở backend).
 * Chấm mực, không tím (tím = bấm/chọn), không vàng (vàng = số chính xác), giống bảng Tổng quan.
 */

/**
 * Màu theo loại lễ (`HolidayOut.kind`): Tết đỏ, ngày lễ cam, cầu du lịch tím, lễ thị trường khách
 * nguồn (Chuseok, Tuần lễ Vàng…) xanh ngọc, mùa nghỉ (hè học sinh) xanh lá. `bg` cho thẻ lịch,
 * `chip` cho nhãn, `dot` cho chấm trong dải chip.
 */
export const HOLIDAY_KIND_STYLE: Record<HolidayKind, { bg: string; chip: string; dot: string }> = {
  tet: { bg: "linear-gradient(135deg,#b91c1c,#f97316)", chip: "bg-danger-soft text-danger-deep", dot: "bg-danger" },
  holiday: { bg: "linear-gradient(135deg,#ea580c,#fbbf24)", chip: "bg-hot-soft text-hot", dot: "bg-hot" },
  travel: { bg: "linear-gradient(135deg,#6d28d9,#ec4899)", chip: "bg-[#f3e8ff] text-[#6d28d9]", dot: "bg-[#6d28d9]" },
  source_market: { bg: "linear-gradient(135deg,#0e7490,#22d3ee)", chip: "bg-[#cffafe] text-[#0e7490]", dot: "bg-[#0e7490]" },
  season: { bg: "linear-gradient(135deg,#15803d,#84cc16)", chip: "bg-[#dcfce7] text-[#15803d]", dot: "bg-[#15803d]" },
};

export function holidayMap(holidays: HolidayOut[] | undefined): Map<string, HolidayOut> {
  return new Map((holidays ?? []).map((h) => [h.date, h]));
}

/** Chấm đánh dấu ngày lễ; giữ chỗ (trong suốt) khi không phải ngày lễ để các cột thẳng hàng. */
export function HolidayDot({ holiday, onDark, className }: { holiday?: HolidayOut | null; onDark?: boolean; className?: string }) {
  return (
    <span
      aria-hidden
      title={holiday?.name}
      className={cx("mx-auto block h-1.5 w-1.5 rounded-full", holiday ? (onDark ? "bg-white" : "bg-ink") : "bg-transparent", className)}
    />
  );
}

type Period = { name: string; from: string; to: string; kind: HolidayKind };

/** Gộp các ngày lễ liền nhau cùng nhóm thành một kỳ. */
function periods(holidays: HolidayOut[]): Period[] {
  const out: Array<Period & { group: string }> = [];
  for (const h of [...holidays].sort((a, b) => a.date.localeCompare(b.date))) {
    const last = out[out.length - 1];
    if (last && last.group === h.group && daysBetween(last.to, h.date) === 1) last.to = h.date;
    else out.push({ name: h.name, from: h.date, to: h.date, group: h.group, kind: h.kind });
  }
  return out;
}

/** Dải chip "Lễ trong kỳ: Quốc khánh · 01/09–02/09"; không hiện gì khi kỳ không có lễ. */
export function HolidayChips({ holidays, start, end, className }: { holidays: HolidayOut[] | undefined; start: string; end: string; className?: string }) {
  const t = useTranslations("components.holidays");
  const { fmtDateShort } = useFmt();
  const list = periods((holidays ?? []).filter((h) => h.date >= start && h.date <= end));
  if (list.length === 0) return null;
  return (
    <span className={cx("inline-flex flex-wrap items-center gap-1.5 text-sm", className)}>
      <span className="text-muted">{t("label")}</span>
      {list.map((p) => (
        <span key={`${p.from}-${p.name}`} title={t(`kind.${p.kind}`)} className="inline-flex items-center gap-1.5 rounded-full bg-sunken px-2.5 py-0.5 font-medium text-ink">
          <span aria-hidden className={cx("h-1.5 w-1.5 rounded-full", HOLIDAY_KIND_STYLE[p.kind]?.dot ?? "bg-ink")} />
          {p.from === p.to ? t("single", { name: p.name, date: fmtDateShort(p.from) }) : t("range", { name: p.name, from: fmtDateShort(p.from), to: fmtDateShort(p.to) })}
        </span>
      ))}
    </span>
  );
}
