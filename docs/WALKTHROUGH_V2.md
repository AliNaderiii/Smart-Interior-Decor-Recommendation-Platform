# Smart Decor v2.0 — 10-minute walkthrough

A demo script for the v2.0 release. Times are cumulative. Everything below was
verified against the running stack; where something is stubbed or blocked it
says so rather than glossing over it.

**Setup before you start**

```bash
# API  (port 8000)
cd backend && source /tmp/env_v2.sh && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Web  (port 5173)
cd frontend && npm run dev
```

Accounts: `demo@smartdecor.dev` / `Demo1234!` · `designer@smartdecor.dev` /
`Design123!` · `admin@smartdecor.dev` / `Admin123!`

---

## 0:00 — 0:45 · The pitch and the landing page

Open `/`.

> "Interior design tools make you choose between a catalogue that ignores your
> room and a human designer at $129 a project. Smart Decor infers your taste
> from images, respects your real dimensions, and explains every single
> recommendation."

Point at three things on the page:

- **Whitespace.** `py-24` sections, one idea per screen. Aesop's rule: products
  need room to float, not a dense grid.
- **No pure white.** The canvas is `#FAF8F5`; cards are white on top of it, so
  elevation reads without heavy shadows.
- **Type.** Inter Variable for Latin, Vazirmatn for Persian, self-hosted with
  `font-display: swap` — no layout shift, no Google Fonts round-trip.

Press **⌘K**. The palette opens. Press **?**. The shortcuts sheet lists every
key. Close with Esc.

> "The whole app is keyboard-drivable. That is a Linear idea and it is the
> difference between a tool you use and a tool you demo."

---

## 0:45 — 2:30 · The quiz

Sign in as `demo@smartdecor.dev`, go to `/quiz`.

**Step 1 — styles.** Full-bleed 5:4 image cards. Click *Modern* and
*Minimal*.

> "You cannot describe your own taste in adjectives. Houzz learned this: people
> discover their style by looking at rooms and reacting. So we ask with
> pictures."

Note the gradient scrim keeping the label legible over any photo, and the
checkmark that draws itself in rather than popping.

**Step 2 — palette.** 48px colour dots with ring states, plus a native colour
picker for anything custom.

**Step 3 — room and budget.** Enter your dimensions. Then the budget control:

> "This is not a bare slider. The bars behind it are the actual price
> distribution of the catalogue, so you can see that dragging to 8M Toman
> leaves you almost nothing. Baymard's research is blunt about this — a dual
> slider with no distribution and no numeric inputs is a usability failure. So
> there are both."

**Step 4 — materials.** Pick two, submit.

Confetti fires. It is reduced-motion guarded — with `prefers-reduced-motion`
set, it silently does not run.

---

## 2:30 — 4:30 · Recommendations, and the honest part

You land on `/recommendations`.

**Sticky category tabs.** Scroll; they stay. The active underline is a
`layoutId` shared element, so it slides between tabs instead of cutting.

**Grid / Masonry toggle.** Switch to masonry.

**Hover a product card.** The second image cross-fades in over 250ms — long
enough to read as a transition, not a flicker.

**The explainability card.** Hover "87% match — why?".

> "Every recommendation shows its own score breakdown: style, colour, budget,
> material, with the specific matched values. Not a black box, and not a
> tooltip either — it is a HoverCard, so you can move your pointer into it and
> read it.
>
> One thing worth saying out loud: this is also clickable. Hover-only would
> have meant the single most important feature on the page was invisible on a
> phone. Our click audit caught that."

**Feedback.** Press 👎 on something you dislike, 👍 on something you like.

> "This is Havenly's revision loop compressed into one keystroke. The signal
> persists to `POST /feedback`, and it re-ranks the next set — a thumbs-down
> costs a product 0.35 of its score, a thumbs-up adds 0.12. Refresh and the
> order has changed."

Update is optimistic with rollback on failure.

---

## 4:30 — 6:00 · Moodboard

Save a few products, go to `/moodboards`, create a board, open it.

**Toolbar.** Undo/redo, zoom, dot-grid toggle — dense, icon-first, 1px
separators. Linear, not Bootstrap.

**Drag a card.** It rotates 1.5° and lifts.

> "Physical cue. You are picking a photo up off a pinboard. It is done in CSS
> with `:has()` on the library's own dragging class, so it costs no JavaScript
> state."

**Undo.** Press ⌘Z a few times.

> "Fifty levels of layout history. Linear's principle: never ask 'are you
> sure', just make everything reversible."

**Present.** Click it. Fullscreen, arrow keys, slide indicators, Esc to leave.

> "This is the deliverable a designer actually shows a client. No editor chrome
> in the frame."

---

## 6:00 — 7:15 · Floorplan — the Modsy lesson

Go to `/floorplan`. Add two or three items from the board.

Point out: walls with real 12cm thickness, a door with an 80cm leaf and swing
arc, a 140cm window, and rulers on the top and left edges.

**Now drag two pieces close together.** A red dashed corridor appears with the
measured gap.

> "76cm is the standard main-circulation clearance. Modsy died in 2022, but the
> reason people loved it was dimensional truth — one reviewer rejected a design
> she loved because it 'didn't work measurement-wise'.
>
> Collision detection alone is not enough. Two sofas 30cm apart do not overlap,
> so a collision check passes them, and you physically cannot walk between
> them. This measures the gap between facing edges — and only for pieces that
> actually line up, so furniture in opposite corners is not flagged as noise."

**Export PNG.** A file downloads. html2canvas is dynamically imported, so its
48KB never touches the initial bundle.

---

## 7:15 — 8:00 · Shopping list

Go to `/shopping-list`.

80px thumbnails, retailer trust badge, quantity stepper, sticky total.

**Press + a few times.** The total updates via `useMemo` over `(rows, qty)`.
Quantities persist per board across reloads.

> "The badge pairs colour with text — 'Link verified', not just a green dot —
> so it survives greyscale and colour-blindness.
>
> There is also a fix here from the Phase 0 audit: this page used to hard-wire
> `boards[0]`. If you had three moodboards you could only ever see the first
> one, with no way to reach the others. There is now a selector."

---

## 8:00 — 9:00 · Designer and Admin

**Sign in as the designer.** `/designer/dashboard`.

An issue list, not a card grid: 1px separators, whole row is the hit target,
status pill, deterministic client avatar, filter tabs with live counts.

> "A designer with 40 clients needs to scan, not admire.
>
> Full disclosure on status: `projects` has no status column in v1.1. Rather
> than block a UI phase on a schema migration, Draft/Shared/Approved is derived
> from real facts — quiz count and whether a share link was generated — plus an
> explicit approve action stored client-side. That is a genuine limitation: it
> is per-browser. `projects.status` is logged as a v2.1 migration."

Open a project, press **Share with client**, then **Copy link** — toast
confirms, and the link works in a private window with no auth.

**Sign in as admin.** `/admin/products`.

- Tick two rows → the bulk bar appears → **Verify 2**. `Promise.allSettled`, so
  a partial failure reports the real count instead of hiding it.
- Hover a thumbnail → zoom panel, bottom right. Keyboard reachable too.
- **Edit** a product, change a colour → the **diff table** shows only the
  touched fields, AI value struck through, correction highlighted. Save is
  disabled until the JSON parses *and* something actually changed.

> "A reviewer approving a raw 14-line JSON blob is approving blindly. This makes
> 'save and verify' an informed action."

---

## 9:00 — 10:00 · The numbers

| Gate | Target | Actual |
|---|---|---|
| Initial JS | < 120 KB gzip | **119.89 KB** |
| Recommend p95 @ 20,700 rows | < 1 s | **721 ms** cold / **202 ms** warm |
| Backend tests | 81+ | **97 passing** |
| Dead keys | 0 | **0** (89 static, 53 clicked) |
| Raw `<img>` | 0 | **0** |
| Security headers | 6/6 | **6/6** |
| Brute force | 429 | **429 + Retry-After: 900** |
| HNSW recall @100 | 100/100 | **100/100** (ef_search 400) |
| WCAG AA contrast | all pairs | **26/26**, both themes |

Close on the trade-offs, because they are the interesting part:

> "Three things I would flag.
>
> **Framer Motion is not in the initial bundle.** Its core is ~35KB gzip the
> moment an eagerly-rendered component imports it. So the shell — page
> transitions, toasts, card lift — is plain CSS, and Framer only runs inside
> lazy route chunks where it earns its weight with shared-element transitions
> and drag.
>
> **Lighthouse is missing from this report.** Chromium cannot be downloaded in
> this sandbox — the CDN refuses the connection. I did not want to fabricate a
> score, so the Playwright e2e suite and Lighthouse run are committed and
> documented as blocked, and I substituted a jsdom click harness and a
> DOM-level a11y audit that actually execute.
>
> **`ecdsa` PYSEC-2026-1325 is unpatched.** It needs a PyJWT migration, which
> is a v2.1 item, not something to rush into a UI release."

---

## Appendix — verification commands

```bash
# Dead keys: static + executed
npx tsx scripts/auditDeadKeys.ts
cd frontend && npx tsx --tsconfig tsconfig.app.json scripts/clickAudit.mts

# Accessibility (contrast + DOM)
cd frontend && npx tsx --tsconfig tsconfig.app.json scripts/a11yAudit.mts

# Bundle budget
cd frontend && npm run build

# Backend suite
cd backend && source /tmp/env_v2.sh && .venv/bin/python -m pytest tests/ -p no:warnings

# Security headers
curl -sS -D - -o /dev/null http://localhost:8000/api/v1/health

# Playwright (needs a downloadable Chromium)
cd frontend && npx playwright install chromium && npx playwright test
```
