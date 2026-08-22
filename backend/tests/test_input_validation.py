"""Stage 03 · input validation and stored XSS (probe V-*, X-*, T-20 … T-27).

The rule under test: a hostile or malformed body is a **422 with a structured
error**, never a 500 and never a silent write. Oversized strings used to reach
the SQLite/Postgres driver and surface as a 500; unknown fields used to be
accepted and splatted into the model.
"""
from __future__ import annotations

import pytest

from app.schemas.sanitize import strip_html

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "<iframe src=javascript:alert(1)></iframe>",
    "<body onload=alert(1)>",
    "&lt;script&gt;alert(1)&lt;/script&gt;",     # entity-encoded
    "<scr<script>ipt>alert(1)</scr</script>ipt>",  # nested/partial
    "<a href='javascript:alert(1)'>click</a>",
    "<style>@import 'http://evil/x.css';</style>",
    "<div onmouseover=\"alert(1)\">hover</div>",
]


# --------------------------------------------------------------- unit: stripper

@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_strip_html_removes_all_markup(payload):
    cleaned = strip_html(payload)
    assert "<" not in cleaned and ">" not in cleaned, cleaned
    assert "onerror" not in cleaned.lower()
    assert "onload" not in cleaned.lower()
    assert "<script" not in cleaned.lower()


def test_strip_html_keeps_ordinary_text_readable():
    assert strip_html("  Nordic  Oak   Sofa ") == "Nordic Oak Sofa"
    # A lone `<` is not markup, so it survives — sanitising must not mangle
    # ordinary prose.
    assert strip_html("Price < 5,000,000 & rising") == "Price < 5,000,000 & rising"
    assert strip_html("Sofa &amp; chair") == "Sofa & chair"


def test_strip_html_removes_null_bytes_and_control_chars():
    assert strip_html("ab\x00cd\x07ef") == "abcdef"


def test_strip_html_is_idempotent():
    once = strip_html("<script>alert(1)</script>hello")
    assert strip_html(once) == once


# ---------------------------------------------------------- stored XSS at rest

@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_moodboard_title_is_sanitised_on_write(client, bearer_headers, payload):
    resp = client.post("/api/v1/moodboards", headers=bearer_headers,
                       json={"title": payload, "items": [], "shopping_list": []})
    assert resp.status_code == 201, resp.text
    stored = resp.json()["data"]["title"]
    assert "<script" not in stored.lower()
    assert "onerror" not in stored.lower()
    assert "<" not in stored and ">" not in stored

    # …and it stays clean when read back out.
    board_id = resp.json()["data"]["id"]
    fetched = client.get(f"/api/v1/moodboards/{board_id}", headers=bearer_headers)
    assert "<script" not in fetched.text.lower()


def test_quiz_client_name_is_sanitised(client, bearer_headers):
    resp = client.post("/api/v1/quiz", headers=bearer_headers, json={
        "styles": ["modern"], "color_palette": [], "room_width_cm": 300,
        "room_length_cm": 300, "budget_min_toman": 0, "budget_max_toman": 100,
        "materials": [], "patterns": [],
        "client_name": "<img src=x onerror=alert('quiz')>Bob",
    })
    assert resp.status_code == 201, resp.text
    assert "onerror" not in resp.text.lower()


def test_product_text_is_sanitised(client, admin_headers):
    resp = client.post("/api/v1/products", headers=admin_headers, json={
        "title": "<script>alert('t')</script>Sofa",
        "description": "<img src=x onerror=alert('d')>Comfy",
        "category": "sofa", "price_toman": 1000,
        "image_url": "https://cdn.example.com/s.png",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert "<script" not in data["title"].lower()
    assert "onerror" not in (data["description"] or "").lower()


def test_ai_extracted_text_is_sanitised(client, admin_headers, monkeypatch,
                                        png_bytes):
    """X-03: prompt injection through an uploaded image must not store markup."""
    from app.api.routes import products as products_mod

    class HostileExtractor:
        def extract(self, _source):
            return {
                "description_for_embedding":
                    "<img src=x onerror=alert('ai')>a modern sofa",
                "colors": ["warm"], "style": ["modern"], "material": ["wood"],
                "patterns": ["solid"], "confidence": 0.9,
            }

    monkeypatch.setattr(products_mod, "FeatureExtractor", HostileExtractor)
    resp = client.post("/api/v1/products/upload", headers=admin_headers,
                       files={"file": ("s.png", png_bytes, "image/png")})
    assert resp.status_code == 201, resp.text
    product = resp.json()["data"]["product"]
    assert "onerror" not in product["title"].lower()
    assert "<" not in product["title"]
    assert "onerror" not in (product["description"] or "").lower()
    assert "modern sofa" in product["title"], "sanitising must not destroy the text"


# ------------------------------------------------------------- oversized input

OVERSIZED = "A" * 10_000


def test_oversized_moodboard_title_is_422_not_500(client, bearer_headers):
    resp = client.post("/api/v1/moodboards", headers=bearer_headers,
                       json={"title": OVERSIZED, "items": [], "shopping_list": []})
    assert resp.status_code == 422, resp.text
    assert resp.json()["success"] is False


def test_oversized_full_name_is_422_not_500(client):
    import uuid

    resp = client.post("/api/v1/auth/register", json={
        "email": f"big-{uuid.uuid4().hex[:8]}@example.com",
        "password": "Str0ngTestPassphrase!", "full_name": OVERSIZED})
    assert resp.status_code == 422, resp.text


def test_oversized_email_is_422_not_500(client):
    resp = client.post("/api/v1/auth/login", json={
        "email": "a" * 5000 + "@example.com", "password": "Whatever123!"})
    assert resp.status_code == 422, resp.text


def test_unbounded_collections_are_rejected(client, bearer_headers):
    resp = client.post("/api/v1/moodboards", headers=bearer_headers, json={
        "title": "big", "items": [],
        "shopping_list": [f"p{i}" for i in range(5000)]})
    assert resp.status_code == 422, resp.text


def test_deeply_nested_json_does_not_crash(client, bearer_headers):
    payload = {"title": "deep", "items": [], "shopping_list": []}
    nested: object = "x"
    for _ in range(200):
        nested = [nested]
    payload["quiz_id"] = nested  # type: ignore[assignment]
    resp = client.post("/api/v1/moodboards", headers=bearer_headers, json=payload)
    assert resp.status_code == 422, resp.status_code


# --------------------------------------------------------------- mass assignment

def test_moodboard_rejects_unknown_fields(client, bearer_headers):
    resp = client.post("/api/v1/moodboards", headers=bearer_headers, json={
        "title": "ok", "items": [], "shopping_list": [],
        "user_id": "1001", "is_admin": True})
    assert resp.status_code == 422, resp.text


def test_product_rejects_server_controlled_fields(client, admin_headers):
    resp = client.post("/api/v1/products", headers=admin_headers, json={
        "title": "Sofa", "category": "sofa", "price_toman": 1000,
        "image_url": "https://cdn.example.com/s.png",
        "id": "attacker-chosen", "is_verified": True})
    assert resp.status_code == 422, resp.text


def test_quiz_rejects_unknown_fields(client, bearer_headers):
    resp = client.post("/api/v1/quiz", headers=bearer_headers, json={
        "styles": ["modern"], "color_palette": [], "room_width_cm": 300,
        "room_length_cm": 300, "budget_min_toman": 0, "budget_max_toman": 100,
        "materials": [], "patterns": [], "user_id": "someone-else"})
    assert resp.status_code == 422, resp.text


def test_payment_verify_rejects_unknown_fields(client, bearer_headers):
    resp = client.post("/api/v1/payment/verify", headers=bearer_headers, json={
        "authority": "A" * 36, "status": "OK", "amount_toman": 1})
    assert resp.status_code == 422, resp.text


# ------------------------------------------------------------- type confusion

@pytest.mark.parametrize("value", [None, 123, {"a": 1}, ["list"], True])
def test_wrong_types_are_422_not_500(client, bearer_headers, value):
    resp = client.post("/api/v1/moodboards", headers=bearer_headers,
                       json={"title": value, "items": [], "shopping_list": []})
    assert resp.status_code == 422, f"{value!r} -> {resp.status_code}"


def test_out_of_range_numbers_are_rejected(client, bearer_headers):
    body = {
        "styles": ["modern"], "color_palette": [], "room_width_cm": 10 ** 12,
        "room_length_cm": -5, "budget_min_toman": -1,
        "budget_max_toman": -2, "materials": [], "patterns": [],
    }
    resp = client.post("/api/v1/quiz", headers=bearer_headers, json=body)
    assert resp.status_code == 422, resp.text


def test_malformed_json_is_422_not_500(client, bearer_headers):
    resp = client.post(
        "/api/v1/moodboards",
        headers={**bearer_headers, "Content-Type": "application/json"},
        content=b"{not json")
    assert resp.status_code == 422, resp.status_code


def test_validation_errors_do_not_leak_internals(client, bearer_headers):
    resp = client.post("/api/v1/moodboards", headers=bearer_headers,
                       json={"title": OVERSIZED})
    assert resp.status_code == 422
    body = resp.text.lower()
    for leak in ("traceback", "sqlalchemy", "/home/", "site-packages", "sqlite3"):
        assert leak not in body, f"error body leaked {leak!r}"


# ------------------------------------------------------------------- taxonomy

def test_unknown_enum_values_are_rejected(client, bearer_headers):
    resp = client.post("/api/v1/quiz", headers=bearer_headers, json={
        "styles": ["'; DROP TABLE products; --"], "color_palette": [],
        "room_width_cm": 300, "room_length_cm": 300,
        "budget_min_toman": 0, "budget_max_toman": 100,
        "materials": [], "patterns": []})
    assert resp.status_code == 422, resp.text


def test_sql_injection_in_a_filter_is_harmless(client, admin_headers, db):
    from sqlalchemy import func, select

    from app.models.product import Product

    before = db.scalar(select(func.count()).select_from(Product))
    resp = client.get("/api/v1/products?category=sofa'; DROP TABLE products; --",
                      headers=admin_headers)
    assert resp.status_code in (200, 422), resp.text
    db.rollback()
    after = db.scalar(select(func.count()).select_from(Product))
    assert after == before, "the catalog changed — injection reached the database"
