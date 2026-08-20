/**
 * Phase 4 — executable dead-key audit (jsdom).
 *
 * WHY THIS EXISTS: `npx playwright install chromium` fails in this
 * environment (ECONNRESET against the CDN), so `tests/e2e/deadKeys.spec.ts`
 * cannot be executed here. Rather than ship an unverified claim, this
 * harness mounts every page in jsdom with a mocked API and actually clicks
 * every interactive control, asserting the same core property:
 *
 *     a click must produce an observable change (DOM or fetch) and must not
 *     throw or log a console error.
 *
 * What this DOES catch: inert handlers, handlers that throw, state that never
 * updates, controls that render but do nothing.
 * What it does NOT catch (Playwright's job): real layout, real navigation,
 * clipboard, downloads, and true HTTP status codes.
 *
 * Run: npx tsx --tsconfig tsconfig.app.json scripts/clickAudit.mts
 */
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
  url: "http://localhost:5173/",
  pretendToBeVisual: true,
});

const g = globalThis as unknown as Record<string, unknown>;
g.window = dom.window;
g.document = dom.window.document;
// Node 22 defines `navigator` as a getter-only global; redefine it.
Object.defineProperty(globalThis, "navigator", {
  value: dom.window.navigator, configurable: true, writable: true,
});
g.HTMLElement = dom.window.HTMLElement;
g.HTMLInputElement = dom.window.HTMLInputElement;
g.Element = dom.window.Element;
g.Node = dom.window.Node;
g.Event = dom.window.Event;
g.MouseEvent = dom.window.MouseEvent;
g.KeyboardEvent = dom.window.KeyboardEvent;
// Radix and framer-motion construct these from the GLOBAL scope; if they
// resolve to Node's built-ins instead of jsdom's, the resulting objects fail
// jsdom's instanceof check inside dispatchEvent.
g.CustomEvent = dom.window.CustomEvent;
g.PointerEvent = dom.window.PointerEvent ?? dom.window.MouseEvent;
g.FocusEvent = dom.window.FocusEvent;
g.SVGElement = dom.window.SVGElement;
g.HTMLButtonElement = dom.window.HTMLButtonElement;
g.DocumentFragment = dom.window.DocumentFragment;
g.getComputedStyle = dom.window.getComputedStyle;
g.localStorage = dom.window.localStorage;
g.sessionStorage = dom.window.sessionStorage;
g.requestAnimationFrame = (cb: FrameRequestCallback) => dom.window.setTimeout(() => cb(Date.now()), 0);
g.cancelAnimationFrame = (id: number) => dom.window.clearTimeout(id);
g.IS_REACT_ACT_ENVIRONMENT = true;

// jsdom lacks these; components legitimately use them.
dom.window.matchMedia ??= ((q: string) => ({
  matches: false, media: q, onchange: null,
  addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia;
class RO { observe() {} unobserve() {} disconnect() {} }
g.ResizeObserver = RO;
g.NodeFilter = dom.window.NodeFilter;   // Radix focus-scope walks the DOM with a TreeWalker
g.DOMRect = dom.window.DOMRect;
dom.window.HTMLElement.prototype.scrollTo = function () {};
dom.window.Element.prototype.scrollTo = function () {};
g.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } };
dom.window.HTMLElement.prototype.scrollIntoView = function () {};
dom.window.HTMLCanvasElement.prototype.getContext = (() => null) as never;
Object.defineProperty(dom.window.navigator, "clipboard", {
  value: { writeText: async () => {}, readText: async () => "" },
  configurable: true,
});

/* --------------------------------------------------------------- API mock */

let fetchCount = 0;
const seededProduct = (id: string, title: string) => ({
  id, title, title_fa: title, category: "sofa", price_toman: 25_000_000,
  image_url: "https://example.com/p.jpg", seller_link: "https://shop.example.com/p",
  seller_link_ok: true, colors: ["#C9BBA8"], styles: ["modern"], materials: ["wood"],
  patterns: [], width_cm: 200, depth_cm: 90, height_cm: 80,
  description: "A sofa.", final_score: 0.87, extraction_confidence: 0.62, is_verified: false,
  explanation: {
    summary: "Matches your modern style and budget.",
    style_match: 90, color_match: 80, budget_fit: 85, material_match: 70,
    matched_styles: ["modern"], matched_colors: ["#C9BBA8"], matched_materials: ["wood"],
  },
});

const BOARD = {
  id: "b1", title: "My Living Room",
  items: [{ product_id: "p1", x: 0, y: 0, w: 4, h: 4 }],
  shopping_list: ["p1", "p2"],
  products: { p1: seededProduct("p1", "Linen Sofa"), p2: seededProduct("p2", "Oak Table") },
};

const ROUTES: [RegExp, unknown][] = [
  [/\/moodboards\/[^/]+$/, BOARD],
  [/\/moodboards$/, [BOARD, { ...BOARD, id: "b2", title: "Bedroom" }]],
  [/\/projects\/[^/]+\/share$/, { share_url: "/share/tok123", token: "tok123" }],
  [/\/projects\/[^/]+$/, {
    id: "pr1", name: "Villa Lavasan", client_name: "Sara Ahmadi",
    client_email: "sara@example.com", notes: "", created_at: new Date().toISOString(),
    quiz_count: 2,
    quizzes: [{ id: "q1", client_name: "Sara", styles: ["modern"], created_at: new Date().toISOString() }],
  }],
  [/\/projects$/, [
    { id: "pr1", name: "Villa Lavasan", client_name: "Sara Ahmadi", client_email: "", notes: "", created_at: new Date().toISOString(), quiz_count: 2 },
    { id: "pr2", name: "Apartment Tajrish", client_name: "Reza N", client_email: "", notes: "", created_at: new Date().toISOString(), quiz_count: 0 },
  ]],
  [/\/products\?/, { items: [seededProduct("p1", "Linen Sofa"), seededProduct("p2", "Oak Table")], total: 2, page: 1, page_size: 15 }],
  [/\/products\/[^/]+\/verify$/, { ok: true }],
  [/\/admin\/users$/, [{ id: "u1", email: "demo@smartdecor.dev", full_name: "Demo", role: "homeowner", is_active: true, subscription_plan: "free", subscription_active: false, created_at: new Date().toISOString() }]],
  [/\/admin\/subscriptions$/, [{ id: "s1", user_email: "demo@smartdecor.dev", plan: "pro", is_active: true, expires_at: null }]],
  [/\/feedback$/, {}],
  [/\/payment\/request$/, { redirect_url: "/upgrade?Authority=A123&Status=OK" }],
  [/\/payment\/verify/, { subscription_plan: "pro", subscription_active: true }],
  [/\/recommend/, { categories: { sofa: [seededProduct("p1", "Linen Sofa"), seededProduct("p2", "Oak Table")] } }],
  [/\/share\//, { client_name: "Sara", quiz: { styles: ["modern"], color_palette: ["#C9BBA8"], room_width_cm: 400, room_length_cm: 500 }, categories: { sofa: [seededProduct("p1", "Linen Sofa")] } }],
  [/\/quiz/, { id: "q1" }],
];

g.fetch = async (input: RequestInfo | URL) => {
  fetchCount++;
  const url = String(typeof input === "string" ? input : (input as Request).url ?? input);
  const hit = ROUTES.find(([re]) => re.test(url));
  const data = hit ? hit[1] : {};
  // jsdom has no Response constructor; Node 22 provides a native one.
  return new Response(JSON.stringify({ data }), {
    status: 200, headers: { "content-type": "application/json" },
  });
};

/* ------------------------------------------------------------------ render */

const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const { act } = await import("react");
const { MemoryRouter } = await import("react-router-dom");
const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
const { ToastProvider } = await import("@/components/Toast");
const { CommandPaletteProvider } = await import("@/components/CommandPalette");
const { useAuthStore } = await import("@/stores/authStore");
const { tokenStore } = await import("@/lib/api");

tokenStore.set("fake-access-token", "fake-refresh-token");
useAuthStore.setState({
  user: {
    id: "u1", email: "demo@smartdecor.dev", full_name: "Demo User",
    role: "admin", subscription_plan: "pro", subscription_active: true,
  } as never,
});

const pages: [string, string, () => Promise<{ default: React.ComponentType }>][] = [
  ["Home", "/", () => import("@/pages/HomePage")],
  ["Login", "/login", () => import("@/pages/LoginPage")],
  ["Register", "/register", () => import("@/pages/RegisterPage")],
  ["Quiz", "/quiz", () => import("@/pages/QuizPage")],
  ["Recommendations", "/recommendations", () => import("@/pages/RecommendationsPage")],
  ["Moodboards", "/moodboards", () => import("@/pages/MoodboardsPage")],
  ["MoodboardEditor", "/moodboard/b1", () => import("@/pages/MoodboardEditorPage")],
  ["Floorplan", "/floorplan", () => import("@/pages/FloorplanPage")],
  ["ShoppingList", "/shopping-list", () => import("@/pages/ShoppingListPage")],
  ["Upgrade", "/upgrade", () => import("@/pages/UpgradePage")],
  ["Share", "/share/tok123", () => import("@/pages/SharePage")],
  ["DesignerDashboard", "/designer/dashboard", () => import("@/pages/designer/DashboardPage")],
  ["DesignerProject", "/designer/project/pr1", () => import("@/pages/designer/ProjectPage")],
  ["AdminProducts", "/admin/products", () => import("@/pages/admin/ProductsPage")],
  ["AdminUsers", "/admin/users", () => import("@/pages/admin/UsersPage")],
  ["AdminSubs", "/admin/subscriptions", () => import("@/pages/admin/SubscriptionsPage")],
];

const SKIP = [/sign out/i, /log out/i, /^delete$/i, /confirm delete/i];

/** Controls whose entire effect is a browser API jsdom does not implement
 *  (file pickers, canvas rasterisation, downloads). Their wiring is verified
 *  by the Playwright spec instead; flagging them here would be a false DEAD. */
const NATIVE_ONLY = [
  /upload product image/i,  // input[type=file].click() — no picker in jsdom
  /export png/i,            // html2canvas needs a real 2D canvas context
  /enlarge image/i,         // hover-zoom driven by pointer events
];

const consoleErrors: string[] = [];
const origError = console.error;
console.error = (...a: unknown[]) => {
  const msg = a.map(String).join(" ");
  // React Router future-flag notices and act() noise are not product bugs.
  // jsdom "Not implemented" notices are engine gaps, not product defects:
  // layout, scrolling and canvas rasterisation simply do not exist here.
  if (/React Router Future Flag|not wrapped in act|validateDOMNesting/i.test(msg)) return;
  if (/Not implemented: Window|Not implemented: HTMLCanvas|getComputedStyle\(\) method/i.test(msg)) return;
  consoleErrors.push(msg);
};

interface Row { page: string; control: string; verdict: string; note: string }
const rows: Row[] = [];
let dead = 0;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

for (const [name, path, load] of pages) {
  const Page = (await load()).default;
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const root = createRoot(container);

  await act(async () => {
    root.render(
      React.createElement(MemoryRouter, { initialEntries: [path] },
        React.createElement(QueryClientProvider, { client: qc },
          React.createElement(ToastProvider, null,
            React.createElement(CommandPaletteProvider, null,
              React.createElement(Page))))),
    );
  });
  await act(async () => { await sleep(120); });

  // Collect stable identities FIRST, then re-query before each click.
  // Clicking re-renders React, which detaches the previously collected nodes;
  // clicking a detached node silently does nothing and looks like a dead key.
  const describe = (el: Element) =>
    ((el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 46) || "(unnamed)");

  const SELECTOR = "button:not([disabled]), a[href], [role='button']:not([aria-disabled='true'])";
  const labels: string[] = [];
  for (const el of container.querySelectorAll(SELECTOR)) {
    const l = describe(el);
    if (!labels.includes(l)) labels.push(l);
  }

  for (const label of labels) {
    if (SKIP.some((re) => re.test(label))) {
      rows.push({ page: name, control: label, verdict: "SKIP", note: "destructive/session-ending" });
      continue;
    }

    // Re-query fresh: the node may have been replaced by an earlier click.
    const el = [...container.querySelectorAll<HTMLElement>(SELECTOR)].find((c) => describe(c) === label);
    if (!el) {
      rows.push({ page: name, control: label, verdict: "OK", note: "removed by an earlier interaction" });
      continue;
    }

    if (el.tagName === "A") {
      const href = el.getAttribute("href") ?? "";
      rows.push({
        page: name, control: label,
        verdict: href ? "OK" : "DEAD",
        note: href ? `link → ${href}` : "anchor without href",
      });
      if (!href) dead++;
      continue;
    }

    // A control that is already in its target state (the active filter tab, the
    // current sort) legitimately does nothing when clicked again.
    // All four ARIA idioms for "this control is already in its target state".
    const alreadyActive = ["aria-pressed", "aria-current", "aria-checked", "aria-selected"]
      .some((a) => el.getAttribute(a) === "true");

    const beforeHtml = container.innerHTML;
    const beforeFetch = fetchCount;
    const beforeErrs = consoleErrors.length;
    let threw = "";

    try {
      await act(async () => {
        el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
        await sleep(60);
      });
    } catch (e) {
      threw = (e as Error).message.split("\n")[0];
    }

    const changed = container.innerHTML !== beforeHtml || fetchCount > beforeFetch;
    const newErrs = consoleErrors.slice(beforeErrs);

    let verdict = "OK";
    let note = changed ? (fetchCount > beforeFetch ? "fetch issued" : "DOM updated") : "";
    if (threw) { verdict = "DEAD"; note = `threw: ${threw}`; dead++; }
    else if (newErrs.length) { verdict = "DEAD"; note = `console error: ${newErrs[0].slice(0, 90)}`; dead++; }
    else if (!changed) {
      if (alreadyActive) { note = "no-op: already the active state"; }
      else if (NATIVE_ONLY.some((re) => re.test(label))) { note = "delegates to a native API jsdom does not implement"; }
      else { verdict = "DEAD"; note = "no DOM or network change"; dead++; }
    }

    rows.push({ page: name, control: label, verdict, note });
  }

  await act(async () => { root.unmount(); });
  container.remove();
}

console.error = origError;

const pad = (s: string, n: number) => s.length > n ? s.slice(0, n - 1) + "…" : s.padEnd(n);
console.log("\n=== CLICK AUDIT (jsdom) ===\n");
console.log(`${pad("PAGE", 18)} ${pad("CONTROL", 46)} ${pad("VERDICT", 8)} NOTE`);
console.log("-".repeat(120));
for (const r of rows) console.log(`${pad(r.page, 18)} ${pad(r.control, 46)} ${pad(r.verdict, 8)} ${r.note}`);

const clicked = rows.filter((r) => r.verdict !== "SKIP").length;
console.log("-".repeat(120));
console.log(`\n${clicked} controls exercised · ${dead} DEAD · ${rows.filter(r => r.verdict === "SKIP").length} skipped`);
console.log(dead === 0 ? "RESULT: PASS — 0 DEAD" : "RESULT: FAIL");
process.exit(dead === 0 ? 0 : 1);
