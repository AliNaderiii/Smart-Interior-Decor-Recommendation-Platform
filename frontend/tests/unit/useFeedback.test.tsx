/** Unit tests for the 👍/👎 feedback hook (Stage 1, T-1.3).
 *
 * Pins the optimistic-update contract: the thumb flips instantly (local
 * cache mutated in onMutate), a failure rolls the cache back, and a success
 * invalidates the cached recommendations so the user actually SEES the list
 * change.
 *
 * Timing notes (react-query v5 under jsdom): mutation callbacks run in
 * microtasks, and the observer's batched notification reaches React one
 * macrotask later — so every assertion about the hook's *React state*
 * (status) goes through `waitFor`, while assertions about the *query cache*
 * (the optimistic data) are synchronous on the client. Deferred promises let
 * us observe the in-flight (optimistic) state separately from the settled
 * state.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return { ...orig, post: postMock };
});

import { useSubmitFeedback } from "@/lib/useFeedback";

type FeedbackMap = Record<string, number>;

function makeClient(existing: FeedbackMap = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  qc.setQueryData(["feedback"], existing);
  return qc;
}

function wrapper(client: QueryClient) {
  return function Wrap({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

/** A promise the test controls — resolves/rejects when told to. */
function deferred<T>() {
  let resolveFn: (v: T) => void = () => {};
  let rejectFn: (e: unknown) => void = () => {};
  const promise = new Promise<T>((resolve, reject) => {
    resolveFn = resolve;
    rejectFn = reject;
  });
  return { promise, resolve: resolveFn, reject: rejectFn };
}

beforeEach(() => {
  postMock.mockReset();
});

describe("useSubmitFeedback — optimistic update", () => {
  it("flips the thumb in the local cache BEFORE the request resolves", async () => {
    const qc = makeClient({});
    const flight = deferred<unknown>();
    postMock.mockReturnValue(flight.promise);

    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(qc),
    });

    await act(async () => {
      result.current.mutate({ productId: "p1", signal: 1 });
    });

    // Optimistic: visible in the query cache while the request is in flight.
    expect(qc.getQueryData<FeedbackMap>(["feedback"])).toEqual({ p1: 1 });
    expect(postMock).toHaveBeenCalledTimes(1);
    expect(postMock.mock.calls[0][0]).toBe("/feedback");
    expect(postMock.mock.calls[0][1]).toMatchObject({ product_id: "p1", signal: 1 });
    await waitFor(() => expect(result.current.status).toBe("pending"));

    await act(async () => {
      flight.resolve({ product_id: "p1", signal: 1 });
    });
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(qc.getQueryData<FeedbackMap>(["feedback"])).toEqual({ p1: 1 });
  });

  it("mirrors the server toggle semantics (same signal again -> removed)", async () => {
    const qc = makeClient({ p2: 1 });
    const flight = deferred<unknown>();
    postMock.mockReturnValue(flight.promise);

    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(qc),
    });

    await act(async () => {
      result.current.mutate({ productId: "p2", signal: 1 });
    });
    // Optimistic step: same signal as the stored one -> removed from the map.
    expect(qc.getQueryData<FeedbackMap>(["feedback"])).toEqual({});
    await waitFor(() => expect(result.current.status).toBe("pending"));

    await act(async () => {
      flight.resolve({ product_id: "p2", signal: 0 });
    });
    // Settled: server's post-toggle state wins.
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(qc.getQueryData<FeedbackMap>(["feedback"])).toEqual({});
  });

  it("rolls back when the request fails", async () => {
    const qc = makeClient({ p3: -1 });
    const flight = deferred<unknown>();
    postMock.mockReturnValue(flight.promise);

    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(qc),
    });

    await act(async () => {
      result.current.mutate({ productId: "p4", signal: -1 });
    });
    // Optimistic step: new vote visible on top of the pre-existing one.
    expect(qc.getQueryData<FeedbackMap>(["feedback"])).toEqual({ p3: -1, p4: -1 });
    await waitFor(() => expect(result.current.status).toBe("pending"));

    await act(async () => {
      flight.reject(new Error("boom"));
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    // Rollback: the failed p4 is gone, the pre-existing p3 untouched.
    expect(qc.getQueryData<FeedbackMap>(["feedback"])).toEqual({ p3: -1 });
  });

  it("invalidates the cached recommendations on success (the list must visibly change)", async () => {
    const qc = makeClient({});
    postMock.mockResolvedValue({ product_id: "p5", signal: 1 });
    let invalidated = 0;
    const spy = vi
      .spyOn(qc, "invalidateQueries")
      .mockImplementation((filters) => {
        if (filters && (filters as { queryKey?: unknown[] }).queryKey?.[0] === "recommend") {
          invalidated += 1;
        }
        return Promise.resolve();
      });

    const { result } = renderHook(() => useSubmitFeedback(), {
      wrapper: wrapper(qc),
    });

    await act(async () => {
      result.current.mutate({ productId: "p5", signal: 1 });
    });
    await waitFor(() => expect(invalidated).toBe(1));
    expect(spy).toHaveBeenCalledWith({ queryKey: ["recommend"] });
  });
});
