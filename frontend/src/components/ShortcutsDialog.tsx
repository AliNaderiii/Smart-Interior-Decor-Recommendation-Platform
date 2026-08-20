/** Keyboard shortcuts help, opened with "?" — RESEARCH_V2 §6 (Linear).
 *
 *  A keyboard layer nobody can discover may as well not exist. Linear's answer
 *  is a single "?" that lists everything; this is that, lazy-loaded so it
 *  costs nothing until asked for. */
import { useEffect } from "react";

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: "Global",
    items: [
      ["⌘K / Ctrl K", "Open the command palette"],
      ["?", "Show this help"],
      ["Esc", "Close any dialog or overlay"],
      ["Tab", "Move to the next control"],
    ],
  },
  {
    title: "Moodboard editor",
    items: [
      ["⌘Z / Ctrl Z", "Undo the last layout change"],
      ["⇧⌘Z / Ctrl ⇧ Z", "Redo"],
      ["Drag", "Move or resize a product"],
    ],
  },
  {
    title: "Present mode",
    items: [
      ["→ / Space", "Next product"],
      ["←", "Previous product"],
      ["Home / End", "Jump to first or last"],
      ["Esc", "Exit presentation"],
    ],
  },
];

export default function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="shortcuts-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl bg-[var(--color-surface)] p-6 shadow-[var(--shadow-float)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <h2 id="shortcuts-title" className="text-lg font-semibold text-[var(--color-ink)]">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
            className="rounded-lg px-2 py-1 text-sm text-[var(--color-muted)] hover:bg-[var(--color-line)] hover:text-[var(--color-ink)]"
          >
            Esc
          </button>
        </div>

        <div className="mt-5 space-y-5">
          {GROUPS.map((g) => (
            <section key={g.title}>
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-faint)]">
                {g.title}
              </h3>
              <dl className="mt-2 space-y-1.5">
                {g.items.map(([keys, desc]) => (
                  <div key={keys} className="flex items-baseline justify-between gap-4">
                    <dt className="text-sm text-[var(--color-muted)]">{desc}</dt>
                    <dd>
                      <kbd className="rounded-md border border-[var(--color-line)] bg-[var(--color-canvas)] px-2 py-0.5 font-mono text-[11px] text-[var(--color-ink)]">
                        {keys}
                      </kbd>
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
