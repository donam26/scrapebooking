"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type ChannelOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useLabel } from "@/lib/labels";
import { hotelTitle, isBookingUrl } from "@/lib/hotels";
import { Button, ErrorBox, Field, Input, Segmented, cx } from "./ui";
import { IconCheck, IconClose, IconLink, IconPlus, IconSearch } from "./icons";

/**
 * "Thêm khách sạn" ngay tại trang Đối thủ / Tìm khách sạn (không chuyển sang Cài đặt): dán đường dẫn
 * Booking.com, chọn vai trò, nhãn tuỳ chọn. Cùng API và cùng câu báo lỗi với Cài đặt › Khách sạn & đối thủ
 * (`settings.watchlist`). `<dialog>` gốc của trình duyệt: Esc để đóng, focus nằm trong hộp.
 */

type Role = "self" | "competitor";
const ROLES: Role[] = ["competitor", "self"];

type WatchlistT = ReturnType<typeof useTranslations<"settings.watchlist">>;

function urlProblem(raw: string, channels: ChannelOut[], t: WatchlistT): string | null {
  const v = raw.trim();
  if (!v) return t("url.empty");
  try {
    new URL(v);
  } catch {
    return t("url.malformed");
  }
  if (channels.length > 0 && !isBookingUrl(v, channels)) return t("url.notBooking");
  return null;
}

function AddHotelForm({ initialUrl, defaultRole, onAdded, onClose, showExplore }: { initialUrl: string; defaultRole: Role; onAdded?: () => void; onClose: () => void; showExplore: boolean }) {
  const t = useTranslations("settings.watchlist");
  const td = useTranslations("components.addHotel");
  const labelOf = useLabel();
  const channels = useApi("channels", () => api.channels()).data ?? [];
  const [url, setUrl] = useState(initialUrl);
  const [role, setRole] = useState<Role>(defaultRole);
  const [label, setLabel] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const add = useMutation(async () => {
    const item = await api.watchlist.add({ url: url.trim(), role, label: label.trim() || null });
    setAdded(hotelTitle(item.hotel, item.label));
    setUrl("");
    setLabel("");
    onAdded?.();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    const p = urlProblem(url, channels, t);
    setProblem(p);
    setAdded(null);
    if (!p) void add.run();
  }
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Field label={t("add.urlLabel")} htmlFor="add-hotel-url" hint={td("urlHint")}>
        <div className="relative">
          <IconLink size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <Input
            id="add-hotel-url"
            type="url"
            inputMode="url"
            autoComplete="off"
            autoFocus={!initialUrl}
            placeholder={t("add.urlPlaceholder")}
            value={url}
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? "add-hotel-url-problem" : undefined}
            onChange={(e) => {
              setUrl(e.target.value);
              if (problem) setProblem(null);
            }}
            className={cx("pl-9", problem && "border-danger focus:border-danger focus:ring-danger/15")}
          />
        </div>
      </Field>
      {problem && (
        <p id="add-hotel-url-problem" role="alert" className="-mt-2 text-sm text-danger">
          {problem}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="text-sm font-semibold text-body">{t("add.role")}</span>
          <Segmented label={t("add.role")} value={role} onChange={setRole} items={ROLES.map((r) => ({ value: r, label: labelOf("watchRole", r) }))} className="self-start" />
        </div>
        <Field label={t("add.labelField")} htmlFor="add-hotel-label" className="min-w-[180px] flex-1">
          <Input id="add-hotel-label" maxLength={120} placeholder={t("add.labelPlaceholder")} value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
      </div>
      <ErrorBox error={add.error} title={t("add.errorTitle")} />
      {added && !add.error && (
        <p role="status" className="flex items-start gap-1.5 text-sm text-yours-deep">
          <IconCheck size={16} className="mt-0.5 shrink-0" />
          <span>{t("add.added", { name: added })}</span>
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        {showExplore ? (
          <Link href="/competitors/market" className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline" onClick={onClose}>
            <IconSearch size={15} /> {td("explore")}
          </Link>
        ) : (
          <span />
        )}
        <span className="flex gap-2">
          <Button type="button" onClick={onClose}>
            {added ? td("done") : td("cancel")}
          </Button>
          <Button type="submit" variant="primary" busy={add.busy} icon={<IconPlus size={16} />}>
            {t("add.submit")}
          </Button>
        </span>
      </div>
    </form>
  );
}

export function AddHotelDialog({
  open,
  onClose,
  onAdded,
  initialUrl = "",
  title,
  hasSelf = true,
  showExplore = true,
}: {
  open: boolean;
  onClose: () => void;
  onAdded?: () => void;
  /** Đường dẫn điền sẵn (nút "Theo dõi" ở Tìm khách sạn). */
  initialUrl?: string;
  /** Tiêu đề hộp; mặc định "Thêm khách sạn". */
  title?: string;
  /** Tenant đã có khách sạn của mình: vai trò mặc định là đối thủ. */
  hasSelf?: boolean;
  /** Link "Tìm trong khu vực" sang Tìm khách sạn để theo dõi. */
  showExplore?: boolean;
}) {
  const td = useTranslations("components.addHotel");
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby="add-hotel-title"
      onClose={onClose}
      onClick={(e) => {
        // Bấm ra nền mờ ngoài hộp thì đóng.
        if (e.target === e.currentTarget) onClose();
      }}
      className="m-auto w-[min(560px,calc(100vw-24px))] max-w-none rounded-xl border border-line bg-surface p-0 text-ink shadow-[0_20px_50px_rgba(17,24,39,0.25)] backdrop:bg-[rgba(17,24,39,0.45)]"
    >
      {open && (
        <div className="p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 id="add-hotel-title" className="text-md font-bold text-ink">
                {title ?? td("title")}
              </h2>
              <p className="mt-1 text-sm text-muted">{td("description")}</p>
            </div>
            <button type="button" onClick={onClose} aria-label={td("close")} className="-mr-1.5 -mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted hover:bg-subtle hover:text-ink">
              <IconClose size={18} />
            </button>
          </div>
          <AddHotelForm key={initialUrl} initialUrl={initialUrl} defaultRole={hasSelf || initialUrl ? "competitor" : "self"} onAdded={onAdded} onClose={onClose} showExplore={showExplore} />
        </div>
      )}
    </dialog>
  );
}
