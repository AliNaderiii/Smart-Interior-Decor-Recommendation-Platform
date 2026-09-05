# MASTER PROMPT 05 — Frontend UX, RTL, Accessibility & Performance

## Mission
Turn the existing frontend into a credible Persian/RTL, mobile-responsive, accessible and fast client-facing product while preserving working behavior.

## Mandatory virtual team
Delegate to: Frontend Lead/UX manager (manager), senior React/TypeScript engineer, product designer, Persian RTL specialist, accessibility specialist, performance/Web Vitals engineer, content designer and responsive QA.

## Allowed scope
`frontend/src/**`, frontend public assets/styles, frontend tests and frontend build config; do not alter backend contracts or payment logic. If an API change is essential, create an integration request with schema and reason.

## Work
1. Map every user journey for anonymous, homeowner, designer and admin; ensure loading, empty, error, retry, success, offline and permission states have useful next actions.
2. Complete RTL: document direction, logical CSS, Persian typography, numerals, تومان formatting, focus order, keyboard navigation, modal behavior, charts, drag/resize and responsive breakpoints.
3. Audit accessibility: semantic landmarks, labels, contrast, focus-visible, screen-reader announcements, reduced motion, keyboard-only flow and automated axe checks.
4. Validate recommendation explanation, soft paywall, feedback and product cards; no misleading locked content or broken seller links.
5. Fix known UX risks: board selector for shopping lists, designer empty-state CTA, autosave feedback, floorplan collision/clearance messaging and error paths for destructive mutations.
6. Ensure image optimization (`picture`, AVIF/WebP where available, srcset/sizes, dimensions, async decode), lazy loading and safe external image handling.
7. Verify true code splitting and initial JS budget; remove accidental modulepreload of heavy async features; run build-size regression checks.
8. Test at mobile/tablet/desktop and slow network. Do not add scope items like export/undo unless explicitly prioritized.

## Evidence
Screenshots or Playwright traces for each role and breakpoint, axe report, Lighthouse report, bundle analysis, keyboard checklist, and `docs/agent-reports/frontend-rtl-ux-report.md`.

## DoD
No broken navigation or dead controls; RTL and English journeys pass; Lighthouse target and LCP target are measured on staging; accessibility blockers are fixed or explicitly accepted; TypeScript/build/lint pass.

## Parallel protocol
Branch `agent/frontend-rtl-ux-<date>`. Own frontend only. Do not modify backend, shared root docs or another branch.
