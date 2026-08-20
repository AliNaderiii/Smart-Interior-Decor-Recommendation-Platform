/** Design-system primitives (docs/DESIGN_SYSTEM.md).
 *  shadcn-styled: rounded-2xl cards, soft shadows, warm neutrals. */
import { type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import clsx from "clsx";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        "rounded-2xl bg-white shadow-[0_1px_3px_rgba(43,38,34,0.08),0_8px_24px_rgba(43,38,34,0.06)]",
        className,
      )}
      {...props}
    />
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const buttonStyles: Record<ButtonVariant, string> = {
  primary: "bg-clay text-white hover:bg-clay-dark focus-visible:ring-clay",
  secondary: "bg-sand text-ink hover:bg-[#e8e0d4] focus-visible:ring-stone",
  ghost: "bg-transparent text-ink hover:bg-sand focus-visible:ring-stone",
  danger: "bg-red-700 text-white hover:bg-red-800 focus-visible:ring-red-700",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        "disabled:opacity-50 disabled:cursor-not-allowed",
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

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[#ddd4c7] py-16 text-center">
      <p className="text-lg font-semibold text-walnut">{title}</p>
      {hint && <p className="max-w-sm text-sm text-stone">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl bg-red-50 py-12 text-center">
      <p className="font-medium text-red-800">{message}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
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
