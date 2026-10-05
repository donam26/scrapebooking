"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { Button, ErrorBox, Field, Input, cx } from "@/components/ui";
import { BrandMark, IconArrowRight, IconChevronLeft, IconLock } from "@/components/icons";
import { LocaleSwitcher } from "@/components/locale-switcher";

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/dashboard";
  return raw;
}

/*
 * Bảng minh hoạ 7 đêm × 4 khách sạn bằng bốn dấu mức tin cậy.
 * Chỉ là hình minh hoạ (aria-hidden), không phải dữ liệu thật.
 */
type DemoCell = "e3" | "e2" | "e1" | "c" | "h" | "s";
// Ô "s" (hết phòng) hiện chữ auth.demo.soldOut.
const DEMO_ROWS: Array<{ id: string; self?: boolean; cells: Array<[DemoCell, string]> }> = [
  { id: "self", self: true, cells: [["e2", "5"], ["e3", "2"], ["h", ""], ["e3", "1"], ["s", ""], ["e2", "4"], ["h", ""]] },
  { id: "A", cells: [["e1", "12"], ["e2", "6"], ["c", "≥"], ["e3", "3"], ["e3", "1"], ["e1", "11"], ["c", "≥"]] },
  { id: "B", cells: [["h", ""], ["e3", "2"], ["s", ""], ["s", ""], ["s", ""], ["e2", "7"], ["h", ""]] },
  { id: "C", cells: [["c", "≥"], ["e2", "8"], ["e2", "5"], ["e3", "2"], ["e3", "3"], ["c", "≥"], ["e1", "14"]] },
];
const DEMO_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const CELL_CLASS: Record<DemoCell, string> = {
  e3: "sb-heat-1",
  e2: "sb-heat-2",
  e1: "sb-heat-4",
  c: "sb-mark-capped",
  h: "sb-mark-hidden",
  s: "sb-mark-sold_out",
};

function DemoBoard() {
  const t = useTranslations("auth.demo");
  return (
    <div className="w-full max-w-[380px] rounded-xl border border-white/10 bg-white/[0.04] p-4">
      <span className="sr-only">{t("srLabel")}</span>
      <div aria-hidden>
        <div className="mb-1.5 grid grid-cols-[72px_repeat(7,minmax(0,1fr))] gap-1 text-center text-2xs font-semibold text-on-night-muted">
          <span />
          {DEMO_DAYS.map((d) => (
            <span key={d} className={d === "sat" || d === "sun" ? "text-white" : undefined}>
              {t(`days.${d}`)}
            </span>
          ))}
        </div>
        <div className="space-y-1">
          {DEMO_ROWS.map((r) => (
            <div key={r.id} className="grid grid-cols-[72px_repeat(7,minmax(0,1fr))] items-center gap-1">
              <span className={cx("flex items-center gap-1.5 truncate text-2xs", r.self ? "font-bold text-white" : "text-on-night-soft")}>
                {r.self && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-white" />}
                {r.self ? t("self") : t("competitor", { letter: r.id })}
              </span>
              {r.cells.map(([k, txt], i) => (
                <span
                  key={i}
                  className={cx(
                    "grid h-6 place-items-center rounded-[5px] font-bold tabular leading-none",
                    CELL_CLASS[k],
                    k === "s" ? "text-[8px] tracking-[0.02em]" : "text-2xs",
                    k === "h" && "!bg-transparent",
                  )}
                >
                  {k === "s" ? t("soldOut") : txt}
                </span>
              ))}
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-2.5 text-2xs text-on-night-muted">
          <span>{t("caption")}</span>
          <span className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-[3px] sb-heat-1" /> {t("nearlyFull")}
            <span className="h-2.5 w-2.5 rounded-[3px] sb-mark-capped" /> {t("atLeast")}
            <span className="h-2.5 w-2.5 rounded-[3px] sb-mark-sold_out" /> {t("soldOutKey")}
          </span>
        </div>
      </div>
    </div>
  );
}

function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="M4 4l16 16" />}
    </svg>
  );
}

function LoginForm() {
  const t = useTranslations("auth.login");
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  // Giữ lỗi gốc, dịch lúc render: đổi ngôn ngữ trên trang này thì câu lỗi đổi theo.
  const [error, setError] = useState<unknown>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.auth.login({ email: email.trim(), password });
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-[380px] space-y-5" noValidate={false}>
      <div>
        <h1 className="text-2xl font-bold tracking-[-0.015em] text-ink">{t("title")}</h1>
        <p className="mt-1 text-base text-muted">{t("subtitle")}</p>
      </div>
      <Field label={t("email")} htmlFor="login-email">
        <Input
          id="login-email"
          type="email"
          autoComplete="username"
          inputMode="email"
          required
          autoFocus
          placeholder={t("emailPlaceholder")}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="h-10"
        />
      </Field>
      <Field label={t("password")} htmlFor="login-password">
        <div className="relative">
          <Input
            id="login-password"
            type={show ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-10 pr-11"
          />
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            aria-pressed={show}
            aria-label={show ? t("hidePassword") : t("showPassword")}
            title={show ? t("hidePassword") : t("showPassword")}
            className="absolute right-1 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-md text-muted transition-colors hover:bg-sunken hover:text-ink"
          >
            <EyeIcon off={show} />
          </button>
        </div>
      </Field>
      <ErrorBox error={error} />
      <Button type="submit" variant="primary" busy={busy} className="h-10 w-full" icon={!busy ? <IconLock size={16} /> : undefined}>
        {busy ? t("submitting") : t("submit")}
      </Button>
      <p className="border-t border-line pt-4 text-sm text-muted">{t("noAccount")}</p>
    </form>
  );
}

export default function LoginPage() {
  const t = useTranslations("auth.login");
  return (
    <div className="flex min-h-screen flex-col bg-surface lg:flex-row">
      {/* Bảng thương hiệu: dải trên cùng trên điện thoại, nửa trái trên máy tính */}
      <aside className="relative flex flex-col overflow-hidden bg-night px-5 py-5 text-on-night-soft sm:px-8 lg:w-[45%] lg:max-w-[640px] lg:px-12 lg:py-10">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: "radial-gradient(60% 50% at 85% 100%, rgba(10,63,168,0.55), transparent 70%), radial-gradient(40% 35% at 0% 0%, rgba(255,255,255,0.12), transparent 70%)" }}
        />
        <div className="relative flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2.5 rounded-md focus-visible:outline-white" aria-label={t("homeLink")}>
            <BrandMark size={30} onBlue />
            <span className="text-[19px] font-semibold tracking-[-0.01em] text-white">OTARadar</span>
          </Link>
          <Link href="/" className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-sm font-medium text-on-night-soft hover:text-white focus-visible:outline-white">
            <IconChevronLeft size={16} />
            <span className="hidden sm:inline">{t("backHome")}</span>
            <span className="sm:hidden">{t("backHomeShort")}</span>
          </Link>
        </div>

        <div className="relative mt-6 lg:mt-auto">
          <p className="max-w-[26ch] text-lg font-semibold leading-snug text-white [text-wrap:balance] sm:text-xl lg:text-[28px] lg:leading-[1.25] lg:tracking-[-0.015em]">
            {t("tagline")}
          </p>
          <p className="mt-3 hidden max-w-[44ch] text-base leading-relaxed text-on-night-soft sm:block">
            {t("lead")}
          </p>
        </div>

        <div className="relative mt-8 hidden lg:mb-auto lg:mt-10 lg:block">
          <DemoBoard />
        </div>

        <p className="relative mt-8 hidden text-xs text-on-night-muted lg:block">
          {t("disclaimer")}
        </p>
      </aside>

      <main className="relative flex flex-1 items-start justify-center px-5 py-10 sm:px-8 lg:items-center lg:py-16">
        <Suspense fallback={null}>
          <div className="w-full max-w-[380px]">
            <div className="mb-6 flex justify-end lg:absolute lg:right-10 lg:top-8 lg:mb-0">
              <LocaleSwitcher variant="light" />
            </div>
            <LoginForm />
            <Link href="/" className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline lg:hidden">
              {t("learnMore")} <IconArrowRight size={14} />
            </Link>
          </div>
        </Suspense>
      </main>
    </div>
  );
}
