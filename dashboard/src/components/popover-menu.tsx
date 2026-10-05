"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "./ui";

/**
 * Nút mở một bảng nổi (menu chuông, trợ giúp, tài khoản trên thanh trên).
 * Mở ra thì focus vào phần tử bấm được đầu tiên; đóng khi bấm ra ngoài, Tab ra ngoài, nhấn Esc
 * (focus trở về nút) hoặc khi nội dung gọi `close()`.
 */
export function PopoverMenu({
  label,
  button,
  children,
  align = "right",
  width = 320,
  buttonClassName,
}: {
  /** Nhãn cho trình đọc màn hình. */
  label: string;
  button: ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  width?: number;
  buttonClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])")?.focus();
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div
      ref={rootRef}
      className="relative"
      onBlur={(e) => {
        // Tab ra khỏi menu thì đóng (relatedTarget null khi bấm vào chữ trong menu: giữ mở).
        if (open && e.relatedTarget && !rootRef.current?.contains(e.relatedTarget as Node)) setOpen(false);
      }}
    >
      <button
        ref={buttonRef}
        type="button"
        aria-label={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={buttonClassName}
      >
        {button}
      </button>
      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label={label}
          style={{ width }}
          className={cx(
            "absolute top-[calc(100%+8px)] z-50 max-w-[calc(100vw-24px)] overflow-hidden rounded-xl border border-line bg-surface text-body shadow-float [animation:sb-fade-in_.15s_var(--sb-ease)]",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
