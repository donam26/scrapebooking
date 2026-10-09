"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useFmt } from "@/lib/format";
import type { DataFreshness } from "@/lib/freshness";
import { IconAlert } from "./icons";
import { cx } from "./ui";

export const FRESHNESS_TONE_TEXT: Record<DataFreshness["tone"], string> = {
  ok: "",
  warn: "font-semibold text-warning-deep",
  bad: "font-semibold text-danger",
};

/**
 * "Dữ liệu mới nhất 06:00 hôm nay" theo định nghĩa chung (lib/freshness.ts: quan sát thành công cuối
 * cùng). Dữ liệu cũ / lượt mới nhất rỗng / lỡ lịch thì tô vàng/đỏ và ghi rõ.
 */
export function DataUpdated({ f, className }: { f: DataFreshness; className?: string }) {
  const t = useTranslations("components.freshness");
  const { fmtAgo, fmtWhen } = useFmt();
  const title = f.latestEmpty && f.latest ? t("latestEmptyTitle", { when: fmtWhen(f.latest.finished_at) }) : undefined;
  return (
    <span className={cx(FRESHNESS_TONE_TEXT[f.tone], className)} title={title}>
      {f.updatedAt ? t("updated", { when: fmtWhen(f.updatedAt) }) : t("noData")}
      {f.stale && ` · ${t("stale")}`}
      {!f.stale && f.latestEmpty && ` · ${t("latestEmpty")}`}
      {!f.stale && !f.latestEmpty && f.overdue && ` · ${t("overdue", { ago: fmtAgo(f.updatedAt) })}`}
    </span>
  );
}

/**
 * Băng cảnh báo khi Booking.com không có dữ liệu mới quá một chu kỳ quét: số trên màn có thể đã cũ.
 * Không hiện gì khi dữ liệu còn mới.
 */
export function StaleBanner({ f, className }: { f: DataFreshness; className?: string }) {
  const t = useTranslations("components.freshness");
  const { fmtWhen } = useFmt();
  if (!f.stale) return null;
  return (
    <div role="status" className={cx("flex items-start gap-2.5 rounded-lg border-l-[3px] border-l-danger bg-danger-soft px-4 py-3 text-sm text-danger-deep", className)}>
      <IconAlert size={16} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-semibold">{t("bannerTitle", { hours: f.staleAfterHours ?? 24 })}</p>
        <p className="mt-0.5">
          {f.updatedAt ? t("bannerLast", { when: fmtWhen(f.updatedAt) }) : t("bannerNever")} {t("bannerBody")}{" "}
          <Link href="/runs" className="font-semibold underline hover:no-underline">
            {t("bannerLink")}
          </Link>
        </p>
      </div>
    </div>
  );
}
