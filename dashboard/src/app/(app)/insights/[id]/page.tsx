"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { fmtDate, fmtDateTime, fmtInt, fmtNum } from "@/lib/format";
import { INSIGHT_STATUS_LABEL, INSIGHT_STATUS_TONE, INSIGHT_TRIGGER_LABEL } from "@/lib/labels";
import { Badge, Card, ErrorBox, PageHeader, Skeleton, Stat } from "@/components/ui";
import { InsightView } from "../insight-view";

export default function InsightDetailPage() {
  const { id } = useParams<{ id: string }>();
  const insightId = Number(id);
  const insight = useApi(Number.isFinite(insightId) ? `insight:${insightId}` : null, () => api.insights.get(insightId));
  const hotels = useApi("watchlist:all", () => api.watchlist.list(true));
  const pending = insight.data?.status === "pending" || insight.data?.status === "batch_pending";
  useInterval(insight.reload, pending ? 5000 : 0);

  const d = insight.data;
  return (
    <>
      <PageHeader
        title={d ? `Bản tin #${d.id}` : "Bản tin"}
        subtitle={
          <Link href="/insights" className="text-sky-700 hover:underline">
            ← Danh sách bản tin
          </Link>
        }
      />
      <ErrorBox error={insight.error} className="mb-4" />
      {!d && !insight.error && <Skeleton rows={8} />}
      {d && (
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap gap-x-6 gap-y-3">
              <Stat label="Trạng thái" value={<Badge tone={INSIGHT_STATUS_TONE[d.status] ?? "gray"}>{INSIGHT_STATUS_LABEL[d.status] ?? d.status}</Badge>} />
              <Stat label="Tạo lúc" value={fmtDateTime(d.generated_at)} />
              <Stat label="Kỳ dữ liệu" value={`${fmtDate(d.period_start)} – ${fmtDate(d.period_end)}`} />
              <Stat label="Nguồn" value={INSIGHT_TRIGGER_LABEL[d.trigger] ?? d.trigger} />
              <Stat label="Đợt quét" value={d.scan_run_id === null ? "—" : `#${d.scan_run_id}`} />
              <Stat label="Mô hình" value={`${d.model} · ${d.prompt_version}`} />
              <Stat label="Token vào/ra" value={`${fmtInt(d.tokens_in)} / ${fmtInt(d.tokens_out)}`} />
              <Stat label="Chi phí" value={`${fmtNum(d.cost_usd, 4)} USD`} />
            </div>
            {pending && <p className="mt-3 text-xs text-slate-500">Đang chờ kết quả, tự làm mới mỗi 5 giây…</p>}
            {d.status === "failed" && d.error && <ErrorBox error={d.error} className="mt-3" />}
          </Card>
          <InsightView insight={d} hotels={hotels.data ?? []} />
        </div>
      )}
    </>
  );
}
