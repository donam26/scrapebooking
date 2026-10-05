/**
 * Đồng hồ đo kiểu OTARadar: nửa vòng (mức nén compset) và vòng tròn (chỉ báo thị trường).
 * `value` là 0–100; null vẽ vòng xám và dấu "—".
 */

import { useTranslations } from "next-intl";

const TRACK = "var(--sb-line)";

/** Nửa vòng cung, số ở giữa, nhãn mức bên dưới. */
export function ArcGauge({ value, color, caption, size = 120 }: { value: number | null; color: string; caption?: string; size?: number }) {
  const t = useTranslations();
  const stroke = 12;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const len = Math.PI * r;
  const v = value === null ? 0 : Math.max(0, Math.min(100, value));
  const arc = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size / 2 + stroke / 2 + 2} viewBox={`0 0 ${size} ${size / 2 + stroke / 2 + 2}`} role="img" aria-label={value === null ? t("common.status.noData") : t("components.gauge.outOf100", { value: Math.round(v) })}>
        <path d={arc} fill="none" stroke={TRACK} strokeWidth={stroke} strokeLinecap="round" />
        {value !== null && v > 0 && <path d={arc} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${(v / 100) * len} ${len}`} />}
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize={size * 0.2} fontWeight={700} fill={value === null ? "var(--sb-faint)" : color} className="tabular">
          {value === null ? "—" : Math.round(v)}
        </text>
      </svg>
      {caption && (
        <div className="-mt-0.5 text-sm font-semibold" style={{ color: value === null ? "var(--sb-faint)" : color }}>
          {caption}
        </div>
      )}
    </div>
  );
}

/** Vòng tròn đầy với phần trăm ở giữa (chỉ báo thị trường). */
export function RingGauge({ value, color, unit = "%", sub, size = 108 }: { value: number | null; color: string; unit?: string; sub?: string; size?: number }) {
  const stroke = 9;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={TRACK} strokeWidth={stroke} />
        {value !== null && v > 0 && (
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${(v / 100) * c} ${c}`} />
        )}
      </svg>
      <div className="absolute inset-0 grid place-content-center text-center">
        <div className="text-[26px] font-bold leading-none tabular" style={{ color: value === null ? "var(--sb-faint)" : color }}>
          {value === null ? "—" : `${Math.round(v)}${unit}`}
        </div>
        {sub && <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-faint">{sub}</div>}
      </div>
    </div>
  );
}
