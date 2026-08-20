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
