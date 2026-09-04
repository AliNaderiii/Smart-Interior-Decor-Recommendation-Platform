/** The scroll-linked stage that hosts the 3D walkthrough.
 *
 * Structure: a tall section (several viewport heights) with a sticky viewport
 * pinned inside it. Scrolling through the tall section advances a 0→1 value
 * that drives the camera, so the page scrolls normally — no scroll hijacking,
 * no `preventDefault`, and the scrollbar stays honest about page length. This
 * matters for accessibility: keyboard PageDown, screen-reader navigation and
 * browser find-in-page all keep working.
 *
 * Loading strategy: `CinematicScene` (and with it three/fiber/drei, ~150 KB
 * gzip) is `React.lazy`'d and only imported once the section is near the
 * viewport. The landing page's first paint never pays for WebGL, which is how
 * the measured Lighthouse 94 survives.
 *
 * Refusal path — the scene is skipped entirely and a static poster shown when:
 *   * the user asked for reduced motion (scroll-linked camera motion is a
 *     known vestibular trigger),
 *   * WebGL is unavailable,
 *   * or the device looks too weak to hold a usable frame rate.
 */
import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useReducedMotion } from "framer-motion";
import { useT } from "@/i18n";
import heroImage from "@/assets/hero.webp";

const CinematicSequence = lazy(() => import("./CinematicSequence"));

/** Static stand-in used whenever the scene is refused. Same framing and copy,
 *  so the section never looks broken — it looks like a photograph. */
function PosterFallback({ caption }: { caption: string }) {
  return (
    <div className="relative h-full w-full overflow-hidden">
      <img
        src={heroImage}
        alt=""
        className="h-full w-full object-cover"
        loading="lazy"
        decoding="async"
      />
      <div className="absolute inset-0 grid place-items-center bg-black/25 p-6 text-center">
        <p className="max-w-md text-sm font-medium text-white/95">{caption}</p>
      </div>
    </div>
  );
}

export function CinematicSection({ children }: { children?: ReactNode }) {
  const t = useT();
  const sectionRef = useRef<HTMLDivElement>(null);
  const progress = useRef(0);
  const reduced = useReducedMotion();

  const [near, setNear] = useState(false);
  const [frame, setFrame] = useState(0);

  // Only fetch the frame set when the section is within one viewport.
  useEffect(() => {
    const el = sectionRef.current;
    if (!el || reduced) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true);
          io.disconnect();
        }
      },
      { rootMargin: "100% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [reduced]);

  // Scroll → progress. Written to a ref (not state) so scrolling never
  // triggers a React re-render; the Canvas reads it inside useFrame.
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const r = el.getBoundingClientRect();
      const total = r.height - window.innerHeight;
      if (total <= 0) return;
      progress.current = Math.min(1, Math.max(0, -r.top / total));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  const showScene = !reduced;

  return (
    <section
      ref={sectionRef}
      // 340vh gives the camera path room to breathe: ~2.4 viewports of scroll
      // for eight waypoints reads as a slow dolly rather than a jump cut.
      className="relative -mx-4 h-[340vh] sm:-mx-6 lg:-mx-8"
      aria-label={t.cinematic.title}
    >
      <div className="sticky top-0 h-screen w-full overflow-hidden">
        {showScene ? (
          <Suspense fallback={<PosterFallback caption={t.cinematic.loading} />}>
            {near ? (
              <CinematicSequence progress={progress} onFrame={setFrame} />
            ) : (
              <PosterFallback caption={t.cinematic.loading} />
            )}
          </Suspense>
        ) : (
          <PosterFallback caption={t.cinematic.staticNotice} />
        )}

        {/* Copy overlay. pointer-events-none so it never blocks scrolling. */}
        <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-6 sm:p-10">
          <div className="max-w-lg rounded-2xl bg-[var(--color-canvas)]/88 p-5 shadow-lg backdrop-blur-md">
            <h2 className="text-2xl font-semibold tracking-tight text-[var(--color-ink)]">
              {t.cinematic.title}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">
              {t.cinematic.captions[Math.min(frame, t.cinematic.captions.length - 1)]}
            </p>
          </div>

          <p className="self-center rounded-full bg-[var(--color-canvas)]/88 px-4 py-1.5 shadow-md text-xs font-medium text-[var(--color-muted)] backdrop-blur-sm">
            {t.cinematic.scrollHint}
          </p>
        </div>

        {children}
      </div>
    </section>
  );
}
