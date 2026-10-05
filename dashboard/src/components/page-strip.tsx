import type { ReactNode } from "react";
import { cx } from "./ui";

/**
 * Dải đầu trang kiểu OTARadar (như "Terminal+ | ngày giờ | mùa … | N khách sạn | cập nhật"):
 * tên tab màu xanh, các mục thông tin ngăn nhau, công cụ (chọn kênh, kỳ xem) bên phải.
 */
export function PageStrip({ title, meta, aside, actions, className }: { title: ReactNode; meta?: ReactNode; aside?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cx("mb-4 flex flex-wrap items-center gap-x-5 gap-y-2.5 rounded-[10px] border border-line bg-surface px-5 py-3 shadow-card", className)}>
      <h1 className="text-lg font-bold text-brand">{title}</h1>
      {meta && <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-base text-body">{meta}</div>}
      <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
        {aside && <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">{aside}</div>}
        {actions}
      </div>
    </div>
  );
}

/** Ngăn dọc mảnh giữa các mục của dải đầu trang. */
export function StripDivider() {
  return <span aria-hidden className="h-4 w-px bg-line-strong" />;
}
