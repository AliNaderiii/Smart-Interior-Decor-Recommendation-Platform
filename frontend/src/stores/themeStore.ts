/** Dark-mode store — persisted, with OS default on first visit. */
import { create } from "zustand";
import { persist } from "zustand/middleware";

type Mode = "light" | "dark";

function systemPref(): Mode {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Applied to <html> so CSS custom properties re-resolve for the whole tree. */
export function applyMode(mode: Mode) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", mode === "dark");
  document.documentElement.style.colorScheme = mode;
}

interface ThemeState {
  mode: Mode;
  setMode: (m: Mode) => void;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: systemPref(),
      setMode: (mode) => {
        applyMode(mode);
        set({ mode });
      },
      toggle: () => get().setMode(get().mode === "dark" ? "light" : "dark"),
    }),
    {
      name: "sd_theme",
      // Re-apply on rehydrate: the persisted choice must win over the OS.
      onRehydrateStorage: () => (state) => {
        if (state) applyMode(state.mode);
      },
    },
  ),
);
