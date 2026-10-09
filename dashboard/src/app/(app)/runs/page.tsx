"use client";

import { useTranslations } from "next-intl";
import { Fragment, useState } from "react";
import { api, type ScanRunOut } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { scanCollectedNothing, useFmt } from "@/lib/format";
import { RUN_STATUS_TONE, useLabel } from "@/lib/labels";
import { Badge, Card, EmptyState, ErrorBox, ROW_CLASS, SkeletonBlock, Table, Td, Th, cx } from "@/components/ui";
import { KpiCard } from "@/components/kpi";
import { PageStrip } from "@/components/page-strip";
import { IconChevronDown, IconChevronRight, IconHistory } from "@/components/icons";
import { RunJobsRow } from "./run-jobs-row";

/** Lịch sử quét Booking.com: 100 lượt gần nhất của tenant, tỷ lệ thành công và lượt bị chặn. */

type TriggerKind = "manual" | "catchup" | "scheduled";

function triggerKind(key: string): TriggerKind {
  if (key.startsWith("manual")) return "manual";
  if (key.startsWith("catchup")) return "catchup";
  return "scheduled";
}

/** Thanh tỷ lệ: xanh thành công, đỏ bị chặn, cam lỗi. */
function ProbeBar({ r }: { r: ScanRunOut }) {
  const total = Math.max(1, r.total_probes);
  const ok = ((r.ok_count + r.sold_out_count) / total) * 100;
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

export default function RunsPage() {
  const t = useTranslations("runs");
  const { fmtDateTime, fmtDuration, fmtInt } = useFmt();
  const label = useLabel();
  const runs = useApi("runs:100", () => api.runs(100));
  const [open, setOpen] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const [now] = useState(() => Date.now());
  useInterval(() => runs.reload(), runs.data?.some((r) => r.status === "running") ? 15_000 : 0);

  const all = runs.data ?? [];
  const day = all.filter((r) => now - new Date(r.started_at ?? r.scheduled_at).getTime() < 24 * 3600 * 1000);
  const probes = day.reduce((s, r) => s + r.total_probes, 0);
  const good = day.reduce((s, r) => s + r.ok_count + r.sold_out_count, 0);
  const blocked = day.reduce((s, r) => s + r.blocked_count, 0);
  const empty = day.filter((r) => scanCollectedNothing(r)).length;

  return (
    <>
      <PageStrip
        title={t("title")}
        meta={<span>{t("meta", { count: all.length })}</span>}
      />
      <ErrorBox error={runs.error} className="mb-4" />
      {!runs.data && !runs.error && <SkeletonBlock className="h-[480px] w-full rounded-[10px]" />}
      {runs.data && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard title={t("kpi.runs24h")} value={fmtInt(day.length)} sub={t("kpi.runs24hSub", { count: probes })} />
            <KpiCard
              title={t("kpi.successRate")}
              info={t("kpi.successRateInfo")}
              value={probes ? `${Math.round((good / probes) * 100)}%` : "—"}
              sub={t("kpi.successRateSub", { count: good })}
              tone={probes && good / probes >= 0.9 ? "good" : "hot"}
            />
            <KpiCard title={t("kpi.blocked")} info={t("kpi.blockedInfo")} value={fmtInt(blocked)} sub={t("kpi.blockedSub")} tone={blocked ? "bad" : "default"} />
            <KpiCard title={t("kpi.empty")} value={fmtInt(empty)} sub={t("kpi.emptySub")} tone={empty ? "bad" : "good"} />
          </div>
          <Card title={t("table.title")} info={t("table.info")} padded={false}>
            {all.length === 0 ? (
              <EmptyState icon={<IconHistory />} title={t("empty.title")} className="m-5">
                {t("empty.body")}
              </EmptyState>
            ) : (
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
                  {all.map((r) => (
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
                      <Td>{t(`trigger.${triggerKind(r.trigger_key)}`)}</Td>
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
            )}
          </Card>
        </div>
      )}
    </>
  );
}
