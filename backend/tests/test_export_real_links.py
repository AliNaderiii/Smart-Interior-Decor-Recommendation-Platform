"""``scripts/export_real_links.py`` → ``scripts/import_catalog.py file`` round trip.

The CI ``link-liveness`` job loads ``seed_data/products_real_links.json``
through the importer's file adapter and then probes only non-synthetic rows.
This test proves the three pieces agree without any network: the exporter
selects verified real rows only and writes template columns; the file adapter
+ contract accept every exported row (no ``rejected``); ``check_links``'
selection drops the synthetic sample and keeps the imported rows.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from ai.embedding_service import get_embedding
from app.models.product import Product
from app.services.catalog_import.adapters import file as file_adapter
from app.services.catalog_import.contract import normalize_row
from scripts import export_real_links as exporter

ROOT_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load_check_links():
    """Import the repo-root ``scripts/check_links.py`` as a module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_links_mod", ROOT_SCRIPTS / "check_links.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_links_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Api:
    """Minimal ``httpx.Client``-shaped wrapper over the TestClient: the exporter
    only uses ``.get(path, params=...)`` relative to ``/api/v1``."""

    def __init__(self, client, headers):
        self.client, self.headers = client, headers

    def get(self, path, params=None):
        return self.client.get(f"/api/v1{path}", params=params, headers=self.headers)


def _api(client, admin_headers):
    return _Api(client, admin_headers)


@pytest.fixture()
def real_rows(db):
    rows = [
        Product(id=uuid.uuid4().hex, title=f"Basalam rug {i}", title_fa=f"فرش دستباف {i}", category="rug",
                room_type="living_room", price_toman=4_500_000 + i, image_url="https://statics.basalam.com/x.jpg",
                seller_link=f"https://basalam.com/shop/product/{100 + i}", is_verified=True, integrity_ok=True,
                source="basalam", source_product_id=str(100 + i), styles=["classic"], colors=["#7B1E26"],
                materials=["fabric"], patterns=["persian"], width_cm=300, depth_cm=200, height_cm=1,
                style_embedding=get_embedding(f"rug {i}"))
        for i in range(3)
    ]
    rows.append(Product(id=uuid.uuid4().hex, title="Unverified chair", title_fa="صندلی", category="chair",
                        room_type="living_room", price_toman=9_000_000, image_url="https://statics.basalam.com/c.jpg",
                        seller_link="https://basalam.com/shop/product/999", is_verified=False, source="basalam",
                        source_product_id="999", style_embedding=get_embedding("chair")))
    db.add_all(rows)
    db.commit()
    yield rows
    db.execute(delete(Product).where(Product.id.in_([r.id for r in rows])))
    db.commit()


class TestExporter:
    def test_selects_verified_real_rows_only(self, client, admin_headers, real_rows):
        products = exporter.fetch_products(_api(client, admin_headers), page_size=50)
        rows = exporter.to_feed_rows(products)
        ids = {r["source_product_id"] for r in rows}
        assert {"100", "101", "102"} <= ids
        assert "999" not in ids  # unverified
        # the synthetic seed (source=synthetic-demo) never leaks into the fixture
        assert all(r["seller_name"] != "synthetic-demo" for r in rows)
        # Only this test's rows are counted: other modules may leave verified
        # `manual` rows behind on a persistent (CI PostgreSQL) database.
        assert sum(1 for r in rows if r["seller_name"] == "basalam") == 3

    def test_exported_rows_pass_the_importer_contract(self, client, admin_headers, real_rows, tmp_path):
        rows = [r for r in exporter.to_feed_rows(exporter.fetch_products(_api(client, admin_headers)))
                if r["seller_name"] == "basalam"]
        for r in rows:
            r.pop("_origin_source", None)
        path = tmp_path / "products_real_links.json"
        path.write_text(json.dumps({"items": rows}, ensure_ascii=False), encoding="utf-8")
        parsed = list(file_adapter.iter_file(path))
        assert len(parsed) == 3
        for raw in parsed:
            feed_row = normalize_row(raw, source="feed:ci-real-rows")
            assert feed_row.category == "rug"
            assert feed_row.seller_link.startswith("https://basalam.com/")
            assert feed_row.price_toman > 0

    def test_main_reports_empty_catalog(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(exporter, "fetch_products", lambda client, page_size=100: [])
        code = exporter.main(["--api", "http://127.0.0.1:9/api/v1", "--token", "t",
                              "--out", str(tmp_path / "out.json")])
        assert code == exporter.EXIT_EMPTY
        assert not (tmp_path / "out.json").exists()


class TestCheckLinksSelection:
    def test_exclude_synthetic_keeps_only_real_rows(self, db, real_rows):
        mod = _load_check_links()
        rows = list(db.scalars(select(Product).where(Product.seller_link != "")))
        assert any(r.source == "synthetic-demo" for r in rows)
        picked = mod.select_products(rows, sources=set(), exclude_synthetic=True, verified_only=False)
        assert picked and all(r.source != "synthetic-demo" for r in picked)
        assert {r.source_product_id for r in picked} >= {"100", "101", "102", "999"}
        picked_v = mod.select_products(rows, sources=set(), exclude_synthetic=True, verified_only=True)
        assert "999" not in {r.source_product_id for r in picked_v}
        by_source = mod.select_products(rows, sources={"basalam"}, exclude_synthetic=False, verified_only=False)
        assert all(r.source == "basalam" for r in by_source) and len(by_source) == 4

    def test_file_mode_reads_the_export_without_a_database(self, tmp_path):
        mod = _load_check_links()
        path = tmp_path / "products_real_links.json"
        path.write_text(json.dumps({"items": [
            {"source_product_id": "100", "category": "rug", "seller_link": "https://basalam.com/s/product/100",
             "seller_name": "basalam"},
            {"source_product_id": "s1", "category": "sofa", "seller_link": "https://www.nilper.com/",
             "source": "synthetic-demo"},
            {"source_product_id": "nolink", "category": "sofa", "seller_link": ""},
        ]}, ensure_ascii=False), encoding="utf-8")
        rows = mod.rows_from_file(path)
        assert len(rows) == 3
        picked = mod.select_products(rows, sources=set(), exclude_synthetic=True, verified_only=True)
        assert [r.id for r in picked] == ["100"]
        assert picked[0].source == "basalam"

