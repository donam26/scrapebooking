"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { api, type CalibrationOut, type PaceNightOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { isWeekend, num, useFmt } from "@/lib/format";
import { actionableSuggestions, pendingSuggestions, SUGGESTION_TONE, suggestionTarget, useMarketText } from "@/lib/market";
import { fillIndicator, fillReading } from "@/lib/market-metrics";
import { CalibrationNote, FillValue } from "@/components/fill";
import { OwnHotelSwitcher, useOwnHotelParam, useOwnHotels } from "@/components/own-hotel";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { SuggestionCard } from "@/components/market-suggestion";
import { OtbPanel } from "@/components/otb-panel";
import { SuggestionOutcomes } from "@/components/suggestion-outcomes";
import { Badge, ButtonLink, Card, EmptyState, ErrorBox, Note, PageHeader, PanelTitle, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "@/components/ui";
import { IconInfo, IconSliders, IconTrend } from "@/components/icons";

/** Nhịp thị trường từ chừng này điểm trở lên được nhấn (cùng ngưỡng với hàng giá so trung vị). */
const PACE_NOTABLE = 0.1;

function Summary({ nights, calibration }: { nights: PaceNightOut[]; calibration: CalibrationOut }) {
  const t = useTranslations("pace.summary");
  const tr = useTranslations("rms.pace");
  const { fmtNight } = useFmt();
  const { suggestionLabel } = useMarketText();
  const pending = actionableSuggestions(nights);
  const holds = pendingSuggestions(nights).length - pending.length;
  const next7 = nights.filter((n) => n.days_to_arrival >= 0 && n.days_to_arrival < 7);
  // Đêm có nhóm lead time sai số quá ngưỡng so PMS thì không tính (ẩn).
  const compOcc = next7.map((n) => fillIndicator(n, calibration)).filter((v): v is number => v !== null);
  const avg = compOcc.length ? compOcc.reduce((a, b) => a + b, 0) / compOcc.length : null;
  const fast = nights.filter((n) => (num(n.comp_pace.delta) ?? 0) >= PACE_NOTABLE);
  const paced = nights.filter((n) => n.comp_pace.delta !== null).length;
  const first = pending[0];
  return (
    <StatStrip
      className="mb-5"
      items={[
        {
          label: t("pendingLabel"),
          value: t("pendingValue", { count: pending.length }),
          hint: (
            <>
              {first ? t("pendingHint", { night: fmtNight(first.stay_date), suggestion: suggestionLabel(first.suggestion!.kind).toLowerCase() }) : t("pendingNone")}
              {holds > 0 && ` · ${tr("pendingHolds", { count: holds })}`}
            </>
          ),
        },
        {
          label: t("compSoldLabel"),
          value: avg === null ? "—" : `≈${Math.round(avg * 100)}%`,
          hint: avg === null ? t("compSoldNone") : t("compSoldHint", { count: compOcc.length }),
        },
        {
          label: t("fastLabel"),
          value: paced ? t("fastValue", { count: fast.length }) : "—",
          hint: paced ? t("fastHint", { pts: Math.round(PACE_NOTABLE * 100), count: paced }) : t("fastNone"),
          tone: fast.length ? "warn" : "default",
        },
        {
          label: t("pmsLabel"),
          value: calibration.status === "calibrated" ? t("pmsCalibrated") : "—",
          hint: calibration.status === "calibrated" ? <CalibrationNote calibration={calibration} /> : t("pmsNone"),
        },
      ]}
    />
  );
}

function NightRow({ n, ownHotelId, calibration }: { n: PaceNightOut; ownHotelId: number | null; calibration: CalibrationOut }) {
  const t = useTranslations("pace.row");
  const { fmtDateShort, fmtNight, fmtPriceShort } = useFmt();
  const { fmtPace, ownOccText, suggestionLabel } = useMarketText();
  const own = ownOccText(n);
  const pace = num(n.comp_pace.delta);
  const weekend = isWeekend(n.stay_date);
  const fill = fillReading(n, calibration);
  return (
    <tr className={ROW_CLASS}>
      <Td className="whitespace-nowrap pl-5">
        {ownHotelId ? (
          <Link href={`/hotels/${ownHotelId}/dates/${n.stay_date}`} className={cx("tabular hover:text-brand hover:underline", weekend ? "font-extrabold text-ink" : "font-semibold text-ink")}>
            {fmtNight(n.stay_date)}
          </Link>
        ) : (
          <span className="font-semibold text-ink tabular">{fmtDateShort(n.stay_date)}</span>
        )}
        {n.holiday && (
          <span className="mt-0.5 flex items-center gap-1 text-xs font-semibold text-ink">
            <span aria-hidden className="h-1 w-1 rounded-full bg-ink" />
            {n.holiday}
          </span>
        )}
      </Td>
      <Td className="whitespace-nowrap tabular">
        <span
          className={cx(own.source === null ? "text-faint" : "font-semibold text-ink")}
          title={own.source === "est" && n.own_occ ? t("estRange", { low: Math.round(Number(n.own_occ.occ_low) * 100), high: Math.round(Number(n.own_occ.occ_high) * 100) }) : undefined}
        >
          {own.text}
        </span>
        {own.source === "pms" && <span className="ml-1 text-xs text-muted">PMS</span>}
        {own.source === "est" && <span className="ml-1 text-xs text-muted">{t("est")}</span>}
      </Td>
      <Td className="whitespace-nowrap tabular">
        {fill.hidden || fill.value !== null ? (
          <>
            <FillValue reading={fill} className="font-semibold text-ink" />
            {!fill.hidden && <span className="ml-1 text-xs text-muted">{t("hotels", { count: n.comp_occ_hotels })}</span>}
          </>
        ) : (
          <span className="text-faint" title={t("compOccMissing")}>
            —
          </span>
        )}
      </Td>
      <Td right className="tabular">
        {n.comp_observed ? `${n.comp_sold_out}/${n.comp_observed}` : "—"}
      </Td>
      <Td right className="tabular">
        {n.comp_pickup_7d === null ? (
          <span className="text-faint" title={t("pickupMissing")}>
            —
          </span>
        ) : n.comp_pickup_7d < 0 ? (
          <span className="text-muted" title={t("pickupNegative")}>
            −{-n.comp_pickup_7d}
          </span>
        ) : (
          <span className="font-semibold text-ink">{n.comp_pickup_7d > 0 ? `+${n.comp_pickup_7d}` : "0"}</span>
        )}
        {n.comp_pickup_7d !== null && <span className="ml-1 text-xs text-muted">{t("hotels", { count: n.comp_pickup_hotels })}</span>}
      </Td>
      <Td className="whitespace-nowrap">
        {pace === null ? (
          <span className="text-faint" title={t("paceMissingTitle", { count: n.comp_pace.references })}>
            {t("paceMissing")}
          </span>
        ) : (
          <span className={cx("tabular", pace >= PACE_NOTABLE ? "font-extrabold text-warning-deep" : pace <= -PACE_NOTABLE ? "text-muted" : "font-semibold text-body")}>
            {fmtPace(pace)}
          </span>
        )}
      </Td>
      <Td className="whitespace-nowrap pr-5">
        {n.suggestion?.decision ? (
          <Badge tone="gray">{n.suggestion.decision === "applied" ? t("applied") : t("dismissed")}</Badge>
        ) : n.suggestion?.kind === "hold" ? (
          <span className="text-sm text-muted">{suggestionLabel("hold")}</span>
        ) : n.suggestion ? (
          <span className="inline-flex items-center gap-1.5">
            <Badge tone={SUGGESTION_TONE[n.suggestion.kind]}>{suggestionLabel(n.suggestion.kind)}</Badge>
            {suggestionTarget(n) !== null && <span className="text-sm font-semibold text-ink tabular">{fmtPriceShort(suggestionTarget(n), n.currency)}</span>}
          </span>
        ) : null}
      </Td>
    </tr>
  );
}

/** Nhịp đặt phòng: ước tính công suất, gợi ý giá và bảng từng đêm. `embedded`: nằm trong Terminal+. */
export function PaceView({ embedded = false }: { embedded?: boolean }) {
  const { start, end, days } = useDateRange();
  const { canWrite } = useSession();
  const t = useTranslations("pace.view");
  const tr = useTranslations("rms.pace");
  const { fmtDate } = useFmt();
  // Cùng khách sạn của bạn (`?hotel=`) với các ô khác trên màn (roadmap 5.5).
  const [hotelParam, setHotel] = useOwnHotelParam();
  const ownHotels = useOwnHotels();
  const { data, error, loading, reload } = useApi(`market:pace:${start}:${end}:${hotelParam ?? ""}`, () => api.market.pace({ start, end, own_hotel_id: hotelParam }));
  const switchers = (
    <>
      <OwnHotelSwitcher hotels={ownHotels} value={hotelParam ?? data?.own_hotel_id ?? null} onChange={setHotel} />
      <DateRangePicker />
    </>
  );
  const pending = data ? actionableSuggestions(data.nights) : [];
  const holds = data ? pendingSuggestions(data.nights).length - pending.length : 0;
  const ownHotelId = hotelParam ?? data?.own_hotel_id ?? null;
  const decided = data ? data.nights.filter((n) => n.suggestion?.decision) : [];
  const hasEstimates = data?.nights.some((n) => n.own_occ || n.comp_occ) ?? false;
  const subtitle = t("subtitle", { days, start: fmtDate(start) });

  return (
    <>
      {embedded ? (
        <div id="pace" className="mb-4 flex scroll-mt-4 flex-wrap items-end justify-between gap-3">
          <div>
            <PanelTitle>{t("embeddedTitle")}</PanelTitle>
            <p className="mt-1 text-sm text-muted">{subtitle}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">{switchers}</div>
        </div>
      ) : (
        <PageHeader title={t("title")} subtitle={subtitle} actions={switchers} />
      )}
      <ErrorBox error={error} className="mb-4" />
      {!data && !error && (
        <div aria-busy className="space-y-4">
          <SkeletonBlock className="h-[92px] w-full rounded-xl" />
          <SkeletonBlock className="h-64 w-full rounded-xl" />
        </div>
      )}
      {data && (
        <div className={cx("space-y-5 transition-opacity duration-200", loading && "opacity-60")}>
          <Note tone="info" icon={<IconInfo size={16} />}>
            {t("note")}
            {data.data_since && ` ${t("dataSince", { date: fmtDate(data.data_since) })}`}
          </Note>
          <Summary nights={data.nights} calibration={data.calibration} />

          <OtbPanel start={start} end={end} ownHotelId={ownHotelId} />

          <Card
            title={t("suggestionsTitle")}
            description={t("suggestionsDescription")}
            actions={
              <ButtonLink href="/settings?tab=strategy" size="sm" variant="quiet" icon={<IconSliders size={15} />}>
                {tr("strategyLink")}
              </ButtonLink>
            }
          >
            {pending.length === 0 ? (
              <EmptyState icon={<IconTrend />} title={t("suggestionsEmptyTitle")} compact>
                {t("suggestionsEmptyBody")}
              </EmptyState>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {pending.map((n) => (
                  <SuggestionCard key={n.stay_date} night={n} ownHotelId={data.own_hotel_id} canWrite={canWrite} onChanged={reload} />
                ))}
              </div>
            )}
            {holds > 0 && pending.length > 0 && <p className="mt-3 text-sm text-muted">{tr("holds", { count: holds })}</p>}
            {decided.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer text-sm font-semibold text-body">{t("decided", { count: decided.length })}</summary>
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  {decided.map((n) => (
                    <SuggestionCard key={n.stay_date} night={n} ownHotelId={data.own_hotel_id} canWrite={canWrite} onChanged={reload} compact />
                  ))}
                </div>
              </details>
            )}
          </Card>

          <SuggestionOutcomes ownHotelId={ownHotelId} />

          <Card
            title={t("nightsTitle")}
            description={
              <>
                {t("nightsDescription")} <CalibrationNote calibration={data.calibration} />
              </>
            }
            padded={false}
          >
            {!hasEstimates && (
              <div className="px-5 pt-4">
                <Note tone="neutral">{t("noEstimates")}</Note>
              </div>
            )}
            <Table dense>
              <thead>
                <tr>
                  <Th className="pl-5">{t("col.night")}</Th>
                  <Th>{t("col.you")}</Th>
                  <Th>{t("col.compSold")}</Th>
                  <Th right>{t("col.compSoldOut")}</Th>
                  <Th right>{t("col.compPickup")}</Th>
                  <Th>{t("col.pace")}</Th>
                  <Th className="pr-5">{t("col.suggestion")}</Th>
                </tr>
              </thead>
              <tbody>
                {data.nights.map((n) => (
                  <NightRow key={n.stay_date} n={n} ownHotelId={data.own_hotel_id} calibration={data.calibration} />
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
