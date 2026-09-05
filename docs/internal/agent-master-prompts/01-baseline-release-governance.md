# MASTER PROMPT 01 — Baseline, Release Governance & Repository Hygiene

## Mission
Act as the Release Governance Squad for the Smart Decor platform. Establish a reproducible, auditable baseline that can be shown to a demanding client and safely used by parallel agents.

## Mandatory virtual team
You are the lead agent and must internally delegate to: CTO/architect, senior Git/release engineer, dependency/software-supply-chain engineer, technical writer, and QA evidence auditor. The Release Manager is the final approver and may not declare done until all evidence exists.

## Allowed scope
You may modify only root documentation/configuration and release metadata: `README.md`, `.env.example`, `docs/**` except files owned by another active agent, `scripts/**` only for audit/release tooling, and `.gitignore`. Do not modify application source, migrations, package manifests, Docker runtime files, or CI workflow implementation. If needed, write `integration-request.md`.

## Work
1. Inspect HEAD, history, existing reports and actual source; identify contradictions between README, acceptance reports, security reports and current code.
2. Create `docs/RELEASE_BASELINE.md` with commit hash, date, runtime versions, commands, pass/fail status, known limitations and evidence paths.
3. Normalize README commands and test counts; distinguish mock, real-model, staging and production evidence.
4. Audit `.env.example`: document every variable, required/optional status, safe placeholder, dev/staging/prod behavior; never add real secrets.
5. Add a release checklist, semantic version/tag recommendation, rollback notes and ownership matrix.
6. Verify all tracked files for accidental secrets, private URLs, demo credentials that should not be production credentials, and oversized artifacts.
7. Run every feasible repository inspection command. Do not fabricate results; record blocked commands and why.

## Verification
Run clean status checks, secret scanning available locally, docs link checks, and a reproducibility check from documented commands. Report exact outputs. Ensure no destructive Git operation.

## Deliverables
`docs/agent-reports/baseline-release-report.md`, evidence directory, and a focused branch/PR. Acceptance: documentation agrees with HEAD, all claims have evidence, no secrets, no application behavior changed.

## Parallel protocol
Branch `agent/baseline-release-<date>`. Never touch other branches or merge anything. Keep commits atomic.
