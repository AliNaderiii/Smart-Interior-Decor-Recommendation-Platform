/** Unit tests for the style-quiz store (Stage 1, T-1.3).
 *
 * Pins the flow contract the recommendations API depends on: max selections
 * per choice group, the default budget window, and reset-to-initial between
 * quiz runs (a stale project_id/client_name leaking into a new quiz is a
 * B2B2C tenancy bug, so reset() is asserted field by field).
 */
import { beforeEach, describe, expect, it } from "vitest";
import { BUDGET_MAX, BUDGET_MIN } from "@/lib/constants";
import { useQuizStore } from "@/stores/quizStore";

const initialState = () => useQuizStore.getState();

beforeEach(() => {
  useQuizStore.getState().reset();
});

describe("selection caps", () => {
  it("allows up to 3 styles and refuses a 4th", () => {
    const s = useQuizStore.getState();
    s.toggleStyle("modern");
    s.toggleStyle("scandinavian");
    s.toggleStyle("industrial");
    s.toggleStyle("boho"); // over the cap
    expect(useQuizStore.getState().styles).toEqual([
      "modern",
      "scandinavian",
      "industrial",
    ]);
  });

  it("allows up to 5 colors and refuses a 6th", () => {
    const s = useQuizStore.getState();
    for (const hex of ["#111111", "#222222", "#333333", "#444444", "#555555", "#666666"]) {
      s.toggleColor(hex);
    }
    expect(useQuizStore.getState().color_palette).toEqual([
      "#111111", "#222222", "#333333", "#444444", "#555555",
    ]);
  });

  it("allows up to 6 materials and refuses a 7th", () => {
    const s = useQuizStore.getState();
    for (const m of ["wood", "metal", "glass", "leather", "rattan", "fabric", "linen"]) {
      s.toggleMaterial(m);
    }
    expect(useQuizStore.getState().materials).toEqual([
      "wood", "metal", "glass", "leather", "rattan", "fabric",
    ]);
  });

  it("toggling an existing value removes it (and frees a slot)", () => {
    const s = useQuizStore.getState();
    s.toggleStyle("modern");
    s.toggleStyle("modern");
    expect(useQuizStore.getState().styles).toEqual([]);
    s.toggleStyle("modern");
    s.toggleStyle("scandinavian");
    s.toggleStyle("industrial");
    s.toggleStyle("modern"); // removes, no cap fight
    expect(useQuizStore.getState().styles).toEqual(["scandinavian", "industrial"]);
    s.toggleStyle("boho"); // slot freed -> allowed again
    expect(useQuizStore.getState().styles).toEqual(["scandinavian", "industrial", "boho"]);
  });
});

describe("defaults", () => {
  it("starts on step 0 with empty selections and the documented budget window", () => {
    const s = initialState();
    expect(s.step).toBe(0);
    expect(s.styles).toEqual([]);
    expect(s.color_palette).toEqual([]);
    expect(s.materials).toEqual([]);
    expect(s.patterns).toEqual([]);
    expect(s.budget_min_toman).toBe(BUDGET_MIN);
    expect(s.budget_max_toman).toBe(Math.round(BUDGET_MAX / 3));
    expect(s.project_id).toBeNull();
    expect(s.client_name).toBe("");
  });
});

describe("setters", () => {
  it("setStep moves the wizard", () => {
    useQuizStore.getState().setStep(2);
    expect(useQuizStore.getState().step).toBe(2);
  });

  it("setDimensions stores width/length", () => {
    useQuizStore.getState().setDimensions(350, 480);
    const s = useQuizStore.getState();
    expect(s.room_width_cm).toBe(350);
    expect(s.room_length_cm).toBe(480);
  });

  it("setBudget replaces the window", () => {
    useQuizStore.getState().setBudget(5_000_000, 80_000_000);
    const s = useQuizStore.getState();
    expect(s.budget_min_toman).toBe(5_000_000);
    expect(s.budget_max_toman).toBe(80_000_000);
  });

  it("setClientMeta carries the designer context into the quiz", () => {
    useQuizStore.getState().setClientMeta("proj-1", "آقای رضایی");
    const s = useQuizStore.getState();
    expect(s.project_id).toBe("proj-1");
    expect(s.client_name).toBe("آقای رضایی");
  });
});

describe("reset", () => {
  it("wipes EVERY field — including designer tenancy bits — back to initial", () => {
    const s = useQuizStore.getState();
    s.toggleStyle("modern");
    s.toggleColor("#123456");
    s.setStep(3);
    s.setBudget(1, 2);
    s.setClientMeta("proj-9", "client-should-not-leak");

    useQuizStore.getState().reset();

    const after = useQuizStore.getState();
    expect(after.step).toBe(0);
    expect(after.styles).toEqual([]);
    expect(after.color_palette).toEqual([]);
    expect(after.materials).toEqual([]);
    expect(after.patterns).toEqual([]);
    expect(after.budget_min_toman).toBe(BUDGET_MIN);
    expect(after.budget_max_toman).toBe(Math.round(BUDGET_MAX / 3));
    expect(after.project_id).toBeNull();
    expect(after.client_name).toBe("");
  });
});
