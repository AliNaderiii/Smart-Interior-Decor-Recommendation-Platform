/** Project status: Draft → Shared → Approved.
 *
 *  HONESTY NOTE: the v1.1 `projects` table has no status column, and inventing
 *  a backend migration for a Phase 3 UI task would put schema churn on the
 *  critical path. So status is DERIVED from facts we actually have, plus one
 *  explicitly designer-set bit:
 *
 *    Draft    — no quizzes run yet (nothing exists to show a client)
 *    Shared   — a share link has been generated for one of its quizzes
 *    Approved — the designer marked it approved
 *
 *  "Shared" and "Approved" are recorded client-side (localStorage). That is a
 *  real limitation: it is per-browser and does not sync across devices. It is
 *  recorded in docs/DESIGN_SYSTEM_V2.md as the v2.1 migration candidate
 *  (`projects.status` enum + `projects.shared_at`).
 */

export type ProjectStatus = "draft" | "shared" | "approved";

const KEY = "sd_project_status";

type Store = Record<string, "shared" | "approved">;

function read(): Store {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Store;
  } catch {
    return {};
  }
}

function write(store: Store) {
  try {
    localStorage.setItem(KEY, JSON.stringify(store));
  } catch {
    /* private mode — status simply falls back to derived-from-quizzes */
  }
}

export function getStatus(projectId: string, quizCount: number): ProjectStatus {
  const flag = read()[projectId];
  if (flag) return flag;
  return quizCount > 0 ? "shared" : "draft";
}

export function setStatus(projectId: string, status: "shared" | "approved") {
  const store = read();
  store[projectId] = status;
  write(store);
}

export function markShared(projectId: string) {
  const store = read();
  // Never downgrade an approved project back to shared.
  if (store[projectId] === "approved") return;
  store[projectId] = "shared";
  write(store);
}

export const STATUS_META: Record<ProjectStatus, { label: string; dot: string; text: string; bg: string }> = {
  draft: {
    label: "Draft",
    dot: "bg-[var(--color-faint)]",
    text: "text-[var(--color-muted)]",
    bg: "bg-[var(--color-line)]",
  },
  shared: {
    label: "Shared",
    dot: "bg-[#3B82F6]",
    text: "text-[#1D4ED8]",
    bg: "bg-[#3B82F6]/10",
  },
  approved: {
    label: "Approved",
    dot: "bg-[var(--color-ok)]",
    text: "text-[var(--color-ok)]",
    bg: "bg-[var(--color-ok)]/10",
  },
};

/** Deterministic initials + hue for a client avatar. Same name always yields
 *  the same colour, so the list is scannable by colour alone. */
export function avatarFor(name: string): { initials: string; hue: number } {
  const clean = name.trim();
  if (!clean) return { initials: "?", hue: 220 };
  const parts = clean.split(/\s+/);
  const initials = (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
  let hash = 0;
  for (let i = 0; i < clean.length; i++) hash = (hash * 31 + clean.charCodeAt(i)) % 360;
  return { initials, hue: hash };
}
