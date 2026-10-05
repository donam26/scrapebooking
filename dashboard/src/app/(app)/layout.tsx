import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { SessionProvider } from "@/lib/session";

// Hợp đồng thiết kế của app: DESIGN.md, mục "Ghi chú kỹ thuật từng layout".
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
