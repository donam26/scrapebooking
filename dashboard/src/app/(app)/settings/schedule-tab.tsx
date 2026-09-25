"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, type TenantOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { Button, Card, ErrorBox, Field, Input, Segmented, Select, Skeleton, cx } from "@/components/ui";
import { IconCheck, IconClose, IconPlus } from "@/components/icons";

const TIMEZONES = ["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore", "Asia/Jakarta", "Asia/Manila", "Asia/Tokyo", "Europe/London", "UTC"];

/** Tên dễ đọc cho múi giờ; giá trị gửi lên vẫn là mã IANA. */
const TZ_LABEL: Record<string, string> = {
  "Asia/Ho_Chi_Minh": "Giờ Việt Nam (GMT+7)",
  "Asia/Bangkok": "Bangkok (GMT+7)",
  "Asia/Singapore": "Singapore (GMT+8)",
  "Asia/Jakarta": "Jakarta (GMT+7)",
  "Asia/Manila": "Manila (GMT+8)",
  "Asia/Tokyo": "Tokyo (GMT+9)",
  "Europe/London": "London (GMT+0/+1)",
  UTC: "UTC",
};
const MAX_TIMES = 8;

type Draft = { scanTimes: string[]; horizon: number; insightHour: string; language: string; timezone: string };

function fromTenant(t: TenantOut): Draft {
  return {
    scanTimes: [...t.scan_times].sort(),
    horizon: t.horizon_days,
    insightHour: t.insight_hour,
    language: t.insight_language,
    timezone: t.timezone,
  };
}

function same(a: Draft, b: Draft): boolean {
  return (
    a.scanTimes.join(",") === b.scanTimes.join(",") &&
    a.horizon === b.horizon &&
    a.insightHour === b.insightHour &&
    a.language === b.language &&
    a.timezone === b.timezone
  );
}

function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** Trục 24 giờ: chấm tím ở từng mốc quét, dấu thoi cho giờ tạo bản tin. */
function DayRail({ scanTimes, insightHour }: { scanTimes: string[]; insightHour: string }) {
  const pct = (t: string) => `${(minutes(t) / 1440) * 100}%`;
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
        {scanTimes.map((t) => (
          <div key={t} className="absolute top-0 -translate-x-1/2" style={{ left: pct(t) }}>
            <div className="absolute bottom-[calc(100%+4px)] left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-bold text-ink tabular">{t}</div>
            <div className="mt-[11px] h-3 w-3 rounded-full bg-brand ring-[3px] ring-surface" />
          </div>
        ))}
        {insightHour && (
          <div className="absolute top-0 -translate-x-1/2" style={{ left: pct(insightHour) }}>
            <div className="mt-[11px] h-3 w-3 rotate-45 rounded-[2px] bg-night ring-[3px] ring-surface" />
            <div className="absolute left-1/2 top-[40px] -translate-x-1/2 whitespace-nowrap rounded bg-surface px-1.5 text-xs font-semibold text-body shadow-[0_1px_2px_rgba(22,18,58,0.1)] tabular">Bản tin {insightHour}</div>
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-brand" /> Lượt quét
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rotate-45 rounded-[1px] bg-night" /> Tạo bản tin AI
        </span>
      </div>
    </div>
  );
}

/** Form lịch quét; `key` ở cha reset form khi dữ liệu tenant đổi. */
export function ScheduleForm({ tenant, readOnly, onSave }: { tenant: TenantOut; readOnly: boolean; onSave: (body: Parameters<typeof api.settings.update>[0]) => Promise<TenantOut> }) {
  const [baseline, setBaseline] = useState<Draft>(() => fromTenant(tenant));
  const [d, setD] = useState<Draft>(() => fromTenant(tenant));
  const [newTime, setNewTime] = useState("12:00");
  const [saved, setSaved] = useState(false);
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

  return (
    <form onSubmit={submit}>
      <fieldset disabled={readOnly} className="min-w-0">
        <section className="px-5 py-5">
          <h3 className="text-base font-bold text-ink">Giờ quét trong ngày</h3>
          <p className="mt-0.5 text-sm text-muted">
            Mỗi mốc giờ tạo một lượt quét toàn bộ khách sạn đang theo dõi, theo {TZ_LABEL[d.timezone] ?? d.timezone}. Tối đa {MAX_TIMES} mốc.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {d.scanTimes.map((t) => (
              <span key={t} className="inline-flex h-9 items-center gap-1 rounded-full border border-line-strong bg-surface pl-3.5 pr-1 text-base font-semibold text-ink tabular">
                {t}
                {!readOnly ? (
                  <button
                    type="button"
                    aria-label={`Xoá mốc ${t}`}
                    title={d.scanTimes.length <= 1 ? "Cần giữ ít nhất một mốc quét" : `Xoá mốc ${t}`}
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
                  aria-label="Mốc giờ mới"
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
                  Thêm mốc
                </Button>
              </span>
            )}
          </div>
          {!readOnly && duplicate && d.scanTimes.length < MAX_TIMES && <p className="mt-2 text-sm text-muted">Đã có mốc {newTime}.</p>}
          <div className="mt-5">
            <DayRail scanTimes={d.scanTimes} insightHour={d.insightHour} />
          </div>
        </section>

        <section className="border-t border-line px-5 py-5">
          <h3 className="text-base font-bold text-ink">Phạm vi quét và bản tin</h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Số đêm quét tới" hint="Từ 1 đến 90 đêm, tính từ hôm nay" htmlFor="sc-horizon">
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
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted">đêm</span>
              </div>
            </Field>
            <Field label="Giờ tạo bản tin AI" hint="Bản tin hằng ngày dùng lượt quét gần nhất" htmlFor="sc-insight">
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
              <span className="text-sm font-semibold text-body">Ngôn ngữ bản tin</span>
              <Segmented
                label="Ngôn ngữ bản tin"
                value={d.language}
                onChange={(v) => {
                  if (readOnly) return;
                  setD({ ...d, language: v });
                  setSaved(false);
                }}
                items={[
                  { value: "vi", label: "Tiếng Việt" },
                  { value: "en", label: "English" },
                ]}
                className={cx("self-start", readOnly && "pointer-events-none opacity-70")}
              />
            </div>
            <Field label="Múi giờ" hint="Giờ quét và giờ bản tin tính theo múi giờ này" htmlFor="sc-tz">
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
                    {TZ_LABEL[z] ?? z}
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
            Lưu cài đặt
          </Button>
          {dirty && (
            <Button
              variant="ghost"
              onClick={() => {
                setD(baseline);
                save.clearError();
              }}
            >
              Bỏ thay đổi
            </Button>
          )}
          <span role="status" className="text-sm">
            {saved && !dirty ? (
              <span className="inline-flex items-center gap-1.5 text-yours-deep">
                <IconCheck size={16} /> Đã lưu
              </span>
            ) : dirty ? (
              <span className="text-muted">Có thay đổi chưa lưu</span>
            ) : null}
          </span>
          {save.error && <ErrorBox error={save.error} className="basis-full" title="Chưa lưu được" />}
        </div>
      )}
    </form>
  );
}

export function ScheduleTab() {
  const { canWrite } = useSession();
  const settings = useApi("settings", () => api.settings.get());
  return (
    <Card padded={false} title="Lịch quét và bản tin" description="Nhịp đếm phòng mỗi ngày và giờ bản tin AI được tạo">
      <ErrorBox error={settings.error} className="m-5" />
      {!settings.data ? (
        !settings.error && <Skeleton rows={5} className="p-5" />
      ) : (
        <ScheduleForm
          key={`${settings.data.id}-${settings.data.created_at}`}
          tenant={settings.data}
          readOnly={!canWrite}
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
