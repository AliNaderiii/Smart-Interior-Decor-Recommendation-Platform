/** Unit tests for the public share page's client-approval loop.
 *
 * The page is the unauthenticated half of the designer workflow that landed
 * in commit 44d9e91 (migration 0005) with no frontend coverage. The backend
 * contract is pinned in `backend/tests/test_designer_workflow.py`; this is
 * the DOM-side twin:
 *
 *  1. an approve click POSTs `{product_id, verdict, comment}` to
 *     `/share/{token}/approve` and reflects the verdict (`aria-pressed`);
 *  2. verdicts already recorded on the link (`/share/{token}/approvals`) are
 *     rendered on load, so a returning client is not asked to decide twice;
 *  3. a dead link (404 / 410 from the API) shows the error state and renders
 *     NO approve controls — nothing to click, nothing to post;
 *  4. the seller link stays sanitised: a `javascript:` URL never becomes an
 *     anchor. This page is reachable by anyone holding a token, which makes
 *     it the highest-value stored-XSS target in the SPA (X-01).
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return { ...orig, get: getMock, post: postMock };
});

import { ApiError } from "@/lib/api";
import type { RecommendedProduct } from "@/lib/types";
import SharePage from "@/pages/SharePage";
import { renderWithProviders } from "./renderWithProviders";

const TOKEN = "tok_abcdefghijklmnopqrstuvwxyz0123456789";

function product(id: string, title: string, sellerLink = "https://www.digikala.com/product/dkp-1/"): RecommendedProduct {
  return {
    id,
    title,
    category: "sofa",
    price_toman: 45_000_000,
    image_url: `/img/${id}.webp`,
    seller_link: sellerLink,
    seller_link_ok: true,
    colors: ["#D9A05B"],
    styles: ["modern"],
    materials: ["wood"],
    patterns: ["solid"],
    width_cm: 220,
    depth_cm: 90,
    height_cm: 80,
    description: "",
    final_score: 0.87,
    explanation: {
      style_match: 90, color_match: 80, budget_fit: 100, material_match: 70, pattern_match: 60, fit_match: 100, fit_reason: "fit_ok",
      matched_materials: ["wood"], summary: "Fits your modern brief.",
    },
  };
}

const SHARE_DATA = {
  client_name: "Sara",
  quiz: { styles: ["modern"], color_palette: ["#D9A05B"], room_width_cm: 400, room_length_cm: 500 },
  categories: { sofa: [product("p1", "Oslo three-seater"), product("p2", "Kian loveseat")] },
};

/** Route the two GETs the page makes by path suffix. */
function mockShareApi(opts: {
  share?: unknown | Error;
  approvals?: { product_id: string; verdict: "approved" | "rejected"; comment: string }[];
}) {
  getMock.mockImplementation((path: string) => {
    if (path.endsWith("/approvals")) return Promise.resolve(opts.approvals ?? []);
    if (opts.share instanceof Error) return Promise.reject(opts.share);
    return Promise.resolve(opts.share ?? SHARE_DATA);
  });
}

function renderShare(token = TOKEN) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/share/${token}`]}>
        <Routes>
          <Route path="/share/:token" element={<SharePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The card that contains the given product title. */
async function cardFor(title: string) {
  const heading = await screen.findByRole("heading", { name: title, level: 3 });
  // Card -> div.p-4 -> h3; climb to the Card so queries stay scoped to it.
  const card = heading.closest("div.overflow-hidden") ?? heading.parentElement!.parentElement!;
  return within(card as HTMLElement);
}

beforeEach(() => {
  localStorage.clear();
  getMock.mockReset();
  postMock.mockReset();
});

describe("share page — client approvals", () => {
  it("posts the verdict to /share/{token}/approve and reflects it as pressed", async () => {
    mockShareApi({});
    postMock.mockResolvedValue({ product_id: "p1", verdict: "approved" });
    renderShare();

    const card = await cardFor("Oslo three-seater");
    const approve = card.getByRole("button", { name: /^approve$/i });
    const reject = card.getByRole("button", { name: /^reject$/i });
    expect(approve.getAttribute("aria-pressed")).toBe("false");

    await userEvent.click(approve);

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    expect(postMock).toHaveBeenCalledWith(`/share/${TOKEN}/approve`, {
      product_id: "p1",
      verdict: "approved",
      comment: "",
    });
    await waitFor(() => expect(approve.getAttribute("aria-pressed")).toBe("true"));
    expect(reject.getAttribute("aria-pressed")).toBe("false");

    // Changing one's mind is an upsert on the server; the UI just flips.
    postMock.mockResolvedValue({ product_id: "p1", verdict: "rejected" });
    await userEvent.click(reject);
    await waitFor(() => expect(reject.getAttribute("aria-pressed")).toBe("true"));
    expect(approve.getAttribute("aria-pressed")).toBe("false");
  });

  it("renders verdicts already recorded on the link, per product", async () => {
    mockShareApi({
      approvals: [
        { product_id: "p1", verdict: "approved", comment: "love it" },
        { product_id: "p2", verdict: "rejected", comment: "" },
      ],
    });
    renderShare();

    const first = await cardFor("Oslo three-seater");
    await waitFor(() =>
      expect(first.getByRole("button", { name: /^approve$/i }).getAttribute("aria-pressed")).toBe("true"),
    );
    // The saved note is surfaced (truncated quote), not hidden behind "Add a note".
    expect(first.getByRole("button", { name: /love it/ })).toBeTruthy();

    const second = await cardFor("Kian loveseat");
    expect(second.getByRole("button", { name: /^reject$/i }).getAttribute("aria-pressed")).toBe("true");
    expect(second.getByRole("button", { name: /^approve$/i }).getAttribute("aria-pressed")).toBe("false");
    expect(second.getByRole("button", { name: /add a note/i })).toBeTruthy();

    expect(postMock).not.toHaveBeenCalled();
  });

  it("sends the note along with the verdict once the client has typed one", async () => {
    mockShareApi({});
    postMock.mockResolvedValue({ product_id: "p1", verdict: "approved" });
    renderShare();

    const card = await cardFor("Oslo three-seater");
    await userEvent.click(card.getByRole("button", { name: /add a note/i }));
    await userEvent.type(card.getByPlaceholderText(/what do you think/i), "too wide for the alcove");
    await userEvent.click(card.getByRole("button", { name: /^reject$/i }));

    await waitFor(() =>
      expect(postMock).toHaveBeenLastCalledWith(`/share/${TOKEN}/approve`, {
        product_id: "p1",
        verdict: "rejected",
        comment: "too wide for the alcove",
      }),
    );
  });

  it.each([
    [404, "unknown token"],
    [410, "expired link"],
  ])("shows the error state and no approve controls when the API answers %i (%s)", async (status) => {
    mockShareApi({ share: new ApiError(status, status === 410 ? "Share link expired" : "Share link not found") });
    renderShare();

    await screen.findByText(/invalid or has expired/i);
    expect(screen.queryByRole("button", { name: /^approve$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^reject$/i })).toBeNull();
    expect(postMock).not.toHaveBeenCalled();
  });

  it("never renders a javascript: seller link as an anchor (X-01)", async () => {
    mockShareApi({
      share: {
        ...SHARE_DATA,
        categories: {
          sofa: [
            product("evil", "Poisoned listing", "javascript:alert(document.cookie)"),
            product("fine", "Honest listing"),
          ],
        },
      },
    });
    const { container } = renderShare();

    await cardFor("Poisoned listing");
    const hrefs = Array.from(container.querySelectorAll("a[href]")).map((a) => a.getAttribute("href") ?? "");
    expect(hrefs.some((h) => h.toLowerCase().startsWith("javascript:"))).toBe(false);
    // The honest one is still linked, so the guard is selective, not blanket.
    expect(hrefs).toContain("https://www.digikala.com/product/dkp-1/");
  });
});
