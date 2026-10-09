"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { api, type PriceBasis } from "@/lib/api";
import { IconChevronDown, IconDownload, IconExternal, IconFile } from "./icons";
import { PopoverMenu } from "./popover-menu";
import { cx } from "./ui";

const ITEM = "flex w-full items-start gap-2.5 rounded-lg px-3 py-2 text-left no-underline transition-colors hover:bg-subtle focus-visible:bg-subtle";

/**
 * Xuất dữ liệu (roadmap 7.4): CSV của màn đang xem, Excel "rate shop" (khách sạn × đêm: giá, trạng
 * thái, KM, hạn chế, n/N) cùng kỳ/cơ sở giá, và báo cáo tháng dạng trang in (mở tab mới,
 * in ra PDF cho chủ đầu tư). Mọi liên kết đi qua proxy `/api` (kèm tenant cho operator).
 */
export function ExportMenu({
  csvHref,
  start,
  end,
  priceBasis,
  month,
}: {
  /** Liên kết CSV của màn hiện tại (nếu có). */
  csvHref?: string;
  start: string;
  end: string;
  priceBasis?: PriceBasis;
  /** Tháng mặc định của báo cáo ("YYYY-MM"), thường là tháng của hôm nay theo tenant. */
  month: string;
}) {
  const t = useTranslations("components.exportMenu");
  const [reportMonth, setReportMonth] = useState(month);
  const validMonth = /^\d{4}-\d{2}$/.test(reportMonth) ? reportMonth : month;
  return (
    <PopoverMenu
      label={t("label")}
      width={320}
      buttonClassName="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-lg bg-surface px-2.5 text-sm font-semibold text-ink ring-1 ring-inset ring-line-strong transition-colors hover:bg-subtle"
      button={
        <>
          <IconDownload size={15} />
          {t("button")}
          <IconChevronDown size={14} className="text-muted" />
        </>
      }
    >
      {(close) => (
        <div className="p-1.5">
          {csvHref && (
            <a href={csvHref} download className={ITEM} onClick={close}>
              <IconDownload size={16} className="mt-0.5 shrink-0 text-muted" />
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-ink">{t("csv")}</span>
                <span className="block text-xs text-muted">{t("csvHint")}</span>
              </span>
            </a>
          )}
          <a href={api.exports.rateShopUrl({ start, end, price_basis: priceBasis })} download className={ITEM} onClick={close}>
            <IconFile size={16} className="mt-0.5 shrink-0 text-muted" />
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink">{t("rateShop")}</span>
              <span className="block text-xs text-muted">{t("rateShopHint")}</span>
            </span>
          </a>
          <div className={cx(ITEM, "hover:bg-transparent")}>
            <IconExternal size={16} className="mt-0.5 shrink-0 text-muted" />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-ink">{t("monthly")}</span>
              <span className="block text-xs text-muted">{t("monthlyHint")}</span>
              <span className="mt-2 flex items-center gap-2">
                <input
                  type="month"
                  aria-label={t("monthAria")}
                  value={reportMonth}
                  max={month}
                  onChange={(e) => setReportMonth(e.target.value)}
                  className="h-8 min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-2 text-sm text-ink tabular focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15"
                />
                <a
                  href={api.exports.monthlyReportUrl({ month: validMonth })}
                  target="_blank"
                  rel="noreferrer"
                  onClick={close}
                  className="inline-flex h-8 shrink-0 items-center rounded-md bg-brand px-2.5 text-sm font-semibold text-white no-underline hover:bg-brand-hover"
                >
                  {t("open")}
                </a>
              </span>
            </span>
          </div>
        </div>
      )}
    </PopoverMenu>
  );
}
