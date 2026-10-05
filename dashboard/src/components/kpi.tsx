"use client";

import type { ReactNode } from "react";
import { InfoTip, cx } from "./ui";

/** Màu số lớn trên thẻ chỉ số (theo mẫu OTARadar). */
export type KpiTone = "default" | "brand" | "good" | "hot" | "bad" | "muted";

export const KPI_TONE_TEXT: Record<KpiTone, string> = {
  default: "text-ink",
  brand: "text-brand",
  good: "text-yours",
  hot: "text-hot",
  bad: "text-danger",
  muted: "text-faint",
};

/** Thẻ một chỉ số: tiêu đề in hoa, số lớn, dòng mô tả. `align="center"` như thẻ ADR/RevPAR của mẫu. */
export function KpiCard({
  title,
  info,
  value,
  sub,
  tone = "default",
  align = "center",
  children,
  className,
}: {
  title: ReactNode;
  info?: ReactNode;
  /** Bỏ qua khi truyền `children` (nội dung riêng như đồng hồ đo). */
  value?: ReactNode;
  sub?: ReactNode;
  tone?: KpiTone;
  align?: "center" | "left";
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("min-w-0 rounded-[10px] border border-line bg-surface px-5 py-4 shadow-card", align === "center" && "text-center", className)}>
      <h3
        className={cx(
          "flex items-center gap-1.5 text-[12.5px] font-semibold uppercase tracking-[0.05em]",
          align === "center" ? "justify-center text-ink" : "text-muted",
        )}
      >
        {title}
        {info && <InfoTip>{info}</InfoTip>}
      </h3>
      {children ?? (
        <>
          <div className={cx("mt-2 text-[28px] font-bold leading-tight tracking-[-0.01em] tabular", KPI_TONE_TEXT[tone])}>{value}</div>
          {sub && <div className="mt-0.5 text-sm text-muted">{sub}</div>}
        </>
      )}
    </section>
  );
}

/** Dải số trong một thẻ, ngăn bằng đường dọc (TOÀN CẢNH THỊ TRƯỜNG HÔM NAY). */
export function SnapshotRow({ items, className }: { items: Array<{ value: ReactNode; label: ReactNode; tone?: KpiTone; title?: string }>; className?: string }) {
  return (
    <dl className={cx("grid grid-cols-2 gap-y-4 sm:grid-cols-3 lg:grid-flow-col lg:auto-cols-fr lg:grid-cols-none", className)}>
      {items.map((it, i) => (
        <div
          key={i}
          title={it.title}
          className={cx("min-w-0 px-3 text-center", i > 0 && "lg:border-l lg:border-line", items.length % 2 === 1 && i === items.length - 1 && "col-span-2 sm:col-span-1")}
        >
          <dd className={cx("text-[28px] font-bold leading-tight tabular", KPI_TONE_TEXT[it.tone ?? "default"])}>{it.value}</dd>
          <dt className="mt-0.5 text-sm text-muted">{it.label}</dt>
        </div>
      ))}
    </dl>
  );
}

/** Hàng "nhãn ……… giá trị" (thẻ KHÁCH SẠN CỦA BẠN, TRẠNG THÁI DỮ LIỆU). */
export function KeyValueRow({ label, value, icon, tone = "default", className }: { label: ReactNode; value: ReactNode; icon?: ReactNode; tone?: KpiTone; className?: string }) {
  return (
    <div className={cx("flex items-center justify-between gap-3 py-2.5 text-base", className)}>
      <span className="flex min-w-0 items-center gap-2 text-body">
        {icon && <span className="shrink-0 text-muted">{icon}</span>}
        <span className="truncate">{label}</span>
      </span>
      <span className={cx("shrink-0 text-right font-semibold tabular", tone === "default" ? "text-ink" : KPI_TONE_TEXT[tone])}>{value}</span>
    </div>
  );
}
