# CONTINUATION PROMPT FOR NEW AGENT - V2 STRICT MODE PHASE 0B -> PHASE 5
# Use this as the FIRST prompt for your NEW agent after handover

---

## CONTEXT: YOU ARE CONTINUING A PROJECT, NOT STARTING FROM ZERO

You are Agent #2, taking over from Agent #1 who completed Phase 0A and started Phase 0B then hit token limit and stopped responding.

**What Agent #1 already did (DO NOT REDO, just verify):**

1.  **Built MVP v1.0** in repo `arena/01a01bbd-smart-interior-decor-recommend`:
    - Monorepo: /backend (FastAPI + Postgres+pgvector + 45 tests green on both SQLite & Postgres), /frontend (React 19 + TS 0 errors, 3 portals), docker-compose.yml, Caddy TLS 1.3, docs/
    - Features: 5-step quiz, explainable recommendations (p95 1.63s on Postgres @100 conc), moodboard drag, 2D floorplan with collision, shopping list fa-IR, designer B2B2C share via secrets.token_urlsafe(32), admin human-in-the-loop with tri-color confidence
    - Security: JWT rotation + Redis blacklist + bcrypt $2b$ + GDPR DELETE, rate limiter 20/min on /recommend, Fernet KMS abstraction
    - Perf: 107KB gzip initial, WebP, lazy, code splitting

2.  **Started V2 Strict Mode Phase 0A** (you must verify file exists):
    - File `docs/RESEARCH_V2.md` with +131 lines exists - contains research on Houzz, Havenly, Modsy, Decorilla, Wayfair, Linear, etc. with "What to steal"
    - If file exists and has 12 platforms: SKIP research, use it. If not exists or <50 lines: Redo Phase 0A quickly by web searching those 12 platforms and writing docs/RESEARCH_V2.md with for each: URL, 3 UX takeaways, 1 thing to steal.

3.  **Started Phase 0B - Brutal Audit**:
    - Last log: "Now live security probes against the running API — IDOR, CORS, headers, brute-force: Ran commands 2"
    - Means Agent #1 was crawling dead keys and running live curl probes but didn't commit results.

**Your starting point: CONTINUE Phase 0B from where it stopped.**

---

## YOUR MISSION NOW - PHASE 0B TO PHASE 5 STRICT MODE

You have the full V2 Strict Mode requirements in file `ADVANCED_MASTER_PROMPT_V2.md` (attached or in repo). Read it fully before coding.

But to save time, here is your prioritized execution order:

### IMMEDIATE (Next 30 min): Finish Phase 0B Audit & Commit

**1. Verify RESEARCH_V2.md exists:**
```bash
ls -lh docs/RESEARCH_V2.md
wc -l docs/RESEARCH_V2.md
# Should be ~131+ lines. If <50 lines, redo it quickly via web search
```

**2. Create the Dead Keys Audit Script:**
Create `scripts/auditDeadKeys.ts` with content from `PHASE0_AUDIT_GUIDE.md` (in repo). Run:
```bash
npx tsx scripts/auditDeadKeys.ts > docs/reports/deadKeys_raw.txt
```

**3. Run Security Probes (continue where Agent #1 stopped):**
Start Postgres+pgvector + Redis + Backend (use pgserver if no Docker):
```bash
python backend/scripts/dev_postgres.py &  # if exists, or pgserver
# or
docker-compose up postgres redis -d
alembic upgrade head
python backend/scripts/seed_products.py --from-json
uvicorn app.main:app --reload --port 8000 &
```

Then run these curls and log to `docs/SECURITY_AUDIT_V2.md`:
```bash
# IDOR test
TOKEN_A=$(curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"demo@smartdecor.dev","password":"Demo1234!"}' | python -c "import sys, json; print(json.load(sys.stdin).get('access_token',''))")
curl -s http://localhost:8000/admin/products -H "Authorization: Bearer $TOKEN_A" -w " HTTP:%{http_code}\n" -o /dev/null

# CORS
curl -s -H "Origin: https://evil.com" http://localhost:8000/auth/login -v 2>&1 | grep -i access-control

# Headers
curl -s -I http://localhost:8000/ | grep -i -E "strict-transport|content-security|x-frame|x-content-type|referrer|permissions"

# Brute force 6x
for i in {1..6}; do curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"demo@smartdecor.dev","password":"wrong"}' -w " Attempt $i HTTP:%{http_code}\n" -o /dev/null; done
```

**4. Performance quick check:**
```bash
npm run build -- --report
# or add rollup-plugin-visualizer
# Check bundle size, largest chunks
```

**5. Commit Phase 0:**
```bash
git add docs/RESEARCH_V2.md docs/AUDIT_V2.md docs/SECURITY_AUDIT_V2.md docs/PERF_REPORT_V2.md scripts/auditDeadKeys.ts
git commit -m "feat(v2): complete Phase 0B audit - dead keys + security probes + perf baseline"
git push origin main
git tag v2-phase0-audit-complete
git push origin v2-phase0-audit-complete
```

**DO NOT proceed to Phase 1 until Phase 0 files are committed. This is strict gate.**

---

### PHASE 1-5: Follow ADVANCED_MASTER_PROMPT_V2.md Exactly

After Phase 0 commit, proceed in order:

**Phase 1: Security Hardening - Fortress Mode**
- Implement security headers middleware (Caddy + FastAPI)
- Move JWT to httpOnly Secure cookies (keep fallback via env USE_COOKIE_AUTH)
- Implement brute force block (Redis 5 fails -> 15 min 429)
- Implement refresh rotation (one-time use, blacklist old)
- Add audit_logs table + pip-audit + npm audit fixes
- Definition of Done: `docs/SECURITY_AUDIT_V2.md` shows all probes PASS, headers present, brute force 429 works

**Phase 2: Performance - 60FPS**
- Fix root cause of hang user reported: lazy load react-grid-layout, OptimizedImage with WebP/AVIF/blur, memoize ProductCard, useTransition for drag, virtualization for recommendations
- Backend: Add indexes, orjson, fix N+1, check EXPLAIN ANALYZE uses HNSW
- Definition of Done: Lighthouse >=90, p95 <1s on Postgres, initial JS <120KB gzip, no Long Task >50ms on moodboard drag

**Phase 3: Minimal Beautiful UI - Linear/Apple Level**
- Read docs/RESEARCH_V2.md "What to steal" and implement
- Rebuild Design System V2: #FAF8F5 background, 16px card radius, soft shadows, Framer Motion, extreme whitespace, Vazirmatn + Inter via fontsource
- Redo pages: Quiz full-screen visual, Recommendations masonry toggle + hover second image, Moodboard toolbar + dot grid + Present mode, Floorplan walkway clearance (76cm), Shopping list Apple-like
- Definition of Done: No default shadcn look, empty/loading/error states designed, dark mode, command palette Cmd+K

**Phase 4: Dead Keys Fix - 100% Functional**
- Run `npx tsx scripts/auditDeadKeys.ts` - must be 0 DEAD
- Implement all essential dead buttons, disable non-essential with tooltip "Coming in v2.1"
- Write Playwright e2e `frontend/tests/e2e/deadKeys.spec.ts` that clicks every button and asserts no console error + 2xx/429
- Definition of Done: audit script PASS, Playwright PASS, Loom video clicking every button

**Phase 5: Polish**
- Confetti on quiz complete, shimmer skeletons, keyboard nav, a11y, dark mode, Framer Motion everywhere

---

## RULES FOR THIS CONTINUATION AGENT

1.  **Do not redo MVP v1.0** - It's already built and pushed to arena/01a01bbd-smart-interior-decor-recommend. You are improving it to v2.0
2.  **Do not redo Phase 0A if RESEARCH_V2.md exists and has >100 lines** - Just verify and continue to 0B
3.  **Commit after every phase:** After Phase 0, after Phase 1, etc. Push each time. Tag.
4.  **If you hit token limit again:** Commit and push, create savepoint tag `v2-phaseX-savepoint`, and tell user to start new agent with this same continuation prompt.
5.  **Security first, perf second, beauty third, functionality always:** No decorative button may remain enabled.

---

## FINAL DELIVERABLE V2 (Same as V2 Master Prompt)

- docs/RESEARCH_V2.md (12 platforms)
- docs/AUDIT_V2.md (0 dead keys after fix)
- docs/SECURITY_AUDIT_V2.md (all probes PASS)
- docs/PERF_REPORT_V2.md (Lighthouse 90+, p95 <1s)
- docs/DESIGN_SYSTEM_V2.md
- Frontend rebuilt minimal beautiful, 0 dead keys, OptimizedImage, Framer Motion, dark mode
- Backend hardened: headers, httpOnly cookies, brute force, audit logs, rate limit real Redis, orjson
- Tests: 45+ + Playwright deadKeys
- Reports: lighthouse.json >=90, p95 <1s, links.json, security_headers.txt

**BEGIN NOW by verifying docs/RESEARCH_V2.md exists, then continue Phase 0B audit from where previous agent stopped (security probes).**

You have been instructed to loop until Definition of Done for each phase is met. Never give up.

BEGIN CONTINUATION.
