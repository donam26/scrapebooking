"use client";

import { useTranslations } from "next-intl";
import { api, type ReputationHotelOut, type VisibilityHotelOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, useFmt } from "@/lib/format";
import type { Tone } from "@/lib/labels";
import { Badge, ButtonLink, Card, EmptyState, ErrorBox, ROW_CLASS, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconPin, IconStar } from "@/components/icons";

/**
 * Đối thủ › Uy tín và vị trí hiển thị (roadmap 7.1, 7.2): điểm/số review theo thời gian, mốc điểm kế
 * tiếp của Booking, bản đồ giá–điểm (tương quan, không phải nhân quả) và thứ hạng trên trang kết quả
 * của khu vực (tách thẻ quảng cáo). Đọc từ trang kết quả đã quét, không tốn thêm lượt quét.
 */

const REPUTATION_DAYS = 90;
const VISIBILITY_DAYS = 14;
/** Chênh chỉ số giá − chỉ số điểm trong ±5 điểm thì coi là tương xứng. */
const MATCH_BAND = 5;

type Named = { hotel_id: number; name: string | null; role: string };

function useNames() {
  const t = useTranslations("reputation");
  return (h: Named) => h.name ?? t("hotelFallback", { id: h.hotel_id });
}

/** Mã huy hiệu đã biết → nhãn; chuỗi khác (tên deal) giữ nguyên. */
function useBadgeLabel() {
  const t = useTranslations("reputation.badge");
  return (code: string) => {
    const key = code.toLowerCase();
    return key === "ad" || key === "preferred" || key === "preferred_plus" || key === "genius" || key === "free_cancellation" ? t(key) : code;
  };
}

function Badges({ items }: { items: string[] }) {
  const label = useBadgeLabel();
  if (items.length === 0) return <span className="text-faint">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((b) => (
        <span key={b} className={cx("rounded-full px-2 py-0.5 text-2xs font-semibold", b.toLowerCase() === "ad" ? "bg-warning-soft text-warning-deep" : "bg-sunken text-body")}>
          {label(b)}
        </span>
      ))}
    </span>
  );
}

function HotelCell({ h }: { h: Named }) {
  const t = useTranslations("reputation");
  const name = useNames();
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className={cx("truncate font-semibold", h.role === "self" ? "text-brand" : "text-ink")} title={name(h)}>
        {name(h)}
      </span>
      {h.role === "self" && <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-2xs font-semibold text-brand-hover">{t("yourHotel")}</span>}
    </span>
  );
}

const THRESHOLD_KEY: Record<string, "t70" | "t75" | "t80" | "t90"> = { "7": "t70", "7.5": "t75", "8": "t80", "9": "t90" };

// ---- Uy tín ----

function ScoreChip({ score }: { score: number }) {
  const { fmtNum } = useFmt();
  return (
    <span className={cx("inline-grid h-7 min-w-8 place-items-center rounded-md rounded-bl-none px-1 text-sm font-bold text-white tabular", score >= 9 ? "bg-[#003b95]" : score >= 8 ? "bg-brand" : score >= 7 ? "bg-[#5b9bff]" : "bg-faint")}>
      {fmtNum(score, 1)}
    </span>
  );
}

function ReputationRow({ h, days }: { h: ReputationHotelOut; days: number }) {
  const t = useTranslations("reputation.reputation");
  const { fmtInt, fmtNum } = useFmt();
  const score = num(h.review_score);
  const change = num(h.score_change);
  const next = num(h.next_threshold);
  const gap = num(h.gap_to_next);
  const thKey = next !== null ? THRESHOLD_KEY[String(next)] : undefined;
  return (
    <tr className={cx(ROW_CLASS, h.role === "self" && "bg-brand-softer/40")}>
      <Td className="max-w-[240px] pl-5">
        <HotelCell h={h} />
      </Td>
      <Td right>{score === null ? <span className="text-faint">—</span> : <ScoreChip score={score} />}</Td>
      <Td right className="whitespace-nowrap" title={t("changeTitle", { days })}>
        {change === null ? <span className="text-faint">—</span> : <span className={change === 0 ? "text-muted" : "font-semibold text-ink"}>{change > 0 ? `+${fmtNum(change, 1)}` : change < 0 ? `−${fmtNum(-change, 1)}` : fmtNum(0, 1)}</span>}
      </Td>
      <Td right>{h.reviews_per_month === null ? <span className="text-faint">—</span> : fmtNum(h.reviews_per_month, 1)}</Td>
      <Td right>{fmtInt(h.review_count)}</Td>
      <Td className="whitespace-nowrap text-sm" title={thKey ? t(`threshold.${thKey}`) : undefined}>
        {next !== null && gap !== null ? (
          <span className="text-body">{t("gap", { gap: fmtNum(gap, 1), threshold: fmtNum(next, 1) })}</span>
        ) : score !== null && score >= 9 ? (
          <span className="text-muted">{t("top")}</span>
        ) : (
          <span className="text-faint">—</span>
        )}
      </Td>
      <Td className="pr-5">
        <Badges items={h.badges} />
      </Td>
    </tr>
  );
}

/** Bản đồ giá–điểm: trục ngang chỉ số điểm, trục dọc chỉ số giá niêm yết, 100 = trung vị compset. */
function ValueMap({ hotels }: { hotels: ReputationHotelOut[] }) {
  const t = useTranslations("reputation.valueMap");
  const name = useNames();
  const { fmtNum } = useFmt();
  const pts = hotels.flatMap((h) => {
    const price = num(h.price_index);
    const score = num(h.score_index);
    return price !== null && score !== null ? [{ h, price, score }] : [];
  });
  if (pts.length === 0) return <p className="text-sm text-muted">{t("empty")}</p>;
  const all = pts.flatMap((p) => [p.price, p.score]);
  const lo = Math.min(90, ...all) - 5;
  const hi = Math.max(110, ...all) + 5;
  const W = 220;
  const H = 180;
  const x = (v: number) => ((v - lo) / (hi - lo)) * W;
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H;
  const verdict = (price: number, score: number): { key: "above" | "below" | "match"; tone: Tone } =>
    price - score > MATCH_BAND ? { key: "above", tone: "amber" } : score - price > MATCH_BAND ? { key: "below", tone: "blue" } : { key: "match", tone: "gray" };
  return (
    <div className="grid gap-5 md:grid-cols-[240px_minmax(0,1fr)] md:items-start">
      <figure className="m-0">
        <svg viewBox={`-12 -6 ${W + 18} ${H + 22}`} role="img" aria-label={t("title")} className="w-full max-w-[260px]">
          <rect x={0} y={0} width={W} height={H} fill="var(--color-subtle, #f8fafc)" rx={6} />
          <line x1={0} x2={W} y1={H} y2={0} stroke="var(--color-line-strong, #d1d5db)" strokeDasharray="3 3" />
          <line x1={x(100)} x2={x(100)} y1={0} y2={H} stroke="var(--color-line-strong, #d1d5db)" />
          <line x1={0} x2={W} y1={y(100)} y2={y(100)} stroke="var(--color-line-strong, #d1d5db)" />
          {pts.map((p) => (
            <circle key={p.h.hotel_id} cx={x(p.score)} cy={y(p.price)} r={p.h.role === "self" ? 6 : 4.5} fill={p.h.role === "self" ? "var(--color-brand, #0052cc)" : "var(--color-muted, #6b7280)"} fillOpacity={p.h.role === "self" ? 1 : 0.7} stroke="#fff" strokeWidth={1.5}>
              <title>{t("point", { name: name(p.h), price: fmtNum(p.price, 0), score: fmtNum(p.score, 0) })}</title>
            </circle>
          ))}
          <text x={W / 2} y={H + 14} textAnchor="middle" fontSize={9} fill="var(--color-muted, #6b7280)">
            {t("axisScore")} →
          </text>
          <text x={-4} y={H / 2} textAnchor="middle" fontSize={9} fill="var(--color-muted, #6b7280)" transform={`rotate(-90 -4 ${H / 2})`}>
            {t("axisPrice")} →
          </text>
        </svg>
      </figure>
      <ul className="divide-y divide-line">
        {pts
          .sort((a, b) => b.price - b.score - (a.price - a.score))
          .map((p) => {
            const v = verdict(p.price, p.score);
            return (
              <li key={p.h.hotel_id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2">
                <HotelCell h={p.h} />
                <span className="flex items-center gap-2">
                  <span className="text-xs text-muted tabular">{t("values", { price: fmtNum(p.price, 0), score: fmtNum(p.score, 0) })}</span>
                  <Badge tone={v.tone}>{t(`verdict.${v.key}`)}</Badge>
                </span>
              </li>
            );
          })}
      </ul>
    </div>
  );
}

export function ReputationCard() {
  const t = useTranslations("reputation.reputation");
  const tv = useTranslations("reputation.valueMap");
  const q = useApi(`reputation:${REPUTATION_DAYS}`, () => api.market.reputation({ days: REPUTATION_DAYS }));
  const hotels = q.data ? [...q.data.hotels].sort((a, b) => Number(b.role === "self") - Number(a.role === "self") || (num(b.review_score) ?? 0) - (num(a.review_score) ?? 0)) : [];
  const anyScore = hotels.some((h) => h.review_score !== null);
  const days = q.data?.days ?? REPUTATION_DAYS;
  return (
    <>
      <Card title={t("title")} description={t("description", { days })} info={t("info")} icon={<IconStar size={15} />} padded={false}>
        <ErrorBox error={q.error} className="m-5" />
        {!q.data && !q.error && <Skeleton rows={4} className="p-5" />}
        {q.data && !anyScore && (
          <div className="p-5">
            <EmptyState icon={<IconStar />} title={t("emptyTitle")} compact>
              {t("emptyBody")}
            </EmptyState>
          </div>
        )}
        {q.data && anyScore && (
          <Table dense>
            <thead>
              <tr>
                <Th className="pl-5">{t("col.hotel")}</Th>
                <Th right>{t("col.score")}</Th>
                <Th right>{t("col.change")}</Th>
                <Th right>{t("col.perMonth")}</Th>
                <Th right>{t("col.count")}</Th>
                <Th>{t("col.next")}</Th>
                <Th className="pr-5">{t("col.badges")}</Th>
              </tr>
            </thead>
            <tbody>
              {hotels.map((h) => (
                <ReputationRow key={h.hotel_id} h={h} days={days} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {q.data && anyScore && (
        <Card title={tv("title")} description={tv("description")}>
          <ValueMap hotels={hotels} />
          <p className="mt-4 rounded-lg bg-subtle px-3.5 py-2.5 text-xs text-muted">{tv("caveat")}</p>
        </Card>
      )}
    </>
  );
}

// ---- Vị trí hiển thị ----

function VisibilityRow({ h }: { h: VisibilityHotelOut }) {
  const t = useTranslations("reputation.visibility");
  const { fmtInt, fmtNum, fmtShare } = useFmt();
  const seen = h.scans > 0;
  return (
    <tr className={cx(ROW_CLASS, h.role === "self" && "bg-brand-softer/40")}>
      <Td className="max-w-[240px] pl-5">
        <HotelCell h={h} />
      </Td>
      {seen ? (
        <>
          <Td right className="whitespace-nowrap">
            <span className="font-semibold text-ink">{fmtNum(h.avg_organic_rank, 1)}</span>
            {h.avg_rank !== null && h.avg_rank !== h.avg_organic_rank && <span className="ml-1 text-xs text-muted">{t("shown", { rank: fmtNum(h.avg_rank, 1) })}</span>}
          </Td>
          <Td right>{fmtInt(h.best_rank)}</Td>
          <Td right>{h.sponsored_share === null ? "—" : fmtShare(h.sponsored_share)}</Td>
          <Td>
            <Badges items={h.badges} />
          </Td>
        </>
      ) : (
        <Td colSpan={4} className="text-sm text-faint">
          {t("notSeen")}
        </Td>
      )}
      <Td right className="pr-5 text-muted">
        {fmtInt(h.scans)}
      </Td>
    </tr>
  );
}

export function VisibilityCard() {
  const t = useTranslations("reputation.visibility");
  const q = useApi(`visibility:${VISIBILITY_DAYS}`, () => api.market.visibility({ days: VISIBILITY_DAYS }));
  const hotels = q.data ? [...q.data.hotels].sort((a, b) => Number(b.role === "self") - Number(a.role === "self") || (num(a.avg_organic_rank) ?? 999) - (num(b.avg_organic_rank) ?? 999)) : [];
  const anySeen = hotels.some((h) => h.scans > 0);
  return (
    <Card title={t("title")} description={t("description", { days: q.data?.days ?? VISIBILITY_DAYS })} info={t("info")} icon={<IconPin size={15} />} padded={false}>
      <ErrorBox error={q.error} className="m-5" />
      {!q.data && !q.error && <Skeleton rows={4} className="p-5" />}
      {q.data && !anySeen && (
        <div className="p-5">
          <EmptyState
            icon={<IconPin />}
            title={t("emptyTitle")}
            compact
            action={
              <ButtonLink href="/settings?tab=market" size="sm">
                {t("emptyAction")}
              </ButtonLink>
            }
          >
            {t("emptyBody")}
          </EmptyState>
        </div>
      )}
      {q.data && anySeen && (
        <Table dense>
          <thead>
            <tr>
              <Th className="pl-5">{t("col.hotel")}</Th>
              <Th right>{t("col.organic")}</Th>
              <Th right>{t("col.best")}</Th>
              <Th right>{t("col.ads")}</Th>
              <Th>{t("col.badges")}</Th>
              <Th right className="pr-5">
                {t("col.scans")}
              </Th>
            </tr>
          </thead>
          <tbody>
            {hotels.map((h) => (
              <VisibilityRow key={h.hotel_id} h={h} />
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
