"use client";

import { Suspense } from "react";
import { api, type CompsetDayOut, type OverviewOut } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { dateRange, fmtDateShort, fmtMoney, fmtNum, fmtWeekday, fmtWhen, num } from "@/lib/format";
import { ButtonLink, EmptyState, ErrorBox, Note, PageHeader, SkeletonBlock, StatStrip, cx } from "@/components/ui";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { RunSummary } from "@/components/run-summary";
import { IconBuilding, IconInfo, IconPlus } from "@/components/icons";
import { Board, hotelName } from "./board";

function dayLabel(d: string): string {
  return `${fmtWeekday(d).replace("Thứ ", "T")} ${fmtDateShort(d)}`;
}

/** Bốn ý tóm tắt cho quyết định buổi sáng: đêm đầu kỳ và 7 đêm tới. */
function Summary({ data }: { data: OverviewOut }) {
  const dates = dateRange(data.start, data.end);
  const d0 = dates[0];
  const next7 = dates.slice(0, 7);
  const byDate = new Map<string, CompsetDayOut>(data.compset.map((c) => [c.stay_date, c]));
  const self = data.hotels.find((h) => h.role === "self") ?? null;
  const c0 = byDate.get(d0);
  const isToday = self?.cells.find((c) => c.stay_date === d0)?.days_to_arrival === 0 || data.hotels[0]?.cells[0]?.days_to_arrival === 0;
  const firstName = isToday ? "đêm nay" : dayLabel(d0);

  // Đối thủ hết phòng: đêm đầu + đêm căng nhất trong 7 đêm
  let peak: CompsetDayOut | null = null;
  for (const d of next7) {
    const c = byDate.get(d);
    if (c && c.competitors_sold_out > 0 && (!peak || c.competitors_sold_out > peak.competitors_sold_out)) peak = c;
  }

  // Chỉ số giá trung bình 7 đêm
  const idx = next7.map((d) => num(byDate.get(d)?.price_index)).filter((v): v is number => v !== null);
  const avgIdx = idx.length ? idx.reduce((a, b) => a + b, 0) / idx.length : null;

  // Đêm của bạn còn ≤ 3 phòng hoặc hết trong cả kỳ
  const tight = self
    ? self.cells.filter((c) => c.availability_status === "sold_out" || (c.exact_rooms_left !== null && c.exact_rooms_left <= 3))
    : [];

  const selfCell0 = self?.cells.find((c) => c.stay_date === d0);
  const selfValue = !self
    ? "Chưa thêm"
    : !selfCell0 || selfCell0.availability_status === null
      ? "Chưa có dữ liệu"
      : selfCell0.availability_status === "sold_out"
        ? "Hết phòng"
        : selfCell0.exact_rooms_left !== null
          ? `Còn ${selfCell0.exact_rooms_left} phòng`
          : "Còn phòng";

  return (
    <StatStrip
      className="mb-6"
      items={[
        {
          label: self ? `${hotelName(self)} ${firstName}` : `Khách sạn của bạn ${firstName}`,
          value: selfValue,
          hint: selfCell0?.min_price ? `Giá thấp nhất ${fmtMoney(selfCell0.min_price, selfCell0.currency)}` : self ? "Không có giá" : "Thêm ở Cài đặt › Khách sạn",
          tone: selfCell0?.availability_status === "sold_out" ? "good" : "default",
        },
        {
          label: `Đối thủ hết phòng ${firstName}`,
          value: c0 ? `${c0.competitors_sold_out}/${c0.competitors_observed}` : "—",
          hint: peak ? `7 đêm tới căng nhất: ${peak.competitors_sold_out}/${peak.competitors_observed} vào ${dayLabel(peak.stay_date)}` : "7 đêm tới: chưa đối thủ nào hết phòng",
        },
        {
          label: "Giá của bạn so với trung vị đối thủ",
          value: avgIdx === null ? "—" : avgIdx < 100 ? `Thấp hơn ${fmtNum(100 - avgIdx, 0)}%` : avgIdx > 100 ? `Cao hơn ${fmtNum(avgIdx - 100, 0)}%` : "Bằng trung vị",
          hint: avgIdx === null ? "Chưa đủ giá để so" : "Trung bình giá thấp nhất 7 đêm tới",
          tone: avgIdx !== null && avgIdx < 80 ? "warn" : "default",
        },
        {
          label: "Đêm bạn còn ≤ 3 phòng",
          value: self ? `${tight.length} đêm` : "—",
          hint: tight.length ? tight.slice(0, 3).map((c) => dayLabel(c.stay_date)).join(", ") + (tight.length > 3 ? "…" : "") : `Trong ${dates.length} đêm đang xem`,
        },
      ]}
    />
  );
}

function OverviewSkeleton() {
  return (
    <div aria-busy aria-label="Đang tải">
      <SkeletonBlock className="mb-6 h-[92px] w-full rounded-xl" />
      <div className="space-y-3">
        <SkeletonBlock className="h-10 w-full" />
        {[0, 1, 2, 3].map((i) => (
          <SkeletonBlock key={i} className="h-[132px] w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function OverviewView() {
  const { start, end, days } = useDateRange();
  const { isOperator } = useSession();
  const { data, error, loading } = useApi(`overview:${start}:${end}`, () => api.overview({ start, end }));
  const run = data?.last_run ?? null;

  return (
    <>
      <PageHeader
        title="Tổng quan"
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>
              {days} đêm, {dayLabel(start)} – {dayLabel(end)}
            </span>
            {run && (
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-yours" />
                Quét lúc {fmtWhen(run.finished_at ?? run.started_at)}
              </span>
            )}
          </span>
        }
        actions={<DateRangePicker />}
      />
      <ErrorBox error={error} className="mb-4" />
      {!data && !error && <OverviewSkeleton />}
      {data && data.hotels.length === 0 && (
        <EmptyState
          icon={<IconBuilding />}
          title="Chưa theo dõi khách sạn nào"
          className="border border-line bg-surface"
          action={
            <ButtonLink href="/settings?tab=watchlist" variant="primary" icon={<IconPlus size={16} />}>
              Thêm khách sạn
            </ButtonLink>
          }
        >
          Thêm khách sạn của bạn và các đối thủ bằng đường dẫn Booking.com. Lượt quét kế tiếp sẽ điền bảng này.
        </EmptyState>
      )}
      {data && data.hotels.length > 0 && (
        <div className={cx("transition-opacity duration-200", loading && "opacity-60")}>
          <Summary data={data} />
          {!data.hotels.some((h) => h.role === "self") && (
            <Note tone="info" icon={<IconInfo size={16} />} className="mb-4">
              Chưa có khách sạn của bạn trong danh sách theo dõi nên chưa so được giá. Thêm ở <a href="/settings?tab=watchlist" className="font-semibold text-brand underline">Cài đặt › Khách sạn</a> với vai trò “Khách sạn của bạn”.
            </Note>
          )}
          <Board data={data} />
          {isOperator && run && (
            <details className="mt-6 rounded-xl border border-line bg-surface">
              <summary className="cursor-pointer px-5 py-3 text-sm font-semibold text-body">Chi tiết kỹ thuật lượt quét #{run.id}</summary>
              <div className="border-t border-line px-5 py-4">
                <RunSummary run={run} />
              </div>
            </details>
          )}
        </div>
      )}
    </>
  );
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<OverviewSkeleton />}>
      <OverviewView />
    </Suspense>
  );
}
