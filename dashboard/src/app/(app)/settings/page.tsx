"use client";

import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useSession } from "@/lib/session";
import { Note, PageHeader, SkeletonBlock, Tabs } from "@/components/ui";
import { IconBell, IconBuilding, IconCalendar, IconClock, IconLock, IconPin, IconTrend, IconUpload, IconUsers } from "@/components/icons";
import { WatchlistTab } from "./watchlist-tab";
import { ScheduleTab } from "./schedule-tab";
import { EventsTab } from "./events-tab";
import { MarketTab } from "./market-tab";
import { UsersTab } from "./users-tab";
import { PmsTab } from "./pms-tab";
import { NotificationsTab } from "./notifications-tab";
import { StrategyTab } from "./strategy-tab";

type TabKey = "watchlist" | "market" | "schedule" | "events" | "notifications" | "users" | "pms" | "strategy";

const TABS: Array<{ key: TabKey; icon: React.ReactNode }> = [
  { key: "watchlist", icon: <IconBuilding size={16} /> },
  { key: "market", icon: <IconPin size={16} /> },
  { key: "schedule", icon: <IconClock size={16} /> },
  { key: "events", icon: <IconCalendar size={16} /> },
  { key: "notifications", icon: <IconBell size={16} /> },
  { key: "users", icon: <IconUsers size={16} /> },
  { key: "pms", icon: <IconUpload size={16} /> },
  { key: "strategy", icon: <IconTrend size={16} /> },
];

function isTab(v: string | null): v is TabKey {
  return TABS.some((it) => it.key === v);
}

function SettingsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("tab");
  const tab: TabKey = isTab(raw) ? raw : "watchlist";
  const { canWrite } = useSession();
  const t = useTranslations("settings.page");

  function setTab(next: TabKey) {
    const q = new URLSearchParams(params.toString());
    if (next === "watchlist") q.delete("tab");
    else q.set("tab", next);
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  return (
    <div className="max-w-[1100px]">
      <PageHeader
        title={t("title")}
        subtitle={canWrite ? t("subtitleWrite") : t("subtitleRead")}
      />
      {!canWrite && (
        <Note tone="info" icon={<IconLock size={16} />} className="mb-5">
          {t("readOnlyNote")}
        </Note>
      )}
      <Tabs value={tab} onChange={setTab} items={TABS.map((it) => ({ ...it, label: t(`tabs.${it.key}`) }))} />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "watchlist" && <WatchlistTab />}
        {tab === "market" && <MarketTab />}
        {tab === "schedule" && <ScheduleTab />}
        {tab === "events" && <EventsTab />}
        {tab === "notifications" && <NotificationsTab />}
        {tab === "users" && <UsersTab />}
        {tab === "pms" && <PmsTab />}
        {tab === "strategy" && <StrategyTab />}
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
