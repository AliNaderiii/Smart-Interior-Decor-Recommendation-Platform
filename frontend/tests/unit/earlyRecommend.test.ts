import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kickoffEarlyRecommend, takeEarlyRecommend } from "@/lib/earlyRecommend";

const DATA = {
  quiz_id: "q1",
  is_pro: false,
  categories: {
    sofa: [
      {
        id: "p1",
        image_url: "https://images.unsplash.com/photo-abc?w=800",
        locked: false,
      },
    ],
  },
};

function envelope(ok = true) {
  return {
    ok: true,
    json: async () => (ok ? { success: true, data: DATA, error: null } : { success: false, data: null, error: "boom" }),
  } as Response;
}

describe("earlyRecommend kickoff", () => {
  beforeEach(() => {
    document.cookie = "csrf_token=tok123";
    document.head.querySelectorAll("link[rel=preload]").forEach((n) => n.remove());
  });

  afterEach(() => {
    // Drain any promise a test left behind so cases stay independent.
    takeEarlyRecommend(null);
    takeEarlyRecommend("abc");
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    vi.unstubAllGlobals();
  });

  it("does nothing on routes other than /recommendations", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    kickoffEarlyRecommend("/quiz", "");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(takeEarlyRecommend(null)).toBeUndefined();
  });

  it("does nothing without a csrf cookie (bearer mode)", () => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    kickoffEarlyRecommend("/recommendations", "?quiz=abc");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fires the exact page POST, hands over the data once, and preloads the hero image", async () => {
    const fetchMock = vi.fn().mockResolvedValue(envelope());
    vi.stubGlobal("fetch", fetchMock);
    kickoffEarlyRecommend("/recommendations", "?quiz=abc");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/recommend?quiz_id=abc",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": "tok123" },
      }),
    );

    const early = takeEarlyRecommend("abc");
    expect(early).toBeDefined();
    await expect(early).resolves.toEqual(DATA);
    // Single-use handover.
    expect(takeEarlyRecommend("abc")).toBeUndefined();
    // LCP image preload injected.
    const link = document.head.querySelector('link[rel=preload][as=image]') as HTMLLinkElement;
    expect(link?.href).toContain("images.unsplash.com");
  });

  it("cleans up after itself when the early request fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue(envelope(false));
    vi.stubGlobal("fetch", fetchMock);
    kickoffEarlyRecommend("/recommendations", "");
    const early = takeEarlyRecommend(null);
    expect(early).toBeDefined();
    await expect(early).rejects.toThrow("boom");
    // Failed promise was dropped — a later take must not resurrect it.
    expect(takeEarlyRecommend(null)).toBeUndefined();
  });
});
