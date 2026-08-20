# V3 datasets audit

**Audit baseline:** `0998ba4` (V2 strict-mode merge)  
**Audit date:** 2026-08-20

## Executive summary

The V2 application had a sound, tested recommendation pipeline and production-shaped provider abstractions, but its default catalog was generated at startup. All **100 products** came from `backend/scripts/seed_products.py`; no retailer catalog was the source of truth. The V3 files close that gap while retaining deterministic offline fallbacks.

## Baseline mock/decorative inventory

| Area | V2 baseline | Evidence / risk | V3 integration decision |
|---|---|---|---|
| Products | 100 generated rows, fixed RNG seed | `build_products()` loops to 100; titles combine English adjectives/styles/categories | Load the committed Persian catalog; keep generator only as explicit fallback |
| Prices | Random ranges by category (sofa 18–120M Toman, etc.) | `random.uniform`, rounded to 100k | Use `price_toman` from dataset; expanded variants are deterministic ±10% and explicitly marked sample data |
| Dimensions | Random category ranges | `random.randint` for width/depth/height | Map `dimensions_cm.length/width/height` to width/depth/height |
| Images | 20 stable Unsplash IDs reused | Images are representative, not seller-owned product photography | Keep sample images until client supplies licensed images/S3 assets; expose the limitation in reports |
| Seller links | Generic Digikala/Torob home/category URLs | Links were not product-specific; `seller_link_ok=True` was assigned without a probe | Use product-level Digikala/Torob/sample retailer URLs and derive verification from an allowlisted hostname |
| Embeddings | Hash by default | Deterministic and useful offline, but not visual CLIP semantics | Retain hash fallback; support CLIP and precomputed vectors with an explicit warning |
| AI extraction | `AI_PROVIDER=mock` by default | Filename/URL keyword heuristic; Gemini/OpenAI paths are implemented but require keys | Keep offline mock, clamp all output to committed taxonomy, document production keys |
| Quiz taxonomy | Six styles/materials hardcoded in TypeScript | Frontend and AI could drift | Import taxonomy and questionnaire JSON as the UI source of truth; copy taxonomy to backend seed data |
| Questionnaire | Functional five-step flow, mostly English and hardcoded | No dataset-backed palettes/ranges/help | Read styles, palette cards, 10–300M ranges, 76cm rule and material metadata from JSON |
| Floorplan | Uses selected product dimensions | With random seed rows the geometry was random | Realistic catalog dimensions now flow through the existing product payload |
| Shopping list | `formatToman()` already used | Persian number formatting was correct; retailer labels were generic | Keep formatter and add Digikala/Torob badges |
| Paywall | Server-enforced first-result teaser; one hardcoded 490k Pro card | Policy and UI were disconnected | Read six plans from JSON and enforce free recommendation limit from backend copy |
| Payment | Zarinpal sandbox/production plus mock gateway; no card storage | Production requires merchant ID | Keep redirect-only architecture and source displayed monthly price from plan data |
| Email | Resend implementation plus logging mock | Mock returns success but sends no email | Keep offline behavior and document Resend key requirement |
| Storage | Local filesystem plus S3-compatible backend | Local path is not production CDN | Keep local fallback; document Arvan/Liara/AWS configuration |

## Baseline catalog composition

The 100 generated rows were spread by cycling six styles over eight categories (`sofa`, `coffee_table`, `rug`, `lighting`, `armchair`, `tv_stand`, `bookshelf`, `curtain`). Their values were reproducible because `random.seed(42)` was used, but reproducibility did not make them retailer data. Persian titles were only a category plus an English style token (for example, `مبل modern`).

## Link checker finding

`scripts/check_links.py` is database-backed and cannot audit seed source links without the application dependencies/database. Static inspection found that baseline seed links were only:

- `https://www.digikala.com/`
- `https://torob.com/`
- `https://www.digikala.com/main/home-and-kitchen/`

Those are reachable retailer destinations but not product links. The V3 loader stores product-specific URLs and flags only known retailer hosts. Availability and current price still require a client feed or scheduled link probe; sample paths must not be represented as live inventory guarantees.

## Data quality and governance notes

1. `products_realistic.json` contains 20 curated examples; `products_realistic_150.json` is a deterministic demo expansion, not 150 independently scraped SKUs.
2. Expanded rows retain source image and seller URL. They include `dataset_notice` so this provenance is explicit.
3. Unsplash remains the image source. Production requires licensed client images or S3/CDN URLs.
4. No API key or credential is committed. `.env.example` and `.env.example.v2` contain placeholders only.
5. Mock AI, local storage, mock payment and mock email remain supported for offline development.
