# Image-Host Migration Spec — Arvan S3 for catalog images

> **Status:** Stage 5 Phase 0 — investigation and design only. **No code changes.**
> This document enumerates every source of product-image URLs, proposes the
> Phase-1 mechanism for serving catalog images from Arvan S3, and provides the
> migration runbook and an interim fallback for the "unsplash is unreachable
> from Iran without a VPN" constraint.

---

## خلاصهٔ اجرایی (فارسی)

تصویر محصولات در نسخهٔ نمایشی از سرویس Unsplash گرفته می‌شود که از داخل ایران
بدون فیلترشکن در دسترس نیست. این سند مشخص می‌کند تصاویر از **کجا** می‌آیند،
و در فاز ۵ چطور به‌صورت قطعی از **فضای ابری ایرانی (Arvan S3)** سرو شوند تا
بدون فیلترشکن و با سرعت بالا باز شوند. سه بخش دارد: (۱) فهرست کاملِ همهٔ
نقاطی که نشانی تصویر در آن‌ها تعریف می‌شود، (۲) طرح فاز ۵ (باکت S3، تنظیمات
محیطی، نقطهٔ بازنویسی نشانی، و سازگاری با سیاست امنیتی CSP که از قبل آماده
است)، و (۳) راهنمای اجرای مهاجرت + راه‌حل موقت برای پیش از مهاجرت. این سند
فقط طراحی است؛ هیچ کدی تغییر نمی‌کند.

---

## 1. Sources of product image URLs (enumerated)

There is **no single runtime URL-rewriting layer**. The `image_url` value is
written once at ingestion time and rendered verbatim by the frontend. Every
source is listed below with its file path.

### 1.1 Demo / offline seed data (Unsplash URLs)

| # | Path | Role |
|---|---|---|
| 1 | `backend/seed_data/products_realistic_150.json` | The 150-product demo catalog; every `image_url` is `https://images.unsplash.com/photo-…` (150/150). |
| 2 | `datasets/products_realistic_150.json` | Canonical dataset copy of the same 150 products (identical content). |
| 3 | `datasets/products_realistic.json` | Smaller curated dataset (seller links, Digikala); also carries Unsplash `image_url` values. |

### 1.2 Seed code that constructs URLs

| # | Path | Mechanism |
|---|---|---|
| 4 | `backend/scripts/seed_products.py:42` | `UNSPLASH = "https://images.unsplash.com/photo-{pid}?w=800&q=70&fm=webp"` + `PHOTO_IDS` list; `seed_products.py:178` formats `image_url=UNSPLASH.format(pid=…)`. This is the **offline/demo** seed. |
| 5 | `backend/scripts/load_realistic_products.py:104` | `image_url=row["image_url"]` — reads the URL straight from the JSON/CSV dataset (sources 1–3). |
| 6 | `backend/scripts/seed_catalog_scale.py:86`, `backend/scripts/seed_perf_products.py` | Load-test/scale seeds generate synthetic `https://images.example.com/…` URLs (not production data). |

### 1.3 Database schema

| # | Path | Detail |
|---|---|---|
| 7 | `backend/app/models/product.py:33` | `image_url: Mapped[str] = mapped_column(Text, nullable=False)` — the single column. |
| 8 | `backend/alembic/versions/0001_initial.py:56` | `sa.Column("image_url", sa.Text(), nullable=False)` — no migration needed to change the *host*; the value is just a string. |

### 1.4 Admin upload path (already S3-compatible)

| # | Path | Detail |
|---|---|---|
| 9 | `backend/app/api/routes/products.py:131` (`upload_product_image`) | Calls `get_storage().upload_file(...)`. With `STORAGE_BACKEND=s3` this already writes to Arvan S3 (`backend/app/core/storage.py:62`, `S3Storage`) and returns `{S3_PUBLIC_BASE_URL or S3_ENDPOINT/bucket}/products/{key}`. |

### 1.5 Frontend rendering (no hardcoded URLs)

The frontend renders the DB value directly; there is no hardcoded image host:

| # | Path |
|---|---|
| 10 | `frontend/src/components/ProductCard.tsx` (lines 208, 239, 252) |
| 11 | `frontend/src/components/BoardGrid.tsx:45` |
| 12 | `frontend/src/components/PresentMode.tsx:110` |
| 13 | `frontend/src/pages/MoodboardsPage.tsx:79` |
| 14 | `frontend/src/pages/SharePage.tsx:81` (via `OptimizedImage`) |
| 15 | `frontend/src/pages/ShoppingListPage.tsx:261` |
| 16 | `frontend/src/pages/admin/ProductsPage.tsx` (zoom + preview, lines 541–549) |
| 17 | `frontend/src/lib/earlyRecommend.ts:51` |
| 18 | `frontend/src/lib/types.ts:46` (`image_url: string`) |

### 1.6 Validation and CSP (already permissive)

| # | Path | Detail |
|---|---|---|
| 19 | `backend/app/core/url_safety.py` | `validate_public_url(..., resolve=False)` is applied at the schema boundary (`backend/app/schemas/product.py:77`). Any `https://` public URL passes; no host allowlist pins it to Unsplash. |
| 20 | `backend/app/core/security_headers.py:build_csp()` | `img-src` already includes `'self'`, `data:`, `blob:`, `https://images.unsplash.com`, **plus** `S3_PUBLIC_BASE_URL`, `S3_ENDPOINT` (and its `https://*.host` virtual-host variant), `IMAGE_CDN_BASE_URL`, and `IMAGE_EXTRA_ORIGINS`. **No CSP change is required to serve images from Arvan S3** — only the env knobs need setting. |
| 21 | `Caddyfile` | Carries a byte-identical CSP copy; `scripts/print_csp.py` regenerates it after a config change, and `backend/tests/test_csp_alignment.py` enforces the alignment. |

---

## 2. Phase-1 mechanism (concrete design, no implementation)

Goal: serve the catalog images from the client's Arvan S3 bucket / CDN so they
load from Iranian IPs without a VPN, and make the host fully configurable.

### 2.1 Environment knobs (already exist in `backend/app/core/config.py`)

| Knob | Purpose |
|---|---|
| `STORAGE_BACKEND=s3` | Switch the upload path (`get_storage()`) to S3. |
| `S3_ENDPOINT` | Arvan endpoint, e.g. `https://s3.ir-thr-at1.arvanstorage.ir`. |
| `S3_BUCKET` | Client's bucket name, e.g. `decor-assets`. |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Arvan IAM credentials (never in the repo). |
| `S3_REGION` | e.g. `ir-thr-at1`. |
| `S3_PUBLIC_BASE_URL` | Public/CDN base for object URLs. |
| `IMAGE_CDN_BASE_URL` | Product-image CDN origin, added to CSP `img-src` automatically. |

### 2.2 URL rewrite point

The design has exactly one rewrite point — **at ingestion**, not at render:

* **Option A (recommended) — rewrite the dataset at import.** A one-time
  migration script downloads each unique `images.unsplash.com` URL (run from a
  machine with VPN), uploads it to the Arvan bucket under
  `products/{hash}.{ext}`, and rewrites `image_url` in the source JSON
  (`datasets/products_realistic_150.json`, `backend/seed_data/products_realistic_150.json`)
  and in the `products` table to
  `{S3_PUBLIC_BASE_URL or IMAGE_CDN_BASE_URL}/products/{hash}.{ext}`.
  `load_realistic_products.py` and `seed_products.py` then consume the new URLs
  unchanged, because they read `image_url` verbatim.

* **Option B — a thin rewrite helper in `seed_products.py`.** Replace the
  `UNSPLASH` constant with an `IMAGE_BASE` built from `IMAGE_CDN_BASE_URL`, so
  the offline/demo seed emits Arvan URLs directly. This covers the demo seed
  only; the JSON datasets still need Option A (or a rewrite in
  `load_realistic_products.py`).

Both options are additive and read-only with respect to the frontend; no
frontend change is needed because rendering is already host-agnostic (Section 1.5).

### 2.3 CSP

No code change: set `IMAGE_CDN_BASE_URL` (and/or `S3_PUBLIC_BASE_URL`) and
`build_csp()` adds the origin to `img-src` automatically (Section 1.6, #20).
After any change, run `scripts/print_csp.py --reference` to regenerate the
Caddyfile copy and keep `test_csp_alignment.py` green.

---

## 3. Migration runbook (client's future bucket)

Assumes the client has provisioned an Arvan S3 bucket and IAM credentials
(Phase 1). All secrets stay out of the repo (server environment only).

1. **Provision** the Arvan bucket (e.g. `decor-assets`) with `public-read` ACL
   for the `products/` prefix, and record the endpoint/region.
2. **Set env knobs** on the server: `STORAGE_BACKEND=s3`, `S3_ENDPOINT`,
   `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`,
   `S3_PUBLIC_BASE_URL` (and `IMAGE_CDN_BASE_URL` if a CDN fronts the bucket).
3. **Mirror the catalog** (from a VPN-connected machine): enumerate unique
   `image_url`s from the datasets in Section 1.1, download, and
   `put_object` to `products/{sha1(url)}.{ext}`.
4. **Rewrite** `image_url` in the datasets (Option A) and the DB
   (`UPDATE products SET image_url = …`), then re-run the seed/idempotent load.
5. **Verify CSP**: `scripts/print_csp.py --reference`, confirm the Arvan/CDN
   origin appears in `img-src`, then run `backend/tests/test_csp_alignment.py`.
6. **Smoke test** from an Iranian IP (no VPN): open the catalog, a moodboard,
   the share page, and the admin product grid — all images must render.

---

## 4. Interim fallback (before migration / unsplash without VPN)

Until the Arvan bucket is provisioned, the demo must work from Iranian IPs
without relying on `images.unsplash.com`. Two acceptable interim paths:

* **A — one-time local mirror via `STORAGE_BACKEND=local`.** Download the demo
  images once (VPN-connected machine), place them under `LOCAL_STORAGE_DIR`,
  and rewrite the 150 `image_url`s to the local `/media/{key}` paths. The
  demo then serves images from the backend itself — zero external egress.
* **B — a small CDN/bucket mirror (Arvan or any Iran-reachable host).** Upload
  the 150 images to the host and point `IMAGE_CDN_BASE_URL` at it; rewrite
  `image_url` to that origin. Functionally identical to Phase 1 but usable
  immediately with any reachable host.

Both are temporary; Phase 1 (Section 3) is the permanent path and reuses the
same rewrite point, so the interim work is not thrown away.
