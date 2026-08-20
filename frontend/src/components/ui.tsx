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

export function Spinner() {
  return (
    <div className="flex justify-center py-16" role="status" aria-label="Loading">
      <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-sand border-t-clay" />
    </div>
  );
}
