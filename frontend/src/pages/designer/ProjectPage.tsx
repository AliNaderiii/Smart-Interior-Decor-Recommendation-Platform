import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { get, post } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button, Card, EmptyState, ErrorState, Input, Spinner } from "@/components/ui";

export default function DesignerProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [shareResult, setShareResult] = useState<{ share_url: string; token: string } | null>(null);
  const [email, setEmail] = useState("");
  const [copied, setCopied] = useState(false);

  const { data: project, isLoading, isError, refetch } = useQuery({
    queryKey: ["project", id],
    queryFn: () => get<Project>(`/projects/${id}`),
    enabled: Boolean(id),
  });

  const share = useMutation({
    mutationFn: (quizId: string) =>
      post<{ share_url: string; token: string }>(`/projects/${id}/share`, {
        quiz_id: quizId,
        send_to_email: email || undefined,
      }),
    onSuccess: setShareResult,
  });

  if (isLoading) return <Spinner />;
  if (isError || !project) return <ErrorState message="Project not found." onRetry={() => refetch()} />;

  async function copyShare() {
    if (!shareResult) return;
    await navigator.clipboard.writeText(window.location.origin + shareResult.share_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-walnut">{project.name}</h1>
      <p className="mt-1 text-sm text-stone">
        Client: {project.client_name || "—"} {project.client_email && `(${project.client_email})`}
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link to={`/quiz?project=${project.id}`}
              className="rounded-xl bg-clay px-4 py-2.5 text-sm font-semibold text-white hover:bg-clay-dark">
          Run quiz for this client
        </Link>
      </div>

      <h2 className="mt-10 text-lg font-bold text-walnut">Quizzes & results</h2>
      {!project.quizzes || project.quizzes.length === 0 ? (
        <div className="mt-4">
          <EmptyState title="No quizzes yet" hint="Run the style quiz on behalf of your client to generate recommendations." />
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {project.quizzes.map((q) => (
            <Card key={q.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{q.client_name || "Unnamed"} — {q.styles.join(", ")}</p>
                <p className="text-xs text-stone">{new Date(q.created_at).toLocaleString()}</p>
              </div>
              <Link to={`/recommendations?quiz=${q.id}`}
                    className="rounded-xl bg-sand px-3 py-2 text-sm font-semibold text-walnut hover:bg-[#e8e0d4]">
                View results
              </Link>
              <Button variant="secondary" onClick={() => share.mutate(q.id)} disabled={share.isPending}>
                {share.isPending ? "Generating…" : "Share with client"}
              </Button>
            </Card>
          ))}
        </div>
      )}

      <Card className="mt-6 p-4">
        <label htmlFor="share-email" className="mb-1 block text-sm font-medium">
          Also email the link to (optional)
        </label>
        <Input id="share-email" type="email" value={email} placeholder="client@example.com"
               onChange={(e) => setEmail(e.target.value)} className="max-w-sm" />
        {shareResult && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-[#e7efe4] px-3 py-2 text-sm">
            <span className="font-medium text-sage">Share link ready:</span>
            <code className="truncate text-xs">{window.location.origin}{shareResult.share_url}</code>
            <Button variant="ghost" className="py-1 text-xs" onClick={copyShare}>
              {copied ? "Copied ✓" : "Copy"}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
