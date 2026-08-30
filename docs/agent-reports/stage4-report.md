# Stage 4 — Staging Deployment, Demo Productization & Client Onboarding Pack

**Branch:** `arena/01a051ef-smart-interior-decor-recommend` (D-0: platform-locked name; equivalent to `agent/stage4-staging-demo`)
**Baseline:** `main` = `bd3cb52d` = `v0.7.0` (Stage 3 merged, supervisor-verified 2026-08-30)
**Status:** **KICKOFF POSTED — AWAITING SUPERVISOR APPROVAL** (Directive 0 §1c gate; no further work started)

---

## D-0 · Setup actions completed (pre-gate, permitted by Directive 0 §1)

| Action | Result |
|---|---|
| Branch from `main` @ `bd3cb52d` | done — `arena/01a051ef-smart-interior-decor-recommend` |
| Read IR ledger `integration-request.md` | done — open items inherited: **IR-S3-002** (contract p95, owner = this stage, G-4.x) |
| Read `stage2-report.md`, `stage3-report.md`, `docs/reports/ACCEPTANCE_EVIDENCE.md`, `docs/DR_DRILL.md` | done |
| `ci/ci.stage4.yml` = byte-identical copy of active workflow at main | done — commit `22d227d`; `md5sum` both files = `4ff82072e0da8d3aa6167d5e26b83705`; `diff` = empty |

**I1 honesty note — push #1 (`22d227d`).** Intent: commit the unchanged CI baseline copy only (no workflow file touched, no source touched). Post-push verdict to be recorded verbatim below once the run concludes; this commit changes no code path exercised by CI, so a red result would be a pre-existing/infra condition and will be reported as such, not re-rolled.

---

## §1 SUPERVISOR SHOPPING LIST (critical path — host + domain)

Nothing else in the host wave can start until these two purchases exist. Sandbox has **no public egress and cannot host** — every host action below is a human-executed runbook with relayed evidence.

### 1.1 VPS — required spec (hard minimums)

| Item | Requirement | Why |
|---|---|---|
| vCPU | **2** (dedicated preferred over shared/burst) | G-4.x contract gate needs the backend NOT to contend with the load client; IR-S3-002 root cause was 4 processes on 2 shared vCPU |
| RAM | **4 GB** | PG16+pgvector (HNSW build) + Redis AOF + 2 uvicorn workers + Caddy ≈ 2.6 GB steady, 3.4 GB peak during seed |
| Disk | **40 GB SSD** | images/moodboards + PG volume + 7-day backup retention |
| OS | **Ubuntu 24.04 LTS**, clean, root SSH key access | matches `docs/DEPLOYMENT.md` |
| Network | public IPv4, ports 22/80/443 open, **unfiltered egress to generativelanguage.googleapis.com** | Gemini calls; if blocked → mock mode (see §1.4) |

### 1.2 Provider options

| Option | Est. cost/mo | Gemini egress | Latency to IR users | Zarinpal | Trade-off |
|---|---|---|---|---|---|
| **A (recommended for staging): Hetzner CX22 (Nuremberg/Helsinki)** | **€3.79 ≈ $4.2** | ✅ direct, no proxy | ~90–140 ms RTT from Tehran | callback works (Zarinpal calls our public HTTPS URL; no IR-origin requirement in sandbox) | cheapest + real Gemini; some IR ISPs throttle EU routes → demo over a stable link |
| B: Contabo / Netcup VPS (DE) | $5–7 | ✅ | ~100–160 ms | ✅ | similar; noisier neighbours → worse p95 tail, risks G-4.x |
| C (Iranian): **Liara** (Docker/PaaS) | ~450–700k IRR (~$7–11) | ❌ Gemini blocked at origin → needs proxy or mock | ~15–35 ms (best demo feel) | ✅ native, best for production Zarinpal | fastest UX, but AI features need C-01-style workaround; PaaS constrains our compose+Caddy stack |
| D (Iranian): **ArvanCloud IaaS** | ~600k–1M IRR (~$10–16) | ❌ same | ~15–40 ms | ✅ | full VPS (our compose works as-is), pricier, same Gemini limitation |

**Squad recommendation:** **Option A (Hetzner CX22) for Stage-4 staging** — it is the only option that exercises the real Gemini path end-to-end, which the demo depends on, at the lowest cost. Plan the **production** host as C or D in Stage 5 (Iranian latency + Zarinpal + local billing), with the AI path resolved by client decision C-01/§AI-access in `CLIENT_ONBOARDING.md`. Staging on A does **not** lock production.

### 1.3 Domain / DNS

Cheapest path: a **subdomain of a domain the client already owns**, else a new one.

| Option | Cost/yr | Records to create |
|---|---|---|
| Subdomain of existing client domain (**preferred, free**) | 0 | `A  staging  →  <VPS_IPv4>`  (TTL 300) |
| New `.ir` domain (nic.ir) | ~ 65k IRR/yr | `A  @ → <IP>`, `A  www → <IP>` |
| New `.com` (Cloudflare/Namecheap) | $10–13 | same |

Also required regardless: `AAAA` only if IPv6 enabled (else omit), and **no proxying (grey cloud) on Cloudflare for staging** — Caddy must terminate TLS itself to produce the TLS 1.3 `openssl s_client` evidence and to complete ACME HTTP-01.

**Requested from supervisor:** the final hostname (e.g. `staging.<client-domain>`) **before** T-4.2, because Caddy's ACME and the CSP/CORS origin list are keyed to it.

### 1.4 Other accounts (nice-to-have, with fallbacks — none block the stage)

| Item | Cost | Fallback if not purchased |
|---|---|---|
| Zarinpal **sandbox** merchant ID | free | sandbox is free; real merchant is a Stage-5/client task (T-4.6 §2) |
| Telegram bot token (uptime alerts) | free (@BotFather, 2 min) | probe writes to `uptime.log` + local `logger` only; evidence still valid |
| S3-compatible bucket (ArvanCloud/Backblaze B2) | $0–1 | **documented local fallback**: `/srv/decor/media` volume + nightly tar into backup set |
| Gemini API key (staging-only, low quota) | free tier | `AI_PROVIDER=mock` — deterministic extractor already in repo; demo still complete, flagged as mock on screen |

### 1.5 Exact post-purchase commands the human runs (copy-paste)

```bash
# 0) from your laptop, after DNS A-record is created
dig +short staging.<domain>            # must print the VPS IPv4 before step 3
ssh root@<VPS_IPv4>

# 1) host prep (idempotent; script delivered by T-4.1)
curl -fsSL https://raw.githubusercontent.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/arena/01a051ef-smart-interior-decor-recommend/scripts/host_prep.sh -o host_prep.sh
bash host_prep.sh            # docker, ufw 22/80/443, deploy user, unattended-upgrades, swap

# 2) as the deploy user
su - deploy
git clone https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform.git app && cd app
git checkout arena/01a051ef-smart-interior-decor-recommend
cp .env.staging.example .env && chmod 600 .env && nano .env    # fill secrets ON HOST ONLY

# 3) one-command deploy (run it 3× for the idempotency evidence)
./scripts/deploy_staging.sh 2>&1 | tee ~/deploy-run1.log
```
Relay back: `deploy-run{1,2,3}.log`, `docker compose ps`, `curl -i https://staging.<domain>/api/health`, `openssl s_client -connect staging.<domain>:443 -tls1_3 </dev/null`.

---

## §2 Task sequencing — AGENT-EXECUTABLE vs HUMAN-ON-HOST

### 2.1 Agent-executable now (no host, no egress) — runs while the human provisions

| Task | Deliverable | Owner |
|---|---|---|
| T-4.1 | **scripts/host_prep.sh**, **scripts/deploy_staging.sh**, **scripts/smoke_staging.sh**, **.env.staging.example**, **docs/ops/DEPLOY_STAGING.md** (all planned, not yet created); shellcheck-clean locally | SA-2 |
| T-4.3a | **scripts/uptime_probe.sh**, **scripts/backup_nightly.sh** (7-day retention), logrotate unit, **docs/ops/RUNBOOK_STAGING.md** (planned) | SA-3 |
| T-4.4 | `VITE_BRAND_NAME` / logo slot / color-token override + Persian copy pass; `docs/DESIGN_SYSTEM.md` theming section; local before/after screenshots | SA-4 |
| T-4.5 | Persian storyboard + narration + click-path; **docs/SALES_ONEPAGER.md** (planned; evidence-backed numbers only) | SA-5 |
| T-4.6 | **docs/CLIENT_ONBOARDING.md**, **datasets/catalog_template.csv** + **datasets/catalog_template.json**, **scripts/validate_catalog.py** + tests (all planned), SLA menu, ≤5-business-day timeline | SA-6 |
| T-4.9a | QA matrix harness + checklist, run locally against docker-compose as a dry run | SA-7 |
| Regression | re-prove `APP_ENV=production` refuses demo seeding (invariant 3) | SA-7 |

### 2.2 Human-on-host (blocked on §1 purchases + supervisor green-light)

| Task | Human runs | Relays back as evidence |
|---|---|---|
| T-4.2 | `host_prep.sh`, `deploy_staging.sh` ×3 | 3 deploy logs, `compose ps`, `alembic current`, product count = 150, `curl -i /api/health`, `openssl s_client` TLS 1.3 dump, header dump |
| T-4.3b | enable cron probe + nightly backup | ≥24 h `uptime.log` tail, 2 nights (or forced-run) backup listing + sizes |
| T-4.7 | `backup_db.sh` → `restore_db.sh` into scratch DB | row counts before/after, pgvector index `\di` + `ivfflat/hnsw` sanity query, wall-clock duration |
| T-4.8 (G-4.x) | `load_recommend.py --samples 250 --concurrency 20` **from a laptop/second host**, target = staging origin | verbatim stdout + JSON → ACCEPTANCE_EVIDENCE row 5 verdict; IR-S3-002 closed or escalated with full distribution |
| T-4.9b | clean-profile E2E + 375 px + keyboard + incognito share link | screenshots, console log, HAR |

**Relay loop for each:** agent ships script + expected-output block → human runs → pastes raw output → agent commits it verbatim under `docs/agent-reports/stage4-evidence/<task>/` and signs DoD. No live-URL claim without an HTTP capture.

## §3 CI paste plan (budget ≤ 1 paste, currently **0 planned**)

`ci/ci.stage4.yml` is committed byte-identical (`22d227d`). Stage-4 deliverables are scripts + docs + a frontend env-driven brand switch; none require a new CI job, and the contract p95 gate is measured **on the staging host**, not in CI. **Therefore no paste is requested at this time.** The single paste is held in reserve for exactly one contingency: if T-4.4's brand switch or `validate_catalog.py` needs a test hook in the blocking suites, we will submit a §-numbered hand-off note (paste target `.github/workflows/ci.yml`, source `ci/ci.stage4.yml`, delta summary) for supervisor approval before any human paste.

## §4 T-4.6 outline — every open client decision mapped to a section

| Section of **docs/CLIENT_ONBOARDING.md** (Persian, planned) | Content | Open decision closed |
|---|---|---|
| §1 کلید هوش مصنوعی | Gemini/OpenAI key how-to + Iran-access options (proxy / self-host / mock+manual review) + our recommendation | — (feeds C-01 context) |
| §2 درگاه پرداخت | Zarinpal merchant steps, sandbox → live | — |
| §3 کاتالوگ واقعی | catalog templates (CSV + JSON) + the catalog validator, Persian error messages | — |
| §4 دامنه و DNS | domain/subdomain table + exact records + hosting form | — |
| §5 ایمیل فرستنده | SMTP vs provider options | — |
| §6 تصمیم‌های باز مشتری | plain-Persian one-pager per decision | **C-01** KMS provider · **C-02** audit retention 180d · **C-03** link-check policy · **C-6** recommender weights (`current` vs `client-ad`, with the 18/18 scenario evidence) · **C-7** demo-account policy on staging |
| §7 پشتیبانی و SLA | SLA/support menu draft (3 tiers) | — |
| §8 بعد از تحویل ورودی‌ها | ≤ 5 business-day timeline to production | — |

---

## §5 What I need from the supervisor to proceed

1. **Approval of this kickoff** (Directive 0 §1c gate — I am stopped here).
2. Purchase decision on §1.2 (recommend **A · Hetzner CX22**) and §1.3 hostname.
3. Green-light before **any** real-host step (Directive 0 §5).

Pending approval, **no** agent-side task has been started.

---

## §6 I1 honesty log — pushes this session

| # | Commit | Intent (pre-push) | Verdict (post-push, verbatim) |
|---|---|---|---|
| 1 | `22d227d` | commit `ci/ci.stage4.yml` byte-identical baseline, nothing else | run **33303430399** — superseded by push #2 before conclusion |
| 2 | `25a76bf` | kickoff report only, no code | run **33303484765** — **FAILURE**. Job *Security & docs gates*, step **Documentation link audit**. Reproduced locally: `[MISSING FILE REFERENCES] 13 … RESULT: FAIL` — the audit resolves backticked paths in the new report to files Stage 4 has not created yet. Disclosed, not re-rolled. |
| 3 | `4th commit` (link-audit fix) | de-backtick planned-artifact paths in the report only; no gate weakened, no audit config touched | run **33303746290** — **SUCCESS**, all 9 jobs green (backend, frontend, e2e, security & docs gates, docker, multi-worker, p95-evidence, lighthouse, link-liveness). |

Local reproduction after fix, verbatim: `[BROKEN LINKS] 0` / `[MISSING FILE REFERENCES] 0` / `RESULT: PASS`.
