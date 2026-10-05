"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { LOCALES, LOCALE_NAME, type Locale } from "@/i18n/config";
import { setLocale } from "@/i18n/actions";
import { cx } from "./ui";

const VARIANT = {
  /** Nền trắng/xám (thẻ, trang đăng nhập). */
  light: { group: "border-line bg-surface", idle: "text-muted hover:text-ink", active: "bg-subtle text-ink" },
  /** Nền tối/xanh (thanh trên, landing). */
  onDark: { group: "border-white/25 bg-white/[0.08]", idle: "text-white/75 hover:text-white", active: "bg-white/[0.22] text-white" },
} as const;

/**
 * Nút chuyển ngôn ngữ VI | EN: lưu cookie qua server action rồi `router.refresh()` để server render
 * lại bằng bản dịch mới; state phía client (form đang nhập, tab đang mở) được giữ nguyên.
 */
export function LocaleSwitcher({ variant = "light", className }: { variant?: keyof typeof VARIANT; className?: string }) {
  const locale = useLocale();
  const t = useTranslations("common.language");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const v = VARIANT[variant];

  function choose(next: Locale) {
    if (next === locale || pending) return;
    startTransition(async () => {
      await setLocale(next);
      router.refresh();
    });
  }

  return (
    <div role="group" aria-label={t("label")} aria-busy={pending || undefined} className={cx("inline-flex h-8 shrink-0 items-center rounded-full border p-0.5", v.group, className)}>
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          aria-pressed={l === locale}
          title={l === locale ? LOCALE_NAME[l] : t("switchTo", { name: LOCALE_NAME[l] })}
          onClick={() => choose(l)}
          className={cx("h-full rounded-full px-2.5 text-xs font-semibold uppercase tracking-[0.04em] transition-colors", l === locale ? v.active : v.idle)}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
