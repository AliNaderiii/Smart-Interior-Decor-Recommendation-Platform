/**
 * ADR-014 — behavioural event tracker.
 * Batching, impression de-duplication, keepalive on hide, closed payload
 * shape, and the guarantee that a failing analytics request never throws.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  _resetForTests,
  flush,
  installFlushOnHide,
  sessionId,
  setTrackingEnabled,
  track,
  trackImpressions,
} from "@/lib/events";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.clear();
  _resetForTests();
  document.cookie = "csrf_token=abc123";
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function lastBody() {
  const [, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return JSON.parse(init.body as string) as { session_id: string; events: unknown[] };
}

describe("events tracker — ADR-014", () => {
  it("keeps one 32-hex session id per tab", () => {
    const a = sessionId();
    expect(a).toMatch(/^[0-9a-f]{32}$/);
    expect(sessionId()).toBe(a);
    expect(sessionStorage.getItem("smartdecor.session")).toBe(a);
  });

  it("batches events and flushes after the timer with CSRF header", () => {
    track({ product_id: "p1", event_type: "click", page_context: "recommend", position: 1 });
    track({ product_id: "p2", event_type: "save", page_context: "recommend" });
    expect(fetchMock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(4000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/events");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("abc123");
    const body = lastBody();
    expect(body.session_id).toBe(sessionId());
    expect(body.events).toEqual([
      { product_id: "p1", event_type: "click", page_context: "recommend", position: 1 },
      { product_id: "p2", event_type: "save", page_context: "recommend" },
    ]);
  });

  it("deduplicates impressions per product and page context", () => {
    const items = [{ id: "a" }, { id: "b" }];
    trackImpressions(items, { page_context: "recommend", quiz_id: "q1", weights_version: "2026-09-06.1" });
    trackImpressions(items, { page_context: "recommend", quiz_id: "q1", weights_version: "2026-09-06.1" }); // re-render
    trackImpressions([{ id: "a" }], { page_context: "visual_search" }); // different context counts
    flush();
    const events = lastBody().events as { product_id: string; event_type: string; page_context: string; position: number }[];
    expect(events).toHaveLength(3);
    expect(events.filter((e) => e.page_context === "recommend").map((e) => [e.product_id, e.position])).toEqual([
      ["a", 1],
      ["b", 2],
    ]);
    expect(events[0]).toMatchObject({ quiz_id: "q1", weights_version: "2026-09-06.1", event_type: "impression" });
  });

  it("flushes immediately when the queue reaches its cap", () => {
    for (let i = 0; i < 40; i++) track({ product_id: `p${i}`, event_type: "click", page_context: "catalog" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(lastBody().events).toHaveLength(40);
  });

  it("uses keepalive when the tab is hidden", () => {
    installFlushOnHide();
    track({ product_id: "p1", event_type: "click", page_context: "recommend" });
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect((fetchMock.mock.calls[0][1] as RequestInit).keepalive).toBe(true);
  });

  it("never throws when the network fails", () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    track({ product_id: "p1", event_type: "click", page_context: "recommend" });
    expect(() => flush()).not.toThrow();
    fetchMock.mockImplementation(() => {
      throw new TypeError("fetch unavailable");
    });
    track({ product_id: "p2", event_type: "click", page_context: "recommend" });
    expect(() => flush()).not.toThrow();
  });

  it("can be disabled (kill switch drops the queue)", () => {
    track({ product_id: "p1", event_type: "click", page_context: "recommend" });
    setTrackingEnabled(false);
    track({ product_id: "p2", event_type: "click", page_context: "recommend" });
    flush();
    expect(fetchMock).not.toHaveBeenCalled();
    setTrackingEnabled(true);
  });
});
