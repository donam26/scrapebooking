"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import type { DemandSignalOut, OverviewOut, OwnDailyOut, PaceNightOut, WeatherOut } from "@/lib/api";
import { channelName } from "@/lib/channels";
import { addDays, dateRange, num, parseDate, useFmt } from "@/lib/format";
import { bookablePrice, cellOn, competitorRows, marketSnapshot, rowName, selfRow } from "@/lib/market-metrics";
import { Card, ErrorBox, cx } from "@/components/ui";
import { RingGauge } from "@/components/gauge";
import { IconCloud, IconPin, IconTrend } from "@/components/icons";

/** Bốn thẻ hàng đầu của Terminal+: chỉ báo thị trường, thời tiết, tín hiệu đặt phòng, doanh thu PMS. */

const CARD = "h-full";

/** Trạng thái thị trường theo công suất ước tính: mềm < 50%, cân bằng 50–74%, căng ≥ 75%. */
function marketMood(pct: number | null): { key: "noData" | "tight" | "balanced" | "soft"; cls: string; color: string } {
  if (pct === null) return { key: "noData", cls: "bg-sunken text-muted", color: "var(--sb-faint)" };
  if (pct >= 75) return { key: "tight", cls: "bg-hot-soft text-hot", color: "var(--sb-hot)" };
  if (pct >= 50) return { key: "balanced", cls: "bg-brand-soft text-brand", color: "var(--sb-brand)" };
  return { key: "soft", cls: "bg-yours-soft text-yours-deep", color: "var(--sb-yours)" };
}

export function MarketIndicator({ o, tonight }: { o: OverviewOut; tonight: PaceNightOut | undefined }) {
  const t = useTranslations("terminal");
  const { fmtCompact, fmtInt, fmtMoney, fmtWhen } = useFmt();
  const s = marketSnapshot(o);
  const self = selfRow(o);
  const occ = num(tonight?.comp_occ);
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
  const withRooms = o.hotels.filter((h) => {
    const c = cellOn(h, o.start);
    return c?.availability_status && c.availability_status !== "sold_out" && c.availability_status !== "unknown";
  }).length;
  const run = o.last_run;
  return (
    <Card
      className={CARD}
      title={city ? t("indicator.cityTitle", { city }) : t("indicator.title")}
      icon={<IconPin size={15} />}
      info={t("indicator.info")}
    >
      <div className="flex flex-col items-center">
        <RingGauge value={pct} color={mood.color} sub={t("occGauge")} />
        <span className={cx("mt-3 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.04em]", mood.cls)}>{t(`mood.${mood.key}`)}</span>
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
          <dt className="text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("indicator.avgRate")}</dt>
          <dd className="text-md font-bold text-ink tabular">{s.avgRate === null ? "—" : fmtCompact(s.avgRate)}</dd>
        </div>
      </dl>
      {prices.length > 1 && (
        <div className="mt-4">
          <div className="text-center text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("indicator.distribution")}</div>
          <div className="relative mt-2 h-2 rounded-full bg-[linear-gradient(90deg,#16a34a,#4ade80_35%,#f59e0b_65%,#ea7317_85%,#8b5cf6)]">
            {prices.map((p) => (
              <span
                key={p.name}
                title={`${p.name}: ${fmtMoney(p.v, "VND")}`}
                className={cx("absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow", p.self ? "bg-brand" : "bg-ink")}
                style={{ left: `${hi === lo ? 50 : ((p.v - lo) / (hi - lo)) * 100}%` }}
              />
            ))}
          </div>
          <div className="mt-1.5 flex justify-between text-[11px] text-muted tabular">
            <span>{fmtCompact(lo)}</span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-brand" /> {t("indicator.yours")}
            </span>
            <span>{fmtCompact(hi)}</span>
          </div>
        </div>
      )}
      {run && <p className="mt-3 text-center text-[11px] text-faint">{t("indicator.scannedAt", { when: fmtWhen(run.finished_at ?? run.started_at) })}</p>}
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
 * Tín hiệu đặt phòng từ kênh (thay thẻ chuyến bay của mẫu): "đặt N lần hôm nay" kênh công bố cho
 * các khách sạn đang theo dõi. Chỉ lấy tín hiệu thấy trong 24 giờ qua và chỉ một kênh (kênh có
 * nhiều khách sạn báo nhất) để không cộng lẫn thông điệp của các kênh. Luôn ghi nguồn.
 */
export function BookingSignalsCard({
  signals,
  loading,
  error,
}: {
  signals: Array<{ name: string; self: boolean; items: DemandSignalOut[] }>;
  loading: boolean;
  error?: unknown;
}) {
  const t = useTranslations("terminal.signals");
  const { fmtInt } = useFmt();
  const [since] = useState(() => Date.now() - 24 * 3600 * 1000);
  const fresh = (s: DemandSignalOut) => new Date(s.observed_at).getTime() >= since;
  const count = new Map<string, number>();
  for (const h of signals) for (const s of h.items) if (s.kind === "bookings_today" && fresh(s)) count.set(s.channel, (count.get(s.channel) ?? 0) + 1);
  const channel = [...count.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null;
  const pick = (h: (typeof signals)[number], kind: string) => h.items.find((s) => s.channel === channel && s.kind === kind && fresh(s));
  const today = signals
    .map((h) => ({ name: h.name, self: h.self, s: pick(h, "bookings_today"), d24: pick(h, "bookings_24h") }))
    .filter((h): h is typeof h & { s: DemandSignalOut } => h.s !== undefined)
    .map((h) => ({ name: h.name, self: h.self, n: Math.round(num(h.s.value) ?? 0), d24: h.d24 ? Math.round(num(h.d24.value) ?? 0) : null }))
    .sort((a, b) => b.n - a.n);
  const total = today.reduce((a, b) => a + b.n, 0);
  const with24 = today.filter((h) => h.d24 !== null);
  const day24 = with24.reduce((a, b) => a + (b.d24 ?? 0), 0);
  return (
    <Card className={CARD} title={t("title")} info={t("info")}>
      {error ? (
        <ErrorBox error={error} />
      ) : loading ? (
        <div className="h-40 sb-skeleton rounded-lg" />
      ) : today.length === 0 ? (
        <div className="flex min-h-[180px] flex-col items-center justify-center text-center text-sm text-muted">
          <IconTrend size={28} className="mb-2 text-faint" />
          {t("empty")}
        </div>
      ) : (
        <div className="text-center">
          <IconTrend size={26} className="mx-auto text-brand" />
          <div className="mt-1 text-[40px] font-bold leading-tight text-ink tabular">{fmtInt(total)}</div>
          <div className="text-sm text-muted">
            {with24.length === today.length && day24 ? t("summary24h", { hotels: today.length, day24: fmtInt(day24) }) : t("summary", { hotels: today.length })}
          </div>
          <ul className="mt-3 space-y-1 text-sm">
            {today.slice(0, 4).map((h) => (
              <li key={h.name} className="flex items-center justify-between gap-2">
                <span className={cx("truncate", h.self ? "font-semibold text-brand" : "text-body")}>{h.name}</span>
                <span className="font-semibold text-ink tabular">{fmtInt(h.n)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-faint">{t("source", { channel: channelName(channel) })}</p>
        </div>
      )}
    </Card>
  );
}

/**
 * Doanh thu 14 ngày: có PMS thì dùng doanh thu đã đặt (on-the-books); chưa có thì ước tính
 * = giá thấp nhất của bạn × công suất ước tính × tồn kho, chỉ trên đêm ước tính đủ tin cậy (ghi "≈").
 */
export function RevenueCard({ rows, nights, today, loading }: { rows: OwnDailyOut[]; nights: PaceNightOut[]; today: string; loading: boolean }) {
  const t = useTranslations("terminal.revenue");
  const { fmtCompact, fmtMoney } = useFmt();
  const days = dateRange(today, addDays(today, 13));
  // Mỗi đêm lấy bản nhập PMS mới nhất.
  const latest = new Map<string, OwnDailyOut>();
  for (const r of rows) {
    const d = String(r.stay_date);
    const prev = latest.get(d);
    if (!prev || r.imported_at > prev.imported_at) latest.set(d, r);
  }
  const pmsValues = days.map((d) => {
    const r = latest.get(d);
    if (!r) return null;
    const rev = num(r.revenue as string | null);
    if (rev !== null) return rev;
    const adr = num(r.adr as string | null);
    return adr !== null && r.rooms_sold !== null ? adr * r.rooms_sold : null;
  });
  const usePms = pmsValues.some((v) => v !== null);
  const byNight = new Map(nights.map((n) => [n.stay_date, n]));
  const estValues = days.map((d) => {
    const n = byNight.get(d);
    const price = num(n?.own_price);
    const occ = n?.own_occ;
    if (!n || price === null || !occ?.reliable) return null;
    return price * (num(occ.occ_mid) ?? 0) * occ.inventory;
  });
  const values = usePms ? pmsValues : estValues;
  const known = values.filter((v): v is number => v !== null);
  const total = known.reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...known);
  return (
    <Card
      className={CARD}
      title={t("title")}
      info={t("info")}
    >
      {loading ? (
        <div className="h-40 sb-skeleton rounded-lg" />
      ) : known.length === 0 ? (
        <div className="flex min-h-[180px] flex-col items-center justify-center text-center text-sm text-muted">
          {t("empty")}
          <Link href="/settings?tab=pms" className="mt-1 font-semibold text-brand hover:underline">
            {t("importPms")}
          </Link>
        </div>
      ) : (
        <div className="text-center">
          <div className="text-[32px] font-bold leading-tight text-brand tabular">
            {usePms ? "" : "≈"}
            {fmtCompact(total)}
          </div>
          <div className="text-sm text-muted">
            {t("caption", { source: usePms ? "pms" : "est", known: known.length })}
          </div>
          <div className="mt-4 flex h-16 items-end gap-1">
            {values.map((v, i) => (
              <span
                key={days[i]}
                title={`${parseDate(days[i]).getDate()}/${parseDate(days[i]).getMonth() + 1}: ${v === null ? t("barNoData") : `${usePms ? "" : "≈"}${fmtMoney(Math.round(v), "VND")}`}`}
                className={cx("flex-1 rounded-t-[3px]", v === null ? "bg-sunken" : "bg-brand")}
                style={{ height: `${v === null ? 12 : Math.max(10, (v / max) * 100)}%` }}
              />
            ))}
          </div>
          {!usePms && (
            <Link href="/settings?tab=pms" className="mt-2 inline-block text-[11px] font-semibold text-brand hover:underline">
              {t("importForActual")}
            </Link>
          )}
        </div>
      )}
    </Card>
  );
}
