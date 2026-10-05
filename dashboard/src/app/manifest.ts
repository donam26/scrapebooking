import type { MetadataRoute } from "next";
import { getLocale, getTranslations } from "next-intl/server";

/**
 * PWA: cài OTARadar lên màn hình điện thoại, mở thẳng vào Bảng điều khiển.
 * Màu theo DESIGN.md: nền xám xanh nhạt, thanh trạng thái xanh OTARadar.
 * Trình duyệt tải manifest không kèm cookie nên thường ra ngôn ngữ mặc định (tiếng Việt).
 */
export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const [locale, t] = await Promise.all([getLocale(), getTranslations("common.meta")]);
  return {
    name: "OTARadar",
    short_name: "OTARadar",
    description: t("manifestDescription"),
    lang: locale,
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    background_color: "#f5f6fa",
    theme_color: "#0062ff",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
