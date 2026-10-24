"use client";

import { useTranslations } from "next-intl";
import type { OwnDailyOut } from "@/lib/api";
import { addDays, dateRange, num, useFmt } from "@/lib/format";
import { Card, cx } from "@/components/ui";

/** Doanh thu đã đặt mỗi đêm trong 14 đêm từ `today` (bản nhập PMS mới nhất của từng đêm); null khi chưa có số. */
export function revenueNights(rows: OwnDailyOut[], today: string): Array<{ date: string; value: number | null }> {
  const latest = new Map<string, OwnDailyOut>();
  for (const r of rows) {
    const d = String(r.stay_date);
    const prev = latest.get(d);
    if (!prev || r.imported_at > prev.imported_at) latest.set(d, r);
  }
  return dateRange(today, addDays(today, 13)).map((date) => {
    const r = latest.get(date);
    if (!r) return { date, value: null };
    const rev = num(r.revenue as string | null);
    if (rev !== null) return { date, value: rev };
    const adr = num(r.adr as string | null);
    return { date, value: adr !== null && r.rooms_sold !== null ? adr * r.rooms_sold : null };
  });
}

/**
 * Doanh thu 14 ngày tới từ PMS (doanh thu đã đặt; thiếu doanh thu thì phòng đã bán × ADR của PMS).
 * Không ước tính từ giá niêm yết. Trang chỉ đặt thẻ này khi có ít nhất một đêm có số.
 */
export function RevenueCard({ nights }: { nights: Array<{ date: string; value: number | null }> }) {
  const t = useTranslations("reports.revenue");
  const { fmtCompact, fmtMoney, fmtNight } = useFmt();
  const known = nights.map((n) => n.value).filter((v): v is number => v !== null);
  const total = known.reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...known);
  return (
    <Card title={t("title")} info={t("info")}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="shrink-0">
          <div className="text-[32px] font-bold leading-tight text-brand tabular">{fmtCompact(total)}</div>
          <div className="text-sm text-muted">{t("caption", { known: known.length })}</div>
        </div>
        <div className="flex h-16 w-full min-w-0 items-end gap-1 sm:flex-1">
          {nights.map((n) => (
            <span
              key={n.date}
              title={`${fmtNight(n.date)}: ${n.value === null ? t("barNoData") : fmtMoney(Math.round(n.value), "VND")}`}
              className={cx("flex-1 rounded-t-[3px]", n.value === null ? "bg-sunken" : "bg-brand")}
              style={{ height: `${n.value === null ? 12 : Math.max(10, (n.value / max) * 100)}%` }}
            />
          ))}
        </div>
      </div>
    </Card>
  );
}
