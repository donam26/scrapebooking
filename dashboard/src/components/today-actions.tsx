"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { cellState, type MarketPaceOut, type OverviewOut, type PaceNightOut } from "@/lib/api";
import { addDays, dateRange, useFmt } from "@/lib/format";
import type { FreshnessState } from "@/lib/freshness";
import type { Tone } from "@/lib/labels";
import { cellOn, compsetTightness, competitorRows, fillIndicator, isTightNight, rowName, selfRow } from "@/lib/market-metrics";
import { SuggestionCard } from "./market-suggestion";
import { Badge, Card, ErrorBox, SkeletonBlock } from "./ui";
import { IconAlert, IconChevronRight } from "./icons";

/**
 * VIỆC CẦN LÀM HÔM NAY (đầu trang Hôm nay): việc thật trong 14 đêm tới, theo thứ tự gợi ý tăng/giảm
 * giá (giá mục tiêu, một câu lý do, nút "Tôi đã đổi giá" / "Bỏ qua" ngay trên thẻ), đối thủ hết
 * phòng đêm nay, rồi đêm căng. "Giữ giá" không phải việc cần làm. Đã ghi quyết định thì thẻ thu lại
 * một dòng có "Hoàn tác".
 *
 * Dữ liệu Booking.com đã cũ (quá một chu kỳ quét) thì không đưa việc nào: gợi ý trên số cũ có thể sai.
 */

/** Số đêm tính từ hôm nay để tìm đêm căng và gợi ý. */
export const ACTION_NIGHTS = 14;
const MAX_ITEMS = 5;

type LinkItem = { key: string; tone: Tone; badge: string; night: string; href: string; lines: ReactNode[] };

function covers(x: { start: string; end: string } | undefined, start: string, end: string): boolean {
  return !!x && x.start === start && x.end >= end;
}

export function TodayActions({
  today,
  overview,
  pace,
  error,
  fresh,
  canWrite,
  onChanged,
}: {
  today: string;
  /** Overview + nhịp phủ ít nhất 14 đêm từ hôm nay (trang đã tải). */
  overview: OverviewOut | undefined;
  pace: MarketPaceOut | undefined;
  error?: unknown;
  fresh: FreshnessState;
  canWrite: boolean;
  /** Tải lại nhịp sau khi ghi/hoàn tác một quyết định. */
  onChanged: () => void;
}) {
  const t = useTranslations("components.todayActions");
  const tm = useTranslations("helpers.marketMetrics");
  const { fmtNight, fmtWhen, fmtAgo } = useFmt();
  const [showAll, setShowAll] = useState(false);
  const end = addDays(today, ACTION_NIGHTS - 1);
  const o = covers(overview, today, end) ? overview : undefined;
  const p = covers(pace, today, end) ? pace : undefined;

  const ownId = p?.own_hotel_id ?? (o ? selfRow(o)?.hotel.id : null) ?? null;
  const hrefFor = (d: string) => (ownId ? `/hotels/${ownId}/dates/${d}` : "/calendar");
  const nightLabel = (d: string) => (d === today ? t("tonight") : fmtNight(d));

  // 1. Gợi ý tăng/giảm giá (cả đã ghi quyết định, để còn hoàn tác tại chỗ).
  const moves: PaceNightOut[] = (p?.nights ?? []).filter((n) => n.suggestion && n.suggestion.kind !== "hold" && n.stay_date >= today && n.stay_date <= end);
  const pending = moves.filter((n) => !n.suggestion!.decision);
  const decided = moves.filter((n) => n.suggestion!.decision);
  const covered = new Set(moves.map((n) => n.stay_date));

  const links: LinkItem[] = [];
  if (o && p) {
    const byNight = new Map(p.nights.map((n) => [n.stay_date, n]));
    const small = (n: { smallSample: boolean }) => (n.smallSample ? ` · ${tm("smallSample")}` : "");
    // 2. Đối thủ hết phòng đêm nay (hạn chế min-stay, đóng ngày đến không tính).
    const soldTonight = competitorRows(o).filter((r) => cellState(cellOn(r, today)) === "sold_out");
    if (soldTonight.length && !covered.has(today)) {
      const tn = compsetTightness(o, today);
      covered.add(today);
      links.push({
        key: "soldTonight",
        tone: "red",
        badge: t("badge.soldOut"),
        night: t("tonight"),
        href: hrefFor(today),
        lines: [
          <span key="names">{t("soldOutTonight", { count: soldTonight.length, names: soldTonight.map(rowName).join(", ") })}</span>,
          <span key="n">{t("tightCount", { tight: tn.tight, observed: tn.observed }) + small(tn)}</span>,
        ],
      });
    }
    // 3. Đêm căng trong 14 đêm tới.
    for (const d of dateRange(today, end)) {
      if (covered.has(d)) continue;
      const tn = compsetTightness(o, d);
      const fill = fillIndicator(byNight.get(d), p.calibration);
      if (!isTightNight(tn, fill)) continue;
      const parts = [];
      if (tn.observed) parts.push(t("tightCount", { tight: tn.tight, observed: tn.observed }) + small(tn));
      if (fill !== null) parts.push(t("fill", { pct: Math.round(fill * 100) }));
      covered.add(d);
      links.push({ key: `tight${d}`, tone: "amber", badge: t("badge.tight"), night: nightLabel(d), href: hrefFor(d), lines: [<span key="n">{parts.join(" · ")}</span>] });
    }
  }

  const total = pending.length + links.length;
  const limit = showAll ? total : MAX_ITEMS;
  const shownMoves = pending.slice(0, limit);
  const shownLinks = links.slice(0, Math.max(0, limit - shownMoves.length));
  const hidden = total - shownMoves.length - shownLinks.length;

  return (
    <Card title={t("title")} info={t("info", { nights: ACTION_NIGHTS })} className="border-brand/30 ring-1 ring-brand/10">
      <ErrorBox error={error} className="mb-3" />
      {fresh.loaded && fresh.stale ? (
        <div role="status" className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger-deep">
          <IconAlert size={17} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">{t("staleTitle")}</p>
            <p className="mt-0.5">
              {fresh.updatedAt ? t("staleBody", { when: fmtWhen(fresh.updatedAt), ago: fmtAgo(fresh.updatedAt) }) : t("staleNever")}{" "}
              <Link href="/runs" className="font-semibold underline hover:no-underline">
                {t("staleLink")}
              </Link>
            </p>
          </div>
        </div>
      ) : !(o && p) && !error ? (
        <div aria-busy className="space-y-2">
          <SkeletonBlock className="h-24 w-full rounded-lg" />
          <SkeletonBlock className="h-24 w-full rounded-lg" />
        </div>
      ) : o && p && total === 0 && decided.length === 0 ? (
        <p className="text-sm text-body">{t("empty", { nights: ACTION_NIGHTS })}</p>
      ) : (
        <div className="space-y-2.5">
          {shownMoves.map((n) => (
            <SuggestionCard
              key={n.stay_date}
              night={n}
              ownHotelId={ownId}
              canWrite={canWrite}
              onChanged={onChanged}
              brief
              title={n.stay_date === today ? t("tonight") : undefined}
            />
          ))}
          {shownLinks.length > 0 && (
            <ol className="divide-y divide-line rounded-xl border border-line">
              {shownLinks.map((it) => (
                <li key={it.key}>
                  <Link href={it.href} className="group flex items-start gap-3 px-4 py-3 transition-colors hover:bg-subtle">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-sm font-bold text-ink tabular">{it.night}</span>
                        <Badge tone={it.tone}>{it.badge}</Badge>
                      </div>
                      <div className="mt-1 flex flex-col gap-0.5 text-sm text-body">{it.lines}</div>
                    </div>
                    <IconChevronRight size={16} className="mt-1 shrink-0 text-faint group-hover:text-brand" />
                  </Link>
                </li>
              ))}
            </ol>
          )}
          {hidden > 0 && (
            <button type="button" onClick={() => setShowAll(true)} className="inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline">
              {t("more", { count: hidden })} <IconChevronRight size={15} />
            </button>
          )}
          {decided.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <p className="text-xs font-semibold text-muted">{t("decided", { count: decided.length })}</p>
              {decided.map((n) => (
                <SuggestionCard key={n.stay_date} night={n} ownHotelId={ownId} canWrite={canWrite} onChanged={onChanged} brief title={n.stay_date === today ? t("tonight") : fmtNight(n.stay_date)} />
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
