"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import type { ListingOut } from "@/lib/api";
import { BOOKING } from "@/lib/hotels";
import { useLabel } from "@/lib/labels";
import { IconExternal } from "./icons";
import { cx } from "./ui";

const STATUS_DOT: Record<string, string> = {
  active: "bg-yours",
  unverified: "bg-brand animate-pulse",
  broken: "bg-danger",
  paused: "bg-faint",
};

/**
 * Chip trang Booking.com của khách sạn: chấm trạng thái, "Booking.com" (mở trang khách sạn), trạng
 * thái nếu khác "đang quét", và các thao tác truyền vào (`children`).
 */
export function ListingChip({ listing, children, className }: { listing: ListingOut; children?: ReactNode; className?: string }) {
  const t = useTranslations("components.listing");
  const label = useLabel();
  const status = listing.status === "active" ? null : label("listingStatus", listing.status);
  return (
    <li
      className={cx(
        "inline-flex h-8 max-w-full items-center gap-1.5 rounded-lg border border-line bg-surface pl-2.5 text-sm",
        children ? "pr-1" : "pr-2.5",
        listing.status === "paused" && "text-faint",
        className,
      )}
    >
      <span aria-hidden className={cx("h-1.5 w-1.5 shrink-0 rounded-full", STATUS_DOT[listing.status] ?? "bg-faint")} />
      <a
        href={listing.url}
        target="_blank"
        rel="noreferrer"
        title={t("open")}
        className={cx("inline-flex shrink-0 items-center gap-1 rounded-sm font-semibold hover:text-brand hover:underline", listing.status === "paused" ? "text-muted" : "text-ink")}
      >
        <span>{BOOKING}</span>
        <IconExternal size={12} className="shrink-0 text-muted" />
      </a>
      {status && (
        <span className={cx("min-w-0 truncate", listing.status === "broken" ? "font-semibold text-danger-deep" : "text-muted")} title={status}>
          · {status}
        </span>
      )}
      {children}
    </li>
  );
}

/** Nút chữ nhỏ trong chip. */
export function ChipAction({ children, onClick, busy, tone = "brand", label, title }: { children: ReactNode; onClick: () => void; busy?: boolean; tone?: "brand" | "muted"; label?: string; title?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      aria-busy={busy || undefined}
      aria-label={label}
      title={title}
      className={cx(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-md px-1.5 text-xs font-semibold transition-colors duration-150 disabled:cursor-wait disabled:opacity-60",
        tone === "brand" ? "text-brand hover:bg-brand-soft hover:text-brand-hover" : "text-muted hover:bg-sunken hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

/** Trang Booking.com của khách sạn ở dạng chỉ đọc (trang chi tiết). */
export function ListingChips({ listings, className }: { listings: ListingOut[]; className?: string }) {
  const t = useTranslations("components.listing");
  if (listings.length === 0) return null;
  return (
    <ul aria-label={t("tracked")} className={cx("flex flex-wrap items-center gap-1.5", className)}>
      {listings.map((l) => (
        <ListingChip key={l.id} listing={l} />
      ))}
    </ul>
  );
}
