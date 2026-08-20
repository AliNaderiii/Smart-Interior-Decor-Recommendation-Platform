import { Card, Skeleton } from "@/components/ui";

/**
 * Loading placeholder shaped like a real ProductCard.
 *
 * V2 Phase 2/5: Phase 0B found 8 pages using a generic centred `<Spinner/>`,
 * which guarantees a layout jump when data arrives (CLS). Stripe and Linear
 * both use content-shaped shimmer instead — the skeleton occupies exactly the
 * space the card will, so the page never moves.
 */
export function ProductCardSkeleton() {
  return (
    <Card className="flex flex-col overflow-hidden" aria-hidden="true">
      <Skeleton className="h-40 w-full rounded-none" />
      <div className="flex flex-1 flex-col gap-2 p-4">
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-5 w-24" />
        <div className="flex gap-1.5">
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-14 rounded-full" />
        </div>
        <div className="mt-auto flex gap-2 pt-2">
          <Skeleton className="h-9 flex-1" />
          <Skeleton className="h-9 w-14" />
        </div>
      </div>
    </Card>
  );
}

export default ProductCardSkeleton;
