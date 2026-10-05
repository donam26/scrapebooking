import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

// Inter cho toàn bộ dashboard (theo giao diện mẫu OTARadar), có bộ dấu tiếng Việt.
const sans = Inter({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-app",
  display: "swap",
});

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("common.meta");
  return {
    title: { default: "OTARadar", template: "%s · OTARadar" },
    description: t("description"),
  };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={`h-full antialiased ${sans.variable}`}>
      <body className="min-h-full flex flex-col">
        {/* Bản dịch + ngôn ngữ đi xuống client component (next-intl v4 tự lấy từ src/i18n/request.ts). */}
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
