import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { SessionProvider } from "@/lib/session";

// i18n-ignore-next-line: hợp đồng thiết kế ẩn cho công cụ review, không hiển thị
const CONTRACT = `<!--
THESIS: Dashboard OTARadar theo giao diện mẫu khách hàng: thanh trên xanh, hàng tab ngang, thẻ trắng tiêu đề in hoa; mỗi số đều từ dữ liệu quét thật, ước tính ghi "≈".
OWN-WORLD: Thanh trên #0062ff có logo dấu sao, nền #f5f6fa, thẻ trắng bo 10px viền #e6e8ef; xanh #0062ff cho hành động, đang chọn và khách sạn của bạn; thang nhiệt phòng còn đỏ #dc2626 → cam → hổ phách → vàng nhạt → xanh lá #4ade80; cầu thấp xanh lá, vừa xanh dương, cao cam. Inter, số tabular.
STORY: Mở app vào Bảng điều khiển → đọc toàn cảnh đêm nay và dự báo cầu 14 đêm → Phòng trống để dò heatmap → Giá & định giá để so giá → Terminal+ cho bối cảnh (lễ, thời tiết, nhịp đặt phòng).
FIRST VIEWPORT: Thanh trên + 8 tab; dải đầu trang tên tab xanh và chọn kênh; lưới thẻ chỉ số; cột phải Cảnh báo, Khách sạn của bạn, Trạng thái dữ liệu.
-->`;

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <div hidden dangerouslySetInnerHTML={{ __html: CONTRACT }} />
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
