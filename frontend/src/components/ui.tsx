// Small styled primitives so pages stay declarative and the visual language
// (radius, focus, disabled states, spacing) is defined once. Not a full design
// system — just the pieces this app repeats.

import { clsx } from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Button({
  variant = "primary",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "accent" | "ghost" | "outline";
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 disabled:opacity-50 disabled:pointer-events-none min-h-[44px] cursor-pointer";
  const variants = {
    primary: "bg-[var(--color-primary)] text-[var(--color-on-primary)] hover:bg-[var(--color-primary-hover)]",
    accent: "bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)]",
    ghost: "text-[var(--color-foreground)] hover:bg-[var(--color-surface-muted)]",
    outline:
      "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)]",
  };
  return (
    <button className={clsx(base, variants[variant], className)} {...props}>
      {children}
    </button>
  );
}

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        "w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2.5 text-sm outline-none placeholder:text-[var(--color-muted-foreground)] focus:border-[var(--color-ring)]",
        className,
      )}
      {...props}
    />
  );
}

export function Card({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "danger" | "processing";
}) {
  const tones = {
    neutral: "bg-[var(--color-surface-muted)] text-[var(--color-muted-foreground)]",
    success: "bg-emerald-50 text-emerald-700",
    danger: "bg-red-50 text-red-700",
    processing: "bg-cyan-50 text-cyan-700",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-[var(--color-muted-foreground)]">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]" />
      {label}
    </span>
  );
}
