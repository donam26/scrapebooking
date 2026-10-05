/**
 * Chỉ số thị trường cho các tab kiểu OTARadar (Bảng điều khiển, Phòng trống, Giá, Terminal+).
 * Chỉ tính từ dữ liệu đã quét trên một kênh: giá là giá niêm yết thấp nhất mỗi đêm,
 * công suất là ước tính từ số phòng còn (luôn ghi "≈" khi hiển thị).
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { CompsetDayOut, DateCell, HotelRow, OverviewOut, PaceNightOut } from "@/lib/api";
import { hotelTitle } from "@/lib/channels";
import { num, parseDate, useFmt, type Fmt } from "@/lib/format";

export type DemandLevel = "low" | "moderate" | "high";

/** Màu theo mẫu: xanh lá thấp, xanh dương vừa, cam cao. */
export const DEMAND_COLOR: Record<DemandLevel, string> = { low: "var(--sb-yours)", moderate: "var(--sb-brand)", high: "var(--sb-hot)" };
export const DEMAND_TEXT: Record<DemandLevel, string> = { low: "text-yours", moderate: "text-brand", high: "text-hot" };

/** Mức theo điểm 0–100: ≥60 cao, 40–59 vừa, dưới 40 thấp. */
export function demandLevel(score: number): DemandLevel {
  if (score >= 60) return "high";
  if (score >= 40) return "moderate";
  return "low";
}

/**
 * Chỉ số cầu một đêm (0–100): công suất ước tính của compset (`source: "occ"`, hiện kèm "≈");
 * khi chưa ước tính được thì dùng tỷ lệ đối thủ đã hết phòng (`source: "sold_out"`). null khi chưa có dữ liệu.
 */
export function demandScore(night: PaceNightOut | undefined, compset: CompsetDayOut | undefined): { score: number; source: "occ" | "sold_out" } | null {
  const occ = num(night?.comp_occ);
  if (occ !== null) return { score: Math.round(occ * 100), source: "occ" };
  if (compset && compset.competitors_observed > 0) return { score: Math.round((compset.competitors_sold_out / compset.competitors_observed) * 100), source: "sold_out" };
  return null;
}

/** Giá đặt được của một ô: bỏ ô hết phòng, không đọc được hoặc chưa quét (giá cũ không còn bán). */
export function bookablePrice(c: DateCell | undefined): number | null {
  if (!c || c.availability_status === null || c.availability_status === "sold_out" || c.availability_status === "unknown") return null;
  return num(c.min_price);
}

export function selfRow(o: OverviewOut): HotelRow | null {
  return o.hotels.find((h) => h.role === "self") ?? null;
}

export function competitorRows(o: OverviewOut): HotelRow[] {
  return o.hotels.filter((h) => h.role !== "self");
}

export function cellOn(row: HotelRow | null | undefined, date: string): DateCell | undefined {
  return row?.cells.find((c) => c.stay_date === date);
}

export function rowName(row: HotelRow): string {
  return hotelTitle(row.hotel, row.label);
}

/** Một khách sạn còn rất ít phòng (≤3, kênh báo chính xác) hoặc đã hết. */
export function isTight(c: DateCell | undefined): boolean {
  if (!c) return false;
  return c.availability_status === "sold_out" || (c.exact_rooms_left !== null && c.exact_rooms_left <= 3);
}

function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

export type MarketSnapshot = {
  competitors: number;
  observed: number;
  soldOut: number;
  low: number;
  /** Tổng số phòng còn của đối thủ có số chính xác. */
  roomsLeft: number;
  /** Số đối thủ góp vào `roomsLeft`. */
  roomsKnown: number;
  avgRate: number | null;
  minRate: { value: number; name: string } | null;
  maxRate: { value: number; name: string } | null;
  currency: string | null;
  /** % đối thủ hết phòng hoặc còn ≤3 phòng (mức nén), null khi chưa quan sát được. */
  compression: number | null;
};

/** Toàn cảnh compset của một đêm (mặc định đêm đầu kỳ). */
export function marketSnapshot(o: OverviewOut, date: string = o.start): MarketSnapshot {
  const comps = competitorRows(o);
  let observed = 0;
  let soldOut = 0;
  let low = 0;
  let roomsLeft = 0;
  let roomsKnown = 0;
  let currency: string | null = null;
  const prices: Array<{ value: number; name: string }> = [];
  for (const r of comps) {
    const c = cellOn(r, date);
    if (!c || c.availability_status === null || c.availability_status === "unknown") continue;
    observed += 1;
    if (c.availability_status === "sold_out") soldOut += 1;
    else if (c.exact_rooms_left !== null && c.exact_rooms_left <= 3) low += 1;
    if (c.exact_rooms_left !== null) {
      roomsLeft += c.exact_rooms_left;
      roomsKnown += 1;
    }
    const p = bookablePrice(c);
    if (p !== null) {
      prices.push({ value: p, name: rowName(r) });
      currency = currency ?? c.currency;
    }
  }
  const sorted = [...prices].sort((a, b) => a.value - b.value);
  return {
    competitors: comps.length,
    observed,
    soldOut,
    low,
    roomsLeft,
    roomsKnown,
    avgRate: mean(prices.map((p) => p.value)),
    minRate: sorted[0] ?? null,
    maxRate: sorted[sorted.length - 1] ?? null,
    currency,
    compression: observed ? Math.round(((soldOut + low) / observed) * 100) : null,
  };
}

/** Giá trung bình đối thủ của một đêm (giá thấp nhất mỗi khách sạn). */
export function avgCompRate(o: OverviewOut, date: string): number | null {
  return mean(
    competitorRows(o)
      .map((r) => bookablePrice(cellOn(r, date)))
      .filter((v): v is number => v !== null),
  );
}

/** Bảng màu đường cho từng khách sạn (khách sạn của bạn luôn xanh OTARadar, thị trường nét đứt đen). */
export const HOTEL_LINE_COLORS = ["#8b5cf6", "#ec4899", "#22c55e", "#f59e0b", "#ef4444", "#14b8a6", "#f97316", "#6366f1", "#84cc16", "#06b6d4"] as const;
export const OWN_LINE_COLOR = "#0062ff";

/** Màu cố định của từng khách sạn (khách sạn của bạn xanh, đối thủ theo thứ tự watchlist), dùng chung mọi biểu đồ. */
export function hotelColors(o: OverviewOut): Map<number, string> {
  const out = new Map<number, string>();
  let ci = 0;
  for (const h of [...o.hotels].sort((a, b) => (a.role === "self" ? -1 : b.role === "self" ? 1 : 0))) {
    out.set(h.hotel.id, h.role === "self" ? OWN_LINE_COLOR : HOTEL_LINE_COLORS[ci++ % HOTEL_LINE_COLORS.length]);
  }
  return out;
}
export const MARKET_LINE_COLOR = "#111827";

/** Khoảng cách đường chim bay (km) giữa hai toạ độ; null khi thiếu toạ độ. */
export function distanceKm(a: { lat?: number | null; lng?: number | null }, b: { lat?: number | null; lng?: number | null }): number | null {
  if (a.lat == null || a.lng == null || b.lat == null || b.lng == null) return null;
  const rad = (x: number) => (x * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

export type MarketMetricsTranslator = ReturnType<typeof useTranslations<"helpers.marketMetrics">>;

/**
 * Phần sinh chữ của chỉ số thị trường. Component: `const { demandLabel, ratePosition, dayHead } = useMarketMetrics();`
 * Ngoài React: `createMarketMetrics(t, fmt)` với `t = await getTranslations("helpers.marketMetrics")`.
 */
export function createMarketMetrics(t: MarketMetricsTranslator, fmt: Fmt) {
  /** Nhãn mức cầu: Thấp / Vừa / Cao. */
  function demandLabel(level: DemandLevel): string {
    return t(`demand.${level}`);
  }

  /** Vị trí giá của bạn so với giá TB đối thủ: "Dưới thị trường" / "Trên thị trường" / "Ngang thị trường". */
  function ratePosition(own: number | null, market: number | null): { text: string; tone: "good" | "warn" | "neutral" } | null {
    if (own === null || market === null || market === 0) return null;
    const d = (own - market) / market;
    if (Math.abs(d) < 0.02) return { text: t("position.level"), tone: "neutral" };
    return d < 0 ? { text: t("position.below"), tone: "good" } : { text: t("position.above"), tone: "warn" };
  }

  /** Đầu cột ngày: "T6" + "02/10"; cuối tuần của khách sạn (T6, T7, CN) tô đỏ như mẫu. */
  function dayHead(iso: string, today?: string): { wd: string; date: string; weekend: boolean; isToday: boolean } {
    const dow = parseDate(iso).getDay();
    return { wd: fmt.fmtWeekday(iso), date: fmt.fmtDateShort(iso), weekend: dow === 5 || dow === 6 || dow === 0, isToday: iso === today };
  }

  return { demandLabel, ratePosition, dayHead };
}

export type MarketMetricsText = ReturnType<typeof createMarketMetrics>;

export function useMarketMetrics(): MarketMetricsText {
  const t = useTranslations("helpers.marketMetrics");
  const fmt = useFmt();
  return useMemo(() => createMarketMetrics(t, fmt), [t, fmt]);
}
