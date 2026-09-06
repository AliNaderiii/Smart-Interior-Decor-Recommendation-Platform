/**
 * Admin engagement funnel (ADR-014) — reads `GET /admin/events/summary`.
 *
 * A report, not a model: impressions → clicks → likes/saves per category,
 * with rates shown only where the denominator exists, and the spec's honest
 * "learning-ready" threshold stated in the header so nobody reads a funnel
 * table as evidence of a trained recommender.
 */
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/constants";
import { useLocale } from "@/i18n";
import { Badge, Card, Skeleton } from "@/components/ui";

interface FunnelRow {
  category: string;
  impression: number;
  click: number;
  like: number;
  dislike: number;
  save: number;
  purchase_click: number;
  ctr: number | null;
  like_rate: number | null;
  save_rate: number | null;
}

export interface EventsSummary {
  window_days: number;
  sessions: number;
  total_events: number;
  totals: Omit<FunnelRow, "category">;
  categories: FunnelRow[];
  learning_ready: boolean;
  learning_threshold_events: number;
}

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);
const LABELS_EN: Record<string, string> = {
  sofa: "Sofa", coffee_table: "Coffee table", rug: "Rug", lighting: "Lighting",
  chair: "Chair", storage: "Storage", decor: "Decor",
};

export function EngagementFunnel({ days = 30 }: { days?: number }) {
  const { locale } = useLocale();
  const label = (id: string) => (locale === "fa" ? CATEGORY_LABELS[id] : LABELS_EN[id]) ?? id;
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-events-summary", days],
    queryFn: () => get<EventsSummary>(`/admin/events/summary?days=${days}`),
    staleTime: 60_000,
  });

  if (isLoading) return <Skeleton className="mt-6 h-40 w-full" />;
  if (isError || !data) return null; // analytics must never break an admin page

  return (
    <Card className="mt-6 overflow-x-auto" data-testid="engagement-funnel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-line)] px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">Engagement funnel — last {data.window_days} days</h2>
          <p className="text-xs text-[var(--color-muted)]">
            {data.sessions} sessions · {data.total_events} events · rates are per impression
          </p>
        </div>
        <Badge tone={data.learning_ready ? "success" : "neutral"}>
          {data.learning_ready
            ? "enough data to evaluate learned weights"
            : `heuristic re-rank only — ${data.total_events}/${data.learning_threshold_events} events`}
        </Badge>
      </div>
      {data.categories.length === 0 ? (
        <p className="px-4 py-6 text-sm text-[var(--color-muted)]">No behavioural events recorded yet.</p>
      ) : (
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="text-start text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2 text-end">Impr.</th>
              <th className="px-4 py-2 text-end">Clicks</th>
              <th className="px-4 py-2 text-end">CTR</th>
              <th className="px-4 py-2 text-end">👍</th>
              <th className="px-4 py-2 text-end">👎</th>
              <th className="px-4 py-2 text-end">Saves</th>
              <th className="px-4 py-2 text-end">Save rate</th>
              <th className="px-4 py-2 text-end">Seller clicks</th>
            </tr>
          </thead>
          <tbody>
            {data.categories.map((r) => (
              <tr key={r.category} className="border-t border-[var(--color-line)] tabular-nums">
                <td className="px-4 py-2 font-medium text-[var(--color-ink)]">{label(r.category)}</td>
                <td className="px-4 py-2 text-end">{r.impression}</td>
                <td className="px-4 py-2 text-end">{r.click}</td>
                <td className="px-4 py-2 text-end">{pct(r.ctr)}</td>
                <td className="px-4 py-2 text-end">{r.like}</td>
                <td className="px-4 py-2 text-end">{r.dislike}</td>
                <td className="px-4 py-2 text-end">{r.save}</td>
                <td className="px-4 py-2 text-end">{pct(r.save_rate)}</td>
                <td className="px-4 py-2 text-end">{r.purchase_click}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-[var(--color-line)] font-semibold tabular-nums">
              <td className="px-4 py-2">All</td>
              <td className="px-4 py-2 text-end">{data.totals.impression}</td>
              <td className="px-4 py-2 text-end">{data.totals.click}</td>
              <td className="px-4 py-2 text-end">{pct(data.totals.ctr)}</td>
              <td className="px-4 py-2 text-end">{data.totals.like}</td>
              <td className="px-4 py-2 text-end">{data.totals.dislike}</td>
              <td className="px-4 py-2 text-end">{data.totals.save}</td>
              <td className="px-4 py-2 text-end">{pct(data.totals.save_rate)}</td>
              <td className="px-4 py-2 text-end">{data.totals.purchase_click}</td>
            </tr>
          </tbody>
        </table>
      )}
    </Card>
  );
}
