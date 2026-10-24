"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { ApiError, api } from "@/lib/api";
import { useErrorMessage } from "@/lib/errors";
import { Button, ButtonLink, ErrorBox, Field, Input, Note } from "@/components/ui";
import { BrandMark, IconAlert, IconArrowRight, IconChevronLeft, IconLock } from "@/components/icons";
import { LocaleSwitcher } from "@/components/locale-switcher";

const MIN_LENGTH = 8;

function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="M4 4l16 16" />}
    </svg>
  );
}

/** Link thiếu, sai, đã dùng hoặc hết hạn: nói rõ và chỉ đường về đăng nhập. */
function LinkProblem({ title, body }: { title: string; body: string }) {
  const t = useTranslations("auth.setPassword");
  return (
    <div className="w-full max-w-[380px] space-y-5">
      <h1 className="text-2xl font-bold tracking-[-0.015em] text-ink">{t("title")}</h1>
      <Note tone="warn" icon={<IconAlert size={18} />}>
        <div role="alert">
          <div className="font-semibold">{title}</div>
          <div className="mt-0.5">{body}</div>
        </div>
      </Note>
      <ButtonLink href="/login" variant="primary" className="h-10 w-full" icon={<IconArrowRight size={16} />}>
        {t("toLogin")}
      </ButtonLink>
    </div>
  );
}

function SetPasswordForm() {
  const t = useTranslations("auth.setPassword");
  const tl = useTranslations("auth.login");
  const errorText = useErrorMessage();
  const router = useRouter();
  const token = useSearchParams().get("token")?.trim() ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  // Giữ lỗi gốc, dịch lúc render: đổi ngôn ngữ trên trang này thì câu lỗi đổi theo.
  const [error, setError] = useState<unknown>(null);

  if (!token) return <LinkProblem title={t("noTokenTitle")} body={t("noTokenBody")} />;
  // 400 = sai hoặc đã dùng, 410 = hết hạn: form không còn tác dụng.
  if (error instanceof ApiError && (error.status === 400 || error.status === 410)) {
    return <LinkProblem title={t("linkProblemTitle")} body={errorText(error)} />;
  }

  const tooShort = (submitted || password.length > 0) && password.length < MIN_LENGTH;
  const mismatch = (submitted || confirm.length > 0) && confirm !== password;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    if (password.length < MIN_LENGTH || password !== confirm) return;
    setBusy(true);
    setError(null);
    try {
      await api.auth.setPassword({ token, password });
      router.replace("/login?password=set");
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-[380px] space-y-5" noValidate>
      <div>
        <h1 className="text-2xl font-bold tracking-[-0.015em] text-ink">{t("title")}</h1>
        <p className="mt-1 text-base text-muted">{t("subtitle")}</p>
      </div>
      <Field
        label={t("password")}
        htmlFor="set-password"
        hint={tooShort ? <span className="text-danger">{t("tooShort")}</span> : t("passwordHint")}
      >
        <div className="relative">
          <Input
            id="set-password"
            type={show ? "text" : "password"}
            autoComplete="new-password"
            required
            minLength={MIN_LENGTH}
            autoFocus
            aria-invalid={tooShort || undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-10 pr-11"
          />
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            aria-pressed={show}
            aria-label={show ? tl("hidePassword") : tl("showPassword")}
            title={show ? tl("hidePassword") : tl("showPassword")}
            className="absolute right-1 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-md text-muted transition-colors hover:bg-sunken hover:text-ink"
          >
            <EyeIcon off={show} />
          </button>
        </div>
      </Field>
      <Field label={t("confirm")} htmlFor="set-password-confirm" hint={mismatch ? <span className="text-danger">{t("mismatch")}</span> : undefined}>
        <Input
          id="set-password-confirm"
          type={show ? "text" : "password"}
          autoComplete="new-password"
          required
          aria-invalid={mismatch || undefined}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="h-10"
        />
      </Field>
      <ErrorBox error={error} />
      <Button type="submit" variant="primary" busy={busy} className="h-10 w-full" icon={!busy ? <IconLock size={16} /> : undefined}>
        {busy ? t("submitting") : t("submit")}
      </Button>
      <p className="border-t border-line pt-4 text-sm text-muted">
        <Link href="/login" className="font-semibold text-brand hover:underline">
          {t("toLogin")}
        </Link>
      </p>
    </form>
  );
}

export default function SetPasswordPage() {
  const t = useTranslations("auth.login");
  return (
    <div className="flex min-h-screen flex-col bg-surface lg:flex-row">
      {/* Bảng thương hiệu như trang đăng nhập: dải trên cùng trên điện thoại, nửa trái trên máy tính */}
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
        <div className="relative mt-6 lg:my-auto">
          <p className="max-w-[26ch] text-lg font-semibold leading-snug text-white [text-wrap:balance] sm:text-xl lg:text-[28px] lg:leading-[1.25] lg:tracking-[-0.015em]">
            {t("tagline")}
          </p>
          <p className="mt-3 hidden max-w-[44ch] text-base leading-relaxed text-on-night-soft sm:block">{t("lead")}</p>
        </div>
        <p className="relative mt-8 hidden text-xs text-on-night-muted lg:block">{t("disclaimer")}</p>
      </aside>

      <main className="relative flex flex-1 items-start justify-center px-5 py-10 sm:px-8 lg:items-center lg:py-16">
        <Suspense fallback={null}>
          <div className="w-full max-w-[380px]">
            <div className="mb-6 flex justify-end lg:absolute lg:right-10 lg:top-8 lg:mb-0">
              <LocaleSwitcher variant="light" />
            </div>
            <SetPasswordForm />
          </div>
        </Suspense>
      </main>
    </div>
  );
}
