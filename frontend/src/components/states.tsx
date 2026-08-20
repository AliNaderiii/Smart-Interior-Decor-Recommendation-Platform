/** Empty and error states.
 *
 *  PERF: split out of ui.tsx deliberately. ui.tsx is in the EAGER entry chunk
 *  (HomePage and LoginPage need Card/Button/Input), so anything living in it
 *  ships to every first-time visitor. No eagerly-rendered surface uses these
 *  two — they only appear behind auth, inside lazy route chunks — and their
 *  inline SVG illustrations are ~0.5 KB gzip of dead weight in the entry
 *  graph. Keeping them here means they load with the route that needs them.
 *
 *  If you ever import this from App/Layout/Home/Login, that saving is gone.
 */
import type { ReactNode } from "react";
import { Button } from "@/components/ui";

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
