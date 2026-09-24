"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { EVENT_TYPES, EVENT_TYPE_LABEL } from "@/lib/labels";
import { Button, Card, ErrorBox, Field, Input, PageHeader, Select, Skeleton, cx } from "@/components/ui";
import { EventTable } from "@/components/event-table";

const PAGE_SIZE = 100;

type Filters = {
  hotelId: number | null;
  types: string[];
  stayFrom: string;
  stayTo: string;
  /** số giờ quan sát gần đây; 0 = tất cả */
  sinceHours: number;
};

const EMPTY: Filters = { hotelId: null, types: [], stayFrom: "", stayTo: "", sinceHours: 0 };

function sinceIso(hours: number): string | null {
  if (hours <= 0) return null;
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

function EventsView() {
  const params = useSearchParams();
  const rawHighlight = Number(params.get("highlight"));
  const highlightId = Number.isFinite(rawHighlight) && rawHighlight > 0 ? rawHighlight : null;

  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<{ f: Filters; since: string | null; offset: number }>({ f: EMPTY, since: null, offset: 0 });

  const watchlist = useApi("watchlist:all", () => api.watchlist.list(true));
  const key = JSON.stringify(applied);
  const events = useApi(key, () =>
    api.events({
      hotel_id: applied.f.hotelId,
      event_type: applied.f.types.length ? applied.f.types.join(",") : null,
      stay_from: applied.f.stayFrom || null,
      stay_to: applied.f.stayTo || null,
      observed_since: applied.since,
      limit: PAGE_SIZE,
      offset: applied.offset,
    }),
  );

  function apply(offset = 0) {
    setApplied({ f: draft, since: sinceIso(draft.sinceHours), offset });
  }
  function toggleType(t: string) {
    setDraft((d) => ({ ...d, types: d.types.includes(t) ? d.types.filter((x) => x !== t) : [...d.types, t] }));
  }

  const count = events.data?.length ?? 0;
  return (
    <>
      <PageHeader title="Sự kiện" subtitle="Biến động hết phòng, có phòng lại, số phòng và giá giữa các đợt quét" />
      <Card className="mb-4">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            apply(0);
          }}
        >
          <Field label="Khách sạn">
            <Select value={draft.hotelId ?? ""} onChange={(e) => setDraft({ ...draft, hotelId: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Tất cả</option>
              {(watchlist.data ?? []).map((w) => (
                <option key={w.hotel.id} value={w.hotel.id}>
                  {w.label || w.hotel.name || w.hotel.booking_slug}
                  {w.active ? "" : " (ngừng)"}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Lưu trú từ">
            <Input type="date" value={draft.stayFrom} onChange={(e) => setDraft({ ...draft, stayFrom: e.target.value })} />
          </Field>
          <Field label="Lưu trú đến">
            <Input type="date" value={draft.stayTo} onChange={(e) => setDraft({ ...draft, stayTo: e.target.value })} />
          </Field>
          <Field label="Quan sát trong">
            <Select value={draft.sinceHours} onChange={(e) => setDraft({ ...draft, sinceHours: Number(e.target.value) })}>
              <option value={0}>Tất cả</option>
              <option value={24}>24 giờ qua</option>
              <option value={72}>3 ngày qua</option>
              <option value={168}>7 ngày qua</option>
              <option value={720}>30 ngày qua</option>
            </Select>
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant="primary">
              Lọc
            </Button>
            <Button
              onClick={() => {
                setDraft(EMPTY);
                setApplied({ f: EMPTY, since: null, offset: 0 });
              }}
            >
              Xoá lọc
            </Button>
          </div>
          <div className="basis-full">
            <div className="mb-1 text-xs font-medium text-slate-600">Loại sự kiện</div>
            <div className="flex flex-wrap gap-1.5">
              {EVENT_TYPES.map((t) => {
                const on = draft.types.includes(t);
                return (
                  <button
                    key={t}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleType(t)}
                    className={cx("rounded-full px-2.5 py-0.5 text-xs ring-1 ring-inset", on ? "bg-sky-700 text-white ring-sky-700" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50")}
                  >
                    {EVENT_TYPE_LABEL[t]}
                  </button>
                );
              })}
            </div>
          </div>
        </form>
      </Card>
      <ErrorBox error={events.error} className="mb-4" />
      {highlightId && <p className="mb-2 text-xs text-slate-500">Đang đánh dấu sự kiện #{highlightId} (nếu nằm trong trang hiện tại).</p>}
      <Card padded={false} title={`Kết quả${events.data ? ` (${count}${count === PAGE_SIZE ? "+" : ""})` : ""}`} actions={
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <span>Trang {Math.floor(applied.offset / PAGE_SIZE) + 1}</span>
          <Button size="sm" disabled={applied.offset === 0} onClick={() => setApplied({ ...applied, offset: Math.max(0, applied.offset - PAGE_SIZE) })}>
            ← Trước
          </Button>
          <Button size="sm" disabled={count < PAGE_SIZE} onClick={() => setApplied({ ...applied, offset: applied.offset + PAGE_SIZE })}>
            Sau →
          </Button>
        </div>
      }>
        <div className={cx("transition-opacity", events.loading && events.data && "opacity-60")}>
          {events.data ? <EventTable events={events.data} highlightId={highlightId} /> : !events.error && <Skeleton rows={8} className="p-4" />}
        </div>
      </Card>
    </>
  );
}

export default function EventsPage() {
  return (
    <Suspense fallback={<Skeleton rows={8} />}>
      <EventsView />
    </Suspense>
  );
}
