#!/usr/bin/env node
/**
 * Authenticated Lighthouse matrix — Stage 2, T-2.1 (supervisor amendment A3).
 *
 * WHY THIS EXISTS: /recommendations (and every other authed route) is wrapped
 * in <RequireAuth>, so an anonymous Lighthouse run measures the /login
 * redirect, not the page (Stage-1 waiver IR-S1-010 numbers for that URL were
 * wrong-page artifacts). This script measures REAL content:
 *
 *   1. launches Chrome (chrome-launcher),
 *   2. seeds the REAL cookie jar over CDP (Network.setCookie) with the
 *      access/refresh/csrf cookies from an API login — the SPA then behaves
 *      exactly as for a logged-in user, including reading the JS-visible
 *      csrf_token cookie and echoing it as X-CSRF-Token on POST /recommend
 *      (an --extra-headers Cookie: pass-through would NOT populate
 *      document.cookie and the in-page CSRF echo would break),
 *   3. runs Lighthouse (node API, same Chrome, disableStorageReset so the
 *      session survives) for each page x {mobile, desktop},
 *   4. FAKE-COVERAGE GUARD: fails hard if any authed page ends up on /login,
 *   5. asserts the contract gates and writes JSON+HTML per cell + summary.
 *
 * DIAGNOSABILITY (hardened after run 33075250048): the sandbox supervising
 * this pipeline cannot download job logs or artifacts (Azure blob egress is
 * blocked) — GitHub check-run ANNOTATIONS are the only readable channel. So:
 *   - every failure path emits ::error:: (including import/launch failures:
 *     libraries are imported dynamically inside the guarded main),
 *   - progress breadcrumbs are written to $LH_OUT_DIR/progress.log,
 *   - the final summary is also emitted as a ::notice:: annotation.
 *
 * Env: LH_BASE_URL, LH_ACCESS_TOKEN, LH_REFRESH_TOKEN, LH_CSRF_TOKEN,
 *      LH_QUIZ_ID, LH_OUT_DIR (default ./lighthouse-matrix)
 *
 * Gates asserted here (job-level continue-on-error stays until T-2.6):
 *   /                          : perf >= 80, LCP < 3000 ms, TTI <= 4000 ms  (IR-S1-010)
 *   /recommendations?quiz=<id> : perf >= 80, LCP < 3000 ms                  (contract)
 *   other pages                : measured + guarded, reported, no threshold.
 */
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.LH_BASE_URL || 'http://127.0.0.1:4173';
const OUT = process.env.LH_OUT_DIR || './lighthouse-matrix';
const QUIZ_ID = process.env.LH_QUIZ_ID || '';

// Boot marker BEFORE anything that can fail: the artifact dir must exist even
// when the run dies immediately, so the uploaded artifact carries the trail.
fs.mkdirSync(OUT, { recursive: true });
const progressPath = path.join(OUT, 'progress.log');
function progress(msg) {
  const line = `${new Date().toISOString()} ${msg}`;
  console.log(line);
  fs.appendFileSync(progressPath, line + '\n');
}
function emitError(msg) {
  // Single-line: GitHub annotations truncate on raw newlines.
  const flat = String(msg).replace(/\s*\n\s*/g, ' | ').slice(0, 2000);
  console.error(`::error title=lighthouse-matrix::${flat}`);
  progress(`ERROR ${flat}`);
  return flat;
}
progress(`boot node=${process.version} base=${BASE} quiz=${QUIZ_ID ? 'set' : 'MISSING'}`);

const COOKIES = [
  { name: 'access_token', value: process.env.LH_ACCESS_TOKEN, httpOnly: true },
  { name: 'refresh_token', value: process.env.LH_REFRESH_TOKEN, httpOnly: true },
  { name: 'csrf_token', value: process.env.LH_CSRF_TOKEN, httpOnly: false },
];

const PAGES = [
  { slug: 'home', url: '/', auth: false,
    gates: { perf: 80, lcpMs: 3000, ttiMs: 4000 } },
  { slug: 'login', url: '/login', auth: false, gates: null },
  { slug: 'quiz', url: '/quiz', auth: true, gates: null },
  { slug: 'recommendations', url: `/recommendations?quiz=${QUIZ_ID}`, auth: true,
    gates: { perf: 80, lcpMs: 3000 } },
  { slug: 'moodboards', url: '/moodboards', auth: true, gates: null },
  { slug: 'shopping-list', url: '/shopping-list', auth: true, gates: null },
];

// Desktop settings inlined (not the deep import) so a packaging change in the
// lighthouse module tree cannot take the whole matrix down; values mirror
// lighthouse/core/config/desktop-config.js @ v12.
const DESKTOP_CONFIG = {
  extends: 'lighthouse:default',
  settings: {
    formFactor: 'desktop',
    screenEmulation: { mobile: false, width: 1350, height: 940, deviceScaleFactor: 1, disabled: false },
    throttling: { rttMs: 40, throughputKbps: 10240, cpuSlowdownMultiplier: 1, requestLatencyMs: 0, downloadThroughputKbps: 0, uploadThroughputKbps: 0 },
    emulatedUserAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.0 Safari/537.36 Chrome-Lighthouse',
  },
};

async function main() {
  for (const c of COOKIES) {
    if (!c.value) throw new Error(`missing env for cookie ${c.name} (GITHUB_ENV propagation?)`);
  }
  if (!QUIZ_ID) throw new Error('missing LH_QUIZ_ID (GITHUB_ENV propagation?)');
  progress('env ok');

  // Dynamic imports INSIDE the guarded main: a resolution failure becomes an
  // annotated ::error:: instead of a silent module-load crash.
  const { default: lighthouse } = await import('lighthouse');
  const { launch } = await import('chrome-launcher');
  const { default: puppeteer } = await import('puppeteer-core');
  progress('imports ok');

  const chrome = await launch({
    chromeFlags: ['--headless', '--no-sandbox', '--disable-dev-shm-usage'],
  });
  progress(`chrome launched pid=${chrome.pid} port=${chrome.port} path=${chrome.process?.spawnfile || 'n/a'}`);

  const browser = await puppeteer.connect({
    browserURL: `http://127.0.0.1:${chrome.port}`, defaultViewport: null,
  });
  progress('puppeteer connected');

  // Seed the real cookie jar via CDP for the preview origin.
  const page = await browser.newPage();
  const cdp = await page.createCDPSession();
  for (const c of COOKIES) {
    await cdp.send('Network.setCookie', {
      name: c.name, value: c.value, url: BASE, httpOnly: c.httpOnly,
      sameSite: 'Strict', path: '/',
    });
  }
  progress('cookies set');

  // The probe fetch must run FROM the app origin: on about:blank the page
  // origin is "null" and fetch(BASE/api/...) is a cross-origin request the
  // API will not answer with CORS headers for -> "TypeError: Failed to fetch"
  // (exactly run 33076489388's failure). /login is public, so this navigation
  // cannot itself depend on the session being probed.
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  progress('navigated to app origin');

  // Session sanity probe THROUGH the preview proxy before measuring anything.
  const me = await page.evaluate(async (base) => {
    const r = await fetch(`${base}/api/v1/auth/me`, { credentials: 'include' });
    return { status: r.status, body: (await r.text()).slice(0, 2000) };
  }, BASE);
  if (me.status !== 200) {
    throw new Error(`session probe /api/v1/auth/me returned ${me.status}: ${me.body}`);
  }
  progress(`session probe ok status=${me.status}`);

  // Run 33077288932 root cause: RequireAuth is SYNCHRONOUS on the zustand
  // auth store, which rehydrates `user` from localStorage["sd_auth"]
  // (persist middleware, profile-only partialize). Cookies alone are not
  // enough — a fresh Lighthouse page has user===null and <Navigate to=/login>
  // fires before any cookie is consulted. Seed the exact persist envelope
  // from the app origin; localStorage is NOT in Lighthouse v12's default
  // clearStorageTypes (file_systems/shader_cache/service_workers/
  // cache_storage) and disableStorageReset is set besides, so it survives
  // every navigation. The csrf_token cookie keeps usingCookieAuth() true.
  const envelope = me.body ? JSON.parse(me.body) : null;
  const user = envelope && envelope.data ? envelope.data : null;
  if (!user || !user.id) {
    throw new Error(`session probe returned no user profile: ${me.body.slice(0, 300)}`);
  }
  await page.evaluate((u) => {
    localStorage.setItem('sd_auth', JSON.stringify({ state: { user: u }, version: 0 }));
  }, user);
  progress(`auth store seeded user id=${user.id} role=${user.role || 'n/a'}`);
  await page.close();

  const summary = [];
  const failures = [];

  // Directive 4 R1/R4 instrumentation: artifact downloads are egress-blocked
  // for the operating sandbox (302 -> Azure blob), so the diagnosis the
  // supervisor requires — LCP element, phase breakdown, slowest requests,
  // long tasks, console-error identity — is pushed out through annotations.
  // network-requests durations are OBSERVED (unthrottled) times from the
  // trace, i.e. the real in-job latency split; the LCP phases are simulated
  // and sum to the reported LCP.
  const consoleErrs = new Map(); // identity -> cells seen in
  const diagNotes = [];
  const apiLatency = [];
  const collectDiag = (lhr, slug, ff) => {
    const cell = `${slug}/${ff}`;
    for (const it of lhr.audits['errors-in-console']?.details?.items ?? []) {
      const key = `${(it.description || it.source || 'unknown').replace(/\s+/g, ' ').slice(0, 140)} @ ${(it.sourceLocation?.url || it.url || '?').slice(0, 80)}`;
      if (!consoleErrs.has(key)) consoleErrs.set(key, []);
      consoleErrs.get(key).push(cell);
    }
    const requests = (lhr.audits['network-requests']?.details?.items ?? []).map((r) => ({
      url: r.url || '',
      dur: Math.round((r.networkEndTime ?? 0) - (r.networkRequestTime ?? 0)),
      kb: Math.round((r.transferSize ?? 0) / 1024),
      type: r.resourceType || '',
    }));
    for (const r of requests) {
      if (r.url.includes('/api/v1/recommend')) apiLatency.push(`${cell}: ${r.dur}ms`);
    }
    if (slug !== 'recommendations' || ff !== 'mobile') return;
    const lcpEl = lhr.audits['largest-contentful-paint-element']?.details?.items ?? [];
    const node = lcpEl[0]?.items?.[0]?.node;
    const phases = (lcpEl[1]?.items ?? [])
      .map((i) => `${i.phase}=${Math.round(i.timing)}ms`).join(' ');
    const nodeTxt = node
      ? (node.snippet || node.selector || '').replace(/\s+/g, ' ').slice(0, 220)
      : 'n/a';
    diagNotes.push(`node=${nodeTxt} ;; phases: ${phases || 'n/a'}`);
    const slowest = [...requests].sort((a, b) => b.dur - a.dur).slice(0, 5)
      .map((r) => `${r.url.replace(/^https?:\/\//, '').slice(0, 80)} ${r.dur}ms ${r.kb}KB ${r.type}`);
    const tasks = (lhr.audits['long-tasks']?.details?.items ?? []).slice(0, 5)
      .map((t) => `${(t.url || '?').replace(/^https?:\/\//, '').slice(0, 60)} ${Math.round(t.duration)}ms`);
    diagNotes.push(`slowest5: ${slowest.join(' | ') || 'n/a'} ;; longtasks: ${tasks.join(' | ') || 'n/a'}`);
  };

  for (const p of PAGES) {
    for (const ff of ['mobile', 'desktop']) {
      const url = BASE + p.url;
      progress(`measuring ${p.slug} [${ff}]`);
      const opts = {
        port: chrome.port, output: ['json', 'html'], logLevel: 'error',
        disableStorageReset: true,           // keep the seeded session
        onlyCategories: ['performance', 'accessibility', 'best-practices'],
      };
      const config = ff === 'desktop' ? DESKTOP_CONFIG : undefined; // default = mobile, simulated Slow-4G throttling
      const result = await lighthouse(url, opts, config);
      const lhr = result.lhr;
      const finalUrl = lhr.finalDisplayedUrl || lhr.finalUrl || '';

      const base = path.join(OUT, `${p.slug}.${ff}`);
      fs.writeFileSync(`${base}.report.json`, result.report[0]);
      fs.writeFileSync(`${base}.report.html`, result.report[1]);

      const row = {
        page: p.slug, formFactor: ff, requestedUrl: url, finalUrl,
        perf: Math.round((lhr.categories.performance?.score ?? 0) * 100),
        a11y: Math.round((lhr.categories.accessibility?.score ?? 0) * 100),
        lcpMs: Math.round(lhr.audits['largest-contentful-paint']?.numericValue ?? -1),
        ttiMs: Math.round(lhr.audits['interactive']?.numericValue ?? -1),
        clsX1000: Math.round((lhr.audits['cumulative-layout-shift']?.numericValue ?? -1) * 1000),
        consoleErrorsScore: lhr.audits['errors-in-console']?.score,
        runWarnings: lhr.runWarnings,
      };
      summary.push(row);
      progress(JSON.stringify(row));
      collectDiag(lhr, p.slug, ff);

      // Fake-coverage guard: an authed page redirected to /login is a wrong-page
      // measurement and must never be reported as coverage (amendment A3).
      if (p.auth && /\/login/.test(finalUrl)) {
        failures.push(emitError(`${p.slug} [${ff}] measured the LOGIN REDIRECT (finalUrl=${finalUrl}) — invalid coverage`));
        continue;
      }
      if (p.gates) {
        if (row.perf < p.gates.perf) {
          failures.push(emitError(`${p.slug} [${ff}] perf ${row.perf} < ${p.gates.perf}`));
        }
        if (p.gates.lcpMs && row.lcpMs >= p.gates.lcpMs) {
          failures.push(emitError(`${p.slug} [${ff}] LCP ${row.lcpMs}ms >= ${p.gates.lcpMs}ms`));
        }
        if (p.gates.ttiMs && row.ttiMs > p.gates.ttiMs) {
          failures.push(emitError(`${p.slug} [${ff}] TTI ${row.ttiMs}ms > ${p.gates.ttiMs}ms`));
        }
      }
    }
  }

  await browser.disconnect();
  chrome.kill();

  fs.writeFileSync(path.join(OUT, 'summary.json'), JSON.stringify({
    generatedUtc: new Date().toISOString(),
    baseUrl: BASE, pages: PAGES.map(p => p.url), summary, failures,
  }, null, 2));

  console.log('\n| page | ff | perf | LCP ms | TTI ms | CLS/1000 | finalUrl |');
  console.log('|---|---|---|---|---|---|---|');
  for (const r of summary) {
    console.log(`| ${r.page} | ${r.formFactor} | ${r.perf} | ${r.lcpMs} | ${r.ttiMs} | ${r.clsX1000} | ${r.finalUrl} |`);
  }

  // Annotation-readable numbers (the only channel the sandbox can consume).
  const compact = summary.map(r =>
    `${r.page}/${r.formFactor}: perf=${r.perf} lcp=${r.lcpMs} tti=${r.ttiMs} cls1000=${r.clsX1000}`).join(' ;; ');
  console.log(`::notice title=lighthouse-matrix-summary::${compact.slice(0, 2000)}`);

  // Directive 4 R1 diagnosis + R2(2) API split + R4 console-error identity.
  if (diagNotes[0]) console.log(`::notice title=lcp-element-phases::${diagNotes[0].slice(0, 2000)}`);
  if (diagNotes[1]) console.log(`::notice title=lcp-network-longtasks::${diagNotes[1].slice(0, 2000)}`);
  if (apiLatency.length) console.log(`::notice title=recommend-api-observed::${apiLatency.join(' ;; ').slice(0, 1500)}`);
  if (consoleErrs.size) {
    const errsTxt = [...consoleErrs]
      .map(([k, cells]) => `${k} [${cells.length} cell(s): ${cells.slice(0, 3).join(',')}${cells.length > 3 ? ',…' : ''}]`)
      .join(' ;; ');
    console.log(`::notice title=console-errors::${errsTxt.slice(0, 2000)}`);
  }

  if (failures.length) {
    console.error(`\n${failures.length} gate failure(s).`);
    process.exit(1);
  }
  console.log('\nAll asserted gates passed.');
}

main().catch((e) => {
  emitError(e && e.stack ? e.stack : e);
  process.exit(1);
});
