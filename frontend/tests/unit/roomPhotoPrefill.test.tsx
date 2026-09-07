/**
 * ADR-015 — RoomPhotoPrefill + quizStore.applySuggestion.
 * The card must (1) refuse non-images / oversize files before any network
 * call, (2) post the photo as multipart to /quiz/analyze-room, (3) apply the
 * server's suggestion to the quiz store exactly once and within the store's
 * limits, (4) render copy that matches the server's confidence tier — and
 * never show a confidence figure for a heuristic (mock) provider.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderWithProviders } from "./renderWithProviders";
import type { RoomAnalysisResult } from "@/lib/types";

const postMock = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, post: (...args: unknown[]) => postMock(...args) };
});

import { RoomPhotoPrefill } from "@/components/RoomPhotoPrefill";
import { SUGGESTION_LIMITS, useQuizStore } from "@/stores/quizStore";

const CONFIDENT: RoomAnalysisResult = {
  suggestion: {
    styles: ["boho", "scandinavian"],
    materials: ["rattan", "wood"],
    color_palette: ["#F2E8D5", "#4C6444", "#D9A05B"],
    patterns: ["geometric"],
  },
  labels: {
    styles: [
      { id: "boho", fa: "بوهو / بوهمی", en: "Bohemian" },
      { id: "scandinavian", fa: "اسکاندیناوی", en: "Scandinavian" },
    ],
    materials: [
      { id: "rattan", fa: "حصیر", en: "Rattan" },
      { id: "wood", fa: "چوب", en: "Wood" },
    ],
  },
  confidence_tier: "confident",
  confidence: 0.91,
  palette: ["#F2E8D5", "#4C6444", "#D9A05B"],
  description: "a bright bohemian living room",
  review_reasons: [],
  meta: {
    provider: "gemini",
    model: "gemini-3.5-flash",
    prompt_version: "r1",
    taxonomy_version: "2.1",
    heuristic: false,
    dimensions_estimated: false,
    unknown_taxonomy_values: [],
  },
};

const PALETTE_ONLY: RoomAnalysisResult = {
  ...CONFIDENT,
  suggestion: { styles: [], materials: [], color_palette: ["#F2E8D5", "#4C6444"], patterns: [] },
  labels: { styles: [], materials: [] },
  confidence_tier: "palette_only",
  confidence: 0.9, // the mock's fake confidence must NOT be displayed
  meta: { ...CONFIDENT.meta, provider: "mock", model: "filename-heuristic", heuristic: true },
};

function render(locale: "en" | "fa" = "en") {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <RoomPhotoPrefill />
    </QueryClientProvider>,
    { locale },
  );
}

function jpeg(name = "room.jpg", size = 2048): File {
  return new File([new Uint8Array(size)], name, { type: "image/jpeg" });
}

beforeEach(() => {
  postMock.mockReset();
  useQuizStore.getState().reset();
  (globalThis.URL as unknown as { createObjectURL: () => string }).createObjectURL = () => "blob:preview";
  (globalThis.URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
});

describe("RoomPhotoPrefill — ADR-015", () => {
  it("rejects a non-image locally without calling the API", async () => {
    render();
    const input = screen.getByTestId("room-photo-input") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "notes.txt", { type: "text/plain" }), { applyAccept: false });
    expect((await screen.findByRole("alert")).textContent).toMatch(/not an image/i);
    expect(postMock).not.toHaveBeenCalled();
  });

  it("rejects an oversize photo locally", async () => {
    render();
    await userEvent.upload(screen.getByTestId("room-photo-input"), jpeg("huge.jpg", 8 * 1024 * 1024 + 1));
    expect((await screen.findByRole("alert")).textContent).toMatch(/larger than 8 MB/i);
    expect(postMock).not.toHaveBeenCalled();
  });

  it("posts multipart to /quiz/analyze-room and applies a confident suggestion to the store", async () => {
    postMock.mockResolvedValueOnce(CONFIDENT);
    render();
    await userEvent.upload(screen.getByTestId("room-photo-input"), jpeg());

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    const [url, body] = postMock.mock.calls[0] as [string, FormData];
    expect(url).toBe("/quiz/analyze-room");
    expect(body).toBeInstanceOf(FormData);
    expect((body.get("file") as File).name).toBe("room.jpg");

    await screen.findByTestId("room-photo-result");
    const state = useQuizStore.getState();
    expect(state.styles).toEqual(["boho", "scandinavian"]);
    expect(state.materials).toEqual(["rattan", "wood"]);
    expect(state.color_palette).toEqual(["#F2E8D5", "#4C6444", "#D9A05B"]);
    expect(state.patterns).toEqual(["geometric"]);
    // dimensions/budget untouched
    expect(state.room_width_cm).toBe(400);
    expect(state.room_length_cm).toBe(500);

    expect(screen.getByTestId("room-photo-prefill").getAttribute("data-tier")).toBe("confident");
    expect(screen.getByTestId("room-photo-styles").textContent).toBe("Bohemian, Scandinavian");
    expect(screen.getByTestId("room-photo-materials").textContent).toBe("Rattan, Wood");
    expect(screen.getByTestId("room-photo-confidence").textContent).toMatch(/91% confidence/);
    expect(screen.queryByTestId("room-photo-heuristic")).toBeNull();
    expect(screen.getByTestId("room-photo-preview").getAttribute("src")).toBe("blob:preview");
  });

  it("palette_only: applies only colours, shows the demo badge and no confidence figure", async () => {
    postMock.mockResolvedValueOnce(PALETTE_ONLY);
    render();
    await userEvent.upload(screen.getByTestId("room-photo-input"), jpeg());
    await screen.findByTestId("room-photo-result");

    const state = useQuizStore.getState();
    expect(state.styles).toEqual([]);
    expect(state.materials).toEqual([]);
    expect(state.color_palette).toEqual(["#F2E8D5", "#4C6444"]);

    expect(screen.getByTestId("room-photo-prefill").getAttribute("data-tier")).toBe("palette_only");
    expect(screen.getByTestId("room-photo-heuristic").textContent).toMatch(/demo mode/i);
    expect(screen.queryByTestId("room-photo-confidence")).toBeNull();
    expect(screen.getByTestId("room-photo-styles").textContent).toBe("—");
    expect(screen.getByTestId("room-photo-result").textContent).toMatch(/only the photo's dominant colours/i);
  });

  it("renders Persian labels from the server's label pairs", async () => {
    postMock.mockResolvedValueOnce(CONFIDENT);
    render("fa");
    await userEvent.upload(screen.getByTestId("room-photo-input"), jpeg());
    await screen.findByTestId("room-photo-result");
    expect(screen.getByTestId("room-photo-styles").textContent).toBe("بوهو / بوهمی، اسکاندیناوی");
    expect(screen.getByTestId("room-photo-materials").textContent).toBe("حصیر، چوب");
  });

  it("surfaces a 429 as the rate-limit message and leaves the store untouched", async () => {
    const { ApiError } = await import("@/lib/api");
    postMock.mockRejectedValueOnce(new ApiError(429, "Too many"));
    render();
    await userEvent.upload(screen.getByTestId("room-photo-input"), jpeg());
    expect((await screen.findByRole("alert")).textContent).toMatch(/too many analyses/i);
    expect(useQuizStore.getState().styles).toEqual([]);
  });
});

describe("quizStore.applySuggestion", () => {
  it("clamps to the same limits as the toggles and normalises hex case", () => {
    useQuizStore.getState().applySuggestion({
      styles: ["modern", "minimal", "classic", "boho"],
      color_palette: ["#abcdef", "#ABCDEF", "#111111", "#222222", "#333333", "#444444", "#555555"],
      materials: ["wood", "metal", "fabric", "leather", "rattan", "glass", "wood"],
      patterns: ["solid", "floral", "geometric", "striped"],
    });
    const s = useQuizStore.getState();
    expect(s.styles).toHaveLength(SUGGESTION_LIMITS.styles);
    expect(s.color_palette).toEqual(["#ABCDEF", "#111111", "#222222", "#333333", "#444444"]);
    expect(s.materials).toHaveLength(SUGGESTION_LIMITS.materials);
    expect(s.patterns).toHaveLength(SUGGESTION_LIMITS.patterns);
  });

  it("replaces rather than merges — a second photo does not accumulate", () => {
    const st = useQuizStore.getState();
    st.applySuggestion({ styles: ["boho"], color_palette: ["#111111"], materials: ["rattan"], patterns: [] });
    st.applySuggestion({ styles: ["modern"], color_palette: ["#222222"], materials: [], patterns: [] });
    const s = useQuizStore.getState();
    expect(s.styles).toEqual(["modern"]);
    expect(s.color_palette).toEqual(["#222222"]);
    expect(s.materials).toEqual([]);
  });
});
