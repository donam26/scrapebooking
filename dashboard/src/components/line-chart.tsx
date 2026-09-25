"use client";

import { useId, useRef, useState } from "react";
import { useElementWidth } from "@/lib/use-width";
import { cx } from "./ui";

/**
 * Bảng màu phân loại đã chạy validate_palette (CVD, độ sáng, độ bão hoà), thứ tự cố định theo loại phòng.
 * Không dùng xanh lá (dành cho khách sạn của bạn) và vàng (dành cho số phòng chính xác).
 */
export const SERIES_COLORS = [
  "#2a78d6",
  "#e0662a",
  "#9c3d8f",
  "#1596b8",
  "#a8601c",
  "#ef7fae",
  "#4a5cc4",
  "#c8352b",
] as const;

/** `floor`: giá trị là mức sàn (“ít nhất”), vẽ bằng chấm rỗng để không nói quá mức tin cậy. */
export type Point = { x: number; y: number; floor?: boolean };
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

const PAD = { top: 14, right: 16, bottom: 28, left: 56 };

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
 * Biểu đồ đường SVG: nét 2px, điểm ≥ 8px có vòng nền, lưới mảnh, một trục y,
 * chú giải luôn có khi ≥ 2 series, rê chuột hiện tooltip.
 */
export function LineChart({ series, height = 220, formatY = (v) => String(v), formatX = (v) => String(v), zeroBased = false, emptyText = "Chưa có dữ liệu", className }: Props) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  // Vẽ theo chiều rộng thật để chữ trục giữ đúng cỡ trên mọi màn hình.
  const W = Math.max(280, useElementWidth(ref) || 640);
  const [hover, setHover] = useState<{ si: number; pi: number } | null>(null);
  const visible = series.filter((s) => s.points.length > 0);
  if (visible.length === 0) {
    return (
      <div ref={ref} className={cx("flex items-center justify-center rounded-lg bg-subtle px-4 text-center text-base text-muted", className)} style={{ height }}>
        {emptyText}
      </div>
    );
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
  const anyFloor = visible.some((s) => s.points.some((p) => p.floor));

  return (
    <div ref={ref} className={cx("relative", className)}>
      <svg width={W} height={height} viewBox={`0 0 ${W} ${height}`} className="block max-w-full overflow-visible" role="img" aria-labelledby={`${id}-title`}>
        <title id={`${id}-title`}>{visible.map((s) => s.name).join(", ")}</title>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(t)} y2={sy(t)} stroke="#ece9f7" strokeWidth={1} />
            <text x={PAD.left - 8} y={sy(t)} textAnchor="end" dominantBaseline="middle" fontSize={11} fontWeight={600} fill="#5e6072" style={{ fontVariantNumeric: "tabular-nums" }}>
              {formatY(t)}
            </text>
          </g>
        ))}
        <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + plotH} y2={PAD.top + plotH} stroke="#cfcce4" strokeWidth={1} />
        {xTicks.map((t, i) => (
          <text key={i} x={sx(t)} y={height - 8} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"} fontSize={11} fill="#5e6072" style={{ fontVariantNumeric: "tabular-nums" }}>
            {formatX(t)}
          </text>
        ))}
        {hovered && <line x1={sx(hovered.x)} x2={sx(hovered.x)} y1={PAD.top} y2={PAD.top + plotH} stroke="#673de6" strokeOpacity={0.3} strokeDasharray="3 3" />}
        {visible.map((s, si) => {
          const color = SERIES_COLORS[si % SERIES_COLORS.length];
          const d = s.points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
          const dim = hover !== null && hover.si !== si;
          return (
            <g key={s.id} opacity={dim ? 0.35 : 1} style={{ transition: "opacity .15s" }}>
              <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {s.points.map((p, pi) => {
                const active = hover?.si === si && hover.pi === pi;
                return (
                  <g key={pi}>
                    <circle cx={sx(p.x)} cy={sy(p.y)} r={active ? 6 : 4} fill={p.floor ? "#fff" : color} stroke={p.floor ? color : "#fff"} strokeWidth={2} />
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
                      aria-label={`${s.name}: ${p.floor ? "ít nhất " : ""}${formatY(p.y)} lúc ${formatX(p.x)}`}
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
          className="pointer-events-none absolute z-10 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-float"
          style={{ left: `${(sx(hovered.x) / W) * 100}%`, top: `${(sy(hovered.y) / height) * 100}%`, transform: "translate(-50%, calc(-100% - 10px))" }}
        >
          <div className="flex items-center gap-1.5 font-semibold text-ink">
            <span className="h-2 w-2 rounded-full" style={{ background: SERIES_COLORS[hover.si % SERIES_COLORS.length] }} />
            {visible[hover.si].name}
          </div>
          <div className="text-muted tabular">
            {hovered.floor ? "Ít nhất " : ""}
            <span className="font-semibold text-ink">{formatY(hovered.y)}</span> · {formatX(hovered.x)}
          </div>
        </div>
      )}
      {(visible.length >= 2 || anyFloor) && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted">
          {visible.length >= 2 &&
            visible.map((s, si) => (
              <li key={s.id} className="flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-4 rounded" style={{ background: SERIES_COLORS[si % SERIES_COLORS.length] }} />
                {s.name}
              </li>
            ))}
          {anyFloor && (
            <li className="flex items-center gap-1.5">
              <svg width="12" height="12" aria-hidden>
                <circle cx="6" cy="6" r="4" fill="#fff" stroke="#5e6072" strokeWidth="2" />
              </svg>
              Chấm rỗng: ít nhất (số thật có thể cao hơn)
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
