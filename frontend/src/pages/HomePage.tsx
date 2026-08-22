import { Link } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { STYLES } from "@/lib/constants";
import { Card } from "@/components/ui";
import { OptimizedImage } from "@/components/OptimizedImage";
import heroImage from "@/assets/hero.png";

const STEPS = [
  {
    n: "01",
    title: "Tell us your space",
    body: "Real dimensions, your budget, and the styles you are drawn to. Two minutes, no account walls.",
  },
  {
    n: "02",
    title: "See why, not just what",
    body: "Every product carries its score breakdown — style fit, colour harmony, budget and how it fits your room.",
  },
  {
    n: "03",
    title: "Arrange, check, buy",
    body: "Drop picks onto a moodboard, verify walkways on the floorplan, then shop from validated retailer links.",
  },
];

export default function HomePage() {
  const user = useAuthStore((s) => s.user);

  const cta = user
    ? user.role === "admin"
      ? "/admin/products"
      : user.role === "designer"
        ? "/designer/dashboard"
        : "/quiz"
    : "/register";

  return (
    <div>
      {/* Hero — Aesop's rule: let it breathe. One idea, enormous margins. */}
      <section className="grid items-center gap-12 py-16 lg:grid-cols-2 lg:py-24">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
            Living room · Iran
          </p>

          <h1 className="mt-4 text-4xl font-semibold leading-[1.1] tracking-tight text-[var(--color-ink)] sm:text-5xl lg:text-6xl">
            Your dream living room,
            <br />
            matched by AI.
          </h1>

          <p className="mt-5 max-w-md text-lg leading-relaxed text-[var(--color-muted)]">
            Answer a two-minute style quiz. Get ranked products per category with
            transparent “why this” scores, an editable moodboard, a real-dimension
            floorplan and a validated shopping list.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to={cta}
              className="rounded-xl bg-[var(--color-accent)] px-6 py-3 font-semibold text-[var(--color-canvas)] transition-opacity hover:opacity-90"
            >
              {user ? "Continue" : "Start the style quiz"}
            </Link>

            {!user && (
              <Link
                to="/login"
                className="rounded-xl border border-[var(--color-line)] px-6 py-3 font-semibold text-[var(--color-ink)] transition-colors hover:bg-[var(--color-line)]"
              >
                Sign in
              </Link>
            )}
          </div>

          <p className="mt-4 text-xs text-[var(--color-faint)]">
            Free to try · No credit card · Prices in Toman
          </p>
        </div>

        <OptimizedImage
          src={heroImage}
          alt="Warm modern living room with a beige sofa and walnut coffee table"
          width={960}
          height={640}
          priority
          deriveSources={false}
          sizes="(max-width: 1024px) 100vw, 50vw"
          wrapperClassName="h-72 w-full rounded-3xl shadow-[var(--shadow-hover)] lg:h-[26rem]"
        />
      </section>

      <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          How it works
        </h2>

        <div className="mt-10 grid gap-10 sm:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n}>
              <span className="text-xs font-semibold tabular-nums tracking-widest text-[var(--color-faint)]">
                {s.n}
              </span>

              <h3 className="mt-3 font-semibold text-[var(--color-ink)]">
                {s.title}
              </h3>

              <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">
                {s.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          Six styles, one quiz
        </h2>

        <p className="mt-2 text-sm text-[var(--color-muted)]">
          Pick the rooms you react to — the model infers your taste from images,
          not adjectives.
        </p>

        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {STYLES.map((s) => (
            <Card key={s.id} className="overflow-hidden">
              <OptimizedImage
                src={s.image}
                alt={`${s.label} style living room`}
                width={320}
                height={200}
                sizes="(max-width: 640px) 50vw, 200px"
                wrapperClassName="h-24 w-full"
              />

              <p className="px-3 py-2.5 text-sm font-medium text-[var(--color-ink)]">
                {s.label}
              </p>
            </Card>
          ))}
        </div>

        <div className="mt-10">
          <Link
            to={cta}
            className="inline-block rounded-xl bg-[var(--color-accent)] px-6 py-3 font-semibold text-[var(--color-canvas)] transition-opacity hover:opacity-90"
          >
            {user ? "Continue" : "Find my style"}
          </Link>
        </div>
      </section>
    </div>
  );
}
