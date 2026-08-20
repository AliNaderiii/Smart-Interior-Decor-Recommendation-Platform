/**
 * Motion constants — DESIGN_SYSTEM_V2 §4.
 *
 * Defined once so the house physics cannot drift between components.
 */
import type { Transition, Variants } from "framer-motion";

/** House spring: settles in ~250ms with no perceptible overshoot.
 *  Decorative bounce (low damping) is banned — this app arranges furniture,
 *  and wobbling furniture reads as broken. */
export const spring: Transition = { type: "spring", damping: 20, stiffness: 300 };

/** Springs are for space (position/scale). Colour and opacity use a tween. */
export const ease: Transition = { duration: 0.2, ease: "easeOut" };

/** Second-image crossfade — Article's 220ms. Instant reads as a glitch. */
export const crossfade: Transition = { duration: 0.22, ease: "easeOut" };

export const hoverLift = { y: -2 } as const;
export const tapPress = { scale: 0.98 } as const;

/** Page transition: fade + 20px rise. */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

/** Stagger helper for grids/lists. Capped so a 40-item grid does not take
 *  two seconds to finish arriving. */
export function staggerContainer(stagger = 0.04, max = 0.3): Variants {
  return {
    initial: {},
    animate: { transition: { staggerChildren: stagger, delayChildren: 0, staggerDirection: 1, when: "beforeChildren", duration: max } },
  };
}

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: spring },
};
