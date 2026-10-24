"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useFmt } from "@/lib/format";

/** Lượt quét khu vực quá chừng này thì gắn chip "Cũ". */
const STALE_MS = 24 * 3600 * 1000;

/**
 * Tuổi số của khu vực: "Số từ lượt quét khu vực 19:07 16/10" (giờ của lượt quét danh sách, không
 * phải lượt quét đối thủ), kèm chip "Cũ · 8 ngày trước" khi lượt quét đã quá 24 giờ.
 */
export function ScanAge({ at }: { at: string | null | undefined }) {
  const t = useTranslations("marketTab.age");
  const { fmtAgo, fmtWhen } = useFmt();
  const [now] = useState(() => Date.now());
  if (!at) return <span>{t("never")}</span>;
  const stale = now - new Date(at).getTime() > STALE_MS;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="tabular">{t("scanned", { when: fmtWhen(at) })}</span>
      {stale && (
        <span title={t("staleTitle")} className="rounded-full bg-warning-soft px-2 py-px text-xs font-semibold text-warning-deep">
          {t("stale", { ago: fmtAgo(at) })}
        </span>
      )}
    </span>
  );
}
