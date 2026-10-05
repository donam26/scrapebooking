"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { api, type PaceNightOut } from "@/lib/api";
import { useMutation } from "@/lib/hooks";
import { useFmt } from "@/lib/format";
import { SUGGESTION_TONE, useMarketText } from "@/lib/market";
import { Badge, Button, cx } from "./ui";
import { IconCheck, IconClose } from "./icons";

/**
 * Một gợi ý giá: đêm, loại, mức thay đổi, lý do bằng số liệu, và hai thao tác ghi nhận.
 * Không tự đẩy giá: "Đã áp dụng" chỉ ghi lại để sau này đo được gợi ý nào có ích.
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
  const decide = useMutation(async (decision: "applied" | "dismissed") => {
    await api.market.decide(night.stay_date, s.kind, decision, s.hotel_id);
    onChanged();
  });
  const undo = useMutation(async () => {
    await api.market.undo(night.stay_date, s.kind, s.hotel_id);
    onChanged();
  });
  const title = `${fmtWeekday(night.stay_date)} ${fmtDateShort(night.stay_date)}`;
  const reasons = compact ? s.reasons.slice(0, 2) : s.reasons;

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
        <span className="text-xs text-muted">{s.confidence === "high" ? t("confidenceHigh") : t("confidenceMedium")}</span>
        {night.own_price && <span className="ml-auto text-sm text-muted tabular">{t("yourPrice", { price: fmtMoney(night.own_price, night.currency) })}</span>}
      </header>
      <ul className="mt-2 space-y-0.5 text-sm text-body">
        {reasons.map((r, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-faint" />
            <span>{r.charAt(0).toUpperCase() + r.slice(1)}</span>
          </li>
        ))}
      </ul>
      {(decide.error || undo.error) && <p role="alert" className="mt-2 text-sm text-danger">{decide.error ?? undo.error}</p>}
      {canWrite && (
        <footer className="mt-3 flex flex-wrap items-center gap-2">
          {s.decision ? (
            <>
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
            </>
          ) : (
            <>
              <Button size="sm" icon={<IconCheck size={15} />} busy={decide.busy} onClick={() => void decide.run("applied")}>
                {t("markApplied")}
              </Button>
              <Button size="sm" variant="ghost" icon={<IconClose size={15} />} disabled={decide.busy} onClick={() => void decide.run("dismissed")}>
                {t("dismiss")}
              </Button>
            </>
          )}
        </footer>
      )}
    </article>
  );
}
