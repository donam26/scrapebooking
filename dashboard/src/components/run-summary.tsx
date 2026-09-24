"use client";

import type { ScanRunOut } from "@/lib/api";
import { fmtDateTime, fmtDuration, fmtInt } from "@/lib/format";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/labels";
import { Badge, Stat } from "./ui";

export function RunSummary({ run }: { run: ScanRunOut | null }) {
  if (!run) return <p className="text-sm text-slate-500">Chưa có đợt quét nào hoàn tất.</p>;
  const okRate = run.total_probes > 0 ? Math.round((run.ok_count / run.total_probes) * 100) : null;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
      <Stat
        label="Đợt quét gần nhất"
        value={
          <span className="flex items-center gap-2">
            #{run.id} <Badge tone={RUN_STATUS_TONE[run.status] ?? "gray"}>{RUN_STATUS_LABEL[run.status] ?? run.status}</Badge>
          </span>
        }
      />
      <Stat label="Kết thúc" value={fmtDateTime(run.finished_at)} />
      <Stat label="Thời lượng" value={fmtDuration(run.started_at, run.finished_at)} />
      <Stat label="Probe OK" value={`${fmtInt(run.ok_count)} / ${fmtInt(run.total_probes)}${okRate !== null ? ` (${okRate}%)` : ""}`} />
      <Stat label="Hết phòng" value={fmtInt(run.sold_out_count)} />
      <Stat label="Bị chặn" value={<span className={run.blocked_count > 0 ? "text-rose-700" : undefined}>{fmtInt(run.blocked_count)}</span>} />
      <Stat label="Lỗi" value={<span className={run.error_count > 0 ? "text-amber-700" : undefined}>{fmtInt(run.error_count)}</span>} />
    </div>
  );
}
