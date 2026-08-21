# AI Privacy & Cost Assessment — Stage 04

Owner: Master Prompt 04 (AI Privacy and Cost Specialist role).
Date: 2026-08-21. Scope: the two places where platform data leaves the
trust boundary — **vision extraction** (admin product uploads) and
**embeddings** — plus the benchmark runs that exercise them.

---

## 1. Data flows (what actually leaves the perimeter)

| Flow | Payload | Destination | Trigger |
|---|---|---|---|
| A. Extraction (Gemini) | product image bytes (base64) + fixed English prompt listing the taxonomy | `generativelanguage.googleapis.com` (Google, US) | admin clicks "upload & extract" |
| B. Extraction (OpenAI) | **image URL only** (their fetchers download it) + prompt | `api.openai.com` | same |
| C. CLIP embeddings | product/quiz **text** (title, tags, description) — images only if a local multimodal query is used | **no external call** — model runs in-process | every product create/update, every quiz |
| D. Benchmark REAL mode | the 50 benchmark images | same as A/B | explicit `--real` |

Quiz answers are never sent to an external provider: they are embedded
locally (flow C) and scored locally.

## 2. Provider privacy & retention

| Aspect | Gemini (staging provider of record) | OpenAI (fallback) | local CLIP |
|---|---|---|---|
| Training on submitted data | **Free tier: YES** ("used to improve our products"); **Paid tier: NO** — per Google's pricing/data-terms documentation (ai.google.dev/gemini-api/docs/pricing, "Used to improve our products" row). **Mandatory control: paid tier only.** | API (non-consumer) terms state no training on submitted data by default — verify the current DPA at contract time | n/a — nothing leaves |
| Retention of prompts/outputs | Google states API input/output is retained only transiently (≤ ~30 days) for abuse monitoring, not tied to identity; prompt caching is opt-in | similar transient retention for abuse; verify current terms | none |
| Image persistence | not stored by Google beyond transient abuse-monitoring window | not stored (fetched transiently) | n/a |
| Regional considerations | Google APIs are subject to Iran-related sanctions/egress restrictions; for an Iranian-catalog product this is a **legal-compatibility question the product owner must answer** — a sanctioned-party interaction would make provider A/B unusable regardless of privacy preference, leaving local CLIP (flow C) as the only lawful path | same class of risk | none — flows C+D stay on-platform |

**Controls implemented in this stage:**

- The extraction prompt contains only the taxonomy vocabulary — no user data,
  no free-form user text is ever placed in a prompt.
- `description_for_embedding` (model-generated prose) is HTML-stripped before
  persistence (Stage 03, X-03) — treat model output as untrusted input.
- SSRF guard on the image fetch (`ai/feature_extractor._fetch_image_bytes`)
  so the extractor cannot be aimed at internal addresses (closes IR-SEC-003).
- No user-uploaded room photos are sent anywhere today: extraction runs on
  *admin catalog* images only. If homeowner room photos are ever extracted,
  this assessment must be redone (consent, purpose limitation, retention).

### Image retention on our side

Uploaded images live in S3-compatible storage (production policy) or local
storage (dev), plus the product row. Recommended retention for benchmark and
extraction inputs: keep the source image (it is the catalog asset), discard
nothing else — the extraction result itself is derived data stored on the
product. **The 50 benchmark fixture images are not in this repository** (URLs
are synthetic); a REAL benchmark run must use a licensed image set documented
in this file before it runs.

## 3. Authorization gate (who may send what, before anything runs)

1. **REAL benchmark**: requires (a) a provisioned API key in the environment,
   (b) an image set with documented license, (c) a recorded one-line
   authorization from the product owner (who, date, scope: "50 benchmark
   images to provider X for quality evaluation").
2. **Production extraction**: requires the paid tier (training-opt-out),
   documented egress approval, and the key stored via the deployment secret
   mechanism — never in the repository (enforced by `scripts/audit_secrets.py`).
3. Anything expanding payloads (e.g. homeowner photos) reopens this document.

## 4. Cost model (estimate — prices re-verified before budgeting)

Per-extraction cost, Gemini price-equivalent models at $0.10 / 1M input
tokens and $0.40 / 1M output tokens (gemini-2.0-flash retired 2026-06-01;
gemini-2.5-flash-lite carries the same rates — see IR-AI-004):

```
per image ≈ (258 image tokens + ~120 prompt tokens) × $0.10/1M
          + ~120 output tokens × $0.40/1M
          ≈ $0.00004  (≈ $0.04 per 1,000 extractions)
```

| Scenario | Extractions | Est. cost |
|---|---|---|
| 50-image benchmark (full) | 50 | **$0.002** |
| 1,000-product catalog ingest | 1,000 | **$0.04** |
| 10,000-product catalog ingest | 10,000 | **$0.40** |
| Steady state (100 admin uploads/mo) | 100 | **$0.004** |

Embeddings: **$0** (local CLIP). `/recommend`: **$0** per call (local vector
math); cost control is the existing 20 req/min/user rate limit.

Cost controls in place: per-admin upload rate limit (10/min, Stage 03),
benchmark `--sample N`, MOCK default in CI, and this assessment. Budget
owners should re-derive the table whenever Google changes list prices — the
assumptions live in `scripts/evaluate_extraction.py::COST_ASSUMPTIONS` and
are printed with every benchmark run.

## 5. Risk acceptance summary

| Risk | Disposition |
|---|---|
| Provider trains on catalog images | Mitigated **only** on the paid tier — free tier is prohibited for this workload |
| Sanctions/egress legality of US providers for an Iranian catalog | **Open product-owner decision**; local CLIP is the fallback that keeps the platform functional |
| Benchmark images lacking license | Blocked-by-default until documented (§3.1b) |
| Runaway extraction spend | Rate limits + estimates above; realistic worst case is cents |
| Provider model retirement (2.0-flash, 2026-06-01) | Loud failure (model-not-found), never silent; default update requested via IR-AI-004 |
