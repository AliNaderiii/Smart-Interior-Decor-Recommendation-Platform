/** Subscription plans with a monthly/annual toggle.
 *
 * Modelled on the competitor's pricing block, but the offer is ours: they
 * meter image generations, we meter what our product actually produces —
 * quizzes, saved moodboards and designer projects. Prices are in Toman
 * because the market is Iranian.
 *
 * The annual column is the default: it is the cheaper option per month, and
 * defaulting to the cheaper price is a trust signal rather than a dark
 * pattern. The saving is stated explicitly rather than implied.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";
import { useLocale } from "@/i18n";
import { ScrollReveal } from "@/components/Scroll3D";

type Cycle = "monthly" | "annual";

export function PricingPlans() {
  const { t, num } = useLocale();
  const [cycle, setCycle] = useState<Cycle>("annual");

  return (
    <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
      <ScrollReveal>
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          {t.pricing.title}
        </h2>
        <p className="mt-2 text-sm text-[var(--color-muted)]">{t.pricing.subtitle}</p>

        {/* Billing cycle switch */}
        <div
          role="group"
          aria-label={t.pricing.cycleLabel}
          className="mt-6 inline-flex items-center gap-1 rounded-xl border border-[var(--color-line)] p-1"
        >
          {(["monthly", "annual"] as const).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCycle(c)}
              aria-pressed={cycle === c}
              className={clsx(
                "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
                cycle === c
                  ? "bg-[var(--color-accent)] text-[var(--color-canvas)]"
                  : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
              )}
            >
              {c === "monthly" ? t.pricing.monthly : t.pricing.annual}
            </button>
          ))}
          <span className="ms-2 me-1 text-xs font-semibold text-[var(--color-accent)]">
            {t.pricing.saveBadge}
          </span>
        </div>
      </ScrollReveal>

      <div className="mt-8 grid gap-5 md:grid-cols-3">
        {t.pricing.plans.map((plan, i) => {
          const price = cycle === "annual" ? plan.annualPerMonth : plan.monthly;
          return (
            <ScrollReveal key={plan.name} delay={i * 0.08}>
              <div
                className={clsx(
                  "relative flex h-full flex-col rounded-2xl border p-6",
                  plan.featured
                    ? "border-[var(--color-accent)] shadow-lg"
                    : "border-[var(--color-line)]",
                )}
              >
                {plan.featured && (
                  <span className="absolute -top-3 start-6 rounded-full bg-[var(--color-accent)] px-3 py-0.5 text-xs font-semibold text-[var(--color-canvas)]">
                    {t.pricing.popular}
                  </span>
                )}

                <p className="text-lg font-semibold text-[var(--color-ink)]">{plan.name}</p>
                <p className="mt-1 text-sm text-[var(--color-muted)]">{plan.for}</p>

                <p className="mt-5">
                  <span className="text-3xl font-semibold tracking-tight text-[var(--color-ink)]">
                    {price === 0 ? t.pricing.free : num(price)}
                  </span>
                  {price > 0 && (
                    <span className="ms-1 text-sm text-[var(--color-muted)]">
                      {t.common.toman} / {t.pricing.perMonth}
                    </span>
                  )}
                </p>
                {price > 0 && cycle === "annual" && (
                  <p className="mt-1 text-xs text-[var(--color-faint)]">
                    {t.pricing.billedYearly(num(plan.annualPerMonth * 12))}
                  </p>
                )}

                <ul className="mt-5 flex-1 space-y-2.5">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-[var(--color-ink)]">
                      <svg
                        width="15"
                        height="15"
                        viewBox="0 0 16 16"
                        fill="none"
                        aria-hidden="true"
                        className="mt-0.5 shrink-0 text-[var(--color-accent)]"
                      >
                        <path
                          d="M3 8.4l3.2 3.2L13 5"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <span className="leading-relaxed">{f}</span>
                    </li>
                  ))}
                </ul>

                <Link
                  to={plan.price === 0 ? "/register" : "/upgrade"}
                  className={clsx(
                    "mt-6 block rounded-xl px-4 py-2.5 text-center text-sm font-semibold transition-opacity hover:opacity-90",
                    plan.featured
                      ? "bg-[var(--color-accent)] text-[var(--color-canvas)]"
                      : "border border-[var(--color-line)] text-[var(--color-ink)]",
                  )}
                >
                  {plan.cta}
                </Link>
              </div>
            </ScrollReveal>
          );
        })}
      </div>

      <ScrollReveal delay={0.3}>
        <p className="mt-6 text-xs text-[var(--color-faint)]">{t.pricing.note}</p>
      </ScrollReveal>
    </section>
  );
}
