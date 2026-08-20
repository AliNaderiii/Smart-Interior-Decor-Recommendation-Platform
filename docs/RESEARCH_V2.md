# RESEARCH V2 — Competitive & Design Teardown (Phase 0A)

**Author:** Agent #2 (V2 Strict Mode)
**Date:** 2026-08-20
**Base:** MVP v1.1 (`v2-strict-mode` @ 61d13e9) — 45/45 tests green on real Postgres 16 + pgvector 0.6.2, p95 1.63 s @100 concurrent, 3 portals (client / designer / admin).
**Method:** Live web research + published UX teardowns (Baymard, Smashing, NN/g-style case studies), archived material for defunct services (Modsy, Made.com). Where a platform is dead, the archived/reported behaviour is used and marked as such.
**Rule of this document:** every platform gets **URL → 3 UX takeaways → 1 thing to steal NOW** with a concrete file-level implementation target in *our* repo. Nothing abstract. If it cannot be mapped to a file, it is not in this document.

---

## Scoring legend used throughout

| Tag | Meaning |
| --- | --- |
| `STEAL-NOW` | Implement in V2 Phase 2/3/4. Has an owner file. |
| `STEAL-LATER` | Good, but out of V2 scope. Logged in backlog table at the end. |
| `AVOID` | Observed anti-pattern. Explicitly do *not* copy. |

---

## TIER 1 — DIRECT COMPETITORS

### 1. Houzz — https://www.houzz.com

The 800-lb gorilla: photo discovery + pro marketplace + shop, glued together by **Ideabooks**.

**UX takeaways**
1. **Ideabooks are the spine of the product, not a side feature.** Users save any photo/product/pro/discussion into a named book, and *annotate each save with a note explaining why they saved it*. Designers then read the notes to decode client taste. A UX case study on Houzz found Ideabooks were buried in navigation and that surfacing them into the main nav measurably increased usage of saved content — discoverability of the save-surface is as important as the save itself.
2. **Style discovery is inductive, not declarative.** Houzz's own guidance ("8 Steps to Finding Your Design Style Using Ideabooks") tells users to save ~24 photos, *then* look at the category label under each photo (Farmhouse / Coastal / Transitional) and count which repeats. The user never fills a form saying "I am Scandinavian" — the system infers it from a pile of visual saves.
3. **Filters are design-domain-specific**, not generic e-commerce: style, room, size, budget, colour — and every saved photo carries its own metadata (paint colours, vendors, products used) so a photo becomes a shoppable object.
4. **"View in My Room"** (AR/camera) is the emotional hook — the UX case study found users scanned for the words *camera* and *furniture* and clicked without reading body copy. Verbs beat prose.

**AVOID:** Houzz's nav is overloaded (Photos / Find Pros / Shop / Stories / Discussions all competing). Our three portals must stay single-purpose.

**STEAL NOW — Inferred style from visual saves + "why" note.**
Our quiz currently asks the user to *declare* a style (`frontend/src/pages/QuizPage.tsx`, 265 lines of stepper form). Replace step 1 with a 6–8 card **visual** style picker where each card is an image, and store per-selection provenance. Then, on the moodboard (`MoodboardEditorPage.tsx`), allow a per-item note. Concretely:
- `QuizPage.tsx` → style step becomes image cards, selection state records `{style, source: "visual_card"}`.
- Moodboard item gets an optional `note` field (already have a JSON items column in `backend/app/models/moodboard.py` — no migration needed if we extend the item payload).

---

### 2. Havenly — https://havenly.com

Human-designer-led e-design. Mini package (~$79) = ideas/colours/shopping list, Full (~$129–199) = layout + visualisations. Reported flow: choose designer → share inspiration → **concept board** → *client feedback round* → revisions → final design + shopping list.

**UX takeaways**
1. **Feedback is a formal, required stage of the pipeline, not a comment box.** Good Housekeeping's walkthrough is explicit: after the concept is delivered, "your honest feedback is key here — express what you like or dislike about the suggested design schemes," and the designer uses that input to finalise. The product *forces* a like/dislike round-trip before final delivery.
2. **Client picks the designer.** Users cite designer choice as the #1 pro. Agency matters — being assigned a stranger (Modsy's model) scored worse in head-to-head reviews.
3. **Tiering by deliverable, not by discount.** Mini vs Full differ by *artifact* (no layout vs layout + visualisation), which is honest and easy to explain on a paywall.

**AVOID:** the designer-side economics (endless free revisions, $20 penalty for slow replies) produced a bad reputation among designers on side-hustle review sites. Our designer portal should cap revision rounds explicitly in the UI so scope is visible to both sides.

**STEAL NOW — 👍/👎 per product that actually re-ranks.**
`frontend/src/components/ProductCard.tsx` gets a two-button feedback affordance; backend gets `POST /feedback` persisting `{user_id, product_id, signal}` and the recommender (`backend/app/services/recommender.py`) applies a per-user boost/penalty term at re-rank time. This is *also* a Phase 4 dead-key fix: a thumbs button that only sets local state is a dead key.
And: **soft paywall**, not a wall — show concept 1 fully, concept 2 at reduced opacity behind an "Unlock" card (`UpgradePage.tsx` / recommendations paywall).

---

### 3. Modsy — https://www.modsy.com *(defunct — shut down 6 July 2022; studied via archived coverage + contemporaneous reviews)*

Photo/video scan of your real room → dimensionally accurate 3D twin → designer produces concepts → free 3D Room Editor for the client.

**UX takeaways**
1. **Two layouts first, then two styled designs.** Reviewers consistently describe the sequence: designer sends **two 2D layout options** with a recommendation of which is better; client picks one; only then do two full 3D design plans arrive *in the same layout but different styles*. Decoupling **spatial** decisions from **stylistic** ones is the single best structural idea in this whole document.
2. **Dimensional truth was the moat.** The render used *your* wall dimensions, window placement and floor plan, so "does this sofa fit between these two windows" was answerable. A review that praised the designs still rejected one because "the Modsy design didn't work measurement-wise" — proving users check real numbers.
3. **Give the client the designer's own tool.** Clients got the same 3D editor the designer used, to copy the room and swap pieces themselves. Enormous trust/engagement win.
4. **The scan flow was the weak point** — one reviewer redid the room walk-through three times before it was accepted. Capture friction kills funnels.

**AVOID:** charging $25/item to include the client's existing furniture. Punishing users for reality is hostile.

**STEAL NOW — Walkway clearance, not just collision.**
`frontend/src/pages/FloorplanPage.tsx` currently reasons about overlap only. Add a clearance rule: main circulation paths need **≥ 76 cm (30 in)**; render a red dashed corridor where clearance fails, plus a ruler along the top and left edge with real cm labels. This is the "measurement-wise" check that made a reviewer reject an otherwise-loved design.

---

### 4. Decorilla — https://www.decorilla.com

Packaged e-design with named tiers and a multi-concept model.

**UX takeaways**
1. **Two concepts from two different designers, client picks one, then goes deep with the winner.** The competitive dynamic yields variety without the client having to articulate taste in words.
2. **Tier names carry the value story** (Bronze / Silver / Gold-style laddering) — each tier is a bundle of concrete artifacts and revision counts, shown as a comparison table before payment.
3. **The shopping list is the monetised deliverable** — trade discounts on the final list are the retention hook, so the list is treated as a first-class page, not an export.

**STEAL NOW — Ship *two* moodboard variations per quiz submission, not one.**
`backend/app/services/recommender.py` already produces a ranked candidate pool; emit variant A ("closest match" — top-ranked) and variant B ("designer's stretch" — same hard filters, but diversified by picking lower-ranked items maximising category/colour spread). `MoodboardsPage.tsx` shows both side by side with a single "Choose this direction" CTA.

---

### 5. Wayfair — https://www.wayfair.com

Best-in-class faceted filtering at enormous catalogue scale.

**UX takeaways**
1. **Colour as swatch chips, never as a text list.** Baymard's e-commerce filter guidance is unambiguous: visual colour chips beat text labels for home goods, and swatches need a tooltip/label for a11y. Text filters force the user to translate "Ecru" into a mental image.
2. **Price is a dual-handle slider + typed min/max, ideally over a histogram.** Smashing's slider research shows that with real (non-uniform) price distributions, a plain linear slider wastes most of its track on empty ranges; overlaying a **histogram of product counts** — or using a log scale — makes the control informative rather than a guess. Always pair with text inputs for exact values.
3. **Result counts next to each option** ("Blue (34)") is called out by Baymard as one of the single highest-impact filter improvements: it prevents zero-result dead ends before the click.
4. **Desktop = persistent left sidebar + live filtering; mobile = bottom-sheet drawer with a sticky "Show N results" apply button.** Real-time updates are preferred on desktop, batched on mobile.

**STEAL NOW — Colour dots + price histogram + live result counts** in the recommendations filter rail (`RecommendationsPage.tsx`). Counts come free: the backend already returns the candidate pool, so facet counts are a client-side `useMemo` reduction. Persian price formatting via `Intl.NumberFormat('fa-IR')`.

---

## TIER 2 — DESIGN & INTERACTION INSPIRATION

### 6. Linear — https://linear.app

The reference for keyboard-first, high-density, near-monochrome product UI.

**UX takeaways**
1. **Everything has a keystroke.** `Cmd/Ctrl+K` command palette, `C` create, `/` search, `P` priority, `L` label, `?` for the shortcut sheet, vim-style `g`+letter navigation. The palette is a *command surface* (create, assign, change status), not just a search box.
2. **Speed is the aesthetic.** ~100 ms interaction target, ~200 ms ease-out transitions, optimistic updates instead of spinners, inline feedback next to the action, undo instead of confirm dialogs.
3. **Restraint as a system:** 4 px spacing unit, Inter/Inter Display, hierarchy from weight and size alone, colour reserved for status only, 1 px separators instead of gaps and shadows, elevation reserved strictly for floating overlays (modal/dropdown/popover).

**STEAL NOW — `Cmd+K` command palette with a real command registry.**
New `frontend/src/components/CommandPalette.tsx` keyed by stable command ids (survive label renames), categories (Navigate / Create / Admin), fuzzy scoring, arrow-key virtual highlight while DOM focus stays in the input (combobox pattern), `Esc` to close, and a visible search button in the header for touch users. Register commands per portal: designer → "New project", "Share project"; admin → "Verify selected", "Sort by confidence"; client → "Jump to style", "Jump to budget".
Also adopt **undo-over-confirm** for moodboard item deletion.

---

### 7. Stripe Dashboard — https://dashboard.stripe.com (patterns: https://docs.stripe.com/stripe-apps/patterns)

**UX takeaways**
1. **Empty states teach instead of apologising.** A fresh Stripe account shows zeroed metrics, flat sparklines, and one prominent instruction — "Make your first test payment" — and for developer surfaces the empty state literally embeds the API snippet. The empty state is treated as onboarding real estate, with the same design care as the populated state.
2. **Hierarchy comes from typography and whitespace, colour is reserved for status.** This is what keeps high-stress financial data legible; decoration is stripped out.
3. **Microcopy does the trust work:** every status message answers *what happened* and *what to do next*; navigation is labelled by user job (Payments, Payouts, Disputes), not by system architecture.
4. Stripe's own app-design docs enumerate the mandatory state set: communicating state, empty state, loading, progress stepping, waiting screens.

**STEAL NOW — a mandated three-state contract for every data surface.**
Every list/table/grid in the app must ship `loading` (layout-matched shimmer, never a grey box or spinner), `empty` (illustration + one sentence + exactly one primary CTA, with *different copy* for first-run vs no-results-after-filter), and `error` (inline retry + support link + error id). Enforced in Phase 5 and asserted in the Playwright suite. Job-based nav labels for the designer/admin portals.

---

### 8. West Elm — https://www.westelm.com

**UX takeaways**
1. **Shoppable inspirational imagery.** Baymard's 2025 navigation study singles out West Elm: room scenes carry product tags, with a persistent tag icon in the lower-left showing the count (e.g. 8 products in this image); on mobile, tapping the image reveals the tags. 70 % of sites fail to link products shown in inspirational imagery — West Elm doesn't.
2. **Editorial room scenes carry the style story**, then hand off to a conventional PDP for the transaction. Inspiration and commerce are separate modes, deliberately bridged.
3. **Consistent 4:3-ish scene crops** keep the grid rhythm intact even with mixed product photography.

**STEAL NOW — tag count badge on moodboard/room imagery.** A moodboard rendered for a client should show a small "N products" badge and reveal per-item hotspots on hover/tap, each linking to the shopping-list row. Directly reuses the moodboard items payload; no backend change.

---

### 9. Article — https://www.article.com

**UX takeaways**
1. **Hover swaps to a second image** (usually the in-room/lifestyle shot) — 200–300 ms crossfade; instant swaps read as jarring. This is the highest-value hover interaction on a furniture card.
2. **Swatches on the card, not just the PDP.** Hovering a swatch updates the card image in place; clicking navigates to the correct variant PDP directly. The anti-pattern is a full page load per swatch — colour choice must feel instant.
3. **Price is stated plainly with the delivery promise adjacent** — for furniture, "when does it arrive" is a purchase-blocking question and belongs near the price.

**STEAL NOW — `ProductCard` v2:** fixed 4:3 aspect box (kills CLS), second image crossfade on hover at 220 ms, colour swatch row that changes the card image *in place* with the swatch name revealed at a single fixed spot on hover (Chantelle pattern — no per-swatch labels cluttering the card), price via `Intl.NumberFormat('fa-IR')`, retailer trust badge.

---

### 10. Made.com — https://www.made.com *(brand collapsed/administration 2022, relaunched as a marketplace brand; studied as a cautionary case)*

**UX takeaways**
1. **Editorial-first grid with generous whitespace** made mid-price furniture read as design-led — proof that perceived quality is mostly layout and photography, not product cost.
2. **Long lead times were the fatal UX/ops mismatch.** The site promised design; fulfilment could not honour it. The lesson for us: **never render an availability or delivery claim we cannot verify.** Our catalogue is scraped/AI-extracted, so unverified fields must be visibly marked, not silently shown.
3. **Community/social proof modules** (customer room photos next to the product) lifted confidence — cheap to imitate, high trust yield.

**STEAL NOW — a verification-honest badge system.** `is_verified` already exists on the product model. Surface it: verified → quiet "قیمت تأییدشده" badge; unverified → muted "قیمت تخمینی" with a hover explanation. Never present an AI-extracted price as fact. Ties directly into the admin confidence workflow.

---

### 11. Pinterest — https://www.pinterest.com

**UX takeaways**
1. **Masonry is the identity.** Each card keeps its natural height and joins the shortest column, so there is no dead air under short cards. Implementation reality: CSS `columns` orders *down* each column (breaks reading order) and native `grid-template-rows: masonry` is only just shipping, so a JS/`react-masonry-css`-style shortest-column placement is required for left-to-right order.
2. **Reserve aspect ratios before images load** or the whole board jumps — the classic masonry CLS trap. Combine with `IntersectionObserver` sentinel infinite scroll and virtualization (`react-window`/TanStack Virtual) for long feeds.
3. **Onboarding is a mandatory visual pick of ≥5 topics**, which both seeds the algorithm and defeats the empty-state problem on day one. Same trick our quiz should use.
4. **Save → board is one tap from anywhere**, with board choice deferred; the save never blocks on organisation.

**STEAL NOW — Grid/Masonry toggle on recommendations + moodboard,** with shortest-column placement, pre-reserved aspect boxes, and virtualization past ~60 items. And: "Add to Moodboard" must never block on the user having a board — offer create-new inline in the same modal (this is a known v1 dead-key suspect).

---

### 12. Aesop — https://www.aesop.com

**UX takeaways**
1. **Two colours plus neutrals, and the whitespace does the work.** The palette (cream/olive/brown) matches the physical packaging; products float in generous padding, which is what reads as "premium".
2. **Editorial collage instead of a product grid** on entry surfaces — the homepage behaves like a magazine spread, and the menu is replaced by small collages that let users pick a next step.
3. **Body copy set large enough to actually read** in a serif, with reviews/specs/badges hidden behind interactions rather than shown all at once — minimalism achieved by *deferral*, not deletion.

**STEAL NOW — the warm-neutral canvas and typographic scale for V2:** background `#FAF8F5` (never pure white), cards `#FFFFFF` with `shadow-[0_8px_30px_rgb(0,0,0,0.04)]`, a single near-black accent `#0F172A`, section padding `py-24`, `text-balance` on headings, tracking `-0.02em`, body 15 px / 1.6, Vazirmatn for Persian numerals. Secondary metadata (match breakdown, dimensions, retailer detail) hidden behind a Radix HoverCard rather than printed on the card.

---

## SYNTHESIS — the V2 product thesis

> **"Infer taste visually (Houzz), decide space before style (Modsy), always offer two directions (Decorilla), let feedback re-rank (Havenly), filter like Wayfair, and render it with Aesop's whitespace at Linear's speed."**

### Ranked implementation table (what actually lands in V2)

| # | Steal | Source | Owner file(s) | Phase |
| --- | --- | --- | --- | --- |
| 1 | Visual style cards replace dropdown quiz | Houzz, Pinterest | `pages/QuizPage.tsx` | 3 |
| 2 | 👍/👎 feedback that re-ranks | Havenly | `components/ProductCard.tsx`, `services/recommender.py`, `POST /feedback` | 3–4 |
| 3 | Walkway clearance ≥76 cm + rulers | Modsy | `pages/FloorplanPage.tsx` | 3 |
| 4 | Two moodboard variants per quiz | Decorilla | `services/recommender.py`, `pages/MoodboardsPage.tsx` | 3 |
| 5 | Colour dots + price histogram + facet counts | Wayfair | `pages/RecommendationsPage.tsx` | 3 |
| 6 | `Cmd+K` command palette + undo-over-confirm | Linear | `components/CommandPalette.tsx` (new) | 3 |
| 7 | Three-state contract (shimmer/empty/error) everywhere | Stripe | all pages, `components/ui.tsx` | 5 |
| 8 | 4:3 card, hover second image, in-place swatches | Article, West Elm | `components/ProductCard.tsx` | 3 |
| 9 | Grid/Masonry toggle + reserved aspect + virtualization | Pinterest | `pages/RecommendationsPage.tsx`, `components/BoardGrid.tsx` | 2–3 |
| 10 | Warm-neutral canvas, typographic scale, deferred detail | Aesop | `index.css`, `docs/DESIGN_SYSTEM_V2.md` | 3 |
| 11 | Verification-honest price badges | Made.com | `components/ProductCard.tsx`, admin flow | 3 |
| 12 | Soft paywall (opacity + unlock card, not blur wall) | Havenly | `pages/UpgradePage.tsx`, recommendations | 3 |

### Explicit anti-patterns (do NOT copy)

| Anti-pattern | Source | Our rule |
| --- | --- | --- |
| Overloaded multi-product nav | Houzz | Each portal has one job; nav labelled by job (Stripe). |
| Charging to include the user's own furniture | Modsy | Existing-item support is free. |
| High-friction capture flow (3 retries) | Modsy | Room input must succeed first try or degrade gracefully to manual dimensions. |
| Unbounded revision loops | Havenly | Revision rounds are explicit and visible in the designer portal. |
| Promising delivery we can't verify | Made.com | Unverified data is badged, never presented as fact. |
| Linear price slider on skewed data | Wayfair/Smashing | Histogram or log scale, plus typed min/max. |
| CSS `columns` for masonry | Pinterest | Breaks reading order — use shortest-column placement. |
| Spinners as the loading state | Linear/Stripe | Layout-matched shimmer + optimistic updates. |

### Backlog (`STEAL-LATER`, out of V2 scope)

- AR "View in Your Space" (Houzz) — needs native/WebXR.
- Client-facing 3D room editor (Modsy) — needs a 3D pipeline.
- Designer marketplace + choose-your-designer (Havenly/Decorilla) — needs two-sided ops.
- Visual search / Lens (Pinterest) — needs an image-embedding search index (we have pgvector; candidate for v2.1).
- Customer room photo UGC module (Made.com) — needs moderation.

---

## Sources consulted

- Houzz: houzz.com; Houzz Magazine "8 Steps to Finding Your Design Style Using Ideabooks"; Prototypr "Houzz: a UX case study"; Houzz Ideabooks tutorials.
- Havenly: havenly.com; Good Housekeeping Havenly review; Mashable "Havenly vs. Modsy"; SideHusl designer-side review.
- Modsy: modsy.com (archived); Fortune/industry coverage of the 6 July 2022 shutdown; Organized-ish Modsy review and Modsy-vs-Havenly comparison; Havenly's "Modsy shutdown" post; 2026 alternative round-ups.
- Decorilla: decorilla.com package/tier structure and multi-concept model.
- Wayfair: wayfair.com; Baymard "What Is an Ecommerce Filter? UI Best Practices"; Smashing Magazine "Designing The Perfect Slider UX"; UXPin filter UI guide.
- Linear: linear.app; Hack Design "Linear for Designers"; Linear design-pattern digests; cmdk / command-palette engineering write-ups.
- Stripe: dashboard.stripe.com; docs.stripe.com/stripe-apps/patterns; 925studios "Stripe Dashboard Design Breakdown".
- West Elm: westelm.com; Baymard homepage & category navigation benchmark 2025.
- Article: article.com; product-card and swatch interaction teardowns (Commerce-UI, CommandC).
- Made.com: made.com; 2022 administration coverage.
- Pinterest: pinterest.com; NameThatUI masonry reference; Pinterest frontend system-design write-ups; CreateBytes Pinterest UI/UX review.
- Aesop: aesop.com; minimalist-design round-ups (Linke.ro, Blacksmith, Social Animal, DesignRush).
