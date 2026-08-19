import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { Moodboard } from "@/lib/types";
import { CATEGORY_LABELS, formatToman } from "@/lib/constants";
import { Card, EmptyState, Spinner } from "@/components/ui";

export default function ShoppingListPage() {
  const [copied, setCopied] = useState<string | null>(null);

  const { data: boards, isLoading } = useQuery({
    queryKey: ["moodboards"],
    queryFn: () => get<Moodboard[]>("/moodboards"),
  });
  const boardId = boards?.[0]?.id;
  const { data: board } = useQuery({
    queryKey: ["moodboard", boardId],
    queryFn: () => get<Moodboard>(`/moodboards/${boardId}`),
    enabled: Boolean(boardId),
  });

  if (isLoading) return <Spinner />;

  const products = board?.products ?? {};
  const rows = (board?.shopping_list ?? [])
    .map((pid) => products[pid])
    .filter((p): p is NonNullable<typeof p> => Boolean(p));
  const total = rows.reduce((s, p) => s + p.price_toman, 0);

  async function copyLink(url: string, id: string) {
    await navigator.clipboard.writeText(url);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  }

  if (rows.length === 0) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-walnut">Shopping list</h1>
        <div className="mt-8">
          <EmptyState
            title="Your shopping list is empty"
            hint='Open a moodboard and press "Add all to shopping list".'
            action={<Link to="/moodboards" className="rounded-xl bg-clay px-4 py-2 text-sm font-semibold text-white">Go to moodboards</Link>}
          />
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-walnut">Shopping list</h1>
      <p className="mt-1 text-sm text-stone">From “{board?.title}” — seller links are validated automatically.</p>

      <Card className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-[#eee7db] text-left text-xs uppercase tracking-wide text-stone">
              <th className="px-4 py-3">Product</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Price</th>
              <th className="px-4 py-3">Seller link</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-b border-[#f5f0e8] last:border-0">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <img src={p.image_url} alt="" width={48} height={48} loading="lazy"
                         className="h-12 w-12 rounded-lg object-cover" />
                    <span className="max-w-[260px] truncate font-medium">{p.title}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-stone">{CATEGORY_LABELS[p.category] ?? p.category}</td>
                <td className="px-4 py-3 font-semibold text-clay-dark">{formatToman(p.price_toman)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span title={p.seller_link_ok === false ? "Link check failed" : p.seller_link_ok ? "Verified (HTTP 200)" : "Not checked yet"}
                          aria-label={p.seller_link_ok ? "Link verified" : "Link not verified"}
                          className={p.seller_link_ok ? "text-sage" : p.seller_link_ok === false ? "text-red-600" : "text-stone"}>
                      ●
                    </span>
                    <a href={p.seller_link} target="_blank" rel="noreferrer noopener"
                       className="font-medium text-clay hover:underline">
                      Open store
                    </a>
                    <button
                      onClick={() => copyLink(p.seller_link, p.id)}
                      className="rounded-lg bg-sand px-2 py-1 text-xs font-medium hover:bg-[#e8e0d4]"
                      aria-label={`Copy link for ${p.title}`}
                    >
                      {copied === p.id ? "Copied ✓" : "Copy"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2} className="px-4 py-4 font-bold">Total</td>
              <td colSpan={2} className="px-4 py-4 text-lg font-bold text-clay-dark">{formatToman(total)}</td>
            </tr>
          </tfoot>
        </table>
      </Card>
    </div>
  );
}
