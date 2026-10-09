"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { api, type ChannelOut, type ListingAction, type ListingOut, type ScanRunOut, type WatchItemOut, type WatchItemUpdate } from "@/lib/api";
import { useApi, useInterval, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { BOOKING, hotelTitle, isBookingUrl } from "@/lib/hotels";
import { num, useFmt } from "@/lib/format";
import { useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Note, Segmented, Select, Skeleton, cx } from "@/components/ui";
import { ChipAction, ListingChip } from "@/components/listing-chip";
import { IconAlert, IconBuilding, IconCheck, IconClock, IconLink, IconPause, IconPencil, IconPlay, IconPlus, IconRefresh, IconStar } from "@/components/icons";

type Role = "self" | "competitor";

const ROLES: Role[] = ["competitor", "self"];

type WatchlistT = ReturnType<typeof useTranslations<"settings.watchlist">>;

/** Nhịp tải lại khi đang có đường dẫn chờ kiểm tra. */
const POLL_MS = 5_000;

/** Kiểm tra sơ bộ phía trình duyệt: đường dẫn hợp lệ và là trang Booking.com. */
function urlProblem(raw: string, channels: ChannelOut[], t: WatchlistT): string | null {
  const v = raw.trim();
  if (!v) return t("url.empty");
  try {
    new URL(v);
  } catch {
    return t("url.malformed");
  }
  if (channels.length === 0) return null; // chưa tải được danh sách tên miền: để server kiểm tra
  if (!isBookingUrl(v, channels)) return t("url.notBooking");
  return null;
}

/** Ô nhập URL, có nhãn "Booking.com" ở mép phải khi nhận ra đường dẫn Booking.com. */
function UrlInput({
  id,
  value,
  onChange,
  channels,
  problem,
  placeholder,
  autoFocus,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  channels: ChannelOut[];
  problem: string | null;
  placeholder: string;
  autoFocus?: boolean;
}) {
  const detected = value.trim() !== "" && isBookingUrl(value, channels);
  return (
    <div className="relative">
      <IconLink size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
      <Input
        id={id}
        type="url"
        inputMode="url"
        autoComplete="off"
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={value}
        aria-invalid={problem ? true : undefined}
        aria-describedby={problem ? `${id}-problem` : detected ? `${id}-source` : undefined}
        onChange={(e) => onChange(e.target.value)}
        className={cx("pl-9", detected && "pr-28", problem && "border-danger focus:border-danger focus:ring-danger/15")}
      />
      {detected && (
        <span
          id={`${id}-source`}
          className="pointer-events-none absolute right-1.5 top-1/2 inline-flex h-6 max-w-[104px] -translate-y-1/2 items-center gap-1 truncate rounded-md bg-brand-soft px-2 text-xs font-semibold text-brand-hover"
        >
          <IconCheck size={12} className="shrink-0" />
          {BOOKING}
        </span>
      )}
    </div>
  );
}

function AddForm({ onAdded, hasSelf, channels }: { onAdded: () => void; hasSelf: boolean; channels: ChannelOut[] }) {
  const [url, setUrl] = useState("");
  const [role, setRole] = useState<Role>(hasSelf ? "competitor" : "self");
  const [label, setLabel] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const t = useTranslations("settings.watchlist");
  const labelOf = useLabel();
  const add = useMutation(async () => {
    const item = await api.watchlist.add({ url: url.trim(), role, label: label.trim() || null });
    setAdded(hotelTitle(item.hotel, item.label));
    setUrl("");
    setLabel("");
    onAdded();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    const p = urlProblem(url, channels, t);
    setProblem(p);
    setAdded(null);
    if (!p) void add.run();
  }
  return (
    <Card title={t("add.title")} description={t("add.description")}>
      <form onSubmit={submit} noValidate className="space-y-3">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,1fr)_auto_200px_auto] lg:items-end">
          <Field label={t("add.urlLabel")} htmlFor="wl-url">
            <UrlInput
              id="wl-url"
              value={url}
              channels={channels}
              problem={problem}
              placeholder={t("add.urlPlaceholder")}
              onChange={(v) => {
                setUrl(v);
                if (problem) setProblem(null);
              }}
            />
          </Field>
          <div className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">{t("add.role")}</span>
            <Segmented label={t("add.role")} value={role} onChange={setRole} items={ROLES.map((r) => ({ value: r, label: labelOf("watchRole", r) }))} className="self-start" />
          </div>
          <Field label={t("add.labelField")} htmlFor="wl-label">
            <Input id="wl-label" maxLength={120} placeholder={t("add.labelPlaceholder")} value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          <Button type="submit" variant="primary" busy={add.busy} icon={<IconPlus size={16} />} className="md:col-span-2 md:justify-self-start lg:col-span-1">
            {t("add.submit")}
          </Button>
        </div>
        {problem && (
          <p id="wl-url-problem" role="alert" className="text-sm text-danger">
            {problem}
          </p>
        )}
        <ErrorBox error={add.error} title={t("add.errorTitle")} />
        {added && !add.error && (
          <p role="status" className="flex items-start gap-1.5 text-sm text-yours-deep">
            <IconCheck size={16} className="mt-0.5 shrink-0" />
            <span>{t("add.added", { name: added })}</span>
          </p>
        )}
      </form>
    </Card>
  );
}

/** Chip trang Booking.com của khách sạn kèm thao tác phù hợp trạng thái. */
function ListingControl({ hotelId, listing, canWrite, isOperator, onChanged }: { hotelId: number; listing: ListingOut; canWrite: boolean; isOperator: boolean; onChanged: () => void }) {
  const act = useMutation(async (action: ListingAction) => {
    await api.watchlist.listingAction(hotelId, listing.id, action);
    onChanged();
  });
  const t = useTranslations("settings.watchlist.listing");
  const s = listing.status;
  return (
    <>
      <ListingChip listing={listing}>
        {canWrite && s === "broken" && (
          <ChipAction onClick={() => void act.run("retry")} busy={act.busy} title={isOperator && listing.last_error ? listing.last_error : t("retryTitle")}>
            <IconRefresh size={13} /> {t("retry")}
          </ChipAction>
        )}
        {canWrite && s === "paused" && (
          <ChipAction onClick={() => void act.run("resume")} busy={act.busy} title={t("resumeTitle")}>
            <IconPlay size={13} /> {t("resume")}
          </ChipAction>
        )}
        {canWrite && s === "active" && (
          <ChipAction tone="muted" onClick={() => void act.run("pause")} busy={act.busy} label={t("pauseLabel")} title={t("pauseTitle")}>
            <IconPause size={13} />
          </ChipAction>
        )}
      </ListingChip>
      {act.error && (
        <li role="alert" className="basis-full text-sm text-danger">
          {act.error}
        </li>
      )}
    </>
  );
}

/** Thay URL Booking.com của khách sạn (đường dẫn lỗi hoặc dán nhầm). */
function ReplaceUrlForm({ hotelId, channels, onDone, onCancel }: { hotelId: number; channels: ChannelOut[]; onDone: () => void; onCancel: () => void }) {
  const [url, setUrl] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const id = `wl-url-${hotelId}`;
  const t = useTranslations("settings.watchlist");
  const tc = useTranslations("common.actions");
  const replace = useMutation(async () => {
    await api.watchlist.addListing(hotelId, url.trim());
    onDone();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    const p = urlProblem(url, channels, t);
    setProblem(p);
    if (!p) void replace.run();
  }
  return (
    <form onSubmit={submit} noValidate className="mt-2.5 space-y-2 rounded-lg bg-subtle p-3">
      <label htmlFor={id} className="block text-sm font-semibold text-body">
        {t("replaceUrl.label")}
      </label>
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1 basis-64">
          <UrlInput
            id={id}
            autoFocus
            value={url}
            channels={channels}
            problem={problem}
            placeholder={t("add.urlPlaceholder")}
            onChange={(v) => {
              setUrl(v);
              if (problem) setProblem(null);
            }}
          />
        </div>
        <Button type="submit" variant="primary" busy={replace.busy} icon={<IconCheck size={16} />}>
          {t("replaceUrl.submit")}
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          {tc("cancel")}
        </Button>
      </div>
      {problem && (
        <p id={`${id}-problem`} role="alert" className="text-sm text-danger">
          {problem}
        </p>
      )}
      {replace.error && (
        <p role="alert" className="text-sm text-danger">
          {replace.error}
        </p>
      )}
      {!problem && !replace.error && <p className="text-xs text-muted">{t("replaceUrl.note")}</p>}
    </form>
  );
}

type OwnHotelOption = { id: number; name: string };

/**
 * Cài đặt compset của một khách sạn (roadmap 7.3, 5.5, 5.6): compset chính/phụ (chỉ compset chính
 * vào trung vị, chỉ số giá, vị trí giá), thuộc compset của khách sạn nào (khi có từ hai khách sạn của
 * bạn), tổng số phòng công bố.
 */
function CompsetControls({ item, ownHotels, canWrite, onChanged }: { item: WatchItemOut; ownHotels: OwnHotelOption[]; canWrite: boolean; onChanged: () => void }) {
  const t = useTranslations("settings.watchlist.compset");
  const { fmtInt, fmtNum } = useFmt();
  const current = item.hotel.rooms_total ?? null;
  const [rooms, setRooms] = useState(current === null ? "" : String(current));
  const patch = useMutation(async (body: WatchItemUpdate) => {
    await api.watchlist.update(item.hotel.id, body);
    onChanged();
  });
  const isComp = item.role !== "self";
  const editable = canWrite && item.active;
  const score = num(item.hotel.review_score);

  function commitRooms() {
    const raw = rooms.trim();
    const next = raw === "" ? null : Number(raw);
    if (next !== null && (!Number.isInteger(next) || next < 1 || next > 5000)) {
      setRooms(current === null ? "" : String(current));
      return;
    }
    if (next === current) return;
    void patch.run({ rooms_total: next });
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
      {isComp && (
        <span className="inline-flex items-center gap-2" title={t("tierTitle")}>
          <span className="whitespace-nowrap text-muted">{t("tier")}</span>
          {editable ? (
            <Segmented
              size="sm"
              label={t("tier")}
              value={item.tier}
              onChange={(v) => v !== item.tier && void patch.run({ tier: v })}
              items={[
                { value: "primary", label: t("primary"), title: t("primaryTitle") },
                { value: "secondary", label: t("secondary"), title: t("secondaryTitle") },
              ]}
            />
          ) : (
            <Badge tone={item.tier === "primary" ? "blue" : "gray"}>{item.tier === "primary" ? t("primary") : t("secondary")}</Badge>
          )}
        </span>
      )}
      {isComp && ownHotels.length >= 2 && (
        <label className="inline-flex items-center gap-2" title={t("compsetOfTitle")}>
          <span className="whitespace-nowrap text-muted">{t("compsetOf")}</span>
          <Select
            value={item.compset_of ?? ""}
            disabled={!editable || patch.busy}
            onChange={(e) => void patch.run({ compset_of: e.target.value ? Number(e.target.value) : null })}
            className="w-52"
          >
            <option value="">{t("shared")}</option>
            {ownHotels.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}
              </option>
            ))}
          </Select>
        </label>
      )}
      <label className="inline-flex items-center gap-2" title={t("roomsTitle")}>
        <span className="whitespace-nowrap text-muted">{t("rooms")}</span>
        {editable ? (
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={5000}
            placeholder={t("roomsPlaceholder")}
            value={rooms}
            onChange={(e) => setRooms(e.target.value)}
            onBlur={commitRooms}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commitRooms();
              }
            }}
            aria-label={t("roomsAria", { name: hotelTitle(item.hotel, item.label) })}
            className="w-24 tabular"
          />
        ) : (
          <span className="font-semibold text-ink tabular">{current === null ? "—" : fmtInt(current)}</span>
        )}
      </label>
      {score !== null && (
        <span className="inline-flex items-center gap-1 text-muted" title={t("reviewTitle")}>
          <IconStar size={13} className="text-[#e0a100]" />
          <span className="font-semibold text-ink tabular">{fmtNum(score, 1)}</span>
          {item.hotel.review_count ? <span className="tabular">{t("reviews", { count: item.hotel.review_count })}</span> : null}
        </span>
      )}
      {patch.busy && <span className="text-xs text-muted">{t("saving")}</span>}
      {patch.error && (
        <span role="alert" className="basis-full text-sm text-danger">
          {patch.error}
        </span>
      )}
    </div>
  );
}

/**
 * Rà soát compset theo quy tắc CoStar STR: ≥4 đối thủ compset chính, không khách sạn nào quá 50% số
 * phòng compset, rà soát ít nhất 2 lần/năm. Một thẻ cho mỗi khách sạn của bạn (khi có từ hai).
 */
function CompsetReview({ ownHotel, items, version }: { ownHotel: OwnHotelOption | null; items: WatchItemOut[]; version: number }) {
  const t = useTranslations("settings.watchlist.review");
  const { fmtDate, fmtNum } = useFmt();
  const q = useApi(`compset-review:${ownHotel?.id ?? ""}:${version}`, () => api.watchlist.compsetReview(ownHotel?.id ?? null));
  const r = q.data;
  const nameOf = (id: number | null | undefined) => {
    const w = items.find((x) => x.hotel.id === id);
    return w ? hotelTitle(w.hotel, w.label) : t("hotelFallback", { id: id ?? 0 });
  };
  function warning(code: string): string {
    if (!r) return code;
    switch (code) {
      case "too_few":
        return t("warn.too_few", { count: r.primary });
      case "dominant_hotel": {
        const share = num(r.dominant_share);
        return t("warn.dominant_hotel", { name: nameOf(r.dominant_hotel_id), pct: share === null ? "—" : fmtNum(share * 100, 0) });
      }
      case "rooms_unknown":
        return t("warn.rooms_unknown", { count: Math.max(0, r.primary - r.rooms_known) });
      case "review_due":
        return r.last_change_at ? t("warn.review_due", { date: fmtDate(r.last_change_at) }) : t("warn.review_due_never");
      default:
        return code;
    }
  }
  return (
    <section className="mx-5 mb-2 mt-3 rounded-lg border border-line bg-subtle px-4 py-3" aria-label={t("aria")}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="text-sm font-bold text-ink">{ownHotel ? t("titleFor", { name: ownHotel.name }) : t("title")}</h4>
        {r && <span className="text-xs text-muted tabular">{t("counts", { primary: r.primary, secondary: r.secondary, known: r.rooms_known })}</span>}
      </div>
      {q.error && <ErrorBox error={q.error} className="mt-2" />}
      {!r && !q.error && <Skeleton rows={1} className="mt-2" />}
      {r &&
        (r.warnings.length === 0 ? (
          <p className="mt-1.5 flex items-center gap-1.5 text-sm text-yours-deep">
            <IconCheck size={14} className="shrink-0" /> {t("ok")}
          </p>
        ) : (
          <ul className="mt-1.5 space-y-1">
            {r.warnings.map((w) => (
              <li key={w} className="flex items-start gap-1.5 text-sm text-warning-deep">
                <IconAlert size={14} className="mt-0.5 shrink-0" />
                <span>{warning(w)}</span>
              </li>
            ))}
          </ul>
        ))}
      <p className="mt-1.5 text-xs text-muted">{t("rules")}</p>
    </section>
  );
}

function Row({
  item,
  canWrite,
  isOperator,
  channels,
  ownHotels,
  onChanged,
}: {
  item: WatchItemOut;
  canWrite: boolean;
  isOperator: boolean;
  channels: ChannelOut[];
  ownHotels: OwnHotelOption[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [label, setLabel] = useState(item.label ?? "");
  const [role, setRole] = useState<string>(item.role);
  const t = useTranslations("settings.watchlist.row");
  const tc = useTranslations("common.actions");
  const labelOf = useLabel();
  const { fmtDate } = useFmt();
  const save = useMutation(async () => {
    await api.watchlist.update(item.hotel.id, { label: label.trim() || null, role });
    setEditing(false);
    onChanged();
  });
  const toggle = useMutation(async () => {
    if (item.active) await api.watchlist.remove(item.hotel.id);
    else await api.watchlist.update(item.hotel.id, { active: true });
    onChanged();
  });
  const name = hotelTitle(item.hotel, item.label);
  const fullName = item.hotel.name && item.hotel.name !== name ? item.hotel.name : null;
  const listings = item.hotel.listings;
  const pending = item.active && !listings.some((l) => l.verified_at) && !item.hotel.name;

  return (
    <li className={cx("px-5 py-3.5", !item.active && "bg-subtle/60")}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <Link
              href={`/hotels/${item.hotel.id}`}
              className={cx("min-w-0 max-w-full truncate text-md font-semibold hover:text-brand hover:underline", item.active ? "text-ink" : "text-muted")}
              title={item.hotel.name ?? undefined}
            >
              {name}
            </Link>
            {!item.active && <Badge tone="gray">{t("stopped")}</Badge>}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted">
            {fullName && <span className="max-w-full truncate">{fullName}</span>}
            {fullName && item.hotel.city && <span aria-hidden>·</span>}
            {item.hotel.city && <span>{item.hotel.city}</span>}
            {(fullName || item.hotel.city) && <span aria-hidden>·</span>}
            <span className="tabular">{t("addedOn", { date: fmtDate(item.added_at) })}</span>
            {pending && (
              <span className="inline-flex items-center gap-1 text-warning-deep">
                · <IconClock size={12} /> {t("pendingFirst")}
              </span>
            )}
          </div>
          {item.active && <CompsetControls item={item} ownHotels={ownHotels} canWrite={canWrite} onChanged={onChanged} />}
          {editing && (
            <div className="mt-2 flex flex-wrap gap-2">
              <Input aria-label={t("labelAria")} value={label} maxLength={120} placeholder={t("labelPlaceholder")} onChange={(e) => setLabel(e.target.value)} className="w-56 max-w-full" />
              <Select aria-label={t("roleAria")} value={role} onChange={(e) => setRole(e.target.value)} className="w-48">
                <option value="competitor">{labelOf("watchRole", "competitor")}</option>
                <option value="self">{labelOf("watchRole", "self")}</option>
              </Select>
            </div>
          )}
        </div>
        {canWrite && (
          <div className="flex shrink-0 justify-end gap-1">
            {editing ? (
              <>
                <Button size="sm" variant="primary" busy={save.busy} onClick={() => void save.run()}>
                  {tc("save")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditing(false);
                    setLabel(item.label ?? "");
                    setRole(item.role);
                    save.clearError();
                  }}
                >
                  {tc("cancel")}
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="ghost" icon={<IconPencil size={15} />} onClick={() => setEditing(true)} aria-label={t("editAria", { name })}>
                  <span className="hidden sm:inline">{tc("edit")}</span>
                </Button>
                <Button
                  size="sm"
                  variant={item.active ? "ghost" : "quiet"}
                  busy={toggle.busy}
                  icon={item.active ? <IconPause size={15} /> : <IconPlay size={15} />}
                  onClick={() => void toggle.run()}
                  title={item.active ? t("stopTitle") : t("resumeTitle")}
                  aria-label={item.active ? t("stopAria", { name }) : t("resumeAria", { name })}
                >
                  <span className="hidden sm:inline">{item.active ? t("stop") : t("resume")}</span>
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      <ul aria-label={t("listingAria", { name })} className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {listings.map((l) => (
          <ListingControl key={l.id} hotelId={item.hotel.id} listing={l} canWrite={canWrite && item.active} isOperator={isOperator} onChanged={onChanged} />
        ))}
        {canWrite && item.active && !replacing && (
          <li>
            <Button size="sm" variant="quiet" icon={listings.length ? <IconLink size={15} /> : <IconPlus size={15} />} onClick={() => setReplacing(true)} className="h-8" title={t("replaceUrlTitle")}>
              {listings.length ? t("replaceUrl") : t("addUrl")}
            </Button>
          </li>
        )}
      </ul>
      {replacing && (
        <ReplaceUrlForm
          hotelId={item.hotel.id}
          channels={channels}
          onCancel={() => setReplacing(false)}
          onDone={() => {
            setReplacing(false);
            onChanged();
          }}
        />
      )}
      {(save.error || toggle.error) && <ErrorBox error={save.error ?? toggle.error} className="mt-2" />}
    </li>
  );
}

function Group({
  title,
  items,
  empty,
  self,
  children,
  ...rowProps
}: {
  title: string;
  items: WatchItemOut[];
  empty: string;
  self?: boolean;
  /** Nội dung chèn dưới tiêu đề nhóm (VD thẻ rà soát compset). */
  children?: ReactNode;
  canWrite: boolean;
  isOperator: boolean;
  channels: ChannelOut[];
  ownHotels: OwnHotelOption[];
  onChanged: () => void;
}) {
  return (
    <section>
      <h3 className="flex items-center gap-2 px-5 pb-1 pt-4 text-base font-bold text-ink">
        {self && <span aria-hidden className="h-2 w-2 rounded-full bg-yours" />}
        {title}
        <span className="rounded-full bg-sunken px-1.5 text-xs font-semibold text-muted tabular">{items.length}</span>
      </h3>
      {children}
      {items.length === 0 ? (
        <p className="mx-5 mb-4 mt-1 rounded-lg bg-subtle px-4 py-3 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((it) => (
            <Row key={it.hotel.id} item={it} {...rowProps} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function WatchlistTab() {
  const { canWrite, isOperator } = useSession();
  const list = useApi("watchlist:inactive", () => api.watchlist.list(true));
  const channelsApi = useApi("channels", () => api.channels());
  const channels = channelsApi.data ?? [];
  const items = list.data ?? [];
  const selfItems = items.filter((it) => it.role === "self");
  const compItems = items.filter((it) => it.role !== "self");
  const activeCount = items.filter((it) => it.active).length;
  const [runs, setRuns] = useState<ScanRunOut[] | null>(null);
  const scan = useMutation(async () => setRuns(await api.watchlist.scanNow()));
  const t = useTranslations("settings.watchlist.list");
  // Đổi compset (chính/phụ, số phòng…) thì tải lại thẻ rà soát.
  const [reviewVersion, setReviewVersion] = useState(0);
  const ownHotels: OwnHotelOption[] = selfItems.filter((it) => it.active).map((it) => ({ id: it.hotel.id, name: hotelTitle(it.hotel, it.label) }));

  // Đường dẫn vừa thêm/thay cần worker kiểm tra: tải lại tới khi xong.
  const checking = items.some((it) => it.active && it.hotel.listings.some((l) => l.status === "unverified"));
  useInterval(() => list.reload(), checking ? POLL_MS : 0);
  function handleChanged() {
    list.reload();
    setReviewVersion((v) => v + 1);
  }
  const rowProps = { canWrite, isOperator, channels, ownHotels, onChanged: handleChanged };

  return (
    <div className="space-y-5">
      {canWrite && list.data && <AddForm onAdded={list.reload} hasSelf={selfItems.length > 0} channels={channels} />}
      <ErrorBox error={list.error} />
      {!list.data && !list.error ? (
        <Card>
          <Skeleton rows={5} />
        </Card>
      ) : list.data && items.length === 0 ? (
        <EmptyState icon={<IconBuilding />} title={t("emptyTitle")} className="border border-line bg-surface">
          {canWrite ? t("emptyWrite") : t("emptyRead")}
        </EmptyState>
      ) : (
        list.data && (
          <Card
            padded={false}
            title={t("title")}
            description={
              <>
                {t("summary", { count: items.length, active: activeCount })}
                {checking && (
                  <span className="ml-2 inline-flex items-center gap-1.5 text-brand-hover">
                    <span aria-hidden className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
                    {t("checking")}
                  </span>
                )}
              </>
            }
            actions={
              canWrite ? (
                <Button
                  size="sm"
                  busy={scan.busy}
                  disabled={activeCount === 0}
                  icon={<IconRefresh size={15} />}
                  onClick={() => void scan.run()}
                  title={t("scanNowTitle")}
                >
                  {t("scanNow")}
                </Button>
              ) : undefined
            }
          >
            {(runs || scan.error) && (
              <div className="px-5 pt-4">
                {runs && (
                  <Note tone="info" icon={<IconCheck size={16} />}>
                    {runs.length === 0 ? t("noneReady") : t("scanStarted")}
                  </Note>
                )}
                <ErrorBox error={scan.error} title={t("scanErrorTitle")} />
              </div>
            )}
            <Group
              self
              title={t("selfTitle")}
              items={selfItems}
              empty={t("selfEmpty")}
              {...rowProps}
            />
            <div className="border-t border-line">
              <Group title={t("compTitle")} items={compItems} empty={t("compEmpty")} {...rowProps}>
                {compItems.length > 0 &&
                  (ownHotels.length >= 2 ? (
                    ownHotels.map((h) => <CompsetReview key={h.id} ownHotel={h} items={items} version={reviewVersion} />)
                  ) : (
                    <CompsetReview ownHotel={null} items={items} version={reviewVersion} />
                  ))}
              </Group>
            </div>
            <div className="border-t border-line px-5 py-3 text-xs text-muted">
              {t("legend")}
            </div>
          </Card>
        )
      )}
    </div>
  );
}
