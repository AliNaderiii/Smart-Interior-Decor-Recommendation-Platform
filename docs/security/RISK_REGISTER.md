# Security risk register — Smart Interior Decor Recommendation Platform

**Owner:** Security & Privacy Hardening stage (Master Prompt 03)
**Branch:** `agent/security-hardening-2026-08-21`
**Date:** 2026-08-21
**Companion documents:** [`THREAT_MODEL.md`](./THREAT_MODEL.md) (STRIDE, T-01…T-46),
[`DEMO_ACCOUNTS.md`](./DEMO_ACCOUNTS.md),
[`PRODUCTION_SECURITY_CHECKLIST.md`](./PRODUCTION_SECURITY_CHECKLIST.md).

Scoring is qualitative and deliberately coarse; the point is ordering, not
precision. **Likelihood** and **Impact** are Low / Medium / High / Critical, and
**Residual** is the rating that remains after the controls in the *Treatment*
column are in place.

| | Meaning |
| --- | --- |
| **Treated** | A control is implemented and covered by a test or probe. |
| **Accepted** | Understood, deliberately not fixed here; rationale recorded. |
| **Deferred** | Needs a change outside this stage's file ownership → integration request. |

---

## 1. Risks closed in this stage

| ID | Risk | Inherent (L/I) | Treatment | Residual | Verification |
| --- | --- | --- | --- | --- | --- |
| **R-01** | Production automatically creates `admin@smartdecor.dev / Admin123!`, a published credential, on every container start (T-01, blocker B-1) | High / **Critical** | Central `app.core.demo_seed` gate: production refusal is non-overridable; explicit `SEED_DEMO_ACCOUNTS` opt-in elsewhere; boot refuses the setting; lifespan guard refuses to serve a production DB that already contains demo rows; SPA hint compiled out of production builds | **Low** — requires an operator to disable the boot guard *and* insert rows by hand | `05-AFTER-demo-seeding-probe.txt` (0/3 production runs create accounts), `07-AFTER-production-failsafe-probe.txt` F-01/F-03/F-04, `tests/test_demo_seeding.py` (17 tests) |
| **R-02** | Redis outage silently disables every rate limit and lockout (fail-open) — a DoS on Redis becomes an authentication bypass (T-25) | Medium / High | Fail **closed** in production (`503` + `Retry-After`); documented fail-open in dev/test so developers are never blocked | Low — an outage costs availability, never authentication | `07-…failsafe-probe.txt` F-06, `tests/test_config_fail_safe.py` |
| **R-03** | Per-worker `fakeredis` in production multiplies every limit by the worker count and de-synchronises the token blacklist (T-26) | Medium / High | `validate_runtime()` requires `REDIS_URL`; `get_redis()` refuses to hand a fake client to a production process | Low | F-05, `tests/test_config_fail_safe.py`, `tests/test_redis_real.py` (real Redis 6.2.14) |
| **R-04** | Login timing discloses whether an address is registered (268 ms vs 9 ms = 29×) (T-03) | High / Medium | Constant-work bcrypt verify against a dummy hash on the miss path | Low — measured 1.0× | probe `T-01`: `known=265.6 ms unknown=265.3 ms` |
| **R-05** | Upload of `evil.html`/SVG/PE stored under an attacker-chosen extension and served same-origin → stored XSS in the SPA (T-28…T-31) | Medium / **Critical** | Magic-byte sniffing, four-format allowlist, re-encode, UUID key with a sniffed extension, storage-root containment, `.bin` for anything unknown | Low | probe `U-01`…`U-04`, `tests/test_upload_security.py` (28 tests) |
| **R-06** | Unbounded upload read + decompression bombs + unthrottled AI inference (T-32, T-33) | Medium / Medium | Streamed capped read, pixel/edge limits, `Image.MAX_IMAGE_PIXELS`, per-admin upload rate limit with `Retry-After` | Low | probe `U-05`, `tests/test_upload_security.py` |
| **R-07** | SSRF through `seller_link` / `image_url` into cloud instance metadata or loopback services (T-35) | Medium / High | `app.core.url_safety` scheme allowlist + DNS resolution + private/loopback/link-local/reserved rejection, applied at validation **and** again per redirect hop with manual redirect following | Low — rebinding between the last check and `connect()` remains theoretically possible (see R-15) | `tests/test_url_safety.py` (34 tests) |
| **R-08** | `javascript:`/`data:` in a stored URL rendered into `<a href>`, including on the unauthenticated share page (T-36) | Medium / High | Server-side scheme validation **and** `safeUrl()` at every render site | Low | probe `X-01`, `frontend/tests/unit/safeUrl.test.ts` |
| **R-09** | Prompt injection through an uploaded image turns AI-generated copy into stored markup (T-37) | Medium / Medium | AI output HTML-stripped and length-bounded at the persistence boundary — model output treated exactly like user input | Low | probe `X-03`, `tests/test_input_validation.py::test_ai_extracted_text_is_sanitised` |
| **R-10** | Unhandled `500` bypassed the header middleware — no CSP/HSTS/nosniff on the response class a fuzzer sees most (T-39) | Medium / Medium | Headers applied inside the middleware's own exception path plus in both exception handlers | Low | `tests/test_security_headers.py` (20 tests, one per status class) |
| **R-11** | Production CORS allowlist contained `http://localhost:5173/4173` with `allow_credentials=true` (T-40) | Low / High | Origins built per environment; production is `FRONTEND_ORIGIN` only and must be `https://` | Low | F-07, probe `C-02` |
| **R-12** | GDPR erasure left `product_feedback` and `audit_logs` (IP + user agent) bound to the deleted user, and was not itself audited (T-43) | Medium / High (regulatory) | Feedback deleted; audit rows **pseudonymised** (keyed HMAC id, IP truncated to /24 or /48, UA dropped); one `user_delete` row written already carrying the pseudonym | Low | probe `G-01`…`G-03`, `tests/test_gdpr.py` (29 tests) |
| **R-13** | No self-service export (GDPR Art. 15/20) — subject access requests served by hand from the production database (T-44) | High / Medium | `GET /users/me/export`, audited and rate limited | Low | `tests/test_gdpr.py` |
| **R-14** | Tokens, passwords and raw email addresses reachable in log streams (T-38, P-01) | Medium / High | `logging.setLogRecordFactory` + `RedactingFilter` on all root handlers: JWTs, bearer/basic, `token=`/`key=`/`password=` params, cookies, PANs, emails → keyed pseudonym | Low | probe `P-01`, `tests/test_gdpr.py` |
| **R-15** | Mass assignment through write models without `extra="forbid"` (`ProductIn`, `ProductUpdate`, `UserPatch`, `VerifyIn`) (T-17) | Medium / High | `extra="forbid"` on every write model; oversized/absent-type inputs return `422` | Low | probe `V-01`, `V-04`, `tests/test_input_validation.py` (45 tests) |
| **R-16** | CSRF on `/auth/refresh` and `/auth/logout` relied on `SameSite` alone — `/refresh` mints a fresh credential pair (T-09) | Medium / High | Double-submit enforced whenever the credential arrives in a cookie; body/Bearer callers exempt because they are not ambient authority | Low | probe `K-02`, `tests/test_auth_hardening.py` |
| **R-17** | The last admin could demote or deactivate itself → permanent platform lockout (T-14) | Low / High | `409` on self role-change and self-deactivation; refusal to remove the last active admin; every role change audited with old → new | Low | probe `A-06`, `L-01`, `tests/test_idor_rbac.py` |
| **R-18** | "Sign out" did not revoke the session under cookie auth (the client skipped the API call when `localStorage` was empty) | Medium / Medium | `handleLogout` always calls `POST /auth/logout`; tokens are no longer duplicated into `localStorage` when cookie auth is active | Low | `frontend/src/components/Layout.tsx`, `authStore.ts` |
| **R-19** | Unauthenticated `GET /share/{token}` allowed unlimited token probing and free recommendation compute (T-19, T-21) | Medium / Medium | Per-IP rate limit + token length guard; share creation audited | Low | probe `R-01` |
| **R-20** | `FERNET_KEY` unset in production → a fresh key per worker → unrecoverable ciphertext (T-45) | Medium / Medium | `validate_runtime()` requires a valid Fernet key in production | Low | F-01, `tests/test_config_fail_safe.py` |

## 2. Accepted risks

| ID | Risk | Why accepted | Compensating control | Review trigger |
| --- | --- | --- | --- | --- |
| **A-01** | `409 Email already registered` confirms an address exists | Removing it means either accepting duplicate accounts or a confusing signup flow. Every mainstream consumer product makes the same trade. | Registration throttled to 3/min/IP and audited; login timing no longer distinguishes registered addresses | If the platform ever handles data whose *membership* is sensitive |
| **A-02** | CSP keeps `style-src 'unsafe-inline'` | Tailwind v4 and framer-motion inject inline styles; removing it breaks the design system. Inline **style** is a far weaker primitive than inline script. | `script-src 'self'` with no `unsafe-inline`/`unsafe-eval`; `object-src 'none'`; `base-uri 'self'` | A Tailwind release that supports nonce-based style injection |
| **A-03** | Throttle keys derive from `X-Forwarded-For` | Correct behind the intended Caddy deployment, which overwrites the header | Documented as a hard deployment requirement in the production checklist | Any deployment topology change |
| **A-04** | `ecdsa 0.19.2` / `PYSEC-2026-1325` has no fixed release | Pulled in transitively by `python-jose`; the vulnerable code path (ECDSA signing/verification) is unreachable — the platform is HS256-only and a boot-time allowlist now enforces that | Algorithm allowlist in `validate_runtime()`; migration to `pyjwt` raised as **IR-SEC-002** | A fixed `ecdsa` release, or IR-SEC-002 being actioned |
| **A-05** | Demo passwords are committed to the repository | They are documentation, not secrets. Treating them as secrets would be theatre; the control is that production cannot create them. | `tests/test_demo_seeding.py` asserts they appear in exactly one module | — |
| **A-06** | The banned-password list is tiny (15 entries) | A real breach-corpus check needs a network call (HIBP k-anonymity range API) or a large local dataset; neither belongs in this stage | 12-char minimum, byte-length bound, repetition and sequence rejection | Before public launch — see **IR-SEC-005** |
| **A-07** | `SECRET_KEY` rotation invalidates every issued token | Acceptable: rotation is an incident-response action, and refresh tokens are short-lived by comparison | Documented in the checklist and the demo-account incident runbook | Introduction of a key-id (`kid`) header |

## 3. Deferred — needs an integration request

| ID | Risk | Blocked by | Request |
| --- | --- | --- | --- |
| **D-01** | `docker-compose.yml` runs the product loader on every backend start; the demo-account path is now gated, but the compose file still hard-codes dev-shaped env values | `docker-compose.yml` is shared infrastructure owned by another stage | **IR-SEC-001** |
| **D-02** | `python-jose` → `pyjwt` migration to drop the `ecdsa` dependency entirely | `backend/requirements.txt` is shared | **IR-SEC-002** |
| **D-03** | `ai/feature_extractor.py` fetches a remote image URL without the SSRF validator (defence in depth — the URL is already validated at the schema boundary and at the link checker) | `backend/ai/**` is owned by the AI stage | **IR-SEC-003** |
| **D-04** | No frontend unit-test runner, so `safeUrl` tests run through `node --experimental-strip-types` instead of CI | `frontend/package.json` and the CI workflow are shared | **IR-SEC-004** |
| **D-05** | No breached-password check at registration | Needs a network dependency and a caching policy decision | **IR-SEC-005** |
| **D-06** | Security CI (pip-audit, `npm audit`, ruff, the probe harnesses) does not run automatically | `.github/workflows/**` is out of scope per Master Prompt 03 | **IR-SEC-006** |
| **D-07** | `audit_logs` has no retention job; the export promises a 180-day window that nothing enforces | Needs a scheduler/worker that does not exist yet | **IR-SEC-007** |

## 4. Risks that remain open regardless of this stage

These are not defects introduced or closed here; they are properties of the
deployment that the platform team must own.

| ID | Risk | Notes |
| --- | --- | --- |
| **O-01** | No TLS termination, WAF or DDoS protection is configured in the repository | HSTS is emitted; the certificate and the edge are the deployment's responsibility |
| **O-02** | Secrets live in `.env` files, not in a secret manager | Rotation is manual; `validate_runtime()` at least refuses defaults in production |
| **O-03** | No intrusion detection or alerting on the audit log | `audit_logs` now records the events worth alerting on — nothing consumes them yet |
| **O-04** | Backup/restore of the production database is undefined | Directly relevant to R-01: a restored staging dump is precisely what the boot guard exists to catch |
| **O-05** | The payment provider integration is a mock | Real integration will need its own review (webhook signature verification, replay protection) |
