# Threat Model — Smart Interior Decor Recommendation Platform

| | |
|---|---|
| **Stage** | Master Prompt 03 — Security, Privacy & Trust Hardening |
| **Owner** | CISO / Security Lead (virtual) |
| **Analyst** | Threat Modeling Analyst (virtual) |
| **Baseline commit** | `2f0338c14718b7a38b167d195e4ec497a94a122b` (`v2-strict-mode`) |
| **Date** | 2026-08-21 |
| **Method** | Asset → trust boundary → STRIDE per boundary → control → evidence |
| **Scope** | FastAPI backend, React SPA, Redis, PostgreSQL/pgvector, S3-compatible object storage, Caddy edge, Zarinpal/Zibal redirect, Gemini/OpenAI vision API, Resend email |

Every threat below is either **mitigated in this stage** (with a test id and an
evidence file), **pre-existing and re-verified**, or **accepted / deferred** with
an owner. Nothing is marked mitigated without a command whose output is committed
under `docs/agent-reports/security-hardening-evidence/`.

---

## 1. Assets

| # | Asset | Classification | Where it lives |
|---|---|---|---|
| A1 | User credentials (bcrypt hashes) | Secret | `users.hashed_password` (PostgreSQL) |
| A2 | Session artefacts — access JWT (15 min), refresh JWT (7 d), CSRF token | Secret | httpOnly cookies + `localStorage` (Bearer fallback), Redis blacklist |
| A3 | Personal data — email, full name, client name, client email, IP, user agent | Personal (GDPR) | `users`, `projects`, `style_quizzes`, `audit_logs` |
| A4 | Tenant content — quizzes, moodboards, projects, shopping lists, feedback | Confidential per-tenant | PostgreSQL |
| A5 | Share-link tokens (`secrets.token_urlsafe(32)`, 256-bit) | Bearer capability | `share_links.token` |
| A6 | Product catalog + AI extraction output + embeddings | Business data | `products`, pgvector column |
| A7 | Uploaded images | Untrusted input, publicly served | Local `/media` (dev) or S3 bucket (prod) |
| A8 | Platform secrets — `SECRET_KEY`, `FERNET_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, S3 keys, `ZARINPAL_MERCHANT_ID`, `RESEND_API_KEY` | Secret | Environment / `.env` (never in Git) |
| A9 | Payment intents (`payments.authority`, amount, status) | Financial | PostgreSQL |
| A10 | Audit trail | Forensic / integrity-critical | `audit_logs` |
| A11 | Availability of AI + DB budget (cost as an asset) | Business | Gemini/OpenAI quota, pgvector CPU |

## 2. Actors and trust levels

| Actor | Trust | Reaches |
|---|---|---|
| Anonymous internet | Untrusted | `/health`, `/auth/register`, `/auth/login`, `/auth/refresh`, `GET /share/{token}`, static SPA, `/media/*` |
| Homeowner (free) | Authenticated, lowest privilege | own quizzes, moodboards, feedback, subscription, paywalled recommendations |
| Homeowner (Pro) | Authenticated + entitlement | as above, unpaywalled |
| Designer | Authenticated, B2B2C | own projects, own quizzes, share-link creation, client email |
| Admin | Highest privilege | all users, roles, product CRUD, image upload, AI extraction, taxonomy, stats |
| Share-link holder | Capability-bearer, unauthenticated | one quiz's recommendations, client first name |
| Background task | In-process, app identity | outbound HTTP to seller links |
| AI provider (Gemini/OpenAI) | **External, untrusted output** | receives images, returns attacker-influenceable text |
| Payment gateway | External, semi-trusted | receives redirect, returns `authority` |
| Seller websites | External, untrusted | targets of the link checker (SSRF sink) |

## 3. Trust boundaries

```
 (TB1) Internet ─── TLS ───► Caddy edge  ────────────────────────────────────┐
                                │                                            │
                        (TB2) Caddy ► uvicorn (X-Forwarded-For / -Proto)     │
                                │                                            │
   ┌────────────────────────────┴────────────────────────────────────┐       │
   │  FastAPI application                                            │       │
   │   (TB3) unauthenticated ► authenticated  (JWT cookie / Bearer)  │       │
   │   (TB4) role boundary    homeowner ► designer ► admin           │       │
   │   (TB5) tenant boundary  user A ► user B (IDOR)                 │       │
   │   (TB6) capability       share token ► one quiz                 │       │
   └───┬───────────┬─────────────┬────────────────┬──────────────────┘       │
       │           │             │                │                          │
  (TB7)│      (TB8)│        (TB9)│          (TB10)│                          │
  Postgres      Redis        S3/local        outbound HTTP ────────────────► Internet
  (tenant     (throttle,     media          (AI provider, seller links,
   data)      blacklist)     (public)        payment gateway, email)
```

* **TB1/TB2** — TLS terminates at Caddy. The app therefore trusts
  `X-Forwarded-Proto` for the HSTS decision and the **left-most**
  `X-Forwarded-For` entry for the client IP used by throttling and audit.
  *If the app is ever exposed without that proxy, both are attacker-controlled.*
  Tracked as **R-14**.
* **TB9** — `/media` serves attacker-supplied bytes from the same origin as the
  SPA in the local-storage profile. Anything that can be persuaded to render as
  HTML there is same-origin script execution. Hardened in this stage (U-01…U-05).
* **TB10** — three outbound sinks reachable with attacker-influenced URLs:
  the seller-link checker, the AI provider's image fetch, and the payment
  redirect. SSRF surface.

## 4. STRIDE per boundary

Legend — **Status**: `FIXED` (this stage) · `OK` (pre-existing, re-verified) ·
`ACCEPTED` (documented residual) · `DEFERRED` (integration request).

### TB3 — Unauthenticated → authenticated

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-01 | Spoofing | **A published default admin credential ships to production.** Both seed entrypoints call `ensure_default_accounts()` unconditionally, and `docker-compose.yml` runs one of them on every backend start. `admin@smartdecor.dev / Admin123!` is printed in `README.md`, `docs/WALKTHROUGH*.md` and on the SPA login page. | Central, fail-safe gate: `app.core.demo_seed` refuses in production *unconditionally*, requires explicit `SEED_DEMO_ACCOUNTS=true` elsewhere; `Settings.validate_runtime()` refuses to boot a production process that asks for it; a boot-time DB guard refuses to serve production if a demo account exists; SPA hint gated on `import.meta.env.DEV` | **FIXED** | `03-*-demo-seeding-probe.txt`, `test_demo_seeding.py` |
| T-02 | Spoofing | Online password guessing | Per-`ip+email` lockout, 5 fails → 15 min, `429` + `Retry-After`; per-IP flood limit | OK (re-verified) | probe `R-04` |
| T-03 | Information disclosure | **Login timing oracle** — a missing user skipped bcrypt entirely (9 ms vs 268 ms), disclosing which addresses are registered | Constant-work dummy bcrypt verify on the miss path | **FIXED** | probe `T-01`, `test_auth_hardening.py` |
| T-04 | Information disclosure | `409 Email already registered` confirms an address | Kept (UX) — throttled to 3 registrations/min/IP + audit | **ACCEPTED** (R-09) | probe `R-03` |
| T-05 | Tampering | JWT algorithm confusion / `alg:none` | `algorithms=[JWT_ALGORITHM]` on decode **and** a boot-time allowlist restricting it to HS256/384/512 | **FIXED** | `test_config_fail_safe.py` |
| T-06 | Repudiation | Auth events untraceable | `audit_logs` for login / failed / blocked / register / refresh / logout, now + `user_delete`, `role_change`, `share_create`, `gdpr_export` | **FIXED** (extended) | probe `L-01`, `G-03` |
| T-07 | Elevation | Self-registration as `admin` | `RegisterIn.role` pattern allows only `homeowner|designer` | OK | `test_auth.py` |
| T-08 | Spoofing | Refresh-token replay after logout | `jti` blacklisted in Redis for the token's remaining lifetime | OK | probe `K-03` |
| T-09 | Tampering | CSRF against cookie-authenticated state change | Double-submit token; **now also enforced on `/auth/refresh` and `/auth/logout`**, which previously relied on `SameSite` alone | **FIXED** | probe `K-02`, `test_auth_hardening.py` |
| T-10 | Denial of service | Password longer than bcrypt's 72-byte input is silently truncated, so two different passwords authenticate the same account | Registration bounds the password at 72 bytes with an explicit message | **FIXED** | `test_auth_hardening.py` |

### TB4 — Role boundary

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-11 | Elevation | Homeowner reaches designer/admin routes | `require_role` dependency on every privileged route | OK | probe `A-03`, `A-04` |
| T-12 | Elevation | Self-promotion through `PATCH /admin/users/{id}` | Route is admin-only; body model now `extra="forbid"` so no unknown key can ride along | **FIXED** (hardened) | probe `A-05`, `V-04` |
| T-13 | Repudiation | Role changes left no trace | `role_change` audit row with actor, target, old → new | **FIXED** | probe `L-01` |
| T-14 | Denial of service | Last admin demotes/disables itself → permanent lockout | Refuse self role-change and self-deactivation (`409`) | **FIXED** | probe `A-06` |

### TB5 — Tenant boundary (IDOR)

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-15 | Information disclosure | Read another tenant's moodboard / quiz / project | Ownership predicate + `404` (not `403`) so existence is not confirmed | OK (regression-tested) | `test_idor_rbac.py`, probe `A-01` |
| T-16 | Tampering | Update/delete another tenant's object | Same predicate on `PATCH`/`DELETE` | OK (regression-tested) | probe `A-02` |
| T-17 | Tampering | Mass assignment of `user_id` / `id` / `is_verified` through create bodies | `extra="forbid"` on every write model — **`ProductIn`/`ProductUpdate`/`UserPatch`/`VerifyIn` were still open** | **FIXED** | probe `V-01`, `V-04` |
| T-18 | Information disclosure | Share a quiz that belongs to someone else | `quiz.user_id == caller` check in `share_project` | OK | `test_idor_rbac.py` |

### TB6 — Share capability

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-19 | Information disclosure | Brute-force / enumerate share tokens | 256-bit token; **plus** a per-IP rate limit on `GET /share/{token}` | **FIXED** | probe `R-01` |
| T-20 | Information disclosure | Expired link keeps working | `410 Gone` past `expires_at` | OK | `test_idor_rbac.py` |
| T-21 | Denial of service | Unauthenticated recommendation compute farmed through share links | Rate limit above; recommendation cache | **FIXED** | probe `R-01` |

### TB7 — Database

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-22 | Tampering | SQL injection | SQLAlchemy Core/ORM parameter binding throughout; no string-built SQL in request paths | OK | code review + `test_input_validation.py` |
| T-23 | Denial of service | Oversized field reaches the driver and returns `500` (`StringDataRightTruncation`) | Bounded `SafeText`/`Field(max_length=…)` on **every** writable string, verified against real PostgreSQL | **FIXED** | `07-postgres-*.log`, probe `V-02` |
| T-24 | Information disclosure | Stack trace / driver error echoed to the client | Generic envelopes; the `422` handler no longer reflects the submitted value | **FIXED** | probe `H-02`, `H-03` |

### TB8 — Redis

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-25 | Denial of service / bypass | **Redis outage silently disabled every throttle** (fail-open), so an attacker who can DoS Redis removes brute-force protection | Fail-**closed** (`503` + `Retry-After`) in production; documented fail-open in dev/test | **FIXED** | probe `D-01`, `test_redis_real.py` |
| T-26 | Tampering | Per-worker fakeredis in production makes limits `N×limit` | `validate_runtime()` requires `REDIS_URL`; `get_redis()` now refuses to hand a fakeredis client to a production process | **FIXED** | `test_config_fail_safe.py` |
| T-27 | Spoofing | Throttle key derived from a spoofable `X-Forwarded-For` when no proxy is in front | Documented deployment requirement; Caddy overwrites the header | **ACCEPTED** (R-14) | `PRODUCTION_SECURITY_CHECKLIST.md` |

### TB9 — Object storage / `/media`

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-28 | Elevation (XSS) | Upload `evil.html` → served from the SPA origin as `text/html` → same-origin script execution | Magic-byte sniffing, image allowlist (PNG/JPEG/WebP/GIF), extension derived from the **sniffed** type, never from the filename | **FIXED** | probe `U-01`, `test_upload_security.py` |
| T-29 | Elevation (XSS) | SVG upload (scriptable image format) | SVG explicitly rejected | **FIXED** | probe `U-02` |
| T-30 | Tampering | `Content-Type` spoofing (PE binary named `.jpg`) | Sniffing beats the declared type | **FIXED** | probe `U-03` |
| T-31 | Tampering | Path traversal via filename | Filename is never used for the storage key; UUID + sniffed extension; storage root containment assertion | **FIXED** | probe `U-04` |
| T-32 | Denial of service | Whole upload read into memory before the size check; decompression bomb (small file, 30 000×30 000 px) | Streamed, capped read that aborts at the limit; Pillow pixel-count and dimension limits; `Image.MAX_IMAGE_PIXELS` | **FIXED** | `test_upload_security.py` |
| T-33 | Denial of service / cost | Unlimited AI extraction calls through `/products/upload` | Per-user upload rate limit with `Retry-After` | **FIXED** | probe `U-05` |
| T-34 | Information disclosure | EXIF GPS / camera serial republished with the image | EXIF stripped on re-encode; documented policy | **FIXED** | `test_upload_security.py` |

### TB10 — Outbound (SSRF) and untrusted AI output

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-35 | Information disclosure | SSRF — `seller_link` / `image_url` pointed at `169.254.169.254`, `127.0.0.1`, `10.0.0.0/8`, `file://`, `gopher://` and fetched by the link checker or the AI provider | `app.core.url_safety`: scheme allowlist (`http`/`https`), DNS resolution, IP-literal and private/loopback/link-local/reserved range rejection at **validation** time and again before the outbound request | **FIXED** | `test_url_safety.py` |
| T-36 | Elevation (XSS) | `javascript:` / `data:text/html` in `seller_link`, rendered straight into `<a href>` in three SPA views | Same URL validator server-side; `safeExternalUrl()` guard client-side | **FIXED** | probe `X-01` |
| T-37 | Tampering | **Prompt injection**: an image containing text that makes the vision model return markup, which is then stored as the product title/description and rendered | AI output HTML-stripped and length-bounded at the persistence boundary | **FIXED** | probe `X-03` |
| T-38 | Information disclosure | API keys leaked into logs / error envelopes | Redacting log filter (JWTs, bearer tokens, `key=`/`api_key=`/`authority=` query values, cookies, emails) | **FIXED** | probe `P-01` |

### Cross-cutting — edge, headers, privacy

| ID | STRIDE | Threat | Control | Status | Evidence |
|---|---|---|---|---|---|
| T-39 | Tampering | **Unhandled `500` bypassed the header middleware entirely** — zero security headers on the one response class an attacker most wants to reach | Headers applied inside the middleware's own exception path; generic envelope | **FIXED** | probe `H-01` |
| T-40 | Elevation | **Production CORS allowlist contained `http://localhost:5173/4173` with `allow_credentials=true`** — any local process could drive an authenticated session | Origins built per environment; production = `FRONTEND_ORIGIN` only, and it must be `https://` | **FIXED** | probe `C-02` |
| T-41 | Elevation | `script-src 'unsafe-inline'` neutralises CSP as an XSS backstop | Removed — the Vite bundle has no inline script; `img-src` derives from `S3_PUBLIC_BASE_URL` (closes IR-005); `upgrade-insecure-requests` in production | **FIXED** | `06-security-headers.txt` |
| T-42 | Information disclosure | Authenticated payloads cached by a shared proxy | `Cache-Control: no-store` + `Vary: Cookie, Authorization` on API responses | **FIXED** (extended) | `06-security-headers.txt` |
| T-43 | Repudiation / privacy | GDPR erasure left `product_feedback` and `audit_logs` bound to the deleted user id, and was not itself audited | Erasure deletes feedback, **pseudonymises** audit rows (keeping the security trail, dropping the link to a person), writes one `user_delete` row with the pseudonym | **FIXED** | probe `G-01`…`G-03` |
| T-44 | Privacy | No self-service data export (GDPR Art. 15/20) | `GET /users/me/export` returning the full personal-data inventory, audited, rate limited | **FIXED** | `test_gdpr.py` |
| T-45 | Information disclosure | `FERNET_KEY` unset in production → a fresh key per process → ciphertext undecryptable and key material not managed | `validate_runtime()` requires a valid Fernet key in production | **FIXED** | `test_config_fail_safe.py` |
| T-46 | Supply chain | `ecdsa 0.19.2` / `PYSEC-2026-1325` with no fixed release, pulled in by `python-jose` | Not exploitable here (HS256 only) and now unreachable by construction (algorithm allowlist). Dependency swap to `pyjwt` raised as **IR-SEC-002** because `requirements.txt` is shared | **ACCEPTED + DEFERRED** | `09-pip-audit.log`, IR-SEC-002 |

## 5. Attack trees for the two highest-value goals

### Goal 1 — Become platform admin

```
Become admin
├── (a) Log in with a published default credential .................... CLOSED  T-01
│      └── production seeding removed + boot guard + SPA hint gated
├── (b) Guess an admin password online ............................... CLOSED  T-02
├── (c) Register with role=admin ..................................... CLOSED  T-07
├── (d) Mass-assign role through a create/update body ................ CLOSED  T-12/T-17
├── (e) Forge a JWT (weak/default SECRET_KEY, alg confusion) ......... CLOSED  T-05 + boot refusal
├── (f) Steal an admin session cookie via XSS ........................ REDUCED T-28/T-36/T-37 + httpOnly + CSP
└── (g) CSRF an admin into changing a role ........................... CLOSED  T-09 (SameSite + double submit)
```

### Goal 2 — Read another tenant's data

```
Read tenant B's data as tenant A
├── (a) Enumerate object ids and request them ........................ CLOSED  T-15/T-16
├── (b) Enumerate share tokens ....................................... CLOSED  T-19 (256-bit + throttle)
├── (c) Read a cached authenticated response from a shared proxy ..... CLOSED  T-42
├── (d) Recover data after erasure ................................... CLOSED  T-43
└── (e) Pivot through stored XSS in a shared moodboard/share page .... CLOSED  T-28/T-36/T-37
```

## 6. Data inventory (GDPR Art. 30 extract)

| Data | Purpose | Lawful basis | Retention | Erasure path |
|---|---|---|---|---|
| Email, full name | Authentication, contact | Contract | Life of account | `DELETE /users/me` — row removed |
| Password hash | Authentication | Contract | Life of account | Removed with the row |
| Quiz answers, room dimensions | Deliver recommendations | Contract | Life of account | Removed |
| Moodboards, shopping lists, feedback | Product feature | Contract | Life of account | Removed (feedback now explicitly) |
| Client name / client email (designer-entered) | B2B2C delivery | Legitimate interest (designer is controller) | Life of project | Removed with the project |
| IP + user agent in `audit_logs` | Security monitoring, fraud | Legitimate interest (Art. 6(1)(f)) | **180 days**, then purge | Pseudonymised on erasure, purged by retention |
| Payment `authority`, amount, status | Financial record | Legal obligation | 7 years (accounting) | **Retained** — documented lawful exception |
| Uploaded images | Catalog content | Contract | Life of product | Admin delete |

Retention is enforced by `scripts/purge_audit_logs.py` (documented in the
production checklist); it is **not yet scheduled** — see risk **R-11**.

## 7. Explicitly out of scope for this stage

Payment gateway signature verification and callback idempotency (Prompt 06),
CI/CD secret handling and branch protection (Prompt 07), Playwright E2E and
Lighthouse (Prompt 08), real-model AI benchmarking (Prompt 04), infrastructure
TLS/WAF/backup execution (client-owned). Findings touching those areas are
recorded as integration requests, not silently fixed.
