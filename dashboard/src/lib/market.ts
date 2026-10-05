/**
 * Định dạng số liệu nhịp đặt phòng và gợi ý giá cho màn "Nhịp đặt phòng" và "Hôm nay".
 * Công suất là ước tính từ số phòng còn trên kênh tham chiếu (Booking), luôn ghi rõ "≈".
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { PaceNightOut, SuggestionOut } from "@/lib/api";
import type { Tone } from "@/lib/labels";
import { num } from "@/lib/format";

/** "≈72%"; null khi không có. */
export function fmtOcc(v: string | number | null | undefined): string | null {
  const n = num(v);
  return n === null ? null : `≈${Math.round(n * 100)}%`;
}

export const SUGGESTION_TONE: Record<SuggestionOut["kind"], Tone> = {
  raise: "purple",
  hold: "gray",
  lower: "amber",
};

export type MarketTextTranslator = ReturnType<typeof useTranslations<"helpers.market">>;

/**
 * Phần sinh chữ. Component: `const { fmtPace, suggestionLabel, fmtChange, ownOccText } = useMarketText();`
 * Ngoài React: `createMarketText(t)` với `t = await getTranslations("helpers.market")`.
 */
export function createMarketText(t: MarketTextTranslator) {
  /** Nhịp so cùng kỳ (điểm phần trăm, có dấu): "+12 điểm", "−8 điểm", "ngang cùng kỳ". */
  function fmtPace(delta: string | number | null | undefined): string | null {
    const n = num(delta);
    if (n === null) return null;
    const pts = Math.round(n * 100);
    if (pts === 0) return t("paceFlat");
    return pts > 0 ? t("paceUp", { pts }) : t("paceDown", { pts: -pts });
  }

  /** Có thể tăng giá / Giữ giá / Xem lại giá. */
  function suggestionLabel(kind: SuggestionOut["kind"]): string {
    return t(`suggestion.${kind}`);
  }

  function fmtChange(pct: number): string {
    if (pct === 0) return t("noChange");
    return pct > 0 ? `+${pct}%` : `−${-pct}%`;
  }

  /** Công suất của bạn: PMS (thật) nếu có, không thì ước tính đủ tin cậy. */
  function ownOccText(n: PaceNightOut): { text: string; source: "pms" | "est" | null } {
    if (n.own_status === "sold_out" || n.own_occ?.status === "sold_out") return { text: t("soldOut"), source: null };
    const pms = num(n.own_pms_occ);
    if (pms !== null) return { text: `${Math.round(pms * 100)}%`, source: "pms" };
    if (n.own_occ?.reliable) return { text: fmtOcc(n.own_occ.occ_mid) ?? "—", source: "est" };
    return { text: n.own_occ ? t("notEnoughData") : "—", source: null };
  }

  return { fmtPace, suggestionLabel, fmtChange, ownOccText };
}

export type MarketText = ReturnType<typeof createMarketText>;

export function useMarketText(): MarketText {
  const t = useTranslations("helpers.market");
  return useMemo(() => createMarketText(t), [t]);
}

/** Gợi ý còn chờ xử lý (chưa áp dụng, chưa bỏ qua), đêm gần trước. */
export function pendingSuggestions(nights: PaceNightOut[]): PaceNightOut[] {
  return nights.filter((n) => n.suggestion && !n.suggestion.decision);
}
