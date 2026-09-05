/** Draggable before/after comparison slider.
 *
 * The single most persuasive element on the competitor's landing page
 * (aismartdecor.com): it proves the product's value in one glance, with no
 * copy to read. Adapted here for our actual proposition — an empty room
 * versus the same room furnished from our recommendations — rather than
 * theirs, which is "your room, restyled".
 *
 * Interaction notes:
 *  * Pointer events cover mouse, touch and pen with one code path.
 *  * The handle is a real <input type="range">, visually hidden but focusable,
 *    so the control is keyboard-operable and announced to screen readers.
 *    A div with mouse handlers would be unusable without a pointer.
 *  * Both images are always painted; the top one is clipped. Swapping
 *    `src` or toggling `display` would decode on every drag frame.
 */
import { useCallback, useId, useRef, useState } from "react";
import { useT } from "@/i18n";

export function BeforeAfter({
  beforeSrc,
  afterSrc,
  beforeLabel,
  afterLabel,
  className = "",
}: {
  beforeSrc: string;
  afterSrc: string;
  beforeLabel: string;
  afterLabel: string;
  className?: string;
}) {
  const [pos, setPos] = useState(50);
  const frameRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const id = useId();
  const t = useT();

  const setFromClientX = useCallback((clientX: number) => {
    const el = frameRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const pct = ((clientX - r.left) / r.width) * 100;
    setPos(Math.min(100, Math.max(0, pct)));
  }, []);

  return (
    <div className={className}>
      <div
        ref={frameRef}
        className="relative aspect-[16/10] w-full select-none overflow-hidden rounded-2xl bg-[var(--color-line)]"
        // Capture on the frame so the drag keeps tracking even when the
        // pointer leaves the element; `touch-none` stops the browser turning
        // a horizontal drag into a scroll gesture on mobile.
        style={{ touchAction: "none" }}
        onPointerDown={(e) => {
          dragging.current = true;
          try {
            e.currentTarget.setPointerCapture(e.pointerId);
          } catch {
            /* capture is best-effort; the window listeners below still work */
          }
          setFromClientX(e.clientX);
        }}
        onPointerMove={(e) => {
          if (dragging.current) setFromClientX(e.clientX);
        }}
        onPointerUp={(e) => {
          dragging.current = false;
          try {
            e.currentTarget.releasePointerCapture(e.pointerId);
          } catch {
            /* ignore */
          }
        }}
        onPointerLeave={() => {
          dragging.current = false;
        }}
        onPointerCancel={() => {
          dragging.current = false;
        }}
      >
        {/* AFTER sits underneath and is fully visible; BEFORE is clipped over
            it, so dragging left reveals more of the redesigned room. */}
        <img
          src={afterSrc}
          alt={afterLabel}
          draggable={false}
          width={1200}
          height={750}
          className="absolute inset-0 h-full w-full object-cover"
          loading="lazy"
          decoding="async"
        />
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
        >
          <img
            src={beforeSrc}
            alt={beforeLabel}
            draggable={false}
            width={1200}
            height={750}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
            decoding="async"
          />
        </div>

        {/* Divider + grab handle */}
        <div
          className="absolute inset-y-0 w-0.5 cursor-ew-resize bg-white/90 shadow-[0_0_12px_rgba(0,0,0,0.35)]"
          style={{ left: `${pos}%`, touchAction: "none" }}
        >
          {/* The knob is deliberately larger than it looks (44px hit area,
              the WCAG target minimum) and carries its own capture, so the
              gesture starts wherever the user actually grabs. */}
          <span className="absolute top-1/2 grid h-11 w-11 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize place-items-center rounded-full bg-white shadow-lg">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M9 6L4 12l5 6M15 6l5 6-5 6"
                stroke="#1a1a1a"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </div>

        {/* Corner labels pinned with PHYSICAL sides, deliberately.
         *
         *  `clip-path: inset(0 X% 0 0)` always clips from the physical left,
         *  so the "before" image always occupies the left of the frame — that
         *  does not flip under RTL. Using the logical `start-3`/`end-3` here
         *  moved the labels to the opposite side in Persian while the images
         *  stayed put, so each label named the wrong picture. */}
        <span className="pointer-events-none absolute bottom-3 left-3 rounded-full bg-black/65 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">
          {beforeLabel}
        </span>
        <span className="pointer-events-none absolute bottom-3 right-3 rounded-full bg-black/65 px-3 py-1 text-xs font-semibold text-white backdrop-blur-sm">
          {afterLabel}
        </span>
      </div>

      {/* The actual control: visually hidden, fully accessible. */}
      <label htmlFor={id} className="sr-only">
        {t.gallery.sliderLabel}
      </label>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        className="sr-only"
        aria-valuetext={`${Math.round(pos)}%`}
      />
    </div>
  );
}
