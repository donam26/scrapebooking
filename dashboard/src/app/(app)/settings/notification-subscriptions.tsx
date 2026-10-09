"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent, type ReactNode } from "react";
import { api, type EngagementWeekOut, type NotificationSettingsOut, type NotifyChannel, type SubscriptionIn, type SubscriptionKind, type SubscriptionOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { num, useFmt } from "@/lib/format";
import { useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, ROW_CLASS, Select, Skeleton, Switch, Table, Td, Th, cx } from "@/components/ui";
import { IconAlert, IconBell, IconCheck, IconLink, IconMail, IconPencil, IconPlus, IconTrash, IconTrend } from "@/components/icons";

/** Nhóm tin của một đăng ký (rỗng = mọi loại), khớp `SubscriptionIn.kinds` ở backend. */
const SUB_KINDS: readonly SubscriptionKind[] = ["alerts", "daily_insight", "weekly_report", "data_stale"];
const CHANNEL_ORDER: readonly NotifyChannel[] = ["email", "zalo", "webhook"];

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const HHMM_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

/** "0912 345 678", "+84 912 345 678" → "84912345678"; sai thì null (khớp `normalize_vn_phone`). */
export function normalizeVnPhone(raw: string): string | null {
  let digits = raw.replace(/\D/g, "");
  if (digits.startsWith("0")) digits = `84${digits.slice(1)}`;
  if (!digits.startsWith("84") || digits.length < 11 || digits.length > 12) return null;
  return digits;
}

function validWebhook(raw: string): boolean {
  if (!raw.startsWith("https://")) return false;
  try {
    return new URL(raw).hostname.includes(".");
  } catch {
    return false;
  }
}

function channelIcon(channel: string, size = 16): ReactNode {
  if (channel === "email") return <IconMail size={size} />;
  if (channel === "webhook") return <IconLink size={size} />;
  return <IconBell size={size} />;
}

/** Chip kênh gửi (email/Zalo/webhook) dùng chung cho đăng ký, nhật ký gửi và bảng hiệu quả. */
export function ChannelChip({ channel }: { channel: string }) {
  const label = useLabel();
  return (
    <span className="inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-full bg-sunken px-2 text-xs font-semibold text-body">
      <span aria-hidden className="text-muted">
        {channelIcon(channel, 12)}
      </span>
      {label("notifyChannel", channel)}
    </span>
  );
}

// ---- Kênh gửi ----

export function ChannelStatus({ data }: { data: NotificationSettingsOut }) {
  const t = useTranslations("settings.notifications.channels");
  const channels = CHANNEL_ORDER.filter((c) => data.channels.includes(c));
  const ready: Record<NotifyChannel, boolean> = { email: data.email_configured, zalo: data.zalo_configured, webhook: true };
  return (
    <Card title={t("title")} description={t("description")}>
      <ul className="grid gap-3 md:grid-cols-3">
        {channels.map((c) => {
          const on = ready[c];
          return (
            <li key={c} className={cx("flex min-w-0 flex-col gap-1.5 rounded-lg border px-4 py-3", on ? "border-line" : "border-dashed border-line-strong bg-subtle")}>
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-base font-bold text-ink">
                  <span aria-hidden className={on ? "text-brand" : "text-faint"}>
                    {channelIcon(c)}
                  </span>
                  {t(`${c}.name`)}
                </span>
                <Badge tone={on ? "green" : "gray"}>{on ? t("on") : t("off")}</Badge>
              </div>
              <p className="text-sm text-muted">{c === "webhook" ? t("webhook.on") : on ? t(`${c}.on`) : t(`${c}.off`)}</p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

// ---- Đăng ký nhận tin ----

type Draft = { channel: NotifyChannel; target: string; kinds: SubscriptionKind[]; quietStart: string; quietEnd: string; maxPerDay: string; active: boolean };

function toDraft(s: SubscriptionOut | null, defaultEmail: string): Draft {
  if (!s) return { channel: "email", target: defaultEmail, kinds: [], quietStart: "", quietEnd: "", maxPerDay: "", active: true };
  return {
    channel: s.channel,
    target: s.target,
    kinds: [...s.kinds],
    quietStart: s.quiet_start ?? "",
    quietEnd: s.quiet_end ?? "",
    maxPerDay: s.max_per_day ? String(s.max_per_day) : "",
    active: s.active,
  };
}

function toBody(d: Draft): SubscriptionIn {
  return {
    channel: d.channel,
    target: d.target.trim(),
    kinds: SUB_KINDS.filter((k) => d.kinds.includes(k)),
    quiet_start: d.quietStart || null,
    quiet_end: d.quietEnd || null,
    max_per_day: d.maxPerDay.trim() ? Number(d.maxPerDay) : null,
    active: d.active,
  };
}

type InvalidKey = "email" | "phone" | "webhook" | "quiet" | "quietSame" | "maxPerDay";

function validate(d: Draft): InvalidKey | null {
  const target = d.target.trim();
  if (d.channel === "email" && !EMAIL_RE.test(target)) return "email";
  if (d.channel === "zalo" && normalizeVnPhone(target) === null) return "phone";
  if (d.channel === "webhook" && !validWebhook(target)) return "webhook";
  if (!!d.quietStart !== !!d.quietEnd) return "quiet";
  if (d.quietStart && (!HHMM_RE.test(d.quietStart) || !HHMM_RE.test(d.quietEnd))) return "quiet";
  if (d.quietStart && d.quietStart === d.quietEnd) return "quietSame";
  if (d.maxPerDay.trim()) {
    const n = Number(d.maxPerDay);
    if (!Number.isInteger(n) || n < 1 || n > 50) return "maxPerDay";
  }
  return null;
}

/** Nơi nhận hiển thị: số Zalo dạng 0912 345 678 cho dễ đọc. */
function shownTarget(s: Pick<SubscriptionOut, "channel" | "target">): string {
  if (s.channel !== "zalo") return s.target;
  const d = s.target.replace(/\D/g, "");
  const local = d.startsWith("84") ? `0${d.slice(2)}` : d;
  return local.length === 10 ? `${local.slice(0, 4)} ${local.slice(4, 7)} ${local.slice(7)}` : s.target;
}

export function Subscriptions({ channels, zaloConfigured }: { channels: string[]; zaloConfigured: boolean }) {
  const t = useTranslations("settings.notifications.subscriptions");
  const { user, canWrite } = useSession();
  const subs = useApi("notifications:subscriptions", () => api.notifications.subscriptions.list());
  const [editing, setEditing] = useState<SubscriptionOut | "new" | null>(null);
  const toggle = useMutation(async (s: SubscriptionOut, active: boolean) => {
    await api.notifications.subscriptions.update(s.id, { ...toBody(toDraft(s, "")), active });
    subs.reload();
  });
  const remove = useMutation(async (id: number) => {
    await api.notifications.subscriptions.remove(id);
    if (editing !== null && editing !== "new" && editing.id === id) setEditing(null);
    subs.reload();
  });
  const available = CHANNEL_ORDER.filter((c) => channels.includes(c));
  const list = subs.data ?? [];

  return (
    <Card
      title={t("title")}
      description={canWrite ? t("descriptionAdmin") : t("descriptionViewer")}
      actions={
        editing === null && (
          <Button size="sm" variant="primary" icon={<IconPlus size={15} />} onClick={() => setEditing("new")}>
            {t("add")}
          </Button>
        )
      }
    >
      <ErrorBox error={subs.error ?? toggle.error ?? remove.error} className="mb-3" />
      {editing === "new" && (
        <SubscriptionForm
          initial={null}
          defaultEmail={user?.email ?? ""}
          channels={available}
          zaloConfigured={zaloConfigured}
          onDone={() => {
            setEditing(null);
            subs.reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
      {!subs.data && !subs.error && <Skeleton rows={2} />}
      {subs.data && list.length === 0 && editing !== "new" && (
        <EmptyState icon={<IconBell />} title={t("emptyTitle")} compact>
          {t("emptyBody")}
        </EmptyState>
      )}
      {list.length > 0 && (
        <ul className={cx("divide-y divide-line rounded-lg border border-line", editing === "new" && "mt-4")}>
          {list.map((s) =>
            editing !== null && editing !== "new" && editing.id === s.id ? (
              <li key={s.id} className="p-4">
                <SubscriptionForm
                  initial={s}
                  defaultEmail={user?.email ?? ""}
                  channels={available}
                  zaloConfigured={zaloConfigured}
                  onDone={() => {
                    setEditing(null);
                    subs.reload();
                  }}
                  onCancel={() => setEditing(null)}
                />
              </li>
            ) : (
              <SubscriptionRow
                key={s.id}
                s={s}
                mine={s.user_id !== null && s.user_id === user?.id}
                showOwner={canWrite}
                zaloConfigured={zaloConfigured}
                busy={toggle.busy || remove.busy}
                onToggle={(active) => void toggle.run(s, active)}
                onEdit={() => setEditing(s)}
                onRemove={() => void remove.run(s.id)}
              />
            ),
          )}
        </ul>
      )}
    </Card>
  );
}

function SubscriptionRow({
  s,
  mine,
  showOwner,
  zaloConfigured,
  busy,
  onToggle,
  onEdit,
  onRemove,
}: {
  s: SubscriptionOut;
  mine: boolean;
  showOwner: boolean;
  zaloConfigured: boolean;
  busy: boolean;
  onToggle: (active: boolean) => void;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const t = useTranslations("settings.notifications.subscriptions");
  const target = shownTarget(s);
  const facts: string[] = [s.kinds.length ? s.kinds.map((k) => t(`kind.${k}`)).join(", ") : t("allKinds")];
  if (s.quiet_start && s.quiet_end) facts.push(t("quiet", { start: s.quiet_start, end: s.quiet_end }));
  if (s.max_per_day) facts.push(t("maxPerDay", { count: s.max_per_day }));
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <div className="pt-0.5">
        <Switch checked={s.active} label={t("toggleAria", { target })} busy={busy} onChange={onToggle} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <ChannelChip channel={s.channel} />
          <span className={cx("min-w-0 truncate text-base font-semibold tabular", s.active ? "text-ink" : "text-muted")} title={s.target}>
            {target}
          </span>
          {showOwner && (mine ? <Badge tone="blue">{t("mine")}</Badge> : <span className="text-xs text-muted">{s.user_id ? t("owner", { id: s.user_id }) : t("ownerUnknown")}</span>)}
          {!s.active && <span className="text-xs font-semibold text-muted">{t("paused")}</span>}
        </div>
        <p className={cx("mt-0.5 text-sm", s.active ? "text-body" : "text-faint")}>{facts.join(" · ")}</p>
        {s.channel === "zalo" && !zaloConfigured && (
          <p className="mt-1 flex items-start gap-1 text-xs text-warning-deep">
            <IconAlert size={13} className="mt-px shrink-0" /> {t("zaloNotReady")}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button size="sm" variant="ghost" icon={<IconPencil size={15} />} aria-label={t("editAria", { target })} onClick={onEdit} />
        <Button size="sm" variant="ghost" icon={<IconTrash size={15} />} aria-label={t("removeAria", { target })} disabled={busy} onClick={onRemove} />
      </div>
    </li>
  );
}

function SubscriptionForm({
  initial,
  defaultEmail,
  channels,
  zaloConfigured,
  onDone,
  onCancel,
}: {
  initial: SubscriptionOut | null;
  defaultEmail: string;
  channels: readonly NotifyChannel[];
  zaloConfigured: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("settings.notifications.subscriptions");
  const tf = useTranslations("settings.notifications.subscriptions.form");
  const [d, setD] = useState<Draft>(() => toDraft(initial, defaultEmail));
  const [touched, setTouched] = useState(false);
  const invalid = validate(d);
  const save = useMutation(async () => {
    const body = toBody(d);
    if (initial) await api.notifications.subscriptions.update(initial.id, body);
    else await api.notifications.subscriptions.create(body);
    onDone();
  });
  const set = (patch: Partial<Draft>) => {
    save.clearError();
    setD((x) => ({ ...x, ...patch }));
  };
  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!invalid) void save.run();
  }
  const hint = tf(`hint.${d.channel}`);

  return (
    <form onSubmit={submit} noValidate className="space-y-4 rounded-lg border border-brand/30 bg-brand-softer/40 p-4">
      <div className="text-sm font-bold text-ink">{initial ? tf("titleEdit") : tf("titleNew")}</div>
      <div className="grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)]">
        <Field label={tf("channel")}>
          <Select
            value={d.channel}
            onChange={(e) => {
              const channel = e.target.value as NotifyChannel;
              set({ channel, target: channel === d.channel ? d.target : channel === "email" ? defaultEmail : "" });
            }}
          >
            {channels.map((c) => (
              <option key={c} value={c}>
                {tf(`target.${c}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={tf(`target.${d.channel}`)} hint={hint || undefined}>
          <Input
            type={d.channel === "email" ? "email" : d.channel === "zalo" ? "tel" : "url"}
            inputMode={d.channel === "zalo" ? "tel" : undefined}
            autoComplete="off"
            placeholder={tf(`placeholder.${d.channel}`)}
            value={d.target}
            onChange={(e) => set({ target: e.target.value })}
            aria-invalid={(touched && (invalid === "email" || invalid === "phone" || invalid === "webhook")) || undefined}
          />
        </Field>
      </div>
      {d.channel === "zalo" && !zaloConfigured && (
        <p className="flex items-start gap-1.5 text-sm text-warning-deep">
          <IconAlert size={15} className="mt-px shrink-0" /> {t("zaloNotReady")}
        </p>
      )}
      <fieldset>
        <legend className="text-sm font-semibold text-body">{tf("kinds")}</legend>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {SUB_KINDS.map((k) => {
            const on = d.kinds.includes(k);
            return (
              <label
                key={k}
                className={cx(
                  "inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-semibold transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand",
                  on ? "border-brand bg-brand-soft text-brand-hover" : "border-line-strong bg-surface text-body hover:border-brand-light",
                )}
              >
                <input type="checkbox" className="sr-only" checked={on} onChange={() => set({ kinds: on ? d.kinds.filter((x) => x !== k) : [...d.kinds, k] })} />
                {on && <IconCheck size={13} />}
                {t(`kind.${k}`)}
              </label>
            );
          })}
        </div>
        <p className="mt-1 text-xs text-muted">{tf("kindsHint")}</p>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_160px] sm:items-start">
        <Field label={tf("quietStart")}>
          <Input type="time" step={60} value={d.quietStart} onChange={(e) => set({ quietStart: e.target.value })} aria-invalid={(touched && (invalid === "quiet" || invalid === "quietSame")) || undefined} />
        </Field>
        <Field label={tf("quietEnd")}>
          <Input type="time" step={60} value={d.quietEnd} onChange={(e) => set({ quietEnd: e.target.value })} aria-invalid={(touched && (invalid === "quiet" || invalid === "quietSame")) || undefined} />
        </Field>
        <Field label={tf("maxPerDay")} hint={tf("maxPerDayHint")}>
          <Input type="number" inputMode="numeric" min={1} max={50} value={d.maxPerDay} onChange={(e) => set({ maxPerDay: e.target.value })} aria-invalid={(touched && invalid === "maxPerDay") || undefined} />
        </Field>
      </div>
      <p className="-mt-2 text-xs text-muted">{tf("quietHint")}</p>
      <label className="inline-flex items-center gap-2 text-sm font-semibold text-body">
        <Switch checked={d.active} label={tf("active")} onChange={(active) => set({ active })} />
        {tf("active")}
      </label>
      {touched && invalid && (
        <p role="alert" className="text-sm text-danger">
          {t(`invalid.${invalid}`)}
        </p>
      )}
      <ErrorBox error={save.error} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" variant="primary" busy={save.busy} icon={<IconCheck size={15} />}>
          {tf("save")}
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          {tf("cancel")}
        </Button>
      </div>
    </form>
  );
}

// ---- Hiệu quả tin gửi (đo O4) ----

const ENGAGEMENT_WEEKS = 8;

/** "2026-W41" → ngày thứ Hai của tuần ISO ("2026-10-05"); sai định dạng thì null. */
function isoWeekMonday(week: string): string | null {
  const m = /^(\d{4})-W(\d{1,2})$/.exec(week);
  if (!m) return null;
  const year = Number(m[1]);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const monday1 = Date.UTC(year, 0, 4 - ((jan4.getUTCDay() + 6) % 7));
  return new Date(monday1 + (Number(m[2]) - 1) * 7 * 86_400_000).toISOString().slice(0, 10);
}

export function Engagement() {
  const t = useTranslations("settings.notifications.engagement");
  const { fmtDateShort, fmtInt, fmtMoney, fmtShare } = useFmt();
  const q = useApi(`notifications:engagement:${ENGAGEMENT_WEEKS}`, () => api.notifications.engagement(ENGAGEMENT_WEEKS));
  const rows: EngagementWeekOut[] = [...(q.data?.weeks ?? [])].sort((a, b) => (a.week === b.week ? CHANNEL_ORDER.indexOf(a.channel as NotifyChannel) - CHANNEL_ORDER.indexOf(b.channel as NotifyChannel) : a.week < b.week ? 1 : -1));
  const rate = (n: number, sent: number) => (sent > 0 && n > 0 ? <span className="ml-1 text-xs font-normal text-muted">{t("rate", { pct: fmtShare(n / sent) })}</span> : null);
  return (
    <Card title={t("title")} description={t("description", { weeks: ENGAGEMENT_WEEKS })} info={t("info")} padded={false}>
      <ErrorBox error={q.error} className="m-5" />
      {!q.data && !q.error && <Skeleton rows={3} className="p-5" />}
      {q.data && rows.length === 0 && (
        <div className="p-5">
          <EmptyState icon={<IconTrend />} title={t("emptyTitle")} compact>
            {t("emptyBody")}
          </EmptyState>
        </div>
      )}
      {rows.length > 0 && (
        <Table dense>
          <thead>
            <tr>
              <Th className="pl-5">{t("week")}</Th>
              <Th>{t("channel")}</Th>
              <Th right>{t("sent")}</Th>
              <Th right>{t("clicked")}</Th>
              <Th right>{t("resolved")}</Th>
              <Th right>{t("failed")}</Th>
              <Th right>
                <span title={t("skippedTitle")}>{t("skipped")}</span>
              </Th>
              <Th right className="pr-5">
                {t("cost")}
              </Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const monday = isoWeekMonday(r.week);
              const cost = num(r.cost_vnd) ?? 0;
              return (
                <tr key={`${r.week}:${r.channel}`} className={ROW_CLASS}>
                  <Td className="whitespace-nowrap pl-5">
                    <span className="font-semibold text-ink tabular">{r.week.replace(/^\d{4}-/, "")}</span>
                    {monday && <span className="ml-1.5 text-xs text-muted tabular">{t("weekOf", { date: fmtDateShort(monday) })}</span>}
                  </Td>
                  <Td>
                    <ChannelChip channel={r.channel} />
                  </Td>
                  <Td right className="font-semibold text-ink">
                    {fmtInt(r.sent)}
                  </Td>
                  <Td right className="whitespace-nowrap">
                    {fmtInt(r.clicked)}
                    {rate(r.clicked, r.sent)}
                  </Td>
                  <Td right className="whitespace-nowrap">
                    {fmtInt(r.resolved)}
                    {rate(r.resolved, r.sent)}
                  </Td>
                  <Td right className={r.failed ? "font-semibold text-danger" : "text-muted"}>
                    {fmtInt(r.failed)}
                  </Td>
                  <Td right className="text-muted">
                    {fmtInt(r.skipped)}
                  </Td>
                  <Td right className="pr-5">
                    {cost > 0 ? fmtMoney(cost, "VND") : "—"}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
