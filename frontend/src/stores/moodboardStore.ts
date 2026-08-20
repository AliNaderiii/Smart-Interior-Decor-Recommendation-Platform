import { create } from "zustand";
import type { RecommendedProduct } from "@/lib/types";

/** Client-side staging area: products picked on /recommendations before a
 *  moodboard is persisted. Server state lives in TanStack Query. */
interface MoodboardStage {
  picked: RecommendedProduct[];
  add: (p: RecommendedProduct) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const useMoodboardStore = create<MoodboardStage>()((set) => ({
  picked: [],
  add: (p) =>
    set((s) => (s.picked.some((x) => x.id === p.id) ? s : { picked: [...s.picked, p] })),
  remove: (id) => set((s) => ({ picked: s.picked.filter((x) => x.id !== id) })),
  clear: () => set({ picked: [] }),
}));
