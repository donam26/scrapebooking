"use client";

import { useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi, useInterval } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useFmt } from "@/lib/format";
import { INSIGHT_STATUS_TONE, useLabel } from "@/lib/labels";
import { Badge, ErrorBox, Note, PageHeader, SkeletonBlock, Spinner, cx } from "@/components/ui";
import { InsightView, parseDropped, parseInsightOutput } from "../insight-view";

export default function InsightDetailPage() {
  const t = useTranslations("insights.detail");
  const tSection = useTranslations("insights.sections");
  const { fmtPeriod, fmtDateTime, fmtInt, fmtNum, fmtWhen } = useFmt();
  const label = useLabel();
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
        { id: "tom-tat", label: tSection("summary"), n: null as number | null },
        { id: "noi-bat", label: tSection("highlights"), n: out.highlights.length },
        { id: "nhu-cau", label: tSection("demandSignals"), n: out.demand_signals.length },
        { id: "co-hoi-gia", label: tSection("pricing"), n: out.pricing_opportunities.length },
        { id: "rui-ro", label: tSection("risks"), n: out.risks.length },
        ...(out.data_quality_note ? [{ id: "du-lieu", label: tSection("dataQuality"), n: null }] : []),
        ...(dropped.length ? [{ id: "bi-loai", label: tSection("dropped"), n: dropped.length }] : []),
      ]
    : [];

  return (
    <>
      <PageHeader
        crumbs={[{ href: "/insights", label: t("crumb") }, { label: d ? t("titleAt", { when: fmtWhen(d.generated_at) }) : t("title") }]}
        title={d ? t("titleAt", { when: fmtWhen(d.generated_at) }) : t("title")}
        subtitle={
          d && (
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="tabular">{t("dataNights", { period: fmtPeriod(d.period_start, d.period_end) })}</span>
              <span>{label("insightTrigger", d.trigger)}</span>
              {d.status !== "completed" && <Badge tone={INSIGHT_STATUS_TONE[d.status] ?? "gray"}>{label("insightStatus", d.status)}</Badge>}
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
                {t("pending")}
              </Note>
            )}
            {d.status === "failed" && d.error && <ErrorBox error={d.error} className="mb-5" title={t("failedTitle")} />}
            <InsightView insight={d} hotels={hotels.data ?? []} eventOf={eventOf} />
          </div>

          <aside className="space-y-4 xl:sticky xl:top-8">
            {toc.length > 0 && (
              <nav aria-label={t("toc")} className="rounded-xl border border-line bg-surface p-2 shadow-card">
                <div className="px-3 pb-1 pt-2 text-xs font-semibold text-muted">{t("toc")}</div>
                <ul>
                  {toc.map((item) => (
                    <li key={item.id}>
                      <a href={`#${item.id}`} className="flex items-center justify-between rounded-lg px-3 py-1.5 text-base text-body hover:bg-subtle hover:text-ink">
                        {item.label}
                        {item.n !== null && <span className={cx("text-sm tabular", item.n === 0 ? "text-faint" : "font-semibold text-muted")}>{item.n}</span>}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            )}
            <dl className="space-y-2.5 rounded-xl border border-line bg-surface p-4 text-sm shadow-card">
              <div>
                <dt className="text-xs text-muted">{t("generatedAt")}</dt>
                <dd className="font-semibold text-ink tabular">{fmtDateTime(d.generated_at)}</dd>
              </div>
              {isOperator && (
                <>
                  <div>
                    <dt className="text-xs text-muted">{t("basedOnRun")}</dt>
                    <dd className="font-semibold text-ink tabular">{d.scan_run_id === null ? "—" : `#${d.scan_run_id}`}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">{t("model")}</dt>
                    <dd className="font-semibold text-ink">
                      {d.model} · {d.prompt_version}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">{t("tokens")}</dt>
                    <dd className="font-semibold text-ink tabular">
                      {fmtInt(d.tokens_in)} / {fmtInt(d.tokens_out)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">{t("cost")}</dt>
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
