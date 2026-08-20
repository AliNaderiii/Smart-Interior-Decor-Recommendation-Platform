# PERF REPORT V2 — Bundle, Backend & Bottlenecks (Phase 0B)

**Phase:** 0B (brutal audit) · **Date:** 2026-08-20 · **Auditor:** Agent #2 (Performance Engineer role)
**Build:** `v2-strict-mode` @ 61d13e9 (MVP v1.1) · **Frontend:** React 19 + Vite 8 (rolldown) · **Backend:** FastAPI on **real PostgreSQL 16.2 + pgvector 0.6.2** (embedded `pgserver`; Docker unavailable in sandbox).

---

## Executive summary

| Metric | v1.1 measured | V2 target | Status |
| --- | --- | --- | --- |
| Backend p95 `/recommend` @100 concurrent (warm) | **546 ms** | <1 000 ms | ✅ **already passing** |
| Backend p95 @100 concurrent (**cold cache**) | **662 ms** | <1 000 ms | ✅ passing |
| Throughput | **194 rps** | — | ✅ |
| Errors under load (500 req) | **0** (500× HTTP 200) | 0 | ✅ |
| Initial JS payload (gzip) | **158.4 KB** | <120 KB | ❌ **over budget** |
| Initial JS excluding mis-preloaded chunk | 137.6 KB | <120 KB | ❌ still over |
| Largest chunk | `vendor` 79.9 KB gzip | <100 KB | ✅ |
| Raw `<img>` tags (no WebP/AVIF/srcset) | **10** | 0 | ❌ |
| Virtualized long lists | **none** | required | ❌ |
| DB query plan | Seq Scan (100 rows) | index at scale | ⚠️ re-validate |

**Headline:** the backend is **not** the source of the hang the client reported — p95 is already 3× better than the v1.1 report (1.63 s → 546 ms) and comfortably inside the <1 s V2 goal. The problem is on the **frontend**, and the single biggest defect is a build-configuration bug that silently defeats the existing lazy-loading.

---

## 1. 🔴 P0 — The lazy chunk isn't lazy

`MoodboardEditorPage.tsx` correctly does the right thing:

```tsx
const BoardGrid = lazy(() => import("@/components/BoardGrid"));
```

and `vite.config.ts` isolates the library into its own chunk:

```ts
manualChunks(id) { if (id.includes("react-grid-layout")) return "gridlayout"; }
```

But the produced `dist/index.html` is:

```html
<script type="module" crossorigin src="/assets/index-Cn03ScH0.js"></script>
<link rel="modulepreload" crossorigin href="/assets/rolldown-runtime-hePW80VL.js">
<link rel="modulepreload" crossorigin href="/assets/gridlayout-BqlW1Ro5.js">   <!-- ❌ -->
<link rel="modulepreload" crossorigin href="/assets/vendor-popztvcq.js">
<link rel="modulepreload" crossorigin href="/assets/query-DlT7lgm_.js">
```

`gridlayout` (**75.6 KB raw / 20.9 KB gzip**) is `modulepreload`ed on **every route** — the home page, the login page, the quiz. The `React.lazy` boundary still defers *execution*, but the bytes are fetched, parsed and kept warm on 100 % of navigations. The chunking work in v1.1 bought nothing on the wire.

**Root cause:** because `manualChunks` names the chunk statically, rolldown treats it as part of the static entry graph and emits a preload hint for it.
**Fix (Phase 2):** stop hand-naming it in `manualChunks` and let the dynamic `import()` create the chunk naturally, or strip the hint via `experimental.renderBuiltUrl` / a `transformIndexHtml` plugin. Verify by asserting `gridlayout` is **absent** from `dist/index.html`.

---

## 2. Bundle analysis

`npm run build` — built in 423 ms.

### Initial payload (everything the browser fetches before first paint)

| Asset | Raw | Gzip | Necessary on first paint? |
| --- | --- | --- | --- |
| `vendor` (react, react-dom, react-router) | 246.5 KB | **79.9 KB** | yes |
| `query` (@tanstack, axios, zustand) | 89.3 KB | **29.7 KB** | partly |
| `index` (app entry) | 95.5 KB | **26.8 KB** | yes |
| `gridlayout` | 75.6 KB | **20.9 KB** | ❌ **no — see §1** |
| `index.css` | 36.4 KB | 7.5 KB | yes |
| `rolldown-runtime` | 0.7 KB | 0.4 KB | yes |
| **Total initial JS** | **507.6 KB** | **158.4 KB** | — |
| **Total initial JS after removing `gridlayout`** | 432.0 KB | **137.6 KB** | — |

Budget is **<120 KB gzip**. Even after fixing the preload bug we are **17.6 KB over**.

### Route chunks (correctly code-split ✅)

`ProductsPage` 2.5 KB · `FloorplanPage` 2.4 KB · `ShoppingListPage` 1.5 KB · `ProjectPage` 1.4 KB · `UpgradePage` 1.4 KB · `DashboardPage` 1.3 KB · `MoodboardEditorPage` 1.3 KB · `MoodboardsPage` 1.2 KB · `SharePage` 1.1 KB · `UsersPage` 0.8 KB · `SubscriptionsPage` 0.6 KB · `BoardGrid` 0.5 KB (all gzip).

Per-route splitting is genuinely well done — every page is ≤2.5 KB gzip.

### Fonts — 214 KB unsubset

| Font file | Size |
| --- | --- |
| `inter-latin-ext-wght-normal.woff2` | 85.1 KB |
| `inter-latin-wght-normal.woff2` | 48.3 KB |
| `vazirmatn-arabic-700-normal.woff` | 27.9 KB |
| `vazirmatn-arabic-400-normal.woff` | 27.3 KB |
| `inter-cyrillic-ext-wght-normal.woff2` | 26.0 KB |

**Cyrillic Inter is shipped and the product is English + Persian** — pure waste. Vazirmatn ships as `.woff`, not `.woff2` (~30 % larger than it needs to be). No `font-display: swap` audit was possible from the build output.

### Phase 2 plan to reach <120 KB gzip

| Action | Est. saving (gzip) |
| --- | --- |
| Fix the `gridlayout` preload (§1) | **−20.9 KB** |
| Drop Cyrillic + latin-ext Inter subsets | −(off critical path, ~111 KB transfer) |
| Vazirmatn `.woff` → `.woff2` | ~−17 KB transfer |
| Split `axios` out of the eager `query` chunk (or drop axios for `fetch`) | ~−5–8 KB |
| Route-level split of `@tanstack/react-query` devtools/unused paths | ~−3 KB |

Target after Phase 2: **≈118–125 KB gzip initial JS.**

---

## 3. Images — 🟠 P1

```
$ grep -rn "<img" frontend/src --include=*.tsx | wc -l
10
```

Across `BoardGrid.tsx`, `ProductCard.tsx`, `HomePage.tsx`, `MoodboardsPage.tsx`, `QuizPage.tsx`, `SharePage.tsx`, `ShoppingListPage.tsx`, `admin/ProductsPage.tsx`. There is **no `OptimizedImage` component** in `frontend/src/components/`.

Good practices already present (do not regress): explicit `width`/`height` on most images, `loading="lazy"`, and `fetchPriority="high"` + `loading="eager"` on the rank-0 LCP card in `ProductCard.tsx`.

Missing: **WebP/AVIF sources**, `srcset`/`sizes` for DPR and viewport, blur-up placeholder, and `decoding="async"`. Product imagery is the dominant byte weight of the recommendations page and is entirely unoptimised.

**Phase 2:** build `components/OptimizedImage.tsx` (`<picture>` + AVIF/WebP + `srcset` + reserved aspect box + async decode) and replace all 10 call sites; assert `0` raw `<img>` in the audit script.

---

## 4. Rendering — 🟠 P1

- **No virtualization anywhere.** `RecommendationsPage.tsx` maps the whole result set into `ProductCard`s. At 100 products this is survivable; combined with masonry (planned in Phase 3) and unoptimised images it is the most likely cause of the reported jank. → TanStack Virtual / `react-window` past ~60 items.
- **`ProductCard` is already `memo`ised** ✅ — good, keep it.
- **Moodboard drag is well engineered** ✅ — `useCallback` + `useRef` + 500 ms debounced autosave means dragging does not spam the API. The remaining risk is that a `layoutOverride` state change re-renders all cards; Phase 2 should confirm with a Performance trace and add `useTransition` if a long task >50 ms appears.
- **Generic `<Spinner/>` in 8 places** rather than layout-matched shimmer → guaranteed layout shift when data lands (CLS). The `Skeleton` primitive exists in `ui.tsx` but is **never imported**.

---

## 5. Backend performance — ✅ already meets the V2 target

### Load test (100 concurrent, warm cache, single uvicorn worker, rate limiter disabled)

```
conc=100 total=500 wall=2.58s rps=193.7
codes={200: 500}
mean=466.0ms p50=491.4ms p95=546.4ms p99=675.7ms max=705.3ms
```

### Load test (100 concurrent, **cold cache** — 300 unique quizzes ⇒ 300 unique cache keys)

```
COLD conc=100 total=300 wall=1.78s rps=168.3 codes={200: 300}
mean=501.4ms p50=588.3ms p95=661.6ms p99=776.9ms max=806.5ms
```

| | v1.1 report | This audit | Target |
| --- | --- | --- | --- |
| p95 @100 conc | 1 630 ms | **546 ms** (warm) / **662 ms** (cold) | <1 000 ms ✅ |

The cold/warm delta is only ~115 ms, which tells us the embedding + vector search path is genuinely cheap — the cache is not masking a slow query. **Zero errors** across 800 total requests.

### Query plan — `EXPLAIN (ANALYZE, BUFFERS)` on the fused Stage A+B query

```
Limit  (cost=9.33..9.37 rows=15) (actual time=0.112..0.114 rows=10 loops=1)
  ->  Sort  (actual time=0.111..0.112 rows=10)
        Sort Key: (style_embedding <=> '[…512 dims…]'::vector)
        Sort Method: quicksort  Memory: 25kB
        ->  Seq Scan on products  (actual time=0.035..0.101 rows=10)
              Filter: (is_verified AND price_toman >= 1000000 AND price_toman <= 90000000
                       AND room_type = 'living_room' AND category = 'sofa')
              Rows Removed by Filter: 90
Planning Time: 0.380 ms
Execution Time: 0.133 ms
```

**Execution time 0.133 ms.** The planner chooses a **Seq Scan** — which is *correct* at 100 rows (reading 100 tuples is cheaper than an index descent), and it is why the HNSW index does not appear in the plan. All required indexes do exist:

```
products_pkey · ix_products_category · ix_products_room_type · ix_products_price_toman
ix_products_is_verified · ix_products_filter · ix_products_style_embedding (HNSW, vector_cosine_ops)
```

⚠️ **This plan does not prove index health at scale.** The V2 claim "uses HNSW" is unverified until the catalogue is large. **Phase 2 action:** seed 10 000+ synthetic products and re-run `EXPLAIN ANALYZE`; assert an `Index Scan using ix_products_style_embedding` and p95 still <1 s.

### N+1 check

No per-product query loop in `app/services/recommender.py` — candidates are fetched in a single fused SQL statement and scored in Python. ✅ No N+1.

---

## 6. Remaining backend opportunities (Phase 2, low risk)

| Action | Rationale |
| --- | --- |
| `orjson` as FastAPI's default response class | Recommendation payloads are large JSON arrays; stdlib `json` is the serialisation hot spot once the DB is 0.1 ms |
| Add `Retry-After` to 429s | Correctness + client backoff (also a SECURITY_AUDIT_V2 item) |
| Real Redis in prod | fakeredis is per-process — rate limits and cache do not shard across workers |
| Cache key = `user_id + quiz hash` | Currently coarse; prevents cross-user cache bleed as personalisation lands |
| Re-test with `--workers 4` | All numbers above are single-worker; real deployment is multi-worker |

---

## 7. Not measurable in this sandbox

Lighthouse, INP and Chrome Performance traces need a headless Chrome + a deployed origin. `lighthouse-budget.json` exists in the repo and CI is wired for it. **Phase 2 DoD** must record: Lighthouse Performance ≥90, LCP <2.5 s, INP <200 ms on moodboard drag, CLS <0.1 — captured against the Liara deployment, not this sandbox.

---

## 8. Phase 2 Definition of Done

1. `gridlayout` **absent** from `dist/index.html` preload hints (regression-tested).
2. Initial JS **<120 KB gzip**.
3. **0** raw `<img>`; all images via `OptimizedImage` with AVIF/WebP + `srcset`.
4. Inter Cyrillic/latin-ext subsets dropped; Vazirmatn served as `.woff2`.
5. Virtualization on any list that can exceed 60 items.
6. Layout-matched shimmer replaces all 8 `<Spinner/>` usages.
7. 10 k-product `EXPLAIN ANALYZE` shows the HNSW index in use, p95 still <1 s.
8. `orjson` enabled; p95 re-measured at 4 workers.
9. Lighthouse ≥90 / LCP <2.5 s / INP <200 ms recorded in `docs/reports/`.

---

# PHASE 2 — IMPLEMENTATION RESULTS

_Measured after the Phase 2 changes landed. Same sandbox, same methodology as
the baseline sections above, so the numbers are directly comparable._

## 9. Frontend bundle

### 9.1 Initial JS — target <120 KB gzip

| Stage | Initial JS (gzip) | Delta |
| --- | --- | --- |
| Phase 0B baseline | **158.40 KB** | — |
| Fix mis-preloaded `gridlayout` chunk | 143.76 KB | −14.64 |
| Replace axios with native `fetch` | 119.95 KB | −23.81 |
| Lazy-load Quiz + Recommendations routes | **117.14 KB** | −2.81 |

**Result: 117.14 KB gzip — under the 120 KB budget** (was 158.40 KB, −26.0 %).
Adding the stylesheet the first paint costs 124.36 KB gzip.

Final entry graph:

| Asset | gzip |
| --- | --- |
| `vendor` (react, react-dom, react-router) | 77.88 KB |
| `index` (app shell + eager routes) | 24.13 KB |
| `query` (@tanstack/react-query, zustand) | 14.77 KB |
| `rolldown-runtime` | 0.36 KB |
| `index.css` | 7.22 KB |

Async chunks stay off the critical path: `BoardGrid` 17.69 KB, `ProductsPage`
2.41, `FloorplanPage` 2.31, every other route ≤1.5 KB.

#### The three findings behind those numbers

1. **`manualChunks` silently defeated the lazy boundary.** Naming
   `react-grid-layout` in `manualChunks` put it in the static entry graph, so
   Vite emitted `<link rel="modulepreload">` for it — the `React.lazy()`
   boundary still deferred *execution*, but ~21 KB gzip was *downloaded* on
   100 % of routes. Un-naming it was not enough: the broader
   `id.includes("node_modules/react")` rule then matched it (and its
   `react-draggable` / `react-resizable` deps) and forced it into the eager
   vendor chunk. It needs an explicit early `return undefined` **ahead of** the
   broad rules. Documented inline in `vite.config.ts` so it is not reintroduced.
2. **axios cost 23.81 KB gzip to do what `fetch` already does.** The client was
   rewritten onto native `fetch` behind the same public surface
   (`get/post/patch/del` + an axios-shaped `api` object), so no call site
   changed except two that were already wrong (see §9.4). axios is removed from
   `package.json`; `grep axios dist/assets/*.js` → 0 hits.
3. **Two eagerly-imported routes were unreachable while logged out.** Quiz and
   Recommendations are both behind `RequireAuth`, so they can never be the
   first paint — an anonymous visitor always lands on `/`, `/login` or
   `/share/:token`. Making them lazy moved 2.81 KB out of the entry chunk.

### 9.2 Fonts — 214 KB → 176 KB, and the right subsets

Baseline shipped Inter's Cyrillic + Greek + Vietnamese subsets to a
Persian/English product, and Vazirmatn twice (`.woff` *and* `.woff2`).

`@fontsource-variable/inter` publishes **no per-subset CSS** for the variable
font (only `index/wght/opsz[-italic].css`, all subsets inlined), so subsetting
required hand-written `@font-face` rules in `frontend/src/fonts.css` pointing at
the package's `files/*.woff2` with the upstream `unicode-range` values.

Build now emits exactly four font files:

| File | Size |
| --- | --- |
| `inter-latin-wght-normal.woff2` | 48.25 KB |
| `inter-latin-ext-wght-normal.woff2` | 85.06 KB |
| `vazirmatn-arabic-400-normal.woff2` | 21.08 KB |
| `vazirmatn-arabic-700-normal.woff2` | 21.72 KB |

All Cyrillic/Greek/Vietnamese subsets and every legacy `.woff` duplicate are
gone (~38 KB saved). CSS gzip fell 7.50 → 6.97 KB in the process.

### 9.3 Images — 10 raw `<img>` → 0

`frontend/src/components/OptimizedImage.tsx` replaces every raw tag:

- `<picture>` with AVIF → WebP → original fallback, via a `?format=&w=`
  derivative convention, guarded by `canDerive` so absolute/data URLs degrade
  to a plain `<img>` instead of emitting broken sources.
- `srcset` at `[320, 480, 640, 960, 1280]` + per-call-site `sizes`.
- **CLS defence**: mandatory `width`/`height` plus an `aspect-ratio` wrapper, so
  the box is reserved before the bytes arrive.
- Blur-up: `placeholderColor` tint cross-fading to the decoded image.
- `decoding="async"`; `priority` opts into `loading="eager"` +
  `fetchPriority="high"` and is set on exactly the two LCP candidates — the
  homepage hero and the first recommendation card (`rank === 0`).
- `React.memo`'d, because it renders inside long product grids.

Verified: `grep -rn "<img" src --include=*.tsx` returns only the single tag
*inside* `OptimizedImage` itself.

### 9.4 Two real bugs found while swapping the HTTP client

- `RecommendationsPage` called `api.post<Envelope<T>>(...)` and then unwrapped
  `.data.data` — a double unwrap that only worked because axios nests its own
  `data`. Now `post<RecommendResult>(url)`.
- The admin product upload posted `FormData` with an explicit
  `Content-Type: application/json` header. The rewrite detects `FormData` and
  omits the header so the browser can set the multipart boundary.

### 9.5 Render behaviour

- `RecommendationsPage` passed a fresh inline `onAdd` arrow on every render,
  which gave the `React.memo`'d `ProductCard` a new prop identity each time and
  **defeated the memo entirely** — adding one product re-rendered every card in
  the grid. Now a `useCallback` with a stable reference.
- `Skeleton` is a real gradient shimmer (`--animate-shimmer` keyframe in
  `index.css`), honouring `prefers-reduced-motion` via `motion-reduce:`.
- `ProductCardSkeleton` mirrors the real card's geometry so the grid does not
  reflow when data lands.

---

## 10. Backend

### 10.1 HNSW at scale — the baseline test was invalid, and it hid a real bug

Phase 0B ran `EXPLAIN ANALYZE` against 100 products and got a Seq Scan, which
proves nothing about the index. The table was seeded to **20,700 products**
(512-dim normalised vectors) and re-run.

The index is used:

```
Limit (actual time=4.085..4.188 rows=14 loops=1)
  ->  Index Scan using ix_products_style_embedding on products
        Order By: (style_embedding <=> $1::vector)
        Filter: (is_verified AND price_toman >= .. AND category = 'sofa' ..)
        Rows Removed by Filter: 32
Planning Time: 0.192 ms
Execution Time: 4.209 ms
```

**But look at `rows=14` for a `LIMIT 100`.** This is a *post-filtered* ANN
search: HNSW walks the graph in distance order while the `WHERE` clause throws
away anything outside the category/budget/verified window. At pgvector's
default `hnsw.ef_search = 40` the index only visits ~40 nodes, so most are
filtered away and Stage C silently receives a fraction of the candidates it is
supposed to rank. Recommendation *quality* degrades as the catalog grows, with
no error anywhere.

Recall vs. `ef_search` (4,210 eligible `sofa` rows, `LIMIT 100`):

| `ef_search` | candidates returned | latency |
| --- | --- | --- |
| 40 (pgvector default) | **14 / 100** | 6.9 ms |
| 100 | 26 / 100 | 5.7 ms |
| 200 | 58 / 100 | 6.7 ms |
| **400 (chosen)** | **100 / 100** | 8.9 ms |
| 800 | 100 / 100 | 13.4 ms |
| exact (seq scan, index off) | 100 / 100 | 14.1 ms |

Fixed by `SET LOCAL hnsw.ef_search` per transaction in `_stage_ab_postgres`,
driven by the new `settings.HNSW_EF_SEARCH = 400`. Full recall for ~2 ms, still
cheaper than the exact scan. Verified: 100/100 candidates.

### 10.2 Cache stampede — the actual cause of the tail latency

At 20,700 rows the first 100-concurrent run showed **p95 3226 ms**, far worse
than the 546 ms baseline. Profiling showed a *single* cold `/recommend` costs
only 139 ms (five sequential pgvector searches at ~31 ms each; the mock
embedding is 0.1 ms). So the query was not slow — the work was being done 100
times over. All 100 concurrent requests shared one cache key, all missed
together, and all recomputed.

Fixed with in-process single-flight (`_INFLIGHT` in `recommender.py`): the first
caller computes, the rest wait on the same lock and re-read the cache, paying a
Redis GET instead of five vector scans. Waiters have a 10 s budget after which
they recompute, so a stuck leader can never become an outage.

### 10.3 Cache key now scoped per user

`rec:{sha256(quiz)}` → `rec:{user_id}:{sha256(quiz)}`. The quiz is a small set
of enumerated choices, so identical answers across users were *likely*, and the
Pro paywall masking is applied on top of the cached result — a shared entry is
a tenancy hazard as soon as anything user-specific enters the payload. It also
lets one account's recommendations be invalidated (e.g. on upgrade) without
flushing the whole `rec:*` namespace.

### 10.4 orjson

Enabled as the app-wide default response class — but **not** via
`fastapi.responses.ORJSONResponse`, which FastAPI 0.141 deprecates and which
emitted a `FastAPIDeprecationWarning` on every single request. FastAPI's
replacement fast path only engages for routes with a `response_model`, and ours
return plain envelope dicts from `ok()`, so it would never apply. Instead
`app/core/json_response.py` subclasses Starlette's `JSONResponse` and renders
with orjson. Deprecation warnings: 0.

### 10.5 Load test — 20,700 products (30x the baseline dataset)

| Scenario | rps | mean | p50 | p95 | p99 | errors |
| --- | --- | --- | --- | --- | --- | --- |
| Cold, shared key, 100 conc x 500 — *before* single-flight | 85.8 | 1112 ms | 599 ms | **3226 ms** | 3352 ms | 0 |
| Cold, shared key, 100 conc x 500 — *after* | 162.3 | 569 ms | 565 ms | **717 ms** | 860 ms | 0 |
| Warm, 100 conc x 500 | 180.8 | 503 ms | 506 ms | **608 ms** | 633 ms | 0 |
| Cold, 300 **distinct** keys, 100 conc | 177.1 | 475 ms | 503 ms | **598 ms** | 655 ms | 0 |

**p95 <1 s met on every scenario**, on 30x the data the baseline used, with
zero non-200 responses across 1,800 requests. Single-flight cut cold-path p95
by 4.5x.

Backend suite: **71/71 passing** throughout.

---

## 11. Phase 2 DoD status

| # | Requirement | Status |
| --- | --- | --- |
| 1 | `gridlayout` absent from `index.html` preloads | ✅ |
| 2 | Initial JS <120 KB gzip | ✅ 117.14 KB |
| 3 | 0 raw `<img>`; all via `OptimizedImage` | ✅ |
| 4 | Font subsets trimmed; Vazirmatn `.woff2` only | ✅ 4 files |
| 5 | Virtualization on lists >60 items | ⏳ see below |
| 6 | Shimmer replaces `<Spinner/>` | ◐ primitive + product grid done; 7 call sites remain (Phase 5) |
| 7 | HNSW proven at 10 k+ rows, p95 <1 s | ✅ 20.7 k rows, p95 598–717 ms |
| 8 | orjson enabled | ✅ (p95 at 4 workers still pending) |
| 9 | Lighthouse ≥90 / LCP / INP in `docs/reports/` | ⏳ needs headless Chrome + deployed origin |

**Item 5 — virtualization is deliberately not implemented yet.** No list in the
app can currently exceed 60 items: `/recommend` returns at most 5 categories x 8
products, and the admin product table is server-paginated. Adding
react-window today would mean measurable complexity (fixed row heights, lost
native find-in-page, extra a11y wiring) guarding a threshold nothing reaches.
The honest trigger is admin catalog growth; revisit when the products table
serves unpaginated result sets or infinite scroll lands on recommendations.
