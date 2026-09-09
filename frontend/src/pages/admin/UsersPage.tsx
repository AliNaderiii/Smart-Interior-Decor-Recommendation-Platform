import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, del, get, patch } from "@/lib/api";
import { deleteConfirmMessage, filterUsers, type AdminUser, type DeleteReceipt } from "@/lib/adminUsers";
import { Badge, Button, Card, Input, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { useToast } from "@/components/Toast";
import { useAuthStore } from "@/stores/authStore";

export default function AdminUsersPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const me = useAuthStore((s) => s.user);
  const [filter, setFilter] = useState("");
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

  // P4-B: administrative erasure. The backend refuses self-deletion and the
  // removal of the last active administrator with 409 and a specific sentence;
  // that sentence is surfaced verbatim rather than flattened into a generic
  // failure (the same defect class LoginPage and the designer quota wall had).
  const deleteUser = useMutation({
    mutationFn: (u: AdminUser) => del<DeleteReceipt>(`/admin/users/${u.id}`),
    onSuccess: (receipt, u) => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      toast.success(`${u.email} deleted. Audit pseudonym ${receipt.audit_pseudonym}.`);
    },
    onError: (err, u) => {
      const specific = err instanceof ApiError && (err.status === 409 || err.status === 404);
      toast.error(specific ? err.message : `Could not delete ${u.email}.`);
    },
  });

  const visible = useMemo(() => filterUsers(users ?? [], filter), [users, filter]);

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
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        {users.length} account{users.length === 1 ? "" : "s"}
        {filter.trim() ? ` · ${visible.length} shown` : ""}
      </p>
      <div className="mt-4 max-w-sm">
        <label htmlFor="admin-users-filter" className="sr-only">Filter by e-mail or name</label>
        <Input
          id="admin-users-filter"
          type="search"
          placeholder="Filter by e-mail or name…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <Card className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-[var(--color-line)] text-start text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((u) => {
              const isMe = me?.id === u.id;
              return (
                <tr key={u.id} className="border-b border-[var(--color-line)] last:border-0">
                  <td className="px-4 py-3 font-medium text-[var(--color-ink)]">
                    {u.email}
                    {isMe && <span className="ms-2 text-xs text-[var(--color-muted)]">(you)</span>}
                  </td>
                  <td className="px-4 py-3">{u.full_name || "—"}</td>
                  <td className="px-4 py-3"><Badge tone={u.role === "admin" ? "clay" : "neutral"}>{u.role}</Badge></td>
                  <td className="px-4 py-3">
                    <Badge tone={u.subscription_active ? "success" : "neutral"}>{u.subscription_plan}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active ? <Badge tone="success">active</Badge> : <Badge tone="warning">disabled</Badge>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        className="py-1 text-xs"
                        onClick={() => toggleActive.mutate(u)}
                        disabled={toggleActive.isPending}
                      >
                        {u.is_active ? "Disable" : "Enable"}
                      </Button>
                      {/* The backend refuses self-deletion (409); not rendering the
                          control for the caller's own row keeps the UI honest about it. */}
                      {!isMe && (
                        <Button
                          variant="ghost"
                          className="py-1 text-xs text-[var(--color-danger)]"
                          aria-label={`Delete ${u.email}`}
                          onClick={() => {
                            if (window.confirm(deleteConfirmMessage(u))) deleteUser.mutate(u);
                          }}
                          disabled={deleteUser.isPending}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {visible.length === 0 && (
          <p className="px-4 py-6 text-sm text-[var(--color-muted)]">No account matches “{filter}”.</p>
        )}
      </Card>
    </div>
  );
}
