# 10-Minute Client Walkthrough Script

Prep: `docker-compose up --build` (or dev mode per README). Seeded accounts:

| Role | Email | Password |
|---|---|---|
| Homeowner | demo@smartdecor.dev | Demo1234! |
| Designer | designer@smartdecor.dev | Design123! |
| Admin | admin@smartdecor.dev | Admin123! |

## Minute 0-1 — Landing & value prop
1. Open `/`. Note the warm Havenly-style design, six style cards, hero CTA.

## Minute 1-3 — Homeowner: style quiz
2. Sign in as **demo@smartdecor.dev**.
3. `/quiz` — walk the 5 steps:
   - **Style**: click *Scandinavian* + *Minimal* (image cards, multi-select ≤3)
   - **Colors**: pick cream, oak, white swatches (+ show the custom color picker)
   - **Dimensions**: 420 × 560 cm (live m² calculation)
   - **Budget**: drag sliders → Persian price format `تومان`
   - **Materials**: wood + fabric
4. Click **Get my recommendations ✨**.

## Minute 3-5 — Explainable recommendations + paywall
5. On `/recommendations`: point out per-category ranked grids (Sofa, Coffee
   Table, Rug, Lighting…) and the **explainability chips** on the #1 card:
   *"92% Style • 85% Color • 90% Budget • Material: wood"*.
6. Scroll: ranks 2-5 are **blurred with "Unlock with Pro"** — enforcement is
   server-side (teaser payload has no price/score fields — show Network tab).
7. Click **Upgrade to Pro** → `/upgrade` → **Pay with Zarinpal** → sandbox
   redirect returns → "Payment confirmed — welcome to Pro!" → recommendations
   now show all ranked items. Note: no card fields anywhere — pure redirect.

## Minute 5-7 — Moodboard, floorplan, shopping list
8. Back on recommendations, click **Add to moodboard** on 4-5 products →
   **Create moodboard**.
9. `/moodboard/:id` — **drag and resize** cards (react-grid-layout), click
   **Save layout**, then **Add all to shopping list**.
10. `/floorplan` — set room 420 × 560; add sofa + coffee table from the
    moodboard; drag them around the SVG room (1px = 1cm scale); shrink the room
    to 200 × 200 to trigger the "does not fit" warning.
11. `/shopping-list` — table with Persian totals, green **link-verified dots**,
    **Copy** buttons, "Open store" links to Digikala/Torob.

## Minute 7-8.5 — Designer portal (B2B2C)
12. Log out, sign in as **designer@smartdecor.dev**.
13. `/designer/dashboard` → **+ New project** ("Villa Lavasan", client
    "Mr. Ahmadi").
14. Open the project → **Run quiz for this client** (note the client-name
    field) → results → back in project click **Share with client** → copy the
    `/share/<token>` link.
15. Open the share link in a **private window**: full read-only
    recommendations, zero auth. (Optionally show the email field → mock email
    logged by backend.)

## Minute 8.5-10 — Admin portal
16. Sign in as **admin@smartdecor.dev**.
17. `/admin/products` → filter **pending** → click **+ Upload product image**
    (any furniture photo) → AI extraction runs → new draft appears with
    color/style/material chips and a **confidence %**.
18. Click **Edit** → show the human-in-the-loop JSON editor → fix price →
    **Save** → **Verify**. The product is now eligible for recommendations.
19. `/admin/users` — disable/enable a user; `/admin/subscriptions` — see the
    demo user's Pro plan from step 7.

## Closing points (30 s)
- 43 automated tests green, incl. **30/30 recommender** + p95 latency test.
- 50-image extraction benchmark ≥ 80 %.
- One-command deploy, TLS 1.3, bcrypt, GDPR delete, no card storage.
- Phase-2 ready: provider-agnostic AI, KMS abstraction, RTL path documented.
