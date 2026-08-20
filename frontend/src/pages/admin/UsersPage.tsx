import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { useToast } from "@/components/Toast";

interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  subscription_plan: string;
  subscription_active: boolean;
  created_at: string;
}

export default function AdminUsersPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: users, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => get<AdminUser[]>("/admin/users"),
  });

  // Phase 0B PARTIAL: this used to mutate silently — the row re-rendered but
  // nothing confirmed the change, so a slow request looked like a dead button.
  const toggleActive = useMutation({
    mutationFn: (u: AdminUser) => patch(`/admin/users/${u.id}`, { is_active: !u.is_active }),
    onSuccess: (_data, u) => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      toast.success(`${u.email} ${u.is_active ? "disabled" : "enabled"}.`);
    },
    onError: () => toast.error("Could not update that user."),
  });

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-8 w-32" />
        <Card className="mt-6 space-y-px p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 py-3">
              <Skeleton className="h-4 w-56" />
              <Skeleton className="ml-auto h-4 w-20" />
            </div>
          ))}
        </Card>
      </div>
    );
  }

  if (isError) return <ErrorState message="Could not load users." onRetry={() => refetch()} />;

  if (!users || users.length === 0) {
    return (
      <div>
        <h1 className="h1 text-[var(--color-ink)]">Users</h1>
        <div className="mt-8">
          <EmptyState title="No users yet" hint="Accounts appear here as soon as people register." />
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="h1 text-[var(--color-ink)]">Users</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">{users.length} account{users.length === 1 ? "" : "s"}</p>
      <Card className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-[var(--color-line)] text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-[var(--color-line)] last:border-0">
                <td className="px-4 py-3 font-medium text-[var(--color-ink)]">{u.email}</td>
                <td className="px-4 py-3">{u.full_name || "—"}</td>
                <td className="px-4 py-3"><Badge tone={u.role === "admin" ? "clay" : "neutral"}>{u.role}</Badge></td>
                <td className="px-4 py-3">
                  <Badge tone={u.subscription_active ? "success" : "neutral"}>{u.subscription_plan}</Badge>
                </td>
                <td className="px-4 py-3">
                  {u.is_active ? <Badge tone="success">active</Badge> : <Badge tone="warning">disabled</Badge>}
                </td>
                <td className="px-4 py-3">
                  <Button
                    variant="ghost"
                    className="py-1 text-xs"
                    onClick={() => toggleActive.mutate(u)}
                    disabled={toggleActive.isPending}
                  >
                    {u.is_active ? "Disable" : "Enable"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
