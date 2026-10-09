/**
 * Chỉ số compset cho các tab Bảng điều khiển, Phòng trống, Giá, Terminal+, Hôm nay.
 * Chỉ tính từ dữ liệu đã quét trên Booking.com: giá là giá niêm yết thấp nhất mỗi đêm (không phải
 * ADR), chỉ báo lấp đầy là ước tính từ số phòng còn (không phải công suất; luôn ghi "≈").
 *
 * Một khái niệm, một cách tính (mọi màn dùng chung các hằng số và hàm dưới đây):
 * - Giá đối thủ của một đêm = TRUNG VỊ giá niêm yết thấp nhất của các đối thủ còn bán.
 * - Một thang mức cầu cho chỉ báo lấp đầy ≈ (0–100): cao ≥ 75, vừa ≥ 50, còn lại thấp.
 * - Đêm căng: ≥ 50% đối thủ quan sát được đã hết hoặc còn ≤ 3 phòng (cần ≥ 2 đối thủ), hoặc chỉ
 *   báo lấp đầy ≥ 85% (cùng ngưỡng với luật gợi ý giá ở backend `market/price_suggest.py`).
 * - Dưới 4 đối thủ quan sát được: chỉ hiện x/N kèm "mẫu nhỏ", không tính % hay mức.
 * - Đêm cuối tuần của khách sạn = đêm thứ Sáu và thứ Bảy.
 * - Năm trạng thái ô (roadmap 2.7): chỉ `sold_out` là hết phòng; `restricted` (min-stay, đóng ngày
 *   đến) đếm riêng; ô cũ hơn 48 giờ (`stale`) không vào trung vị hay tỷ lệ.
 * - Chỉ báo lấp đầy của một đêm bị ẩn khi nhóm lead time của đêm đó đã hiệu chỉnh với PMS mà sai số
 *   quá ngưỡng (`by_lead[].usable = false`).
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { cellState, type CalibrationOut, type CompsetDayOut, type DateCell, type HotelRow, type LeadCalibrationOut, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { hotelTitle } from "@/lib/hotels";
import { isWeekend, num, useFmt, type Fmt } from "@/lib/format";

export type DemandLevel = "low" | "moderate" | "high";

/** Thang mức cầu duy nhất (điểm 0–100 của chỉ báo lấp đầy ≈): từ `high` là cao, từ `moderate` là vừa. */
export const DEMAND_THRESHOLDS = { high: 75, moderate: 50 } as const;

/** Số đối thủ quan sát được tối thiểu để tính %/mức (ít hơn: chỉ hiện x/N, "mẫu nhỏ"). */
export const MIN_SAMPLE = 4;

/** Đêm căng: tỷ lệ đối thủ hết/sắp hết, hoặc chỉ báo lấp đầy (0..1), từ ngưỡng này trở lên. */
export const TIGHT_SHARE = 0.5;
export const TIGHT_FILL = 0.85;

/** "Sắp hết": Booking.com báo chính xác còn chừng này phòng trở xuống. */
export const LOW_ROOMS = 3;

/** Màu theo mức: xanh lá thấp, xanh dương vừa, cam cao. */
export const DEMAND_COLOR: Record<DemandLevel, string> = { low: "var(--sb-yours)", moderate: "var(--sb-brand)", high: "var(--sb-hot)" };
export const DEMAND_TEXT: Record<DemandLevel, string> = { low: "text-yours", moderate: "text-brand", high: "text-hot" };
export const DEMAND_SOFT: Record<DemandLevel, string> = { low: "bg-yours-soft text-yours-deep", moderate: "bg-brand-soft text-brand", high: "bg-hot-soft text-hot" };

/** Mức theo điểm 0–100 (thang chung `DEMAND_THRESHOLDS`). */
export function demandLevel(pct: number): DemandLevel {
  if (pct >= DEMAND_THRESHOLDS.high) return "high";
  if (pct >= DEMAND_THRESHOLDS.moderate) return "moderate";
  return "low";
}

/** Nhóm lead time của hiệu chỉnh (khớp backend `LEAD_BUCKETS`). */
export type LeadBucket = "0-7" | "8-30" | "31-90";

export function leadBucket(daysToArrival: number | null | undefined): LeadBucket | null {
  if (daysToArrival === null || daysToArrival === undefined || daysToArrival < 0) return null;
  if (daysToArrival <= 7) return "0-7";
  if (daysToArrival <= 30) return "8-30";
  if (daysToArrival <= 90) return "31-90";
  return null;
}

/** Hiệu chỉnh của nhóm lead time chứa đêm này (null khi chưa có). */
export function leadCalibration(calibration: CalibrationOut | null | undefined, daysToArrival: number | null | undefined): LeadCalibrationOut | null {
  const b = leadBucket(daysToArrival);
  return (b && calibration?.by_lead?.find((x) => x.bucket === b)) || null;
}

/**
 * Nhóm lead time đã so với PMS (có đêm) mà sai số quá ngưỡng: ẩn chỉ báo của đêm. Chưa hiệu chỉnh
 * (chưa có PMS, hoặc nhóm chưa có đêm nào để so) thì vẫn hiện, kèm chữ "chưa hiệu chỉnh".
 */
export function fillHidden(calibration: CalibrationOut | null | undefined, daysToArrival: number | null | undefined): boolean {
  const lc = leadCalibration(calibration, daysToArrival);
  return !!lc && lc.nights > 0 && !lc.usable;
}

/**
 * Chỉ báo lấp đầy ≈ của compset một đêm (0..1, từ API nhịp); null khi chưa ước tính được
 * hoặc bị ẩn vì sai số nhóm lead time quá lớn (khi truyền `calibration`).
 */
export function fillIndicator(night: PaceNightOut | undefined, calibration?: CalibrationOut | null): number | null {
  if (!night || fillHidden(calibration, night.days_to_arrival)) return null;
  return num(night.comp_occ);
}

/** Chỉ báo lấp đầy một đêm kèm khoảng [thấp, cao] và lý do ẩn. */
export type FillReading = {
  /** 0..1; null khi chưa ước tính được hoặc bị ẩn. */
  value: number | null;
  low: number | null;
  high: number | null;
  /** Ẩn vì sai số so PMS ở nhóm lead time này quá ngưỡng. */
  hidden: boolean;
  /** Hiệu chỉnh của nhóm lead time chứa đêm. */
  lead: LeadCalibrationOut | null;
  /** Số đối thủ góp vào chỉ báo. */
  hotels: number;
};

export function fillReading(night: PaceNightOut | undefined, calibration: CalibrationOut | null | undefined): FillReading {
  const lead = leadCalibration(calibration, night?.days_to_arrival);
  const hidden = !!night && night.comp_occ !== null && fillHidden(calibration, night.days_to_arrival);
  return {
    value: hidden ? null : num(night?.comp_occ),
    low: hidden ? null : num(night?.comp_occ_low),
    high: hidden ? null : num(night?.comp_occ_high),
    hidden,
    lead,
    hotels: night?.comp_occ_hotels ?? 0,
  };
}

/**
 * Giá đặt được của một ô (giá 1 đêm còn bán): bỏ ô hết phòng, bị hạn chế (min-stay, đóng ngày đến),
 * không giá, lỗi, chưa quét và ô cũ hơn 48 giờ (giá cũ có thể không còn bán).
 */
export function bookablePrice(c: DateCell | undefined): number | null {
  if (!c || c.stale || cellState(c) !== "available") return null;
  return num(c.min_price);
}

/** Ô quan sát được trạng thái (còn bán, hết phòng, hạn chế) và không cũ. */
function observed(c: DateCell | undefined): c is DateCell {
  const s = cellState(c);
  return !!c && !c.stale && (s === "available" || s === "sold_out" || s === "restricted");
}

export function selfRow(o: OverviewOut): HotelRow | null {
  return o.hotels.find((h) => h.role === "self") ?? null;
}

export function competitorRows(o: OverviewOut): HotelRow[] {
  return o.hotels.filter((h) => h.role !== "self");
}

/** Số compset của backend cho một đêm (chỉ compset chính, quan sát ≤48 giờ, có cờ cỡ mẫu). */
export function compsetDay(o: OverviewOut, date: string): CompsetDayOut | undefined {
  return o.compset.find((c) => c.stay_date === date);
}

export function cellOn(row: HotelRow | null | undefined, date: string): DateCell | undefined {
  return row?.cells.find((c) => c.stay_date === date);
}

export function rowName(row: HotelRow): string {
  return hotelTitle(row.hotel, row.label);
}

/** Một khách sạn đã hết hoặc còn rất ít phòng (≤ `LOW_ROOMS`, Booking.com báo chính xác). Hạn chế không tính. */
export function isTight(c: DateCell | undefined): boolean {
  if (!c) return false;
  const s = cellState(c);
  return s === "sold_out" || (s === "available" && c.exact_rooms_left !== null && c.exact_rooms_left <= LOW_ROOMS);
}

/** Trung vị; null khi rỗng. */
export function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** Đối thủ hết/sắp hết của một đêm. */
export type Tightness = {
  /** Đối thủ hết phòng + còn ≤ 3 phòng (không gồm bị hạn chế). */
  tight: number;
  /** Hết phòng thật (chỉ `sold_out`). */
  soldOut: number;
  low: number;
  /** Bị hạn chế (min-stay, đóng ngày đến): vẫn bán ở điều kiện khác, đếm riêng. */
  restricted: number;
  /** Đối thủ có dữ liệu đọc được đêm đó (N). */
  observed: number;
  /** % đối thủ hết/sắp hết (0–100); null khi dưới `MIN_SAMPLE` đối thủ quan sát được. */
  share: number | null;
  /** Có quan sát nhưng dưới `MIN_SAMPLE` đối thủ: hiện x/N kèm "mẫu nhỏ". */
  smallSample: boolean;
};

function tightnessOf(cells: Array<DateCell | undefined>): Tightness {
  let seen = 0;
  let soldOut = 0;
  let low = 0;
  let restricted = 0;
  for (const c of cells) {
    if (!observed(c)) continue;
    seen += 1;
    const s = cellState(c);
    if (s === "sold_out") soldOut += 1;
    else if (s === "restricted") restricted += 1;
    else if (c.exact_rooms_left !== null && c.exact_rooms_left <= LOW_ROOMS) low += 1;
  }
  const tight = soldOut + low;
  return { tight, soldOut, low, restricted, observed: seen, share: seen >= MIN_SAMPLE ? Math.round((tight / seen) * 100) : null, smallSample: seen > 0 && seen < MIN_SAMPLE };
}

/** Đối thủ hết/sắp hết của một đêm trong overview. */
export function compsetTightness(o: OverviewOut, date: string): Tightness {
  return tightnessOf(competitorRows(o).map((r) => cellOn(r, date)));
}

/** Đêm căng theo định nghĩa chung (xem đầu tệp). `fill`: chỉ báo lấp đầy 0..1 hoặc null. */
export function isTightNight(t: Tightness, fill: number | null): boolean {
  return (t.observed >= 2 && t.tight / t.observed >= TIGHT_SHARE) || (fill !== null && fill >= TIGHT_FILL);
}

export type MarketSnapshot = {
  competitors: number;
  observed: number;
  soldOut: number;
  low: number;
  restricted: number;
  tightness: Tightness;
  /** Tổng số phòng còn của đối thủ có số chính xác. */
  roomsLeft: number;
  /** Số đối thủ góp vào `roomsLeft`. */
  roomsKnown: number;
  /** Trung vị giá niêm yết thấp nhất của các đối thủ còn bán (null khi chưa đủ mẫu). */
  medianRate: number | null;
  /** Số đối thủ có giá góp vào trung vị. */
  priced: number;
  /** Số compset của backend đêm đó (cỡ mẫu n/N, mẫu nhỏ/chưa đủ mẫu). */
  compset: CompsetDayOut | undefined;
  minRate: { value: number; name: string } | null;
  maxRate: { value: number; name: string } | null;
  currency: string | null;
};

/** Toàn cảnh compset của một đêm (mặc định đêm đầu kỳ). */
export function marketSnapshot(o: OverviewOut, date: string = o.start): MarketSnapshot {
  const comps = competitorRows(o);
  let roomsLeft = 0;
  let roomsKnown = 0;
  let currency: string | null = null;
  const prices: Array<{ value: number; name: string }> = [];
  for (const r of comps) {
    const c = cellOn(r, date);
    if (!observed(c)) continue;
    if (c.exact_rooms_left !== null && cellState(c) === "available") {
      roomsLeft += c.exact_rooms_left;
      roomsKnown += 1;
    }
    const p = bookablePrice(c);
    if (p !== null) {
      prices.push({ value: p, name: rowName(r) });
      currency = currency ?? c.currency;
    }
  }
  const tightness = compsetTightness(o, date);
  const sorted = [...prices].sort((a, b) => a.value - b.value);
  return {
    competitors: comps.length,
    observed: tightness.observed,
    soldOut: tightness.soldOut,
    low: tightness.low,
    restricted: tightness.restricted,
    tightness,
    roomsLeft,
    roomsKnown,
    medianRate: medianCompRate(o, date),
    priced: compsetDay(o, date)?.competitors_priced ?? prices.length,
    compset: compsetDay(o, date),
    minRate: sorted[0] ?? null,
    maxRate: sorted[sorted.length - 1] ?? null,
    currency,
  };
}

/**
 * Trung vị giá đối thủ của một đêm (giá niêm yết thấp nhất mỗi khách sạn còn bán). Lấy số của
 * backend (chỉ compset chính, null khi chưa đủ mẫu); backend cũ không có thì tự tính.
 */
export function medianCompRate(o: OverviewOut, date: string): number | null {
  const c = compsetDay(o, date);
  if (c) return num(c.median_price);
  return median(
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

/** Vị trí giá: `belowTight` = rẻ hơn trung vị khi đêm căng (cơ hội tăng giá, tô cảnh báo); còn lại trung tính. */
export type RatePosition = { kind: "level" | "below" | "belowTight" | "above"; text: string; tone: "warn" | "neutral" };

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

  /**
   * Vị trí giá của bạn so với trung vị đối thủ. Rẻ hơn không mặc nhiên là tốt: chỉ khi đêm căng
   * (`tight`, xem `isTightNight`) thì rẻ hơn mới được nhấn là "cơ hội tăng giá"; không tô xanh.
   */
  function ratePosition(own: number | null, med: number | null, tight: boolean): RatePosition | null {
    if (own === null || med === null || med === 0) return null;
    const d = (own - med) / med;
    if (Math.abs(d) < 0.02) return { kind: "level", text: t("position.level"), tone: "neutral" };
    if (d > 0) return { kind: "above", text: t("position.above"), tone: "neutral" };
    return tight ? { kind: "belowTight", text: t("position.belowTight"), tone: "warn" } : { kind: "below", text: t("position.below"), tone: "neutral" };
  }

  /** Đầu cột ngày: "T6" + "02/10"; đêm cuối tuần của khách sạn (T6, T7) tô đỏ như mẫu. */
  function dayHead(iso: string, today?: string): { wd: string; date: string; weekend: boolean; isToday: boolean } {
    return { wd: fmt.fmtWeekday(iso), date: fmt.fmtDateShort(iso), weekend: isWeekend(iso), isToday: iso === today };
  }

  return { demandLabel, ratePosition, dayHead };
}

export type MarketMetricsText = ReturnType<typeof createMarketMetrics>;

export function useMarketMetrics(): MarketMetricsText {
  const t = useTranslations("helpers.marketMetrics");
  const fmt = useFmt();
  return useMemo(() => createMarketMetrics(t, fmt), [t, fmt]);
}
