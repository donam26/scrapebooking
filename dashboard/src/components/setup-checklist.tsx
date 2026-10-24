"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { api, type CompsetBalanceOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { num, useFmt } from "@/lib/format";
import { Button, Card, ErrorBox, cx } from "./ui";
import { IconAlert, IconCheck, IconChevronRight } from "./icons";

/**
 * Thẻ "Thiết lập 5 bước" cho cột phụ của Hôm nay (UX Phase 3, C1): khách sạn của bạn, ≥4 đối thủ,
 * vị trí giá, ai nhận cảnh báo, (tuỳ chọn) nhập PMS. Mỗi bước một link tới đúng tab Cài đặt, xong thì
 * có dấu ✓. Tự ẩn khi xong bước 1–4 hoặc khi quản trị bấm "Ẩn" (lưu ở backend, mọi người cùng thấy).
 * Chỉ quản trị khách sạn thấy (người xem không làm được các bước này).
 *
 * Bước 2 kèm ghi chú khi nhóm đối thủ đắt hơn bạn ≥1,6 lần (Q4).
 */
export function SetupChecklist({ className }: { className?: string }) {
  const t = useTranslations("setup");
  const { canWrite } = useSession();
  const q = useApi(canWrite ? "settings:setup" : null, () => api.settings.setup());
  const hide = useMutation(async () => {
    await api.settings.setSetupDismissed(true);
    q.reload();
  });
  const s = q.data;
  if (!canWrite || !s || s.done || s.dismissed_at) return null;

  const steps: Array<{ key: string; done: boolean; href: string; label: string; hint?: string; extra?: React.ReactNode }> = [
    { key: "own", done: s.own_hotel, href: "/settings?tab=watchlist", label: t("own"), hint: t("ownHint") },
    {
      key: "competitors",
      done: s.competitors >= s.competitors_needed,
      href: "/settings?tab=watchlist",
      label: t("competitors", { needed: s.competitors_needed }),
      hint: t("competitorsCount", { count: s.competitors, needed: s.competitors_needed }),
      extra: s.balance?.pricier ? <BalanceNote balance={s.balance} compact /> : null,
    },
    { key: "strategy", done: s.strategy, href: "/settings?tab=strategy", label: t("strategy"), hint: t("strategyHint") },
    { key: "alerts", done: s.alerts, href: "/settings?tab=notifications", label: t("alerts"), hint: t("alertsHint") },
    { key: "pms", done: s.pms, href: "/settings?tab=pms", label: t("pms"), hint: t("pmsHint") },
  ];
  const required = steps.slice(0, 4).filter((x) => x.done).length;

  return (
    <Card title={t("title")} description={t("progress", { done: required, total: 4 })} className={className}>
      <ol className="-mt-1 space-y-1">
        {steps.map((step, i) => (
          <li key={step.key}>
            <Link
              href={step.href}
              className={cx("group flex items-start gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-subtle", step.done && "opacity-80")}
              aria-label={step.done ? t("doneAria", { step: step.label }) : undefined}
            >
              <span
                aria-hidden
                className={cx(
                  "mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold tabular",
                  step.done ? "bg-yours-soft text-yours-deep" : "border border-line-strong bg-surface text-body",
                )}
              >
                {step.done ? <IconCheck size={14} /> : i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className={cx("block text-base font-semibold", step.done ? "text-muted line-through decoration-line-strong" : "text-ink group-hover:text-brand")}>{step.label}</span>
                {step.hint && <span className="block text-sm text-muted">{step.hint}</span>}
              </span>
              {!step.done && <IconChevronRight size={16} className="mt-1 shrink-0 text-faint group-hover:text-brand" />}
            </Link>
            {step.extra && <div className="mb-1 ml-11 mr-2">{step.extra}</div>}
          </li>
        ))}
      </ol>
      <ErrorBox error={hide.error} className="mt-2" />
      <div className="mt-3 flex items-center justify-between gap-3 border-t border-line pt-3">
        <span className="text-xs text-muted">{t("autoHide")}</span>
        <Button size="sm" variant="ghost" busy={hide.busy} onClick={() => void hide.run()}>
          {t("dismiss")}
        </Button>
      </div>
    </Card>
  );
}

/** Đường dẫn Khám phá thị trường sắp theo giá, gợi ý khách sạn cùng tầm giá với bạn. */
export function similarHotelsHref(b: CompsetBalanceOut): string {
  const q = new URLSearchParams({ sort: "price" });
  const own = num(b.own_price);
  const stars = num(b.own_stars ?? null);
  if (own !== null) q.set("near", String(Math.round(own)));
  if (stars !== null) q.set("stars", String(Math.round(stars)));
  return `/competitors/market?${q.toString()}`;
}

/**
 * Ghi chú "Nhóm đối thủ đắt hơn bạn nhiều" (Q4): giá giữa nhóm ≥1,6 lần giá bạn trong 14 đêm tới.
 * Dùng ở thẻ thiết lập (bước 2) và Cài đặt › Khách sạn & đối thủ.
 */
export function BalanceNote({ balance, compact }: { balance: CompsetBalanceOut; compact?: boolean }) {
  const t = useTranslations("setup.balance");
  const { fmtNum, fmtMoney } = useFmt();
  const ratio = num(balance.ratio) ?? 0;
  return (
    <div role="note" className={cx("flex items-start gap-2 rounded-lg border border-[#fcd34d] bg-warning-soft text-warning-deep", compact ? "px-3 py-2 text-sm" : "px-3.5 py-2.5 text-sm")}>
      <IconAlert size={15} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-semibold">{t("title", { ratio: fmtNum(ratio, 1) })}</p>
        <p className="mt-0.5">
          {t("body", { own: fmtMoney(num(balance.own_price), "VND"), comp: fmtMoney(num(balance.comp_price), "VND"), nights: balance.nights })}{" "}
          <Link href={similarHotelsHref(balance)} className="font-semibold underline hover:no-underline">
            {t("link")}
          </Link>
        </p>
      </div>
    </div>
  );
}
