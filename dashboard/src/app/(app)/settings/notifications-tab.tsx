"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { api, type NotificationKind, type NotificationLogOut, type NotificationRuleOut, type RecipientOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useFmt } from "@/lib/format";
import { NOTIFICATION_STATUS_TONE, useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Input, Note, ROW_CLASS, Skeleton, Switch, Table, Td, Th, cx } from "@/components/ui";
import { IconAlert, IconBell, IconCheck, IconMail, IconPlus, IconTrash } from "@/components/icons";
import { ChannelChip, ChannelStatus, Engagement, Subscriptions } from "./notification-subscriptions";

/** Miền giá trị của tham số, khớp `PARAM_BOUNDS` ở backend (notify/kinds.py). */
const BOUNDS: Record<string, [number, number]> = {
  within_days: [1, 90],
  min_sold_out: [1, 50],
  min_pct: [3, 90],
  min_share_pct: [25, 100],
  max_gap_pct: [3, 50],
};

type ParamInput = (key: string, suffix?: string) => ReactNode;

type NotificationsT = ReturnType<typeof useTranslations<"settings.notifications">>;

type Describe = (t: NotificationsT, num: ParamInput, ctx: { insightHour: string | null }) => ReactNode;

/** Câu mô tả của từng loại thông báo; ô số nằm ngay trong câu. */
const RULE_SPECS: Record<NotificationKind, Describe> = {
  daily_insight: (t, _n, { insightHour }) => (insightHour ? t("rules.daily_insight.describeAt", { hour: insightHour }) : t("rules.daily_insight.describe")),
  weekly_report: (t) => t("rules.weekly_report.describe"),
  data_stale: (t) => t("rules.data_stale.describe"),
  market_tight: (t, num) => t.rich("rules.market_tight.describe", { pct: () => num("min_share_pct", "%"), days: () => num("within_days") }),
  competitor_sold_out: (t, num) => t.rich("rules.competitor_sold_out.describe", { days: () => num("within_days"), soldOut: () => num("min_sold_out") }),
  competitor_low_stock: (t, num) => t.rich("rules.competitor_low_stock.describe", { days: () => num("within_days") }),
  competitor_price_drop: (t, num) => t.rich("rules.competitor_price_drop.describe", { pct: () => num("min_pct", "%"), days: () => num("within_days") }),
  competitor_price_rise: (t, num) => t.rich("rules.competitor_price_rise.describe", { pct: () => num("min_pct", "%"), days: () => num("within_days") }),
  competitor_promo: (t, num) => t.rich("rules.competitor_promo.describe", { pct: () => num("min_pct", "%"), days: () => num("within_days") }),
  own_closed: (t, num) => t.rich("rules.own_closed.describe", { days: () => num("within_days") }),
  own_position_drift: (t, num) => t.rich("rules.own_position_drift.describe", { pct: () => num("max_gap_pct", "%"), days: () => num("within_days") }),
};

/** Nhóm và thứ tự hiển thị: việc cần làm với đối thủ/thị trường, khách sạn của bạn, rồi bản tin. */
const RULE_GROUPS: Array<{ key: "competitors" | "own" | "briefs"; kinds: NotificationKind[] }> = [
  { key: "competitors", kinds: ["market_tight", "competitor_sold_out", "competitor_low_stock", "competitor_price_drop", "competitor_price_rise", "competitor_promo"] },
  { key: "own", kinds: ["own_closed", "own_position_drift"] },
  { key: "briefs", kinds: ["daily_insight", "weekly_report", "data_stale"] },
];

/** Tên ô số trong câu (cho trình đọc màn hình): cùng khoá `min_pct` mang nghĩa khác nhau theo loại. */
function paramLabel(kind: NotificationKind, key: string): "param.minDrop" | "param.minRise" | "param.minDepth" | "param.minSoldOut" | "param.minShare" | "param.maxGap" | "param.withinDays" {
  if (key === "min_pct") {
    if (kind === "competitor_price_rise") return "param.minRise";
    if (kind === "competitor_promo") return "param.minDepth";
    return "param.minDrop";
  }
  if (key === "min_sold_out") return "param.minSoldOut";
  if (key === "min_share_pct") return "param.minShare";
  if (key === "max_gap_pct") return "param.maxGap";
  return "param.withinDays";
}

export function NotificationsTab() {
  const { canWrite, isOperator } = useSession();
  const settings = useApi("notifications:settings", () => api.notifications.settings());
  const log = useApi("notifications:log", () => api.notifications.log(30));
  const tenant = useApi("settings", () => api.settings.get());
  const data = settings.data;
  const t = useTranslations("settings.notifications");

  return (
    <div className="space-y-5">
      <ErrorBox error={settings.error} />
      {data && !data.email_configured && (
        <Note tone="warn" icon={<IconAlert size={16} />}>
          {t("emailOff")}{" "}
          {isOperator ? t("emailOffOperator") : t("emailOffTenant")}
        </Note>
      )}
      {!data && !settings.error && <Skeleton rows={6} />}
      {data && (
        <>
          <ChannelStatus data={data} />
          <Subscriptions channels={data.channels} zaloConfigured={data.zalo_configured} />
          <Recipients recipients={data.recipients} canWrite={canWrite} configured={data.email_configured} onChanged={() => { settings.reload(); log.reload(); }} />
          <Card title={t("rulesTitle")} description={t("rulesDescription")}>
            <div className="-my-1 space-y-4">
              {RULE_GROUPS.map((g) => {
                const rules = g.kinds.flatMap((k) => data.rules.filter((x) => x.kind === k));
                if (rules.length === 0) return null;
                return (
                  <section key={g.key}>
                    <h3 className="border-b border-line pb-1.5 text-xs font-semibold uppercase tracking-[0.05em] text-muted">{t(`groups.${g.key}`)}</h3>
                    <ul className="divide-y divide-line">
                      {rules.map((rule) => (
                        <RuleRow key={rule.kind} kind={rule.kind as NotificationKind} rule={rule} canWrite={canWrite} insightHour={tenant.data?.insight_hour ?? null} onSaved={settings.reload} />
                      ))}
                    </ul>
                  </section>
                );
              })}
            </div>
          </Card>
        </>
      )}
      <Engagement />
      <SentLog log={log.data} error={log.error} isOperator={isOperator} onChanged={log.reload} />
    </div>
  );
}

function Recipients({ recipients, canWrite, configured, onChanged }: { recipients: RecipientOut[]; canWrite: boolean; configured: boolean; onChanged: () => void }) {
  const [email, setEmail] = useState("");
  const [result, setResult] = useState<NotificationLogOut | null>(null);
  const t = useTranslations("settings.notifications.recipients");
  const tc = useTranslations("common.actions");
  const add = useMutation(async () => {
    await api.notifications.addRecipient(email.trim());
    setEmail("");
    onChanged();
  });
  const remove = useMutation(async (id: number) => {
    await api.notifications.removeRecipient(id);
    onChanged();
  });
  const test = useMutation(async () => {
    setResult(await api.notifications.test());
    onChanged();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    void add.run();
  }

  return (
    <Card
      title={t("title")}
      description={t("description")}
      actions={
        canWrite && (
          <Button size="sm" icon={<IconMail size={15} />} busy={test.busy} disabled={recipients.length === 0} onClick={() => { setResult(null); void test.run(); }}>
            {t("test")}
          </Button>
        )
      }
    >
      {canWrite && (
        <form onSubmit={submit} className="mb-4 flex flex-wrap items-start gap-2">
          <Input
            type="email"
            required
            aria-label={t("emailAria")}
            placeholder={t("emailPlaceholder")}
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full max-w-sm"
          />
          <Button type="submit" variant="primary" busy={add.busy} icon={<IconPlus size={16} />}>
            {t("add")}
          </Button>
        </form>
      )}
      <ErrorBox error={add.error ?? remove.error ?? test.error} className="mb-3" title={t("errorTitle")} />
      {result && <TestResult row={result} configured={configured} />}
      {recipients.length === 0 ? (
        <EmptyState icon={<IconMail />} title={t("emptyTitle")} compact>
          {t("emptyBody")}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {recipients.map((r) => (
            <li key={r.id} className="flex items-center gap-3 px-4 py-2.5">
              <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-bold text-brand-hover">
                {r.email.slice(0, 1).toUpperCase()}
              </span>
              <span className="min-w-0 flex-1 truncate text-base font-semibold text-ink" title={r.email}>
                {r.email}
              </span>
              {canWrite && (
                <Button size="sm" variant="ghost" icon={<IconTrash size={15} />} aria-label={t("removeAria", { email: r.email })} busy={remove.busy} onClick={() => void remove.run(r.id)}>
                  <span className="max-sm:sr-only">{tc("delete")}</span>
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TestResult({ row, configured }: { row: NotificationLogOut; configured: boolean }) {
  const t = useTranslations("settings.notifications.test");
  const label = useLabel();
  if (row.status === "sent") {
    return (
      <p role="status" className="mb-3 flex items-center gap-1.5 text-sm text-yours-deep">
        <IconCheck size={16} /> {t("sent", { count: row.recipients.length })}
      </p>
    );
  }
  const reason = row.reason ? label("notificationReason", row.reason) : t("notSent");
  return (
    <p role="status" className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-warning-deep">
      <IconAlert size={16} /> {configured ? reason : t("notSentUnconfigured", { reason })}
    </p>
  );
}

function RuleRow({
  kind,
  rule,
  canWrite,
  insightHour,
  onSaved,
}: {
  kind: NotificationKind;
  rule: NotificationRuleOut;
  canWrite: boolean;
  insightHour: string | null;
  onSaved: () => void;
}) {
  const [params, setParams] = useState<Record<string, string>>(() => toDraft(rule.params));
  const [saved, setSaved] = useState(false);
  const t = useTranslations("settings.notifications");
  const tc = useTranslations("common.actions");
  const title = t(`rules.${kind}.title`);
  const dirty = Object.keys(rule.params).some((k) => params[k] !== String(rule.params[k]));
  const firstInvalid = Object.entries(params).find(([k, v]) => !inBounds(k, v));
  const invalid = firstInvalid ? t("invalid", { min: BOUNDS[firstInvalid[0]]?.[0] ?? 0, max: BOUNDS[firstInvalid[0]]?.[1] ?? 0 }) : null;
  const save = useMutation(async (active: boolean, values: Record<string, number>) => {
    await api.notifications.updateRule(rule.kind, { active, params: values });
    setSaved(true);
    onSaved();
  });

  const num: ParamInput = (key, suffix) => (
    <span className="inline-flex items-baseline gap-0.5 whitespace-nowrap">
      <input
        type="number"
        inputMode="numeric"
        aria-label={t("param.aria", { rule: title, param: t(paramLabel(kind, key)) })}
        min={BOUNDS[key]?.[0]}
        max={BOUNDS[key]?.[1]}
        disabled={!canWrite || !rule.active}
        value={params[key] ?? ""}
        onChange={(e) => {
          setSaved(false);
          setParams((p) => ({ ...p, [key]: e.target.value }));
        }}
        className={cx(
          "mx-0.5 h-7 w-14 rounded-md border bg-surface px-1.5 text-center text-sm font-semibold text-ink tabular [appearance:textfield] transition-[border-color,box-shadow] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15 disabled:bg-subtle disabled:text-faint",
          inBounds(key, params[key] ?? "") ? "border-line-strong" : "border-danger ring-3 ring-danger/15",
        )}
      />
      {suffix}
    </span>
  );

  return (
    <li className="flex items-start gap-4 py-3.5">
      <div className="pt-0.5">
        <Switch
          checked={rule.active}
          label={title}
          disabled={!canWrite}
          busy={save.busy}
          onChange={(next) => {
            setSaved(false);
            void save.run(next, rule.params);
          }}
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className={cx("text-md font-bold", rule.active ? "text-ink" : "text-muted")}>{title}</div>
        <p className={cx("mt-0.5 text-base leading-7", rule.active ? "text-body" : "text-faint")}>{RULE_SPECS[kind](t, num, { insightHour })}</p>
        {kind === "own_position_drift" && (
          <p className="mt-1 text-sm text-muted">
            {t.rich("rules.own_position_drift.needsStrategy", {
              link: (c) => (
                <Link href="/settings?tab=strategy" className="font-semibold text-brand hover:underline">
                  {c}
                </Link>
              ),
            })}
          </p>
        )}
        {save.error && <p role="alert" className="mt-1 text-sm text-danger">{save.error}</p>}
        {invalid && <p role="alert" className="mt-1 text-sm text-danger">{invalid}</p>}
      </div>
      {canWrite && (dirty || saved) && (
        <div className="shrink-0 pt-0.5">
          {dirty ? (
            <Button size="sm" variant="primary" disabled={!!invalid} busy={save.busy} onClick={() => void save.run(rule.active, fromDraft(params))}>
              {tc("save")}
            </Button>
          ) : (
            <span role="status" className="inline-flex h-8 items-center gap-1 text-sm text-yours-deep">
              <IconCheck size={15} /> {t("saved")}
            </span>
          )}
        </div>
      )}
    </li>
  );
}

function toDraft(params: Record<string, number>): Record<string, string> {
  return Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)]));
}

function fromDraft(params: Record<string, string>): Record<string, number> {
  return Object.fromEntries(Object.entries(params).map(([k, v]) => [k, Number(v)]));
}

function inBounds(key: string, raw: string): boolean {
  const n = Number(raw);
  const [lo, hi] = BOUNDS[key] ?? [-Infinity, Infinity];
  return raw.trim() !== "" && Number.isInteger(n) && n >= lo && n <= hi;
}

function SentLog({ log, error, isOperator, onChanged }: { log: NotificationLogOut[] | undefined; error: unknown; isOperator: boolean; onChanged: () => void }) {
  const t = useTranslations("settings.notifications.log");
  const tl = useTranslations("labels");
  const label = useLabel();
  const { fmtDayTime } = useFmt();
  const resolve = useMutation(async (id: number) => {
    await api.notifications.resolve(id);
    onChanged();
  });
  return (
    <Card title={t("title")} description={t("description", { count: 30 })} padded={false}>
      <ErrorBox error={error ?? resolve.error} className="m-5" />
      {!log && !error && <Skeleton rows={3} className="p-5" />}
      {log && log.length === 0 && (
        <div className="p-5">
          <EmptyState icon={<IconBell />} title={t("emptyTitle")} compact>
            {t("emptyBody")}
          </EmptyState>
        </div>
      )}
      {log && log.length > 0 && (
        <Table dense>
          <thead>
            <tr>
              <Th className="pl-5">{t("time")}</Th>
              <Th>{t("kind")}</Th>
              <Th>{t("channel")}</Th>
              <Th>{t("content")}</Th>
              <Th right>{t("recipients")}</Th>
              <Th>{t("status")}</Th>
              <Th className="pr-5">{t("resolved")}</Th>
            </tr>
          </thead>
          <tbody>
            {log.map((n) => (
              <tr key={n.id} className={ROW_CLASS}>
                <Td className="whitespace-nowrap pl-5 tabular">{fmtDayTime(n.sent_at ?? n.created_at)}</Td>
                <Td className="whitespace-nowrap">{label("notificationKind", n.kind)}</Td>
                <Td>
                  <ChannelChip channel={n.channel} />
                </Td>
                <Td className="max-w-[380px]">
                  <span className="line-clamp-1 text-ink" title={n.subject}>
                    {n.subject || "—"}
                  </span>
                  {isOperator && n.detail && <span className="mt-0.5 line-clamp-2 text-xs text-danger-deep">{n.detail}</span>}
                </Td>
                <Td right className="tabular">{n.recipients.length || "—"}</Td>
                <Td>
                  <Badge tone={NOTIFICATION_STATUS_TONE[n.status] ?? "gray"} title={n.reason ? label("notificationReason", n.reason) : undefined}>
                    {n.status === "skipped" && n.reason
                      ? tl.has(`notificationReason.${n.reason}` as Parameters<typeof tl>[0])
                        ? label("notificationReason", n.reason)
                        : label("notificationStatus", "skipped")
                      : label("notificationStatus", n.status)}
                  </Badge>
                </Td>
                <Td className="whitespace-nowrap pr-5">
                  {n.resolved_at ? (
                    <Badge tone="green" title={t("resolvedTitle", { time: fmtDayTime(n.resolved_at) })}>
                      {t("resolved")}
                    </Badge>
                  ) : n.status === "sent" && n.kind !== "test" ? (
                    <Button size="sm" variant="quiet" icon={<IconCheck size={14} />} busy={resolve.busy} aria-label={t("resolveAria", { subject: n.subject })} onClick={() => void resolve.run(n.id)}>
                      {t("resolve")}
                    </Button>
                  ) : (
                    <span className="text-faint">—</span>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
