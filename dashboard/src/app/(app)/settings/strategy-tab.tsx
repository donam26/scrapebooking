"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { ApiError, api, type MarketPaceOut, type StrategyIn, type StrategyOut } from "@/lib/api";
import { useApi, useMutation, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, num, useFmt } from "@/lib/format";
import { OwnHotelSwitcher, useOwnHotelParam, useOwnHotels } from "@/components/own-hotel";
import { Button, ButtonLink, Card, EmptyState, ErrorBox, Field, Input, Note, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconBuilding, IconCheck, IconInfo } from "@/components/icons";

/**
 * Cài đặt › Chiến lược giá (UX Phase 3, C7): bước 1 chọn vị trí giá bằng 4 thẻ (giữ như hiện nay /
 * rẻ hơn ~10% / ngang / cao hơn ~10% so với giá giữa của đối thủ), bước 2 (tuỳ chọn) sàn, trần, đổi tối
 * đa mỗi ngày; "Nâng cao" chứa giá gốc, làm tròn, theo thứ, dịp lễ, sát ngày. Khung "Xem trước 7 đêm
 * tới" gọi gợi ý với chiến lược nháp (không lưu) mỗi khi đổi, sau 400ms. Người xem chỉ đọc.
 */

const ROUND_OPTIONS = [0, 1000, 5000, 10000, 50000, 100000] as const;
/** 0 = thứ Hai … 6 = Chủ nhật (khớp `weekday_adj` ở backend). */
const WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"] as const;
type Weekday = (typeof WEEKDAYS)[number];
/** Ba vị trí sẵn (chỉ số giá niêm yết: giá bạn / giá giữa đối thủ × 100). */
const POSITIONS = [
  { key: "cheaper", index: 90 },
  { key: "level", index: 100 },
  { key: "higher", index: 110 },
] as const;
const PREVIEW_NIGHTS = 7;
const DEBOUNCE_MS = 400;

type Draft = {
  base: string;
  floor: string;
  ceiling: string;
  targetIndex: string;
  /** "Giữ như hiện nay": vị trí đi theo mức giá thường (tính lại mỗi ngày), tăng giá vẫn cần tín hiệu cầu. */
  followTypical: boolean;
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

/** Mức giá thường của bạn (30 đêm tới) cho thẻ "Giữ như hiện nay"; chưa tính được thì số đã lưu. */
function keepIndex(s: StrategyOut): number | null {
  return s.typical_index ?? (s.configured ? num(s.target_index) : null);
}

function toDraft(s: StrategyOut): Draft {
  const wd = s.weekday_adj ?? {};
  return {
    base: moneyDraft(s.base_price),
    floor: moneyDraft(s.floor_price),
    ceiling: moneyDraft(s.ceiling_price),
    targetIndex: String(s.configured && !s.follow_typical ? num(s.target_index) ?? 100 : keepIndex(s) ?? 100),
    followTypical: !s.configured || s.follow_typical,
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
    follow_typical: d.followTypical,
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

function Section({ step, title, hint, children }: { step?: number; title: string; hint?: string; children: ReactNode }) {
  const t = useTranslations("rms.strategy");
  return (
    <section className="border-t border-line pt-4 first:border-t-0 first:pt-0">
      <h3 className="flex items-center gap-2 text-base font-bold text-ink">
        {step && (
          <span aria-hidden className="grid h-6 w-6 place-items-center rounded-full bg-brand text-xs font-bold text-white tabular">
            {step}
          </span>
        )}
        {step && <span className="sr-only">{t("stepSr", { n: step })}</span>}
        {title}
      </h3>
      {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
      <div className="mt-3">{children}</div>
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

function PositionCard({ on, title, hint, onPick, disabled }: { on: boolean; title: string; hint: string; onPick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      disabled={disabled}
      onClick={onPick}
      className={cx(
        "flex min-w-0 flex-col items-start gap-1 rounded-xl border px-4 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed",
        on ? "border-brand bg-brand-softer ring-1 ring-brand/30" : "border-line bg-surface enabled:hover:border-line-strong",
      )}
    >
      <span className="flex w-full items-center justify-between gap-2">
        <span className="text-base font-bold text-ink">{title}</span>
        <span aria-hidden className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full border", on ? "border-brand bg-brand text-white" : "border-line-strong")}>
          {on && <IconCheck size={12} />}
        </span>
      </span>
      <span className="text-sm text-muted">{hint}</span>
    </button>
  );
}

function StrategyForm({ strategy, canWrite, onSaved }: { strategy: StrategyOut; canWrite: boolean; onSaved: () => void }) {
  const t = useTranslations("rms.strategy");
  const { fmtMoney, fmtNum } = useFmt();
  const [d, setD] = useState<Draft>(() => toDraft(strategy));
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState(false);
  const [advanced, setAdvanced] = useState(false);
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
  const keep = keepIndex(strategy);
  const keepRounded = keep === null ? null : Math.round(keep);
  // "Giữ như hiện nay" là một chế độ riêng (theo mức thường, cần tín hiệu cầu), luôn hiện khi tính được.
  const showKeep = keepRounded !== null;
  const picked = (v: number) => !d.followTypical && Math.abs(index - v) < 0.05;
  const custom = !d.followTypical && inRange(index, 50, 200, false) && !POSITIONS.some((p) => picked(p.index));
  const bad = (...keys: InvalidKey[]) => (touched && invalid !== null && keys.includes(invalid)) || undefined;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_400px] lg:items-start">
      <Card title={t("title")} description={t("description")}>
        {!strategy.configured && (
          <Note tone="info" icon={<IconInfo size={16} />} className="mb-4">
            {strategy.typical_index !== null && strategy.typical_index !== undefined ? t("defaults", { index: strategy.typical_index }) : t("defaultsNoTypical")}
          </Note>
        )}
        <form onSubmit={submit} noValidate className="space-y-5">
          <fieldset disabled={!canWrite} className="space-y-5">
            <Section step={1} title={t("sections.position")} hint={t("positionHint")}>
              <div role="radiogroup" aria-label={t("sections.position")} className={cx("grid gap-2", showKeep ? "sm:grid-cols-2" : "sm:grid-cols-3")}>
                {showKeep && keep !== null && (
                  <PositionCard on={d.followTypical} disabled={!canWrite} title={t("cards.keep", { index: keepRounded ?? 0 })} hint={t("cards.keepHint")} onPick={() => set({ followTypical: true, targetIndex: String(keep) })} />
                )}
                {POSITIONS.map((p) => (
                  <PositionCard
                    key={p.key}
                    on={picked(p.index)}
                    disabled={!canWrite}
                    title={t(`cards.${p.key}`)}
                    hint={keepRounded === p.index ? `${t(`cards.${p.key}Hint`)} ${t("cards.sameAsNow")}` : t(`cards.${p.key}Hint`)}
                    onPick={() => set({ followTypical: false, targetIndex: String(p.index) })}
                  />
                ))}
              </div>
              {custom && <p className="mt-2 text-sm text-body">{t("cards.custom", { index: fmtNum(index, 0) })}</p>}
            </Section>

            <Section step={2} title={t("sections.limits")} hint={t("limitsHint")}>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label={t("field.floor")} hint={moneyHint(d.floor, t("field.floorHint"))}>
                  <Suffixed suffix="₫" inputMode="numeric" placeholder={t("field.optional")} value={d.floor} onChange={(e) => set({ floor: e.target.value })} aria-invalid={bad("price", "floorCeiling", "baseRange")} />
                </Field>
                <Field label={t("field.ceiling")} hint={moneyHint(d.ceiling, t("field.ceilingHint"))}>
                  <Suffixed suffix="₫" inputMode="numeric" placeholder={t("field.optional")} value={d.ceiling} onChange={(e) => set({ ceiling: e.target.value })} aria-invalid={bad("price", "floorCeiling", "baseRange")} />
                </Field>
                <Field label={t("field.maxChange")} hint={t("field.maxChangeHint")}>
                  <Suffixed suffix="%" type="number" inputMode="numeric" min={1} max={50} value={d.maxChange} onChange={(e) => set({ maxChange: e.target.value })} aria-invalid={bad("maxChange")} />
                </Field>
              </div>
            </Section>

            <section className="border-t border-line pt-3">
              <button type="button" aria-expanded={advanced} onClick={() => setAdvanced((v) => !v)} className="text-sm font-semibold text-brand hover:underline">
                {advanced ? t("advancedHide") : t("advancedShow")}
              </button>
              {advanced && (
                <div className="mt-4 space-y-5">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field label={t("field.targetIndex")} hint={t("field.targetIndexHint")}>
                      <Suffixed suffix="%" type="number" inputMode="decimal" min={50} max={200} step={1} value={d.targetIndex} onChange={(e) => set({ followTypical: false, targetIndex: e.target.value })} aria-invalid={bad("targetIndex")} />
                    </Field>
                    <Field label={t("field.base")} hint={moneyHint(d.base, t("field.baseHint"))}>
                      <Suffixed suffix="₫" inputMode="numeric" placeholder={t("field.optional")} value={d.base} onChange={(e) => set({ base: e.target.value })} aria-invalid={bad("price", "baseRange")} />
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
                  </div>
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-body">{t("sections.weekday")}</h4>
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
                  </div>
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
                </div>
              )}
            </section>
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
      <Preview hotelId={strategy.hotel_id} body={invalid ? null : toBody(d)} />
    </div>
  );
}

/** "Xem trước 7 đêm tới": gợi ý với chiến lược nháp (không lưu), tải lại 400ms sau lần đổi cuối. */
function Preview({ hotelId, body }: { hotelId: number; body: StrategyIn | null }) {
  const t = useTranslations("rms.strategy.preview");
  const { fmtMoney, fmtNight, fmtNightRel, fmtSigned } = useFmt();
  const today = useTenantToday();
  const key = body && today ? JSON.stringify(body) : null;
  const [state, setState] = useState<{ key: string; data?: MarketPaceOut; error?: unknown } | null>(null);

  useEffect(() => {
    if (!key || !today || !body) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api.market.pacePreview(body, { start: today, end: addDays(today, PREVIEW_NIGHTS - 1), own_hotel_id: hotelId }).then(
        (data) => !cancelled && setState({ key, data }),
        (error: unknown) => !cancelled && setState({ key, error }),
      );
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // body đổi cùng key (JSON của body): không cần đưa body vào phụ thuộc.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, today, hotelId]);

  const loading = key !== null && state?.key !== key;
  const nights = state?.data?.nights ?? [];
  return (
    <Card title={t("title", { nights: PREVIEW_NIGHTS })} description={t("description")} padded={false} className="lg:sticky lg:top-4">
      {!body && <p className="px-5 pb-4 text-sm text-muted">{t("invalid")}</p>}
      {state?.error !== undefined && <ErrorBox error={state.error} className="mx-5 mb-4" />}
      {body && !state?.data && !state?.error && <Skeleton rows={4} className="px-5 pb-4" />}
      {state?.data && (
        <div aria-busy={loading || undefined} className={cx("transition-opacity", loading && "opacity-60")}>
          {nights.length === 0 ? (
            <p className="px-5 pb-4 text-sm text-muted">{t("empty")}</p>
          ) : (
            <Table dense>
              <thead>
                <tr>
                  <Th className="pl-5">{t("night")}</Th>
                  <Th right className="px-2">{t("yours")}</Th>
                  <Th right className="px-2">{t("suggested")}</Th>
                  <Th right className="pl-2 pr-5">
                    {t("change")}
                  </Th>
                </tr>
              </thead>
              <tbody>
                {nights.map((n) => {
                  const s = n.suggestion;
                  const own = num(n.own_price);
                  const target = s && s.kind !== "hold" ? num(s.target_price ?? null) : null;
                  return (
                    <tr key={n.stay_date}>
                      <Td className="whitespace-nowrap pl-5 font-semibold text-ink">{n.days_to_arrival === 0 ? fmtNightRel(0) : fmtNight(n.stay_date)}</Td>
                      <Td right className="whitespace-nowrap px-2 tabular">{own === null ? "—" : fmtMoney(own, "VND")}</Td>
                      <Td right className="whitespace-nowrap px-2 font-semibold tabular text-ink">{target === null ? <span className="font-normal text-muted">{s ? t("hold") : "—"}</span> : fmtMoney(target, "VND")}</Td>
                      <Td right className={cx("whitespace-nowrap pl-2 pr-5 tabular", s?.kind === "raise" ? "text-yours-deep" : s?.kind === "lower" ? "text-danger-deep" : "text-muted")}>
                        {s && s.kind !== "hold" ? `${fmtSigned(s.change_pct)}%` : "—"}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
          <p className="px-5 py-3 text-xs text-muted">{t("note")}</p>
        </div>
      )}
    </Card>
  );
}
