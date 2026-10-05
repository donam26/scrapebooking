"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { api, type DestinationOut, type MarketAreaOut } from "@/lib/api";
import { useApi, useInterval, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useFmt } from "@/lib/format";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Note, Skeleton, Switch, cx } from "@/components/ui";
import { IconInfo, IconPin, IconRefresh, IconSearch, IconTrash } from "@/components/icons";
import type { Tone } from "@/lib/labels";

/**
 * Cài đặt › Thị trường: chọn khu vực (thành phố/quận) để quét danh sách MỌI khách sạn trên Booking.com
 * mỗi ngày (03:00) và quét chi tiết các khách sạn nhiều đánh giá nhất (05:00), như bên OTARadar.
 */

type MarketT = ReturnType<typeof useTranslations<"settings.market">>;

const DEST_TYPES = ["city", "district", "region"] as const;

function destTypeLabel(t: MarketT, type: string): string {
  return (DEST_TYPES as readonly string[]).includes(type) ? t(`destType.${type as (typeof DEST_TYPES)[number]}`) : type;
}

type ListStatus = "queued" | "running" | "completed" | "capped" | "blocked" | "error" | "paused";

const LIST_STATUS: Record<ListStatus, Tone> = {
  queued: "gray",
  running: "blue",
  completed: "green",
  capped: "amber",
  blocked: "red",
  error: "red",
  paused: "amber",
};

/** Mã lỗi ngắn backend trả về (chi tiết chỉ nằm trong log) → câu cho người dùng. */
function listErrorText(t: MarketT, code: string): string {
  if (code.startsWith("blocked: wrong dates")) return t("listError.wrongDates");
  if (code.startsWith("blocked")) return t("listError.blocked");
  if (code === "error: timeout") return t("listError.timeout");
  if (code === "error: network") return t("listError.network");
  if (code === "error: stuck") return t("listError.stuck");
  return code;
}

type Config = { list_nights: number; detail_horizon_days: number; detail_max_hotels: number; max_pages: number };

const DEFAULT_CONFIG: Config = { list_nights: 14, detail_horizon_days: 30, detail_max_hotels: 300, max_pages: 60 };

function NumberField({ id, label, hint, value, min, max, onChange, disabled }: { id: string; label: string; hint: string; value: number; min: number; max: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <Input id={id} type="number" min={min} max={max} value={value} disabled={disabled} onChange={(e) => onChange(Math.max(min, Math.min(max, Number(e.target.value) || min)))} className="tabular" />
    </Field>
  );
}

function ConfigFields({ prefix, value, onChange, disabled }: { prefix: string; value: Config; onChange: (c: Config) => void; disabled?: boolean }) {
  const t = useTranslations("settings.market.config");
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <NumberField id={`${prefix}-nights`} label={t("listNights")} hint={t("listNightsHint")} value={value.list_nights} min={1} max={30} disabled={disabled} onChange={(v) => onChange({ ...value, list_nights: v })} />
      <NumberField id={`${prefix}-max`} label={t("maxHotels")} hint={t("maxHotelsHint")} value={value.detail_max_hotels} min={0} max={500} disabled={disabled} onChange={(v) => onChange({ ...value, detail_max_hotels: v })} />
      <NumberField id={`${prefix}-horizon`} label={t("horizon")} hint={t("horizonHint")} value={value.detail_horizon_days} min={1} max={90} disabled={disabled} onChange={(v) => onChange({ ...value, detail_horizon_days: v })} />
      <NumberField id={`${prefix}-pages`} label={t("maxPages")} hint={t("maxPagesHint")} value={value.max_pages} min={1} max={100} disabled={disabled} onChange={(v) => onChange({ ...value, max_pages: v })} />
    </div>
  );
}

function AddArea({ onAdded }: { onAdded: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<DestinationOut[] | null>(null);
  const [picked, setPicked] = useState<DestinationOut | null>(null);
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  const t = useTranslations("settings.market");
  const tc = useTranslations("common.actions");
  const search = useMutation(async () => {
    setPicked(null);
    setResults(await api.market.areas.search(q.trim()));
  });
  const create = useMutation(async () => {
    if (!picked) return;
    await api.market.areas.create({
      name: picked.name,
      dest_id: picked.dest_id,
      dest_type: picked.dest_type as "city" | "district" | "region",
      country_code: picked.country_code ?? "vn",
      channel: "booking",
      ...config,
    });
    setPicked(null);
    setResults(null);
    setQ("");
    onAdded();
  });
  return (
    <Card title={t("add.title")} icon={<IconPin size={16} />} info={t("add.info")}>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim().length >= 2) void search.run();
        }}
      >
        <Field label={t("add.searchLabel")} htmlFor="area-q" className="min-w-[260px] flex-1">
          <Input id="area-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("add.searchPlaceholder")} />
        </Field>
        <Button type="submit" busy={search.busy} icon={<IconSearch size={16} />} disabled={q.trim().length < 2}>
          {tc("search")}
        </Button>
      </form>
      {search.error && <ErrorBox error={search.error} className="mt-3" />}
      {results && results.length === 0 && <p className="mt-3 text-sm text-muted">{t("add.noResults")}</p>}
      {results && results.length > 0 && (
        <ul className="mt-3 divide-y divide-line rounded-lg border border-line">
          {results.map((d) => {
            const on = picked?.dest_id === d.dest_id && picked.dest_type === d.dest_type;
            return (
              <li key={`${d.dest_type}:${d.dest_id}`}>
                <button type="button" onClick={() => setPicked(d)} className={cx("flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left hover:bg-subtle", on && "bg-brand-softer")}>
                  <span className="min-w-0">
                    <span className="block font-semibold text-ink">{d.name}</span>
                    <span className="block truncate text-sm text-muted">{d.label}</span>
                  </span>
                  <span className="shrink-0 text-right text-sm">
                    <span className="block font-medium text-body">{destTypeLabel(t, d.dest_type)}</span>
                    {d.nr_hotels !== null && <span className="block text-xs text-muted tabular">{t("add.properties", { count: d.nr_hotels })}</span>}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {picked && (
        <div className="mt-4 space-y-3 rounded-lg border border-brand/30 bg-brand-softer p-4">
          <div className="font-semibold text-ink">
            {picked.name} <span className="font-normal text-muted">· {destTypeLabel(t, picked.dest_type)}</span>
          </div>
          {picked.nr_hotels !== null && picked.nr_hotels > 1000 && (
            <Note tone="warn" icon={<IconInfo size={16} />}>
              {t("add.bigArea", { count: picked.nr_hotels })}
            </Note>
          )}
          <ConfigFields prefix="new" value={config} onChange={setConfig} />
          <div className="flex items-center gap-3">
            <Button variant="primary" busy={create.busy} onClick={() => void create.run()}>
              {t("add.submit")}
            </Button>
            <span className="text-xs text-muted">{t("add.firstScanHint")}</span>
          </div>
          {create.error && <ErrorBox error={create.error} />}
        </div>
      )}
    </Card>
  );
}

function AreaCard({ area, canWrite, onChanged }: { area: MarketAreaOut; canWrite: boolean; onChanged: () => void }) {
  const [config, setConfig] = useState<Config>({ list_nights: area.list_nights, detail_horizon_days: area.detail_horizon_days, detail_max_hotels: area.detail_max_hotels, max_pages: area.max_pages });
  const [scanMsg, setScanMsg] = useState<"queued" | "alreadyRunning" | null>(null);
  const t = useTranslations("settings.market");
  const { fmtWhen } = useFmt();
  const dirty = config.list_nights !== area.list_nights || config.detail_horizon_days !== area.detail_horizon_days || config.detail_max_hotels !== area.detail_max_hotels || config.max_pages !== area.max_pages;
  const save = useMutation(async () => {
    await api.market.areas.update(area.id, config);
    onChanged();
  });
  const toggle = useMutation(async (active: boolean) => {
    await api.market.areas.update(area.id, { active });
    onChanged();
  });
  const scan = useMutation(async () => {
    const r = await api.market.areas.scanNow(area.id);
    setScanMsg(r.enqueued ? "queued" : "alreadyRunning");
    onChanged();
  });
  const del = useMutation(async () => {
    if (!window.confirm(t("area.deleteConfirm", { name: area.name }))) return;
    await api.market.areas.remove(area.id);
    onChanged();
  });
  const status = area.last_list_status;
  const st = status
    ? status in LIST_STATUS
      ? { label: t(`listStatus.${status as ListStatus}`), tone: LIST_STATUS[status as ListStatus] }
      : { label: status, tone: "gray" as Tone }
    : null;
  return (
    <Card
      title={area.name}
      icon={<IconPin size={16} />}
      description={t("area.description", { type: destTypeLabel(t, area.dest_type), count: area.hotels_total })}
      actions={
        <div className="flex items-center gap-2">
          {st && <Badge tone={st.tone}>{st.label}</Badge>}
          {canWrite && <Switch checked={area.active} onChange={(v) => void toggle.run(v)} label={area.active ? t("area.scanning") : t("area.paused")} />}
        </div>
      }
    >
      <dl className="grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted">{t("area.lastListScan")}</dt>
          <dd className="font-semibold text-ink">{area.last_list_scan_at ? fmtWhen(area.last_list_scan_at) : t("area.notScanned")}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("area.lastDetailScan")}</dt>
          <dd className="font-semibold text-ink">{area.last_detail_scan_at ? fmtWhen(area.last_detail_scan_at) : t("area.notScanned")}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("area.lastRequest")}</dt>
          <dd className="font-semibold text-ink">{area.list_requested_at ? fmtWhen(area.list_requested_at) : "—"}</dd>
        </div>
      </dl>
      {area.last_list_error && (
        <Note tone="warn" icon={<IconInfo size={16} />} className="mt-3">
          {listErrorText(t, area.last_list_error)}
        </Note>
      )}
      <div className="mt-4">
        <ConfigFields prefix={`a${area.id}`} value={config} onChange={setConfig} disabled={!canWrite} />
      </div>
      {canWrite && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" size="sm" disabled={!dirty} busy={save.busy} onClick={() => void save.run()}>
            {t("area.saveConfig")}
          </Button>
          <Button size="sm" icon={<IconRefresh size={15} />} busy={scan.busy} disabled={!area.active} onClick={() => void scan.run()}>
            {t("area.scanNow")}
          </Button>
          {scanMsg && <span className="text-sm text-yours-deep">{t(`area.${scanMsg}`)}</span>}
          <Button size="sm" variant="danger" className="ml-auto" icon={<IconTrash size={15} />} busy={del.busy} onClick={() => void del.run()}>
            {t("area.delete")}
          </Button>
        </div>
      )}
      {[save.error, toggle.error, scan.error, del.error].filter(Boolean).map((e) => (
        <ErrorBox key={e} error={e} className="mt-3" />
      ))}
    </Card>
  );
}

export function MarketTab() {
  const { canWrite } = useSession();
  const t = useTranslations("settings.market");
  const areas = useApi("settings:market-areas", () => api.market.areas.list());
  // Đang quét danh sách: tự làm mới để thấy trạng thái.
  useInterval(() => areas.reload(), areas.data?.some((a) => a.last_list_status === "running" || a.last_list_status === "queued") ? 10_000 : 0);
  return (
    <div className="space-y-5">
      <Note tone="info" icon={<IconInfo size={16} />}>
        {t("intro")}
      </Note>
      {canWrite && <AddArea onAdded={areas.reload} />}
      <ErrorBox error={areas.error} />
      {!areas.data && !areas.error && <Skeleton rows={4} />}
      {areas.data && areas.data.length === 0 && (
        <EmptyState icon={<IconPin />} title={t("emptyTitle")} className="border border-line bg-surface">
          {t("emptyBody")}
        </EmptyState>
      )}
      {areas.data?.map((a) => (
        <AreaCard key={`${a.id}:${a.list_nights}:${a.detail_horizon_days}:${a.detail_max_hotels}:${a.max_pages}`} area={a} canWrite={canWrite} onChanged={areas.reload} />
      ))}
    </div>
  );
}
