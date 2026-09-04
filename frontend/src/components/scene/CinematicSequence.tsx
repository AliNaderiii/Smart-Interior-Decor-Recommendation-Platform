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
  const lastShown = useRef(0);
  const eased = useRef(0);
  const [, force] = useState(0);

  // Warm frames in PARALLEL, coarse-to-fine.
  //
  // The first implementation walked 0..35 sequentially and awaited each one.
  // On a slow connection the user out-scrolls the loader: the <img> pins to
  // the last decoded frame (observed on production — the sequence froze on
  // frame21 while the scroll was already at frame35) and the walkthrough
  // looks broken.
  //
  // Instead: fetch a sparse spread across the whole range first, so *some*
  // frame is available at every scroll position within the first moments,
  // then fill in the gaps. Requests are issued concurrently and never
  // awaited in series.
  useEffect(() => {
    let cancelled = false;

    const warm = (i: number) =>
      new Promise<void>((resolve) => {
        if (decoded.current[i]) return resolve();
        const img = new Image();
        img.src = FRAMES[i];
        const done = () => {
          decoded.current[i] = true;
          resolve();
        };
        img.decode?.().then(done, done) ?? (img.onload = done);
        img.onerror = done;
      });

    (async () => {
      // Pass 1: every 2nd frame (~9 images, ~560 KB) so the whole journey is
      // scrubbable within the first moments even on a slow link. The set was
      // reduced from 36 to 18 frames for the same reason: measured on a
      // throttled connection, 36 frames could not warm before a normal user
      // had scrolled the section, so the shot visibly froze.
      const coarse = [];
      for (let i = 0; i < FRAMES.length; i += 2) coarse.push(i);
      if (!coarse.includes(FRAMES.length - 1)) coarse.push(FRAMES.length - 1);
      await Promise.all(coarse.map(warm));
      if (cancelled) return;
      force((n) => n + 1);

      // Pass 2: everything else, in small concurrent batches so we neither
      // stall on one image nor open 36 sockets at once.
      const rest = [];
      for (let i = 0; i < FRAMES.length; i++) if (!coarse.includes(i)) rest.push(i);
      const BATCH = 8;
      for (let i = 0; i < rest.length; i += BATCH) {
        if (cancelled) return;
        await Promise.all(rest.slice(i, i + BATCH).map(warm));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  /** Best decoded frame to display for scroll index `i`.
   *
   *  Searches BACKWARDS only. Showing a frame from further along the journey
   *  than the user has actually scrolled is worse than showing an earlier one:
   *  it reveals the interior before they have "entered", and then appears to
   *  rewind once the correct frame decodes. Measured on a throttled
   *  connection, the bidirectional version opened on frame 17 of 18 and then
   *  jumped back to 9.
   *
   *  Frame 0 is fetched eagerly, so the backwards search almost always
   *  terminates on something real. */
  const resolveFrame = useMemo(
    () => (i: number) => {
      for (let j = i; j >= 0; j--) if (decoded.current[j]) return j;
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
        // Clamp to the scroll position: never show a frame the user has not
        // reached. Combined with the backwards-only search this makes the
        // sequence monotonic while warming — it may lag, but it never jumps
        // ahead and never rewinds.
        const pick = Math.min(resolveFrame(idx), idx);
        lastShown.current = pick;
        const src = FRAMES[pick];
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
