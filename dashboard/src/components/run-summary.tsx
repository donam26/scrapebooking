"use client";

import { useTranslations } from "next-intl";
import type { ScanRunOut } from "@/lib/api";
import { useFmt } from "@/lib/format";
import { RUN_STATUS_TONE, useLabel } from "@/lib/labels";
import { Badge, Stat, cx } from "./ui";

/** Số đo kỹ thuật của một lượt quét (chỉ hiện cho operator). */
export function RunSummary({ run }: { run: ScanRunOut | null }) {
  const t = useTranslations("components.runSummary");
  const { fmtDateTime, fmtDuration, fmtInt } = useFmt();
  const label = useLabel();
  if (!run) return <p className="text-base text-muted">{t("empty")}</p>;
  const okRate = run.total_probes > 0 ? Math.round((run.ok_count / run.total_probes) * 100) : null;
  return (
    <div className="flex flex-wrap items-start gap-x-8 gap-y-3">
      <Stat
        label={t("run")}
        value={
          <span className="flex items-center gap-2">
            #{run.id} <Badge tone={RUN_STATUS_TONE[run.status] ?? "gray"}>{label("runStatus", run.status)}</Badge>
          </span>
        }
      />
      <Stat label={t("finished")} value={fmtDateTime(run.finished_at)} />
      <Stat label={t("duration")} value={fmtDuration(run.started_at, run.finished_at)} />
      <Stat label={t("probesOk")} value={`${fmtInt(run.ok_count)} / ${fmtInt(run.total_probes)}${okRate !== null ? ` (${okRate}%)` : ""}`} />
      <Stat label={t("soldOut")} value={fmtInt(run.sold_out_count)} />
      <Stat label={t("blocked")} value={<span className={cx(run.blocked_count > 0 && "text-danger")}>{fmtInt(run.blocked_count)}</span>} />
      <Stat label={t("errors")} value={<span className={cx(run.error_count > 0 && "text-warning-deep")}>{fmtInt(run.error_count)}</span>} />
    </div>
  );
}
