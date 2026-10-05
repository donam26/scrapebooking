import type { Locale } from "@/i18n/config";
import type vi from "./vi";

/**
 * Bản dịch theo ngôn ngữ. Tiếng Việt là nguồn gốc: kiểu `Messages` suy ra từ `vi/`, bản khác
 * phải khớp đủ khoá (tsc báo thiếu; `npm run i18n:check` báo thừa/thiếu và lệch tham số ICU).
 */
export type Messages = typeof vi;

const LOADERS: Record<Locale, () => Promise<Messages>> = {
  vi: () => import("./vi").then((m) => m.default),
  en: () => import("./en").then((m) => m.default),
};

export function loadMessages(locale: Locale): Promise<Messages> {
  return LOADERS[locale]();
}
