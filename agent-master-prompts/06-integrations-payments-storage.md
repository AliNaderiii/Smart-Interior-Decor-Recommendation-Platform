# MASTER PROMPT 06 — Payment, Email, Storage, Seller Links & External Integrations

## Mission
Replace demo-only assumptions with safe provider adapters and production-like sandbox flows.

## Mandatory virtual team
Delegate to: Integrations Lead (manager), payment engineer, backend API engineer, S3/storage engineer, email/deliverability engineer, seller-link/data-quality engineer, privacy/security reviewer and integration QA.

## Allowed scope
`backend/app/services/payment.py`, `storage.py`, `emailer.py`, `link_checker.py`, relevant integration routes/schemas/tests, integration docs and provider adapters. Do not modify core recommender or frontend except integration request.

## Work
1. Define provider-neutral interfaces and configuration for Zarinpal/Zibal-compatible gateway, mock and sandbox; never store card data.
2. Implement payment state machine: initiated, redirected, verified, failed, expired, refunded if applicable. Make callback/verify idempotent, transaction-safe and replay-resistant; prevent duplicate Pro activation.
3. Separate sandbox and Production credentials/config; validate callback origin and amount/currency/authority.
4. Implement S3-compatible storage with safe key naming, content type/size policy, public vs signed URL decision, lifecycle and deletion behavior.
5. Move long AI extraction and link checking out of request path via a documented queue/background strategy; define retry/dead-letter behavior.
6. Implement real email share with template, localization, expiry, unsubscribe/abuse controls, rate limits and no token leakage in logs.
7. Validate seller URLs with timeout, redirects, canonicalization, SSRF protections, status history and user-facing stale/unavailable state.
8. Write contract tests for adapters and sandbox smoke tests; mock tests must be clearly labeled.

## Evidence
State-machine diagram, API contracts, idempotency tests, sandbox transaction logs with secrets redacted, storage security tests, email preview, link-check report and `docs/agent-reports/integrations-report.md`.

## DoD
Payment cannot double-charge or double-activate; upload cannot execute arbitrary content; failed providers degrade gracefully; link/email jobs are observable; all external dependencies have timeout/retry policy.

## Parallel protocol
Branch `agent/integrations-<date>`. Keep changes inside integration ownership. Shared migration changes require an integration request to the release manager.
