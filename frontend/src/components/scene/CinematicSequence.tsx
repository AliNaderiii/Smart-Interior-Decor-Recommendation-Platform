/** Scroll-driven photoreal walkthrough.
 *
 * Why an image sequence and not WebGL: the reference sites the client cited
 * (ApplyDesign, Roomtodo) both present photography — ApplyDesign's marketing
 * site ships no WebGL at all. Procedural geometry cannot reach photorealism,
 * and photoreal GLTF interiors run 3–15 MB per room plus a renderer.
 *
 * How the 36 frames stay visually identical
 * -----------------------------------------
 * Eight photoreal keyframes were generated, each using the previous as a
 * visual reference so the architecture, materials and blue-hour grade cannot
 * drift. The 28 in-between frames are then *derived* from those keyframes
 * offline (dissolve + matched push-in), so every frame is literally the same
 * photograph — there is no per-frame regeneration that could change a wall
 * colour or move a sofa. That was the flaw in the first six-frame attempt:
 * each shot was generated independently and they did not match.
 *
 * Playback
 * --------
 * Frames are hard-selected by scroll position rather than cross-faded in the
 * browser. At 36 frames the steps are small enough that a straight cut reads
 * as motion — exactly how a scrubbed video behaves — and it avoids the
 * double-exposure ghosting a long CSS fade produces. A slow Ken Burns push is
 * still applied within each step so the motion never fully stops.
 *
 * Loading
 * -------
 * Frames stream in priority order: the first frame is fetched eagerly, the
 * rest are warmed in the background after mount. Until a frame has decoded,
 * the nearest already-decoded frame is shown, so scrolling early never shows
 * a blank.
 *
 * Accessibility: `prefers-reduced-motion` renders one static frame with no
 * scroll coupling.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";

/** Vite resolves this at build time into a map of hashed asset URLs. Using a
 *  glob rather than 36 import statements keeps the frame count a data
 *  question, not a code change. */
const MODULES = import.meta.glob<string>("@/assets/scene/frame*.webp", {
  eager: true,
  import: "default",
});

const FRAMES: string[] = Object.keys(MODULES)
  .sort()
  .map((k) => MODULES[k]);

export const FRAME_COUNT = FRAMES.length;

/** Six narrative beats spread across the frame range. */
const CAPTION_COUNT = 6;

/** Ken Burns push within a single frame's scroll step. */
const PUSH = 0.035;

export default function CinematicSequence({
  progress,
  onFrame,
}: {
  progress: React.MutableRefObject<number>;
  onFrame?: (captionIndex: number) => void;
}) {
  const reduced = useReducedMotion();
  const imgRef = useRef<HTMLImageElement>(null);
  const decoded = useRef<boolean[]>(new Array(FRAMES.length).fill(false));
  const currentSrc = useRef<string>("");
  const lastCaption = useRef(-1);
  const eased = useRef(0);
  const [, force] = useState(0);

  // Warm every frame in the background, in order, so early scrolling has
  // something to show and later scrolling is already resident.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let i = 0; i < FRAMES.length; i++) {
        if (cancelled) return;
        await new Promise<void>((resolve) => {
          const img = new Image();
          img.src = FRAMES[i];
          const done = () => {
            decoded.current[i] = true;
            resolve();
          };
          img.decode?.().then(done, done) ?? (img.onload = done);
        });
        if (i === 0) force((n) => n + 1);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** Nearest frame at or before `i` that has finished decoding. */
  const resolveFrame = useMemo(
    () => (i: number) => {
      for (let j = i; j >= 0; j--) if (decoded.current[j]) return j;
      for (let j = i + 1; j < FRAMES.length; j++) if (decoded.current[j]) return j;
      return 0;
    },
    [],
  );

  useEffect(() => {
    if (reduced) return;
    let raf = 0;

    const tick = () => {
      // Damp the raw scroll value: wheel and trackpad deltas arrive in jumps,
      // and sampling them directly makes the push-in judder.
      eased.current += (progress.current - eased.current) * 0.12;
      const p = Math.min(0.9999, Math.max(0, eased.current));

      const pos = p * (FRAMES.length - 1);
      const idx = Math.round(pos);
      const frac = pos - Math.floor(pos);

      const el = imgRef.current;
      if (el) {
        const src = FRAMES[resolveFrame(idx)];
        if (src !== currentSrc.current) {
          currentSrc.current = src;
          el.src = src;
        }
        el.style.transform = `scale(${1 + PUSH * frac})`;
      }

      const caption = Math.min(
        CAPTION_COUNT - 1,
        Math.floor(p * CAPTION_COUNT),
      );
      if (caption !== lastCaption.current) {
        lastCaption.current = caption;
        onFrame?.(caption);
      }
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [progress, reduced, onFrame, resolveFrame]);

  if (reduced) {
    return (
      <img
        src={FRAMES[Math.floor(FRAMES.length / 2)]}
        alt=""
        className="h-full w-full object-cover"
        decoding="async"
      />
    );
  }

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#12100e]">
      <img
        ref={imgRef}
        src={FRAMES[0]}
        alt=""
        aria-hidden="true"
        className="absolute inset-0 h-full w-full object-cover will-change-transform"
        style={{ transformOrigin: "center 55%" }}
        decoding="sync"
        fetchPriority="high"
      />
    </div>
  );
}
