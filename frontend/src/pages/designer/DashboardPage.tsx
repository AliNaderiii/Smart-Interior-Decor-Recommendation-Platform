import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, get, post } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button, Card, Input, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { useToast } from "@/components/Toast";
import { useCommands } from "@/components/CommandPalette";
import { STATUS_META, avatarFor, getStatus, type ProjectStatus } from "@/lib/projectStatus";

type Filter = "all" | ProjectStatus;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "draft", label: "Draft" },
  { id: "shared", label: "Shared" },
  { id: "approved", label: "Approved" },
];

function Avatar({ name }: { name: string }) {
  const { initials, hue } = avatarFor(name);
  return (
    <span
      aria-hidden="true"
      className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold"
      style={{
        backgroundColor: `hsl(${hue} 62% 92%)`,
        color: `hsl(${hue} 55% 32%)`,
      }}
    >
      {initials}
    </span>
  );
}

function StatusPill({ status }: { status: ProjectStatus }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.bg} ${meta.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden="true" />
      {meta.label}
    </span>
  );
}

export default function DesignerDashboardPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [form, setForm] = useState({ name: "", client_name: "", client_email: "" });

  const { data: projects, isLoading, isError, refetch } = useQuery({
    queryKey: ["projects"],
    queryFn: () => get<Project[]>("/projects"),
  });

  const create = useMutation({
    mutationFn: () => post<Project>("/projects", form),
    onSuccess: () => {
      setOpen(false);
      setForm({ name: "", client_name: "", client_email: "" });
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project created.");
    },
    // Stage 1 (T-1.4 close-out / T-1.7): this used to swallow the server's
    // message and always say "Could not create the project.". The most
    // important failure here is the 402 project quota, whose body carries a
    // specific, actionable Persian sentence («سهمیهٔ پروژه‌های شما … به پایان
    // رسیده است … اشتراک خود را ارتقا دهید») — a designer who hits the free
    // limit was told nothing about why or what to do. Same ApiError shape and
    // same fix as LoginPage. A dedicated upgrade/paywall surface is out of
    // scope for this stage and stays recorded as a PARTIAL in spec-delta.md.
    onError: (e: unknown) =>
      toast.error(e instanceof ApiError ? e.message : "Could not create the project."),
  });

  useCommands(
    [
      {
        id: "designer.new",
        label: "New project",
        group: "Create",
        keywords: "client engagement add create project",
        run: () => setOpen(true),
      },
    ],
    [],
  );

  const rows = useMemo(() => {
    const withStatus = (projects ?? []).map((p) => ({ p, status: getStatus(p.id, p.quiz_count) }));
    return filter === "all" ? withStatus : withStatus.filter((r) => r.status === filter);
  }, [projects, filter]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: 0, draft: 0, shared: 0, approved: 0 };
    for (const p of projects ?? []) {
      c.all++;
      c[getStatus(p.id, p.quiz_count)]++;
    }
    return c;
  }, [projects]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h1 text-[var(--color-ink)]">Projects</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Manage client engagements, run quizzes on their behalf, share results.
          </p>
        </div>
        <Button variant="accent" onClick={() => setOpen(true)}>
          New project
          <kbd className="ml-2 rounded border border-current/25 px-1 text-[10px] opacity-70">⌘K</kbd>
        </Button>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Create project"
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        >
          <Card className="w-full max-w-md p-6">
            <h2 className="text-lg font-semibold text-[var(--color-ink)]">New client project</h2>
            <div className="mt-4 space-y-3">
              <div>
                <label htmlFor="p-name" className="mb-1 block text-sm font-medium text-[var(--color-ink)]">
                  Project name
                </label>
                <Input
                  id="p-name"
                  autoFocus
                  value={form.name}
                  placeholder="Villa Lavasan — living room"
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor="p-client" className="mb-1 block text-sm font-medium text-[var(--color-ink)]">
                  Client name
                </label>
                <Input
                  id="p-client"
                  value={form.client_name}
                  onChange={(e) => setForm({ ...form, client_name: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor="p-email" className="mb-1 block text-sm font-medium text-[var(--color-ink)]">
                  Client email (optional)
                </label>
                <Input
                  id="p-email"
                  type="email"
                  value={form.client_email}
                  onChange={(e) => setForm({ ...form, client_email: e.target.value })}
                />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button variant="accent" onClick={() => create.mutate()} disabled={!form.name || create.isPending}>
                {create.isPending ? "Creating…" : "Create"}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Linear's filter row: counts inline, current filter has weight, no chrome. */}
      {projects && projects.length > 0 && (
        <div className="mt-8 flex items-center gap-1 border-b border-[var(--color-line)] pb-px">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              aria-pressed={filter === f.id}
              className={`relative px-3 py-2 text-sm font-medium transition-colors ${
                filter === f.id
                  ? "text-[var(--color-ink)]"
                  : "text-[var(--color-muted)] hover:text-[var(--color-ink)]"
              }`}
            >
              {f.label}
              <span className="ml-1.5 text-xs text-[var(--color-faint)] tabular-nums">{counts[f.id]}</span>
              {filter === f.id && (
                <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-[var(--color-accent)]" />
              )}
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="mt-6 space-y-px">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-3 py-3">
              <Skeleton className="h-7 w-7 rounded-full" />
              <Skeleton className="h-4 w-64" />
              <Skeleton className="ml-auto h-4 w-20" />
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="mt-8">
          <ErrorState message="Could not load your projects." onRetry={() => refetch()} />
        </div>
      ) : !projects || projects.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="No projects yet"
            hint="A project holds one client, their style quiz, and the boards you share back. Create the first one to get started."
            action={
              <Button variant="accent" onClick={() => setOpen(true)}>
                Create your first project
              </Button>
            }
          />
        </div>
      ) : rows.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title={`No ${filter} projects`}
            hint="Try a different filter to see the rest of your work."
            action={
              <Button variant="secondary" onClick={() => setFilter("all")}>
                Show all projects
              </Button>
            }
          />
        </div>
      ) : (
        /* Issue-list table: 1px separators, no card borders, whole row is the
           hit target. Density over decoration — a designer with 40 clients
           needs to scan, not admire. */
        <ul className="mt-2">
          {rows.map(({ p, status }) => (
            <li key={p.id} className="border-b border-[var(--color-line)] last:border-0">
              <Link
                to={`/designer/project/${p.id}`}
                className="group flex items-center gap-3 rounded-lg px-3 py-3 transition-colors hover:bg-[var(--color-line)]/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
              >
                <StatusPill status={status} />
                <span className="min-w-0 flex-1 truncate font-medium text-[var(--color-ink)]">{p.name}</span>
                <span className="hidden items-center gap-2 sm:flex">
                  <Avatar name={p.client_name || "Unassigned"} />
                  <span className="w-32 truncate text-sm text-[var(--color-muted)]">
                    {p.client_name || "No client"}
                  </span>
                </span>
                <span className="hidden w-20 text-right text-xs text-[var(--color-faint)] tabular-nums md:block">
                  {p.quiz_count} quiz{p.quiz_count === 1 ? "" : "zes"}
                </span>
                <span className="w-24 text-right text-xs text-[var(--color-faint)] tabular-nums">
                  {new Date(p.created_at).toLocaleDateString("fa-IR")}
                </span>
                <span
                  aria-hidden="true"
                  className="text-[var(--color-faint)] opacity-0 transition-opacity group-hover:opacity-100"
                >
                  ›
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
