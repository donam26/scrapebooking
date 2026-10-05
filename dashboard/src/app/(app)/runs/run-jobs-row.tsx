"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useFmt } from "@/lib/format";
import { Badge, ErrorBox, cx } from "@/components/ui";
import type { Tone } from "@/lib/labels";

/** Trạng thái job từng khách sạn trong một lượt quét. */
type JobStatus = "queued" | "running" | "done" | "failed";
const JOB_STATUS_TONE: Record<JobStatus, Tone> = {
  queued: "gray",
  running: "blue",
  done: "green",
  failed: "red",
};

function isJobStatus(s: string): s is JobStatus {
  return s in JOB_STATUS_TONE;
}

/** Dòng mở rộng dưới một lượt quét: từng khách sạn của tenant, như "job từng khách sạn" của mẫu. */
export function RunJobsRow({ runId, colSpan }: { runId: number; colSpan: number }) {
  const { isOperator } = useSession();
  const t = useTranslations("runs.jobs");
  const { fmtDayTime, fmtDuration, fmtInt } = useFmt();
  const jobs = useApi(`run-jobs:${runId}`, () => api.runJobs(runId));
  return (
    <tr className="bg-subtle">
      <td colSpan={colSpan} className="px-5 py-3">
        <ErrorBox error={jobs.error} />
        {!jobs.data && !jobs.error && <div className="sb-skeleton h-16 rounded-lg" />}
        {jobs.data && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="py-1.5 pr-3 font-medium">{t("hotel")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("status")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("started")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("duration")}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t("probes")}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t("withData")}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t("blocked")}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t("errors")}</th>
                {isOperator && <th className="py-1.5 font-medium">{t("errorDetail")}</th>}
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((j) => {
                const st = isJobStatus(j.status)
                  ? { label: t(`jobStatus.${j.status}`), tone: JOB_STATUS_TONE[j.status] }
                  : { label: j.status, tone: "gray" as Tone };
                return (
                  <tr key={j.hotel_id} className="border-t border-line">
                    <td className="py-1.5 pr-3">
                      <Link href={`/hotels/${j.hotel_id}`} className="font-medium text-ink hover:text-brand hover:underline">
                        {j.hotel_name ?? t("hotelFallback", { id: j.hotel_id })}
                      </Link>
                    </td>
                    <td className="py-1.5 pr-3">
                      <Badge tone={st.tone}>{st.label}</Badge>
                    </td>
                    <td className="py-1.5 pr-3 tabular">{j.started_at ? fmtDayTime(j.started_at) : "—"}</td>
                    <td className="py-1.5 pr-3 tabular">{fmtDuration(j.started_at, j.finished_at)}</td>
                    <td className="py-1.5 pr-3 text-right tabular">{fmtInt(j.total_probes)}</td>
                    <td className="py-1.5 pr-3 text-right font-semibold text-yours-deep tabular">{fmtInt(j.ok_count + j.sold_out_count)}</td>
                    <td className={cx("py-1.5 pr-3 text-right tabular", j.blocked_count > 0 && "font-semibold text-danger")}>{fmtInt(j.blocked_count)}</td>
                    <td className={cx("py-1.5 pr-3 text-right tabular", j.error_count > 0 && "font-semibold text-hot")}>{fmtInt(j.error_count)}</td>
                    {isOperator && (
                      <td className="max-w-[280px] truncate py-1.5 font-mono text-xs text-muted" title={j.error ?? undefined}>
                        {j.error ?? ""}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </td>
    </tr>
  );
}
