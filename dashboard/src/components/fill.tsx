"use client";

import { useTranslations } from "next-intl";
import type { CalibrationOut } from "@/lib/api";
import { num, useFmt } from "@/lib/format";
import type { FillReading } from "@/lib/market-metrics";
import { cx } from "./ui";

/**
 * Chỉ báo lấp đầy (thử nghiệm) và độ tin của nó (roadmap 1.3, 5.6):
 * - giá trị luôn kèm "≈" và khoảng [thấp, cao]: "≈72% (65–80%)";
 * - ẩn khi nhóm lead time của đêm đã so với PMS mà sai số quá ngưỡng (ghi lý do);
 * - sai số so PMS theo nhóm lead time: "sai số so PMS ±4 / ±9 / — điểm ở 0–7 / 8–30 / 31–90 ngày".
 */

const BUCKETS = ["0-7", "8-30", "31-90"] as const;

export function useFillText() {
  const t = useTranslations("components.fill");
  const { fmtNum } = useFmt();
  const pct = (v: number) => Math.round(v * 100);

  /** "≈72% (65–80%)", "≈72%"; null khi không có giá trị (chưa ước tính hoặc bị ẩn). */
  function fillText(r: Pick<FillReading, "value" | "low" | "high">): string | null {
    if (r.value === null) return null;
    if (r.low !== null && r.high !== null && pct(r.low) !== pct(r.high)) return t("range", { pct: pct(r.value), low: pct(r.low), high: pct(r.high) });
    return t("point", { pct: pct(r.value) });
  }

  /** Lý do ẩn: "sai số so PMS ±24 điểm ở 8–30 ngày". */
  function hiddenText(r: Pick<FillReading, "lead">): string {
    const mae = num(r.lead?.mean_abs_error_pts);
    return t("hiddenTitle", { bucket: t(`bucket.${(r.lead?.bucket ?? "0-7") as (typeof BUCKETS)[number]}`), mae: mae === null ? "—" : fmtNum(mae, 0) });
  }

  /** "sai số so PMS ±4 / ±9 / — điểm ở 0–7 / 8–30 / 31–90 ngày" hoặc "chưa hiệu chỉnh (chưa có PMS)". */
  function calibrationText(c: CalibrationOut | null | undefined): { text: string; calibrated: boolean } {
    const lead = c?.by_lead ?? [];
    if (!c || c.status !== "calibrated" || lead.every((x) => x.nights === 0)) {
      // Backend cũ chưa có by_lead: dùng sai số chung.
      const mae = num(c?.mean_abs_error_pts);
      if (c && c.nights > 0 && mae !== null && lead.length === 0) return { text: t("calibratedAll", { mae: fmtNum(mae, 1), count: c.nights }), calibrated: true };
      return { text: t("uncalibrated"), calibrated: false };
    }
    const values = BUCKETS.map((b) => {
      const x = lead.find((l) => l.bucket === b);
      const mae = num(x?.mean_abs_error_pts);
      return !x || x.nights === 0 || mae === null ? "—" : `±${fmtNum(mae, 0)}`;
    }).join(" / ");
    return { text: t("calibrated", { values }), calibrated: true };
  }

  /** Tooltip chi tiết từng nhóm: "0–7 ngày: ±4 điểm, lệch +2, 18 đêm". */
  function calibrationTitle(c: CalibrationOut | null | undefined): string {
    const lines = (c?.by_lead ?? []).map((x) => {
      const mae = num(x.mean_abs_error_pts);
      const bias = num(x.bias_pts);
      return x.nights === 0 || mae === null
        ? t("leadLineNone", { bucket: t(`bucket.${x.bucket as (typeof BUCKETS)[number]}`) })
        : t("leadLine", {
            bucket: t(`bucket.${x.bucket as (typeof BUCKETS)[number]}`),
            mae: fmtNum(mae, 1),
            bias: bias === null ? "—" : `${bias > 0 ? "+" : bias < 0 ? "−" : ""}${fmtNum(Math.abs(bias), 1)}`,
            count: x.nights,
            usable: x.usable ? "yes" : "no",
          });
    });
    return [t("calibrationInfo"), ...lines].join("\n");
  }

  return { fillText, hiddenText, calibrationText, calibrationTitle };
}

/** Giá trị chỉ báo của một đêm: "≈72% (65–80%)", "ẩn" (kèm lý do khi rê), hoặc "—". */
export function FillValue({ reading, className, hiddenClassName }: { reading: FillReading; className?: string; hiddenClassName?: string }) {
  const t = useTranslations("components.fill");
  const { fillText, hiddenText } = useFillText();
  if (reading.hidden) {
    return (
      <span className={cx("text-faint", hiddenClassName)} title={hiddenText(reading)}>
        {t("hidden")}
      </span>
    );
  }
  return <span className={className}>{fillText(reading) ?? "—"}</span>;
}

/** Dòng sai số so PMS theo nhóm lead time (hoặc "chưa hiệu chỉnh"). */
export function CalibrationNote({ calibration, className }: { calibration: CalibrationOut | null | undefined; className?: string }) {
  const { calibrationText, calibrationTitle } = useFillText();
  const c = calibrationText(calibration);
  return (
    <span className={cx(c.calibrated ? "text-body" : "text-warning-deep", className)} title={calibrationTitle(calibration)}>
      {c.text}
    </span>
  );
}
