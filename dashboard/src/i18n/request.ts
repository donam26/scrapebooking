import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from "./config";
import { loadMessages } from "@/messages";

/**
 * next-intl không dùng tiền tố URL: ngôn ngữ lấy từ cookie NEXT_LOCALE (nút chuyển ngôn ngữ
 * đặt cookie qua server action `setLocale`), thiếu hoặc sai thì dùng tiếng Việt.
 */
export default getRequestConfig(async () => {
  const value = (await cookies()).get(LOCALE_COOKIE)?.value;
  const locale = isLocale(value) ? value : DEFAULT_LOCALE;
  return {
    locale,
    messages: await loadMessages(locale),
    // Ngày giờ hiển thị dùng múi giờ trình duyệt/tenant qua lib/format; đặt cố định để server và
    // client không lệch khi next-intl tự định dạng.
    timeZone: "Asia/Ho_Chi_Minh",
  };
});
