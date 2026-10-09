/**
 * Chữ cho gói giá (roadmap 2.4, 2.8).
 *
 * Khoá gói `"t|f"` = hoàn huỷ | bữa sáng, mỗi vế t (có) / f (không) / ? (chưa rõ); `"*"` = dữ liệu cũ
 * không có chi tiết gói (giá thấp nhất mọi gói).
 *
 * Component: `const { rateConditions, rateKeyText } = useRateText();`.
 */
import { useTranslations } from "next-intl";
import { useMemo } from "react";

export type RateTextTranslator = ReturnType<typeof useTranslations<"helpers.rates">>;

export function createRateText(t: RateTextTranslator) {
  /** Điều kiện gói: "hoàn huỷ, không bữa sáng"; null khi khoá rỗng. `"*"` → "mọi gói". */
  function rateConditions(key: string | null | undefined): string | null {
    if (!key) return null;
    if (key === "*") return t("anyRate");
    const [r, b] = key.split("|");
    const parts = [r === "t" ? t("refundable") : r === "f" ? t("nonRefundable") : null, b === "t" ? t("breakfast") : b === "f" ? t("roomOnly") : null].filter(
      (x): x is string => x !== null,
    );
    return parts.length ? parts.join(", ") : t("unknownConditions");
  }

  /** "cùng gói hoàn huỷ, không bữa sáng" (đổi giá trên cùng điều kiện). */
  function rateKeyText(key: string | null | undefined): string | null {
    const c = rateConditions(key);
    if (c === null) return null;
    return key === "*" ? c : t("sameRate", { conditions: c });
  }

  return { rateConditions, rateKeyText };
}

export type RateText = ReturnType<typeof createRateText>;

export function useRateText(): RateText {
  const t = useTranslations("helpers.rates");
  return useMemo(() => createRateText(t), [t]);
}
