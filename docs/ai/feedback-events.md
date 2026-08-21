# Feedback Event Design — like / dislike / click / save

Owner: Master Prompt 04. **Status: design + partial implementation.** What
exists today is a bounded heuristic re-rank (see
[`recommender-config.md`](recommender-config.md) §4). **There is no trained
feedback recommender in this codebase and none is claimed.** This document
defines the event model that a future learning stage would need, so the data
can start being captured correctly now.

## 1. What exists today (implemented, tested)

| Piece | Where | Test |
|---|---|---|
| `product_feedback` table (`user_id`, `product_id`, `signal ±1`, `category`) with one-verdict-per-user-per-product upsert | `app/models/feedback.py` | `tests/test_feedback_v2.py` |
| 👍/👎 API | `app/api/routes/feedback.py` | idem |
| Bounded re-rank after explainable scoring (+0.12 / −0.35), feedback in the cache fingerprint | `app/services/recommender.py` | `tests/test_recommender_v2.py`, real-Redis invalidation test |

## 2. Designed, not yet built: the event stream

A thumb is a *decision*; an event stream records *behaviour*. Proposed
`feedback_events` (append-only, no upserts — history is the point):

| field | type | notes |
|---|---|---|
| `id` | uuid | |
| `user_id` | uuid, nullable | anonymous sessions get a session id instead |
| `session_id` | uuid | groups one browsing session |
| `quiz_id` | uuid, nullable | links the event to the recommendation context |
| `product_id` | uuid | |
| `category` | enum(taxonomy) | denormalised for fast cohort queries |
| `event_type` | enum(`impression`, `click`, `like`, `dislike`, `save`, `unlike`, `share`, `purchase_click`) | **impression is the denominator** — without it, CTR-style features are unfathomable |
| `position` | int | rank at display time (1–5) — needed for position-bias correction |
| `page_context` | enum(`recommend`, `moodboard`, `share`, `catalog`) | |
| `weights_version` | string | which recommender config produced the list |
| `created_at` | timestamptz | |

Design rules:

1. **Write path is fire-and-forget** — event logging must never fail a user
   request (background task; the existing audit-log pattern is the reference).
2. **Privacy**: events are behavioural data tied to a user id; GDPR export
   and erasure must cover them from day one (`user_delete` cascades; the
   Stage 03 pseudonymisation pattern applies if they are ever aggregated
   into analytics rows).
3. **No PII in events** — no free text, no image blobs, no quiz answers
   inline (reference the quiz by id).
4. **Impression logging is the hard part** (volume ~10–50× clicks); sample or
   batch if volume demands, but record the sampling rate in the row.

## 3. What learning would require later (explicitly out of scope now)

- ≳10k events with impressions before any learned weight is trustworthy;
- an offline evaluation split (e.g. leave-one-session-out) and a success
  metric defined **before** training;
- position-bias handling (events carry `position` for this reason);
- a revert path: learned weights must remain behind the same versioned-config
  interface (`recommender_config.json` → model-backed source) so the
  acceptance scenarios and fidelity tests keep running unchanged;
- A/B rollout with the `weights_version` stamp already present in every
  payload and cached result.

Until all five exist, the honest description of this system is: *deterministic
three-stage recommender with explainable scoring and a bounded, transparent
feedback adjustment*.
