"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import type { Tone } from "@/lib/labels";
import { errorMessage } from "@/lib/api";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// ---- Badge ----

const TONE_CLASS: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  red: "bg-rose-50 text-rose-800 ring-rose-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  gray: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-sky-50 text-sky-800 ring-sky-200",
  purple: "bg-violet-50 text-violet-800 ring-violet-200",
};

export function Badge({
  tone = "gray",
  children,
  className,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
        TONE_CLASS[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

// ---- Button ----

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  busy?: boolean;
};

const VARIANT_CLASS = {
  primary: "bg-sky-700 text-white hover:bg-sky-800 disabled:bg-sky-300",
  secondary: "bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-white text-rose-700 ring-1 ring-inset ring-rose-300 hover:bg-rose-50 disabled:text-rose-300",
  ghost: "text-slate-700 hover:bg-slate-100 disabled:text-slate-400",
};

export function Button({ variant = "secondary", size = "md", busy, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded font-medium transition-colors disabled:cursor-not-allowed",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-sm",
        VARIANT_CLASS[variant],
        className,
      )}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cx("inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}

// ---- Form controls ----

const CONTROL_CLASS =
  "h-8 rounded border border-slate-300 bg-white px-2 text-sm text-slate-900 shadow-xs focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200 disabled:bg-slate-50 disabled:text-slate-400";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(CONTROL_CLASS, className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cx(CONTROL_CLASS, "pr-7", className)}>
      {children}
    </select>
  );
}

export function Field({ label, children, hint, className }: { label: string; children: ReactNode; hint?: string; className?: string }) {
  return (
    <label className={cx("flex flex-col gap-1 text-xs font-medium text-slate-600", className)}>
      <span>{label}</span>
      {children}
      {hint && <span className="text-[11px] font-normal text-slate-500">{hint}</span>}
    </label>
  );
}

// ---- Layout blocks ----

export function Card({ title, actions, children, className, padded = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface shadow-xs", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          {title && <h2 className="text-sm font-semibold text-slate-800">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Skeleton({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx("animate-pulse space-y-2", className)} aria-busy>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-4 rounded bg-slate-200" style={{ width: `${70 + ((i * 13) % 30)}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null;
  return (
    <div role="alert" className={cx("rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800", className)}>
      {errorMessage(error)}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="rounded border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500">{children}</p>;
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: Array<{ key: T; label: string }> }) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
      {items.map((it) => (
        <button
          key={it.key}
          role="tab"
          type="button"
          aria-selected={it.key === value}
          onClick={() => onChange(it.key)}
          className={cx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium",
            it.key === value ? "border-sky-700 text-sky-800" : "border-transparent text-slate-500 hover:text-slate-800",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

// ---- Table ----

export function Table({ children, className, dense }: { children: ReactNode; className?: string; dense?: boolean }) {
  return (
    <div className={cx("overflow-x-auto", className)}>
      <table className={cx("w-full border-collapse text-left text-sm", dense ? "[&_td]:px-2 [&_td]:py-1 [&_th]:px-2 [&_th]:py-1.5" : "[&_td]:px-3 [&_td]:py-1.5 [&_th]:px-3 [&_th]:py-2")}>
        {children}
      </table>
    </div>
  );
}

export function Th({ children, className, right }: { children?: ReactNode; className?: string; right?: boolean }) {
  return (
    <th scope="col" className={cx("border-b border-line bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500", right && "text-right", className)}>
      {children}
    </th>
  );
}

export function Td({ children, className, right, mono, title }: { children?: ReactNode; className?: string; right?: boolean; mono?: boolean; title?: string }) {
  return (
    <td title={title} className={cx("border-b border-line align-top text-slate-800", right && "text-right tabular", mono && "font-mono text-xs", className)}>
      {children}
    </td>
  );
}

export function LinkButton({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link href={href} className={cx("text-sky-700 hover:underline", className)}>
      {children}
    </Link>
  );
}

/** Ô "nhãn: giá trị" cho panel chi tiết. */
export function Stat({ label, value, className }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div className={cx("min-w-0", className)}>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-sm font-medium text-slate-900">{value}</div>
    </div>
  );
}

export function StatTile({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: Tone; hint?: ReactNode }) {
  const toneText: Record<Tone, string> = {
    green: "text-emerald-700",
    red: "text-rose-700",
    amber: "text-amber-700",
    gray: "text-slate-900",
    blue: "text-sky-800",
    purple: "text-violet-800",
  };
  return (
    <div className="rounded-lg border border-line bg-surface p-4 shadow-xs">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold", toneText[tone ?? "gray"])}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}
