"""ADR-013 — visual search ("find furniture that looks like this photo").

Two layers:

* the service (``app.services.visual_search``): palette extraction is
  deterministic and ignores backgrounds; the palette mode ranks by the
  platform's own perceptual colour metric; the CLIP mode blends cross-modal
  cosine with the palette prior (exercised with a fake CLIP model, since the
  test environment has no torch);
* the route (``POST /search/visual``): auth, upload hardening, category
  validation, paywall shape, rate limit, honest ``meta.mode`` — and the
  privacy property that nothing about the photo is persisted.
"""
from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from ai import embedding_service as es
from app.models.product import Product
from app.services import visual_search as vs

URL = "/api/v1/search/visual"


# ------------------------------------------------------------------ helpers

def _jpeg(color=(30, 90, 160), size=(160, 120), background=None, quality=90) -> bytes:
    """A JPEG of one flat colour, optionally on a white/black background frame."""
    im = Image.new("RGB", size, background or color)
    if background is not None:
        # object occupies the centre 60 %, background the frame
        w, h = size
        obj = Image.new("RGB", (int(w * 0.6), int(h * 0.6)), color)
        im.paste(obj, (int(w * 0.2), int(h * 0.2)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _post(client, headers, data: bytes, *, name="photo.jpg", ctype="image/jpeg", params=None):
    return client.post(
        URL, headers=headers, params=params or {},
        files={"file": (name, data, ctype)},
    )


def _hex_to_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _close(hex_a: str, rgb_b, tol=28) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(_hex_to_rgb(hex_a), rgb_b))


# ============================================================ palette layer

class TestPaletteExtraction:
    def test_flat_image_yields_its_colour_first(self):
        pal = vs.extract_palette(_jpeg((200, 40, 40)))
        assert pal and _close(pal[0], (200, 40, 40))
        assert all(p.startswith("#") and len(p) == 7 and p == p.upper() for p in pal)

    def test_is_deterministic(self):
        data = _jpeg((60, 120, 80), background=(255, 255, 255))
        assert vs.extract_palette(data) == vs.extract_palette(data)

    def test_white_background_is_demoted_behind_the_object(self):
        """A green sofa on a white wall must read as green, not white."""
        pal = vs.extract_palette(_jpeg((40, 110, 70), background=(255, 255, 255)))
        assert _close(pal[0], (40, 110, 70)), pal

    def test_black_background_is_demoted_too(self):
        pal = vs.extract_palette(_jpeg((190, 150, 90), background=(0, 0, 0)))
        assert _close(pal[0], (190, 150, 90)), pal

    def test_palette_size_is_bounded_and_unique(self):
        # a gradient produces many clusters; we still return ≤ PALETTE_SIZE unique swatches
        im = Image.new("RGB", (128, 64))
        px = im.load()
        for x in range(128):
            for y in range(64):
                px[x, y] = (x * 2, 255 - x * 2, (x * 3) % 256)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        pal = vs.extract_palette(buf.getvalue())
        assert 1 <= len(pal) <= vs.PALETTE_SIZE
        assert len(set(pal)) == len(pal)


# ============================================================ service layer

@pytest.fixture()
def catalogue(db):
    """Three verified rugs in distinct colours + one unverified decoy, in a
    private price band so they cannot collide with the seeded catalogue."""
    made = []
    specs = [
        ("Forest Green Rug", ["#2F6B3A"], True),
        ("Terracotta Rug", ["#C1633F"], True),
        ("Navy Rug", ["#1F2F5A"], True),
        ("Unverified Green Rug", ["#2F6B3A"], False),
    ]
    for i, (title, colors, verified) in enumerate(specs):
        p = Product(
            title=f"{title} {uuid.uuid4().hex[:6]}", title_fa=title, category="rug",
            price_toman=777_000_000 + i, image_url="https://images.unsplash.com/x",
            colors=colors, styles=["modern"], materials=["wool"], patterns=["solid"],
            width_cm=200, depth_cm=150, height_cm=1, description="",
            is_verified=verified,
            style_embedding=es.get_embedding(f"{title} modern wool rug"),
        )
        db.add(p)
        made.append(p)
    db.commit()
    yield made
    for p in made:
        db.delete(p)
    db.commit()


def _titles(items):
    return [i["title_fa"] for i in items]


class TestPaletteMode:
    def test_ranks_by_perceptual_colour_distance_and_reports_mode(self, db, catalogue):
        res = vs.search(db, _jpeg((47, 107, 58)), category="rug", limit=10)
        assert res["meta"]["mode"] == "palette"
        assert res["meta"]["category"] == "rug"
        top = res["items"][0]
        assert top["title_fa"] == "Forest Green Rug"
        assert 0 <= top["palette_match"] <= 1 and top["similarity"] == top["palette_match"]
        assert "clip_similarity" not in top

    def test_unverified_products_never_surface(self, db, catalogue):
        res = vs.search(db, _jpeg((47, 107, 58)), category="rug", limit=50)
        assert "Unverified Green Rug" not in _titles(res["items"])

    def test_category_filter_is_respected(self, db, catalogue):
        res = vs.search(db, _jpeg((47, 107, 58)), category="sofa", limit=50)
        assert res["items"] and all(i["category"] == "sofa" for i in res["items"])

    def test_limit_is_honoured_and_scores_sorted(self, db, catalogue):
        res = vs.search(db, _jpeg((193, 99, 63)), category=None, limit=5)
        sims = [i["similarity"] for i in res["items"]]
        assert len(res["items"]) == 5 and sims == sorted(sims, reverse=True)


class _FakeClip:
    """Stands in for SentenceTransformer: every image embeds to one fixed
    direction (products already carry hash embeddings)."""

    def __init__(self, vec):
        self.vec = vec

    def encode(self, inputs, normalize_embeddings=True):
        import math
        n = math.sqrt(sum(v * v for v in self.vec)) or 1.0
        return [[v / n for v in self.vec] for _ in inputs]


class TestClipMode:
    def test_blends_cross_modal_cosine_with_palette_prior(self, db, catalogue, monkeypatch):
        # Point the fake image tower at the Navy rug's own vector so the
        # CLIP term alone ranks navy first even for a green photo …
        navy = next(p for p in catalogue if p.title_fa == "Navy Rug")
        monkeypatch.setattr(es, "get_backend", lambda: "clip")
        monkeypatch.setattr(es, "_load_clip", lambda: _FakeClip(list(navy.style_embedding)))
        res = vs.search(db, _jpeg((47, 107, 58)), category="rug", limit=10)
        assert res["meta"]["mode"] == "clip"
        by_title = {i["title_fa"]: i for i in res["items"]}
        navy_row, green_row = by_title["Navy Rug"], by_title["Forest Green Rug"]
        # … and the blend is exactly 0.8·clip + 0.2·palette for every row.
        for row in res["items"]:
            assert row["similarity"] == pytest.approx(
                vs.CLIP_WEIGHT * row["clip_similarity"] + vs.PALETTE_WEIGHT * row["palette_match"],
                abs=1e-3,
            )
        assert navy_row["clip_similarity"] == pytest.approx(1.0, abs=1e-3)
        assert green_row["palette_match"] > navy_row["palette_match"]
        assert res["items"][0]["title_fa"] == "Navy Rug"  # shape/style wins, colour corrects


# ============================================================== route layer

@pytest.fixture()
def photo():
    return _jpeg((47, 107, 58), background=(255, 255, 255))


class TestRoute:
    def test_requires_authentication(self, client, photo):
        client.cookies.clear()
        assert _post(client, {}, photo).status_code == 401

    def test_returns_ranked_items_palette_and_honest_mode(self, client, bearer_headers, photo):
        resp = _post(client, bearer_headers, photo, params={"limit": 6})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["meta"]["mode"] == "palette"          # hash backend in tests
        assert data["meta"]["embedding_backend"] == "hash"
        assert data["meta"]["palette"] and data["meta"]["palette"][0].startswith("#")
        assert data["meta"]["query_image"]["content_type"] == "image/jpeg"
        assert 1 <= len(data["items"]) <= 6
        assert data["is_pro"] is False

    def test_free_user_gets_one_full_item_per_category_rest_teasers(self, client, bearer_headers, photo):
        data = _post(client, bearer_headers, photo, params={"category": "sofa", "limit": 5}).json()["data"]
        items = data["items"]
        assert len(items) >= 2
        assert "price_toman" in items[0] and not items[0].get("locked")
        for teaser in items[1:]:
            assert teaser["locked"] is True
            assert set(teaser) <= {"id", "title", "title_fa", "category", "image_url", "similarity", "locked"}
            assert "price_toman" not in teaser and "seller_link" not in teaser

    def test_pro_user_gets_everything(self, client, bearer_headers, db, photo):
        from app.models.user import User
        me = client.get("/api/v1/auth/me", headers=bearer_headers).json()["data"]
        user = db.get(User, me["id"])
        user.subscription.is_active = True
        user.subscription.plan = "pro"
        db.commit()
        data = _post(client, bearer_headers, photo, params={"category": "sofa", "limit": 5}).json()["data"]
        assert data["is_pro"] is True
        assert all(not i.get("locked") and "price_toman" in i for i in data["items"])

    def test_unknown_category_is_422(self, client, bearer_headers, photo):
        resp = _post(client, bearer_headers, photo, params={"category": "hot_tub"})
        assert resp.status_code == 422
        assert "hot_tub" in resp.text

    def test_limit_is_bounded(self, client, bearer_headers, photo):
        assert _post(client, bearer_headers, photo, params={"limit": 0}).status_code == 422
        assert _post(client, bearer_headers, photo, params={"limit": 99}).status_code == 422

    def test_non_image_is_rejected_with_415_not_500(self, client, bearer_headers):
        resp = _post(client, bearer_headers, b"<html>not an image</html>", name="a.jpg")
        assert resp.status_code == 415
        assert resp.json()["success"] is False

    def test_svg_polyglot_is_rejected(self, client, bearer_headers):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        assert _post(client, bearer_headers, svg, name="x.svg", ctype="image/svg+xml").status_code == 415

    def test_photo_is_never_persisted(self, client, bearer_headers, db, photo, monkeypatch):
        """ADR-013 privacy: no storage write, no product row, no cache entry."""
        from app.core import storage as storage_mod
        from app.core.redis_client import get_redis

        calls: list[str] = []

        class _Spy:
            def upload_file(self, *a, **k):
                calls.append("upload_file")
                return "http://should-not-happen"

        monkeypatch.setattr(storage_mod, "_storage", _Spy())
        before_products = db.query(Product).count()
        before_keys = {str(k) for k in get_redis().keys("*")}
        assert _post(client, bearer_headers, photo).status_code == 200
        db.expire_all()
        assert calls == []
        assert db.query(Product).count() == before_products
        new_keys = {str(k) for k in get_redis().keys("*")} - before_keys
        assert all("rl:" in k for k in new_keys), new_keys  # only the rate-limit bucket

    def test_rate_limited_per_user(self, client, bearer_headers, photo, reset_settings):
        reset_settings(VISUAL_SEARCH_RATE_LIMIT_PER_MINUTE=2)
        codes = [_post(client, bearer_headers, photo).status_code for _ in range(3)]
        assert codes == [200, 200, 429]

    def test_rejected_upload_is_audited(self, client, bearer_headers, db):
        from app.models.audit_log import AuditLog
        before = db.query(AuditLog).filter(AuditLog.action == "upload_rejected").count()
        _post(client, bearer_headers, b"nope", name="a.jpg")
        assert db.query(AuditLog).filter(AuditLog.action == "upload_rejected").count() == before + 1
