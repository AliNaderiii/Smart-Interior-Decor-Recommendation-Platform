import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import type { Moodboard, MoodboardItem } from "@/lib/types";
import { formatToman } from "@/lib/constants";
import { Button, Card, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { useToast } from "@/components/Toast";
import { useCommands } from "@/components/CommandPalette";

// react-grid-layout is heavy — lazy-load it off the critical path (LCP budget)
const BoardGrid = lazy(() => import("@/components/BoardGrid"));
const PresentMode = lazy(() => import("@/components/PresentMode"));

interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

const ZOOM_STEPS = [0.6, 0.75, 0.9, 1, 1.15, 1.35] as const;
const BASE_WIDTH = 1080;

/** Layouts are value objects; comparing serialised form is cheap enough at
 *  board scale (tens of items) and avoids pushing no-op history entries when
 *  react-grid-layout re-emits an identical layout on mount. */
function sameLayout(a: LayoutItem[], b: LayoutItem[]) {
  if (a.length !== b.length) return false;
  return a.every((l, i) => {
    const o = b[i];
    return o && l.i === o.i && l.x === o.x && l.y === o.y && l.w === o.w && l.h === o.h;
  });
}

function ToolbarButton({
  children,
  label,
  onClick,
  disabled,
  active,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={`grid h-8 min-w-8 place-items-center rounded-lg px-2 text-xs font-medium transition-colors disabled:opacity-35 ${
        active
          ? "bg-[var(--color-accent)] text-[var(--color-canvas)]"
          : "text-[var(--color-muted)] hover:bg-[var(--color-line)] hover:text-[var(--color-ink)]"
      }`}
    >
      {children}
    </button>
  );
}

export default function MoodboardEditorPage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const [saved, setSaved] = useState(true);
  const [zoom, setZoom] = useState(3); // index into ZOOM_STEPS -> 1.0
  const [dots, setDots] = useState(true);
  const [presenting, setPresenting] = useState(false);

  const { data: board, isLoading, isError, refetch } = useQuery({
    queryKey: ["moodboard", id],
    queryFn: () => get<Moodboard>(`/moodboards/${id}`),
    enabled: Boolean(id),
  });

  const [layoutOverride, setLayoutOverride] = useState<LayoutItem[] | null>(null);

  const layout: LayoutItem[] = useMemo(() => {
    if (layoutOverride) return layoutOverride;
    return (board?.items ?? []).map((item) => ({
      i: item.product_id, x: item.x, y: item.y, w: item.w, h: item.h,
    }));
  }, [board, layoutOverride]);

  /* ----------------------------------------------------------- history stack
   * Linear's rule (RESEARCH_V2 §5): never ask "are you sure?", just make the
   * action reversible. Past/future stacks hold whole layouts — a board is
   * small, so snapshotting beats diffing. */
  const past = useRef<LayoutItem[][]>([]);
  const future = useRef<LayoutItem[][]>([]);
  const [historyTick, setHistoryTick] = useState(0);

  const save = useMutation({
    mutationFn: (items: MoodboardItem[]) => patch(`/moodboards/${id}`, { items }),
    onSuccess: () => setSaved(true),
    onError: () => toast.error("Could not save the layout."),
  });

  // Debounced autosave (500ms): drags fire onLayoutChange rapidly — we only
  // persist once the layout has been stable for half a second (no DB spam).
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveRef = useRef(save.mutate);
  saveRef.current = save.mutate;

  const queueSave = useCallback((items: LayoutItem[]) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      saveRef.current(items.map((l) => ({ product_id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })));
    }, 500);
  }, []);

  const layoutRef = useRef(layout);
  layoutRef.current = layout;

  const onLayoutChange = useCallback(
    (next: readonly { i: string; x: number; y: number; w: number; h: number }[]) => {
      const items = next.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h }));
      if (sameLayout(items, layoutRef.current)) return;
      past.current = [...past.current.slice(-49), layoutRef.current];
      future.current = [];
      setHistoryTick((t) => t + 1);
      setLayoutOverride(items);
      setSaved(false);
      queueSave(items);
    },
    [queueSave],
  );

  const undo = useCallback(() => {
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push(layoutRef.current);
    setLayoutOverride(prev);
    setHistoryTick((t) => t + 1);
    setSaved(false);
    queueSave(prev);
  }, [queueSave]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(layoutRef.current);
    setLayoutOverride(next);
    setHistoryTick((t) => t + 1);
    setSaved(false);
    queueSave(next);
  }, [queueSave]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.key.toLowerCase() !== "z") return;
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA)$/.test(target.tagName)) return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  const addAllToShoppingList = useMutation({
    mutationFn: () => {
      const ids = (board?.items ?? []).map((i) => i.product_id);
      return patch(`/moodboards/${id}`, { shopping_list: ids });
    },
    onSuccess: () => {
      refetch();
      toast.success("All products added to your shopping list.");
    },
    onError: () => toast.error("Could not update the shopping list."),
  });

  const products = useMemo(() => board?.products ?? {}, [board]);
  const presentProducts = useMemo(
    () => layout.map((l) => products[l.i]).filter((p): p is NonNullable<typeof p> => Boolean(p)),
    [layout, products],
  );

  useCommands(
    [
      { id: "mb.present", label: "Present moodboard", group: "Actions", keywords: "fullscreen slideshow client", run: () => setPresenting(true) },
      { id: "mb.undo", label: "Undo", group: "Actions", shortcut: "⌘Z", run: undo },
      { id: "mb.redo", label: "Redo", group: "Actions", shortcut: "⇧⌘Z", run: redo },
      { id: "mb.dots", label: "Toggle dot grid", group: "Actions", run: () => setDots((d) => !d) },
      { id: "mb.zoomin", label: "Zoom in", group: "Actions", run: () => setZoom((z) => Math.min(ZOOM_STEPS.length - 1, z + 1)) },
      { id: "mb.zoomout", label: "Zoom out", group: "Actions", run: () => setZoom((z) => Math.max(0, z - 1)) },
      { id: "mb.shopping", label: "Add all to shopping list", group: "Actions", run: () => addAllToShoppingList.mutate() },
    ],
    [undo, redo, addAllToShoppingList],
  );

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-6 h-[420px] w-full rounded-2xl" />
      </div>
    );
  }
  if (isError || !board) {
    return <ErrorState message="Moodboard not found." onRetry={() => refetch()} />;
  }

  const total = board.shopping_list.reduce(
    (sum, pid) => sum + (products[pid]?.price_toman ?? 0), 0,
  );
  const canUndo = past.current.length > 0;
  const canRedo = future.current.length > 0;
  void historyTick; // re-render trigger for the ref-backed stacks

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1 text-[var(--color-ink)]">{board.title}</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Drag and resize products — changes autosave, and ⌘Z undoes anything.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${saved ? "text-[var(--color-faint)]" : "text-[var(--color-warn)]"}`} aria-live="polite">
            {save.isPending ? "Saving…" : saved ? "All changes saved" : "Unsaved changes"}
          </span>
          <Button variant="secondary" onClick={() => setPresenting(true)} disabled={presentProducts.length === 0}>
            Present
          </Button>
          <Button variant="accent" onClick={() => addAllToShoppingList.mutate()} disabled={addAllToShoppingList.isPending}>
            {addAllToShoppingList.isPending ? "Adding…" : "Add all to shopping list"}
          </Button>
        </div>
      </div>

      {/* ---------- Linear-style toolbar: dense, icon-first, 1px separators ---------- */}
      <div className="mt-6 flex flex-wrap items-center gap-1 rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] px-2 py-1.5">
        <ToolbarButton label="Undo (⌘Z)" onClick={undo} disabled={!canUndo}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M3 8h7a3 3 0 010 6H7M3 8l3-3M3 8l3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </ToolbarButton>
        <ToolbarButton label="Redo (⇧⌘Z)" onClick={redo} disabled={!canRedo}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13 8H6a3 3 0 000 6h3M13 8l-3-3M13 8l-3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </ToolbarButton>

        <span className="mx-1 h-5 w-px bg-[var(--color-line)]" aria-hidden="true" />

        <ToolbarButton label="Zoom out" onClick={() => setZoom((z) => Math.max(0, z - 1))} disabled={zoom === 0}>
          −
        </ToolbarButton>
        <span className="w-12 text-center text-xs tabular-nums text-[var(--color-muted)]">
          {Math.round(ZOOM_STEPS[zoom] * 100)}%
        </span>
        <ToolbarButton
          label="Zoom in"
          onClick={() => setZoom((z) => Math.min(ZOOM_STEPS.length - 1, z + 1))}
          disabled={zoom === ZOOM_STEPS.length - 1}
        >
          +
        </ToolbarButton>
        <ToolbarButton label="Reset zoom to 100%" onClick={() => setZoom(3)} disabled={zoom === 3}>
          Fit
        </ToolbarButton>

        <span className="mx-1 h-5 w-px bg-[var(--color-line)]" aria-hidden="true" />

        <ToolbarButton label="Toggle dot grid" onClick={() => setDots((d) => !d)} active={dots}>
          Dots
        </ToolbarButton>

        <span className="ml-auto pr-1 text-xs text-[var(--color-faint)]">
          {layout.length} item{layout.length === 1 ? "" : "s"}
        </span>
      </div>

      <Card className="mt-3 overflow-auto p-4">
        {layout.length === 0 ? (
          <EmptyState
            title="This board is empty"
            hint="Save products from your recommendations and they will appear here, ready to arrange."
          />
        ) : (
          <div
            className={dots ? "board-dots rounded-xl" : "rounded-xl"}
            style={{ width: BASE_WIDTH * ZOOM_STEPS[zoom] }}
          >
            <Suspense fallback={<Skeleton className="h-[420px] w-full rounded-xl" />}>
              <BoardGrid
                layout={layout}
                products={products}
                onLayoutChange={onLayoutChange}
                width={BASE_WIDTH * ZOOM_STEPS[zoom]}
              />
            </Suspense>
          </div>
        )}
      </Card>

      <Card className="mt-6 flex items-center justify-between p-4">
        <p className="text-sm text-[var(--color-muted)]">
          {board.shopping_list.length} item{board.shopping_list.length === 1 ? "" : "s"} in shopping list
        </p>
        <p className="font-semibold tabular-nums text-[var(--color-ink)]">{formatToman(total)}</p>
      </Card>

      {presenting && (
        <Suspense fallback={null}>
          <PresentMode
            title={board.title}
            products={presentProducts}
            onClose={() => setPresenting(false)}
          />
        </Suspense>
      )}
    </div>
  );
}
