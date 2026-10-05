"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type ChannelOut, type ListingAction, type ListingOut, type ScanRunOut, type WatchItemOut } from "@/lib/api";
import { useApi, useInterval, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { channelName, detectChannel, hotelTitle } from "@/lib/channels";
import { useFmt } from "@/lib/format";
import { useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Note, Segmented, Select, Skeleton, cx } from "@/components/ui";
import { ChipAction, ListingChip } from "@/components/channels";
import { IconBuilding, IconCheck, IconClock, IconClose, IconLink, IconPause, IconPencil, IconPlay, IconPlus, IconRefresh, IconSearch } from "@/components/icons";

type Role = "self" | "competitor";

const ROLES: Role[] = ["competitor", "self"];

type WatchlistT = ReturnType<typeof useTranslations<"settings.watchlist">>;

/** Nhịp tải lại khi đang có kênh chờ kiểm tra hoặc đang tìm trên kênh khác. */
const POLL_MS = 5_000;
/** Sau "Tìm trên kênh khác": tiếp tục tải lại chừng này để gợi ý hiện ra. */
const DISCOVER_WINDOW_MS = 90_000;

function supportedNames(channels: ChannelOut[]): string {
  return channels
    .filter((c) => c.collectable)
    .map((c) => c.name)
    .join(", ");
}

/** Kiểm tra sơ bộ phía trình duyệt: đường dẫn hợp lệ và thuộc một kênh đang quét được. */
function urlProblem(raw: string, channels: ChannelOut[], t: WatchlistT): string | null {
  const v = raw.trim();
  if (!v) return t("url.empty");
  try {
    new URL(v);
  } catch {
    return t("url.malformed");
  }
  if (channels.length === 0) return null; // chưa tải được danh sách kênh: để server kiểm tra
  const ch = detectChannel(v, channels);
  const supported = supportedNames(channels);
  if (!ch) return t("url.unsupported", { channels: supported });
  if (!ch.collectable) return t("url.notCollectable", { channel: ch.name, channels: supported });
  return null;
}

/** Ô nhập URL có nhãn kênh nhận ra được ở mép phải. */
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
  const detected = value.trim() ? detectChannel(value, channels) : null;
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
        aria-describedby={problem ? `${id}-problem` : `${id}-channel`}
        onChange={(e) => onChange(e.target.value)}
        className={cx("pl-9", detected && "pr-28", problem && "border-danger focus:border-danger focus:ring-danger/15")}
      />
      {detected && (
        <span
          id={`${id}-channel`}
          className={cx(
            "pointer-events-none absolute right-1.5 top-1/2 inline-flex h-6 max-w-[104px] -translate-y-1/2 items-center gap-1 truncate rounded-md px-2 text-xs font-semibold",
            detected.collectable ? "bg-brand-soft text-brand-hover" : "bg-sunken text-muted",
          )}
        >
          {detected.collectable && <IconCheck size={12} className="shrink-0" />}
          {detected.name}
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
  const [added, setAdded] = useState<{ name: string; channel: string } | null>(null);
  const t = useTranslations("settings.watchlist");
  const labelOf = useLabel();
  const add = useMutation(async () => {
    const item = await api.watchlist.add({ url: url.trim(), role, label: label.trim() || null });
    const channel = detectChannel(url, channels)?.code ?? item.hotel.listings[0]?.channel ?? "";
    setAdded({ name: hotelTitle(item.hotel, item.label), channel });
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
  const supported = supportedNames(channels);
  return (
    <Card
      title={t("add.title")}
      description={supported ? t("add.description", { channels: supported }) : t("add.descriptionAny")}
    >
      <form onSubmit={submit} noValidate className="space-y-3">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,1fr)_auto_200px_auto] lg:items-end">
          <Field label={t("add.urlLabel")} htmlFor="wl-url">
            <UrlInput
              id="wl-url"
              value={url}
              channels={channels}
              problem={problem}
              placeholder={supported ? t("add.urlPlaceholder", { channels: supported }) : t("add.urlPlaceholderAny")}
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
        {problem ? (
          <p id="wl-url-problem" role="alert" className="text-sm text-danger">
            {problem}
          </p>
        ) : (
          supported && <p className="text-xs text-muted">{t("add.supported", { channels: supported })}</p>
        )}
        <ErrorBox error={add.error} title={t("add.errorTitle")} />
        {added && !add.error && (
          <p role="status" className="flex items-start gap-1.5 text-sm text-yours-deep">
            <IconCheck size={16} className="mt-0.5 shrink-0" />
            <span>
              {added.channel ? t("add.addedOn", { name: added.name, channel: channelName(added.channel) }) : t("add.added", { name: added.name })}
            </span>
          </p>
        )}
      </form>
    </Card>
  );
}

/** Chip một kênh kèm thao tác phù hợp trạng thái. */
function ListingControl({ hotelId, listing, canWrite, isOperator, onChanged }: { hotelId: number; listing: ListingOut; canWrite: boolean; isOperator: boolean; onChanged: () => void }) {
  const act = useMutation(async (action: ListingAction) => {
    await api.watchlist.listingAction(hotelId, listing.id, action);
    onChanged();
  });
  const t = useTranslations("settings.watchlist.listing");
  const name = channelName(listing.channel);
  const s = listing.status;
  return (
    <>
      <ListingChip listing={listing}>
        {canWrite && s === "suggested" && (
          <>
            <ChipAction onClick={() => void act.run("confirm")} busy={act.busy} title={t("confirmTitle", { channel: name })}>
              <IconCheck size={13} /> {t("confirm")}
            </ChipAction>
            <ChipAction tone="muted" onClick={() => void act.run("reject")} busy={act.busy} title={t("rejectTitle")}>
              {t("reject")}
            </ChipAction>
          </>
        )}
        {canWrite && s === "broken" && (
          <ChipAction onClick={() => void act.run("retry")} busy={act.busy} title={isOperator && listing.last_error ? listing.last_error : t("retryTitle", { channel: name })}>
            <IconRefresh size={13} /> {t("retry")}
          </ChipAction>
        )}
        {canWrite && s === "paused" && (
          <ChipAction onClick={() => void act.run("resume")} busy={act.busy} title={t("resumeTitle", { channel: name })}>
            <IconPlay size={13} /> {t("resume")}
          </ChipAction>
        )}
        {canWrite && s === "active" && (
          <ChipAction tone="muted" onClick={() => void act.run("pause")} busy={act.busy} label={t("pauseLabel", { channel: name })} title={t("pauseTitle", { channel: name })}>
            <IconPause size={13} />
          </ChipAction>
        )}
      </ListingChip>
      {act.error && (
        <li role="alert" className="basis-full text-sm text-danger">
          {name}: {act.error}
        </li>
      )}
    </>
  );
}

function AddListingForm({ hotelId, channels, onDone, onCancel }: { hotelId: number; channels: ChannelOut[]; onDone: () => void; onCancel: () => void }) {
  const [url, setUrl] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const id = `wl-add-${hotelId}`;
  const t = useTranslations("settings.watchlist");
  const tc = useTranslations("common.actions");
  const add = useMutation(async () => {
    await api.watchlist.addListing(hotelId, url.trim());
    onDone();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    const p = urlProblem(url, channels, t);
    setProblem(p);
    if (!p) void add.run();
  }
  return (
    <form onSubmit={submit} noValidate className="mt-2.5 space-y-2 rounded-lg bg-subtle p-3">
      <label htmlFor={id} className="block text-sm font-semibold text-body">
        {t("addListing.label")}
      </label>
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1 basis-64">
          <UrlInput
            id={id}
            autoFocus
            value={url}
            channels={channels}
            problem={problem}
            placeholder={t("addListing.placeholder")}
            onChange={(v) => {
              setUrl(v);
              if (problem) setProblem(null);
            }}
          />
        </div>
        <Button type="submit" variant="primary" busy={add.busy} icon={<IconPlus size={16} />}>
          {t("addListing.submit")}
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
      {add.error && (
        <p role="alert" className="text-sm text-danger">
          {add.error}
        </p>
      )}
      {!problem && !add.error && <p className="text-xs text-muted">{t("addListing.replaceNote")}</p>}
    </form>
  );
}

function Row({ item, canWrite, isOperator, channels, onChanged, onDiscover }: { item: WatchItemOut; canWrite: boolean; isOperator: boolean; channels: ChannelOut[]; onChanged: () => void; onDiscover: () => void }) {
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [label, setLabel] = useState(item.label ?? "");
  const [role, setRole] = useState<string>(item.role);
  const [searched, setSearched] = useState<string[] | null>(null);
  const t = useTranslations("settings.watchlist.row");
  const tc = useTranslations("common.actions");
  const labelOf = useLabel();
  const { fmtDate } = useFmt();
  const name = hotelTitle(item.hotel, item.label);
  const save = useMutation(async () => {
    await api.watchlist.update(item.hotel.id, { label: label.trim() || null, role });
    setEditing(false);
    onChanged();
  });
  const toggle = useMutation(async () => {
    if (item.active) {
      // Ngừng quét = gỡ khỏi watchlist trên mọi kênh (bật lại được): hỏi lại trước khi làm.
      if (!window.confirm(t("stopConfirm", { name }))) return;
      await api.watchlist.remove(item.hotel.id);
    } else {
      await api.watchlist.update(item.hotel.id, { active: true });
    }
    onChanged();
  });
  const discover = useMutation(async () => {
    const out = await api.watchlist.discover(item.hotel.id);
    setSearched(out.channels ?? []);
    onDiscover();
  });
  const fullName = item.hotel.name && item.hotel.name !== name ? item.hotel.name : null;
  const listings = item.hotel.listings;
  const pending = item.active && !listings.some((l) => l.verified_at) && !item.hotel.name;
  const missing = channels.filter((c) => c.collectable && !listings.some((l) => l.channel === c.code));

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

      <ul aria-label={t("channelsAria", { name })} className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {listings.map((l) => (
          <ListingControl key={l.id} hotelId={item.hotel.id} listing={l} canWrite={canWrite && item.active} isOperator={isOperator} onChanged={onChanged} />
        ))}
        {canWrite && item.active && !adding && (
          <li>
            <Button size="sm" variant="quiet" icon={<IconPlus size={15} />} onClick={() => setAdding(true)} className="h-8">
              {t("addChannel")}
            </Button>
          </li>
        )}
        {canWrite && item.active && missing.length > 0 && (
          <li>
            <Button
              size="sm"
              variant="quiet"
              busy={discover.busy}
              icon={<IconSearch size={15} />}
              onClick={() => void discover.run()}
              className="h-8"
              title={t("discoverTitle", { channels: missing.map((c) => c.name).join(", ") })}
            >
              {t("discover")}
            </Button>
          </li>
        )}
      </ul>
      {searched && !discover.error && (
        <p role="status" className="mt-2 flex items-center gap-1.5 text-sm text-muted">
          {searched.length > 0 ? (
            <>
              <IconSearch size={14} className="shrink-0" /> {t("searching", { channels: searched.map(channelName).join(", ") })}
            </>
          ) : (
            t("allChannels")
          )}
          <button type="button" aria-label={t("dismiss")} onClick={() => setSearched(null)} className="ml-1 grid h-6 w-6 place-items-center rounded-md text-faint hover:bg-sunken hover:text-ink">
            <IconClose size={13} />
          </button>
        </p>
      )}
      {adding && (
        <AddListingForm
          hotelId={item.hotel.id}
          channels={channels}
          onCancel={() => setAdding(false)}
          onDone={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}
      {(save.error || toggle.error || discover.error) && <ErrorBox error={save.error ?? toggle.error ?? discover.error} className="mt-2" />}
    </li>
  );
}

function Group({
  title,
  items,
  empty,
  self,
  ...rowProps
}: {
  title: string;
  items: WatchItemOut[];
  empty: string;
  self?: boolean;
  canWrite: boolean;
  isOperator: boolean;
  channels: ChannelOut[];
  onChanged: () => void;
  onDiscover: () => void;
}) {
  return (
    <section>
      <h3 className="flex items-center gap-2 px-5 pb-1 pt-4 text-base font-bold text-ink">
        {self && <span aria-hidden className="h-2 w-2 rounded-full bg-yours" />}
        {title}
        <span className="rounded-full bg-sunken px-1.5 text-xs font-semibold text-muted tabular">{items.length}</span>
      </h3>
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

  // Kênh vừa thêm cần worker kiểm tra; gợi ý từ kênh khác đến sau "Tìm trên kênh khác".
  const checking = items.some((it) => it.active && it.hotel.listings.some((l) => l.status === "unverified"));
  const [discoverUntil, setDiscoverUntil] = useState(0);
  useInterval(
    () => {
      if (discoverUntil > 0 && Date.now() > discoverUntil) setDiscoverUntil(0);
      list.reload();
    },
    checking || discoverUntil > 0 ? POLL_MS : 0,
  );
  const rowProps = {
    canWrite,
    isOperator,
    channels,
    onChanged: list.reload,
    onDiscover: () => setDiscoverUntil(Date.now() + DISCOVER_WINDOW_MS),
  };

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
                    {runs.length === 0 ? t("noChannelsReady") : t("scanStarted", { channels: runs.map((r) => channelName(r.channel)).join(", ") })}
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
              <Group title={t("compTitle")} items={compItems} empty={t("compEmpty")} {...rowProps} />
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
