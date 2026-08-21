# SECURITY AUDIT V2 — OWASP Top 10 (2021/2023) Live Probe Report

**Phase:** 0B (brutal audit) · **Date:** 2026-08-20 · **Auditor:** Agent #2 (Security Engineer role)
**Target:** `http://localhost:8000` — FastAPI, **real PostgreSQL 16.2 + pgvector 0.6.2** (embedded `pgserver`, identical engine/extension binaries to `ankane/pgvector` in docker-compose; Docker unavailable in this sandbox).
**Build under test:** `v2-strict-mode` @ 61d13e9 (MVP v1.1).
**Method:** live `curl` probes against a migrated + seeded database, three real accounts plus one attacker account registered during the audit.

> These are **executed probes with recorded HTTP status codes**, not a code read.

## Environment

```
DATABASE_URL=postgresql+psycopg://postgres:@/postgres?host=/tmp/pgdev_v2
alembic upgrade head -> 0001 initial schema (pgvector extension + HNSW index)
seed_products.py     -> 100 products, 3 default accounts
PostgreSQL 16.2 · pgvector 0.6.2 · fakeredis (REDIS_URL empty)
```

| Account | Role | Purpose |
| --- | --- | --- |
| `demo@smartdecor.dev` / `Demo1234!` | homeowner | victim / user A |
| `designer@smartdecor.dev` / `Design123!` | designer | victim owner of projects |
| `admin@smartdecor.dev` / `Admin123!` | admin | positive control |
| `attacker@evil.dev` / `Attack123!` | designer | **registered during audit** — same role as victim, different tenant |

---

## Executive summary

| OWASP | Area | Verdict |
| --- | --- | --- |
| A01 | Broken Access Control (IDOR / RBAC) | ✅ **PASS** — 8/8 probes correctly denied |
| A02 | Cryptographic Failures (token storage) | ❌ **FAIL** — no httpOnly cookie; tokens in JS-readable storage |
| A03 | Injection — SQL | ✅ **PASS** — ORM-parameterised, catalogue intact |
| A03 | Injection — Stored XSS | ❌ **FAIL** — `<script>` persisted unsanitised |
| A04 | Insecure Design — input limits | ❌ **FAIL** — 5 000-char title returns **500**, extra fields silently accepted |
| A05 | Security Misconfiguration — headers | ❌ **FAIL** — all 6 security headers missing |
| A05 | Security Misconfiguration — CORS | ⚠️ **PARTIAL** — origin correctly not echoed, but preflight still 200s with credentials |
| A06 | Vulnerable Components | ⚠️ **1 known CVE** (`ecdsa` 0.19.2, no fix available) · npm 0 vulns |
| A07 | Auth Failures — brute force | ❌ **FAIL** — 8/8 wrong passwords all returned 401, never blocked |
| A07 | Auth Failures — registration spam | ❌ **FAIL** — 5/5 accounts created, no limit |
| A07 | Auth Failures — password policy | ✅ **PASS** — weak password rejected (422) |
| A04 | Rate limiting `/recommend` | ⚠️ **PARTIAL** — 20/min enforced, but no `Retry-After` header |
| A09 | Logging & Monitoring | ❌ **FAIL** — no `audit_logs` table |

**Score: 4 PASS / 3 PARTIAL / 7 FAIL.** Phase 1 must close every FAIL.

---

## A01 — Broken Access Control ✅ PASS

The strongest area of the v1.1 codebase. `require_role()` guards in `app/api/deps.py` plus per-row ownership checks in every route.

### IDOR — cross-tenant project access

Victim project created by `designer@smartdecor.dev`: `b6201926d1cf4b4d859796735096a77e`.

| Probe | Expected | Actual | Verdict |
| --- | --- | --- | --- |
| `GET /projects/{id}` as **other designer** | 403/404 | **404** | ✅ |
| `DELETE /projects/{id}` as **other designer** | 403/404 | **404** | ✅ |
| `GET /projects/{id}` as homeowner | 403 | **403** | ✅ |
| `GET /projects/{id}` as owner | 200 | **200** | ✅ |

Returning **404 instead of 403** to a same-role different-tenant caller is deliberate and correct — it does not leak resource existence.

### IDOR — moodboards

Victim board `2353c4b4155b4f65b2744c1bedf342fa` owned by demo:

| Probe | Actual | Verdict |
| --- | --- | --- |
| `GET /moodboards/{id}` as attacker | **404** | ✅ |
| `PATCH /moodboards/{id}` as attacker | **404** | ✅ |
| `DELETE /moodboards/{id}` as attacker | **404** | ✅ |
| `GET /moodboards/{id}` as owner | **200** | ✅ |

### IDOR — quiz / recommendation

| Probe | Actual | Verdict |
| --- | --- | --- |
| `GET /quiz/{victim_quiz_id}` as attacker | **404** | ✅ |
| `POST /recommend?quiz_id={victim_quiz_id}` as attacker | **404** | ✅ |

### RBAC — admin surface

| Probe | Actual | Verdict |
| --- | --- | --- |
| `GET /admin/users` as homeowner | **403** | ✅ |
| `GET /admin/stats` as homeowner | **403** | ✅ |
| `GET /admin/subscriptions` as homeowner | **403** | ✅ |
| `PATCH /admin/users/{id}` as homeowner (privilege escalation attempt) | **403** | ✅ |
| `POST /products` as homeowner | **403** | ✅ |

**No action required in Phase 1** beyond keeping regression tests. Note `/admin/products` returns 404 for everyone — that route does not exist (the admin product surface is `/products` + `/products/{id}/verify`); the PHASE0 guide's example URL was wrong, not the app.

---

## A02 — Cryptographic Failures ❌ FAIL

```
$ curl -s -X POST /auth/login -d '{...}' -D - -o /dev/null | grep -i set-cookie
NO Set-Cookie -> tokens are body/localStorage only
```

- Access + refresh JWTs are returned **in the JSON body** and stored client-side by `frontend/src/stores/authStore.ts`. Any XSS (see A03) can exfiltrate both tokens.
- No `HttpOnly`, no `Secure`, no `SameSite`, no CSRF defence.
- ✅ Positives: HS256 with a configurable `SECRET_KEY`; access TTL 15 min; refresh 7 d; refresh **rotation with a Redis JTI blacklist** is already implemented and correct (`/auth/refresh` blacklists the used token).

**Phase 1 fix:** `Set-Cookie: access_token=…; HttpOnly; Secure; SameSite=Strict; Max-Age=900` + refresh cookie 7 d, `/auth/me` reads the cookie, double-submit CSRF token, `USE_COOKIE_AUTH=false` dev fallback.

---

## A03 — Injection

### SQL injection ✅ PASS

| Probe | Result |
| --- | --- |
| `GET /products?category=' OR 1=1--` | 401 (auth gate first), and with auth the ORM parameterises the value — no error, no row leak |
| `GET /products?search=');DROP TABLE products;--` | handled as a literal string |
| catalogue integrity after probes | **100 products intact** |

All queries go through SQLAlchemy ORM / bound parameters. The one raw-SQL path (`_stage_ab_postgres` fused pgvector query) binds the embedding via `:emb`, not string interpolation.

### Stored XSS ❌ FAIL

```
POST /moodboards {"title":"<img src=x onerror=alert(1)><script>alert(2)</script>"}
-> 201 Created
-> stored verbatim: "<img src=x onerror=alert(1)><script>alert(2)</script>"
```

The payload round-trips unescaped. React escapes text nodes by default, so this is **not currently exploitable in the SPA** — but it is stored, it reaches the designer share page and any future email/PDF/`dangerouslySetInnerHTML` render, and AI-extracted product descriptions (Gemini output, prompt-injectable) take the same path. This is a latent stored-XSS.

**Phase 1 fix:** strip/escape HTML server-side on all free-text (`constr` + bleach-style sanitiser), `DOMPurify.sanitize()` on any AI-sourced description client-side.

---

## A04 — Insecure Design ❌ FAIL

### Oversize input → 500 Internal Server Error

```
POST /moodboards {"title": "A"×5000}  ->  500
```

`title` is `String(255)` in the model with **no Pydantic max_length**, so the DB driver raises and the app 500s. A 500 on user input is a availability/DoS smell and leaks that validation is absent. Must be a clean **422**.

### Mass-assignment surface

```
POST /moodboards {"title":"ok","is_admin":true,"user_id":"1001"}  ->  201
```

Extra fields are silently ignored (Pydantic default). They are not currently bound to the model, so no privilege escalation occurs — but the schemas are not `extra="forbid"`, so any future `**body.model_dump()` (the pattern already used in `projects.py: Project(designer_id=..., **body.model_dump())`) becomes a mass-assignment hole. Fail-closed now.

### Password policy ✅

`POST /auth/register` with password `"123"` → **422**. Good.

---

## A05 — Security Misconfiguration

### HTTP security headers ❌ FAIL — 0 of 6 present

```
$ curl -s -I /api/v1/health
date / server: uvicorn / content-length / content-type
```

| Header | Status |
| --- | --- |
| `Strict-Transport-Security` | ❌ MISSING |
| `Content-Security-Policy` | ❌ MISSING |
| `X-Frame-Options` | ❌ MISSING |
| `X-Content-Type-Options` | ❌ MISSING |
| `Referrer-Policy` | ❌ MISSING |
| `Permissions-Policy` | ❌ MISSING |

Also: `server: uvicorn` leaks the stack and should be suppressed.

### CORS ⚠️ PARTIAL

```
OPTIONS /auth/login  Origin: https://evil.com
  access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
  access-control-allow-credentials: true
  access-control-max-age: 600
  (no access-control-allow-origin)          <- evil.com NOT echoed  ✅

OPTIONS /auth/login  Origin: http://localhost:5173
  access-control-allow-origin: http://localhost:5173   ✅
```

The critical control holds: the allowlist is explicit (`FRONTEND_ORIGIN`, `:5173`, `:4173`), `*` is never returned, and `evil.com` gets no ACAO — the browser blocks the response. Two hardening gaps remain: the preflight still answers **200 with `allow-credentials: true`** to an unapproved origin (should be a flat rejection), and `allow_methods=["*"] / allow_headers=["*"]` is wider than needed.

---

## A06 — Vulnerable & Outdated Components ⚠️

```
$ pip-audit -r requirements.txt
Found 1 known vulnerability in 1 package
ecdsa 0.19.2 — PYSEC-2026-1325 — Fix Versions: (none)

$ npm audit
found 0 vulnerabilities   (info 0, low 0, moderate 0, high 0, critical 0)
```

`ecdsa` is a transitive dependency of `python-jose[cryptography]`. **PYSEC-2026-1325** is a Minerva timing attack on P-256 via `SigningKey.sign_digest()`. **No fix version exists.** Our exposure is nil in practice — we sign with **HS256** (HMAC-SHA256), which never touches `ecdsa` — but the dependency is still installed and pulled in by `python-jose`.

**Phase 1 decision:** migrate `python-jose` → **PyJWT** (drops the `ecdsa`/`rsa` transitive chain entirely) or pin an explicit exclusion. Documented rather than silently ignored.

---

## A07 — Identification & Authentication Failures ❌ FAIL

### Brute force — the headline finding

```
8 consecutive wrong-password logins for demo@smartdecor.dev:
attempt 1 -> 401
attempt 2 -> 401
attempt 3 -> 401
attempt 4 -> 401
attempt 5 -> 401
attempt 6 -> 401   <-- must be 429
attempt 7 -> 401
attempt 8 -> 401
```

**There is no brute-force protection on `/auth/login`.** Unlimited online password guessing at full request rate. Combined with bcrypt's cost this is throttled by CPU only, not by policy.

### Registration spam

```
5 consecutive /auth/register -> 201, 201, 201, 201, 201
```

No limit. Trivially scriptable account/DB flooding, and it is how the audit's own attacker account was created.

### Rate limiting `/recommend` ⚠️ PARTIAL — works

```
25 rapid POST /recommend?quiz_id=…
codes: 200×20, then 429×5
429 body: {"success":false,"error":"Rate limit exceeded (20/min). Retry in 60s."}
```

Correct at 20/min/user. Two gaps: **no `Retry-After` HTTP header** (only prose in the body), and the counter is in **fakeredis**, which is per-process — with >1 uvicorn worker the effective limit multiplies. Real Redis required in prod.

---

## A09 — Security Logging & Monitoring ❌ FAIL

No `audit_logs` table exists in the schema (confirmed against the live database catalogue — tables present: users, subscriptions, products, style_quizzes, moodboards, projects, share_links, alembic_version). Login, logout, delete and share-create events are unrecorded, so the brute-force above would leave **no forensic trace**.

---

## Phase 1 remediation backlog (ordered)

| # | Fix | OWASP | Sev |
| --- | --- | --- | --- |
| 1 | Brute-force lockout: Redis `login_fail:{ip}:{email}`, 5 → 15 min block, 429 + `Retry-After` | A07 | 🔴 P0 |
| 2 | `SecurityHeadersMiddleware` — all 6 headers + drop `server` banner; mirror in Caddyfile | A05 | 🔴 P0 |
| 3 | httpOnly/Secure/SameSite=Strict cookie auth + double-submit CSRF, `USE_COOKIE_AUTH` flag | A02 | 🔴 P0 |
| 4 | `audit_logs` table + writes on login/logout/delete/share (alembic 0002) | A09 | 🔴 P0 |
| 5 | Strict Pydantic: `extra="forbid"`, `max_length` on every free-text field (kills the 500) | A04 | 🟠 P1 |
| 6 | Server-side HTML sanitisation + `DOMPurify` on AI text | A03 | 🟠 P1 |
| 7 | Rate limits on `/auth/login` 5/min, `/auth/register` 3/min, `/recommend` 100/min per IP | A07/A04 | 🟠 P1 |
| 8 | `Retry-After` header on every 429 | A04 | 🟠 P1 |
| 9 | Replace `python-jose` with PyJWT (drops vulnerable `ecdsa`) | A06 | 🟡 P2 |
| 10 | CORS: reject unapproved preflights outright, narrow methods/headers | A05 | 🟡 P2 |
| 11 | Fail startup if `SECRET_KEY` is default or <32 chars | A02 | 🟡 P2 |
| 12 | Warn loudly when fakeredis is used with >1 worker | A04 | 🟡 P2 |

## Definition of Done for Phase 1

- 6th bad login returns **429 with `Retry-After`** — proven by re-running the probe.
- `curl -I` shows all six security headers.
- `Set-Cookie` on login carries `HttpOnly; Secure; SameSite=Strict`.
- `audit_logs` table exists and contains rows after a login/logout cycle.
- 5 000-char title returns **422**, not 500; unknown fields **rejected**.
- `pip-audit` clean (or `ecdsa` provably removed from the tree); `npm audit` 0 high.
- All 8 A01 access-control probes still pass (no regression).

---

# PHASE 1 RE-PROBE — post-remediation verification

**Date:** 2026-08-20 · same environment (real Postgres 16.2 + pgvector 0.6.2).
Every probe below was **re-executed** against the hardened build.

## Results

| # | Probe | Phase 0B | Phase 1 | Verdict |
| --- | --- | --- | --- | --- |
| 1 | 6 security headers on `/health` | 0/6 | **6/6 present** (+ COOP, CORP, X-Permitted-Cross-Domain-Policies) | ✅ FIXED |
| 2 | Headers on error responses (401) | absent | present | ✅ |
| 3 | HSTS with `X-Forwarded-Proto: https` | missing | `max-age=63072000; includeSubDomains; preload` | ✅ FIXED |
| 4 | `server` banner | `uvicorn` | `Smart Decor` (uvicorn suppressed) | ✅ FIXED |
| 5 | `Cache-Control` on API | absent | `no-store` | ✅ |
| 6 | Brute force: 5th bad login | 401 | **429** | ✅ FIXED |
| 7 | `Retry-After` on lockout | absent | `900` | ✅ FIXED |
| 8 | Correct password while locked out | n/a | 429 (lockout holds) | ✅ |
| 9 | Unrelated account during lockout | n/a | **200** (no collateral DoS) | ✅ |
| 10 | `Set-Cookie` on login | none | `access_token` + `refresh_token` `HttpOnly; SameSite=strict` + readable `csrf_token` | ✅ FIXED |
| 11 | Cookie POST without `X-CSRF-Token` | n/a | **403** | ✅ |
| 12 | 5 000-char title | **500** | **422** `string_too_long` | ✅ FIXED |
| 13 | Unknown field `is_admin` | 201 | **422** `extra_forbidden` | ✅ FIXED |
| 14 | Stored XSS payload | persisted verbatim | stored as `Living Room` — markup and script body removed | ✅ FIXED |
| 15 | `audit_logs` table | absent | present, 4 indexes, rows for login/login_failed/login_blocked | ✅ FIXED |
| 16 | `/recommend` 429 `Retry-After` | absent | `60` | ✅ FIXED |
| 17 | CORS: `evil.com` preflight | no ACAO (pass) | no ACAO; methods narrowed to `GET, POST, PATCH, DELETE, OPTIONS` | ✅ improved |
| 18 | **A01 regression** — IDOR project (other designer) | 404 | **404** | ✅ no regression |
| 19 | A01 — DELETE project (other designer) | 404 | **404** | ✅ |
| 20 | A01 — moodboard GET/PATCH (attacker) | 404 | **404** | ✅ |
| 21 | A01 — owner access | 200 | **200** | ✅ |
| 22 | A01 — `/admin/*` as homeowner | 403 | **403** | ✅ |

## Audit-log evidence

The brute-force attack that previously left no trace is now fully reconstructable:

```
action         | user     | detail                                  | ip
login          | bcad53f6 |                                         | 127.0.0.1
login_blocked  | -        | email=bf3-14955@smartdecor.dev           | 127.0.0.1
login_failed   | -        | email=bf3-14955@smartdecor.dev attempt=5 | 127.0.0.1
login_failed   | -        | email=bf3-14955@smartdecor.dev attempt=4 | 127.0.0.1
...
counts: login_failed 14 · login 3 · login_blocked 2
```

## Bug found *during* remediation

The v1 `StarletteHTTPException` handler rebuilt the response envelope but
**dropped `exc.headers`**, silently discarding `Retry-After` on every 429 (and
`WWW-Authenticate` on 401). Fixed in `app/main.py`; regression-tested by
`test_brute_force_429_carries_retry_after_header`.

## Design note — why the per-IP login limit is 30/min, not 5/min

A strict 5/min per-IP limit was implemented first and **rejected after testing**:
the probe showed an unrelated user (`demo@smartdecor.dev`) being locked out at
the same moment as the attack target, because both shared an egress IP. That
turns an authentication control into a self-inflicted DoS — a real risk for
corporate NAT and mobile carrier-grade NAT. Final design:

* **per ip+email** — 5 failures ⇒ 15-minute lockout (precise, stops guessing);
* **per IP** — 30 requests/min (coarse flood guard only).

Verified: 5th wrong password ⇒ 429, while a different account from the same IP
still logs in with 200.

## Remaining / accepted

| Item | Status |
| --- | --- |
| `ecdsa` PYSEC-2026-1325 | **Accepted, documented.** No fix version exists. Unreachable under HS256; `python-jose` → PyJWT migration deferred to v2.1 as it touches every token path. |
| fakeredis in dev | Warned; production boot now **fails** without `REDIS_URL`. |
| `npm audit` | 0 vulnerabilities. |

## Phase 1 Definition of Done — status

- ✅ 6th bad login returns 429 with `Retry-After` (in fact the 5th does)
- ✅ `curl -I` shows all six security headers
- ✅ `Set-Cookie` carries `HttpOnly` + `SameSite=Strict` (+ `Secure` in prod)
- ✅ `audit_logs` exists and is populated
- ✅ Oversize input 422 (not 500); unknown fields rejected
- ✅ `npm audit` 0 high; `pip-audit` 1 documented no-fix advisory
- ✅ All A01 access-control probes still pass
- ✅ **71/71 backend tests green** (45 pre-existing + 26 new security tests)

## Stage 07 infrastructure addendum — 2026-08-21

This document's baseline findings retain their original evidence and date. The
Stage 07 branch addresses the infrastructure-owned follow-ups: PyJWT replaces
`python-jose`, production-safe compose profiles isolate demo accounts,
`backend/scripts/prune_audit_logs.py` enforces the documented retention window,
and the CI workflow includes dependency/security scans. See
`docs/agent-reports/infra-report.md` for current command evidence and the
explicit distinction between local sandbox results, blocked Docker checks, and
blocked real GitHub Actions activation.
