import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { SessionProvider } from "@/lib/session";

const CONTRACT = `<!--
THESIS: Dashboard là bảng thị trường theo từng khách sạn: mỗi khách sạn một dải 30 đêm mang bốn dấu tin cậy và đường giá cùng trục; từ chối kiểu admin Tailwind mặc định với bảng số trơn, nhãn kỹ thuật lộ cho chủ khách sạn.
OWN-WORLD: Thanh bên tím than #16123a có logo ô cửa, nền sương #f4f5ff, thẻ trắng bo 12px viền #e3e1f0, tím #673de6 chỉ cho hành động và đang chọn; vàng #ffcd35 đậm dần theo độ khan (số chính xác), sọc #d6cbff (ít nhất), viền đứt (ẩn), tím đậm #2f1c6a "HẾT"; xanh #00b090 chỉ cho khách sạn của bạn. Be Vietnam Pro, số tabular.
STORY: Mở app → đọc đêm nay và 7 đêm tới trong một dòng → dò một đêm qua cả chồng khách sạn → bấm ô vào chi tiết đêm → đọc bản tin có bằng chứng bấm được.
FIRST VIEWPORT: Thanh bên 248px; tiêu đề Tổng quan, độ mới dữ liệu, chọn kỳ 14/30/60 đêm; dòng tóm tắt; dải Thị trường; dải Khách sạn của bạn (chấm xanh); các dải đối thủ cùng trục ngày dính. Signature: dò một đêm, rê hoặc tab vào một cột sáng cả chồng và bảng đọc liệt kê mọi khách sạn đêm đó.
FORM: Surface roll "Từng khách sạn một dải", vị trí 6 trong danh sách 7, seed 2dedb492.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
-->`;

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <div hidden dangerouslySetInnerHTML={{ __html: CONTRACT }} />
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
