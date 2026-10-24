"use client";

import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import type { HotelEventsSummaryOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { Card, ErrorBox, Skeleton, cx } from "./ui";
import { IconPulse } from "./icons";

/**
 * Tóm tắt thay đổi của một khách sạn trong N ngày (`GET /events/summary`), đếm theo đêm:
 * "Giá ↑ 3 đêm (tới +12%) · hết phòng 31/10, 01/11 · bật KM 2 đêm".
 * - `ChangeSummaryLine`: một dòng (thẻ đối thủ, Hôm nay gom theo khách sạn với days=1).
 * - `ChangeSummaryCard`: thẻ ≤6 dòng ở đầu trang một khách sạn.
 * Cửa sổ không có lượt quét nào thì nói "Chưa có lượt quét mới", không nói "Không đổi gì".
 */

/** Số đêm hết phòng liệt kê bằng ngày, còn lại gộp "+N đêm". */
const SOLD_OUT_LISTED = 3;

type ItemKey = "priceUp" | "priceDown" | "soldOut" | "roomsDrop" | "promo" | "restrictions";
type Item = { key: ItemKey; label: string; value: string; short: string[]; tone: "warn" | "neutral" | "promo" };

export type ChangeSummaryState =
  | { kind: "noScans"; last: string | null }
  | { kind: "none" }
  | { kind: "minor" }
  | { kind: "changes"; items: Item[] };

function useChangeSummaryState() {
  const t = useTranslations("components.changeSummary");
  const { fmtDateShort, fmtPct } = useFmt();
  return (s: HotelEventsSummaryOut): ChangeSummaryState => {
    if (!s.last_observed_at || s.last_observed_at < s.window_from) return { kind: "noScans", last: s.last_observed_at };
    const items: Item[] = [];
    const pct = (v: string | null) => {
      const n = num(v);
      return n === null ? null : fmtPct(n, { signed: true, digits: 0 });
    };
    for (const key of ["priceUp", "priceDown"] as const) {
      const m = key === "priceUp" ? s.price_up : s.price_down;
      if (m.nights <= 0) continue;
      const p = pct(m.max_pct);
      items.push({
        key,
        label: t(`label.${key}`),
        value: p ? t("value.price", { count: m.nights, pct: p }) : t("value.nights", { count: m.nights }),
        short: [p ? t(`short.${key}Pct`, { count: m.nights, pct: p }) : t(`short.${key}`, { count: m.nights })],
        tone: "neutral",
      });
    }
    if (s.sold_out_total > 0 || s.back_available_nights > 0) {
      const listed = s.sold_out_nights.slice(0, SOLD_OUT_LISTED).map(fmtDateShort).join(", ");
      const rest = s.sold_out_total - Math.min(s.sold_out_nights.length, SOLD_OUT_LISTED);
      const sold =
        s.sold_out_total === 0
          ? null
          : listed
            ? rest > 0
              ? t("value.soldOutMore", { nights: listed, count: rest })
              : listed
            : t("value.nights", { count: s.sold_out_total });
      const back = s.back_available_nights > 0 ? t("short.back", { count: s.back_available_nights }) : null;
      items.push({
        key: "soldOut",
        label: t("label.soldOut"),
        value: [sold, back].filter(Boolean).join(" · "),
        short: [sold ? t("short.soldOut", { nights: sold }) : null, back].filter((x): x is string => !!x),
        tone: "warn",
      });
    }
    if (s.rooms_drop_nights > 0) {
      items.push({ key: "roomsDrop", label: t("label.roomsDrop"), value: t("value.nights", { count: s.rooms_drop_nights }), short: [t("short.roomsDrop", { count: s.rooms_drop_nights })], tone: "neutral" });
    }
    if (s.promo_on > 0 || s.promo_off > 0) {
      const parts = [s.promo_on > 0 ? t("short.promoOn", { count: s.promo_on }) : null, s.promo_off > 0 ? t("short.promoOff", { count: s.promo_off }) : null].filter((x): x is string => !!x);
      items.push({ key: "promo", label: t("label.promo"), value: parts.join(" · "), short: parts, tone: "promo" });
    }
    if (s.restriction_changes > 0) {
      items.push({ key: "restrictions", label: t("label.restrictions"), value: t("value.restrictions", { count: s.restriction_changes }), short: [t("short.restrictions", { count: s.restriction_changes })], tone: "neutral" });
    }
    if (items.length > 0) return { kind: "changes", items };
    return s.total_events > 0 ? { kind: "minor" } : { kind: "none" };
  };
}

/** Câu trạng thái khi không có gì để liệt kê ("Không đổi gì trong 7 ngày"…). */
function useQuietText() {
  const t = useTranslations("components.changeSummary");
  const { fmtWhen } = useFmt();
  return (st: ChangeSummaryState, days: number, staleSince: string | null): string | null => {
    const until = staleSince ? ` · ${t("untilLast", { when: fmtWhen(staleSince) })}` : "";
    if (st.kind === "noScans") return st.last ? `${t("noScans", { days })} · ${t("lastScan", { when: fmtWhen(st.last) })}` : t("noScans", { days });
    if (st.kind === "none") return `${t("none", { days })}${until}`;
    if (st.kind === "minor") return `${t("minorOnly", { days })}${until}`;
    return null;
  };
}

function capitalize(s: string, locale: string): string {
  return s ? s.charAt(0).toLocaleUpperCase(locale) + s.slice(1) : s;
}

/**
 * Một dòng: "7 ngày qua: Giá ↑ 3 đêm (tới +12%) · hết phòng 31/10, 01/11 · bật KM 2 đêm".
 * `label={null}` bỏ tiền tố "7 ngày qua:". `stale` (dữ liệu dừng): thêm "tới lần quét cuối …".
 */
export function ChangeSummaryLine({
  summary,
  days = 7,
  stale = false,
  label,
  className,
}: {
  summary: HotelEventsSummaryOut | null | undefined;
  days?: number;
  stale?: boolean;
  label?: ReactNode;
  className?: string;
}) {
  const t = useTranslations("components.changeSummary");
  const locale = useLocale();
  const { fmtWhen } = useFmt();
  const stateOf = useChangeSummaryState();
  const quiet = useQuietText();
  if (!summary) return null;
  const st = stateOf(summary);
  const staleSince = stale ? summary.last_observed_at : null;
  const prefix = label === undefined ? t("window", { days }) : label;
  const text = st.kind === "changes" ? capitalize(st.items.flatMap((i) => i.short).join(" · "), locale) : quiet(st, days, staleSince);
  return (
    <p className={cx("text-sm", st.kind === "changes" ? "text-body" : "text-muted", className)}>
      {prefix !== null && <span className="font-semibold text-ink">{prefix}: </span>}
      {text}
      {st.kind === "changes" && staleSince && <span className="text-muted"> · {t("untilLast", { when: fmtWhen(staleSince) })}</span>}
    </p>
  );
}

const TONE_DOT: Record<Item["tone"], string> = {
  warn: "bg-warning-deep",
  promo: "bg-[#db2777]",
  neutral: "bg-line-strong",
};

/** Thẻ "7 ngày qua" (≤6 dòng) ở đầu trang một khách sạn. */
export function ChangeSummaryCard({
  summary,
  days = 7,
  stale = false,
  error,
  loading,
  className,
}: {
  summary: HotelEventsSummaryOut | null | undefined;
  days?: number;
  stale?: boolean;
  error?: unknown;
  loading?: boolean;
  className?: string;
}) {
  const t = useTranslations("components.changeSummary");
  const { fmtWhen } = useFmt();
  const stateOf = useChangeSummaryState();
  const quiet = useQuietText();
  const st = summary ? stateOf(summary) : null;
  const staleSince = stale && summary ? summary.last_observed_at : null;
  return (
    <Card title={t("window", { days })} info={t("cardDescription")} icon={<IconPulse size={15} />} className={className}>
      <ErrorBox error={error} />
      {!summary && !error && loading !== false && <Skeleton rows={3} />}
      {summary && st && st.kind !== "changes" && <p className="text-sm text-muted">{quiet(st, days, staleSince)}</p>}
      {st?.kind === "changes" && (
        <>
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_minmax(0,1fr)]">
            {st.items.map((i) => (
              <div key={i.key} className="contents">
                <dt className="flex items-center gap-2 font-semibold text-ink" title={i.key === "roomsDrop" ? t("roomsDropTitle") : undefined}>
                  <span aria-hidden className={cx("h-2 w-2 shrink-0 rounded-full", TONE_DOT[i.tone])} />
                  {i.label}
                </dt>
                <dd className="text-body tabular max-sm:mb-1 max-sm:pl-4">{i.value}</dd>
              </div>
            ))}
          </dl>
          {staleSince && <p className="mt-3 text-xs text-muted">{t("untilLast", { when: fmtWhen(staleSince) })}</p>}
        </>
      )}
    </Card>
  );
}
