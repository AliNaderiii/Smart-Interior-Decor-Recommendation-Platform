import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import { Badge, Card, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";

interface AdminSub {
  id: string;
  user_email: string;
  plan: string;
  is_active: boolean;
  expires_at: string | null;
}

export default function AdminSubscriptionsPage() {
  const { data: subs, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-subs"],
    queryFn: () => get<AdminSub[]>("/admin/subscriptions"),
  });

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-8 w-44" />
        <Card className="mt-6 space-y-px p-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 py-3">
              <Skeleton className="h-4 w-52" />
              <Skeleton className="ml-auto h-4 w-16" />
            </div>
          ))}
        </Card>
      </div>
    );
  }

  if (isError) return <ErrorState message="Could not load subscriptions." onRetry={() => refetch()} />;

  if (!subs || subs.length === 0) {
    return (
      <div>
        <h1 className="h1 text-[var(--color-ink)]">Subscriptions</h1>
        <div className="mt-8">
          <EmptyState
            title="No subscriptions yet"
            hint="Paid plans appear here once a customer completes checkout."
          />
        </div>
      </div>
    );
  }

  const activeCount = subs.filter((s) => s.is_active).length;

  return (
    <div>
      <h1 className="h1 text-[var(--color-ink)]">Subscriptions</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        {activeCount} active of {subs.length}
      </p>
      <Card className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-[var(--color-line)] text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Expires</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.id} className="border-b border-[var(--color-line)] last:border-0">
                <td className="px-4 py-3 font-medium text-[var(--color-ink)]">{s.user_email}</td>
                <td className="px-4 py-3"><Badge tone={s.plan === "pro" ? "clay" : "neutral"}>{s.plan}</Badge></td>
                <td className="px-4 py-3">
                  {s.is_active ? <Badge tone="success">active</Badge> : <Badge>inactive</Badge>}
                </td>
                <td className="px-4 py-3 text-[var(--color-muted)]">
                  {s.expires_at ? new Date(s.expires_at).toLocaleDateString("fa-IR") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
