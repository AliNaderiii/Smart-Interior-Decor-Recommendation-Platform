/** Unit tests for designer project status presentation.
 *
 * Phase A moved status onto the server (`projects.status`, migration 0005).
 * The old getStatus/setStatus/markShared helpers wrote to localStorage and are
 * gone, so the tests that pinned that contract are gone with them — a test
 * that asserts a deleted behaviour is worse than no test, because it fails CI
 * for a change that was deliberate.
 *
 * What remains worth pinning: the display metadata must cover every status the
 * API can return, and the avatar helper must stay deterministic.
 */
import { describe, expect, it } from "vitest";
import { STATUS_META, STATUS_ORDER, avatarFor, type ProjectStatus } from "@/lib/projectStatus";

describe("STATUS_META", () => {
  it("covers every status the backend can send", () => {
    // Mirrors the CHECK-equivalent pattern in ProjectStatusIn on the server.
    const fromApi: ProjectStatus[] = ["draft", "shared", "approved", "completed"];
    for (const status of fromApi) {
      const meta = STATUS_META[status];
      expect(meta, `missing meta for "${status}"`).toBeDefined();
      expect(meta.label).toBeTruthy();
      expect(meta.dot).toBeTruthy();
      expect(meta.text).toBeTruthy();
      expect(meta.bg).toBeTruthy();
    }
  });

  it("STATUS_ORDER lists each status exactly once, in lifecycle order", () => {
    expect(STATUS_ORDER).toEqual(["draft", "shared", "approved", "completed"]);
    expect(new Set(STATUS_ORDER).size).toBe(STATUS_ORDER.length);
  });

  it("every ordered status has display metadata", () => {
    for (const status of STATUS_ORDER) {
      expect(STATUS_META[status]).toBeDefined();
    }
  });
});

describe("avatarFor", () => {
  it("is deterministic: same name, same hue", () => {
    expect(avatarFor("Sara Ahmadi")).toEqual(avatarFor("Sara Ahmadi"));
  });

  it("builds initials from the first two words", () => {
    expect(avatarFor("Sara Ahmadi").initials).toBe("SA");
  });

  it("handles single-word and empty names without crashing", () => {
    expect(avatarFor("Sara").initials).toBe("S");
    expect(avatarFor("   ").initials).toBe("?");
    expect(avatarFor("   ").hue).toBe(220);
  });

  it("keeps hue in [0, 360)", () => {
    for (const name of ["Sara", "مهدی رضایی", "X Y Z W"]) {
      const { hue } = avatarFor(name);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    }
  });

  it("works with Persian names", () => {
    const { initials } = avatarFor("مهدی رضایی");
    expect(initials.length).toBeGreaterThan(0);
  });
});
