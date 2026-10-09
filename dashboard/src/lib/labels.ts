/**
 * Mã trạng thái của backend: danh sách mã và màu (tone). Chữ hiển thị của từng mã nằm ở
 * `src/messages/<ngôn ngữ>/labels.json`, đọc qua `useLabel()`:
 *   const label = useLabel();  label("eventType", ev.event_type)  // mã lạ -> trả nguyên mã
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { Messages } from "@/messages";

export const EVENT_TYPES = [
  "sold_out",
  "restock",
  "rooms_decrease",
  "rooms_increase",
  "low_stock_enter",
  "price_up",
  "price_down",
  "room_type_new",
  "room_type_gone",
  "lowest_rate_shift",
  "restricted",
  "restriction_lifted",
  "min_stay_change",
  "promo_start",
  "promo_end",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

/** Nhóm loại thay đổi cho bộ lọc (khoá nhóm: events.filters.group.<key>). */
export const EVENT_TYPE_GROUPS: ReadonlyArray<{ key: "rooms" | "price" | "restrictions"; types: readonly EventType[] }> = [
  { key: "rooms", types: ["sold_out", "restock", "rooms_decrease", "rooms_increase", "low_stock_enter", "room_type_new", "room_type_gone"] },
  { key: "price", types: ["price_up", "price_down", "lowest_rate_shift"] },
  { key: "restrictions", types: ["restricted", "restriction_lifted", "min_stay_change", "promo_start", "promo_end"] },
];

export type Tone = "green" | "red" | "amber" | "gray" | "blue" | "purple" | "plum";

export const EVENT_TYPE_TONE: Record<string, Tone> = {
  sold_out: "plum",
  restock: "blue",
  rooms_decrease: "amber",
  rooms_increase: "blue",
  low_stock_enter: "amber",
  price_up: "gray",
  price_down: "gray",
  room_type_new: "gray",
  room_type_gone: "gray",
  // Giá thấp nhất đổi do phòng/gói rẻ nhất hết/mở lại: không phải đổi giá.
  lowest_rate_shift: "gray",
  // Hạn chế (min-stay, đóng ngày đến) không phải hết phòng: hổ phách, không đỏ.
  restricted: "amber",
  restriction_lifted: "blue",
  min_stay_change: "amber",
  promo_start: "amber",
  promo_end: "gray",
};

export const AVAILABILITY_TONE: Record<string, Tone> = {
  available: "blue",
  sold_out: "plum",
  restricted: "amber",
  unknown: "gray",
};

/** Năm trạng thái ô (`DateCell.state`): hạn chế hổ phách (không đỏ), không giá/lỗi xám. */
export const CELL_STATE_TONE: Record<string, Tone> = {
  available: "blue",
  sold_out: "plum",
  restricted: "amber",
  no_price: "gray",
  error: "gray",
};

export const STOCK_CONFIDENCE_TONE: Record<string, Tone> = {
  exact: "amber",
  capped: "purple",
  hidden: "gray",
  sold_out: "plum",
};

export const RUN_STATUS_TONE: Record<string, Tone> = {
  running: "blue",
  completed: "green",
  partial: "amber",
  failed: "red",
};

export const INSIGHT_STATUS_TONE: Record<string, Tone> = {
  pending: "blue",
  batch_pending: "amber",
  completed: "green",
  failed: "red",
};

export const NOTIFICATION_STATUS_TONE: Record<string, Tone> = {
  sent: "green",
  failed: "red",
  sending: "blue",
  skipped: "gray",
};

export const IMPORT_STATUS_TONE: Record<string, Tone> = {
  completed: "green",
  partial: "amber",
  failed: "red",
};

export const LEVEL_TONE: Record<string, Tone> = {
  high: "green",
  medium: "amber",
  low: "gray",
};

export const SESSION_STATUS_TONE: Record<string, Tone> = {
  active: "green",
  retired: "gray",
  blocked: "red",
  expired: "amber",
};

export const CANONICAL_PMS_COLUMNS = [
  "stay_date",
  "rooms_total",
  "rooms_sold",
  "rooms_available",
  "occupancy_pct",
  "adr",
  "revenue",
] as const;

/** Nhóm nhãn trong labels.json (eventType, runStatus, userRole…). */
export type LabelGroup = keyof Messages["labels"];

type LabelsTranslator = ReturnType<typeof useTranslations<"labels">>;

/** Hàm tra nhãn từ translator "labels" (dùng ở helper ngoài React hoặc server: getTranslations("labels")). */
export function createLabel(t: LabelsTranslator) {
  return (group: LabelGroup, key: string | null | undefined): string => {
    if (!key) return "—";
    const id = `${group}.${key}` as Parameters<LabelsTranslator>[0];
    return t.has(id) ? t(id) : key;
  };
}

export type LabelFn = ReturnType<typeof createLabel>;

/** `label(group, code)`: nhãn theo ngôn ngữ hiện tại, "—" khi rỗng, nguyên mã khi chưa có bản dịch. */
export function useLabel(): LabelFn {
  const t = useTranslations("labels");
  return useMemo(() => createLabel(t), [t]);
}
