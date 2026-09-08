/** ADR-016 helpers shared by the admin page and its tests. */

/** `catalog integrity failed [a,b,c]: …` → ["a", "b", "c"] (the 409 body of
 *  POST /products/{id}/verify and PATCH /products/{id} with is_verified). */
export function parseIntegrityCodes(message: string): string[] {
  const m = /\[([a-z_,]+)\]/i.exec(message ?? "");
  return m ? m[1].split(",").filter(Boolean) : [];
}

/** Whole days between an ISO timestamp and `now` (never negative, NaN → 0). */
export function daysSince(iso: string, now: number): number {
  const ms = now - new Date(iso).getTime();
  return Number.isFinite(ms) ? Math.max(0, Math.floor(ms / 86_400_000)) : 0;
}
