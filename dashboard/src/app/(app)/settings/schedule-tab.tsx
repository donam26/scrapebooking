"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";
import { api, type TenantOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { activeChannels, channelName, sortChannels } from "@/lib/channels";
import { LOCALES, LOCALE_NAME } from "@/i18n/config";
import { Button, Card, ErrorBox, Field, Input, Segmented, Select, Skeleton, cx } from "@/components/ui";
import { IconCheck, IconClose, IconPlus } from "@/components/icons";

const TIMEZONES = ["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore", "Asia/Jakarta", "Asia/Manila", "Asia/Tokyo", "Europe/London", "UTC"];

/** Tên dễ đọc cho múi giờ; giá trị gửi lên vẫn là mã IANA. */
const TZ_LABEL: Record<string, string> = {
  "Asia/Bangkok": "Bangkok (GMT+7)",
  "Asia/Singapore": "Singapore (GMT+8)",
  "Asia/Jakarta": "Jakarta (GMT+7)",
  "Asia/Manila": "Manila (GMT+8)",
  "Asia/Tokyo": "Tokyo (GMT+9)",
  "Europe/London": "London (GMT+0/+1)",
  UTC: "UTC",
};
const MAX_TIMES = 8;

type Draft = { scanTimes: string[]; horizon: number; insightHour: string; language: string; timezone: string; referenceChannel: string };

function fromTenant(t: TenantOut): Draft {
  return {
    scanTimes: [...t.scan_times].sort(),
    horizon: t.horizon_days,
    insightHour: t.insight_hour,
    language: t.insight_language,
    timezone: t.timezone,
    referenceChannel: t.reference_channel,
  };
}

function same(a: Draft, b: Draft): boolean {
  return (
    a.scanTimes.join(",") === b.scanTimes.join(",") &&
    a.horizon === b.horizon &&
    a.insightHour === b.insightHour &&
    a.language === b.language &&
    a.timezone === b.timezone &&
    a.referenceChannel === b.referenceChannel
  );
}

function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** Trục 24 giờ: chấm xanh ở từng mốc quét, dấu thoi cho giờ tạo bản tin. */
function DayRail({ scanTimes, insightHour }: { scanTimes: string[]; insightHour: string }) {
  const t = useTranslations("settings.schedule.rail");
  const pct = (time: string) => `${(minutes(time) / 1440) * 100}%`;
  return (
    <div className="rounded-lg bg-subtle px-5 pb-4 pt-9" aria-hidden>
      <div className="relative h-14">
        {/* nửa đêm → trưa → nửa đêm: nền ngày nhạt ở giữa */}
        <div className="absolute inset-x-0 top-[14px] h-1.5 rounded-full bg-[linear-gradient(90deg,#dcd8ef_0%,#ebe4ff_25%,#f4f0ff_50%,#ebe4ff_75%,#dcd8ef_100%)]" />
        {[0, 6, 12, 18, 24].map((h) => (
          <div key={h} className="absolute top-[24px] -translate-x-1/2 text-2xs font-semibold text-faint tabular" style={{ left: `${(h / 24) * 100}%` }}>
            {h}h
          </div>
        ))}
        {scanTimes.map((time) => (
          <div key={time} className="absolute top-0 -translate-x-1/2" style={{ left: pct(time) }}>
            <div className="absolute bottom-[calc(100%+4px)] left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-bold text-ink tabular">{time}</div>
            <div className="mt-[11px] h-3 w-3 rounded-full bg-brand ring-[3px] ring-surface" />
          </div>
        ))}
        {insightHour && (
          <div className="absolute top-0 -translate-x-1/2" style={{ left: pct(insightHour) }}>
            <div className="mt-[11px] h-3 w-3 rotate-45 rounded-[2px] bg-night ring-[3px] ring-surface" />
            <div className="absolute left-1/2 top-[40px] -translate-x-1/2 whitespace-nowrap rounded bg-surface px-1.5 text-xs font-semibold text-body shadow-[0_1px_2px_rgba(17,24,39,0.1)] tabular">{t("insight", { time: insightHour })}</div>
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-brand" /> {t("scan")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rotate-45 rounded-[1px] bg-night" /> {t("insightLegend")}
        </span>
      </div>
    </div>
  );
}

/** Form lịch quét; `key` ở cha reset form khi dữ liệu tenant đổi. */
export function ScheduleForm({
  tenant,
  readOnly,
  onSave,
  channelOptions,
}: {
  tenant: TenantOut;
  readOnly: boolean;
  onSave: (body: Parameters<typeof api.settings.update>[0]) => Promise<TenantOut>;
  /** Kênh chọn được làm kênh tham chiếu (đang quét được và tenant có khách sạn đang quét). */
  channelOptions: string[];
}) {
  const [baseline, setBaseline] = useState<Draft>(() => fromTenant(tenant));
  const [d, setD] = useState<Draft>(() => fromTenant(tenant));
  const [newTime, setNewTime] = useState("12:00");
  const [saved, setSaved] = useState(false);
  const tr = useTranslations("settings.schedule");
  const tzLabel = (z: string) => (z === "Asia/Ho_Chi_Minh" ? tr("tzVietnam") : (TZ_LABEL[z] ?? z));
  const dirty = !same(d, baseline);
  const duplicate = d.scanTimes.includes(newTime);
  const horizonBad = !Number.isInteger(d.horizon) || d.horizon < 1 || d.horizon > 90;

  const save = useMutation(async () => {
    setSaved(false);
    const t = await onSave({
      scan_times: d.scanTimes.filter(Boolean),
      horizon_days: d.horizon,
      insight_hour: d.insightHour,
      insight_language: d.language,
      timezone: d.timezone,
      reference_channel: d.referenceChannel,
    });
    // Hiện đúng giá trị server đã chuẩn hoá (giờ quét sắp xếp, bỏ trùng).
    const next = fromTenant(t);
    setBaseline(next);
    setD(next);
    setSaved(true);
  });

  useEffect(() => {
    if (!saved) return;
    const id = window.setTimeout(() => setSaved(false), 4000);
    return () => window.clearTimeout(id);
  }, [saved]);

  function addTime() {
    if (!newTime || duplicate || d.scanTimes.length >= MAX_TIMES) return;
    setD({ ...d, scanTimes: [...d.scanTimes, newTime].sort() });
    setSaved(false);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (horizonBad || d.scanTimes.length === 0) return;
    void save.run();
  }

  const tzOptions = TIMEZONES.includes(d.timezone) ? TIMEZONES : [d.timezone, ...TIMEZONES];
  const refOptions = sortChannels([...channelOptions, baseline.referenceChannel]);

  return (
    <form onSubmit={submit}>
      <fieldset disabled={readOnly} className="min-w-0">
        <section className="px-5 py-5">
          <h3 className="text-base font-bold text-ink">{tr("times.title")}</h3>
          <p className="mt-0.5 text-sm text-muted">
            {tr("times.hint", { timezone: tzLabel(d.timezone), max: MAX_TIMES })}
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {d.scanTimes.map((t) => (
              <span key={t} className="inline-flex h-9 items-center gap-1 rounded-full border border-line-strong bg-surface pl-3.5 pr-1 text-base font-semibold text-ink tabular">
                {t}
                {!readOnly ? (
                  <button
                    type="button"
                    aria-label={tr("times.removeAria", { time: t })}
                    title={d.scanTimes.length <= 1 ? tr("times.keepOne") : tr("times.removeAria", { time: t })}
                    disabled={d.scanTimes.length <= 1}
                    onClick={() => {
                      setD({ ...d, scanTimes: d.scanTimes.filter((x) => x !== t) });
                      setSaved(false);
                    }}
                    className="grid h-7 w-7 place-items-center rounded-full text-muted transition-colors hover:bg-danger-soft hover:text-danger disabled:cursor-not-allowed disabled:text-faint disabled:hover:bg-transparent"
                  >
                    <IconClose size={14} />
                  </button>
                ) : (
                  <span className="w-2" />
                )}
              </span>
            ))}
            {!readOnly && d.scanTimes.length < MAX_TIMES && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-sunken p-1 pl-1.5">
                <input
                  type="time"
                  aria-label={tr("times.newAria")}
                  value={newTime}
                  onChange={(e) => setNewTime(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addTime();
                    }
                  }}
                  className="h-7 rounded-full border border-line-strong bg-surface px-2.5 text-base text-ink tabular focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15"
                />
                <Button size="sm" variant="quiet" icon={<IconPlus size={15} />} onClick={addTime} disabled={!newTime || duplicate} className="h-7 rounded-full">
                  {tr("times.add")}
                </Button>
              </span>
            )}
          </div>
          {!readOnly && duplicate && d.scanTimes.length < MAX_TIMES && <p className="mt-2 text-sm text-muted">{tr("times.duplicate", { time: newTime })}</p>}
          <div className="mt-5">
            <DayRail scanTimes={d.scanTimes} insightHour={d.insightHour} />
          </div>
        </section>

        <section className="border-t border-line px-5 py-5">
          <h3 className="text-base font-bold text-ink">{tr("reference.title")}</h3>
          <p className="mt-0.5 max-w-[70ch] text-sm text-muted">
            {tr("reference.description")}
          </p>
          <div className="mt-3">
            {refOptions.length > 1 ? (
              <Segmented
                label={tr("reference.title")}
                value={d.referenceChannel}
                onChange={(v) => {
                  if (readOnly) return;
                  setD({ ...d, referenceChannel: v });
                  setSaved(false);
                }}
                items={refOptions.map((c) => ({ value: c, label: channelName(c) }))}
                className={cx(readOnly && "pointer-events-none opacity-70")}
              />
            ) : (
              <p className="text-base text-body">
                <span className="font-semibold text-ink">{channelName(d.referenceChannel)}</span>
                <span className="text-muted"> · {tr("reference.onlyOne")}</span>
              </p>
            )}
          </div>
        </section>

        <section className="border-t border-line px-5 py-5">
          <h3 className="text-base font-bold text-ink">{tr("scope.title")}</h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label={tr("scope.horizon")} hint={tr("scope.horizonHint")} htmlFor="sc-horizon">
              <div className="relative">
                <Input
                  id="sc-horizon"
                  type="number"
                  min={1}
                  max={90}
                  required
                  value={Number.isNaN(d.horizon) ? "" : d.horizon}
                  aria-invalid={horizonBad || undefined}
                  onChange={(e) => {
                    setD({ ...d, horizon: e.target.valueAsNumber });
                    setSaved(false);
                  }}
                  className={cx("pr-12 tabular", horizonBad && "border-danger focus:border-danger focus:ring-danger/15")}
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted">{tr("scope.nights")}</span>
              </div>
            </Field>
            <Field label={tr("scope.insightHour")} hint={tr("scope.insightHourHint")} htmlFor="sc-insight">
              <Input
                id="sc-insight"
                type="time"
                required
                value={d.insightHour}
                onChange={(e) => {
                  setD({ ...d, insightHour: e.target.value });
                  setSaved(false);
                }}
                className="tabular"
              />
            </Field>
            <div className="flex min-w-0 flex-col gap-1.5">
              <span className="text-sm font-semibold text-body">{tr("scope.language")}</span>
              <Segmented
                label={tr("scope.language")}
                value={d.language}
                onChange={(v) => {
                  if (readOnly) return;
                  setD({ ...d, language: v });
                  setSaved(false);
                }}
                items={LOCALES.map((l) => ({ value: l, label: LOCALE_NAME[l] }))}
                className={cx("self-start", readOnly && "pointer-events-none opacity-70")}
              />
              <span className="text-xs text-muted">{tr("scope.languageHint")}</span>
            </div>
            <Field label={tr("scope.timezone")} hint={tr("scope.timezoneHint")} htmlFor="sc-tz">
              <Select
                id="sc-tz"
                value={d.timezone}
                onChange={(e) => {
                  setD({ ...d, timezone: e.target.value });
                  setSaved(false);
                }}
              >
                {tzOptions.map((z) => (
                  <option key={z} value={z}>
                    {tzLabel(z)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </section>
      </fieldset>

      {!readOnly && (
        <div className="flex flex-wrap items-center gap-3 border-t border-line bg-subtle px-5 py-3.5">
          <Button type="submit" variant="primary" busy={save.busy} disabled={!dirty || horizonBad || d.scanTimes.length === 0}>
            {tr("save")}
          </Button>
          {dirty && (
            <Button
              variant="ghost"
              onClick={() => {
                setD(baseline);
                save.clearError();
              }}
            >
              {tr("discard")}
            </Button>
          )}
          <span role="status" className="text-sm">
            {saved && !dirty ? (
              <span className="inline-flex items-center gap-1.5 text-yours-deep">
                <IconCheck size={16} /> {tr("saved")}
              </span>
            ) : dirty ? (
              <span className="text-muted">{tr("unsaved")}</span>
            ) : null}
          </span>
          {save.error && <ErrorBox error={save.error} className="basis-full" title={tr("saveError")} />}
        </div>
      )}
    </form>
  );
}

export function ScheduleTab() {
  const { canWrite } = useSession();
  const t = useTranslations("settings.schedule");
  const settings = useApi("settings", () => api.settings.get());
  const channels = useApi("channels", () => api.channels());
  const watchlist = useApi("watchlist", () => api.watchlist.list());
  // Kênh tham chiếu hợp lệ: kênh quét được mà tenant đang có khách sạn quét trên đó.
  const tenantChannels = new Set((watchlist.data ?? []).flatMap((w) => (w.active ? activeChannels(w.hotel) : [])));
  const channelOptions = (channels.data ?? []).filter((c) => c.collectable && tenantChannels.has(c.code)).map((c) => c.code);
  return (
    <Card padded={false} title={t("cardTitle")} description={t("cardDescription")}>
      <ErrorBox error={settings.error} className="m-5" />
      {!settings.data ? (
        !settings.error && <Skeleton rows={5} className="p-5" />
      ) : (
        <ScheduleForm
          key={`${settings.data.id}-${settings.data.created_at}`}
          tenant={settings.data}
          readOnly={!canWrite}
          channelOptions={channelOptions}
          onSave={async (body) => {
            const t = await api.settings.update(body);
            settings.reload();
            return t;
          }}
        />
      )}
    </Card>
  );
}
