/**
 * Visual search (ADR-013) — "find furniture that looks like this photo".
 *
 * One screen, three regions: the drop zone (with a local preview drawn from
 * an object URL — the file never leaves the browser until the user clicks
 * search), the extracted palette (tap-through to the quiz, which is the
 * bridge back into the recommender), and the ranked results. The backend
 * reports HOW it searched (`meta.mode`) and the page says so out loud: a
 * colour-only search must never pretend to be a vision model.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, post } from "@/lib/api";
import type { RecommendedProduct, VisualSearchItem, VisualSearchResult } from "@/lib/types";
import { CATEGORY_LABELS } from "@/lib/constants";
import { useLocale } from "@/i18n";
import { useMoodboardStore } from "@/stores/moodboardStore";
import { useQuizStore } from "@/stores/quizStore";
import { Button, Card } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { OptimizedImage } from "@/components/OptimizedImage";
import { useToast } from "@/components/Toast";
import { track, trackImpressions } from "@/lib/events";

const MAX_BYTES = 8 * 1024 * 1024;
const CATEGORY_IDS = Object.keys(CATEGORY_LABELS);
const CATEGORY_LABELS_EN: Record<string, string> = {
  sofa: "Sofa",
  coffee_table: "Coffee table",
  rug: "Rug",
  lighting: "Lighting",
  chair: "Chair",
  storage: "Storage",
  decor: "Decor",
};

function isFullItem(item: VisualSearchItem): item is VisualSearchItem & RecommendedProduct {
  return !item.locked && typeof item.price_toman === "number";
}

export default function VisualSearchPage() {
  const { t, locale, money, num } = useLocale();
  const navigate = useNavigate();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const { picked, add } = useMoodboardStore();
  const pickedIds = useMemo(() => new Set(picked.map((p) => p.id)), [picked]);
  const toggleColor = useQuizStore((s) => s.toggleColor);
  const currentPalette = useQuizStore((s) => s.color_palette);

  // Object URL for the preview; revoked when the file changes/unmounts so a
  // session of many photos does not leak blobs.
  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const search = useMutation({
    mutationFn: async (payload: { file: File; category: string }) => {
      const form = new FormData();
      form.append("file", payload.file);
      const qs = new URLSearchParams({ limit: "12" });
      if (payload.category) qs.set("category", payload.category);
      return post<VisualSearchResult>(`/search/visual?${qs.toString()}`, form);
    },
    // ADR-014: a visual-search result list is an impression set too.
    onSuccess: (res) => trackImpressions(res.items, { page_context: "visual_search" }),
  });

  const accept = useCallback(
    (next: File | null) => {
      setLocalError(null);
      search.reset();
      if (!next) return;
      if (!next.type.startsWith("image/")) {
        setLocalError(t.visualSearch.notImage);
        return;
      }
      if (next.size > MAX_BYTES) {
        setLocalError(t.visualSearch.tooLarge);
        return;
      }
      setFile(next);
    },
    [search, t.visualSearch.notImage, t.visualSearch.tooLarge],
  );

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    accept(e.dataTransfer.files?.[0] ?? null);
  };

  const runSearch = () => {
    if (!file) return;
    search.mutate({ file, category });
  };

  const applyPalette = (palette: string[]) => {
    for (const hex of palette) {
      if (!currentPalette.includes(hex)) toggleColor(hex);
    }
    toast.success(t.visualSearch.paletteApplied);
    navigate("/quiz");
  };

  const errorMessage = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.status === 429) return t.visualSearch.rateLimited;
      if (err.status === 413) return t.visualSearch.tooLarge;
      if (err.status === 415) return t.visualSearch.notImage;
    }
    return t.visualSearch.errorTitle;
  };

  const catLabel = (id: string) => (locale === "fa" ? CATEGORY_LABELS[id] : CATEGORY_LABELS_EN[id]) ?? id;
  const result = search.data;

  return (
    <div data-testid="visual-search-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h1 text-[var(--color-ink)]">{t.visualSearch.title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--color-muted)]">{t.visualSearch.subtitle}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
        {/* ------------------------------------------------ drop zone */}
        <Card className="p-4">
          <div
            role="button"
            tabIndex={0}
            aria-label={t.visualSearch.dropTitle}
            data-testid="visual-dropzone"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`relative flex min-h-56 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed p-4 text-center transition-colors ${
              dragging
                ? "border-[var(--color-accent)] bg-[var(--color-accent)]/5"
                : "border-[var(--color-line)] hover:border-[var(--color-muted)]"
            }`}
          >
            {previewUrl ? (
              <img
                src={previewUrl}
                alt={t.visualSearch.previewAlt}
                data-testid="visual-preview"
                className="max-h-72 w-full rounded-xl object-contain"
              />
            ) : (
              <>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="text-[var(--color-muted)]">
                  <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
                  <circle cx="9" cy="10" r="1.6" fill="currentColor" />
                  <path d="M4 17l5-5 4 4 3-3 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                </svg>
                <p className="mt-3 text-sm font-semibold text-[var(--color-ink)]">{t.visualSearch.dropTitle}</p>
                <p className="mt-1 text-xs text-[var(--color-muted)]">{t.visualSearch.dropHint}</p>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              data-testid="visual-file-input"
              aria-label={t.visualSearch.chooseFile}
              onChange={(e) => accept(e.target.files?.[0] ?? null)}
            />
          </div>

          {localError && (
            <p role="alert" className="mt-3 text-sm text-[var(--color-danger)]">
              {localError}
            </p>
          )}

          <label className="mt-4 block text-xs font-semibold text-[var(--color-muted)]" htmlFor="visual-category">
            {t.visualSearch.categoryLabel}
          </label>
          <select
            id="visual-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="mt-1 w-full rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)]"
          >
            <option value="">{t.visualSearch.categoryAll}</option>
            {CATEGORY_IDS.map((id) => (
              <option key={id} value={id}>
                {catLabel(id)}
              </option>
            ))}
          </select>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="accent"
              onClick={runSearch}
              disabled={!file || search.isPending}
              data-testid="visual-search-submit"
            >
              {search.isPending ? t.visualSearch.searching : t.visualSearch.searchCta}
            </Button>
            {file && (
              <Button variant="ghost" onClick={() => inputRef.current?.click()}>
                {t.visualSearch.changePhoto}
              </Button>
            )}
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-[var(--color-muted)]">{t.visualSearch.privacy}</p>
        </Card>

        {/* ------------------------------------------------ results */}
        <div className="min-w-0">
          {search.isError && (
            <ErrorState message={errorMessage(search.error)} onRetry={file ? runSearch : undefined} />
          )}

          {result && (
            <>
              {/* palette + mode */}
              <Card className="p-4" data-testid="visual-palette">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold text-[var(--color-muted)]">{t.visualSearch.paletteTitle}</p>
                    <div className="mt-2 flex gap-2">
                      {result.meta.palette.map((hex) => (
                        <span
                          key={hex}
                          title={hex}
                          className="h-8 w-8 rounded-full border border-[var(--color-line)] shadow-sm"
                          style={{ backgroundColor: hex }}
                        />
                      ))}
                    </div>
                  </div>
                  {result.meta.palette.length > 0 && (
                    <Button variant="secondary" onClick={() => applyPalette(result.meta.palette)}>
                      {t.visualSearch.usePalette}
                    </Button>
                  )}
                </div>
                <p className="mt-3 text-xs leading-relaxed text-[var(--color-muted)]" data-testid="visual-mode" data-mode={result.meta.mode}>
                  {result.meta.mode === "clip" ? t.visualSearch.modeClip : t.visualSearch.modePalette}
                </p>
              </Card>

              <div className="mt-6 flex items-center justify-between">
                <h2 className="h3 text-[var(--color-ink)]">{t.visualSearch.resultsTitle(result.items.length)}</h2>
                {!result.is_pro && result.items.some((i) => i.locked) && (
                  <Link to="/upgrade" className="text-sm font-semibold text-[var(--color-accent)] underline-offset-4 hover:underline">
                    {t.visualSearch.lockedHint}
                  </Link>
                )}
              </div>

              {result.items.length === 0 ? (
                <div className="mt-4">
                  <EmptyState title={t.visualSearch.emptyTitle} hint={t.visualSearch.emptyHint} />
                </div>
              ) : (
                <ul className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="visual-results">
                  {result.items.map((item) => {
                    const title = (locale === "fa" && item.title_fa) || item.title;
                    const pct = num(Math.round(item.similarity * 100));
                    return (
                      <li key={item.id}>
                        <Card className="flex h-full flex-col overflow-hidden" data-testid="visual-result" data-locked={item.locked ? "true" : "false"}>
                          <div className="relative">
                            <OptimizedImage
                              src={item.image_url}
                              alt={item.locked ? "" : title}
                              width={400}
                              height={260}
                              sizes="(max-width: 768px) 100vw, 33vw"
                              wrapperClassName="h-40 w-full"
                              placeholderColor={item.colors?.[0]}
                              className={item.locked ? "blur-lg saturate-50" : undefined}
                            />
                            <span className="absolute left-2 top-2 rounded-full bg-[var(--color-surface)]/90 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-ink)] backdrop-blur">
                              {t.visualSearch.similarity(pct)}
                            </span>
                            <span className="absolute right-2 bottom-2 rounded-full bg-[var(--color-surface)]/90 px-2 py-0.5 text-[10px] font-medium text-[var(--color-muted)] backdrop-blur">
                              {catLabel(item.category)}
                            </span>
                          </div>
                          <div className="flex flex-1 flex-col gap-2 p-3">
                            {isFullItem(item) ? (
                              <>
                                <p className="line-clamp-2 text-sm font-semibold text-[var(--color-ink)]">{title}</p>
                                <p className="text-sm font-semibold tabular-nums text-[var(--color-ink)]">{money(item.price_toman)}</p>
                                <div className="mt-auto flex items-center gap-1.5">
                                  {(item.colors ?? []).slice(0, 4).map((c) => (
                                    <span key={c} className="h-3.5 w-3.5 rounded-full border border-[var(--color-line)]" style={{ backgroundColor: c }} title={c} />
                                  ))}
                                </div>
                                <Button
                                  variant={pickedIds.has(item.id) ? "secondary" : "accent"}
                                  className="mt-1 w-full"
                                  disabled={pickedIds.has(item.id)}
                                  onClick={() => {
                                    add(item);
                                    toast.success(`${title} — ${t.visualSearch.added}`);
                                    track({ product_id: item.id, event_type: "save", page_context: "visual_search" });
                                  }}
                                >
                                  {pickedIds.has(item.id) ? t.visualSearch.added : t.visualSearch.addToMoodboard}
                                </Button>
                              </>
                            ) : (
                              <div className="flex flex-1 flex-col items-center justify-center gap-2 py-3 text-center">
                                <p className="text-xs text-[var(--color-muted)]">{t.visualSearch.lockedHint}</p>
                                <Link
                                  to="/upgrade"
                                  className="rounded-xl bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-[var(--color-canvas)] hover:opacity-90"
                                >
                                  {t.recommendations.unlockCta}
                                </Link>
                              </div>
                            )}
                          </div>
                        </Card>
                      </li>
                    );
                  })}
                </ul>
              )}
            </>
          )}

          {!result && !search.isError && !search.isPending && (
            <div className="hidden lg:block">
              <EmptyState title={t.visualSearch.dropTitle} hint={t.visualSearch.subtitle} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
