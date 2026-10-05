"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type InsightOut } from "@/lib/api";
import { useErrorMessage } from "@/lib/errors";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useFmt } from "@/lib/format";
import { INSIGHT_STATUS_TONE, LEVEL_TONE, useLabel } from "@/lib/labels";
import { Badge, Button, EmptyState, ErrorBox, Note, PageHeader, SkeletonBlock, Spinner, cx } from "@/components/ui";
import { BRIEF_TABS, SubTabs } from "@/components/sub-tabs";
import { IconArrowRight, IconBrief, IconCalendar, IconSparkle } from "@/components/icons";
import { insightCounts, parseInsightOutput } from "./insight-view";

const POLL_MS = 5000;

function Counts({ r }: { r: InsightOut }) {
  const t = useTranslations("insights.counts");
  const c = insightCounts(parseInsightOutput(r.output_json));
  const parts = [
    c.highlights && t("highlights", { count: c.highlights }),
    c.signals && t("signals", { count: c.signals }),
    c.pricing && t("pricing", { count: c.pricing }),
    c.risks && t("risks", { count: c.risks }),
  ].filter(Boolean);
  return parts.length ? <span>{parts.join(" · ")}</span> : null;
}

/** Thông tin kỹ thuật (chỉ operator): mô hình, token, chi phí. */
function Tech({ r }: { r: InsightOut }) {
  const t = useTranslations("insights.list");
  const { fmtInt, fmtNum } = useFmt();
  return (
    <span className="text-xs text-faint tabular" title={t("operatorOnly")}>
      {t("tech", { model: r.model, version: r.prompt_version, tokensIn: fmtInt(r.tokens_in), tokensOut: fmtInt(r.tokens_out), cost: fmtNum(r.cost_usd, 4) })}
    </span>
  );
}

function Latest({ r, isOperator }: { r: InsightOut; isOperator: boolean }) {
  const t = useTranslations("insights.list");
  const tLevel = useTranslations("insights.level");
  const { fmtPeriod, fmtWhen } = useFmt();
  const label = useLabel();
  const out = parseInsightOutput(r.output_json);
  const top = out?.highlights.slice(0, 3) ?? [];
  return (
    <article className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line bg-night px-6 py-4 text-on-night-soft">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-white/10 text-exact">
            <IconSparkle size={18} />
          </span>
          <div>
            <h2 className="text-md font-bold text-white">{t("latest")}</h2>
            <div className="text-sm">
              {fmtWhen(r.generated_at)} · {label("insightTrigger", r.trigger)}
            </div>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 text-sm tabular">
          <IconCalendar size={15} className="text-on-night-muted" />
          {t("dataNights", { period: fmtPeriod(r.period_start, r.period_end) })}
        </span>
      </header>
      <div className="px-6 py-5">
        <p className="max-w-[75ch] text-lg leading-[1.7] text-ink">{out?.summary || t("noSummaryYet")}</p>
        {top.length > 0 && (
          <ul className="mt-5 space-y-2">
            {top.map((h, i) => (
              <li key={i} className="flex items-start gap-3 rounded-lg bg-subtle px-4 py-3">
                <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                <span className="min-w-0 flex-1 text-base font-semibold text-ink">{h.title}</span>
                {h.confidence && (
                  <Badge tone={LEVEL_TONE[h.confidence] ?? "gray"} className="shrink-0">
                    {tLevel("confidence", { level: h.confidence, label: label("level", h.confidence).toLowerCase() })}
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-6 py-3.5 text-sm text-muted">
        <span className="flex flex-col gap-0.5">
          <Counts r={r} />
          {isOperator && <Tech r={r} />}
        </span>
        <Link href={`/insights/${r.id}`} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3.5 text-base font-semibold text-white hover:bg-brand-hover">
          {t("readFull")} <IconArrowRight size={16} />
        </Link>
      </footer>
    </article>
  );
}

function OlderRow({ r, isOperator }: { r: InsightOut; isOperator: boolean }) {
  const t = useTranslations("insights.list");
  const { fmtPeriod, fmtWhen } = useFmt();
  const label = useLabel();
  const errorText = useErrorMessage();
  const out = parseInsightOutput(r.output_json);
  const done = r.status === "completed";
  return (
    <li>
      <Link href={`/insights/${r.id}`} className="group grid gap-x-6 gap-y-1 px-5 py-4 transition-colors hover:bg-subtle md:grid-cols-[180px_minmax(0,1fr)_auto]">
        <div>
          <div className="font-semibold text-ink tabular group-hover:text-brand">{fmtWhen(r.generated_at)}</div>
          <div className="text-sm text-muted">{label("insightTrigger", r.trigger)}</div>
        </div>
        <div className="min-w-0">
          {done ? (
            <p className="line-clamp-2 text-base text-body">{out?.summary || t("noSummary")}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={INSIGHT_STATUS_TONE[r.status] ?? "gray"}>{label("insightStatus", r.status)}</Badge>
              {r.status === "failed" && r.error && <span className="truncate text-sm text-danger-deep">{errorText(r.error)}</span>}
            </div>
          )}
          <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted">
            <span className="tabular">{t("nights", { period: fmtPeriod(r.period_start, r.period_end) })}</span>
            {done && <Counts r={r} />}
          </div>
          {isOperator && (
            <div className="mt-0.5">
              <Tech r={r} />
            </div>
          )}
        </div>
        <IconArrowRight size={16} className="hidden self-center text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-brand md:block" />
      </Link>
    </li>
  );
}

export default function InsightsPage() {
  const t = useTranslations("insights.list");
  const { canWrite, isOperator } = useSession();
  const list = useApi("insights", () => api.insights.list(50));
  const settings = useApi("settings", () => api.settings.get());
  const [pollingId, setPollingId] = useState<number | null>(null);
  const generate = useMutation(async () => {
    const created = await api.insights.generate();
    setPollingId(created.id);
    list.reload();
    return created;
  });

  // Poll GET /insights/{id} mỗi 5s tới khi status != pending, rồi tải lại danh sách.
  const reload = list.reload;
  useEffect(() => {
    if (pollingId === null) return;
    const id = window.setInterval(async () => {
      try {
        const row = await api.insights.get(pollingId);
        if (row.status !== "pending") {
          setPollingId(null);
          reload();
        }
      } catch {
        setPollingId(null);
      }
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [pollingId, reload]);

  const rows = list.data ?? [];
  const latest = rows.find((r) => r.status === "completed") ?? null;
  const others = rows.filter((r) => r !== latest);
  const hour = settings.data?.insight_hour;

  return (
    <>
      <SubTabs items={BRIEF_TABS} />
      <PageHeader
        title={t("title")}
        subtitle={hour ? t("subtitleAt", { hour }) : t("subtitle")}
        actions={
          canWrite && (
            <Button variant="primary" icon={<IconSparkle size={16} />} busy={generate.busy || pollingId !== null} onClick={() => void generate.run()}>
              {pollingId !== null ? t("generating") : t("generate")}
            </Button>
          )
        }
      />
      {pollingId !== null && (
        <Note tone="info" icon={<Spinner className="text-brand" />} className="mb-4">
          {t("generatingNote")}
        </Note>
      )}
      <ErrorBox error={generate.error} className="mb-4" />
      <ErrorBox error={list.error} className="mb-4" />

      {!list.data && !list.error ? (
        <div className="space-y-4" aria-busy>
          <SkeletonBlock className="h-[300px] w-full rounded-xl" />
          <SkeletonBlock className="h-[220px] w-full rounded-xl" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<IconBrief />}
          title={t("emptyTitle")}
          className="border border-line bg-surface"
          action={
            canWrite && (
              <Button variant="primary" icon={<IconSparkle size={16} />} busy={generate.busy} onClick={() => void generate.run()}>
                {t("generateFirst")}
              </Button>
            )
          }
        >
          {hour ? t("emptyBodyAt", { hour }) : t("emptyBody")}
        </EmptyState>
      ) : (
        <div className={cx("space-y-6", list.loading && "opacity-70")}>
          {latest && <Latest r={latest} isOperator={isOperator} />}
          {others.length > 0 && (
            <section>
              <h2 className="mb-3 text-lg font-bold text-ink">
                {latest ? t("previous") : t("briefs")} <span className="text-base font-semibold text-muted tabular">{others.length}</span>
              </h2>
              <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface shadow-card">
                {others.map((r) => (
                  <OlderRow key={r.id} r={r} isOperator={isOperator} />
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </>
  );
}
