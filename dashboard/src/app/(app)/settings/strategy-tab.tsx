"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { ApiError, api, type StrategyIn, type StrategyOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { num, useFmt } from "@/lib/format";
import { OwnHotelSwitcher, useOwnHotelParam, useOwnHotels } from "@/components/own-hotel";
import { Button, ButtonLink, Card, EmptyState, ErrorBox, Field, Input, Note, Select, Skeleton, cx } from "@/components/ui";
import { IconBuilding, IconCheck, IconInfo } from "@/components/icons";

/**
 * Cài đặt › Chiến lược giá (roadmap 6.1): giá gốc, sàn/trần, định vị mục tiêu so với trung vị giá
 * niêm yết compset, bước làm tròn, mức đổi tối đa mỗi ngày, điều chỉnh theo thứ, dịp lễ và sát ngày.
 * Gợi ý giá (Nhịp đặt phòng, Hôm nay) dùng chiến lược này; người xem chỉ đọc.
 */

const ROUND_OPTIONS = [0, 1000, 5000, 10000, 50000, 100000] as const;
/** 0 = thứ Hai … 6 = Chủ nhật (khớp `weekday_adj` ở backend). */
const WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"] as const;
type Weekday = (typeof WEEKDAYS)[number];

type Draft = {
  base: string;
  floor: string;
  ceiling: string;
  targetIndex: string;
  roundTo: number;
  maxChange: string;
  weekday: Record<Weekday, string>;
  holiday: string;
  lmDays: string;
  lmAdj: string;
};

function moneyDraft(v: string | null | undefined): string {
  const n = num(v);
  return n === null ? "" : String(Math.round(n));
}

function toDraft(s: StrategyOut): Draft {
  const wd = s.weekday_adj ?? {};
  return {
    base: moneyDraft(s.base_price),
    floor: moneyDraft(s.floor_price),
    ceiling: moneyDraft(s.ceiling_price),
    targetIndex: String(num(s.target_index) ?? 100),
    roundTo: s.round_to,
    maxChange: String(s.max_daily_change_pct),
    weekday: Object.fromEntries(WEEKDAYS.map((d) => [d, wd[d] ? String(wd[d]) : ""])) as Draft["weekday"],
    holiday: String(s.holiday_uplift_pct),
    lmDays: String(s.last_minute_days),
    lmAdj: String(s.last_minute_adj_pct),
  };
}

/** Số tiền gõ tay: bỏ dấu ngăn nghìn ("1.200.000" → 1200000); rỗng = null; sai = NaN. */
function money(raw: string): number | null {
  const v = raw.trim().replace(/[.,\s]/g, "");
  return v === "" ? null : Number(v);
}

/** Số nguyên gõ tay (chấp nhận dấu trừ "−"); rỗng = `empty`. */
function int(raw: string, empty: number): number {
  const v = raw.trim().replace("−", "-");
  return v === "" ? empty : Number(v);
}

function decimal(raw: string): number {
  return Number(raw.trim().replace(",", "."));
}

function inRange(n: number, lo: number, hi: number, integer = true): boolean {
  return Number.isFinite(n) && (!integer || Number.isInteger(n)) && n >= lo && n <= hi;
}

type InvalidKey = "price" | "floorCeiling" | "baseRange" | "targetIndex" | "maxChange" | "weekday" | "holiday" | "lastMinuteDays" | "lastMinuteAdj";

function validate(d: Draft): InvalidKey | null {
  const [base, floor, ceiling] = [money(d.base), money(d.floor), money(d.ceiling)];
  if ([base, floor, ceiling].some((v) => v !== null && !(Number.isFinite(v) && v > 0))) return "price";
  if (floor !== null && ceiling !== null && floor > ceiling) return "floorCeiling";
  if (base !== null && ((floor !== null && base < floor) || (ceiling !== null && base > ceiling))) return "baseRange";
  if (!inRange(decimal(d.targetIndex), 50, 200, false)) return "targetIndex";
  if (!inRange(int(d.maxChange, NaN), 1, 50)) return "maxChange";
  if (WEEKDAYS.some((w) => !inRange(int(d.weekday[w], 0), -30, 50))) return "weekday";
  if (!inRange(int(d.holiday, NaN), -30, 50)) return "holiday";
  if (!inRange(int(d.lmDays, NaN), 0, 14)) return "lastMinuteDays";
  if (!inRange(int(d.lmAdj, NaN), -30, 0)) return "lastMinuteAdj";
  return null;
}

function toBody(d: Draft): StrategyIn {
  const weekday: Record<string, number> = {};
  for (const w of WEEKDAYS) {
    const v = int(d.weekday[w], 0);
    if (v) weekday[w] = v;
  }
  return {
    base_price: money(d.base),
    floor_price: money(d.floor),
    ceiling_price: money(d.ceiling),
    target_index: decimal(d.targetIndex),
    round_to: d.roundTo,
    max_daily_change_pct: int(d.maxChange, 15),
    weekday_adj: weekday,
    holiday_uplift_pct: int(d.holiday, 0),
    last_minute_days: int(d.lmDays, 0),
    last_minute_adj_pct: int(d.lmAdj, 0),
  };
}

export function StrategyTab() {
  const t = useTranslations("rms.strategy");
  const { canWrite } = useSession();
  const ownHotels = useOwnHotels();
  const [hotelParam, setHotel] = useOwnHotelParam();
  const q = useApi(`rms:strategy:${hotelParam ?? ""}`, () => api.market.strategy.get(hotelParam));
  const noOwn = q.error instanceof ApiError && q.error.status === 404;

  return (
    <div className="space-y-5">
      {noOwn ? (
        <EmptyState
          icon={<IconBuilding />}
          title={t("noOwnTitle")}
          className="border border-line bg-surface"
          action={
            canWrite && (
              <ButtonLink href="/settings?tab=watchlist" variant="primary">
                {t("addOwn")}
              </ButtonLink>
            )
          }
        >
          {t("noOwnBody")}
        </EmptyState>
      ) : (
        <>
          <ErrorBox error={q.error} />
          <OwnHotelSwitcher hotels={ownHotels} value={hotelParam ?? q.data?.hotel_id ?? null} onChange={setHotel} />
          {!q.data && !q.error && <Skeleton rows={8} />}
          {q.data && <StrategyForm key={q.data.hotel_id} strategy={q.data} canWrite={canWrite} onSaved={q.reload} />}
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line pt-4 first:border-t-0 first:pt-0">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.05em] text-muted">{title}</h3>
      {children}
    </section>
  );
}

/** Ô số có hậu tố (%, ₫) bên phải. */
function Suffixed({ suffix, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { suffix: string }) {
  return (
    <span className={cx("relative block", className)}>
      <Input {...rest} className="pr-8 tabular" />
      <span aria-hidden className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted">
        {suffix}
      </span>
    </span>
  );
}

function StrategyForm({ strategy, canWrite, onSaved }: { strategy: StrategyOut; canWrite: boolean; onSaved: () => void }) {
  const t = useTranslations("rms.strategy");
  const { fmtMoney, fmtNum } = useFmt();
  const [d, setD] = useState<Draft>(() => toDraft(strategy));
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState(false);
  const invalid = validate(d);
  const save = useMutation(async () => {
    await api.market.strategy.put(toBody(d), strategy.hotel_id);
    setSaved(true);
    onSaved();
  });
  const set = (patch: Partial<Draft>) => {
    setSaved(false);
    save.clearError();
    setD((x) => ({ ...x, ...patch }));
  };
  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!invalid) void save.run();
  }
  const moneyHint = (raw: string, hint: string) => {
    const v = money(raw);
    return v !== null && Number.isFinite(v) && v > 0 ? `${fmtMoney(v, "VND")} · ${hint}` : hint;
  };
  const index = decimal(d.targetIndex);
  const preview = inRange(index, 50, 200, false) ? (Math.abs(index - 100) < 0.05 ? t("field.targetEqual") : t("field.targetPreview", { factor: fmtNum(index / 100, 2) })) : null;
  const bad = (...keys: InvalidKey[]) => (touched && invalid !== null && keys.includes(invalid)) || undefined;

  return (
    <Card title={t("title")} description={t("description")}>
      {!strategy.configured && (
        <Note tone="info" icon={<IconInfo size={16} />} className="mb-4">
          {t("defaults")}
        </Note>
      )}
      <form onSubmit={submit} noValidate className="space-y-5">
        <fieldset disabled={!canWrite} className="space-y-5">
          <Section title={t("sections.limits")}>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label={t("field.base")} hint={moneyHint(d.base, t("field.baseHint"))}>
                <Suffixed suffix="₫" inputMode="numeric" placeholder={t("field.optional")} value={d.base} onChange={(e) => set({ base: e.target.value })} aria-invalid={bad("price", "baseRange")} />
              </Field>
              <Field label={t("field.floor")} hint={moneyHint(d.floor, t("field.floorHint"))}>
                <Suffixed suffix="₫" inputMode="numeric" placeholder={t("field.optional")} value={d.floor} onChange={(e) => set({ floor: e.target.value })} aria-invalid={bad("price", "floorCeiling", "baseRange")} />
              </Field>
              <Field label={t("field.ceiling")} hint={moneyHint(d.ceiling, t("field.ceilingHint"))}>
                <Suffixed suffix="₫" inputMode="numeric" placeholder={t("field.optional")} value={d.ceiling} onChange={(e) => set({ ceiling: e.target.value })} aria-invalid={bad("price", "floorCeiling", "baseRange")} />
              </Field>
            </div>
          </Section>

          <Section title={t("sections.position")}>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label={t("field.targetIndex")} hint={t("field.targetIndexHint")}>
                <Input type="number" inputMode="decimal" min={50} max={200} step={1} value={d.targetIndex} onChange={(e) => set({ targetIndex: e.target.value })} aria-invalid={bad("targetIndex")} className="tabular" />
                {preview && <span className="text-xs font-semibold text-ink">{preview}</span>}
              </Field>
              <Field label={t("field.roundTo")}>
                <Select value={d.roundTo} onChange={(e) => set({ roundTo: Number(e.target.value) })}>
                  {!(ROUND_OPTIONS as readonly number[]).includes(d.roundTo) && <option value={d.roundTo}>{fmtMoney(d.roundTo, "VND")}</option>}
                  {ROUND_OPTIONS.map((r) => (
                    <option key={r} value={r}>
                      {r === 0 ? t("field.roundNone") : fmtMoney(r, "VND")}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={t("field.maxChange")} hint={t("field.maxChangeHint")}>
                <Suffixed suffix="%" type="number" inputMode="numeric" min={1} max={50} value={d.maxChange} onChange={(e) => set({ maxChange: e.target.value })} aria-invalid={bad("maxChange")} />
              </Field>
            </div>
          </Section>

          <Section title={t("sections.weekday")}>
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
              {WEEKDAYS.map((w) => (
                <label key={w} className="flex min-w-0 flex-col gap-1">
                  <span className={cx("text-center text-sm font-semibold", w === "4" || w === "5" ? "text-ink" : "text-body")}>{t(`weekday.${w}`)}</span>
                  <Suffixed
                    suffix="%"
                    type="number"
                    inputMode="numeric"
                    min={-30}
                    max={50}
                    placeholder="0"
                    aria-label={t("weekdayAria", { day: t(`weekday.${w}`) })}
                    value={d.weekday[w]}
                    onChange={(e) => set({ weekday: { ...d.weekday, [w]: e.target.value } })}
                    aria-invalid={(touched && invalid === "weekday" && !inRange(int(d.weekday[w], 0), -30, 50)) || undefined}
                  />
                </label>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-muted">{t("field.weekdayHint")}</p>
          </Section>

          <Section title={t("sections.special")}>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label={t("field.holiday")} hint={t("field.holidayHint")}>
                <Suffixed suffix="%" type="number" inputMode="numeric" min={-30} max={50} value={d.holiday} onChange={(e) => set({ holiday: e.target.value })} aria-invalid={bad("holiday")} />
              </Field>
              <Field label={t("field.lastMinuteDays")} hint={t("field.lastMinuteDaysHint")}>
                <Input type="number" inputMode="numeric" min={0} max={14} value={d.lmDays} onChange={(e) => set({ lmDays: e.target.value })} aria-invalid={bad("lastMinuteDays")} className="tabular" />
              </Field>
              <Field label={t("field.lastMinuteAdj")} hint={t("field.lastMinuteAdjHint")}>
                <Suffixed suffix="%" type="number" inputMode="numeric" min={-30} max={0} value={d.lmAdj} onChange={(e) => set({ lmAdj: e.target.value })} aria-invalid={bad("lastMinuteAdj")} />
              </Field>
            </div>
          </Section>
        </fieldset>

        <p className="text-sm text-muted">
          {t.rich("driftNote", {
            link: (c) => (
              <Link href="/settings?tab=notifications" className="font-semibold text-brand hover:underline">
                {c}
              </Link>
            ),
          })}
        </p>
        {touched && invalid && (
          <p role="alert" className="text-sm text-danger">
            {t(`invalid.${invalid}`)}
          </p>
        )}
        <ErrorBox error={save.error} />
        {canWrite && (
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" busy={save.busy}>
              {t("save")}
            </Button>
            {saved && (
              <span role="status" className="inline-flex items-center gap-1 text-sm text-yours-deep">
                <IconCheck size={15} /> {t("saved")}
              </span>
            )}
          </div>
        )}
      </form>
    </Card>
  );
}
