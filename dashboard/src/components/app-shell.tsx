"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { api, type TenantOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useLabel } from "@/lib/labels";
import { useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { EmptyState, ErrorBox, Select, SkeletonBlock, cx } from "./ui";
import { LocaleSwitcher } from "./locale-switcher";
import { HEAT_LEVELS } from "./marks";
import { PopoverMenu } from "./popover-menu";
import { BrandMark, IconBell, IconBuilding, IconHelp, IconLogout, IconUser } from "./icons";

/**
 * Khung OTARadar: thanh trên xanh (logo, chọn khách sạn/tenant, trợ giúp, chuông, tài khoản)
 * và hàng tab ngang trắng, tab đang mở gạch chân xanh.
 */

/** `key`: khoá trong shell.nav (messages/<ngôn ngữ>/shell.json). */
type NavItem = { href: string; key: NavKey; match?: (p: string) => boolean };
type NavKey = "today" | "dashboard" | "competitors" | "availability" | "rates" | "terminal" | "insights" | "runs" | "settings" | "tenants" | "users" | "health";

const TENANT_NAV: NavItem[] = [
  { href: "/today", key: "today" },
  { href: "/dashboard", key: "dashboard" },
  { href: "/competitors", key: "competitors", match: (p) => p.startsWith("/competitors") || p.startsWith("/hotels") },
  { href: "/availability", key: "availability", match: (p) => p.startsWith("/availability") || p.startsWith("/overview") },
  { href: "/rates", key: "rates" },
  { href: "/terminal", key: "terminal", match: (p) => p.startsWith("/terminal") || p.startsWith("/pace") },
  { href: "/insights", key: "insights", match: (p) => p.startsWith("/insights") || p.startsWith("/events") },
  { href: "/runs", key: "runs" },
  { href: "/settings", key: "settings" },
];

const ADMIN_NAV: NavItem[] = [
  { href: "/admin/tenants", key: "tenants" },
  { href: "/admin/users", key: "users" },
  { href: "/admin/health", key: "health" },
];

function isActive(item: NavItem, pathname: string): boolean {
  if (item.match) return item.match(pathname);
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

const TOPBAR_BUTTON =
  "grid h-9 w-9 place-items-center rounded-full text-white/90 transition-colors hover:bg-white/15 hover:text-white focus-visible:outline-white";

/** Operator chọn tenant đang xem. `onBlue`: đặt trên thanh trên xanh. */
export function TenantSwitcher({ onBlue = false, className }: { onBlue?: boolean; className?: string }) {
  const { isOperator, tenants, tenantId, setTenantId } = useSession();
  const t = useTranslations("shell.tenant");
  if (!isOperator) return null;
  return (
    <Select
      aria-label={t("pick")}
      value={tenantId ?? ""}
      onChange={(e) => setTenantId(e.target.value === "" ? null : Number(e.target.value))}
      className={cx(
        onBlue &&
          "!h-9 max-w-[min(320px,42vw)] truncate border-white/25 bg-white/[0.12] !pr-9 font-medium text-white shadow-none [background-image:url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")] hover:border-white/45 focus:border-white focus:ring-white/25 [&>option]:text-ink",
        className,
      )}
    >
      <option value="">{t("pickPlaceholder")}</option>
      {tenants.map((tenant) => (
        <option key={tenant.id} value={tenant.id}>
          {tenant.name}
          {tenant.active ? "" : ` ${t("inactive")}`}
        </option>
      ))}
    </Select>
  );
}

/** Tên khách sạn/tenant đang xem (người dùng tenant không đổi được). */
function HotelPill({ name }: { name: string | undefined }) {
  if (!name) return null;
  return (
    <span
      title={name}
      className="inline-flex h-9 max-w-[min(320px,42vw)] items-center gap-2 rounded-lg border border-white/25 bg-white/[0.12] px-3 text-base font-medium text-white"
    >
      <IconBuilding size={16} className="shrink-0 opacity-80" />
      <span className="truncate">{name}</span>
    </span>
  );
}

/** Độ mới dữ liệu (định nghĩa chung ở lib/freshness.ts) và mốc quét kế tiếp theo lịch tenant. */
function Freshness({ settings }: { settings: TenantOut | undefined }) {
  const t = useTranslations("shell.freshness");
  const { fmtAgo, fmtWhen, nextScanLabel } = useFmt();
  const f = useDataFreshness(settings?.scan_times);
  const next = settings ? nextScanLabel(settings.scan_times, settings.timezone) : null;
  if (!f.updatedAt && !f.latest && !f.running && !next) return <div className="text-sm text-muted">{t("noScan")}</div>;
  return (
    <div className="text-sm leading-relaxed">
      <div className="flex items-center gap-2 text-ink">
        <span aria-hidden className={cx("h-2 w-2 shrink-0 rounded-full", f.tone === "bad" ? "bg-danger" : f.tone === "warn" ? "bg-hot" : "bg-yours")} />
        {f.updatedAt ? t("updatedAt", { when: fmtWhen(f.updatedAt) }) : t("noScan")}
      </div>
      {f.running && <div className="pl-4 text-muted">{t("scanning")}</div>}
      {f.latestEmpty && <div className={cx("pl-4 font-semibold", f.tone === "bad" ? "text-danger" : "text-warning-deep")}>{t("failed")}</div>}
      {f.overdue && <div className="pl-4 font-semibold text-warning-deep">{t("overdue", { ago: fmtAgo(f.updatedAt) })}</div>}
      {next && <div className="pl-4 text-muted">{t("next", { when: next })}</div>}
    </div>
  );
}

function HelpMenu({ settings }: { settings: TenantOut | undefined }) {
  const { tenantId } = useSession();
  const t = useTranslations("shell.help");
  const label = useLabel();
  return (
    <PopoverMenu label={t("title")} button={<IconHelp size={21} />} buttonClassName={TOPBAR_BUTTON} width={340}>
      {() => (
        <div className="divide-y divide-line">
          <div className="px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.06em] text-muted">{t("data")}</div>
            <div className="mt-1.5">{tenantId !== null ? <Freshness settings={settings} /> : <span className="text-sm text-muted">{t("pickTenant")}</span>}</div>
          </div>
          <div className="px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.06em] text-muted">{t("heatTitle")}</div>
            <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
              {HEAT_LEVELS.map((h) => (
                <li key={h.cls} className="flex items-center gap-2">
                  <span aria-hidden className={cx("h-3 w-3 rounded-[3px]", h.cls)} />
                  {label("heatLevel", h.key)}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted">{t("heatNote")}</p>
          </div>
        </div>
      )}
    </PopoverMenu>
  );
}

/** Chuông: 8 thay đổi mới nhất (hết phòng, có lại, đổi giá…), chấm đỏ nếu có thay đổi trong 24 giờ. */
function BellMenu() {
  const t = useTranslations("shell.bell");
  const label = useLabel();
  const { fmtAgo, fmtDateShort } = useFmt();
  const events = useApi("shell:events", () => api.events({ limit: 8 }));
  const items = events.data ?? [];
  const [now] = useState(() => Date.now());
  const fresh = items.some((e) => now - new Date(e.observed_at).getTime() < 24 * 3600 * 1000);
  return (
    <PopoverMenu
      label={t("title")}
      buttonClassName={cx(TOPBAR_BUTTON, "relative")}
      width={360}
      button={
        <>
          <IconBell size={20} />
          {fresh && <span aria-hidden className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[#ff4d4f] ring-2 ring-night" />}
        </>
      }
    >
      {(close) => (
        <div>
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-[0.06em] text-muted">{t("latest")}</span>
            <Link href="/events" onClick={close} className="text-sm font-semibold text-brand hover:underline">
              {t("viewAll")}
            </Link>
          </div>
          {events.error ? (
            <ErrorBox error={events.error} className="m-3" />
          ) : items.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-muted">{events.loading ? t("loading") : t("empty")}</div>
          ) : (
            <ul className="max-h-[360px] divide-y divide-line overflow-y-auto">
              {items.map((e) => (
                <li key={e.id}>
                  <Link href={`/hotels/${e.hotel_id}/dates/${e.stay_date}`} onClick={close} className="block px-4 py-2.5 hover:bg-subtle">
                    <div className="truncate text-sm font-semibold text-ink">{e.hotel_name ?? t("hotelFallback", { id: e.hotel_id })}</div>
                    <div className="text-sm text-body">
                      {t("eventLine", { event: label("eventType", e.event_type), night: fmtDateShort(e.stay_date) })}
                    </div>
                    <div className="text-xs text-muted">{fmtAgo(e.observed_at)}</div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </PopoverMenu>
  );
}

function UserMenu() {
  const { user, logout } = useSession();
  const t = useTranslations("shell.user");
  const label = useLabel();
  if (!user) return null;
  return (
    <PopoverMenu
      label={t("title")}
      width={280}
      buttonClassName="grid h-9 w-9 place-items-center rounded-full bg-white/[0.18] text-white transition-colors hover:bg-white/[0.28] focus-visible:outline-white"
      button={<IconUser size={19} />}
    >
      {() => (
        <div>
          <div className="border-b border-line px-4 py-3">
            <div className="truncate text-base font-semibold text-ink" title={user.email}>
              {user.email}
            </div>
            <div className="text-sm text-muted">{label("userRole", user.role)}</div>
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <span className="text-sm text-muted">{t("language")}</span>
            <LocaleSwitcher />
          </div>
          <button
            type="button"
            onClick={() => void logout()}
            className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-base font-medium text-body hover:bg-subtle hover:text-danger"
          >
            <IconLogout size={17} /> {t("logout")}
          </button>
        </div>
      )}
    </PopoverMenu>
  );
}

function TopBar() {
  const { user, isOperator, tenantId } = useSession();
  const settings = useApi(tenantId === null ? null : "settings", () => api.settings.get());
  const t = useTranslations("shell");
  return (
    <div className="bg-night text-white">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Link href="/dashboard" className="flex shrink-0 items-center gap-2.5 rounded-md focus-visible:outline-white" aria-label={t("homeLink")}>
          <BrandMark size={30} onBlue />
          <span className="text-[19px] font-semibold tracking-[-0.01em] max-sm:hidden">OTARadar</span>
        </Link>
        <div className="flex-1" />
        {user && (isOperator ? <TenantSwitcher onBlue /> : <HotelPill name={settings.data?.name} />)}
        {user && (
          <div className="flex items-center gap-1 sm:gap-2">
            <HelpMenu settings={settings.data} />
            {tenantId !== null && <BellMenu />}
            <UserMenu />
          </div>
        )}
      </div>
    </div>
  );
}

function TabLink({ item, active }: { item: NavItem; active: boolean }) {
  const t = useTranslations("shell.nav");
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cx(
        "relative inline-flex h-12 shrink-0 items-center whitespace-nowrap px-3.5 text-md transition-colors duration-150 sm:px-5",
        active ? "font-semibold text-ink" : "text-body hover:text-brand",
      )}
    >
      {t(item.key)}
      {active && <span aria-hidden className="absolute inset-x-1.5 bottom-0 h-[2.5px] rounded-full bg-brand" />}
    </Link>
  );
}

function TabBar() {
  const pathname = usePathname();
  const { isOperator } = useSession();
  const t = useTranslations("shell");
  return (
    <nav aria-label={t("mainNav")} className="border-b border-line bg-surface">
      <div className="sb-scroll mx-auto flex max-w-[1600px] items-stretch overflow-x-auto px-2 sm:px-4 lg:px-6">
        {TENANT_NAV.map((n) => (
          <TabLink key={n.href} item={n} active={isActive(n, pathname)} />
        ))}
        {isOperator && (
          <>
            <span aria-hidden className="mx-2 my-3 w-px shrink-0 bg-line" />
            <span className="inline-flex shrink-0 items-center px-2 text-xs font-semibold uppercase tracking-[0.06em] text-faint">{t("operatorSection")}</span>
            {ADMIN_NAV.map((n) => (
              <TabLink key={n.href} item={n} active={isActive(n, pathname)} />
            ))}
          </>
        )}
      </div>
    </nav>
  );
}

function ShellLoading() {
  const t = useTranslations("common.status");
  return (
    <div className="space-y-4" aria-busy aria-label={t("loading")}>
      <SkeletonBlock className="h-14 w-full rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <SkeletonBlock key={i} className="h-36 rounded-xl" />
        ))}
      </div>
      <SkeletonBlock className="h-72 w-full rounded-xl" />
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, loading, error, isOperator, tenantId } = useSession();
  const isAdminRoute = pathname.startsWith("/admin");
  const t = useTranslations("shell");

  let body: ReactNode;
  if (loading) {
    body = <ShellLoading />;
  } else if (error || !user) {
    body = <ErrorBox error={error ?? t("sessionError")} className="max-w-xl" />;
  } else if (isOperator && tenantId === null && !isAdminRoute) {
    body = (
      <EmptyState
        icon={<IconBuilding />}
        title={t("tenant.pickTitle")}
        className="mx-auto mt-10 max-w-lg border border-line bg-surface"
        action={
          <div className="flex flex-col items-center gap-3">
            <div className="w-64 text-left">
              <TenantSwitcher />
            </div>
            <Link href="/admin/tenants" className="text-base font-semibold text-brand hover:underline">
              {t("tenant.manage")}
            </Link>
          </div>
        }
      >
        {t("tenant.pickHint")}
      </EmptyState>
    );
  } else {
    body = children;
  }

  return (
    <div className="min-h-screen">
      <header>
        <TopBar />
        <TabBar />
      </header>
      <main className="mx-auto min-w-0 max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8 lg:py-6">{body}</main>
    </div>
  );
}
