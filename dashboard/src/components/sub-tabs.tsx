"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "./ui";

/** `key`: khoá trong components.subTabs.tabs (tab dựng sẵn); hoặc truyền `label` đã dịch. */
type SubTabKey = "aiBriefs" | "events" | "compset" | "market";
export type SubTabItem = { href: string; exact?: boolean } & ({ label: string } | { key: SubTabKey });

/** Tab con dạng viên thuốc trong một tab chính (VD Bản tin: Bản tin AI | Sự kiện thay đổi). */
export function SubTabs({ items, className }: { items: SubTabItem[]; className?: string }) {
  const t = useTranslations("components.subTabs");
  const pathname = usePathname();
  return (
    <nav aria-label={t("label")} className={cx("mb-4 inline-flex rounded-lg bg-sunken p-0.5", className)}>
      {items.map((it) => {
        const on = pathname === it.href || (!it.exact && pathname.startsWith(`${it.href}/`));
        return (
          <Link
            key={it.href}
            href={it.href}
            aria-current={on ? "page" : undefined}
            className={cx(
              "rounded-md px-3.5 py-1.5 text-sm font-semibold transition-colors",
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

/** Tab con của tab Bản tin. */
export const BRIEF_TABS: SubTabItem[] = [
  { href: "/insights", key: "aiBriefs" },
  { href: "/events", key: "events" },
];

/** Tab con của tab Đối thủ. */
export const COMPETITOR_TABS: SubTabItem[] = [
  { href: "/competitors", key: "compset", exact: true },
  { href: "/competitors/market", key: "market" },
];
