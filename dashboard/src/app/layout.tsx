import type { Metadata } from "next";
import { Be_Vietnam_Pro } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

// Be Vietnam Pro cho toàn bộ dashboard: một họ chữ, dấu tiếng Việt chuẩn ở mọi cỡ.
const sans = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-app",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "ScrapeBooking", template: "%s · ScrapeBooking" },
  description: "Số phòng còn và giá của đối thủ trên Booking.com, cập nhật ba lần mỗi ngày",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi" className={`h-full antialiased ${sans.variable}`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
