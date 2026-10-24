"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { api, ApiError, type DestinationOut, type MarketAreaCreate, type MarketAreaOut } from "@/lib/api";
import { useApi, useInterval, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useFmt } from "@/lib/format";
import { DEFAULT_RADIUS, DEFAULT_SEGMENT, RADII, SEGMENTS, asRadius, normalizeNflt, useMarketAreaText, type Radius } from "@/lib/market-area";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Note, Segmented, Select, Skeleton, Switch, cx } from "@/components/ui";
import { IconInfo, IconPin, IconRefresh, IconSearch, IconTrash } from "@/components/icons";
import type { Tone } from "@/lib/labels";

/**
 * Cài đặt › Thị trường: khu vực thị trường trên Booking.com — tìm theo tên (thành phố, quận, địa danh;
 * tuỳ chọn bán kính) hoặc bán kính quanh khách sạn của bạn — lọc theo phân khúc. Mỗi ngày 03:00 đọc
 * số chỗ còn phòng, giá và thang "còn bán ≥N phòng" cho từng đêm (mức căng thị trường trên Booking.com).
 */

type MarketT = ReturnType<typeof useTranslations<"settings.market">>;

const DEST_TYPES = ["city", "district", "region", "landmark", "latlong"] as const;
type DestType = (typeof DEST_TYPES)[number];
/** Loại địa điểm tìm được theo tên (latlong chỉ tạo từ "quanh khách sạn của bạn"). */
type SearchDestType = Exclude<DestType, "latlong">;

function isDestType(type: string): type is DestType {
  return (DEST_TYPES as readonly string[]).includes(type);
}

function isSearchDestType(type: string): type is SearchDestType {
  return isDestType(type) && type !== "latlong";
}

function destTypeLabel(t: MarketT, type: string): string {
  return isDestType(type) ? t(`destType.${type}`) : type;
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

/** Phạm vi của khu vực: bán kính (null = không lọc) và phân khúc (bộ lọc Booking, null = mọi loại chỗ ở). */
type Scope = { radius: Radius | null; segment: string | null };

/** Mã nước 2 chữ thường của tenant (khu vực "quanh khách sạn"); không hợp lệ thì "vn". */
function countryCode(raw: string | null | undefined): string {
  const cc = (raw ?? "").toLowerCase();
  return /^[a-z]{2}$/.test(cc) ? cc : "vn";
}

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

/** Bán kính (nhóm chọn) và phân khúc (mẫu, hoặc bộ lọc riêng đã lưu qua API). */
function ScopeFields({ prefix, value, onChange, radiusRequired, disabled }: { prefix: string; value: Scope; onChange: (s: Scope) => void; radiusRequired?: boolean; disabled?: boolean }) {
  const t = useTranslations("settings.market.scope");
  const { segmentLabel, radiusLabel } = useMarketAreaText();
  const preset = SEGMENTS.find((s) => normalizeNflt(s.nflt) === normalizeNflt(value.segment));
  const selected = preset ? (preset.nflt ?? "") : (value.segment ?? "");
  const radii = RADII.map((r) => ({ value: r as number, label: radiusLabel(r) }));
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-1.5">
        <span className="text-sm font-semibold text-body">{t("radius")}</span>
        <Segmented
          label={t("radius")}
          value={value.radius ?? 0}
          disabled={disabled}
          className="self-start"
          onChange={(v) => onChange({ ...value, radius: asRadius(v) })}
          items={radiusRequired ? radii : [{ value: 0, label: t("radiusNone") }, ...radii]}
        />
        <span className="text-xs text-muted">{radiusRequired ? t("radiusRequiredHint") : t("radiusHint")}</span>
      </div>
      <Field label={t("segment")} htmlFor={`${prefix}-segment`} hint={t("segmentHint")}>
        <Select id={`${prefix}-segment`} value={selected} disabled={disabled} onChange={(e) => onChange({ ...value, segment: e.target.value || null })}>
          {SEGMENTS.map((s) => (
            <option key={s.key} value={s.nflt ?? ""}>
              {segmentLabel(s.nflt)}
            </option>
          ))}
          {!preset && value.segment && <option value={value.segment}>{segmentLabel(value.segment)}</option>}
        </Select>
      </Field>
    </div>
  );
}

/** Phần chung của hai cách tạo khu vực: phạm vi, cấu hình quét, nút thêm. */
function NewAreaForm({
  prefix,
  heading,
  notice,
  scope,
  onScope,
  radiusRequired,
  config,
  onConfig,
  busy,
  error,
  disabled,
  onSubmit,
}: {
  prefix: string;
  heading: ReactNode;
  notice?: ReactNode;
  scope: Scope;
  onScope: (s: Scope) => void;
  radiusRequired?: boolean;
  config: Config;
  onConfig: (c: Config) => void;
  busy: boolean;
  error: string | null;
  disabled?: boolean;
  onSubmit: () => void;
}) {
  const t = useTranslations("settings.market.add");
  const { isOperator } = useSession();
  return (
    <div className="space-y-4 rounded-lg border border-brand/30 bg-brand-softer p-4">
      <div className="min-w-0 break-words font-semibold text-ink">{heading}</div>
      {notice}
      <ScopeFields prefix={prefix} value={scope} onChange={onScope} radiusRequired={radiusRequired} />
      {/* Tham số vận hành (số đêm, số khách sạn, số trang quét) chỉ operator đổi được (C3). */}
      {isOperator && <ConfigFields prefix={prefix} value={config} onChange={onConfig} />}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button variant="primary" busy={busy} disabled={disabled} onClick={onSubmit}>
          {t("submit")}
        </Button>
        <span className="text-xs text-muted">{t("firstScanHint")}</span>
      </div>
      {error && <ErrorBox error={error} />}
    </div>
  );
}

/** Cách 1: tìm thành phố/quận/vùng/địa danh theo tên trên Booking.com, tuỳ chọn bán kính. */
function SearchArea({ onAdded }: { onAdded: () => void }) {
  const { isOperator } = useSession();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<DestinationOut[] | null>(null);
  const [picked, setPicked] = useState<(DestinationOut & { dest_type: SearchDestType }) | null>(null);
  const [scope, setScope] = useState<Scope>({ radius: null, segment: DEFAULT_SEGMENT });
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  const t = useTranslations("settings.market");
  const tc = useTranslations("common.actions");
  const search = useMutation(async () => {
    setPicked(null);
    setResults((await api.market.areas.search(q.trim())).filter((d) => isSearchDestType(d.dest_type)));
  });
  const create = useMutation(async () => {
    if (!picked) return;
    await api.market.areas.create({
      name: picked.name,
      dest_id: picked.dest_id,
      dest_type: picked.dest_type,
      country_code: countryCode(picked.country_code),
      channel: "booking",
      radius_m: scope.radius,
      segment_nflt: scope.segment,
      // Khách sạn không gửi tham số vận hành: backend dùng mặc định.
      ...(isOperator ? config : {}),
    } as MarketAreaCreate);
    setPicked(null);
    setResults(null);
    setQ("");
    onAdded();
  });
  function pick(d: DestinationOut) {
    if (!isSearchDestType(d.dest_type)) return;
    setPicked({ ...d, dest_type: d.dest_type });
    // Địa danh (bãi biển, chợ…) dùng kèm bán kính; thành phố/quận mặc định không lọc bán kính.
    setScope((s) => ({ ...s, radius: d.dest_type === "landmark" ? DEFAULT_RADIUS : null }));
  }
  return (
    <>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim().length >= 2) void search.run();
        }}
      >
        <Field label={t("add.searchLabel")} htmlFor="area-q" className="min-w-0 flex-1 basis-[240px]">
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
                <button type="button" aria-pressed={on} onClick={() => pick(d)} className={cx("flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left hover:bg-subtle", on && "bg-brand-softer")}>
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
        <div className="mt-4">
          <NewAreaForm
            prefix="new"
            heading={
              <>
                {picked.name} <span className="font-normal text-muted">· {destTypeLabel(t, picked.dest_type)}</span>
              </>
            }
            notice={
              picked.nr_hotels !== null && picked.nr_hotels > 1000 && scope.radius === null ? (
                <Note tone="warn" icon={<IconInfo size={16} />}>
                  {t("add.bigArea", { count: picked.nr_hotels })}
                </Note>
              ) : picked.dest_type === "landmark" && scope.radius === null ? (
                <Note tone="info" icon={<IconInfo size={16} />}>
                  {t("add.landmarkHint")}
                </Note>
              ) : undefined
            }
            scope={scope}
            onScope={setScope}
            config={config}
            onConfig={setConfig}
            busy={create.busy}
            error={create.error}
            onSubmit={() => void create.run()}
          />
        </div>
      )}
    </>
  );
}

/** Cách 2: bán kính quanh toạ độ khách sạn của bạn (khu vực `latlong`, bán kính bắt buộc). */
function AroundHotel({ areas, onAdded }: { areas: MarketAreaOut[]; onAdded: () => void }) {
  const { isOperator } = useSession();
  const t = useTranslations("settings.market.add");
  const { fmtNum } = useFmt();
  const [scope, setScope] = useState<Scope>({ radius: DEFAULT_RADIUS, segment: DEFAULT_SEGMENT });
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  // 404: tenant chưa có khách sạn "của bạn" có toạ độ (toạ độ lấy khi quét trang Booking.com của nó).
  const loc = useApi("settings:self-location", () =>
    api.market.areas.selfLocation().catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
  );
  const tenant = useApi("settings", () => api.settings.get());
  const me = loc.data ?? null;
  const radius = scope.radius ?? DEFAULT_RADIUS;
  const name = me ? t("aroundName", { km: radius / 1000, name: me.name ?? t("aroundHotelFallback") }).slice(0, 200) : "";
  // Cùng toạ độ (5 số lẻ như backend đặt dest_id) = đã có khu vực quanh khách sạn này.
  const existing = me ? areas.find((a) => a.dest_type === "latlong" && a.dest_id === `${me.lat.toFixed(5)},${me.lng.toFixed(5)}`) : undefined;
  const create = useMutation(async () => {
    if (!me) return;
    const body = {
      name,
      dest_type: "latlong",
      lat: me.lat,
      lng: me.lng,
      radius_m: radius,
      segment_nflt: scope.segment,
      country_code: countryCode(tenant.data?.country_code),
      channel: "booking",
      ...(isOperator ? config : {}),
    } as MarketAreaCreate;
    await api.market.areas.create(body);
    onAdded();
  });

  if (loc.error) return <ErrorBox error={loc.error} />;
  if (loc.data === undefined) return <Skeleton rows={3} />;
  if (!me) {
    return (
      <Note tone="warn" icon={<IconInfo size={16} />}>
        {t.rich("aroundNoCoords", {
          link: (c) => (
            <Link href="/settings" className="font-semibold underline">
              {c}
            </Link>
          ),
        })}
      </Note>
    );
  }
  return (
    <NewAreaForm
      prefix="around"
      heading={
        <>
          {name}
          <span className="mt-0.5 block text-sm font-normal text-muted">
            {t.rich("aroundCenter", {
              name: me.name ?? t("aroundHotelFallback"),
              lat: fmtNum(me.lat, 5),
              lng: fmtNum(me.lng, 5),
              b: (c) => <span className="font-semibold text-body">{c}</span>,
            })}
          </span>
        </>
      }
      notice={
        existing && (
          <Note tone="warn" icon={<IconInfo size={16} />}>
            {t("aroundExists", { name: existing.name })}
          </Note>
        )
      }
      scope={scope}
      onScope={setScope}
      radiusRequired
      config={config}
      onConfig={setConfig}
      busy={create.busy}
      error={create.error}
      disabled={Boolean(existing)}
      onSubmit={() => void create.run()}
    />
  );
}

type AddMode = "search" | "around";

function AddArea({ areas, onAdded }: { areas: MarketAreaOut[]; onAdded: () => void }) {
  const [mode, setMode] = useState<AddMode>("search");
  const t = useTranslations("settings.market.add");
  return (
    <Card title={t("title")} icon={<IconPin size={16} />} info={t("info")}>
      <Segmented
        label={t("mode")}
        value={mode}
        onChange={setMode}
        items={[
          { value: "search", label: t("modeSearch") },
          { value: "around", label: t("modeAround") },
        ]}
      />
      <div className="mt-4">{mode === "search" ? <SearchArea onAdded={onAdded} /> : <AroundHotel areas={areas} onAdded={onAdded} />}</div>
    </Card>
  );
}

function AreaCard({ area, canWrite, onChanged }: { area: MarketAreaOut; canWrite: boolean; onChanged: () => void }) {
  const savedScope: Scope = { radius: asRadius(area.radius_m), segment: area.segment_nflt };
  const [config, setConfig] = useState<Config>({ list_nights: area.list_nights, detail_horizon_days: area.detail_horizon_days, detail_max_hotels: area.detail_max_hotels, max_pages: area.max_pages });
  const [scope, setScope] = useState<Scope>(savedScope);
  const [scanMsg, setScanMsg] = useState<"queued" | "alreadyRunning" | null>(null);
  const t = useTranslations("settings.market");
  const { isOperator } = useSession();
  const { fmtWhen } = useFmt();
  const { segmentLabel } = useMarketAreaText();
  const configDirty = isOperator && config.list_nights !== area.list_nights || config.detail_horizon_days !== area.detail_horizon_days || config.detail_max_hotels !== area.detail_max_hotels || config.max_pages !== area.max_pages;
  const scopeDirty = scope.radius !== savedScope.radius || normalizeNflt(scope.segment) !== normalizeNflt(savedScope.segment);
  const save = useMutation(async () => {
    // Chỉ gửi bán kính/phân khúc khi đổi: PATCH null là xoá.
    // Khách sạn không gửi tham số vận hành (API trả 403 khi đổi).
    await api.market.areas.update(area.id, { ...(isOperator ? config : {}), ...(scopeDirty ? { radius_m: scope.radius, segment_nflt: scope.segment } : {}) });
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
  const description = [
    destTypeLabel(t, area.dest_type),
    area.radius_m ? t("area.radius", { km: area.radius_m / 1000 }) : null,
    segmentLabel(area.segment_nflt),
    t("area.known", { count: area.hotels_total }),
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Card
      title={area.name}
      icon={<IconPin size={16} />}
      description={description}
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
      <div className="mt-4 space-y-4">
        <ScopeFields prefix={`a${area.id}`} value={scope} onChange={setScope} radiusRequired={area.dest_type === "latlong"} disabled={!canWrite} />
        {isOperator && <ConfigFields prefix={`a${area.id}`} value={config} onChange={setConfig} disabled={!canWrite} />}
      </div>
      {canWrite && scopeDirty && (
        <Note tone="info" icon={<IconInfo size={16} />} className="mt-3">
          {t("area.scopeChanged")}
        </Note>
      )}
      {canWrite && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" size="sm" disabled={!configDirty && !scopeDirty} busy={save.busy} onClick={() => void save.run()}>
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
      {canWrite && <AddArea areas={areas.data ?? []} onAdded={areas.reload} />}
      <ErrorBox error={areas.error} />
      {!areas.data && !areas.error && <Skeleton rows={4} />}
      {areas.data && areas.data.length === 0 && (
        <EmptyState icon={<IconPin />} title={t("emptyTitle")} className="border border-line bg-surface">
          {t("emptyBody")}
        </EmptyState>
      )}
      {areas.data?.map((a) => (
        <AreaCard key={`${a.id}:${a.list_nights}:${a.detail_horizon_days}:${a.detail_max_hotels}:${a.max_pages}:${a.radius_m}:${a.segment_nflt}`} area={a} canWrite={canWrite} onChanged={areas.reload} />
      ))}
    </div>
  );
}
