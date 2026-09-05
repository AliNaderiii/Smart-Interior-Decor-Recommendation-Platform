import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { get, patch, post } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button, Card, Input, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { useToast } from "@/components/Toast";
import { STATUS_META, STATUS_ORDER, avatarFor, type ProjectStatus } from "@/lib/projectStatus";

export default function DesignerProjectPage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const [shareResult, setShareResult] = useState<{ share_url: string; token: string } | null>(null);
  const [email, setEmail] = useState("");
  const [copied, setCopied] = useState(false);

  const { data: project, isLoading, isError, refetch } = useQuery({
    queryKey: ["project", id],
    queryFn: () => get<Project>(`/projects/${id}`),
    enabled: Boolean(id),
  });

  // Sharing a project moves it out of draft on the server, so the dashboard
  // reflects it for anyone looking — not just this browser.
  const statusMut = useMutation({
    mutationFn: (next: string) => patch<Project>(`/projects/${id}/status`, { status: next }),
    onSuccess: () => {
      refetch();
      toast.success("Project status updated.");
    },
    onError: () => toast.error("Could not update the project status."),
  });

  const share = useMutation({
    mutationFn: (quizId: string) =>
      post<{ share_url: string; token: string }>(`/projects/${id}/share`, {
        quiz_id: quizId,
        send_to_email: email || undefined,
      }),
    onSuccess: (result) => {
      setShareResult(result);
      if (project?.status === "draft") statusMut.mutate("shared");
      toast.success(
        email ? `Share link created and emailed to ${email}.` : "Share link created.",
      );
    },
    onError: () => toast.error("Could not create the share link."),
  });

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-8 w-72" />
        <Skeleton className="mt-3 h-4 w-52" />
        <Skeleton className="mt-8 h-24 w-full rounded-2xl" />
      </div>
    );
  }
  if (isError || !project) {
    return <ErrorState message="Project not found." onRetry={() => refetch()} />;
  }

  const status = project.status as ProjectStatus;
  const meta = STATUS_META[status];
  const { initials, hue } = avatarFor(project.client_name || "Unassigned");
  const shareUrl = shareResult ? window.location.origin + shareResult.share_url : "";

  async function copyShare() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      toast.success("Share link copied to clipboard.");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Clipboard blocked by your browser — select the link and copy manually.");
    }
  }

  return (
    <div>
      <Link
        to="/designer"
        className="text-sm text-[var(--color-muted)] transition-colors hover:text-[var(--color-ink)]"
      >
        ‹ All projects
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-semibold"
            style={{ backgroundColor: `hsl(${hue} 62% 92%)`, color: `hsl(${hue} 55% 32%)` }}
          >
            {initials}
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="h1 text-[var(--color-ink)]">{project.name}</h1>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.bg} ${meta.text}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden="true" />
                {meta.label}
              </span>
            </div>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              {project.client_name || "No client name"}
              {project.client_email && ` · ${project.client_email}`}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {/* Lifecycle switcher. Writes to the server so the state is the
              same on every device and for every viewer of the project. */}
          <select
            value={status}
            onChange={(e) => statusMut.mutate(e.target.value as ProjectStatus)}
            disabled={statusMut.isPending}
            aria-label="Project status"
            className="rounded-xl border border-[var(--color-line)] bg-transparent px-3 py-2.5 text-sm font-medium text-[var(--color-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            {STATUS_ORDER.map((sVal) => (
              <option key={sVal} value={sVal}>
                {STATUS_META[sVal].label}
              </option>
            ))}
          </select>
          <Link
            to={`/quiz?project=${project.id}`}
            className="rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
          >
            Run quiz for this client
          </Link>
        </div>
      </div>

      {/* At-a-glance counters. Before Phase A a project page showed only a
          list of quizzes, so a designer could not tell whether the client had
          actually responded to anything. */}
      <div className="mt-8 grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-[var(--color-line)] p-4">
          <p className="text-2xl font-semibold tabular-nums text-[var(--color-ink)]">
            {project.moodboard_count}
          </p>
          <p className="mt-1 text-sm text-[var(--color-muted)]">Moodboards</p>
        </div>
        <div className="rounded-2xl border border-[var(--color-line)] p-4">
          <p className="text-2xl font-semibold tabular-nums text-[var(--color-ok)]">
            {project.approved_count}
          </p>
          <p className="mt-1 text-sm text-[var(--color-muted)]">Approved by client</p>
        </div>
        <div className="rounded-2xl border border-[var(--color-line)] p-4">
          <p className="text-2xl font-semibold tabular-nums text-[var(--color-warn)]">
            {project.rejected_count}
          </p>
          <p className="mt-1 text-sm text-[var(--color-muted)]">Rejected</p>
        </div>
      </div>

      {/* The client's actual verdicts. A rejection with a reason is the most
          actionable thing on this page, so it is shown before the quiz list. */}
      {project.feedback && project.feedback.length > 0 && (
        <>
          <h2 className="mt-10 text-lg font-semibold text-[var(--color-ink)]">Client feedback</h2>
          <ul className="mt-4 space-y-2">
            {project.feedback.map((f) => (
              <li
                key={f.product_id}
                className="flex flex-wrap items-start gap-3 rounded-2xl border border-[var(--color-line)] p-4"
              >
                <span
                  className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                    f.verdict === "approved"
                      ? "bg-[var(--color-ok)]/10 text-[var(--color-ok)]"
                      : "bg-[var(--color-warn)]/10 text-[var(--color-warn)]"
                  }`}
                >
                  {f.verdict === "approved" ? "Approved" : "Rejected"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-[var(--color-ink)]">{f.title}</p>
                  {f.comment && (
                    <p className="mt-1 text-sm leading-relaxed text-[var(--color-muted)]">
                      “{f.comment}”
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {project.moodboards && project.moodboards.length > 0 && (
        <>
          <h2 className="mt-10 text-lg font-semibold text-[var(--color-ink)]">Moodboards</h2>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {project.moodboards.map((m) => (
              <li key={m.id}>
                <Link
                  to={`/moodboard/${m.id}`}
                  className="block rounded-2xl border border-[var(--color-line)] p-4 transition-colors hover:border-[var(--color-accent)]"
                >
                  <p className="font-medium text-[var(--color-ink)]">{m.title}</p>
                  <p className="mt-1 text-sm text-[var(--color-muted)]">
                    {m.item_count} items
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}

      <h2 className="mt-10 text-lg font-semibold text-[var(--color-ink)]">Quizzes &amp; results</h2>
      {!project.quizzes || project.quizzes.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="No quizzes yet"
            hint="Run the style quiz on behalf of your client to generate recommendations you can share back."
            action={
              <Link
                to={`/quiz?project=${project.id}`}
                className="inline-block rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
              >
                Start the quiz
              </Link>
            }
          />
        </div>
      ) : (
        <ul className="mt-4 space-y-3">
          {project.quizzes.map((q) => (
            <li key={q.id}>
              <Card className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-[var(--color-ink)]">
                    {q.client_name || "Unnamed"} — {q.styles.join(", ")}
                  </p>
                  <p className="text-xs text-[var(--color-faint)]">
                    {new Date(q.created_at).toLocaleString("fa-IR")}
                  </p>
                </div>
                <Link
                  to={`/recommendations?quiz=${q.id}`}
                  className="rounded-xl border border-[var(--color-line)] px-3 py-2 text-sm font-semibold text-[var(--color-ink)] hover:bg-[var(--color-line)]"
                >
                  View results
                </Link>
                <Button variant="secondary" onClick={() => share.mutate(q.id)} disabled={share.isPending}>
                  {share.isPending ? "Generating…" : email ? "Share & email" : "Share with client"}
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <Card className="mt-6 p-4">
        <label htmlFor="share-email" className="mb-1 block text-sm font-medium text-[var(--color-ink)]">
          Also email the link to (optional)
        </label>
        <Input
          id="share-email"
          type="email"
          value={email}
          placeholder="client@example.com"
          onChange={(e) => setEmail(e.target.value)}
          className="max-w-sm"
        />
        <p className="mt-1.5 text-xs text-[var(--color-faint)]">
          Fill this in before pressing “Share” and the link is emailed as well as copied here.
        </p>

        {shareResult && (
          <div className="mt-4 rounded-xl border border-[var(--color-ok)]/25 bg-[var(--color-ok)]/8 p-3">
            <p className="text-sm font-medium text-[var(--color-ok)]">Share link ready</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg bg-[var(--color-surface)] px-2 py-1.5 text-xs text-[var(--color-ink)]">
                {shareUrl}
              </code>
              <Button variant="secondary" className="py-1.5 text-xs" onClick={copyShare}>
                {copied ? "Copied ✓" : "Copy link"}
              </Button>
              <a
                href={shareResult.share_url}
                target="_blank"
                rel="noreferrer noopener"
                className="rounded-xl border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--color-ink)] hover:bg-[var(--color-line)]"
              >
                Preview ↗
              </a>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
