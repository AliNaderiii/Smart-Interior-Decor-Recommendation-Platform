# Stage 04 Production-Readiness Remediation — Evidence Index

Branch: `arena/stage04-production-remediation-2026-08-21` (stacked on PR #9 HEAD
`ded3b5fecb36a8983a6b935c2539d7a002a0730e`). All runs below are **LOCAL
SANDBOX** results, not GitHub CI. Evidence classes are labelled honestly:
**MOCK** (deterministic heuristic — not vision-model accuracy), **LOCAL**
(real service, real code), **BLOCKED** (credential/egress missing — exact
command recorded).

| File | What it shows | Class |
| --- | --- | --- |
| `r00-environment.txt` | Python 3.11.2, fastapi 0.141.1, PG 16.2 + pgvector 0.6.2 (pgserver), redislite-backed Redis 6.2.14, 2 vCPU | — |
| `r01-sqlite-full-suite.log` | `pytest tests/ --ignore=tests/test_pgvector_real.py` → **523 passed, 13 skipped, exit 0** | LOCAL |
| `r03-pg-redis-full-suite.log` | Full suite incl. real-service modules, PostgreSQL `ai_test` + dedicated `decor_pgvector_test` + real Redis → **544 passed, 0 skipped/errors, exit 0** | LOCAL |
| `r04-pgvector-dedicated.log` | `pytest tests/test_pgvector_real.py` standalone (CI-shape env) → **8 passed, exit 0** | LOCAL |
| `r05-redis-real-dedicated.log` | `pytest tests/test_recommender_redis_real.py` → **5 passed, exit 0** | LOCAL |
| `r02-recommender-acceptance.log` | `pytest tests/test_recommender.py` → **30/30, exit 0** (DoD ≥ 28/30) | LOCAL |
| `r06-recommender-scenario-harness.log` | `scripts/evaluate_recommender.py` → **18/18 scenarios, exit 0** | LOCAL |
| `r07-mock-extraction-benchmark.log` | `scripts/evaluate_extraction.py` → MOCK baseline ≥ 0.80, exit 0 — **explicitly labelled MOCK; NOT vision-model accuracy** | MOCK |
| `r08-real-gemini-BLOCKED.log` | `AI_PROVIDER=gemini GEMINI_API_KEY= python scripts/evaluate_extraction.py --real` → refuses (no key); exact command in the transcript | BLOCKED |
| `r09-real-clip-BLOCKED.log` | HF egress probe `http_code=000` (SSL_ERROR_SYSCALL); packages not present in this venv; pointer to the full PR #9 transcript (torch+ST installed, download refused) | BLOCKED |

New remediation coverage (inside r01/r03): provider fail-closed matrix
(`tests/test_provider_fail_closed.py`, 27 tests incl. the 12 required
regression cases), startup embedding validation
(`tests/test_startup_embedding_validation.py`, 8), production seeding
(`tests/test_production_seeding.py`, 8), review-workflow proof
(`tests/test_review_workflow.py`, 5), Gemini-model-default regression, plus
`ruff` / `scripts/audit_secrets.py` / `scripts/audit_docs_links.py` all PASS.

GitHub CI: `ci/github-ci.yml` now provisions a dedicated
`decor_pgvector_test` database and fails the job if the real-service modules
skip — **actual GitHub check status must be read from the PR after push**
(not claimed here).
