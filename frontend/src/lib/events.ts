/**
 * Behavioural event tracker (ADR-014) — the client half of
 * `docs/ai/feedback-events.md`.
 *
 * Rules:
 *  - fire-and-forget: nothing here can throw into UI code or block a click;
 *  - batched: events are queued and flushed every FLUSH_MS, when the queue
 *    reaches MAX_QUEUE, or on page hide (with `keepalive` so the request
 *    survives navigation);
 *  - deduplicated impressions: one impression per (session, product, page
 *    context) — a re-render is not a second showing;
 *  - no PII: the payload is a closed vocabulary plus ids.
 *
 * The session id lives in sessionStorage (one per tab lifetime), which is
 * what the spec means by "groups one browsing session".
 */
export type EventType =
  | "impression"
  | "click"
  | "like"
  | "dislike"
  | "unlike"
  | "save"
  | "share"
  | "purchase_click";
export type PageContext = "recommend" | "moodboard" | "share" | "catalog" | "visual_search";

export interface TrackedEvent {
  product_id: string;
  event_type: EventType;
  page_context: PageContext;
  position?: number;
  quiz_id?: string | null;
  weights_version?: string | null;
}

const SESSION_KEY = "smartdecor.session";
const FLUSH_MS = 4000;
const MAX_QUEUE = 40;
const ENDPOINT = "/api/v1/events";

let queue: TrackedEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
const seenImpressions = new Set<string>();
let disabled = false;

function randomHex32(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID().replace(/-/g, "");
  let out = "";
  for (let i = 0; i < 32; i++) out += Math.floor(Math.random() * 16).toString(16);
  return out;
}

export function sessionId(): string {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing && /^[0-9a-f]{32}$/.test(existing)) return existing;
    const fresh = randomHex32();
    sessionStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch {
    return randomHex32();
  }
}

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

/** Send whatever is queued. `unload` switches to keepalive semantics. */
export function flush(unload = false): void {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  if (queue.length === 0 || disabled) return;
  const events = queue.slice(0, 100);
  queue = queue.slice(100);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const csrf = readCookie("csrf_token");
  if (csrf) headers["X-CSRF-Token"] = csrf;
  try {
    void fetch(ENDPOINT, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ session_id: sessionId(), events }),
      keepalive: unload,
    }).catch(() => {
      /* analytics must never surface as a UI error */
    });
  } catch {
    /* ignore — same reason */
  }
  if (queue.length) schedule();
}

function schedule(): void {
  if (timer || disabled) return;
  timer = setTimeout(() => flush(false), FLUSH_MS);
}

/** Queue one event. Impressions are deduplicated per session/product/context. */
export function track(event: TrackedEvent): void {
  if (disabled) return;
  if (event.event_type === "impression") {
    const key = `${event.page_context}:${event.product_id}`;
    if (seenImpressions.has(key)) return;
    seenImpressions.add(key);
  }
  queue.push(event);
  if (queue.length >= MAX_QUEUE) flush(false);
  else schedule();
}

/** Convenience: a whole ranked list was shown. */
export function trackImpressions(
  items: { id: string }[],
  ctx: { page_context: PageContext; quiz_id?: string | null; weights_version?: string | null },
): void {
  items.forEach((item, i) =>
    track({
      product_id: item.id,
      event_type: "impression",
      page_context: ctx.page_context,
      position: i + 1,
      quiz_id: ctx.quiz_id ?? null,
      weights_version: ctx.weights_version ?? null,
    }),
  );
}

let installed = false;
/** Flush on tab hide/unload. Safe to call more than once. */
export function installFlushOnHide(): void {
  if (installed || typeof document === "undefined") return;
  installed = true;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush(true);
  });
  window.addEventListener("pagehide", () => flush(true));
}

/** Test hook / kill switch. */
export function _resetForTests(): void {
  queue = [];
  seenImpressions.clear();
  if (timer) clearTimeout(timer);
  timer = null;
  disabled = false;
}
export function setTrackingEnabled(enabled: boolean): void {
  disabled = !enabled;
  if (!enabled) queue = [];
}
