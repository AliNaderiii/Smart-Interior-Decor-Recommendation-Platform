"""Seller-feed importer (P4-ب item 2): contract, adapters, pipeline, CLI.

No network anywhere: images are served from an in-process fetcher, the
Basalam gateway is an ``httpx.MockTransport`` replaying the recorded-shape
fixture, and the vision provider is the deterministic mock (its
``detected_category`` comes from the image filename, which is exactly what
lets these tests stage an image↔category disagreement on purpose).
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import delete, select

from ai import catalog_integrity as policy
from app.models.audit_log import ACTION_CATALOG_IMPORT, AuditLog
from app.models.product import Product
from app.services.catalog_import import contract, images, pipeline
from app.services.catalog_import.adapters import basalam
from app.services.catalog_import.adapters import file as file_adapter

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = "feed:test-seller"


# --------------------------------------------------------------------- helpers

def _png(seed=(120, 80, 40), size=(64, 48)) -> bytes:
    """A small *textured* PNG — flat colours all share one perceptual hash."""
    r, g, b = seed
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = ((x * (r + 7)) % 256, (y * (g + 5)) % 256, ((x * y) * (b + 11)) % 256)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _phash(data: bytes) -> str:
    from app.core.uploads import perceptual_hash

    with Image.open(io.BytesIO(data)) as im:
        return perceptual_hash(im)


class FakeFetcher:
    """In-memory image server: ``url -> bytes``; anything else is unreachable."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.calls: list[str] = []

    def __call__(self, url: str) -> images.AcquiredImage:
        self.calls.append(url)
        data = self.files.get(url)
        if data is None:
            raise images.ImageUnavailable("image_unreachable", "404")
        return images.AcquiredImage(
            data=data, content_type="image/png", extension=".png", phash=_phash(data),
            width=64, height=48, original_url=url,
        )


class FakeLink:
    def __init__(self, ok=True, classification="ok"):
        self.ok, self.classification = ok, classification


def _row(**overrides) -> dict:
    base = {
        "source_product_id": f"SKU-{uuid.uuid4().hex[:6]}",
        "title_fa": "مبل راحتی سه‌نفره مدل آرتا",
        "title_en": "Arta 3-seat sofa",
        "category": "مبل",
        "price_toman": "48,500,000",
        "image_url": "https://cdn.example-seller.ir/p/sofa-modern-fabric.png",
        "seller_link": "https://example-seller.ir/product/arta-3-seat-sofa",
        "width_cm": 215, "depth_cm": 92, "height_cm": 84,
        "colors": "#C9B79C|#3B3B3B", "styles": "modern|minimal", "materials": "fabric|wood",
        "patterns": "solid", "description": "مبل سه‌نفره با پارچه کتان",
    }
    base.update(overrides)
    return base


@pytest.fixture()
def fetcher():
    return FakeFetcher({
        "https://cdn.example-seller.ir/p/sofa-modern-fabric.png": _png((120, 80, 40)),
        "https://cdn.example-seller.ir/p/rug-persian-red.png": _png((150, 20, 20)),
        "https://cdn.example-seller.ir/p/sofa-second.png": _png((20, 60, 120)),
        "https://cdn.example-seller.ir/p/chandelier-metal-black.png": _png((10, 10, 10)),
    })


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from app.db.session import SessionLocal

    with SessionLocal() as s:
        s.execute(delete(Product).where(Product.source.in_([SOURCE, "feed:other", basalam.SOURCE])))
        s.commit()


def _import(db, rows, *, fetcher, options=None, **kw):
    from ai.feature_extractor import FeatureExtractor

    return pipeline.import_rows(
        db, rows, source=SOURCE, options=options or pipeline.ImportOptions(dry_run=False, image_mode="rehost"),
        extractor=FeatureExtractor("mock"), fetch_image=fetcher, check_link=lambda url: FakeLink(), **kw,
    )


# ------------------------------------------------------------------- contract

class TestContract:
    def test_persian_digits_and_separators(self):
        assert contract.to_int("۳۴٬۰۰۰٬۰۰۰") == 34_000_000
        assert contract.to_int("48,500,000 تومان") == 48_500_000
        assert contract.to_int("85 cm") == 85
        assert contract.to_int("") is None
        assert contract.to_int("abc") is None
        assert contract.to_int(0, allow_zero=False) is None
        assert contract.to_int(-5) is None

    def test_category_mapping_accepts_persian_labels_and_ids(self):
        assert contract.map_category("مبل") == "sofa"
        assert contract.map_category("Rug") == "rug"
        assert contract.map_category("میز جلومبلی") == "coffee_table"
        assert contract.map_category("لوستر") == "lighting"
        assert contract.map_category("مبل تک نفره") == "chair"
        assert contract.map_category("بوفه") == "storage"
        assert contract.map_category("کوسن") == "decor"
        assert contract.map_category("کیف چرم") is None
        assert contract.map_category("chaise longue", {"chaise longue": "sofa"}) == "sofa"

    def test_dimensions_parse_string_and_mapping(self):
        assert contract.parse_dimensions("220x95x85") == (220, 95, 85)
        assert contract.parse_dimensions("۲۲۰ در ۹۵ در ۸۵") == (220, 95, 85)
        assert contract.parse_dimensions("300 × 200") == (300, 200, 0)
        assert contract.parse_dimensions({"length": 220, "width": 95, "height": 85}) == (220, 95, 85)
        assert contract.parse_dimensions("large") is None

    def test_normalize_happy_path(self):
        row = contract.normalize_row(_row(), source=SOURCE, now=datetime(2026, 9, 9, tzinfo=timezone.utc))
        assert row.category == "sofa"
        assert row.price_toman == 48_500_000
        assert (row.width_cm, row.depth_cm, row.height_cm) == (215, 92, 84)
        assert row.colors == ["#C9B79C", "#3B3B3B"]
        assert row.styles == ["modern", "minimal"]
        assert row.materials == ["fabric", "wood"]
        assert row.price_checked_at == datetime(2026, 9, 9, tzinfo=timezone.utc)
        assert row.warnings == []

    def test_normalize_rejects_with_stable_codes(self):
        with pytest.raises(contract.RowRejected) as exc:
            contract.normalize_row(
                {"title_fa": "", "category": "کیف", "price_toman": "0", "image_url": "ftp://x/y.jpg"},
                source=SOURCE,
            )
        assert set(exc.value.codes) == {
            "source_product_id_missing", "title_fa_missing", "category_unmapped",
            "price_invalid", "image_url_invalid",
        }

    def test_rejection_carries_what_was_seen(self):
        """The report must explain *why* without the raw dump (P4-ب-2c: 60× image_url_invalid told nothing)."""
        with pytest.raises(contract.RowRejected) as exc:
            contract.normalize_row(_row(image_url="", image_raw="photo={'MEDIUM': None}"), source=SOURCE)
        assert exc.value.codes == ["image_url_invalid"]
        assert exc.value.details == ["image_url=missing image_raw=photo={'MEDIUM': None}"]
        assert exc.value.title_fa == "مبل راحتی سه‌نفره مدل آرتا"

        with pytest.raises(contract.RowRejected) as exc:
            contract.normalize_row(_row(image_url="//cdn.x.ir/a.jpg", price_toman="0", category="کیف"), source=SOURCE)
        assert set(exc.value.codes) == {"image_url_invalid", "price_invalid", "category_unmapped"}
        joined = " | ".join(exc.value.details)
        assert "category=کیف" in joined and "price_toman=0" in joined
        assert "image_url=" in joined and "value=//cdn.x.ir/a.jpg" in joined

    def test_normalize_never_guesses_values(self):
        """Unknown tags are dropped and reported; a rial price is converted and reported."""
        row = contract.normalize_row(
            _row(price_toman="", price="485000000", currency="rial", styles="modern|futuristic",
                 colors="#FFFFFF|red", width_cm="", depth_cm=None, height_cm="n/a"),
            source=SOURCE,
        )
        assert row.price_toman == 48_500_000
        assert row.styles == ["modern"]
        assert row.colors == ["#FFFFFF"]
        assert (row.width_cm, row.depth_cm, row.height_cm) == (0, 0, 0)
        assert "price_converted_from_rial" in row.warnings
        assert any(w.startswith("unknown_style_dropped:futuristic") for w in row.warnings)
        assert any(w.startswith("invalid_color_dropped:red") for w in row.warnings)

    def test_html_is_stripped_from_seller_text(self):
        row = contract.normalize_row(
            _row(title_fa="<img src=x onerror=alert(1)>مبل راحتی", description="<script>x</script>خوب"),
            source=SOURCE,
        )
        assert row.title_fa == "مبل راحتی"
        assert row.description == "خوب"

    def test_unsafe_seller_link_is_dropped_not_stored(self):
        row = contract.normalize_row(_row(seller_link="http://127.0.0.1/admin"), source=SOURCE)
        assert row.seller_link == ""
        assert "seller_link_invalid_dropped" in row.warnings

    def test_seller_source_slug_rules(self):
        assert contract.seller_source("Nilper") == "feed:nilper"
        with pytest.raises(ValueError):
            contract.seller_source("bad slug!")
        with pytest.raises(ValueError):
            contract.seller_source("x" * 40)


# --------------------------------------------------------------- file adapter

class TestFileAdapter:
    def test_template_round_trips_through_normaliser(self):
        rows = list(file_adapter.iter_csv(file_adapter.template_csv()))
        assert len(rows) == 1
        row = contract.normalize_row(rows[0], source=SOURCE)
        assert row.source_product_id == "NLP-1042"
        assert row.category == "sofa"
        assert row.price_toman == 48_500_000

    def test_persian_headers_and_bom(self):
        csv_text = "\ufeffکد,عنوان,دسته,قیمت (ریال),تصویر,لینک محصول,ابعاد\n" \
                   "A1,فرش دستباف تبریز,فرش,۱٬۸۵۰٬۰۰۰٬۰۰۰,https://cdn.x.ir/a.jpg,https://x.ir/product/a,300x200\n"
        rows = list(file_adapter.iter_csv(csv_text))
        assert rows[0]["source_product_id"] == "A1"
        assert rows[0]["currency"] == "rial"
        row = contract.normalize_row(rows[0], source=SOURCE)
        assert row.category == "rug"
        assert row.price_toman == 185_000_000
        assert (row.width_cm, row.depth_cm) == (300, 200)

    def test_json_items_and_realistic_dataset_keys(self, tmp_path):
        payload = {"items": [{
            "id": "R-1", "title_fa": "فرش مدرن طوسی", "title_en": "Grey rug", "category": "rug",
            "price_toman": 22_000_000, "image_url": "https://cdn.x.ir/r.jpg",
            "seller_link": "https://x.ir/product/r-1", "dimensions_cm": {"length": 300, "width": 200, "height": 1},
            "color_palette": ["#9E9E9E"], "style_tags": ["modern"], "material_tags": ["fabric"],
            "description_for_embedding": "a grey modern rug",
        }]}
        p = tmp_path / "feed.json"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        rows = list(file_adapter.iter_file(p))
        row = contract.normalize_row(rows[0], source=SOURCE)
        assert row.styles == ["modern"] and row.materials == ["fabric"] and row.colors == ["#9E9E9E"]
        assert (row.width_cm, row.depth_cm, row.height_cm) == (300, 200, 1)

    def test_unknown_suffix_rejected(self, tmp_path):
        p = tmp_path / "feed.xlsx"
        p.write_bytes(b"PK")
        with pytest.raises(ValueError):
            list(file_adapter.iter_file(p))


# ------------------------------------------------------------ basalam adapter

def _basalam_transport(fixture: dict, *, calls: list | None = None, status: int = 200,
                       key: str = "openapi_raw_data"):
    """Fake gateway: ``fixture[key]`` is the product list (SDK dialect by default, ``products`` = live)."""
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append((request.method, request.url.path, request.headers.get("authorization"),
                          json.loads(request.content or b"null")))
        if status != 200:
            return httpx.Response(status, json={"message": "nope"})
        if request.url.path == "/v1/products/search":
            body = json.loads(request.content)
            return httpx.Response(200, json=fixture if body.get("start", 0) == 0 else {**fixture, key: []})
        if request.url.path.startswith("/v1/products/"):
            pid = request.url.path.rsplit("/", 1)[-1]
            item = next(i for i in fixture[key] if str(i["id"]) == pid)
            return httpx.Response(200, json={**item, "description": "توضیح کامل"})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class TestBasalamAdapter:
    @pytest.fixture()
    def fixture(self):
        return json.loads((FIXTURES / "basalam_search_sample.json").read_text(encoding="utf-8"))

    def test_find_product_list_handles_every_known_envelope(self, fixture):
        items = fixture["openapi_raw_data"]
        assert basalam.find_product_list(items) == items
        assert basalam.find_product_list(fixture) == items
        assert basalam.find_product_list({"data": items}) == items
        assert basalam.find_product_list({"data": {"products": items}}) == items
        assert basalam.find_product_list({"hits": {"hits": [{"_source": items[0]}]}}) == [{"_source": items[0]}]
        assert basalam.find_product_list({"meta": {"count": 0}, "data": []}) == []

    def test_item_to_row_maps_fields_honestly(self, fixture):
        sofa = basalam.item_to_row(fixture["openapi_raw_data"][0], target_category="sofa")
        assert sofa["source_product_id"] == "24223620"
        assert (sofa["price"], sofa["currency"]) == (340_000_000, "rial")  # price, never primary_price; rial
        assert contract.normalize_row(sofa, source=basalam.SOURCE).price_toman == 34_000_000
        assert sofa["image_url"].endswith("scarlet-sofa_lg.jpg")
        assert sofa["seller_link"] == "https://basalam.com/mobl-ara/product/24223620"
        assert sofa["seller_name"] == "مبل آرا"
        assert sofa["category_chain"] == ["مبل راحتی", "مبلمان منزل"]
        # explicit attributes win: 220 / 90 / 0.85 m → 85 cm
        assert (sofa["width_cm"], sofa["depth_cm"], sofa["height_cm"]) == (220, 90, 85)
        assert sofa["dimensions_source"] == "attributes"
        assert sofa["materials"] == ["fabric", "wood"]
        assert sofa["available"] is True

        rug = basalam.item_to_row(fixture["openapi_raw_data"][1], target_category="rug")
        assert (rug["width_cm"], rug["depth_cm"], rug["height_cm"]) == (300, 200, 0)
        assert rug["materials"] == ["fabric"]

        cushion = basalam.item_to_row(fixture["openapi_raw_data"][2], target_category="decor")
        assert cushion["available"] is False

        lamp = basalam.item_to_row(fixture["openapi_raw_data"][3], target_category="lighting")
        assert lamp["seller_link"] == "https://basalam.com/noor-light/product/26000002"
        assert "width_cm" not in lamp  # no attributes, packaging not opted in

    def test_packaging_dimensions_only_when_opted_in(self, fixture):
        lamp = fixture["openapi_raw_data"][3]
        lamp = {**lamp, "packaging_dimensions": {"height": 60, "width": 60, "length": 60}}
        assert "width_cm" not in basalam.item_to_row(lamp)
        row = basalam.item_to_row(lamp, use_packaging_dimensions=True)
        assert (row["width_cm"], row["depth_cm"], row["height_cm"]) == (60, 60, 60)
        assert row["dimensions_source"] == "packaging"

    def test_search_is_public_and_details_need_a_token(self, fixture):
        calls: list = []
        with basalam.BasalamClient(transport=_basalam_transport(fixture, calls=calls), pause_seconds=0) as client:
            rows = list(basalam.iter_search(client, queries={"sofa": ["مبل راحتی"]}, rows=48))
            assert calls[0][:3] == ("POST", "/v1/products/search", None)
            assert calls[0][3] == {"q": "مبل راحتی", "rows": 48, "start": 0}
            with pytest.raises(basalam.BasalamError, match="token"):
                client.product(24223620)
        ids = [r["source_product_id"] for r in rows]
        assert ids == ["24223620", "25410382", "26000001", "26000002", "26000003"]
        # seller category maps when it can; the unmappable bag falls back to the query's category
        by_id = {r["source_product_id"]: r for r in rows}
        assert by_id["24223620"]["category"] == "sofa"
        assert by_id["25410382"]["category"] == "rug"
        assert by_id["26000002"]["category"] == "lighting"
        assert by_id["26000003"]["category"] == "sofa"        # target category — vision must confirm
        assert by_id["26000003"]["feed_category"] == "کیف چرم"  # provenance keeps the seller's label

    def test_details_merge_with_token(self, fixture):
        calls: list = []
        with basalam.BasalamClient(token="t0k", transport=_basalam_transport(fixture, calls=calls),
                                   pause_seconds=0) as client:
            rows = list(basalam.iter_search(client, queries={"sofa": ["مبل"]}, details=True, max_per_query=1))
        assert rows[0]["description"] == "مبل سه نفره با پارچه مخمل و پایه چوب راش"  # summary wins over description
        detail_calls = [c for c in calls if c[1] == "/v1/products/24223620"]
        assert detail_calls and detail_calls[0][2] == "Bearer t0k"

    def test_gateway_errors_are_clean_failures(self, fixture):
        with basalam.BasalamClient(transport=_basalam_transport(fixture, status=503), retries=2,
                                   pause_seconds=0) as client:
            with pytest.raises(basalam.BasalamError, match="failed after 2 attempts"):
                client.search("مبل")
        with basalam.BasalamClient(token="x", transport=_basalam_transport(fixture, status=403),
                                   pause_seconds=0) as client:
            with pytest.raises(basalam.BasalamError, match="403"):
                client.product(1)

    def test_query_plan_covers_every_taxonomy_category(self):
        from ai import taxonomy as tax

        assert set(basalam.CATEGORY_QUERIES) == set(tax.categories())

    # ---- the live search dialect (P4-ب-2c: first live run rejected 60/60 as image_url_invalid)

    @pytest.fixture()
    def live(self):
        return json.loads((FIXTURES / "basalam_search_live_shape.json").read_text(encoding="utf-8"))

    def test_live_envelope_and_upper_case_photo_keys(self, live):
        items = basalam.find_product_list(live)
        assert [i["id"] for i in items] == [28107984, 41448876, 42115964, 44587637, 13441005]

        rug = basalam.item_to_row(items[0], target_category="rug")
        assert rug["source_product_id"] == "28107984"
        assert rug["title_fa"].startswith("فرش دستباف یک متری")               # `name`, not `title`
        assert rug["image_url"].endswith("hunting-rug.jpg_512X512X70.jpg")   # photo.MEDIUM
        assert "vendor-avatar" not in rug["image_url"]                       # vendor.photo is never the product
        assert rug["seller_link"] == "https://basalam.com/gerehcarpetir/product/28107984"
        assert rug["seller_name"] == "فرش دستبافت گره"                        # vendor.name
        assert rug["category"] == rug["feed_category"] == "فرش دستباف"       # categoryTitle
        assert contract.map_category(rug["feed_category"]) == "rug"          # Basalam leaf title is a known alias
        assert rug["basalam_category_id"] == 299                             # new_categoryId
        assert rug["available"] is True and rug["has_variation"] is False
        assert "image_raw" not in rug

    def test_live_prices_are_rial_and_become_toman(self, live):
        items = basalam.find_product_list(live)
        rug = basalam.item_to_row(items[0], target_category="rug")
        assert (rug["price"], rug["currency"]) == (297_000_000, "rial")     # never primaryPrice
        assert "price_toman" not in rug                                       # the contract converts, once
        feed = contract.normalize_row(rug, source=basalam.SOURCE)
        assert feed.price_toman == 29_700_000                                 # what basalam.com shows
        assert "price_converted_from_rial" in feed.warnings

        # discounted product: price (what the buyer pays) < primaryPrice
        patina = basalam.item_to_row(items[1], target_category="rug")
        assert patina["price"] == 4_665_600
        assert contract.normalize_row(patina, source=basalam.SOURCE).price_toman == 466_560

        # operator override, stamped on the row
        assert basalam.item_to_row(items[0], price_unit="toman")["currency"] == "toman"
        with pytest.raises(ValueError, match="price_unit"):
            basalam.item_to_row(items[0], price_unit="dollar")

    def test_photo_shapes_seen_in_the_wild(self, live):
        items = basalam.find_product_list(live)
        # protocol-relative → https
        assert basalam.item_to_row(items[1])["image_url"].startswith("https://statics.example-basalam.test/")
        # mainPhoto {url}
        assert basalam.item_to_row(items[2])["image_url"].endswith("kilim.jpg_512X512X70.jpg")
        # nothing usable → empty URL + the raw value for the report
        empty = basalam.item_to_row(items[3])
        assert empty["image_url"] == ""
        assert "photo={'MEDIUM': None, 'SMALL': ''}" in empty["image_raw"]
        # size preference and case-insensitivity
        assert basalam._photo_url({"photo": {"small": "https://x.test/s.jpg", "LARGE": "https://x.test/l.jpg"}}) \
            == "https://x.test/l.jpg"
        assert basalam._photo_url({"photo": {"Original": "https://x.test/o.jpg", "md": "https://x.test/m.jpg"}}) \
            == "https://x.test/o.jpg"
        assert basalam._photo_url({"images": ["//x.test/a.jpg", "https://x.test/b.jpg"]}) == "https://x.test/a.jpg"
        assert basalam._photo_url({"photos": [{"lg": "https://x.test/p.jpg"}]}) == "https://x.test/p.jpg"
        assert basalam._photo_url({"photo": {"WEIRD": "https://x.test/w.jpg"}}) == "https://x.test/w.jpg"
        assert basalam._photo_url({"photo": "ftp://x.test/w.jpg"}) == ""
        assert basalam._photo_url({"vendor_photo": {"LARGE": "https://x.test/avatar.jpg"}}) == ""
        assert basalam._photo_url({}) == ""

    def test_live_availability_flags(self, live):
        items = basalam.find_product_list(live)
        assert basalam.item_to_row(items[4])["available"] is False          # IsAvailable false, stock 0
        assert basalam._available({"IsAvailable": True, "canAddToCart": False}) is False
        assert basalam._available({"status": {"id": 3790, "title": "ناموجود"}}) is False
        assert basalam._available({"status": {"id": 2976, "title": "در دسترس"}, "stock": 3}) is True

    def test_live_shape_through_iter_search(self, live):
        with basalam.BasalamClient(transport=_basalam_transport(live, key="products"),
                                   pause_seconds=0) as client:
            rows = list(basalam.iter_search(client, queries={"rug": ["فرش دستباف"]}, rows=48))
        by_id = {r["source_product_id"]: r for r in rows}
        assert set(by_id) == {"28107984", "41448876", "42115964", "44587637", "13441005"}
        assert all(r["category"] == "rug" for r in rows)                     # فرش دستباف/فرش ماشینی/گلیم all map
        assert by_id["28107984"]["query"] == "فرش دستباف"
        assert all(r["category_candidates"] == ["rug"] for r in rows)        # seller and query agree → one candidate

    # ---- P4-ب·2e (2026-09-11): the 6-category dry-run excluded 35 rows as
    # image_category_mismatch, most of them *correct* products under a wrong
    # label (armchairs filed under «مبل», TV stands under «میز»), and sent ~30
    # off-scope hits (park lamps, kids' chairs, book sets) to the vision API.

    def _hit(self, live, **overrides):
        item = dict(basalam.find_product_list(live)[0])
        item.update(overrides)
        return item

    def test_seller_and_query_disagreement_yields_two_candidates(self, live):
        # 46957138 live: query «مبل تک نفره» (chair), seller says «مبل» / 357 (sofa)
        armchair = self._hit(live, id=46957138, name="مبل تک نفره راحتی مدل لیانا", categoryTitle="مبل",
                             new_categoryId=357)
        row = basalam.item_to_row(armchair, target_category="chair")
        assert row["seller_category"] == "sofa"
        assert basalam.resolve_category(row) == ("sofa", ["sofa", "chair"])   # filed under the seller's label …
        # … and the pipeline lets the picture pick between the two (TestPipeline).

        # 23838782 live: query «میز تلویزیون» (storage), seller says «میز» / 358 (table)
        tv = self._hit(live, id=23838782, name="میز تلویزیون مدرن کد 65", categoryTitle="میز", new_categoryId=358)
        row = basalam.item_to_row(tv, target_category="storage")
        assert basalam.resolve_category(row) == ("coffee_table", ["coffee_table", "storage"])

        # agreement → exactly one candidate; unmappable seller label → the query alone
        sofa = self._hit(live, name="مبل راحتی اسکارلت", categoryTitle="مبل", new_categoryId=357)
        assert basalam.resolve_category(basalam.item_to_row(sofa, target_category="sofa")) == ("sofa", ["sofa"])
        bag = self._hit(live, name="کیف چرم", categoryTitle="کیف چرم", new_categoryId=None)
        assert basalam.resolve_category(basalam.item_to_row(bag, target_category="sofa")) == ("sofa", ["sofa"])
        assert basalam.resolve_category(basalam.item_to_row(bag)) == (None, [])

    def test_basalam_numeric_leaf_is_a_second_reading_of_the_seller_label(self, live):
        # «کمد، کتابخانه، بوفه» (356) — a title the alias table did not know before 2e
        shelf = self._hit(live, name="کتابخانه ایستاده مدل آرتا", categoryTitle="عنوان ناشناخته", new_categoryId=356)
        row = basalam.item_to_row(shelf, target_category="storage")
        assert row["seller_category"] == "storage"
        assert basalam.resolve_category(row) == ("storage", ["storage"])
        # 297 «تابلو فرش» is wall art, not a floor rug — and its title says so too
        tableau = self._hit(live, name="تابلو فرش منظره", categoryTitle="تابلو فرش", new_categoryId=297)
        row = basalam.item_to_row(tableau, target_category="rug")
        assert row["seller_category"] == "decor" and row["off_scope"] == "title:تابلو"

    @pytest.mark.parametrize("title,category,cid,expected", [
        ("چراغ پارکی و حیاطی مدل سنگی", "lighting", 360, "title:پارکی"),
        ("لامپ مادون قرمز فیزیوتراپی", "lighting", None, "title:مادون قرمز"),
        ("صندلی ماشین کودک", "chair", 355, "title:کودک"),
        ("مبل کودک تختخوابشو", "sofa", 357, "title:کودک"),
        ("کتاب خانه درختی جلد ۱", "storage", 791, "basalam_category:791 books"),
        ("شلف حمام و دستشویی", "storage", 352, "basalam_category:352 bathroom-accessories"),
        ("صندلی راک و میز مینیاتوری کد17-ماکت", "chair", 290, "title:ماکت"),
        ("گلیم دیواری 20*20", "rug", None, "title:دیواری"),
        # P4-ب·2f — the 2026-09-11 live pilot / dry-run rows
        ("صندلی راحتی تاشو مدل راحت نشین برند (F.I.T) مناسب خانه پارک طبیعت", "chair", 355, "title:تاشو"),  # 15184851
        ("صندلی راحتی پنج حالته سفارشی رنگ بندی طوسی کاور رایگان ( پس کرایه )", "chair", 355, "title:حالته"),  # 6884086
        ("صندلی راحتی با کفی پارچه نیلپر مدل NOCF515X", "chair", 355, None),  # 58082825: an office chair — the word is not in its title (see vendor/desk-chair terms below)
        ("صندلی اداری مدیریتی نیلپر", "chair", 355, "title:اداری"),
        ("صندلی گیمینگ دی ایکس ریسر", "chair", 355, "title:گیمینگ"),
        ("صندلی چوبی روستیک برای نهار خوری", "chair", 358, "title:نهار خوری"),   # 17937965: dining, spelled with a space
        ("صندلی ناهار خوری فایبر پایه فلزی (پسکرایه)", "chair", 355, "title:ناهار خوری"),  # 9216895
        ("آباژور (چراغ خواب)فوتبالی کریستیانو رونالدو", "lighting", 360, "title:فوتبالی"),  # 10071814
        ("کاناپه تخت شو طرح السا با تشک های متصل", "sofa", 357, "title:السا"),      # 20158371 (title rule, any vendor)
        ("مبل کودک طرح باب اسفنجی", "sofa", 7690, "title:کودک"),
        ("عروسک اسفنجی کوسنی", "decor", 528, "basalam_category:528 girls-toys"),
        # legitimate rows the same words must NOT catch
        ("فرش ماشینی ۱۲۰۰ شانه طرح باغی", "rug", 300, None),        # «ماشینی» ≠ «ماشین»; «باغی» is a carpet design
        ("شلف دیواری چوبی سه طبقه", "storage", 291, None),           # «دیواری» is off-scope for rugs only
        ("میز تلویزیون دیواری رنگ دلخواه", "storage", 358, None),
        ("مبل تک نفره راحتی", "chair", 355, None),
        ("صندلی مدرن کافه ای فلزی برند آلوارس", "chair", 355, None),  # 52820553: «فضای باز» in the *description* only — dropped from the list
        ("مبل تختخواب شو دو نفره", "sofa", 3773, None),               # a sofa-bed for adults is a sofa
        ("", "sofa", None, None),
    ])
    def test_off_scope_is_explicit_whole_word_and_per_category(self, title, category, cid, expected):
        assert basalam.off_scope_reason(title, category, cid) == expected

    # ---- P4-ب·2f: replica guard, kids'-furniture vendors, materials from the title

    def test_weight_guard_catches_the_figurine_and_spares_the_buffet(self, live):
        """14597663 (2026-09-11 live pilot): a 20 g «صندلی راحتی دکوری کوچک» under
        «مجسمه و تندیس» (295) reached ``chair`` verified because the picture IS a
        chair. 14102454 — a 150 cm buffet, 1.5 kg, same leaf — is real."""
        figurine = self._hit(live, id=14597663, name="صندلی راحتی دکوری کوچک چوبی ماهو", categoryTitle="مجسمه و تندیس",
                             new_categoryId=295, weight=20, price=500000.0)
        row = basalam.item_to_row(figurine, target_category="chair")
        assert row["weight_g"] == 20 and row["off_scope"] == "miniature:weight=20g"
        buffet = self._hit(live, id=14102454, name="بوفه و دکوری", categoryTitle="مجسمه و تندیس",
                           new_categoryId=295, weight=1500, price=666800000.0)
        row = basalam.item_to_row(buffet, target_category="storage")
        assert "off_scope" not in row and row["weight_g"] == 1500
        # a 295 hit with no weight but a replica word in the title
        assert basalam.off_scope_reason("مبل فیگور دکوری", "sofa", 295) == "miniature:295 sculpture-and-statue title"
        # decor is exempt from the weight rule (a cushion cover weighs 150 g, a sticker 20 g)
        assert basalam.off_scope_reason("کوسن مخمل", "decor", 305, weight_g=20) is None
        # no weight → no verdict from the weight rule, and a real chair under 355 is untouched
        assert basalam.off_scope_reason("صندلی چوبی لهستانی", "chair", 355, weight_g=None) is None
        assert basalam.off_scope_reason("صندلی چوبی لهستانی", "chair", 355, weight_g="۶۰۰۰") is None
        assert basalam.MINIATURE_MAX_WEIGHT_G == 100

    # ---- P4-ب·2g: a placeholder weight is not a measurement

    @pytest.mark.parametrize("pid, title, category, cid, grams", [
        (25744387, "مبل تک نفره دسته چوبی افسون تمام چوب", "sofa", 357, 2),
        (5517592, "مبل راحتی پاریس ویژه جهیزیه", "sofa", 357, 1),
        (4506396, "مبل راحتی اسکارلت", "sofa", 357, 1),
        (2448551, "مبل تختخوابشو 140", "sofa", 357, 1),
        (925069, "مبل ال دسته دوبل", "sofa", 357, 1),
        (702819, "مبل ال کنج", "sofa", 357, 1),
        (762717, "مبل ال 5نفره", "sofa", 357, 1),
        (27740063, "کاناپه چستر سناتور", "sofa", 357, 1),
        (37977395, "میز جلومبلی کلاسیک", "coffee_table", 358, 1),
        (10098793, "شلف دیواری آیراد چهار طبقه", "storage", 291, 1),
    ])
    def test_placeholder_weights_are_unknown_not_evidence(self, live, pid, title, category, cid, grams):
        """2026-09-11 rehearsal of 2f: these ten real, full-size pieces were skipped
        as ``miniature:weight=1g`` / ``2g`` — sellers who ship by freight leave the
        shipping weight at a placeholder (25744387's own product page says
        ``net_weight: 2``). Below ``MINIATURE_MIN_WEIGHT_G`` the number is unknown:
        no verdict, but it still travels on the row for the audit trail."""
        assert basalam.off_scope_reason(title, category, cid, weight_g=grams) is None
        hit = self._hit(live, id=pid, name=title, new_categoryId=cid, weight=grams)
        row = basalam.item_to_row(hit, target_category=category)
        assert "off_scope" not in row
        assert row["weight_g"] == grams

    def test_weight_guard_fires_only_inside_the_measured_band(self):
        """The floor spares placeholders; the figurine (20 g) is still caught, and
        the band edges are exact so a future tweak shows up here first."""
        assert basalam.MINIATURE_MIN_WEIGHT_G == 10
        assert 0 < basalam.MINIATURE_MIN_WEIGHT_G < basalam.MINIATURE_MAX_WEIGHT_G
        verdict = "miniature:weight={}g"
        for grams in (1, 2, 5, 9, 0, "۰", "۱"):
            assert basalam.off_scope_reason("مبل راحتی", "sofa", 357, weight_g=grams) is None, grams
        for grams in (10, 20, 50, 99, "۲۰"):
            expected = verdict.format(contract.to_int(grams))
            assert basalam.off_scope_reason("مبل راحتی", "sofa", 357, weight_g=grams) == expected, grams
            assert basalam.off_scope_reason("صندلی راک چوبی", "chair", 355, weight_g=grams) == expected, grams
        for grams in (100, 150, 1500, 70000):
            assert basalam.off_scope_reason("مبل راحتی", "sofa", 357, weight_g=grams) is None, grams
        # decor stays exempt at every weight; the title rule under 295 does not need a weight
        assert basalam.off_scope_reason("کوسن مخمل", "decor", 305, weight_g=20) is None
        assert basalam.off_scope_reason("مبل فیگور دکوری", "sofa", 295, weight_g=1) == "miniature:295 sculpture-and-statue title"

    # ---- P4-ب·2h: the picture cannot see scale — price can

    def test_price_floor_catches_the_heavy_replica_under_the_sculpture_leaf(self, live):
        """24617673 (2026-09-11 rehearsal): «صندلی راک چوبی دکوری» under «مجسمه و
        تندیس» (295), a solid 800 g, 20×16.5×28 cm, 495 000 toman — passed the
        weight rule, «دکوری» alone is not a replica word, and the picture IS a
        rocking chair, so it was verified as ``chair``. No real chair costs less
        than the integrity band's floor; under the replica-prone leaf that is a
        verdict. The 1.5 kg buffet (14102454, 66.7 M toman) stays real."""
        rocker = self._hit(live, id=24617673, name="صندلی راک چوبی دکوری ", categoryTitle="مجسمه و تندیس",
                           new_categoryId=295, weight=800, price=4950000.0)
        row = basalam.item_to_row(rocker, target_category="chair")
        assert row["off_scope"] == "miniature:295 price=495000t<1000000t"
        assert row["price"] == 4950000 and row["currency"] == "rial" and row["weight_g"] == 800
        buffet = self._hit(live, id=14102454, name="بوفه و دکوری با مرغوبترین چوب و اکسسوری منزل",
                           categoryTitle="مجسمه و تندیس", new_categoryId=295, weight=1500, price=666790000.0)
        assert "off_scope" not in basalam.item_to_row(buffet, target_category="storage")
        # the floor is the integrity band's lower edge — one notion of "cheaper than any real X"
        assert basalam.REPLICA_PRICE_FLOOR_TOMAN == {
            c: policy.PRICE_BANDS_TOMAN[c][0] for c in ("chair", "coffee_table", "lighting", "sofa", "storage")}
        assert (basalam.off_scope_reason("مبل راحتی دکوری", "sofa", 295, price_toman=4_999_999)
                == "miniature:295 price=4999999t<5000000t")
        assert basalam.off_scope_reason("مبل راحتی دکوری", "sofa", 295, price_toman=5_000_000) is None
        # only under a replica-prone leaf: a cheap hit under the real chair leaf is the integrity
        # gate's business (``price_out_of_band``), not the adapter's
        assert basalam.off_scope_reason("صندلی چوبی", "chair", 355, price_toman=495_000) is None
        # decor is exempt (a real figurine under 295 IS decor), and no price → no verdict
        assert basalam.off_scope_reason("مجسمه اسب", "decor", 295, price_toman=50_000) is None
        assert basalam.off_scope_reason("صندلی راک چوبی دکوری", "chair", 295) is None
        assert basalam.off_scope_reason("صندلی راک چوبی دکوری", "chair", 295, price_toman="") is None
        # the title rule still wins when both apply, and the weight rule before it
        assert (basalam.off_scope_reason("صندلی راحتی دکوری کوچک", "chair", 295, price_toman=50_000)
                == "miniature:295 sculpture-and-statue title")
        assert (basalam.off_scope_reason("صندلی راک", "chair", 295, weight_g=20, price_toman=50_000)
                == "miniature:weight=20g")

    def test_wholesale_listings_are_off_scope(self, live):
        """36791198 (2026-09-11 rehearsal): «آباژور عمده مولکولی» verified as
        ``lighting`` at 9.6 M toman — the price of a 12-pack (``is_wholesale``
        true, «پک ها 12 عددی»). A shopper following a recommendation cannot buy
        one, so the flag is a verdict; the word «عمده» in a title is not (8343366
        «مبل راحتی پاناما (عمده» is a retail listing with a bulk discount)."""
        pack = self._hit(live, id=36791198, name="آباژور عمده مولکولی( چراغ خواب رومیزی)", categoryTitle="آباژور",
                         new_categoryId=360, weight=350, price=96000000.0, is_wholesale=True)
        row = basalam.item_to_row(pack, target_category="lighting")
        assert row["off_scope"] == "wholesale:is_wholesale" and row["wholesale"] is True
        retail = self._hit(live, id=8343366, name="مبل راحتی پاناما (عمده ", categoryTitle="مبل",
                           new_categoryId=357, weight=28000, price=727500000.0, is_wholesale=False)
        row = basalam.item_to_row(retail, target_category="sofa")
        assert "off_scope" not in row and "wholesale" not in row
        # absent flag (the fixture, older dumps) → nothing; only a literal true counts
        assert "is_wholesale" not in basalam.find_product_list(live)[0]
        assert "off_scope" not in basalam.item_to_row(self._hit(live, is_wholesale="true"), target_category="sofa")
        assert basalam.off_scope_reason("آباژور", "lighting", 360, wholesale=True) == "wholesale:is_wholesale"
        assert basalam.off_scope_reason("آباژور", "lighting", 360, wholesale=False) is None

    def test_kids_lighting_vendor_is_off_scope(self, live):
        """babylightland — «سرزمین روشنایی کودک … تخصصی ترین تولید کننده محصولات
        کودک» — had a Manchester City chandelier (12153417) and a Ronaldo figure
        lamp (10071814) verified as ``lighting`` in the 2026-09-11 rehearsal. A
        club name is not a term we can list; the shop is."""
        item = self._hit(live, id=12153417, name="لوستر منچستر سیتی (ارسال رایگان)قابل شستشو", categoryTitle="لوستر",
                         new_categoryId=366, price=79000000.0,
                         vendor={"identifier": "babylightland", "name": "سرزمین روشنایی کودک.... babylightland", "id": 507021})
        row = basalam.item_to_row(item, target_category="lighting")
        assert row["off_scope"] == "vendor:babylightland kids-lighting-maker"
        assert basalam.OFF_SCOPE_VENDORS["babylightland"] == "kids-lighting-maker"

    def test_kids_furniture_vendor_is_off_scope_whatever_the_title(self, live):
        """sitatoys — «تولید کننده مبل کودک و نوجوان در طرح های مختلف کارتونی» —
        had four cartoon sofa-beds verified as ``sofa`` in the 2026-09-11
        dry-run; one title («کاناپه تخت شو کیتی») carries no kids' word."""
        item = self._hit(live, id=21917212, name="کاناپه تخت شو کیتی با تشک های متصل بهم(پس کرایه)",
                         categoryTitle="مبل", new_categoryId=357,
                         vendor={"identifier": "sitatoys", "name": "تولیدی صنعتی سیتا", "id": 322886})
        row = basalam.item_to_row(item, target_category="sofa")
        assert row["off_scope"] == "vendor:sitatoys kids-furniture-maker"
        assert basalam.off_scope_reason(
            "کاناپه تخت شو کیتی", "sofa", 357, vendor_identifier="SitaToys") == "vendor:sitatoys kids-furniture-maker"
        # every listed vendor names its evidence, and the list stays small on purpose
        assert all(v for v in basalam.OFF_SCOPE_VENDORS.values()) and len(basalam.OFF_SCOPE_VENDORS) <= 10

    def test_materials_come_from_the_title_when_the_hit_has_no_attributes(self, live):
        """Search hits carry no attributes, so a «میز تلویزیون ملامینه» had no
        seller material and the vision guess alone was ``material_implausible``
        ×3 in the 2026-09-11 dry-run (28019052, 44651380, 24366842)."""
        assert basalam.materials_from_title("میز جلومبلی عسلی سه تیکه لمین") == ["wood"]
        assert basalam.materials_from_title("میز تلویزیون ملامینه مدل 63") == ["wood"]
        assert basalam.materials_from_title("میز عسلی چوبی با صفحه شیشه ای") == ["wood", "glass"]
        assert basalam.materials_from_title("مبل راحتی مخمل پایه فلزی") == ["fabric", "metal"]
        # «استیل» in a title is a *style* («مبل استیل» = carved classic), «گردویی» a colour
        assert basalam.materials_from_title("مبل استیل سلطنتی رنگ گردویی") == []
        assert basalam.materials_from_title("") == []
        item = self._hit(live, id=44651380, name="میز تلویزیون ملامینه کد 63", categoryTitle="میز", new_categoryId=358)
        item.pop("attributes", None)
        item.pop("attribute_groups", None)
        assert basalam.item_to_row(item, target_category="storage")["materials"] == ["wood"]
        # an attribute, when present, still wins over the title
        item["attributes"] = [{"key": "جنس", "value": "ملامینه درجه یک"}]
        assert basalam.item_to_row(item, target_category="storage")["materials"] == ["wood"]
        item["attributes"] = [{"key": "جنس", "value": "فلز و شیشه"}]
        assert basalam.item_to_row(item, target_category="storage")["materials"] == ["metal", "glass"]

    def test_material_alias_table_knows_engineered_wood_boards(self):
        for word in ("ملامینه", "ملامین", "لمینت", "لمین", "نئوپان", "هایگلاس"):
            assert basalam._MATERIAL_ALIASES[word] == "wood", word
        assert basalam.materials_from_attributes({"attributes": [{"key": "جنس", "value": "ملامینه درجه یک "}]}) == ["wood"]
        assert basalam.materials_from_attributes({"attributes": [{"key": "جنس", "value": "لمین"}]}) == ["wood"]

    def test_chair_query_plan_no_longer_uses_the_camping_prone_term(self):
        # «صندلی راحتی»: 65% chair live; its first page was folding camping / relax chairs (2026-09-11 pilot)
        assert "صندلی راحتی" not in basalam.CATEGORY_QUERIES["chair"]
        assert "صندلی راک چوبی" in basalam.CATEGORY_QUERIES["chair"] and "مبل تک نفره" in basalam.CATEGORY_QUERIES["chair"]

    def test_off_scope_rows_are_marked_by_the_adapter_not_dropped(self, live):
        """The adapter only *marks*; the pipeline decides (and counts) — a
        dropped row would vanish from the report."""
        park = self._hit(live, id=45733176, name="چراغ پارکی مدل حیاطی", categoryTitle="آباژور", new_categoryId=360)
        row = basalam.item_to_row(park, target_category="lighting")
        assert row["off_scope"] == "title:پارکی"
        with basalam.BasalamClient(transport=_basalam_transport({**live, "products": [park]}, key="products"),
                                   pause_seconds=0) as client:
            rows = list(basalam.iter_search(client, queries={"lighting": ["آباژور"]}, rows=48))
        assert [r["source_product_id"] for r in rows] == ["45733176"] and rows[0]["off_scope"] == "title:پارکی"

    def test_query_plan_avoids_the_terms_that_pulled_off_scope_hits(self):
        # «چراغ ایستاده» → park lamps + physiotherapy lamp; «کتابخانه چوبی» → book sets («کتاب خانه»)
        assert "چراغ ایستاده" not in basalam.CATEGORY_QUERIES["lighting"]
        assert "کتابخانه چوبی" not in basalam.CATEGORY_QUERIES["storage"]
        assert "آباژور ایستاده" in basalam.CATEGORY_QUERIES["lighting"]
        assert "کتابخانه ایستاده" in basalam.CATEGORY_QUERIES["storage"]
        # every numeric leaf maps onto a real taxonomy id, and no off-scope leaf is also a mapped one
        from ai import taxonomy as tax

        assert set(basalam.BASALAM_CATEGORY_IDS.values()) <= set(tax.categories())
        assert not set(basalam.BASALAM_CATEGORY_IDS) & set(basalam.OFF_SCOPE_CATEGORY_IDS)
        # a replica-prone leaf is an honest decor leaf (mapped), never a blanket off-scope one
        assert set(basalam.MINIATURE_PRONE_CATEGORY_IDS) <= set(basalam.BASALAM_CATEGORY_IDS)
        assert not set(basalam.MINIATURE_PRONE_CATEGORY_IDS) & set(basalam.OFF_SCOPE_CATEGORY_IDS)
        assert all(v == v.lower().strip() for v in basalam.OFF_SCOPE_VENDORS)


# --------------------------------------------------------------- image step

class TestImages:
    def test_acquire_validates_hashes_and_can_skip_storage(self, monkeypatch):
        data = _png()
        monkeypatch.setattr(images, "_fetch_image_bytes", lambda url, timeout=30.0: (data, "image/png"))
        img = images.acquire("https://cdn.x.ir/a.png", store=False)
        assert img.phash == _phash(data) and img.hosted_url == "" and img.content_type == "image/png"
        stored = images.acquire("https://cdn.x.ir/a.png", store=True)
        assert stored.hosted_url.startswith("/media/") and stored.hosted_url.endswith(".png")

    def test_acquire_rejects_non_images(self, monkeypatch):
        monkeypatch.setattr(images, "_fetch_image_bytes", lambda url, timeout=30.0: (b"<html>nope</html>", "text/html"))
        with pytest.raises(images.ImageUnavailable) as exc:
            images.acquire("https://cdn.x.ir/a.png", store=False)
        assert exc.value.code == "image_invalid"

    def test_cdn_octet_stream_is_sniffed_without_a_warning(self, monkeypatch, caplog):
        """Basalam's CDN declares ``binary/octet-stream`` for every picture; the
        first live run printed the upload-mismatch warning 60 times. The sniff
        decides the format — the warning is for a person mislabelling an upload."""
        monkeypatch.setattr(images, "_fetch_image_bytes",
                            lambda url, timeout=30.0: (_png((90, 60, 30)), "binary/octet-stream"))
        with caplog.at_level("WARNING", logger="app.core.uploads"):
            got = images.acquire("https://statics.basalam.com/public-1/users/x/01-01/a.jpg_512X512X70.jpg", store=False)
        assert got.content_type.startswith("image/") and got.phash
        assert "does not match sniffed format" not in caplog.text

    def test_acquire_refuses_unsafe_urls_before_any_fetch(self):
        """The real SSRF guard runs (no monkeypatch): metadata/loopback hosts never get a request."""
        for url in ("http://169.254.169.254/latest/meta-data/sofa.jpg", "http://127.0.0.1:6379/x.png",
                    "file:///etc/passwd"):
            with pytest.raises(images.ImageUnavailable) as exc:
                images.acquire(url, store=False)
            assert exc.value.code == "image_url_unsafe", url

    def test_oversized_download_is_refused(self, monkeypatch):
        monkeypatch.setattr(images, "MAX_FEED_IMAGE_BYTES", 10)
        monkeypatch.setattr(images, "_fetch_image_bytes", lambda url, timeout=30.0: (_png(), "image/png"))
        with pytest.raises(images.ImageUnavailable) as exc:
            images.acquire("https://cdn.x.ir/a.png", store=False)
        assert exc.value.code == "image_too_large"


# ------------------------------------------------------------------ pipeline

class TestPipeline:
    def test_rejected_rows_report_title_and_reason(self, db, fetcher):
        report = _import(db, [_row(source_product_id="NOPIC-1", image_url="", image_raw="photo=None")], fetcher=fetcher)
        rejected = report.rows[0]
        assert (rejected.action, rejected.codes) == ("rejected", ["image_url_invalid"])
        assert rejected.title_fa == "مبل راحتی سه‌نفره مدل آرتا"
        assert rejected.warnings == ["image_url=missing image_raw=photo=None"]
        assert report.to_dict()["rows"][0]["warnings"] == rejected.warnings

    def test_dry_run_writes_nothing_but_reports_everything(self, db, fetcher, monkeypatch):
        monkeypatch.setattr(pipeline, "persist", lambda img: pytest.fail("dry run must not store images"))
        rows = [_row(source_product_id="DRY-1")]
        report = _import(db, rows, fetcher=fetcher, options=pipeline.ImportOptions(dry_run=True, image_mode="rehost"))
        assert report.summary()["created"] == 1
        assert report.rows[0].integrity_ok is not None
        assert db.scalar(select(Product).where(Product.source_product_id == "DRY-1")) is None
        assert fetcher.calls == ["https://cdn.example-seller.ir/p/sofa-modern-fabric.png"]

    def test_real_run_creates_unverified_rows_with_provenance(self, db, fetcher):
        report = _import(db, [_row(source_product_id="P-1")], fetcher=fetcher)
        assert report.summary()["created"] == 1
        p = db.scalar(select(Product).where(Product.source_product_id == "P-1"))
        assert p is not None
        assert p.source == SOURCE and p.is_verified is False
        assert p.image_url.startswith("/media/") and p.image_phash
        assert report.summary()["external_image_origins"] == []
        assert p.price_checked_at is not None
        assert p.extraction_raw["detected_category"] == "sofa"          # mock reads the filename
        assert p.extraction_raw["import"]["image_url"].endswith("sofa-modern-fabric.png")
        assert p.extraction_raw["import"]["feed_category"] == "مبل"
        assert p.integrity_ok is True and p.integrity_reasons == []
        assert p.style_embedding is not None
        assert p.seller_link_ok is True and p.link_status == "ok"
        audit = db.scalars(select(AuditLog).where(AuditLog.action == ACTION_CATALOG_IMPORT)
                           .order_by(AuditLog.created_at.desc())).first()
        assert audit is not None and f"source={SOURCE} created=1" in audit.detail

    def test_image_category_disagreement_is_flagged_and_never_verified(self, db, fetcher):
        # The seller says "rug" but the picture (per the vision check) is a sofa —
        # the exact bug ADR-016 was written for.
        rows = [_row(source_product_id="LIE-1", category="فرش", title_fa="فرش دستباف",
                     width_cm=300, depth_cm=200, height_cm=1, materials="fabric")]
        report = _import(db, rows, fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        r = report.rows[0]
        assert r.action == "created"
        assert r.detected_category == "sofa"
        assert "image_category_mismatch" in r.integrity_reasons
        assert r.integrity_ok is False and r.verified is False
        assert report.summary()["category_mismatch"] == 1
        p = db.scalar(select(Product).where(Product.source_product_id == "LIE-1"))
        assert p.is_verified is False and p.integrity_ok is False

    def test_verify_only_when_clean_and_vision_agrees(self, db, fetcher):
        rows = [_row(source_product_id="OK-1"),
                _row(source_product_id="NOLINK-1", seller_link="",
                     image_url="https://cdn.example-seller.ir/p/sofa-second.png")]
        report = _import(db, rows, fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        by = {r.source_product_id: r for r in report.rows}
        assert by["OK-1"].verified is True
        # A missing seller link is a sellability (production-tier) code: in the
        # non-strict dev gate the row is still eligible, but strict mode blocks it.
        assert "seller_link_missing" in policy.PRODUCTION_BLOCKING
        nolink = db.scalar(select(Product).where(Product.source_product_id == "NOLINK-1"))
        strict = policy.integrity_decision(nolink, strict=True)
        assert "seller_link_missing" in strict["reasons"] and strict["ok"] is False

    def test_verify_requires_vision(self):
        with pytest.raises(ValueError):
            pipeline.ImportOptions(verify=True, vision=False)

    # ---- P4-ب·2e: the picture arbitrates between two candidates; off-scope
    # rows never reach the image step; ``tolerate`` is explicit and stored.

    def test_image_picks_between_seller_label_and_query_target(self, db, fetcher):
        """An armchair the seller filed under «مبل»: seller says sofa, the
        query said chair, the picture is a chair → filed as chair, verified,
        provenance stored. Before 2e this row was excluded as a mismatch."""
        rows = [_row(source_product_id="ARM-1", title_fa="مبل تک نفره راحتی مدل لیانا", category="sofa",
                     category_candidates=["sofa", "chair"], seller_category="sofa", target_category="chair",
                     image_url="https://cdn.example-seller.ir/p/armchair-fabric-modern.png",
                     width_cm=80, depth_cm=85, height_cm=90)]
        fetcher.files["https://cdn.example-seller.ir/p/armchair-fabric-modern.png"] = _png((77, 33, 11))
        report = _import(db, rows, fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        r = report.rows[0]
        assert r.detected_category == "chair" and r.category == "chair"
        assert r.category_candidates == ["sofa", "chair"] and r.category_resolved_by == "image"
        assert "category_resolved_by_image:sofa->chair" in r.warnings
        assert r.integrity_ok is True and r.verified is True
        assert report.summary()["category_resolved_by_image"] == 1 and report.summary()["category_mismatch"] == 0
        p = db.scalar(select(Product).where(Product.source_product_id == "ARM-1"))
        assert p.category == "chair" and p.is_verified is True
        assert p.extraction_raw["import"]["category_candidates"] == ["sofa", "chair"]
        assert p.extraction_raw["import"]["category_resolved_by"] == "image"

    def test_image_matching_neither_candidate_is_still_a_mismatch(self, db, fetcher):
        """Two candidates never widen the gate: a coffee table returned by the
        sofa query and filed under «مبل» stays excluded."""
        rows = [_row(source_product_id="ARM-2", category="sofa", category_candidates=["sofa", "chair"],
                     seller_category="sofa", target_category="chair",
                     image_url="https://cdn.example-seller.ir/p/coffee-table-wood.png")]
        fetcher.files["https://cdn.example-seller.ir/p/coffee-table-wood.png"] = _png((5, 99, 42))
        report = _import(db, rows, fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        r = report.rows[0]
        assert r.detected_category == "coffee_table" and r.category == "sofa"
        assert r.category_resolved_by is None and "image_category_mismatch" in r.integrity_reasons
        assert r.integrity_ok is False and r.verified is False

    def test_single_candidate_is_never_re_filed_by_the_picture(self, db, fetcher):
        # Seller and query agreed on «rug»; the picture is a sofa → mismatch, not a silent re-file.
        rows = [_row(source_product_id="LIE-2", category="فرش", category_candidates=["rug"], title_fa="فرش دستباف",
                     width_cm=300, depth_cm=200, height_cm=1, materials="fabric")]
        report = _import(db, rows, fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        r = report.rows[0]
        assert r.category == "rug" and r.detected_category == "sofa" and r.category_resolved_by is None
        assert "image_category_mismatch" in r.integrity_reasons and r.verified is False

    def test_off_scope_rows_are_skipped_before_download_and_vision(self, db, fetcher):
        calls: list[str] = []

        class Counting:
            def extract_bytes(self, data, mime, *, image_hint="", prompt_kind="product", **kw):
                calls.append(image_hint)
                from ai.feature_extractor import FeatureExtractor

                return FeatureExtractor("mock").extract_bytes(data, mime=mime, image_hint=image_hint,
                                                              prompt_kind=prompt_kind)

        rows = [_row(source_product_id="PARK-1", title_fa="چراغ پارکی مدل حیاطی", category="lighting",
                     off_scope="title:پارکی", image_url="https://cdn.example-seller.ir/p/chandelier-metal-black.png"),
                _row(source_product_id="OK-2")]
        report = pipeline.import_rows(
            db, rows, source=SOURCE, options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"),
            extractor=Counting(), fetch_image=fetcher, check_link=lambda u: FakeLink(),
        )
        park, ok = report.rows
        assert park.action == "skipped" and park.codes == ["off_scope"] and "title:پارکی" in park.warnings
        assert ok.action == "created" and ok.verified is True
        assert "chandelier-metal-black.png" not in " ".join(fetcher.calls)   # never downloaded
        assert calls == ["sofa-modern-fabric.png"]                          # vision paid once, for the real row
        assert report.summary()["off_scope"] == 1 and report.summary()["rejection_codes"] == {"off_scope": 1}
        assert db.scalar(select(Product).where(Product.source_product_id == "PARK-1")) is None

    def test_replica_guard_and_vendor_rule_skip_before_download(self, db, fetcher):
        rows = [_row(source_product_id="MINI-1", title_fa="صندلی راحتی دکوری کوچک چوبی", category="chair",
                     off_scope="miniature:weight=20g", weight_g=20),
                _row(source_product_id="KIDS-1", title_fa="کاناپه تخت شو کیتی", category="sofa",
                     off_scope="vendor:sitatoys kids-furniture-maker"),
                _row(source_product_id="MINI-2", title_fa="صندلی راک چوبی دکوری", category="chair",
                     price_toman="495000", off_scope="miniature:295 price=495000t<1000000t", weight_g=800),
                _row(source_product_id="PACK-1", title_fa="آباژور عمده مولکولی", category="lighting",
                     off_scope="wholesale:is_wholesale", wholesale=True)]
        report = _import(db, rows, fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        assert [r.action for r in report.rows] == ["skipped"] * 4
        assert [r.warnings[-1] for r in report.rows] == [
            "miniature:weight=20g", "vendor:sitatoys kids-furniture-maker",
            "miniature:295 price=495000t<1000000t", "wholesale:is_wholesale"]
        assert fetcher.calls == [] and report.summary()["off_scope"] == 4
        ids = ["MINI-1", "KIDS-1", "MINI-2", "PACK-1"]
        assert db.scalar(select(Product).where(Product.source_product_id.in_(ids))) is None

    def test_weight_travels_into_the_import_provenance(self, db, fetcher):
        report = _import(db, [_row(source_product_id="W-1", weight_g="۴۵۰۰۰")], fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        assert report.rows[0].action == "created"
        p = db.scalar(select(Product).where(Product.source_product_id == "W-1"))
        assert p.extraction_raw["import"]["weight_g"] == "۴۵۰۰۰"
        assert p.extraction_raw["import"]["policy"] == pipeline.IMPORT_POLICY_VERSION == "catalog_import/2026-09-11.4"

    def test_off_scope_never_touches_an_existing_row(self, db, fetcher):
        _import(db, [_row(source_product_id="KEEP-1")], fetcher=fetcher,
                options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        before = db.scalar(select(Product).where(Product.source_product_id == "KEEP-1"))
        assert before.is_verified is True
        report = _import(db, [_row(source_product_id="KEEP-1", off_scope="title:کودک")], fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        r = report.rows[0]
        assert r.action == "skipped" and r.product_id == before.id
        assert any("already in the catalog" in w for w in r.warnings)
        db.refresh(before)
        assert before.is_verified is True and before.title_fa == "مبل راحتی سه‌نفره مدل آرتا"

    def test_tolerate_is_restricted_and_needs_verify(self):
        assert pipeline.ImportOptions(verify=True, tolerate={"ambiguous_style"}).tolerate == frozenset({"ambiguous_style"})
        with pytest.raises(ValueError, match="not allowed"):
            pipeline.ImportOptions(verify=True, tolerate={"low_confidence"})
        with pytest.raises(ValueError, match="not allowed"):
            pipeline.ImportOptions(verify=True, tolerate={"provider_error"})
        with pytest.raises(ValueError, match="only affects verify"):
            pipeline.ImportOptions(tolerate={"ambiguous_style"})

    def test_tolerated_ambiguous_style_is_verified_and_keeps_its_flag(self, db, fetcher):
        """Mock filename ``modern`` + ``scandi`` → styles {modern, scandinavian}
        = the confusable cluster → ``ambiguous_style`` as the *sole* reason."""
        url = "https://cdn.example-seller.ir/p/sofa-modern-scandi-fabric.png"
        fetcher.files[url] = _png((31, 41, 59))
        row = _row(source_product_id="AMB-1", image_url=url, styles="")
        strict = _import(db, [row], fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        r = strict.rows[0]
        assert r.review_reasons == ["ambiguous_style"] and r.verified is False and r.needs_review is True
        assert strict.summary()["needs_review"] == 1 and strict.summary()["tolerated"] == 0

        tolerant = _import(db, [dict(row, image_url=url)], fetcher=fetcher,
                           options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost",
                                                          refresh_images=True, tolerate={"ambiguous_style"}))
        r = tolerant.rows[0]
        assert r.verified is True and r.tolerated_reasons == ["ambiguous_style"]
        s = tolerant.summary()
        assert s["verified"] == 1 and s["tolerated"] == 1 and s["tolerated_reasons"] == {"ambiguous_style": 1}
        assert s["needs_review"] == 0 and s["review_reasons"] == {}      # nobody is waiting for a human
        p = db.scalar(select(Product).where(Product.source_product_id == "AMB-1"))
        assert p.is_verified is True
        assert p.extraction_raw["needs_review"] is True                      # the flag stays on the row …
        assert p.extraction_raw["review_reasons"] == ["ambiguous_style"]
        assert p.extraction_raw["import"]["tolerated"] == ["ambiguous_style"]  # … and so does the decision

    def test_tolerate_never_covers_a_second_reason(self, db, fetcher):
        """ambiguous_style + low_confidence: the tolerated reason does not
        drag the other one through."""
        class Hedging:
            def extract_bytes(self, data, mime, *, image_hint="", prompt_kind="product", **kw):
                from ai.feature_extractor import FeatureExtractor

                out = FeatureExtractor("mock").extract_bytes(data, mime=mime, image_hint=image_hint,
                                                             prompt_kind=prompt_kind)
                out.update(style=["modern", "minimal"], confidence=0.55, needs_review=True,
                           review_reasons=["low_confidence", "ambiguous_style"])
                return out

        report = pipeline.import_rows(
            db, [_row(source_product_id="AMB-2", styles="")], source=SOURCE,
            options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost",
                                           tolerate={"ambiguous_style"}),
            extractor=Hedging(), fetch_image=fetcher, check_link=lambda u: FakeLink(),
        )
        r = report.rows[0]
        assert r.verified is False and r.tolerated_reasons == []
        assert r.review_reasons == ["low_confidence", "ambiguous_style"]
        assert report.summary()["needs_review"] == 1

    def test_tolerate_never_verifies_a_flag_without_a_reason(self, db, fetcher):
        class Flagged:
            def extract_bytes(self, data, mime, *, image_hint="", prompt_kind="product", **kw):
                from ai.feature_extractor import FeatureExtractor

                out = FeatureExtractor("mock").extract_bytes(data, mime=mime, image_hint=image_hint,
                                                             prompt_kind=prompt_kind)
                out.update(needs_review=True, review_reasons=[])
                return out

        report = pipeline.import_rows(
            db, [_row(source_product_id="AMB-3")], source=SOURCE,
            options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost",
                                           tolerate={"ambiguous_style"}),
            extractor=Flagged(), fetch_image=fetcher, check_link=lambda u: FakeLink(),
        )
        assert report.rows[0].verified is False

    def test_upsert_updates_price_without_refetching_unchanged_image(self, db, fetcher):
        first = _import(db, [_row(source_product_id="UP-1", price_toman="40000000")], fetcher=fetcher)
        assert first.summary()["created"] == 1
        calls_before = len(fetcher.calls)
        later = datetime.now(timezone.utc) + timedelta(days=1)
        second = _import(db, [_row(source_product_id="UP-1", price_toman="42000000")], fetcher=fetcher, now=later)
        assert (second.summary()["updated"], second.summary()["created"]) == (1, 0)
        assert len(fetcher.calls) == calls_before  # unchanged picture → no download, no second inference
        p = db.scalar(select(Product).where(Product.source_product_id == "UP-1"))
        checked = p.price_checked_at.replace(tzinfo=timezone.utc) if p.price_checked_at.tzinfo is None else p.price_checked_at
        assert p.price_toman == 42_000_000 and checked >= later - timedelta(seconds=1)  # SQLite drops tzinfo
        third = _import(db, [_row(source_product_id="UP-1", price_toman="42000000")], fetcher=fetcher, now=later)
        assert third.summary()["unchanged"] == 1
        assert db.scalar(select(Product).where(Product.source_product_id == "UP-1")).id == p.id

    def test_changed_image_is_refetched(self, db, fetcher):
        _import(db, [_row(source_product_id="IMG-1")], fetcher=fetcher)
        n = len(fetcher.calls)
        _import(db, [_row(source_product_id="IMG-1", image_url="https://cdn.example-seller.ir/p/sofa-second.png")],
                fetcher=fetcher)
        assert fetcher.calls[n:] == ["https://cdn.example-seller.ir/p/sofa-second.png"]

    def test_duplicate_image_inside_batch_is_skipped_not_created(self, db, fetcher, monkeypatch):
        stored: list[str] = []
        real_persist = pipeline.persist
        monkeypatch.setattr(pipeline, "persist", lambda img: (stored.append(img.original_url), real_persist(img))[1])
        rows = [_row(source_product_id="D-1"), _row(source_product_id="D-2")]  # same picture
        report = _import(db, rows, fetcher=fetcher)
        by = {r.source_product_id: r for r in report.rows}
        assert by["D-1"].action == "created"
        assert by["D-2"].action == "skipped" and by["D-2"].codes == ["duplicate_image"]
        assert db.scalar(select(Product).where(Product.source_product_id == "D-2")) is None
        assert len(stored) == 1  # the twin never reached storage

    def test_unreachable_image_rejects_row(self, db, fetcher):
        report = _import(db, [_row(source_product_id="NOIMG", image_url="https://cdn.example-seller.ir/p/missing.png")],
                         fetcher=fetcher)
        assert report.rows[0].action == "rejected" and report.rows[0].codes == ["image_unreachable"]
        assert db.scalar(select(Product).where(Product.source_product_id == "NOIMG")) is None

    def test_unavailable_rows_are_skipped_and_existing_ones_unverified(self, db, fetcher):
        _import(db, [_row(source_product_id="AV-1")], fetcher=fetcher,
                options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        assert db.scalar(select(Product).where(Product.source_product_id == "AV-1")).is_verified is True
        report = _import(db, [_row(source_product_id="AV-1", available="ناموجود")], fetcher=fetcher)
        assert report.rows[0].action == "skipped" and report.rows[0].codes == ["unavailable"]
        db.expire_all()
        assert db.scalar(select(Product).where(Product.source_product_id == "AV-1")).is_verified is False

    def test_link_mode_keeps_seller_url_but_still_fingerprints(self, db, fetcher):
        report = _import(db, [_row(source_product_id="LINK-1")], fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, image_mode="link"))
        assert report.rows[0].action == "created"
        p = db.scalar(select(Product).where(Product.source_product_id == "LINK-1"))
        assert p.image_url == "https://cdn.example-seller.ir/p/sofa-modern-fabric.png" and p.image_phash
        # the operator is told which origins the CSP must allow
        assert report.summary()["external_image_origins"] == ["https://cdn.example-seller.ir"]

    def test_limit_and_rejections_do_not_abort_the_batch(self, db, fetcher):
        rows = [_row(source_product_id="L-bad", price_toman="0"), _row(source_product_id="L-1"),
                _row(source_product_id="L-2", image_url="https://cdn.example-seller.ir/p/sofa-second.png"),
                _row(source_product_id="L-3", image_url="https://cdn.example-seller.ir/p/rug-persian-red.png")]
        report = _import(db, rows, fetcher=fetcher,
                         options=pipeline.ImportOptions(dry_run=False, limit=2, image_mode="rehost"))
        actions = [(r.source_product_id, r.action) for r in report.rows]
        assert actions == [("L-bad", "rejected"), ("L-1", "created"), ("L-2", "created")]

    def test_vision_outage_flags_row_instead_of_fabricating(self, db, fetcher):
        class Broken:
            def extract_bytes(self, *a, **k):
                raise RuntimeError("quota exhausted")

        report = pipeline.import_rows(
            db, [_row(source_product_id="OUT-1")], source=SOURCE,
            options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"),
            extractor=Broken(), fetch_image=fetcher, check_link=lambda u: FakeLink(),
        )
        r = report.rows[0]
        assert r.action == "created" and r.needs_review is True and r.verified is False
        p = db.scalar(select(Product).where(Product.source_product_id == "OUT-1"))
        assert p.extraction_raw["provider_error"].startswith("RuntimeError")
        assert p.styles == ["modern", "minimal"]  # seller tags kept; nothing invented

    def test_on_row_reports_each_row_with_review_reasons(self, db, fetcher):
        """The operator console is fed per row (progress on a 60-row live run)
        and each result says *why* the vision gate wants a human."""
        seen: list[pipeline.RowResult] = []
        rows = [_row(source_product_id="PR-1"),
                _row(source_product_id="PR-bad", image_url=""),
                _row(source_product_id="PR-2", image_url="https://cdn.example-seller.ir/p/sofa-second.png")]
        report = _import(db, rows, fetcher=fetcher, on_row=seen.append)
        assert [r.source_product_id for r in seen] == ["PR-1", "PR-bad", "PR-2"]
        assert seen[1].action == "rejected" and seen[1].codes == ["image_url_invalid"]
        first = report.rows[0]
        assert first.needs_review is not None
        if first.needs_review:
            assert first.review_reasons  # never "needs review" without a reason
        assert set(report.summary()["review_reasons"]) <= {
            "low_confidence", "missing_style", "missing_material", "provider_error", "fallback_provider",
            "unknown_taxonomy_values", "ambiguous_style", "category_mismatch",
        }

    def test_on_row_failure_never_aborts_the_import(self, db, fetcher):
        def boom(_r):
            raise RuntimeError("printer died")

        report = _import(db, [_row(source_product_id="PR-3")], fetcher=fetcher, on_row=boom)
        assert report.summary()["created"] == 1

    def test_provider_error_text_is_redacted_before_it_is_stored(self, db, fetcher):
        """An httpx error message embeds the request URL; a key in it must not
        reach ``extraction_raw`` or the JSON report."""
        class Leaky:
            def extract_bytes(self, *a, **k):
                raise RuntimeError("POST https://generativelanguage.googleapis.com/x:generateContent?key=AQ.SECRET-VALUE")

        report = pipeline.import_rows(
            db, [_row(source_product_id="PR-leak")], source=SOURCE,
            options=pipeline.ImportOptions(dry_run=False, image_mode="rehost"),
            extractor=Leaky(), fetch_image=fetcher, check_link=lambda u: FakeLink(),
        )
        p = db.scalar(select(Product).where(Product.source_product_id == "PR-leak"))
        assert "SECRET-VALUE" not in p.extraction_raw["provider_error"]
        assert "[REDACTED]" in p.extraction_raw["provider_error"]
        assert report.rows[0].review_reasons == ["provider_error"]

    def test_recommender_excludes_mismatched_import_but_can_see_verified_one(self, db, fetcher):
        from app.services.recommender import _catalog_quality as catalog_quality

        rows = [_row(source_product_id="REC-ok"),
                _row(source_product_id="REC-lie", category="فرش", title_fa="فرش دستباف", width_cm=300, depth_cm=200,
                     height_cm=1, materials="fabric", image_url="https://cdn.example-seller.ir/p/sofa-second.png")]
        _import(db, rows, fetcher=fetcher, options=pipeline.ImportOptions(dry_run=False, verify=True, image_mode="rehost"))
        quality = catalog_quality(db, ["sofa", "rug"])
        ok = db.scalar(select(Product).where(Product.source_product_id == "REC-ok"))
        lie = db.scalar(select(Product).where(Product.source_product_id == "REC-lie"))
        assert ok.is_verified and ok.integrity_ok is True
        assert lie.is_verified is False and lie.integrity_ok is False
        assert quality["sofa"]["eligible"] >= 1


# ----------------------------------------------------------------------- CLI

class TestCli:
    def test_template_flag_prints_csv(self, capsys):
        from scripts import import_catalog

        assert import_catalog.main(["--template"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("source_product_id,title_fa,") and "NLP-1042" in out

    def test_cli_console_is_redacted_and_quiet_by_default(self, monkeypatch):
        """Regression for the 2026-09-10 live run: every ``httpx`` request line was
        printed raw, one carried the Gemini key in ``?key=``. The CLI now installs
        the record-factory redactor before any handler exists and demotes
        per-request chatter unless ``--verbose``."""
        import logging

        from app.core import log_redaction
        from scripts import import_catalog

        # Restore *exactly* what we found: app.main layers a request-id factory on
        # top of the redactor, and other tests depend on it staying in place.
        saved_factory = logging.getLogRecordFactory()
        saved_state = (log_redaction._INSTALLED, log_redaction._PREVIOUS_FACTORY)
        monkeypatch.setattr(log_redaction, "_INSTALLED", False)
        root = logging.getLogger()
        saved_level, saved_handlers = root.level, list(root.handlers)
        try:
            root.handlers.clear()
            import_catalog._configure_logging(verbose=False)
            import_catalog._configure_logging(verbose=False)  # idempotent: no double wrapping
            assert logging.getLogger("httpx").level == logging.WARNING
            record = logging.getLogger("httpx").makeRecord(
                "httpx", logging.INFO, __file__, 1,
                'HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/m:generateContent?key=AQ.LEAKED-KEY "200"',
                (), None)
            assert "LEAKED-KEY" not in record.getMessage() and "[REDACTED]" in record.getMessage()
        finally:
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)
            for name in ("httpx", "httpcore", "app.core.uploads", "PIL", "alembic"):
                logging.getLogger(name).setLevel(logging.NOTSET)
            logging.setLogRecordFactory(saved_factory)
            log_redaction._INSTALLED, log_redaction._PREVIOUS_FACTORY = saved_state

    def test_file_dry_run_end_to_end(self, tmp_path, monkeypatch, fetcher, capsys):
        from scripts import import_catalog

        monkeypatch.setattr(pipeline, "acquire", lambda url, timeout=30.0, store=False: fetcher(url))
        monkeypatch.setattr("app.services.link_checker.check_url_detailed", lambda url, timeout=10.0: FakeLink())
        feed = tmp_path / "feed.csv"
        feed.write_text(file_adapter.template_csv().replace(
            "https://cdn.example-seller.ir/products/arta-3-seat.jpg",
            "https://cdn.example-seller.ir/p/sofa-modern-fabric.png"), encoding="utf-8")
        report = tmp_path / "report.json"
        code = import_catalog.main(["file", "--path", str(feed), "--seller", "example", "--image-mode", "rehost",
                                    "--report", str(report)])
        out = capsys.readouterr().out
        assert code == 0, out
        assert "DRY-RUN (nothing written)" in out and "created=1" in out
        assert "[1/1]   NLP-1042  created" in out                 # one progress line per row
        assert "note: nothing is recommendable yet" in out        # no --verify → said out loud
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["summary"]["dry_run"] is True and data["rows"][0]["source_product_id"] == "NLP-1042"
        assert "review_reasons" in data["summary"] and "review_reasons" in data["rows"][0]
        from app.db.session import SessionLocal

        with SessionLocal() as s:
            assert s.scalar(select(Product).where(Product.source == "feed:example")) is None

    def test_usage_errors_exit_2(self, tmp_path, capsys):
        from scripts import import_catalog

        assert import_catalog.main(["file", "--path", str(tmp_path / "missing.csv"), "--seller", "x"]) == 2
        feed = tmp_path / "f.csv"
        feed.write_text(file_adapter.template_csv(), encoding="utf-8")
        assert import_catalog.main(["file", "--path", str(feed), "--seller", "Bad Slug"]) == 2
        assert import_catalog.main(["basalam", "--category", "shoes"]) == 2

    def test_tolerate_flag_is_validated_before_anything_runs(self, tmp_path, capsys):
        from scripts import import_catalog

        feed = tmp_path / "f.csv"
        feed.write_text(file_adapter.template_csv(), encoding="utf-8")
        assert import_catalog.main(["file", "--path", str(feed), "--seller", "x", "--verify",
                                    "--tolerate", "low_confidence"]) == 2
        err = capsys.readouterr().err
        assert "--tolerate ['low_confidence'] is not allowed" in err and "ambiguous_style" in err
        assert import_catalog.main(["file", "--path", str(feed), "--seller", "x", "--tolerate", "ambiguous_style"]) == 2
        assert "only has an effect together with --verify" in capsys.readouterr().err
        # the parser help names the allowed reasons, so the operator never has to guess
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf), pytest.raises(SystemExit):
            import_catalog.main(["basalam", "--help"])
        help_text = " ".join(buf.getvalue().split())   # argparse wraps lines
        assert "--tolerate REASON" in help_text and "allowed: ambiguous_style" in help_text
        args = import_catalog.build_parser().parse_args(["basalam", "--verify", "--tolerate", "ambiguous_style"])
        assert import_catalog._options(args).tolerate == frozenset({"ambiguous_style"})
        assert import_catalog.main(["basalam", "--query", "nonsense"]) == 2
        assert import_catalog.main([]) == 2

    def test_inspect_raw_explains_a_dump_offline(self, tmp_path, capsys):
        from scripts import import_catalog

        live = json.loads((FIXTURES / "basalam_search_live_shape.json").read_text(encoding="utf-8"))
        dump = tmp_path / "basalam-raw.json"
        dump.write_text(json.dumps({"query": "فرش دستباف", "response": live}, ensure_ascii=False), encoding="utf-8")
        assert import_catalog.main(["--inspect-raw", str(dump)]) == 0
        out = capsys.readouterr().out
        assert "query: فرش دستباف" in out and "items found: 5" in out
        assert "envelope keys: _note, correction, meta, facets, products" in out
        assert "price: 297000000 rial  category: 'فرش دستباف' → rug" in out
        assert "verdict: ok → 29,700,000 toman, category=rug" in out
        assert "image_raw: photo={'MEDIUM': None, 'SMALL': ''}" in out
        assert "verdict: REJECTED image_url_invalid" in out
        assert "4/5 inspected items pass the normaliser" in out

    def test_inspect_raw_shows_candidates_and_off_scope(self, tmp_path, capsys):
        from scripts import import_catalog

        live = json.loads((FIXTURES / "basalam_search_live_shape.json").read_text(encoding="utf-8"))
        first = dict(basalam.find_product_list(live)[0])
        armchair = {**first, "id": 46957138, "name": "مبل تک نفره راحتی", "categoryTitle": "مبل", "new_categoryId": 357}
        park = {**first, "id": 45733176, "name": "چراغ پارکی حیاطی", "categoryTitle": "آباژور", "new_categoryId": 360}
        dump = tmp_path / "raw.json"
        dump.write_text(json.dumps({"query": "مبل تک نفره", "response": {**live, "products": [armchair, park]}},
                                   ensure_ascii=False), encoding="utf-8")
        assert import_catalog.main(["--inspect-raw", str(dump)]) == 0
        out = capsys.readouterr().out
        assert "candidates: sofa | chair (seller label and search term disagree" in out
        assert "off_scope: title:پارکی (would be skipped before download/vision)" in out

        assert import_catalog.main(["--inspect-raw", str(tmp_path / "missing.json")]) == 2
        (tmp_path / "empty.json").write_text('{"response": {"products": []}}', encoding="utf-8")
        assert import_catalog.main(["--inspect-raw", str(tmp_path / "empty.json")]) == 1

    def test_basalam_cli_uses_fixture_transport(self, monkeypatch, fetcher, capsys, tmp_path):
        from scripts import import_catalog

        fixture = json.loads((FIXTURES / "basalam_search_sample.json").read_text(encoding="utf-8"))
        transport = _basalam_transport(fixture)
        original = basalam.BasalamClient

        def patched(*args, **kwargs):
            kwargs["transport"] = transport
            kwargs["pause_seconds"] = 0
            return original(*args, **kwargs)

        monkeypatch.setattr(basalam, "BasalamClient", patched)
        served = FakeFetcher({
            "https://statics.example-basalam.test/p/scarlet-sofa_lg.jpg": _png((1, 2, 3)),
            "https://statics.example-basalam.test/p/tabriz-rug.jpg": _png((4, 5, 6)),
            "https://statics.example-basalam.test/p/black-chandelier.jpg": _png((7, 8, 9)),
            "https://statics.example-basalam.test/p/leather-bag.jpg": _png((9, 9, 9)),
        })
        monkeypatch.setattr(pipeline, "acquire", lambda url, timeout=30.0, store=False: served(url))
        monkeypatch.setattr("app.services.link_checker.check_url_detailed", lambda url, timeout=10.0: FakeLink())
        dump = tmp_path / "raw.json"
        code = import_catalog.main(["basalam", "--category", "sofa", "--image-mode", "link", "--dump-raw", str(dump)])
        out = capsys.readouterr().out
        assert code == 0, out
        assert "fetched 5 candidate products" in out
        assert json.loads(dump.read_text(encoding="utf-8"))["query"] == "مبل راحتی"
        assert "skipped" in out and "unavailable" in out  # the out-of-stock cushion
