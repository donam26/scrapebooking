"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { api, type OutcomeNightOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { num, useFmt } from "@/lib/format";
import type { Tone } from "@/lib/labels";
import { SUGGESTION_TONE, useMarketText } from "@/lib/market";
import { Badge, Button, Card, EmptyState, ErrorBox, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "./ui";
import { IconTrend } from "./icons";

const DAYS = 60;
const LEAD = 7;
const RECENT = 8;

const VERDICT_TONE: Record<OutcomeNightOut["verdict"], Tone> = {
  good: "green",
  review: "amber",
  neutral: "gray",
  pending: "gray",
};

type SuggestionKind = keyof typeof SUGGESTION_TONE;

function isKind(k: string): k is SuggestionKind {
  return k === "raise" || k === "hold" || k === "lower";
}

/** Bảng đêm đã ghi quyết định; `onUndo` (đêm sắp tới) thêm nút Hoàn tác cạnh quyết định. */
function OutcomeTable({ nights, onUndo, undoing }: { nights: OutcomeNightOut[]; onUndo?: (n: OutcomeNightOut) => void; undoing?: string | null }) {
  const t = useTranslations("reports.outcomes.card");
  const { fmtMoney, fmtNight, fmtPct, fmtPriceShort } = useFmt();
  const { suggestionLabel, fmtChange } = useMarketText();
  return (
    <Table dense>
      <thead>
        <tr>
          <Th className="pl-5">{t("col.night")}</Th>
          <Th>{t("col.suggestion")}</Th>
          <Th>{t("col.decision")}</Th>
          <Th right>{t("col.price")}</Th>
          <Th right>{t("col.occ")}</Th>
          <Th right>
            <span title={t("adrTitle")}>{t("col.adr")}</span>
          </Th>
          <Th className="pr-5">{t("col.verdict")}</Th>
        </tr>
      </thead>
      <tbody>
        {nights.map((n) => {
          const set = num(n.applied_price) ?? num(n.target_price);
          const key = `${n.stay_date}:${n.kind}`;
          return (
            <tr key={key} className={ROW_CLASS}>
              <Td className="whitespace-nowrap pl-5 font-semibold text-ink tabular">{fmtNight(n.stay_date)}</Td>
              <Td className="whitespace-nowrap">
                {isKind(n.kind) ? <Badge tone={SUGGESTION_TONE[n.kind]}>{suggestionLabel(n.kind)}</Badge> : n.kind}
                {n.change_pct !== 0 && <span className="ml-1.5 text-xs font-semibold text-body tabular">{fmtChange(n.change_pct)}</span>}
              </Td>
              <Td className="whitespace-nowrap text-sm">
                {n.decision === "applied" || n.decision === "dismissed" ? t(`decision.${n.decision}`) : n.decision}
                {onUndo && (
                  <Button size="sm" variant="quiet" className="ml-2" busy={undoing === key} onClick={() => onUndo(n)}>
                    {t("undo")}
                  </Button>
                )}
              </Td>
              <Td right className="whitespace-nowrap">
                <span className="text-muted">{fmtPriceShort(n.own_price)}</span>
                {set !== null && n.decision === "applied" && (
                  <>
                    {" → "}
                    <span className="font-semibold text-ink">{fmtPriceShort(set)}</span>
                  </>
                )}
              </Td>
              <Td right>{n.actual_occ_pct === null ? "—" : fmtPct(n.actual_occ_pct, { digits: 0 })}</Td>
              <Td right>{n.actual_adr === null ? "—" : fmtMoney(n.actual_adr, "VND")}</Td>
              <Td className="pr-5">
                <Badge tone={VERDICT_TONE[n.verdict]} dot={n.verdict !== "pending"}>
                  {t(`verdict.${n.verdict}`)}
                </Badge>
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/**
 * Kết quả gợi ý giá (Báo cáo › Kết quả gợi ý, roadmap 6.4): tỷ lệ đã đổi giá, gợi ý đúng hướng / cần
 * xem lại sau đêm lưu trú (theo công suất PMS thật), và kiểm tra lại 60 ngày (chạy lại cách gợi ý trên
 * giá đối thủ 7 ngày trước).
 * `undoFrom` (hôm nay của tenant): tách các đêm từ ngày này thành "đêm sắp tới" có nút Hoàn tác.
 */
export function SuggestionOutcomes({ ownHotelId, undoFrom }: { ownHotelId: number | null; undoFrom?: string | null }) {
  const t = useTranslations("reports.outcomes.card");
  const { canWrite } = useSession();
  const { fmtInt, fmtShare } = useFmt();
  const [all, setAll] = useState(false);
  const [undoing, setUndoing] = useState<string | null>(null);
  const outcomes = useApi(`rms:outcomes:${DAYS}:${ownHotelId ?? ""}`, () => api.market.outcomes({ days: DAYS, own_hotel_id: ownHotelId }));
  const backtest = useApi(`rms:backtest:${DAYS}:${LEAD}:${ownHotelId ?? ""}`, () => api.market.backtest({ days: DAYS, lead: LEAD, own_hotel_id: ownHotelId }));
  const undo = useMutation(async (n: OutcomeNightOut) => {
    setUndoing(`${n.stay_date}:${n.kind}`);
    try {
      await api.market.undo(n.stay_date, n.kind);
      outcomes.reload();
    } finally {
      setUndoing(null);
    }
  });
  const o = outcomes.data;
  const b = backtest.data;
  const error = outcomes.error ?? backtest.error;
  const nights = o ? [...o.nights].sort((x, y) => (x.stay_date < y.stay_date ? 1 : -1)) : [];
  // Đêm sắp tới (gần trước) còn hoàn tác được; đêm đã qua (mới trước) chờ hoặc đã có kết quả.
  const upcoming = undoFrom ? nights.filter((n) => n.stay_date >= undoFrom).reverse() : [];
  const past = undoFrom ? nights.filter((n) => n.stay_date < undoFrom) : nights;
  const shown = all ? past : past.slice(0, RECENT);
  const scoredOutcomes = o ? nights.filter((n) => n.verdict === "good" || n.verdict === "review" || n.verdict === "neutral").length : 0;
  const scoredBacktest = b ? b.good + b.review : 0;
  const heading = "border-t border-line px-5 pb-1 pt-3 text-xs font-semibold uppercase tracking-[0.05em] text-muted";

  return (
    <Card title={t("title")} description={t("description", { days: DAYS })} info={t("info", { lead: LEAD })} padded={false}>
      <ErrorBox error={error} className="m-5" />
      {!error && (!o || !b) && <SkeletonBlock className="m-5 h-24 rounded-lg" />}
      {o && b && o.decided === 0 && b.nights === 0 && (
        <div className="p-5">
          <EmptyState icon={<IconTrend />} title={t("emptyTitle")} compact>
            {t("emptyBody")}
          </EmptyState>
        </div>
      )}
      {o && b && (o.decided > 0 || b.nights > 0) && (
        <>
          <div className="px-5 pb-4 pt-1">
            <StatStrip
              items={[
                {
                  label: t("applyRate"),
                  value: o.apply_rate === null ? "—" : fmtShare(o.apply_rate),
                  hint: t("applyRateHint", { applied: o.applied, decided: o.decided }),
                },
                { label: t("good"), value: fmtInt(o.good), hint: t("goodHint", { count: scoredOutcomes }), tone: o.good ? "good" : "default" },
                { label: t("review"), value: fmtInt(o.review), hint: t("reviewHint"), tone: o.review ? "warn" : "default" },
                {
                  label: t("backtest", { days: DAYS }),
                  value: b.hit_rate === null ? "—" : fmtShare(b.hit_rate),
                  hint: scoredBacktest ? t("backtestHint", { good: b.good, scored: scoredBacktest, raise: b.raise_nights, lower: b.lower_nights }) : t("backtestNone"),
                },
              ]}
            />
            {/* Đã ghi quyết định nhưng chưa đêm nào có số PMS sau lưu trú: nói vì sao chưa có kết quả. */}
            {scoredOutcomes === 0 && <p className="mt-3 text-sm text-muted">{t("emptyBody")}</p>}
          </div>
          {upcoming.length > 0 && (
            <>
              <div className={heading}>
                {t("upcoming")}
                <span className="ml-2 font-normal normal-case tracking-normal">{t("upcomingHint")}</span>
              </div>
              <OutcomeTable nights={upcoming} onUndo={canWrite ? (n) => void undo.run(n) : undefined} undoing={undoing} />
              {undo.error && (
                <p role="alert" className="px-5 py-2 text-sm text-danger">
                  {undo.error}
                </p>
              )}
            </>
          )}
          {past.length > 0 && (
            <>
              <div className={heading}>{undoFrom ? t("past") : t("recent")}</div>
              <OutcomeTable nights={shown} />
              {past.length > RECENT && (
                <button type="button" onClick={() => setAll((v) => !v)} className={cx("mx-5 my-3 text-sm font-semibold text-brand hover:underline")}>
                  {all ? t("showLess") : t("showAll", { count: past.length })}
                </button>
              )}
            </>
          )}
        </>
      )}
    </Card>
  );
}
