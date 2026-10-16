import type { DateCell } from "@/lib/api";

/**
 * Phòng còn của cả khách sạn trên Booking.com cho một đêm (backend `analytics/rooms_left_bounds.py`):
 * chỉ là số chính xác khi min = max; còn lại là khoảng [min, max] hoặc "ít nhất min" (max = null,
 * thường vì có loại phòng chạm trần 10 của Booking). Không bao giờ hiện tổng thiếu như số chính xác.
 */
export type RoomsLeft = { min: number; max: number | null; exact: number | null };

type RoomsFields = Pick<DateCell, "exact_rooms_left"> & Partial<Pick<DateCell, "rooms_left_min" | "rooms_left_max">>;

export function roomsLeftOf(c: RoomsFields | null | undefined): RoomsLeft | null {
  if (!c) return null;
  const exact = c.exact_rooms_left ?? null;
  const min = c.rooms_left_min ?? exact;
  if (min === null) return null;
  const max = c.rooms_left_max ?? exact;
  return { min, max, exact: max !== null && max === min ? min : null };
}

/** Chữ ngắn: "12", "12–19" hoặc "≥12". */
export function roomsLeftText(r: RoomsLeft, fmtInt: (n: number) => string = String): string {
  if (r.exact !== null) return fmtInt(r.exact);
  if (r.max !== null) return `${fmtInt(r.min)}–${fmtInt(r.max)}`;
  return `≥${fmtInt(r.min)}`;
}

/** Chắc chắn còn không quá `n` phòng (cần biết trần): "≥2" không bao giờ là "sắp hết". */
export function definitelyAtMost(c: RoomsFields | null | undefined, n: number): boolean {
  const r = roomsLeftOf(c);
  return r !== null && r.max !== null && r.max <= n;
}
