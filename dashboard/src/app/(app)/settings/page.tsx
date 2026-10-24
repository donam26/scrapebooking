"use client";

import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { useSession } from "@/lib/session";
import { Note, PageHeader, SkeletonBlock, Tabs } from "@/components/ui";
import { IconBell, IconBuilding, IconLock, IconSliders, IconTrend, IconUpload, IconUsers } from "@/components/icons";
import { WatchlistTab } from "./watchlist-tab";
import { UsersTab } from "./users-tab";
import { PmsTab } from "./pms-tab";
import { NotificationsTab } from "./notifications-tab";
import { StrategyTab } from "./strategy-tab";
import { AdvancedTab, type AdvancedSection } from "./advanced-tab";

/**
 * Cài đặt (UX Phase 3, C3): sáu tab theo việc của khách sạn. "Nâng cao" gom Lịch quét, Khu vực thị
 * trường và Sự kiện địa phương. URL cũ `?tab=schedule|market|events` mở "Nâng cao" và cuộn tới mục đó.
 */
type TabKey = "watchlist" | "notifications" | "users" | "pms" | "strategy" | "advanced";

const TABS: Array<{ key: TabKey; icon: React.ReactNode }> = [
  { key: "watchlist", icon: <IconBuilding size={16} /> },
  { key: "notifications", icon: <IconBell size={16} /> },
  { key: "users", icon: <IconUsers size={16} /> },
  { key: "pms", icon: <IconUpload size={16} /> },
  { key: "strategy", icon: <IconTrend size={16} /> },
  { key: "advanced", icon: <IconSliders size={16} /> },
];

/** `?tab=` cũ → mục trong "Nâng cao". */
const SECTION_ALIASES: readonly AdvancedSection[] = ["schedule", "market", "events"];

function resolve(raw: string | null): { tab: TabKey; section: AdvancedSection | null } {
  if (raw && (SECTION_ALIASES as readonly string[]).includes(raw)) return { tab: "advanced", section: raw as AdvancedSection };
  const tab = TABS.find((it) => it.key === raw)?.key ?? "watchlist";
  return { tab, section: null };
}

function SettingsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { tab, section } = resolve(params.get("tab"));
  const { canWrite } = useSession();
  const t = useTranslations("settings.page");

  // Link cũ tới một mục của "Nâng cao": cuộn tới mục đó sau khi tab hiện ra.
  useEffect(() => {
    if (!section) return;
    const id = window.setTimeout(() => document.getElementById(`settings-${section}`)?.scrollIntoView({ block: "start" }), 50);
    return () => window.clearTimeout(id);
  }, [section]);

  function setTab(next: TabKey) {
    const q = new URLSearchParams(params.toString());
    if (next === "watchlist") q.delete("tab");
    else q.set("tab", next);
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  return (
    <div className="max-w-[1100px]">
      <PageHeader title={t("title")} subtitle={canWrite ? t("subtitleWrite") : t("subtitleRead")} />
      {!canWrite && (
        <Note tone="info" icon={<IconLock size={16} />} className="mb-5">
          {t("readOnlyNote")}
        </Note>
      )}
      <Tabs value={tab} onChange={setTab} items={TABS.map((it) => ({ ...it, label: t(`tabs.${it.key}`) }))} />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "watchlist" && <WatchlistTab />}
        {tab === "notifications" && <NotificationsTab />}
        {tab === "users" && <UsersTab />}
        {tab === "pms" && <PmsTab />}
        {tab === "strategy" && <StrategyTab />}
        {tab === "advanced" && <AdvancedTab />}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-64 w-full max-w-[1100px] rounded-xl" />}>
      <SettingsView />
    </Suspense>
  );
}
