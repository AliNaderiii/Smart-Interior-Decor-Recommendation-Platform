import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, patch } from "@/lib/api";
import { Badge, Button, Card, Spinner } from "@/components/ui";

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
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => get<AdminUser[]>("/admin/users"),
  });

  const toggleActive = useMutation({
    mutationFn: (u: AdminUser) => patch(`/admin/users/${u.id}`, { is_active: !u.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  if (isLoading) return <Spinner />;

  return (
    <div>
      <h1 className="text-2xl font-bold text-walnut">Users</h1>
      <Card className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-[#eee7db] text-left text-xs uppercase tracking-wide text-stone">
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(users ?? []).map((u) => (
              <tr key={u.id} className="border-b border-[#f5f0e8] last:border-0">
                <td className="px-4 py-3 font-medium">{u.email}</td>
                <td className="px-4 py-3">{u.full_name || "—"}</td>
                <td className="px-4 py-3"><Badge tone={u.role === "admin" ? "clay" : "neutral"}>{u.role}</Badge></td>
                <td className="px-4 py-3">
                  <Badge tone={u.subscription_active ? "success" : "neutral"}>{u.subscription_plan}</Badge>
                </td>
                <td className="px-4 py-3">
                  {u.is_active ? <Badge tone="success">active</Badge> : <Badge tone="warning">disabled</Badge>}
                </td>
                <td className="px-4 py-3">
                  <Button variant="ghost" className="py-1 text-xs" onClick={() => toggleActive.mutate(u)}>
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
