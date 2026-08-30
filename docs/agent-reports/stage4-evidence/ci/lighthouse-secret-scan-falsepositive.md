# CI defect — `Lighthouse report secret scan` false positive (found Stage 4, T-4.1)

**Status:** ROOT-CAUSED, fix proposed, **NOT applied** (needs the 1 CI paste — supervisor decision)
**First observed:** run `33307641975` (commit `6d91985`), job *Lighthouse CI*, step *Lighthouse report secret scan*
**Failing assertion (verbatim from the workflow):**

```
HITS=$(
  grep -rcE \
    "(BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35})" \
    /tmp/lighthouse-matrix/*.json \
    | awk -F: '{s+=$2} END {print s+0}'
)
echo "Credential-pattern hits: $HITS"
test "$HITS" -eq 0
```

Annotation: `failure: Process completed with exit code 1.`

## It is not a regression from Stage 4

* The diff at `6d91985` is **one line of Markdown** in `docs/ops/DEPLOY_STAGING.md`. It cannot affect a Lighthouse report.
* Lighthouse itself **passed** on that very run — annotation, verbatim:
  `home/mobile: perf=100 lcp=1279 tti=1286 ... recommendations/mobile: perf=98 lcp=2112 tti=2112 ...`
  All 12 cells are within the contract gates (perf>=80, LCP<3000, TTI<=4000).
* Steps 1–13 of the job all concluded `success`; only step 14 (the scan) failed.
* Searching the last 25 CI runs, this step has **never failed before** — consistent with a
  low-probability, content-dependent event rather than a code change.

## Root cause: the `sk-` pattern matches random base64url

The matrix step seeds real session cookies over CDP, so each Lighthouse report JSON embeds the
`access_token` / `refresh_token` / `csrf_token` JWTs many times (request headers, cookie jar,
network records, across 12 cells).

A JWT is **base64url**: `A-Za-z0-9-_`. The alternative `sk-[A-Za-z0-9]{20,}` therefore matches
any random run of `s`, `k`, `-`, then 20+ alphanumerics — a sequence that occurs naturally inside
long random base64url strings. It is looking for an OpenAI key and finding token entropy.

Measured false-positive rate (200 000 trials, 700 random base64url chars each — the size of one
embedded token trio):

```
random-base64url false-positive rate: 288/200000 = 0.14400% per 700 chars
  probability over   12 embeddings in a run: 1.71%
  probability over   60 embeddings in a run: 8.28%
  probability over  200 embeddings in a run: 25.04%
  probability over 1000 embeddings in a run: 76.33%
```

Reproduce: `docs/agent-reports/stage4-evidence/ci/falsepositive_probability.py`.

So the step is a latent flake whose rate scales with how many times the tokens appear in the
reports. It will keep firing on unrelated commits.

## Proposed fix — strengthens precision, does NOT weaken the gate

Two changes, both narrowing what counts as a *random* match while still catching a real key:

1. **Anchor the patterns on a non-token boundary.** A real leaked key is preceded by a quote,
   whitespace, `=` or `:` — never by another base64 character. `(^|[^A-Za-z0-9_-])` before each
   alternative removes essentially all base64url interior matches while every real key still matches.
2. **Redact the session tokens before the reports are written** in
   `frontend/scripts/lighthouse-auth-matrix.mjs`, so CI artifacts stop shipping live JWTs at all.
   This is the better control on its own merits: the artifact is downloadable for 90 days.

Detection strength after the fix is *higher*, not lower: a genuine `sk-...` / `ghp_...` / `AIza...`
/ PEM header in a report still fails the build, and the artifacts no longer contain credentials.

**Not applied.** `.github/workflows/*` cannot be pushed by this token, so change (1) needs the
stage's single CI paste. Change (2) touches `frontend/scripts/` and can ship without a paste, but
alone it only reduces the exposure — it does not remove the flake, because any base64url content in
a report can still trip the pattern.

Awaiting a supervisor ruling before spending the paste budget.
