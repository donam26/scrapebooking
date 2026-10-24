/**
 * Khu vực thị trường trên Booking.com (Cài đặt › Thị trường, Terminal+, Đối thủ › Thị trường):
 * phân khúc (bộ lọc `nflt` của Booking), bán kính, và chỉ số thang phòng trống của thị trường.
 *
 * Mọi số của thang là CẬN DƯỚI phòng Booking.com còn bán ("mức căng thị trường trên Booking.com"),
 * không phải công suất. c(N) = số khách sạn trong phân khúc còn bán được ≥ N phòng cùng lúc một đêm.
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { LadderRungOut } from "@/lib/api";
import type { RoomsLeft } from "@/lib/rooms-left";

// ---- phân khúc, bán kính ----

/** Mẫu phân khúc của UI: mọi loại chỗ ở / khách sạn / khách sạn + resort + căn hộ khách sạn. */
export const SEGMENTS = [
  { key: "all", nflt: null },
  { key: "hotels", nflt: "ht_id=204" },
  { key: "hotelsPlus", nflt: "ht_id=204;ht_id=206;ht_id=219" },
] as const;
export type SegmentKey = (typeof SEGMENTS)[number]["key"];

/** Phân khúc mặc định cho khu vực mới: khách sạn + resort + căn hộ khách sạn. */
export const DEFAULT_SEGMENT: string = SEGMENTS[2].nflt;

/** Bán kính Booking cho phép (bộ lọc `distance`), mét. */
export const RADII = [1000, 3000, 5000] as const;
export type Radius = (typeof RADII)[number];
/** Bán kính mặc định của khu vực "quanh khách sạn của bạn" và của địa danh. */
export const DEFAULT_RADIUS: Radius = 3000;

export function asRadius(v: number | null | undefined): Radius | null {
  return RADII.find((r) => r === v) ?? null;
}

/** Bộ lọc chuẩn hoá để so (thứ tự các điều kiện không quan trọng); rỗng = null. */
export function normalizeNflt(nflt: string | null | undefined): string | null {
  if (!nflt) return null;
  const parts = nflt
    .split(";")
    .map((p) => p.trim())
    .filter(Boolean)
    .sort();
  return parts.length ? parts.join(";") : null;
}

/** Mẫu phân khúc của một bộ lọc; bộ lọc khác các mẫu là "custom". */
export function segmentKey(nflt: string | null | undefined): SegmentKey | "custom" {
  const n = normalizeNflt(nflt);
  return SEGMENTS.find((s) => normalizeNflt(s.nflt) === n)?.key ?? "custom";
}

// ---- loại chỗ ở (thành phần thị trường) ----

/** Loại chỗ ở của Booking (`ht_id`) có nhãn riêng; mã khác gộp vào "other". */
export const PROPERTY_TYPES = ["204", "201", "219", "206", "213", "216", "222", "220", "203", "208"] as const;
export type PropertyType = (typeof PROPERTY_TYPES)[number];

function isPropertyType(id: string): id is PropertyType {
  return (PROPERTY_TYPES as readonly string[]).includes(id);
}

/** Thành phần thị trường {ht_id: số còn phòng} → nhóm theo loại, nhiều trước (mã lạ gộp "other"). */
export function compositionGroups(composition: Record<string, number>): Array<{ type: PropertyType | "other"; count: number }> {
  const groups = new Map<PropertyType | "other", number>();
  for (const [id, count] of Object.entries(composition)) {
    if (!count) continue;
    const type = isPropertyType(id) ? id : "other";
    groups.set(type, (groups.get(type) ?? 0) + count);
  }
  return [...groups].map(([type, count]) => ({ type, count })).sort((a, b) => b.count - a.count);
}

// ---- thang phòng trống ----

/** Các nấc hiện gọn trên thẻ thị trường. */
export const LADDER_RUNGS = [1, 5, 10, 20, 30] as const;
/** Nấc "sâu" của dải 14 đêm và của mức căng c(10)/c(1). */
export const DEEP_RUNG = 10;

/** {N: c(N)} từ `list_scan.ladder` (mảng nấc) hoặc từ `trend.nights[].ladder` ({"10": c}). */
export function rungMap(ladder: ReadonlyArray<Pick<LadderRungOut, "rooms" | "available">> | Record<string, number>): Map<number, number> {
  const out = new Map<number, number>();
  if (Array.isArray(ladder)) {
    for (const r of ladder) out.set(r.rooms, r.available);
  } else {
    for (const [k, v] of Object.entries(ladder)) if (/^\d+$/.test(k) && typeof v === "number") out.set(Number(k), v);
  }
  return out;
}

/**
 * c(N) của một nấc. Nấc không có trong lượt quét: 0 khi một nấc thấp hơn đã về 0 (lượt quét dừng thang
 * ở đó), còn lại null (chưa biết, không đoán).
 */
export function rungCount(counts: Map<number, number>, rooms: number): number | null {
  const v = counts.get(rooms);
  if (v !== undefined) return v;
  for (const [n, c] of counts) if (n < rooms && c === 0) return 0;
  return null;
}

// ---- mức căng so thường lệ ----

/** Mức căng (c(10)/c(1)) lệch trung vị không quá chừng này (5 điểm %) thì "như thường lệ". */
export const TIGHTNESS_BAND = 0.05;

export type TightnessTrend = "tighter" | "usual" | "looser";

/** Mức căng thấp = ít khách sạn còn nhiều phòng = căng. So với trung vị các đêm của vòng quét. */
export function tightnessTrend(value: number | null | undefined, median: number | null | undefined): TightnessTrend | null {
  if (value === null || value === undefined || median === null || median === undefined) return null;
  // Làm tròn hiệu để 0,55 − 0,60 không thành −0,0500…01 do số thực.
  const d = Math.round((value - median) * 10_000) / 10_000;
  if (d < -TIGHTNESS_BAND) return "tighter";
  if (d > TIGHTNESS_BAND) return "looser";
  return "usual";
}

/** Màu theo so thường lệ: căng hơn cam, như thường lệ xám (vòng đo xanh), thoáng hơn xanh lá. */
export const TIGHTNESS_STYLE: Record<TightnessTrend, { chip: string; color: string }> = {
  tighter: { chip: "bg-hot-soft text-hot", color: "var(--sb-hot)" },
  usual: { chip: "bg-sunken text-body", color: "var(--sb-brand)" },
  looser: { chip: "bg-yours-soft text-yours-deep", color: "var(--sb-yours)" },
};

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/**
 * Thang nhiệt theo tỉ lệ khách sạn hết phòng (cùng màu với số phòng còn: đỏ gần như kín → xanh lá còn
 * nhiều chỗ): từ 90% đỏ, 75% cam, 50% hổ phách, 25% vàng nhạt, 10% xanh nhạt, dưới 10% xanh lá.
 */
export const SOLD_OUT_STEPS = [0.9, 0.75, 0.5, 0.25, 0.1] as const;

export function soldOutHeat(share: number): string {
  const i = SOLD_OUT_STEPS.findIndex((s) => share >= s);
  return `sb-heat-${i === -1 ? SOLD_OUT_STEPS.length : i}`;
}

/** Khoảng phòng còn (thang tìm kiếm hoặc trang khách sạn) → RoomsLeft; max null = "≥ min". */
export function roomsRange(min: number | null | undefined, max: number | null | undefined): RoomsLeft | null {
  if (min === null || min === undefined) return null;
  const hi = max ?? null;
  return { min, max: hi, exact: hi !== null && hi === min ? min : null };
}

// ---- chữ ----

export type MarketAreaTranslator = ReturnType<typeof useTranslations<"helpers.marketArea">>;

/**
 * Nhãn khu vực theo ngôn ngữ. Component: `const { segmentLabel, radiusLabel } = useMarketAreaText();`
 * Ngoài React: `createMarketAreaText(t)` với `t = await getTranslations("helpers.marketArea")`.
 */
export function createMarketAreaText(t: MarketAreaTranslator) {
  /** "Khách sạn", "Mọi loại chỗ ở"… ; bộ lọc riêng hiện kèm chuỗi bộ lọc. */
  function segmentLabel(nflt: string | null | undefined): string {
    const key = segmentKey(nflt);
    return key === "custom" ? t("segment.custom", { nflt: nflt ?? "" }) : t(`segment.${key}`);
  }

  /** "3 km"; null khi không lọc bán kính. */
  function radiusLabel(meters: number | null | undefined): string | null {
    return meters ? t("radius", { km: meters / 1000 }) : null;
  }

  function propertyTypeLabel(type: PropertyType | "other"): string {
    return t(`propertyType.${type}`);
  }

  function tightnessLabel(trend: TightnessTrend): string {
    return t(`tightness.${trend}`);
  }

  return { segmentLabel, radiusLabel, propertyTypeLabel, tightnessLabel };
}

export type MarketAreaText = ReturnType<typeof createMarketAreaText>;

export function useMarketAreaText(): MarketAreaText {
  const t = useTranslations("helpers.marketArea");
  return useMemo(() => createMarketAreaText(t), [t]);
}
