"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { api, apiUrl, type EventOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { useDataFreshness } from "@/lib/freshness";
import { useApi } from "@/lib/hooks";
import { EVENT_TYPES, EVENT_TYPE_TONE, useLabel, type EventType, type Tone } from "@/lib/labels";
import { hotelTitle } from "@/lib/hotels";
import { Button, ButtonLink, Card, ErrorBox, Note, PageHeader, Segmented, Select, SkeletonBlock, Switch, cx } from "@/components/ui";
import { DataUpdated } from "@/components/freshness";
import { REPORT_TABS, SubTabs } from "@/components/sub-tabs";
import { EventTable } from "@/components/event-table";
import { IconChevronDown, IconChevronLeft, IconChevronRight, IconClose, IconDownload, IconInfo } from "@/components/icons";

const PAGE_SIZE = 100;
/** Kỳ quan sát mặc định: 7 ngày (D6). */
const DEFAULT_SINCE = 168;

type Filters = {
  hotelId: number | null;
  types: string[];
  stayFrom: string;
  stayTo: string;
  /** số giờ quan sát gần đây; 0 = tất cả */
  sinceHours: number;
  /** Hiện cả thay đổi ±1 phòng (mặc định ẩn). */
  small: boolean;
};

const EMPTY: Filters = { hotelId: null, types: [], stayFrom: "", stayTo: "", sinceHours: DEFAULT_SINCE, small: false };

/** `key`: khoá trong events.since. */
const SINCE_OPTIONS: { value: number; key: "h24" | "d3" | "d7" | "d30" | "all" }[] = [
  { value: 24, key: "h24" },
  { value: 72, key: "d3" },
  { value: 168, key: "d7" },
  { value: 720, key: "d30" },
  { value: 0, key: "all" },
];

/** Bốn nhóm lọc nhanh (khoá: events.filters.group.<key>); "Thêm lọc" mở từng loại. */
const GROUPS: ReadonlyArray<{ key: "rooms" | "price" | "restrictions" | "promos"; types: readonly EventType[] }> = [
  { key: "rooms", types: ["sold_out", "restock", "rooms_decrease", "rooms_increase", "low_stock_enter", "room_type_new", "room_type_gone"] },
  { key: "price", types: ["price_up", "price_down", "lowest_rate_shift"] },
  { key: "restrictions", types: ["restricted", "restriction_lifted", "min_stay_change"] },
  { key: "promos", types: ["promo_start", "promo_end"] },
];

function sinceIso(hours: number): string | null {
  if (hours <= 0) return null;
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

/**
 * Thay đổi ±1 phòng (số phòng còn tăng/giảm đúng 1). API `/events` chỉ lọc theo loại, khách sạn, đêm
 * và thời điểm quan sát, không lọc theo độ lớn, nên ẩn ở client trên trang đã tải (trang có thể ít
 * hơn PAGE_SIZE dòng).
 */
function isSmallRoomChange(e: EventOut): boolean {
  if (e.event_type !== "rooms_decrease" && e.event_type !== "rooms_increase") return false;
  const d = num(e.delta);
  return d !== null && Math.abs(d) <= 1;
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Bộ lọc nằm trong URL (?hotel=&types=&from=&to=&since=&small=&page=) để chia sẻ và tải lại được. */
function filtersFromParams(params: URLSearchParams): { f: Filters; offset: number } {
  const hotel = Number(params.get("hotel"));
  const rawSince = params.get("since");
  const since = rawSince === "all" ? 0 : Number(rawSince);
  const page = Number(params.get("page"));
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  return {
    f: {
      hotelId: Number.isInteger(hotel) && hotel > 0 ? hotel : null,
      types: (params.get("types") ?? "").split(",").filter((t) => (EVENT_TYPES as readonly string[]).includes(t)),
      stayFrom: DATE_RE.test(from) ? from : "",
      stayTo: DATE_RE.test(to) ? to : "",
      // Không có `since` = 7 ngày; "all" = mọi thời điểm.
      sinceHours: rawSince === null ? DEFAULT_SINCE : Number.isFinite(since) && since >= 0 ? since : DEFAULT_SINCE,
      small: params.get("small") === "1",
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
  if (f.sinceHours !== DEFAULT_SINCE) q.set("since", f.sinceHours > 0 ? String(f.sinceHours) : "all");
  if (f.small) q.set("small", "1");
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

const CHIP = "inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-sm font-semibold transition-colors duration-150";
const CHIP_OFF = "bg-surface text-body ring-1 ring-inset ring-line-strong hover:bg-subtle hover:ring-[#b7bfcc]";
const CHIP_ON = "bg-night text-white";
const CHIP_PART = "bg-brand-softer text-brand ring-1 ring-inset ring-brand/40 hover:bg-brand-soft";

const DATE_INPUT =
  "h-9 w-[150px] rounded-lg border border-line-strong bg-surface px-2.5 text-base text-ink tabular hover:border-[#b7bfcc] focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15";

function EventsView() {
  const t = useTranslations("events");
  const label = useLabel();
  const { fmtWhen } = useFmt();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const rawHighlight = Number(params.get("highlight"));
  const highlightId = Number.isFinite(rawHighlight) && rawHighlight > 0 ? rawHighlight : null;
  const fresh = useDataFreshness();
  const [now] = useState(() => Date.now());

  // URL là nguồn duy nhất của bộ lọc: đổi là áp dụng ngay, tải lại và chia sẻ link đều nhất quán.
  const paramsKey = params.toString();
  const applied = useMemo(() => filtersFromParams(new URLSearchParams(paramsKey)), [paramsKey]);
  const f = applied.f;
  // Đang chọn từng loại lẻ trong một nhóm thì mở sẵn "Thêm lọc" để thấy đang lọc gì.
  const partial = GROUPS.some((g) => {
    const n = g.types.filter((x) => f.types.includes(x)).length;
    return n > 0 && n < g.types.length;
  });
  const [moreOpen, setMoreOpen] = useState(false);
  const more = moreOpen || partial;

  const watchlist = useApi("watchlist:all", () => api.watchlist.list(true));
  const key = JSON.stringify({ ...applied, f: { ...f, small: undefined } });
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
  function toggleGroup(types: readonly string[]) {
    const all = types.every((x) => f.types.includes(x));
    go({ types: all ? f.types.filter((x) => !types.includes(x)) : [...new Set([...f.types, ...types])] });
  }

  const active = f.hotelId !== null || f.types.length > 0 || !!f.stayFrom || !!f.stayTo || f.sinceHours !== DEFAULT_SINCE || f.small;
  const raw = events.data ?? [];
  const shown = f.small ? raw : raw.filter((e) => !isSmallRoomChange(e));
  const hiddenSmall = raw.length - shown.length;
  const page = Math.floor(applied.offset / PAGE_SIZE) + 1;
  const mine = (watchlist.data ?? []).filter((w) => w.role === "self");
  const others = (watchlist.data ?? []).filter((w) => w.role !== "self");

  // D6: trống vì chưa có lượt quét mới (dữ liệu cũ, hoặc không có lượt quét nào trong kỳ đang lọc) thì nói thẳng.
  const windowStart = f.sinceHours > 0 ? now - f.sinceHours * 3_600_000 : null;
  const noScanInWindow = fresh.loaded && (!fresh.updatedAt || (windowStart !== null && new Date(fresh.updatedAt).getTime() < windowStart));
  const emptyText =
    fresh.loaded && (fresh.stale || noScanInWindow) ? (
      <>
        {fresh.updatedAt ? t("list.emptyNoScan", { when: fmtWhen(fresh.updatedAt) }) : t("list.emptyNeverScanned")}{" "}
        <Link href="/runs" className="font-semibold text-brand hover:underline">
          {t("list.emptyRuns")}
        </Link>
      </>
    ) : active ? (
      t("list.emptyFiltered")
    ) : (
      t("list.empty")
    );

  return (
    <>
      <SubTabs items={REPORT_TABS} />
      <PageHeader
        title={t("title")}
        subtitle={
          <>
            {t("subtitle")}
            {fresh.loaded && (
              <span className="mt-0.5 block text-sm">
                <DataUpdated f={fresh} />
              </span>
            )}
          </>
        }
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
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">{t("filters.hotel")}</span>
            {/* Nhóm "Khách sạn của bạn" / "Đối thủ" thay cho hậu tố "(của bạn)" (nhãn có thể đã ghi "của tôi", N7). */}
            <Select className="w-[240px] max-w-full" value={f.hotelId ?? ""} onChange={(e) => go({ hotelId: e.target.value ? Number(e.target.value) : null })}>
              <option value="">{t("filters.allHotels")}</option>
              {[
                { key: "yourHotels", items: mine },
                { key: "competitors", items: others },
              ]
                .filter((g) => g.items.length > 0)
                .map((g) => (
                  <optgroup key={g.key} label={t(`filters.${g.key as "yourHotels" | "competitors"}`)}>
                    {g.items.map((w) => (
                      <option key={w.hotel.id} value={w.hotel.id}>
                        {hotelTitle(w.hotel, w.label)}
                        {w.active ? "" : ` ${t("filters.inactive")}`}
                      </option>
                    ))}
                  </optgroup>
                ))}
            </Select>
          </label>
          <div className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">{t("filters.observedWithin")}</span>
            <Segmented
              label={t("filters.observedWithin")}
              value={f.sinceHours}
              onChange={(v) => go({ sinceHours: v })}
              items={SINCE_OPTIONS.map((o) => ({ value: o.value, label: t(`since.${o.key}`) }))}
              className="max-w-full flex-wrap"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">{t("filters.stayNight")}</span>
            <div className="flex flex-wrap items-center gap-2">
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

        <div role="group" aria-label={t("filters.eventType")} className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-sm font-semibold text-body">{t("filters.type")}</span>
          {GROUPS.map((g) => {
            const n = g.types.filter((x) => f.types.includes(x)).length;
            const state = n === 0 ? "off" : n === g.types.length ? "on" : "part";
            return (
              <button
                key={g.key}
                type="button"
                aria-pressed={state === "on" ? true : state === "part" ? "mixed" : false}
                title={t("filters.groupTitle", { types: g.types.map((x) => label("eventType", x)).join(", ") })}
                onClick={() => toggleGroup(g.types)}
                className={cx(CHIP, state === "on" ? CHIP_ON : state === "part" ? CHIP_PART : CHIP_OFF)}
              >
                {t(`filters.group.${g.key}`)}
                {state === "part" && <span className="text-xs tabular">{`${n}/${g.types.length}`}</span>}
              </button>
            );
          })}
          <button
            type="button"
            aria-expanded={more}
            onClick={() => setMoreOpen((v) => !v)}
            disabled={partial}
            className="inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-sm font-semibold text-brand hover:underline disabled:cursor-default disabled:no-underline"
          >
            {more ? t("filters.less") : t("filters.more")}
            <IconChevronDown size={14} className={cx("transition-transform duration-150", more && "rotate-180")} />
          </button>
          <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-sm text-body max-sm:ml-0 max-sm:w-full">
            <Switch checked={f.small} onChange={(v) => go({ small: v })} label={t("filters.small")} />
            <span>{t("filters.small")}</span>
          </label>
        </div>

        {more && (
          <div className="space-y-1.5 rounded-lg bg-subtle p-3">
            {GROUPS.map((g) => (
              <div key={g.key} className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 min-w-[96px] shrink-0 text-sm font-semibold text-muted">{t(`filters.group.${g.key}`)}</span>
                {g.types.map((type) => {
                  const on = f.types.includes(type);
                  return (
                    <button key={type} type="button" aria-pressed={on} onClick={() => toggleType(type)} className={cx(CHIP, on ? CHIP_ON : CHIP_OFF)}>
                      <span aria-hidden className={cx("h-2 w-2 rounded-full", DOT[EVENT_TYPE_TONE[type] ?? "gray"], on && "ring-2 ring-white/40")} />
                      {label("eventType", type)}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </div>

      {highlightId && (
        <Note tone="info" icon={<IconInfo size={16} />} className="mb-4">
          {t("highlight.text")}{" "}
          <Link href={pathname + filtersToQuery(f, applied.offset, null)} className="font-semibold text-brand hover:underline">
            {t("highlight.clear")}
          </Link>
        </Note>
      )}
      <ErrorBox error={events.error} className="mb-4" />

      <Card
        padded={false}
        title={events.data ? (raw.length === PAGE_SIZE ? t("list.countMore", { count: shown.length }) : t("list.count", { count: shown.length })) : t("title")}
        description={
          <>
            {active ? t("list.filtered") : t("list.newestFirst")}
            {hiddenSmall > 0 && ` · ${t("list.smallHidden", { count: hiddenSmall })}`}
          </>
        }
        actions={
          (applied.offset > 0 || raw.length === PAGE_SIZE) && (
            <div className="flex items-center gap-1.5 text-sm text-muted">
              <Button size="sm" variant="ghost" icon={<IconChevronLeft size={15} />} disabled={applied.offset === 0} onClick={() => go({}, Math.max(0, applied.offset - PAGE_SIZE))}>
                {t("list.prev")}
              </Button>
              <span className="tabular">{t("list.page", { page })}</span>
              <Button size="sm" variant="ghost" disabled={raw.length < PAGE_SIZE} onClick={() => go({}, applied.offset + PAGE_SIZE)}>
                {t("list.next")} <IconChevronRight size={15} />
              </Button>
            </div>
          )
        }
      >
        <div className={cx("transition-opacity duration-200", events.loading && events.data && "opacity-60")}>
          {events.data ? (
            <EventTable
              events={shown}
              highlightId={highlightId}
              labelOf={(id) => watchlist.data?.find((w) => w.hotel.id === id)?.label ?? undefined}
              emptyText={emptyText}
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
