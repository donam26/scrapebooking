"use client";

import { useId, useState } from "react";
import { cx } from "./ui";

/** Bảng màu phân loại đã kiểm tra CVD (thứ tự cố định, không xoay vòng). */
export const SERIES_COLORS = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#4a3aa7",
  "#e34948",
] as const;

export type Point = { x: number; y: number };
export type Series = { id: string | number; name: string; points: Point[] };

type Props = {
  series: Series[];
  height?: number;
  formatY?: (v: number) => string;
  formatX?: (v: number) => string;
  /** Trục y bắt đầu từ 0 (số phòng) hay tự co theo dữ liệu (giá). */
  zeroBased?: boolean;
  emptyText?: string;
  className?: string;
};

const W = 720;
const PAD = { top: 12, right: 16, bottom: 28, left: 56 };

function niceTicks(min: number, max: number, count = 4): number[] {
  if (max <= min) return [min];
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + 1e-9; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

/**
 * Biểu đồ đường SVG tối giản: 2px, điểm >= 8px với vòng nền, lưới mảnh,
 * legend luôn có khi >= 2 series, tooltip khi rê chuột.
 */
export function LineChart({ series, height = 200, formatY = (v) => String(v), formatX = (v) => String(v), zeroBased = false, emptyText = "Chưa có dữ liệu", className }: Props) {
  const id = useId();
  const [hover, setHover] = useState<{ si: number; pi: number } | null>(null);
  const visible = series.filter((s) => s.points.length > 0);
  if (visible.length === 0) {
    return <div className={cx("flex items-center justify-center text-sm text-slate-500", className)} style={{ height }}>{emptyText}</div>;
  }
  const xs = visible.flatMap((s) => s.points.map((p) => p.x));
  const ys = visible.flatMap((s) => s.points.map((p) => p.y));
  let xMin = Math.min(...xs);
  let xMax = Math.max(...xs);
  if (xMax === xMin) {
    xMin -= 1;
    xMax += 1;
  }
  let yMin = zeroBased ? 0 : Math.min(...ys);
  let yMax = Math.max(...ys);
  if (yMax === yMin) {
    yMax = yMin + 1;
    if (!zeroBased) yMin -= 1;
  }
  const ticks = niceTicks(yMin, yMax);
  if (ticks.length) {
    yMin = Math.min(yMin, ticks[0]);
    yMax = Math.max(yMax, ticks[ticks.length - 1]);
  }
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const sx = (x: number) => PAD.left + ((x - xMin) / (xMax - xMin)) * plotW;
  const sy = (y: number) => PAD.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

  const xTickCount = Math.min(6, Math.max(2, Math.round(plotW / 120)));
  const xTicks = Array.from({ length: xTickCount }, (_, i) => xMin + ((xMax - xMin) * i) / (xTickCount - 1));

  const hovered = hover ? visible[hover.si]?.points[hover.pi] : undefined;

  return (
    <div className={cx("relative", className)}>
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img" aria-labelledby={`${id}-title`}>
        <title id={`${id}-title`}>{visible.map((s) => s.name).join(", ")}</title>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(t)} y2={sy(t)} stroke="#e5e7eb" strokeWidth={1} />
            <text x={PAD.left - 6} y={sy(t)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="#6b7280" className="tabular">
              {formatY(t)}
            </text>
          </g>
        ))}
        <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + plotH} y2={PAD.top + plotH} stroke="#cbd5e1" strokeWidth={1} />
        {xTicks.map((t, i) => (
          <text key={i} x={sx(t)} y={height - 8} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"} fontSize={11} fill="#6b7280">
            {formatX(t)}
          </text>
        ))}
        {visible.map((s, si) => {
          const color = SERIES_COLORS[si % SERIES_COLORS.length];
          const d = s.points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
          return (
            <g key={s.id}>
              <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {s.points.map((p, pi) => {
                const active = hover?.si === si && hover.pi === pi;
                return (
                  <g key={pi}>
                    <circle cx={sx(p.x)} cy={sy(p.y)} r={active ? 6 : 4} fill={color} stroke="#fff" strokeWidth={2} />
                    <circle
                      cx={sx(p.x)}
                      cy={sy(p.y)}
                      r={12}
                      fill="transparent"
                      onMouseEnter={() => setHover({ si, pi })}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover({ si, pi })}
                      onBlur={() => setHover(null)}
                      tabIndex={0}
                      aria-label={`${s.name}: ${formatY(p.y)} lúc ${formatX(p.x)}`}
                    />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      {hovered && hover && (
        <div
          className="pointer-events-none absolute z-10 rounded border border-line bg-white px-2 py-1 text-xs shadow-md"
          style={{ left: `${(sx(hovered.x) / W) * 100}%`, top: `${(sy(hovered.y) / height) * 100}%`, transform: "translate(-50%, -120%)" }}
        >
          <div className="font-medium text-slate-800">{visible[hover.si].name}</div>
          <div className="text-slate-600">
            {formatY(hovered.y)} · {formatX(hovered.x)}
          </div>
        </div>
      )}
      {visible.length >= 2 && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
          {visible.map((s, si) => (
            <li key={s.id} className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-4 rounded" style={{ background: SERIES_COLORS[si % SERIES_COLORS.length] }} />
              {s.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
