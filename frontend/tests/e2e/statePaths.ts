/**
 * The one place that decides where role storageState files live.
 *
 * WHY THIS MODULE EXISTS (CI run 32988827678, auth-smoke ENOENT):
 * globalSetup wrote its state with `path.join(config.rootDir, ...)`, but
 * `config.rootDir` is the *testDir* (`frontend/tests/e2e`), while a relative
 * `storageState` in a project's `use` block is resolved by the Playwright
 * client against `process.cwd()` (`frontend/`). So setup wrote
 *   frontend/tests/e2e/test-results/state/homeowner.json
 * and the project read
 *   frontend/test-results/state/homeowner.json
 * -> ENOENT.
 *
 * Both sides now import the SAME absolute path from here, so the writer and
 * the reader cannot drift apart again regardless of the cwd the suite is
 * launched from (CI runs it from `frontend/`, a developer may not).
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

/** `frontend/` — this file is at `frontend/tests/e2e/statePaths.ts`. */
const FRONTEND_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Directory holding the per-role storageState files. */
export const STATE_DIR = path.join(FRONTEND_DIR, "test-results", "state");

export type Role = "homeowner" | "designer" | "admin";

/** Absolute path to one role's storageState file. */
export function statePath(role: Role): string {
  return path.join(STATE_DIR, `${role}.json`);
}
