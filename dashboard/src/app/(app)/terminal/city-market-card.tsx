"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import type { MarketCityOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import { Card, cx } from "@/components/ui";
import { RingGauge } from "@/components/gauge";
import { IconPin } from "@/components/icons";

/**
 * CHỈ BÁO THỊ TRƯỜNG cả khu vực (như "Hanoi market indicator" của mẫu): công suất ước tính từ các
 * khách sạn quét chi tiết, số khách sạn còn phòng đêm nay trên Booking, phòng còn/tồn kho, giá TB và
 * phân bố giá. Giá là mẫu trên các khách sạn đã thấy ở trang kết quả.
 */

function mood(pct: number | null): { key: "noData" | "tight" | "balanced" | "soft"; cls: string; color: string } {
  if (pct === null) return { key: "noData", cls: "bg-sunken text-muted", color: "var(--sb-faint)" };
  if (pct >= 75) return { key: "tight", cls: "bg-hot-soft text-hot", color: "var(--sb-hot)" };
  if (pct >= 50) return { key: "balanced", cls: "bg-brand-soft text-brand", color: "var(--sb-brand)" };
  return { key: "soft", cls: "bg-yours-soft text-yours-deep", color: "var(--sb-yours)" };
}

/** Màu cột phân bố giá: rẻ xanh lá → đắt tím (như dải màu của mẫu). */
const BAR_COLORS = ["#16a34a", "#4ade80", "#a3e635", "#facc15", "#f59e0b", "#ea7317", "#ef4444", "#8b5cf6"];

export function CityMarketCard({ city }: { city: MarketCityOut }) {
  const t = useTranslations("terminal");
  const { fmtCompact, fmtInt, fmtWhen } = useFmt();
  const { list_scan: list, detail, area } = city;
  const occ = num(detail.occupancy_est);
  const pct = occ === null ? null : Math.round(occ * 100);
  const m = mood(pct);
  const maxCount = Math.max(1, ...list.histogram.map((b) => b.count));
  const avg = num(list.avg);
  return (
    <Card
      className="h-full"
      title={t("city.title", { name: area.name })}
      icon={<IconPin size={15} />}
      info={t("city.info", { coverage: detail.coverage_hotels, priced: list.priced })}
    >
      <div className="flex flex-col items-center">
        <RingGauge value={pct} color={m.color} sub={t("occGauge")} />
        <span className={cx("mt-3 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.04em]", m.cls)}>{t(`mood.${m.key}`)}</span>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div title={t("city.roomsLeftTitle")}>
          <dt className="text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("city.roomsLeft")}</dt>
          <dd className="text-md font-bold text-ink tabular">{detail.rooms_left_known_sum ? fmtInt(detail.rooms_left_known_sum) : "—"}</dd>
        </div>
        <div title={t("city.inventoryTitle")}>
          <dt className="text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("city.inventory")}</dt>
          <dd className="text-md font-bold text-ink tabular">{detail.inventory_sum ? fmtInt(detail.inventory_sum) : "—"}</dd>
        </div>
        <div>
          <dt className="text-[10px] font-semibold uppercase tracking-[0.05em] text-faint">{t("city.avgRate")}</dt>
          <dd className="text-md font-bold text-ink tabular">{avg === null ? "—" : fmtCompact(avg)}</dd>
        </div>
      </dl>
      <p className="mt-2 text-center text-xs text-muted">
        {list.properties_found !== null ? (
          list.properties_found <= area.hotels_total ? (
            t.rich("city.found", { found: fmtInt(list.properties_found), total: fmtInt(area.hotels_total), b: (c) => <span className="font-semibold text-ink tabular">{c}</span> })
          ) : (
            t.rich("city.foundOver", { found: fmtInt(list.properties_found), total: fmtInt(area.hotels_total), b: (c) => <span className="font-semibold text-ink tabular">{c}</span> })
          )
        ) : (
          t("city.notScanned")
        )}
      </p>
      {list.histogram.length > 0 && (
        <div className="mt-3">
          <div className="text-center text-[10px] font-semibold uppercase tracking-[0.05em] text-faint" title={list.sample ? t("city.sampleTitle") : undefined}>
            {list.sample
              ? t("city.histogramSample", { priced: fmtInt(list.priced), found: fmtInt(list.properties_found ?? list.priced) })
              : t("city.histogramAll", { priced: fmtInt(list.priced) })}
          </div>
          <div className="mt-1.5 flex h-10 items-end gap-0.5">
            {list.histogram.map((b, i) => (
              <span
                key={b.lo}
                title={t("city.barTitle", { range: `${fmtCompact(num(b.lo))}${b.hi ? `–${fmtCompact(num(b.hi))}` : "+"}`, count: b.count })}
                className="flex-1 rounded-t-[2px]"
                style={{ height: `${Math.max(6, (b.count / maxCount) * 100)}%`, background: BAR_COLORS[i % BAR_COLORS.length] }}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-muted tabular">
            <span>&lt;{fmtCompact(num(list.histogram[0]?.hi ?? null))}</span>
            <span>{fmtCompact(num(list.histogram[list.histogram.length - 1]?.lo ?? null))}+</span>
          </div>
        </div>
      )}
      <p className="mt-2 text-center text-[11px] text-faint">
        {list.scanned_at ? t("city.listScanned", { when: fmtWhen(list.scanned_at) }) : t("city.neverScanned")}
        {" · "}
        <Link href="/competitors/market" className="font-semibold text-brand hover:underline">
          {t("city.explore")}
        </Link>
      </p>
    </Card>
  );
}
