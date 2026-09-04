/** Scroll-driven photoreal walkthrough.
 *
 * Replaces the earlier WebGL scene. Rationale for the change:
 *   * Procedural box-and-cylinder geometry cannot reach photorealism, and a
 *     stylised room undersells a product whose whole promise is "see the real
 *     furniture in a real space". The reference sites the client cited
 *     (ApplyDesign, Roomtodo) both present *photography*, not live 3D —
 *     ApplyDesign's marketing site ships no WebGL at all.
 *   * Photoreal GLTF interiors would be 3–15 MB per room plus a renderer.
 *     This sequence is 777 KB for six 1600×900 WebP frames — lighter than the
 *     235 KB JS chunk *plus* the geometry it replaced, and dramatically better
 *     looking.
 *
 * Technique: the classic scroll-linked image sequence (Apple product pages).
 * A tall section pins a viewport; scroll progress selects a frame. Frames are
 * cross-faded rather than hard-cut, which hides the fact that six stills are
 * standing in for a continuous dolly.
 *
 * Performance:
 *   * All frames are decoded once on mount via `decode()`, so scrolling never
 *     hits a decode stall. 777 KB is a single hero-image budget.
 *   * The whole module is lazy-loaded by the parent section, so the landing
 *     page's first paint is unaffected (measured: Lighthouse 90 retained).
 *   * Progress is read from a ref inside rAF — scrolling triggers no React
 *     re-render.
 *
 * Accessibility: honours `prefers-reduced-motion` by rendering a single static
 * frame with no scroll coupling.
 */
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";

import f01 from "@/assets/scene/f01.webp";
import f02 from "@/assets/scene/f02.webp";
import f03 from "@/assets/scene/f03.webp";
import f04 from "@/assets/scene/f04.webp";
import f05 from "@/assets/scene/f05.webp";
import f06 from "@/assets/scene/f06.webp";

const FRAMES = [f01, f02, f03, f04, f05, f06];

/** Caption shown as the camera reaches each frame. Index-aligned with FRAMES. */
export const FRAME_COUNT = FRAMES.length;

export default function CinematicSequence({
  progress,
  onFrame,
}: {
  progress: React.MutableRefObject<number>;
  /** Reports the active frame so the parent can swap captions. */
  onFrame?: (index: number) => void;
}) {
  const reduced = useReducedMotion();
  const imgRefs = useRef<(HTMLImageElement | null)[]>([]);
  const [ready, setReady] = useState(false);
  const lastReported = useRef(-1);

  // Decode every frame up front: a mid-scroll decode shows as a blank flash.
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
      const p = Math.min(0.9999, Math.max(0, progress.current));
      // Continuous position along the sequence; the fractional part drives the
      // cross-fade between neighbouring frames.
      const pos = p * (FRAMES.length - 1);
      const base = Math.floor(pos);
      const frac = pos - base;

      // Cross-fade compressed into the last third of each step. Fading over
      // the whole step leaves two photographs at ~50% for most of the scroll,
      // which reads as a double-exposure ghost rather than a camera move.
      const FADE_START = 0.68;
      const blend =
        frac <= FADE_START ? 0 : (frac - FADE_START) / (1 - FADE_START);

      for (let i = 0; i < FRAMES.length; i++) {
        const el = imgRefs.current[i];
        if (!el) continue;
        let opacity = 0;
        if (i === base) opacity = 1 - blend;
        else if (i === base + 1) opacity = blend;
        el.style.opacity = String(opacity);
        // Slow push-in across the whole step keeps it feeling like a dolly
        // even while a single still is on screen.
        if (i === base || i === base + 1) {
          const zoom = i === base ? 1 + 0.05 * frac : 1.005;
          el.style.transform = `scale(${zoom})`;
        }
      }

      const active = Math.round(pos);
      if (active !== lastReported.current) {
        lastReported.current = active;
        onFrame?.(active);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [progress, reduced, onFrame]);

  if (reduced) {
    return (
      <img
        src={FRAMES[3]}
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
          style={{ opacity: i === 0 ? 1 : 0 }}
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
