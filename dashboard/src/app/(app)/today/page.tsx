"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { api, type CompsetDayOut, type DateCell, type HotelRow } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, todayIso, useFmt } from "@/lib/format";
import { deltaVsMedian, useNightReason } from "@/lib/night-reason";
import { pendingSuggestions, SUGGESTION_TONE, useMarketText } from "@/lib/market";
import { MarkSwatch, useMarks } from "@/components/marks";
import { EventTable } from "@/components/event-table";
import { SuggestionCard } from "@/components/market-suggestion";
import { Badge, ButtonLink, Card, EmptyState, ErrorBox, Note, PageHeader, SkeletonBlock, cx } from "@/components/ui";
import { IconArrowRight, IconBrief, IconBuilding, IconPlus } from "@/components/icons";

const DAYS = 7;

type TodayTranslator = ReturnType<typeof useTranslations<"today">>;

function name(row: HotelRow, t: TodayTranslator): string {
  return row.label || row.hotel.name || t("hotelFallback", { id: row.hotel.id });
}

function statusText(cell: DateCell | undefined, t: TodayTranslator): string {
  if (!cell || cell.availability_status === null) return t("status.noData");
  if (cell.availability_status === "sold_out") return t("status.soldOut");
  if (cell.availability_status === "unknown") return t("status.unknown");
  return cell.exact_rooms_left === null ? t("status.available") : t("status.roomsLeft", { count: cell.exact_rooms_left });
}

function signedPct(v: number | null): string {
  if (v === null) return "—";
  return v > 0 ? `+${v}%` : v < 0 ? `−${-v}%` : "0%";
}

export default function TodayPage() {
  const t = useTranslations("today");
  const tc = useTranslations("common.actions");
  const { fmtCompact, fmtDateShort, fmtMoney, fmtWeekday, fmtWhen } = useFmt();
  const { nightReason } = useNightReason();
  const { suggestionLabel } = useMarketText();
  const { cellMark } = useMarks();
  const [today] = useState(todayIso);
  const end = addDays(today, DAYS - 1);
  const { canWrite } = useSession();
  const [since] = useState(() => new Date(Date.now() - 24 * 3600 * 1000).toISOString());
  const overview = useApi(`today:overview:${today}`, () => api.overview({ start: today, end }));
  const pace = useApi(`today:pace:${today}`, () => api.market.pace({ start: today, end }));
  const events = useApi(`today:events:${today}`, () => api.events({ observed_since: since, limit: 8 }));
  const insights = useApi("today:insights", () => api.insights.list(1));

  const data = overview.data;
  const self = data?.hotels.find((h) => h.role === "self") ?? null;
  const labels = new Map((data?.hotels ?? []).map((h) => [h.hotel.id, name(h, t)]));
  const compset = new Map<string, CompsetDayOut>((data?.compset ?? []).map((c) => [c.stay_date, c]));
  const holidays = new Map((data?.holidays ?? []).map((h) => [h.date, h.name]));
  const tonight = self?.cells.find((c) => c.stay_date === today);
  const c0 = compset.get(today);
  const reason = nightReason(c0, holidays.get(today));
  const suggestions = pace.data ? pendingSuggestions(pace.data.nights) : [];
  const byNight = new Map((pace.data?.nights ?? []).map((n) => [n.stay_date, n]));
  const insight = insights.data?.find((i) => i.status === "completed");
  const summary = typeof insight?.output_json?.summary === "string" ? insight.output_json.summary : null;
  const run = data?.last_run ?? null;

  return (
    <div className="mx-auto max-w-[760px]">
      <PageHeader
        title={t("title")}
        subtitle={
          <span>
            {fmtWeekday(today)} {fmtDateShort(today)}
            {run && ` · ${t("scannedAt", { when: fmtWhen(run.finished_at ?? run.started_at) })}`}
          </span>
        }
      />
      <ErrorBox error={overview.error} className="mb-4" />
      {!data && !overview.error && (
        <div aria-busy className="space-y-3">
          <SkeletonBlock className="h-28 w-full rounded-xl" />
          <SkeletonBlock className="h-64 w-full rounded-xl" />
        </div>
      )}
      {data && data.hotels.length === 0 && (
        <EmptyState
          icon={<IconBuilding />}
          title={t("empty.title")}
          className="border border-line bg-surface"
          action={
            <ButtonLink href="/settings?tab=watchlist" variant="primary" icon={<IconPlus size={16} />}>
              {t("empty.add")}
            </ButtonLink>
          }
        >
          {t("empty.body")}
        </EmptyState>
      )}
      {data && data.hotels.length > 0 && (
        <div className="space-y-4">
          <section aria-label={t("tonight.aria")} className="rounded-xl border border-yours/35 bg-surface p-4 shadow-card ring-1 ring-yours/10 sm:p-5">
            {self ? (
              <>
                <div className="flex items-center gap-3">
                  <MarkSwatch mark={cellMark(tonight)} size={32} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-muted">{t("tonight.hotelTonight", { name: name(self, t) })}</div>
                    <div className="text-xl font-bold text-ink tabular">{statusText(tonight, t)}</div>
                  </div>
                  {tonight?.min_price && (
                    <div className="text-right">
                      <div className="text-sm text-muted">{t("tonight.lowestRate")}</div>
                      <div className="text-lg font-bold text-ink tabular">{fmtMoney(tonight.min_price, tonight.currency)}</div>
                    </div>
                  )}
                </div>
                {reason && <p className="mt-3 border-t border-line pt-3 text-base text-body">{reason}</p>}
              </>
            ) : (
              <Note tone="info">{t("tonight.noSelf")}</Note>
            )}
          </section>

          <ErrorBox error={pace.error ?? insights.error} />
          {suggestions.length > 0 && (
            <Card
              title={t("suggestions.title")}
              description={t("suggestions.description", { count: suggestions.length, days: DAYS })}
              actions={
                <Link href="/terminal#pace" className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
                  {tc("viewAll")} <IconArrowRight size={14} />
                </Link>
              }
            >
              <div className="space-y-3">
                {suggestions.slice(0, 3).map((n) => (
                  <SuggestionCard key={n.stay_date} night={n} ownHotelId={pace.data?.own_hotel_id ?? null} canWrite={canWrite} onChanged={pace.reload} compact />
                ))}
              </div>
            </Card>
          )}

          <Card title={t("nights.title", { days: DAYS })} padded={false}>
            <ul className="divide-y divide-line">
              {Array.from({ length: DAYS }, (_, i) => addDays(today, i)).map((d) => {
                const cell = self?.cells.find((c) => c.stay_date === d);
                const c = compset.get(d);
                const delta = deltaVsMedian(c?.price_index);
                const sug = byNight.get(d)?.suggestion;
                const row = (
                  <div className="flex items-center gap-3 px-4 py-3 sm:px-5">
                    <div className="w-[68px] shrink-0">
                      <div className="text-sm font-bold text-ink tabular">
                        {fmtWeekday(d)} {fmtDateShort(d)}
                      </div>
                      {holidays.get(d) && <div className="truncate text-2xs font-semibold text-ink">{holidays.get(d)}</div>}
                    </div>
                    <MarkSwatch mark={cellMark(cell)} size={24} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-body">
                        {statusText(cell, t)}
                        {cell?.min_price && <span className="text-muted tabular"> · {fmtCompact(cell.min_price)}</span>}
                      </div>
                      <div className="text-xs text-muted tabular">
                        {c && c.competitors_observed ? t("nights.compSoldOut", { soldOut: c.competitors_sold_out, observed: c.competitors_observed }) : t("nights.noComp")}
                        {delta !== null && ` · ${t("nights.vsMedian", { pct: signedPct(delta) })}`}
                      </div>
                    </div>
                    {sug && !sug.decision && <Badge tone={SUGGESTION_TONE[sug.kind]}>{suggestionLabel(sug.kind)}</Badge>}
                  </div>
                );
                return (
                  <li key={d}>
                    {self ? (
                      <Link href={`/hotels/${self.hotel.id}/dates/${d}`} className={cx("block transition-colors duration-100 hover:bg-subtle")}>
                        {row}
                      </Link>
                    ) : (
                      row
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card
            title={t("changes.title")}
            padded={false}
            actions={
              <Link href="/events" className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
                {t("changes.allEvents")} <IconArrowRight size={14} />
              </Link>
            }
          >
            <ErrorBox error={events.error} className="m-4" />
            {events.data && (
              <EventTable events={events.data} labelOf={(id) => labels.get(id)} emptyText={t("changes.empty")} />
            )}
          </Card>

          {insight && (
            <Card
              title={t("brief.title")}
              actions={
                <Link href={`/insights/${insight.id}`} className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
                  {t("brief.read")} <IconArrowRight size={14} />
                </Link>
              }
            >
              <div className="flex gap-3">
                <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">
                  <IconBrief size={18} />
                </span>
                <p className="line-clamp-4 text-base text-body">{summary ?? t("brief.noSummary")}</p>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
