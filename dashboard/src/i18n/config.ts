/**
 * Cấu hình ngôn ngữ dùng chung (server, client, proxy API). Thêm ngôn ngữ mới:
 * 1. thêm mã vào LOCALES + INTL_LOCALE + LOCALE_NAME,
 * 2. tạo `src/messages/<mã>/` (chép từ `vi/`, dịch từng tệp) và đăng ký trong `src/messages/index.ts`,
 * 3. thêm `backend/app/i18n/locales/<mã>.json`,
 * 4. chạy `npm run i18n:check` (và `pytest tests/unit/test_i18n.py` ở backend).
 * Chi tiết: docs/i18n.md.
 */

export const LOCALES = ["vi", "en"] as const;
export type Locale = (typeof LOCALES)[number];

/** Khách hàng chính là khách sạn Việt Nam: chưa chọn thì dùng tiếng Việt. */
export const DEFAULT_LOCALE: Locale = "vi";

/** Cookie lưu ngôn ngữ đã chọn (cũng là tên next-intl dùng mặc định). */
export const LOCALE_COOKIE = "NEXT_LOCALE";

/** Thẻ BCP 47 cho Intl (số, tiền, ngày). en-GB: ngày dạng 24/09/2026 như bản tiếng Việt. */
export const INTL_LOCALE: Record<Locale, string> = {
  vi: "vi-VN",
  en: "en-GB",
};

/** Tên ngôn ngữ viết bằng chính ngôn ngữ đó (nút chuyển ngôn ngữ). */
export const LOCALE_NAME: Record<Locale, string> = {
  vi: "Tiếng Việt", // i18n-ignore: tên ngôn ngữ luôn viết bằng chính nó
  en: "English",
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}
