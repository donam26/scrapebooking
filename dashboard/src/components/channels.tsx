"use client";

import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import type { DemandSignalOut, ListingOut } from "@/lib/api";
import { channelName, shownDemandSignals, useDemandText } from "@/lib/channels";
import { useFmt } from "@/lib/format";
import { useLabel, type LabelFn } from "@/lib/labels";
import { IconExternal, IconTrend } from "./icons";
import { Segmented, cx } from "./ui";

/** Kênh đang xem trong URL (`?channel=`); null = để server chọn kênh tham chiếu của tenant. */
export function useChannelParam(): [string | null, (next: string) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("channel");
  const value = raw && /^[a-z]+$/.test(raw) ? raw : null;
  function set(next: string) {
    const q = new URLSearchParams(params.toString());
    q.set("channel", next);
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
  }
  return [value, set];
}

/**
 * Chọn kênh đang xem. Số phòng còn là của từng kênh nên mỗi lần chỉ xem một kênh, không cộng.
 * Chỉ hiện khi có từ hai kênh trở lên.
 */
export function ChannelSwitcher({ channels, value, onChange, className }: { channels: string[]; value: string; onChange: (c: string) => void; className?: string }) {
  const t = useTranslations("components.channels");
  if (channels.length < 2) return null;
  return (
    <div className={cx("sb-scroll max-w-full overflow-x-auto", className)}>
      <Segmented label={t("switcher")} value={value} onChange={onChange} items={channels.map((c) => ({ value: c, label: channelName(c), title: t("switcherTitle", { channel: channelName(c) }) }))} />
    </div>
  );
}

const STATUS_DOT: Record<string, string> = {
  active: "bg-yours",
  unverified: "bg-brand animate-pulse",
  suggested: "bg-brand",
  broken: "bg-danger",
  paused: "bg-faint",
};

type ChannelsTranslator = ReturnType<typeof useTranslations<"components.channels">>;

/** Câu trạng thái ngắn của một listing; listing đang quét thì không cần chữ. */
export function listingStatusText(l: ListingOut, t: ChannelsTranslator, label: LabelFn): string | null {
  if (l.status === "active") return null;
  if (l.status === "suggested") {
    // match_score 0..1: độ giống tên + khoảng cách toạ độ.
    const score = l.match_score === null ? NaN : Math.round(Number(l.match_score) * 100);
    return Number.isFinite(score) ? t("suggestedMatch", { score }) : label("listingStatus", "suggested");
  }
  return label("listingStatus", l.status);
}

/**
 * Chip một kênh của khách sạn: chấm trạng thái, tên kênh (mở trang trên kênh), trạng thái nếu
 * khác "đang quét", và các thao tác truyền vào (`children`).
 */
export function ListingChip({ listing, children, className }: { listing: ListingOut; children?: ReactNode; className?: string }) {
  const t = useTranslations("components.channels");
  const label = useLabel();
  const status = listingStatusText(listing, t, label);
  const suggested = listing.status === "suggested";
  return (
    <li
      className={cx(
        "inline-flex h-8 max-w-full items-center gap-1.5 rounded-lg border pl-2.5 text-sm",
        children ? "pr-1" : "pr-2.5",
        suggested ? "border-brand-soft bg-brand-softer" : "border-line bg-surface",
        listing.status === "paused" && "text-faint",
        className,
      )}
    >
      <span aria-hidden className={cx("h-1.5 w-1.5 shrink-0 rounded-full", STATUS_DOT[listing.status] ?? "bg-faint")} />
      <a
        href={listing.url}
        target="_blank"
        rel="noreferrer"
        title={t("openOnChannel", { channel: channelName(listing.channel) })}
        className={cx("inline-flex shrink-0 items-center gap-1 rounded-sm font-semibold hover:text-brand hover:underline", listing.status === "paused" ? "text-muted" : "text-ink")}
      >
        <span>{channelName(listing.channel)}</span>
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

/** Nút chữ nhỏ trong chip kênh. */
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

/** Các kênh của khách sạn ở dạng chỉ đọc (trang chi tiết): bỏ qua gợi ý chưa xác nhận. */
export function ListingChips({ listings, className }: { listings: ListingOut[]; className?: string }) {
  const t = useTranslations("components.channels");
  const shown = listings.filter((l) => l.status !== "suggested");
  if (shown.length === 0) return null;
  return (
    <ul aria-label={t("tracked")} className={cx("flex flex-wrap items-center gap-1.5", className)}>
      {shown.map((l) => (
        <ListingChip key={l.id} listing={l} />
      ))}
    </ul>
  );
}

/**
 * Tín hiệu cầu do kênh tự công bố ("Theo Agoda: đặt 13 lần trong 24 giờ qua"). Đây là thông điệp
 * marketing của kênh, độ tin cậy thấp: luôn ghi nguồn, không đưa vào chỉ số giá.
 */
export function DemandSignals({ signals: all, isOperator, className, title: titleProp }: { signals: DemandSignalOut[]; isOperator?: boolean; className?: string; title?: string }) {
  const t = useTranslations("components.channels");
  const { fmtAgo } = useFmt();
  const demandText = useDemandText();
  const title = titleProp ?? t("demandTitle");
  const signals = shownDemandSignals(all);
  if (signals.length === 0) return null;
  return (
    <section className={cx("rounded-xl border border-line bg-surface px-5 py-3.5 shadow-card", className)} aria-label={title}>
      <h2 className="flex items-center gap-2 text-md font-bold text-ink">
        <IconTrend size={16} className="text-muted" />
        {title}
      </h2>
      <ul className="mt-2 space-y-1.5">
        {signals.map((s) => (
          <li key={`${s.channel}-${s.kind}-${s.stay_date ?? ""}`} className="flex flex-wrap items-baseline gap-x-2 text-base" title={isOperator && s.raw_text ? s.raw_text : undefined}>
            <span className="text-body">
              <span className="font-semibold text-ink">{t("demandSource", { channel: channelName(s.channel) })}</span> {demandText(s)}
            </span>
            <span className="text-xs text-muted">{fmtAgo(s.observed_at)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">{t("demandNote")}</p>
    </section>
  );
}
