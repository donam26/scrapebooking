"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { cellState, type CalibrationOut, type OverviewOut, type OwnDailyOut, type PaceNightOut, type WeatherOut } from "@/lib/api";
import { addDays, dateRange, num, useFmt } from "@/lib/format";
import type { FreshnessState } from "@/lib/freshness";
import { DEMAND_COLOR, DEMAND_SOFT, bookablePrice, cellOn, competitorRows, demandLevel, fillReading, marketSnapshot, rowName, selfRow } from "@/lib/market-metrics";
import { DataUpdated } from "@/components/freshness";
import { useFillText } from "@/components/fill";
import { SampleTag, sampleFade } from "@/components/compset-sample";
import { Card, ErrorBox, cx } from "@/components/ui";
import { RingGauge } from "@/components/gauge";
import { IconCloud, IconPin } from "@/components/icons";

/** Ba thẻ hàng đầu của Terminal+: chỉ báo compset, thời tiết, doanh thu PMS. */

const CARD = "h-full";

/** Trạng thái theo chỉ báo lấp đầy ≈ (0–100), cùng thang mức chung `DEMAND_THRESHOLDS`: mềm / cân bằng / căng. */
export function marketMood(pct: number | null): { key: "noData" | "tight" | "balanced" | "soft"; cls: string; color: string } {
  if (pct === null) return { key: "noData", cls: "bg-sunken text-muted", color: "var(--sb-faint)" };
  const level = demandLevel(pct);
  return { key: level === "high" ? "tight" : level === "moderate" ? "balanced" : "soft", cls: DEMAND_SOFT[level], color: DEMAND_COLOR[level] };
}

export function MarketIndicator({
  o,
  tonight,
  calibration,
  fresh,
}: {
  o: OverviewOut;
  tonight: PaceNightOut | undefined;
  calibration?: CalibrationOut;
  fresh: FreshnessState;
}) {
  const t = useTranslations("terminal");
  const { fmtInt, fmtMoney, fmtPriceShort } = useFmt();
  const { fillText, hiddenText } = useFillText();
  const s = marketSnapshot(o);
  const self = selfRow(o);
  const reading = fillReading(tonight, calibration);
  const occ = reading.value;
  const pct = occ === null ? null : Math.round(occ * 100);
  const mood = marketMood(pct);
  // "Ho Chi Minh Municipality" / "Ho Chi Minh City" → "Ho Chi Minh"
  const city = (self?.hotel.city ?? competitorRows(o)[0]?.hotel.city ?? "").replace(/\s+(municipality|city)$/i, "") || null;
  // Mọi khách sạn có giá đêm nay (cả của bạn), đặt lên dải phân bố giá.
  const prices = o.hotels
    .map((h) => ({ name: rowName(h), self: h.role === "self", v: bookablePrice(cellOn(h, o.start)) }))
    .filter((p): p is { name: string; self: boolean; v: number } => p.v !== null);
  const lo = Math.min(...prices.map((p) => p.v));
  const hi = Math.max(...prices.map((p) => p.v));
  const currency = s.currency ?? "VND";
  // Còn bán 1 đêm (không gồm hết phòng, bị hạn chế, không giá, lỗi).
  const withRooms = o.hotels.filter((h) => cellState(cellOn(h, o.start)) === "available").length;
  return (
    <Card
      className={CARD}
      title={city ? t("indicator.cityTitle", { city }) : t("indicator.title")}
      icon={<IconPin size={15} />}
      info={t("indicator.info")}
    >
      <div className="flex flex-col items-center" title={reading.hidden ? hiddenText(reading) : (fillText(reading) ?? undefined)}>
        <RingGauge value={pct} color={mood.color} sub={t("occGauge")} />
        {reading.low !== null && reading.high !== null && <span className="mt-1 text-[11px] text-muted tabular">{fillText(reading)}</span>}
        <span className={cx("mt-3 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.04em]", mood.cls)}>{reading.hidden ? t("indicator.fillHidden") : t(`mood.${mood.key}`)}</span>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div>
          <dt className="text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("indicator.roomsLeft")}</dt>
          <dd className="text-md font-bold text-ink tabular">{s.roomsKnown ? fmtInt(s.roomsLeft) : "—"}</dd>
        </div>
        <div>
          <dt className="text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("indicator.withRooms")}</dt>
          <dd className="text-md font-bold text-ink tabular">
            {withRooms}/{o.hotels.length}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("indicator.medianRate")}</dt>
          <dd className={cx("text-md font-bold text-ink tabular", sampleFade(s.compset))}>{s.medianRate === null ? "—" : fmtPriceShort(s.medianRate, currency)}</dd>
          {s.compset && (
            <dd className="text-[10px] leading-tight">
              <SampleTag c={s.compset} short />
            </dd>
          )}
        </div>
      </dl>
      {prices.length > 1 && (
        <div className="mt-4">
          <div className="text-center text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("indicator.distribution")}</div>
          <div className="relative mt-2 h-2 rounded-full bg-[linear-gradient(90deg,#16a34a,#4ade80_35%,#f59e0b_65%,#ea7317_85%,#8b5cf6)]">
            {prices.map((p) => (
              <span
                key={p.name}
                title={`${p.name}: ${fmtMoney(p.v, currency)}`}
                className={cx("absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow", p.self ? "bg-brand" : "bg-ink")}
                style={{ left: `${hi === lo ? 50 : ((p.v - lo) / (hi - lo)) * 100}%` }}
              />
            ))}
          </div>
          <div className="mt-1.5 flex justify-between text-[11px] text-muted tabular">
            <span>{fmtPriceShort(lo, currency)}</span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-brand" /> {t("indicator.yours")}
            </span>
            <span>{fmtPriceShort(hi, currency)}</span>
          </div>
        </div>
      )}
      {fresh.loaded && (
        <p className="mt-3 text-center text-[11px] text-faint">
          <DataUpdated f={fresh} />
        </p>
      )}
    </Card>
  );
}

/** Biểu tượng thời tiết theo mã icon OpenWeather (không tải ảnh ngoài). */
function weatherEmoji(icon: string): string {
  const code = icon.slice(0, 2);
  return { "01": "☀️", "02": "🌤️", "03": "⛅", "04": "☁️", "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "❄️", "50": "🌫️" }[code] ?? "🌡️";
}

export function WeatherCard({ data, error }: { data: WeatherOut | undefined; error: unknown }) {
  const t = useTranslations("terminal.weather");
  const { fmtWeekday } = useFmt();
  return (
    <Card className={CARD} title={t("title")} info={t("info")}>
      {error ? (
        <ErrorBox error={error} />
      ) : !data ? (
        <div className="h-40 sb-skeleton rounded-lg" />
      ) : !data.configured || data.error || !data.current ? (
        <div className="flex h-full min-h-[180px] flex-col items-center justify-center text-center text-sm text-muted">
          <IconCloud size={30} className="mb-2 text-faint" />
          {!data.configured ? (
            t.rich("needsKey", { code: (c) => <code className="mt-1 rounded bg-sunken px-1.5 py-0.5 text-xs">{c}</code> })
          ) : (
            (data.error ?? t("noForecast"))
          )}
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-center gap-3">
            <span className="text-[40px] leading-none" aria-hidden>
              {weatherEmoji(data.current.icon)}
            </span>
            <div>
              <div className="text-[30px] font-bold leading-none text-ink tabular">{Math.round(data.current.temp)}°C</div>
              <div className="mt-1 text-sm capitalize text-muted">{data.current.description}</div>
            </div>
          </div>
          <div className="mt-1 text-center text-xs text-muted">
            {data.location ? `${data.location} · ` : ""}
            {t("current", { feels: Math.round(data.current.feels_like), humidity: data.current.humidity })}
          </div>
          <ul className="mt-4 grid grid-cols-5 gap-1 border-t border-line pt-3 text-center">
            {data.days.slice(0, 5).map((d, i) => (
              <li key={d.date} title={i === 0 ? t("restOfToday", { description: d.description }) : d.description}>
                <div className="text-[11px] font-semibold uppercase text-muted">{i === 0 ? t("today") : fmtWeekday(d.date)}</div>
                <div className="my-0.5 text-lg" aria-hidden>
                  {weatherEmoji(d.icon)}
                </div>
                <div className="text-xs font-semibold text-ink tabular">{Math.round(d.temp_max)}°</div>
                <div className="text-[11px] text-muted tabular">{Math.round(d.temp_min)}°</div>
                {d.pop >= 0.3 && <div className="text-[10px] font-semibold text-brand tabular">{Math.round(d.pop * 100)}%</div>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/**
 * Doanh thu 14 ngày tới từ PMS (doanh thu đã đặt; thiếu doanh thu thì số phòng bán × ADR). Chưa có số
 * PMS thì không ước tính thay (giá niêm yết × chỉ báo lấp đầy không phải doanh thu): chỉ hiện lời mời
 * nhập dữ liệu PMS.
 */
export function RevenueCard({ rows, today, loading }: { rows: OwnDailyOut[]; today: string; loading: boolean }) {
  const t = useTranslations("terminal.revenue");
  const { fmtCompact, fmtMoney, fmtNight } = useFmt();
  const days = dateRange(today, addDays(today, 13));
  // Mỗi đêm lấy bản nhập PMS mới nhất.
  const latest = new Map<string, OwnDailyOut>();
  for (const r of rows) {
    const d = String(r.stay_date);
    const prev = latest.get(d);
    if (!prev || r.imported_at > prev.imported_at) latest.set(d, r);
  }
  const values = days.map((d) => {
    const r = latest.get(d);
    if (!r) return null;
    const rev = num(r.revenue as string | null);
    if (rev !== null) return rev;
    const adr = num(r.adr as string | null);
    return adr !== null && r.rooms_sold !== null ? adr * r.rooms_sold : null;
  });
  const known = values.filter((v): v is number => v !== null);
  const total = known.reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...known);
  if (!loading && known.length === 0) {
    return (
      <Card className={CARD} title={t("noPmsTitle")} info={t("noPmsInfo")}>
        <div className="flex min-h-[180px] flex-col items-center justify-center text-center text-sm text-muted">
          {t("noPms")}
          <Link href="/settings?tab=pms" className="mt-1 font-semibold text-brand hover:underline">
            {t("importPms")}
          </Link>
        </div>
      </Card>
    );
  }
  return (
    <Card className={CARD} title={t("title")} info={t("info")}>
      {loading ? (
        <div className="h-40 sb-skeleton rounded-lg" />
      ) : (
        <div className="text-center">
          <div className="text-[32px] font-bold leading-tight text-brand tabular">{fmtCompact(total)}</div>
          <div className="text-sm text-muted">{t("caption", { known: known.length })}</div>
          <div className="mt-4 flex h-16 items-end gap-1">
            {values.map((v, i) => (
              <span
                key={days[i]}
                title={`${fmtNight(days[i])}: ${v === null ? t("barNoData") : fmtMoney(Math.round(v), "VND")}`}
                className={cx("flex-1 rounded-t-[3px]", v === null ? "bg-sunken" : "bg-brand")}
                style={{ height: `${v === null ? 12 : Math.max(10, (v / max) * 100)}%` }}
              />
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
