"use client";

import { useTranslations } from "next-intl";
import type { WeatherOut } from "@/lib/api";
import { useFmt } from "@/lib/format";
import { Card } from "@/components/ui";

/** Biểu tượng thời tiết theo mã icon OpenWeather (không tải ảnh ngoài). */
function weatherEmoji(icon: string): string {
  const code = icon.slice(0, 2);
  return { "01": "☀️", "02": "🌤️", "03": "⛅", "04": "☁️", "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "❄️", "50": "🌫️" }[code] ?? "🌡️";
}

/**
 * Dự báo 5 ngày tại khách sạn. Chỉ hiện khi có dự báo: chưa cấu hình khoá, lỗi hay chưa có số thì
 * không hiện gì (Q8; operator xem cấu hình ở trang sức khoẻ, tenant không thấy tên biến môi trường).
 */
export function WeatherCard({ data }: { data: WeatherOut | undefined }) {
  const t = useTranslations("marketTab.weather");
  const { fmtWeekday } = useFmt();
  if (!data?.configured || data.error || !data.current) return null;
  const current = data.current;
  return (
    <Card className="h-full" title={t("title")} info={t("info")}>
      <div className="flex items-center justify-center gap-3">
        <span className="text-[40px] leading-none" aria-hidden>
          {weatherEmoji(current.icon)}
        </span>
        <div>
          <div className="text-[30px] font-bold leading-none text-ink tabular">{Math.round(current.temp)}°C</div>
          <div className="mt-1 text-sm capitalize text-muted">{current.description}</div>
        </div>
      </div>
      <div className="mt-1 text-center text-xs text-muted">
        {data.location ? `${data.location} · ` : ""}
        {t("current", { feels: Math.round(current.feels_like), humidity: current.humidity })}
      </div>
      <ul className="mt-4 grid grid-cols-5 gap-1 border-t border-line pt-3 text-center">
        {data.days.slice(0, 5).map((d, i) => (
          <li key={d.date} title={i === 0 ? t("restOfToday", { description: d.description }) : d.description}>
            <div className="text-[11px] font-semibold uppercase text-muted">{i === 0 ? t("today") : fmtWeekday(d.date)}</div>
            <div className="my-0.5 text-lg" aria-hidden>
              {weatherEmoji(d.icon)}
            </div>
            <div className="text-xs font-semibold text-ink tabular">{Math.round(d.temp_max)}°</div>
            <div className="text-[11px] text-muted tabular">{Math.round(d.temp_min)}°</div>
            {d.pop >= 0.3 && <div className="text-[10px] font-semibold text-brand tabular">{Math.round(d.pop * 100)}%</div>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
