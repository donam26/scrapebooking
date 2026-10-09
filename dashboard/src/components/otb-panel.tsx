"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { api, type KpiOut, type OtbNightOut, type OtbOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, isWeekend, num, useFmt } from "@/lib/format";
import { ButtonLink, Card, EmptyState, ErrorBox, Note, ROW_CLASS, SkeletonBlock, StatStrip, Table, Td, Th, cx } from "./ui";
import { IconArrowRight, IconBuilding, IconUpload } from "./icons";

/**
 * OTB của khách sạn của bạn (roadmap Phase 5) — nửa còn lại của quyết định giá:
 * - KPI thật từ PMS 30 đêm qua (Công suất, ADR, RevPAR) — chỉ ở đây mới dùng các tên này.
 * - Theo đêm: OTB, pickup 1/7 ngày, so 4 tuần trước (cùng thứ, cùng lead), cùng kỳ năm trước
 *   (STLY), dự báo cộng pickup lịch sử.
 * `OtbPanel`: bản đầy đủ (Nhịp đặt phòng / Terminal+); `OtbCompact`: bản gọn (Hôm nay).
 */

const FIRST_ROWS = 14;
const IMPORT_HREF = "/settings?tab=pms#otb";

/** "+3" / "−2" / "0"; null → "—". */
function signed(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0";
}

/** Bạn đi trước kỳ tham chiếu: xanh; đi sau: hổ phách; bằng: trung tính. */
function deltaClass(n: number | null | undefined): string {
  if (n === null || n === undefined) return "text-faint";
  return n > 0 ? "font-semibold text-yours-deep" : n < 0 ? "font-semibold text-warning-deep" : "text-body";
}

function hasOtb(o: OtbOut): boolean {
  return o.as_of_date !== null && o.nights.some((n) => n.rooms_otb !== null);
}

/** Công suất OTB của cả kỳ (%), chỉ khi biết phòng sẵn có. */
function windowOcc(k: KpiOut): number | null {
  return num(k.occupancy_pct) ?? (k.rooms_available ? (k.rooms_sold / k.rooms_available) * 100 : null);
}

function useOtb(start: string, end: string, ownHotelId: number | null | undefined) {
  return useApi(`otb:${start}:${end}:${ownHotelId ?? ""}`, () => api.market.otb({ start, end, own_hotel_id: ownHotelId }));
}

function ImportEmpty({ compact }: { compact?: boolean }) {
  const t = useTranslations("otb.panel");
  const { canWrite } = useSession();
  return (
    <EmptyState
      icon={<IconUpload />}
      title={t("emptyTitle")}
      compact={compact}
      action={
        canWrite && (
          <ButtonLink href={IMPORT_HREF} variant="primary" size="sm" icon={<IconUpload size={15} />}>
            {t("importAction")}
          </ButtonLink>
        )
      }
    >
      {t("emptyBody")}
      {!canWrite && <span className="mt-1 block text-sm">{t("emptyViewer")}</span>}
    </EmptyState>
  );
}

function PmsKpis({ o, className }: { o: OtbOut; className?: string }) {
  const t = useTranslations("otb.panel.kpi");
  const { fmtInt, fmtMoney, fmtNum, fmtPct } = useFmt();
  const a = o.actual_30d;
  const w = o.otb_window;
  const pms = a.nights > 0;
  const occ = windowOcc(w);
  const idx = num(o.price_index_median);
  const items: Array<{ label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "default" | "good" | "warn" | "bad" }> = [
    { label: t("occ"), value: pms ? fmtPct(a.occupancy_pct) : "—", hint: pms ? t("occHint", { sold: fmtInt(a.rooms_sold), available: fmtInt(a.rooms_available) }) : t("noPms") },
    { label: t("adr"), value: pms ? fmtMoney(a.adr, "VND") : "—", hint: pms ? t("adrHint") : t("noPms") },
    { label: t("revpar"), value: pms ? fmtMoney(a.revpar, "VND") : "—", hint: pms ? t("revparHint") : t("noPms") },
  ];
  if (hasOtb(o)) {
    items.push({
      label: t("otb"),
      value: occ === null ? fmtInt(w.rooms_sold) : fmtPct(occ),
      hint: w.nights ? t("otbHint", { rooms: fmtInt(w.rooms_sold), revenue: fmtMoney(w.revenue, "VND") }) : t("otbNone"),
    });
  }
  items.push({
    label: t("index"),
    value: idx === null ? "—" : fmtNum(idx, 0),
    hint: idx === null ? t("indexNone") : t("indexHint", { count: o.price_index_nights }),
  });
  return <StatStrip items={items} className={className} />;
}

function NightRow({ n }: { n: OtbNightOut }) {
  const t = useTranslations("otb.panel");
  const { fmtNight, fmtPct, fmtPriceShort } = useFmt();
  const occ = num(n.occ_otb_pct);
  const fOcc = num(n.forecast_occ_pct);
  return (
    <tr className={ROW_CLASS}>
      <Td className={cx("whitespace-nowrap pl-5 tabular", isWeekend(n.stay_date) ? "font-extrabold text-ink" : "font-semibold text-ink")}>{fmtNight(n.stay_date)}</Td>
      <Td right className="whitespace-nowrap">
        {n.rooms_otb === null ? (
          <span className="text-faint">—</span>
        ) : (
          <>
            <span className="font-semibold text-ink">{t("rooms", { count: n.rooms_otb })}</span>
            {occ !== null && <span className="ml-1 text-xs text-muted">{fmtPct(occ, { digits: 0 })}</span>}
          </>
        )}
      </Td>
      <Td right>{n.adr_otb === null ? <span className="text-faint">—</span> : fmtPriceShort(n.adr_otb, "VND")}</Td>
      <Td right className={deltaClass(n.pickup_1d)}>
        {signed(n.pickup_1d)}
      </Td>
      <Td right className={deltaClass(n.pickup_7d)}>
        {signed(n.pickup_7d)}
      </Td>
      <Td right className="whitespace-nowrap" title={n.ref_4w !== null ? t("ref4w", { count: n.ref_4w }) : undefined}>
        <span className={deltaClass(n.pace_4w)}>{signed(n.pace_4w)}</span>
        {n.ref_4w !== null && <span className="ml-1 text-xs text-muted">/{n.ref_4w}</span>}
      </Td>
      <Td right className="whitespace-nowrap" title={n.stly !== null ? t("stlyRooms", { count: n.stly }) : undefined}>
        {n.stly === null ? (
          <span className="text-faint">—</span>
        ) : (
          <>
            <span className="text-body">{n.stly}</span>
            <span className={cx("ml-1.5", deltaClass(n.pace_stly))}>{signed(n.pace_stly)}</span>
          </>
        )}
      </Td>
      <Td right className="whitespace-nowrap pr-5" title={n.forecast_basis ? t("forecastBasis", { count: n.forecast_basis }) : undefined}>
        {n.forecast_rooms === null ? (
          <span className="text-faint">—</span>
        ) : (
          <>
            <span className="font-semibold text-ink">{fOcc !== null ? fmtPct(fOcc, { digits: 0 }) : t("rooms", { count: n.forecast_rooms })}</span>
            {fOcc !== null && <span className="ml-1 text-xs text-muted">{t("rooms", { count: n.forecast_rooms })}</span>}
          </>
        )}
      </Td>
    </tr>
  );
}

/** OTB đầy đủ: KPI PMS 30 ngày, OTB kỳ, chỉ số giá niêm yết và bảng từng đêm. */
export function OtbPanel({ start, end, ownHotelId }: { start: string; end: string; ownHotelId: number | null }) {
  const t = useTranslations("otb.panel");
  const { canWrite } = useSession();
  const { fmtDate } = useFmt();
  const [all, setAll] = useState(false);
  const { data: o, error, loading } = useOtb(start, end, ownHotelId);
  const nights = o ? o.nights : [];
  const shown = all ? nights : nights.slice(0, FIRST_ROWS);

  return (
    <Card
      title={t("title")}
      info={t("info")}
      description={o?.as_of_date ? t("asOf", { date: fmtDate(o.as_of_date) }) : undefined}
      padded={false}
      actions={
        o &&
        hasOtb(o) &&
        canWrite && (
          <ButtonLink href={IMPORT_HREF} size="sm" variant="quiet" icon={<IconUpload size={15} />}>
            {t("importAction")}
          </ButtonLink>
        )
      }
    >
      <ErrorBox error={error} className="m-5" />
      {!o && !error && <SkeletonBlock className="m-5 h-28 rounded-lg" />}
      {o && o.hotel_id === null && (
        <div className="p-5">
          <EmptyState
            icon={<IconBuilding />}
            title={t("noSelfTitle")}
            compact
            action={
              canWrite && (
                <ButtonLink href="/settings?tab=watchlist" size="sm">
                  {t("noSelfAction")}
                </ButtonLink>
              )
            }
          >
            {t("noSelfBody")}
          </EmptyState>
        </div>
      )}
      {o && o.hotel_id !== null && (
        <div className={cx("transition-opacity", loading && "opacity-60")}>
          <div className="px-5 pb-4 pt-1">
            <PmsKpis o={o} />
          </div>
          {!hasOtb(o) ? (
            <div className="px-5 pb-5">
              <ImportEmpty compact />
            </div>
          ) : (
            <>
              <Table dense>
                <thead>
                  <tr>
                    <Th className="pl-5">{t("col.night")}</Th>
                    <Th right>{t("col.otb")}</Th>
                    <Th right>{t("col.adr")}</Th>
                    <Th right>{t("col.pickup1")}</Th>
                    <Th right>{t("col.pickup7")}</Th>
                    <Th right>{t("col.pace4w")}</Th>
                    <Th right>{t("col.stly")}</Th>
                    <Th right className="pr-5">
                      {t("col.forecast")}
                    </Th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((n) => (
                    <NightRow key={n.stay_date} n={n} />
                  ))}
                </tbody>
              </Table>
              {nights.length > FIRST_ROWS && (
                <button type="button" onClick={() => setAll((v) => !v)} className="mx-5 my-3 text-sm font-semibold text-brand hover:underline">
                  {all ? t("showLess") : t("showAll", { count: nights.length })}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

/** OTB gọn cho Hôm nay: KPI PMS 30 ngày và 7 đêm tới (OTB, pickup 7 ngày, so năm trước, dự báo). */
export function OtbCompact({ today, ownHotelId = null }: { today: string; ownHotelId?: number | null }) {
  const t = useTranslations("otb.compact");
  const tp = useTranslations("otb.panel");
  const tk = useTranslations("otb.panel.kpi");
  const { canWrite } = useSession();
  const { fmtMoney, fmtNight, fmtPct } = useFmt();
  const { data: o, error } = useOtb(today, addDays(today, 6), ownHotelId);
  if (error) return <ErrorBox error={error} />;
  if (!o) return <SkeletonBlock className="h-36 w-full rounded-xl" />;
  if (o.hotel_id === null) return null;
  const a = o.actual_30d;
  const pms = a.nights > 0;
  const otb = hasOtb(o);
  // Chưa có cả số PMS lẫn OTB: một dòng gợi ý thay vì thẻ toàn ô trống.
  if (!pms && !otb) {
    return (
      <Note tone="neutral" icon={<IconUpload size={16} />}>
        {t("empty")}{" "}
        {canWrite && (
          <Link href={IMPORT_HREF} className="font-semibold text-brand hover:underline">
            {t("importLink")}
          </Link>
        )}
      </Note>
    );
  }
  const mini = [
    { label: tk("occ"), value: pms ? fmtPct(a.occupancy_pct) : "—" },
    { label: tk("adr"), value: pms ? fmtMoney(a.adr, "VND") : "—" },
    { label: tk("revpar"), value: pms ? fmtMoney(a.revpar, "VND") : "—" },
  ];
  return (
    <Card
      title={t("title")}
      info={tp("info")}
      actions={
        <Link href="/pace" className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
          {t("details")} <IconArrowRight size={14} />
        </Link>
      }
    >
      <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-line bg-line">
        {mini.map((m) => (
          <div key={m.label} className="min-w-0 bg-surface px-3 py-2.5">
            <dt className="truncate text-xs text-muted" title={m.label}>
              {m.label}
            </dt>
            <dd className="mt-0.5 text-base font-bold text-ink tabular">{m.value}</dd>
          </div>
        ))}
      </dl>
      {!pms && <p className="mt-2 text-xs text-muted">{tk("noPms")}</p>}
      {otb ? (
        <>
          <div className="mb-1 mt-4 text-xs font-semibold uppercase tracking-[0.05em] text-muted">{t("next")}</div>
          <ul className="divide-y divide-line">
            {o.nights.map((n) => {
              const occ = num(n.occ_otb_pct);
              const fOcc = num(n.forecast_occ_pct);
              return (
                <li key={n.stay_date} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2 text-sm">
                  <span className={cx("w-[68px] shrink-0 tabular", isWeekend(n.stay_date) ? "font-extrabold text-ink" : "font-semibold text-ink")}>{fmtNight(n.stay_date)}</span>
                  <span className="min-w-[88px] font-semibold text-ink tabular">
                    {n.rooms_otb === null ? "—" : occ !== null ? fmtPct(occ, { digits: 0 }) : tp("rooms", { count: n.rooms_otb })}
                    {n.rooms_otb !== null && occ !== null && <span className="ml-1 text-xs font-normal text-muted">{tp("rooms", { count: n.rooms_otb })}</span>}
                  </span>
                  <span className="text-muted tabular">
                    <span className={deltaClass(n.pickup_7d)}>{signed(n.pickup_7d)}</span> {t("pickup7")}
                  </span>
                  {n.pace_stly !== null && (
                    <span className="text-muted tabular" title={n.stly !== null ? tp("stlyRooms", { count: n.stly }) : undefined}>
                      <span className={deltaClass(n.pace_stly)}>{signed(n.pace_stly)}</span> {t("vsStly")}
                    </span>
                  )}
                  {n.forecast_rooms !== null && (
                    <span className="ml-auto text-muted tabular" title={n.forecast_basis ? tp("forecastBasis", { count: n.forecast_basis }) : undefined}>
                      {t("forecast")} <span className="font-semibold text-ink">{fOcc !== null ? fmtPct(fOcc, { digits: 0 }) : tp("rooms", { count: n.forecast_rooms })}</span>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted">
          {t("empty")}{" "}
          {canWrite && (
            <Link href={IMPORT_HREF} className="font-semibold text-brand hover:underline">
              {t("importLink")}
            </Link>
          )}
        </p>
      )}
    </Card>
  );
}
