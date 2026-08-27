/** Unit tests for the derived designer project status (Stage 1, T-1.3).
 *
 * getStatus/setStatus/markShared persist to localStorage under a single key;
 * the v2.1 limitation (per-browser status, no backend column) is documented
 * in src/lib/projectStatus.ts — these tests pin the CURRENT contract so the
 * migration cannot silently change semantics.
 */
import { beforeEach, describe, expect, it } from "vitest";
import {
  STATUS_META,
  avatarFor,
  getStatus,
  markShared,
  setStatus,
} from "@/lib/projectStatus";

const KEY = "sd_project_status";

beforeEach(() => {
  localStorage.clear();
});

describe("getStatus", () => {
  it("derives draft when there are no quizzes and no stored flag", () => {
    expect(getStatus("p1", 0)).toBe("draft");
  });

  it("derives shared when quizzes exist but the designer set no flag", () => {
    expect(getStatus("p2", 3)).toBe("shared");
  });

  it("prefers an explicit approved flag over derivation", () => {
    setStatus("p3", "approved");
    expect(getStatus("p3", 0)).toBe("approved");
  });

  it("prefers an explicit shared flag over draft derivation", () => {
    setStatus("p4", "shared");
    expect(getStatus("p4", 0)).toBe("shared");
  });

  it("isolates status per project id", () => {
    setStatus("a", "approved");
    expect(getStatus("a", 0)).toBe("approved");
    expect(getStatus("b", 0)).toBe("draft");
  });

  it("falls back to derivation when localStorage is unreadable (private mode)", () => {
    const original = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error("SecurityError");
    };
    try {
      expect(getStatus("p5", 2)).toBe("shared");
    } finally {
      Storage.prototype.getItem = original;
    }
  });
});

describe("markShared", () => {
  it("records shared for a project", () => {
    markShared("p6");
    expect(getStatus("p6", 0)).toBe("shared");
  });

  it("never downgrades an approved project back to shared", () => {
    setStatus("p7", "approved");
    markShared("p7");
    expect(getStatus("p7", 0)).toBe("approved");
  });

  it("upgrades shared -> approved is possible via setStatus", () => {
    markShared("p8");
    setStatus("p8", "approved");
    expect(getStatus("p8", 5)).toBe("approved");
  });
});

describe("avatarFor", () => {
  it("is deterministic: same name, same hue", () => {
    const a = avatarFor("Sara Ahmadi");
    const b = avatarFor("Sara Ahmadi");
    expect(a).toEqual(b);
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
});

describe("STATUS_META", () => {
  it("covers every status with RTL-friendly display meta", () => {
    for (const status of ["draft", "shared", "approved"] as const) {
      const meta = STATUS_META[status];
      expect(meta.label).toBeTruthy();
      expect(meta.dot).toBeTruthy();
      expect(meta.text).toBeTruthy();
      expect(meta.bg).toBeTruthy();
    }
  });
});

describe("storage shape", () => {
  it("persists a plain JSON map under the documented key", () => {
    markShared("p9");
    const raw = localStorage.getItem(KEY);
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw!)).toEqual({ p9: "shared" });
  });
});
