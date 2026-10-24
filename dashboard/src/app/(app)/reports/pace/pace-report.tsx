"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { ReactNode } from "react";
import { api, type CalibrationOut, type PaceNightOut } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { isWeekend, num, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { actionableSuggestions, useMarketText } from "@/lib/market";
import { fillIndicator, fillReading } from "@/lib/market-metrics";
import { CalibrationNote, FillValue } from "@/components/fill";
import { DataUpdated } from "@/components/freshness";
import { OwnHotelSwitcher, useOwnHotelParam, useOwnHotels } from "@/components/own-hotel";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { OtbPanel, hasOtb, useOtb } from "@/components/otb-panel";
import { REPORT_TABS, SubTabs } from "@/components/sub-tabs";
import { Badge, ButtonLink, Card, EmptyState, ErrorBox, Note, PageHeader, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "@/components/ui";
import { IconInfo, IconTrend, IconUpload } from "@/components/icons";
import { RevenueCard, revenueNights } from "./revenue-card";

/**
 * Báo cáo › Nhịp đặt phòng (Q5): bảng từng đêm (ẩn cột chưa có số, E2), đánh dấu "Có gợi ý" dẫn tới
 * trang đêm (gợi ý chỉ còn ở Hôm nay và trang đêm, S5), doanh thu 14 ngày và phòng đã đặt khi đã có
 * số PMS; chưa có thì một thẻ "Nhập PMS để mở…".
 */

const DEFAULT_DAYS = 14;
/** Nhịp thị trường từ chừng này điểm trở lên được nhấn (cùng ngưỡng với hàng giá so trung vị). */
const PACE_NOTABLE = 0.1;

type Col = "you" | "compSold" | "compSoldOut" | "compPickup" | "pace" | "suggestion";

function Summary({ nights, calibration }: { nights: PaceNightOut[]; calibration: CalibrationOut }) {
  const t = useTranslations("pace.summary");
  const pending = actionableSuggestions(nights);
  const next7 = nights.filter((n) => n.days_to_arrival >= 0 && n.days_to_arrival < 7);
  // Đêm có nhóm lead time sai số quá ngưỡng so PMS thì không tính (ẩn).
  const compOcc = next7.map((n) => fillIndicator(n, calibration)).filter((v): v is number => v !== null);
  const avg = compOcc.length ? compOcc.reduce((a, b) => a + b, 0) / compOcc.length : null;
  const fast = nights.filter((n) => (num(n.comp_pace.delta) ?? 0) >= PACE_NOTABLE);
  const paced = nights.filter((n) => n.comp_pace.delta !== null).length;
  const today = (c: ReactNode) => (
    <Link href="/today" className="font-semibold text-brand hover:underline">
      {c}
    </Link>
  );
  // Chỉ hiện ô có số (E2): ô "—" không giúp ra quyết định.
  const items: Parameters<typeof StatStrip>[0]["items"] = [
    {
      label: t("pendingLabel"),
      value: t("pendingValue", { count: pending.length }),
      hint: pending.length ? t.rich("pendingHint", { link: today }) : t("pendingNone"),
    },
  ];
  if (avg !== null) items.push({ label: t("compSoldLabel"), value: `≈${Math.round(avg * 100)}%`, hint: t("compSoldHint", { count: compOcc.length }) });
  if (paced) {
    items.push({
      label: t("fastLabel"),
      value: t("fastValue", { count: fast.length }),
      hint: t("fastHint", { pts: Math.round(PACE_NOTABLE * 100), count: paced }),
      tone: fast.length ? "warn" : "default",
    });
  }
  if (calibration.status === "calibrated") items.push({ label: t("pmsLabel"), value: t("pmsCalibrated"), hint: <CalibrationNote calibration={calibration} /> });
  // Chỉ có số đêm có gợi ý: một dòng thay cho dải số gần như trống.
  if (items.length === 1) {
    return (
      <Note tone="neutral" icon={<IconTrend size={16} />}>
        <span className="font-semibold text-ink">
          {t("pendingLabel")}: {t("pendingValue", { count: pending.length })}
        </span>
        {" · "}
        {pending.length ? t.rich("pendingHint", { link: today }) : t("pendingNone")}
      </Note>
    );
  }
  return <StatStrip items={items} />;
}

function NightRow({ n, ownHotelId, calibration, cols }: { n: PaceNightOut; ownHotelId: number | null; calibration: CalibrationOut; cols: Set<Col> }) {
  const t = useTranslations("pace.row");
  const { fmtDateShort, fmtNight } = useFmt();
  const { fmtPace, ownOccText } = useMarketText();
  const own = ownOccText(n);
  const pace = num(n.comp_pace.delta);
  const weekend = isWeekend(n.stay_date);
  const fill = fillReading(n, calibration);
  const s = n.suggestion;
  const nightHref = ownHotelId ? `/hotels/${ownHotelId}/dates/${n.stay_date}` : null;
  return (
    <tr className={ROW_CLASS}>
      <Td className="whitespace-nowrap pl-5">
        {nightHref ? (
          <Link href={nightHref} className={cx("tabular hover:text-brand hover:underline", weekend ? "font-extrabold text-ink" : "font-semibold text-ink")}>
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
      {cols.has("you") && (
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
      )}
      {cols.has("compSold") && (
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
      )}
      {cols.has("compSoldOut") && (
        <Td right className="tabular">
          {n.comp_observed ? `${n.comp_sold_out}/${n.comp_observed}` : "—"}
        </Td>
      )}
      {cols.has("compPickup") && (
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
      )}
      {cols.has("pace") && (
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
      )}
      {cols.has("suggestion") && (
        <Td className="whitespace-nowrap pr-5">
          {s?.decision ? (
            <Badge tone="gray">{s.decision === "applied" ? t("applied") : t("dismissed")}</Badge>
          ) : s && s.kind !== "hold" ? (
            nightHref ? (
              <Link href={nightHref} title={t("hasSuggestionTitle")} className="inline-flex rounded-md bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand hover:underline">
                {t("hasSuggestion")}
              </Link>
            ) : (
              <Badge tone="blue">{t("hasSuggestion")}</Badge>
            )
          ) : null}
        </Td>
      )}
    </tr>
  );
}

/** Thẻ duy nhất khi chưa có số PMS: thay cho doanh thu 14 ngày, phòng đã đặt và kết quả gợi ý. */
function PmsLock() {
  const t = useTranslations("reports.pmsLock");
  const { canWrite } = useSession();
  return (
    <EmptyState
      icon={<IconUpload />}
      title={t("title")}
      className="border border-line bg-surface"
      compact
      action={
        canWrite && (
          <ButtonLink href="/settings?tab=pms" variant="primary" size="sm" icon={<IconUpload size={15} />}>
            {t("action")}
          </ButtonLink>
        )
      }
    >
      {t("body")}
      {!canWrite && <span className="mt-1 block text-sm">{t("viewer")}</span>}
    </EmptyState>
  );
}

export function PaceReport() {
  const { start, end, days } = useDateRange(DEFAULT_DAYS);
  const t = useTranslations("pace.view");
  const { fmtDate } = useFmt();
  const { ownOccText } = useMarketText();
  const fresh = useDataFreshness();
  const today = useTenantToday();
  // Cùng khách sạn của bạn (`?hotel=`) với các ô khác trên màn (roadmap 5.5).
  const [hotelParam, setHotel] = useOwnHotelParam();
  const ownHotels = useOwnHotels();
  const { data, error, loading } = useApi(`market:pace:${start}:${end}:${hotelParam ?? ""}`, () => api.market.pace({ start, end, own_hotel_id: hotelParam }));
  const ownHotelId = hotelParam ?? data?.own_hotel_id ?? null;
  const otb = useOtb(start, end, hotelParam);
  const pmsHotel = otb.data?.hotel_id ?? null;
  const pms = useApi(pmsHotel ? `pms:daily:${pmsHotel}` : null, () => api.pms.daily(pmsHotel, 200));
  const revenue = today && pms.data ? revenueNights(pms.data, today) : null;
  const hasRevenue = !!revenue?.some((n) => n.value !== null);
  // "Đã có PMS": số PMS 30 ngày qua, phòng đã đặt theo ngày, hoặc doanh thu 14 ngày tới.
  const pmsReady = otb.data !== undefined && (otb.data.hotel_id === null || pmsHotel === null || pms.data !== undefined || pms.error !== undefined);
  const hasPms = !!otb.data && (otb.data.actual_30d.nights > 0 || hasOtb(otb.data) || hasRevenue);

  const nights = data?.nights ?? [];
  const calibration = data?.calibration;
  // E2: cột toàn "—" / "chưa đủ lịch sử" thì ẩn, ghi một dòng cột nào đã ẩn.
  const cols = new Set<Col>();
  if (calibration) {
    if (nights.some((n) => ownOccText(n).source !== null || n.own_status === "sold_out")) cols.add("you");
    if (nights.some((n) => {
      const f = fillReading(n, calibration);
      return f.hidden || f.value !== null;
    }))
      cols.add("compSold");
    if (nights.some((n) => n.comp_observed > 0)) cols.add("compSoldOut");
    if (nights.some((n) => n.comp_pickup_7d !== null)) cols.add("compPickup");
    if (nights.some((n) => n.comp_pace.delta !== null)) cols.add("pace");
    if (nights.some((n) => n.suggestion && (n.suggestion.decision || n.suggestion.kind !== "hold"))) cols.add("suggestion");
  }
  const hidden = (["you", "compSold", "compSoldOut", "compPickup", "pace"] as const).filter((c) => !cols.has(c));

  return (
    <>
      <SubTabs items={REPORT_TABS} />
      <PageHeader
        title={t("title")}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span>{t("subtitle", { days, start: fmtDate(start) })}</span>
            {fresh.loaded && (
              <>
                <span aria-hidden>·</span>
                <DataUpdated f={fresh} />
              </>
            )}
          </span>
        }
        actions={
          <>
            <OwnHotelSwitcher hotels={ownHotels} value={ownHotelId} onChange={setHotel} />
            <DateRangePicker defaultDays={DEFAULT_DAYS} />
          </>
        }
      />
      <ErrorBox error={error} className="mb-4" />
      {!data && !error && (
        <div aria-busy className="space-y-4">
          <SkeletonBlock className="h-[92px] w-full rounded-xl" />
          <SkeletonBlock className="h-64 w-full rounded-xl" />
        </div>
      )}
      {data && calibration && (
        <div className={cx("space-y-5 transition-opacity duration-200", loading && "opacity-60")}>
          <Summary nights={nights} calibration={calibration} />

          {/* Số PMS của bạn: doanh thu 14 ngày + phòng đã đặt; chưa có thì một thẻ mời nhập. */}
          <ErrorBox error={otb.error} />
          {!pmsReady && !otb.error ? (
            <SkeletonBlock className="h-36 w-full rounded-xl" />
          ) : hasPms ? (
            <>
              {hasRevenue && revenue && <RevenueCard nights={revenue} />}
              <OtbPanel state={otb} />
            </>
          ) : (
            !otb.error && <PmsLock />
          )}

          <Card
            title={t("nightsTitle")}
            description={
              <>
                {t("nightsDescription")}
                {/* Ghi chú hiệu chỉnh chỉ có nghĩa khi cột lấp đầy ≈ đang hiện. */}
                {cols.has("compSold") && (
                  <>
                    {" "}
                    <CalibrationNote calibration={calibration} />
                  </>
                )}
              </>
            }
            padded={false}
          >
            <div className="space-y-2 px-5 pb-3">
              {cols.has("compSold") && (
                <Note tone="info" icon={<IconInfo size={16} />}>
                  {t("note")}
                  {data.data_since && ` ${t("dataSince", { date: fmtDate(data.data_since) })}`}
                </Note>
              )}
              {!nights.some((n) => n.own_occ || n.comp_occ) && <Note tone="neutral">{t("noEstimates")}</Note>}
              {hidden.length > 0 && <p className="text-xs text-muted">{t("hiddenCols", { cols: hidden.map((c) => t(`col.${c}`)).join(", ") })}</p>}
            </div>
            <Table dense>
              <thead>
                <tr>
                  <Th className="pl-5">{t("col.night")}</Th>
                  {cols.has("you") && <Th>{t("col.you")}</Th>}
                  {cols.has("compSold") && <Th>{t("col.compSold")}</Th>}
                  {cols.has("compSoldOut") && <Th right>{t("col.compSoldOut")}</Th>}
                  {cols.has("compPickup") && <Th right>{t("col.compPickup")}</Th>}
                  {cols.has("pace") && <Th>{t("col.pace")}</Th>}
                  {cols.has("suggestion") && <Th className="pr-5">{t("col.suggestion")}</Th>}
                </tr>
              </thead>
              <tbody>
                {nights.map((n) => (
                  <NightRow key={n.stay_date} n={n} ownHotelId={ownHotelId} calibration={calibration} cols={cols} />
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
