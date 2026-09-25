"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import type { Tone } from "@/lib/labels";
import { errorMessage } from "@/lib/api";
import { IconAlert, IconChevronRight } from "./icons";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// ---- Badge (nhãn trạng thái: chấm màu + chữ) ----

const TONE_CLASS: Record<Tone, string> = {
  green: "bg-yours-soft text-yours-deep",
  red: "bg-danger-soft text-danger-deep",
  amber: "bg-warning-soft text-warning-deep",
  gray: "bg-sunken text-muted",
  blue: "bg-brand-softer text-brand-hover",
  purple: "bg-brand-soft text-brand-hover",
  plum: "bg-plum text-white",
};

const DOT_CLASS: Record<Tone, string> = {
  green: "bg-yours",
  red: "bg-danger",
  amber: "bg-[#e0a100]",
  gray: "bg-faint",
  blue: "bg-brand",
  purple: "bg-brand",
  plum: "bg-exact",
};

export function Badge({
  tone = "gray",
  children,
  className,
  title,
  dot = true,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
  dot?: boolean;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-full px-2 text-xs font-semibold",
        TONE_CLASS[tone],
        className,
      )}
    >
      {dot && <span aria-hidden className={cx("h-1.5 w-1.5 shrink-0 rounded-full", DOT_CLASS[tone])} />}
      {children}
    </span>
  );
}

// ---- Button ----

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "quiet";
  size?: "sm" | "md";
  busy?: boolean;
  icon?: ReactNode;
};

const VARIANT_CLASS = {
  primary:
    "bg-brand text-white shadow-[0_1px_2px_rgba(47,28,106,0.25)] hover:bg-brand-hover active:translate-y-px disabled:bg-brand/45 disabled:shadow-none",
  secondary:
    "bg-surface text-ink ring-1 ring-inset ring-line-strong hover:bg-subtle hover:ring-[#b9b5d6] active:bg-sunken disabled:text-faint disabled:hover:bg-surface",
  danger: "bg-surface text-danger ring-1 ring-inset ring-danger/35 hover:bg-danger-soft disabled:text-danger/40",
  ghost: "text-body hover:bg-sunken hover:text-ink disabled:text-faint disabled:hover:bg-transparent",
  quiet: "text-brand hover:bg-brand-softer hover:text-brand-hover disabled:text-faint disabled:hover:bg-transparent",
};

export function Button({ variant = "secondary", size = "md", busy, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-semibold transition-[background-color,box-shadow,color,transform] duration-150 disabled:cursor-not-allowed",
        size === "sm" ? "h-8 px-2.5 text-sm" : "h-9 px-3.5 text-base",
        VARIANT_CLASS[variant],
        className,
      )}
    >
      {busy ? <Spinner /> : icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  icon,
  children,
  className,
  external,
}: {
  href: string;
  variant?: keyof typeof VARIANT_CLASS;
  size?: "sm" | "md";
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  external?: boolean;
}) {
  const cls = cx(
    "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-semibold no-underline transition-[background-color,box-shadow,color] duration-150",
    size === "sm" ? "h-8 px-2.5 text-sm" : "h-9 px-3.5 text-base",
    VARIANT_CLASS[variant],
    className,
  );
  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={cls}>
        {icon}
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {icon}
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cx("inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}

// ---- Form controls ----

const CONTROL_CLASS =
  "h-9 w-full min-w-0 rounded-lg border border-line-strong bg-surface px-3 text-base text-ink shadow-[inset_0_1px_1px_rgba(22,18,58,0.04)] transition-[border-color,box-shadow] duration-150 placeholder:text-faint hover:border-[#b9b5d6] focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15 disabled:cursor-not-allowed disabled:bg-subtle disabled:text-faint";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(CONTROL_CLASS, className)} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={cx(CONTROL_CLASS, "h-auto py-2", className)} />;
}


export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cx(CONTROL_CLASS, "sb-select cursor-pointer appearance-none pr-9", className)}>
      {children}
    </select>
  );
}

export function Field({
  label,
  children,
  hint,
  className,
  htmlFor,
}: {
  label: ReactNode;
  children: ReactNode;
  hint?: ReactNode;
  className?: string;
  htmlFor?: string;
}) {
  const inner = (
    <>
      <span className="text-sm font-semibold text-body">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </>
  );
  if (htmlFor) {
    return (
      <div className={cx("flex min-w-0 flex-col gap-1.5", className)}>
        <label htmlFor={htmlFor} className="text-sm font-semibold text-body">
          {label}
        </label>
        {children}
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
    );
  }
  return <label className={cx("flex min-w-0 flex-col gap-1.5", className)}>{inner}</label>;
}

/** Nhóm nút chọn một (thay cho select ngắn): 14/30/60 đêm, vai trò, ngôn ngữ… */
export function Segmented<T extends string | number>({
  value,
  onChange,
  items,
  label,
  size = "md",
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  items: Array<{ value: T; label: ReactNode; title?: string }>;
  label: string;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cx("inline-flex shrink-0 rounded-lg bg-sunken p-0.5", className)}>
      {items.map((it) => {
        const on = it.value === value;
        return (
          <button
            key={String(it.value)}
            type="button"
            role="radio"
            aria-checked={on}
            title={it.title}
            onClick={() => onChange(it.value)}
            className={cx(
              "whitespace-nowrap rounded-md font-semibold transition-[background-color,color,box-shadow] duration-150",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-sm",
              on ? "bg-surface text-ink shadow-[0_1px_2px_rgba(22,18,58,0.12),0_0_0_1px_rgba(22,18,58,0.04)]" : "text-muted hover:text-ink",
            )}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

// ---- Layout blocks ----

export function Card({
  title,
  description,
  actions,
  children,
  className,
  padded = true,
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
  id?: string;
}) {
  return (
    <section id={id} className={cx("min-w-0 rounded-xl border border-line bg-surface shadow-card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            {title && <h2 className="text-md font-bold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export type Crumb = { href?: string; label: ReactNode };

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Đường dẫn" className="mb-2">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted">
        {items.map((c, i) => (
          <li key={i} className="flex min-w-0 items-center gap-1">
            {i > 0 && <IconChevronRight size={14} className="shrink-0 text-faint" />}
            {c.href ? (
              <Link href={c.href} className="truncate rounded-sm hover:text-brand hover:underline">
                {c.label}
              </Link>
            ) : (
              <span className="truncate text-body" aria-current="page">
                {c.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  crumbs,
  meta,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  crumbs?: Crumb[];
  meta?: ReactNode;
}) {
  return (
    <div className="mb-6">
      {crumbs && <Breadcrumbs items={crumbs} />}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-[-0.015em] text-ink [text-wrap:balance]">{title}</h1>
          {subtitle && <div className="mt-1 text-base text-muted">{subtitle}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta && <div className="mt-3">{meta}</div>}
    </div>
  );
}

export function Skeleton({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx("space-y-2.5", className)} aria-busy aria-label="Đang tải">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="sb-skeleton h-4 rounded-md" style={{ width: `${68 + ((i * 13) % 30)}%` }} />
      ))}
    </div>
  );
}

export function SkeletonBlock({ className }: { className?: string }) {
  return <div aria-hidden className={cx("sb-skeleton rounded-lg", className)} />;
}

export function ErrorBox({ error, className, title }: { error: unknown; className?: string; title?: string }) {
  if (!error) return null;
  return (
    <div role="alert" className={cx("flex items-start gap-2.5 rounded-lg border border-danger/20 bg-danger-soft px-3.5 py-2.5 text-base text-danger-deep", className)}>
      <IconAlert size={18} className="mt-px shrink-0" />
      <div className="min-w-0">
        {title && <div className="font-semibold">{title}</div>}
        <div className="break-words">{errorMessage(error)}</div>
      </div>
    </div>
  );
}

/** Trạng thái rỗng: nói rõ vì sao trống và làm gì tiếp theo. */
export function EmptyState({
  children,
  title,
  icon,
  action,
  className,
  compact,
}: {
  children?: ReactNode;
  title?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div className={cx("flex flex-col items-center justify-center rounded-lg bg-subtle text-center", compact ? "px-4 py-6" : "px-6 py-10", className)}>
      {icon && <div className="mb-3 grid h-10 w-10 place-items-center rounded-full bg-brand-soft text-brand">{icon}</div>}
      {title && <div className="text-md font-bold text-ink">{title}</div>}
      {children && <div className={cx("max-w-md text-base text-muted", title ? "mt-1" : undefined)}>{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  items: Array<{ key: T; label: string; icon?: ReactNode; count?: number }>;
  className?: string;
}) {
  return (
    <div role="tablist" className={cx("sb-scroll mb-6 flex gap-1 overflow-x-auto border-b border-line", className)}>
      {items.map((it) => {
        const on = it.key === value;
        return (
          <button
            key={it.key}
            role="tab"
            type="button"
            id={`tab-${it.key}`}
            aria-selected={on}
            aria-controls={`panel-${it.key}`}
            onClick={() => onChange(it.key)}
            className={cx(
              "-mb-px inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-2 pb-2.5 pt-2 text-sm font-semibold transition-colors duration-150 sm:px-3 sm:text-base",
              on ? "border-brand text-ink" : "border-transparent text-muted hover:border-line-strong hover:text-ink",
            )}
          >
            {it.icon && <span className={cx("hidden sm:inline", on ? "text-brand" : "text-faint")}>{it.icon}</span>}
            {it.label}
            {it.count !== undefined && <span className="rounded-full bg-sunken px-1.5 text-xs font-semibold text-muted tabular">{it.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

// ---- Table ----

export function Table({ children, className, dense }: { children: ReactNode; className?: string; dense?: boolean }) {
  return (
    <div className={cx("sb-scroll relative overflow-x-auto", className)}>
      <table
        className={cx(
          "w-full border-collapse text-left text-base",
          dense
            ? "[&_td]:px-3 [&_td]:py-2 [&_th]:px-3 [&_th]:py-2"
            : "[&_td]:px-4 [&_td]:py-3 [&_th]:px-4 [&_th]:py-2.5",
          "[&_tbody_tr:last-child_td]:border-b-0",
        )}
      >
        {children}
      </table>
    </div>
  );
}

export function Th({ children, className, right }: { children?: ReactNode; className?: string; right?: boolean }) {
  return (
    <th
      scope="col"
      className={cx("relative whitespace-nowrap border-b border-line bg-subtle text-xs font-semibold text-muted", right && "text-right", className)}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  className,
  right,
  mono,
  title,
  colSpan,
}: {
  children?: ReactNode;
  className?: string;
  right?: boolean;
  mono?: boolean;
  title?: string;
  colSpan?: number;
}) {
  return (
    <td
      title={title}
      colSpan={colSpan}
      className={cx("border-b border-line align-middle text-body", right && "text-right tabular", mono && "font-mono text-xs", className)}
    >
      {children}
    </td>
  );
}

/** Hàng bảng có hover nhạt. */
export const ROW_CLASS = "transition-colors duration-100 hover:bg-subtle";

export function LinkButton({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link href={href} className={cx("font-semibold text-brand hover:text-brand-hover hover:underline", className)}>
      {children}
    </Link>
  );
}

/** Ô "nhãn: giá trị" cho panel chi tiết. */
export function Stat({ label, value, className }: { label: ReactNode; value: ReactNode; className?: string }) {
  return (
    <div className={cx("min-w-0", className)}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-base font-semibold text-ink tabular">{value}</div>
    </div>
  );
}

/** Dải số đo nằm ngang, ngăn bằng đường tóc (không phải lưới thẻ). */
export function StatStrip({
  items,
  className,
}: {
  items: Array<{ label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "default" | "good" | "warn" | "bad" }>;
  className?: string;
}) {
  const toneText = { default: "text-ink", good: "text-yours-deep", warn: "text-warning-deep", bad: "text-danger" };
  return (
    <dl
      className={cx(
        "grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line shadow-card lg:grid-flow-col lg:auto-cols-fr lg:grid-cols-none",
        className,
      )}
    >
      {items.map((it, i) => (
        <div key={i} className={cx("min-w-0 bg-surface px-4 py-3.5 sm:px-5 sm:py-4", items.length % 2 === 1 && i === items.length - 1 && "col-span-2 lg:col-span-1")}>
          <dt className="text-sm text-muted">{it.label}</dt>
          <dd className={cx("mt-1 text-lg font-bold tracking-[-0.01em] tabular sm:text-xl", toneText[it.tone ?? "default"])}>{it.value}</dd>
          {it.hint && <dd className="mt-0.5 text-xs text-muted">{it.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

/** Giữ tương thích: ô số đơn lẻ. */
export function StatTile({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: Tone; hint?: ReactNode }) {
  const toneText: Record<Tone, string> = {
    green: "text-yours-deep",
    red: "text-danger",
    amber: "text-warning-deep",
    gray: "text-ink",
    blue: "text-brand",
    purple: "text-brand",
    plum: "text-plum",
  };
  return (
    <div className="rounded-xl border border-line bg-surface px-5 py-4 shadow-card">
      <div className="text-sm text-muted">{label}</div>
      <div className={cx("mt-1 text-xl font-bold tabular", toneText[tone ?? "gray"])}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

/** Ghi chú trung tính (không viền màu bên trái). */
export function Note({ children, tone = "neutral", icon, className }: { children: ReactNode; tone?: "neutral" | "warn" | "info"; icon?: ReactNode; className?: string }) {
  const cls = {
    neutral: "bg-subtle text-body border-line",
    warn: "bg-warning-soft text-warning-deep border-[#f3dc9a]",
    info: "bg-brand-softer text-body border-brand-soft",
  }[tone];
  return (
    <div className={cx("flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm", cls, className)}>
      {icon && <span className="mt-px shrink-0">{icon}</span>}
      <div className="min-w-0">{children}</div>
    </div>
  );
}
