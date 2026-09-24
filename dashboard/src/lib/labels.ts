/** Nhãn tiếng Việt cho các mã trạng thái của backend. */

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
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export const EVENT_TYPE_LABEL: Record<string, string> = {
  sold_out: "Hết phòng",
  restock: "Có phòng lại",
  rooms_decrease: "Giảm phòng",
  rooms_increase: "Tăng phòng",
  low_stock_enter: "Sắp hết phòng",
  price_up: "Tăng giá",
  price_down: "Giảm giá",
  room_type_new: "Loại phòng mới",
  room_type_gone: "Mất loại phòng",
};

export type Tone = "green" | "red" | "amber" | "gray" | "blue" | "purple";

export const EVENT_TYPE_TONE: Record<string, Tone> = {
  sold_out: "red",
  restock: "green",
  rooms_decrease: "amber",
  rooms_increase: "green",
  low_stock_enter: "red",
  price_up: "blue",
  price_down: "purple",
  room_type_new: "gray",
  room_type_gone: "gray",
};

export const AVAILABILITY_LABEL: Record<string, string> = {
  available: "Còn phòng",
  sold_out: "Hết phòng",
  unknown: "Không rõ",
};

export const AVAILABILITY_TONE: Record<string, Tone> = {
  available: "green",
  sold_out: "red",
  unknown: "gray",
};

export const STOCK_CONFIDENCE_LABEL: Record<string, string> = {
  exact: "Chính xác",
  capped: "Ít nhất",
  hidden: "Ẩn",
  sold_out: "Hết",
};

export const STOCK_CONFIDENCE_TONE: Record<string, Tone> = {
  exact: "green",
  capped: "blue",
  hidden: "gray",
  sold_out: "red",
};

export const USER_ROLE_LABEL: Record<string, string> = {
  operator: "Vận hành",
  tenant_admin: "Quản trị",
  viewer: "Chỉ xem",
};

export const WATCH_ROLE_LABEL: Record<string, string> = {
  self: "Khách sạn của bạn",
  competitor: "Đối thủ",
};

export const RUN_STATUS_LABEL: Record<string, string> = {
  running: "Đang chạy",
  completed: "Hoàn tất",
  partial: "Một phần",
  failed: "Thất bại",
};

export const RUN_STATUS_TONE: Record<string, Tone> = {
  running: "blue",
  completed: "green",
  partial: "amber",
  failed: "red",
};

export const INSIGHT_STATUS_LABEL: Record<string, string> = {
  pending: "Đang tạo",
  batch_pending: "Chờ batch",
  completed: "Hoàn tất",
  failed: "Thất bại",
};

export const INSIGHT_STATUS_TONE: Record<string, Tone> = {
  pending: "blue",
  batch_pending: "amber",
  completed: "green",
  failed: "red",
};

export const INSIGHT_TRIGGER_LABEL: Record<string, string> = {
  daily: "Hằng ngày",
  on_demand: "Theo yêu cầu",
};

export const IMPORT_STATUS_LABEL: Record<string, string> = {
  completed: "Hoàn tất",
  partial: "Một phần",
  failed: "Thất bại",
};

export const IMPORT_STATUS_TONE: Record<string, Tone> = {
  completed: "green",
  partial: "amber",
  failed: "red",
};

export const LEVEL_LABEL: Record<string, string> = {
  high: "Cao",
  medium: "Trung bình",
  low: "Thấp",
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

export const PMS_COLUMN_LABEL: Record<string, string> = {
  stay_date: "Ngày lưu trú",
  rooms_total: "Tổng phòng",
  rooms_sold: "Phòng đã bán",
  rooms_available: "Phòng còn",
  occupancy_pct: "Công suất (%)",
  adr: "ADR",
  revenue: "Doanh thu",
};

export function label(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return "—";
  return map[key] ?? key;
}
