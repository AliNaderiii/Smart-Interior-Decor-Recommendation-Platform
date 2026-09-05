import { useParams } from "react-router-dom";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { get, post } from "@/lib/api";
import type { RecommendedProduct } from "@/lib/types";
import { CATEGORY_LABELS, formatToman } from "@/lib/constants";
import { safeUrl } from "@/lib/safeUrl";
import { Badge, Card, Skeleton } from "@/components/ui";
import { ErrorState } from "@/components/states";
import { OptimizedImage } from "@/components/OptimizedImage";
import { useT } from "@/i18n";

interface ShareData {
  client_name: string;
  quiz: { styles: string[]; color_palette: string[]; room_width_cm: number; room_length_cm: number };
  categories: Record<string, RecommendedProduct[]>;
}

type Verdict = "approved" | "rejected";

/** Per-product approve / reject control for the client.
 *
 *  This is what turns the share link from a brochure into a workflow. The
 *  client has no account — the token in the URL is the credential — so the
 *  control posts straight to the public endpoint and reflects the result
 *  locally without any auth round-trip.
 */
function ApproveControls({
  token,
  productId,
  current,
  onDone,
}: {
  token: string;
  productId: string;
  current?: { verdict: Verdict; comment: string };
  onDone: (v: Verdict, comment: string) => void;
}) {
  const t = useT();
  const [comment, setComment] = useState(current?.comment ?? "");
  const [showNote, setShowNote] = useState(false);

  const vote = useMutation({
    mutationFn: (verdict: Verdict) =>
      post(`/share/${token}/approve`, { product_id: productId, verdict, comment }),
    onSuccess: (_d, verdict) => onDone(verdict, comment),
  });

  return (
    <div className="space-y-2 border-t border-[var(--color-line)] pt-3">
      <div className="flex gap-2">
        {(["approved", "rejected"] as const).map((v) => {
          const active = current?.verdict === v;
          return (
            <button
              key={v}
              type="button"
              onClick={() => vote.mutate(v)}
              disabled={vote.isPending}
              aria-pressed={active}
              className={
                "flex-1 rounded-xl px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] " +
                (active
                  ? v === "approved"
                    ? "bg-[var(--color-ok)] text-white"
                    : "bg-[var(--color-warn)] text-white"
                  : "border border-[var(--color-line)] text-[var(--color-ink)] hover:bg-[var(--color-line)]")
              }
            >
              {v === "approved" ? t.share.approve : t.share.reject}
            </button>
          );
        })}
      </div>

      {showNote ? (
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          onBlur={() => current && vote.mutate(current.verdict)}
          rows={2}
          maxLength={1000}
          placeholder={t.share.notePlaceholder}
          className="w-full rounded-xl border border-[var(--color-line)] bg-transparent p-2 text-xs text-[var(--color-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        />
      ) : (
        <button
          type="button"
          onClick={() => setShowNote(true)}
          className="text-xs text-[var(--color-muted)] underline decoration-dotted underline-offset-2 hover:text-[var(--color-ink)]"
        >
          {comment ? `“${comment.slice(0, 40)}”` : t.share.addNote}
        </button>
      )}
    </div>
  );
}

/** Public recommendation view (no auth). Read-only apart from the client's
 *  own approve/reject verdicts, which the designer sees on their dashboard. */
export default function SharePage() {
  const t = useT();
  const { token } = useParams<{ token: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["share", token],
    queryFn: () => get<ShareData>(`/share/${token}`),
    enabled: Boolean(token),
    retry: false,
  });

  // Verdicts already recorded on this link, so returning to the page does not
  // present a blank slate and invite the client to decide twice.
  const { data: saved } = useQuery({
    queryKey: ["share-approvals", token],
    queryFn: () =>
      get<{ product_id: string; verdict: Verdict; comment: string }[]>(
        `/share/${token}/approvals`,
      ),
    enabled: Boolean(token),
    retry: false,
  });

  const [verdicts, setVerdicts] = useState<Record<string, { verdict: Verdict; comment: string }>>({});
  const merged = {
    ...Object.fromEntries((saved ?? []).map((a) => [a.product_id, { verdict: a.verdict, comment: a.comment }])),
    ...verdicts,
  };

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
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{t.shoppingList.sharedPlan}</p>
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
                  {/* X-01: this page is unauthenticated and reachable by
                      anyone holding a share token, which makes it the highest
                      value stored-XSS target in the SPA. */}
                  {safeUrl(p.seller_link) && (
                    <a href={safeUrl(p.seller_link)} target="_blank" rel="noreferrer noopener"
                       className="inline-block rounded-xl border border-[var(--color-line)] px-3 py-1.5 text-xs font-semibold text-[var(--color-ink)] hover:bg-[var(--color-line)]">
                      View at seller
                    </a>
                  )}
                  {token && (
                    <ApproveControls
                      token={token}
                      productId={p.id}
                      current={merged[p.id]}
                      onDone={(verdict, comment) =>
                        setVerdicts((prev) => ({ ...prev, [p.id]: { verdict, comment } }))
                      }
                    />
                  )}
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}
      <p className="mt-16 border-t border-[var(--color-line)] pt-8 text-center text-xs text-[var(--color-faint)]">
        {t.share.footer}
      </p>
    </div>
  );
}
