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

  /** Có thể tăng giá / Giữ giá / Có thể giảm giá. */
  function suggestionLabel(kind: SuggestionOut["kind"]): string {
    return t(`suggestion.${kind}`);
  }

  /** Nhãn thẻ gợi ý: "Giá thấp hơn mức thường" khi chỉ lệch vị trí thường ngày, không có tín hiệu cầu. */
  function suggestionBadge(s: Pick<SuggestionOut, "kind" | "adjustments">): string {
    return s.adjustments.some((r) => r.key === "below_usual") ? t("suggestion.belowUsual") : t(`suggestion.${s.kind}`);
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

  return { fmtPace, suggestionLabel, suggestionBadge, fmtChange, ownOccText };
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

/** Khoá điều chỉnh là tín hiệu cầu thật (không phải thứ trong tuần hay sát ngày). */
const DEMAND_KEYS = ["comp_tight", "comp_occ", "comp_pace", "own_occ_high", "own_rooms_few", "own_pace_ahead", "holiday", "event"];

/**
 * Một câu lý do chính của gợi ý: điều chỉnh cùng chiều có % lớn nhất (ưu tiên tín hiệu cầu), không
 * có thì lý do "thấp hơn mức thường", cuối cùng là câu đầu tiên backend trả về.
 */
export function mainReason(s: Pick<SuggestionOut, "kind" | "adjustments" | "reasons">): string | null {
  const sign = s.kind === "lower" ? -1 : 1;
  const same = s.adjustments.filter((r) => (r.pct ?? 0) * sign > 0);
  const demand = same.filter((r) => DEMAND_KEYS.some((k) => r.key.startsWith(k)));
  const pick = (demand.length ? demand : same).sort((a, b) => (b.pct ?? 0) * sign - (a.pct ?? 0) * sign)[0];
  // Không có điều chỉnh cùng chiều: câu "vì sao" là lệch mức thường của chính bạn hoặc công suất thấp.
  const why = ["below_usual", "own_occ_low_pms", "own_occ_low_otb", "above_usual"];
  const r =
    pick ??
    why.map((k) => s.adjustments.find((x) => x.key === k)).find(Boolean) ??
    s.adjustments.find((x) => x.pct === null && !x.key.startsWith("clamp_") && !x.key.startsWith("position"));
  if (r) return adjustmentText(r);
  return s.reasons[0] ? s.reasons[0].charAt(0).toUpperCase() + s.reasons[0].slice(1) : null;
}
