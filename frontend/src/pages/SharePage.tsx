import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { RecommendedProduct } from "@/lib/types";
import { CATEGORY_LABELS, formatToman } from "@/lib/constants";
import { Badge, Card, ErrorState, Spinner } from "@/components/ui";
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

  if (isLoading) return <Spinner />;
  if (isError || !data) return <ErrorState message="This share link is invalid or has expired." />;

  return (
    <div>
      <Card className="p-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-clay-dark">Shared room plan</p>
        <h1 className="mt-1 text-2xl font-bold text-walnut">
          {data.client_name ? `${data.client_name}'s living room` : "Living room plan"}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {data.quiz.styles.map((s) => <Badge key={s} tone="clay">{s}</Badge>)}
          <span className="text-sm text-stone">
            {data.quiz.room_width_cm}×{data.quiz.room_length_cm} cm
          </span>
          <span className="flex gap-1">
            {data.quiz.color_palette.map((hex) => (
              <span key={hex} className="h-5 w-5 rounded-full border border-[#e5ded3]" style={{ backgroundColor: hex }} title={hex} />
            ))}
          </span>
        </div>
      </Card>

      {Object.entries(data.categories).map(([category, items]) => (
        <section key={category} className="mt-10">
          <h2 className="mb-4 text-lg font-bold text-walnut">{CATEGORY_LABELS[category] ?? category}</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((p, i) => (
              <Card key={p.id} className="overflow-hidden">
                <OptimizedImage src={p.image_url} alt={p.title} width={400} height={260}
                                priority={i === 0} sizes="(max-width: 768px) 100vw, 33vw"
                                wrapperClassName="h-40 w-full" />
                <div className="space-y-2 p-4">
                  <h3 className="line-clamp-2 text-sm font-semibold">{p.title}</h3>
                  <p className="font-bold text-clay-dark">{formatToman(p.price_toman)}</p>
                  <p className="text-xs text-stone">{p.explanation.summary}</p>
                  {p.seller_link && (
                    <a href={p.seller_link} target="_blank" rel="noreferrer noopener"
                       className="inline-block rounded-xl bg-sand px-3 py-1.5 text-xs font-semibold text-walnut hover:bg-[#e8e0d4]">
                      View at seller
                    </a>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}
      <p className="mt-12 text-center text-xs text-stone">Powered by Smart Decor — read-only shared view</p>
    </div>
  );
}
