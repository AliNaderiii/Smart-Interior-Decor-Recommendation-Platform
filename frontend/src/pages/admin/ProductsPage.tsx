import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, patch, post } from "@/lib/api";
import type { AdminProduct } from "@/lib/types";
import { CATEGORY_LABELS, STYLES, formatToman } from "@/lib/constants";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { EmptyState, ErrorState } from "@/components/states";
import { OptimizedImage } from "@/components/OptimizedImage";
import { useToast } from "@/components/Toast";
import { useCommands } from "@/components/CommandPalette";
import { JsonDiff, diffObjects } from "@/components/JsonDiff";
import { useDialog } from "@/hooks/useDialog";

interface ProductList {
  items: AdminProduct[];
  total: number;
  page: number;
  page_size: number;
}

/** The subset of a product the reviewer may correct. Kept in one place so the
 *  editor, the diff and the PATCH payload can never drift apart. */
function editableOf(p: AdminProduct): Record<string, unknown> {
  return {
    title: p.title, category: p.category, price_toman: p.price_toman,
    colors: p.colors, styles: p.styles, materials: p.materials,
    patterns: p.patterns, width_cm: p.width_cm, depth_cm: p.depth_cm,
    height_cm: p.height_cm, seller_link: p.seller_link, description: p.description,
  };
}

function EditProductModal({
  editing,
  onClose,
  editJson,
  setEditJson,
  toggleEditorStyle,
  editorStyles,
  diffRows,
  jsonValid,
  onSave,
  isPending,
  isError,
}: {
  editing: AdminProduct;
  onClose: () => void;
  editJson: string;
  setEditJson: (v: string) => void;
  toggleEditorStyle: (id: string) => void;
  editorStyles: string[];
  diffRows: ReturnType<typeof diffObjects>;
  jsonValid: boolean;
  onSave: () => void;
  isPending: boolean;
  isError: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useDialog({
    isOpen: true,
    onClose,
    containerRef,
    restoreFocus: true,
    trapFocus: true,
    closeOnEscape: true,
  });

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Edit product"
      onClick={onClose}
    >
      <Card className="max-h-[90vh] w-full max-w-2xl overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-[var(--color-ink)]">Review AI extraction: {editing.title}</h2>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Human-in-the-loop: correct what the model got wrong, check the diff, then save.
        </p>
        <fieldset className="mt-4">
          <legend className="text-xs font-semibold text-[var(--color-muted)]">Style taxonomy</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {STYLES.map((style) => (
              <button
                key={style.id}
                type="button"
                onClick={() => toggleEditorStyle(style.id)}
                aria-pressed={editorStyles.includes(style.id)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  editorStyles.includes(style.id)
                    ? "border-[var(--color-accent)] bg-[var(--color-accent)]/10"
                    : "border-[var(--color-line)]"
                }`}
              >
                {style.icon} {style.fa}
              </button>
            ))}
          </div>
        </fieldset>
        <textarea
          value={editJson}
          onChange={(e) => setEditJson(e.target.value)}
          rows={14}
          aria-label="Product JSON"
          spellCheck={false}
          className={`mt-3 w-full rounded-xl border bg-[var(--color-canvas)] p-3 font-mono text-xs text-[var(--color-ink)] focus:outline-none ${
            jsonValid
              ? "border-[var(--color-line)] focus:border-[var(--color-accent)]"
              : "border-[var(--color-danger)]"
          }`}
        />
        {!jsonValid && (
          <p className="mt-1 text-xs text-[var(--color-danger)]" role="alert">
            Not valid JSON yet — fix the syntax to enable saving.
          </p>
        )}

        <h3 className="mt-5 text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
          Changes vs AI extraction
        </h3>
        <div className="mt-2">
          <JsonDiff rows={diffRows} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="accent"
            onClick={onSave}
            disabled={isPending || !jsonValid || diffRows.length === 0}
          >
            {isPending
              ? "Saving…"
              : diffRows.length > 0
                ? `Save ${diffRows.length} change${diffRows.length === 1 ? "" : "s"}`
                : "Save changes"}
          </Button>
        </div>
        {isError && (
          <p className="mt-2 text-xs text-[var(--color-danger)]" role="alert">
            Save failed — please try again.
          </p>
        )}
      </Card>
    </div>
  );
}

export default function AdminProductsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<"all" | "pending" | "verified">("all");
  const [linkFilter, setLinkFilter] = useState<"all" | "ok" | "redirect" | "quarantined">("all");
  const [editing, setEditing] = useState<AdminProduct | null>(null);
  const [editJson, setEditJson] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadResult, setUploadResult] = useState<string>("");

  const [sortLowConfidence, setSortLowConfidence] = useState(false);
  const [sortPrice, setSortPrice] = useState<"asc" | "desc" | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState<{ src: string; title: string } | null>(null);

  const query = filter === "all" ? "" : `&is_verified=${filter === "verified"}`;
  const linkQuery = linkFilter === "all" ? "" : `&link_status=${linkFilter}`;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-products", page, filter, linkFilter],
    queryFn: () => get<ProductList>(`/products?page=${page}&page_size=15${query}${linkQuery}`),
  });

  const items = useMemo(() => {
    const rows = data?.items ?? [];
    const sorted = [...rows];
    if (sortLowConfidence) {
      sorted.sort((a, b) => a.extraction_confidence - b.extraction_confidence);
    }
    if (sortPrice === "asc") {
      sorted.sort((a, b) => a.price_toman - b.price_toman);
    } else if (sortPrice === "desc") {
      sorted.sort((a, b) => b.price_toman - a.price_toman);
    }
    return sorted;
  }, [data, sortLowConfidence, sortPrice]);

  const verify = useMutation({
    mutationFn: (id: string) => post(`/products/${id}/verify`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-products"] }),
    onError: () => toast.error("Could not verify that product."),
  });

  /** Bulk verify: fire all PATCHes, then report how many actually landed. */
  const bulkVerify = useMutation({
    mutationFn: async (ids: string[]) => {
      const results = await Promise.allSettled(ids.map((id) => post(`/products/${id}/verify`)));
      return {
        ok: results.filter((r) => r.status === "fulfilled").length,
        failed: results.filter((r) => r.status === "rejected").length,
      };
    },
    onSuccess: ({ ok, failed }) => {
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["admin-products"] });
      if (failed === 0) toast.success(`Verified ${ok} product${ok === 1 ? "" : "s"}.`);
      else toast.error(`Verified ${ok}, but ${failed} failed.`);
    },
    onError: () => toast.error("Bulk verify failed."),
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
      toast.success("Product updated.");
    },
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return post<{ extraction: { confidence: number } }>("/products/upload", form);
    },
    onSuccess: (result) => {
      setUploadResult(
        `AI extraction complete (confidence ${(result.extraction.confidence * 100).toFixed(0)}%) — review & verify below.`,
      );
      qc.invalidateQueries({ queryKey: ["admin-products"] });
    },
    onError: () => toast.error("Upload or extraction failed."),
  });

  function openEdit(p: AdminProduct) {
    setEditing(p);
    setEditJson(JSON.stringify(editableOf(p), null, 2));
  }

  function toggleEditorStyle(styleId: string) {
    try {
      const parsed = JSON.parse(editJson) as Record<string, unknown>;
      const current = Array.isArray(parsed.styles) ? (parsed.styles as string[]) : [];
      parsed.styles = current.includes(styleId) ? current.filter((id) => id !== styleId) : [...current, styleId];
      setEditJson(JSON.stringify(parsed, null, 2));
    } catch {
      /* handled */
    }
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const selectableIds = items.filter((p) => !p.is_verified).map((p) => p.id);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => selected.has(id));

  const diffRows = useMemo(() => {
    if (!editing) return [];
    try {
      return diffObjects(editableOf(editing), JSON.parse(editJson));
    } catch {
      return [];
    }
  }, [editing, editJson]);

  const jsonValid = useMemo(() => {
    try {
      JSON.parse(editJson);
      return true;
    } catch {
      return false;
    }
  }, [editJson]);

  const editorStyles = useMemo(() => {
    try {
      const value = (JSON.parse(editJson) as { styles?: unknown }).styles;
      return Array.isArray(value) ? (value as string[]) : [];
    } catch {
      return [];
    }
  }, [editJson]);

  useCommands(
    [
      {
        id: "admin.upload",
        label: "Upload product image",
        group: "Admin",
        keywords: "add new product ai extract",
        run: () => fileRef.current?.click(),
      },
      {
        id: "admin.pending",
        label: "Show pending review",
        group: "Admin",
        run: () => {
          setFilter("pending");
          setPage(1);
        },
      },
      {
        id: "admin.verified",
        label: "Show verified",
        group: "Admin",
        run: () => {
          setFilter("verified");
          setPage(1);
        },
      },
      {
        id: "admin.all",
        label: "Show all products",
        group: "Admin",
        run: () => {
          setFilter("all");
          setPage(1);
        },
      },
      {
        id: "admin.sortconf",
        label: "Sort by lowest confidence",
        group: "Admin",
        keywords: "review triage",
        run: () => setSortLowConfidence(true),
      },
      {
        id: "admin.bulk",
        label: "Verify selected products",
        group: "Admin",
        run: () => selected.size && bulkVerify.mutate([...selected]),
      },
    ],
    [selected, bulkVerify],
  );

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="h1 text-[var(--color-ink)]">Products</h1>
        <div className="flex flex-wrap items-center gap-2">
          {(["all", "pending", "verified"] as const).map((f) => (
            <Button
              key={f}
              variant={filter === f ? "accent" : "ghost"}
              className="py-1.5 text-xs capitalize"
              aria-pressed={filter === f}
              onClick={() => {
                setFilter(f);
                setPage(1);
              }}
            >
              {f}
            </Button>
          ))}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            aria-label="Choose a product image to upload"
            onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])}
          />
          <Button variant="accent" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? "Extracting features…" : "Upload product image"}
          </Button>
        </div>
      </div>

      {/* Seller link filter row (IR-S2-001) */}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--color-line)] pt-3 text-xs">
        <span className="font-medium text-[var(--color-muted)]">وضعیت لینک فروشنده:</span>
        {[
          { id: "all", label: "همه لینک‌ها" },
          { id: "ok", label: "سالم (OK)" },
          { id: "redirect", label: "تغییر مسیر (Redirect)" },
          { id: "quarantined", label: "قرنطینه / نامعتبر (Quarantined)" },
        ].map((lf) => (
          <button
            key={lf.id}
            type="button"
            onClick={() => {
              setLinkFilter(lf.id as typeof linkFilter);
              setPage(1);
            }}
            className={`rounded-lg px-2.5 py-1 transition-colors ${
              linkFilter === lf.id
                ? "bg-[var(--color-ink)] text-[var(--color-canvas)] font-semibold"
                : "bg-[var(--color-line)]/50 text-[var(--color-muted)] hover:bg-[var(--color-line)]"
            }`}
          >
            {lf.label}
          </button>
        ))}
      </div>

      {uploadResult && (
        <p className="mt-3 rounded-xl bg-[var(--color-ok)]/8 px-3 py-2 text-sm text-[var(--color-ok)]">{uploadResult}</p>
      )}

      {selected.size > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--color-accent)]/20 bg-[var(--color-accent)]/5 px-4 py-2.5">
          <span className="text-sm font-medium text-[var(--color-ink)]">
            {selected.size} selected
          </span>
          <Button
            variant="accent"
            className="py-1.5 text-xs"
            onClick={() => bulkVerify.mutate([...selected])}
            disabled={bulkVerify.isPending}
          >
            {bulkVerify.isPending ? "Verifying…" : `Verify ${selected.size}`}
          </Button>
          <Button variant="ghost" className="py-1.5 text-xs" onClick={() => setSelected(new Set())}>
            Clear selection
          </Button>
        </div>
      )}

      {isLoading ? (
        <Card className="mt-6 space-y-px p-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 py-2.5">
              <Skeleton className="h-12 w-12 rounded-lg" />
              <Skeleton className="h-4 w-56" />
              <Skeleton className="ml-auto h-4 w-16" />
            </div>
          ))}
        </Card>
      ) : isError ? (
        <div className="mt-6">
          <ErrorState message="Could not load the product catalogue." onRetry={() => refetch()} />
        </div>
      ) : items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No products match the filter"
            hint={
              linkFilter !== "all"
                ? "No products with this seller link status."
                : filter === "pending"
                ? "All products verified! Upload new images to extract."
                : "Try changing the filter or upload new items."
            }
          />
        </div>
      ) : (
        <Card className="mt-6 overflow-x-auto p-0">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-[var(--color-line)] bg-[var(--color-canvas)] text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">
              <tr>
                <th className="w-8 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) =>
                      setSelected(e.target.checked ? new Set(selectableIds) : new Set())
                    }
                    disabled={selectableIds.length === 0}
                    aria-label="Select all unverified products"
                    className="h-4 w-4 accent-[var(--color-accent)]"
                  />
                </th>
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3">AI features</th>
                <th className="px-4 py-3">
                  <button
                    onClick={() => setSortLowConfidence((v) => !v)}
                    className="uppercase tracking-wide hover:text-[var(--color-ink)]"
                    title="Sort lowest confidence first to prioritize review"
                  >
                    Confidence {sortLowConfidence ? "↑" : "·"}
                  </button>
                </th>
                <th className="px-4 py-3">
                  <button
                    onClick={() => setSortPrice((s) => (s === "asc" ? "desc" : s === "desc" ? null : "asc"))}
                    className="uppercase tracking-wide hover:text-[var(--color-ink)]"
                    title="Sort by price"
                    aria-label="Sort by price"
                  >
                    Price {sortPrice === "asc" ? "↑" : sortPrice === "desc" ? "↓" : "·"}
                  </button>
                </th>
                <th className="px-4 py-3">Status / Seller Link</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const isQuarantined =
                  p.link_status === "dead" ||
                  p.link_status === "unsafe" ||
                  p.link_status === "blocked" ||
                  p.seller_link_ok === false;

                return (
                  <tr
                    key={p.id}
                    className={`border-b border-[var(--color-line)] align-top last:border-0 ${
                      selected.has(p.id) ? "bg-[var(--color-accent)]/5" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selected.has(p.id)}
                        onChange={() => toggleSelected(p.id)}
                        disabled={p.is_verified}
                        aria-label={`Select ${p.title}`}
                        className="h-4 w-4 accent-[var(--color-accent)]"
                      />
                    </td>
                    <td className="max-w-[240px] px-4 py-3">
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          className="shrink-0 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
                          onMouseEnter={() => setZoom({ src: p.image_url, title: p.title })}
                          onMouseLeave={() => setZoom(null)}
                          onFocus={() => setZoom({ src: p.image_url, title: p.title })}
                          onBlur={() => setZoom(null)}
                          onClick={() => setZoom({ src: p.image_url, title: p.title })}
                          aria-label={`Enlarge image of ${p.title}`}
                        >
                          <OptimizedImage
                            src={p.image_url}
                            alt=""
                            width={48}
                            height={48}
                            sizes="48px"
                            widths={[48, 96, 144]}
                            wrapperClassName="h-12 w-12 shrink-0 rounded-lg"
                          />
                        </button>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-[var(--color-ink)]">{p.title}</p>
                          <p className="text-xs text-[var(--color-muted)]">
                            {CATEGORY_LABELS[p.category] ?? p.category}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex max-w-[220px] flex-wrap gap-1">
                        {p.styles.map((s) => (
                          <Badge key={s} tone="clay">
                            {s}
                          </Badge>
                        ))}
                        {p.materials.map((m) => (
                          <Badge key={m}>{m}</Badge>
                        ))}
                        {p.colors.slice(0, 3).map((c) => (
                          <span
                            key={c}
                            className="h-5 w-5 rounded-full border border-[var(--color-line)]"
                            style={{ backgroundColor: c }}
                            title={c}
                          />
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          p.extraction_confidence >= 0.9
                            ? "rounded-full bg-[var(--color-ok)]/10 px-2 py-0.5 font-semibold text-[var(--color-ok)]"
                            : p.extraction_confidence >= 0.7
                              ? "rounded-full bg-[var(--color-warn)]/10 px-2 py-0.5 font-semibold text-[var(--color-warn)]"
                              : "rounded-full bg-[var(--color-danger)]/10 px-2 py-0.5 font-semibold text-[var(--color-danger)]"
                        }
                        title={p.extraction_confidence < 0.7 ? "Low confidence — review carefully" : undefined}
                      >
                        {(p.extraction_confidence * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">{formatToman(p.price_toman)}</td>
                    <td className="px-4 py-3">
                      <div className="space-y-1">
                        <div>
                          {p.is_verified ? (
                            <Badge tone="success">verified</Badge>
                          ) : (
                            <Badge tone="warning">pending review</Badge>
                          )}
                        </div>
                        {p.seller_link && (
                          <div className="flex items-center gap-1">
                            {isQuarantined ? (
                              <span
                                className="inline-flex items-center gap-1 rounded-md bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:bg-red-950/50 dark:text-red-400"
                                title="Quarantined: seller link is broken or unsafe"
                              >
                                🔴 قرنطینه
                              </span>
                            ) : p.link_status === "redirect" ? (
                              <span
                                className="inline-flex items-center gap-1 rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/50 dark:text-amber-400"
                                title="Redirected link"
                              >
                                ⚠️ ریدایرکت
                              </span>
                            ) : (
                              <span
                                className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400"
                                title="Link valid"
                              >
                                ✓ سالم
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1.5">
                        {!p.is_verified && (
                          <Button
                            variant="accent"
                            className="py-1 text-xs"
                            onClick={() => verify.mutate(p.id)}
                            disabled={verify.isPending}
                          >
                            Verify
                          </Button>
                        )}
                        <Button variant="ghost" className="py-1 text-xs" onClick={() => openEdit(p)}>
                          Edit
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      <div className="mt-4 flex items-center justify-between text-sm text-[var(--color-muted)]">
        <span>{data?.total ?? 0} products</span>
        <div className="flex gap-2">
          <Button variant="secondary" className="py-1.5 text-xs" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ← Prev
          </Button>
          <Button
            variant="secondary"
            className="py-1.5 text-xs"
            disabled={!data || page * data.page_size >= data.total}
            onClick={() => setPage(page + 1)}
          >
            Next →
          </Button>
        </div>
      </div>

      {editing && (
        <EditProductModal
          editing={editing}
          onClose={() => setEditing(null)}
          editJson={editJson}
          setEditJson={setEditJson}
          toggleEditorStyle={toggleEditorStyle}
          editorStyles={editorStyles}
          diffRows={diffRows}
          jsonValid={jsonValid}
          onSave={() => saveEdit.mutate()}
          isPending={saveEdit.isPending}
          isError={saveEdit.isError}
        />
      )}

      {zoom && (
        <div className="pointer-events-none fixed bottom-6 right-6 z-40 w-72 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface)] shadow-[var(--shadow-hover)]">
          <OptimizedImage
            src={zoom.src}
            alt={zoom.title}
            width={480}
            height={480}
            sizes="288px"
            widths={[288, 480, 640]}
            wrapperClassName="aspect-square w-full"
          />
          <p className="truncate px-3 py-2 text-xs font-medium text-[var(--color-ink)]">{zoom.title}</p>
        </div>
      )}
    </div>
  );
}
