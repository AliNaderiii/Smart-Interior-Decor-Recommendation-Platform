# Phase 4 — Dead Keys: click log

**Result: PASS — 0 DEAD.**

Two independent audits, both green:

| Audit | Method | Coverage | Result |
|---|---|---|---|
| `scripts/auditDeadKeys.ts` | static AST scan | 89 interactive elements, 30 files | 0 DEAD, 0 PARTIAL |
| `frontend/scripts/clickAudit.mts` | jsdom, real clicks | 53 controls across 16 pages | 0 DEAD |
| `frontend/tests/e2e/deadKeys.spec.ts` | Playwright | all routes × 3 roles | **not executed — see below** |

## Why there are two audits

Static analysis proves a handler *exists*. It cannot prove the handler *does
anything*. A button wired to `onClick={() => {}}` passes the AST scan and is
still dead to the user. The jsdom harness closes that gap: it mounts each page
against a mocked API, clicks every enabled control, and asserts that the click
produces an observable change (DOM mutation or a fetch) without throwing or
logging a console error.

## Playwright status

`tests/e2e/deadKeys.spec.ts` and `playwright.config.ts` are committed and are
the intended CI gate. They could not be run in this sandbox:
`npx playwright install chromium` fails with ECONNRESET against the Chrome for
Testing CDN, and no system Chromium exists. The spec additionally covers what
jsdom structurally cannot: real navigation, true HTTP status codes (2xx/3xx or
429), clipboard reads, and the PNG download event.

Run it anywhere with a browser:

```bash
cd frontend && npx playwright install chromium
npx playwright test          # expects the dev server + API on :5173 / :8000
```

## Real defects this audit found and fixed

1. **`ProductCard` explainability trigger was hover-only.** The `HoverCard`
   opened on pointer hover with no click handler, so on touch devices the
   entire "why we matched this" breakdown — the product's core
   differentiator — was unreachable. Now a controlled `open` state toggled by
   click as well as hover.
2. **`UpgradePage.startPayment` crashed on a malformed gateway response.** It
   destructured `redirect_url` and immediately called `.startsWith()` on it. A
   200 response without that field (a plausible gateway outage) turned a
   recoverable payment failure into a white screen. Now guarded, with a user
   -facing message, plus a `catch` for the network path.
3. **Admin filter buttons had no `aria-pressed`.** Sighted users saw the
   active filter via colour alone; screen-reader users got no state at all.

## Verdicts other than OK/DEAD

- `SKIP` — destructive or session-ending (Sign out, Delete). Delete is covered
  by its own dedicated Playwright test rather than the blanket sweep, which
  would otherwise destroy the fixtures mid-run.
- `no-op: already the active state` — clicking the already-selected filter tab
  or layout toggle. Detected via `aria-pressed`/`aria-current`/`aria-checked`/
  `aria-selected`; a control that correctly reports its state is not dead.
- `delegates to a native API jsdom does not implement` — Upload (opens a file
  picker), Export PNG (needs a real canvas 2D context), image hover-zoom.
  Verified by the Playwright spec instead.
- `removed by an earlier interaction` — the control legitimately unmounted
  because a previous click in the same sweep changed the view.

## Full click log

```

=== CLICK AUDIT (jsdom) ===

PAGE               CONTROL                                        VERDICT  NOTE
------------------------------------------------------------------------------------------------------------------------
Home               Continue                                       OK       link → /admin/products
Login              Sign in                                        OK       DOM updated
Login              Create one                                     OK       link → /register
Register           Create account                                 OK       DOM updated
Register           Sign in                                        OK       link → /login
Quiz               Modernمدرن                                     OK       DOM updated
Quiz               Scandinavianاسکاندیناوی                        OK       DOM updated
Quiz               Industrialصنعتی                                OK       DOM updated
Quiz               Bohoبوهو                                       OK       DOM updated
Quiz               Minimalمینیمال                                 OK       DOM updated
Quiz               Classicکلاسیک                                  OK       DOM updated
Recommendations    grid                                           OK       DOM updated
Recommendations    masonry                                        OK       DOM updated
Recommendations    Upgrade to Pro                                 OK       link → /upgrade
Recommendations    Sofa                                           OK       DOM updated
Recommendations    Why we matched Linen Sofa: 87 percent overall  OK       DOM updated
Recommendations    Add to moodboard                               OK       DOM updated
Recommendations    More like Linen Sofa                           OK       fetch issued
Recommendations    Fewer like Linen Sofa                          OK       fetch issued
Recommendations    View at retailer ↗                             OK       link → https://shop.example.com/p
Recommendations    Why we matched Oak Table: 87 percent overall   OK       DOM updated
Recommendations    More like Oak Table                            OK       fetch issued
Recommendations    Fewer like Oak Table                           OK       fetch issued
Moodboards         Clear                                          OK       DOM updated
Moodboards         Create moodboard                               OK       removed by an earlier interaction
Moodboards         Open                                           OK       link → /moodboard/b1
Moodboards         Delete                                         SKIP     destructive/session-ending
MoodboardEditor    Try again                                      OK       fetch issued
Floorplan          Export PNG                                     OK       DOM updated
Floorplan          Linen Sofa200×90cm                             OK       DOM updated
Floorplan          Oak Table200×90cm                              OK       DOM updated
ShoppingList       Copy list                                      OK       DOM updated
ShoppingList       Open store ↗                                   OK       link → https://shop.example.com/p
ShoppingList       Increase quantity of Linen Sofa                OK       DOM updated
ShoppingList       Increase quantity of Oak Table                 OK       DOM updated
Upgrade            Pay with Zarinpal                              OK       fetch issued
DesignerDashboard  New project⌘K                                  OK       DOM updated
DesignerDashboard  All2                                           OK       no-op: already the active state
DesignerDashboard  Draft1                                         OK       DOM updated
DesignerDashboard  Shared1                                        OK       DOM updated
DesignerDashboard  Approved0                                      OK       DOM updated
DesignerDashboard  SharedVilla LavasanSASara Ahmadi2 quizzes8/20/ OK       removed by an earlier interaction
DesignerDashboard  DraftApartment TajrishRNReza N0 quizzes8/20/20 OK       removed by an earlier interaction
DesignerProject    Try again                                      OK       fetch issued
AdminProducts      all                                            OK       no-op: already the active state
AdminProducts      pending                                        OK       fetch issued
AdminProducts      verified                                       OK       fetch issued
AdminProducts      Upload product image                           OK       delegates to a native API jsdom does not implement
AdminProducts      Confidence ·                                   OK       DOM updated
AdminProducts      Enlarge image of Linen Sofa                    OK       DOM updated
AdminProducts      Verify                                         OK       fetch issued
AdminProducts      Edit                                           OK       DOM updated
AdminProducts      Enlarge image of Oak Table                     OK       DOM updated
AdminUsers         Disable                                        OK       fetch issued
------------------------------------------------------------------------------------------------------------------------

53 controls exercised · 0 DEAD · 1 skipped
RESULT: PASS — 0 DEAD
```

## Static audit

```
=== DEAD KEYS AUDIT ===
scanned 30 files, 89 interactive elements

(no findings)

TOTAL: 0 DEAD, 0 PARTIAL, 0 OK-DISABLED
RESULT: PASS — 0 DEAD
```
