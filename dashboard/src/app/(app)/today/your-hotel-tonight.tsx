"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { cellState, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { useFmt } from "@/lib/format";
import { cellOn, compsetDay, lastPrice, medianCompRate, selfRow } from "@/lib/market-metrics";
import { deltaVsMedian, useNightReason } from "@/lib/night-reason";
import { roomsLeftOf, roomsLeftText } from "@/lib/rooms-left";
import { useMarketText } from "@/lib/market";
import { MarkSwatch, useMarks } from "@/components/marks";
import { SampleTag, sampleFade } from "@/components/compset-sample";
import { KeyValueRow } from "@/components/kpi";
import { Card } from "@/components/ui";

/**
 * Khách sạn của bạn đêm nay. Số chính là giá bạn so giá giữa đối thủ (luôn có khi đủ mẫu), không
 * phải công suất (thường "không đủ số"). Công suất chỉ là một dòng, khi có PMS hoặc ước tính đủ tin cậy.
 */
export function YourHotelTonight({ o, night, today }: { o: OverviewOut; night: PaceNightOut | undefined; today: string }) {
  const t = useTranslations("today.yourHotel");
  const { fmtMoney } = useFmt();
  const { fmtRank } = useNightReason();
  const { ownOccText } = useMarketText();
  const { cellMark } = useMarks();
  const self = selfRow(o);
  if (!self) {
    return (
      <Card title={t("title")}>
        <p className="text-sm text-body">
          {t.rich("empty", {
            link: (c) => (
              <Link href="/settings?tab=watchlist" className="font-semibold text-brand hover:underline">
                {c}
              </Link>
            ),
          })}
        </p>
      </Card>
    );
  }
  const cell = cellOn(self, today);
  const own = lastPrice(cell);
  const market = medianCompRate(o, today);
  const c0 = compsetDay(o, today);
  const delta = deltaVsMedian(c0?.price_index);
  const rank = c0 ? fmtRank(c0.own_rank, c0.priced_hotels) : null;
  const rooms = roomsLeftOf(cell);
  const left = cellState(cell) === "sold_out" ? t("soldOut") : rooms === null ? null : t("rooms", { rooms: roomsLeftText(rooms) });
  const occ = night ? ownOccText(night) : null;
  const currency = cell?.currency ?? null;
  return (
    <Card title={t("title")} info={t("info")}>
      <div className="flex items-center gap-3 border-b border-line pb-4">
        <MarkSwatch mark={cellMark(cell)} size={36} />
        <div className="min-w-0">
          <div className="text-[28px] font-bold leading-tight text-ink tabular">{delta === null ? "—" : delta > 0 ? `+${delta}%` : delta < 0 ? `−${-delta}%` : "0%"}</div>
          <div className="text-sm text-muted">{delta === null ? t("noCompare") : t("deltaCaption")}</div>
        </div>
      </div>
      <div className="divide-y divide-line">
        <KeyValueRow
          label={t("yourRate")}
          value={
            own === null ? (
              "—"
            ) : (
              <span className={own.stale ? "text-muted" : undefined} title={own.stale ? t("staleTitle") : undefined}>
                {fmtMoney(own.value, currency)}
                {own.stale && <span className="ml-1 text-xs font-normal">{t("staleShort")}</span>}
              </span>
            )
          }
        />
        <KeyValueRow
          label={t("marketRate")}
          value={
            <span className="flex flex-col items-end">
              <span className={sampleFade(c0)}>{market === null ? "—" : fmtMoney(Math.round(market), currency)}</span>
              {c0 && <SampleTag c={c0} short className="text-xs font-normal" />}
            </span>
          }
        />
        <KeyValueRow label={t("roomsLeft")} value={left ?? t("hidden")} />
        {rank && <KeyValueRow label={t("rank")} value={rank} />}
        {occ && occ.source && <KeyValueRow label={occ.source === "pms" ? t("occPms") : t("occEstimate")} value={occ.text} />}
      </div>
    </Card>
  );
}
