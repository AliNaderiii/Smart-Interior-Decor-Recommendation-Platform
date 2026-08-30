# Demo container — engineering notes

Companion to `deploy/hf-space/README.md` (which is the Space's own front page).
This file is for us, not the client.

---

## 1. What is in the image, and what it costs

Single container, four services under supervisord, built by the free Hugging
Face Space builder (we do **not** build it in CI — see §4).

| Layer | Contents | Estimated size |
|---|---|---|
| `python:3.12.9-slim` base | Debian slim + CPython 3.12 | ~125 MB |
| PostgreSQL 16 + pgvector (PGDG) | server, client, contrib, the vector extension | ~145 MB |
| Redis server | `redis-server` from Debian | ~15 MB |
| nginx + supervisor + gosu | edge, process manager | ~30 MB |
| Python dependencies | 71 locked packages; no torch, no sentence-transformers | ~180 MB |
| Application | `backend/` 1.2 MB + `datasets/` 224 KB | ~2 MB |
| Built SPA | Vite `dist/` copied from the build stage | ~3 MB |
| **Estimated total** | | **≈ 500 MB (450–560 MB)** |

**This is an estimate, not a measurement.** No container runtime exists in this
sandbox (`docker: command not found`), so the image has never been built here.
The figures come from the published sizes of the base/apt layers and the
measured source tree. First build on the Space will produce the real number —
please relay it, and I will replace this table with the measured values.

Two deliberate choices keep it lean:

* `EMBEDDING_BACKEND=hash`, so `torch` and `sentence-transformers` stay out of
  the lockfile entirely. Adding CLIP would add **~2.5 GB** and a ~600 MB
  first-boot model download — unacceptable on a free tier, and unnecessary for
  a demo whose recommendations are deterministic anyway.
* Multi-stage build: the Node toolchain and the Python wheel-build stage are
  discarded; only `dist/` and the installed site-packages survive.

Free Space limits: 2 vCPU / 16 GB RAM / 50 GB disk. We are far inside them; the
binding constraint is **shared CPU**, which is why G-4.x records the tier
alongside its numbers (deviation D-4d).

---

## 2. Why one container, when production uses five

A Hugging Face Space runs exactly one container. That is the whole reason.
It is a demo-delivery constraint, not an architecture change:
`docker-compose.prod.yml` (separate Postgres, Redis, backend, frontend and
Caddy) is untouched and remains the Stage-5 production topology.

The asset-reuse map (N3) is honoured — the boot sequence is
`scripts/deploy_staging.sh` refolded:

| `deploy_staging.sh` step | Where it lives now |
|---|---|
| 1 environment gate | `demo_env.py` (reads live settings, not a `.env` file) |
| 5 start services | `entrypoint.sh` steps 1–2, then supervisord |
| 6 alembic upgrade head | `entrypoint.sh` step 4 |
| 7 seed catalog + demo accounts | `entrypoint.sh` step 5 (`--if-empty`) |
| 9 demo-refusal invariant | `entrypoint.sh` step 6 (inlined from `prove_demo_refusal.sh`) |
| 8 health | image `HEALTHCHECK` + the workflow's two-consecutive-200s probe |

`scripts/host_prep.sh`, `scripts/render_caddyfile.sh` and the Caddy TLS
evidence stay committed and **parked for Stage 5**.

---

## 3. The docs-off condition (D-4.1), enforced three times

The container runs `APP_ENV=development` on purpose — `validate_runtime()`
refuses production with `AI_PROVIDER=mock` and `STORAGE_BACKEND=local`, which
is exactly the demo profile. So "not production" is **not** a safe test for a
public host, and the interactive API docs needed an explicit switch:

1. **Application** — `API_DOCS_MODE=disabled` feeds `settings.api_docs_enabled`,
   which `app/main.py` uses for `docs_url` / `redoc_url` / `openapi_url`.
   Production remains an unconditional lock inside that property: no mode value
   can reopen docs in production.
2. **Boot gate** — `demo_env.py` refuses to start the container if
   `api_docs_enabled` is true.
3. **Edge** — nginx returns 404 for `/docs`, `/redoc`, `/openapi.json`
   (and `/metrics`), so even a misconfigured rebuild cannot publish them.

The deploy workflow then verifies all three paths against the **live URL**, and
T-4.9 re-verifies as part of the QA sweep.

---

## 4. What is already tested, and what is not — stated plainly

**Already exercised by existing CI jobs** (the demo image reuses these
verbatim):

| Component | Proven by |
|---|---|
| `npm ci` + `npm run build` (identical toolchain, `node:22.14-alpine`) | `frontend` job, every push |
| `requirements.lock.txt` resolving and installing from wheels | `backend` job + `docker` job |
| `alembic upgrade head` against real PostgreSQL 16 + pgvector | `backend` job (PG service container) |
| `load_realistic_products.py --realistic --expand-to 150 --if-empty` | `backend` + `p95-evidence` jobs |
| The demo-refusal invariant logic | `backend` job (`test_security_v2.py`) |
| The new `API_DOCS_MODE` switch and the production lock | `backend` job (3 new tests in `test_security_headers.py`) |
| App behaviour behind a reverse proxy with 2 uvicorn workers + real Redis | `multi-worker` job |

**NOT tested until first activation — untested means untested:**

| Untested thing | Why it cannot be tested here | First real test |
|---|---|---|
| The image actually building | no container runtime in the sandbox (`docker: command not found`) | first Space build |
| PGDG apt repo resolving `postgresql-16-pgvector` on Debian trixie | needs a build | first Space build |
| supervisord actually supervising these two programs | needs a running container | first boot |
| `initdb` + `pg_ctl` as UID 1000 on the Space filesystem | HF-specific filesystem/permissions | first boot |
| nginx binding 7860 and the SPA fallback serving | needs a running container | first boot |
| `huggingface_hub` create/upload/secrets API calls | no HF account or token here | first workflow run |
| End-to-end wake + two-consecutive-200s probe | no public URL yet | first workflow run |

What I *did* verify statically: `entrypoint.sh` is shellcheck-clean;
`supervisord.conf` parses as INI with the expected sections;
`nginx.conf` has balanced braces, no unterminated directives, and the docs-off
locations present; `README.md` front-matter is valid with
`sdk: docker` and `app_port: 7860` matching `EXPOSE` and nginx `listen`;
`ci/stage4-deploy.yml` parses as YAML and its two job guards are mutually
exclusive across all four trigger combinations; `demo_env.py` parses and its
docs truth-table was verified in isolation.

**The first deploy is the acceptance test.** I expect the most likely failure
to be the PGDG apt line or the `initdb`-as-UID-1000 step; both are recoverable
inside the 5-iteration ceiling and neither risks anything outside the Space.

---

## 5. First-deploy sequence

1. Human completes `docs/ops/HF_SPACE_SETUP.fa.md` (HF account, write token,
   `HF_TOKEN` + `HF_USERNAME` repository secrets). ~10 minutes.
2. Supervisor approves the single paste sitting; the human pastes
   `ci/ci.stage4.yml` into the active CI workflow (byte-identical, so it is a
   no-op there) and `ci/stage4-deploy.yml` into a new sibling workflow file
   named stage4-deploy.yml. Until that paste happens the deploy workflow does
   not exist under the workflows directory, which is why it is not linked here.
3. The next push touching `deploy/hf-space/**`, `backend/**` or `frontend/**`
   fires the deploy job. (`workflow_dispatch` only appears once the workflow is
   on the default branch — hence the push trigger.)
4. The job: builds the SPA → assembles the context → creates the Space →
   sets generated demo secrets → uploads → waits for `RUNNING` → probes until
   two consecutive 200s → verifies `/docs`, `/redoc`, `/openapi.json` are closed.
5. Relay back: the run URL, the Space URL, the measured image size from the
   Space build log, and the first-boot `entrypoint.sh` transcript.

Rollback is trivial and costs nothing: delete the Space in the HF UI, or push
a revert. No infrastructure, no billing, nothing to clean up.


---

## 6. BLOCKER — HTTP 402 on Space creation (deploy #7, 2026-08-30)

Deploy #7 (run `33319446945`) reached `Create the Space` with a correct
`SPACE_ID` and the instrumentation returned the real cause verbatim:

```
Could not create the Space — HfHubHTTPError (HTTP 402): 402 Client Error:
Payment Required for url: https://huggingface.co/api/repos/create
(Request ID: Root=1-6a944ac7-3765db443549270f39f9821e;...)
```

**This is not a bug in the workflow, the token, or the container.** Hugging
Face changed its Spaces policy. Per the official docs (Spaces Overview,
"Creating a new Space", read 2026-08-30):

> Static Spaces are free for everyone. Gradio and Docker Spaces run on compute
> and require a paid plan to create: PRO for personal accounts, Team or
> Enterprise for organizations. Free personal accounts in good standing can
> still host up to 2 Gradio Spaces running on ZeroGPU.

Our demo is a **Docker** Space (`space_sdk="docker"` — it must be, since it
runs PostgreSQL + pgvector, Redis, uvicorn and nginx). Docker Spaces now
require **HF PRO**, roughly **$9/month**. The 402 is the Hub correctly
enforcing that on a free account.

`huggingface_hub` itself acknowledges this shape: release note
*"[Fix] Do not fail on create space if exists_ok=True and 402 Payment
required error"* — the 402 on `create_repo` for Spaces is expected behaviour
on non-paid accounts, not an anomaly.

### Why no code fix was attempted

**Directive 3 is ZERO paid host/domain/services.** Every "fix" inside the
workflow would either spend money or defeat the demo:

| Option | Verdict |
|---|---|
| Upgrade to HF PRO (~$9/mo) | **Violates Directive 3.** Requires an explicit human+supervisor decision, not an agent one. |
| Switch to a **static** Space | Free, but serves only static files — no backend, no PostgreSQL, no `/api`. The demo's entire value is the live recommendation flow. Useless here. |
| Switch to a **Gradio** Space | The free ZeroGPU allowance is for Gradio apps; it will not run our multi-service container, and rewriting the product as a Gradio app is a new build, not a deployment. |
| Retry / different token scope | Pointless. 402 is a billing decision, not an auth failure. A write-scoped token still gets 402. |

The workflow is therefore **correct and complete** — it fails exactly where it
should, with an accurate message. It stays committed and unchanged, ready to
run the moment a target that accepts a Docker container exists.

### What is NOT affected

* The demo container itself is unproven but untouched by this — no build has
  ever run, so apt/pgvector and initdb-as-UID-1000 remain **unverified**.
* `scripts/run_local_demo.ps1` (N2, frozen) still gives the client a working
  local demo on the human's Windows laptop, with no hosting at all.
* Everything else in Stage 4 — validator, onboarding pack, docs-off switch,
  CI retiering — is independent of the hosting target and is done.

### Decision required (human + supervisor)

1. **Free alternative host** that accepts a Docker container — the workflow's
   assemble/upload/probe logic ports with modest changes. Candidates need
   checking for a free tier that permits a long-running container.
2. **Accept HF PRO** as the one paid exception, which requires reversing
   Directive 3 explicitly.
3. **Drop public hosting for Stage 4** and demo from the local launcher plus a
   recorded walkthrough, deferring the public URL to Stage 5.

Until one is chosen, T-4.2 (live staging), T-4.8 (G-4.x staging p95) and T-4.9
(QA against the public URL) cannot complete, and I will not claim otherwise.

---

## 7. Final paste — activate verification, retire the doomed deploy workflow

Directive 4 / D-4.5. **One sitting, one commit.** It activates the runner-hosted
verification workflow and removes the deploy workflow, whose every run now fails
with HTTP 402 (IR-S4-003).

Run these from the repository root, on branch
`arena/01a051ef-smart-interior-decor-recommend`:

```bash
git pull origin arena/01a051ef-smart-interior-decor-recommend

# 1. activate the verification workflow
cp ci/stage4-verify.yml .github/workflows/stage4-verify.yml

# 2. retire the deploy workflow: every push currently fires a doomed 402 run.
#    The MIRROR (ci/stage4-deploy.yml) stays committed as the Stage-5 artifact.
git rm .github/workflows/stage4-deploy.yml

# 3. commit and push
git add .github/workflows/stage4-verify.yml
git commit -m "Stage 4 - activate runner-hosted verification, retire the 402 deploy workflow"
git push origin arena/01a051ef-smart-interior-decor-recommend
```

Before committing, confirm the copy is byte-identical:

```bash
md5sum ci/stage4-verify.yml .github/workflows/stage4-verify.yml
# both must print: e1d738c7d6336c5d957f72fe34d7eb6f
```

**What happens next.** That commit adds the workflow at its active path, which
the workflow itself watches, so it fires the first verification run
immediately. Expect it to take a while — it builds the demo image from scratch.

**Expect failures on that first run, and do not be alarmed.** This is the first
time the image has ever been built or booted anywhere. The two likeliest breaks
are the PGDG apt line resolving `postgresql-16-pgvector`, and `initdb` running
as UID 1000. Both are recoverable and neither can affect anything outside the
runner. The agent owns that fix loop.

---

## 8. Re-pasting a fix after a failed verification run

The repo token cannot write `.github/workflows/*`, so every fix to the
verification workflow lands in the mirror `ci/stage4-verify.yml` only, and you
copy it across. This is the loop, repeated once per fix:

```bash
git pull origin arena/01a051ef-smart-interior-decor-recommend

cp ci/stage4-verify.yml .github/workflows/stage4-verify.yml

md5sum ci/stage4-verify.yml .github/workflows/stage4-verify.yml
# both must print the same hash; current mirror: e1d738c7d6336c5d957f72fe34d7eb6f

git add .github/workflows/stage4-verify.yml
git commit -m "Stage 4 - paste verification fix"
git push origin arena/01a051ef-smart-interior-decor-recommend
```

Pushing the active path fires a new verification run automatically.

### Why the workflow now shouts its errors

Raw step logs and job artifacts cannot be downloaded through the API from the
agent's sandbox — GitHub's blob storage closes the connection. Only *check-run
annotations* come back. So the container boot failure path re-emits the
decisive log lines as `::error::` annotations. Those lines are duplicated: they
appear both in the normal step log (for you, in the browser) and as
annotations (for the agent). That redundancy is deliberate — it is the only
channel through which a boot failure can be diagnosed remotely.
