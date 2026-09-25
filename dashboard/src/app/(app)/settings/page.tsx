"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useSession } from "@/lib/session";
import { Note, PageHeader, SkeletonBlock, Tabs } from "@/components/ui";
import { IconBuilding, IconClock, IconLock, IconUpload, IconUsers } from "@/components/icons";
import { WatchlistTab } from "./watchlist-tab";
import { ScheduleTab } from "./schedule-tab";
import { UsersTab } from "./users-tab";
import { PmsTab } from "./pms-tab";

type TabKey = "watchlist" | "schedule" | "users" | "pms";

const TABS: Array<{ key: TabKey; label: string; icon: React.ReactNode }> = [
  { key: "watchlist", label: "Khách sạn", icon: <IconBuilding size={16} /> },
  { key: "schedule", label: "Lịch quét", icon: <IconClock size={16} /> },
  { key: "users", label: "Người dùng", icon: <IconUsers size={16} /> },
  { key: "pms", label: "Nhập PMS", icon: <IconUpload size={16} /> },
];

function isTab(v: string | null): v is TabKey {
  return v === "watchlist" || v === "schedule" || v === "users" || v === "pms";
}

function SettingsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("tab");
  const tab: TabKey = isTab(raw) ? raw : "watchlist";
  const { canWrite } = useSession();

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
        title="Cài đặt"
        subtitle={canWrite ? "Khách sạn theo dõi, giờ quét, người dùng và dữ liệu công suất từ PMS" : "Xem khách sạn theo dõi, giờ quét, người dùng và dữ liệu PMS của tenant"}
      />
      {!canWrite && (
        <Note tone="info" icon={<IconLock size={16} />} className="mb-5">
          Tài khoản chỉ xem: bạn xem được mọi cài đặt nhưng không thay đổi được. Liên hệ quản trị viên khách sạn nếu cần sửa.
        </Note>
      )}
      <Tabs value={tab} onChange={setTab} items={TABS} />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "watchlist" && <WatchlistTab />}
        {tab === "schedule" && <ScheduleTab />}
        {tab === "users" && <UsersTab />}
        {tab === "pms" && <PmsTab />}
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
