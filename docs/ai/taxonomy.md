# Interior-Design Taxonomy — reference (Stage 04)

Owner: Master Prompt 04 (taxonomy expert role). Machine-readable source:
`backend/seed_data/style_taxonomy.json` (`taxonomy_version: 2.1`).
Single load point in code: `backend/ai/taxonomy.py`.

## 1. Design rules

1. **Stable IDs** — snake_case English ids are the join key across quiz,
   products, extraction and the frontend. Labels (fa/en) may change; ids
   never. `taxonomy_version` 2.1 is **additive** over 2.0 (no id changed or
   removed).
2. **Persian labels mandatory** — every entity carries `name_fa`; integrity is
   test-enforced (`tests/test_ai_taxonomy.py::test_persian_labels_exist_for_every_entity`).
3. **One source** — quiz schema allowlists, extractor sanitisation and seed
   data all read the same module; drift is structurally impossible (tested).
4. **Unknown values are never guessed** — see §5.

## 2. Styles (6, ids unchanged since v1)

| id | name_fa | palette anchor |
|---|---|---|
| `modern` | مدرن | #2E2E2E #FFFFFF |
| `scandinavian` | اسکاندیناوی | #F2E8D5 #C8A165 |
| `industrial` | صنعتی | #1A1A1A #8B4513 |
| `boho` | بوهو / بوهمی | #C1633F #4C6444 |
| `minimal` | مینیمال | #FFFFFF #EDEDED |
| `classic` | کلاسیک | #6D4C33 #7B1E26 |

Each style entry also carries description_fa/en, materials, adjectives,
icon, sample image, retailer keywords and price tier (unchanged from 2.0 —
see the JSON).

## 3. Materials (6) and patterns (6)

| material | name_fa | subtypes (fa) |
|---|---|---|
| `wood` | چوب | بلوط روشن، گردو تیره، کاج، منگنه |
| `metal` | فلز | فلز مشکی مات، برنجی، استیل، آهن خام |
| `fabric` | پارچه | کتان، بوکله، مخمل، کتان بافت |
| `leather` | چرم | چرم طبیعی، چرم مصنوعی |
| `rattan` | حصیر | حصیر طبیعی، جوت، کنف |
| `glass` | شیشه | شیشه شفاف، دودی |

| pattern | name_fa | added in |
|---|---|---|
| `solid` | ساده / تک‌رنگ | 2.1 (formalised; previously extractor-only) |
| `geometric` | هندسی | 2.1 |
| `floral` | گلدار | 2.1 |
| `striped` | راه‌راه | 2.1 |
| `abstract` | انتزاعی | 2.1 |
| `persian` | نقش ایرانی | 2.1 |

Before 2.1 the pattern allowlist existed **only** inside the extractor as a
code literal; it is now taxonomy data with Persian labels.

## 4. Categories and room type

Room type is single-valued by design: `living_room` (the product scope of the
current platform). Categories (7, matching `app.models.product.CATEGORIES`,
cross-checked by test):

| category | name_fa |
|---|---|
| `sofa` | مبل |
| `coffee_table` | میز جلومبلی |
| `rug` | فرش |
| `lighting` | روشنایی |
| `chair` | صندلی |
| `storage` | نگهداری و ذخیره‌سازی |
| `decor` | دکوراتیو |

The seed pipeline generates eight source categories (`armchair`, `tv_stand`,
`bookshelf`, `curtain`) aliased into these seven (`chair`, `storage`, `decor`)
— documented behaviour, unchanged this stage.

## 5. Unknown-value policy (explicit)

Declared in the JSON (`unknown_value_policy`, with a Persian translation) and
enforced in three places:

* **Quiz input** — `styles`/`materials`/`patterns` outside the taxonomy →
  **422** with the allowed list in the error (`app/schemas/quiz.py`);
  `color_palette` entries must be `#RRGGBB` (was unvalidated — a malformed
  color silently scored as maximum distance); empty optional lists mean
  **"no preference"** and score neutrally (0.5), never zero.
* **Extraction output** — model values outside the taxonomy are **discarded,
  not mapped** to a nearest guess, recorded in `unknown_taxonomy_values`, and
  force the human-review gate (`ai/extraction_review.py`).
* **Scoring** — jaccard/color functions return the neutral 0.5 when either
  side is unknown, so an unknown never masquerades as a mismatch.

Dimension/room-type edge behaviour: room width/length bounded 100–3000 cm
(schema); budget bounded to the PostgreSQL int4 range (≤ 2,000,000,000
toman) with `budget_max > budget_min` enforced.

## 6. Integrity checks

`ai.taxonomy.validate()` (run by tests and the evaluation harness) asserts:
version present, unique style ids, `name_fa` on every entity, palettes
non-empty. The model-level `CATEGORIES` constant is cross-checked against the
taxonomy so the recommender can never query a category that does not exist.
