"use client";

import { useTranslations } from "next-intl";
import type { MarketAreaOut } from "@/lib/api";
import { cx } from "./ui";

/**
 * Ô chọn khu vực thị trường gọn (cao 32px) cho đầu thẻ/đầu trang khi tenant có từ 2 khu vực đang
 * hoạt động. Lựa chọn và lưu trữ nằm ở `useMarketAreaChoice` (lib/market-area-choice.ts). Nơi dùng
 * đặt độ rộng tối đa qua `className` (vd. `max-w-[200px]`).
 */
export function AreaSelect({
  areas,
  value,
  onChange,
  className,
}: {
  areas: Array<Pick<MarketAreaOut, "id" | "name">>;
  value: number | undefined;
  onChange: (id: number) => void;
  className?: string;
}) {
  const t = useTranslations("components.areaSelect");
  return (
    <select
      aria-label={t("label")}
      title={t("label")}
      value={value ?? ""}
      onChange={(e) => onChange(Number(e.target.value))}
      className={cx(
        "sb-select h-8 min-w-0 cursor-pointer appearance-none truncate rounded-lg border border-line-strong bg-surface pl-2.5 pr-8 text-sm font-semibold normal-case tracking-normal text-ink transition-[border-color,box-shadow] duration-150 focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15",
        className,
      )}
    >
      {areas.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name}
        </option>
      ))}
    </select>
  );
}
