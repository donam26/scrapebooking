"use client";

import { useTranslations } from "next-intl";
import { Suspense } from "react";
import { useTenantToday } from "@/lib/hooks";
import { OwnHotelSwitcher, useOwnHotelParam, useOwnHotels } from "@/components/own-hotel";
import { SuggestionOutcomes } from "@/components/suggestion-outcomes";
import { REPORT_TABS, SubTabs } from "@/components/sub-tabs";
import { PageHeader, SkeletonBlock } from "@/components/ui";

/**
 * Báo cáo › Kết quả gợi ý (Q5, T9): quyết định đã ghi cho các đêm sắp tới (Hoàn tác ngay tại chỗ) và
 * kết quả sau đêm lưu trú theo số PMS. Gợi ý chờ xử lý chỉ ở Hôm nay và trang đêm (S5).
 */
function OutcomesView() {
  const t = useTranslations("reports.outcomes");
  const today = useTenantToday();
  const [hotelParam, setHotel] = useOwnHotelParam();
  const ownHotels = useOwnHotels();
  return (
    <>
      <SubTabs items={REPORT_TABS} />
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
        actions={<OwnHotelSwitcher hotels={ownHotels} value={hotelParam ?? ownHotels[0]?.id ?? null} onChange={setHotel} />}
      />
      {today ? <SuggestionOutcomes ownHotelId={hotelParam} undoFrom={today} /> : <SkeletonBlock className="h-64 w-full rounded-xl" />}
    </>
  );
}

export default function ReportsOutcomesPage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[400px] w-full rounded-[10px]" />}>
      <OutcomesView />
    </Suspense>
  );
}
