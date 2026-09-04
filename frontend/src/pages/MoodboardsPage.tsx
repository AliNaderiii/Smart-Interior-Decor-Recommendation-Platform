import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post } from "@/lib/api";
import type { Moodboard } from "@/lib/types";
import { useMoodboardStore } from "@/stores/moodboardStore";
import { Button, Card, Input, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { OptimizedImage } from "@/components/OptimizedImage";
import { useToast } from "@/components/Toast";
import { useT } from "@/i18n";

export default function MoodboardsPage() {
  const t = useT();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { picked, clear } = useMoodboardStore();
  const [title, setTitle] = useState(t.moodboards.defaultName);
  // Two-step delete: the second click within the same row confirms. Cheaper
  // than a modal and reversible right up to the moment you press again.
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const { data: boards, isLoading, isError, refetch } = useQuery({
    queryKey: ["moodboards"],
    queryFn: () => get<Moodboard[]>("/moodboards"),
  });

  const createBoard = useMutation({
    mutationFn: async () => {
      const items = picked.map((p, i) => ({
        product_id: p.id,
        x: (i % 3) * 4,
        y: Math.floor(i / 3) * 4,
        w: 4,
        h: 4,
      }));
      return post<Moodboard>("/moodboards", {
        title,
        items,
        shopping_list: picked.map((p) => p.id),
      });
    },
    onSuccess: (board) => {
      clear();
      qc.invalidateQueries({ queryKey: ["moodboards"] });
      toast.success(t.moodboards.created);
      navigate(`/moodboard/${board.id}`);
    },
    onError: () => toast.error(t.moodboards.createFailed),
  });

  const deleteBoard = useMutation({
    mutationFn: (id: string) => del(`/moodboards/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["moodboards"] });
      setConfirmId(null);
      toast.success(t.moodboards.deleted);
    },
    onError: () => {
      setConfirmId(null);
      toast.error(t.moodboards.deleteFailed);
    },
  });

  return (
    <div>
      <div>
        <h1 className="h1 text-[var(--color-ink)]">{t.moodboards.title}</h1>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          {t.moodboards.subtitle}
        </p>
      </div>

      {picked.length > 0 && (
        <Card className="mt-6 flex flex-wrap items-center gap-3 p-4">
          <div className="flex -space-x-3">
            {picked.slice(0, 5).map((p) => (
              <OptimizedImage
                key={p.id}
                src={p.image_url}
                alt=""
                width={40}
                height={40}
                sizes="40px"
                widths={[40, 80, 120]}
                wrapperClassName="h-10 w-10 rounded-full border-2 border-[var(--color-surface)]"
              />
            ))}
          </div>
          <p className="text-sm text-[var(--color-muted)]">
            {picked.length} product{picked.length === 1 ? "" : "s"} selected
          </p>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <label htmlFor="board-title" className="sr-only">
              Moodboard title
            </label>
            <Input id="board-title" value={title} onChange={(e) => setTitle(e.target.value)} className="w-48" />
            <Button variant="ghost" onClick={clear}>
              Clear
            </Button>
            <Button variant="accent" onClick={() => createBoard.mutate()} disabled={createBoard.isPending || !title.trim()}>
              {createBoard.isPending ? t.moodboards.creating : t.moodboards.createCta}
            </Button>
          </div>
        </Card>
      )}

      {isLoading ? (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="p-5">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="mt-3 h-3 w-32" />
              <Skeleton className="mt-5 h-9 w-24 rounded-xl" />
            </Card>
          ))}
        </div>
      ) : isError ? (
        <div className="mt-8">
          <ErrorState message={t.moodboards.loadFailed} onRetry={() => refetch()} />
        </div>
      ) : !boards || boards.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title={t.moodboards.emptyTitle}
            hint={t.moodboards.emptyHint}
            action={
              <Link
                to="/recommendations"
                className="inline-block rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
              >
                Browse recommendations
              </Link>
            }
          />
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {boards.map((b) => (
            <Card key={b.id} className="flex flex-col p-5">
              <h2 className="font-semibold text-[var(--color-ink)]">{b.title}</h2>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                {b.items.length} item{b.items.length === 1 ? "" : "s"} · {b.shopping_list.length} in shopping list
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <Link
                  to={`/moodboard/${b.id}`}
                  className="rounded-xl bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
                >
                  Open
                </Link>
                {confirmId === b.id ? (
                  <>
                    <Button
                      variant="ghost"
                      className="text-[var(--color-danger)]"
                      onClick={() => deleteBoard.mutate(b.id)}
                      disabled={deleteBoard.isPending}
                    >
                      {deleteBoard.isPending ? t.moodboards.deleting : t.moodboards.confirmDelete}
                    </Button>
                    <Button variant="ghost" onClick={() => setConfirmId(null)}>
                      Cancel
                    </Button>
                  </>
                ) : (
                  <Button variant="ghost" onClick={() => setConfirmId(b.id)}>
                    Delete
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
