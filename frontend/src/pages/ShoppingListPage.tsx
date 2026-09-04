import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { Moodboard } from "@/lib/types";
import { CATEGORY_LABELS, formatToman } from "@/lib/constants";
import { safeUrl } from "@/lib/safeUrl";
import { Card, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { OptimizedImage } from "@/components/OptimizedImage";
import { useToast } from "@/components/Toast";
import { useCommands } from "@/components/CommandPalette";

/** Persisted so quantities survive a reload — a stepper that forgets is worse
 *  than no stepper. Keyed per board. */
const QTY_KEY = "sd_shopping_qty";

function loadQty(boardId: string): Record<string, number> {
  try {
    const all = JSON.parse(localStorage.getItem(QTY_KEY) ?? "{}");
    return all[boardId] ?? {};
  } catch {
    return {};
  }
}

function saveQty(boardId: string, qty: Record<string, number>) {
  try {
    const all = JSON.parse(localStorage.getItem(QTY_KEY) ?? "{}");
    all[boardId] = qty;
    localStorage.setItem(QTY_KEY, JSON.stringify(all));
  } catch {
    /* quota or private mode — quantities simply do not persist */
  }
}

/* ------------------------------------------------------------------ stepper */

function QuantityStepper({
  value,
  onChange,
  label,
}: {
  value: number;
  onChange: (v: number) => void;
  label: string;
}) {
  const btn =
    "grid h-8 w-8 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:bg-[var(--color-line)] hover:text-[var(--color-ink)] disabled:opacity-40 disabled:hover:bg-transparent";
  return (
    <div className="inline-flex items-center rounded-xl border border-[var(--color-line)]">
      <button
        type="button"
        className={btn}
        onClick={() => onChange(Math.max(1, value - 1))}
        disabled={value <= 1}
        aria-label={`Decrease quantity of ${label}`}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M2 6h8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>
      <span className="w-8 text-center text-sm font-semibold tabular-nums text-[var(--color-ink)]" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        className={btn}
        onClick={() => onChange(Math.min(99, value + 1))}
        disabled={value >= 99}
        aria-label={`Increase quantity of ${label}`}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M6 2v8M2 6h8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );
}

/* --------------------------------------------------------------------- page */

export default function ShoppingListPage() {
  const toast = useToast();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [qty, setQty] = useState<Record<string, number>>({});

  const {
    data: boards,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["moodboards"],
    queryFn: () => get<Moodboard[]>("/moodboards"),
  });

  // Phase 0B flagged `boards[0]` as a UX dead-end: a user with several boards
  // could only ever see the first one, with no way to reach the others. The
  // first board is now just the DEFAULT, and a selector exposes the rest.
  const boardId = selectedId ?? boards?.[0]?.id;

  const { data: board, isLoading: boardLoading } = useQuery({
    queryKey: ["moodboard", boardId],
    queryFn: () => get<Moodboard>(`/moodboards/${boardId}`),
    enabled: Boolean(boardId),
  });

  useEffect(() => {
    if (boardId) setQty(loadQty(boardId));
  }, [boardId]);

  const products = useMemo(() => board?.products ?? {}, [board]);
  const rows = useMemo(
    () =>
      (board?.shopping_list ?? [])
        .map((pid) => products[pid])
        .filter((p): p is NonNullable<typeof p> => Boolean(p)),
    [board, products],
  );

  // useMemo so the total does not recompute on unrelated renders, and so it is
  // provably derived from (rows, qty) rather than drifting in local state.
  const { total, itemCount } = useMemo(() => {
    let total = 0;
    let itemCount = 0;
    for (const p of rows) {
      const n = qty[p.id] ?? 1;
      total += p.price_toman * n;
      itemCount += n;
    }
    return { total, itemCount };
  }, [rows, qty]);

  function setQuantity(pid: string, n: number) {
    setQty((prev) => {
      const next = { ...prev, [pid]: n };
      if (boardId) saveQty(boardId, next);
      return next;
    });
  }

  async function copyAll() {
    const text = rows
      .map((p) => `${qty[p.id] ?? 1}x ${p.title} — ${formatToman(p.price_toman)} — ${p.seller_link}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(`${text}\n\nTotal: ${formatToman(total)}`);
      toast.success("Shopping list copied to clipboard.");
    } catch {
      toast.error("Clipboard blocked by your browser.");
    }
  }

  useCommands(
    [
      { id: "shop.copy", label: "Copy shopping list", group: "Actions", keywords: "clipboard export", run: copyAll },
    ],
    [rows, qty, total],
  );

  if (isLoading || boardLoading) {
    return (
      <div>
        <Skeleton className="h-8 w-52" />
        <div className="mt-8 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="flex items-center gap-4 p-4">
              <Skeleton className="h-20 w-20 shrink-0 rounded-xl" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-24" />
              </div>
              <Skeleton className="h-8 w-24" />
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Could not load your shopping list." onRetry={() => refetch()} />;
  }

  if (rows.length === 0) {
    return (
      <div>
        <h1 className="h1 text-[var(--color-ink)]">Shopping list</h1>
        <div className="mt-8">
          <EmptyState
            title={boards?.length ? "Nothing added yet" : "Create a moodboard first"}
            hint={
              boards?.length
                ? "Open a moodboard and choose “Add all to shopping list” to collect everything you want to buy."
                : "Your shopping list is built from a moodboard. Pick products you like and save them to a board."
            }
            action={
              <Link
                to={boards?.length ? "/moodboards" : "/recommendations"}
                className="inline-block rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
              >
                {boards?.length ? "Go to moodboards" : "Browse recommendations"}
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div className="pb-28">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h1 text-[var(--color-ink)]">Shopping list</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {itemCount} item{itemCount === 1 ? "" : "s"} from “{board?.title}”
          </p>
        </div>
        <div className="flex items-center gap-2">
          {boards && boards.length > 1 && (
            <>
              <label htmlFor="board-select" className="sr-only">
                Choose moodboard
              </label>
              <select
                id="board-select"
                value={boardId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)]"
              >
                {boards.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.title}
                  </option>
                ))}
              </select>
            </>
          )}
          <button
            type="button"
            onClick={copyAll}
            className="rounded-xl border border-[var(--color-line)] px-4 py-2 text-sm font-semibold text-[var(--color-ink)] hover:bg-[var(--color-line)]"
          >
            Copy list
          </button>
        </div>
      </div>

      {/* Apple-cart line items: generous row height, image left, one action
          cluster right. No table chrome — the data is not tabular, it is a
          list of things you are buying. */}
      <ul className="mt-8 space-y-3">
        {rows.map((p) => {
          const n = qty[p.id] ?? 1;
          return (
            <li key={p.id}>
              <Card className="flex flex-wrap items-center gap-4 p-4">
                <OptimizedImage
                  src={p.image_url}
                  alt=""
                  width={80}
                  height={80}
                  sizes="80px"
                  widths={[80, 160, 240]}
                  wrapperClassName="h-20 w-20 shrink-0 rounded-xl"
                />
                <div className="min-w-[12rem] flex-1">
                  <p className="font-medium text-[var(--color-ink)]">{p.title}</p>
                  <p className="mt-0.5 text-xs text-[var(--color-muted)]">
                    {CATEGORY_LABELS[p.category] ?? p.category}
                  </p>
                  <div className="mt-1.5 flex items-center gap-2">
                    {/* Retailer trust badge — colour is paired with text so the
                        signal survives greyscale and colour-blindness. */}
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        p.seller_link_ok
                          ? "bg-[var(--color-ok)]/10 text-[var(--color-ok)]"
                          : p.seller_link_ok === false
                            ? "bg-[var(--color-danger)]/10 text-[var(--color-danger)]"
                            : "bg-[var(--color-line)] text-[var(--color-muted)]"
                      }`}
                    >
                      {p.seller_link_ok ? "Link verified" : p.seller_link_ok === false ? "Link broken" : "Not checked"}
                    </span>
                    {/* X-01: stored seller links are sanitised at render, and
                        a rejected link renders as nothing rather than as a
                        dead `href=""` that reloads the page. */}
                    {safeUrl(p.seller_link) && (
                      <a
                        href={safeUrl(p.seller_link)}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-xs font-medium text-[var(--color-muted)] underline-offset-2 hover:text-[var(--color-ink)] hover:underline"
                      >
                        Open store ↗
                      </a>
                    )}
                  </div>
                </div>
                <QuantityStepper value={n} onChange={(v) => setQuantity(p.id, v)} label={p.title} />
                <div className="w-32 text-end">
                  <p className="font-semibold tabular-nums text-[var(--color-ink)]">
                    {formatToman(p.price_toman * n)}
                  </p>
                  {n > 1 && (
                    <p className="text-[11px] tabular-nums text-[var(--color-faint)]">
                      {formatToman(p.price_toman)} each
                    </p>
                  )}
                </div>
              </Card>
            </li>
          );
        })}
      </ul>

      {/* Sticky total: the number you care about must never scroll away. */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-[var(--color-line)] bg-[var(--color-canvas)]/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-[var(--color-faint)]">Total</p>
            <p className="text-xl font-semibold tabular-nums text-[var(--color-ink)]">{formatToman(total)}</p>
          </div>
          <p className="text-xs text-[var(--color-muted)]">
            {itemCount} item{itemCount === 1 ? "" : "s"} · prices from retailer pages
          </p>
        </div>
      </div>
    </div>
  );
}
