/**
 * Toast system — DESIGN_SYSTEM_V2 §7 ("undo over confirm").
 *
 * Phase 0B's dead-key audit flagged two buttons as PARTIAL purely because the
 * app had *no* feedback surface: a delete would fire, succeed or fail, and say
 * nothing. This is that surface. It also enables Linear's undo-over-confirm
 * pattern — a destructive action completes immediately and offers Undo, which
 * is faster and less annoying than a confirm modal.
 */
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
  /** Optional action, e.g. Undo. Dismisses the toast when invoked. */
  action?: { label: string; onClick: () => void };
  /** Copyable error id — Stripe's "what happened / what next" microcopy. */
  errorId?: string;
}

interface ToastApi {
  push: (t: Omit<Toast, "id">) => number;
  dismiss: (id: number) => void;
  success: (message: string, action?: Toast["action"]) => number;
  error: (message: string, errorId?: string) => number;
}

const ToastContext = createContext<ToastApi | null>(null);

/** Non-throwing: a component that toasts should never crash a page that
 *  forgot the provider (e.g. an isolated test render). */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  const noop = useMemo<ToastApi>(
    () => ({ push: () => -1, dismiss: () => {}, success: () => -1, error: () => -1 }),
    [],
  );
  return ctx ?? noop;
}

const KIND_STYLES: Record<ToastKind, string> = {
  success: "border-l-[3px] border-l-[var(--color-ok)]",
  error: "border-l-[3px] border-l-[var(--color-danger)]",
  info: "border-l-[3px] border-l-[var(--color-accent)]",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t) {
      clearTimeout(t);
      timers.current.delete(id);
    }
    setToasts((prev) => prev.filter((x) => x.id !== id));
  }, []);

  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = ++seq.current;
      setToasts((prev) => [...prev, { ...t, id }]);
      // Errors and actionable toasts linger — you cannot click Undo on a
      // toast that vanished in 3 seconds.
      const ttl = t.action || t.kind === "error" ? 8000 : 3500;
      timers.current.set(id, setTimeout(() => dismiss(id), ttl));
      return id;
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      push,
      dismiss,
      success: (message, action) => push({ kind: "success", message, action }),
      error: (message, errorId) => push({ kind: "error", message, errorId }),
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* aria-live so screen readers announce without stealing focus. */}
      <div
        className="pointer-events-none fixed bottom-6 right-6 z-[100] flex w-[min(24rem,calc(100vw-3rem))] flex-col gap-2"
        role="status"
        aria-live="polite"
      >
        {toasts.map((t) => (
            <div
              key={t.id}
              className={`toast-in pointer-events-auto flex items-start gap-3 rounded-2xl bg-[var(--color-surface)] p-4 shadow-[var(--shadow-float)] ${KIND_STYLES[t.kind]}`}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[var(--color-ink)]">{t.message}</p>
                {t.errorId && (
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(t.errorId!)}
                    className="mt-1 font-mono text-[11px] text-[var(--color-muted)] underline decoration-dotted hover:text-[var(--color-ink)]"
                    title="Copy error id"
                  >
                    {t.errorId}
                  </button>
                )}
              </div>
              {t.action && (
                <button
                  type="button"
                  onClick={() => {
                    t.action!.onClick();
                    dismiss(t.id);
                  }}
                  className="shrink-0 rounded-lg px-2 py-1 text-sm font-semibold text-[var(--color-accent)] hover:bg-[var(--color-line)]"
                >
                  {t.action.label}
                </button>
              )}
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss notification"
                className="shrink-0 rounded-lg p-1 text-[var(--color-faint)] hover:bg-[var(--color-line)] hover:text-[var(--color-ink)]"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}
      </div>
    </ToastContext.Provider>
  );
}
