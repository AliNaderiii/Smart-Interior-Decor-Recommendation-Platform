/** Drag & resize moodboard grid — isolated so react-grid-layout stays in a
 *  lazy chunk (Vite manualChunks: "gridlayout") off the LCP critical path. */
import { GridLayout, noCompactor, type Layout } from "react-grid-layout";
import type { RecommendedProduct } from "@/lib/types";

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
}

export default function BoardGrid({ layout, products, onLayoutChange }: Props) {
  return (
    <GridLayout
      className="layout"
      layout={layout as Layout}
      width={1080}
      gridConfig={{ cols: 12, rowHeight: 40 }}
      compactor={noCompactor}
      onLayoutChange={(next: Layout) =>
        onLayoutChange(next.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h })))
      }
    >
      {layout.map((l) => {
        const p = products[l.i];
        return (
          <div key={l.i} className="border border-[#eee7db] bg-white">
            {p ? (
              <div className="flex h-full flex-col">
                <img
                  src={p.image_url}
                  alt={p.title}
                  loading="lazy"
                  className="min-h-0 w-full flex-1 object-cover"
                  draggable={false}
                />
                <div className="truncate px-2 py-1 text-[11px] font-medium">{p.title}</div>
              </div>
            ) : (
              <div className="grid h-full place-items-center text-xs text-stone">?</div>
            )}
          </div>
        );
      })}
    </GridLayout>
  );
}
