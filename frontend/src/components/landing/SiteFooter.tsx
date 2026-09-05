/** Site footer.
 *
 * Structure follows the competitor's: a short brand blurb plus grouped link
 * columns. The groups are ours, though — theirs advertises twenty-two image
 * tools; ours points at the capabilities this product actually has, so no
 * link leads to a page that does not exist.
 */
import { Link } from "react-router-dom";
import { useLocale } from "@/i18n";
import { Logo } from "@/components/Logo";

export function SiteFooter() {
  const { t, num } = useLocale();
  const year = new Date().getFullYear();

  return (
    <footer className="mt-16 border-t border-[var(--color-line)] bg-[var(--color-ink)] text-[var(--color-canvas)]">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-10 md:grid-cols-[1.6fr_1fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-2">
              <Logo size={30} className="text-[var(--color-canvas)]" />
              <span className="text-lg font-semibold">{t.brand}</span>
            </div>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-[var(--color-canvas)]/70">
              {t.footer.blurb}
            </p>
          </div>

          {t.footer.columns.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h3 className="text-sm font-semibold">{col.title}</h3>
              <ul className="mt-3 space-y-2">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      to={l.to}
                      className="text-sm text-[var(--color-canvas)]/70 transition-colors hover:text-[var(--color-canvas)]"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-10 flex flex-col gap-3 border-t border-[var(--color-canvas)]/15 pt-6 text-xs text-[var(--color-canvas)]/60 sm:flex-row sm:items-center sm:justify-between">
          <p>{t.footer.rights(num(year))}</p>
          <p>{t.footer.builtWith}</p>
        </div>
      </div>
    </footer>
  );
}
