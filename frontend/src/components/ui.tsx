/** Design-system primitives (docs/DESIGN_SYSTEM.md).
 *  shadcn-styled: rounded-2xl cards, soft shadows, warm neutrals. */
import { type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import clsx from "clsx";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        "rounded-2xl bg-[var(--color-surface)] shadow-[var(--shadow-card)]",
        className,
      )}
      {...props}
    />
  );
}

/** Card that lifts on hover (DESIGN_SYSTEM_V2 §4: y:-2 + shadow).
 *
 *  CSS-driven (`.card-lift`), not Framer Motion — this renders in the eager
 *  shell and appears dozens of times per grid, so it must cost nothing on the
 *  critical path. `prefers-reduced-motion` is handled in the stylesheet. */
export function MotionCard({
  className,
  children,
  onClick,
  interactive = true,
}: {
  className?: string;
  children: ReactNode;
  onClick?: () => void;
  interactive?: boolean;
}) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        "rounded-2xl bg-[var(--color-surface)] shadow-[var(--shadow-card)]",
        interactive && "card-lift",
        className,
      )}
    >
      {children}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "accent";

const buttonStyles: Record<ButtonVariant, string> = {
  primary: "bg-clay text-white hover:bg-clay-dark focus-visible:ring-clay",
  secondary: "bg-sand text-ink hover:bg-[#e8e0d4] focus-visible:ring-stone",
  ghost: "bg-transparent text-ink hover:bg-sand focus-visible:ring-stone",
  danger: "bg-red-700 text-white hover:bg-red-800 focus-visible:ring-red-700",
  /* The V2 single accent — near-black. Used for primary CTAs on rebuilt pages. */
  accent: "bg-[var(--color-accent)] text-[var(--color-canvas)] hover:opacity-90 focus-visible:ring-[var(--color-accent)]",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={clsx(
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        "active:scale-[0.98] motion-reduce:active:scale-100",
        "disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100",
        buttonStyles[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "clay";
  className?: string;
}) {
  const tones = {
    neutral: "bg-sand text-walnut",
    success: "bg-[#e7efe4] text-sage",
    warning: "bg-amber-100 text-amber-800",
    clay: "bg-[#f7e3d9] text-clay-dark",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-xl border border-[#e5ded3] bg-white px-3.5 py-2.5 text-sm",
        "placeholder:text-stone focus:border-clay focus:outline-none focus:ring-2 focus:ring-clay/20",
        props.className,
      )}
    />
  );
}

/** Shimmer placeholder (V2): a moving gradient sweep, not a pulsing grey box.
 *  Honours prefers-reduced-motion by falling back to a static tint. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={clsx(
        "relative overflow-hidden rounded-xl bg-sand",
        "before:absolute before:inset-0 before:-translate-x-full before:animate-shimmer",
        "before:bg-gradient-to-r before:from-transparent before:via-white/60 before:to-transparent",
        "motion-reduce:before:hidden",
        className,
      )}
    />
  );
}

/** Empty state — Stripe's rule: teach, never apologise.
 *  Illustration + one sentence + exactly one primary CTA. Callers must pass
 *  DIFFERENT copy for first-run vs no-results-after-filter. */
export function EmptyState({
  title,
  hint,
  action,
  icon,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center">
      {icon ?? (
        <div className="mb-1 grid h-14 w-14 place-items-center rounded-2xl bg-[var(--color-line)]" aria-hidden="true">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-[var(--color-faint)]">
            <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M3 15l4.5-4.5 3.5 3.5 3-3L21 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      )}
      <p className="h3 text-[var(--color-ink)]">{title}</p>
      {hint && <p className="max-w-sm text-sm text-[var(--color-muted)]">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Inline error — never a full-page takeover (Stripe). Retry + copyable id so
 *  a support conversation can start with a fact instead of "it broke". */
export function ErrorState({
  message,
  onRetry,
  errorId,
}: {
  message: string;
  onRetry?: () => void;
  errorId?: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-2xl border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5 py-12 text-center"
    >
      <div className="grid h-11 w-11 place-items-center rounded-full bg-[var(--color-danger)]/10" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-[var(--color-danger)]">
          <path d="M10 6v5M10 14h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </div>
      <p className="font-medium text-[var(--color-danger)]">{message}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
      {errorId && (
        <button
          type="button"
          onClick={() => navigator.clipboard?.writeText(errorId)}
          className="font-mono text-[11px] text-[var(--color-muted)] underline decoration-dotted"
          title="Copy error id for support"
        >
          {errorId}
        </button>
      )}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex justify-center py-16" role="status" aria-label="Loading">
      <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-sand border-t-clay" />
    </div>
  );
}
