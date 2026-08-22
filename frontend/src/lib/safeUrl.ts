/** URL sanitisation for anything that reaches an `href`, `src` or `window.open`.
 *
 * Stage 03 — probe `X-01`.
 *
 * The baseline API stored `seller_link` as a free string with no scheme check,
 * and three views rendered it straight into `<a href>`:
 * `ProductCard`, `ShoppingListPage` and — the one that matters most —
 * `SharePage`, which is **unauthenticated** and reachable by anyone holding a
 * share token. React escapes text nodes, but it does *not* stop
 * `href="javascript:…"`: a click executes the payload in the origin of the SPA,
 * with the victim's session.
 *
 * The backend now rejects dangerous schemes at the schema boundary
 * (`app.core.url_safety`), so this is the second lock rather than the only one.
 * It exists because the frontend cannot verify when a given row was written:
 * anything stored before the validator landed, or written by a future endpoint
 * that forgets it, still flows through these components. Rendering is the last
 * place the value can be checked, so it is checked here too.
 */

/** Schemes a link may use. Everything else is refused. */
const ALLOWED_PROTOCOLS = new Set(["http:", "https:", "mailto:", "tel:"]);

/** Rendered instead of a rejected link: inert, and obviously not a URL. */
export const BLOCKED_URL = "";

/**
 * Return `url` when it is safe to put in an `href`, otherwise `""`.
 *
 * Relative URLs (`/share/abc`, `products/1`) are allowed: they cannot carry a
 * scheme, so they cannot be `javascript:`. Anything absolute must parse and
 * must use an allowlisted protocol.
 */
export function safeUrl(url: string | null | undefined): string {
  if (!url) return BLOCKED_URL;

  // Strip control characters *before* inspecting the scheme:
  // `java\tscript:alert(1)` and `java\nscript:alert(1)` are both parsed as
  // `javascript:` by browsers, and a leading `\u0000`-`\u0020` run is ignored.
  // eslint-disable-next-line no-control-regex -- matching control characters is the point
  const cleaned = url.replace(/[\u0000-\u0020\u007f-\u009f]/g, "").trim();
  if (!cleaned) return BLOCKED_URL;

  // Protocol-relative (`//evil.example/x`) inherits the current scheme and is
  // a legitimate absolute URL, so resolve it against the page origin.
  if (cleaned.startsWith("/") || cleaned.startsWith("#") || cleaned.startsWith("?")) {
    // A path cannot contain a scheme, and `//` is handled by the parse below.
    if (!cleaned.startsWith("//")) return cleaned;
  }

  let parsed: URL;
  try {
    parsed = new URL(cleaned, window.location.origin);
  } catch {
    return BLOCKED_URL;
  }

  if (!ALLOWED_PROTOCOLS.has(parsed.protocol)) return BLOCKED_URL;
  return parsed.href;
}

/** True when the value would be rendered as a working link. */
export function isSafeUrl(url: string | null | undefined): boolean {
  return safeUrl(url) !== BLOCKED_URL;
}

/**
 * Same policy, for image sources.
 *
 * `data:` is excluded deliberately even though it cannot execute in `<img>`:
 * a `data:image/svg+xml` payload *can* execute when the same value is later
 * reused in a context that renders SVG inline, and product imagery legitimately
 * comes from the CDN only.
 */
export function safeImageUrl(url: string | null | undefined): string {
  const safe = safeUrl(url);
  if (!safe) return BLOCKED_URL;
  if (safe.startsWith("mailto:") || safe.startsWith("tel:")) return BLOCKED_URL;
  return safe;
}
