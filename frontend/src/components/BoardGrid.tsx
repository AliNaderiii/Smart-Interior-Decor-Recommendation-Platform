/** Drag & resize moodboard grid — isolated so react-grid-layout stays in a
 *  lazy chunk (Vite manualChunks: "gridlayout") off the LCP critical path. */
import { GridLayout, noCompactor, type Layout } from "react-grid-layout";
import type { RecommendedProduct } from "@/lib/types";
import { OptimizedImage } from "@/components/OptimizedImage";

interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Props {
  layout: LayoutItem[];
  products: Record<string, RecommendedProduct>;
  onLayoutChange: (next: readonly LayoutItem[]) => void;
  /** Canvas width in px — driven by the editor's zoom control. */
  width?: number;
}

export default function BoardGrid({ layout, products, onLayoutChange, width = 1080 }: Props) {
  return (
    <GridLayout
      className="layout"
      layout={layout as Layout}
      width={width}
      gridConfig={{ cols: 12, rowHeight: 40 }}
      compactor={noCompactor}
      onLayoutChange={(next: Layout) =>
        onLayoutChange(next.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h })))
      }
    >
      {layout.map((l) => {
        const p = products[l.i];
        return (
          // `.board-card` tilts the card 1.5deg while react-grid-layout has it
          // in flight — the physical "picking up a photo" cue from a real
          // pinboard, which pure translation never conveys.
          <div key={l.i} className="board-card overflow-hidden rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] shadow-[var(--shadow-card)]">
            {p ? (
              <div className="flex h-full flex-col">
                <OptimizedImage
                  src={p.image_url}
                  alt={p.title}
                  width={320}
                  height={220}
                  sizes="(max-width: 768px) 50vw, 25vw"
                  wrapperClassName="min-h-0 w-full flex-1"
                  className="select-none"
                />
                <div className="truncate px-2 py-1.5 text-[11px] font-medium text-[var(--color-ink)]">{p.title}</div>
              </div>
            ) : (
              <div className="grid h-full place-items-center text-xs text-[var(--color-faint)]">Unavailable</div>
            )}
          </div>
        );
      })}
    </GridLayout>
  );
}
