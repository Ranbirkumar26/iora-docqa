"use client";

import { IconX } from "@/components/icons";

// Tiny shared UI primitives. Keeps every panel consistent.

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin text-current ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-label="Loading"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function Alert({
  kind = "error",
  children,
  onClose,
}: {
  kind?: "error" | "warn" | "ok";
  children: React.ReactNode;
  onClose?: () => void;
}) {
  const styles = {
    error:
      "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300",
    warn:
      "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    ok:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  }[kind];
  return (
    <div
      className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 text-sm ${styles}`}
      role="alert"
    >
      <div className="min-w-0 flex-1 break-words">{children}</div>
      {onClose && (
        <button
          onClick={onClose}
          className="shrink-0 rounded p-0.5 opacity-70 transition hover:opacity-100"
          aria-label="Dismiss"
        >
          <IconX />
        </button>
      )}
    </div>
  );
}

export function Badge({
  children,
  tone = "zinc",
}: {
  children: React.ReactNode;
  tone?: "zinc" | "indigo" | "emerald" | "amber";
}) {
  const styles = {
    zinc: "border-edge-strong bg-inset text-muted",
    indigo: "border-accent/40 bg-accent/10 text-accent",
    emerald:
      "border-emerald-600/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    amber:
      "border-amber-600/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${styles}`}
    >
      {children}
    </span>
  );
}

export function PrimaryButton({
  children,
  loading,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-md shadow-accent/25 transition hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-edge-strong bg-panel px-4 py-2.5 text-sm font-medium text-fg transition hover:bg-inset focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </span>
      <input
        {...rest}
        className="min-h-11 w-full rounded-xl border border-edge-strong bg-field px-3.5 py-2.5 text-sm text-fg placeholder-faint transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
      />
    </label>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-2xl border border-edge bg-panel ${className}`}>
      {children}
    </div>
  );
}
