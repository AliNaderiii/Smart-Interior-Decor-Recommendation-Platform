# Demo accounts — how they work, and why production can never have them

**Status:** authoritative. Code that creates demo logins lives in exactly one
module, `backend/app/core/demo_seed.py`, and this document describes its
contract.

---

## 1. The problem this replaces

Before Stage 03 both seeding entrypoints contained their own inline copy of a
default-account block:

* `backend/scripts/load_realistic_products.py` → `ensure_default_accounts()`
* `backend/scripts/seed_products.py` → an inline block inside `seed()`

Neither checked the environment, and `docker-compose.yml` runs the first one on
**every backend container start**:

```yaml
command: sh -c "... && python scripts/load_realistic_products.py --realistic --if-empty && uvicorn app.main:app ..."
```

The result was a production deployment that created, unprompted:

| Email | Password | Role |
| --- | --- | --- |
| `admin@smartdecor.dev` | `Admin123!` | **admin** |
| `designer@smartdecor.dev` | `Design123!` | designer |
| `demo@smartdecor.dev` | `Demo1234!` | homeowner |

…with the same credentials published in `README.md`, the walkthrough docs and
the SPA login page. This is Baseline blocker **B-1** and threat **T-01**.
Reproduction: `docs/agent-reports/security-hardening-evidence/03-BEFORE-demo-seeding-probe.txt`
(three of three production runs created a working administrator).

## 2. The gate

Demo accounts are created only when **all three** locks are open:

| # | Lock | Overridable? |
| --- | --- | --- |
| 1 | `APP_ENV` is **not** `production` | **No.** Not by config, not by CLI flag, not by env var. |
| 2 | `SEED_DEMO_ACCOUNTS=true` (default `false` in every environment) | Yes — that is the intended developer switch. |
| 3 | The caller uses `app.core.demo_seed.ensure_demo_accounts()` | The credentials exist nowhere else. |

Four independent defences enforce lock 1:

1. **`demo_seeding_allowed()`** returns `False` under production and logs a
   `CRITICAL` line. With `strict=True` it raises `DemoSeedRefused`.
2. **Boot-time config validation** — `Settings.validate_runtime()` refuses to
   start a production process at all when `SEED_DEMO_ACCOUNTS=true`. Asking for
   demo accounts in production is a startup failure, not a silent skip.
3. **Boot-time database guard** — `assert_no_demo_accounts_in_production()`
   runs in the FastAPI lifespan and refuses to serve if any demo email is
   already present in a production database. This catches restored staging
   dumps, deployments predating the fix, and manual inserts. Disable only with
   `REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION=false`, and only if you know why.
4. **`enable_for_this_process()`** (the `--seed-demo-accounts` CLI flag) raises
   under production rather than no-op'ing, so a deploy script cannot mistake a
   refusal for success.

## 3. Local development — the supported way to get demo data

Nothing about the developer experience changed except that you now have to ask.

```bash
# .env (development)
APP_ENV=development
SEED_DEMO_ACCOUNTS=true
```

then, as before:

```bash
cd backend
python scripts/load_realistic_products.py --realistic --if-empty
# or
python scripts/seed_products.py --if-empty
```

Or opt in for a single run without touching `.env`:

```bash
python scripts/load_realistic_products.py --realistic --if-empty --seed-demo-accounts
```

Either way you get the same three logins listed above, plus a `WARNING` in the
log naming them. The SPA still shows the credential hint on the login page, but
only in a **development build** — `import.meta.env.DEV` compiles the block out
of the production bundle entirely (verified in
`docs/agent-reports/security-hardening-evidence/11-AFTER-frontend-verification.txt`).

### Changing the demo password

`DEMO_ACCOUNT_PASSWORD` overrides the password for all three accounts. Useful
for a shared demo/staging box where the published passwords are still too
guessable — but note that a shared staging environment reachable from the
internet should be treated as production and use real accounts.

## 4. What to do if you find these accounts in a production database

The boot guard will already have stopped the process. Then:

1. **Assume the admin account was used.** `Admin123!` is public; treat this as
   a credential compromise, not a hygiene issue.
2. Delete or rename the three users.
3. Rotate `SECRET_KEY` (invalidates every issued JWT), `FERNET_KEY`, S3
   credentials, and the payment provider keys.
4. Review `audit_logs` for `login`, `role_change`, `product_verify` and
   `user_delete` rows attributed to those user ids.
5. Only then restart with `REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION=true` (the
   default) to confirm the database is clean.

## 5. Verification

| What | Command | Evidence |
| --- | --- | --- |
| Seeding probe (6 cases) | `cd backend && .venv/bin/python ../docs/security/probes/probe_demo_seeding.py` | `05-AFTER-demo-seeding-probe.txt` |
| Production fail-safe probe | `cd backend && .venv/bin/python ../docs/security/probes/probe_production_failsafe.py` | `07-AFTER-production-failsafe-probe.txt` |
| Regression tests | `cd backend && .venv/bin/python -m pytest tests/test_demo_seeding.py` | `08-AFTER-pytest-full-suite.txt` |

`tests/test_demo_seeding.py` also asserts that the passwords appear as string
literals in **no module other than `demo_seed.py`** — a second copy is how the
first version of this fix would quietly be undone.
