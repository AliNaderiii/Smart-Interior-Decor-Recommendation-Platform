/**
 * RoomPhotoPrefill — "show us your room, we fill in the quiz" (ADR-015).
 *
 * Mounted at the top of quiz step 1 (styles). One photo → POST
 * /quiz/analyze-room → `quizStore.applySuggestion`. The tier returned by the
 * server decides the copy, not the client: a heuristic (mock) provider can
 * only ever add the pixel palette, and the card says so instead of showing a
 * fake confidence figure.
 *
 * Nothing is uploaded to storage; the preview is a local object URL.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, post } from "@/lib/api";
import { useLocale } from "@/i18n";
import { useQuizStore } from "@/stores/quizStore";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui";
import type { RoomAnalysisResult } from "@/lib/types";
import clsx from "clsx";

const MAX_BYTES = 8 * 1024 * 1024;

export function RoomPhotoPrefill() {
  const { t, locale, num } = useLocale();
  const toast = useToast();
  const applySuggestion = useQuizStore((s) => s.applySuggestion);
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const analyse = useMutation({
    mutationFn: async (photo: File) => {
      const form = new FormData();
      form.append("file", photo);
      return post<RoomAnalysisResult>("/quiz/analyze-room", form);
    },
    onSuccess: (res) => {
      applySuggestion(res.suggestion);
      toast.success(t.roomPhoto.applied);
    },
  });

  const onPick = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const next = e.target.files?.[0] ?? null;
      e.target.value = "";
      setLocalError(null);
      analyse.reset();
      if (!next) return;
      if (!next.type.startsWith("image/")) { setLocalError(t.roomPhoto.notImage); return; }
      if (next.size > MAX_BYTES) { setLocalError(t.roomPhoto.tooLarge); return; }
      setFile(next);
      analyse.mutate(next);
    },
    [analyse, t.roomPhoto.notImage, t.roomPhoto.tooLarge],
  );

  const errorMessage = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.status === 429) return t.roomPhoto.rateLimited;
      if (err.status === 413) return t.roomPhoto.tooLarge;
      if (err.status === 415) return t.roomPhoto.notImage;
    }
    return t.roomPhoto.errorTitle;
  };

  const result = analyse.data;
  const tierCopy = result
    ? result.confidence_tier === "confident"
      ? t.roomPhoto.tierConfident
      : result.confidence_tier === "suggested"
        ? t.roomPhoto.tierSuggested
        : t.roomPhoto.tierPaletteOnly
    : null;
  const label = (row: { id: string; fa: string; en: string }) => (locale === "fa" ? row.fa : row.en);

  return (
    <section
      data-testid="room-photo-prefill"
      data-tier={result?.confidence_tier ?? ""}
      className="mb-6 rounded-2xl border border-dashed border-[var(--color-accent)]/50 bg-[var(--color-accent)]/5 p-4 sm:p-5"
      aria-labelledby="room-photo-title"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        {previewUrl ? (
          <img
            src={previewUrl}
            alt={t.roomPhoto.previewAlt}
            data-testid="room-photo-preview"
            className="h-28 w-40 shrink-0 rounded-xl object-cover ring-1 ring-black/10"
          />
        ) : (
          <div aria-hidden="true" className="grid h-28 w-40 shrink-0 place-items-center rounded-xl bg-white/60 text-3xl ring-1 ring-black/5">
            📷
          </div>
        )}

        <div className="min-w-0 flex-1">
          <h2 id="room-photo-title" className="text-base font-semibold text-[var(--color-ink)]">{t.roomPhoto.title}</h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">{t.roomPhoto.subtitle}</p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only"
              data-testid="room-photo-input"
              onChange={onPick}
            />
            <Button
              type="button"
              variant={result ? "secondary" : "accent"}
              onClick={() => inputRef.current?.click()}
              disabled={analyse.isPending}
              data-testid="room-photo-cta"
            >
              {analyse.isPending ? t.roomPhoto.analyzing : result ? t.roomPhoto.retry : t.roomPhoto.cta}
            </Button>
            <span className="text-xs text-[var(--color-faint)]">{t.roomPhoto.privacy}</span>
          </div>

          {localError && <p role="alert" className="mt-3 text-sm text-red-700">{localError}</p>}
          {analyse.isError && (
            <p role="alert" className="mt-3 text-sm text-red-700">{errorMessage(analyse.error)}</p>
          )}

          {result && (
            <div data-testid="room-photo-result" className="mt-4 rounded-xl bg-white/80 p-3 text-sm ring-1 ring-black/5">
              <p
                className={clsx(
                  "font-medium",
                  result.confidence_tier === "confident" && "text-emerald-800",
                  result.confidence_tier === "suggested" && "text-amber-800",
                  result.confidence_tier === "palette_only" && "text-[var(--color-muted)]",
                )}
              >
                {tierCopy}
              </p>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[var(--color-ink)]">
                <dt className="text-[var(--color-muted)]">{t.roomPhoto.styles}</dt>
                <dd data-testid="room-photo-styles">
                  {result.labels.styles.length ? result.labels.styles.map(label).join(locale === "fa" ? "، " : ", ") : t.roomPhoto.noneDetected}
                </dd>
                <dt className="text-[var(--color-muted)]">{t.roomPhoto.materials}</dt>
                <dd data-testid="room-photo-materials">
                  {result.labels.materials.length ? result.labels.materials.map(label).join(locale === "fa" ? "، " : ", ") : t.roomPhoto.noneDetected}
                </dd>
                <dt className="text-[var(--color-muted)]">{t.roomPhoto.colors}</dt>
                <dd className="flex flex-wrap gap-1.5" data-testid="room-photo-palette">
                  {result.palette.map((hex) => (
                    <span key={hex} title={hex} className="h-5 w-5 rounded-full ring-1 ring-inset ring-black/10" style={{ backgroundColor: hex }} />
                  ))}
                </dd>
              </dl>
              <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--color-faint)]">
                {result.meta.heuristic ? (
                  <span data-testid="room-photo-heuristic" className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-900">{t.roomPhoto.heuristicBadge}</span>
                ) : (
                  <span data-testid="room-photo-confidence">{t.roomPhoto.confidence(num(Math.round(result.confidence * 100)))}</span>
                )}
                <span>{t.roomPhoto.dimensionsNote}</span>
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
