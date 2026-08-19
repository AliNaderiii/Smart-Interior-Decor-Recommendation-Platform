import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import type { Moodboard, MoodboardItem } from "@/lib/types";
import { formatToman } from "@/lib/constants";
import { Button, Card, ErrorState, Spinner } from "@/components/ui";

// react-grid-layout is heavy — lazy-load it off the critical path (LCP budget)
const BoardGrid = lazy(() => import("@/components/BoardGrid"));

interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export default function MoodboardEditorPage() {
  const { id } = useParams<{ id: string }>();
  const [saved, setSaved] = useState(true);

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

  const save = useMutation({
    mutationFn: (items: MoodboardItem[]) => patch(`/moodboards/${id}`, { items }),
    onSuccess: () => setSaved(true),
  });

  const onLayoutChange = useCallback(
    (next: readonly { i: string; x: number; y: number; w: number; h: number }[]) => {
      setLayoutOverride(next.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h })));
      setSaved(false);
    },
    [],
  );

  const addAllToShoppingList = useMutation({
    mutationFn: () => {
      const ids = (board?.items ?? []).map((i) => i.product_id);
      return patch(`/moodboards/${id}`, { shopping_list: ids });
    },
    onSuccess: () => refetch(),
  });

  if (isLoading) return <Spinner />;
  if (isError || !board) return <ErrorState message="Moodboard not found." onRetry={() => refetch()} />;

  const products = board.products ?? {};
  const total = board.shopping_list.reduce(
    (sum, pid) => sum + (products[pid]?.price_toman ?? 0), 0,
  );

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-walnut">{board.title}</h1>
          <p className="mt-1 text-sm text-stone">Drag & resize products. Layout saves to your account.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-stone">{saved ? "All changes saved" : "Unsaved changes"}</span>
          <Button
            variant="secondary"
            onClick={() =>
              save.mutate(layout.map((l) => ({ product_id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })))
            }
            disabled={saved || save.isPending}
          >
            {save.isPending ? "Saving…" : "Save layout"}
          </Button>
          <Button onClick={() => addAllToShoppingList.mutate()}>Add all to shopping list</Button>
        </div>
      </div>

      <Card className="mt-6 overflow-hidden p-4">
        <Suspense fallback={<Spinner />}>
          <BoardGrid layout={layout} products={products} onLayoutChange={onLayoutChange} />
        </Suspense>
      </Card>

      <Card className="mt-6 flex items-center justify-between p-4">
        <p className="text-sm text-stone">
          {board.shopping_list.length} items in shopping list
        </p>
        <p className="font-bold text-clay-dark">{formatToman(total)}</p>
      </Card>
    </div>
  );
}
