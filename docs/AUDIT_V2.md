# AUDIT V2 — Dead Keys, Gaps & Bottlenecks (Phase 0B)

**Phase:** 0B (brutal audit) · **Date:** 2026-08-20 · **Auditor:** Agent #2 (QA / Dead Keys Hunter role)
**Build:** `v2-strict-mode` @ 61d13e9 (MVP v1.1) · **Tool:** `scripts/auditDeadKeys.ts` (`npx tsx scripts/auditDeadKeys.ts`)
**Companion docs:** `docs/SECURITY_AUDIT_V2.md` (OWASP probes), `docs/PERF_REPORT_V2.md` (bundle + p95), `docs/RESEARCH_V2.md` (12-platform teardown).

---

## Executive summary

```
=== DEAD KEYS AUDIT ===
scanned 21 files, 55 interactive elements

[PARTIAL] frontend/src/pages/MoodboardsPage.tsx:92 <Button> "Delete" — handler triggers an API call but file has no catch/onError/toast
[PARTIAL] frontend/src/pages/admin/UsersPage.tsx:58 <Button> "(no label)" — handler triggers an API call but file has no catch/onError/toast

TOTAL: 0 DEAD, 2 PARTIAL, 0 OK-DISABLED
RESULT: PASS — 0 DEAD
```

| Metric | Value |
| --- | --- |
| Files scanned | 21 |
| Interactive elements found | 55 |
| **DEAD (enabled but inert)** | **0** |
| **PARTIAL (wired, no error path)** | **2** |
| Permanently disabled without explanation | 0 |
| `<a href="#">` decorative links | 0 |

**Headline:** the client's complaint that *"some keys are decorative"* is **not reproducible by static analysis on v1.1** — every one of the 55 interactive elements is wired to a handler, a `type="submit"`, an `href`, or a router `<Link>`. The real defects are of a different class: **missing error paths**, **absent features that were never built** (so there is no button to be dead), and **UX dead-ends** where a button works but leads nowhere useful. Those are catalogued below and are what Phase 4 must actually fix.

---

## 1. Tooling note — why the audit script was rewritten

`PHASE0_AUDIT_GUIDE.md` supplies a regex template. It was implemented and then **replaced**, because on this codebase it produces both false negatives and false positives:

| Guide template weakness | Consequence | Fix in our implementation |
| --- | --- | --- |
| `/<Button[^>]*>/` cannot match tags containing `>` inside a handler (`onClick={() => x > 1}`) or spanning multiple lines | Silently skips most real buttons — our buttons are multi-line | Brace/quote-aware tag scanner (`readOpeningTag`) |
| No notion of `type="submit"` | Every form submit button reported as DEAD | `type="submit"` counts as wired |
| No notion of `<Link to=…>` | Every router link reported as DEAD | `Link`/`NavLink`/`to` recognised |
| Substring `suspiciousButtons` check | Flags any file *mentioning* "Share" | Dropped in favour of per-element analysis |
| No line numbers | Findings not actionable | Every finding carries `file:line` |
| Treats all `disabled` as fine | Hides permanently-dead buttons | `disabled={true}` without `title`/`aria-label` ⇒ **DEAD** |

The script exits **1** when `DEAD > 0`, so it works as a strict-mode CI gate. `--json` emits machine-readable findings for the Phase 4 Playwright suite.

---

## 2. PARTIAL findings — must fix in Phase 1/4

### P-1 · `MoodboardsPage.tsx:92` — "Delete" board has no failure path

```tsx
const del = useMutation({ mutationFn: (id) => del(`/moodboards/${id}`), onSuccess: … });
<Button variant="danger" onClick={() => remove.mutate(b.id)}>Delete</Button>
```

If the DELETE fails (401 after token expiry, 500, offline) the row silently stays and **the user is told nothing**. Destructive action with no feedback.
**Fix:** `onError` + toast, and per Linear's undo-over-confirm pattern (RESEARCH_V2 §6) replace the confirm dialog with optimistic removal + a 5 s "Undo" toast.

### P-2 · `admin/UsersPage.tsx:58` — role/activation mutation has no failure path

Same class: an admin toggling a user's role gets no error feedback if the call fails — the most dangerous place to be silent, since the admin will assume the privilege change applied.
**Fix:** `onError` + toast + optimistic rollback.

---

## 3. Manual QA — verified working (not dead)

Each was booted against the live API (real Postgres) and traced to a real network call:

| Control | File | Verdict |
| --- | --- | --- |
| "Add to moodboard" | `ProductCard.tsx:105` | ✅ calls `onAdd`, flips to "Added ✓" and disables — correct disabled state |
| "Buy" seller link | `ProductCard.tsx:114` | ✅ real `href`, `target=_blank`, `rel=noreferrer noopener` |
| "Unlock with Pro" (locked card) | `ProductCard.tsx:26` | ✅ real `href="/upgrade"` |
| "Save layout" | `MoodboardEditorPage.tsx:92` | ✅ PATCH; correctly `disabled={saved \|\| isPending}` |
| "Add all to shopping list" | `MoodboardEditorPage.tsx:100` | ✅ PATCH + refetch |
| Moodboard drag/resize | `BoardGrid.tsx` | ✅ debounced 500 ms autosave — genuinely good |
| Quantity/Copy link | `ShoppingListPage.tsx:96` | ✅ clipboard + "Copied ✓" 1.5 s feedback |
| "Open store" | `ShoppingListPage.tsx:90` | ✅ real href |
| "+ New project" → modal → "Create" | `designer/DashboardPage.tsx:33,61` | ✅ modal opens, POST fires, `disabled={!form.name}` |
| "Share with client" | `designer/ProjectPage.tsx:71` | ✅ POST `/projects/{id}/share`, renders link |
| "Copy" share link | `designer/ProjectPage.tsx:88` | ✅ clipboard |
| "Sort by confidence" | `admin/ProductsPage.tsx:117` | ✅ real `useMemo` sort + explanatory `title` |
| Verify product | `admin/ProductsPage.tsx` | ✅ POST `/products/{id}/verify` |
| Login / Register submit | `LoginPage.tsx`, `RegisterPage.tsx` | ✅ react-hook-form + zod |

**The v1 "known likely dead keys" list in the guide does not match reality**: `Export PNG`, `Present mode`, `Undo/Redo`, `Masonry toggle`, `Zoom`, `Send Email`, `Bulk verify` and `Cmd+K` **do not exist as buttons at all**. They were never built. There is therefore nothing dead to disable — they are **missing features** (§4), and any of them we add in Phase 3/5 must ship wired or ship `disabled` with a tooltip.

---

## 4. Missing-feature gaps (no button exists → Phase 3/5 scope)

| Gap | Evidence | Phase |
| --- | --- | --- |
| No command palette | `grep -rn "metaKey\|cmdk"` → **0 hits** | 3 |
| No dark mode | `grep -rn "dark:"` → **0 hits** | 3 |
| No Framer Motion | not in `package.json` | 3 |
| No `OptimizedImage` | **10 raw `<img>`** across 8 files | 2 |
| No masonry/grid toggle | absent | 3 |
| No 👍/👎 feedback loop | absent (RESEARCH_V2 §2 — Havenly) | 3 |
| No walkway-clearance check | `FloorplanPage.tsx` does overlap only (RESEARCH_V2 §3 — Modsy) | 3 |
| No export to PNG | absent; needs `html2canvas` | 5 |
| No undo/redo on moodboard | absent | 5 |
| No toast system at all | no toast lib → root cause of both PARTIALs | 1 |
| No confetti / delight | absent | 5 |
| No colour-dot filters or price histogram | `RecommendationsPage.tsx` (RESEARCH_V2 §5 — Wayfair) | 3 |

---

## 5. UX dead-ends (button works, journey doesn't)

1. **Shopping list is hard-wired to `boards[0]`.** `ShoppingListPage.tsx:14` — `const boardId = boards?.[0]?.id`. A user with three moodboards can only ever see the shopping list of the first. Everything "works", the product is wrong. **P1 fix: board selector.**
2. **`EmptyState` on the designer dashboard has no CTA.** `DashboardPage.tsx:73` passes `title` + `hint` but no `action`, so the empty state is a dead end — exactly the anti-pattern Stripe avoids (RESEARCH_V2 §7).
3. **Generic `<Spinner/>` instead of layout-matched shimmer** on every page — 8 usages. Guarantees layout shift on load.
4. **`Skeleton` component exists but is never imported anywhere.** Dead code, not a dead key.
5. **Blur paywall is a hard wall** (`ProductCard.tsx:24`, `blur-md`) — RESEARCH_V2 §2 prescribes the soft Havenly paywall instead.

---

## 6. Security gaps found (detail in `SECURITY_AUDIT_V2.md`)

Live probes against real Postgres. Summary only:

| Severity | Finding |
| --- | --- |
| 🔴 P0 | **No brute-force protection** — 8/8 wrong passwords all returned 401 |
| 🔴 P0 | **All 6 security headers missing** (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy) |
| 🔴 P0 | **Tokens not in httpOnly cookies** — no `Set-Cookie` at all |
| 🔴 P0 | **No `audit_logs` table** |
| 🟠 P1 | **500 on 5 000-char title** (should be 422); schemas not `extra="forbid"` |
| 🟠 P1 | **Stored XSS persists unsanitised** |
| 🟠 P1 | No rate limit on `/auth/login` or `/auth/register` |
| 🟡 P2 | `ecdsa` 0.19.2 PYSEC-2026-1325 (no fix available; unused under HS256) |
| ✅ | **A01 access control: 8/8 IDOR/RBAC probes correctly denied** |

---

## 7. Performance bottlenecks (detail in `PERF_REPORT_V2.md`)

| Severity | Finding |
| --- | --- |
| 🔴 P0 | **`gridlayout` chunk is `modulepreload`ed on every page** — the `React.lazy` is defeated by Vite's preload hints; ~21 KB gzip wasted on 100 % of routes |
| 🟠 P1 | **10 raw `<img>`** — no WebP/AVIF, no `srcset` |
| 🟠 P1 | **No virtualization** — recommendations render the full result set |
| 🟠 P1 | `vendor` chunk 79.9 KB gzip of a 141 KB gzip initial payload |
| 🟡 P2 | Recommender query uses **Seq Scan** (correct at 100 rows; must be re-validated at 10 k+) |
| ✅ | **p95 546 ms @100 concurrent** (warm) / **662 ms** (cold) — already beats the <1 s V2 target, down from 1.63 s in v1.1 |

---

## 8. Phase 4 Definition of Done

- `npx tsx scripts/auditDeadKeys.ts` → **`0 DEAD, 0 PARTIAL`** (both PARTIALs fixed with a real toast system).
- `frontend/tests/e2e/deadKeys.spec.ts` (Playwright) clicks **every one of the 55+ interactive elements** across all three portals and asserts: no console error, and network 2xx (or an expected 4xx/429).
- Every newly-added Phase 3/5 control is either fully wired **or** `disabled` **with** a `title`/tooltip — enforced by the script's disabled-without-explanation rule.
- The two UX dead-ends (shopping-list board selector, empty-state CTA) are closed.
