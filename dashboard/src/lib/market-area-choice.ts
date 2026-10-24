"use client";

import { useCallback, useSyncExternalStore } from "react";
import { api, type MarketAreaOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

/**
 * Khu vực thị trường đang xem ở Terminal+ (thẻ khu vực + dải 14 đêm) và Đối thủ › Khám phá thị
 * trường; tenant có tới 3 khu vực. Lựa chọn lưu theo trình duyệt (localStorage, theo tenant) và dùng
 * chung giữa các màn, các tab. Id đã lưu không còn (đã xoá hoặc tạm dừng) thì về khu vực đang hoạt
 * động đầu tiên, đúng khu vực backend chọn khi không truyền `area_id`.
 */

const KEY = "sb.market_area_id";
/** Lựa chọn trong phiên: dùng khi localStorage bị chặn hoặc ghi lỗi. */
const memory = new Map<string, number>();
const listeners = new Set<() => void>();

function storageKey(tenantId: number | null): string {
  return `${KEY}.${tenantId ?? "me"}`;
}

function readStored(key: string): number | null {
  const mem = memory.get(key);
  if (mem !== undefined) return mem;
  try {
    const raw = window.localStorage.getItem(key);
    const n = raw === null ? NaN : Number(raw);
    return Number.isInteger(n) ? n : null;
  } catch {
    return null;
  }
}

function store(key: string, id: number): void {
  memory.set(key, id);
  try {
    window.localStorage.setItem(key, String(id));
  } catch {
    // localStorage bị chặn: chỉ giữ trong phiên.
  }
  for (const notify of listeners) notify();
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  // Tab khác đổi khu vực: bỏ bản trong phiên để đọc lại localStorage.
  const onStorage = (e: StorageEvent) => {
    if (e.key !== null && !e.key.startsWith(KEY)) return;
    if (e.key === null) memory.clear();
    else memory.delete(e.key);
    notify();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener("storage", onStorage);
  };
}

export type MarketAreaChoice = {
  /** Mọi khu vực của tenant; undefined khi đang tải. */
  areas: MarketAreaOut[] | undefined;
  /** Khu vực đang hoạt động (thứ tự id); từ 2 khu vực thì hiện ô chọn. */
  active: MarketAreaOut[];
  /** Khu vực đang chọn; undefined khi không có khu vực hoạt động (để backend tự chọn). */
  area: MarketAreaOut | undefined;
  areaId: number | undefined;
  select: (id: number) => void;
  /** Đã tải xong (hoặc lỗi) danh sách khu vực: từ đây mới gọi API theo `areaId`. */
  ready: boolean;
};

export function useMarketAreaChoice(): MarketAreaChoice {
  const { tenantId } = useSession();
  const key = storageKey(tenantId);
  const areas = useApi("market:areas", () => api.market.areas.list());
  const saved = useSyncExternalStore(subscribe, () => readStored(key), () => null);
  const active = (areas.data ?? []).filter((a) => a.active);
  const area = active.find((a) => a.id === saved) ?? active[0];
  const select = useCallback((id: number) => store(key, id), [key]);
  return { areas: areas.data, active, area, areaId: area?.id, select, ready: areas.data !== undefined || areas.error !== undefined };
}
