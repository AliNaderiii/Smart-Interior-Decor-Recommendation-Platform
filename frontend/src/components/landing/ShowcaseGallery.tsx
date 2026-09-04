/** Scroll-revealed showcase of what the platform produces.
 *
 * Replaces the 29-frame cinematic walkthrough. Rationale for the change
 * (client decision, and the right one): the walkthrough was decorative — a
 * corridor of a house that is not our product. Each card here instead proves
 * one concrete capability and says what the user gets, which is both more
 * persuasive and cheaper (four lazy images vs 3.4 MB of frames).
 *
 * Layout borrows the competitor's alternating image/text rhythm, but the
 * content is ours: every card is tied to a capability they do not have —
 * scored recommendations, real Toman prices, dimensioned floorplans.
 */
import { useT } from "@/i18n";
import { ScrollReveal, CardTilt3D } from "@/components/Scroll3D";
import { BeforeAfter } from "./BeforeAfter";

import beforeEmpty from "@/assets/gallery/before-empty.webp";
import afterFurnished from "@/assets/gallery/after-furnished.webp";
import gModern from "@/assets/gallery/g-modern.webp";
import gScandinavian from "@/assets/gallery/g-scandinavian.webp";
import gBoho from "@/assets/gallery/g-boho.webp";
import gClassic from "@/assets/gallery/g-classic.webp";

const STYLE_SHOTS = [
  { src: gModern, key: "modern" },
  { src: gScandinavian, key: "scandinavian" },
  { src: gBoho, key: "boho" },
  { src: gClassic, key: "classic" },
] as const;

export function ShowcaseGallery() {
  const t = useT();

  return (
    <section className="border-t border-[var(--color-line)] py-16 lg:py-24">
      <ScrollReveal>
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
          {t.gallery.title}
        </h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-[var(--color-muted)]">
          {t.gallery.subtitle}
        </p>
      </ScrollReveal>

      {/* Hero proof: empty room -> furnished from our recommendations. */}
      <ScrollReveal delay={0.1}>
        <div className="mt-10 grid items-center gap-8 lg:grid-cols-2">
          <BeforeAfter
            beforeSrc={beforeEmpty}
            afterSrc={afterFurnished}
            beforeLabel={t.gallery.before}
            afterLabel={t.gallery.after}
          />
          <div>
            <h3 className="text-xl font-semibold text-[var(--color-ink)]">
              {t.gallery.baTitle}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">
              {t.gallery.baBody}
            </p>
            <p className="mt-3 text-xs text-[var(--color-faint)]">
              {t.gallery.baHint}
            </p>
          </div>
        </div>
      </ScrollReveal>

      {/* Style range. Each shot is what a completed room looks like for that
          style in our taxonomy — the same ids the recommender scores against. */}
      <ScrollReveal delay={0.15}>
        <h3 className="mt-16 text-xl font-semibold text-[var(--color-ink)]">
          {t.gallery.stylesTitle}
        </h3>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-[var(--color-muted)]">
          {t.gallery.stylesBody}
        </p>
      </ScrollReveal>

      <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
        {STYLE_SHOTS.map((shot, i) => {
          const copy = t.gallery.styleCards[i];
          return (
            <ScrollReveal key={shot.key} delay={i * 0.08}>
              <CardTilt3D>
                <figure className="overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface,transparent)]">
                  <img
                    src={shot.src}
                    alt={copy.title}
                    className="aspect-[16/10] w-full object-cover"
                    loading="lazy"
                    decoding="async"
                  />
                  <figcaption className="p-4">
                    <p className="font-semibold text-[var(--color-ink)]">{copy.title}</p>
                    <p className="mt-1 text-sm leading-relaxed text-[var(--color-muted)]">
                      {copy.body}
                    </p>
                  </figcaption>
                </figure>
              </CardTilt3D>
            </ScrollReveal>
          );
        })}
      </div>
    </section>
  );
}
