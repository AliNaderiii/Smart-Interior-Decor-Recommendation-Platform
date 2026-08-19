import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, get, patch, post } from "@/lib/api";
import type { Envelope } from "@/lib/api";
import type { AdminProduct } from "@/lib/types";
import { CATEGORY_LABELS, formatToman } from "@/lib/constants";
import { Badge, Button, Card, Spinner } from "@/components/ui";

interface ProductList {
  items: AdminProduct[];
  total: number;
  page: number;
  page_size: number;
}

export default function AdminProductsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<"all" | "pending" | "verified">("all");
  const [editing, setEditing] = useState<AdminProduct | null>(null);
  const [editJson, setEditJson] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadResult, setUploadResult] = useState<string>("");

  const query = filter === "all" ? "" : `&is_verified=${filter === "verified"}`;
  const { data, isLoading } = useQuery({
    queryKey: ["admin-products", page, filter],
    queryFn: () => get<ProductList>(`/products?page=${page}&page_size=15${query}`),
  });

  const verify = useMutation({
    mutationFn: (id: string) => post(`/products/${id}/verify`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-products"] }),
  });

  const saveEdit = useMutation({
    mutationFn: async () => {
      if (!editing) return;
      const parsed = JSON.parse(editJson) as Partial<AdminProduct>;
      return patch(`/products/${editing.id}`, parsed);
    },
    onSuccess: () => {
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["admin-products"] });
    },
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data: resp } = await api.post<Envelope<{ extraction: { confidence: number } }>>(
        "/products/upload", form, { headers: { "Content-Type": "multipart/form-data" } },
      );
      return resp.data;
    },
    onSuccess: (result) => {
      setUploadResult(
        `AI extraction complete (confidence ${(result.extraction.confidence * 100).toFixed(0)}%) — review & verify below.`,
      );
      qc.invalidateQueries({ queryKey: ["admin-products"] });
    },
  });

  function openEdit(p: AdminProduct) {
    setEditing(p);
    setEditJson(JSON.stringify(
      { title: p.title, category: p.category, price_toman: p.price_toman,
        colors: p.colors, styles: p.styles, materials: p.materials,
        patterns: p.patterns, width_cm: p.width_cm, depth_cm: p.depth_cm,
        height_cm: p.height_cm, seller_link: p.seller_link, description: p.description },
      null, 2,
    ));
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-walnut">Products</h1>
        <div className="flex items-center gap-2">
          {(["all", "pending", "verified"] as const).map((f) => (
            <Button key={f} variant={filter === f ? "primary" : "ghost"} className="py-1.5 text-xs capitalize"
                    onClick={() => { setFilter(f); setPage(1); }}>
              {f}
            </Button>
          ))}
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
                 onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
          <Button onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? "Extracting features…" : "+ Upload product image"}
          </Button>
        </div>
      </div>
      {uploadResult && <p className="mt-3 rounded-lg bg-[#e7efe4] px-3 py-2 text-sm text-sage">{uploadResult}</p>}

      {isLoading ? (
        <Spinner />
      ) : (
        <Card className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="border-b border-[#eee7db] text-left text-xs uppercase tracking-wide text-stone">
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3">AI features</th>
                <th className="px-4 py-3">Confidence</th>
                <th className="px-4 py-3">Price</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((p) => (
                <tr key={p.id} className="border-b border-[#f5f0e8] align-top last:border-0">
                  <td className="max-w-[240px] px-4 py-3">
                    <div className="flex items-center gap-3">
                      <img src={p.image_url} alt="" width={48} height={48} loading="lazy"
                           className="h-12 w-12 shrink-0 rounded-lg object-cover" />
                      <div className="min-w-0">
                        <p className="truncate font-medium">{p.title}</p>
                        <p className="text-xs text-stone">{CATEGORY_LABELS[p.category] ?? p.category}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex max-w-[220px] flex-wrap gap-1">
                      {p.styles.map((s) => <Badge key={s} tone="clay">{s}</Badge>)}
                      {p.materials.map((m) => <Badge key={m}>{m}</Badge>)}
                      {p.colors.slice(0, 3).map((c) => (
                        <span key={c} className="h-5 w-5 rounded-full border border-[#e5ded3]" style={{ backgroundColor: c }} title={c} />
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={p.extraction_confidence >= 0.8 ? "text-sage" : "text-amber-700"}>
                      {(p.extraction_confidence * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">{formatToman(p.price_toman)}</td>
                  <td className="px-4 py-3">
                    {p.is_verified
                      ? <Badge tone="success">verified</Badge>
                      : <Badge tone="warning">pending review</Badge>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1.5">
                      {!p.is_verified && (
                        <Button className="py-1 text-xs" onClick={() => verify.mutate(p.id)}>Verify</Button>
                      )}
                      <Button variant="ghost" className="py-1 text-xs" onClick={() => openEdit(p)}>Edit</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div className="mt-4 flex items-center justify-between text-sm text-stone">
        <span>{data?.total ?? 0} products</span>
        <div className="flex gap-2">
          <Button variant="secondary" className="py-1.5 text-xs" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</Button>
          <Button variant="secondary" className="py-1.5 text-xs"
                  disabled={!data || page * data.page_size >= data.total}
                  onClick={() => setPage(page + 1)}>Next →</Button>
        </div>
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" role="dialog" aria-modal="true" aria-label="Edit product">
          <Card className="w-full max-w-lg p-6">
            <h2 className="text-lg font-bold text-walnut">Edit product JSON</h2>
            <p className="mt-1 text-xs text-stone">Human-in-the-loop: correct AI-extracted features, then save & verify.</p>
            <textarea
              value={editJson}
              onChange={(e) => setEditJson(e.target.value)}
              rows={14}
              aria-label="Product JSON"
              className="mt-3 w-full rounded-xl border border-[#e5ded3] bg-[#fbfaf8] p-3 font-mono text-xs focus:border-clay focus:outline-none"
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              <Button onClick={() => saveEdit.mutate()} disabled={saveEdit.isPending}>
                {saveEdit.isPending ? "Saving…" : "Save changes"}
              </Button>
            </div>
            {saveEdit.isError && <p className="mt-2 text-xs text-red-700">Invalid JSON or save failed.</p>}
          </Card>
        </div>
      )}
    </div>
  );
}
