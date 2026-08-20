/**
 * Cmd/Ctrl+K command palette — RESEARCH_V2 §6 (Linear).
 *
 * Design decisions worth stating:
 *  - **Stable ids.** Commands are keyed by id (`nav.recommendations`), not by
 *    label, so renaming a label never breaks a registration or a test.
 *  - **A command surface, not a search box.** It performs actions (create,
 *    toggle theme, verify) as well as navigating — that is what makes it worth
 *    a keystroke.
 *  - **Registry is dynamic.** Pages register contextual commands on mount via
 *    `useCommands()`, so the admin page can expose "Verify selected" without
 *    the palette importing admin code (which would defeat route splitting).
 *  - **Combobox a11y.** DOM focus stays in the input while a virtual highlight
 *    moves, per WAI-ARIA — screen readers announce the active option without
 *    focus thrash. `cmdk` implements this correctly.
 */
import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useThemeStore } from "@/stores/themeStore";

const PaletteOverlay = lazy(() => import("@/components/CommandPaletteOverlay"));
const ShortcutsDialog = lazy(() => import("@/components/ShortcutsDialog"));

export interface CommandItem {
  id: string;
  label: string;
  group: "Navigate" | "Create" | "Actions" | "Admin" | "Appearance";
  /** Extra search terms that should match this command. */
  keywords?: string;
  shortcut?: string;
  run: () => void;
}

interface PaletteApi {
  open: boolean;
  setOpen: (v: boolean) => void;
  register: (items: CommandItem[]) => () => void;
}

const PaletteContext = createContext<PaletteApi | null>(null);

export function useCommandPalette() {
  const ctx = useContext(PaletteContext);
  return ctx ?? { open: false, setOpen: () => {}, register: () => () => {} };
}

/** Register page-scoped commands for the lifetime of the calling component. */
export function useCommands(items: CommandItem[], deps: unknown[] = []) {
  const { register } = useCommandPalette();
  useEffect(() => {
    return register(items);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const [dynamic, setDynamic] = useState<CommandItem[]>([]);
  const navigate = useNavigate();
  const toggleTheme = useThemeStore((s) => s.toggle);
  const mode = useThemeStore((s) => s.mode);

  const register = useCallback((items: CommandItem[]) => {
    setDynamic((prev) => [...prev, ...items]);
    const ids = new Set(items.map((i) => i.id));
    return () => setDynamic((prev) => prev.filter((i) => !ids.has(i.id)));
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault(); // else Chrome opens its search bar
        setOpen((v) => !v);
        return;
      }
      // "?" opens help — but never while the user is typing into a field,
      // otherwise it hijacks a legitimate question mark.
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const t = e.target as HTMLElement | null;
        if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
        e.preventDefault();
        setHelp((v) => !v);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const base = useMemo<CommandItem[]>(
    () => [
      { id: "nav.home", label: "Go to Home", group: "Navigate", run: () => navigate("/") },
      { id: "nav.quiz", label: "Take the style quiz", group: "Navigate", keywords: "style questionnaire start", run: () => navigate("/quiz") },
      { id: "nav.recommendations", label: "Go to Recommendations", group: "Navigate", keywords: "products matches", run: () => navigate("/recommendations") },
      { id: "nav.moodboards", label: "Go to Moodboards", group: "Navigate", keywords: "boards collage", run: () => navigate("/moodboards") },
      { id: "nav.floorplan", label: "Go to Floorplan", group: "Navigate", keywords: "layout room plan", run: () => navigate("/floorplan") },
      { id: "nav.shopping", label: "Go to Shopping list", group: "Navigate", keywords: "cart basket buy", run: () => navigate("/shopping-list") },
      { id: "nav.upgrade", label: "Upgrade to Pro", group: "Navigate", keywords: "billing subscription pay", run: () => navigate("/upgrade") },
      { id: "help.shortcuts", label: "Keyboard shortcuts", group: "Appearance", keywords: "keys hotkeys help ?", shortcut: "?", run: () => setHelp(true) },
      {
        id: "theme.toggle",
        label: mode === "dark" ? "Switch to light mode" : "Switch to dark mode",
        group: "Appearance",
        keywords: "dark light theme contrast",
        run: toggleTheme,
      },
    ],
    [navigate, toggleTheme, mode],
  );

  const all = useMemo(() => {
    // Dynamic wins on id collision, so a page can override a base command.
    const map = new Map<string, CommandItem>();
    for (const c of [...base, ...dynamic]) map.set(c.id, c);
    return [...map.values()];
  }, [base, dynamic]);

  const groups = useMemo(() => {
    const order: CommandItem["group"][] = ["Create", "Actions", "Navigate", "Admin", "Appearance"];
    return order
      .map((g) => ({ group: g, items: all.filter((c) => c.group === g) }))
      .filter((g) => g.items.length > 0);
  }, [all]);

  const api = useMemo(() => ({ open, setOpen, register }), [open, register]);

  return (
    <PaletteContext.Provider value={api}>
      {children}
      {/* cmdk + the overlay chrome are ~28 KB gzip and are only needed once
          the user actually opens the palette, so they load on demand. Mounted
          only while open, which also means the dialog cannot trap focus or
          intercept keys when it is closed. */}
      <Suspense fallback={null}>{open && <PaletteOverlay groups={groups} onClose={() => setOpen(false)} />}</Suspense>
      <Suspense fallback={null}>{help && <ShortcutsDialog onClose={() => setHelp(false)} />}</Suspense>
    </PaletteContext.Provider>
  );
}
