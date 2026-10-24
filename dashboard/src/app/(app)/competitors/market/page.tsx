"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, ApiError, type CityHotelOut } from "@/lib/api";
import { useApi, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { num, useFmt } from "@/lib/format";
import { roomsRange } from "@/lib/market-area";
import { useMarketAreaChoice } from "@/lib/market-area-choice";
import { roomsLeftText } from "@/lib/rooms-left";
import { usePlaceName } from "@/lib/place-names";
import { Badge, Button, EmptyState, ErrorBox, Input, Segmented, SkeletonBlock, Table, Td, Th, ROW_CLASS, cx } from "@/components/ui";
import { PageStrip, StripDivider } from "@/components/page-strip";
import { AreaSelect } from "@/components/area-select";
import { roomsShade } from "@/components/marks";
import { COMPETITOR_TABS, SubTabs } from "@/components/sub-tabs";
import { AddHotelDialog } from "@/components/add-hotel-dialog";
import { IconChevronLeft, IconChevronRight, IconExternal, IconPin, IconPlus, IconSearch, IconStar } from "@/components/icons";

/**
 * Đối thủ › Tìm khách sạn để theo dõi (Khám phá cũ): mọi khách sạn của khu vực trên Booking.com với
 * điểm đánh giá, hạng sao, khoảng cách, giá của đêm đã quét danh sách, số phòng còn bán được (thang
 * tìm kiếm của khu vực) và nút "Theo dõi" mở cùng hộp "Thêm khách sạn" như trang Đối thủ.
 * Tiêu đề cột giá ghi đúng đêm của giá; danh sách quét cũ hơn 24 giờ thì có dấu "cũ" (D3).
 */

/** Danh sách quét cũ hơn chừng này thì đánh dấu cũ. */
const LIST_STALE_MS = 24 * 3600 * 1000;

type Sort = "review_count" | "review_score" | "price" | "distance";
const SORTS: Sort[] = ["review_count", "review_score", "price", "distance"];
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

/**
 * Phòng còn theo thang tìm kiếm của khu vực (đêm đã liệt kê từng khách sạn): "1", "5–9", "≥30";
 * tô theo thang nhiệt như mọi số phòng còn ("≥N"/khoảng vắt qua hai mức thì nền sọc "ít nhất").
 */
function RoomsChip({ min, max }: { min: number | null | undefined; max: number | null | undefined }) {
  const tt = useTranslations("market.table");
  const { fmtInt } = useFmt();
  const r = roomsRange(min, max);
  if (!r) return <span className="text-faint">—</span>;
  const text = roomsLeftText(r, fmtInt);
  return (
    <span title={tt("roomsTitle", { range: text })} className={cx("inline-grid h-6 min-w-9 place-items-center rounded-md px-1.5 text-xs font-bold tabular", roomsShade(r))}>
      {text}
    </span>
  );
}

function FollowButton({ hotel, onFollow }: { hotel: CityHotelOut; onFollow: (h: CityHotelOut) => void }) {
  const { canWrite } = useSession();
  const t = useTranslations("market.follow");
  if (hotel.watched) return <Badge tone={hotel.role === "self" ? "blue" : "green"}>{hotel.role === "self" ? t("yours") : t("following")}</Badge>;
  if (!canWrite || !hotel.url) return null;
  return (
    <Button size="sm" variant="quiet" icon={<IconPlus size={15} />} onClick={() => onFollow(hotel)}>
      {t("follow")}
    </Button>
  );
}

function MarketView() {
  const t = useTranslations("market.page");
  const tt = useTranslations("market.table");
  const { fmtAgo, fmtDateShort, fmtInt, fmtMoney, fmtNum, fmtWhen } = useFmt();
  const place = usePlaceName();
  const today = useTenantToday();
  const [following, setFollowing] = useState<CityHotelOut | null>(null);
  const [now] = useState(() => Date.now());
  // `?sort=price` (link từ cảnh báo nhóm đối thủ lệch giá ở Thiết lập/Cài đặt) chọn sẵn cách sắp xếp.
  const params = useSearchParams();
  const sortParam = params.get("sort") as Sort | null;
  const [sort, setSort] = useState<Sort>(sortParam && SORTS.includes(sortParam) ? sortParam : "review_count");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  // Khu vực đang xem: cùng lựa chọn với Terminal+ (lưu theo trình duyệt); ô chọn khi có từ 2 khu vực.
  const choice = useMarketAreaChoice();
  const city = useApi(today && choice.ready ? `explore:city:${today}:${choice.areaId ?? ""}` : null, () =>
    api.market.city({ date: today!, area_id: choice.areaId }).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
  );
  const areaId = choice.areaId ?? city.data?.area.id;
  const hotels = useApi(today && city.data && areaId ? `explore:hotels:${today}:${areaId}:${sort}:${query}:${offset}` : null, () =>
    api.market.cityHotels({ date: today!, area_id: areaId, sort, q: query || undefined, limit: PAGE, offset }),
  );
  const total = hotels.data?.total ?? 0;
  // Đêm của giá trong bảng (đêm của lượt quét danh sách) và tuổi lượt quét.
  const night = hotels.data?.stay_date ?? city.data?.stay_date ?? today;
  const isTonight = !!night && night === today;
  const scannedAt = city.data?.list_scan.scanned_at ?? null;
  const listStale = !!scannedAt && now - new Date(scannedAt).getTime() > LIST_STALE_MS;
  const staleTitle = scannedAt ? t("listStaleTitle", { when: fmtWhen(scannedAt), ago: fmtAgo(scannedAt) }) : undefined;

  return (
    <>
      <SubTabs items={COMPETITOR_TABS} />
      <PageStrip
        title={t("title")}
        meta={
          city.data && (
            <>
              <span className="inline-flex min-w-0 max-w-full items-center gap-1.5">
                <IconPin size={15} className="shrink-0 text-muted" />
                {choice.active.length >= 2 ? (
                  <AreaSelect
                    areas={choice.active}
                    value={areaId}
                    onChange={(id) => {
                      setOffset(0);
                      choice.select(id);
                    }}
                    className="max-w-[240px]"
                  />
                ) : (
                  city.data.area.name
                )}
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
        aside={
          scannedAt && (
            <span className={listStale ? "font-semibold text-warning-deep" : undefined} title={listStale ? staleTitle : undefined}>
              {t("listScanned", { when: fmtWhen(scannedAt) })}
              {listStale && ` · ${fmtAgo(scannedAt)}`}
            </span>
          )
        }
      />
      {following && (
        <AddHotelDialog
          open
          initialUrl={following.url ?? ""}
          title={t("followTitle", { name: following.name ?? tt("hotelFallback") })}
          showExplore={false}
          onClose={() => setFollowing(null)}
          onAdded={hotels.reload}
        />
      )}
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
              className="flex min-w-0 items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setOffset(0);
                setQuery(q.trim());
              }}
            >
              <div className="relative min-w-0">
                <IconSearch size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
                <Input aria-label={t("searchLabel")} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchPlaceholder")} className="w-[240px] max-w-full pl-8" />
              </div>
              <Button type="submit" size="sm">
                {t("search")}
              </Button>
            </form>
            <div className="sb-scroll max-w-full overflow-x-auto">
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
                  <Th right>
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                      {isTonight || !night ? tt("tonightRate") : tt("nightRate", { night: fmtDateShort(night) })}
                      {listStale && (
                        <span className="rounded-full bg-warning-soft px-1.5 py-px text-2xs font-semibold normal-case tracking-normal text-warning-deep" title={staleTitle}>
                          {tt("staleChip")}
                        </span>
                      )}
                    </span>
                  </Th>
                  <Th>{tt("rooms")}</Th>
                  <Th>{isTonight || !night ? tt("tonight") : tt("night", { night: fmtDateShort(night) })}</Th>
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
                        {h.district && <div className="truncate text-xs text-muted">{place(h.district)}</div>}
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
                      <Td right className={cx("font-semibold", listStale ? "text-muted" : "text-ink")} title={listStale ? staleTitle : undefined}>
                        {h.price === null ? "—" : fmtMoney(h.price, h.currency)}
                        {h.only_left != null && h.only_left > 0 && <div className="text-xs font-normal text-muted">{tt("onlyLeft", { count: h.only_left })}</div>}
                      </Td>
                      <Td>
                        <RoomsChip min={h.rooms_min} max={h.rooms_max} />
                      </Td>
                      <Td>{h.available === null ? <span className="text-faint">{tt("unknown")}</span> : h.available ? <Badge tone="green">{tt("available")}</Badge> : <Badge tone="red">{tt("soldOut")}</Badge>}</Td>
                      <Td className="pr-5 text-right">
                        <FollowButton hotel={h} onFollow={setFollowing} />
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
