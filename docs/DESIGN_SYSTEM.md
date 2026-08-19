# Design System — Smart Decor

Aesthetic benchmark: Havenly / Houzz — warm, editorial, airy. Light beige canvas,
soft shadows, generous radii.

## Design tokens (`frontend/src/index.css` `@theme`)

| Token | Value | Usage |
|---|---|---|
| `--color-cream` | `#FAF9F7` | Page background |
| `--color-sand` | `#F2EDE6` | Secondary surfaces, badges |
| `--color-clay` | `#C1633F` | Primary actions, accents |
| `--color-clay-dark` | `#A34E2E` | Hover, prices |
| `--color-walnut` | `#5D4037` | Headings |
| `--color-sage` | `#4C6444` | Success, verified links |
| `--color-ink` | `#2B2622` | Body text |
| `--color-stone` | `#8A8178` | Muted text |

## Typography

- **Inter** (Latin) with **Vazirmatn** fallback for Persian glyphs (prices render
  as `45,000,000 تومان` via `formatToman`).
- Scale: page title `text-2xl font-bold text-walnut`, section `text-lg font-bold`,
  body `text-sm`, captions `text-xs text-stone`.

## Components (`frontend/src/components/ui.tsx`)

- **Card** — `rounded-2xl bg-white`, layered soft shadow
  (`0 1px 3px / 0 8px 24px` at ~7 % ink).
- **Button** — variants `primary` (clay), `secondary` (sand), `ghost`, `danger`;
  all with `focus-visible:ring-2` for keyboard users.
- **Badge** — tones `neutral | success | warning | clay`; used for explainability
  chips ("92% Style", "Material: wood").
- **Input** — 1px `#E5DED3` border, clay focus ring.
- **Skeleton / EmptyState / ErrorState / Spinner** — every page has loading,
  empty and error states; no unstyled fallbacks.

## Patterns

- **Explainability chips** on every product card: Style % (clay), Color % (green),
  Budget % (neutral), matched material (amber) + one-line summary.
- **Paywall teaser**: blurred image + white veil + "Unlock with Pro" CTA.
- **Quiz stepper**: 5 slim progress bars, `aria-current="step"`.
- Style options are image cards (Unsplash, WebP, fixed dimensions → no CLS).
- Color palette is fully visual: preset swatches + native color picker.

## Accessibility

- Contrast: ink on cream 12.9:1; clay on white 4.6:1 (AA for large/bold UI text).
- All interactive elements keyboard-reachable, visible `focus-visible` rings.
- Toggle buttons expose `aria-pressed`; dialogs use `role="dialog" aria-modal`;
  floorplan SVG has `role="application"` with an aria-label.
- Images always have `alt`, `width`, `height`.

## Responsive

Mobile-first; verified breakpoints 375 px (single column, horizontal scroll nav),
768 px (2-col grids), 1440 px (4-col recommendation grid, max-w-6xl container).

## Performance rules (bindings for every new page)

1. `loading="lazy"` on all below-the-fold images, eager + `fetchPriority="high"`
   only for the LCP candidate.
2. Explicit `width`/`height` attributes — zero CLS.
3. Unsplash URLs must carry `fm=webp&q=70&w=…`.
4. Heavy libs (drag & drop) only via `React.lazy` in a dedicated chunk.
