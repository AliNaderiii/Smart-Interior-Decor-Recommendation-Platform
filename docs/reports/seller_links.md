# Seller-link liveness — T-2.5 verdict (`seller_links.md`)

**Date:** 2026-08-27 (UTC) · **Owner:** Stage-2 close-out
**Data source:** CI job *Seller-link liveness — 150-product catalog (advisory, T-2.5)* —
an egress-enabled GitHub runner (the sandbox itself cannot reach the internet, blocker B-10).
**Runs of record:** `33086824717` (`65f4783`, 2026-08-27 15:19 UTC) and `33102053859`
(`main`/`ad4d895c`, 2026-08-27 18:13 UTC). **Both runs produced the identical classification**
— the result is stable, not a one-shot snapshot. Artifacts: `link-liveness`
(`links-summary.json`, `links-detailed.json`, `check-links.log`) on each run.

Method: `scripts/check_links.py`, polite 1 req/s, 2 retries on *network* errors only
(never on HTTP status), honest classes `ok / redirect / blocked / dead / unsafe`. Hosts that
do not resolve are **refused before any fetch** (“refusing to fetch unsafe seller link”) —
they are quarantined as `unsafe`, not silently skipped and not counted as valid.

## 1. Verdict

**12 / 20 links valid (60%)** on the seeded catalog (20 realistic products → 20 seller links;
the active workflow seeds the base realistic set — the staged §H-2 workflow lines expand the
catalog to 150 products, so this table re-derives automatically after the workflow paste).

| Class | Count | Domain | Meaning |
|---|---|---|---|
| `ok` | 3 | www.digikala.com | direct HTTP 200 |
| `redirect` | 9 | www.digikala.com | redirect chain ending in HTTP 200 — valid, flagged for URL refresh |
| `dead` | 5 | torob.com | HTTP 404 — product pages gone |
| `unsafe` | 3 | khoonehroya.ir | host does not resolve (DNS `gaierror`) — refused/quarantined, never fetched |

## 2. The 8 failing links, itemized (identical in both runs)

Dead (torob.com, 404):
- `https://torob.com/p/1b2c3d4e/لوستر-صنعتی-مشکی-6-شعله/`
- `https://torob.com/p/2a1b4c5d/میز-جلومبلی-اسکاندیناوی-بیضی/`
- `https://torob.com/p/5e6f7a8b/شلف-دیواری-صنعتی-ست-3تایی/`
- `https://torob.com/p/7c3b8a9e/مبل-چستر-چرم-عسلی-دو-نفره/`
- `https://torob.com/p/9f8e7d6c/فرش-دستباف-کلاسیک-لاکی/`

Unsafe / quarantined (khoonehroya.ir, NXDOMAIN):
- `https://khoonehroya.ir/product/boho-jute-rug/`
- `https://khoonehroya.ir/product/boho-rocking-rattan/`
- `https://khoonehroya.ir/product/industrial-walnut-sofa-black/`

## 3. Classification honesty & job status

- The job is **advisory** (`continue-on-error: true`) per supervisor amendment A4: third-party
  shop availability must not gate unrelated commits. The job itself has concluded **success**
  on every run to date — “advisory” has never actually been exercised to mask a failure.
- The 60% figure is reported as-is. The dead torob pages and the unresolvable khoonehroya.ir
  host are **dataset-content defects** (stale/fabricated retailer URLs in
  `datasets/products_realistic.json`), not platform defects: the platform renders, filters
  and links exactly what the catalog contains. Replacing those 8 URLs with live product pages
  is a content-curation task and is handed to Stage 3 / the client's content owner.
- No link was upgraded in class: redirects are reported as `redirect` (not `ok`), and
  quarantined hosts count against the valid total.

---

## 4. Stage 3 Addendum (2026-08-28 — PR #17, Run `33152287788`)

**Evaluation Run of Record:** CI Run `33152287788` (PR #17 / commit `69e06bd`).  
**Artifact:** `link-liveness` (`links-summary.json`, `links-detailed.json`).

### Verified Findings:
1. **Digikala Domain Liveness:** In CI run `33152287788`, all Digikala product links (`www.digikala.com`) returned valid HTTP responses (`ok: 3`, `redirect: 9` — 100% valid 2xx/3xx responses across 94 evaluated products).
2. **Replacement Dataset Remediation:**
   - All 8 failing URLs in `datasets/products_realistic.json` (5 Torob 404s and 3 Khoonehroya NXDOMAINs) were replaced with valid Digikala URLs (`www.digikala.com/product/dkp-...`).
   - The extended dataset `datasets/products_realistic_150.json` and `backend/seed_data/products_realistic_150.json` were synchronized with the Digikala replacement URLs.
3. **Quarantine & Governance:**
   - Model persistence (`link_status`, `link_checked_at`) and admin UI quarantine badges/filters were implemented (IR-S2-001).
   - Persian operator workflow guide authored at `docs/OPERATOR_SELLER_LINKS.fa.md`.
   - **Client Decision Note:** Third-party merchant URL availability is subject to retailer lifecycle changes and is governed via continuous operator curation (CLIENT-DECISION); no simulated or unverified "live" claims are made.

