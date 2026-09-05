# MASTER PROMPT 07 — Production Infrastructure, CI/CD & Observability

## Mission
Make deployment repeatable, secure and observable on a real cloud target while remaining portable across AWS/Arvan/Liara-style infrastructure.

## Mandatory virtual team
Delegate to: Platform/DevOps Lead (manager), cloud architect, Docker/Linux engineer, CI engineer, SRE/observability engineer, database reliability engineer, network/TLS engineer and cost analyst.

## Allowed scope
`docker-compose*.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `Caddyfile`, `.github/workflows/**` (or canonical CI location), deployment docs/scripts and observability config. Do not change app business logic.

## Work
1. Define dev/staging/production topology, domains, TLS termination, proxy headers, CORS origin and secret management.
2. Make containers non-root where feasible, minimal, pinned and health-checked; add readiness versus liveness checks for app, DB, Redis and storage.
3. Ensure PostgreSQL 16 + pgvector migrations, indexes, connection pool, backup/restore and rollback are documented and tested.
4. Require real Redis in production; verify cache, rate limit and token blacklist behavior across multiple workers.
5. Activate CI on pull requests: install, lint, typecheck, unit/integration tests, PostgreSQL/pgvector and Redis services, dependency audit, build, image scan and artifact upload.
6. Add deployment gate for real AI benchmark, seller-link check, Lighthouse and smoke tests; never place secrets in workflow logs.
7. Configure structured logs, request IDs, metrics for latency/error/rate-limit/AI cost/payment states, error tracking and alert thresholds. Redact tokens and PII.
8. Document zero-downtime/rollback strategy, migrations, incident response, restore RTO/RPO and cost estimate.
9. Test TLS 1.3, security headers, cache policy and preview host behavior.

## Evidence
CI run URL or local equivalent, image scan output, health checks, migration/restore transcript, TLS/header scan, load test with worker count, architecture diagram and `docs/agent-reports/infra-report.md`.

## DoD
A new operator can deploy from docs; failed deploy has rollback; staging is reachable over TLS; CI is actually triggered, not merely present as an unused file; no P0 operational gap.

## Parallel protocol
Branch `agent/infra-cicd-<date>`. Own infrastructure/CI only. Do not edit application source or package manifests without integration request.
