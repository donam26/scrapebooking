"use client";

import { useState } from "react";
import { useSession } from "@/lib/session";
import { PageHeader, Tabs } from "@/components/ui";
import { WatchlistTab } from "./watchlist-tab";
import { ScheduleTab } from "./schedule-tab";
import { UsersTab } from "./users-tab";
import { PmsTab } from "./pms-tab";

type TabKey = "watchlist" | "schedule" | "users" | "pms";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "watchlist", label: "Watchlist" },
  { key: "schedule", label: "Lịch quét" },
  { key: "users", label: "Người dùng" },
  { key: "pms", label: "Nhập PMS" },
];

export default function SettingsPage() {
  const [tab, setTab] = useState<TabKey>("watchlist");
  const { canWrite } = useSession();
  return (
    <>
      <PageHeader title="Cài đặt" subtitle={canWrite ? "Watchlist, lịch quét, người dùng và nhập dữ liệu PMS" : "Tài khoản chỉ xem: không thể thay đổi cài đặt"} />
      <Tabs value={tab} onChange={setTab} items={TABS} />
      {tab === "watchlist" && <WatchlistTab />}
      {tab === "schedule" && <ScheduleTab />}
      {tab === "users" && <UsersTab />}
      {tab === "pms" && <PmsTab />}
    </>
  );
}
