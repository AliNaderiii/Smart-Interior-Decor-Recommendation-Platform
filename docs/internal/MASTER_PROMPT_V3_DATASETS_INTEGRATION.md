# MASTER PROMPT V3 - REALISTIC DATASETS INTEGRATION
# For Ali Naderi - Smart Interior Decor Platform
# Goal: Transform 70% Mock/Decorative site into 100% Functional with 6 Realistic Datasets
# Use this as prompt to new Arena agent (or same agent) after v2-strict-mode

---

## YOU ARE A STAFF DATA ENGINEER + FULLSTACK ENGINEER + PM (15+ years)

You have the MVP v2-strict-mode running at https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/tree/v2-strict-mode
- 97 tests green, 119.89KB JS, p95 721ms @20k rows, 0 dead keys, WCAG AA 26/26
- But 70% of features are decorative mock: products are random Unsplash with random prices, AI is mock hash embeddings, seller links are Unsplash not Digikala, dimensions random, paywall mock

Your predecessor created 6 realistic datasets in `/datasets/` folder inspired by IKEA, Wayfair, Houzz, West Elm:

1. `products_realistic.json` - 20 realistic Iranian-market products (Persian names, Toman prices, Digikala/Torob links, real dimensions, color palettes, style/material tags, embedding descriptions)
2. `style_taxonomy.json` - 6 styles with fa/en names, colors, materials, icons, Wayfair keywords
3. `questionnaire.json` - 5 steps quiz (visual cards, color dots 48px, dimensions with 76cm walkway rule, budget histogram 10-300M Toman fa-IR, material multi-select)
4. `subscription_plans.json` - 3 homeowner plans (Free 0, Premium 99k/mo, Pro 199k/mo) + 3 designer plans (Free, Studio 299k, Agency 699k) with soft paywall logic like Havenly
5. `service_keys_template.env` - Complete .env template for AI (Gemini/OpenAI/CLIP), S3 (Arvan/Liara/AWS), Payment (Zarinpal), Email (Resend), Security (SECRET_KEY, FERNET), CDN
6. `design_assets.md` - Design tokens #FAF8F5, Inter+Vazirmatn, Framer Motion, empty states, Persian formatting, OptimizedImage

Your mission is to INTEGRATE all 6 datasets into the codebase so the demo at http://localhost:8080 shows realistic Persian products with Digikala links and real dimensions, not random Unsplash.

---

## PHASE 0: AUDIT CURRENT MOCK STATE (Do not skip)

Before writing code, create `docs/DATASETS_AUDIT.md`:

- Run current site via Docker: `docker compose up -d` and check http://localhost:8080
- Document which features are mock/decorative:
  - Products page: Does it show random price 18M-120M? Unsplash links? Random dimensions?
  - AI extraction: Does upload return random colors or real colors from Gemini?
  - Seller links: Do they go to Unsplash or Digikala? What does `check_links.py` return?
  - Floorplan: Are dimensions random or from realistic JSON?
  - Shopping list: Price fa-IR formatting? Links valid?
  - Paywall: Zarinpal sandbox or mock?
  - Email sharing: mailto or Resend?
- List all 100 current seed products: Are they random or realistic?

Commit audit.

---

## PHASE 1: PRODUCTS DATASET INTEGRATION (Highest Value)

**Goal:** Replace 100 random mock products with 20-150 realistic Iranian-market products from `datasets/products_realistic.json`

**Tasks:**

1.  **Read datasets/products_realistic.json** - Understand structure:
```json
{
  "id": "prod_001",
  "title_fa": "مبل راحتی مدرن 3 نفره طوسی",
  "price_toman": 48500000,
  "seller_link": "https://www.digikala.com/product/dkp-4585217/...",
  "image_url": "https://images.unsplash.com/...",
  "dimensions_cm": {"length": 220, "width": 95, "height": 85},
  "color_palette": ["#CFCFD1", ...],
  "style_tags": ["modern"],
  "material_tags": ["fabric", "metal"],
  "description_for_embedding": "modern minimal light gray 3-seater..."
}
```

2.  **Create `backend/scripts/load_realistic_products.py`:**
```python
"""
Load realistic products from datasets/products_realistic.json
- Reads JSON
- For each product, generates embedding via get_embedding(description_for_embedding)
  - If EMBEDDING_BACKEND=hash (offline), uses deterministic hash (current)
  - If EMBEDDING_BACKEND=clip_local and CLIP model available, uses real CLIP 512-dim
  - If seed_data/embeddings_real.json exists and --from-json flag, uses precomputed real vectors
- Creates Product row with real Persian data: title_fa, price_toman, seller_link Digikala, dimensions, color_palette, style_tags, material_tags, width_cm, depth_cm, height_cm, is_verified=True
- Also creates default accounts if not exist: demo@smartdecor.dev / Demo1234! etc (reuse existing logic from seed_products.py)
- Supports --expand flag: If only 20 products provided, duplicate with variations to reach 150 (change price +/-10%, dimensions +/-5%, color variations) - inspired by IKEA catalog expansion
- Supports --clear flag: Delete all existing products first

Usage:
python scripts/load_realistic_products.py --realistic
python scripts/load_realistic_products.py --realistic --expand-to 150
python scripts/load_realistic_products.py --realistic --from-json  # use embeddings_real.json if exists
"""

# Implementation must:
# - Use SessionLocal
# - For each product in JSON, call product_to_text and get_embedding
# - Handle both hash and real CLIP gracefully (try real, fallback to hash with warning)
# - Log: "Loaded 20 realistic products with Digikala links, avg price 45M, categories: sofa:5, coffee_table:3, etc"
# - After load, run: SELECT COUNT(*) and SELECT AVG(price) and log
```

3.  **Modify `backend/scripts/seed_products.py` to optionally read realistic JSON:**
   - Add argument `--realistic` that reads `datasets/products_realistic.json` instead of generating random
   - If file not found, fallback to random generation (backward compat)
   - Keep existing --from-json and --real-embeddings logic

4.  **Expand dataset from 20 to 150:**
   - Current file has 20 sample products. For realistic demo, need 100-150.
   - Write helper `datasets/expand_products.py` that takes 20 and generates 130 more by:
     - For each of 6 styles, generate 5 more variations per category (change price +/-10%, dimensions +/-5%, color palette shift, title variation with Fa adjectives like "چستر" vs "راحتی")
     - Ensure categories balanced: sofa 30, coffee_table 20, rug 20, lighting 20, chair 20, storage 20, decor 20 = 150
     - Save to `datasets/products_realistic_150.json`

5.  **Update Docker seed command:**
   - In `docker-compose.yml` backend command, change from `seed_products.py --if-empty --from-json` to `load_realistic_products.py --realistic --if-empty --from-json` or keep both (first try realistic, fallback to random)

6.  **Test:**
   - `docker compose down -v && docker compose up -d`
   - `docker compose exec postgres psql -U decor -d decor -c "SELECT title, price, seller_link, length_cm, width_cm FROM products LIMIT 5;"`
   - Should show Persian titles, Toman prices, Digikala links, real dimensions (not random)
   - Open http://localhost:8080/recommendations - should show realistic products with Persian names and Digikala badges
   - Open http://localhost:8080/shopping-list - should show ۴۵٬۰۰۰٬۰۰۰ تومان formatting and Digikala links (not Unsplash)

**Definition of Done Phase 1:**
- `datasets/products_realistic_150.json` exists with 150 products (or 20 if you keep sample)
- `backend/scripts/load_realistic_products.py` exists and works
- `docker compose exec postgres psql ... SELECT title` shows Persian titles and Digikala links
- Frontend at http://localhost:8080/recommendations shows realistic products, not random
- Commit: `feat(data): realistic products with Digikala links and real dimensions`

---

## PHASE 2: STYLE TAXONOMY & QUESTIONNAIRE INTEGRATION

**Goal:** Make quiz and admin use `style_taxonomy.json` and `questionnaire.json` as single source of truth

**Tasks:**

1.  **Style Taxonomy:**
   - Copy `datasets/style_taxonomy.json` to `frontend/src/assets/style_taxonomy.json` and `backend/seed_data/style_taxonomy.json`
   - Update backend Pydantic schemas to validate style_tags against this taxonomy (allowed values: modern, scandinavian, industrial, boho, minimal, classic)
   - Update frontend QuizPage Step 1 to read from taxonomy JSON instead of hardcoded array - display images from taxonomy.sample_image, icons, Persian labels
   - Update Admin ProductsPage: Style multi-select should show taxonomy options with icons and Persian labels, not free text
   - Update AI feature extractor prompt to clamp styles to taxonomy: "Allowed styles: {list from taxonomy}. Return ONLY from this list"
   - Commit

2.  **Questionnaire:**
   - Copy `datasets/questionnaire.json` to `frontend/src/assets/questionnaire.json`
   - Update QuizPage to read steps from JSON:
     - Step 1 style: visual cards 500x400 with gradient overlay (already done) but now data from JSON
     - Step 2 color: color dots 48px from JSON palettes (warm_neutrals, earthy_boho, etc) with mood labels
     - Step 3 dimensions: inputs with help text "76cm walkway (Modsy golden rule)" from JSON
     - Step 4 budget: histogram slider with ranges low/medium/high/luxury from JSON, fa-IR formatting, per-category toggle
     - Step 5 material: multi-select with icons 🪵🔩🧵 from JSON subtypes
   - Ensure budget ranges stored in Toman and displayed as ۱۰-۳۰ میلیون تومان
   - Commit

**Definition of Done Phase 2:**
- Quiz reads from questionnaire.json, not hardcoded
- Style taxonomy used in both frontend and backend validation
- Admin can only select styles from taxonomy (not free text)
- Commit

---

## PHASE 3: SUBSCRIPTION PLANS & PAYWALL INTEGRATION

**Tasks:**

1.  **Read datasets/subscription_plans.json**
2.  **Update frontend/src/pages/UpgradePage.tsx** to read plans from JSON:
   - Display 3 homeowner plans (Free 0, Premium 99k/mo, Pro 199k/mo) with features, popular badge, CTA فارسی, yearly discount 17%
   - Display 3 designer plans similarly
   - Use fa-IR price formatting: ۹۹٬۰۰۰ تومان
3.  **Update backend paywall middleware:**
   - Read limits from JSON: recommendations_per_category, moodboards, etc
   - Enforce: Free user only 1 recommendation per category, others blurred 40% + card "با پریمیوم 4 پیشنهاد بیشتر"
   - Ensure Zarinpal sandbox flow still works, no card storage
4.  **Update docs:**
   - Copy subscription_plans.json to docs/PLANS.json for client approval
5.  **Commit**

---

## PHASE 4: SERVICE KEYS & REAL AI INTEGRATION

**Tasks:**

1.  **Copy datasets/service_keys_template.env to .env.example.v2** and merge with current .env.example
   - Ensure all 7 sections documented: DB/Cache, AI, S3, Payment, Email, Security, CDN
   - Ensure mock fallbacks documented for offline dev
2.  **AI Provider-Agnostic Hardening:**
   - Ensure backend/app/core/config.py has AI_PROVIDER (mock/gemini/openai/clip_local) and EMBEDDING_BACKEND (hash/clip_local/openai)
   - Ensure ai/feature_extractor.py has provider switch via env and JSON-forced prompts with taxonomy clamping
   - Ensure ai/embedding_service.py has hash fallback that logs warning "Using hash fallback, not real CLIP - generate embeddings_real.json with --real-embeddings on networked machine"
   - Document one-time command to generate real embeddings:
     ```
     pip install torch sentence-transformers
     python backend/scripts/seed_products.py --real-embeddings
     # Creates backend/seed_data/embeddings_real.json
     ```
3.  **S3 & Payment & Email Mock Fallbacks:**
   - Ensure storage abstraction returns placeholder URL when S3_PROVIDER=mock, and real URL when arvan
   - Ensure payment returns mock redirect when PAYMENT_PROVIDER=mock
   - Ensure email returns mailto: + copy toast when EMAIL_PROVIDER=mock, real Resend when resend
4.  **Documentation:**
   - Update docs/DEPLOYMENT.md with section "How to go from mock to production with real Iranian product data and keys"
   - List what client needs to provide for production (6 keys + Excel)
5.  **Commit**

---

## PHASE 5: DESIGN ASSETS & POLISH

**Tasks:**

1.  **Read datasets/design_assets.md** and ensure design tokens implemented:
   - Background #FAF8F5 (not pure white)
   - Card radius 16px, soft shadow 0 8px 30px rgba(0,0,0,0.04)
   - Inter + Vazirmatn self-hosted via fontsource (no Google CDN)
   - Framer Motion spring damping 20 stiffness 300
   - formatToman uses fa-IR -> ۴۵٬۰۰۰٬۰۰۰ تومان (already done, verify)
   - OptimizedImage uses color_palette as blur placeholder (already done, verify)
2.  **Empty States:**
   - Check frontend pages: If no projects, does it show illustration + CTA or blank white? If blank, add illustration from undraw.co with #FAF8F5 background
3.  **Persian Formatting Sweep:**
   - Search all frontend files for `toLocaleString` or price display - ensure all use `formatToman` with fa-IR
   - Check dates if any use fa-IR
4.  **Commit**

---

## PHASE 6: FINAL INTEGRATION TEST & REPORTS

**Tasks:**

1.  **Rebuild with Realistic Data:**
```bash
docker compose down -v
docker compose up --build -d
docker compose logs backend --tail 20
# Should show: Loaded 150 realistic products with Digikala links
```

2.  **Test Every Feature with Real Data:**
   - Quiz with realistic budget ranges (10-300M Toman fa-IR)
   - Recommendations show Persian titles + Digikala links + real dimensions + explainability
   - Moodboard drag saves real product IDs (not mock)
   - Floorplan: Add realistic sofa 220x95 - does it show correct dimensions? Does collision detection work with real dimensions? Does walkway 76cm check work?
   - Shopping list: Shows ۴۵٬۰۰۰٬۰۰۰ تومان + Digikala badge + link validation (green dot)
   - Designer share: Copy link + toast works
   - Admin upload: Upload image -> mock AI extraction but with taxonomy clamping -> verify -> appears in recommendations
   - Paywall: Free user sees 1 per category + blur card

3.  **Run Existing Tests:**
```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend pytest -v
# Should still be 97 green (or 81 if on older branch)
```

4.  **Generate Reports for Client:**
   - `docs/reports/realistic_data_report.md`: How many products, avg price, categories breakdown, sample Digikala links, dimensions range
   - `docs/CLIENT_DATASETS_REQUEST.md`: What we used as sample (6 datasets) and what client needs to provide for production (Excel with same columns as products_realistic.json + 5 other items)
   - Update `docs/ACCEPTANCE_REPORT.md` with realistic data notes

5.  **Commit & Tag:**
```bash
git add datasets/ backend/scripts/load_realistic_products.py frontend/src/assets/ docs/
git commit -m "feat(data): integrate 6 realistic datasets - Persian products with Digikala links, taxonomy, questionnaire, plans"
git tag v2-datasets-realistic
git push origin v2-strict-mode
git push origin v2-datasets-realistic
```

---

## DEFINITION OF DONE V3 DATASETS INTEGRATION

- [ ] `datasets/products_realistic_150.json` exists with 100-150 products (or 20 sample if you keep)
- [ ] `backend/scripts/load_realistic_products.py` exists and loads realistic Persian products with Digikala links and real dimensions
- [ ] `docker compose exec postgres psql ... SELECT title, seller_link` shows Persian titles and Digikala links, not random
- [ ] Frontend at http://localhost:8080/recommendations shows realistic products (مبل چستر عسلی 2 نفره - ۸۹٬۰۰۰٬۰۰۰ تومان) with Digikala badge, not random Unsplash titles
- [ ] Style taxonomy from `style_taxonomy.json` used in quiz visual cards and admin multi-select (not hardcoded)
- [ ] Questionnaire from `questionnaire.json` used in QuizPage (budget histogram fa-IR, color dots 48px, 76cm help text)
- [ ] Subscription plans from `subscription_plans.json` used in UpgradePage with fa-IR pricing ۹۹٬۰۰۰ تومان and soft paywall logic
- [ ] Service keys template merged into .env.example with documentation for mock->production path
- [ ] Design assets verified: formatToman fa-IR everywhere, #FAF8F5 background, OptimizedImage uses color_palette
- [ ] Tests still green: 97 tests (or 81) pass
- [ ] Docs: `realistic_data_report.md` and `CLIENT_DATASETS_REQUEST.md` exist
- [ ] Commit and tag v2-datasets-realistic

**After this, site is no longer decorative mock - it's functional with realistic Iranian-market data, ready to show to Ponisha client as "This is sample structure, replace with your 300 products Excel"**

---

## NOTES FOR AGENT

- You are on branch v2-strict-mode @61d13e9+ which already has Phase 0-5 V2 Strict Mode (security, perf, minimal UI, 0 dead keys)
- Do NOT rebuild MVP v1.1 - you are improving it with realistic data
- Do NOT re-download CLIP model if huggingface blocked - use hash fallback with warning, and document one-time command to generate embeddings_real.json on networked machine
- Products realistic JSON currently has 20 sample products - expand to 150 via script or manually if needed for demo richness
- Keep mock fallbacks working offline - client may not have Gemini key yet
- All 6 datasets are in /datasets/ folder in repo root (if not, check workspace /home/user/datasets/ and copy to repo)
- After integration, update README with section "Realistic Datasets - How to go from mock to production"

---

## BEGIN NOW

1. Verify `datasets/` folder exists and has 6 files (or 5 JSON + 1 md)
2. If not, copy from /home/user/datasets/ to repo_root/datasets/
3. Create `docs/DATASETS_AUDIT.md` with current mock state analysis
4. Proceed Phase 1 Products Integration - create load_realistic_products.py and test via docker compose

You are continuing excellent Senior work. This integration will transform decorative demo into functional product.

BEGIN V3 DATASETS INTEGRATION.
