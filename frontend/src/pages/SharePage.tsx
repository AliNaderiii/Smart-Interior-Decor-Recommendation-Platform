import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { RecommendedProduct } from "@/lib/types";
import { CATEGORY_LABELS, formatToman } from "@/lib/constants";
import { Badge, Card, Skeleton } from "@/components/ui";
import { ErrorState } from "@/components/states";
import { OptimizedImage } from "@/components/OptimizedImage";

interface ShareData {
  client_name: string;
  quiz: { styles: string[]; color_palette: string[]; room_width_cm: number; room_length_cm: number };
  categories: Record<string, RecommendedProduct[]>;
}

/** Public read-only recommendation view (no auth). */
export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["share", token],
    queryFn: () => get<ShareData>(`/share/${token}`),
    enabled: Boolean(token),
    retry: false,
  });

  if (isLoading) {
    return (
      <div>
        <Card className="p-6">
          <Skeleton className="h-3 w-28" />
          <Skeleton className="mt-3 h-8 w-72" />
          <Skeleton className="mt-4 h-5 w-56" />
        </Card>
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="overflow-hidden">
              <Skeleton className="h-40 w-full" />
              <div className="space-y-2 p-4">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-24" />
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <ErrorState message="This share link is invalid or has expired. Ask your designer to send a fresh one." />
    );
  }

  return (
    <div>
      <Card className="p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">Shared room plan</p>
        <h1 className="mt-2 h1 text-[var(--color-ink)]">
          {data.client_name ? `${data.client_name}'s living room` : "Living room plan"}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {data.quiz.styles.map((s) => <Badge key={s} tone="clay">{s}</Badge>)}
          <span className="text-sm text-[var(--color-muted)]">
            {data.quiz.room_width_cm}×{data.quiz.room_length_cm} cm
          </span>
          <span className="flex gap-1">
            {data.quiz.color_palette.map((hex) => (
              <span key={hex} className="h-5 w-5 rounded-full border border-[var(--color-line)]" style={{ backgroundColor: hex }} title={hex} />
            ))}
          </span>
        </div>
      </Card>

      {Object.entries(data.categories).map(([category, items]) => (
        <section key={category} className="mt-10">
          <h2 className="mb-4 text-lg font-semibold text-[var(--color-ink)]">{CATEGORY_LABELS[category] ?? category}</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((p, i) => (
              <Card key={p.id} className="overflow-hidden">
                <OptimizedImage src={p.image_url} alt={p.title} width={400} height={260}
                                priority={i === 0} sizes="(max-width: 768px) 100vw, 33vw"
                                wrapperClassName="h-40 w-full" />
                <div className="space-y-2 p-4">
                  <h3 className="line-clamp-2 text-sm font-semibold text-[var(--color-ink)]">{p.title}</h3>
                  <p className="font-semibold tabular-nums text-[var(--color-ink)]">{formatToman(p.price_toman)}</p>
                  <p className="text-xs leading-relaxed text-[var(--color-muted)]">{p.explanation.summary}</p>
                  {p.seller_link && (
                    <a href={p.seller_link} target="_blank" rel="noreferrer noopener"
                       className="inline-block rounded-xl border border-[var(--color-line)] px-3 py-1.5 text-xs font-semibold text-[var(--color-ink)] hover:bg-[var(--color-line)]">
                      View at seller
                    </a>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}
      <p className="mt-16 border-t border-[var(--color-line)] pt-8 text-center text-xs text-[var(--color-faint)]">
        Powered by Smart Decor — read-only shared view
      </p>
    </div>
  );
}
