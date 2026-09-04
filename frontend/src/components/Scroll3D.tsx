/** Scroll-driven 3D presentation primitives.
 *
 * Scope, deliberately: this is *presentation only*. Nothing here touches the
 * recommender, the scoring payload, or any request. The AI extraction accuracy
 * (82.2% on the 50-image benchmark) is a backend property and is unaffected by
 * how a card is rotated on screen.
 *
 * Why CSS 3D transforms and not Three.js/WebGL:
 *   * `rotateX/rotateY/translateZ` are composited on the GPU by the browser
 *     with no extra bytes shipped. A WebGL scene would add ~150 KB gzip of
 *     runtime plus a canvas that competes with the product photography for
 *     paint time — for an effect the user perceives as "the page has depth".
 *   * framer-motion is already a dependency (used nowhere until now), so the
 *     marginal bundle cost of everything below is a few hundred bytes.
 *   * The perspective illusion degrades to a plain, correct page when the
 *     transforms are dropped, which is exactly what we want for
 *     `prefers-reduced-motion` and for low-end devices.
 *
 * Accessibility: every effect here is suppressed under
 * `prefers-reduced-motion: reduce`. Motion tied to scroll position is a known
 * vestibular trigger, so the reduced path renders static content rather than a
 * shortened animation.
 */
import { useRef, type ReactNode } from "react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "framer-motion";

/* ------------------------------------------------------------------ helpers */

/** Softens a raw scroll MotionValue so depth changes glide instead of tracking
 *  the wheel one-to-one, which reads as jittery on trackpads. */
function useSmooth(value: MotionValue<number>) {
  return useSpring(value, { stiffness: 120, damping: 30, mass: 0.4 });
}

/* ------------------------------------------------------------- ScrollStage */

/** Establishes the shared 3D viewing volume.
 *
 *  `perspective` must live on an ancestor of the transformed elements,
 *  otherwise each child gets its own vanishing point and the composition looks
 *  like unrelated pieces tilting independently rather than one scene with
 *  depth. */
export function ScrollStage({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <div
      className={className}
      style={{ perspective: "1200px", perspectiveOrigin: "50% 50%" }}
    >
      {children}
    </div>
  );
}

/* --------------------------------------------------------------- TiltOnScroll */

/** A section that rises out of the page as it enters the viewport: it starts
 *  pitched away from the reader and pushed back in Z, then settles flat and
 *  forward at centre screen. This is the "page is three-dimensional while you
 *  scroll" effect. */
export function TiltOnScroll({
  children,
  className = "",
  /** Degrees of initial pitch. Kept small — past ~12° text antialiasing
   *  visibly degrades on Windows. */
  intensity = 8,
}: {
  children: ReactNode;
  className?: string;
  intensity?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "center center"],
  });
  const p = useSmooth(scrollYProgress);

  const rotateX = useTransform(p, [0, 1], [intensity, 0]);
  const translateZ = useTransform(p, [0, 1], [-120, 0]);
  const opacity = useTransform(p, [0, 0.55], [0, 1]);

  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      ref={ref}
      className={className}
      style={{
        rotateX,
        translateZ,
        opacity,
        transformStyle: "preserve-3d",
        transformOrigin: "50% 100%",
        willChange: "transform, opacity",
      }}
    >
      {children}
    </motion.div>
  );
}

/* ---------------------------------------------------------------- ParallaxZ */

/** Moves an element along Y at a different rate than the page, producing the
 *  depth cue that sells the whole effect: near things travel further than far
 *  things. `depth` > 0 lags (reads as distant), < 0 leads (reads as close). */
export function ParallaxZ({
  children,
  className = "",
  depth = 40,
}: {
  children: ReactNode;
  className?: string;
  depth?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const p = useSmooth(scrollYProgress);
  const y = useTransform(p, [0, 1], [depth, -depth]);

  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div ref={ref} className={className} style={{ y, willChange: "transform" }}>
      {children}
    </motion.div>
  );
}

/* --------------------------------------------------------------- CardTilt3D */

/** Pointer-reactive tilt for a single card.
 *
 *  Pointer events only: on touch this would fight the scroll gesture, and
 *  `pointermove` does not fire on a plain tap, so touch users simply get the
 *  flat card. */
export function CardTilt3D({
  children,
  className = "",
  max = 7,
}: {
  children: ReactNode;
  className?: string;
  max?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  if (reduced) return <div className={className}>{children}</div>;

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== "mouse") return;
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    // -0.5..0.5 from the card centre, so the tilt follows the cursor.
    const dx = (e.clientX - r.left) / r.width - 0.5;
    const dy = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform =
      `perspective(700px) rotateY(${dx * max * 2}deg) rotateX(${-dy * max * 2}deg) translateZ(6px)`;
  };

  const reset = () => {
    const el = ref.current;
    if (el) el.style.transform = "perspective(700px) rotateY(0deg) rotateX(0deg) translateZ(0)";
  };

  return (
    <div
      ref={ref}
      className={className}
      onPointerMove={onMove}
      onPointerLeave={reset}
      style={{ transition: "transform 220ms cubic-bezier(0.22,1,0.36,1)", willChange: "transform" }}
    >
      {children}
    </div>
  );
}

/* ------------------------------------------------------------- ScrollReveal */

/** Staggered entrance for a list. Children rise and fade in sequence instead
 *  of the whole grid snapping in at once. */
export function ScrollReveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24, rotateX: 6 }}
      whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      style={{ transformStyle: "preserve-3d" }}
    >
      {children}
    </motion.div>
  );
}

/* ------------------------------------------------------------ ScrollProgress */

/** Thin reading-progress rail. RTL-aware: the document direction makes it
 *  fill right-to-left without a separate code path. */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 30, mass: 0.3 });
  const reduced = useReducedMotion();
  if (reduced) return null;

  return (
    <motion.div
      aria-hidden="true"
      style={{ scaleX, transformOrigin: "right" }}
      className="fixed inset-x-0 top-0 z-50 h-0.5 bg-[var(--color-accent)]"
    />
  );
}
