"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "./ui";

/** `key`: khoá trong components.subTabs.tabs (tab dựng sẵn); hoặc truyền `label` đã dịch. */
type SubTabKey = "aiBriefs" | "events" | "outcomes" | "pace" | "compset" | "market" | "radar";
export type SubTabItem = { href: string; exact?: boolean } & ({ label: string } | { key: SubTabKey });

/**
 * Tab con dạng viên thuốc trong một tab chính (VD Báo cáo: Bản tin AI | Nhật ký thay đổi | …).
 * Màn hẹp: các viên xuống dòng trong khung, trang không cuộn ngang.
 */
export function SubTabs({ items, className }: { items: SubTabItem[]; className?: string }) {
  const t = useTranslations("components.subTabs");
  const pathname = usePathname();
  return (
    <nav aria-label={t("label")} className={cx("mb-4 flex w-fit max-w-full flex-wrap gap-0.5 rounded-lg bg-sunken p-0.5", className)}>
      {items.map((it) => {
        const on = pathname === it.href || (!it.exact && pathname.startsWith(`${it.href}/`));
        return (
          <Link
            key={it.href}
            href={it.href}
            aria-current={on ? "page" : undefined}
            className={cx(
              "whitespace-nowrap rounded-md px-3.5 py-1.5 text-sm font-semibold transition-colors",
              on ? "bg-surface text-ink shadow-[0_1px_2px_rgba(17,24,39,0.12)]" : "text-muted hover:text-ink",
            )}
          >
            {"label" in it ? it.label : t(`tabs.${it.key}`)}
          </Link>
        );
      })}
    </nav>
  );
}

/** Tab con của tab Báo cáo. */
export const REPORT_TABS: SubTabItem[] = [
  { href: "/insights", key: "aiBriefs" },
  { href: "/events", key: "events" },
  { href: "/reports/outcomes", key: "outcomes" },
  { href: "/reports/pace", key: "pace" },
];

/** Tab con của tab Đối thủ. */
export const COMPETITOR_TABS: SubTabItem[] = [
  { href: "/competitors", key: "compset", exact: true },
  { href: "/competitors/radar", key: "radar" },
  { href: "/competitors/market", key: "market" },
];
