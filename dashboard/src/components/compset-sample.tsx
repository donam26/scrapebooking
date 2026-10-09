"use client";

import { useTranslations } from "next-intl";
import type { CompsetDayOut } from "@/lib/api";
import { cx } from "./ui";

/**
 * Cỡ mẫu của số compset một đêm (roadmap 1.9, theo ngưỡng CoStar STR): trung vị, chỉ số giá niêm
 * yết và vị trí giá cần ≥4 đối thủ có giá cùng điều kiện (`sample = ok`); 3 đối thủ thì hiện mờ
 * "mẫu nhỏ" (`small`); dưới 3 thì backend trả null và giao diện ghi "chưa đủ mẫu" (`insufficient`).
 * Luôn hiện n/N: n đối thủ có giá / N đối thủ compset chính.
 */

export type SampleLevel = CompsetDayOut["sample"];

/** Số đối thủ có giá tối thiểu để số compset là "đủ mẫu". */
export const SAMPLE_MIN = 4;

type SampleLike = Pick<CompsetDayOut, "sample" | "competitors_priced" | "competitors_total">;

/** Lớp làm mờ cho số tính từ mẫu nhỏ. */
export function sampleFade(c: Pick<CompsetDayOut, "sample"> | null | undefined): string {
  return c?.sample === "small" ? "opacity-60" : "";
}

/** Có tính được trung vị/chỉ số/vị trí (mẫu đủ hoặc nhỏ). */
export function sampleUsable(c: Pick<CompsetDayOut, "sample"> | null | undefined): boolean {
  return !!c && c.sample !== "insufficient";
}

export type SampleTextTranslator = ReturnType<typeof useTranslations<"components.sample">>;

export function createSampleText(t: SampleTextTranslator) {
  const vars = (c: SampleLike) => ({ n: c.competitors_priced, total: c.competitors_total, min: SAMPLE_MIN });
  return {
    /** "5/7" */
    count: (c: SampleLike) => t("countShort", vars(c)),
    /** "5/7 đối thủ có giá" */
    countLong: (c: SampleLike) => t("count", vars(c)),
    /** Chữ trạng thái mẫu: null (đủ), "mẫu nhỏ", "chưa đủ mẫu (2/7, cần ≥4)". */
    status: (c: SampleLike) => (c.sample === "small" ? t("small") : c.sample === "insufficient" ? t("insufficient", vars(c)) : null),
    /** Tooltip giải thích. */
    title: (c: SampleLike) => (c.sample === "small" ? t("smallTitle", vars(c)) : c.sample === "insufficient" ? t("insufficientTitle", vars(c)) : t("okTitle", vars(c))),
  };
}

export function useSampleText() {
  const t = useTranslations("components.sample");
  return createSampleText(t);
}

/**
 * Nhãn cỡ mẫu: "5/7 đối thủ có giá", "3/7 · mẫu nhỏ", "chưa đủ mẫu (2/7, cần ≥4)".
 * `short`: chỉ "5/7" khi đủ mẫu.
 */
export function SampleTag({ c, short, className }: { c: SampleLike | null | undefined; short?: boolean; className?: string }) {
  const s = useSampleText();
  if (!c) return null;
  const status = s.status(c);
  return (
    <span title={s.title(c)} className={cx("whitespace-nowrap tabular", c.sample === "insufficient" ? "text-faint" : "text-muted", className)}>
      {c.sample === "insufficient" ? status : short ? s.count(c) : s.countLong(c)}
      {c.sample === "small" && <span className="ml-1 rounded bg-sunken px-1 py-px text-2xs font-semibold text-muted">{status}</span>}
    </span>
  );
}

/** Nhãn chỉ số và vị trí giá theo đúng tên nghề (không gọi ARI/RPI). */
export function useCompsetLabels() {
  const t = useTranslations("components.sample");
  return {
    index: t("index"),
    indexTitle: t("indexTitle"),
    rankLabel: t("rankLabel"),
    /** "2/6 (1 = rẻ nhất)" */
    rank: (rank: number | null | undefined, total: number) => (rank ? t("rank", { rank, total }) : null),
  };
}
