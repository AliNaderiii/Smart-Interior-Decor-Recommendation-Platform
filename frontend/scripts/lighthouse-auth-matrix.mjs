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
import lighthouse from 'lighthouse';
import desktopConfig from 'lighthouse/core/config/desktop-config.js';
import { launch } from 'chrome-launcher';
import puppeteer from 'puppeteer-core';

const BASE = process.env.LH_BASE_URL || 'http://127.0.0.1:4173';
const OUT = process.env.LH_OUT_DIR || './lighthouse-matrix';
const QUIZ_ID = process.env.LH_QUIZ_ID || '';
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

function fail(msg) { console.error(`::error::${msg}`); return msg; }

async function main() {
  for (const c of COOKIES) {
    if (!c.value) throw new Error(`missing env for cookie ${c.name}`);
  }
  if (!QUIZ_ID) throw new Error('missing LH_QUIZ_ID');
  fs.mkdirSync(OUT, { recursive: true });

  const chrome = await launch({
    chromeFlags: ['--headless=new', '--no-sandbox', '--disable-dev-shm-usage'],
  });
  const browser = await puppeteer.connect({
    browserURL: `http://127.0.0.1:${chrome.port}`, defaultViewport: null,
  });

  // Seed the real cookie jar via CDP for the preview origin.
  const page = await browser.newPage();
  const cdp = await page.createCDPSession();
  for (const c of COOKIES) {
    await cdp.send('Network.setCookie', {
      name: c.name, value: c.value, url: BASE, httpOnly: c.httpOnly,
      sameSite: 'Strict', path: '/',
    });
  }
  // Session sanity probe THROUGH the preview proxy before measuring anything.
  const me = await page.evaluate(async (base) => {
    const r = await fetch(`${base}/api/v1/auth/me`, { credentials: 'include' });
    return { status: r.status, body: (await r.text()).slice(0, 200) };
  }, BASE);
  if (me.status !== 200) {
    throw new Error(fail(`session probe /api/v1/auth/me returned ${me.status}: ${me.body}`));
  }
  console.log('session probe OK:', me.body);
  await page.close();

  const summary = [];
  const failures = [];

  for (const p of PAGES) {
    for (const ff of ['mobile', 'desktop']) {
      const url = BASE + p.url;
      const opts = {
        port: chrome.port, output: ['json', 'html'], logLevel: 'error',
        disableStorageReset: true,           // keep the seeded session
        onlyCategories: ['performance', 'accessibility', 'best-practices'],
      };
      const config = ff === 'desktop' ? desktopConfig : undefined; // default = mobile, simulated Slow-4G throttling
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
        runWarnings: lhr.runWarnings,
      };
      summary.push(row);
      console.log(JSON.stringify(row));

      // Fake-coverage guard: an authed page redirected to /login is a wrong-page
      // measurement and must never be reported as coverage (amendment A3).
      if (p.auth && /\/login/.test(finalUrl)) {
        failures.push(fail(`${p.slug} [${ff}] measured the LOGIN REDIRECT (finalUrl=${finalUrl}) — invalid coverage`));
        continue;
      }
      if (p.gates) {
        if (row.perf < p.gates.perf) {
          failures.push(fail(`${p.slug} [${ff}] perf ${row.perf} < ${p.gates.perf}`));
        }
        if (p.gates.lcpMs && row.lcpMs >= p.gates.lcpMs) {
          failures.push(fail(`${p.slug} [${ff}] LCP ${row.lcpMs}ms >= ${p.gates.lcpMs}ms`));
        }
        if (p.gates.ttiMs && row.ttiMs > p.gates.ttiMs) {
          failures.push(fail(`${p.slug} [${ff}] TTI ${row.ttiMs}ms > ${p.gates.ttiMs}ms`));
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

  if (failures.length) {
    console.error(`\n${failures.length} gate failure(s).`);
    process.exit(1);
  }
  console.log('\nAll asserted gates passed.');
}

main().catch((e) => { console.error(e); process.exit(1); });
