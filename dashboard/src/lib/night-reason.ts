/**
 * Câu sự thật về vị thế của khách sạn bạn trong một đêm, ghép từ số liệu thị trường.
 * Chỉ nêu điều dữ liệu cho thấy (đối thủ hết phòng, giá so trung vị, hạng giá, ngày lễ);
 * không đưa ra gợi ý giá.
 *
 * Component: `const { nightReason, fmtRank, fmtVsMedian } = useNightReason();`
 * Ngoài React: `createNightReason(t, fmt)` với `t = await getTranslations("helpers.nightReason")`.
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { CompsetDayOut } from "@/lib/api";
import { num, useFmt, type Fmt } from "@/lib/format";

export type NightReasonTranslator = ReturnType<typeof useTranslations<"helpers.nightReason">>;

/** Chênh lệch giá của bạn so với trung vị đối thủ, làm tròn tới phần trăm; null khi chưa so được. */
export function deltaVsMedian(priceIndex: string | number | null | undefined): number | null {
  const idx = num(priceIndex);
  return idx === null ? null : Math.round(idx - 100);
}

export function createNightReason(t: NightReasonTranslator, fmt: Fmt) {
  /** "rẻ nhất trong 6", "đắt nhất trong 6", "rẻ thứ 2/6"; null khi không xếp hạng được. */
  function fmtRank(rank: number | null | undefined, total: number): string | null {
    if (!rank || total < 2) return null;
    if (rank === 1) return t("rankCheapest", { total });
    if (rank >= total) return t("rankPriciest", { total });
    return t("rank", { rank, total });
  }

  /** "thấp hơn trung vị 12%", "cao hơn trung vị 8%", "ngang trung vị"; null khi chưa so được. */
  function fmtVsMedian(priceIndex: string | number | null | undefined): string | null {
    const d = deltaVsMedian(priceIndex);
    if (d === null) return null;
    if (d === 0) return t("vsMedianLevel");
    return d < 0 ? t("vsMedianBelow", { pct: fmt.fmtNum(-d) }) : t("vsMedianAbove", { pct: fmt.fmtNum(d) });
  }

  function nightReason(c: CompsetDayOut | null | undefined, holiday?: string | null): string | null {
    const parts: string[] = [];
    if (c && c.competitors_observed > 0 && c.competitors_sold_out > 0) {
      parts.push(t("soldOut", { soldOut: c.competitors_sold_out, observed: c.competitors_observed }));
    }
    const vs = fmtVsMedian(c?.price_index);
    if (c && vs) {
      const rank = fmtRank(c.own_rank, c.priced_hotels);
      parts.push(rank ? t("yourPriceRank", { vs, rank }) : t("yourPrice", { vs }));
    }
    if (holiday) parts.push(t("holiday", { holiday }));
    if (!parts.length) return null;
    const s = parts.join(" · ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  return { fmtRank, fmtVsMedian, nightReason };
}

export type NightReasonText = ReturnType<typeof createNightReason>;

export function useNightReason(): NightReasonText {
  const t = useTranslations("helpers.nightReason");
  const fmt = useFmt();
  return useMemo(() => createNightReason(t, fmt), [t, fmt]);
}
