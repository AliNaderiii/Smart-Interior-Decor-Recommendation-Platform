# MASTER PROMPT 08 — Quality Engineering, E2E & Acceptance Certification

## Mission
Certify the platform against the employer's acceptance criteria and expose defects before a client demo.

## Mandatory virtual team
Delegate to: QA Director (manager), test architect, backend/API tester, Playwright E2E engineer, performance engineer, accessibility tester, security regression tester and release/UAT coordinator.

## Allowed scope
`backend/tests/**`, `frontend/tests/**`, test fixtures/scripts, `docs/qa/**`, `docs/agent-reports/qa-*`. Fix production code only for defects discovered in these tests, within a narrowly owned file; otherwise create a defect report/integration request.

## Test matrix
1. Clean install, migration from empty DB, seed, restart and rollback.
2. Homeowner: register/login/logout, quiz validation, recommendation, explanation, free paywall, Pro unlock, moodboard autosave/edit, floorplan, shopping list and seller click.
3. Designer: create multiple projects, run quiz for client, share expiry/link/email, tenant isolation.
4. Admin: upload, AI extraction preview, confidence review/edit/verify, taxonomy, user/subscription management.
5. Negative security: IDOR, RBAC, CSRF, XSS, malicious upload, rate limits, expired share and payment replay.
6. Recommender: all 30 agreed scenarios, no-result, budget edge, unknown features, deterministic ranking and explanation consistency.
7. Performance: p95 <2s with declared concurrency/catalog/cache/worker setup; frontend Lighthouse ≥80, LCP <3s, CLS/INP; mobile slow network.
8. Accessibility: keyboard and axe scan in English and Persian RTL.
9. External contracts: payment sandbox, S3, email and seller-link health.

## Rules
Tests must be deterministic, isolated and data-clean. No sleep-based flakiness; use explicit waits. Capture traces/screenshots/video on failure. Expected 4xx must be asserted precisely. Never use production data or secrets.

## Deliverables
Traceability matrix mapping every requirement to test/evidence, defect backlog with severity, raw reports, CI commands, UAT script and `docs/agent-reports/qa-certification-report.md`.

## Certification
The QA Director may issue PASS, CONDITIONAL PASS or FAIL. Conditional items must list owner and deadline; no vague green status.

## Parallel protocol
Branch `agent/qa-certification-<date>`. Do not rewrite other agents' tests or source without agreement; test infrastructure additions stay in test directories.
