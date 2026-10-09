"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { api, apiUrl } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { EVENT_TYPES, EVENT_TYPE_GROUPS, EVENT_TYPE_TONE, useLabel, type Tone } from "@/lib/labels";
import { hotelTitle } from "@/lib/hotels";
import { Button, ButtonLink, Card, ErrorBox, Note, PageHeader, Segmented, Select, SkeletonBlock, cx } from "@/components/ui";
import { BRIEF_TABS, SubTabs } from "@/components/sub-tabs";
import { EventTable } from "@/components/event-table";
import { IconChevronLeft, IconChevronRight, IconClose, IconDownload, IconInfo } from "@/components/icons";

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

/** `key`: khoá trong events.since. */
const SINCE_OPTIONS: { value: number; key: "h24" | "d3" | "d7" | "d30" | "all" }[] = [
  { value: 24, key: "h24" },
  { value: 72, key: "d3" },
  { value: 168, key: "d7" },
  { value: 720, key: "d30" },
  { value: 0, key: "all" },
];

function sinceIso(hours: number): string | null {
  if (hours <= 0) return null;
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Bộ lọc nằm trong URL (?hotel=&types=&from=&to=&since=&page=) để chia sẻ và tải lại được. */
function filtersFromParams(params: URLSearchParams): { f: Filters; offset: number } {
  const hotel = Number(params.get("hotel"));
  const since = Number(params.get("since"));
  const page = Number(params.get("page"));
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  return {
    f: {
      hotelId: Number.isInteger(hotel) && hotel > 0 ? hotel : null,
      types: (params.get("types") ?? "").split(",").filter((t) => (EVENT_TYPES as readonly string[]).includes(t)),
      stayFrom: DATE_RE.test(from) ? from : "",
      stayTo: DATE_RE.test(to) ? to : "",
      sinceHours: Number.isFinite(since) && since > 0 ? since : 0,
    },
    offset: Number.isInteger(page) && page > 1 ? (page - 1) * PAGE_SIZE : 0,
  };
}

function filtersToQuery(f: Filters, offset: number, highlight: number | null): string {
  const q = new URLSearchParams();
  if (f.hotelId !== null) q.set("hotel", String(f.hotelId));
  if (f.types.length) q.set("types", f.types.join(","));
  if (f.stayFrom) q.set("from", f.stayFrom);
  if (f.stayTo) q.set("to", f.stayTo);
  if (f.sinceHours > 0) q.set("since", String(f.sinceHours));
  if (offset > 0) q.set("page", String(offset / PAGE_SIZE + 1));
  if (highlight !== null) q.set("highlight", String(highlight));
  const s = q.toString();
  return s ? `?${s}` : "";
}

const DOT: Record<Tone, string> = {
  green: "bg-yours",
  red: "bg-danger",
  amber: "bg-[#e0a100]",
  gray: "bg-faint",
  blue: "bg-brand",
  purple: "bg-brand",
  plum: "bg-plum",
};

const DATE_INPUT =
  "h-9 w-[150px] rounded-lg border border-line-strong bg-surface px-2.5 text-base text-ink tabular hover:border-[#b7bfcc] focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15";

function EventsView() {
  const t = useTranslations("events");
  const label = useLabel();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const rawHighlight = Number(params.get("highlight"));
  const highlightId = Number.isFinite(rawHighlight) && rawHighlight > 0 ? rawHighlight : null;

  // URL là nguồn duy nhất của bộ lọc: đổi là áp dụng ngay, tải lại và chia sẻ link đều nhất quán.
  const paramsKey = params.toString();
  const applied = useMemo(() => filtersFromParams(new URLSearchParams(paramsKey)), [paramsKey]);
  const f = applied.f;

  const watchlist = useApi("watchlist:all", () => api.watchlist.list(true));
  const key = JSON.stringify(applied);
  const events = useApi(key, () =>
    api.events({
      hotel_id: f.hotelId,
      event_type: f.types.length ? f.types.join(",") : null,
      stay_from: f.stayFrom || null,
      stay_to: f.stayTo || null,
      observed_since: sinceIso(f.sinceHours),
      limit: PAGE_SIZE,
      offset: applied.offset,
    }),
  );

  /** Đổi bộ lọc/trang: ghi vào URL (bỏ `highlight` vì người dùng đã chuyển sang xem khác). */
  function go(next: Partial<Filters>, offset = 0) {
    router.replace(`${pathname}${filtersToQuery({ ...f, ...next }, offset, null)}`, { scroll: false });
  }
  function toggleType(type: string) {
    go({ types: f.types.includes(type) ? f.types.filter((x) => x !== type) : [...f.types, type] });
  }

  const active = f.hotelId !== null || f.types.length > 0 || !!f.stayFrom || !!f.stayTo || f.sinceHours > 0;
  const count = events.data?.length ?? 0;
  const page = Math.floor(applied.offset / PAGE_SIZE) + 1;

  return (
    <>
      <SubTabs items={BRIEF_TABS} />
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
        actions={
          <ButtonLink
            href={apiUrl("/export/events.csv", {
              hotel_id: f.hotelId,
              event_type: f.types.length ? f.types.join(",") : null,
              stay_from: f.stayFrom || null,
              stay_to: f.stayTo || null,
              observed_since: sinceIso(f.sinceHours),
            })}
            download
            icon={<IconDownload size={16} />}
          >
            {t("downloadCsv")}
          </ButtonLink>
        }
      />

      <div className="mb-4 space-y-3">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">{t("filters.hotel")}</span>
            <Select className="w-[220px]" value={f.hotelId ?? ""} onChange={(e) => go({ hotelId: e.target.value ? Number(e.target.value) : null })}>
              <option value="">{t("filters.allHotels")}</option>
              {(watchlist.data ?? []).map((w) => (
                <option key={w.hotel.id} value={w.hotel.id}>
                  {hotelTitle(w.hotel, w.label)}
                  {w.role === "self" ? ` ${t("filters.yours")}` : ""}
                  {w.active ? "" : ` ${t("filters.inactive")}`}
                </option>
              ))}
            </Select>
          </label>
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">{t("filters.observedWithin")}</span>
            <Segmented
              label={t("filters.observedWithin")}
              value={f.sinceHours}
              onChange={(v) => go({ sinceHours: v })}
              items={SINCE_OPTIONS.map((o) => ({ value: o.value, label: t(`since.${o.key}`) }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">{t("filters.stayNight")}</span>
            <div className="flex items-center gap-2">
              <input type="date" aria-label={t("filters.stayFrom")} className={DATE_INPUT} value={f.stayFrom} onChange={(e) => go({ stayFrom: e.target.value })} />
              <span className="text-muted">–</span>
              <input type="date" aria-label={t("filters.stayTo")} className={DATE_INPUT} value={f.stayTo} min={f.stayFrom || undefined} onChange={(e) => go({ stayTo: e.target.value })} />
            </div>
          </div>
          {active && (
            <Button variant="quiet" icon={<IconClose size={15} />} onClick={() => go(EMPTY)}>
              {t("filters.clear")}
            </Button>
          )}
        </div>

        <div role="group" aria-label={t("filters.eventType")} className="space-y-1.5">
          {EVENT_TYPE_GROUPS.map((g, gi) => (
            <div key={g.key} className="flex flex-wrap items-center gap-1.5">
              <span className={cx("mr-1 min-w-[118px] shrink-0 text-sm font-semibold", gi === 0 ? "text-body" : "text-muted")}>
                {gi === 0 ? `${t("filters.type")} · ` : ""}
                {t(`filters.group.${g.key}`)}
              </span>
              {g.types.map((type) => {
                const on = f.types.includes(type);
                return (
                  <button
                    key={type}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleType(type)}
                    className={cx(
                      "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm font-semibold transition-colors duration-150",
                      on ? "bg-night text-white" : "bg-surface text-body ring-1 ring-inset ring-line-strong hover:bg-subtle hover:ring-[#b7bfcc]",
                    )}
                  >
                    <span aria-hidden className={cx("h-2 w-2 rounded-full", DOT[EVENT_TYPE_TONE[type] ?? "gray"], on && "ring-2 ring-white/40")} />
                    {label("eventType", type)}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {highlightId && (
        <Note tone="info" icon={<IconInfo size={16} />} className="mb-4">
          {t("highlight.text", { id: highlightId })}{" "}
          <Link href={pathname + filtersToQuery(f, applied.offset, null)} className="font-semibold text-brand hover:underline">
            {t("highlight.clear")}
          </Link>
        </Note>
      )}
      <ErrorBox error={events.error} className="mb-4" />

      <Card
        padded={false}
        title={events.data ? (count === PAGE_SIZE ? t("list.countMore", { count }) : t("list.count", { count })) : t("title")}
        description={active ? t("list.filtered") : t("list.newestFirst")}
        actions={
          (applied.offset > 0 || count === PAGE_SIZE) && (
            <div className="flex items-center gap-1.5 text-sm text-muted">
              <Button size="sm" variant="ghost" icon={<IconChevronLeft size={15} />} disabled={applied.offset === 0} onClick={() => go({}, Math.max(0, applied.offset - PAGE_SIZE))}>
                {t("list.prev")}
              </Button>
              <span className="tabular">{t("list.page", { page })}</span>
              <Button size="sm" variant="ghost" disabled={count < PAGE_SIZE} onClick={() => go({}, applied.offset + PAGE_SIZE)}>
                {t("list.next")} <IconChevronRight size={15} />
              </Button>
            </div>
          )
        }
      >
        <div className={cx("transition-opacity duration-200", events.loading && events.data && "opacity-60")}>
          {events.data ? (
            <EventTable
              events={events.data}
              highlightId={highlightId}
              labelOf={(id) => watchlist.data?.find((w) => w.hotel.id === id)?.label ?? undefined}
              emptyText={active ? t("list.emptyFiltered") : t("list.empty")}
            />
          ) : (
            !events.error && (
              <div className="space-y-2 p-5">
                {Array.from({ length: 8 }, (_, i) => (
                  <SkeletonBlock key={i} className="h-9 w-full" />
                ))}
              </div>
            )
          )}
        </div>
      </Card>
    </>
  );
}

export default function EventsPage() {
  return (
    <Suspense fallback={null}>
      <EventsView />
    </Suspense>
  );
}
