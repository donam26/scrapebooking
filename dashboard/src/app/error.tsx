"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { Button, ButtonLink } from "@/components/ui";

/** Lỗi render không bắt được ở trang: báo theo ngôn ngữ đang chọn, cho thử lại. */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations("common.errorPage");
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main className="grid min-h-[60vh] place-items-center px-4">
      <div role="alert" className="max-w-md text-center">
        <h1 className="text-2xl font-bold text-ink">{t("title")}</h1>
        <p className="mt-2 text-base text-muted">{t("body")}</p>
        {error.digest && <p className="mt-1 text-sm text-faint tabular">{t("code", { digest: error.digest })}</p>}
        <div className="mt-6 flex justify-center gap-3">
          <Button variant="primary" onClick={reset}>
            {t("retry")}
          </Button>
          <ButtonLink href="/dashboard">{t("toDashboard")}</ButtonLink>
        </div>
      </div>
    </main>
  );
}
