/**
 * Tham số động trên URL (`/hotels/[id]`, `/insights/[id]`, `/hotels/[id]/dates/[date]`).
 * Sai định dạng -> null để trang gọi `notFound()` thay vì xoay skeleton mãi.
 */

/** Số nguyên dương viết thường ("12"); không nhận "0", "1e3", " 12", "12.0". */
export function parseIdParam(raw: string | undefined): number | null {
  return raw !== undefined && /^[1-9]\d{0,14}$/.test(raw) ? Number(raw) : null;
}

/** Ngày YYYY-MM-DD đọc được (không nhận "2026-13-45"). */
export function parseDateParam(raw: string | undefined): string | null {
  return raw !== undefined && /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(raw)) ? raw : null;
}
