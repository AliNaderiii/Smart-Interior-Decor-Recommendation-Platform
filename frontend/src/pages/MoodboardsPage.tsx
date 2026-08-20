import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post } from "@/lib/api";
import type { Moodboard } from "@/lib/types";
import { useMoodboardStore } from "@/stores/moodboardStore";
import { Button, Card, EmptyState, Input, Spinner } from "@/components/ui";
import { OptimizedImage } from "@/components/OptimizedImage";

export default function MoodboardsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { picked, clear } = useMoodboardStore();
  const [title, setTitle] = useState("My Living Room");

  const { data: boards, isLoading } = useQuery({
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
      navigate(`/moodboard/${board.id}`);
    },
  });

  const deleteBoard = useMutation({
    mutationFn: (id: string) => del(`/moodboards/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["moodboards"] }),
  });

  return (
    <div>
      <h1 className="text-2xl font-bold text-walnut">Moodboards</h1>

      {picked.length > 0 && (
        <Card className="mt-6 flex flex-wrap items-center gap-3 p-4">
          <div className="flex -space-x-3">
            {picked.slice(0, 5).map((p) => (
              <OptimizedImage key={p.id} src={p.image_url} alt="" width={40} height={40}
                              sizes="40px" widths={[40, 80, 120]}
                              wrapperClassName="h-10 w-10 rounded-full border-2 border-white" />
            ))}
          </div>
          <p className="text-sm text-stone">{picked.length} products selected</p>
          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="board-title" className="sr-only">Moodboard title</label>
            <Input id="board-title" value={title} onChange={(e) => setTitle(e.target.value)} className="w-48" />
            <Button onClick={() => createBoard.mutate()} disabled={createBoard.isPending}>
              {createBoard.isPending ? "Creating…" : "Create moodboard"}
            </Button>
          </div>
        </Card>
      )}

      {isLoading ? (
        <Spinner />
      ) : !boards || boards.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="No moodboards yet"
            hint="Pick products on the recommendations page, then create your first board."
            action={<Link to="/recommendations" className="rounded-xl bg-clay px-4 py-2 text-sm font-semibold text-white">Browse recommendations</Link>}
          />
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {boards.map((b) => (
            <Card key={b.id} className="p-5">
              <h2 className="font-semibold">{b.title}</h2>
              <p className="mt-1 text-sm text-stone">
                {b.items.length} items · {b.shopping_list.length} in shopping list
              </p>
              <div className="mt-4 flex gap-2">
                <Link to={`/moodboard/${b.id}`} className="rounded-xl bg-clay px-4 py-2 text-sm font-semibold text-white hover:bg-clay-dark">
                  Open
                </Link>
                <Button variant="ghost" onClick={() => deleteBoard.mutate(b.id)}>Delete</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
