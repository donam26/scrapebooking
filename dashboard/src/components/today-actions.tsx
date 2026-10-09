"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { ReactNode } from "react";
import { api, cellState, type MarketPaceOut, type OverviewOut, type SuggestionOut } from "@/lib/api";
import { addDays, dateRange, useFmt } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Tone } from "@/lib/labels";
import { SUGGESTION_TONE, actionableSuggestions, adjustmentText, suggestionTarget, useMarketText } from "@/lib/market";
import { cellOn, compsetTightness, competitorRows, fillIndicator, isTightNight, rowName, selfRow } from "@/lib/market-metrics";
import { Badge, Card, ErrorBox, SkeletonBlock } from "./ui";
import { IconChevronRight } from "./icons";

/**
 * VIỆC CẦN LÀM HÔM NAY (đầu Bảng điều khiển và Hôm nay): tối đa 5 việc từ dữ liệu sẵn có, theo thứ tự
 * gợi ý tăng/giảm giá (giá mục tiêu backend tính theo chiến lược giá, kèm cơ sở giá), đối thủ hết
 * phòng đêm nay, rồi đêm căng trong 14 đêm tới; mỗi đêm một mục. "Giữ giá" (đa số đêm) không phải
 * việc cần làm nên không liệt kê. Mỗi việc dẫn tới chi tiết đêm của khách sạn bạn (chưa có thì tới
 * Nhịp đặt phòng).
 */

/** Số đêm tính từ hôm nay để tìm đêm căng và gợi ý. */
export const ACTION_NIGHTS = 14;
const MAX_ITEMS = 5;

type Item = { key: string; tone: Tone; badge: string; night: string; href: string; lines: ReactNode[] };

function covers(x: { start: string; end: string } | undefined, start: string, end: string): boolean {
  return !!x && x.start === start && x.end >= end;
}

/**
 * `fromParent`: trang đã tải (hoặc đang tải) overview + nhịp phủ 14 đêm từ hôm nay và truyền vào; thẻ
 * không tự tải. Không thì thẻ tự tải dữ liệu 14 đêm của mình (VD Bảng điều khiển đang xem kỳ khác).
 */
export function TodayActions({
  today,
  ownHotelId = null,
  fromParent,
  overview,
  pace,
  error: parentError,
}: {
  today: string;
  /** Khách sạn của bạn đang xem (`?hotel=`); null = server chọn. */
  ownHotelId?: number | null;
  fromParent: boolean;
  overview?: OverviewOut;
  pace?: MarketPaceOut;
  /** Lỗi tải dữ liệu của trang khi `fromParent`. */
  error?: unknown;
}) {
  const t = useTranslations("components.todayActions");
  const tm = useTranslations("helpers.marketMetrics");
  const { fmtMoney, fmtNight } = useFmt();
  const { suggestionLabel, fmtChange } = useMarketText();
  const end = addDays(today, ACTION_NIGHTS - 1);
  const ownOv = useApi(fromParent ? null : `actions:ov:${today}:${ownHotelId ?? ""}`, () => api.overview({ start: today, end, own_hotel_id: ownHotelId }));
  const ownPace = useApi(fromParent ? null : `actions:pace:${today}:${ownHotelId ?? ""}`, () => api.market.pace({ start: today, end, own_hotel_id: ownHotelId }));
  // Dữ liệu cũ của kỳ khác (đang tải lại) không được dùng: coi như đang tải.
  const o = fromParent ? (covers(overview, today, end) ? overview : undefined) : ownOv.data;
  const p = fromParent ? (covers(pace, today, end) ? pace : undefined) : ownPace.data;
  const error = fromParent ? parentError : (ownOv.error ?? ownPace.error);

  const items: Item[] = [];
  if (o && p) {
    const ownId = p.own_hotel_id ?? selfRow(o)?.hotel.id ?? null;
    const hrefFor = (d: string) => (ownId ? `/hotels/${ownId}/dates/${d}` : "/pace");
    const nightLabel = (d: string) => (d === today ? t("tonight") : fmtNight(d));
    const byNight = new Map(p.nights.map((n) => [n.stay_date, n]));
    const small = (n: { smallSample: boolean }) => (n.smallSample ? ` · ${tm("smallSample")}` : "");

    // 1. Gợi ý tăng/giảm giá đang chờ (giữ giá không phải việc cần làm).
    const moves = actionableSuggestions(p.nights).filter((n) => n.stay_date >= today && n.stay_date <= end);
    const suggestionItem = (n: (typeof moves)[number]): Item => {
      const s = n.suggestion as SuggestionOut;
      const target = suggestionTarget(n);
      const lines: ReactNode[] = [];
      if (target !== null) {
        lines.push(
          <span key="target">
            {t.rich("target", {
              price: fmtMoney(target, n.currency),
              change: fmtChange(s.change_pct),
              b: (c) => <span className="font-bold text-ink tabular">{c}</span>,
            })}
          </span>,
        );
        lines.push(<span key="basis">{t("basis", { price: fmtMoney(n.own_price, n.currency) })}</span>);
      } else {
        lines.push(<span key="target">{t("noOwnPrice", { change: fmtChange(s.change_pct) })}</span>);
      }
      // Lý do chính: điều chỉnh có % lớn nhất (dữ liệu cũ: lý do đầu tiên).
      // Lý do chính cùng chiều với gợi ý (tăng → điều chỉnh dương lớn nhất); không có thì là giá tham chiếu.
      const sign = s.kind === "lower" ? -1 : 1;
      const main = [...s.adjustments].filter((r) => (r.pct ?? 0) * sign > 0).sort((a, b) => (b.pct ?? 0) * sign - (a.pct ?? 0) * sign)[0];
      const reason = main ? adjustmentText(main) : s.reasons[0] ? s.reasons[0].charAt(0).toUpperCase() + s.reasons[0].slice(1) : null;
      if (reason) lines.push(<span key="reason">{t("reason", { reason })}</span>);
      return { key: `sug${n.stay_date}`, tone: SUGGESTION_TONE[s.kind], badge: suggestionLabel(s.kind), night: nightLabel(n.stay_date), href: hrefFor(n.stay_date), lines };
    };
    items.push(...moves.map(suggestionItem));
    const covered = new Set(moves.map((n) => n.stay_date));

    // 2. Đối thủ hết phòng đêm nay.
    // Chỉ hết phòng thật; bị hạn chế (min-stay, đóng ngày đến) không tính.
    const soldTonight = competitorRows(o).filter((r) => cellState(cellOn(r, today)) === "sold_out");
    if (soldTonight.length && !covered.has(today)) {
      const tn = compsetTightness(o, today);
      covered.add(today);
      items.push({
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
      items.push({ key: `tight${d}`, tone: "amber", badge: t("badge.tight"), night: nightLabel(d), href: hrefFor(d), lines: [<span key="n">{parts.join(" · ")}</span>] });
    }
  }

  const shown = items.slice(0, MAX_ITEMS);
  return (
    <Card title={t("title")} info={t("info", { nights: ACTION_NIGHTS })} className="border-brand/30 ring-1 ring-brand/10">
      <ErrorBox error={error} className="mb-3" />
      {!(o && p) && !error ? (
        <div aria-busy className="space-y-2">
          <SkeletonBlock className="h-14 w-full rounded-lg" />
          <SkeletonBlock className="h-14 w-full rounded-lg" />
        </div>
      ) : o && p && shown.length === 0 ? (
        <p className="text-sm text-muted">{t("empty", { nights: ACTION_NIGHTS })}</p>
      ) : (
        <ol className="divide-y divide-line">
          {shown.map((it) => (
            <li key={it.key}>
              <Link href={it.href} className="group -mx-2 flex items-start gap-3 rounded-md px-2 py-2.5 transition-colors hover:bg-subtle">
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
      {items.length > shown.length && (
        <Link href="/pace" className="mt-2 inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline">
          {t("more", { count: items.length - shown.length })} <IconChevronRight size={15} />
        </Link>
      )}
    </Card>
  );
}
