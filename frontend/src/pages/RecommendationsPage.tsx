import { useCallback, useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { post } from "@/lib/api";
import type { RecommendResult, RecommendedProduct } from "@/lib/types";
import { CATEGORY_LABELS } from "@/lib/constants";
import { useMoodboardStore } from "@/stores/moodboardStore";
import { ProductCard } from "@/components/ProductCard";
import { Button, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { ProductCardSkeleton } from "@/components/ProductCardSkeleton";

function useRecommendations(quizId: string | null) {
  return useQuery({
    queryKey: ["recommend", quizId],
    queryFn: async (): Promise<RecommendResult> => {
      const url = quizId ? `/recommend?quiz_id=${quizId}` : "/recommend";
      return post<RecommendResult>(url);
    },
    staleTime: 5 * 60 * 1000,
  });
}

export default function RecommendationsPage() {
  const [params] = useSearchParams();
  const quizId = params.get("quiz");
  const { data, isLoading, isError, refetch } = useRecommendations(quizId);
  const { picked, add } = useMoodboardStore();
  const navigate = useNavigate();

  const pickedIds = useMemo(() => new Set(picked.map((p) => p.id)), [picked]);

  // Perf: ProductCard is React.memo'd, but an inline arrow recreated on every
  // render gives it a new `onAdd` identity each time and defeats the memo —
  // every card re-rendered whenever any card was added. useCallback keeps the
  // reference stable so only the changed card re-renders.
  const addToBoard = useCallback((p: RecommendedProduct) => add(p), [add]);

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-8 w-64" />
        {/* Layout-matched shimmer (Stripe/Linear pattern): the skeleton mirrors
            the real card so nothing shifts when data lands. */}
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <ProductCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }
  if (isError) return <ErrorState message="Could not load recommendations." onRetry={() => refetch()} />;
  if (!data || Object.keys(data.categories).length === 0) {
    return (
      <EmptyState
        title="No matches in this budget"
        hint="Try widening your budget range or picking different styles."
        action={<Link to="/quiz" className="rounded-xl bg-clay px-4 py-2 text-sm font-semibold text-white">Retake quiz</Link>}
      />
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-walnut">Your recommendations</h1>
          <p className="mt-1 text-sm text-stone">
            Ranked by style, color, budget and material fit — hover the badges to see why.
          </p>
        </div>
        <div className="flex gap-2">
          {!data.is_pro && (
            <Link to="/upgrade" className="rounded-xl bg-[#f7e3d9] px-4 py-2 text-sm font-semibold text-clay-dark hover:bg-[#f3d6c8]">
              Upgrade to Pro
            </Link>
          )}
          <Button onClick={() => navigate("/moodboards")} disabled={picked.length === 0}>
            Create moodboard ({picked.length})
          </Button>
        </div>
      </div>

      {Object.entries(data.categories).map(([category, items]) => (
        <section key={category} className="mt-10" aria-labelledby={`h-${category}`}>
          <h2 id={`h-${category}`} className="mb-4 text-lg font-bold text-walnut">
            {CATEGORY_LABELS[category] ?? category}
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((product, i) => (
              <ProductCard
                key={product.id}
                product={product}
                rank={i}
                onAdd={product.locked ? undefined : addToBoard}
                added={pickedIds.has(product.id)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
