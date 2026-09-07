"""ADR-015 — room photo → pre-filled style quiz.

Three layers:

* ``FeatureExtractor.extract_bytes``: the new in-memory entry point shares
  the stamping / fallback / review gate with ``extract`` and stamps the room
  prompt version separately from the product benchmark prompt;
* ``room_analysis.analyse_room``: confidence tiers are honest — a heuristic
  provider can only ever yield ``palette_only``; a real provider below the
  auto-accept threshold is ``suggested``; nothing exceeds the quiz store
  limits; taxonomy clamping holds;
* ``POST /quiz/analyze-room``: auth, upload hardening, rate limit, the
  response contract the quiz page consumes, and the privacy property that
  nothing about the photo is persisted.

No external API is called: the "real" provider is a stub.
"""
from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import func, select

from ai import feature_extractor as fe
from ai.extraction_review import AUTO_ACCEPT_THRESHOLD
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.quiz import StyleQuiz
from app.services import room_analysis as ra

URL = "/api/v1/quiz/analyze-room"


def _room_jpeg(wall=(242, 232, 213), sofa=(76, 100, 68), size=(240, 180)) -> bytes:
    """A 'room': a large light wall with a darker piece of furniture in it."""
    im = Image.new("RGB", size, wall)
    w, h = size
    im.paste(Image.new("RGB", (int(w * 0.5), int(h * 0.4)), sofa), (int(w * 0.25), int(h * 0.45)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _post(client, headers, data: bytes, *, name="room.jpg", ctype="image/jpeg"):
    return client.post(URL, headers=headers, files={"file": (name, data, ctype)})


class _StubVision(fe.BaseProvider):
    """Stands in for Gemini/OpenAI: returns a canned, taxonomy-valid answer."""

    name = "gemini"

    def __init__(self, payload: dict, *, raise_exc: Exception | None = None):
        self._payload = payload
        self._raise = raise_exc
        self.calls: list[dict] = []

    def extract(self, image_url: str) -> dict:  # pragma: no cover - not used here
        raise AssertionError("room analysis must use the bytes path")

    def extract_bytes(self, data: bytes, mime: str, *, prompt=fe.EXTRACTION_PROMPT, hint=""):
        self.calls.append({"bytes": len(data), "mime": mime, "prompt": prompt, "hint": hint})
        if self._raise is not None:
            raise self._raise
        return fe._sanitize(dict(self._payload))


@pytest.fixture()
def real_vision(monkeypatch):
    """Install a stub *real* provider behind ``FeatureExtractor``."""

    def _install(payload: dict, *, raise_exc: Exception | None = None) -> _StubVision:
        stub = _StubVision(payload, raise_exc=raise_exc)

        def _init(self, provider=None):
            self._fallback_problem = None
            self.provider = stub

        monkeypatch.setattr(fe.FeatureExtractor, "__init__", _init)
        return stub

    return _install


GOOD_ROOM = {
    "colors": ["#F2E8D5", "#4C6444"],
    "style": ["boho", "scandinavian"],
    "material": ["rattan", "wood", "fabric"],
    "patterns": ["geometric"],
    "description_for_embedding": "a bright bohemian living room with rattan and warm wood",
    "confidence": 0.91,
}


# --------------------------------------------------------------- extract_bytes
class TestExtractBytes:
    def test_room_prompt_is_sent_and_room_version_stamped(self, real_vision):
        stub = real_vision(GOOD_ROOM)
        out = fe.FeatureExtractor().extract_bytes(b"\xff\xd8xx", mime="image/jpeg", prompt_kind="room")
        assert stub.calls[0]["prompt"] == fe.ROOM_PROMPT
        assert stub.calls[0]["mime"] == "image/jpeg"
        assert out["prompt_kind"] == "room"
        assert out["prompt_version"] == fe.ROOM_PROMPT_VERSION == "r1"
        assert out["provider"] == "gemini"
        assert out["needs_review"] is False

    def test_product_kind_keeps_the_benchmark_prompt_version(self, real_vision):
        real_vision(GOOD_ROOM)
        out = fe.FeatureExtractor().extract_bytes(b"\xff\xd8xx", prompt_kind="product")
        assert out["prompt_version"] == fe.EXTRACTION_PROMPT_VERSION == "p5"

    def test_unknown_prompt_kind_is_a_programming_error(self, real_vision):
        real_vision(GOOD_ROOM)
        with pytest.raises(KeyError):
            fe.FeatureExtractor().extract_bytes(b"x", prompt_kind="kitchen")

    def test_room_prompt_pins_the_taxonomy(self):
        for style in fe.ALLOWED_STYLES:
            assert style in fe.ROOM_PROMPT
        for material in fe.ALLOWED_MATERIALS:
            assert material in fe.ROOM_PROMPT
        assert "is_empty_room" in fe.ROOM_PROMPT

    def test_provider_failure_degrades_to_labelled_fallback_outside_production(self, real_vision):
        real_vision(GOOD_ROOM, raise_exc=RuntimeError("quota"))
        out = fe.FeatureExtractor().extract_bytes(b"x", image_hint="boho-room.jpg", prompt_kind="room")
        assert out["provider"] == "mock-fallback"
        assert out["confidence"] <= 0.30
        assert out["needs_review"] is True
        assert "provider_error" in out["review_reasons"]

    def test_mock_provider_uses_the_filename_hint_only(self):
        out = fe.MockProvider().extract_bytes(b"\x00" * 10, "image/png", hint="industrial-metal.png")
        assert out["style"] == ["industrial"]
        assert out["material"] == ["metal"]

    def test_base_provider_bytes_path_is_explicitly_unsupported(self):
        class Legacy(fe.BaseProvider):
            name = "legacy"

            def extract(self, image_url):
                return {}

        with pytest.raises(NotImplementedError):
            Legacy().extract_bytes(b"x", "image/jpeg")


# -------------------------------------------------------------- accent colours
class TestAccentColors:
    def test_small_saturated_piece_in_a_neutral_room_is_found(self):
        """3 % of the frame in mustard yellow on white walls + oak floor."""
        im = Image.new("RGB", (200, 160), (236, 234, 230))
        im.paste(Image.new("RGB", (150, 60), (184, 150, 105)), (0, 100))   # 'oak' floor: s≈0.43 < floor
        im.paste(Image.new("RGB", (32, 30), (227, 187, 62)), (80, 70))      # chair: ~3 %
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=92)
        accents = ra.accent_colors(buf.getvalue())
        assert len(accents) == 1
        r, g, b = (int(accents[0][i:i + 2], 16) for i in (1, 3, 5))
        assert r > 190 and g > 150 and b < 110      # unmistakably the yellow chair

    def test_neutral_room_yields_no_accent(self):
        assert ra.accent_colors(_room_jpeg(wall=(236, 234, 230), sofa=(120, 118, 115))) == []

    def test_two_objects_two_swatches_one_object_one_swatch(self):
        im = Image.new("RGB", (240, 180), (242, 232, 213))
        im.paste(Image.new("RGB", (120, 72), (180, 40, 40)), (60, 81))      # red sofa
        one = io.BytesIO()
        im.save(one, format="JPEG", quality=92)
        im.paste(Image.new("RGB", (40, 40), (30, 60, 200)), (10, 10))       # + blue cushion
        two = io.BytesIO()
        im.save(two, format="JPEG", quality=92)
        assert len(ra.accent_colors(one.getvalue())) == 1
        assert len(ra.accent_colors(two.getvalue())) == 2

    def test_below_share_floor_is_ignored(self):
        im = Image.new("RGB", (200, 200), (240, 240, 240))
        im.paste(Image.new("RGB", (8, 8), (220, 30, 30)), (50, 50))         # 0.16 %: a book spine
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        assert ra.accent_colors(buf.getvalue()) == []

    def test_accent_leads_the_room_palette_and_cap_holds(self):
        im = Image.new("RGB", (240, 180), (242, 232, 213))
        im.paste(Image.new("RGB", (120, 72), (180, 40, 40)), (60, 81))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=92)
        palette = ra._room_palette(buf.getvalue())
        assert palette[0] == ra.accent_colors(buf.getvalue())[0]
        assert len(palette) <= ra.MAX_COLORS
        assert len(set(palette)) == len(palette)


# --------------------------------------------------------------- analyse_room
class TestAnalyseRoom:
    def test_confident_tier_prefills_everything(self, real_vision):
        real_vision(GOOD_ROOM)
        out = ra.analyse_room(_room_jpeg(), image_hint="IMG_0001.jpg")
        assert out["confidence_tier"] == "confident"
        assert out["suggestion"]["styles"] == ["boho", "scandinavian"]
        assert out["suggestion"]["materials"] == ["rattan", "wood", "fabric"]
        assert out["suggestion"]["patterns"] == ["geometric"]
        # colours come from the pixels, not from the model
        assert out["suggestion"]["color_palette"] == out["palette"][:5]
        assert any(c.upper().startswith("#4") for c in out["palette"])  # the green sofa survived
        assert out["meta"]["heuristic"] is False
        assert out["meta"]["dimensions_estimated"] is False
        assert out["labels"]["styles"][0] == {"id": "boho", "fa": "بوهو / بوهمی", "en": "Bohemian"}

    def test_below_threshold_is_suggested_not_confident(self, real_vision):
        real_vision({**GOOD_ROOM, "confidence": AUTO_ACCEPT_THRESHOLD - 0.05})
        out = ra.analyse_room(_room_jpeg())
        assert out["confidence_tier"] == "suggested"
        assert out["suggestion"]["styles"]  # still offered, just flagged
        assert "low_confidence" in out["review_reasons"]

    def test_unknown_taxonomy_values_demote_to_suggested(self, real_vision):
        real_vision({**GOOD_ROOM, "style": ["japandi", "boho"], "material": ["concrete"]})
        out = ra.analyse_room(_room_jpeg())
        assert out["suggestion"]["styles"] == ["boho"]          # clamped, never guessed
        assert out["suggestion"]["materials"] == []
        assert out["confidence_tier"] == "suggested"
        assert set(out["meta"]["unknown_taxonomy_values"]) == {"japandi", "concrete"}

    def test_heuristic_provider_can_only_yield_palette_only(self, reset_settings):
        reset_settings(AI_PROVIDER="mock")
        # The mock would happily say "boho + rattan @0.9" from the filename —
        # that must never pre-select styles for a user.
        out = ra.analyse_room(_room_jpeg(), image_hint="boho-rattan-room.jpg")
        assert out["meta"]["provider"] == "mock"
        assert out["meta"]["heuristic"] is True
        assert out["confidence_tier"] == "palette_only"
        assert out["suggestion"]["styles"] == []
        assert out["suggestion"]["materials"] == []
        assert len(out["suggestion"]["color_palette"]) >= 2

    def test_provider_failure_still_returns_the_palette(self, real_vision):
        real_vision(GOOD_ROOM, raise_exc=RuntimeError("boom"))
        out = ra.analyse_room(_room_jpeg())
        assert out["confidence_tier"] == "palette_only"
        assert out["palette"]
        assert out["meta"]["provider"] in ("mock-fallback", "failed")

    def test_suggestions_never_exceed_quiz_store_limits(self, real_vision):
        real_vision({
            **GOOD_ROOM,
            "style": ["modern", "minimal", "classic", "boho"],
            "material": ["wood", "metal", "fabric", "leather", "rattan", "glass"],
        })
        out = ra.analyse_room(_room_jpeg())
        assert len(out["suggestion"]["styles"]) <= ra.MAX_STYLES == 3
        assert len(out["suggestion"]["materials"]) <= ra.MAX_MATERIALS == 6
        assert len(out["suggestion"]["color_palette"]) <= ra.MAX_COLORS == 5

    def test_empty_room_answer_is_confident_but_material_free(self, real_vision):
        real_vision({**GOOD_ROOM, "material": [], "style": ["minimal"], "confidence": 0.85})
        out = ra.analyse_room(_room_jpeg())
        # review gate flags missing_material → not "confident", but the style
        # suggestion is still valuable for an empty room.
        assert out["confidence_tier"] == "suggested"
        assert out["suggestion"]["styles"] == ["minimal"]
        assert out["suggestion"]["materials"] == []


# --------------------------------------------------------------------- route
class TestRoute:
    def test_requires_auth(self, client):
        assert _post(client, {}, _room_jpeg()).status_code == 401

    def test_contract_for_the_quiz_page(self, client, auth_headers, real_vision):
        headers, _ = auth_headers
        real_vision(GOOD_ROOM)
        resp = _post(client, headers, _room_jpeg(), name="living-room.jpg")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert set(data) >= {
            "suggestion", "labels", "confidence_tier", "confidence",
            "palette", "description", "review_reasons", "meta",
        }
        assert set(data["suggestion"]) == {"styles", "materials", "color_palette", "patterns"}
        assert data["confidence_tier"] in ra.CONFIDENCE_TIERS
        assert data["meta"]["query_image"] == {"width": 240, "height": 180, "content_type": "image/jpeg"}
        assert data["meta"]["taxonomy_version"] == "2.1"
        # the suggestion must be directly submittable to POST /quiz
        quiz = client.post(
            "/api/v1/quiz", headers=headers,
            json={
                **data["suggestion"],
                "room_width_cm": 400, "room_length_cm": 500,
                "budget_min_toman": 10_000_000, "budget_max_toman": 200_000_000,
            },
        )
        assert quiz.status_code == 201, quiz.text

    def test_mock_environment_is_honest_in_the_response(self, client, auth_headers, reset_settings):
        reset_settings(AI_PROVIDER="mock")
        headers, _ = auth_headers
        data = _post(client, headers, _room_jpeg(), name="modern-wood-room.jpg").json()["data"]
        assert data["meta"]["heuristic"] is True
        assert data["confidence_tier"] == "palette_only"
        assert data["suggestion"]["styles"] == []

    @pytest.mark.parametrize(("name", "payload", "ctype", "expected"), [
        ("evil.html", b"<html><script>alert(1)</script></html>", "text/html", 415),
        ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml", 415),
        ("payload.jpg", b"MZ\x90\x00\x03" + b"\x00" * 200, "image/jpeg", 415),
    ])
    def test_upload_hardening_applies(self, client, auth_headers, db, name, payload, ctype, expected):
        headers, me = auth_headers
        resp = _post(client, headers, payload, name=name, ctype=ctype)
        assert resp.status_code in (expected, 400, 422), resp.text
        rejected = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "upload_rejected", AuditLog.user_id == me["user"]["id"]
            )
        ).all()
        assert any("room-analysis" in (r.detail or "") for r in rejected)

    def test_rate_limited_like_an_upload(self, client, auth_headers, reset_settings, real_vision):
        reset_settings(ROOM_ANALYSIS_RATE_LIMIT_PER_MINUTE=2)
        real_vision(GOOD_ROOM)
        headers, _ = auth_headers
        codes = [_post(client, headers, _room_jpeg()).status_code for _ in range(3)]
        assert codes[:2] == [200, 200] and codes[2] == 429

    def test_nothing_is_persisted(self, client, auth_headers, db, real_vision, tmp_path, monkeypatch):
        """No quiz row, no product row, no stored file — the photo is discarded."""
        from app.core import storage as storage_mod

        headers, me = auth_headers
        real_vision(GOOD_ROOM)
        quizzes_before = db.scalar(select(func.count(StyleQuiz.id)))
        products_before = db.scalar(select(func.count(Product.id)))
        uploads: list = []
        monkeypatch.setattr(
            storage_mod.LocalStorage, "upload_file",
            lambda self, *a, **k: uploads.append(a) or "http://x/never",
        )
        resp = _post(client, headers, _room_jpeg(), name=f"{uuid.uuid4().hex}.jpg")
        assert resp.status_code == 200
        db.expire_all()
        assert db.scalar(select(func.count(StyleQuiz.id))) == quizzes_before
        assert db.scalar(select(func.count(Product.id))) == products_before
        assert uploads == []
        # and no audit row leaks the filename either
        rows = db.scalars(select(AuditLog).where(AuditLog.user_id == me["user"]["id"])).all()
        assert all(".jpg" not in (r.detail or "") for r in rows)
