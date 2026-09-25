"use client";

import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDateTime, fmtInt, fmtNum, fmtWhen } from "@/lib/format";
import { INSIGHT_STATUS_LABEL, INSIGHT_STATUS_TONE, INSIGHT_TRIGGER_LABEL } from "@/lib/labels";
import { Badge, ErrorBox, Note, PageHeader, SkeletonBlock, Spinner, cx } from "@/components/ui";
import { InsightView, parseDropped, parseInsightOutput, periodText } from "../insight-view";

export default function InsightDetailPage() {
  const { id } = useParams<{ id: string }>();
  const insightId = Number(id);
  const { isOperator } = useSession();
  const insight = useApi(Number.isFinite(insightId) ? `insight:${insightId}` : null, () => api.insights.get(insightId));
  const hotels = useApi("watchlist:all", () => api.watchlist.list(true));
  // Sự kiện làm bằng chứng: lấy các sự kiện quanh thời điểm tạo bản tin để hiện tên, loại, đêm.
  const hasEvt = JSON.stringify(insight.data?.output_json ?? {}).includes('"evt:');
  const since = insight.data ? new Date(new Date(insight.data.generated_at).getTime() - 10 * 86_400_000).toISOString() : null;
  const evs = useApi(hasEvt && since ? `insight-events:${insightId}` : null, () => api.events({ observed_since: since, limit: 2000 }));
  const eventOf = (eid: number) => evs.data?.find((e) => e.id === eid);
  const pending = insight.data?.status === "pending" || insight.data?.status === "batch_pending";
  useInterval(insight.reload, pending ? 5000 : 0);

  const d = insight.data;
  const out = d ? parseInsightOutput(d.output_json) : null;
  const dropped = d ? parseDropped(d.dropped_highlights) : [];
  const toc = out
    ? [
        { id: "tom-tat", label: "Tóm tắt", n: null as number | null },
        { id: "noi-bat", label: "Điểm nổi bật", n: out.highlights.length },
        { id: "nhu-cau", label: "Tín hiệu nhu cầu", n: out.demand_signals.length },
        { id: "co-hoi-gia", label: "Cơ hội giá", n: out.pricing_opportunities.length },
        { id: "rui-ro", label: "Rủi ro", n: out.risks.length },
        ...(out.data_quality_note ? [{ id: "du-lieu", label: "Giới hạn của dữ liệu", n: null }] : []),
        ...(dropped.length ? [{ id: "bi-loai", label: "Nhận định bị loại", n: dropped.length }] : []),
      ]
    : [];

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/insights", label: "Bản tin AI" }, { label: d ? `Bản tin ${fmtWhen(d.generated_at)}` : "Bản tin" }]}
        title={d ? `Bản tin ${fmtWhen(d.generated_at)}` : "Bản tin"}
        subtitle={
          d && (
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="tabular">Dữ liệu đêm {periodText(d.period_start, d.period_end)}</span>
              <span>{INSIGHT_TRIGGER_LABEL[d.trigger] ?? d.trigger}</span>
              {d.status !== "completed" && <Badge tone={INSIGHT_STATUS_TONE[d.status] ?? "gray"}>{INSIGHT_STATUS_LABEL[d.status] ?? d.status}</Badge>}
            </span>
          )
        }
      />
      <ErrorBox error={insight.error} className="mb-4" />
      {!d && !insight.error && (
        <div className="max-w-3xl space-y-3" aria-busy>
          <SkeletonBlock className="h-5 w-full" />
          <SkeletonBlock className="h-5 w-11/12" />
          <SkeletonBlock className="h-5 w-4/5" />
          <SkeletonBlock className="mt-6 h-40 w-full rounded-xl" />
        </div>
      )}
      {d && (
        <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_260px]">
          <div className="min-w-0 max-w-[880px]">
            {pending && (
              <Note tone="info" icon={<Spinner className="text-brand" />} className="mb-5">
                Đang chờ kết quả từ mô hình, trang tự làm mới mỗi 5 giây.
              </Note>
            )}
            {d.status === "failed" && d.error && <ErrorBox error={d.error} className="mb-5" title="Tạo bản tin thất bại" />}
            <InsightView insight={d} hotels={hotels.data ?? []} eventOf={eventOf} />
          </div>

          <aside className="space-y-4 xl:sticky xl:top-8">
            {toc.length > 0 && (
              <nav aria-label="Trong bản tin này" className="rounded-xl border border-line bg-surface p-2 shadow-card">
                <div className="px-3 pb-1 pt-2 text-xs font-semibold text-muted">Trong bản tin này</div>
                <ul>
                  {toc.map((t) => (
                    <li key={t.id}>
                      <a href={`#${t.id}`} className="flex items-center justify-between rounded-lg px-3 py-1.5 text-base text-body hover:bg-subtle hover:text-ink">
                        {t.label}
                        {t.n !== null && <span className={cx("text-sm tabular", t.n === 0 ? "text-faint" : "font-semibold text-muted")}>{t.n}</span>}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            )}
            <dl className="space-y-2.5 rounded-xl border border-line bg-surface p-4 text-sm shadow-card">
              <div>
                <dt className="text-xs text-muted">Tạo lúc</dt>
                <dd className="font-semibold text-ink tabular">{fmtDateTime(d.generated_at)}</dd>
              </div>
              {isOperator && (
                <>
                  <div>
                    <dt className="text-xs text-muted">Dựa trên lượt quét</dt>
                    <dd className="font-semibold text-ink tabular">{d.scan_run_id === null ? "—" : `#${d.scan_run_id}`}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Mô hình</dt>
                    <dd className="font-semibold text-ink">
                      {d.model} · {d.prompt_version}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Token vào / ra</dt>
                    <dd className="font-semibold text-ink tabular">
                      {fmtInt(d.tokens_in)} / {fmtInt(d.tokens_out)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Chi phí</dt>
                    <dd className="font-semibold text-ink tabular">{fmtNum(d.cost_usd, 4)} USD</dd>
                  </div>
                </>
              )}
            </dl>
          </aside>
        </div>
      )}
    </>
  );
}
