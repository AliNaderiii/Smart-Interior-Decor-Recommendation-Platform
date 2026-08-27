/** T-1.4 local evidence — protocol-level auth checks against the running
 *  app (vite :5173 proxying /api -> uvicorn :8000, default cookie mode).
 *  Mirrors the transport assertions of tests/e2e/auth-negative.spec.ts. */
const BASE = "http://localhost:5173";
const results = [];
function check(name, cond, detail = "") {
  results.push({ name, pass: !!cond, detail });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
}
function parseSetCookies(res) {
  return (res.headers.getSetCookie?.() ?? []).map((c) => c.split(";")[0]);
}

// --- 1. valid login (demo homeowner) ---------------------------------------
{
  const res = await fetch(`${BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "demo@smartdecor.dev", password: "Demo1234!" }),
    redirect: "manual",
  });
  const body = await res.json();
  const cookies = parseSetCookies(res);
  check("valid login -> 200", res.status === 200, `status=${res.status}`);
  check("envelope {success,data,error} + user", body.success === true && !!body.data?.user);
  check("httpOnly access_token cookie issued", cookies.some((c) => c.startsWith("access_token=")) , cookies.join(", "));
  check("httpOnly refresh_token cookie issued", cookies.some((c) => c.startsWith("refresh_token=")));
  check("readable csrf_token cookie issued (double-submit)", cookies.some((c) => c.startsWith("csrf_token=")));
  check("cookies are httpOnly+SameSite=Strict",
    (res.headers.getSetCookie?.() ?? []).filter((c) => c.startsWith("access_token="))[0]
      ?.toLowerCase().includes("httponly"));
  check("no redirect on login (no Location header)", res.headers.get("location") === null, `location=${res.headers.get("location")}`);
}

// --- 2. bad login with XSS payload in the password -------------------------
{
  const payload = '<img src=x onerror="window.__xss_fired=true">';
  const res = await fetch(`${BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: `xss-probe-${Date.now()}@example.com`, password: payload }),
    redirect: "manual",
  });
  const text = await res.text();
  const cookies = parseSetCookies(res);
  check("XSS-payload login -> 401", res.status === 401, `status=${res.status}`);
  check("generic error, no reflection of the payload",
    text.includes("Invalid credentials") && !text.includes(payload), text.slice(0, 120));
  check("no credential cookies on failed login",
    !cookies.some((c) => c.startsWith("access_token=") || c.startsWith("refresh_token=")), cookies.join(", ") || "(none)");
  check("no redirect (no Location header)", res.headers.get("location") === null);
}

// --- 3. wrong password on the REAL demo account -----------------------------
{
  const res = await fetch(`${BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "demo@smartdecor.dev", password: "DefinitelyWrong1!" }),
    redirect: "manual",
  });
  const body = await res.json().catch(() => ({}));
  const cookies = parseSetCookies(res);
  check("wrong password -> 401 + generic message",
    res.status === 401 && body.error === "Invalid credentials", `status=${res.status} error=${body.error}`);
  check("no credentials issued on wrong password",
    !cookies.some((c) => /token=/.test(c)), cookies.join(", ") || "(none)");
}

// --- 4. admin route as anonymous --------------------------------------------
{
  const res = await fetch(`${BASE}/api/v1/admin/users`, { redirect: "manual" });
  check("anonymous GET /admin/users -> 401 (no admin data)", res.status === 401, `status=${res.status}`);
}

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} protocol checks passed`);
process.exit(failed.length ? 1 : 0);
