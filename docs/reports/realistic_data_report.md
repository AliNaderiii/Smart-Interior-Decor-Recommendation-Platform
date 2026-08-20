# Realistic data integration report

Generated 2026-08-20 from `datasets/products_realistic_150.json`.

## Catalog profile

- Products: **150** (expanded deterministically from 20 curated samples)
- Average price: **22,636,600 Toman**
- Price range: **780,000–95,080,000 Toman**
- Dimensions: length **33–367cm**, depth/width **19–257cm**, height **1–166cm**
- Verified loader rows: 150
- Embedding dimensions: 512 (hash offline; CLIP/precomputed supported)

| Category | Rows |
|---|---:|
| sofa | 30 |
| coffee_table | 20 |
| rug | 20 |
| lighting | 20 |
| chair | 20 |
| storage | 20 |
| decor | 20 |

## Sample retailer destinations

- `https://www.digikala.com/product/dkp-4585217/...`
- `https://torob.com/p/7c3b8a9e/...`
- `https://www.digikala.com/product/dkp-3984521/...`

These are sample dataset links, not a live stock/price feed. Production must validate URLs and availability against the client's current catalog.

## Provenance

The 20 source records include Persian titles, Toman prices, physical dimensions, palettes, styles, materials and embedding descriptions. The 130 extra rows vary title, price (±10%), dimensions (±5%) and palette deterministically while retaining the source seller/image. Every expanded record carries `dataset_notice`. This gives demo category density without pretending that generated variants are independently sourced SKUs.
