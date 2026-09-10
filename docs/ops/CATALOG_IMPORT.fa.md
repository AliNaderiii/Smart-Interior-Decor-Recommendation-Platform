# راهنمای اپراتور: وارد کردن کاتالوگ واقعی فروشندگان (P4-ب / ADR-018)

**مخاطب:** ادمین محتوا / اپراتور استقرار
**ابزار:** `backend/scripts/import_catalog.py`
**قاعده‌ی طلایی:** هیچ ردیفی «تأییدشده» به دنیا نمی‌آید. هر محصول وارد‌شده اول به صف بازبینی ادمین می‌رود (`/admin/products` → فیلتر *pending*) مگر این‌که با `--verify` وارد شده باشد **و** دروازه‌ی صحت کاتالوگ (ADR-016) پاک باشد **و** مدل بینایی دسته‌ی اعلام‌شده‌ی فروشنده را تأیید کرده باشد.

---

## ۱. چه چیزی وارد می‌شود و چه چیزی نه

هر ردیف باید این‌ها را داشته باشد، در غیر این صورت با کد رد می‌شود:

| فیلد | الزامی | کد رد در گزارش |
|---|---|---|
| `source_product_id` (کد محصول نزد فروشنده) | بله | `source_product_id_missing` |
| `title_fa` (عنوان فارسی واقعی) | بله | `title_fa_missing` |
| `category` (برچسب دسته‌ی فروشنده؛ فارسی یا انگلیسی) | بله | `category_unmapped` |
| `price_toman` (یا `price` + `currency=rial`) | بله | `price_invalid` |
| `image_url` (آدرس مطلق http/https عکس همان محصول) | بله | `image_url_invalid` / `image_unreachable` / `image_invalid` |
| `seller_link` (لینک عمیق صفحه‌ی محصول) | خیر، ولی بدون آن در استقرار تولید پیشنهاد نمی‌شود (`seller_link_missing`) | — |
| ابعاد (`width_cm`,`depth_cm`,`height_cm` یا `dimensions_cm`=«220x95x85») | خیر (۰ = نامشخص) | — |
| `colors` (#RRGGBB)، `styles`، `materials`، `patterns` | خیر — اگر نباشد، از مدل بینایی پر می‌شود؛ مقدار خارج از تاکسونومی حذف و گزارش می‌شود | — |

چیزهایی که **هرگز** انجام نمی‌شود: حدس زدن دسته از روی عنوان، پر کردن ابعاد/قیمت خالی، ساختن عکس، تأیید خودکار بدون بررسی تصویر.

## ۲. مسیر هر ردیف

```
فید فروشنده ─▶ normalize (ساختار) ─▶ دانلود عکس با محافظ SSRF ─▶ اعتبارسنجی مثل آپلود ادمین + pHash
   ─▶ مدل بینایی (detected_category, برچسب‌ها) ─▶ upsert روی (source, source_product_id)
   ─▶ امبدینگ ─▶ مهر دروازه‌ی صحت (ADR-016) ─▶ صف بازبینی (یا --verify اگر همه چیز پاک بود)
```

اجرای دوباره‌ی همان فید = **به‌روزرسانی** قیمت/لینک/موجودی همان ردیف‌ها (نه تکرار). عکس بدون تغییر دوباره دانلود یا تحلیل نمی‌شود. ردیفی که فروشنده «ناموجود» اعلام کند، رد می‌شود و اگر قبلاً تأیید شده بود، از تأیید خارج می‌شود.

## ۳. پیش‌نیازها

```powershell
cd C:\Users\alina\Smart-Interior-Decor-Recommendation-Platform\backend
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8="1"
```

* `DATABASE_URL` به دیتابیس هدف اشاره کند. برای Render **External Database URL** را بردارید (Dashboard → سرویس Postgres → Connect → External؛ با `postgresql://…render.com/…` شروع می‌شود — Internal URL فقط داخل شبکه‌ی Render کار می‌کند) و در همان پنجره‌ی PowerShell `$env:DATABASE_URL="…"` بگذارید. شکل بدون درایور (`postgresql://` یا `postgres://`) قبول است و خودکار به psycopg 3 می‌رود. برای تمرین لوکال: `sqlite:///./import_rehearsal.sqlite3` و بعد `alembic upgrade head`.
* **قبل از هر چیز** هدف را چک کنید — بدون خواندن یا نوشتن حتی یک ردیف:

  ```powershell
  python scripts\import_catalog.py --check-db
  # database: postgresql+psycopg://…@dpg-….render.com/decor (postgresql/psycopg, alembic 0008, APP_ENV=development)
  # vision:   gemini model=gemini-3.5-flash-lite key set
  ```

  اگر مقدار جای‌گذار راهنما (`<…>`) هنوز در متغیر باشد، URL نامعتبر باشد، درایور نصب نباشد، میزبان در دسترس نباشد یا اسکیما از کد عقب باشد، ابزار با کد خروج `2` و یک جمله‌ی «مشکل + راه‌حل» می‌ایستد؛ همین پیش‌پرواز پیش از تماس با باسلام و پیش از خواندن فایل، در خود `file`/`basalam` هم اجرا می‌شود. رمز عبور هرگز چاپ نمی‌شود.
* مدل بینایی: `AI_PROVIDER=gemini` + `GEMINI_API_KEY` (یا openai). با `AI_PROVIDER=mock` ردیف‌ها وارد می‌شوند ولی هیچ‌کدام قابل تأیید خودکار نیستند و در تولید اصلاً بوت نمی‌شود.
* عکس‌ها: اگر `STORAGE_BACKEND=s3` تنظیم است، عکس‌ها روی فضای خودتان کپی می‌شوند (`rehost`)؛ در غیر این صورت آدرس فروشنده نگه داشته می‌شود (`link`) — روی Render رایگان دیسک بین دیپلوی‌ها پاک می‌شود، پس بدون S3 از `rehost` استفاده نکنید.

## ۴. مسیر الف — فایل CSV/JSON فروشنده

قالب را بگیرید و به فروشنده بدهید (اکسل باز می‌کند؛ عناوین فارسی هم پذیرفته می‌شود: «کد، عنوان، دسته، قیمت (تومان)، تصویر، لینک محصول، ابعاد، جنس، …»):

```powershell
python scripts\import_catalog.py --template > feed_template.csv
```

اجرای آزمایشی (چیزی نوشته نمی‌شود، گزارش کامل تولید می‌شود):

```powershell
python scripts\import_catalog.py file --path C:\Users\alina\Downloads\nilper.csv --seller nilper --report nilper-dry.json
```

خروجی نمونه:

```
== catalog import: feed:nilper — DRY-RUN (nothing written); integrity strict=False
   rows: 120  created=112 updated=0 unchanged=0 rejected=5 skipped=3
   eligible for recommendations: 109  excluded by integrity: 3  verified: 0  needs review: 14
   !! image≠category on 2 rows (kept unverified, excluded)
   by category: chair=20, coffee_table=18, sofa=40, storage=34
   integrity reasons: image_category_mismatch×2, dimensions_out_of_band×1
   rejections/skips: price_invalid×3, image_unreachable×2, unavailable×3
   - rejected         NLP-2231  price_invalid  مبل اداری مدل ...
```

اگر اعداد منطقی بود، نوشتن واقعی:

```powershell
python scripts\import_catalog.py file --path C:\Users\alina\Downloads\nilper.csv --seller nilper --yes
```

سپس در `/admin/products` فیلتر *pending* را باز کنید، عکس و دسته را ببینید و تأیید کنید. برای فروشنده‌ای که فیدش قبلاً چند بار پاک از آب درآمده:

```powershell
python scripts\import_catalog.py file --path ... --seller nilper --yes --verify
```

`--verify` فقط ردیف‌های پاک با تأیید تصویری را تأیید می‌کند؛ بقیه باز هم به صف می‌روند.

## ۵. مسیر ب — باسلام (Open API رسمی)

جست‌وجوی عمومی توکن نمی‌خواهد. شکل واقعی پاسخ جست‌وجو (۱۴۰۵/۰۶/۱۹) ثبت و در `tests/fixtures/basalam_search_live_shape.json` نگه داشته شده: پوشش `{"meta", "facets", "products": [...]}` و هر نتیجه با کلیدهای `name`، `photo: {"MEDIUM", "SMALL"}`، `primaryPrice`، `IsAvailable`، `categoryTitle`، `vendor.name`. **قیمت‌های درگاه به ریال است** (۱۰ برابر عددی که در basalam.com می‌بینید؛ برای نمونه `price: 297000000` = ۲۹٬۷۰۰٬۰۰۰ تومان). آداپتور این را می‌داند و به تومان تبدیل می‌کند (`price_converted_from_rial` در هشدارهای ردیف ثبت می‌شود).

اجرای آزمایشی همیشه با ثبت پاسخ خام:

```powershell
python scripts\import_catalog.py basalam --category rug --max-per-query 20 --image-mode link --dump-raw basalam-raw.json --report basalam-dry.json
```

* اگر ردیف‌ها رد شدند، گزارش می‌گوید **چه چیزی دیده شده** — هر ردیف رد‌شده یک خط `↳` دارد (مثلاً `image_url=missing image_raw=photo={'MEDIUM': None}` یا `price_toman=None price=0 currency=rial`). همان اطلاعات در `basalam-dry.json` زیر `rows[].warnings` است.
* بدون پایگاه داده و بدون شبکه می‌توانید ببینید آداپتور فایل خام را چطور می‌خواند:

```powershell
python scripts\import_catalog.py --inspect-raw basalam-raw.json
```

  خروجی برای پنج قلم اول: قیمت خوانده‌شده و تومانِ حاصل، آدرس عکس (یا مقدار خام اگر پیدا نشد)، برچسب دسته‌ی فروشنده و نگاشت آن، در دسترس‌بودن، لینک فروشنده و حکم نرمال‌ساز. اگر `items found: 0` دیدید یا حکم‌ها غیرمنتظره بود، فایل را برای من بفرستید.
* اگر روزی باسلام واحد قیمت را عوض کرد: `--price-unit toman` (واحد روی هر ردیف ثبت می‌شود).
* بعد از این‌که اجرای آزمایشی معقول بود:

```powershell
python scripts\import_catalog.py basalam --yes                       # هر هفت دسته، بدون تأیید خودکار
python scripts\import_catalog.py basalam --yes --verify --category sofa --category rug
```

با توکن دسترسی شخصی (پنل توسعه‌دهندگان باسلام → Tokens → scope `vendor.product.read`) جزئیات کامل محصول (ویژگی‌ها، ابعاد، موجودی) هم گرفته می‌شود، یا تمام محصولات یک غرفه‌ی همکار:

```powershell
$env:BASALAM_TOKEN="..."   # هرگز در ریپو یا چت نگذارید
python scripts\import_catalog.py basalam --details --yes
python scripts\import_catalog.py basalam --vendor 78910 --yes
```

نکته‌های صداقت داده در این آداپتور:
* قیمت = `price` (آنچه خریدار می‌پردازد)، نه `primary_price`/`primaryPrice` (قیمت پیش از تخفیف)؛ ریال → تومان یک‌بار و با ثبت هشدار. برای محصولِ دارای تنوع (`has_variation`) این قیمت ارزان‌ترین گونه است — پرچم روی ردیف می‌ماند تا در صف بازبینی دیده شود.
* عکس فقط از ظرف‌های خودِ محصول (`photo`/`photos`/`mainPhoto`/`images`) خوانده می‌شود؛ `vendor.photo` آواتار غرفه است و هرگز عکس محصول نمی‌شود.
* دسته = برچسب خود فروشنده اگر روی تاکسونومی بنشیند، وگرنه دسته‌ی جست‌وجو — و در هر دو حالت مدل بینایی باید تأیید کند (`image_category_mismatch` در غیر این صورت).
* ابعاد فقط از ویژگی‌های صریح محصول (طول/عرض/ارتفاع/ابعاد). `packaging_dimensions` جعبه است نه محصول؛ فقط با `--use-packaging-dimensions` و با ثبت منشأ.
* فروشندگان باسلام عکس کارخانه را به اشتراک می‌گذارند؛ عکس تکراری در همان اجرا ردیف دوم نمی‌سازد (`duplicate_image`).

## ۶. بعد از وارد کردن

1. `/admin/stats` → تعداد محصولات و «excluded» را ببینید.
2. `/admin/products` → *pending* را بازبینی کنید. ردیف با `image_category_mismatch` را **اصلاح** کنید (دسته‌ی درست) یا حذف کنید — تأیید اجباری فقط با `?force=true` و با ثبت در ممیزی.
3. کش پیشنهادها به‌طور خودکار پاک می‌شود (`rec:*`)؛ یک آزمون کوییک روی دمو بزنید.
4. در استقرار تولید (strict) ردیف بدون لینک عمیق یا با قیمت قدیمی‌تر از ۳۰ روز پیشنهاد نمی‌شود → آیتم ۳ (بازبینی دوره‌ای قیمت/لینک) همین را خودکار می‌کند.

## ۷. کدهای خروج

`0` انجام شد (یا اجرای آزمایشی) · `1` هیچ ردیفی قابل ورود نبود / درگاه پاسخ نداد · `2` خطای استفاده (مسیر/اسلاگ/دسته‌ی نامعتبر، یا `DATABASE_URL` ناقابل‌استفاده — پیام «fix:» را دنبال کنید).
