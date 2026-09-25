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

const CONTRACT = `<!--
THESIS: Trang giới thiệu theo chuẩn landing SaaS mà người dùng chọn (tham chiếu Hostinger): khách hiểu ngay dịch vụ đếm phòng còn và giá đối thủ, thấy sản phẩm chạy thật, rồi liên hệ.
OWN-WORLD: Nền tím than #16123a có quầng tím #673de6, nút tím #673de6 bo 8px, phần sáng #f4f5ff với thẻ trắng bo 16–24px, dấu tích xanh #00b090, dữ liệu: vàng #ffcd35 (số chính xác), tím nhạt gạch chéo (ít nhất), viền đứt (ẩn), tím đậm #2f1c6a (hết phòng). Be Vietnam Pro.
STORY: Hiểu (đếm phòng, 3 lượt/ngày, 30 đêm) → tin (mức tin cậy, bằng chứng, dữ liệu minh hoạ tương tác) → liên hệ (Zalo/điện thoại/email).
FIRST VIEWPORT: Trái: nhãn sản phẩm, tiêu đề trắng lớn, 3 dấu tích, "Liên hệ báo giá", nút tím Liên hệ tư vấn, dòng cam kết. Phải: ảnh biển Mỹ Khê bo góc với bảng phòng mini, nhãn sự kiện, hộp bản tin gõ chữ, công tắc lượt quét.
FORM: Chuẩn ngành (lối thoát chuẩn), người dùng chọn thay cho hướng được bốc thăm, seed e9787018.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
-->`;

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className={`lp ${sans.variable}`}>
      <div hidden dangerouslySetInnerHTML={{ __html: CONTRACT }} />
      {children}
    </div>
  );
}
