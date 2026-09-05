# Internal — build-process artefacts

Working documents from the way this platform was built (staged, agent-assisted
development with human review at every gate). They are kept for
traceability — every decision, waiver and change request is on record — but
they are **not product documentation** and nothing in the runtime, CI or
release process depends on them.

| File | What it is |
|---|---|
| `agent-master-prompts/` | Per-stage briefs (governance, security, recommender, RTL/UX, infra, QA, sales/demo) and the session-kickoff template |
| `ADVANCED_MASTER_PROMPT_V2.md`, `CONTINUATION_PROMPT_V2.md` | V2 "strict mode" briefs |
| `MASTER_PROMPT_V3_DATASETS_INTEGRATION.md` | V3 brief for the realistic-dataset integration |
| `PHASE0_AUDIT_GUIDE.md` | The original dead-key / dead-link audit procedure (superseded by `scripts/auditDeadKeys.ts` and `tests/e2e/deadKeys.spec.ts`) |
| `integration-request.md` | Cross-stage change requests (IR-xxx) with their resolutions |

Moved here from the repository root on 2026-09-05. `scripts/audit_docs_links.py`
skips the prompt files by default (they intentionally reference files that
did not exist yet when they were written); pass `--include-prompts` to audit
them anyway.

For the product itself start at the top-level [README](../../README.md), then
[`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) and
[`docs/RELEASE_CHECKLIST.md`](../RELEASE_CHECKLIST.md).
