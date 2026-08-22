# MASTER PROMPT 03 — Security, Privacy & Trust Hardening

## Mission
Bring the current Smart Decor MVP to a defensible pre-production security posture without breaking legitimate flows.

## Mandatory virtual team
Delegate to: Security Lead/CISO (manager), senior FastAPI security engineer, frontend application-security engineer, DevSecOps engineer, privacy/GDPR specialist, threat-model analyst and penetration-test QA. The CISO owns go/no-go.

## Allowed scope
`backend/app/core/**`, `backend/app/api/routes/auth.py`, `users.py`, `projects.py`, `moodboards.py`, relevant schemas and security migrations/tests; `frontend/src/stores/authStore.ts`, `frontend/src/lib/api.ts` and security-related UI only; `docs/security/**`; security CI/config only by integration request. Avoid unrelated UI redesign.

## Threat model and work
1. Inventory assets, trust boundaries, roles, tenant ownership, share tokens, AI inputs, uploads, payment redirects and personal data.
2. Test and fix authentication: secure HttpOnly/Secure/SameSite cookies where production mode requires them, refresh rotation, CSRF double-submit, logout, token replay and dev fallback isolation.
3. Enforce brute-force and abuse controls on login, register, recommend, share and upload using shared Redis in production; return correct 429 and `Retry-After`.
4. Verify IDOR/RBAC for homeowner, designer and admin; ensure 404/403 behavior does not leak resources.
5. Add strict Pydantic constraints (`extra=forbid`, lengths, ranges, enum validation), safe error envelopes and no stack traces to clients.
6. Sanitize free text and AI output, test stored XSS payloads, unsafe URLs, SSRF via seller/image URLs and malicious filenames.
7. Harden uploads: MIME sniffing, size/pixel limits, extension normalization, EXIF policy, storage isolation and non-executable serving.
8. Verify CSP, HSTS, CORS allowlist, security headers, cache-control, TLS proxy assumptions and log redaction.
9. Verify GDPR delete, retention, audit log, export/data inventory, backup encryption and secret/key rotation documentation.
10. Run dependency audit and explain accepted advisories; never weaken security just to make a scanner green.

## Required tests/evidence
Add regression tests for each finding and negative tests for every authorization boundary. Execute unit/integration tests with real PostgreSQL and Redis where possible. Provide a threat model, risk register (severity/likelihood/owner/fix), before/after outputs and explicit residual risks.

## DoD
No known P0 security finding; all auth/IDOR/CSRF/XSS/upload tests pass; production fails safely when required secrets/Redis are absent; no credentials committed; report is honest about untested infrastructure.

## Parallel protocol
Branch `agent/security-hardening-<date>`. Do not alter unrelated product code or another agent's files. If a shared migration/CI file is needed, create `integration-request.md` and a patch description instead of editing it.
