# Release Checklist

Baseline: `f97bfad` · Owner of this document: Baseline & Release Governance (Master Prompt 01).

**Rule of the gate:** a box may only be ticked by pasting the command **and** its
output into `docs/agent-reports/<stage>-evidence/`. A tick without evidence is a
governance failure, not a pass. Status below is the measured state at `f97bfad`
(2026-08-21) — see `docs/RELEASE_BASELINE.md` §5.

Legend: `[x]` verified · `[!]` verified FAILING · `[ ]` not verified / blocked.

---

## A. Repository hygiene

- [x] Working tree clean before the release commit — `git status --porcelain`
- [x] No secrets, tokens, keys or credentials in tracked files — `python scripts/audit_secrets.py` → 0 findings across 244 files
- [x] No forbidden tracked paths (`.env`, `*.pem`, `*.sqlite3`, `dist/`, `node_modules/`) — 0
- [x] No oversized tracked artifacts (>2 MiB) — 0 (largest tracked file: 149 KiB)
- [x] `.gitignore` covers venvs, caches, build output, Playwright output, key material and local DBs
- [x] `.env.example` documents every variable with required/optional status and safe placeholders
- [x] No tracked file was accidentally ignored by a `.gitignore` change — `git ls-files | git check-ignore --stdin` → empty
- [ ] Baseline tag created and pushed — **no tags exist**; see `docs/ROLLBACK_AND_VERSIONING.md`
- [ ] `CHANGELOG.md` exists — **absent**

## B. Documentation integrity

- [x] Documentation link audit — `python scripts/audit_docs_links.py` → 0 broken markdown links
- [!] File-reference audit → **5 missing references** (`embeddings_real.json` ×3, `.env.example.v2` ×2) — IR-003
- [x] `README.md` test counts match a measured run at HEAD
- [!] `docs/reports/*`, `docs/RESEARCH_V2.md`, `docs/WALKTHROUGH.md`, `ci/README.md` still assert 43/45 tests — IR-003
- [x] Every performance / AI number is labelled MOCK, LOCAL, STAGING or PRODUCTION
- [!] `docs/API.md` omits `/feedback` (3 operations) and `/health` — IR-003
- [x] Baseline document exists and is linked from `README.md`

## C. Build & dependencies

- [x] Backend deps install from a clean venv — `pip install -r backend/requirements.txt` → exit 0
- [x] Frontend deps install from the lockfile — `npm ci` → exit 0, 163 packages
- [x] Frontend strict build — `npm run build` (`tsc -b && vite build`) → exit 0, 0 TS errors
- [x] Frontend lint — `npm run lint` → 0 errors (12 warnings)
- [!] Backend lint — `ruff check app ai scripts` → **exit 1, 3 errors** — IR-002 (**CI-breaking**)
- [!] Python dependencies pinned/locked — **not pinned**, all `>=` ranges, no constraints file — IR-009
- [x] Frontend dependencies locked — `package-lock.json` present and honoured by `npm ci`

## D. Tests

- [x] Backend suite green on the dev fallback — **97 passed** (SQLite + fakeredis + mock AI)
- [ ] Backend suite green on **PostgreSQL 16 + pgvector** — blocked (BL-1), last evidenced 2026-08-19 @ `a847ad5` with 45 tests
- [ ] Backend suite green on **real Redis** — blocked (BL-2)
- [ ] Frontend unit tests — **no test runner and no `npm test` script exist** — IR-007
- [ ] Playwright E2E (`deadKeys.spec.ts`) — blocked (BL-7), no browsers, no wired script
- [x] Static dead-keys audit — `npx tsx scripts/auditDeadKeys.ts` → 0 DEAD, 0 PARTIAL
- [ ] Three-role E2E + paywall journey — not executed at HEAD
- [ ] Migration test: empty DB → `alembic upgrade head` → seed → restart → downgrade — blocked on Postgres; **fails on SQLite** (B-7)

## E. Security

- [x] Secret scan clean at HEAD
- [x] Unauthenticated access to a protected route is refused — `GET /api/v1/products` → 401
- [x] Security headers present on every response incl. errors — CSP, HSTS-equivalents, `X-Frame-Options: DENY`, `nosniff`, Referrer-Policy, Permissions-Policy, COOP, CORP
- [x] Production config fail-fast exists — `Settings.validate_runtime()` rejects default/short `SECRET_KEY`, empty `REDIS_URL`, `COOKIE_SECURE=false`
- [!] **Demo accounts are seeded unconditionally, including under `APP_ENV=production`** — B-1 / IR-001
- [!] Python dependency CVE — `ecdsa 0.19.2` `PYSEC-2026-1325`, **no fix available** — IR-008
- [x] npm dependency CVEs — 0
- [ ] TLS 1.3 verified against a running Caddy — blocked (no Docker)
- [ ] Penetration / OWASP re-probe at HEAD — last run 2026-08-20 @ `ebfec13`

## F. Data & AI evidence

- [x] Offline embedding backend sanity — `hash`, 512-dim, <10 s
- [x] Extraction benchmark in **MOCK** mode — 50 images, 100%
- [ ] Extraction benchmark in **REAL** mode ≥80% — blocked (BL-3), needs C-1
- [ ] Real CLIP embeddings generated and seeded — blocked (BL-4)
- [ ] Seller links 200 OK — blocked (BL-5); local run returned 0/100 due to blocked egress
- [x] Dataset provenance disclosed (150 rows = deterministic expansion of 20 curated rows)
- [ ] Client's real catalog imported — needs C-5

## G. Performance

- [ ] `/recommend` p95 <2 s on **Postgres + pgvector** at HEAD — last evidenced 2026-08-19 @ `a847ad5` (p95 1625 ms)
- [ ] Lighthouse ≥80 and LCP <3 s — blocked (BL-6), no Chrome
- [x] JS budget respected by the build — largest eager chunk 221 KB raw / 70.8 KB gzip; budget 350 KB script

## H. Release mechanics

- [ ] CI active in `.github/workflows/` and green — **CI has never run** (B-2)
- [ ] All required status checks configured as branch protection on `v2-strict-mode`
- [ ] SemVer tag applied to the release commit
- [ ] Rollback point identified and documented — see `docs/ROLLBACK_AND_VERSIONING.md` §4
- [ ] `main` reconciled with `v2-strict-mode` (currently 7 commits behind)
- [x] PR opened against the designated integration branch, not merged by the authoring agent

---

## Gate summary at `f97bfad`

| Section | Verified | Failing | Not verified |
|---|---:|---:|---:|
| A. Hygiene | 7 | 0 | 2 |
| B. Documentation | 4 | 3 | 0 |
| C. Build & deps | 5 | 2 | 0 |
| D. Tests | 2 | 0 | 6 |
| E. Security | 5 | 2 | 2 |
| F. Data & AI | 3 | 0 | 4 |
| G. Performance | 1 | 0 | 2 |
| H. Release mechanics | 1 | 0 | 5 |
| **Total** | **28** | **7** | **21** |

**A release must not be cut while any item in section E is failing.**
