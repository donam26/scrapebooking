"use client";

import { useTranslations } from "next-intl";
import { Fragment, useState } from "react";
import { api, type ScanRunOut } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { scanCollectedNothing, useFmt } from "@/lib/format";
import { dataFreshness, isMarketRun, runCollected, runFinished, successPct, type DataFreshness } from "@/lib/freshness";
import { RUN_STATUS_TONE, useLabel } from "@/lib/labels";
import { Badge, Card, EmptyState, ErrorBox, ROW_CLASS, SkeletonBlock, Table, Td, Th, cx } from "@/components/ui";
import { KpiCard } from "@/components/kpi";
import { PageStrip } from "@/components/page-strip";
import { IconChevronDown, IconChevronRight, IconHistory } from "@/components/icons";
import { RunJobsRow } from "./run-jobs-row";

/**
 * Lịch sử quét Booking.com (Q7, D4). Mọi vai trò: một câu trạng thái từ `/data-status` (xanh khi ổn,
 * đỏ khi dữ liệu cũ) và dải 7 ngày. Tenant: bảng gọn (thời gian, loại, kết quả bằng lời). Operator
 * giữ KPI 24 giờ, mã lượt, số trang đọc / bị chặn / lỗi và chi tiết từng khách sạn.
 */

const PAGE = 30;
const DAY_MS = 24 * 3600 * 1000;

type TriggerKind = "manual" | "catchup" | "scheduled" | "market";

function triggerKind(r: Pick<ScanRunOut, "trigger_key">): TriggerKind {
  if (isMarketRun(r)) return "market";
  if (r.trigger_key.startsWith("manual")) return "manual";
  if (r.trigger_key.startsWith("catchup")) return "catchup";
  return "scheduled";
}

/** Ngày địa phương dạng "2026-10-24" (không qua UTC, tránh lùi một ngày ở múi giờ dương). */
function localIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

type DayState = "ok" | "empty" | "none";

/** 7 ngày gần nhất (cũ → mới): có lượt thu được số / có lượt nhưng rỗng / không có lượt (như ngăn Tình trạng dữ liệu). */
function lastSevenDays(runs: ScanRunOut[], now: Date): Array<{ day: Date; state: DayState }> {
  const out: Array<{ day: Date; state: DayState }> = [];
  for (let i = 6; i >= 0; i--) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    const next = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1);
    const inDay = runs.filter((r) => {
      if (isMarketRun(r) || !runFinished(r) || !r.finished_at) return false;
      const at = new Date(r.finished_at);
      return at >= day && at < next;
    });
    out.push({ day, state: inDay.some(runCollected) ? "ok" : inDay.length ? "empty" : "none" });
  }
  return out;
}

const STATUS_TONE: Record<DataFreshness["tone"], string> = {
  ok: "border-l-yours bg-yours-soft text-yours-deep",
  warn: "border-l-[#e0a100] bg-warning-soft text-warning-deep",
  bad: "border-l-danger bg-danger-soft text-danger-deep",
};

/** Câu trạng thái (một câu, màu theo độ mới) và dải 7 ngày. */
function StatusPanel({ f, runs, pct }: { f: DataFreshness; runs: ScanRunOut[]; pct: number | null }) {
  const t = useTranslations("runs.status");
  const { fmtAgo, fmtWhen, fmtWeekday, fmtDateShort } = useFmt();
  const [now] = useState(() => new Date());
  // Có lượt kết thúc sau mốc dữ liệu cuối mà không đọc được gì: "các lượt quét không đọc được", không phải "không có lượt quét".
  const emptySince = f.latest !== null && f.updatedAt !== null && (f.latest.finished_at ?? "") > f.updatedAt && !runCollected(f.latest);
  const sentence = !f.updatedAt
    ? t("never")
    : f.stale
      ? t(emptySince ? "staleEmpty" : "stale", { when: fmtWhen(f.updatedAt), ago: fmtAgo(f.updatedAt) })
      : f.latestEmpty
        ? t("latestEmpty", { when: fmtWhen(f.updatedAt) })
        : f.overdue
          ? t("overdue", { ago: fmtAgo(f.updatedAt) })
          : t("ok", { when: fmtWhen(f.updatedAt), pct: pct === null ? "none" : String(pct) });
  return (
    <section className="rounded-[10px] border border-line bg-surface p-4 shadow-card sm:p-5">
      <p role="status" className={cx("rounded-lg border-l-[3px] px-4 py-3 text-base font-semibold leading-relaxed", STATUS_TONE[f.tone])}>
        {sentence}
      </p>
      <div className="mt-4">
        <div className="text-xs font-semibold text-muted">{t("last7Days")}</div>
        <ol className="mt-1.5 grid grid-cols-7 gap-1.5">
          {lastSevenDays(runs, now).map(({ day, state }) => {
            const iso = localIso(day);
            return (
              <li key={iso} className="min-w-0 text-center" title={t(`day.${state}`)}>
                <span className={cx("block h-3 rounded-sm", state === "ok" ? "bg-yours" : state === "empty" ? "bg-danger" : "bg-line-strong")} />
                <span className="mt-1 block truncate text-[11px] text-muted tabular">
                  {fmtWeekday(iso)} {fmtDateShort(iso)}
                </span>
              </li>
            );
          })}
        </ol>
        <p className="mt-1.5 text-xs text-muted">{t("legend")}</p>
      </div>
    </section>
  );
}

/** Thanh tỷ lệ: xanh thành công, đỏ bị chặn, cam lỗi. */
function ProbeBar({ r }: { r: ScanRunOut }) {
  const total = Math.max(1, r.total_probes);
  // Thành công = mọi đêm đọc được (còn, hết, hạn chế), tức là trừ bị chặn và lỗi.
  const ok = ((r.total_probes - r.blocked_count - r.error_count) / total) * 100;
  const blocked = (r.blocked_count / total) * 100;
  const err = (r.error_count / total) * 100;
  return (
    <div className="flex h-1.5 w-28 overflow-hidden rounded-full bg-sunken" aria-hidden>
      <span className="bg-yours" style={{ width: `${ok}%` }} />
      <span className="bg-danger" style={{ width: `${blocked}%` }} />
      <span className="bg-hot" style={{ width: `${err}%` }} />
    </div>
  );
}

/** Kết quả một lượt bằng lời cho tenant: có số cho N khách sạn / một phần / không đọc được. */
function RunResult({ r }: { r: ScanRunOut }) {
  const t = useTranslations("runs.result");
  if (r.status === "running") return <span className="text-brand">{t("running")}</span>;
  if (!runFinished(r)) return <span className="text-muted">{t("queued")}</span>;
  if (!runCollected(r)) return <span className="font-semibold text-danger">{t("none")}</span>;
  // Không trang nào bị chặn hay lỗi: mọi khách sạn của lượt đều có số.
  if (r.blocked_count === 0 && r.error_count === 0) return <span className="font-semibold text-yours-deep">{t("full", { count: r.total_jobs })}</span>;
  return <span className="font-semibold text-warning-deep">{t("partial")}</span>;
}

function TenantTable({ runs }: { runs: ScanRunOut[] }) {
  const t = useTranslations("runs");
  const { fmtDateTime } = useFmt();
  return (
    <Table dense>
      <thead>
        <tr>
          <Th className="pl-5">{t("table.time")}</Th>
          <Th>{t("table.kind")}</Th>
          <Th className="pr-5">{t("table.result")}</Th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id} className={ROW_CLASS}>
            <Td className="whitespace-nowrap pl-5 tabular">{fmtDateTime(r.started_at ?? r.scheduled_at)}</Td>
            <Td>{t(`trigger.${triggerKind(r)}`)}</Td>
            <Td className="pr-5">
              <RunResult r={r} />
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function OperatorTable({ runs }: { runs: ScanRunOut[] }) {
  const t = useTranslations("runs");
  const { fmtDateTime, fmtDuration, fmtInt } = useFmt();
  const label = useLabel();
  const [open, setOpen] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <Table dense className="mt-3">
      <thead>
        <tr>
          <Th className="pl-5">{t("table.run")}</Th>
          <Th>{t("table.trigger")}</Th>
          <Th>{t("table.started")}</Th>
          <Th>{t("table.duration")}</Th>
          <Th>{t("table.status")}</Th>
          <Th right>{t("table.probes")}</Th>
          <Th right>{t("table.withData")}</Th>
          <Th right>{t("table.soldOut")}</Th>
          <Th right>{t("table.blocked")}</Th>
          <Th right>{t("table.errors")}</Th>
          <Th className="pr-5">{t("table.ratio")}</Th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <Fragment key={r.id}>
            <tr className={cx(ROW_CLASS, "cursor-pointer")} onClick={() => toggle(r.id)}>
              <Td className="pl-5 font-semibold text-ink tabular">
                <button
                  type="button"
                  aria-expanded={open.has(r.id)}
                  aria-label={t("table.expand", { id: r.id })}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(r.id);
                  }}
                  className="inline-flex items-center gap-1 rounded hover:text-brand"
                >
                  {open.has(r.id) ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}#{r.id}
                </button>
              </Td>
              <Td>{t(`trigger.${triggerKind(r)}`)}</Td>
              <Td className="whitespace-nowrap tabular">{fmtDateTime(r.started_at ?? r.scheduled_at)}</Td>
              <Td className="tabular">{r.status === "running" ? "…" : fmtDuration(r.started_at, r.finished_at)}</Td>
              <Td>
                <Badge tone={scanCollectedNothing(r) && r.status !== "failed" ? "red" : (RUN_STATUS_TONE[r.status] ?? "gray")}>
                  {scanCollectedNothing(r) && r.status !== "failed" ? t("table.noData") : label("runStatus", r.status)}
                </Badge>
              </Td>
              <Td right>{fmtInt(r.total_probes)}</Td>
              <Td right className="font-semibold text-yours-deep">
                {fmtInt(r.ok_count)}
              </Td>
              <Td right>{fmtInt(r.sold_out_count)}</Td>
              <Td right className={cx(r.blocked_count > 0 && "font-semibold text-danger")}>
                {fmtInt(r.blocked_count)}
              </Td>
              <Td right className={cx(r.error_count > 0 && "font-semibold text-hot")}>
                {fmtInt(r.error_count)}
              </Td>
              <Td className="pr-5">
                <ProbeBar r={r} />
              </Td>
            </tr>
            {open.has(r.id) && <RunJobsRow runId={r.id} colSpan={11} />}
          </Fragment>
        ))}
      </tbody>
    </Table>
  );
}

/** KPI 24 giờ (chỉ operator). 0 lượt trong 24 giờ không bao giờ tô xanh. */
function OperatorKpis({ runs, now }: { runs: ScanRunOut[]; now: number }) {
  const t = useTranslations("runs.kpi");
  const { fmtInt } = useFmt();
  const day = runs.filter((r) => now - new Date(r.started_at ?? r.scheduled_at).getTime() < DAY_MS);
  const probes = day.reduce((s, r) => s + r.total_probes, 0);
  const good = day.reduce((s, r) => s + r.total_probes - r.blocked_count - r.error_count, 0);
  const blocked = day.reduce((s, r) => s + r.blocked_count, 0);
  const empty = day.filter((r) => scanCollectedNothing(r)).length;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard title={t("runs24h")} value={fmtInt(day.length)} sub={t("runs24hSub", { count: probes })} tone={day.length ? "default" : "bad"} />
      <KpiCard
        title={t("successRate")}
        info={t("successRateInfo")}
        value={probes ? `${Math.round((good / probes) * 100)}%` : "—"}
        sub={t("successRateSub", { count: good })}
        tone={probes ? (good / probes >= 0.9 ? "good" : "hot") : "default"}
      />
      <KpiCard title={t("blocked")} info={t("blockedInfo")} value={fmtInt(blocked)} sub={t("blockedSub")} tone={blocked ? "bad" : "default"} />
      <KpiCard title={t("empty")} value={fmtInt(empty)} sub={t("emptySub")} tone={empty ? "bad" : day.length ? "good" : "default"} />
    </div>
  );
}

export default function RunsPage() {
  const t = useTranslations("runs");
  const { isOperator } = useSession();
  const runs = useApi("runs:100", () => api.runs(100));
  const status = useApi("freshness:status", () => api.dataStatus());
  const settings = useApi("settings", () => api.settings.get());
  const [limit, setLimit] = useState(PAGE);
  const [now] = useState(() => Date.now());
  useInterval(() => runs.reload(), runs.data?.some((r) => r.status === "running") ? 15_000 : 0);

  const all = runs.data ?? [];
  const shown = all.slice(0, limit);
  const f = dataFreshness(status.data, runs.data, { scanTimes: settings.data?.scan_times });
  const pct = status.data ? successPct(status.data) : null;
  const statusDone = status.data !== undefined || status.error !== undefined;

  return (
    <>
      <PageStrip title={t("title")} meta={<span>{t("meta", { count: all.length })}</span>} />
      <ErrorBox error={runs.error} className="mb-4" />
      {(!runs.data || !statusDone) && !runs.error && <SkeletonBlock className="h-[480px] w-full rounded-[10px]" />}
      {runs.data && statusDone && (
        <div className="space-y-4">
          <StatusPanel f={f} runs={all} pct={pct} />
          {isOperator && <OperatorKpis runs={all} now={now} />}
          <Card title={t("table.title")} info={isOperator ? t("table.info") : t("table.tenantInfo")} padded={false}>
            {all.length === 0 ? (
              <EmptyState icon={<IconHistory />} title={t("empty.title")} className="m-5">
                {t("empty.body")}
              </EmptyState>
            ) : (
              <>
                {isOperator ? <OperatorTable runs={shown} /> : <TenantTable runs={shown} />}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-sm text-muted">
                  <span className="tabular">{t("table.shown", { shown: shown.length, total: all.length })}</span>
                  {all.length > limit && (
                    <button type="button" onClick={() => setLimit((n) => n + PAGE)} className="font-semibold text-brand hover:underline">
                      {t("table.showMore", { count: Math.min(PAGE, all.length - limit) })}
                    </button>
                  )}
                </div>
              </>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
