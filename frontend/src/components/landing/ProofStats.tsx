/** Verifiable metrics instead of invented testimonials.
 *
 * The earlier version carried three quotes attributed to "a homeowner in
 * Tehran", "an interior designer" and so on. The product has no users yet, so
 * those quotes were fabricated — and fabricated praise is both dishonest and
 * transparently AI-shaped to any reader who has seen a landing page before.
 * A client with an intellectual-property background is exactly the sort of
 * reader who notices.
 *
 * What replaces it is stronger anyway: numbers that can be checked. Every
 * figure below is the output of a command that was actually run, and each one
 * names its own evidence so a sceptical reader can verify it.
 */
import { useLocale } from "@/i18n";
import { ScrollReveal } from "@/components/Scroll3D";

export function ProofStats() {
  const { t, num } = useLocale();

  return (
    <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
      <ScrollReveal>
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          {t.stats.title}
        </h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-[var(--color-muted)]">
          {t.stats.subtitle}
        </p>
      </ScrollReveal>

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {t.stats.items.map((item, i) => (
          <ScrollReveal key={item.label} delay={i * 0.07}>
            <div className="h-full rounded-2xl border border-[var(--color-line)] p-5">
              <p className="text-3xl font-semibold tracking-tight text-[var(--color-ink)]">
                {num(item.value)}
                <span className="text-lg text-[var(--color-accent)]">{item.unit}</span>
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--color-ink)]">
                {item.label}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--color-muted)]">
                {item.note}
              </p>
            </div>
          </ScrollReveal>
        ))}
      </div>

      <ScrollReveal delay={0.3}>
        <p className="mt-6 text-xs text-[var(--color-faint)]">{t.stats.footnote}</p>
      </ScrollReveal>
    </section>
  );
}
