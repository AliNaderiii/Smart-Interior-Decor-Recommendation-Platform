"""Basalam Open API → importer rows (official gateway ``openapi.basalam.com``).

Two dialects, both verified (2026-09-09 against ``basalam/python-sdk`` and
``developers.basalam.com/docs/quick-start``; 2026-09-10 against the live
search engine the gateway fronts, cross-checked with public product pages):

* ``POST /v1/products/search`` — JSON body ``{"q", "rows", "start",
  "filters": {"minPrice", "maxPrice", "slug", "vendorIdentifier", …}}``,
  **no token**. The response is the search engine's own envelope
  ``{"meta": …, "facets": …, "products": [hit, …]}`` and each *hit* speaks
  the search dialect, **not** the SDK models::

      {"id": 28107984, "name": "فرش دستباف یک متری …",
       "price": 297000000.0, "primaryPrice": 297000000,
       "photo": {"MEDIUM": "https://statics.basalam.com/…jpg_512X512X70.jpg",
                 "SMALL": "…_256X256X70.jpg"}, "photos": [],
       "status": {"id": 2976, "title": "در دسترس"}, "stock": 1,
       "IsAvailable": true, "IsSaleable": true, "canAddToCart": true,
       "vendor": {"id": 1011, "identifier": "gerehcarpetir",
                  "name": "فرش دستبافت گره", "photo": {"LARGE": …},
                  "owner": {"city": "اصفهان"}},
       "categoryTitle": "فرش دستباف", "new_categoryId": 299,
       "rating": {"average": 5.0, "count": 1}, "sales_count": 1,
       "weight": 6000, "has_variation": false, "tags": [...], "ads": {}}

* ``GET /v1/products/{id}`` and ``GET /v1/vendors/{id}/products?page&per_page``
  need a bearer token and answer in the SDK dialect: ``title``, ``photo
  {original, xs, sm, md, lg}``, ``photos[]``, ``vendor {id, identifier,
  title, city}``, ``category {id, title, parent}``, ``status {name,
  value}``, ``inventory``, ``is_available``, ``summary``/``description``,
  ``attribute_groups[].attributes[] {title, value, unit}`` or
  ``attributes[] {key, value}``, ``packaging_dimensions``, ``url``.

* **Money is rial in both dialects.** Product 28107984 is listed at
  ``price: 297000000`` and its page sells it for 29٬700٬000 تومان; the same
  ×10 holds for every product checked (also ``primaryPrice`` and the
  ``freeShippingToIran`` thresholds). The adapter therefore declares
  ``currency = "rial"`` (:data:`PRICE_UNIT`) and lets the contract apply its
  single conversion rule (``price // 10`` + ``price_converted_from_rial``);
  ``--price-unit toman`` exists only as an operator override should the
  gateway ever change the unit, and the unit is stamped on the row.

* Public product page: ``https://basalam.com/<vendor identifier>/product/<id>``
  (verified live).

Photo parsing is deliberately shape-tolerant: size keys are matched
case-insensitively (``LARGE``/``lg``/``original``/``MEDIUM``/…), containers
``photo``/``main_photo``/``mainPhoto``/``image``/``photos``/``images``/``media``
may hold a string, a dict or a list of either, and a protocol-relative
``//host/…`` becomes ``https://``. Only the *product's own* containers are
read — ``vendor.photo`` / ``vendor_photo`` are the shop's avatar, never the
product picture. When nothing usable is found the raw value travels with
the row (``image_raw``) so the rejection in the report says *what* was seen.

Honesty rules specific to this adapter:

* the **category** is carried as *candidates*, not decided here (P4-ب·2e,
  2026-09-11): the seller's own label (``categoryTitle`` / the ``category``
  chain / :data:`BASALAM_CATEGORY_IDS`) and the search term's target
  category. When they agree there is one candidate; when they disagree —
  Basalam sellers file armchairs under «مبل» (sofa) and TV stands under
  «میز» (table) — the pipeline lets the *picture* decide between the two
  (``detected_category``), and a picture that matches neither is an
  ``image_category_mismatch`` as before. The vision check has to agree with
  the final category before a row can be verified;
* **off-scope hits are skipped before any download or inference**: the
  search engine returns park lamps for «آباژور», kids' chairs for «صندلی»,
  book sets for «کتابخانه», bathroom shelves for «شلف». A short, explicit
  list of title words and Basalam leaf categories that can never be
  living-room decor (:data:`OFF_SCOPE_TITLE_TERMS`,
  :data:`OFF_SCOPE_CATEGORY_IDS`) marks such rows ``off_scope``; the
  pipeline skips them and the report counts them. Skipping is conservative
  — a false positive costs one candidate, never a wrong row;
* **dimensions** come only from explicit product attributes (طول/عرض/ارتفاع/
  ابعاد). ``packaging_dimensions`` describe the box, not the product, and are
  used only when the operator opts in (``use_packaging_dimensions``), with
  the provenance recorded on the row;
* **price** is ``price`` (what the buyer pays), never ``primary_price`` /
  ``primaryPrice`` (the pre-discount figure), and for a product with
  variations it is the lowest variant's price — ``has_variation`` is kept
  on the row so the review queue can see it.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from ai.catalog_integrity import PRICE_BANDS_TOMAN
from app.services.catalog_import.contract import (
    map_category,
    normalize_digits,
    parse_dimensions,
    to_int,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://openapi.basalam.com"
SOURCE = "basalam"
PRODUCT_URL = "https://basalam.com/{vendor}/product/{id}"
#: Unit of every money field the gateway returns (see module docstring).
PRICE_UNIT = "rial"
PRICE_UNITS = ("rial", "toman")
USER_AGENT = "SmartDecor-CatalogImporter/1.0 (+https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform)"

#: Search queries per taxonomy category — Persian retail vocabulary, most
#: specific first. Operators can override with ``--query``.
CATEGORY_QUERIES: dict[str, list[str]] = {
    "sofa": ["مبل راحتی", "مبل ال", "کاناپه"],
    "coffee_table": ["میز جلومبلی", "میز عسلی"],
    "rug": ["فرش دستباف", "فرش ماشینی", "گلیم"],
    # «چراغ ایستاده» pulled park/garden lamps and an infrared physiotherapy
    # lamp (2026-09-10 dry-run); «آباژور ایستاده» is 96% decorative-lamp live.
    "lighting": ["لوستر", "آباژور", "آباژور ایستاده"],
    # «صندلی راحتی» is 65% chair live and its top hits were folding camping /
    # relax chairs and a car seat cushion (2026-09-11 pilot); «صندلی راک چوبی»
    # is 72% chair and reads as a living-room piece.
    "chair": ["مبل تک نفره", "صندلی چوبی", "صندلی راک چوبی"],
    # «کتابخانه چوبی» is tokenised as «کتاب خانه» and returned book sets
    # («کتاب خانه درختی»); «کتابخانه ایستاده» is 65% closet/bookcase live.
    "storage": ["بوفه", "شلف دیواری", "میز تلویزیون", "کتابخانه ایستاده"],
    "decor": ["کوسن", "تابلو دکوراتیو", "آینه دکوراتیو", "گلدان دکوری"],
}

#: Basalam leaf categories (``new_categoryId`` on search hits) → taxonomy id.
#: Read live from ``facets.query_category`` and hits on 2026-09-10/11. Used
#: as a *second reading of the seller's label* when ``categoryTitle`` is not
#: an alias — never as the final word (see :func:`resolve_category`).
BASALAM_CATEGORY_IDS: dict[int, str] = {
    357: "sofa",
    355: "chair",
    358: "coffee_table",   # «میز» — any table; the picture tells a TV stand (storage) from a coffee table
    356: "storage",        # «کمد، کتابخانه، بوفه»
    291: "storage",        # «شلف و استند»
    366: "lighting",       # chandelier
    365: "lighting",       # lamps
    360: "lighting",       # decorative-lamp (آباژور)
    362: "lighting",       # bedside-lamp
    363: "lighting",       # desk-lamp
    305: "decor",          # «بالش و کوسن»
    287: "decor",          # «آینه و تابلو دکوراتیو»
    295: "decor",          # «مجسمه و تندیس»
    290: "decor",          # «ساعت دیواری»
    297: "decor",          # «تابلو فرش» hangs on a wall — it is wall art, not a floor rug
    299: "rug",            # hand-made carpet
    300: "rug",            # machine-made carpet
    301: "rug",            # modern carpet
    302: "rug",            # kilim
}

#: Basalam leaf categories that can never be living-room decor. A hit filed
#: there is skipped (``off_scope``) before its picture is downloaded or sent
#: to the vision provider. Slugs are Basalam's own (``facets.query_category``).
OFF_SCOPE_CATEGORY_IDS: dict[int, str] = {
    791: "books", 543: "novel-stories-books", 552: "psychology-books", 556: "kids-teenager-books",
    594: "travel-appliances", 591: "camping",
    437: "baby-food-accessories", 439: "baby-travel-accessories", 265: "baby-accessories",
    352: "bathroom-accessories", 353: "toilet-supplies",
    424: "rehabilitation-tools",
    1123: "shoe-rack", 359: "clothes-organizer", 330: "ironing", 289: "tablecloths",
    562: "blackboard-whiteboard", 576: "turbah-and-stand", 535: "dolls-figor-toys",
    528: "girls-toys", 532: "baby-toys",
    864: "tv-accessories", 306: "beds",
}

#: Replica guard (P4-ب·2f). 2026-09-11 live pilot: 14597663 — a 20 g «صندلی
#: راحتی دکوری کوچک» filed under «مجسمه و تندیس» (295) — reached ``chair`` as
#: verified because the picture *is* a chair. A blanket rule on leaf 295 is
#: wrong: 14102454, a 150 cm buffet, sits under the same leaf and is real. So
#: the guard reads the hit's own numbers instead:
#:
#: * a search hit whose ``weight`` (grams) reads as a *measurement* — at least
#:   :data:`MINIATURE_MIN_WEIGHT_G` — and is below :data:`MINIATURE_MAX_WEIGHT_G`
#:   cannot be a sofa, chair, table, cabinet or lamp, whatever the picture
#:   shows;
#: * a hit under a :data:`MINIATURE_PRONE_CATEGORY_IDS` leaf whose title says
#:   replica («فیگور», «دکوری کوچک», «جاکلیدی» …) is one;
#: * a hit under such a leaf that is *priced* below the cheapest plausible
#:   piece of its target category (:data:`REPLICA_PRICE_FLOOR_TOMAN`, the
#:   lower edge of the integrity price bands) is one too — 24617673, a solid
#:   800 g «صندلی راک چوبی دکوری» 28 cm tall at 495 000 toman, passed the
#:   weight rule and was verified as ``chair`` in the 2026-09-11 rehearsal.
#:   The picture cannot see scale; weight and price can.
#:
#: Decor is exempt from the weight and price rules: an empty cushion cover is
#: ~150 g and a wall sticker 20 g.
#:
#: The floor exists because the field is a *shipping* weight and sellers who
#: ship by freight leave it at a placeholder. The 2026-09-11 rehearsal of 2f
#: skipped ten real, full-size pieces as ``miniature:weight=1g`` /
#: ``weight=2g``: 25744387 (a solid-wood armchair, ``net_weight`` 2 on its own
#: product page), 5517592 (a sofa set), 4506396, 2448551, 925069, 702819,
#: 762717, 27740063, 37977395 (a coffee table), 10098793 (a four-tier wall
#: shelf whose real 6000 g sits in ``unit_quantity``). No furniture or lamp
#: hit in those 285 rows carried a weight between 3 g and 99 g; the one true
#: replica seen so far, 14597663, weighs 20 g. Below the floor the weight is *unknown*, never
#: evidence — the raw number still travels to ``extraction_raw.import.weight_g``
#: and the console line names it, so a kilogram typed into a gram field would
#: show up as ``miniature:weight=15g`` and cost one candidate, never a row.
MINIATURE_PRONE_CATEGORY_IDS: dict[int, str] = {
    295: "sculpture-and-statue",
}
MINIATURE_MIN_WEIGHT_G = 10
MINIATURE_MAX_WEIGHT_G = 100
_WEIGHT_GUARDED_CATEGORIES = frozenset({"sofa", "chair", "coffee_table", "storage", "lighting"})
#: Toman. Below this a hit under a replica-prone leaf cannot be the real
#: thing; read from the integrity bands so there is one notion of "cheaper
#: than any plausible sofa / chair / table / cabinet / lamp".
REPLICA_PRICE_FLOOR_TOMAN: dict[str, int] = {
    category: PRICE_BANDS_TOMAN[category][0] for category in sorted(_WEIGHT_GUARDED_CATEGORIES)
}
_MINIATURE_TERMS = ("فیگور", "فیگورین", "دکوری کوچک", "کوچک دکوری", "مینی", "جاکلیدی", "جا کلیدی", "آویز")

#: Sellers who only make children's furniture (cartoon sofa-beds, kids'
#: chairs). A vendor allow/deny list is a blunt tool, so it stays tiny and
#: every entry names the evidence: ``sitatoys`` — «تولید کننده مبل کودک و
#: نوجوان در طرح های مختلف کارتونی» (shop summary), four «کاناپه تخت شو السا /
#: کیتی / باب اسفنجی / بن تن» verified as ``sofa`` in the 2026-09-11 dry-run.
#: ``babylightland`` — «سرزمین روشنایی کودک … تخصصی ترین تولید کننده محصولات
#: کودک» (shop title and summary): a Manchester City chandelier (12153417)
#: and a Cristiano Ronaldo figure lamp (10071814) verified as ``lighting`` in
#: the 2026-09-11 rehearsal; the same shop's 12-pack «آباژور عمده» (36791198)
#: is also caught by the wholesale flag.
OFF_SCOPE_VENDORS: dict[str, str] = {
    "sitatoys": "kids-furniture-maker",
    "babylightland": "kids-lighting-maker",
}

#: Title words that mark a hit as outside the living-room scope, matched as
#: whole words (so «ماشین» — a car seat — never fires on «فرش ماشینی»).
#: ``"*"`` applies to every category; the rest only to that category, because
#: the same word is legitimate elsewhere («دیواری» kills a wall-hung kilim
#: but a «شلف دیواری» is exactly what the storage query wants).
# «فضای باز» is NOT here: sellers list it as one of several uses of a real
# indoor chair («خانه، مطالعه، فضای باز، کافه» — 52820553, 2026-09-11 dry-run).
_OUTDOOR_TERMS = ("پارکی", "حیاطی", "محوطه", "محوطه ای", "باغی", "خیابانی",
                  "مسافرتی", "کمپینگ", "کمپ", "ساحلی", "پیک نیک", "چادر", "طبیعت گردی")
#: Cartoon franchises Iranian kids'-furniture makers print on sofa-beds and
#: chairs; none is a living-room style.
_CARTOON_TERMS = ("السا", "فروزن", "کیتی", "باب اسفنجی", "بن تن", "مینیون", "مینیونها", "میکی موس",
                  "پو", "پونی", "یونیکورن", "اسپایدرمن", "مرد عنکبوتی", "بتمن", "سوپرمن", "کارتونی",
                  "سیندرلا", "پرنسس", "دایناسور", "مک کوئین")
OFF_SCOPE_TITLE_TERMS: dict[str, tuple[str, ...]] = {
    "*": (
        "کودک", "کودکان", "کودکانه", "بچه", "بچگانه", "نوزاد", "نوزادی", "عروسک", "عروسکی",
        "حمام", "دستشویی", "توالت", "سرویس بهداشتی",
        "ماکت", "مینیاتوری", "مینیاتور", "بادی",
        "مادون قرمز", "فیزیوتراپی", "ماساژور", "ماساژ",
        "خودرو", "اتومبیل", "ماشین",
        # football-club merchandise (a «لوستر منچستر سیتی», an «آباژور فوتبالی»)
        # is a kids'-room theme, not a living-room style
        "فوتبالی", "فوتبال",
        *_CARTOON_TERMS,
    ),
    # «طرح باغی» is a classic carpet design and «ساحلی» a decor mood: outdoor
    # words are off-scope only for furniture and lamps.
    "sofa": _OUTDOOR_TERMS,
    # A living-room ``chair`` is an armchair, a rocking / bentwood / wooden
    # chair. Folding camping and poolside recliners («تاشو», «ریلکسی») and
    # desk chairs («اداری», «کارمندی», «مدیریتی», «گیمینگ») are real chairs a
    # decor recommender must not show — 3 of the 5 rows of the 2026-09-11
    # live pilot were exactly these.
    "chair": (*_OUTDOOR_TERMS, "آرایشگاهی", "گیمینگ", "چرخدار", "تاشو", "تا شو", "ریلکسی", "پلاژی", "حالته",
              "اداری", "کارمندی", "کارشناسی", "مدیریتی", "کنفرانسی", "انتظار", "دانش آموزی",
              "آموزشی", "پزشکی", "طبی", "کانتر", "اپن", "بار", "غذاخوری", "ناهارخوری", "نهارخوری",
              # sellers also spell dining with a space («صندلی چوبی روستیک برای نهار خوری»,
              # 17937965, verified in the 2026-09-11 rehearsal); a term may be two words
              "غذا خوری", "ناهار خوری", "نهار خوری",
              "تحریر", "کامپیوتر", "ماهیگیری", "استخر", "استخری"),
    "coffee_table": (*_OUTDOOR_TERMS, "ناهارخوری", "غذاخوری", "ناهار خوری", "نهار خوری", "غذا خوری",
                     "تحریر", "آرایش", "اتو", "لپ تاپ", "لپتاپ", "کامپیوتر"),
    "storage": (*_OUTDOOR_TERMS, "آشپزخانه", "ادویه", "جاکفشی", "کفش", "دارو"),
    "lighting": (*_OUTDOOR_TERMS, "هیتر", "بخاری", "رشد گیاه"),
    "rug": ("دیواری", "تابلو", "تابلوفرش", "سجاده", "جانماز", "پادری"),
}

_TITLE_WORD_SPLIT_RE = re.compile(r"[\s\u200c\-_/|,،؛;:()\[\]{}«»\"'.!?*+]+")


def _title_words(title: str) -> list[str]:
    return [t for t in _TITLE_WORD_SPLIT_RE.split(normalize_digits(str(title or "")).replace("ي", "ی").replace("ك", "ک"))
            if t]


def _has_term(tokens: list[str], term: str) -> bool:
    """Whole-word match of ``term`` (one or more words; ZWNJ splits like a space)."""
    parts = _title_words(term)
    if not parts:
        return False
    if len(parts) == 1:
        return parts[0] in tokens
    return any(tokens[i:i + len(parts)] == parts for i in range(len(tokens) - len(parts) + 1))


def off_scope_reason(title: str, category: str | None, basalam_category_id: Any = None, *,
                     vendor_identifier: str | None = None, weight_g: Any = None,
                     price_toman: Any = None, wholesale: bool = False) -> str | None:
    """``"title:پارکی"`` / ``"basalam_category:791 books"`` / ``"vendor:sitatoys
    kids-furniture-maker"`` / ``"wholesale:is_wholesale"`` /
    ``"miniature:weight=20g"`` / ``"miniature:295 price=495000t<1000000t"``
    when the hit is outside the living-room scope, else ``None``. Pure and
    cheap: runs before any I/O. Every rule names its evidence so the console
    line explains itself.

    ``weight_g`` below :data:`MINIATURE_MIN_WEIGHT_G` is a placeholder the
    seller never filled in (1 g armchairs are common) and yields no verdict.
    ``wholesale`` is Basalam's ``is_wholesale`` flag: the listed price buys a
    carton (36791198: twelve lamps for 9.6 M toman), which a shopper following
    a recommendation cannot act on.
    """
    cid = to_int(basalam_category_id) if basalam_category_id is not None else None
    if cid is not None and cid in OFF_SCOPE_CATEGORY_IDS:
        return f"basalam_category:{cid} {OFF_SCOPE_CATEGORY_IDS[cid]}"
    vendor = str(vendor_identifier or "").strip().lower()
    if vendor and vendor in OFF_SCOPE_VENDORS:
        return f"vendor:{vendor} {OFF_SCOPE_VENDORS[vendor]}"
    if wholesale is True:
        return "wholesale:is_wholesale"
    tokens = _title_words(title)
    if tokens:
        for term in (*OFF_SCOPE_TITLE_TERMS["*"], *OFF_SCOPE_TITLE_TERMS.get(category or "", ())):
            if _has_term(tokens, term):
                return f"title:{term}"
    grams = to_int(weight_g, allow_zero=False) if weight_g is not None else None
    if (
        grams is not None
        and MINIATURE_MIN_WEIGHT_G <= grams < MINIATURE_MAX_WEIGHT_G
        and category in _WEIGHT_GUARDED_CATEGORIES
    ):
        return f"miniature:weight={grams}g"
    if cid is not None and cid in MINIATURE_PRONE_CATEGORY_IDS:
        if tokens and any(_has_term(tokens, term) for term in _MINIATURE_TERMS):
            return f"miniature:{cid} {MINIATURE_PRONE_CATEGORY_IDS[cid]} title"
        toman = to_int(price_toman, allow_zero=False) if price_toman is not None else None
        floor = REPLICA_PRICE_FLOOR_TOMAN.get(category or "")
        if toman is not None and floor and toman < floor:
            return f"miniature:{cid} price={toman}t<{floor}t"
    return None

#: Basalam status enum (from the SDK): 2976 published; the rest are not sellable.
_UNSELLABLE_STATUS = {3790, 4184, 3568}
#: Keys that hold the *product's* picture(s); ``vendor.photo`` / ``vendor_photo``
#: are the shop avatar and are deliberately absent.
_PHOTO_CONTAINERS = ("photo", "main_photo", "mainPhoto", "image", "photos", "images", "media")
#: Size keys, largest bounded rendition first, compared case-insensitively.
_PHOTO_SIZE_ORDER = ("large", "lg", "original", "medium", "md", "small", "sm",
                     "extra_small", "xs", "url", "src", "link", "path")
#: Flags that, when explicitly ``false``, mean "cannot be bought right now".
_AVAILABILITY_FLAGS = ("is_available", "IsAvailable", "isAvailable", "is_saleable", "IsSaleable",
                       "isSaleable", "can_add_to_cart", "canAddToCart", "published")

_MATERIAL_ALIASES: dict[str, str] = {
    "چوب": "wood", "چوبی": "wood", "ام دی اف": "wood", "ام‌دی‌اف": "wood", "mdf": "wood", "راش": "wood",
    "گردو": "wood",
    # Engineered wood boards Iranian sellers name by their surface — «ملامینه»
    # (melamine-faced chipboard), «لمینت»/«لمین» (laminate), «نئوپان», «hpl»,
    # «پی وی سی» on a board (PVC-foil MDF). 3 TV stands / a coffee table were
    # ``material_implausible`` in the 2026-09-11 dry-run only because these
    # words were unknown and the vision guess stood alone.
    "ملامینه": "wood", "ملامین": "wood", "لمینت": "wood", "لمینیت": "wood", "لمین": "wood",
    "نئوپان": "wood", "هایگلاس": "wood", "های گلاس": "wood", "hpl": "wood", "روکش pvc": "wood",
    "پی وی سی": "wood", "چند لایی": "wood", "چندلایی": "wood", "بامبو چوبی": "wood",
    "روس": "wood", "نراد": "wood", "بلوط": "wood", "افرا": "wood", "توسکا": "wood", "ملچ": "wood",
    "فلز": "metal", "فلزی": "metal", "آهن": "metal", "استیل": "metal", "برنج": "metal",
    "پارچه": "fabric", "پارچه‌ای": "fabric", "مخمل": "fabric", "کتان": "fabric", "پشم": "fabric",
    "نخ": "fabric", "ابریشم": "fabric", "اکریلیک": "fabric", "پلی استر": "fabric",
    "چرم": "leather", "چرم طبیعی": "leather", "چرم مصنوعی": "leather",
    "شیشه": "glass", "شیشه‌ای": "glass", "بلور": "glass",
    "حصیر": "rattan", "حصیری": "rattan", "راتان": "rattan", "بامبو": "rattan", "جوت": "rattan",
}
_DIM_TITLES = {
    "width_cm": ("طول", "length"),
    "depth_cm": ("عرض", "width", "عمق", "depth"),
    "height_cm": ("ارتفاع", "height", "بلندی"),
}
_CM_UNITS = ("سانتی", "سانت", "cm", "centimet")
_M_UNITS = ("متر", "m")


class BasalamError(RuntimeError):
    """Gateway refused or failed the request after retries."""


@dataclass
class BasalamClient:
    """Minimal synchronous client — only the three read endpoints the importer needs."""

    token: str | None = None
    base_url: str = BASE_URL
    timeout: float = 30.0
    retries: int = 3
    pause_seconds: float = 0.5
    #: Injectable transport for tests (``httpx.MockTransport``).
    transport: httpx.BaseTransport | None = None
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> BasalamClient:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout,
                                    transport=self.transport)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _request(self, method: str, path: str, *, auth: bool = False, **kwargs: Any) -> Any:
        if auth and not self.token:
            raise BasalamError(f"{method} {path} needs a Basalam personal access token (BASALAM_TOKEN)")
        assert self._client is not None, "use BasalamClient as a context manager"
        last: str = ""
        for attempt in range(1, self.retries + 1):
            try:
                resp = self._client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code in (429,) or resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}"
                elif resp.status_code in (401, 403):
                    raise BasalamError(f"{method} {path}: HTTP {resp.status_code} — token missing, expired or lacks the scope")
                elif resp.status_code >= 400:
                    raise BasalamError(f"{method} {path}: HTTP {resp.status_code} {resp.text[:200]}")
                else:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise BasalamError(f"{method} {path}: response is not JSON ({exc})") from exc
            time.sleep(min(2.0 ** attempt, 8.0) * self.pause_seconds)
        raise BasalamError(f"{method} {path} failed after {self.retries} attempts ({last})")

    def search(self, q: str, *, rows: int = 48, start: int = 0,
               vendor_identifier: str | None = None, min_price: int | None = None,
               max_price: int | None = None) -> Any:
        filters: dict[str, Any] = {}
        if vendor_identifier:
            filters["vendorIdentifier"] = vendor_identifier
        if min_price is not None:
            filters["minPrice"] = int(min_price)
        if max_price is not None:
            filters["maxPrice"] = int(max_price)
        body: dict[str, Any] = {"q": q, "rows": rows, "start": start}
        if filters:
            body["filters"] = filters
        return self._request("POST", "/v1/products/search", json=body)

    def product(self, product_id: int | str) -> Any:
        return self._request("GET", f"/v1/products/{product_id}", auth=True,
                             headers={"Prefer": "return=minimal"})

    def vendor_products(self, vendor_id: int | str, *, page: int = 1, per_page: int = 50) -> Any:
        return self._request("GET", f"/v1/vendors/{vendor_id}/products", auth=True,
                             params={"page": page, "per_page": per_page})


# ------------------------------------------------------------- response parsing

def find_product_list(value: Any, depth: int = 4) -> list[dict[str, Any]]:
    """Locate the list of product objects inside whatever envelope the gateway used."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping) and depth > 0:
        if len(value) == 1:  # {"openapi_raw_data": [...]} style wrapper
            inner = next(iter(value.values()))
            if isinstance(inner, (list, Mapping)):
                found = find_product_list(inner, depth - 1)
                if found:
                    return found
        for key in ("products", "items", "data", "results", "hits", "docs", "result"):
            if key in value:
                found = find_product_list(value[key], depth - 1)
                if found:
                    return found
        for inner in value.values():
            if isinstance(inner, (list, Mapping)):
                found = find_product_list(inner, depth - 1)
                if found:
                    return found
    return []


def _unwrap(item: Mapping[str, Any]) -> Mapping[str, Any]:
    src = item.get("_source")
    return src if isinstance(src, Mapping) else item


def _as_url(value: Any) -> str:
    """A usable absolute http(s) URL or ``""`` (``//host/…`` → ``https://host/…``)."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text.startswith("//"):
        text = "https:" + text
    return text if text.startswith(("http://", "https://")) else ""


def _url_from_photo(photo: Any, depth: int = 0) -> str:
    """First usable URL inside a photo value of any shape seen in the wild."""
    if isinstance(photo, str):
        return _as_url(photo)
    if isinstance(photo, list):
        for entry in photo[:5]:
            url = _url_from_photo(entry, depth)
            if url:
                return url
        return ""
    if isinstance(photo, Mapping) and depth < 2:
        by_key = {str(k).strip().lower(): v for k, v in photo.items()}
        for size in _PHOTO_SIZE_ORDER:
            if size in by_key:
                url = _url_from_photo(by_key[size], depth + 1)
                if url:
                    return url
        for value in photo.values():  # unknown size label — still the product's picture
            if isinstance(value, str):
                url = _as_url(value)
                if url:
                    return url
    return ""


def _photo_url(item: Mapping[str, Any]) -> str:
    for key in _PHOTO_CONTAINERS:
        url = _url_from_photo(item.get(key))
        if url:
            return url
    return ""


def _photo_raw(item: Mapping[str, Any], limit: int = 160) -> str:
    """Compact description of what the photo containers held (for the report)."""
    parts = [f"{key}={item[key]!r}" for key in _PHOTO_CONTAINERS if key in item]
    text = " ".join(parts) if parts else "no photo container in item (keys: " + ", ".join(list(item)[:12]) + ")"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _price(item: Mapping[str, Any]) -> int | None:
    for key in ("price", "primary_price", "primaryPrice"):
        raw = item.get(key)
        if isinstance(raw, Mapping):
            raw = raw.get("value", raw.get("amount"))
        value = to_int(raw, allow_zero=False)
        if value is not None:
            return value
    return None


def _weight_g(item: Mapping[str, Any]) -> int | None:
    """The hit's own weight in grams (``weight`` on search hits, ``net_weight`` on
    product objects) — ``None`` when absent or zero, never guessed."""
    for key in ("weight", "net_weight", "packaged_weight"):
        value = to_int(item.get(key), allow_zero=False)
        if value is not None and value > 0:
            return value
    return None


def _available(item: Mapping[str, Any]) -> bool:
    if any(item.get(flag) is False for flag in _AVAILABILITY_FLAGS):
        return False
    inventory = item.get("inventory", item.get("stock"))
    if inventory is not None and to_int(inventory) == 0:
        return False
    status = item.get("status")
    if isinstance(status, Mapping):
        value = to_int(status.get("value", status.get("id")))
        if value in _UNSELLABLE_STATUS:
            return False
        if str(status.get("name") or status.get("title") or "").strip() in ("ناموجود", "غیرفعال"):
            return False
    return True


def _vendor(item: Mapping[str, Any]) -> tuple[str, str]:
    vendor = item.get("vendor")
    if isinstance(vendor, Mapping):
        return (str(vendor.get("identifier") or ""), str(vendor.get("title") or vendor.get("name") or ""))
    return (str(item.get("vendorIdentifier") or item.get("vendor_identifier") or ""),
            str(item.get("vendorTitle") or item.get("vendor_title") or ""))


def _seller_link(item: Mapping[str, Any], vendor_identifier: str, product_id: str) -> str:
    url = item.get("url") or item.get("link")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    if vendor_identifier and product_id:
        return PRODUCT_URL.format(vendor=vendor_identifier, id=product_id)
    return ""


def _category_label(item: Mapping[str, Any]) -> str:
    cat = item.get("category")
    if isinstance(cat, Mapping):
        return str(cat.get("title") or cat.get("name") or "")
    if isinstance(cat, str):
        return cat
    # search dialect: the seller's leaf category arrives as a flat title
    return str(item.get("categoryTitle") or item.get("category_title") or "").strip()


def _category_id(item: Mapping[str, Any]) -> Any:
    cat = item.get("category")
    if isinstance(cat, Mapping) and cat.get("id") is not None:
        return cat.get("id")
    return item.get("new_categoryId") or item.get("categoryId") or None


def _category_chain(item: Mapping[str, Any]) -> list[str]:
    """Leaf → root category titles (the leaf may be too specific to map)."""
    out: list[str] = []
    node = item.get("category")
    depth = 0
    while isinstance(node, Mapping) and depth < 6:
        title = str(node.get("title") or node.get("name") or "").strip()
        if title:
            out.append(title)
        node = node.get("parent")
        depth += 1
    return out


def _iter_attributes(item: Mapping[str, Any]) -> Iterator[tuple[str, str, str]]:
    groups = item.get("attribute_groups")
    if isinstance(groups, list):
        for group in groups:
            attrs = group.get("attributes") if isinstance(group, Mapping) else None
            for attr in attrs or []:
                if isinstance(attr, Mapping):
                    title = str(attr.get("title") or "").strip()
                    value = attr.get("value")
                    if value in (None, "") and isinstance(attr.get("selected_values"), list):
                        value = ", ".join(
                            str(v.get("title") or v.get("value") or "") for v in attr["selected_values"]
                            if isinstance(v, Mapping)
                        )
                    yield title, str(value or "").strip(), str(attr.get("unit") or "").strip()
    attrs = item.get("attributes")
    if isinstance(attrs, list):
        for attr in attrs:
            if isinstance(attr, Mapping):
                yield (str(attr.get("title") or attr.get("key") or "").strip(),
                       str(attr.get("value") or "").strip(), str(attr.get("unit") or "").strip())


def _to_cm(value: str, unit: str) -> int | None:
    # Keep the decimal ("0.85 متر", "2.5 m") until the unit has been applied.
    text = re.sub(r"[^\d.]", "", normalize_digits(value).replace("٫", ".").replace(",", ""))
    try:
        decimal = float(text or "x")
    except ValueError:
        return None
    if decimal < 0:
        return None
    unit_l = unit.lower()
    if any(u in unit_l for u in _CM_UNITS) or not unit_l:
        return int(round(decimal))
    if unit_l.startswith("mm") or "میلی" in unit_l:
        return int(round(decimal / 10))
    if any(unit_l == u or unit_l.startswith(u) for u in _M_UNITS):
        return int(round(decimal * 100))
    return None


def dimensions_from_attributes(item: Mapping[str, Any]) -> dict[str, int]:
    """Explicit product-dimension attributes → ``{width_cm, depth_cm, height_cm}`` (partial)."""
    dims: dict[str, int] = {}
    for title, value, unit in _iter_attributes(item):
        low = title.lower()
        if not value:
            continue
        if "ابعاد" in low or low in ("dimensions", "size"):
            parsed = parse_dimensions(value)
            if parsed:
                dims.setdefault("width_cm", parsed[0])
                dims.setdefault("depth_cm", parsed[1])
                dims.setdefault("height_cm", parsed[2])
            continue
        for column, names in _DIM_TITLES.items():
            if any(low == n or low.startswith(n + " ") or low.startswith(n + "(") for n in names):
                cm = _to_cm(value, unit)
                if cm is not None and column not in dims:
                    dims[column] = cm
    return dims


#: Title words that name a material unambiguously. A subset of
#: :data:`_MATERIAL_ALIASES` on purpose: «استیل» in a title is the *style*
#: («مبل استیل» = carved classic sofa), «گردویی» is a colour, «برنج» may be rice.
_TITLE_MATERIAL_ALIASES: dict[str, str] = {
    "چوبی": "wood", "چوب": "wood", "ام دی اف": "wood", "mdf": "wood", "ملامینه": "wood", "ملامین": "wood",
    "لمینت": "wood", "لمین": "wood", "نئوپان": "wood", "هایگلاس": "wood", "های گلاس": "wood",
    "فلزی": "metal", "آهنی": "metal", "آهن": "metal", "فرفورژه": "metal", "برنجی": "metal", "مسی": "metal",
    "پارچه ای": "fabric", "پارچه‌ای": "fabric", "پارچه": "fabric", "مخمل": "fabric", "مخملی": "fabric",
    "کتان": "fabric", "پشمی": "fabric", "ابریشمی": "fabric",
    "چرم": "leather", "چرمی": "leather",
    "شیشه ای": "glass", "شیشه‌ای": "glass", "شیشه": "glass", "بلور": "glass", "کریستال": "glass",
    "حصیری": "rattan", "حصیر": "rattan", "راتان": "rattan", "بامبو": "rattan", "جوت": "rattan",
}


def materials_from_title(title: str) -> list[str]:
    """Materials the seller wrote *in the title* («میز عسلی چوبی با صفحه شیشه ای»
    → ``["wood", "glass"]``), in title order. Search hits carry no attributes,
    so without ``--details`` this is the only seller-declared material; the
    pipeline lets it win over the vision guess exactly like an attribute would.
    """
    tokens = _title_words(title)
    if not tokens:
        return []
    found: list[tuple[int, str]] = []
    for alias, material in _TITLE_MATERIAL_ALIASES.items():
        parts = _title_words(alias)
        for i in range(len(tokens) - len(parts) + 1):
            if tokens[i:i + len(parts)] == parts:
                if material not in {m for _, m in found}:
                    found.append((i, material))
                break
    return [m for _, m in sorted(found)]


def materials_from_attributes(item: Mapping[str, Any]) -> list[str]:
    """Materials named in the seller's attributes, in the order the seller wrote them."""
    found: list[tuple[int, str]] = []
    for title, value, _unit in _iter_attributes(item):
        if any(k in title for k in ("جنس", "متریال", "material")):
            low = value.lower()
            for alias, material in _MATERIAL_ALIASES.items():
                pos = low.find(alias)
                if pos >= 0 and material not in {m for _, m in found}:
                    found.append((pos, material))
    return [m for _, m in sorted(found)]


def item_to_row(raw_item: Mapping[str, Any], *, target_category: str | None = None,
                use_packaging_dimensions: bool = False, price_unit: str = PRICE_UNIT) -> dict[str, Any]:
    """One Basalam product object (either dialect) → the mapping ``normalize_row`` reads.

    ``price_unit`` is stamped on the row as ``currency``; the contract converts
    rial to toman (``price // 10``) and records ``price_converted_from_rial``.
    """
    if price_unit not in PRICE_UNITS:
        raise ValueError(f"price_unit must be one of {PRICE_UNITS}, got {price_unit!r}")
    item = _unwrap(raw_item)
    product_id = str(item.get("id") or item.get("product_id") or "").strip()
    vendor_identifier, vendor_title = _vendor(item)
    chain = _category_chain(item)
    label = chain[0] if chain else _category_label(item)
    image_url = _photo_url(item)
    row: dict[str, Any] = {
        "source_product_id": product_id,
        "title_fa": item.get("title") or item.get("name") or "",
        "category": label,
        "feed_category": label,
        "category_chain": chain,
        "target_category": target_category,
        "price": _price(item),
        "currency": price_unit,
        "image_url": image_url,
        "seller_link": _seller_link(item, vendor_identifier, product_id),
        "seller_name": vendor_title,
        "vendor_identifier": vendor_identifier,
        "description": item.get("summary") or item.get("description") or "",
        "available": _available(item),
        "materials": materials_from_attributes(item) or materials_from_title(
            str(item.get("title") or item.get("name") or "")),
        "basalam_category_id": _category_id(item),
        "sales_count": item.get("sales_count"),
        "rating": item.get("rating"),
        "has_variation": bool(item.get("has_variation")),
    }
    if not image_url:
        row["image_raw"] = _photo_raw(item)
    row["seller_category"] = seller_category(row)
    weight = _weight_g(item)
    if weight is not None:
        row["weight_g"] = weight
    if item.get("is_wholesale") is True:
        row["wholesale"] = True
    price = row["price"]
    price_toman = (price // 10 if price_unit == "rial" else price) if isinstance(price, int) else None
    scope = off_scope_reason(row["title_fa"], target_category or row["seller_category"], row["basalam_category_id"],
                             vendor_identifier=vendor_identifier, weight_g=weight, price_toman=price_toman,
                             wholesale=row.get("wholesale", False))
    if scope:
        row["off_scope"] = scope
    dims = dimensions_from_attributes(item)
    if dims:
        row.update(dims)
        row["dimensions_source"] = "attributes"
    elif use_packaging_dimensions and isinstance(item.get("packaging_dimensions"), Mapping):
        parsed = parse_dimensions(item["packaging_dimensions"])
        if parsed:
            row["width_cm"], row["depth_cm"], row["height_cm"] = parsed
            row["dimensions_source"] = "packaging"
    return row


# --------------------------------------------------------------------- crawl

def seller_category(row: Mapping[str, Any]) -> str | None:
    """The taxonomy category the *seller's* labelling maps to, or ``None``.

    Reads the category chain (leaf → root), the flat ``categoryTitle`` and
    finally Basalam's numeric leaf id (:data:`BASALAM_CATEGORY_IDS`).
    """
    for label in [*(row.get("category_chain") or []), row.get("feed_category"), row.get("category")]:
        mapped = map_category(label)
        if mapped:
            return mapped
    cid = to_int(row.get("basalam_category_id")) if row.get("basalam_category_id") is not None else None
    if cid is not None:
        return BASALAM_CATEGORY_IDS.get(cid)
    return None


def resolve_category(row: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    """``(category, candidates)`` for an adapter row.

    ``category`` is what the row is *filed under before the picture is seen*:
    the seller's category when it maps, else the query's target. ``candidates``
    is every category the two signals name (1 or 2 entries, seller first).
    With two candidates the pipeline lets ``detected_category`` pick — that
    is the P4-ب·2e fix for armchairs filed under «مبل» and TV stands under
    «میز» — and still excludes a row whose picture matches neither.
    """
    seller = seller_category(row)
    target = row.get("target_category") or None
    candidates = [c for c in (seller, target) if c]
    candidates = list(dict.fromkeys(candidates))
    return (candidates[0] if candidates else None), candidates


def _pick_category(row: dict[str, Any], _mapper: Callable[[Any], str | None] | None = None) -> str | None:
    """Backward-compatible wrapper: the filed category only (see :func:`resolve_category`)."""
    return resolve_category(row)[0]


def _stamp_category(row: dict[str, Any]) -> dict[str, Any]:
    row["category"], row["category_candidates"] = resolve_category(row)
    return row


def iter_search(client: BasalamClient, *, queries: Mapping[str, list[str]] | None = None,
                rows: int = 48, max_per_query: int = 200, max_pages: int = 20,
                vendor_identifier: str | None = None, details: bool = False,
                use_packaging_dimensions: bool = False, price_unit: str = PRICE_UNIT,
                on_raw: Callable[[str, Any], None] | None = None) -> Iterator[dict[str, Any]]:
    """Yield importer rows for every (category, query) pair, de-duplicated by product id.

    ``details=True`` additionally fetches ``GET /v1/products/{id}`` (needs a
    token) for attributes, availability and the full description.
    """
    plan = queries or CATEGORY_QUERIES
    seen: set[str] = set()
    for category, terms in plan.items():
        for term in terms:
            fetched = 0
            for page in range(max_pages):
                if fetched >= max_per_query:
                    break
                payload = client.search(term, rows=rows, start=page * rows, vendor_identifier=vendor_identifier)
                if on_raw is not None:
                    on_raw(term, payload)
                items = find_product_list(payload)
                if not items:
                    break
                for raw_item in items:
                    if fetched >= max_per_query:
                        break
                    item = _unwrap(raw_item)
                    product_id = str(item.get("id") or "")
                    if not product_id or product_id in seen:
                        continue
                    seen.add(product_id)
                    fetched += 1
                    if details:
                        try:
                            detail = client.product(product_id)
                            if isinstance(detail, Mapping):
                                item = {**item, **_unwrap(detail)}
                        except BasalamError as exc:
                            logger.warning("basalam detail fetch failed for %s: %s", product_id, exc)
                    row = item_to_row(item, target_category=category,
                                      use_packaging_dimensions=use_packaging_dimensions, price_unit=price_unit)
                    _stamp_category(row)
                    row["query"] = term
                    yield row
                if len(items) < rows:
                    break
                time.sleep(client.pause_seconds)


def iter_vendor(client: BasalamClient, vendor_id: int | str, *, per_page: int = 50, max_pages: int = 40,
                default_category: str | None = None, use_packaging_dimensions: bool = False,
                price_unit: str = PRICE_UNIT,
                on_raw: Callable[[str, Any], None] | None = None) -> Iterator[dict[str, Any]]:
    """Yield every product of one vendor (token with ``vendor.product.read``)."""
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        payload = client.vendor_products(vendor_id, page=page, per_page=per_page)
        if on_raw is not None:
            on_raw(f"vendor:{vendor_id}:page{page}", payload)
        items = find_product_list(payload)
        if not items:
            break
        for raw_item in items:
            item = _unwrap(raw_item)
            product_id = str(item.get("id") or "")
            if not product_id or product_id in seen:
                continue
            seen.add(product_id)
            row = item_to_row(item, target_category=default_category,
                              use_packaging_dimensions=use_packaging_dimensions, price_unit=price_unit)
            _stamp_category(row)
            yield row
        if len(items) < per_page:
            break
        time.sleep(client.pause_seconds)
