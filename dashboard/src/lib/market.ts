/**
 * Định dạng số liệu nhịp đặt phòng và gợi ý giá cho màn "Nhịp đặt phòng" và "Hôm nay".
 * Công suất là ước tính từ số phòng còn trên Booking.com, luôn ghi rõ "≈".
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { PaceNightOut, ReasonOut, SuggestionOut } from "@/lib/api";
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
  /** Nhịp so các tuần trước cùng thứ (điểm phần trăm, có dấu): "+12 điểm", "−8 điểm", "ngang các tuần trước". */
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

/**
 * Giá mục tiêu của một gợi ý (VND). Ưu tiên `target_price` backend đã tính theo chiến lược giá
 * (tham chiếu × điều chỉnh, chặn sàn/trần/mức đổi tối đa, làm tròn). Dữ liệu cũ chưa có thì tính
 * tạm = giá thấp nhất của bạn × (1 + mức đổi), làm tròn tới 1.000 ₫ (tiền khác VND: 1 đơn vị).
 * null khi không có gợi ý hoặc chưa có giá của bạn.
 */
export function suggestionTarget(n: Pick<PaceNightOut, "own_price" | "currency" | "suggestion">): number | null {
  if (!n.suggestion) return null;
  const backend = num(n.suggestion.target_price);
  if (backend !== null) return backend;
  const own = num(n.own_price);
  if (own === null) return null;
  const step = n.currency && n.currency !== "VND" ? 1 : 1000;
  return Math.round((own * (1 + n.suggestion.change_pct / 100)) / step) * step;
}

/** Gợi ý còn chờ xử lý (chưa áp dụng, chưa bỏ qua), đêm gần trước. Gồm cả "giữ giá". */
export function pendingSuggestions(nights: PaceNightOut[]): PaceNightOut[] {
  return nights.filter((n) => n.suggestion && !n.suggestion.decision);
}

/** Gợi ý cần làm: tăng/giảm giá còn chờ xử lý. "Giữ giá" (đa số đêm) không phải việc cần làm. */
export function actionableSuggestions(nights: PaceNightOut[]): PaceNightOut[] {
  return pendingSuggestions(nights).filter((n) => n.suggestion!.kind !== "hold");
}

/**
 * Chữ của một điều chỉnh không kèm đuôi "(+5%)" backend đã gắn (hiện % riêng thành chip), viết
 * hoa chữ đầu.
 */
export function adjustmentText(r: Pick<ReasonOut, "text" | "pct">): string {
  const text = r.pct !== null ? r.text.replace(/\s*\([+\-−]?\d+%\)$/, "") : r.text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
