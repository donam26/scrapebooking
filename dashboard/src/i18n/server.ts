import { getLocale, getTranslations } from "next-intl/server";
import { createFmt, type Fmt } from "@/lib/format";

/** Bộ định dạng cho server component async (component thường dùng `useFmt()`). */
export async function getFmt(): Promise<Fmt> {
  const [locale, t] = await Promise.all([getLocale(), getTranslations("format")]);
  return createFmt(locale, t);
}
