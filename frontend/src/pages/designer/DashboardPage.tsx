import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button, Card, EmptyState, Input, Spinner } from "@/components/ui";

export default function DesignerDashboardPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", client_name: "", client_email: "" });

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => get<Project[]>("/projects"),
  });

  const create = useMutation({
    mutationFn: () => post<Project>("/projects", form),
    onSuccess: () => {
      setOpen(false);
      setForm({ name: "", client_name: "", client_email: "" });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-walnut">Projects</h1>
          <p className="mt-1 text-sm text-stone">Manage client engagements, run quizzes on their behalf, share results.</p>
        </div>
        <Button onClick={() => setOpen(true)}>+ New project</Button>
      </div>

      {open && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" role="dialog" aria-modal="true" aria-label="Create project">
          <Card className="w-full max-w-md p-6">
            <h2 className="text-lg font-bold text-walnut">New client project</h2>
            <div className="mt-4 space-y-3">
              <div>
                <label htmlFor="p-name" className="mb-1 block text-sm font-medium">Project name</label>
                <Input id="p-name" value={form.name} placeholder="Villa Lavasan — living room"
                       onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <label htmlFor="p-client" className="mb-1 block text-sm font-medium">Client name</label>
                <Input id="p-client" value={form.client_name}
                       onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
              </div>
              <div>
                <label htmlFor="p-email" className="mb-1 block text-sm font-medium">Client email (optional)</label>
                <Input id="p-email" type="email" value={form.client_email}
                       onChange={(e) => setForm({ ...form, client_email: e.target.value })} />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
              <Button onClick={() => create.mutate()} disabled={!form.name || create.isPending}>
                {create.isPending ? "Creating…" : "Create"}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {isLoading ? (
        <Spinner />
      ) : !projects || projects.length === 0 ? (
        <div className="mt-8">
          <EmptyState title="No projects yet" hint="Create your first client project to start a style quiz on their behalf." />
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Card key={p.id} className="p-5">
              <h2 className="font-semibold">{p.name}</h2>
              <p className="mt-1 text-sm text-stone">
                {p.client_name || "No client name"} · {p.quiz_count} quiz{p.quiz_count === 1 ? "" : "zes"}
              </p>
              <p className="mt-1 text-xs text-stone">{new Date(p.created_at).toLocaleDateString()}</p>
              <Link to={`/designer/project/${p.id}`}
                    className="mt-4 inline-block rounded-xl bg-clay px-4 py-2 text-sm font-semibold text-white hover:bg-clay-dark">
                Open project
              </Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
