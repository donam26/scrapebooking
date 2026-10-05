/**
 * Kênh bán phòng (Booking.com, Agoda, iVIVU, Trip.com…): tên hiển thị, nhận diện URL, tên khách sạn
 * khi chưa quét xong và câu đọc cho tín hiệu cầu do kênh công bố.
 *
 * Số phòng còn luôn là của một kênh; không cộng giữa các kênh (D4).
 */
import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { ChannelOut, DemandSignalOut, HotelOut, ListingOut } from "./api";
import { num, prettySlug, useFmt, type Fmt } from "./format";
import { CHANNEL_LABEL } from "./labels";

export function channelName(code: string | null | undefined): string {
  if (!code) return "—";
  return CHANNEL_LABEL[code] ?? code;
}

const ORDER = Object.keys(CHANNEL_LABEL);

/** Bỏ trùng và xếp kênh theo thứ tự cố định (thị phần VN như backend), kênh lạ xếp cuối. */
export function sortChannels(codes: Iterable<string>): string[] {
  const rank = (c: string) => (ORDER.includes(c) ? ORDER.indexOf(c) : ORDER.length);
  return [...new Set(codes)].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** Kênh của một URL theo tên miền (chưa kiểm tra có phải trang một khách sạn không). */
export function detectChannel(raw: string, channels: ChannelOut[]): ChannelOut | null {
  let host: string;
  try {
    host = new URL(raw.trim()).hostname.toLowerCase();
  } catch {
    return null;
  }
  return channels.find((c) => c.hosts.some((d) => host === d || host.endsWith(`.${d}`))) ?? null;
}

/** Tên tạm từ khoá listing khi kênh chưa trả tên: "vn/meander-saigon" -> "Meander Saigon". */
export function listingKeyName(l: Pick<ListingOut, "channel" | "listing_key">): string {
  const parts = l.listing_key.split("/").filter(Boolean);
  // Agoda: "<slug>/hotel/<thành-phố>"; các kênh khác: slug ở đoạn cuối.
  const slug = l.channel === "agoda" ? parts[0] : parts[parts.length - 1];
  if (!slug || slug === "id" || /^\d+$/.test(slug)) return `${channelName(l.channel)} #${parts[parts.length - 1] ?? l.listing_key}`;
  return prettySlug(slug);
}

/** Tên hiển thị của khách sạn: nhãn của tenant → tên đã quét → tên trên một kênh → khoá listing. */
export function hotelTitle(hotel: HotelOut, label?: string | null): string {
  if (label) return label;
  if (hotel.name) return hotel.name;
  const named = hotel.listings.find((l) => l.name);
  if (named?.name) return named.name;
  const first = hotel.listings[0];
  return first ? listingKeyName(first) : `#${hotel.id}`;
}

/** Kênh đang quét được của khách sạn (listing đã kiểm tra). */
export function activeChannels(hotel: HotelOut): string[] {
  return hotel.listings.filter((l) => l.status === "active").map((l) => l.channel);
}

/** Gắn `?channel=` vào đường dẫn trong app để trang kế tiếp xem cùng kênh. */
export function withChannel(href: string, channel: string | null | undefined): string {
  if (!channel) return href;
  return `${href}${href.includes("?") ? "&" : "?"}channel=${encodeURIComponent(channel)}`;
}

/** Loại tín hiệu cầu đọc được thành câu; loại khác (VD điểm nội bộ của kênh) không hiện. */
const SHOWN_DEMAND = new Set(["bookings_24h", "bookings_today", "rooms_sold_24h", "bookings_month", "last_booked_minutes", "high_demand"]);

export function shownDemandSignals(signals: DemandSignalOut[]): DemandSignalOut[] {
  return signals.filter((s) => SHOWN_DEMAND.has(s.kind));
}

export type ChannelsTranslator = ReturnType<typeof useTranslations<"helpers.channels">>;

/**
 * Câu đọc cho tín hiệu cầu, không kèm nguồn: "đặt 13 lần trong 24 giờ qua".
 * Đây là thông điệp marketing của kênh, nên nơi hiển thị luôn ghi "Theo <kênh>".
 * Component: `const demandText = useDemandText();`. Ngoài React: `createDemandText(t, fmt)`.
 */
export function createDemandText(t: ChannelsTranslator, fmt: Fmt) {
  function windowText(hours: number): string {
    return hours >= 48 && hours % 24 === 0 ? t("windowDays", { count: hours / 24 }) : t("windowHours", { count: hours });
  }

  return (s: DemandSignalOut): string => {
    const v = num(s.value);
    const count = v === null ? 0 : Math.round(v);
    switch (s.kind) {
      case "bookings_24h":
        return t("bookingsWindow", { count, window: windowText(s.window_hours ?? 24) });
      case "bookings_today":
        return t("bookingsToday", { count });
      case "last_booked_minutes":
        return v !== null && v >= 60 ? t("lastBookedHours", { count: Math.round(v / 60) }) : t("lastBookedMinutes", { count });
      case "rooms_sold_24h":
        return t("roomsSold", { count, window: windowText(s.window_hours ?? 24) });
      case "bookings_month":
        return s.window_hours ? t("bookingsMonthWindow", { count, window: windowText(s.window_hours) }) : t("bookingsMonth", { count });
      case "high_demand":
        return s.stay_date ? t("highDemandNight", { night: fmt.fmtNight(s.stay_date) }) : t("highDemand");
      default:
        return `${s.kind} ${v === null ? s.value : fmt.fmtInt(count)}`;
    }
  };
}

export function useDemandText(): (s: DemandSignalOut) => string {
  const t = useTranslations("helpers.channels");
  const fmt = useFmt();
  return useMemo(() => createDemandText(t, fmt), [t, fmt]);
}
