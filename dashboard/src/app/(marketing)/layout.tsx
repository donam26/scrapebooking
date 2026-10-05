import { Be_Vietnam_Pro } from "next/font/google";
import type { ReactNode } from "react";
import "./landing.css";

// Be Vietnam Pro: sans hình học do nhà thiết kế Việt làm, dấu tiếng Việt chuẩn ở mọi cỡ.
const sans = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--lp-font",
  display: "swap",
});

// Hợp đồng thiết kế của trang giới thiệu: DESIGN.md, mục "Ghi chú kỹ thuật từng layout".
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return <div className={`lp ${sans.variable}`}>{children}</div>;
}
