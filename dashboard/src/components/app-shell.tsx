"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useSession } from "@/lib/session";
import { USER_ROLE_LABEL } from "@/lib/labels";
import { Button, ErrorBox, Select, Skeleton, cx } from "./ui";

const TENANT_NAV = [
  { href: "/overview", label: "Tổng quan" },
  { href: "/events", label: "Sự kiện" },
  { href: "/insights", label: "Bản tin AI" },
  { href: "/settings", label: "Cài đặt" },
];

const ADMIN_NAV = [
  { href: "/admin/tenants", label: "Tenant" },
  { href: "/admin/users", label: "Người dùng" },
  { href: "/admin/health", label: "Sức khoẻ scraper" },
];

function NavLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cx(
        "block whitespace-nowrap rounded px-3 py-1.5 text-sm",
        active ? "bg-sky-100 font-medium text-sky-900" : "text-slate-700 hover:bg-slate-100",
      )}
    >
      {label}
    </Link>
  );
}

export function TenantSwitcher() {
  const { isOperator, tenants, tenantId, setTenantId } = useSession();
  if (!isOperator) return null;
  return (
    <label className="flex items-center gap-2 text-xs text-slate-600">
      <span className="hidden sm:inline">Tenant</span>
      <Select
        aria-label="Chọn tenant"
        value={tenantId ?? ""}
        onChange={(e) => setTenantId(e.target.value === "" ? null : Number(e.target.value))}
        className="max-w-[200px]"
      >
        <option value="">— Chọn tenant —</option>
        {tenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
            {t.active ? "" : " (tắt)"}
          </option>
        ))}
      </Select>
    </label>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const session = useSession();
  const { user, loading, error, isOperator, tenantId, tenant, logout } = session;
  const isAdminRoute = pathname.startsWith("/admin");

  let body: ReactNode;
  if (loading) {
    body = <Skeleton rows={6} className="max-w-xl" />;
  } else if (error || !user) {
    body = <ErrorBox error={error ?? "Không tải được phiên đăng nhập"} />;
  } else if (isOperator && tenantId === null && !isAdminRoute) {
    body = (
      <div className="max-w-md rounded-lg border border-line bg-surface p-6 shadow-xs">
        <h2 className="text-base font-semibold">Chọn tenant để xem</h2>
        <p className="mt-1 text-sm text-slate-600">Tài khoản vận hành cần chọn một tenant ở thanh trên, hoặc tạo tenant mới.</p>
        <div className="mt-3 flex items-center gap-3">
          <TenantSwitcher />
          <Link href="/admin/tenants" className="text-sm text-sky-700 hover:underline">
            Quản lý tenant
          </Link>
        </div>
      </div>
    );
  } else {
    body = children;
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-line bg-surface md:w-56 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-4 py-3">
          <span className="inline-block h-6 w-6 rounded bg-sky-700" aria-hidden />
          <span className="text-sm font-semibold text-slate-900">Theo dõi đối thủ</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-4">
          {TENANT_NAV.map((n) => (
            <NavLink key={n.href} {...n} active={pathname === n.href || pathname.startsWith(`${n.href}/`) || (n.href === "/overview" && pathname.startsWith("/hotels"))} />
          ))}
          {isOperator && (
            <>
              <div className="mt-0 hidden px-3 pt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400 md:block">Vận hành</div>
              {ADMIN_NAV.map((n) => (
                <NavLink key={n.href} {...n} active={pathname.startsWith(n.href)} />
              ))}
            </>
          )}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2">
          <div className="flex items-center gap-3">
            <TenantSwitcher />
            {!isOperator && tenant && <span className="text-sm text-slate-600">{tenant.name}</span>}
          </div>
          {user && (
            <div className="flex items-center gap-3 text-xs text-slate-600">
              <span>
                <span className="font-medium text-slate-800">{user.email}</span> · {USER_ROLE_LABEL[user.role] ?? user.role}
              </span>
              <Button size="sm" variant="ghost" onClick={() => void logout()}>
                Đăng xuất
              </Button>
            </div>
          )}
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">{body}</main>
      </div>
    </div>
  );
}
