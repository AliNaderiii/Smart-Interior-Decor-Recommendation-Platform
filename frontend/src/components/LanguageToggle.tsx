import { useLocale } from "@/i18n";
import clsx from "clsx";

/** Two-state language switch.
 *
 *  A segmented control rather than a dropdown: with exactly two locales a
 *  select costs an extra click and hides the alternative. Each option is
 *  labelled in its *own* language (فارسی / EN) so a reader who cannot read the
 *  current interface can still find their way out — the standard rule for
 *  language pickers.
 */
export function LanguageToggle() {
  const { locale, setLocale, t } = useLocale();

  return (
    <div
      role="group"
      aria-label={t.nav.language}
      className="flex items-center gap-0.5 rounded-lg border border-[var(--color-line)] p-0.5"
    >
      {(
        [
          { id: "fa", label: "فا" },
          { id: "en", label: "EN" },
        ] as const
      ).map((opt) => {
        const active = locale === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => setLocale(opt.id)}
            aria-pressed={active}
            className={clsx(
              "rounded-md px-2 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
              active
                ? "bg-[var(--color-accent)] text-[var(--color-canvas)]"
                : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
