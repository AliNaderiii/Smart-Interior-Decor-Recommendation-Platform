/**
 * ADR-013 — VisualSearchPage.
 * The page must (1) refuse non-images and oversize files before any network
 * call, (2) post the photo as multipart with the category filter, (3) render
 * ranked results with the paywall shape the API returned, (4) SAY which
 * retrieval mode produced them, and (5) hand the extracted palette to the
 * quiz store.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderWithProviders } from "./renderWithProviders";
import type { VisualSearchResult } from "@/lib/types";

const postMock = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, post: (...args: unknown[]) => postMock(...args) };
});

import VisualSearchPage from "@/pages/VisualSearchPage";
import { useQuizStore } from "@/stores/quizStore";
import { useMoodboardStore } from "@/stores/moodboardStore";

const RESULT: VisualSearchResult = {
  is_pro: false,
  meta: {
    mode: "palette",
    palette: ["#2F6B3A", "#D9CBB3"],
    category: null,
    candidates: 40,
    embedding_backend: "hash",
    query_image: { width: 160, height: 120, content_type: "image/jpeg" },
  },
  items: [
    {
      id: "p1",
      title: "Forest Green Rug",
      title_fa: "فرش سبز جنگلی",
      category: "rug",
      price_toman: 27_000_000,
      image_url: "https://images.example.com/rug.jpg",
      seller_link: "https://example.com/rug",
      seller_link_ok: true,
      colors: ["#2F6B3A"],
      styles: ["modern"],
      materials: ["wool"],
      patterns: ["solid"],
      width_cm: 200,
      depth_cm: 150,
      height_cm: 1,
      description: "",
      similarity: 0.91,
      palette_match: 0.91,
    },
    {
      id: "p2",
      title: "Navy Rug",
      category: "rug",
      image_url: "https://images.example.com/navy.jpg",
      similarity: 0.62,
      locked: true,
    },
  ],
};

function render(locale: "en" | "fa" = "en") {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/visual-search"]}>
        <Routes>
          <Route path="/visual-search" element={<VisualSearchPage />} />
          <Route path="/quiz" element={<div>QUIZ PAGE</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
    { locale },
  );
}

function jpeg(name = "sofa.jpg", size = 1024): File {
  return new File([new Uint8Array(size)], name, { type: "image/jpeg" });
}

beforeEach(() => {
  postMock.mockReset();
  useQuizStore.getState().reset();
  useMoodboardStore.getState().clear();
  // jsdom has no object URLs
  (globalThis.URL as unknown as { createObjectURL: () => string }).createObjectURL = () => "blob:preview";
  (globalThis.URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
});

describe("VisualSearchPage — ADR-013", () => {
  it("rejects a non-image locally without calling the API", async () => {
    render();
    const input = screen.getByTestId("visual-file-input") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "notes.txt", { type: "text/plain" }), { applyAccept: false });
    expect((await screen.findByRole("alert")).textContent).toMatch(/not an image/i);
    expect(postMock).not.toHaveBeenCalled();
    expect((screen.getByTestId("visual-search-submit") as HTMLButtonElement).disabled).toBe(true);
  });

  it("rejects an oversize photo locally", async () => {
    render();
    const input = screen.getByTestId("visual-file-input") as HTMLInputElement;
    await userEvent.upload(input, jpeg("huge.jpg", 8 * 1024 * 1024 + 1));
    expect((await screen.findByRole("alert")).textContent).toMatch(/larger than 8 MB/i);
    expect(postMock).not.toHaveBeenCalled();
  });

  it("posts multipart with the category filter and renders ranked results + mode notice", async () => {
    postMock.mockResolvedValue(RESULT);
    render();
    await userEvent.upload(screen.getByTestId("visual-file-input"), jpeg());
    expect(screen.getByTestId("visual-preview")).toBeTruthy();
    await userEvent.selectOptions(screen.getByLabelText(/limit to category/i), "rug");
    await userEvent.click(screen.getByTestId("visual-search-submit"));

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    const [url, body] = postMock.mock.calls[0] as [string, FormData];
    expect(url).toBe("/search/visual?limit=12&category=rug");
    expect(body).toBeInstanceOf(FormData);
    expect((body.get("file") as File).name).toBe("sofa.jpg");

    const results = await screen.findByTestId("visual-results");
    const cards = results.querySelectorAll('[data-testid="visual-result"]');
    expect(cards).toHaveLength(2);
    expect(cards[0].getAttribute("data-locked")).toBe("false");
    expect(cards[0].textContent).toContain("Forest Green Rug");
    expect(cards[0].textContent).toContain("91% similar");
    expect(cards[1].getAttribute("data-locked")).toBe("true");
    expect(cards[1].textContent).toContain("Upgrade to Pro");
    // The page says HOW it searched.
    const mode = screen.getByTestId("visual-mode");
    expect(mode.getAttribute("data-mode")).toBe("palette");
    expect(mode.textContent).toMatch(/colour mode/i);
    expect(screen.getByText("2 similar products")).toBeTruthy();
  });

  it("renders the vision-mode notice when the backend used CLIP", async () => {
    postMock.mockResolvedValue({ ...RESULT, meta: { ...RESULT.meta, mode: "clip", embedding_backend: "clip" } });
    render();
    await userEvent.upload(screen.getByTestId("visual-file-input"), jpeg());
    await userEvent.click(screen.getByTestId("visual-search-submit"));
    const mode = await screen.findByTestId("visual-mode");
    expect(mode.getAttribute("data-mode")).toBe("clip");
    expect(mode.textContent).toMatch(/vision mode/i);
  });

  it("hands the extracted palette to the quiz store and navigates to /quiz", async () => {
    postMock.mockResolvedValue(RESULT);
    render();
    await userEvent.upload(screen.getByTestId("visual-file-input"), jpeg());
    await userEvent.click(screen.getByTestId("visual-search-submit"));
    await screen.findByTestId("visual-palette");
    await userEvent.click(screen.getByRole("button", { name: /use these colours/i }));
    expect(useQuizStore.getState().color_palette).toEqual(["#2F6B3A", "#D9CBB3"]);
    expect(await screen.findByText("QUIZ PAGE")).toBeTruthy();
  });

  it("adds a full result to the moodboard staging area", async () => {
    postMock.mockResolvedValue(RESULT);
    render();
    await userEvent.upload(screen.getByTestId("visual-file-input"), jpeg());
    await userEvent.click(screen.getByTestId("visual-search-submit"));
    await screen.findByTestId("visual-results");
    await userEvent.click(screen.getByRole("button", { name: /^add to moodboard$/i }));
    expect(useMoodboardStore.getState().picked.map((p) => p.id)).toEqual(["p1"]);
    expect((screen.getByRole("button", { name: /^added$/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("maps a 429 to the rate-limit message", async () => {
    const { ApiError } = await import("@/lib/api");
    postMock.mockRejectedValue(new ApiError(429, "slow down"));
    render();
    await userEvent.upload(screen.getByTestId("visual-file-input"), jpeg());
    await userEvent.click(screen.getByTestId("visual-search-submit"));
    expect((await screen.findByRole("alert")).textContent).toMatch(/too many searches/i);
  });

  it("is fully localised in Persian", async () => {
    postMock.mockResolvedValue(RESULT);
    render("fa");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("جست‌وجوی تصویری");
    await userEvent.upload(screen.getByTestId("visual-file-input"), jpeg());
    await userEvent.click(screen.getByTestId("visual-search-submit"));
    const results = await screen.findByTestId("visual-results");
    expect(results.textContent).toContain("فرش سبز جنگلی");
    expect(screen.getByTestId("visual-mode").textContent).toMatch(/حالت رنگ‌محور/);
  });
});
