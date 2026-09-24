"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { InsightDetailOut, WatchItemOut } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { LEVEL_LABEL, LEVEL_TONE } from "@/lib/labels";
import { Badge, Card, cx } from "@/components/ui";

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

/** `evt:<id>` -> /events?highlight=; `metric:<hotel>:<date>` -> chi tiết ngày; `compset:<date>` -> tổng quan. */
export function evidenceHref(ref: string): string | null {
  const evt = /^evt:(\d+)$/.exec(ref);
  if (evt) return `/events?highlight=${evt[1]}`;
  const metric = /^metric:(\d+):(\d{4}-\d{2}-\d{2})$/.exec(ref);
  if (metric) return `/hotels/${metric[1]}/dates/${metric[2]}`;
  const compset = /^compset:(\d{4}-\d{2}-\d{2})$/.exec(ref);
  if (compset) return `/overview?start=${compset[1]}`;
  return null;
}

function evidenceLabel(e: Evidence): string {
  const evt = /^evt:(\d+)$/.exec(e.ref);
  if (evt) return `Sự kiện #${evt[1]}`;
  const metric = /^metric:(\d+):(\d{4}-\d{2}-\d{2})$/.exec(e.ref);
  if (metric) return `Chỉ số KS ${metric[1]} · ${fmtDate(metric[2])}`;
  const compset = /^compset:(\d{4}-\d{2}-\d{2})$/.exec(e.ref);
  if (compset) return `Compset ${fmtDate(compset[1])}`;
  return e.ref;
}

export function EvidenceChips({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) return null;
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1">
      {evidence.map((e, i) => {
        const href = evidenceHref(e.ref);
        const cls = "inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700 ring-1 ring-inset ring-slate-200";
        return (
          <li key={`${e.ref}-${i}`}>
            {href ? (
              <Link href={href} className={cx(cls, "hover:bg-sky-50 hover:text-sky-800 hover:ring-sky-200")} title={e.ref}>
                {evidenceLabel(e)}
              </Link>
            ) : (
              <span className={cls} title={e.ref}>
                {evidenceLabel(e)}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function DateSpan({ from, to }: { from: string; to: string }) {
  if (!from) return null;
  return <span className="text-xs text-slate-500">{from === to || !to ? fmtDate(from) : `${fmtDate(from)} – ${fmtDate(to)}`}</span>;
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <Card title={`${title} (${count})`}>
      {count === 0 ? <p className="text-sm text-slate-500">Không có.</p> : children}
    </Card>
  );
}

export function InsightView({ insight, hotels }: { insight: InsightDetailOut; hotels: WatchItemOut[] }) {
  const out = parseInsightOutput(insight.output_json);
  const dropped = parseDropped(insight.dropped_highlights);
  const hotelName = (id: number) => {
    const w = hotels.find((h) => h.hotel.id === id);
    return w ? w.label || w.hotel.name || w.hotel.booking_slug : `KS #${id}`;
  };

  if (!out) {
    return <Card>{insight.status === "failed" ? <p className="text-sm text-rose-700">Tạo bản tin thất bại: {insight.error ?? "không rõ lỗi"}</p> : <p className="text-sm text-slate-500">Chưa có nội dung.</p>}</Card>;
  }

  return (
    <div className="space-y-4">
      <Card title="Tóm tắt">
        <p className="whitespace-pre-line text-sm leading-relaxed text-slate-800">{out.summary || "—"}</p>
        {out.data_quality_note && (
          <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <span className="font-medium">Ghi chú chất lượng dữ liệu: </span>
            {out.data_quality_note}
          </p>
        )}
      </Card>

      <Section title="Điểm nổi bật" count={out.highlights.length}>
        <ol className="space-y-3">
          {out.highlights.map((h, i) => (
            <li key={i} className="rounded border border-line p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-medium text-slate-900">{h.title}</h3>
                <div className="flex items-center gap-2">
                  <DateSpan from={h.date_from} to={h.date_to} />
                  <Badge tone={LEVEL_TONE[h.confidence] ?? "gray"} title="Mức tin cậy">
                    Tin cậy: {LEVEL_LABEL[h.confidence] ?? h.confidence}
                  </Badge>
                </div>
              </div>
              {h.hotel_ids.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {h.hotel_ids.map((id) => (
                    <Link key={id} href={`/hotels/${id}`} className="text-xs text-sky-700 hover:underline">
                      {hotelName(id)}
                    </Link>
                  ))}
                </div>
              )}
              {h.recommendation && (
                <p className="mt-2 text-sm text-slate-800">
                  <span className="font-medium text-slate-600">Đề xuất: </span>
                  {h.recommendation}
                </p>
              )}
              <EvidenceChips evidence={h.evidence} />
            </li>
          ))}
        </ol>
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Tín hiệu nhu cầu" count={out.demand_signals.length}>
          <ul className="space-y-2">
            {out.demand_signals.map((s, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="w-24 shrink-0 tabular text-slate-600">{fmtDate(s.date)}</span>
                <Badge tone={LEVEL_TONE[s.level] ?? "gray"}>{LEVEL_LABEL[s.level] ?? s.level}</Badge>
                <span className="text-slate-800">{s.reason}</span>
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Cơ hội giá" count={out.pricing_opportunities.length}>
          <ul className="space-y-3">
            {out.pricing_opportunities.map((p, i) => (
              <li key={i} className="text-sm">
                <DateSpan from={p.date_from} to={p.date_to} />
                <p className="text-slate-800">{p.rationale}</p>
                <EvidenceChips evidence={p.evidence} />
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <Section title="Rủi ro" count={out.risks.length}>
        <ul className="space-y-3">
          {out.risks.map((r, i) => (
            <li key={i} className="text-sm">
              <h3 className="font-medium text-slate-900">{r.title}</h3>
              <p className="text-slate-800">{r.rationale}</p>
              <EvidenceChips evidence={r.evidence} />
            </li>
          ))}
        </ul>
      </Section>

      {dropped.length > 0 && (
        <details className="rounded-lg border border-line bg-surface shadow-xs">
          <summary className="cursor-pointer px-4 py-2.5 text-sm font-semibold text-slate-700">Bằng chứng bị loại ({dropped.length})</summary>
          <div className="border-t border-line p-4">
            <p className="mb-3 text-xs text-slate-500">Các mục AI đưa ra nhưng không có bằng chứng hợp lệ trong dữ liệu đầu vào nên đã bị loại khỏi bản tin.</p>
            <ul className="space-y-3">
              {dropped.map((d, i) => (
                <li key={i} className="rounded border border-dashed border-slate-300 p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="gray">{d.section}</Badge>
                    <span className="font-medium text-slate-800">{str(d.item.title) || str(d.item.rationale) || str(d.item.reason) || "(không có tiêu đề)"}</span>
                  </div>
                  {str(d.item.recommendation) && <p className="mt-1 text-slate-700">{str(d.item.recommendation)}</p>}
                  <ul className="mt-1 list-disc pl-5 text-xs text-rose-700">
                    {d.reasons.map((r, j) => (
                      <li key={j}>{r}</li>
                    ))}
                  </ul>
                  <EvidenceChips evidence={evidenceList(d.item.evidence)} />
                </li>
              ))}
            </ul>
          </div>
        </details>
      )}
    </div>
  );
}
