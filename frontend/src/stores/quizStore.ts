import { create } from "zustand";
import type { QuizAnswers } from "@/lib/types";
import { BUDGET_MAX, BUDGET_MIN } from "@/lib/constants";

interface QuizState extends QuizAnswers {
  step: number;
  setStep: (step: number) => void;
  toggleStyle: (id: string) => void;
  toggleColor: (hex: string) => void;
  toggleMaterial: (id: string) => void;
  setDimensions: (w: number, l: number) => void;
  setBudget: (min: number, max: number) => void;
  setClientMeta: (projectId: string | null, clientName: string) => void;
  /** ADR-015: replace styles/colours/materials/patterns with an AI suggestion
   *  (clamped to the same per-field limits the toggles enforce). Dimensions
   *  and budget are untouched — a photo cannot estimate them honestly. */
  applySuggestion: (s: QuizSuggestion) => void;
  reset: () => void;
}

export interface QuizSuggestion {
  styles: string[];
  color_palette: string[];
  materials: string[];
  patterns: string[];
}

export const SUGGESTION_LIMITS = { styles: 3, color_palette: 5, materials: 6, patterns: 3 } as const;

function clampUnique(list: string[], max: number): string[] {
  return Array.from(new Set(list)).slice(0, max);
}

const initial: QuizAnswers & { step: number } = {
  step: 0,
  styles: [],
  color_palette: [],
  room_width_cm: 400,
  room_length_cm: 500,
  budget_min_toman: BUDGET_MIN,
  budget_max_toman: Math.round(BUDGET_MAX / 3),
  materials: [],
  patterns: [],
  project_id: null,
  client_name: "",
};

function toggle(list: string[], id: string, max: number): string[] {
  if (list.includes(id)) return list.filter((x) => x !== id);
  if (list.length >= max) return list;
  return [...list, id];
}

export const useQuizStore = create<QuizState>()((set) => ({
  ...initial,
  setStep: (step) => set({ step }),
  toggleStyle: (id) => set((s) => ({ styles: toggle(s.styles, id, 3) })),
  toggleColor: (hex) => set((s) => ({ color_palette: toggle(s.color_palette, hex, 5) })),
  toggleMaterial: (id) => set((s) => ({ materials: toggle(s.materials, id, 6) })),
  setDimensions: (room_width_cm, room_length_cm) => set({ room_width_cm, room_length_cm }),
  setBudget: (budget_min_toman, budget_max_toman) => set({ budget_min_toman, budget_max_toman }),
  setClientMeta: (project_id, client_name) => set({ project_id, client_name }),
  applySuggestion: (sg) =>
    set({
      styles: clampUnique(sg.styles, SUGGESTION_LIMITS.styles),
      color_palette: clampUnique(sg.color_palette.map((c) => c.toUpperCase()), SUGGESTION_LIMITS.color_palette),
      materials: clampUnique(sg.materials, SUGGESTION_LIMITS.materials),
      patterns: clampUnique(sg.patterns, SUGGESTION_LIMITS.patterns),
    }),
  reset: () => set(initial),
}));
