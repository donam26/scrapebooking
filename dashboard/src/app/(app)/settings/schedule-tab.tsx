"use client";

import { useState, type FormEvent } from "react";
import { api, type TenantOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { Button, Card, ErrorBox, Field, Input, Select, Skeleton } from "@/components/ui";

const TIMEZONES = ["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore", "Asia/Jakarta", "Asia/Manila", "Asia/Tokyo", "Europe/London", "UTC"];

/** Form lịch quét; `key` ở cha reset form khi dữ liệu tenant đổi. */
export function ScheduleForm({ tenant, readOnly, onSave }: { tenant: TenantOut; readOnly: boolean; onSave: (body: Parameters<typeof api.settings.update>[0]) => Promise<unknown> }) {
  const [scanTimes, setScanTimes] = useState<string[]>(tenant.scan_times);
  const [horizon, setHorizon] = useState<number>(tenant.horizon_days);
  const [insightHour, setInsightHour] = useState(tenant.insight_hour);
  const [language, setLanguage] = useState(tenant.insight_language);
  const [timezone, setTimezone] = useState(tenant.timezone);
  const [saved, setSaved] = useState(false);
  const save = useMutation(async () => {
    setSaved(false);
    await onSave({
      scan_times: scanTimes.filter(Boolean),
      horizon_days: horizon,
      insight_hour: insightHour,
      insight_language: language,
      timezone,
    });
    setSaved(true);
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    void save.run();
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <fieldset disabled={readOnly} className="space-y-4">
        <div>
          <div className="mb-1 text-xs font-medium text-slate-600">Giờ quét trong ngày (theo múi giờ tenant)</div>
          <div className="flex flex-wrap items-center gap-2">
            {scanTimes.map((t, i) => (
              <span key={i} className="flex items-center gap-1">
                <Input type="time" required value={t} onChange={(e) => setScanTimes(scanTimes.map((x, j) => (j === i ? e.target.value : x)))} />
                {!readOnly && (
                  <Button size="sm" variant="ghost" aria-label="Xoá giờ quét" onClick={() => setScanTimes(scanTimes.filter((_, j) => j !== i))} disabled={scanTimes.length <= 1}>
                    ×
                  </Button>
                )}
              </span>
            ))}
            {!readOnly && (
              <Button size="sm" onClick={() => setScanTimes([...scanTimes, "12:00"])} disabled={scanTimes.length >= 8}>
                + Thêm giờ
              </Button>
            )}
          </div>
          <p className="mt-1 text-[11px] text-slate-500">Mỗi mốc giờ tạo một đợt quét toàn bộ watchlist. Mặc định 06:00, 14:00, 22:00.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Số ngày quét tới (horizon)" hint="1–90 ngày">
            <Input type="number" min={1} max={90} required value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </Field>
          <Field label="Giờ tạo bản tin AI">
            <Input type="time" required value={insightHour} onChange={(e) => setInsightHour(e.target.value)} />
          </Field>
          <Field label="Ngôn ngữ bản tin">
            <Select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="vi">Tiếng Việt</option>
              <option value="en">English</option>
            </Select>
          </Field>
          <Field label="Múi giờ">
            <Input list="tz-list" required value={timezone} onChange={(e) => setTimezone(e.target.value)} />
            <datalist id="tz-list">
              {TIMEZONES.map((z) => (
                <option key={z} value={z} />
              ))}
            </datalist>
          </Field>
        </div>
      </fieldset>
      <ErrorBox error={save.error} />
      {!readOnly && (
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" busy={save.busy}>
            Lưu cài đặt
          </Button>
          {saved && <span className="text-sm text-emerald-700">Đã lưu.</span>}
        </div>
      )}
    </form>
  );
}

export function ScheduleTab() {
  const { canWrite } = useSession();
  const settings = useApi("settings", () => api.settings.get());
  return (
    <Card title="Lịch quét và bản tin">
      <ErrorBox error={settings.error} className="mb-3" />
      {!settings.data ? (
        !settings.error && <Skeleton rows={4} />
      ) : (
        <ScheduleForm
          key={`${settings.data.id}-${settings.data.created_at}`}
          tenant={settings.data}
          readOnly={!canWrite}
          onSave={async (body) => {
            await api.settings.update(body);
            settings.reload();
          }}
        />
      )}
    </Card>
  );
}
