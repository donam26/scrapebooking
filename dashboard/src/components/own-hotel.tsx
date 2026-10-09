"use client";

import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { hotelTitle } from "@/lib/hotels";
import { useApi } from "@/lib/hooks";
import { Segmented, cx } from "./ui";

/**
 * Nhiều khách sạn của bạn (roadmap 5.5): mỗi khách sạn một compset, một nhịp. Khách sạn đang xem nằm
 * trong URL (`?hotel=`); null = để server chọn khách sạn đầu tiên của tenant.
 */
export function useOwnHotelParam(): [number | null, (next: number) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("hotel");
  const value = raw && /^\d+$/.test(raw) ? Number(raw) : null;
  function set(next: number) {
    const q = new URLSearchParams(params.toString());
    q.set("hotel", String(next));
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
  }
  return [value, set];
}

export type OwnHotel = { id: number; name: string };

/** Khách sạn của bạn trong watchlist (vai trò "self", đang theo dõi). */
export function useOwnHotels(): OwnHotel[] {
  const q = useApi("watchlist:self", () => api.watchlist.list());
  return useMemo(
    () => (q.data ?? []).filter((w) => w.role === "self" && w.active).map((w) => ({ id: w.hotel.id, name: hotelTitle(w.hotel, w.label) })),
    [q.data],
  );
}

/** Chọn khách sạn của bạn đang xem; chỉ hiện khi tenant có từ hai khách sạn trở lên. */
export function OwnHotelSwitcher({ hotels, value, onChange, className }: { hotels: OwnHotel[]; value: number | null; onChange: (id: number) => void; className?: string }) {
  const t = useTranslations("components.ownHotel");
  if (hotels.length < 2) return null;
  const current = String(value ?? hotels[0].id);
  return (
    <div className={cx("sb-scroll max-w-full overflow-x-auto", className)}>
      <Segmented
        label={t("label")}
        value={current}
        onChange={(v) => onChange(Number(v))}
        items={hotels.map((h) => ({ value: String(h.id), label: h.name, title: t("title", { name: h.name }) }))}
      />
    </div>
  );
}
