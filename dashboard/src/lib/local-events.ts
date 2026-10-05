/** Loại sự kiện địa phương (tenant tự nhập) và màu thẻ trên lịch Terminal+. Tên loại: `useLocalEventLabel()`. */

import { useTranslations } from "next-intl";

export type LocalEventCategory = "festival" | "mice" | "sports" | "season" | "other";

export const LOCAL_EVENT_CATEGORIES: Array<{ value: LocalEventCategory; bg: string; chip: string }> = [
  { value: "festival", bg: "linear-gradient(135deg,#db2777,#f59e0b)", chip: "bg-[#fce7f3] text-[#be185d]" },
  { value: "mice", bg: "linear-gradient(135deg,#4f46e5,#06b6d4)", chip: "bg-[#e0e7ff] text-[#4338ca]" },
  { value: "sports", bg: "linear-gradient(135deg,#059669,#84cc16)", chip: "bg-[#dcfce7] text-[#047857]" },
  { value: "season", bg: "linear-gradient(135deg,#0ea5e9,#6366f1)", chip: "bg-[#e0f2fe] text-[#0369a1]" },
  { value: "other", bg: "linear-gradient(135deg,#475569,#94a3b8)", chip: "bg-sunken text-muted" },
];

export function localEventCategory(value: string) {
  return LOCAL_EVENT_CATEGORIES.find((c) => c.value === value) ?? LOCAL_EVENT_CATEGORIES[LOCAL_EVENT_CATEGORIES.length - 1];
}

/** `(category) => tên loại` theo ngôn ngữ hiện tại; loại lạ tính là "Khác" như `localEventCategory`. */
export function useLocalEventLabel(): (category: string) => string {
  const t = useTranslations("helpers.localEvents.category");
  return (category) => t(localEventCategory(category).value);
}

/** "+40%" / "−10%" cho mức tăng cầu dự kiến. */
export function fmtUplift(pct: number | null | undefined): string | null {
  if (pct === null || pct === undefined || pct === 0) return null;
  return pct > 0 ? `+${pct}%` : `−${-pct}%`;
}
