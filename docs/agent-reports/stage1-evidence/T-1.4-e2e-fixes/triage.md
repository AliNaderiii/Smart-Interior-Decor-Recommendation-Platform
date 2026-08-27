# T-1.4 close-out — triage of the 5 e2e failures in CI run 32988827678

Run `32988827678` (head `1812247`) was the **first time these specs ever ran in
a real browser** (IR-S1-001: the sandbox cannot download Chromium). 24 of 29
tests passed, including every auth-negative test and all three new role
journeys. The 5 failures were read via the annotation reporter added in
`1812247` — job logs and artifacts are both network-blocked from the sandbox.

**Verdict: 5/5 were faults in the test harness, not in the product.** No
assertion was skipped or weakened to reach green; one assertion was *added*.

---

## 1. `auth-smoke.spec.ts:16` — ENOENT on the storageState file

```
Error reading storage state from test-results/state/homeowner.json:
ENOENT: no such file or directory, open 'test-results/state/homeowner.json'
```

**Cause — a path-resolution mismatch between writer and reader.** Proved by
instrumenting a throwaway Playwright config:

```
GLOBALSETUP_WRITES=[.../frontend/tests/e2e/test-results/state/homeowner.json]
PROJECT_READS  =[.../frontend/test-results/state/homeowner.json]
```

`globalSetup` used `path.join(config.rootDir, ...)`, and `config.rootDir` is the
**testDir** (`frontend/tests/e2e`), not the project root. A relative
`storageState` in a project's `use` block is resolved by the Playwright client
against `process.cwd()` (`frontend/`, where CI invokes the suite). The two never
pointed at the same file.

**Fix.** New module `frontend/tests/e2e/statePaths.ts` derives an absolute
`STATE_DIR` from `import.meta.url`; `globalSetup.ts`, `playwright.config.ts` and
the `journey-designer` cleanup hook all import it, so writer and reader cannot
drift again regardless of cwd. `globalSetup` also `mkdir -p`s the directory,
asserts the file exists after writing, and logs each path.

**Why only this one test failed, when 8 siblings share the project:** the state
file was missing for the whole run, so every `chromium-homeowner` test that
needed a fresh context hit the same error; Playwright reported the first
occurrence per worker and the retry, which is the 2 annotations recorded. The
fix removes the cause rather than the symptom.

**Hardening (separate concern).** A silent login failure produced exactly this
same opaque ENOENT. `globalSetup` now waits for the login form to be visible
(hydration), and on a login that never leaves `/login` throws with the account,
the final URL, the page's `role="alert"` text and a full-page screenshot.

## 2-4. `deadKeys.spec.ts:94` — the click sweep, once per role

94 "click threw" + 88 "DEAD" verdicts across the three roles. Three independent
harness bugs, all confirmed against the source:

**(a) The `sr-only` skip link.** `/ :: Skip to content — click threw` was the
*first* failure on every route. Tailwind's `sr-only` renders a 1x1 clipped
element: `isVisible()` returns true, but `click()` cannot reach it until it is
focused, so it times out. The control is **not dead** — `Layout.tsx:107` has
`href="#main"` and `Layout.tsx:178` is `<main id="main">`.
*Fix:* excluded from the blind sweep with a comment explaining why, and a new
test `skip link is focusable and jumps to main content` asserts it the way a
keyboard user reaches it (Tab -> focused + visible, Enter -> URL `#main`, target
element visible). Net assertions go **up**, not down.

**(b) Modal overlays were never dismissed.** `⌘K` appears 4x in the "click
threw" tally. Clicking a control that opens the command palette or a dialog
leaves an overlay covering the page, so every later click in the sweep times
out — this is what turned ~3 real openers into ~90 bogus failures (38 of them on
`/admin/products` alone, the route with the most controls).
*Fix:* `dismissOverlay()` presses Escape (twice, for stacked dialogs) after each
click and verifies via `[aria-modal='true'], [role='dialog']` that it closed.

**(c) Page-load noise attributed to the wrong control.** The only "bad response"
entries were:

```
/recommendations :: Skip to content    — bad response: 422 POST /api/v1/recommend
/recommendations :: Switch to dark mode — bad response: 422 POST /api/v1/recommend
```

Opening `/recommendations` without quiz answers legitimately 422s on page load;
the watcher was still holding that event when the next control was clicked.
*Fix:* `watch.reset()` after every navigation, so a control is only ever judged
on traffic it actually caused. Click errors now also report the real exception
message instead of the bare string `"click threw"`.

## 5. `deadKeys.spec.ts:225` — command palette

`getByPlaceholder(/type a command/i)` timed out after 10s.

**Cause:** that placeholder has never existed. `CommandPaletteOverlay.tsx:47`
uses `placeholder="Search commands…"`. The Cmd/Ctrl+K handler is present and
correct (`CommandPalette.tsx:72`), and the overlay is **lazy-loaded**
(`lazy(() => import("@/components/CommandPaletteOverlay"))`), so the input only
exists once that chunk resolves.

**Fix:** match `/search commands/i` and allow 15s for the lazy chunk. The key
press was already correct and was left alone.

---

## Local verification (browser-independent gates)

See `frontend-gates.log` in this directory:

- `npm run lint` — 0 errors, 12 pre-existing warnings
- `npm test` — 58 passed / 8 files
- `npx tsc -p tsconfig.tests.json` — clean
- `npx playwright test --list` — **30 tests in 6 files** (29 + the new skip-link test)
- `npm run build` — ok

The specs themselves still cannot execute locally (IR-S1-001); CI is the only
environment that can run them.
