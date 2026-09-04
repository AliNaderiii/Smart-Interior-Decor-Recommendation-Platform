import { useCallback, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { Moodboard } from "@/lib/types";
import { useQuizStore } from "@/stores/quizStore";
import { Button, Card, Input } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useCommands } from "@/components/CommandPalette";
import { useT } from "@/i18n";

/** 2D floorplan preview (MVP): SVG room at 1px = 1cm (scaled to fit),
 *  draggable product rectangles, fit warnings when furniture exceeds room. */

interface PlacedItem {
  id: string;
  label: string;
  w: number; // cm
  d: number; // cm
  x: number; // cm
  y: number; // cm
  color: string;
}

const PALETTE = ["#C1633F", "#4C6444", "#3B5B7A", "#8A8178", "#5D4037", "#C8A165"];

/** Minimum comfortable walkway, in cm.
 *
 *  RESEARCH_V2 §3 (Modsy): dimensional truth was the moat — a reviewer
 *  rejected an otherwise-loved design because it "didn't work measurement-
 *  wise". 76cm (30in) is the standard main-circulation clearance. Collision
 *  detection alone passes a layout where you physically cannot walk between
 *  two pieces, which is the failure this catches. */
const MIN_CLEARANCE_CM = 76;

/** Drawn wall thickness in cm (typical interior partition). */
const WALL_CM = 12;

/** Ruler gutter, in cm of SVG user space, reserved outside the room. */
const GUTTER = 46;

export default function FloorplanPage() {
  const t = useT();
  const quiz = useQuizStore();
  const [width, setWidth] = useState(quiz.room_width_cm);
  const [length, setLength] = useState(quiz.room_length_cm);
  const [items, setItems] = useState<PlacedItem[]>([]);
  const dragRef = useRef<{ id: string; offsetX: number; offsetY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const { data: boards } = useQuery({
    queryKey: ["moodboards"],
    queryFn: () => get<Moodboard[]>("/moodboards"),
  });
  const { data: board } = useQuery({
    queryKey: ["moodboard", boards?.[0]?.id],
    queryFn: () => get<Moodboard>(`/moodboards/${boards![0].id}`),
    enabled: Boolean(boards && boards.length > 0),
  });

  const available = useMemo(() => {
    if (!board?.products) return [];
    return Object.values(board.products).filter((p) => p.width_cm > 0 && p.depth_cm > 0);
  }, [board]);

  function addItem(productId: string) {
    const p = board?.products?.[productId];
    if (!p || items.some((i) => i.id === p.id)) return;
    setItems((prev) => [
      ...prev,
      {
        id: p.id,
        label: p.title.split("—")[0].trim(),
        w: p.width_cm,
        d: p.depth_cm,
        x: 20,
        y: 20,
        color: PALETTE[prev.length % PALETTE.length],
      },
    ]);
  }

  /** Screen -> room coordinates. The viewBox now includes a ruler gutter, so
   *  the scale factor must use the FULL viewBox extent and the gutter must be
   *  subtracted, otherwise every drag is offset by the ruler width. */
  function svgPoint(e: React.PointerEvent): { x: number; y: number } {
    const rect = svgRef.current!.getBoundingClientRect();
    const vbW = width + GUTTER;
    const vbH = length + GUTTER;
    return {
      x: (e.clientX - rect.left) / (rect.width / vbW) - GUTTER,
      y: (e.clientY - rect.top) / (rect.height / vbH) - GUTTER,
    };
  }

  function onPointerDown(e: React.PointerEvent, item: PlacedItem) {
    const pt = svgPoint(e);
    dragRef.current = { id: item.id, offsetX: pt.x - item.x, offsetY: pt.y - item.y };
    (e.target as Element).setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current;
    if (!drag) return;
    const pt = svgPoint(e);
    setItems((prev) =>
      prev.map((item) =>
        item.id === drag.id
          ? {
              ...item,
              x: Math.max(0, Math.min(width - item.w, pt.x - drag.offsetX)),
              y: Math.max(0, Math.min(length - item.d, pt.y - drag.offsetY)),
            }
          : item,
      ),
    );
  }

  const toast = useToast();
  const exportRef = useRef<HTMLDivElement>(null);
  const [exporting, setExporting] = useState(false);

  const overflows = items.filter((i) => i.w > width || i.d > length);
  const usedArea = items.reduce((s, i) => s + i.w * i.d, 0);
  const roomArea = width * length;

  /** AABB overlap check: flag pairs overlapping >50% of the smaller item. */
  const collisions = useMemo(() => {
    const pairs: [string, string][] = [];
    const colliding = new Set<string>();
    for (let a = 0; a < items.length; a++) {
      for (let b = a + 1; b < items.length; b++) {
        const A = items[a], B = items[b];
        const ox = Math.max(0, Math.min(A.x + A.w, B.x + B.w) - Math.max(A.x, B.x));
        const oy = Math.max(0, Math.min(A.y + A.d, B.y + B.d) - Math.max(A.y, B.y));
        const overlap = ox * oy;
        const smaller = Math.min(A.w * A.d, B.w * B.d);
        if (smaller > 0 && overlap / smaller > 0.5) {
          pairs.push([A.label, B.label]);
          colliding.add(A.id);
          colliding.add(B.id);
        }
      }
    }
    return { pairs, colliding };
  }, [items]);

  /** Gaps narrower than MIN_CLEARANCE_CM between facing edges of two items.
   *
   *  Only considers pairs that actually overlap on the perpendicular axis —
   *  two sofas at opposite corners of the room have a small x-gap but you are
   *  never walking between them, so flagging that would be noise. */
  const clearance = useMemo(() => {
    const zones: { x: number; y: number; w: number; h: number; gap: number; between: [string, string] }[] = [];
    for (let a = 0; a < items.length; a++) {
      for (let b = a + 1; b < items.length; b++) {
        const A = items[a], B = items[b];
        // Horizontal gap (walking left/right between them)
        const yOverlap = Math.min(A.y + A.d, B.y + B.d) - Math.max(A.y, B.y);
        if (yOverlap > 30) {
          const [L, R] = A.x <= B.x ? [A, B] : [B, A];
          const gap = R.x - (L.x + L.w);
          if (gap > 0 && gap < MIN_CLEARANCE_CM) {
            zones.push({
              x: L.x + L.w, y: Math.max(A.y, B.y), w: gap, h: yOverlap,
              gap: Math.round(gap), between: [L.label, R.label],
            });
          }
        }
        // Vertical gap (walking up/down between them)
        const xOverlap = Math.min(A.x + A.w, B.x + B.w) - Math.max(A.x, B.x);
        if (xOverlap > 30) {
          const [T, Bt] = A.y <= B.y ? [A, B] : [B, A];
          const gap = Bt.y - (T.y + T.d);
          if (gap > 0 && gap < MIN_CLEARANCE_CM) {
            zones.push({
              x: Math.max(A.x, B.x), y: T.y + T.d, w: xOverlap, h: gap,
              gap: Math.round(gap), between: [T.label, Bt.label],
            });
          }
        }
      }
    }
    return zones;
  }, [items]);

  /** PNG export via html2canvas — dynamically imported (~48 KB gzip) so it
   *  never touches the initial bundle for a button most users never press. */
  const exportPng = useCallback(async () => {
    if (!exportRef.current) return;
    setExporting(true);
    try {
      const html2canvas = (await import("html2canvas")).default;
      const canvas = await html2canvas(exportRef.current, {
        backgroundColor: "#FFFFFF",
        scale: 2, // retina-quality output
        logging: false,
      });
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = `floorplan-${width}x${length}cm.png`;
      a.click();
      toast.success("نقشه چیدمان به‌صورت تصویر ذخیره شد.");
    } catch {
      toast.error("Could not export the floorplan.");
    } finally {
      setExporting(false);
    }
  }, [width, length, toast]);

  useCommands(
    [
      { id: "fp.export", label: "Export floorplan as PNG", group: "Actions", keywords: "download image save", run: () => void exportPng() },
      { id: "fp.clear", label: "Clear all furniture", group: "Actions", run: () => setItems([]) },
    ],
    [exportPng],
  );

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h1 text-[var(--color-ink)]">{t.floorplan.title}</h1>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {t.floorplan.subtitle}
          </p>
        </div>
        <Button variant="accent" onClick={() => void exportPng()} disabled={exporting}>
          {exporting ? "در حال ذخیره…" : t.floorplan.exportPng}
        </Button>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_280px]">
        <Card className="p-4">
          <div ref={exportRef} className="rounded-xl bg-white p-2">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${width + GUTTER} ${length + GUTTER}`}
            width="100%"
            style={{ maxHeight: 600, aspectRatio: `${width + GUTTER} / ${length + GUTTER}` }}
            className="touch-none rounded-xl bg-white"
            onPointerMove={onPointerMove}
            onPointerUp={() => (dragRef.current = null)}
            role="application"
            aria-label={`Room floorplan ${width} by ${length} centimeters with ${items.length} items`}
          >
            {/* ---------- Rulers (top + left), Modsy's "measurement-wise" check ---------- */}
            <g fontSize={Math.max(11, width / 55)} fill="#9CA3AF" fontFamily="Inter Variable, sans-serif">
              {Array.from({ length: Math.floor(width / 50) + 1 }).map((_, i) => {
                const cm = i * 50;
                const major = cm % 100 === 0;
                return (
                  <g key={`rt${i}`}>
                    <line
                      x1={GUTTER + cm} y1={GUTTER - (major ? 12 : 7)}
                      x2={GUTTER + cm} y2={GUTTER}
                      stroke="#D1D5DB" strokeWidth={1}
                    />
                    {major && (
                      <text x={GUTTER + cm} y={GUTTER - 16} textAnchor="middle">{cm}</text>
                    )}
                  </g>
                );
              })}
              {Array.from({ length: Math.floor(length / 50) + 1 }).map((_, i) => {
                const cm = i * 50;
                const major = cm % 100 === 0;
                return (
                  <g key={`rl${i}`}>
                    <line
                      x1={GUTTER - (major ? 12 : 7)} y1={GUTTER + cm}
                      x2={GUTTER} y2={GUTTER + cm}
                      stroke="#D1D5DB" strokeWidth={1}
                    />
                    {major && (
                      <text x={GUTTER - 16} y={GUTTER + cm} textAnchor="end" dominantBaseline="middle">{cm}</text>
                    )}
                  </g>
                );
              })}
              <text x={GUTTER - 16} y={GUTTER - 16} textAnchor="end" dominantBaseline="middle" fontSize={Math.max(10, width / 70)}>cm</text>
            </g>

            <g transform={`translate(${GUTTER}, ${GUTTER})`}>
              {/* ---------- Walls with real thickness ---------- */}
              <rect
                x={-WALL_CM} y={-WALL_CM}
                width={width + WALL_CM * 2} height={length + WALL_CM * 2}
                fill="#374151"
              />
              <rect x={0} y={0} width={width} height={length} fill="#FAF8F5" />

              {/* 50cm minor / 100cm major grid */}
              {Array.from({ length: Math.floor(width / 50) }).map((_, i) => (
                <line key={`v${i}`} x1={(i + 1) * 50} y1={0} x2={(i + 1) * 50} y2={length}
                      stroke={(i + 1) % 2 === 0 ? "#E5E7EB" : "#F3F4F6"} strokeWidth={1} />
              ))}
              {Array.from({ length: Math.floor(length / 50) }).map((_, i) => (
                <line key={`h${i}`} x1={0} y1={(i + 1) * 50} x2={width} y2={(i + 1) * 50}
                      stroke={(i + 1) % 2 === 0 ? "#E5E7EB" : "#F3F4F6"} strokeWidth={1} />
              ))}

              {/* ---------- Door: 80cm leaf + swing arc, bottom wall ---------- */}
              <g>
                <rect x={width * 0.12} y={-WALL_CM} width={80} height={WALL_CM} fill="#FAF8F5" />
                <path
                  d={`M ${width * 0.12} 0 A 80 80 0 0 1 ${width * 0.12 + 80} 80`}
                  fill="none" stroke="#9CA3AF" strokeWidth={1.5} strokeDasharray="6 5"
                />
                <line x1={width * 0.12} y1={0} x2={width * 0.12} y2={80}
                      stroke="#6B7280" strokeWidth={2.5} />
                <text x={width * 0.12 + 40} y={-WALL_CM - 6} textAnchor="middle"
                      fontSize={Math.max(10, width / 70)} fill="#6B7280">door 80</text>
              </g>

              {/* ---------- Window: 140cm, right wall ---------- */}
              <g>
                <rect x={width} y={length * 0.3} width={WALL_CM} height={140} fill="#FAF8F5" />
                <line x1={width} y1={length * 0.3} x2={width} y2={length * 0.3 + 140}
                      stroke="#60A5FA" strokeWidth={3} />
                <line x1={width + WALL_CM} y1={length * 0.3} x2={width + WALL_CM} y2={length * 0.3 + 140}
                      stroke="#60A5FA" strokeWidth={3} />
                <text x={width + WALL_CM + 8} y={length * 0.3 + 70}
                      fontSize={Math.max(10, width / 70)} fill="#6B7280" dominantBaseline="middle">win 140</text>
              </g>

              {/* ---------- Clearance violations: red dashed corridor ---------- */}
              {clearance.map((z, i) => (
                <g key={`c${i}`}>
                  <rect x={z.x} y={z.y} width={z.w} height={z.h}
                        fill="#B91C1C" fillOpacity={0.12}
                        stroke="#B91C1C" strokeWidth={2} strokeDasharray="8 5" />
                  <text x={z.x + z.w / 2} y={z.y + z.h / 2} textAnchor="middle" dominantBaseline="middle"
                        fontSize={Math.max(12, width / 50)} fill="#B91C1C" fontWeight={700}
                        style={{ pointerEvents: "none" }}>
                    {z.gap}cm
                  </text>
                </g>
              ))}

              {/* ---------- Furniture ---------- */}
              {items.map((item) => {
                const bad = collisions.colliding.has(item.id);
                return (
                  <g key={item.id} onPointerDown={(e) => onPointerDown(e, item)} className="cursor-move">
                    <rect x={item.x} y={item.y} width={item.w} height={item.d}
                          fill={bad ? "#B91C1C" : item.color}
                          fillOpacity={0.82} rx={4}
                          stroke={bad ? "#7F1D1D" : "rgba(0,0,0,0.15)"}
                          strokeWidth={bad ? 3 : 1} />
                    <text x={item.x + item.w / 2} y={item.y + item.d / 2 - 7}
                          textAnchor="middle" dominantBaseline="middle"
                          fontSize={Math.max(12, width / 45)} fill="#fff" fontWeight={600}
                          style={{ pointerEvents: "none", userSelect: "none" }}>
                      {item.label.length > 14 ? item.label.slice(0, 14) + "…" : item.label}
                    </text>
                    {/* Real dimensions on the piece — the whole point of the tool. */}
                    <text x={item.x + item.w / 2} y={item.y + item.d / 2 + 9}
                          textAnchor="middle" dominantBaseline="middle"
                          fontSize={Math.max(10, width / 60)} fill="#fff" fillOpacity={0.85}
                          style={{ pointerEvents: "none", userSelect: "none" }}>
                      {item.w}×{item.d}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
          </div>
          <p className="mt-3 text-xs text-[var(--color-muted)]">
            {width}cm × {length}cm · footprint {(usedArea / 10000).toFixed(1)} m² of{" "}
            {(roomArea / 10000).toFixed(1)} m² ({Math.round((usedArea / roomArea) * 100)}%)
          </p>
          {overflows.length > 0 && (
            <p className="mt-2 rounded-xl bg-[var(--color-danger)]/8 px-3 py-2 text-sm text-[var(--color-danger)]" role="alert">
              {overflows.map((o) => o.label).join(", ")} do{overflows.length === 1 ? "es" : ""} not fit this room.
            </p>
          )}
          {collisions.pairs.length > 0 && (
            <p className="mt-2 rounded-xl bg-[var(--color-danger)]/8 px-3 py-2 text-sm text-[var(--color-danger)]" role="alert">
              Overlapping: {collisions.pairs.map(([a, b]) => `${a} × ${b}`).join(", ")} — move them apart.
            </p>
          )}
          {clearance.length > 0 && (
            <p className="mt-2 rounded-xl bg-[var(--color-warn)]/8 px-3 py-2 text-sm text-[var(--color-warn)]" role="alert">
              Tight walkway: {clearance.map((z) => `${z.between[0]} ↔ ${z.between[1]} (${z.gap}cm)`).join(", ")}.
              Aim for at least {MIN_CLEARANCE_CM}cm to walk through comfortably.
            </p>
          )}
          {items.length > 0 && clearance.length === 0 && collisions.pairs.length === 0 && overflows.length === 0 && (
            <p className="mt-2 rounded-xl bg-[var(--color-ok)]/8 px-3 py-2 text-sm text-[var(--color-ok)]">
              Everything fits with comfortable {MIN_CLEARANCE_CM}cm walkways.
            </p>
          )}
        </Card>

        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="text-sm font-semibold text-[var(--color-ink)]">{t.floorplan.roomDimensions}</h2>
            <div className="mt-3 space-y-3">
              <div>
                <label htmlFor="fp-w" className="mb-1 block text-xs text-[var(--color-muted)]">{t.floorplan.width}</label>
                <Input id="fp-w" type="number" min={100} max={3000} value={width}
                       onChange={(e) => setWidth(Math.max(100, Number(e.target.value)))} />
              </div>
              <div>
                <label htmlFor="fp-l" className="mb-1 block text-xs text-[var(--color-muted)]">{t.floorplan.length}</label>
                <Input id="fp-l" type="number" min={100} max={3000} value={length}
                       onChange={(e) => setLength(Math.max(100, Number(e.target.value)))} />
              </div>
            </div>
          </Card>

          <Card className="p-4">
            <h2 className="text-sm font-semibold text-[var(--color-ink)]">{t.floorplan.addFromMoodboard}</h2>
            {available.length === 0 ? (
              <p className="mt-2 text-xs text-[var(--color-muted)]">{t.floorplan.addFromMoodboardHint}</p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {available.map((p) => (
                  <li key={p.id}>
                    <Button variant="ghost" className="w-full justify-between text-xs"
                            onClick={() => addItem(p.id)}
                            disabled={items.some((i) => i.id === p.id)}>
                      <span className="truncate">{p.title.split("—")[0]}</span>
                      <span className="text-[var(--color-muted)]">{p.width_cm}×{p.depth_cm}cm</span>
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
