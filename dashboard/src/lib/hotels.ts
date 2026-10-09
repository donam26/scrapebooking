/**
 * Khách sạn trên Booking.com (nguồn dữ liệu duy nhất): tên hiển thị, nhận diện URL và tên khách sạn
 * khi chưa quét xong.
 */
import type { ChannelOut, HotelOut, ListingOut } from "./api";
import { prettySlug } from "./format";

/** Tên nguồn dữ liệu (khớp `app/channels/registry.py`). */
export const BOOKING = "Booking.com";

/**
 * URL thuộc Booking.com theo tên miền (`GET /channels`: `hosts`); chưa kiểm tra có phải trang một
 * khách sạn không.
 */
export function isBookingUrl(raw: string, channels: ChannelOut[]): boolean {
  let host: string;
  try {
    host = new URL(raw.trim()).hostname.toLowerCase();
  } catch {
    return false;
  }
  return channels.some((c) => c.hosts.some((d) => host === d || host.endsWith(`.${d}`)));
}

/** Tên tạm từ khoá listing khi chưa quét được tên: "vn/meander-saigon" -> "Meander Saigon". */
export function listingKeyName(l: Pick<ListingOut, "listing_key">): string {
  const parts = l.listing_key.split("/").filter(Boolean);
  const slug = parts[parts.length - 1];
  if (!slug || slug === "id" || /^\d+$/.test(slug)) return `${BOOKING} #${slug ?? l.listing_key}`;
  return prettySlug(slug);
}

/** Tên hiển thị của khách sạn: nhãn của tenant → tên đã quét → tên trên Booking.com → khoá listing. */
export function hotelTitle(hotel: HotelOut, label?: string | null): string {
  if (label) return label;
  if (hotel.name) return hotel.name;
  const named = hotel.listings.find((l) => l.name);
  if (named?.name) return named.name;
  const first = hotel.listings[0];
  return first ? listingKeyName(first) : `#${hotel.id}`;
}
