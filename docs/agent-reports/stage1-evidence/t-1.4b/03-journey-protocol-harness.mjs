/**
 * Stage 1, T-1.4 close-out — journey protocol harness.
 *
 * WHY THIS EXISTS: the Playwright chromium binary cannot be downloaded in this
 * sandbox (see 00-browser-download-blocked-retry.log, blocker IR-S1-001), so
 * the three journey specs cannot be EXECUTED locally. They will run in the CI
 * `e2e` job. This harness independently verifies, against the same live app
 * the specs target, that every backend contract the specs assert on actually
 * holds — so a CI failure would be a selector problem, not a wrong assertion.
 *
 * It exercises the same sequences the specs do, at the protocol layer:
 *   homeowner: login -> quiz -> recommend (3-5 per category, explanation
 *              payload) -> moodboard create -> shopping list -> logout
 *   designer:  login -> projects list -> create up to quota -> 402 Persian
 *   admin:     login -> products list -> upload (mock AI extraction) ->
 *              verify -> appears verified -> users -> subscriptions
 *
 * Run:  node <this file>            (expects the API on :8000)
 */
const API = process.env.API_BASE ?? "http://localhost:8000/api/v1";

let passed = 0;
let failed = 0;

function check(name, condition, detail = "") {
  if (condition) {
    passed++;
    console.log(`PASS  ${name}${detail ? ` — ${detail}` : ""}`);
  } else {
    failed++;
    console.log(`FAIL  ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

/** Minimal cookie jar: the backend issues httpOnly access/refresh cookies plus
 *  a readable csrf_token that must be echoed as X-CSRF-Token (double submit). */
function makeSession() {
  return { cookies: new Map() };
}

function cookieHeader(session) {
  return [...session.cookies].map(([k, v]) => `${k}=${v}`).join("; ");
}

function absorb(session, response) {
  for (const raw of response.headers.getSetCookie?.() ?? []) {
    const [pair] = raw.split(";");
    const idx = pair.indexOf("=");
    const name = pair.slice(0, idx).trim();
    const value = pair.slice(idx + 1).trim();
    if (value === "" || value === '""') session.cookies.delete(name);
    else session.cookies.set(name, value);
  }
}

async function call(session, method, path, body, isForm = false) {
  const headers = { Cookie: cookieHeader(session) };
  const csrf = session.cookies.get("csrf_token");
  if (csrf) headers["X-CSRF-Token"] = csrf;
  let payload;
  if (isForm) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const response = await fetch(`${API}${path}`, { method, headers, body: payload });
  absorb(session, response);
  let json = null;
  try {
    json = await response.json();
  } catch {
    /* non-JSON (should not happen on this API) */
  }
  return { status: response.status, json };
}

async function login(email, password) {
  const session = makeSession();
  const res = await call(session, "POST", "/auth/login", { email, password });
  return { session, res };
}

/* ------------------------------------------------------- homeowner journey */

async function homeownerJourney() {
  console.log("\n=== homeowner journey (journey-homeowner.spec.ts) ===");
  const { session, res } = await login("demo@smartdecor.dev", "Demo1234!");
  check("homeowner login 200", res.status === 200, `status=${res.status}`);
  check(
    "session cookies issued (access+refresh+csrf)",
    ["access_token", "refresh_token", "csrf_token"].every((c) => session.cookies.has(c)),
    [...session.cookies.keys()].join(","),
  );

  // Step: the 5-step quiz submits the same payload shape QuizPage.tsx posts.
  const quiz = await call(session, "POST", "/quiz", {
    styles: ["modern"],
    color_palette: ["#E8E2D9"],
    room_width_cm: 400,
    room_length_cm: 500,
    budget_min_toman: 5_000_000,
    budget_max_toman: 80_000_000,
    materials: ["wood"],
    patterns: [],
  });
  check("quiz submit 201/200", [200, 201].includes(quiz.status), `status=${quiz.status}`);
  const quizId = quiz.json?.data?.id;
  check("quiz returns an id", Boolean(quizId), String(quizId));

  // Step: recommendations — the 3-5 per category contract the spec asserts.
  const rec = await call(session, "POST", `/recommend?quiz_id=${quizId}`);
  check("recommend 200", rec.status === 200, `status=${rec.status}`);
  const categories = rec.json?.data?.categories ?? {};
  const names = Object.keys(categories);
  check("recommend returns categories", names.length > 0, `${names.length} categories`);
  for (const name of names) {
    const items = categories[name];
    check(
      `category "${name}" has 3-5 items`,
      items.length >= 3 && items.length <= 5,
      `${items.length} items`,
    );
  }
  // Explanation chips: the spec asserts a "NN% match — why?" button per card,
  // which ProductCard renders from product.explanation + final_score.
  const sample = categories[names[0]]?.[0];
  check(
    "each product carries an explanation breakdown",
    sample &&
      typeof sample.final_score === "number" &&
      sample.explanation &&
      ["style_match", "color_match", "budget_fit", "material_match"].every(
        (k) => k in sample.explanation,
      ),
    sample ? Object.keys(sample.explanation ?? {}).join(",") : "no product",
  );
  check(
    "products carry a price for the shopping list",
    typeof sample?.price_toman === "number" && sample.price_toman > 0,
    String(sample?.price_toman),
  );

  // Step: moodboard create (what MoodboardsPage posts).
  const title = `E2E Board ${Date.now()}`;
  const board = await call(session, "POST", "/moodboards", {
    title,
    items: [{ product_id: sample.id, x: 0, y: 0, w: 4, h: 4 }],
    shopping_list: [sample.id],
  });
  check("moodboard create 201/200", [200, 201].includes(board.status), `status=${board.status}`);
  const boardId = board.json?.data?.id;
  check("moodboard returns an id", Boolean(boardId));

  // Step: the editor reads the board back with its products resolved.
  const fetched = await call(session, "GET", `/moodboards/${boardId}`);
  check("moodboard readable by the editor", fetched.status === 200, `status=${fetched.status}`);
  check(
    "moodboard contains the added item",
    (fetched.json?.data?.items ?? []).some((i) => i.product_id === sample.id),
  );
  check(
    "shopping list resolves products with prices (total is computable)",
    Boolean(fetched.json?.data?.products?.[sample.id]?.price_toman),
    String(fetched.json?.data?.products?.[sample.id]?.price_toman),
  );

  // Step: remove works (the editor PUTs the reduced layout).
  const emptied = await call(session, "PATCH", `/moodboards/${boardId}`, {
    items: [],
    shopping_list: [],
  });
  check("moodboard item removal accepted (PATCH)", [200, 204].includes(emptied.status), `status=${emptied.status}`);

  await call(session, "DELETE", `/moodboards/${boardId}`);

  // Step: logout really revokes the session.
  const out = await call(session, "POST", "/auth/logout", {});
  check("logout 200", out.status === 200, `status=${out.status}`);
  const after = await call(session, "GET", "/moodboards");
  check("session unusable after logout", after.status === 401, `status=${after.status}`);
}

/* -------------------------------------------------------- designer journey */

async function designerJourney() {
  console.log("\n=== designer journey (journey-designer.spec.ts) ===");
  const { session, res } = await login("designer@smartdecor.dev", "Design123!");
  check("designer login 200", res.status === 200, `status=${res.status}`);

  // Clean slate so the quota assertions mean something.
  const existing = await call(session, "GET", "/projects");
  check("projects dashboard readable", existing.status === 200, `status=${existing.status}`);
  for (const p of existing.json?.data ?? []) {
    await call(session, "DELETE", `/projects/${p.id}`);
  }

  const QUOTA = 2; // designer_free limits.projects in seed_data/subscription_plans.json
  const created = [];
  for (let i = 1; i <= QUOTA; i++) {
    const r = await call(session, "POST", "/projects", {
      name: `E2E Project harness-${i}`,
      client_name: "E2E Client",
    });
    check(`create project #${i} -> 201`, r.status === 201, `status=${r.status}`);
    if (r.json?.data?.id) created.push(r.json.data.id);
  }

  const overQuota = await call(session, "POST", "/projects", {
    name: "E2E Project harness-over",
    client_name: "E2E Client",
  });
  check("project beyond quota -> 402", overQuota.status === 402, `status=${overQuota.status}`);
  const message = overQuota.json?.error ?? "";
  check(
    "402 carries the Persian quota message the UI must surface",
    /سهمیهٔ پروژه‌های شما/.test(message),
    message,
  );
  check("nothing created behind the wall", overQuota.json?.data === null);

  const after = await call(session, "GET", "/projects");
  check(
    "project count capped at the quota",
    (after.json?.data ?? []).length === QUOTA,
    `${(after.json?.data ?? []).length} projects`,
  );

  for (const id of created) await call(session, "DELETE", `/projects/${id}`);
}

/* ----------------------------------------------------------- admin journey */

async function adminJourney() {
  console.log("\n=== admin journey (journey-admin.spec.ts) ===");
  const { session, res } = await login("admin@smartdecor.dev", "Admin123!");
  check("admin login 200", res.status === 200, `status=${res.status}`);

  const list = await call(session, "GET", "/products?page=1&page_size=15");
  check("products console data 200", list.status === 200, `status=${list.status}`);
  check("catalogue has rows", (list.json?.data?.items ?? []).length > 0,
    `${list.json?.data?.total} total`);

  // Upload: the same 1x1 PNG the spec feeds the file input.
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64",
  );
  const form = new FormData();
  form.append("file", new Blob([png], { type: "image/png" }), "e2e-product.png");
  const upload = await call(session, "POST", "/products/upload", form, true);
  check("upload -> 201", upload.status === 201, `status=${upload.status}`);
  const extraction = upload.json?.data?.extraction;
  check(
    "AI extraction returns colour / style / material / confidence",
    extraction &&
      ["colors", "style", "material", "confidence"].every((k) => k in extraction),
    extraction ? Object.keys(extraction).join(",") : "none",
  );
  check(
    "confidence is a number the preview can render as a percentage",
    typeof extraction?.confidence === "number",
    String(extraction?.confidence),
  );
  const newId = upload.json?.data?.product?.id;
  check("upload created a draft product", Boolean(newId), String(newId));

  // It lands in the pending queue (human-in-the-loop).
  const pending = await call(session, "GET", "/products?page=1&page_size=15&is_verified=false");
  check(
    "draft appears in the PENDING list",
    (pending.json?.data?.items ?? []).some((p) => p.id === newId),
  );

  // Approve it.
  const verify = await call(session, "POST", `/products/${newId}/verify`);
  check("verify -> 2xx", verify.status < 300, `status=${verify.status}`);

  const verified = await call(session, "GET", "/products?page=1&page_size=100&is_verified=true");
  check(
    "product now appears in the VERIFIED list",
    (verified.json?.data?.items ?? []).some((p) => p.id === newId),
  );

  const users = await call(session, "GET", "/admin/users");
  check("user management 200", users.status === 200, `status=${users.status}`);
  check(
    "seeded demo user listed",
    JSON.stringify(users.json?.data ?? "").includes("demo@smartdecor.dev"),
  );

  const subs = await call(session, "GET", "/admin/subscriptions");
  check("subscription management 200", subs.status === 200, `status=${subs.status}`);

  const taxonomy = await call(session, "GET", "/admin/taxonomy");
  check("style taxonomy readable 200", taxonomy.status === 200, `status=${taxonomy.status}`);
}

/* ---------------------------------------------------------------- runner */

const started = new Date().toISOString();
console.log(`Stage 1 T-1.4 close-out journey protocol harness — ${started}`);
console.log(`API: ${API}`);

await homeownerJourney();
await designerJourney();
await adminJourney();

console.log(`\n---------------------------------------------`);
console.log(`TOTAL: ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
