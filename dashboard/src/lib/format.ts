/**
 * Định dạng số, tiền, ngày theo ngôn ngữ đang chọn.
 * Backend (pydantic) trả Decimal dưới dạng chuỗi ("110.00"), date "YYYY-MM-DD", datetime ISO.
 *
 * - Hàm thuần không phụ thuộc ngôn ngữ (parse, cộng ngày, so lịch quét…) export trực tiếp.
 * - Hàm hiển thị nằm trong bộ `Fmt` gắn với một ngôn ngữ:
 *     component (server hoặc client): `const { fmtMoney, fmtNight } = useFmt();`
 *     server component async:          `const { fmtMoney } = await getFmt();` (src/i18n/server.ts)
 *     helper ngoài React:              nhận `fmt: Fmt` làm tham số.
 */

import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";
import { INTL_LOCALE, type Locale } from "@/i18n/config";

// ---- hàm thuần (không phụ thuộc ngôn ngữ) ----

/** Chuỗi Decimal -> number, null nếu không parse được. */
export function num(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
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

/** Ngày hôm nay "YYYY-MM-DD" theo múi giờ (của tenant), không theo giờ trình duyệt. */
export function todayIn(timezone: string, nowMs: number): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(nowMs);
  } catch {
    return isoDate(new Date(nowMs));
  }
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

/** Đêm cuối tuần của khách sạn: đêm thứ Sáu và thứ Bảy (đêm Chủ nhật là đêm trong tuần). */
export function isWeekend(iso: string): boolean {
  const d = parseDate(iso).getDay();
  return d === 5 || d === 6;
}

/** Hai mốc cùng ngày (giờ trình duyệt)? */
function sameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** Giờ hiện tại "HH:MM" theo múi giờ tenant. */
function nowHHMM(timezone: string, now: Date): string {
  try {
    return new Intl.DateTimeFormat("en-GB", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(now);
  } catch {
    return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  }
}

/**
 * Lượt quét gần nhất cũ hơn một chu kỳ lịch (khoảng lớn nhất giữa hai mốc liên tiếp, tính vòng qua
 * nửa đêm, cộng 2 giờ cho thời gian chạy): ít nhất một mốc quét đã bị lỡ, dữ liệu đang cũ.
 */
export function scanOverdue(lastIso: string | null | undefined, scanTimes: string[], now: Date = new Date()): boolean {
  const mins = scanTimes
    .filter(Boolean)
    .map((t) => {
      const [h, m] = t.split(":").map(Number);
      return h * 60 + m;
    })
    .sort((a, b) => a - b);
  if (!lastIso || mins.length === 0) return false;
  const maxGap = Math.max(...mins.map((m, i) => (i + 1 < mins.length ? mins[i + 1] : mins[0] + 1440) - m));
  return now.getTime() - new Date(lastIso).getTime() > (maxGap + 120) * 60_000;
}

/** Lượt quét đã kết thúc mà không thu được đêm nào (proxy lỗi, bị chặn…): dữ liệu không được làm mới. */
export function scanCollectedNothing(run: { status: string; ok_count: number; sold_out_count: number }): boolean {
  return run.status !== "running" && run.ok_count + run.sold_out_count === 0;
}

/** Slug trong đường dẫn thành tên đọc được: "vn/meander-saigon" -> "Meander Saigon". */
export function prettySlug(slug: string): string {
  const last = slug.split("/").pop() ?? slug;
  return last
    .split("-")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// ---- bộ định dạng theo ngôn ngữ ----

/** Translator của namespace "format" (next-intl), dùng cho các cụm chữ như "hôm nay", "1g 12p". */
export type FormatTranslator = ReturnType<typeof useTranslations<"format">>;

/** Thứ viết tắt kiểu lịch Việt: CN, T2…T7 (ổn định giữa các bản ICU, khác "Th 5" của Intl). */
const VI_WEEKDAY = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

export function createFmt(locale: Locale, t: FormatTranslator) {
  const tag = INTL_LOCALE[locale];
  const numberFmt = new Intl.NumberFormat(tag, { maximumFractionDigits: 2 });
  const intFmt = new Intl.NumberFormat(tag, { maximumFractionDigits: 0 });
  const compactFmt = new Intl.NumberFormat(tag, { notation: "compact", maximumFractionDigits: 1 });
  const dateFmt = new Intl.DateTimeFormat(tag, { day: "2-digit", month: "2-digit", year: "numeric" });
  const weekdayFmt = new Intl.DateTimeFormat(tag, { weekday: "short" });
  const dateTimeFmt = new Intl.DateTimeFormat(tag, { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const timeFmt = new Intl.DateTimeFormat(tag, { hour: "2-digit", minute: "2-digit" });
  const dayMonthFmt = new Intl.DateTimeFormat(tag, { day: "2-digit", month: "2-digit" });
  /** "24/09": thứ tự ngày/tháng theo ngôn ngữ, luôn ngăn bằng "/" (vi-VN của Intl dùng "-"). */
  const dayMonth = (d: Date) =>
    dayMonthFmt
      .formatToParts(d)
      .filter((x) => x.type === "day" || x.type === "month")
      .map((x) => x.value)
      .join("/");
  const digitsCache = new Map<number, Intl.NumberFormat>();
  const currencyCache = new Map<string, Intl.NumberFormat | null>();

  function digitsFmt(digits: number): Intl.NumberFormat {
    let f = digitsCache.get(digits);
    if (!f) {
      f = new Intl.NumberFormat(tag, { maximumFractionDigits: digits });
      digitsCache.set(digits, f);
    }
    return f;
  }

  function currencyFormatter(currency: string): Intl.NumberFormat | null {
    if (currencyCache.has(currency)) return currencyCache.get(currency) ?? null;
    let f: Intl.NumberFormat | null;
    try {
      f = new Intl.NumberFormat(tag, { style: "currency", currency, maximumFractionDigits: currency === "VND" ? 0 : 2 });
    } catch {
      f = null;
    }
    currencyCache.set(currency, f);
    return f;
  }

  function fmtNum(value: string | number | null | undefined, digits?: number): string {
    const n = num(value);
    if (n === null) return "—";
    return (digits === undefined ? numberFmt : digitsFmt(digits)).format(n);
  }

  function fmtInt(value: number | null | undefined): string {
    return value === null || value === undefined ? "—" : intFmt.format(value);
  }

  /** Số rút gọn cho ô hẹp: 1250000 -> "1,3 Tr" / "1.3M". */
  function fmtCompact(value: string | number | null | undefined): string {
    const n = num(value);
    return n === null ? "—" : compactFmt.format(n);
  }

  function fmtMoney(value: string | number | null | undefined, currency: string | null | undefined): string {
    const n = num(value);
    if (n === null) return "—";
    const f = currency ? currencyFormatter(currency) : null;
    if (f) return f.format(n);
    return currency ? `${numberFmt.format(n)} ${currency}` : numberFmt.format(n);
  }

  /**
   * Giá ngắn luôn có đơn vị cho ô hẹp: VND 850.000 -> "850k", 1.250.000 -> "1,3tr" / "1.3M",
   * 12.400.000 -> "12tr". Tiền khác VND (hoặc không rõ) dùng `fmtMoney` đầy đủ.
   */
  function fmtPriceShort(value: string | number | null | undefined, currency: string | null | undefined = "VND"): string {
    const n = num(value);
    if (n === null) return "—";
    if (currency && currency !== "VND") return fmtMoney(n, currency);
    const abs = Math.abs(n);
    const k = Math.round(abs / 1000);
    if (k >= 1000) return t("priceMillion", { value: digitsFmt(abs >= 10_000_000 ? 0 : 1).format(n / 1_000_000) });
    if (k >= 1) return t("priceThousand", { value: intFmt.format(Math.sign(n) * k) });
    return fmtMoney(n, "VND");
  }

  /** Số thập phân đã là phần trăm (12.5 -> "12,5%"), có dấu khi `signed`. */
  function fmtPct(value: string | number | null | undefined, opts: { signed?: boolean; digits?: number } = {}): string {
    const n = num(value);
    if (n === null) return "—";
    const s = digitsFmt(opts.digits ?? 1).format(Math.abs(n));
    const sign = n > 0 ? (opts.signed ? "+" : "") : n < 0 ? "−" : "";
    return `${sign}${s}%`;
  }

  /** Tỷ lệ 0..1 -> phần trăm. */
  function fmtShare(value: string | number | null | undefined): string {
    const n = num(value);
    return n === null ? "—" : fmtPct(n * 100, { digits: 0 });
  }

  function fmtSigned(value: string | number | null | undefined): string {
    const n = num(value);
    if (n === null) return "—";
    return n > 0 ? `+${numberFmt.format(n)}` : numberFmt.format(n);
  }

  /** "YYYY-MM-DD" -> "24/09/2026" */
  function fmtDate(iso: string | null | undefined): string {
    return iso ? dateFmt.format(parseDate(iso)) : "—";
  }

  /** "YYYY-MM-DD" -> "24/09" (thứ tự ngày/tháng theo ngôn ngữ). */
  function fmtDateShort(iso: string): string {
    return dayMonth(parseDate(iso));
  }

  /** "YYYY-MM-DD" -> "T5" / "Thu" */
  function fmtWeekday(iso: string): string {
    const d = parseDate(iso);
    return locale === "vi" ? VI_WEEKDAY[d.getDay()] : weekdayFmt.format(d);
  }

  /** "YYYY-MM-DD" -> "T5 24/09" / "Thu 24/09". */
  function fmtNight(iso: string): string {
    return `${fmtWeekday(iso)} ${fmtDateShort(iso)}`;
  }

  /** ISO datetime -> "24/09/2026 14:05" */
  function fmtDateTime(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : dateTimeFmt.format(d);
  }

  /** ISO datetime -> "14:05 24/09" */
  function fmtDayTime(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${timeFmt.format(d)} ${dayMonth(d)}`;
  }

  function fmtTime(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : timeFmt.format(d);
  }

  /** Khoảng thời gian giữa hai mốc ISO -> "1g 12p" / "1h 12m". */
  function fmtDuration(fromIso: string | null | undefined, toIso: string | null | undefined): string {
    if (!fromIso || !toIso) return "—";
    const ms = new Date(toIso).getTime() - new Date(fromIso).getTime();
    if (!Number.isFinite(ms) || ms < 0) return "—";
    const minutes = Math.round(ms / 60_000);
    if (minutes < 60) return t("durationMinutes", { minutes });
    return t("durationHours", { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
  }

  /** ISO datetime -> "14:06 hôm nay" / "22:05 hôm qua" / "22:05 24/09". */
  function fmtWhen(iso: string | null | undefined, now: Date = new Date()): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const time = timeFmt.format(d);
    if (sameLocalDay(d, now)) return t("timeToday", { time });
    const y = new Date(now);
    y.setDate(y.getDate() - 1);
    if (sameLocalDay(d, y)) return t("timeYesterday", { time });
    return `${time} ${dayMonth(d)}`;
  }

  /** Khoảng cách tới hiện tại: "3 phút trước", "2 giờ trước", "hôm qua"… */
  function fmtAgo(iso: string | null | undefined, now: Date = new Date()): string {
    if (!iso) return "—";
    const ms = now.getTime() - new Date(iso).getTime();
    if (!Number.isFinite(ms)) return "—";
    const minutes = Math.round(ms / 60_000);
    if (minutes < 1) return t("justNow");
    if (minutes < 60) return t("minutesAgo", { count: minutes });
    const hours = Math.round(minutes / 60);
    if (hours < 24) return t("hoursAgo", { count: hours });
    const days = Math.round(hours / 24);
    return days === 1 ? t("yesterday") : t("daysAgo", { count: days });
  }

  /** Mốc quét kế tiếp theo lịch tenant: "22:00" hoặc "06:00 ngày mai". */
  function nextScanLabel(scanTimes: string[], timezone: string, now: Date = new Date()): string | null {
    const times = [...scanTimes].filter(Boolean).sort();
    if (times.length === 0) return null;
    const cur = nowHHMM(timezone, now);
    const next = times.find((x) => x > cur);
    return next ?? t("timeTomorrow", { time: times[0] });
  }

  /** "D-0" -> "Đêm nay", "D-1" -> "Đêm mai", còn lại "Còn N ngày". */
  function fmtNightRel(daysToArrival: number | null | undefined): string | null {
    if (daysToArrival === null || daysToArrival === undefined) return null;
    if (daysToArrival === 0) return t("tonight");
    if (daysToArrival === 1) return t("tomorrowNight");
    return t("daysAway", { count: daysToArrival });
  }

  /** Kỳ ngắn: "25/09 – 24/10/2026". */
  function fmtPeriod(fromIso: string, toIso: string): string {
    return `${fmtDateShort(fromIso)} – ${fmtDate(toIso)}`;
  }

  return {
    locale,
    fmtPeriod,
    fmtNum,
    fmtInt,
    fmtCompact,
    fmtMoney,
    fmtPriceShort,
    fmtPct,
    fmtShare,
    fmtSigned,
    fmtDate,
    fmtDateShort,
    fmtWeekday,
    fmtNight,
    fmtDateTime,
    fmtDayTime,
    fmtTime,
    fmtDuration,
    fmtWhen,
    fmtAgo,
    nextScanLabel,
    fmtNightRel,
  };
}

export type Fmt = ReturnType<typeof createFmt>;

/** Bộ định dạng theo ngôn ngữ hiện tại; dùng được trong server component (không async) và client. */
export function useFmt(): Fmt {
  const locale = useLocale();
  const t = useTranslations("format");
  return useMemo(() => createFmt(locale, t), [locale, t]);
}
