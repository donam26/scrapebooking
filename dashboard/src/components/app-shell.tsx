"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, type TenantOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { USER_ROLE_LABEL } from "@/lib/labels";
import { fmtWhen, nextScanLabel } from "@/lib/format";
import { EmptyState, ErrorBox, Select, SkeletonBlock, cx } from "./ui";
import {
  BrandMark,
  IconBoard,
  IconBrief,
  IconBuilding,
  IconClose,
  IconHeartbeat,
  IconLogout,
  IconMenu,
  IconPulse,
  IconSliders,
  IconUsers,
} from "./icons";

type NavItem = { href: string; label: string; icon: ReactNode; match?: (p: string) => boolean };

const TENANT_NAV: NavItem[] = [
  { href: "/overview", label: "Tổng quan", icon: <IconBoard />, match: (p) => p.startsWith("/overview") || p.startsWith("/hotels") },
  { href: "/events", label: "Sự kiện", icon: <IconPulse /> },
  { href: "/insights", label: "Bản tin AI", icon: <IconBrief /> },
  { href: "/settings", label: "Cài đặt", icon: <IconSliders /> },
];

const ADMIN_NAV: NavItem[] = [
  { href: "/admin/tenants", label: "Tenant", icon: <IconBuilding /> },
  { href: "/admin/users", label: "Tài khoản", icon: <IconUsers /> },
  { href: "/admin/health", label: "Sức khoẻ scraper", icon: <IconHeartbeat /> },
];

function isActive(item: NavItem, pathname: string): boolean {
  if (item.match) return item.match(pathname);
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavLink({ item, active, onNavigate }: { item: NavItem; active: boolean; onNavigate?: () => void }) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cx(
        "group flex h-10 items-center gap-3 rounded-lg px-3 text-md font-medium transition-colors duration-150",
        "focus-visible:outline-brand-light",
        active ? "bg-white/[0.09] text-white" : "text-on-night-soft hover:bg-white/[0.05] hover:text-white",
      )}
    >
      <span className={cx("shrink-0 transition-colors", active ? "text-brand-light" : "text-on-night-muted group-hover:text-on-night-soft")}>{item.icon}</span>
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

/** Operator chọn tenant đang xem (trên nền tím than). */
export function TenantSwitcher({ dark = true }: { dark?: boolean }) {
  const { isOperator, tenants, tenantId, setTenantId } = useSession();
  if (!isOperator) return null;
  return (
    <label className="block">
      <span className={cx("mb-1.5 block text-xs font-semibold", dark ? "text-on-night-muted" : "text-body")}>Đang xem tenant</span>
      <Select
        aria-label="Chọn tenant"
        value={tenantId ?? ""}
        onChange={(e) => setTenantId(e.target.value === "" ? null : Number(e.target.value))}
        className={cx(
          dark &&
            "border-white/15 bg-white/[0.06] text-white shadow-none hover:border-white/30 focus:border-brand-light focus:ring-brand-light/25 [&>option]:text-ink",
        )}
      >
        <option value="">Chọn tenant…</option>
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

/** Độ mới dữ liệu: lượt quét gần nhất và mốc kế tiếp theo lịch tenant. */
function Freshness({ settings }: { settings: TenantOut | undefined }) {
  const runs = useApi("shell:runs", () => api.runs(1));
  const last = runs.data?.[0];
  const next = settings ? nextScanLabel(settings.scan_times, settings.timezone) : null;
  if (!last && !next) return null;
  const running = last?.status === "running";
  return (
    <div className="rounded-lg bg-white/[0.04] px-3 py-2.5 text-xs leading-relaxed text-on-night-soft">
      <div className="flex items-center gap-2">
        <span aria-hidden className={cx("h-2 w-2 shrink-0 rounded-full", running ? "animate-pulse bg-exact" : "bg-yours shadow-[0_0_0_3px_rgba(0,176,144,0.18)]")} />
        <span className="text-white">{running ? "Đang quét…" : last ? `Quét lúc ${fmtWhen(last.finished_at ?? last.started_at)}` : "Chưa có lượt quét"}</span>
      </div>
      {next && <div className="mt-0.5 pl-4 text-on-night-muted">Lượt tiếp theo {next}</div>}
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user, isOperator, tenantId, logout } = useSession();
  // Tên và lịch quét của tenant đang xem (người dùng tenant không có danh sách tenant).
  const settings = useApi(tenantId === null ? null : "settings", () => api.settings.get());
  const tenantName = settings.data?.name;
  const initial = (user?.email ?? "?").slice(0, 1).toUpperCase();

  return (
    <div className="flex h-full flex-col bg-night text-on-night-soft">
      <div className="flex h-16 shrink-0 items-center gap-2.5 px-5">
        <BrandMark size={28} />
        <span className="text-[13.5px] font-extrabold tracking-[0.08em] text-white">SCRAPEBOOKING</span>
      </div>

      <div className="px-4 pb-3">
        {isOperator ? (
          <TenantSwitcher />
        ) : (
          tenantName && (
            <div className="rounded-lg border border-white/10 px-3 py-2.5">
              <div className="text-xs text-on-night-muted">Khách sạn</div>
              <div className="line-clamp-2 text-md font-semibold leading-snug text-white" title={tenantName}>
                {tenantName}
              </div>
            </div>
          )
        )}
      </div>

      <nav aria-label="Điều hướng chính" className="sb-scroll flex-1 overflow-y-auto px-3 pb-4">
        <ul className="space-y-0.5">
          {TENANT_NAV.map((n) => (
            <li key={n.href}>
              <NavLink item={n} active={isActive(n, pathname)} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
        {isOperator && (
          <>
            <div className="mb-1.5 mt-6 px-3 text-xs font-semibold text-on-night-muted">Vận hành</div>
            <ul className="space-y-0.5">
              {ADMIN_NAV.map((n) => (
                <li key={n.href}>
                  <NavLink item={n} active={isActive(n, pathname)} onNavigate={onNavigate} />
                </li>
              ))}
            </ul>
          </>
        )}
      </nav>

      <div className="space-y-3 border-t border-white/[0.08] px-4 py-4">
        {tenantId !== null && <Freshness settings={settings.data} />}
        {user && (
          <div className="flex items-center gap-3">
            <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-night-3 text-sm font-bold text-white">
              {initial}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-white" title={user.email}>
                {user.email}
              </div>
              <div className="text-xs text-on-night-muted">{USER_ROLE_LABEL[user.role] ?? user.role}</div>
            </div>
            <button
              type="button"
              onClick={() => void logout()}
              title="Đăng xuất"
              aria-label="Đăng xuất"
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-on-night-muted transition-colors hover:bg-white/[0.08] hover:text-white focus-visible:outline-brand-light"
            >
              <IconLogout size={17} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ShellLoading() {
  return (
    <div className="space-y-4" aria-busy aria-label="Đang tải">
      <SkeletonBlock className="h-8 w-56" />
      <SkeletonBlock className="h-4 w-80" />
      <SkeletonBlock className="mt-6 h-24 w-full" />
      <SkeletonBlock className="h-64 w-full" />
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, loading, error, isOperator, tenantId } = useSession();
  const isAdminRoute = pathname.startsWith("/admin");
  const [drawer, setDrawer] = useState(false);

  // Đóng ngăn kéo khi đổi trang; Esc để đóng.
  const [drawerPath, setDrawerPath] = useState(pathname);
  if (drawerPath !== pathname) {
    setDrawerPath(pathname);
    setDrawer(false);
  }
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  let body: ReactNode;
  if (loading) {
    body = <ShellLoading />;
  } else if (error || !user) {
    body = <ErrorBox error={error ?? "Không tải được phiên đăng nhập"} className="max-w-xl" />;
  } else if (isOperator && tenantId === null && !isAdminRoute) {
    body = (
      <EmptyState
        icon={<IconBuilding />}
        title="Chọn tenant để xem"
        className="mx-auto mt-10 max-w-lg border border-line bg-surface"
        action={
          <div className="flex flex-col items-center gap-3">
            <div className="w-64 text-left">
              <TenantSwitcher dark={false} />
            </div>
            <Link href="/admin/tenants" className="text-base font-semibold text-brand hover:underline">
              Quản lý tenant
            </Link>
          </div>
        }
      >
        Tài khoản vận hành xem dữ liệu theo từng tenant. Chọn một tenant ở đây hoặc ở thanh bên.
      </EmptyState>
    );
  } else {
    body = children;
  }

  return (
    <div className="min-h-screen lg:pl-[248px]">
      {/* Thanh bên cố định (máy tính) */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] lg:block">
        <Sidebar />
      </aside>

      {/* Thanh trên + ngăn kéo (điện thoại, máy tính bảng) */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 bg-night px-4 lg:hidden">
        <button
          type="button"
          onClick={() => setDrawer(true)}
          aria-label="Mở menu"
          aria-expanded={drawer}
          className="grid h-9 w-9 place-items-center rounded-lg text-white hover:bg-white/10 focus-visible:outline-brand-light"
        >
          <IconMenu size={20} />
        </button>
        <BrandMark size={24} />
        <span className="text-[13px] font-extrabold tracking-[0.08em] text-white">SCRAPEBOOKING</span>
      </header>
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button type="button" aria-label="Đóng menu" className="absolute inset-0 bg-night/55 backdrop-blur-[2px]" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 w-[280px] max-w-[85vw] shadow-float [animation:sb-fade-in_.2s_var(--sb-ease)]">
            <Sidebar onNavigate={() => setDrawer(false)} />
            <button
              type="button"
              onClick={() => setDrawer(false)}
              aria-label="Đóng menu"
              className="absolute right-3 top-3.5 grid h-9 w-9 place-items-center rounded-lg text-on-night-soft hover:bg-white/10 hover:text-white"
            >
              <IconClose size={18} />
            </button>
          </div>
        </div>
      )}

      <main className="mx-auto min-w-0 max-w-[1560px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{body}</main>
    </div>
  );
}
