import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Theo dõi đối thủ", template: "%s · Theo dõi đối thủ" },
  description: "Giám sát tình trạng phòng và giá đối thủ trên Booking.com",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
