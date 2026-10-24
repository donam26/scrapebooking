"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { api, type ScanRunOut, type TenantOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useLabel } from "@/lib/labels";
import { useFmt } from "@/lib/format";
import { isMarketRun, runCollected, runFinished, successPct, useDataFreshness, type FreshnessState } from "@/lib/freshness";
import { EmptyState, ErrorBox, Select, SkeletonBlock, cx } from "./ui";
import { LocaleSwitcher } from "./locale-switcher";
import { HEAT_LEVELS } from "./marks";
import { PopoverMenu } from "./popover-menu";
import { BrandMark, IconBell, IconBrief, IconBuilding, IconCalendar, IconLogout, IconPin, IconSliders, IconSunrise, IconUser } from "./icons";

/**
 * Khung OTARadar: thanh trên xanh (logo, khách sạn/tenant, độ mới dữ liệu, chuông, cài đặt, tài
 * khoản), năm tab theo công việc (hàng tab trên máy tính, thanh đáy trên điện thoại).
 */

/** `key`: khoá trong shell.nav (messages/<ngôn ngữ>/shell.json). */
type NavItem = { href: string; key: NavKey; icon?: ReactNode; match?: (p: string) => boolean };
type NavKey = "today" | "calendar" | "competitors" | "market" | "reports" | "tenants" | "users" | "health";

const TENANT_NAV: NavItem[] = [
  { href: "/today", key: "today", icon: <IconSunrise size={22} />, match: (p) => p.startsWith("/today") || p.startsWith("/dashboard") },
  {
    href: "/calendar",
    key: "calendar",
    icon: <IconCalendar size={22} />,
    match: (p) => ["/calendar", "/availability", "/rates", "/overview"].some((x) => p.startsWith(x)),
  },
  { href: "/competitors", key: "competitors", icon: <IconBuilding size={22} />, match: (p) => p.startsWith("/competitors") || p.startsWith("/hotels") },
  { href: "/market", key: "market", icon: <IconPin size={22} />, match: (p) => p.startsWith("/market") || p.startsWith("/terminal") },
  {
    href: "/insights",
    key: "reports",
    icon: <IconBrief size={22} />,
    match: (p) => ["/insights", "/events", "/reports", "/pace"].some((x) => p.startsWith(x)),
  },
];

const ADMIN_NAV: NavItem[] = [
  { href: "/admin/tenants", key: "tenants" },
  { href: "/admin/users", key: "users" },
  { href: "/admin/health", key: "health" },
];

/** Trang chi tiết (và chi tiết đêm) của chính khách sạn bạn: thuộc tab Lịch giá & phòng, không phải Đối thủ. */
function isOwnHotelPath(pathname: string, ownIds: number[]): boolean {
  const m = /^\/hotels\/(\d+)/.exec(pathname);
  return !!m && ownIds.includes(Number(m[1]));
}

function isActive(item: NavItem, pathname: string, ownIds: number[] = []): boolean {
  if (isOwnHotelPath(pathname, ownIds)) return item.key === "calendar";
  if (item.match) return item.match(pathname);
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

/** Id các khách sạn của bạn (để tô đúng tab khi xem trang của chính mình). */
function useOwnIds(): number[] {
  const { tenantId } = useSession();
  const wl = useApi(tenantId === null ? null : "shell:own", () => api.watchlist.list());
  return (wl.data ?? []).filter((w) => w.role === "self").map((w) => w.hotel.id);
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
      className="inline-flex h-9 max-w-[min(280px,30vw)] items-center gap-2 rounded-lg border border-white/25 bg-white/[0.12] px-3 text-base font-medium text-white max-md:hidden"
    >
      <IconBuilding size={16} className="shrink-0 opacity-80" />
      <span className="truncate">{name}</span>
    </span>
  );
}

const DOT_TONE: Record<FreshnessState["tone"], string> = { ok: "bg-[#4ade80]", warn: "bg-[#fbbf24]", bad: "bg-[#ff4d4f]" };

type DayState = "ok" | "empty" | "none";

/** Ngày địa phương dạng "2026-10-24" (không qua UTC, tránh lùi một ngày ở múi giờ dương). */
function localIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** 7 ngày gần nhất (cũ → mới): có lượt thu được dữ liệu / có lượt nhưng rỗng / không có lượt nào. */
function lastSevenDays(runs: ScanRunOut[], now = new Date()): Array<{ day: Date; state: DayState }> {
  const days: Array<{ day: Date; state: DayState }> = [];
  for (let i = 6; i >= 0; i--) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    const next = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1);
    const inDay = runs.filter((r) => {
      if (isMarketRun(r) || !runFinished(r) || !r.finished_at) return false;
      const at = new Date(r.finished_at);
      return at >= day && at < next;
    });
    days.push({ day, state: inDay.some(runCollected) ? "ok" : inDay.length ? "empty" : "none" });
  }
  return days;
}

/**
 * Độ mới dữ liệu ngay trên thanh trên ("● Cập nhật 18:36 hôm nay" / "● Dữ liệu dừng · 8 ngày
 * trước"); bấm mở bảng "Tình trạng dữ liệu": câu trạng thái, lượt kế tiếp, tỷ lệ đọc thành công,
 * 7 ngày qua, cách đọc số và màu.
 */
function DataPill({ settings }: { settings: TenantOut | undefined }) {
  const t = useTranslations("shell.freshness");
  const label = useLabel();
  const { fmtAgo, fmtWhen, nextScanLabel, fmtWeekday } = useFmt();
  const f = useDataFreshness(settings?.scan_times);
  const [now] = useState(() => new Date());
  if (!f.loaded) return <span className="h-9 w-24 rounded-full bg-white/10 max-sm:w-9" aria-hidden />;
  const next = settings ? nextScanLabel(settings.scan_times, settings.timezone) : null;
  const pct = f.status ? successPct(f.status) : null;
  const short = !f.updatedAt ? t("noScan") : f.stale ? t("pillStale", { ago: fmtAgo(f.updatedAt) }) : f.tone === "warn" ? t("pillWarn", { when: fmtWhen(f.updatedAt) }) : t("pillOk", { when: fmtWhen(f.updatedAt) });
  const sentence = !f.updatedAt
    ? t("statusNever")
    : f.stale
      ? t("statusStale", { when: fmtWhen(f.updatedAt), ago: fmtAgo(f.updatedAt) })
      : f.latestEmpty
        ? t("statusLatestEmpty", { when: fmtWhen(f.updatedAt) })
        : f.overdue
          ? t("statusOverdue", { ago: fmtAgo(f.updatedAt) })
          : t("statusOk", { when: fmtWhen(f.updatedAt) });
  return (
    <PopoverMenu
      label={t("panelTitle")}
      width={360}
      buttonClassName="inline-flex h-9 items-center gap-2 rounded-full bg-white/[0.14] px-3 text-sm font-medium text-white transition-colors hover:bg-white/[0.24] focus-visible:outline-white max-sm:px-2.5"
      button={
        <>
          <span aria-hidden className={cx("h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-white/30", DOT_TONE[f.tone])} />
          <span className="max-w-[220px] truncate max-sm:hidden">{short}</span>
          {f.running && <span className="text-white/80 max-md:hidden">· {t("scanning")}</span>}
        </>
      }
    >
      {(close) => (
        <div className="divide-y divide-line">
          <div className="px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.06em] text-muted">{t("panelTitle")}</div>
            <p className={cx("mt-1.5 text-sm leading-relaxed", f.tone === "bad" ? "font-semibold text-danger" : f.tone === "warn" ? "font-semibold text-warning-deep" : "text-ink")}>{sentence}</p>
            <dl className="mt-2 space-y-1 text-sm">
              {next && (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{t("nextScan")}</dt>
                  <dd className="font-semibold text-ink tabular">{next}</dd>
                </div>
              )}
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{t("success7d")}</dt>
                <dd className="font-semibold text-ink tabular">{pct === null ? "—" : `${pct}%`}</dd>
              </div>
            </dl>
            <div className="mt-3">
              <div className="text-xs text-muted">{t("last7Days")}</div>
              <ol className="mt-1 grid grid-cols-7 gap-1">
                {lastSevenDays(f.runs, now).map(({ day, state }) => (
                  <li key={localIso(day)} className="text-center">
                    <span
                      className={cx("block h-2.5 rounded-sm", state === "ok" ? "bg-yours" : state === "empty" ? "bg-danger" : "bg-line-strong")}
                      title={t(`day.${state}`)}
                    />
                    <span className="mt-0.5 block text-[11px] text-muted">{fmtWeekday(localIso(day))}</span>
                  </li>
                ))}
              </ol>
              <p className="mt-1 text-xs text-muted">{t("last7DaysLegend")}</p>
            </div>
            <Link href="/runs" onClick={close} className="mt-3 inline-block text-sm font-semibold text-brand hover:underline">
              {t("viewRuns")}
            </Link>
          </div>
          <div className="px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.06em] text-muted">{t("howToRead")}</div>
            <ul className="mt-1.5 space-y-1 text-sm text-body">
              <li>{t("readExact")}</li>
              <li>{t("readFloor")}</li>
              <li>{t("readRange")}</li>
              <li>{t("readEstimate")}</li>
            </ul>
            <ul className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
              {HEAT_LEVELS.map((h) => (
                <li key={h.cls} className="flex items-center gap-2">
                  <span aria-hidden className={cx("h-3 w-3 rounded-[3px]", h.cls)} />
                  {label("heatLevel", h.key)}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </PopoverMenu>
  );
}

/** Chuông: 8 thay đổi mới nhất (hết phòng, có lại, đổi giá…), chấm đỏ nếu có trong 24 giờ. */
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
  const { user, logout, isOperator } = useSession();
  const t = useTranslations("shell");
  const label = useLabel();
  if (!user) return null;
  return (
    <PopoverMenu
      label={t("user.title")}
      width={280}
      buttonClassName="grid h-9 w-9 place-items-center rounded-full bg-white/[0.18] text-white transition-colors hover:bg-white/[0.28] focus-visible:outline-white"
      button={<IconUser size={19} />}
    >
      {(close) => (
        <div>
          <div className="border-b border-line px-4 py-3">
            <div className="truncate text-base font-semibold text-ink" title={user.email}>
              {user.email}
            </div>
            <div className="text-sm text-muted">{label("userRole", user.role)}</div>
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <span className="text-sm text-muted">{t("user.language")}</span>
            <LocaleSwitcher />
          </div>
          {isOperator && (
            <ul className="border-b border-line py-1.5 md:hidden">
              {ADMIN_NAV.map((n) => (
                <li key={n.href}>
                  <Link href={n.href} onClick={close} className="block px-4 py-2 text-base text-body hover:bg-subtle hover:text-brand">
                    {t(`nav.${n.key}`)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={() => void logout()}
            className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-base font-medium text-body hover:bg-subtle hover:text-danger"
          >
            <IconLogout size={17} /> {t("user.logout")}
          </button>
        </div>
      )}
    </PopoverMenu>
  );
}

function TopBar() {
  const { user, isOperator, tenantId } = useSession();
  const pathname = usePathname();
  const settings = useApi(tenantId === null ? null : "settings", () => api.settings.get());
  const t = useTranslations("shell");
  const onSettings = pathname.startsWith("/settings");
  return (
    <div className="bg-night text-white">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-2 px-4 sm:gap-3 sm:px-6 lg:px-8">
        <Link href="/today" className="flex shrink-0 items-center gap-2.5 rounded-md focus-visible:outline-white" aria-label={t("homeLink")}>
          <BrandMark size={30} onBlue />
          <span className="text-[19px] font-semibold tracking-[-0.01em] max-sm:hidden">OTARadar</span>
        </Link>
        <div className="flex-1" />
        {user && (isOperator ? <TenantSwitcher onBlue className="max-md:max-w-[38vw]" /> : <HotelPill name={settings.data?.name} />)}
        {user && (
          <div className="flex items-center gap-1 sm:gap-2">
            {tenantId !== null && <DataPill settings={settings.data} />}
            {tenantId !== null && <BellMenu />}
            {tenantId !== null && (
              <Link
                href="/settings"
                aria-label={t("nav.settings")}
                title={t("nav.settings")}
                aria-current={onSettings ? "page" : undefined}
                className={cx(TOPBAR_BUTTON, onSettings && "bg-white/20 text-white")}
              >
                <IconSliders size={20} />
              </Link>
            )}
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

/** Hàng tab trên máy tính và máy tính bảng (≥768px). */
function TabBar() {
  const pathname = usePathname();
  const { isOperator } = useSession();
  const ownIds = useOwnIds();
  const t = useTranslations("shell");
  return (
    <nav aria-label={t("mainNav")} className="border-b border-line bg-surface max-md:hidden">
      <div className="sb-scroll mx-auto flex max-w-[1600px] items-stretch overflow-x-auto px-2 sm:px-4 lg:px-6">
        {TENANT_NAV.map((n) => (
          <TabLink key={n.href} item={n} active={isActive(n, pathname, ownIds)} />
        ))}
        {isOperator && (
          <>
            <span aria-hidden className="mx-2 my-3 w-px shrink-0 bg-line" />
            <span className="inline-flex shrink-0 items-center px-2 text-xs font-semibold uppercase tracking-[0.06em] text-muted">{t("operatorSection")}</span>
            {ADMIN_NAV.map((n) => (
              <TabLink key={n.href} item={n} active={isActive(n, pathname)} />
            ))}
          </>
        )}
      </div>
    </nav>
  );
}

/** Thanh đáy trên điện thoại (<768px): năm mục, biểu tượng + nhãn ngắn. */
function BottomNav() {
  const pathname = usePathname();
  const ownIds = useOwnIds();
  const t = useTranslations("shell");
  return (
    <nav aria-label={t("mainNav")} className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
      <ul className="grid grid-cols-5">
        {TENANT_NAV.map((n) => {
          const active = isActive(n, pathname, ownIds);
          return (
            <li key={n.href}>
              <Link
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cx("flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold", active ? "text-brand" : "text-muted hover:text-ink")}
              >
                {n.icon}
                <span className="max-w-full truncate px-0.5">{t(`navShort.${n.key}`)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
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
      <main className="mx-auto min-w-0 max-w-[1600px] px-4 py-5 max-md:pb-24 sm:px-6 lg:px-8 lg:py-6">{body}</main>
      {user && <BottomNav />}
    </div>
  );
}
