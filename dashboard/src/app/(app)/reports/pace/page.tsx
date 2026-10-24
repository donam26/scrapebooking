"use client";

import { Suspense } from "react";
import { SkeletonBlock } from "@/components/ui";
import { PaceReport } from "./pace-report";

export default function ReportsPacePage() {
  return (
    <Suspense fallback={<SkeletonBlock className="h-[400px] w-full rounded-[10px]" />}>
      <PaceReport />
    </Suspense>
  );
}
