# Stage 04 evidence index — AI Recommender, Extraction & Data Quality

Branch `arena/01a02613-smart-interior-decor-recommend`, base `a07f014`,
2026-08-21 (UTC). Environment of record: see `00-environment.txt`
(Linux 6.1.158+, 2 vCPU, 3.8 GiB; PostgreSQL 16.2 + pgvector 0.6.2 via
pgserver; Redis 6.2.14 via redislite; Python 3.11.2, venv with
`backend/requirements.lock.txt`; pypi reachable, huggingface.co and
download.pytorch.org BLOCKED; no AI provider keys present).

Evidence classes used in the file names:
- plain `log`/`json` — executed in this sandbox (LOCAL class for services,
  MOCK class where the provider is the deterministic heuristic);
- `BLOCKED` — could not be executed; the exact command and error are inside.

| File | What it proves |
|---|---|
| `00-environment.txt` | Environment of record for every number below |
| `01-mock-extraction-benchmark.log` | 50-image MOCK benchmark run, labelled MOCK, with per-feature P/R, calibration, latency, review rate |
| `mock-extraction-report.json` | machine-readable version of the above (mode/is_mock/disclaimer/versions) |
| `02-real-provider-benchmark-BLOCKED.log` | exact blocked commands (gemini + openai, empty keys) and the unblock path |
| `03-clip-verification-BLOCKED.log` | torch+sentence-transformers installed OK; HuggingFace model download blocked (curl 000 + OSError) |
| `04-sqlite-suite.log` | full suite, SQLite + fakeredis: 463 passed, 13 skipped, exit 0 |
| `05-pg-redis-parity-suite.log` | full suite, real PG 16.2 + pgvector 0.6.2 + real Redis 6.2.14: 476 passed, exit 0 |
| `06-pgvector-real-tests.log` | dedicated-DB pgvector module: migrations to head, vector(512) column, HNSW index, wrong-dim rejected, hard filters, determinism, recall ≥ 0.95, no-result, plan capture |
| `07-acceptance-30-scenarios.log` | the 30 recommender acceptance tests: 30/30 (DoD ≥ 28/30) |
| `08-recommender-scenario-harness.log` | 18/18 harness scenarios incl. tie-break, no-result, diversity, explanation fidelity, budget edges |
| `recommender-scenarios.json` | machine-readable per-scenario results with versions |
| `09-bench-pgvector.log` | DB-level plans + latency at exactly 1,000 and 11,000 rows; HNSW probe showing ef_search 40 → 40/100 truncation vs 400 → 100/100 |
| `bench-pgvector-1000.json` / `bench-pgvector-10000.json` | machine-readable benchmark output incl. full EXPLAIN plans |
| `10-app-level-latency-11k.log` | app-level /recommend on the 11k catalog: cold p95 227 ms, warm (Redis) p95 2 ms |

Reproduction commands are in `docs/ai/evaluation-report.md` §8.
