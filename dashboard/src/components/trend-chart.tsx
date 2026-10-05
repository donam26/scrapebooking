"use client";

import { useTranslations } from "next-intl";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cx } from "./ui";

/**
 * Biểu đồ xu hướng nhiều đường (Recharts) theo mẫu OTARadar: đường cong mượt, lưới đứt nhạt,
 * tối đa hai trục y, tooltip liệt kê mọi đường, chú giải gạch màu bên dưới.
 */

export type TrendSeries = {
  key: string;
  name: string;
  color: string;
  dashed?: boolean;
  width?: number;
  /** Trục phải (ví dụ công suất %). */
  right?: boolean;
  /** Tô nền dưới đường. */
  area?: boolean;
  /** Nối qua điểm thiếu số (mặc định không, để không vẽ giá/công suất chưa quan sát). */
  connectNulls?: boolean;
};

export type TrendRow = { x: string } & Record<string, number | string | null>;

type Props = {
  data: TrendRow[];
  series: TrendSeries[];
  height?: number;
  formatX?: (x: string) => string;
  formatLeft?: (v: number) => string;
  formatRight?: (v: number) => string;
  /** Giá trị trong tooltip theo đường. */
  formatValue?: (v: number, s: TrendSeries) => string;
  leftDomain?: [number | "auto" | "dataMin" | "dataMax", number | "auto" | "dataMin" | "dataMax"];
  rightDomain?: [number, number];
  legend?: boolean;
  className?: string;
  emptyText?: string;
};

type TipPayload = { dataKey?: string | number; value?: number | string | null; color?: string };

function ChartTooltip({
  active,
  payload,
  label,
  series,
  formatX,
  formatValue,
}: {
  active?: boolean;
  payload?: readonly TipPayload[];
  label?: string | number;
  series: TrendSeries[];
  formatX?: (x: string) => string;
  formatValue?: (v: number, s: TrendSeries) => string;
}) {
  if (!active || !payload?.length) return null;
  const rows = payload
    .map((p) => ({ p, s: series.find((s) => s.key === p.dataKey) }))
    .filter((r): r is { p: TipPayload; s: TrendSeries } => r.s !== undefined && typeof r.p.value === "number")
    // Đường thị trường và khách sạn của bạn lên trước, còn lại theo giá trị giảm dần.
    .sort((a, b) => Number(b.p.value) - Number(a.p.value));
  return (
    <div className="min-w-[180px] rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-float">
      <div className="mb-1 font-semibold text-ink">{formatX ? formatX(String(label)) : label}</div>
      <ul className="space-y-0.5">
        {rows.map(({ p, s }) => (
          <li key={s.key} className="flex items-center justify-between gap-4">
            <span className="flex min-w-0 items-center gap-1.5 text-body">
              <span aria-hidden className="h-0.5 w-3 shrink-0 rounded" style={{ background: s.color }} />
              <span className="truncate">{s.name}</span>
            </span>
            <span className="font-semibold text-ink tabular">{formatValue ? formatValue(Number(p.value), s) : String(p.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Chú giải gạch màu (nét đứt cho đường đứt). */
export function TrendLegend({ series, className }: { series: TrendSeries[]; className?: string }) {
  return (
    <ul className={cx("flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs", className)}>
      {series.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5" style={{ color: s.color }}>
          <svg width="18" height="8" aria-hidden>
            <line x1="1" x2="17" y1="4" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "3 2" : undefined} strokeLinecap="round" />
            <circle cx="9" cy="4" r="2.5" fill="#fff" stroke={s.color} strokeWidth="1.5" />
          </svg>
          {s.name}
        </li>
      ))}
    </ul>
  );
}

export function TrendChart({
  data,
  series,
  height = 260,
  formatX,
  formatLeft,
  formatRight,
  formatValue,
  leftDomain = ["auto", "auto"],
  rightDomain = [0, 100],
  legend = true,
  className,
  emptyText,
}: Props) {
  const t = useTranslations("common.status");
  const hasRight = series.some((s) => s.right);
  const hasData = data.some((row) => series.some((s) => typeof row[s.key] === "number"));
  if (!hasData) {
    return (
      <div className={cx("grid place-items-center rounded-lg bg-subtle text-sm text-muted", className)} style={{ height }}>
        {emptyText ?? t("noData")}
      </div>
    );
  }
  return (
    <div className={className}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: hasRight ? 4 : 12, bottom: 0, left: 4 }}>
            <CartesianGrid stroke="#eceef3" strokeDasharray="3 3" />
            <XAxis
              dataKey="x"
              tickFormatter={formatX}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#d3d8e2" }}
              minTickGap={14}
            />
            <YAxis
              yAxisId="left"
              tickFormatter={formatLeft}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              tickLine={false}
              axisLine={{ stroke: "#d3d8e2" }}
              width={58}
              domain={leftDomain}
            />
            {hasRight && (
              <YAxis
                yAxisId="right"
                orientation="right"
                tickFormatter={formatRight}
                tick={{ fontSize: 11, fill: "#6b7280" }}
                tickLine={false}
                axisLine={{ stroke: "#d3d8e2" }}
                width={44}
                domain={rightDomain}
              />
            )}
            <Tooltip
              cursor={{ stroke: "#9ca3af", strokeDasharray: "3 3" }}
              content={(props) => (
                <ChartTooltip
                  active={props.active}
                  payload={props.payload as unknown as TipPayload[] | undefined}
                  label={props.label as string | number | undefined}
                  series={series}
                  formatX={formatX}
                  formatValue={formatValue}
                />
              )}
            />
            {series.map((s) =>
              s.area ? (
                <Area
                  key={s.key}
                  yAxisId={s.right ? "right" : "left"}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name}
                  stroke={s.color}
                  strokeWidth={s.width ?? 2}
                  strokeDasharray={s.dashed ? "6 4" : undefined}
                  fill={s.color}
                  fillOpacity={0.08}
                  connectNulls={s.connectNulls ?? false}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              ) : (
                <Line
                  key={s.key}
                  yAxisId={s.right ? "right" : "left"}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name}
                  stroke={s.color}
                  strokeWidth={s.width ?? 2}
                  strokeDasharray={s.dashed ? "6 4" : undefined}
                  connectNulls={s.connectNulls ?? false}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              ),
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {legend && <TrendLegend series={series} className="mt-2" />}
    </div>
  );
}

/** Đường nhỏ không trục (thẻ đối thủ): xu hướng giá vài tuần tới. */
export function Sparkline({ values, color, height = 40 }: { values: Array<number | null>; color: string; height?: number }) {
  const data = values.map((v, i) => ({ x: String(i), v }));
  if (!values.some((v) => v !== null)) return <div style={{ height }} className="rounded bg-subtle" />;
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 4, right: 2, bottom: 4, left: 2 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
