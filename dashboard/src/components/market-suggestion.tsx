"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type PaceNightOut, type ReasonOut } from "@/lib/api";
import { useMutation } from "@/lib/hooks";
import { num, useFmt } from "@/lib/format";
import { SUGGESTION_TONE, adjustmentText, mainReason, suggestionTarget, useMarketText } from "@/lib/market";
import { Badge, Button, cx } from "./ui";
import { IconAlert, IconCheck, IconClose } from "./icons";

const CLAMPS = ["floor", "ceiling", "max_change", "no_lower_tight"] as const;
type Clamp = (typeof CLAMPS)[number];

/** "+5%" / "−5%" với dấu trừ thật. */
function signedPct(pct: number): string {
  return pct > 0 ? `+${pct}%` : `−${-pct}%`;
}

/** Chỉ giữ chữ số: "3.700.000" / "3,700,000" -> "3700000". */
function digits(raw: string): string {
  return raw.replace(/\D/g, "");
}

/**
 * Một gợi ý giá: đêm, loại, GIÁ MỤC TIÊU bằng tiền (backend đã tính theo chiến lược giá), lý do
 * bằng lời, và thao tác ghi nhận kèm giá thật sự đã đặt. Không tự đẩy giá: "Tôi đã đổi giá" chỉ ghi
 * lại để đo được gợi ý nào có ích. Đã ghi thì thẻ thu lại một dòng, còn nút "Hoàn tác" tại chỗ.
 *
 * `brief`: chỉ một câu lý do chính (Việc cần làm hôm nay); cách tính đầy đủ nằm trong "Cách tính".
 * `staleSince`: dữ liệu Booking.com đã cũ (ISO lần đọc cuối) thì làm mờ và khoá thao tác.
 */
export function SuggestionCard({
  night,
  ownHotelId,
  canWrite,
  onChanged,
  compact,
  brief,
  staleSince,
  title,
}: {
  night: PaceNightOut;
  ownHotelId: number | null;
  canWrite: boolean;
  onChanged: () => void;
  compact?: boolean;
  brief?: boolean;
  staleSince?: string | null;
  /** Thay tiêu đề đêm (VD "Đêm nay"). */
  title?: string;
}) {
  const t = useTranslations("components.marketSuggestion");
  const { fmtDateShort, fmtMoney, fmtWeekday, fmtWhen, fmtInt } = useFmt();
  const { fmtChange, suggestionBadge } = useMarketText();
  const s = night.suggestion!;
  const target = suggestionTarget(night);
  const [applying, setApplying] = useState(false);
  const [price, setPrice] = useState("");
  const [priceError, setPriceError] = useState(false);
  const decide = useMutation(async (decision: "applied" | "dismissed", appliedPrice?: number | null) => {
    await api.market.decide(night.stay_date, s.kind, decision, appliedPrice);
    setApplying(false);
    onChanged();
  });
  const undo = useMutation(async () => {
    await api.market.undo(night.stay_date, s.kind);
    onChanged();
  });
  const heading = title ?? `${fmtWeekday(night.stay_date)} ${fmtDateShort(night.stay_date)}`;
  const reference = num(s.reference_price);
  const clamp = CLAMPS.includes(s.clamped as Clamp) ? (s.clamped as Clamp) : null;
  // Điều chỉnh có % trước (đó là phần làm giá đổi), dòng thông tin sau.
  const adjustments = [...s.adjustments]
    .filter((r) => !r.key.startsWith("clamp_") && r.key !== "no_lower_tight")
    .sort((a, b) => Number(a.pct === null) - Number(b.pct === null));
  const shown: ReasonOut[] = brief ? [] : compact ? adjustments.slice(0, 3) : adjustments;
  const legacy = adjustments.length === 0 ? (compact || brief ? s.reasons.slice(0, brief ? 1 : 2) : s.reasons) : [];
  const main = brief ? mainReason(s) : null;
  const stale = !!staleSince;
  const lowConfidence = s.confidence === "low";

  function startApply() {
    setPrice(target !== null ? fmtInt(Math.round(target)) : "");
    setPriceError(false);
    setApplying(true);
  }

  function confirmApply(e: FormEvent) {
    e.preventDefault();
    const raw = digits(price);
    if (raw === "") return void decide.run("applied", null);
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return setPriceError(true);
    void decide.run("applied", n);
  }

  // Đã ghi quyết định: một dòng gọn, vẫn hoàn tác được tại chỗ.
  if (s.decision) {
    return (
      <article className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line bg-subtle px-4 py-2.5">
        <span className="text-sm font-bold text-ink">{heading}</span>
        <span role="status" className={cx("inline-flex items-center gap-1 text-sm font-semibold", s.decision === "applied" ? "text-yours-deep" : "text-muted")}>
          {s.decision === "applied" ? (
            <>
              <IconCheck size={15} /> {t("applied")}
            </>
          ) : (
            t("dismissed")
          )}
        </span>
        {canWrite && (
          <Button size="sm" variant="quiet" busy={undo.busy} onClick={() => void undo.run()} className="ml-auto">
            {t("undo")}
          </Button>
        )}
        {undo.error && <p role="alert" className="w-full text-sm text-danger">{undo.error}</p>}
      </article>
    );
  }

  return (
    <article className={cx("rounded-xl border border-line bg-surface p-4", stale && "border-dashed opacity-70")}>
      <header className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        {ownHotelId ? (
          <Link href={`/hotels/${ownHotelId}/dates/${night.stay_date}`} className="text-md font-bold text-ink hover:text-brand hover:underline">
            {heading}
          </Link>
        ) : (
          <span className="text-md font-bold text-ink">{heading}</span>
        )}
        <Badge tone={SUGGESTION_TONE[s.kind]}>{suggestionBadge(s)}</Badge>
        {s.change_pct !== 0 && <span className="rounded-md bg-sunken px-1.5 py-0.5 text-sm font-bold text-ink tabular">{fmtChange(s.change_pct)}</span>}
        {lowConfidence && <span className="text-xs font-semibold text-warning-deep">{t("confidenceLow")}</span>}
      </header>
      {target !== null && (
        <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-sm text-muted">{s.kind === "hold" ? t("holdAt") : t("target")}</span>
          <span className="text-lg font-bold text-ink tabular">{fmtMoney(target, night.currency)}</span>
          <span className="text-sm text-muted tabular">{t("basis", { price: fmtMoney(night.own_price, night.currency) })}</span>
        </div>
      )}
      {main && <p className="mt-1.5 text-sm text-body">{main}</p>}
      {(shown.length > 0 || legacy.length > 0) && (
        <ul className="mt-2 space-y-0.5 text-sm text-body">
          {shown.map((r, i) => (
            <li key={`${r.key}${i}`} className="flex items-start gap-2">
              <span aria-hidden className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-faint" />
              <span className={cx("min-w-0 flex-1", r.pct === null && "text-muted")}>{adjustmentText(r)}</span>
              {r.pct !== null && r.pct !== 0 && <span className="shrink-0 rounded bg-sunken px-1.5 text-xs font-bold leading-5 text-ink tabular">{signedPct(r.pct)}</span>}
            </li>
          ))}
          {legacy.map((r, i) => (
            <li key={`legacy${i}`} className="flex gap-2">
              <span aria-hidden className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-faint" />
              <span>{r.charAt(0).toUpperCase() + r.slice(1)}</span>
            </li>
          ))}
        </ul>
      )}
      {clamp && (
        <p className="mt-1.5 flex items-start gap-1.5 text-xs font-semibold text-warning-deep">
          <IconAlert size={13} className="mt-px shrink-0" /> {t(`clamp.${clamp}`)}
        </p>
      )}
      {s.restrictions.length > 0 && !brief && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-muted">{t("restrictions")}:</span>
          {s.restrictions.map((r, i) => (
            <span key={i} className="sb-mark-restricted rounded-md px-2 py-0.5 text-xs font-semibold">
              {r.charAt(0).toUpperCase() + r.slice(1)}
            </span>
          ))}
        </div>
      )}
      {brief && (adjustments.length > 0 || reference !== null) && (
        <details className="mt-1.5 text-sm">
          <summary className="cursor-pointer text-xs font-semibold text-muted hover:text-ink">{t("howComputed")}</summary>
          <ul className="mt-1.5 space-y-0.5 text-body">
            {reference !== null && (
              <li className="text-muted tabular">{t("reference", { price: fmtMoney(reference, night.currency) })}</li>
            )}
            {adjustments.map((r, i) => (
              <li key={`${r.key}${i}`} className="flex items-start gap-2">
                <span className={cx("min-w-0 flex-1", r.pct === null && "text-muted")}>{adjustmentText(r)}</span>
                {r.pct !== null && r.pct !== 0 && <span className="shrink-0 text-xs font-bold text-ink tabular">{signedPct(r.pct)}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
      {stale && <p className="mt-2 text-xs font-semibold text-warning-deep">{t("staleNote", { when: fmtWhen(staleSince) })}</p>}
      {decide.error && <p role="alert" className="mt-2 text-sm text-danger">{decide.error}</p>}
      {canWrite && (
        <footer className="mt-3">
          {applying ? (
            <form onSubmit={confirmApply} noValidate className="flex flex-wrap items-end gap-2 rounded-lg bg-subtle p-2.5">
              <label className="flex min-w-0 flex-col gap-1">
                <span className="text-xs font-semibold text-body">{t("applyPrice")}</span>
                <input
                  type="text"
                  inputMode="numeric"
                  autoFocus
                  value={price}
                  onChange={(e) => {
                    const d = digits(e.target.value);
                    setPrice(d === "" ? "" : fmtInt(Number(d)));
                    setPriceError(false);
                  }}
                  aria-invalid={priceError || undefined}
                  className={cx(
                    "h-8 w-36 rounded-md border bg-surface px-2 text-sm font-semibold text-ink tabular focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15",
                    priceError ? "border-danger" : "border-line-strong",
                  )}
                />
              </label>
              <Button type="submit" size="sm" variant="primary" icon={<IconCheck size={15} />} busy={decide.busy}>
                {t("confirm")}
              </Button>
              <Button size="sm" variant="ghost" disabled={decide.busy} onClick={() => setApplying(false)}>
                {t("cancel")}
              </Button>
              <p className={cx("w-full text-xs", priceError ? "text-danger" : "text-muted")}>{priceError ? t("invalidPrice") : t("applyHint")}</p>
            </form>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" icon={<IconCheck size={15} />} busy={decide.busy} disabled={stale} title={stale ? t("staleDisabled") : undefined} onClick={startApply}>
                {t("markApplied")}
              </Button>
              <Button size="sm" variant="ghost" icon={<IconClose size={15} />} disabled={decide.busy || stale} onClick={() => void decide.run("dismissed")}>
                {t("dismiss")}
              </Button>
            </div>
          )}
        </footer>
      )}
    </article>
  );
}
