/** Scroll-driven photoreal walkthrough.
 *
 * Why an image sequence and not WebGL: the reference sites the client cited
 * (ApplyDesign, Roomtodo) both present photography — ApplyDesign's marketing
 * site ships no WebGL at all. Procedural geometry cannot reach photorealism,
 * and photoreal GLTF interiors run 3–15 MB per room plus a renderer.
 *
 * How the 18 frames stay visually identical
 * -----------------------------------------
 * Eight photoreal keyframes were generated, each using the previous as a
 * visual reference so architecture, materials and the blue-hour grade cannot
 * drift. The in-between frames are *derived* from those keyframes offline, so
 * every frame is literally the same photograph — there is no per-frame
 * regeneration that could repaint a wall or move a sofa.
 *
 * Why a <canvas> and not an <img> whose src we swap
 * -------------------------------------------------
 * The previous implementation set `el.src` on a single <img> each time the
 * scroll crossed a frame boundary. Measured on the deployed demo, every swap
 * cost **20–36 ms of decode** even with the file already in cache — against a
 * 16.7 ms budget at 60 fps. The compositor therefore presented a stale or
 * partially-uploaded texture on the swap frame, which is the flickering /
 * "static" artefact the user reported. It got worse the faster you scrolled
 * (more boundaries crossed per second) and almost vanished when scrolling
 * slowly, which matches the report exactly and rules out the network.
 *
 * The fix is to do zero decoding during scroll:
 *   1. Every frame is decoded once, up front, into an ImageBitmap (or an
 *      HTMLImageElement fallback) — a GPU-uploadable, already-decoded surface.
 *   2. Scrolling only ever issues `drawImage`, which is a texture blit.
 *   3. Drawing happens inside a single rAF loop that bails out when neither
 *      the frame index nor the Ken Burns scale has changed, so a stationary
 *      page costs nothing.
 *
 * Accessibility: `prefers-reduced-motion` renders one static frame with no
 * scroll coupling.
 */
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";

/** Vite resolves this at build time into a map of hashed asset URLs. */
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

/** Ken Burns push applied within a single frame's scroll step. */
const PUSH = 0.035;

/** Source frames are 16:9; the canvas backing store matches so `drawImage`
 *  never has to resample on a mismatched aspect. */
const BASE_W = 1280;
const BASE_H = 720;

type Surface = ImageBitmap | HTMLImageElement;

export default function CinematicSequence({
  progress,
  onFrame,
}: {
  progress: React.MutableRefObject<number>;
  onFrame?: (captionIndex: number) => void;
}) {
  const reduced = useReducedMotion();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const surfaces = useRef<(Surface | null)[]>(new Array(FRAMES.length).fill(null));
  const lastDrawn = useRef({ idx: -1, scale: -1 });
  const lastCaption = useRef(-1);
  const eased = useRef(0);
  const [firstReady, setFirstReady] = useState(false);

  /* ------------------------------------------------------------- decoding */

  useEffect(() => {
    let cancelled = false;

    const load = async (i: number): Promise<void> => {
      if (surfaces.current[i]) return;
      try {
        // createImageBitmap decodes off the main thread and yields a surface
        // the compositor can upload directly — no main-thread decode later.
        const res = await fetch(FRAMES[i]);
        const blob = await res.blob();
        const bmp = await createImageBitmap(blob);
        if (cancelled) {
          bmp.close?.();
          return;
        }
        surfaces.current[i] = bmp;
      } catch {
        // Safari < 15 and any fetch failure: fall back to a plain decoded
        // <img>, which drawImage accepts just as well.
        await new Promise<void>((resolve) => {
          const img = new Image();
          img.src = FRAMES[i];
          const done = () => {
            if (!cancelled) surfaces.current[i] = img;
            resolve();
          };
          img.decode?.().then(done, done) ?? (img.onload = done);
          img.onerror = () => resolve();
        });
      }
    };

    (async () => {
      // Frame 0 first so the section is never blank.
      await load(0);
      if (cancelled) return;
      setFirstReady(true);

      // Then a coarse spread so the whole journey is scrubbable early,
      // then fill the gaps. Concurrency is bounded so we neither stall on a
      // single request nor open 18 sockets at once.
      const coarse: number[] = [];
      for (let i = 2; i < FRAMES.length; i += 4) coarse.push(i);
      const rest: number[] = [];
      for (let i = 1; i < FRAMES.length; i++) {
        if (!coarse.includes(i)) rest.push(i);
      }
      const BATCH = 4;
      for (const group of [coarse, rest]) {
        for (let i = 0; i < group.length; i += BATCH) {
          if (cancelled) return;
          await Promise.all(group.slice(i, i + BATCH).map(load));
        }
      }
    })();

    return () => {
      cancelled = true;
      for (const s of surfaces.current) {
        if (s && "close" in s) s.close();
      }
    };
  }, []);

  /* -------------------------------------------------------------- drawing */

  useEffect(() => {
    if (reduced) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    // A modest backing store keeps `drawImage` cheap; the element is stretched
    // by CSS. At these dimensions the source is still denser than the CSS
    // pixels it covers on a phone, so it stays sharp.
    canvas.width = BASE_W;
    canvas.height = BASE_H;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    ctx.imageSmoothingQuality = "high";

    let raf = 0;

    /** Nearest already-decoded frame at or before `i`. Never look ahead: a
     *  frame from further along the journey would reveal the interior before
     *  the viewer has "entered", then appear to rewind. */
    const resolve = (i: number) => {
      for (let j = i; j >= 0; j--) if (surfaces.current[j]) return j;
      return -1;
    };

    const tick = () => {
      raf = requestAnimationFrame(tick);

      // Damp the raw scroll value: wheel and trackpad deltas arrive in jumps,
      // and sampling them directly makes the push-in judder.
      eased.current += (progress.current - eased.current) * 0.12;
      const p = Math.min(0.9999, Math.max(0, eased.current));

      const pos = p * (FRAMES.length - 1);
      const idx = Math.min(Math.round(pos), FRAMES.length - 1);
      const frac = pos - Math.floor(pos);
      const scale = 1 + PUSH * frac;

      const pick = resolve(idx);
      if (pick < 0) return;

      // Skip the blit entirely when nothing visible changed.
      const scaleQ = Math.round(scale * 500) / 500;
      if (lastDrawn.current.idx === pick && lastDrawn.current.scale === scaleQ) {
        return;
      }
      lastDrawn.current = { idx: pick, scale: scaleQ };

      const surface = surfaces.current[pick]!;
      // Ken Burns: draw a centre-biased crop scaled up to fill the canvas.
      const sw = BASE_W / scaleQ;
      const sh = BASE_H / scaleQ;
      const sx = (BASE_W - sw) / 2;
      const sy = (BASE_H - sh) * 0.55;
      ctx.drawImage(surface, sx, sy, sw, sh, 0, 0, BASE_W, BASE_H);

      const caption = Math.min(CAPTION_COUNT - 1, Math.floor(p * CAPTION_COUNT));
      if (caption !== lastCaption.current) {
        lastCaption.current = caption;
        onFrame?.(caption);
      }
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [progress, reduced, onFrame, firstReady]);

  /* ---------------------------------------------------------------- render */

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
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="absolute inset-0 h-full w-full object-cover"
      />
      {!firstReady && (
        <div className="absolute inset-0 animate-pulse bg-[#12100e]" aria-hidden="true" />
      )}
    </div>
  );
}
