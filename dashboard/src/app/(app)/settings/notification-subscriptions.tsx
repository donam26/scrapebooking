"use client";

import { useTranslations } from "next-intl";
import { Fragment, useState, type FormEvent, type ReactNode } from "react";
import { api, type EngagementWeekOut, type NotificationLogOut, type NotificationSettingsOut, type NotifyChannel, type SubscriptionIn, type SubscriptionKind, type SubscriptionOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { num, useFmt } from "@/lib/format";
import { useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, ROW_CLASS, Select, Skeleton, Switch, Table, Td, Th, cx } from "@/components/ui";
import { IconAlert, IconBell, IconCheck, IconLink, IconMail, IconPencil, IconPlus, IconTrash, IconTrend } from "@/components/icons";

/**
 * Cài đặt › Cảnh báo › "Ai nhận gì" (UX Phase 3, C2): một bảng duy nhất, mỗi người nhận (email, số
 * Zalo hoặc webhook) một hàng, mỗi loại tin một công tắc. Hàng là một đăng ký nhận tin ở backend
 * (`kinds` rỗng = mọi loại; tắt hết = tạm dừng hàng).
 */

/** Cột của bảng, khớp `SubscriptionIn.kinds` ở backend. */
export const SUB_KINDS: readonly SubscriptionKind[] = ["alerts", "daily_insight", "weekly_report", "data_stale"];
const CHANNEL_ORDER: readonly NotifyChannel[] = ["email", "zalo", "webhook"];
const DEFAULT_QUIET = { start: "22:00", end: "06:00" };

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

/** Đoán kênh từ chữ người dùng gõ: có @ là email, https:// là webhook, còn lại là số Zalo. */
function guessChannel(raw: string): NotifyChannel {
  const v = raw.trim();
  if (v.includes("@")) return "email";
  if (/^https?:\/\//i.test(v)) return "webhook";
  return "zalo";
}

function channelIcon(channel: string, size = 16): ReactNode {
  if (channel === "email") return <IconMail size={size} />;
  if (channel === "webhook") return <IconLink size={size} />;
  return <IconBell size={size} />;
}

/** Chip kênh gửi (email/Zalo/webhook) dùng chung cho bảng người nhận, nhật ký gửi và bảng hiệu quả. */
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

/** Kênh gửi được: email/Zalo khi đơn vị vận hành đã bật, webhook luôn được. */
export function usableChannels(data: NotificationSettingsOut): Record<NotifyChannel, boolean> {
  return { email: data.email_configured, zalo: data.zalo_configured, webhook: true };
}

// ---- Kênh gửi (chỉ operator: trạng thái kỹ thuật) ----

export function ChannelStatus({ data }: { data: NotificationSettingsOut }) {
  const t = useTranslations("settings.notifications.channels");
  const channels = CHANNEL_ORDER.filter((c) => data.channels.includes(c));
  const ready = usableChannels(data);
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

// ---- Bảng "Ai nhận gì" ----

/** Loại tin hàng đang nhận (hàng tạm dừng = không nhận gì). */
function receives(s: SubscriptionOut): SubscriptionKind[] {
  if (!s.active) return [];
  return s.kinds.length ? SUB_KINDS.filter((k) => s.kinds.includes(k)) : [...SUB_KINDS];
}

function body(s: SubscriptionOut, patch: Partial<SubscriptionIn> = {}): SubscriptionIn {
  return {
    channel: s.channel,
    target: s.target,
    kinds: SUB_KINDS.filter((k) => s.kinds.includes(k)),
    quiet_start: s.quiet_start ?? null,
    quiet_end: s.quiet_end ?? null,
    max_per_day: s.max_per_day ?? null,
    active: s.active,
    ...patch,
  };
}

/** Bật/tắt một loại tin của một hàng. Tắt hết thì tạm dừng hàng (kinds rỗng ở backend = mọi loại). */
function toggled(s: SubscriptionOut, kind: SubscriptionKind, on: boolean): SubscriptionIn {
  const now = new Set(receives(s));
  if (on) now.add(kind);
  else now.delete(kind);
  const kinds = SUB_KINDS.filter((k) => now.has(k));
  return kinds.length === 0 ? body(s, { active: false, kinds: [] }) : body(s, { active: true, kinds });
}

/** Nơi nhận hiển thị: số Zalo dạng 0912 345 678 cho dễ đọc. */
function shownTarget(s: Pick<SubscriptionOut, "channel" | "target">): string {
  if (s.channel !== "zalo") return s.target;
  const d = s.target.replace(/\D/g, "");
  const local = d.startsWith("84") ? `0${d.slice(2)}` : d;
  return local.length === 10 ? `${local.slice(0, 4)} ${local.slice(4, 7)} ${local.slice(7)}` : s.target;
}

export function Recipients({ settings, onSent }: { settings: NotificationSettingsOut; onSent: () => void }) {
  const t = useTranslations("settings.notifications.who");
  const { canWrite, isOperator } = useSession();
  const subs = useApi("notifications:subscriptions", () => api.notifications.subscriptions.list());
  const [editing, setEditing] = useState<number | null>(null);
  const [tested, setTested] = useState<{ id: number; row: NotificationLogOut } | null>(null);
  const ready = usableChannels(settings);
  const save = useMutation(async (id: number, next: SubscriptionIn) => {
    await api.notifications.subscriptions.update(id, next);
    subs.reload();
  });
  const remove = useMutation(async (s: SubscriptionOut) => {
    if (!window.confirm(t("removeConfirm", { target: shownTarget(s) }))) return;
    await api.notifications.subscriptions.remove(s.id);
    if (editing === s.id) setEditing(null);
    subs.reload();
  });
  const test = useMutation(async (id: number) => {
    setTested(null);
    setTested({ id, row: await api.notifications.subscriptions.test(id) });
    onSent();
  });
  const list = subs.data ?? [];
  // Kênh khách sạn thêm được: kênh chưa bật bị ẩn với khách sạn (Q6); operator thấy mọi kênh.
  const addable = CHANNEL_ORDER.filter((c) => settings.channels.includes(c) && (isOperator || ready[c]));

  return (
    <Card title={t("title")} description={canWrite ? t("descriptionAdmin") : t("descriptionViewer")} padded={false}>
      <div className="px-5 pt-4">
        <AddRecipient channels={addable} onAdded={subs.reload} />
      </div>
      <ErrorBox error={subs.error ?? save.error ?? remove.error ?? test.error} className="mx-5 mt-3" />
      {!subs.data && !subs.error && <Skeleton rows={2} className="p-5" />}
      {subs.data && list.length === 0 && (
        <div className="p-5">
          <EmptyState icon={<IconBell />} title={t("emptyTitle")} compact>
            {t("emptyBody")}
          </EmptyState>
        </div>
      )}
      {list.length > 0 && (
        // Điện thoại: mỗi người nhận một thẻ (bảng 7 cột quá rộng cho 375px).
        <ul className="mt-4 divide-y divide-line border-t border-line sm:hidden">
          {list.map((s) => {
            const on = receives(s);
            const target = shownTarget(s);
            return (
              <li key={s.id} className="space-y-2.5 px-5 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className={cx("truncate font-semibold tabular", s.active ? "text-ink" : "text-muted")} title={s.target}>
                      {target}
                    </p>
                    <span className="mt-1 flex flex-wrap items-center gap-1.5">
                      <ChannelChip channel={s.channel} />
                      {!ready[s.channel] && <span className="text-xs text-warning-deep">{isOperator ? t("blockedOperator") : t("blocked")}</span>}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button size="sm" variant="ghost" icon={<IconMail size={14} />} aria-label={t("testAria", { target })} onClick={() => void test.run(s.id)} />
                    <Button size="sm" variant="ghost" icon={<IconPencil size={14} />} aria-label={t("editAria", { target })} onClick={() => setEditing(editing === s.id ? null : s.id)} />
                    <Button size="sm" variant="ghost" icon={<IconTrash size={14} />} aria-label={t("removeAria", { target })} disabled={remove.busy} onClick={() => void remove.run(s)} />
                  </div>
                </div>
                <ul className="grid grid-cols-2 gap-x-3 gap-y-2">
                  {SUB_KINDS.map((k) => (
                    <li key={k} className="flex items-center gap-2 text-sm text-body">
                      <Switch checked={on.includes(k)} label={t("toggleAria", { kind: t(`kind.${k}`), target })} busy={save.busy} onChange={(next) => void save.run(s.id, toggled(s, k, next))} />
                      {t(`kind.${k}`)}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted">
                  {t("quiet")}: {s.quiet_start && s.quiet_end ? t("quietRange", { start: s.quiet_start, end: s.quiet_end }) : t("quietNone")}
                </p>
                {tested?.id === s.id && <TestResult row={tested.row} />}
                {editing === s.id && (
                  <EditRow sub={s} busy={save.busy} onCancel={() => setEditing(null)} onSave={async (next) => {
                    await save.run(s.id, next);
                    setEditing(null);
                  }} />
                )}
              </li>
            );
          })}
        </ul>
      )}
      {list.length > 0 && (
        <Table dense className="mt-4 hidden border-t border-line sm:block">
          <thead>
            <tr>
              <Th className="pl-5">{t("person")}</Th>
              {SUB_KINDS.map((k) => (
                <Th key={k} className="text-center">
                  <span className="block whitespace-normal leading-tight">{t(`kind.${k}`)}</span>
                </Th>
              ))}
              <Th>{t("quiet")}</Th>
              <Th className="pr-5">
                <span className="sr-only">{t("actions")}</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => {
              const on = receives(s);
              const target = shownTarget(s);
              const blocked = !ready[s.channel];
              return (
                <Fragment key={s.id}>
                  <tr className={cx(ROW_CLASS, "align-middle")}>
                    <Td className="pl-5">
                      <div className="flex min-w-0 max-w-[260px] flex-col gap-1">
                        <span className={cx("truncate font-semibold tabular", s.active ? "text-ink" : "text-muted")} title={s.target}>
                          {target}
                        </span>
                        <span className="flex flex-wrap items-center gap-1.5">
                          <ChannelChip channel={s.channel} />
                          {!s.active && <span className="text-xs font-semibold text-muted">{t("paused")}</span>}
                          {blocked && <span className="text-xs text-warning-deep">{isOperator ? t("blockedOperator") : t("blocked")}</span>}
                        </span>
                      </div>
                    </Td>
                    {SUB_KINDS.map((k) => (
                      <Td key={k} className="text-center">
                        <span className="inline-flex">
                          <Switch checked={on.includes(k)} label={t("toggleAria", { kind: t(`kind.${k}`), target })} busy={save.busy} onChange={(next) => void save.run(s.id, toggled(s, k, next))} />
                        </span>
                      </Td>
                    ))}
                    <Td className="whitespace-nowrap">
                      <button type="button" onClick={() => setEditing(editing === s.id ? null : s.id)} className="rounded-sm text-sm text-body underline decoration-dotted underline-offset-2 hover:text-brand" aria-expanded={editing === s.id} aria-label={t("editAria", { target })}>
                        {s.quiet_start && s.quiet_end ? t("quietRange", { start: s.quiet_start, end: s.quiet_end }) : t("quietNone")}
                      </button>
                    </Td>
                    <Td className="whitespace-nowrap pr-5">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="sm" variant="quiet" icon={<IconMail size={14} />} busy={test.busy && tested === null} onClick={() => void test.run(s.id)} aria-label={t("testAria", { target })}>
                          <span className="max-md:sr-only">{t("test")}</span>
                        </Button>
                        <Button size="sm" variant="ghost" icon={<IconPencil size={14} />} aria-label={t("editAria", { target })} onClick={() => setEditing(editing === s.id ? null : s.id)} />
                        <Button size="sm" variant="ghost" icon={<IconTrash size={14} />} aria-label={t("removeAria", { target })} disabled={remove.busy} onClick={() => void remove.run(s)} />
                      </div>
                    </Td>
                  </tr>
                  {tested?.id === s.id && (
                    <tr>
                      <td colSpan={SUB_KINDS.length + 3} className="px-5 pb-2">
                        <TestResult row={tested.row} />
                      </td>
                    </tr>
                  )}
                  {editing === s.id && (
                    <tr>
                      <td colSpan={SUB_KINDS.length + 3} className="border-b border-line bg-subtle/60 px-5 py-3">
                        <EditRow sub={s} busy={save.busy} onCancel={() => setEditing(null)} onSave={async (next) => {
                          await save.run(s.id, next);
                          setEditing(null);
                        }} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </Table>
      )}
      <p className="px-5 py-3 text-xs text-muted">{t("legend")}</p>
    </Card>
  );
}

function TestResult({ row }: { row: NotificationLogOut }) {
  const t = useTranslations("settings.notifications.who");
  const label = useLabel();
  if (row.status === "sent") {
    return (
      <p role="status" className="flex items-center gap-1.5 text-sm text-yours-deep">
        <IconCheck size={15} /> {t("testSent")}
      </p>
    );
  }
  return (
    <p role="status" className="flex items-center gap-1.5 text-sm font-semibold text-warning-deep">
      <IconAlert size={15} /> {row.reason ? label("notificationReason", row.reason) : t("testNotSent")}
    </p>
  );
}

type Invalid = "email" | "phone" | "webhook" | "channel" | "quiet" | "quietSame" | "maxPerDay";

function targetProblem(channel: NotifyChannel, raw: string): Invalid | null {
  const v = raw.trim();
  if (channel === "email" && !EMAIL_RE.test(v)) return "email";
  if (channel === "zalo" && normalizeVnPhone(v) === null) return "phone";
  if (channel === "webhook" && !validWebhook(v)) return "webhook";
  return null;
}

/** "Thêm người nhận": gõ email, số Zalo hoặc URL webhook; kênh tự đoán, đổi được khi có nhiều kênh. */
function AddRecipient({ channels, onAdded }: { channels: readonly NotifyChannel[]; onAdded: () => void }) {
  const t = useTranslations("settings.notifications.who");
  const tf = useTranslations("settings.notifications.who.form");
  const [target, setTarget] = useState("");
  const [picked, setPicked] = useState<NotifyChannel | null>(null);
  const [touched, setTouched] = useState(false);
  const guessed = guessChannel(target);
  const channel: NotifyChannel = picked ?? (channels.includes(guessed) ? guessed : (channels[0] ?? "email"));
  const problem: Invalid | null = channels.length === 0 ? null : !channels.includes(channel) ? "channel" : targetProblem(channel, target);
  const add = useMutation(async () => {
    await api.notifications.subscriptions.create({
      channel,
      target: target.trim(),
      kinds: [...SUB_KINDS],
      quiet_start: DEFAULT_QUIET.start,
      quiet_end: DEFAULT_QUIET.end,
      max_per_day: null,
      active: true,
    });
    setTarget("");
    setPicked(null);
    setTouched(false);
    onAdded();
  });
  if (channels.length === 0) return null;
  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!problem) void add.run();
  }
  return (
    <form onSubmit={submit} noValidate className="space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={tf(`target.${channels.length === 1 ? channels[0] : "any"}`)} className="min-w-0 flex-1 basis-64">
          <Input
            type="text"
            inputMode={channel === "zalo" ? "tel" : channel === "email" ? "email" : "url"}
            autoComplete="off"
            placeholder={tf(`placeholder.${channels.length === 1 ? channels[0] : "any"}`)}
            value={target}
            onChange={(e) => {
              setTarget(e.target.value);
              add.clearError();
            }}
            aria-invalid={(touched && !!problem) || undefined}
          />
        </Field>
        {channels.length > 1 && (
          <Field label={tf("channel")} className="w-36">
            <Select value={channel} onChange={(e) => setPicked(e.target.value as NotifyChannel)}>
              {channels.map((c) => (
                <option key={c} value={c}>
                  {tf(`channelName.${c}`)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Button type="submit" variant="primary" busy={add.busy} icon={<IconPlus size={15} />}>
          {t("add")}
        </Button>
      </div>
      {touched && problem ? (
        <p role="alert" className="text-sm text-danger">
          {tf(`invalid.${problem}`)}
        </p>
      ) : (
        <p className="text-xs text-muted">{tf("hint", { start: DEFAULT_QUIET.start, end: DEFAULT_QUIET.end })}</p>
      )}
      <ErrorBox error={add.error} />
    </form>
  );
}

/** Sửa nơi nhận, giờ im lặng và trần tin mỗi ngày của một hàng. */
function EditRow({ sub, busy, onSave, onCancel }: { sub: SubscriptionOut; busy: boolean; onSave: (b: SubscriptionIn) => void; onCancel: () => void }) {
  const tf = useTranslations("settings.notifications.who.form");
  const [target, setTarget] = useState(shownTarget(sub));
  const [quietStart, setQuietStart] = useState(sub.quiet_start ?? "");
  const [quietEnd, setQuietEnd] = useState(sub.quiet_end ?? "");
  const [maxPerDay, setMaxPerDay] = useState(sub.max_per_day ? String(sub.max_per_day) : "");
  const [touched, setTouched] = useState(false);
  let problem: Invalid | null = targetProblem(sub.channel, target);
  if (!problem && !!quietStart !== !!quietEnd) problem = "quiet";
  if (!problem && quietStart && (!HHMM_RE.test(quietStart) || !HHMM_RE.test(quietEnd))) problem = "quiet";
  if (!problem && quietStart && quietStart === quietEnd) problem = "quietSame";
  if (!problem && maxPerDay.trim()) {
    const n = Number(maxPerDay);
    if (!Number.isInteger(n) || n < 1 || n > 50) problem = "maxPerDay";
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (problem) return;
    onSave(body(sub, { target: target.trim(), quiet_start: quietStart || null, quiet_end: quietEnd || null, max_per_day: maxPerDay.trim() ? Number(maxPerDay) : null }));
  }
  return (
    <form onSubmit={submit} noValidate className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] sm:items-end">
        <Field label={tf(`target.${sub.channel}`)}>
          <Input type="text" autoComplete="off" value={target} onChange={(e) => setTarget(e.target.value)} aria-invalid={(touched && (problem === "email" || problem === "phone" || problem === "webhook")) || undefined} />
        </Field>
        <Field label={tf("quietStart")}>
          <Input type="time" step={60} value={quietStart} onChange={(e) => setQuietStart(e.target.value)} />
        </Field>
        <Field label={tf("quietEnd")}>
          <Input type="time" step={60} value={quietEnd} onChange={(e) => setQuietEnd(e.target.value)} />
        </Field>
        <Field label={tf("maxPerDay")}>
          <Input type="number" inputMode="numeric" min={1} max={50} placeholder={tf("maxPerDayNone")} value={maxPerDay} onChange={(e) => setMaxPerDay(e.target.value)} />
        </Field>
      </div>
      <p className="text-xs text-muted">{tf("quietHint")}</p>
      {touched && problem && (
        <p role="alert" className="text-sm text-danger">
          {tf(`invalid.${problem}`)}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" variant="primary" busy={busy} icon={<IconCheck size={14} />}>
          {tf("save")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          {tf("cancel")}
        </Button>
      </div>
    </form>
  );
}

// ---- Hiệu quả tin gửi (đo O4, chỉ operator) ----

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
