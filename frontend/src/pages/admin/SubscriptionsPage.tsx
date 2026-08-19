import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import { Badge, Card, Spinner } from "@/components/ui";

interface AdminSub {
  id: string;
  user_email: string;
  plan: string;
  is_active: boolean;
  expires_at: string | null;
}

export default function AdminSubscriptionsPage() {
  const { data: subs, isLoading } = useQuery({
    queryKey: ["admin-subs"],
    queryFn: () => get<AdminSub[]>("/admin/subscriptions"),
  });

  if (isLoading) return <Spinner />;

  return (
    <div>
      <h1 className="text-2xl font-bold text-walnut">Subscriptions</h1>
      <Card className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-[#eee7db] text-left text-xs uppercase tracking-wide text-stone">
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Expires</th>
            </tr>
          </thead>
          <tbody>
            {(subs ?? []).map((s) => (
              <tr key={s.id} className="border-b border-[#f5f0e8] last:border-0">
                <td className="px-4 py-3 font-medium">{s.user_email}</td>
                <td className="px-4 py-3"><Badge tone={s.plan === "pro" ? "clay" : "neutral"}>{s.plan}</Badge></td>
                <td className="px-4 py-3">
                  {s.is_active ? <Badge tone="success">active</Badge> : <Badge>inactive</Badge>}
                </td>
                <td className="px-4 py-3 text-stone">
                  {s.expires_at ? new Date(s.expires_at).toLocaleDateString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
