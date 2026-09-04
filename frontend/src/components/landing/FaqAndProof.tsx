/** FAQ and social proof — two sections the landing page was missing.
 *
 * The competitor's FAQ answers exactly the objections that stop a purchase
 * ("do I need design experience?", "what should I upload?"). Ours answers the
 * objections specific to *our* proposition: are the prices real, are the
 * seller links real, is my data safe.
 *
 * Implementation note: native <details>/<summary> rather than a JS accordion.
 * It is keyboard- and screen-reader-correct for free, works before hydration,
 * and is searchable by the browser's find-in-page — which a div-based
 * accordion with hidden content is not.
 */
import { useT } from "@/i18n";
import { ScrollReveal } from "@/components/Scroll3D";

function Stars() {
  return (
    <span className="text-sm text-[var(--color-accent)]" aria-hidden="true">
      ★★★★★
    </span>
  );
}

export function FaqAndProof() {
  const t = useT();

  return (
    <>
      {/* ------------------------------------------------------ testimonials */}
      <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
        <ScrollReveal>
          <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
            {t.proof.title}
          </h2>
          <p className="mt-2 text-sm text-[var(--color-muted)]">{t.proof.subtitle}</p>
        </ScrollReveal>

        <div className="mt-8 grid gap-5 sm:grid-cols-3">
          {t.proof.items.map((item, i) => (
            <ScrollReveal key={item.quote} delay={i * 0.08}>
              <figure className="h-full rounded-2xl border border-[var(--color-line)] p-5">
                <Stars />
                <blockquote className="mt-3 text-sm leading-relaxed text-[var(--color-ink)]">
                  “{item.quote}”
                </blockquote>
                <figcaption className="mt-3 text-xs text-[var(--color-muted)]">
                  — {item.role}
                </figcaption>
              </figure>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* --------------------------------------------------------------- faq */}
      <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
        <ScrollReveal>
          <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
            {t.faq.title}
          </h2>
          <p className="mt-2 text-sm text-[var(--color-muted)]">{t.faq.subtitle}</p>
        </ScrollReveal>

        <div className="mt-8 max-w-3xl divide-y divide-[var(--color-line)] border-y border-[var(--color-line)]">
          {t.faq.items.map((item, i) => (
            <ScrollReveal key={item.q} delay={i * 0.05}>
              <details className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold text-[var(--color-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
                  {item.q}
                  <span
                    aria-hidden="true"
                    className="shrink-0 text-lg text-[var(--color-muted)] transition-transform group-open:rotate-45"
                  >
                    +
                  </span>
                </summary>
                <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">
                  {item.a}
                </p>
              </details>
            </ScrollReveal>
          ))}
        </div>
      </section>
    </>
  );
}
