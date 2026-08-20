/**
 * Confetti on genuine milestones only — quiz completion and first share.
 *
 * Two constraints that matter more than the effect itself:
 *  1. `canvas-confetti` is ~7 KB gzip and is needed at most once per session,
 *     so it is dynamically imported at the moment of celebration. It must
 *     never sit in the initial bundle.
 *  2. Honour `prefers-reduced-motion`. A burst of moving particles is exactly
 *     the kind of vestibular trigger that setting exists to prevent, so we
 *     silently skip it rather than degrade it.
 */
export async function celebrate() {
  if (typeof window === "undefined") return;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

  try {
    const confetti = (await import("canvas-confetti")).default;
    // Warm neutrals from the design system, not primary-colour party colours.
    const colors = ["#C1633F", "#5D4037", "#4C6444", "#D4AF37", "#F2E8D5"];
    const base = { spread: 70, startVelocity: 34, ticks: 160, zIndex: 300, colors, disableForReducedMotion: true };
    confetti({ ...base, particleCount: 55, origin: { x: 0.2, y: 0.7 } });
    confetti({ ...base, particleCount: 55, origin: { x: 0.8, y: 0.7 } });
  } catch {
    // Never let a decorative effect break a real flow.
  }
}
