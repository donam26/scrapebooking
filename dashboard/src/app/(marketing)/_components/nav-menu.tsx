"use client";

import { useRef } from "react";

/** Menu thu gọn cho màn hình hẹp: <details> gốc, tự đóng khi chọn một mục. */
export function NavMenu({ items }: { items: { href: string; label: string }[] }) {
  const ref = useRef<HTMLDetailsElement>(null);
  return (
    <details className="lp-menu" ref={ref}>
      <summary aria-label="Mở menu">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      </summary>
      <nav aria-label="Mục trên trang">
        {items.map((n) => (
          <a key={n.href} href={n.href} onClick={() => ref.current?.removeAttribute("open")}>
            {n.label}
          </a>
        ))}
      </nav>
    </details>
  );
}
