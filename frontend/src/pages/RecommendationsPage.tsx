import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { post } from "@/lib/api";
import { takeEarlyRecommend } from "@/lib/earlyRecommend";
import type { RecommendResult, RecommendedProduct } from "@/lib/types";
import { CATEGORY_LABELS } from "@/lib/constants";
import { useMoodboardStore } from "@/stores/moodboardStore";
import { ProductCard } from "@/components/ProductCard";
import { ProductCardSkeleton } from "@/components/ProductCardSkeleton";
import { Button, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { useFeedbackMap, useSubmitFeedback } from "@/lib/useFeedback";
import { useToast } from "@/components/Toast";
import { useCommands } from "@/components/CommandPalette";
import { spring, staggerContainer, staggerItem } from "@/lib/motion";

import { useT } from "@/i18n";
import { ScrollStage, CardTilt3D } from "@/components/Scroll3D";

type LayoutMode = "grid" | "masonry";

function useRecommendations(quizId: string | null) {
  return useQuery({
    queryKey: ["recommend", quizId],
    queryFn: async (): Promise<RecommendResult> => {
      // T-2.1: consume the boot-time kickoff when one is in flight (started
      // in main.tsx before React mounted — see lib/earlyRecommend.ts). Any
      // early failure falls through to the normal post() path, which owns
      // refresh-on-401 and error shaping.
      const early = takeEarlyRecommend(quizId);
      if (early) {
        try {
          return await early;
        } catch {
          /* fall back to the canonical request below */
        }
      }
      if (!quizId) {
        return { categories: {}, cached: false, is_pro: false };
      }
      return post<RecommendResult>(`/recommend?quiz_id=${quizId}`);
    },
    staleTime: 5 * 60 * 1000,
  });
}

/* ------------------------------------------------------------ layout toggle */

function LayoutToggle({ mode, onChange }: { mode: LayoutMode; onChange: (m: LayoutMode) => void }) {
  return (
    <div
      className="inline-flex rounded-xl bg-[var(--color-line)] p-0.5"
      role="radiogroup"
      aria-label="Layout"
    >
      {(["grid", "masonry"] as const).map((opt) => (
        <button
          key={opt}
          type="button"
          role="radio"
          aria-checked={mode === opt}
          onClick={() => onChange(opt)}
          className={`relative rounded-[10px] px-3 py-1.5 text-xs font-semibold capitalize transition-colors ${
            mode === opt ? "text-[var(--color-ink)]" : "text-[var(--color-muted)] hover:text-[var(--color-ink)]"
          }`}
        >
          {mode === opt && (
            <motion.span
              layoutId="layout-toggle-pill"
              className="absolute inset-0 rounded-[10px] bg-[var(--color-surface)] shadow-sm"
              transition={spring}
            />
          )}
          <span className="relative">{opt}</span>
        </button>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- sticky tabs */

function CategoryTabs({
  categories,
  active,
  onSelect,
}: {
  categories: string[];
  active: string | null;
  onSelect: (c: string) => void;
}) {
  return (
    <div className="sticky top-14 z-30 -mx-4 border-b border-[var(--color-line)] bg-[var(--color-canvas)]/85 px-4 backdrop-blur">
      <div className="flex gap-1 overflow-x-auto py-2" role="tablist" aria-label="Product categories">
        {categories.map((c) => (
          <button
            key={c}
            role="tab"
            aria-selected={active === c}
            onClick={() => onSelect(c)}
            className={`relative whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              active === c
                ? "text-[var(--color-ink)]"
                : "text-[var(--color-muted)] hover:text-[var(--color-ink)]"
            }`}
          >
            {CATEGORY_LABELS[c] ?? c}
            {active === c && (
              <motion.span
                layoutId="cat-underline"
                className="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-full bg-[var(--color-accent)]"
                transition={spring}
              />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- page */

export default function RecommendationsPage() {
  const t = useT();
  const [params] = useSearchParams();
  const quizId = params.get("quiz");
  const { data, isLoading, isError, error, refetch, isFetching } = useRecommendations(quizId);
  const { picked, add } = useMoodboardStore();
  const navigate = useNavigate();
  const toast = useToast();
  const reduce = useReducedMotion();

  const [layout, setLayout] = useState<LayoutMode>("grid");
  const [activeCat, setActiveCat] = useState<string | null>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  const { data: feedbackMap } = useFeedbackMap();
  const submitFeedback = useSubmitFeedback();

  const pickedIds = useMemo(() => new Set(picked.map((p) => p.id)), [picked]);

  // Perf: ProductCard is React.memo'd, but an inline arrow recreated on every
  // render gives it a new `onAdd` identity each time and defeats the memo —
  // every card re-rendered whenever any card was added. useCallback keeps the
  // reference stable so only the changed card re-renders.
  const addToBoard = useCallback(
    (p: RecommendedProduct) => {
      add(p);
      toast.success(`${p.title} added to your moodboard.`);
    },
    [add, toast],
  );

  const handleFeedback = useCallback(
    (p: RecommendedProduct, signal: 1 | -1) => {
      submitFeedback.mutate({ productId: p.id, signal, category: p.category });
    },
    [submitFeedback],
  );

  const categories = useMemo(() => Object.keys(data?.categories ?? {}), [data]);

  // T-2.1 progressive render (Directive 4 R2.3): three CI runs measured LCP
  // 6497-6570ms with TTI pinned at ~6.7-6.8s regardless of chunk layout or
  // fetch timing — the binding constraint is the main-thread cost of the
  // INITIAL commit: 30 ProductCards (MotionCard + Radix HoverCard portal +
  // AnimatePresence each) across 6 sections, multiplied 4x by the mobile CPU
  // simulation. Only the first section can paint inside the first viewport,
  // so commit that one synchronously (the LCP card is in it) and mount the
  // rest one idle callback later. Content and order are identical; the
  // below-fold sections appear within milliseconds of the browser going
  // idle — before any human can scroll to them.
  const [deferBelowFold, setDeferBelowFold] = useState(true);
  useEffect(() => {
    if (!data || !deferBelowFold) return;
    const win = window as Window & {
      requestIdleCallback?: (cb: () => void) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    const schedule = win.requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 1));
    const cancel = win.cancelIdleCallback ?? window.clearTimeout;
    const id = schedule(() => setDeferBelowFold(false));
    return () => cancel(id);
  }, [data, deferBelowFold]);

  useEffect(() => {
    if (!activeCat && categories.length) setActiveCat(categories[0]);
  }, [categories, activeCat]);

  // Scroll-spy: keep the sticky tab in sync with what is actually on screen.
  useEffect(() => {
    if (!categories.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible?.target instanceof HTMLElement && visible.target.dataset.cat) {
          setActiveCat(visible.target.dataset.cat);
        }
      },
      { rootMargin: "-96px 0px -70% 0px", threshold: 0 },
    );
    for (const el of Object.values(sectionRefs.current)) if (el) io.observe(el);
    return () => io.disconnect();
    // deferBelowFold: re-attach once the deferred sections have mounted,
    // otherwise the observer only ever saw the first section.
  }, [categories, deferBelowFold]);

  const scrollToCat = useCallback((c: string) => {
    setActiveCat(c);
    // A tab click may target a section the idle callback has not mounted
    // yet — mount everything first, then scroll on the next frame.
    setDeferBelowFold(false);
    requestAnimationFrame(() => {
      sectionRefs.current[c]?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  useCommands(
    [
      {
        id: "recs.layout",
        label: layout === "grid" ? "Switch to masonry layout" : "Switch to grid layout",
        group: "Actions",
        keywords: "view columns pinterest",
        run: () => setLayout(layout === "grid" ? "masonry" : "grid"),
      },
      {
        id: "recs.moodboard",
        label: "Create moodboard from selection",
        group: "Create",
        keywords: "board collage",
        run: () => navigate("/moodboards"),
      },
      {
        id: "recs.retake",
        label: "Retake the style quiz",
        group: "Actions",
        run: () => navigate("/quiz"),
      },
    ],
    [layout, navigate],
  );

  if (isLoading) {
    return (
      <div>
        {/* Layout-matched shimmer (Stripe/Linear pattern): the skeleton must
            mirror the LOADED page chrome, not just the cards. T-2.1 baseline
            (run 33078900123) measured CLS 0.112 on recommendations/mobile —
            the old skeleton had no actions row, no category tab bar and no
            section heading, so the entire grid shifted down when data landed. */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <Skeleton className="h-8 w-64" />
            <Skeleton className="mt-2 h-4 w-72 max-w-full" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-28 rounded-xl" />
            <Skeleton className="h-10 w-40 rounded-xl" />
          </div>
        </div>
        <div className="mt-6 border-b border-[var(--color-line)]">
          <div className="flex gap-1 py-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-20 rounded-lg" />
            ))}
          </div>
        </div>
        <section className="mt-12">
          <div className="mb-4 flex items-baseline justify-between">
            <Skeleton className="h-7 w-40" />
            <Skeleton className="h-3 w-16" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        </section>
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        message={t.recommendations.errorTitle}
        onRetry={() => refetch()}
        errorId={(error as { status?: number })?.status ? `HTTP ${(error as { status?: number }).status}` : undefined}
      />
    );
  }

  // B-1: these were one branch, so arriving here without a quiz (e.g. clicking
  // "Recommendations" in the nav before finishing the quiz) claimed the budget
  // had failed — blaming the user's inputs for a step they never took. The
  // backend is fine: POST /quiz -> POST /recommend?quiz_id=... returns 35
  // products across 7 categories. Distinguish "no input yet" from "input
  // produced nothing".
  if (!quizId) {
    return (
      <EmptyState
        title={t.recommendations.noQuizTitle}
        hint={t.recommendations.noQuizHint}
        action={
          <Link
            to="/quiz"
            className="inline-block rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
          >
            {t.recommendations.noQuizCta}
          </Link>
        }
      />
    );
  }

  if (!data || categories.length === 0) {
    return (
      <EmptyState
        title={t.recommendations.emptyTitle}
        hint={t.recommendations.emptyHint}
        action={
          <Link
            to="/quiz"
            className="inline-block rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
          >
            {t.recommendations.emptyCta}
          </Link>
        }
      />
    );
  }

  const gridClass =
    layout === "grid"
      ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      : // Masonry via CSS columns. Reading order runs top-to-bottom per column
        // rather than left-to-right (RESEARCH_V2 §11); acceptable here because
        // each card is independent — there is no sequence to follow.
        "columns-1 gap-4 sm:columns-2 lg:columns-4 [&>*]:mb-4 [&>*]:break-inside-avoid";

  return (
    <ScrollStage>
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h1 text-[var(--color-ink)]">{t.recommendations.title}</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {t.recommendations.subtitle}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LayoutToggle mode={layout} onChange={setLayout} />
          {!data.is_pro && (
            <Link
              to="/upgrade"
              className="rounded-xl border border-[var(--color-line)] px-4 py-2 text-sm font-semibold text-[var(--color-ink)] hover:bg-[var(--color-line)]"
            >
              Upgrade to Pro
            </Link>
          )}
          <Button variant="accent" onClick={() => navigate("/moodboards")} disabled={picked.length === 0}>
            Create moodboard ({picked.length})
          </Button>
        </div>
      </div>

      <div className="mt-6">
        <CategoryTabs categories={categories} active={activeCat} onSelect={scrollToCat} />
      </div>

      {/* Refetch after feedback: subtle, non-blocking (Linear — optimistic, no
          spinner takeover). */}
      {isFetching && (
        <div className="mt-3 text-xs text-[var(--color-muted)]" role="status">
          Re-ranking…
        </div>
      )}

      {Object.entries(data.categories)
        .slice(0, deferBelowFold ? 1 : undefined)
        .map(([category, items]) => (
        <section
          key={category}
          data-cat={category}
          ref={(el) => {
            sectionRefs.current[category] = el;
          }}
          className="mt-12 scroll-mt-32"
          aria-labelledby={`h-${category}`}
        >
          <div className="mb-4 flex items-baseline justify-between">
            <h2 id={`h-${category}`} className="h2 text-[var(--color-ink)]">
              {CATEGORY_LABELS[category] ?? category}
            </h2>
            <span className="text-xs tabular-nums text-[var(--color-faint)]">{items.length} options</span>
          </div>
          <motion.div
            className={gridClass}
            variants={reduce ? undefined : staggerContainer()}
            initial="initial"
            animate="animate"
          >
            {items.map((product, i) => (
              <motion.div key={product.id} variants={reduce ? undefined : staggerItem}>
                <CardTilt3D>
                <ProductCard
                  product={product}
                  rank={i}
                  onAdd={product.locked ? undefined : addToBoard}
                  added={pickedIds.has(product.id)}
                  feedback={feedbackMap?.[product.id]}
                  onFeedback={product.locked ? undefined : handleFeedback}
                />
                </CardTilt3D>
              </motion.div>
            ))}
          </motion.div>
        </section>
      ))}
    </div>
    </ScrollStage>
  );
}
