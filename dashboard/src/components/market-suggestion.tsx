"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type PaceNightOut } from "@/lib/api";
import { useMutation } from "@/lib/hooks";
import { num, useFmt } from "@/lib/format";
import { SUGGESTION_TONE, adjustmentText, suggestionTarget, useMarketText } from "@/lib/market";
import { Badge, Button, cx } from "./ui";
import { IconAlert, IconCheck, IconClose } from "./icons";

const CLAMPS = ["floor", "ceiling", "max_change", "no_lower_tight"] as const;
type Clamp = (typeof CLAMPS)[number];

/** "+5%" / "−5%" với dấu trừ thật. */
function signedPct(pct: number): string {
  return pct > 0 ? `+${pct}%` : `−${-pct}%`;
}

/**
 * Một gợi ý giá (RMS-lite, roadmap 6.2–6.4): đêm, loại, GIÁ MỤC TIÊU bằng tiền (backend đã tính theo
 * chiến lược giá), giá tham chiếu, từng điều chỉnh có số và % cộng dồn, gợi ý hạn chế, ghi chú khi
 * bị chặn sàn/trần/mức đổi tối đa, và thao tác ghi nhận kèm giá thật sự đã đặt.
 * Không tự đẩy giá: "Đã áp dụng" chỉ ghi lại để đo được gợi ý nào có ích.
 */
export function SuggestionCard({
  night,
  ownHotelId,
  canWrite,
  onChanged,
  compact,
}: {
  night: PaceNightOut;
  ownHotelId: number | null;
  canWrite: boolean;
  onChanged: () => void;
  compact?: boolean;
}) {
  const t = useTranslations("components.marketSuggestion");
  const { fmtDateShort, fmtMoney, fmtWeekday } = useFmt();
  const { suggestionLabel, fmtChange } = useMarketText();
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
  const title = `${fmtWeekday(night.stay_date)} ${fmtDateShort(night.stay_date)}`;
  const reference = num(s.reference_price);
  const clamp = CLAMPS.includes(s.clamped as Clamp) ? (s.clamped as Clamp) : null;
  // Điều chỉnh có % trước (đó là phần làm giá đổi), dòng thông tin sau; bản gọn lấy 3 dòng đầu.
  const adjustments = [...s.adjustments].filter((r) => !r.key.startsWith("clamp_") && r.key !== "no_lower_tight").sort((a, b) => Number(a.pct === null) - Number(b.pct === null));
  const shown = compact ? adjustments.slice(0, 3) : adjustments;
  const legacy = adjustments.length === 0 ? (compact ? s.reasons.slice(0, 2) : s.reasons) : [];
  const confidence = s.confidence === "high" ? t("confidenceHigh") : s.confidence === "low" ? t("confidenceLow") : t("confidenceMedium");

  function startApply() {
    setPrice(target !== null ? String(Math.round(target)) : "");
    setPriceError(false);
    setApplying(true);
  }

  function confirmApply(e: FormEvent) {
    e.preventDefault();
    const raw = price.trim().replace(/[.,\s]/g, "");
    if (raw === "") return void decide.run("applied", null);
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return setPriceError(true);
    void decide.run("applied", n);
  }

  return (
    <article className={cx("rounded-xl border border-line bg-surface p-4", s.decision && "bg-subtle")}>
      <header className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        {ownHotelId ? (
          <Link href={`/hotels/${ownHotelId}/dates/${night.stay_date}`} className="text-md font-bold text-ink hover:text-brand hover:underline">
            {title}
          </Link>
        ) : (
          <span className="text-md font-bold text-ink">{title}</span>
        )}
        <Badge tone={SUGGESTION_TONE[s.kind]}>{suggestionLabel(s.kind)}</Badge>
        {s.change_pct !== 0 && <span className="rounded-md bg-sunken px-1.5 py-0.5 text-sm font-bold text-ink tabular">{fmtChange(s.change_pct)}</span>}
        <span className={cx("text-xs", s.confidence === "low" ? "font-semibold text-warning-deep" : "text-muted")}>{confidence}</span>
      </header>
      {target !== null && (
        <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-sm text-muted">{s.kind === "hold" ? t("holdAt") : t("target")}</span>
          <span className="text-lg font-bold text-ink tabular">{fmtMoney(target, night.currency)}</span>
          <span className="text-sm text-muted tabular">
            {t("basis", { price: fmtMoney(night.own_price, night.currency) })}
          </span>
          {reference !== null && (
            <span className="text-sm text-muted tabular" title={t("referenceTitle")}>
              · {t("reference", { price: fmtMoney(reference, night.currency) })}
            </span>
          )}
        </div>
      )}
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
      {s.restrictions.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-muted">{t("restrictions")}:</span>
          {s.restrictions.map((r, i) => (
            <span key={i} className="sb-mark-restricted rounded-md px-2 py-0.5 text-xs font-semibold">
              {r.charAt(0).toUpperCase() + r.slice(1)}
            </span>
          ))}
        </div>
      )}
      {(decide.error || undo.error) && <p role="alert" className="mt-2 text-sm text-danger">{decide.error ?? undo.error}</p>}
      {canWrite && (
        <footer className="mt-3">
          {s.decision ? (
            <div className="flex flex-wrap items-center gap-2">
              <span role="status" className="inline-flex items-center gap-1 text-sm font-semibold text-yours-deep">
                {s.decision === "applied" ? (
                  <>
                    <IconCheck size={15} /> {t("applied")}
                  </>
                ) : (
                  <span className="text-muted">{t("dismissed")}</span>
                )}
              </span>
              <Button size="sm" variant="quiet" busy={undo.busy} onClick={() => void undo.run()}>
                {t("undo")}
              </Button>
            </div>
          ) : applying ? (
            <form onSubmit={confirmApply} noValidate className="flex flex-wrap items-end gap-2 rounded-lg bg-subtle p-2.5">
              <label className="flex min-w-0 flex-col gap-1">
                <span className="text-xs font-semibold text-body">{t("applyPrice")}</span>
                <input
                  type="text"
                  inputMode="numeric"
                  autoFocus
                  value={price}
                  onChange={(e) => {
                    setPrice(e.target.value);
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
              <Button size="sm" icon={<IconCheck size={15} />} busy={decide.busy} onClick={startApply}>
                {t("markApplied")}
              </Button>
              <Button size="sm" variant="ghost" icon={<IconClose size={15} />} disabled={decide.busy} onClick={() => void decide.run("dismissed")}>
                {t("dismiss")}
              </Button>
            </div>
          )}
        </footer>
      )}
    </article>
  );
}
