/** Fullscreen presentation of a moodboard — lazy-loaded so framer-motion and
 *  this whole surface stay out of the editor's first paint.
 *
 *  RESEARCH_V2 §2 (Havenly/Decorilla): the concept board IS the deliverable
 *  that gets shown to a client. A designer should be able to walk through it
 *  one product at a time without any editor chrome in the frame. */
import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { RecommendedProduct } from "@/lib/types";
import { formatToman } from "@/lib/constants";
import { OptimizedImage } from "@/components/OptimizedImage";
import { useDialog } from "@/hooks/useDialog";

interface Props {
  title: string;
  products: RecommendedProduct[];
  onClose: () => void;
}

export default function PresentMode({ title, products, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState(1);
  const reduce = useReducedMotion();

  useDialog({
    isOpen: true,
    onClose,
    containerRef,
    restoreFocus: true,
    trapFocus: true,
    closeOnEscape: true,
    lockScroll: true,
  });

  const go = useCallback(
    (delta: number) => {
      setDir(delta);
      setIndex((i) => (i + delta + products.length) % products.length);
    },
    [products.length],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
      else if (e.key === "Home") setIndex(0);
      else if (e.key === "End") setIndex(products.length - 1);
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [go, products.length]);

  const p = products[index];
  if (!p) return null;

  const slide = reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        initial: { opacity: 0, x: dir * 40 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: dir * -40 },
      };

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-50 flex flex-col bg-[#0B0F17] text-white"
      role="dialog"
      aria-modal="true"
      aria-label={`Presenting ${title}`}
    >
      <header className="flex items-center justify-between px-6 py-4">
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs text-white/50">
            {index + 1} of {products.length} · arrow keys to navigate · Esc to exit
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl border border-white/20 px-3 py-1.5 text-sm hover:bg-white/10"
        >
          Exit
        </button>
      </header>

      <div className="relative flex min-h-0 flex-1 items-center justify-center px-4 pb-4">
        <button
          type="button"
          onClick={() => go(-1)}
          aria-label="Previous product"
          className="absolute left-4 z-10 grid h-12 w-12 place-items-center rounded-full bg-white/10 text-2xl hover:bg-white/20"
        >
          ‹
        </button>

        <AnimatePresence mode="wait" initial={false}>
          <motion.figure
            key={p.id}
            {...slide}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="flex h-full max-w-4xl flex-col items-center justify-center gap-5"
          >
            <OptimizedImage
              src={p.image_url}
              alt={p.title}
              width={1280}
              height={960}
              sizes="80vw"
              priority
              wrapperClassName="max-h-[62vh] w-auto rounded-2xl overflow-hidden"
            />
            <figcaption className="text-center">
              <p className="text-lg font-semibold">{p.title}</p>
              <p className="mt-1 text-sm text-white/60">{formatToman(p.price_toman)}</p>
            </figcaption>
          </motion.figure>
        </AnimatePresence>

        <button
          type="button"
          onClick={() => go(1)}
          aria-label="Next product"
          className="absolute right-4 z-10 grid h-12 w-12 place-items-center rounded-full bg-white/10 text-2xl hover:bg-white/20"
        >
          ›
        </button>
      </div>

      <nav className="flex justify-center gap-1.5 pb-6" aria-label="Slides">
        {products.map((item, i) => (
          <button
            key={item.id}
            type="button"
            onClick={() => { setDir(i > index ? 1 : -1); setIndex(i); }}
            aria-label={`Go to ${item.title}`}
            aria-current={i === index}
            className={`h-1.5 rounded-full transition-all ${
              i === index ? "w-8 bg-white" : "w-1.5 bg-white/30 hover:bg-white/50"
            }`}
          />
        ))}
      </nav>
    </div>
  );
}
