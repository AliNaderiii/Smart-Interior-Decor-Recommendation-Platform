# Staging Deployment Runbook — Smart Interior Decor Platform

**Stage 4 · T-4.1** · English runbook with a Persian quick section (§9)
**Audience:** the human operator on the staging host. The agent sandbox has no
public egress and cannot host anything, so **every step here is executed by a
human and its raw output relayed back** as evidence.

**Time to first live URL:** ~25 minutes on a fresh VPS (≈8 min host prep, ≈12 min
first Docker build, ≈2 min ACME + health, ≈3 min verification).

---

## 0. Before you start — the two prerequisites

| # | Prerequisite | How to confirm |
|---|---|---|
| 1 | A VPS: **2 vCPU / 4 GB RAM / 40 GB SSD / Ubuntu 24.04 LTS**, root SSH-key access, ports 22/80/443 reachable | `ssh root@<IP> 'nproc; free -h; df -h /'` |
| 2 | A DNS **A record** for your chosen hostname pointing at the VPS IPv4, already propagated | `dig +short staging.<domain>` prints the VPS IP |

> **DNS must resolve before the first deploy.** Caddy obtains the Let's Encrypt
> certificate over an HTTP-01 challenge on port 80; if the name does not point
> here yet, the deploy fails at step 8 with a health-check timeout — no damage,
> just re-run once DNS is live.

If you use Cloudflare, keep the record **DNS-only (grey cloud)**. Orange-cloud
proxying terminates TLS at Cloudflare and makes the TLS 1.3 evidence
(`openssl s_client`) measure Cloudflare's edge instead of our origin.

---

## 1. Host preparation (once per server)

```bash
ssh root@<VPS_IPv4>
curl -fsSLO https://raw.githubusercontent.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/arena/01a051ef-smart-interior-decor-recommend/scripts/host_prep.sh
bash host_prep.sh
```

`scripts/host_prep.sh` is idempotent — safe to re-run any time. It installs:

| Step | What | Why |
|---|---|---|
| 1 | curl, git, jq, openssl, ufw, psql-16, cron, logrotate | tooling the deploy and ops scripts assume |
| 2 | Docker Engine + compose plugin (official apt repo) + **10 MB × 5 log rotation** | container logs otherwise fill a 40 GB disk in weeks |
| 3 | non-root **`deploy`** user in the `docker` group, root's SSH keys copied over | nothing runs the app as root |
| 4 | **UFW**: deny incoming; allow only 22/80/443 | Postgres and Redis are never published to the host — they are reachable only on the compose network |
| 5 | unattended-upgrades | security patches without a human |
| 6 | **2 GB swap** | 4 GB RAM is tight while PG builds the pgvector HNSW index during the seed |
| 7 | SSH hardening: no password auth, no root password login | only applied if `deploy` already has an authorized key — it will not lock you out |

Verify, and **relay this output**:

```bash
bash host_prep.sh --check
```

Expected shape:

```
os              : Ubuntu 24.04.x LTS
cpus            : 2
memory          : 3.8Gi
disk (/)        : 34G free of 39G
docker          : Docker version 27.x.x, build ...
compose plugin  : Docker Compose version v2.x.x
deploy user     : uid=1001(deploy) gid=1001(deploy) groups=1001(deploy),988(docker)
ufw             : Status: active
swap            : /swapfile 2G
```

---

## 2. Clone and configure

```bash
su - deploy
git clone https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform.git app
cd app
git checkout arena/01a051ef-smart-interior-decor-recommend
cp .env.staging.example .env
chmod 600 .env
```

Generate the four secrets **on the host** and paste them into `.env` — never
reuse a development value, never send them through chat:

```bash
openssl rand -hex 32                                             # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FERNET_KEY
openssl rand -base64 24                                          # POSTGRES_PASSWORD
openssl rand -base64 18                                          # DEMO_ACCOUNT_PASSWORD
```

Then fill every `[FILL]` marker. The host-keyed values must all agree:

```
STAGING_HOST=staging.example.com
FRONTEND_ORIGIN=https://staging.example.com
PAYMENT_CALLBACK_URL=https://staging.example.com/payment/callback
EMAIL_FROM=noreply@staging.example.com
ACME_EMAIL=ops@example.com
DATABASE_URL=postgresql+psycopg://decor:<same POSTGRES_PASSWORD>@postgres:5432/decor
```

Check your work before deploying anything:

```bash
python3 scripts/assert_staging_env.py .env --host staging.example.com
```

This is the same gate the deploy runs. It must print `RESULT: PASS` with
exactly **2 documented waivers** (`AI_PROVIDER=mock`, `STORAGE_BACKEND=local` —
supervisor ruling R3). Anything else lists the precise fix.

### Why `APP_ENV=development` on a public host (decision D-4.1)

Ruling R3 says staging runs with **no AI key and no S3 bucket**.
`Settings.validate_runtime()` *correctly refuses* to boot `APP_ENV=production`
with `AI_PROVIDER=mock` or `STORAGE_BACKEND=local`, and demo accounts are
refused under production unconditionally. We did **not** weaken that check
(gate discipline). Instead:

* `docker-compose.staging.yml` pins the production-shaped settings explicitly
  (secure+strict cookies, JSON logs, shared Redis, resource limits);
* `scripts/assert_staging_env.py` re-asserts the production checks that still
  matter on a public host and **fails the deploy** if any is missing;
* every deploy re-proves that `APP_ENV=production` still refuses demo accounts
  (`scripts/prove_demo_refusal.sh`, step 9).

Stage 5 production cutover swaps in `docker-compose.prod.yml` with a real AI
key and S3 bucket; every production fail-safe then applies unchanged.

---

## 3. Deploy

```bash
./scripts/deploy_staging.sh 2>&1 | tee ~/deploy-run1.log
```

Preview the plan without touching anything first, if you like:

```bash
./scripts/deploy_staging.sh --dry-run
```

The pipeline, in order:

| Step | Action | Fails when |
|---|---|---|
| 0 | preflight: tools, repo root, `.env` present and `chmod 600` | a tool is missing → run `host_prep.sh` |
| 1 | environment gate (`assert_staging_env.py`) | any weak/unfilled value — **nothing is deployed** |
| 2 | `git pull --ff-only` on the current branch (`--no-pull` to skip) | local commits diverge |
| 3 | render `Caddyfile.staging` from the committed `Caddyfile` | see §4 |
| 4 | `docker compose build` (brand args from `.env`) | build error |
| 5 | `docker compose up -d --remove-orphans` | port 80/443 already in use |
| 6 | wait for `alembic current` to report `(head)` (up to 5 min) | migration error |
| 7 | seed the 150-product catalog `--if-empty` + demo accounts | fewer than 150 rows afterwards |
| 8 | health: container-internal, then **public HTTPS** (30 × 10 s) | DNS not propagated, port 443 blocked, ACME failed |
| 9 | re-prove the production demo-account refusal | the invariant regressed |
| 10 | `smoke_staging.sh` against the public origin | any smoke check fails |
| 11 | append an end-state fingerprint | — |

### Idempotency evidence (T-4.1 DoD)

Run it **three times** and relay all three logs:

```bash
./scripts/deploy_staging.sh 2>&1 | tee ~/deploy-run1.log
./scripts/deploy_staging.sh 2>&1 | tee ~/deploy-run2.log
./scripts/deploy_staging.sh 2>&1 | tee ~/deploy-run3.log
cat deploy-state/fingerprint.log
```

On run 3 the script itself prints the verdict:

```
OK   IDEMPOTENCY PROVEN: 3 runs, 1 distinct end state (<hash>)
```

The fingerprint covers commit, alembic revision, product count, user count,
running services, image-id digest and the Caddyfile hash. Product and user
counts must **not** grow across runs — that is what `--if-empty` and the demo
gate guarantee.

---

## 4. What the Caddy render does — and never does

`scripts/render_caddyfile.sh` derives `Caddyfile.staging` from the committed
`Caddyfile`, changing **exactly three lines**:

| From | To |
|---|---|
| `:443 {` | `staging.example.com {` |
| `tls internal {` | `tls {` (real Let's Encrypt cert; `protocols tls1.3 tls1.3` untouched) |
| `email admin@smartdecor.local` | `email <ACME_EMAIL>` |

Everything else is copied byte-for-byte, and the script **verifies the header
block is identical afterwards** and deletes its own output if it is not. This
matters because the CSP in the `Caddyfile` is generated from `build_csp()` and
pinned byte-for-byte by `backend/tests/test_csp_alignment.py` in blocking CI —
hand-editing it breaks the build. To change the CSP, change the image-host
settings and re-run `python backend/scripts/print_csp.py --reference`.

`Caddyfile.staging` is gitignored: it embeds the real hostname and is
regenerated on every deploy.

---

## 5. Verify, and relay this evidence

```bash
# a) public health + headers
curl -sSi https://staging.example.com/api/v1/health/ready

# b) TLS 1.3 handshake (T-4.2 DoD, closes the Stage-3 BLOCKED-with-recipe item)
openssl s_client -connect staging.example.com:443 -servername staging.example.com -tls1_3 </dev/null 2>&1 | head -30

# c) TLS 1.2 must be refused if you pinned 1.3-only
openssl s_client -connect staging.example.com:443 -tls1_2 </dev/null 2>&1 | head -10

# d) full header profile
curl -sSI https://staging.example.com/

# e) full smoke suite
./scripts/smoke_staging.sh https://staging.example.com --verbose

# f) service state
docker compose -f docker-compose.yml -f docker-compose.staging.yml ps
```

`smoke_staging.sh` checks: DNS, the http→https redirect, the TLS 1.3 handshake,
seven security headers plus `Server` suppression, both health endpoints, the
SPA index, a real register+login round-trip on a throwaway account, an
authenticated non-empty catalog read, and reports whether `/docs` is exposed.
It exits non-zero if any check fails.

**No one may claim the staging URL works without (a), (b) and (e) pasted into
the evidence pack.** That is the honesty protocol, not a formality.

---

## 6. Demo credentials

The three demo logins (`admin@`, `designer@`, `demo@smartdecor.dev`) are created
with your randomized `DEMO_ACCOUNT_PASSWORD`, **not** the documented dev
defaults, because this host is public.

Deliver them to the supervisor **out-of-band** (password manager or a private
channel). Never commit them, never put them in a ticket, never paste them into
a report. See client decision **C-7** for whether they survive into production
(recommendation: they do not).

---

## 7. Rollback

The deploy is a git checkout plus containers, so rollback is a checkout plus a
redeploy:

```bash
cd ~/app
git log --oneline -10                 # find the last good commit
git checkout <good_sha>
./scripts/deploy_staging.sh --no-pull 2>&1 | tee ~/rollback.log
```

**Database rollback is different and dangerous.** Alembic downgrades are not
exercised by CI. If a migration is the problem, restore from a backup instead:

```bash
./scripts/backup_db.sh backups 7        # take a fresh dump FIRST, always
./scripts/restore_db.sh backups/<file>.dump
```

Full procedure, including the scratch-database drill: `docs/ops/RUNBOOK_STAGING.md`
and `docs/DISASTER_RECOVERY.md`.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| step 8 times out, `curl` returns 000 | DNS not propagated | `dig +short staging.<domain>`; wait for TTL, re-run the deploy |
| step 8 returns 502 | backend unhealthy behind Caddy | `docker compose ... logs backend --tail 100` |
| Caddy log: `challenge failed` | port 80 blocked or a proxy in front | `ufw status`; set Cloudflare to DNS-only |
| step 1 fails on `FERNET_KEY` | left empty or copied a truncated value | regenerate with the command in §2 |
| step 7: fewer than 150 products | seeder could not read the dataset | `docker compose ... exec backend ls -l datasets/products_realistic_150.json` |
| `port is already allocated` | another web server on 80/443 | `sudo ss -lptn 'sport = :443'`; stop nginx/apache |
| build killed / OOM | swap missing | re-run `host_prep.sh` (step 6 adds 2 GB swap) |
| step 9 fails | the production demo-account refusal regressed | **stop** — this is a critical security regression, report it before touching anything |

Log locations:

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml logs -f backend
docker compose -f docker-compose.yml -f docker-compose.staging.yml logs -f caddy
ls -la deploy-state/          # fingerprints + demo-refusal transcripts
```

---

## 9. راهنمای سریع فارسی — استقرار استیجینگ

**پیش‌نیاز:** یک سرور اوبونتو ۲۴.۰۴ (۲ هسته، ۴ گیگ رم، ۴۰ گیگ دیسک) و یک رکورد
DNS از نوع A که نام دامنه را به IP سرور اشاره داده باشد.

```bash
# ۱) آماده‌سازی سرور (یک‌بار، با کاربر root)
bash host_prep.sh

# ۲) کلون و تنظیمات (با کاربر deploy)
git clone <repo> app && cd app
cp .env.staging.example .env && chmod 600 .env
nano .env            # همهٔ موارد [FILL] را پر کنید

# ۳) بررسی تنظیمات پیش از استقرار
python3 scripts/assert_staging_env.py .env --host staging.example.com

# ۴) استقرار (سه بار اجرا کنید تا تکرارپذیری اثبات شود)
./scripts/deploy_staging.sh 2>&1 | tee ~/deploy-run1.log

# ۵) تأیید نهایی
./scripts/smoke_staging.sh https://staging.example.com
```

**نکات مهم:**

* رمزها را فقط روی خود سرور بسازید؛ هرگز در مخزن یا در چت قرار ندهید.
* فایل `.env` باید دسترسی `600` داشته باشد.
* اگر مرحلهٔ ۸ خطا داد، معمولاً یعنی DNS هنوز آماده نیست — چند دقیقه صبر کنید و
  دوباره اجرا کنید. اسکریپت قابل اجرای مجدد است و چیزی خراب نمی‌شود.
* حساب‌های دمو با رمز تصادفی ساخته می‌شوند و فقط روی استیجینگ وجود دارند.
* خروجی هر سه اجرا و همچنین خروجی `openssl s_client` را برای ثبت شواهد ارسال کنید.
