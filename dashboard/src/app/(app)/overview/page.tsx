"use client";

import { Suspense } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { fmtDate } from "@/lib/format";
import { Card, ErrorBox, PageHeader, Skeleton, cx } from "@/components/ui";
import { DateRangePicker, useDateRange } from "@/components/date-range";
import { RunSummary } from "@/components/run-summary";
import { Heatmap } from "./heatmap";

function OverviewView() {
  const { start, end } = useDateRange();
  const { data, error, loading } = useApi(`overview:${start}:${end}`, () => api.overview({ start, end }));

  return (
    <>
      <PageHeader title="Tổng quan" subtitle={`Tình trạng phòng và giá theo ngày lưu trú, ${fmtDate(start)} – ${fmtDate(end)}`} actions={<DateRangePicker />} />
      <ErrorBox error={error} className="mb-4" />
      <Card className="mb-4">{data ? <RunSummary run={data.last_run} /> : <Skeleton rows={1} />}</Card>
      <Card title="Heatmap khách sạn × ngày" padded={false}>
        <div className={cx("p-2 transition-opacity", loading && data && "opacity-60")}>
          {data ? <Heatmap data={data} /> : <Skeleton rows={8} className="p-2" />}
        </div>
      </Card>
    </>
  );
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<Skeleton rows={8} />}>
      <OverviewView />
    </Suspense>
  );
}
