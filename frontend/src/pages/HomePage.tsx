import { Link } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { STYLES } from "@/lib/constants";
import { Card } from "@/components/ui";
import { OptimizedImage } from "@/components/OptimizedImage";
// WebP, pre-sized to the largest rendered width (1440px = 960 CSS px at 1.5x
// DPR). The source PNG was 2.7 MB and pushed mobile LCP to 17.5 s — the single
// audit dragging Lighthouse performance to 72. Vite fingerprints local assets,
// so OptimizedImage's `deriveSources` URL derivation cannot apply; importing
// the already-optimised file is the correct route.
import heroImage from "@/assets/hero.webp";
import { t, toFa } from "@/i18n/fa";
import {
  ScrollStage,
  TiltOnScroll,
  ParallaxZ,
  CardTilt3D,
  ScrollReveal,
  ScrollProgress,
} from "@/components/Scroll3D";


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
    <ScrollStage>
      <ScrollProgress />
      {/* Hero — Aesop's rule: let it breathe. One idea, enormous margins. */}
      <section className="grid items-center gap-12 py-16 lg:grid-cols-2 lg:py-24">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-muted)]">
            {t.home.eyebrow}
          </p>

          <h1 className="mt-4 text-4xl font-semibold leading-[1.3] tracking-tight text-[var(--color-ink)] sm:text-5xl lg:text-6xl">
            {t.home.title}
            <br />
            {t.home.titleAccent}
          </h1>

          <p className="mt-5 max-w-md text-lg leading-relaxed text-[var(--color-muted)]">
            {t.home.subtitle}
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to={cta}
              className="rounded-xl bg-[var(--color-accent)] px-6 py-3 font-semibold text-[var(--color-canvas)] transition-opacity hover:opacity-90"
            >
              {user ? t.common.continue : t.home.cta}
            </Link>

            {!user && (
              <Link
                to="/login"
                className="rounded-xl border border-[var(--color-line)] px-6 py-3 font-semibold text-[var(--color-ink)] transition-colors hover:bg-[var(--color-line)]"
              >
                {t.nav.login}
              </Link>
            )}
          </div>

          <p className="mt-4 text-xs text-[var(--color-faint)]">{t.home.ctaNote}</p>
        </div>

        <ParallaxZ depth={30}>
        <OptimizedImage
          src={heroImage}
          alt="نشیمن مدرن و گرم با مبل بژ و میز جلومبلی گردویی"
          width={960}
          height={640}
          priority
          deriveSources={false}
          sizes="(max-width: 1024px) 100vw, 50vw"
          wrapperClassName="h-72 w-full rounded-3xl shadow-[var(--shadow-hover)] lg:h-[26rem]"
        />
        </ParallaxZ>
      </section>

      <TiltOnScroll className="border-t border-[var(--color-line)] py-16 lg:py-24">
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          {t.home.howItWorks}
        </h2>

        <div className="mt-10 grid gap-10 sm:grid-cols-3">
          {t.home.steps.map((s, i) => (
            <ScrollReveal key={s.title} delay={i * 0.12}>
              <span className="text-xs font-semibold tabular-nums tracking-widest text-[var(--color-faint)]">
                {toFa(String(i + 1).padStart(2, "0"))}
              </span>

              <h3 className="mt-3 font-semibold text-[var(--color-ink)]">{s.title}</h3>

              <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">
                {s.body}
              </p>
            </ScrollReveal>
          ))}
        </div>
      </TiltOnScroll>

      {/* The differentiator the old page never showed: an actual scored card.
          "Explainable recommendations" is the whole pitch, so state it with a
          concrete example rather than an adjective. */}
      <TiltOnScroll className="border-t border-[var(--color-line)] py-16 lg:py-24">
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          هر پیشنهاد، دلیل دارد
        </h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-[var(--color-muted)]">
          به‌جای فهرست بی‌توضیح، هر محصول با امتیاز تفکیک‌شده می‌آید تا بدانید چرا
          انتخاب شده و کجا با سلیقه‌تان فاصله دارد.
        </p>

        <CardTilt3D className="mt-8 max-w-md">
        <Card className="overflow-hidden p-5">
          <p className="font-semibold text-[var(--color-ink)]">مبل مدرن — چرم عسلی</p>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {toFa("42,900,000")} {t.common.toman}
          </p>

          <div className="mt-4 space-y-2.5">
            {[
              { label: t.recommendations.scoreStyle, value: 58 },
              { label: t.recommendations.scoreColor, value: 50 },
              { label: t.recommendations.scoreBudget, value: 94 },
              { label: t.recommendations.scoreMaterial, value: 50 },
            ].map((row) => (
              <div key={row.label} className="flex items-center gap-3">
                <span className="w-24 shrink-0 text-xs text-[var(--color-muted)]">
                  {row.label}
                </span>
                <span
                  className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-line)]"
                  role="img"
                  aria-label={`${row.label}: ${toFa(row.value)} درصد`}
                >
                  {/* RTL: the track is a flex row so the fill starts at the
                      right edge, matching reading direction. A bare width on a
                      block child fills from the left and reads as inverted. */}
                  <span className="flex h-full w-full justify-end">
                    <span
                      className="block h-full rounded-full bg-[var(--color-accent)]"
                      style={{ width: `${row.value}%` }}
                    />
                  </span>
                </span>
                <span className="w-9 shrink-0 text-xs tabular-nums text-[var(--color-ink)]">
                  {toFa(row.value)}٪
                </span>
              </div>
            ))}
          </div>
        </Card>
        </CardTilt3D>
      </TiltOnScroll>

      <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          {t.home.stylesTitle}
        </h2>

        <p className="mt-2 text-sm text-[var(--color-muted)]">{t.home.stylesSubtitle}</p>

        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {STYLES.map((s, i) => (
            <ScrollReveal key={s.id} delay={i * 0.07}>
            <CardTilt3D>
            <Card className="overflow-hidden">
              <OptimizedImage
                src={s.image}
                alt={`نشیمن با سبک ${s.fa}`}
                width={320}
                height={200}
                sizes="(max-width: 640px) 50vw, 200px"
                wrapperClassName="h-24 w-full"
              />

              <p className="px-3 py-2.5 text-sm font-medium text-[var(--color-ink)]">
                {s.fa}
              </p>
            </Card>
            </CardTilt3D>
            </ScrollReveal>
          ))}
        </div>

        <div className="mt-10">
          <Link
            to={cta}
            className="inline-block rounded-xl bg-[var(--color-accent)] px-6 py-3 font-semibold text-[var(--color-canvas)] transition-opacity hover:opacity-90"
          >
            {user ? t.common.continue : t.home.cta}
          </Link>
        </div>
      </section>
    </ScrollStage>
  );
}
