import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { Moodboard } from "@/lib/types";
import { useQuizStore } from "@/stores/quizStore";
import { Button, Card, Input } from "@/components/ui";

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

export default function FloorplanPage() {
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

  function svgPoint(e: React.PointerEvent): { x: number; y: number } {
    const rect = svgRef.current!.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) / (rect.width / width),
      y: (e.clientY - rect.top) / (rect.height / length),
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

  const overflows = items.filter((i) => i.w > width || i.d > length);
  const usedArea = items.reduce((s, i) => s + i.w * i.d, 0);
  const roomArea = width * length;

  return (
    <div>
      <h1 className="text-2xl font-bold text-walnut">2D Floorplan preview</h1>
      <p className="mt-1 text-sm text-stone">Scale 1px = 1cm (fitted). Drag furniture to arrange your room.</p>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_280px]">
        <Card className="p-4">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${width} ${length}`}
            width="100%"
            style={{ maxHeight: 560, aspectRatio: `${width} / ${length}` }}
            className="rounded-xl bg-[#f7f3ec] touch-none"
            onPointerMove={onPointerMove}
            onPointerUp={() => (dragRef.current = null)}
            role="application"
            aria-label={`Room floorplan ${width} by ${length} centimeters`}
          >
            <rect x={0} y={0} width={width} height={length} fill="none" stroke="#5D4037" strokeWidth={Math.max(2, width / 200)} />
            {/* grid every 100 cm */}
            {Array.from({ length: Math.floor(width / 100) }).map((_, i) => (
              <line key={`v${i}`} x1={(i + 1) * 100} y1={0} x2={(i + 1) * 100} y2={length} stroke="#e5ded3" strokeWidth={1} />
            ))}
            {Array.from({ length: Math.floor(length / 100) }).map((_, i) => (
              <line key={`h${i}`} x1={0} y1={(i + 1) * 100} x2={width} y2={(i + 1) * 100} stroke="#e5ded3" strokeWidth={1} />
            ))}
            {items.map((item) => (
              <g key={item.id} onPointerDown={(e) => onPointerDown(e, item)} className="cursor-move">
                <rect x={item.x} y={item.y} width={item.w} height={item.d}
                      fill={item.color} fillOpacity={0.75} rx={6} />
                <text x={item.x + item.w / 2} y={item.y + item.d / 2}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={Math.max(12, width / 40)} fill="#fff" fontWeight={600}
                      style={{ pointerEvents: "none", userSelect: "none" }}>
                  {item.label.length > 14 ? item.label.slice(0, 14) + "…" : item.label}
                </text>
              </g>
            ))}
          </svg>
          <p className="mt-2 text-xs text-stone">
            {width}cm × {length}cm · furniture footprint {(usedArea / 10000).toFixed(1)} m² of {(roomArea / 10000).toFixed(1)} m² ({Math.round((usedArea / roomArea) * 100)}%)
          </p>
          {overflows.length > 0 && (
            <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
              ⚠ {overflows.map((o) => o.label).join(", ")} do{overflows.length === 1 ? "es" : ""} not fit this room.
            </p>
          )}
        </Card>

        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="text-sm font-semibold text-walnut">Room dimensions</h2>
            <div className="mt-3 space-y-3">
              <div>
                <label htmlFor="fp-w" className="mb-1 block text-xs text-stone">Width (cm)</label>
                <Input id="fp-w" type="number" min={100} max={3000} value={width}
                       onChange={(e) => setWidth(Math.max(100, Number(e.target.value)))} />
              </div>
              <div>
                <label htmlFor="fp-l" className="mb-1 block text-xs text-stone">Length (cm)</label>
                <Input id="fp-l" type="number" min={100} max={3000} value={length}
                       onChange={(e) => setLength(Math.max(100, Number(e.target.value)))} />
              </div>
            </div>
          </Card>

          <Card className="p-4">
            <h2 className="text-sm font-semibold text-walnut">Add from your moodboard</h2>
            {available.length === 0 ? (
              <p className="mt-2 text-xs text-stone">Create a moodboard first — its products appear here with real dimensions.</p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {available.map((p) => (
                  <li key={p.id}>
                    <Button variant="ghost" className="w-full justify-between text-xs"
                            onClick={() => addItem(p.id)}
                            disabled={items.some((i) => i.id === p.id)}>
                      <span className="truncate">{p.title.split("—")[0]}</span>
                      <span className="text-stone">{p.width_cm}×{p.depth_cm}cm</span>
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
