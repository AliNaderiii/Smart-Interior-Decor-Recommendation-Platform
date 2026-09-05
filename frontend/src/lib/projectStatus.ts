/** Project status metadata.
 *
 *  Status is now a real column on `projects` (migration 0005) and travels with
 *  the API payload. The previous implementation derived it from quiz counts
 *  and kept the designer-set part in localStorage — which meant it did not
 *  survive a change of browser and could not be seen by anyone else. The
 *  localStorage read/write helpers are gone; this module is presentation
 *  metadata only.
 */

export type ProjectStatus = "draft" | "shared" | "approved" | "completed";

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
  completed: {
    label: "Completed",
    dot: "bg-[var(--color-accent)]",
    text: "text-[var(--color-accent)]",
    bg: "bg-[var(--color-accent)]/10",
  },
};

/** Lifecycle order, used by the status switcher in the project header. */
export const STATUS_ORDER: ProjectStatus[] = ["draft", "shared", "approved", "completed"];

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
