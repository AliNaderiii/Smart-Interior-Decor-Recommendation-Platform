# Production security checklist

Run through this before the first production deploy, and again after any change
to the deployment topology. Every item is either **enforced** (the application
refuses to start or refuses the request if it is wrong) or **manual** (nobody
but you can check it).

Legend: 🔒 enforced by code · ✅ manual verification · 📋 operational process

---

## 1. Configuration — the application refuses to boot without these

`Settings.validate_runtime()` runs at import time in `app/main.py` and raises
`RuntimeError` listing **every** problem at once.

| | Setting | Required value | Why |
| --- | --- | --- | --- |
| 🔒 | `APP_ENV` | `production` | Switches every fail-safe below |
| 🔒 | `SECRET_KEY` | ≥32 chars, not the default | Signs every JWT |
| 🔒 | `SEED_DEMO_ACCOUNTS` | `false` (default) | Demo logins must never exist here — see [`DEMO_ACCOUNTS.md`](./DEMO_ACCOUNTS.md) |
| 🔒 | `REDIS_URL` | a real, shared Redis | fakeredis is per-worker, so limits and lockouts would not be shared |
| 🔒 | `COOKIE_SECURE` | `true` | Session cookies must not travel in clear text |
| 🔒 | `COOKIE_SAMESITE` | `strict` or `lax`; `none` requires `COOKIE_SECURE=true` | CSRF depth |
| 🔒 | `FRONTEND_ORIGIN` | a single `https://` origin | It is the entire CORS allowlist in production |
| 🔒 | `FERNET_KEY` | a valid urlsafe-base64 32-byte key | Otherwise every worker generates its own and at-rest ciphertext becomes unrecoverable |
| 🔒 | `STORAGE_BACKEND` | `s3` | `local` serves uploaded bytes from the application origin |
| 🔒 | `JWT_ALGORITHM` | `HS256` (allowlist: HS256/384/512) | Blocks algorithm confusion — checked in every environment |
| 🔒 | AI provider keys | present whenever `AI_PROVIDER != mock` | A half-configured provider fails at request time instead |
| ✅ | `DEMO_ACCOUNT_PASSWORD` | unset | Only meaningful in development |
| ✅ | `REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION` | `true` (default) | Leave it on |

Verify with:

```bash
cd backend && .venv/bin/python ../docs/security/probes/probe_production_failsafe.py
# expect: 8 checks, 8 secure, 0 INSECURE
```

## 2. Accounts and credentials

* 🔒 The lifespan boot guard refuses to serve if `users` contains any
  `*@smartdecor.dev` demo address.
* ✅ At least two human administrators exist before launch — the platform
  refuses to remove the last active admin, but one admin is still a single
  point of failure.
* ✅ `SECRET_KEY`, `FERNET_KEY`, S3 keys and payment keys are generated per
  environment and stored outside the repository.
* 📋 A rotation owner and cadence are agreed. Rotating `SECRET_KEY` logs
  everyone out — that is expected, not a bug.
* ✅ No `.env`, `*.pem` or dump file is committed. Confirm with
  `git log -p --all -S 'SECRET_KEY=' | head`.

## 3. Network and edge

* ✅ TLS terminates at the reverse proxy (Caddy) with a valid certificate;
  HTTP redirects to HTTPS.
* 🔒 The app emits `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  in production and whenever `X-Forwarded-Proto: https`.
* ✅ **The proxy overwrites `X-Forwarded-For`** rather than appending to a
  client-supplied value. Rate-limit and lockout keys derive from it — a proxy
  that forwards a client-controlled header makes every per-IP control
  bypassable (accepted risk **A-03**).
* ✅ The Redis and PostgreSQL ports are not reachable from the internet.
* ✅ `/media` is not served by the application (`STORAGE_BACKEND=s3` enforces
  this) and the bucket has no public write access.

## 4. HTTP responses

Verified by `tests/test_security_headers.py` on 200, 401, 403, 404, 405, 422,
429 **and 500**.

* 🔒 `Content-Security-Policy` with `script-src 'self'` (no `unsafe-inline`,
  no `unsafe-eval`), `frame-ancestors 'none'`, `object-src 'none'`,
  `base-uri 'self'`, `form-action 'self'`, plus `upgrade-insecure-requests`
  in production.
* ✅ Confirm `img-src` lists your actual CDN: it is derived from
  `S3_PUBLIC_BASE_URL` / `S3_ENDPOINT`, so a misconfigured bucket URL shows up
  as broken images, not as a silently loosened policy.
* 🔒 `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`.
* 🔒 `Cache-Control: no-store` and `Vary: Cookie, Authorization, Origin` on
  every `/api/v1` response.
* 🔒 `Server` does not advertise uvicorn/Python.
* 🔒 `/docs`, `/redoc` and `/openapi.json` return 404 in production.

## 5. Authentication and session

* 🔒 5 failed logins per `ip+email` → 15-minute lockout, `429` + `Retry-After`.
* 🔒 Per-IP throttles on login (10/min), registration (3/min), recommendations,
  uploads, share views and GDPR export; all return `Retry-After`.
* 🔒 With Redis unavailable, production **fails closed** with `503` +
  `Retry-After` — it never silently disables the controls.
* 🔒 Access/refresh/CSRF cookies are `HttpOnly` (except the CSRF token by
  design), `Secure`, `SameSite`, `Path=/`.
* 🔒 Double-submit CSRF on every unsafe cookie-authenticated request,
  including `/auth/refresh` and `/auth/logout`.
* 🔒 Refresh tokens rotate and the used `jti` is blacklisted for its remaining
  lifetime in shared Redis.
* ✅ Access-token lifetime (`ACCESS_TOKEN_EXPIRE_MINUTES`) and refresh lifetime
  are appropriate for your risk appetite; the defaults are 15 minutes / 7 days.

## 6. Data protection and privacy

* 🔒 `GET /users/me/export` serves GDPR Art. 15/20 requests (audited, rate
  limited).
* 🔒 `DELETE /users/me` deletes owned data and **pseudonymises** the audit
  trail (keyed HMAC id, IP truncated to /24 or /48, user agent dropped).
* 🔒 EXIF — including GPS — is stripped from every uploaded image.
* 🔒 Logs are redacted: JWTs, bearer/basic credentials, `token=`/`key=`/
  `password=` parameters, cookies, card numbers, and email addresses
  (pseudonymised, domain preserved).
* 📋 **Retention is not yet automated.** The export tells users security events
  are kept 180 days; nothing enforces that today (**IR-SEC-007**).
* 📋 A privacy notice, a lawful basis per processing activity and a DPA with
  each processor (hosting, S3, AI provider, email, payments) exist. The
  Art. 30 inventory is in [`THREAT_MODEL.md`](./THREAT_MODEL.md) §GDPR.
* ✅ If the AI provider is not `mock`, confirm that uploaded room photos being
  sent to a third party is covered by the privacy notice and the DPA.

## 7. Uploads

* 🔒 Magic-byte sniffing; only PNG / JPEG / WebP / GIF.
* 🔒 Re-encoded on ingest (kills polyglots and appended payloads).
* 🔒 Storage key is `uuid4 + sniffed extension`; the client filename never
  reaches the filesystem or the S3 key; unknown extensions become `.bin`.
* 🔒 Size, pixel-count and edge-length caps; oversized uploads are `413`.
* 🔒 Per-admin upload rate limit.
* ✅ The S3 bucket sets `Content-Type` from the object metadata and does not
  allow directory listing.

## 8. Dependencies and supply chain

```bash
cd backend && .venv/bin/pip-audit -r requirements.txt
cd frontend && npm audit --omit=dev
```

* ✅ Current known finding: `ecdsa 0.19.2` / `PYSEC-2026-1325`, **no fixed
  release**. Accepted (**A-04**): the vulnerable ECDSA path is unreachable
  because the platform is HS256-only and the algorithm allowlist enforces it.
  Tracked for removal as **IR-SEC-002**.
* 📋 These scans do not run in CI yet (**IR-SEC-006**) — run them manually each
  release until they do.
* ✅ Lockfiles (`package-lock.json`) are committed and installs use `npm ci`.

## 9. Monitoring and response

* ✅ Application logs are shipped somewhere durable and searchable.
* 📋 Alert on: `login_blocked`, `role_change`, `upload_rejected`,
  `user_delete`, any `503` from the fail-closed path, and any startup failure
  mentioning `demo account`.
* 📋 The demo-account incident runbook in [`DEMO_ACCOUNTS.md`](./DEMO_ACCOUNTS.md) §4
  is understood by whoever is on call.
* 📋 Database backups are taken, restore is rehearsed, and **restores into
  production are checked for demo accounts** — the boot guard will catch it,
  but only after the restore has already happened.

## 10. Pre-launch verification run

```bash
# backend suite (376 tests)
cd backend && .venv/bin/python -m pytest -p no:warnings

# real shared Redis behaviour
TEST_REDIS_URL=redis://<host>:6379/9 .venv/bin/python -m pytest tests/test_redis_real.py

# black-box API probe (37 checks)
.venv/bin/python ../docs/security/probes/probe_api_security.py --label RELEASE

# demo-seeding probe (6 cases, production must create 0 users)
.venv/bin/python ../docs/security/probes/probe_demo_seeding.py

# production fail-safe probe (8 checks)
.venv/bin/python ../docs/security/probes/probe_production_failsafe.py

# frontend
cd ../frontend && npm run build && npm run lint
node --experimental-strip-types --test tests/unit/safeUrl.test.ts
grep -r 'Admin123' dist/ && echo "FAIL: demo credentials in the bundle"
```

Expected: `376 passed`, `37 secure / 0 INSECURE`, `production runs that created
demo accounts = 0`, `8 secure / 0 INSECURE`, a clean build, and no credential
match in `dist/`.
