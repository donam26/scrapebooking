"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { api, type OutcomeNightOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, useFmt } from "@/lib/format";
import type { Tone } from "@/lib/labels";
import { SUGGESTION_TONE, useMarketText } from "@/lib/market";
import { Badge, Card, EmptyState, ErrorBox, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "./ui";
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

/**
 * Đo kết quả gợi ý giá (roadmap 6.4): tỷ lệ áp dụng, gợi ý đúng hướng / cần xem lại sau đêm lưu trú
 * (theo công suất PMS thật), và kiểm tra lại 60 ngày (chạy lại luật trên giá đối thủ 7 ngày trước).
 */
export function SuggestionOutcomes({ ownHotelId }: { ownHotelId: number | null }) {
  const t = useTranslations("rms.outcomes");
  const { fmtInt, fmtMoney, fmtNight, fmtPct, fmtPriceShort, fmtShare } = useFmt();
  const { suggestionLabel, fmtChange } = useMarketText();
  const [all, setAll] = useState(false);
  const outcomes = useApi(`rms:outcomes:${DAYS}:${ownHotelId ?? ""}`, () => api.market.outcomes({ days: DAYS, own_hotel_id: ownHotelId }));
  const backtest = useApi(`rms:backtest:${DAYS}:${LEAD}:${ownHotelId ?? ""}`, () => api.market.backtest({ days: DAYS, lead: LEAD, own_hotel_id: ownHotelId }));
  const o = outcomes.data;
  const b = backtest.data;
  const error = outcomes.error ?? backtest.error;
  const nights = o ? [...o.nights].sort((x, y) => (x.stay_date < y.stay_date ? 1 : -1)) : [];
  const shown = all ? nights : nights.slice(0, RECENT);
  const scoredOutcomes = o ? nights.filter((n) => n.verdict === "good" || n.verdict === "review" || n.verdict === "neutral").length : 0;
  const scoredBacktest = b ? b.good + b.review : 0;

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
          </div>
          {nights.length > 0 && (
            <>
              <div className="border-t border-line px-5 pb-1 pt-3 text-xs font-semibold uppercase tracking-[0.05em] text-muted">{t("recent")}</div>
              <Table dense>
                <thead>
                  <tr>
                    <Th className="pl-5">{t("col.night")}</Th>
                    <Th>{t("col.suggestion")}</Th>
                    <Th>{t("col.decision")}</Th>
                    <Th right>{t("col.price")}</Th>
                    <Th right>{t("col.occ")}</Th>
                    <Th right>{t("col.adr")}</Th>
                    <Th className="pr-5">{t("col.verdict")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((n) => {
                    const set = num(n.applied_price) ?? num(n.target_price);
                    return (
                      <tr key={`${n.stay_date}:${n.kind}`} className={ROW_CLASS}>
                        <Td className="whitespace-nowrap pl-5 font-semibold text-ink tabular">{fmtNight(n.stay_date)}</Td>
                        <Td className="whitespace-nowrap">
                          {isKind(n.kind) ? <Badge tone={SUGGESTION_TONE[n.kind]}>{suggestionLabel(n.kind)}</Badge> : n.kind}
                          {n.change_pct !== 0 && <span className="ml-1.5 text-xs font-semibold text-body tabular">{fmtChange(n.change_pct)}</span>}
                        </Td>
                        <Td className="whitespace-nowrap text-sm">{n.decision === "applied" || n.decision === "dismissed" ? t(`decision.${n.decision}`) : n.decision}</Td>
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
              {nights.length > RECENT && (
                <button type="button" onClick={() => setAll((v) => !v)} className={cx("mx-5 my-3 text-sm font-semibold text-brand hover:underline")}>
                  {all ? t("showLess") : t("showAll", { count: nights.length })}
                </button>
              )}
            </>
          )}
        </>
      )}
    </Card>
  );
}
