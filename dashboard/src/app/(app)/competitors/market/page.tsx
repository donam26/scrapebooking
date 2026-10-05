"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { Suspense, useState } from "react";
import { api, ApiError, type CityHotelOut } from "@/lib/api";
import { useApi, useMutation, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { num, useFmt } from "@/lib/format";
import { Badge, Button, EmptyState, ErrorBox, Input, Segmented, SkeletonBlock, Table, Td, Th, ROW_CLASS, cx } from "@/components/ui";
import { PageStrip, StripDivider } from "@/components/page-strip";
import { COMPETITOR_TABS, SubTabs } from "@/components/sub-tabs";
import { IconChevronLeft, IconChevronRight, IconExternal, IconPin, IconPlus, IconSearch, IconStar } from "@/components/icons";

/**
 * Đối thủ › Khám phá thị trường (như bên OTARadar chọn đối thủ từ danh sách khách sạn đã quét):
 * mọi khách sạn của khu vực trên Booking.com với điểm đánh giá, hạng sao, khoảng cách, giá đêm nay,
 * và nút "Theo dõi" để thêm vào compset.
 */

type Sort = "review_count" | "review_score" | "price" | "distance";
const PAGE = 50;

function ScoreBadge({ score, count }: { score: string | null; count: number | null }) {
  const { fmtInt, fmtNum } = useFmt();
  const s = num(score);
  if (s === null) return <span className="text-faint">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cx("inline-grid h-7 min-w-8 place-items-center rounded-md rounded-bl-none px-1 text-sm font-bold text-white tabular", s >= 9 ? "bg-[#003b95]" : s >= 8 ? "bg-brand" : s >= 7 ? "bg-[#5b9bff]" : "bg-faint")}>
        {fmtNum(s, 1)}
      </span>
      {count !== null && <span className="text-xs text-muted tabular">{fmtInt(count)}</span>}
    </span>
  );
}

function FollowButton({ hotel, onDone }: { hotel: CityHotelOut; onDone: () => void }) {
  const { canWrite } = useSession();
  const t = useTranslations("market.follow");
  const add = useMutation(async () => {
    if (!hotel.url) return;
    await api.watchlist.add({ url: hotel.url, role: "competitor", label: null });
    onDone();
  });
  if (hotel.watched) return <Badge tone={hotel.role === "self" ? "blue" : "green"}>{hotel.role === "self" ? t("yours") : t("following")}</Badge>;
  if (!canWrite || !hotel.url) return null;
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <Button size="sm" variant="quiet" icon={<IconPlus size={15} />} busy={add.busy} onClick={() => void add.run()}>
        {t("follow")}
      </Button>
      {add.error && <span className="max-w-[180px] text-right text-xs text-danger">{add.error}</span>}
    </span>
  );
}

function MarketView() {
  const t = useTranslations("market.page");
  const tt = useTranslations("market.table");
  const { fmtInt, fmtMoney, fmtNum, fmtWhen } = useFmt();
  const today = useTenantToday();
  const [sort, setSort] = useState<Sort>("review_count");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const city = useApi(today && `explore:city:${today}`, () =>
    api.market.city({ date: today! }).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
  );
  const hotels = useApi(today && city.data ? `explore:hotels:${today}:${sort}:${query}:${offset}` : null, () =>
    api.market.cityHotels({ date: today!, sort, q: query || undefined, limit: PAGE, offset }),
  );
  const total = hotels.data?.total ?? 0;

  return (
    <>
      <SubTabs items={COMPETITOR_TABS} />
      <PageStrip
        title={t("title")}
        meta={
          city.data && (
            <>
              <span className="inline-flex items-center gap-1.5">
                <IconPin size={15} className="text-muted" /> {city.data.area.name}
              </span>
              <StripDivider />
              <span>{t("knownHotels", { count: city.data.area.hotels_total })}</span>
              {city.data.list_scan.properties_found !== null && (
                <>
                  <StripDivider />
                  <span>{t.rich("availableTonight", { count: city.data.list_scan.properties_found, b: (c) => <span className="font-semibold text-ink">{c}</span> })}</span>
                </>
              )}
            </>
          )
        }
        aside={city.data?.list_scan.scanned_at && <span>{t("listScanned", { when: fmtWhen(city.data.list_scan.scanned_at) })}</span>}
      />
      <ErrorBox error={city.error ?? hotels.error} className="mb-4" />
      {city.data === undefined && !city.error && <SkeletonBlock className="h-[480px] w-full rounded-[10px]" />}
      {city.data === null && (
        <EmptyState icon={<IconPin />} title={t("emptyTitle")} className="border border-line bg-surface">
          {t.rich("emptyBody", {
            link: (c) => (
              <Link href="/settings?tab=market" className="font-semibold text-brand hover:underline">
                {c}
              </Link>
            ),
          })}
        </EmptyState>
      )}
      {city.data && (
        <section className="rounded-[10px] border border-line bg-surface shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setOffset(0);
                setQuery(q.trim());
              }}
            >
              <div className="relative">
                <IconSearch size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
                <Input aria-label={t("searchLabel")} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchPlaceholder")} className="w-[240px] pl-8" />
              </div>
              <Button type="submit" size="sm">
                {t("search")}
              </Button>
            </form>
            <Segmented
              label={t("sort")}
              value={sort}
              onChange={(v) => {
                setOffset(0);
                setSort(v);
              }}
              items={[
                { value: "review_count", label: t("sorts.review_count") },
                { value: "review_score", label: t("sorts.review_score") },
                { value: "price", label: t("sorts.price") },
                { value: "distance", label: t("sorts.distance") },
              ]}
            />
          </div>
          {!hotels.data && !hotels.error && <SkeletonBlock className="mx-5 mb-5 h-64" />}
          {hotels.data && hotels.data.items.length === 0 && <p className="px-5 pb-5 text-sm text-muted">{t("noMatch")}</p>}
          {hotels.data && hotels.data.items.length > 0 && (
            <Table dense className={cx("transition-opacity", hotels.loading && "opacity-60")}>
              <thead>
                <tr>
                  <Th className="pl-5">{tt("hotel")}</Th>
                  <Th>{tt("reviews")}</Th>
                  <Th>{tt("stars")}</Th>
                  <Th right>{tt("distance")}</Th>
                  <Th right>{tt("tonightRate")}</Th>
                  <Th>{tt("tonight")}</Th>
                  <Th className="pr-5" />
                </tr>
              </thead>
              <tbody>
                {hotels.data.items.map((h) => {
                  const stars = num(h.stars);
                  return (
                    <tr key={h.hotel_id} className={ROW_CLASS}>
                      <Td className="pl-5">
                        <div className="flex min-w-0 max-w-[340px] items-center gap-1.5">
                          {h.watched ? (
                            <Link href={`/hotels/${h.hotel_id}`} className="truncate font-semibold text-ink hover:text-brand hover:underline">
                              {h.name ?? `#${h.hotel_id}`}
                            </Link>
                          ) : (
                            <span className="truncate font-semibold text-ink">{h.name ?? `#${h.hotel_id}`}</span>
                          )}
                          {h.url && (
                            <a href={h.url} target="_blank" rel="noreferrer" aria-label={tt("openOnBooking", { name: h.name ?? tt("hotelFallback") })} className="shrink-0 text-muted hover:text-brand">
                              <IconExternal size={13} />
                            </a>
                          )}
                        </div>
                        {h.district && <div className="truncate text-xs text-muted">{h.district}</div>}
                      </Td>
                      <Td>
                        <ScoreBadge score={h.review_score} count={h.review_count} />
                      </Td>
                      <Td>
                        {stars !== null && stars > 0 ? (
                          <span className="inline-flex text-[#f59e0b]" aria-label={tt("starsAria", { count: stars })}>
                            {Array.from({ length: Math.round(stars) }, (_, i) => (
                              <IconStar key={i} size={12} fill="currentColor" />
                            ))}
                          </span>
                        ) : (
                          <span className="text-faint">—</span>
                        )}
                      </Td>
                      <Td right>{h.distance_km === null ? "—" : tt("km", { km: fmtNum(h.distance_km, 1) })}</Td>
                      <Td right className="font-semibold text-ink">
                        {h.price === null ? "—" : fmtMoney(h.price, h.currency)}
                      </Td>
                      <Td>{h.available === null ? <span className="text-faint">{tt("unknown")}</span> : h.available ? <Badge tone="green">{tt("available")}</Badge> : <Badge tone="red">{tt("soldOut")}</Badge>}</Td>
                      <Td className="pr-5 text-right">
                        <FollowButton hotel={h} onDone={hotels.reload} />
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
          {total > PAGE && (
            <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
              <span className="text-muted tabular">
                {fmtInt(offset + 1)}–{fmtInt(Math.min(offset + PAGE, total))} / {fmtInt(total)}
              </span>
              <span className="flex gap-2">
                <Button size="sm" icon={<IconChevronLeft size={15} />} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  {t("prev")}
                </Button>
                <Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
                  {t("next")} <IconChevronRight size={15} />
                </Button>
              </span>
            </div>
          )}
        </section>
      )}
    </>
  );
}

export default function CompetitorMarketPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[480px] w-full rounded-[10px]" />}>
      <MarketView />
    </Suspense>
  );
}
