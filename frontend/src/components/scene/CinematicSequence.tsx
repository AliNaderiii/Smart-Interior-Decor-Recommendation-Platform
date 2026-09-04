/** Scroll-driven photoreal walkthrough.
 *
 * Why an image sequence and not WebGL: the reference sites the client cited
 * (ApplyDesign, Roomtodo) both present photography — ApplyDesign's marketing
 * site ships no WebGL at all. Procedural geometry cannot reach photorealism,
 * and photoreal GLTF interiors run 3–15 MB per room plus a renderer. Eleven
 * 1600×900 WebP stills total ~1.4 MB and look like the product.
 *
 * Cinematic feel — the three things that separate "film" from "slideshow":
 *
 *  1. DENSITY. Six frames over ~2.4 viewports meant a cut every ~0.4 screens.
 *     Now eleven frames over ~7 viewports: each shot holds for most of a
 *     screen of scrolling before it yields.
 *  2. HOLD-THEN-DISSOLVE. A linear cross-fade leaves two photographs at 50%
 *     for half the step, which reads as a double exposure. Each frame instead
 *     holds fully opaque, then dissolves over the last ~28% of its step with
 *     a smoothstep curve so the hand-off has no hard edges.
 *  3. CONTINUOUS PUSH-IN. A still that does not move is a slide. Every frame
 *     is very slowly scaled (a Ken Burns push) across its entire step, and the
 *     incoming frame starts fractionally wider so the motion carries across
 *     the dissolve instead of resetting.
 *
 * Performance: frames are decoded up front so scrolling never hits a decode
 * stall; progress is read from a ref inside rAF, so scrolling causes no React
 * re-render. The module is lazy-loaded by the parent section.
 *
 * Accessibility: `prefers-reduced-motion` renders one static frame with no
 * scroll coupling.
 */
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";

import frame01 from "@/assets/scene/frame01.webp";
import frame02 from "@/assets/scene/frame02.webp";
import frame03 from "@/assets/scene/frame03.webp";
import frame04 from "@/assets/scene/frame04.webp";
import frame05 from "@/assets/scene/frame05.webp";
import frame06 from "@/assets/scene/frame06.webp";
import frame07 from "@/assets/scene/frame07.webp";
import frame08 from "@/assets/scene/frame08.webp";
import frame09 from "@/assets/scene/frame09.webp";
import frame10 from "@/assets/scene/frame10.webp";
import frame11 from "@/assets/scene/frame11.webp";

const FRAMES = [
  frame01, frame02, frame03, frame04, frame05, frame06,
  frame07, frame08, frame09, frame10, frame11,
];

export const FRAME_COUNT = FRAMES.length;

/** Maps each frame to one of the six narrative captions. */
const CAPTION_OF_FRAME = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5];

/** Fraction of a step spent fully on one frame before the dissolve starts. */
const HOLD = 0.72;
/** Ken Burns push applied across a single step. Subtle on purpose: anything
 *  above ~6% starts to look like a zoom effect rather than a camera move. */
const PUSH = 0.055;

/** Smoothstep — removes the linear ramp's visible start/stop. */
function smooth(t: number): number {
  return t * t * (3 - 2 * t);
}

export default function CinematicSequence({
  progress,
  onFrame,
}: {
  progress: React.MutableRefObject<number>;
  onFrame?: (captionIndex: number) => void;
}) {
  const reduced = useReducedMotion();
  const imgRefs = useRef<(HTMLImageElement | null)[]>([]);
  const [ready, setReady] = useState(false);
  const lastCaption = useRef(-1);
  const eased = useRef(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      FRAMES.map(
        (src) =>
          new Promise<void>((resolve) => {
            const img = new Image();
            img.src = src;
            img.decode?.().then(() => resolve(), () => resolve()) ??
              (img.onload = () => resolve());
          }),
      ),
    ).then(() => {
      if (!cancelled) setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (reduced) return;
    let raf = 0;

    const tick = () => {
      // Damp the raw scroll value. Wheel and trackpad deltas arrive in jumps;
      // sampling them directly makes the push-in judder.
      eased.current += (progress.current - eased.current) * 0.09;
      const p = Math.min(0.9999, Math.max(0, eased.current));

      const pos = p * (FRAMES.length - 1);
      const base = Math.floor(pos);
      const frac = pos - base;

      // Hold, then dissolve over the tail of the step.
      const dissolve = frac <= HOLD ? 0 : smooth((frac - HOLD) / (1 - HOLD));

      for (let i = 0; i < FRAMES.length; i++) {
        const el = imgRefs.current[i];
        if (!el) continue;

        if (i === base) {
          el.style.opacity = String(1 - dissolve);
          // Push in across the whole step, not just the dissolve.
          el.style.transform = `scale(${1 + PUSH * frac})`;
        } else if (i === base + 1) {
          el.style.opacity = String(dissolve);
          // Start slightly wider than where the outgoing frame ends so the
          // move continues through the cut instead of snapping back.
          el.style.transform = `scale(${1 + PUSH * 0.35 * (1 - dissolve)})`;
        } else if (el.style.opacity !== "0") {
          el.style.opacity = "0";
        }
      }

      const caption = CAPTION_OF_FRAME[Math.min(base, CAPTION_OF_FRAME.length - 1)];
      if (caption !== lastCaption.current) {
        lastCaption.current = caption;
        onFrame?.(caption);
      }
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [progress, reduced, onFrame]);

  if (reduced) {
    return (
      <img
        src={FRAMES[6]}
        alt=""
        className="h-full w-full object-cover"
        decoding="async"
      />
    );
  }

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#1a1410]">
      {FRAMES.map((src, i) => (
        <img
          key={src}
          ref={(el) => {
            imgRefs.current[i] = el;
          }}
          src={src}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-cover will-change-[opacity,transform]"
          style={{ opacity: i === 0 ? 1 : 0, transformOrigin: "center 55%" }}
          decoding="async"
          fetchPriority={i === 0 ? "high" : "low"}
        />
      ))}
      {!ready && (
        <div className="absolute inset-0 animate-pulse bg-[#1a1410]" aria-hidden="true" />
      )}
    </div>
  );
}
