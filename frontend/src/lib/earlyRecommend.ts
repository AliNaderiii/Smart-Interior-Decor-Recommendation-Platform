import type { RecommendResult } from "@/lib/types";

/**
 * Early /recommend kickoff — T-2.1 optimization (Directive 4 R2.2).
 *
 * Measured problem (CI run 33081447868, recommendations/mobile, Slow-4G
 * simulation): LCP 6564ms with the phase split TTFB 453 / **load delay
 * 5145** / load time 255 / render delay 711. The LCP product photo cannot
 * even be REQUESTED until the whole serial chain completes:
 *
 *   entry JS → lazy route chunk → React mount → react-query → POST
 *   /recommend (round trip) → card render → image request
 *
 * The API itself is fast (37ms observed in-job) and the response is small
 * (~10KB) — the cost is where the round trip SITS. This module runs at
 * entry-module evaluation time, before React ever mounts:
 *
 *  1. If (and only if) the current URL is /recommendations and the session
 *     is cookie-mode (readable csrf_token present), it fires the exact POST
 *     the page would fire, in parallel with route-chunk download and parse.
 *  2. As soon as the response arrives it injects
 *     `<link rel="preload" as="image" fetchpriority="high">` for the first
 *     card's photo — the LCP image starts downloading while React is still
 *     booting, instead of last in the chain.
 *  3. The page's query consumes the in-flight promise via
 *     `takeEarlyRecommend()`; on ANY early failure the caller falls back to
 *     the normal `post()` path (auth refresh, error shaping, retries), so
 *     behavior on the failure paths is unchanged.
 *
 * Bearer-token mode (USE_COOKIE_AUTH=false) intentionally skips the kickoff:
 * tokens live in localStorage and the normal path handles them; the default
 * production mode is cookies.
 */

interface RecommendEnvelope {
  success: boolean;
  data: RecommendResult;
  error: string | null;
}

const inflight = new Map<string, Promise<RecommendResult>>();

function csrfToken(): string | null {
  const m = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function preloadFirstImage(data: RecommendResult): void {
  const categories = data?.categories ?? {};
  const first = Object.values(categories)[0]?.[0];
  const src = first && !first.locked ? first.image_url : undefined;
  if (!src) return;
  const link = document.createElement("link");
  link.rel = "preload";
  // setAttribute rather than IDL properties: `as`/`fetchPriority` reflection
  // is missing in older engines (and jsdom); the attribute form is canonical.
  link.setAttribute("as", "image");
  link.setAttribute("fetchpriority", "high");
  link.href = src;
  document.head.appendChild(link);
}

/** Fire the kickoff for the current location. Exported for tests. */
export function kickoffEarlyRecommend(
  pathname = window.location.pathname,
  search = window.location.search,
): void {
  if (!pathname.startsWith("/recommendations")) return;
  const csrf = csrfToken();
  if (!csrf) return; // not cookie-authenticated — normal path handles it
  const quizId = new URLSearchParams(search).get("quiz");
  const key = quizId ?? "";
  if (inflight.has(key)) return;
  const url = quizId
    ? `/api/v1/recommend?quiz_id=${encodeURIComponent(quizId)}`
    : "/api/v1/recommend";
  const promise = fetch(url, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrf },
  })
    .then(async (resp) => {
      if (!resp.ok) throw new Error(`early recommend HTTP ${resp.status}`);
      const json = (await resp.json()) as RecommendEnvelope;
      if (!json?.success || !json.data) throw new Error(json?.error ?? "early recommend failed");
      preloadFirstImage(json.data);
      return json.data;
    });
  // An early failure must not poison the page: drop it so the query's
  // fallback (full api.ts path with refresh handling) takes over cleanly.
  promise.catch(() => inflight.delete(key));
  inflight.set(key, promise);
}

/** Hand the in-flight promise to the page query exactly once. */
export function takeEarlyRecommend(quizId: string | null): Promise<RecommendResult> | undefined {
  const key = quizId ?? "";
  const p = inflight.get(key);
  inflight.delete(key);
  return p;
}

// Module-evaluation side effect: main.tsx imports this before React renders.
if (typeof window !== "undefined" && !import.meta.env?.TEST) {
  kickoffEarlyRecommend();
}
