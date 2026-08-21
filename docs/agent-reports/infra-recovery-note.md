# Infrastructure recovery note

Date: 2026-08-21
Branch: `arena/01a0252d-smart-interior-decor-recommend`
Baseline: `7f424f08659d10ca7923e3dc548da6ae355044a7`

## Why this note exists

An earlier infrastructure pass accidentally ran `git reset --hard HEAD~1` after a temporary workflow-permission probe. That destructive operation removed uncommitted tracked-file changes from the working tree. The probe push itself was rejected by GitHub, and the rejection is preserved in `docs/agent-reports/infra-evidence/00-git-push-permission-test.log`.

The recovery did not use another destructive Git operation. `git fsck` was used only for inspection; it found the temporary probe objects but no recoverable copies of the lost tracked-file edits. The surviving untracked files, the committed baseline, prior evidence logs, and the intended Stage 07 requirements were used to reconstruct the work.

## Required safety boundary

No further `git reset --hard`, `git clean -fd`, `git checkout -- .`, `git restore .`, `git rebase`, `git filter-branch`, or force push is permitted for this task. Checkpoint commits will be made after coherent groups of changes. A workflow file must not be pushed with the currently configured GitHub App because the App lacks the `workflows` permission.

## Initial post-incident inventory

The first recovery inventory, before this note was written, was:

- Modified but unstaged: `backend/alembic/versions/0003_product_feedback.py`, `backend/app/core/config.py`, `backend/app/core/security.py`, `backend/requirements.txt`, `backend/scripts/seed_perf_products.py`, `backend/tests/test_perf_v2.py`, `ci/README.md`, `ci/github-ci.yml`, `scripts/audit_docs_links.py`, and `scripts/audit_secrets.py`.
- Untracked: the surviving observability, health, retention, multi-worker, lockfile, compose-overlay, recovery-document, backup-script, Docker-ignore, and evidence files listed by `git status --short` at recovery time.
- Staged: none.

## Changes lost in the reset

The following tracked-file edits were reported lost and have been reconstructed from the baseline and task requirements. They must be treated as reconstructed until re-tested; this note does not assert byte-for-byte equivalence with the lost versions:

- `.env.example`
- `Caddyfile`
- `backend/Dockerfile`
- `backend/app/main.py`
- `backend/app/core/config.py` (observability additions were reconstructed)
- `backend/app/core/security.py` (PyJWT migration was reconstructed)
- `backend/requirements.txt` (dependency change was reconstructed)
- `backend/alembic/versions/0003_product_feedback.py`
- `backend/scripts/seed_perf_products.py`
- `backend/tests/test_idor_rbac.py` (the pre-incident modification was inspected/reasoned about separately; no Stage 07 reconstruction is assumed without evidence)
- `backend/tests/test_perf_v2.py`
- `ci/README.md`
- `ci/github-ci.yml`
- `docker-compose.yml`
- `docker-compose.test.yml`
- `docs/API.md`
- `docs/DEPLOYMENT.md`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `scripts/audit_docs_links.py`
- `scripts/audit_secrets.py`
- `scripts/enable_ci.sh`

## Changes that survived and are being preserved

These files survived as untracked work and are not being discarded:

- `backend/app/core/observability.py`
- `backend/app/api/routes/health.py`
- `backend/tests/test_observability.py`
- `backend/tests/test_audit_retention.py`
- `backend/scripts/verify_multi_worker_redis.py`
- `backend/scripts/prune_audit_logs.py`
- `backend/requirements.lock.txt`
- `backend/.dockerignore` and `frontend/.dockerignore`
- `docker-compose.dev.yml` and `docker-compose.prod.yml`
- `docs/DISASTER_RECOVERY.md`
- `scripts/backup.sh`
- `docs/agent-reports/infra-evidence/**`

## Reconstruction and verification policy

Reconstructed files will be reviewed against the baseline before editing, validated with focused tests, and included in small logical commits. Evidence will distinguish local sandbox execution from checks that require Docker or a real GitHub Actions runner. Any check not run will remain explicitly marked BLOCKED with its command, observed error, and unblock path in the final infrastructure report.
