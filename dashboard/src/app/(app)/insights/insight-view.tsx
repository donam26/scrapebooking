"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import type { ReactNode } from "react";
import type { EventOut, InsightDetailOut, WatchItemOut } from "@/lib/api";
import { useFmt, type Fmt } from "@/lib/format";
import { hotelTitle } from "@/lib/hotels";
import { LEVEL_TONE, useLabel, type LabelFn } from "@/lib/labels";
import { Badge, EmptyState, Note, cx } from "@/components/ui";
import { IconAlert, IconBoard, IconBuilding, IconCalendar, IconChevronRight, IconInfo, IconPulse, IconSparkle } from "@/components/icons";

// ---- Kiểu đầu ra AI (khớp backend/app/insight/schema.py) ----

export type Evidence = { kind: string; ref: string };
export type Highlight = {
  title: string;
  date_from: string;
  date_to: string;
  hotel_ids: number[];
  evidence: Evidence[];
  confidence: string;
  recommendation: string;
};
export type DemandSignal = { date: string; level: string; reason: string };
export type PricingOpportunity = { date_from: string; date_to: string; rationale: string; evidence: Evidence[] };
export type Risk = { title: string; rationale: string; evidence: Evidence[] };
export type InsightOutput = {
  summary: string;
  highlights: Highlight[];
  demand_signals: DemandSignal[];
  pricing_opportunities: PricingOpportunity[];
  risks: Risk[];
  data_quality_note: string;
};
export type Dropped = { section: string; item: Record<string, unknown>; reasons: string[] };

const str = (v: unknown): string => (typeof v === "string" ? v : v === null || v === undefined ? "" : String(v));
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" ? (v as Record<string, unknown>) : {});

function evidenceList(v: unknown): Evidence[] {
  return arr(v).map((e) => {
    const o = obj(e);
    return { kind: str(o.kind), ref: str(o.ref) };
  });
}

/** Chuẩn hoá `output_json` (object không kiểu từ API) về cấu trúc hiển thị, chịu được thiếu trường. */
export function parseInsightOutput(raw: Record<string, unknown> | null | undefined): InsightOutput | null {
  if (!raw) return null;
  return {
    summary: str(raw.summary),
    highlights: arr(raw.highlights).map((h) => {
      const o = obj(h);
      return {
        title: str(o.title),
        date_from: str(o.date_from),
        date_to: str(o.date_to),
        hotel_ids: arr(o.hotel_ids).map(Number).filter(Number.isFinite),
        evidence: evidenceList(o.evidence),
        confidence: str(o.confidence),
        recommendation: str(o.recommendation),
      };
    }),
    demand_signals: arr(raw.demand_signals).map((s) => {
      const o = obj(s);
      return { date: str(o.date), level: str(o.level), reason: str(o.reason) };
    }),
    pricing_opportunities: arr(raw.pricing_opportunities).map((p) => {
      const o = obj(p);
      return { date_from: str(o.date_from), date_to: str(o.date_to), rationale: str(o.rationale), evidence: evidenceList(o.evidence) };
    }),
    risks: arr(raw.risks).map((r) => {
      const o = obj(r);
      return { title: str(o.title), rationale: str(o.rationale), evidence: evidenceList(o.evidence) };
    }),
    data_quality_note: str(raw.data_quality_note),
  };
}

export function parseDropped(raw: Record<string, unknown>[]): Dropped[] {
  return raw.map((d) => ({ section: str(d.section), item: obj(d.item), reasons: arr(d.reasons).map(str) }));
}

/** `evt:<id>` -> /events?highlight=; `metric:<hotel>:<date>` -> chi tiết đêm; `compset:<date>` -> tổng quan. */
export function evidenceHref(ref: string): string | null {
  const evt = /^evt:(\d+)$/.exec(ref);
  if (evt) return `/events?highlight=${evt[1]}`;
  const metric = /^metric:(\d+):(\d{4}-\d{2}-\d{2})$/.exec(ref);
  if (metric) return `/hotels/${metric[1]}/dates/${metric[2]}`;
  const compset = /^compset:(\d{4}-\d{2}-\d{2})$/.exec(ref);
  if (compset) return `/availability?start=${compset[1]}`;
  return null;
}

type NameOf = (id: number) => string;
type EvidenceTranslator = ReturnType<typeof useTranslations<"insights.evidence">>;
/** Tra sự kiện theo id để bằng chứng đọc được: "Caravelle · Giảm phòng · đêm T7 26/09". */
export type EventOf = (id: number) => EventOut | undefined;

function evidenceLabel(
  e: Evidence,
  nameOf: NameOf,
  eventOf: EventOf | undefined,
  t: EvidenceTranslator,
  label: LabelFn,
  fmtNight: Fmt["fmtNight"],
): { icon: ReactNode; text: string } {
  const evt = /^evt:(\d+)$/.exec(e.ref);
  if (evt) {
    const ev = eventOf?.(Number(evt[1]));
    return {
      icon: <IconPulse size={13} />,
      text: ev
        ? t("event", { hotel: nameOf(ev.hotel_id), type: label("eventType", ev.event_type).toLowerCase(), night: fmtNight(ev.stay_date) })
        : t("eventFallback", { id: evt[1] }),
    };
  }
  const metric = /^metric:(\d+):(\d{4}-\d{2}-\d{2})$/.exec(e.ref);
  if (metric) return { icon: <IconBuilding size={13} />, text: t("metric", { hotel: nameOf(Number(metric[1])), night: fmtNight(metric[2]) }) };
  const compset = /^compset:(\d{4}-\d{2}-\d{2})$/.exec(e.ref);
  if (compset) return { icon: <IconBoard size={13} />, text: t("compset", { night: fmtNight(compset[1]) }) };
  // Tín hiệu cầu Booking.com hiển thị ("đặt 13 lần trong 24 giờ"): thông điệp marketing, không có trang riêng.
  if (/^demand:\d+$/.test(e.ref)) return { icon: <IconInfo size={13} />, text: t("demand") };
  return { icon: <IconInfo size={13} />, text: e.ref };
}

export function EvidenceChips({ evidence, nameOf, eventOf, label = true }: { evidence: Evidence[]; nameOf: NameOf; eventOf?: EventOf; label?: boolean }) {
  const t = useTranslations("insights.evidence");
  const labelOf = useLabel();
  const { fmtNight } = useFmt();
  if (evidence.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      {label && <span className="mr-0.5 text-xs font-semibold text-muted">{t("label")}</span>}
      {evidence.map((e, i) => {
        const href = evidenceHref(e.ref);
        const { icon, text } = evidenceLabel(e, nameOf, eventOf, t, labelOf, fmtNight);
        const cls = "inline-flex h-7 items-center gap-1.5 rounded-lg bg-surface px-2 text-xs font-medium text-body ring-1 ring-inset ring-line tabular";
        return href ? (
          <Link key={`${e.ref}-${i}`} href={href} className={cx(cls, "transition-colors hover:bg-brand-softer hover:text-brand-hover hover:ring-brand-soft")} title={e.ref}>
            <span className="text-muted">{icon}</span>
            {text}
          </Link>
        ) : (
          <span key={`${e.ref}-${i}`} className={cls} title={e.ref}>
            <span className="text-muted">{icon}</span>
            {text}
          </span>
        );
      })}
    </div>
  );
}

function DateSpan({ from, to }: { from: string; to: string }) {
  const t = useTranslations("insights.view");
  const { fmtNight } = useFmt();
  if (!from) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-muted tabular">
      <IconCalendar size={14} />
      {from === to || !to ? t("night", { night: fmtNight(from) }) : `${fmtNight(from)} – ${fmtNight(to)}`}
    </span>
  );
}

function Section({ id, title, count, children, empty }: { id: string; title: string; count: number; children: ReactNode; empty: string }) {
  return (
    <section id={id} className="scroll-mt-20">
      <h2 className="mb-3 flex items-baseline gap-2 text-lg font-bold text-ink">
        {title}
        <span className="text-base font-semibold text-muted tabular">{count}</span>
      </h2>
      {count === 0 ? <p className="rounded-lg bg-subtle px-4 py-3 text-base text-muted">{empty}</p> : children}
    </section>
  );
}

export function insightCounts(out: InsightOutput | null) {
  return {
    highlights: out?.highlights.length ?? 0,
    signals: out?.demand_signals.length ?? 0,
    pricing: out?.pricing_opportunities.length ?? 0,
    risks: out?.risks.length ?? 0,
  };
}

/** `unknown`: tên hiển thị cho khách sạn không còn trong watchlist. */
export function hotelNames(hotels: WatchItemOut[], unknown: NameOf): { nameOf: NameOf; isSelf: (id: number) => boolean } {
  return {
    nameOf: (id: number) => {
      const w = hotels.find((h) => h.hotel.id === id);
      return w ? hotelTitle(w.hotel, w.label) : unknown(id);
    },
    isSelf: (id: number) => hotels.some((h) => h.hotel.id === id && h.role === "self"),
  };
}

/** Nội dung đọc của một bản tin: tóm tắt, điểm nổi bật, tín hiệu, cơ hội giá, rủi ro, mục bị loại. */
export function InsightView({ insight, hotels, eventOf }: { insight: InsightDetailOut; hotels: WatchItemOut[]; eventOf?: EventOf }) {
  const t = useTranslations("insights.view");
  const tSection = useTranslations("insights.sections");
  const tLevel = useTranslations("insights.level");
  const tField = useTranslations("insights.fieldWords");
  const locale = useLocale();
  const label = useLabel();
  const { fmtNight } = useFmt();
  const out = parseInsightOutput(insight.output_json);
  const dropped = parseDropped(insight.dropped_highlights);
  const { nameOf, isSelf } = hotelNames(hotels, (id) => t("unknownHotel", { id }));

  if (!out) {
    return insight.status === "failed" ? (
      <Note tone="warn" icon={<IconAlert size={16} />}>
        {t("failed", { error: insight.error ?? t("unknownError") })}
      </Note>
    ) : (
      <EmptyState icon={<IconSparkle />} title={t("waitingTitle")}>
        {t("waitingBody")}
      </EmptyState>
    );
  }

  return (
    <div className="space-y-10">
      <section id="tom-tat" className="scroll-mt-20">
        <p className="max-w-[70ch] whitespace-pre-line text-lg leading-[1.7] text-ink">{out.summary || "—"}</p>
      </section>

      <Section id="noi-bat" title={tSection("highlights")} count={out.highlights.length} empty={t("highlightsEmpty")}>
        <div className="space-y-3">
          {out.highlights.map((h, i) => (
            <article key={i} className="rounded-xl border border-line bg-surface p-5 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                <h3 className="max-w-[60ch] text-md font-bold leading-snug text-ink">{h.title}</h3>
                {h.confidence && (
                  <Badge tone={LEVEL_TONE[h.confidence] ?? "gray"} title={t("confidenceHint")}>
                    {tLevel("confidence", { level: h.confidence, label: label("level", h.confidence).toLowerCase() })}
                  </Badge>
                )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
                <DateSpan from={h.date_from} to={h.date_to} />
                {h.hotel_ids.length > 0 && (
                  <span className="flex flex-wrap items-center gap-1">
                    {h.hotel_ids.map((id) => (
                      <Link
                        key={id}
                        href={`/hotels/${id}`}
                        className={cx(
                          "rounded-md px-1.5 py-0.5 text-sm font-semibold hover:underline",
                          isSelf(id) ? "bg-yours-soft text-yours-deep" : "bg-sunken text-body hover:text-brand",
                        )}
                      >
                        {nameOf(id)}
                      </Link>
                    ))}
                  </span>
                )}
              </div>
              {h.recommendation && (
                <div className="mt-3.5 rounded-lg bg-brand-softer px-4 py-3">
                  <div className="text-xs font-semibold text-brand-hover">{t("recommendation")}</div>
                  <p className="mt-0.5 max-w-[72ch] text-base text-ink">{h.recommendation}</p>
                </div>
              )}
              <EvidenceChips evidence={h.evidence} nameOf={nameOf} eventOf={eventOf} />
            </article>
          ))}
        </div>
      </Section>

      <Section id="nhu-cau" title={tSection("demandSignals")} count={out.demand_signals.length} empty={t("demandEmpty")}>
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface shadow-card">
          {out.demand_signals.map((s, i) => (
            <li key={i} className="grid gap-x-4 gap-y-1 px-5 py-3 sm:grid-cols-[124px_160px_minmax(0,1fr)] sm:items-baseline">
              <span className="font-semibold text-ink tabular">{s.date ? t("night", { night: fmtNight(s.date) }) : "—"}</span>
              <span>
                <Badge tone={LEVEL_TONE[s.level] ?? "gray"}>{tLevel("demand", { level: s.level, label: label("level", s.level).toLowerCase() })}</Badge>
              </span>
              <span className="text-base text-body">{s.reason}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="co-hoi-gia" title={tSection("pricing")} count={out.pricing_opportunities.length} empty={t("pricingEmpty")}>
        <div className="space-y-3">
          {out.pricing_opportunities.map((p, i) => (
            <article key={i} className="rounded-xl border border-line bg-surface p-5 shadow-card">
              <DateSpan from={p.date_from} to={p.date_to} />
              <p className="mt-1.5 max-w-[72ch] text-base text-ink">{p.rationale}</p>
              <EvidenceChips evidence={p.evidence} nameOf={nameOf} eventOf={eventOf} />
            </article>
          ))}
        </div>
      </Section>

      <Section id="rui-ro" title={tSection("risks")} count={out.risks.length} empty={t("risksEmpty")}>
        <div className="space-y-3">
          {out.risks.map((r, i) => (
            <article key={i} className="rounded-xl border border-line bg-surface p-5 shadow-card">
              <h3 className="flex items-start gap-2 text-md font-bold text-ink">
                <IconAlert size={17} className="mt-0.5 shrink-0 text-warning-deep" />
                {r.title}
              </h3>
              <p className="mt-1.5 max-w-[72ch] text-base text-body">{r.rationale}</p>
              <EvidenceChips evidence={r.evidence} nameOf={nameOf} eventOf={eventOf} />
            </article>
          ))}
        </div>
      </Section>

      {out.data_quality_note && (
        <details id="du-lieu" className="group scroll-mt-20 rounded-xl border border-line bg-surface">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3.5 [&::-webkit-details-marker]:hidden">
            <span className="flex items-center gap-2">
              <IconInfo size={16} className="text-muted" />
              <span className="text-md font-bold text-ink">{tSection("dataQuality")}</span>
              <span className="text-sm text-muted">{t("dataQualityHint")}</span>
            </span>
            <IconChevronRight size={16} className="shrink-0 text-muted transition-transform group-open:rotate-90" />
          </summary>
          <p className="max-w-[80ch] border-t border-line px-5 py-4 text-base text-body">{plainNote(out.data_quality_note, tField, locale)}</p>
        </details>
      )}

      {dropped.length > 0 && (
        <details id="bi-loai" className="group scroll-mt-20 rounded-xl border border-dashed border-line-strong bg-subtle">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3.5 [&::-webkit-details-marker]:hidden">
            <span>
              <span className="text-md font-bold text-ink">{tSection("dropped")}</span>
              <span className="ml-2 text-base font-semibold text-muted tabular">{dropped.length}</span>
              <span className="mt-0.5 block text-sm text-muted">{t("droppedHint")}</span>
            </span>
            <IconChevronRight size={16} className="shrink-0 text-muted transition-transform group-open:rotate-90" />
          </summary>
          <ul className="space-y-3 border-t border-line px-5 py-4">
            {dropped.map((d, i) => (
              <li key={i} className="rounded-lg bg-surface p-4 ring-1 ring-line">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="gray" dot={false}>
                    {Object.hasOwn(SECTION_KEY, d.section) ? tSection(SECTION_KEY[d.section]) : d.section}
                  </Badge>
                  <span className="font-semibold text-ink">{str(d.item.title) || str(d.item.rationale) || str(d.item.reason) || t("untitled")}</span>
                </div>
                {str(d.item.recommendation) && <p className="mt-1.5 text-base text-body">{str(d.item.recommendation)}</p>}
                <ul className="mt-2 space-y-0.5 text-sm text-danger-deep">
                  {d.reasons.map((r, j) => (
                    <li key={j} className="flex gap-1.5">
                      <IconAlert size={14} className="mt-0.5 shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
                <EvidenceChips evidence={evidenceList(d.item.evidence)} nameOf={nameOf} eventOf={eventOf} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

type FieldWordsTranslator = ReturnType<typeof useTranslations<"insights.fieldWords">>;
type FieldWordKey = Parameters<FieldWordsTranslator>[0];

/** Ghi chú dữ liệu do AI viết đôi khi lộ tên trường; đổi sang lời thường trước khi hiện. */
const FIELD_WORDS: Array<[RegExp, FieldWordKey]> = [
  [/\bexact_share_7d\b/g, "exactShare7d"],
  [/\bexact_share\b/g, "exactShare"],
  [/\bexact_rooms_left\b/g, "exactRoomsLeft"],
  [/\bprice_index\b/g, "priceIndex"],
  [/\bpickup_24h\b/g, "pickup24h"],
  [/\bvelocity_3d\b/g, "velocity3d"],
  [/\bown_occupancy_pct\b|\boccupancy_pct\b/g, "occupancy"],
  [/\bsold_out\b/g, "soldOut"],
  [/\bunknown\b/g, "unknown"],
  [/\bcapped\b/g, "capped"],
  [/\bhidden\b/g, "hidden"],
  [/\bexact\b/g, "exact"],
  [/\bcompset\b/gi, "compset"],
];

/** Ghi chú viết theo ngôn ngữ báo cáo của tenant; có dấu tiếng Việt thì coi là tiếng Việt. */
const VI_CHARS = /[ăâđêôơưạảãầấậẩẫằắặẳẵẹẻẽềếệểễịỉĩọỏõồốộổỗờớợởỡụủũừứựửữỳỵỷỹ]/i;

export function plainNote(text: string, t: FieldWordsTranslator, uiLocale: string): string {
  let out = text;
  // Lời thay thế theo ngôn ngữ giao diện: chỉ thay khi ghi chú cùng ngôn ngữ, tránh câu lẫn hai thứ tiếng.
  const noteLocale = VI_CHARS.test(text) ? "vi" : "en";
  if (noteLocale === uiLocale) for (const [re, key] of FIELD_WORDS) out = out.replace(re, t(key));
  // Tên trường còn sót (snake_case) -> tách thành chữ.
  return out.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (m) => m.replace(/_/g, " "));
}

/** Mục của bản tin -> khoá trong insights.sections. */
const SECTION_KEY: Record<string, "highlights" | "demandSignals" | "pricing" | "risks"> = {
  highlights: "highlights",
  demand_signals: "demandSignals",
  pricing_opportunities: "pricing",
  risks: "risks",
};

