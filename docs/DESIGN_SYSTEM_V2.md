# DESIGN SYSTEM V2 — Smart Interior Decor

**Status:** Phase 3 contract. Every rule here is enforced in code (`src/index.css` `@theme` tokens + `src/components/ui.tsx` primitives). If a screen disagrees with this document, the screen is wrong.

**Design thesis** (from `docs/RESEARCH_V2.md` §Synthesis):

> Infer taste visually (Houzz), decide space before style (Modsy), always offer two directions (Decorilla), let feedback re-rank (Havenly), filter like Wayfair, render with **Aesop's whitespace at Linear's speed**.

Those last five words are the whole visual brief. Aesop supplies the canvas — warm off-white, extreme padding, editorial restraint. Linear supplies the *behaviour* — ~100 ms response, keyboard-first, colour reserved for status, elevation only for things that actually float.

---

## 1. Colour

### 1.1 Core palette

| Token | Hex | Role |
| --- | --- | --- |
| `--color-canvas` | `#FAF8F5` | Page background. **Never pure white** — Aesop's cream keeps large surfaces from glaring. |
| `--color-surface` | `#FFFFFF` | Cards, popovers, sheets. Reads as "raised" purely by contrast with the canvas. |
| `--color-ink` | `#111827` | Primary text and the single accent. |
| `--color-muted` | `#6B7280` | Secondary text, metadata. |
| `--color-faint` | `#9CA3AF` | Tertiary — placeholders, disabled labels, timestamps. |
| `--color-line` | `#F3F4F6` | 1px separators. Linear's rule: separate with a line, not a gap-plus-shadow. |
| `--color-accent` | `#0F172A` | The **only** accent. Near-black, so emphasis costs no chroma. |

**One accent, deliberately.** A decor product is a photograph gallery — every product image is already saturated. A branded accent hue would compete with the merchandise. Near-black buttons let the sofas carry the colour.

### 1.2 Status colours — the *only* legitimate use of hue

| Token | Hex | Meaning |
| --- | --- | --- |
| `--color-ok` | `#047857` | Verified price, approved project, success. |
| `--color-warn` | `#B45309` | Estimated price, low AI confidence, needs review. |
| `--color-danger` | `#B91C1C` | Destructive action, clearance violation, error. |

Stripe's discipline: hierarchy comes from typography and whitespace; colour means *state*. If something is coloured, a user must be able to ask "what state is that?" and get an answer.

### 1.3 Legacy warm palette (retained)

`clay #C1633F`, `walnut #5D4037`, `sage #4C6444`, `sand #F2EDE6`, `stone #8A8178` remain as tokens. V1 shipped with these and ripping them out mid-flight would churn every file for no user-visible gain. **New surfaces use the V2 tokens**; `clay` survives as the brand tint on marketing/quiz progress only.

### 1.4 Dark mode

Class-based (`.dark` on `<html>`), not `prefers-color-scheme` alone — the toggle must be able to override the OS.

| Light | Dark | Note |
| --- | --- | --- |
| canvas `#FAF8F5` | `#0F172A` (slate-900) | |
| surface `#FFFFFF` | `#1E293B` (slate-800) | Elevation via *lighter* surface, since shadows are invisible on dark. |
| ink `#111827` | `#F1F5F9` (slate-100) | |
| muted `#6B7280` | `#94A3B8` (slate-400) | |
| line `#F3F4F6` | `#334155` (slate-700) | |

**Never invert product photography.** Images keep their own light; only chrome flips.

---

## 2. Typography

**Inter Variable** (latin + latin-ext) for Latin; **Vazirmatn** (arabic) for Persian. Subset and self-hosted — Phase 2 cut this to 4 woff2 files. Persian numerals via `Intl.NumberFormat('fa-IR')`.

| Role | Size / line-height | Weight | Tracking |
| --- | --- | --- | --- |
| Display | 48px / 1.1 | 650 | −0.03em |
| H1 | 32px / 1.2 | 650 | −0.02em |
| H2 | 24px / 1.3 | 650 | −0.02em |
| H3 | 18px / 1.4 | 600 | −0.01em |
| Body | 15px / 1.6 | 400 | 0 |
| Small | 13px / 1.5 | 500 | 0 |
| Micro | 11px / 1.4 | 600 | +0.04em, uppercase |

**Weight 650, not 700.** Inter's variable axis makes 650 available, and it is the difference between "designed" and "bold by default". Headings get `text-balance` so a two-line title breaks evenly instead of orphaning one word.

Negative tracking on large text only. Below ~18px it closes counters and hurts legibility — and it must never be applied to Vazirmatn, where Persian letterforms connect and negative tracking corrupts the joins. Enforced by scoping tracking utilities to the Latin heading classes.

---

## 3. Space, radius, elevation

**8px grid.** Every margin, padding and gap is a multiple of 8 (4px permitted for optical nudges inside dense controls). Section rhythm is `py-24` (96px) on desktop, `py-12` mobile — Aesop's "let it breathe".

| Radius | Use |
| --- | --- |
| 8px | Inputs, small chips |
| 12px | Buttons |
| **16px** | **Cards — the signature radius** |
| 24px | Sheets, modals, hero imagery |
| full | Avatars, colour dots, pills |

Shadows are soft, wide and nearly transparent — a lift, not a drop:

```
--shadow-card:  0 1px 3px rgb(17 24 39 / 0.04), 0 8px 30px rgb(17 24 39 / 0.04);
--shadow-hover: 0 2px 6px rgb(17 24 39 / 0.06), 0 12px 40px rgb(17 24 39 / 0.08);
--shadow-float: 0 8px 40px rgb(17 24 39 / 0.12);   /* overlays ONLY */
```

Linear's rule, adopted: **elevation is reserved for things that genuinely float** (modal, popover, palette, dropdown). A card in a grid is not floating; it gets `--shadow-card` at most, and static data panels get a 1px `--color-line` border instead.

---

## 4. Motion

The brief specifies **spring, damping 20, stiffness 300**. That is the house physics for anything that moves *position or scale*:

```ts
export const spring = { type: "spring", damping: 20, stiffness: 300 } as const;
```

It settles in ~250 ms with no perceptible overshoot — responsive, not bouncy. Decorative bounce (low damping) is banned: this app arranges furniture, and wobbling furniture reads as broken.

| Interaction | Spec |
| --- | --- |
| Card hover | `y: -2`, shadow → `--shadow-hover`, spring |
| Button/card tap | `scale: 0.98`, spring |
| Page transition | opacity 0→1 + `y: 20 → 0`, spring |
| Colour/opacity only | 200 ms `ease-out` (a tween — springs are for space, not for hue) |
| Product 2nd image | 220 ms crossfade (Article's timing; instant reads as a glitch) |
| Skeleton shimmer | 1.6 s linear, infinite |

**`prefers-reduced-motion` is a hard requirement, not a nicety.** A `useReducedMotion()` gate collapses every spring to a 0.01 s tween and disables shimmer/confetti. Vestibular-triggering motion is an accessibility defect.

---

## 5. Component contracts

### 5.1 The three-state rule (Stripe)

Every data surface ships **all three**, no exceptions — asserted in the Phase 4 Playwright suite:

1. **Loading** — layout-matched shimmer. A centred spinner is a defect: it guarantees a layout jump when data lands.
2. **Empty** — teaches, never apologises. Illustration + one sentence + exactly one primary CTA. First-run and no-results-after-filter get **different copy** ("Take the quiz" vs "Widen your budget").
3. **Error** — inline (never a full-page takeover), with a retry button and a copyable error id.

### 5.2 Buttons

Variants: `primary` (accent fill), `secondary` (line border), `ghost` (hover tint), `danger`. Min hit target **44×44px**. Focus ring is `2px --color-accent` at `2px` offset — always visible, never `outline: none`.

**No decorative buttons.** A control that is not wired is either implemented or rendered `disabled` with a tooltip explaining why. Enforced by `scripts/auditDeadKeys.ts`.

### 5.3 Cards

16px radius, `--shadow-card`, `overflow-hidden`, 4:3 media box with reserved aspect ratio (CLS). Hover: `y:-2` + shadow. Secondary metadata (match breakdown, dimensions) lives in a **HoverCard**, not printed on the face — Aesop's "hide detail behind interaction".

### 5.4 Keyboard

`Cmd/Ctrl+K` palette everywhere; `Esc` closes any overlay; `/` focuses search; Tab order follows DOM order; arrow keys drive the palette with a virtual highlight while DOM focus stays in the input (combobox pattern).

---

## 6. Accessibility floor (AA)

- Contrast ≥ 4.5:1 body, ≥ 3:1 large text and UI boundaries. `muted #6B7280` on `canvas #FAF8F5` = **5.1:1** ✓. `faint #9CA3AF` is therefore restricted to ≥18px or non-essential text.
- Every image has a real `alt`; decorative images get `alt=""`.
- Every icon-only control has an `aria-label`.
- Colour is never the sole carrier of meaning — the confidence system pairs hue with a text label, so it survives both colour blindness and greyscale printing.
- All interactive elements reachable and operable by keyboard, with a visible focus ring.

---

## 7. Anti-patterns (explicitly rejected)

| Rejected | Why |
| --- | --- |
| Pure `#FFFFFF` page background | Glares at full-viewport scale; Aesop's cream is the whole mood. |
| Multiple brand accent hues | Competes with product photography. |
| Bouncy springs (damping < 15) | Wobbling furniture reads as broken. |
| Centred spinners | Guarantee a layout jump; shimmer preserves geometry. |
| Confirm dialogs for reversible actions | Linear's undo-over-confirm — a toast with Undo beats a modal. |
| Shadows on static data panels | Elevation must mean "floating". |
| Negative tracking on Persian | Corrupts Vazirmatn's letterform joins. |
| Colour as the only status signal | Fails colour-blind users and greyscale. |
| Tooltips for rich content | Not focusable/hoverable-into; rich detail needs a HoverCard. |

---

## 8. Token reference (implemented in `src/index.css`)

```css
@theme {
  --color-canvas:  #FAF8F5;
  --color-surface: #FFFFFF;
  --color-ink:     #111827;
  --color-muted:   #6B7280;
  --color-faint:   #9CA3AF;
  --color-line:    #F3F4F6;
  --color-accent:  #0F172A;
  --color-ok:      #047857;
  --color-warn:    #B45309;
  --color-danger:  #B91C1C;

  --radius-card: 16px;

  --shadow-card:  0 1px 3px rgb(17 24 39 / 0.04), 0 8px 30px rgb(17 24 39 / 0.04);
  --shadow-hover: 0 2px 6px rgb(17 24 39 / 0.06), 0 12px 40px rgb(17 24 39 / 0.08);
  --shadow-float: 0 8px 40px rgb(17 24 39 / 0.12);

  --animate-shimmer: shimmer 1.6s infinite;
}
```

Motion constants live in `src/lib/motion.ts` so the spring is defined exactly once.
