/**
 * Định dạng số, tiền, ngày cho giao diện vi-VN.
 * Backend (pydantic) trả Decimal dưới dạng chuỗi ("110.00"), date "YYYY-MM-DD", datetime ISO.
 */

const LOCALE = "vi-VN";

/** Chuỗi Decimal -> number, null nếu không parse được. */
export function num(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

const numberFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 });
const intFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const currencyCache = new Map<string, Intl.NumberFormat>();

function currencyFormatter(currency: string): Intl.NumberFormat | null {
  const cached = currencyCache.get(currency);
  if (cached) return cached;
  try {
    const fmt = new Intl.NumberFormat(LOCALE, {
      style: "currency",
      currency,
      maximumFractionDigits: currency === "VND" ? 0 : 2,
    });
    currencyCache.set(currency, fmt);
    return fmt;
  } catch {
    return null;
  }
}

export function fmtNum(value: string | number | null | undefined, digits?: number): string {
  const n = num(value);
  if (n === null) return "—";
  if (digits === undefined) return numberFmt.format(n);
  return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: digits }).format(n);
}

export function fmtInt(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : intFmt.format(value);
}

const compactFmt = new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 });

/** Số rút gọn cho ô hẹp: 1250000 -> "1,3 Tr". */
export function fmtCompact(value: string | number | null | undefined): string {
  const n = num(value);
  return n === null ? "—" : compactFmt.format(n);
}

export function fmtMoney(
  value: string | number | null | undefined,
  currency: string | null | undefined,
): string {
  const n = num(value);
  if (n === null) return "—";
  const fmt = currency ? currencyFormatter(currency) : null;
  if (fmt) return fmt.format(n);
  return currency ? `${numberFmt.format(n)} ${currency}` : numberFmt.format(n);
}

/** Số thập phân đã là phần trăm (12.5 -> "12,5%"), có dấu khi `signed`. */
export function fmtPct(
  value: string | number | null | undefined,
  opts: { signed?: boolean; digits?: number } = {},
): string {
  const n = num(value);
  if (n === null) return "—";
  const digits = opts.digits ?? 1;
  const s = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: digits }).format(Math.abs(n));
  const sign = n > 0 ? (opts.signed ? "+" : "") : n < 0 ? "−" : "";
  return `${sign}${s}%`;
}

/** Tỷ lệ 0..1 -> phần trăm. */
export function fmtShare(value: string | number | null | undefined): string {
  const n = num(value);
  return n === null ? "—" : fmtPct(n * 100, { digits: 0 });
}

export function fmtSigned(value: string | number | null | undefined): string {
  const n = num(value);
  if (n === null) return "—";
  return n > 0 ? `+${numberFmt.format(n)}` : numberFmt.format(n);
}

/** "YYYY-MM-DD" -> Date local (tránh lệch ngày do UTC). */
export function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function todayIso(): string {
  return isoDate(new Date());
}

export function addDays(iso: string, days: number): string {
  const d = parseDate(iso);
  d.setDate(d.getDate() + days);
  return isoDate(d);
}

export function daysBetween(fromIso: string, toIso: string): number {
  const a = parseDate(fromIso).getTime();
  const b = parseDate(toIso).getTime();
  return Math.round((b - a) / 86_400_000);
}

export function dateRange(startIso: string, endIso: string): string[] {
  const n = daysBetween(startIso, endIso);
  if (n < 0) return [];
  return Array.from({ length: n + 1 }, (_, i) => addDays(startIso, i));
}

const dateFmt = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric" });
const weekdayFmt = new Intl.DateTimeFormat(LOCALE, { weekday: "short" });
const dateTimeFmt = new Intl.DateTimeFormat(LOCALE, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const timeFmt = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit" });

/** "YYYY-MM-DD" -> "24/09/2026" */
export function fmtDate(iso: string | null | undefined): string {
  return iso ? dateFmt.format(parseDate(iso)) : "—";
}

/** "YYYY-MM-DD" -> "24/09" */
export function fmtDateShort(iso: string): string {
  const d = parseDate(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** "YYYY-MM-DD" -> "T5 24/09" (CN cho chủ nhật). */
export function fmtNight(iso: string): string {
  return `${fmtWeekday(iso).replace("Thứ ", "T")} ${fmtDateShort(iso)}`;
}

/** "YYYY-MM-DD" -> "T5" */
export function fmtWeekday(iso: string): string {
  return weekdayFmt.format(parseDate(iso));
}

export function isWeekend(iso: string): boolean {
  const d = parseDate(iso).getDay();
  return d === 0 || d === 6;
}

/** ISO datetime -> "24/09/2026 14:05" */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dateTimeFmt.format(d);
}

/** ISO datetime -> "14:05 24/09" */
export function fmtDayTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${timeFmt.format(d)} ${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : timeFmt.format(d);
}

/** Khoảng thời gian giữa hai mốc ISO -> "1g 12p". */
export function fmtDuration(fromIso: string | null | undefined, toIso: string | null | undefined): string {
  if (!fromIso || !toIso) return "—";
  const ms = new Date(toIso).getTime() - new Date(fromIso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${minutes}p`;
  return `${Math.floor(minutes / 60)}g ${minutes % 60}p`;
}

/** Hai mốc cùng ngày (giờ trình duyệt)? */
function sameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** ISO datetime -> "14:06 hôm nay" / "22:05 hôm qua" / "22:05 24/09". */
export function fmtWhen(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const t = timeFmt.format(d);
  if (sameLocalDay(d, now)) return `${t} hôm nay`;
  const y = new Date(now);
  y.setDate(y.getDate() - 1);
  if (sameLocalDay(d, y)) return `${t} hôm qua`;
  return `${t} ${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Khoảng cách tới hiện tại: "3 phút trước", "2 giờ trước", "hôm qua"… */
export function fmtAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const ms = now.getTime() - new Date(iso).getTime();
  if (!Number.isFinite(ms)) return "—";
  const m = Math.round(ms / 60_000);
  if (m < 1) return "vừa xong";
  if (m < 60) return `${m} phút trước`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} giờ trước`;
  const days = Math.round(h / 24);
  return days === 1 ? "hôm qua" : `${days} ngày trước`;
}

/** Giờ hiện tại "HH:MM" theo múi giờ tenant. */
function nowHHMM(timezone: string, now: Date): string {
  try {
    return new Intl.DateTimeFormat("en-GB", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(now);
  } catch {
    return timeFmt.format(now);
  }
}

/** Mốc quét kế tiếp theo lịch tenant: "22:00" hoặc "06:00 ngày mai". */
export function nextScanLabel(scanTimes: string[], timezone: string, now: Date = new Date()): string | null {
  const times = [...scanTimes].filter(Boolean).sort();
  if (times.length === 0) return null;
  const cur = nowHHMM(timezone, now);
  const next = times.find((t) => t > cur);
  return next ?? `${times[0]} ngày mai`;
}

/** "D-0" -> "Đêm nay", "D-1" -> "Đêm mai". */
export function fmtNightRel(daysToArrival: number | null | undefined): string | null {
  if (daysToArrival === null || daysToArrival === undefined) return null;
  if (daysToArrival === 0) return "Đêm nay";
  if (daysToArrival === 1) return "Đêm mai";
  return `Còn ${daysToArrival} ngày`;
}

/** Tên tạm từ slug Booking khi khách sạn chưa được quét: "vn/meander-saigon" -> "Meander Saigon". */
export function prettySlug(slug: string): string {
  const last = slug.split("/").pop() ?? slug;
  return last
    .split("-")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
