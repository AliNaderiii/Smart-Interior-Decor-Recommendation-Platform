"""Rate limiter tests — /recommend capped at 20/min per user (AI cost control)."""
from __future__ import annotations

QUIZ = {
    "styles": ["modern"], "color_palette": ["#2E2E2E"],
    "room_width_cm": 400, "room_length_cm": 500,
    "budget_min_toman": 1_000_000, "budget_max_toman": 150_000_000,
    "materials": ["wood"], "patterns": [],
}


def test_recommend_rate_limited_at_20_per_minute(client, auth_headers):
    headers, _ = auth_headers
    codes = [client.post("/api/v1/recommend", headers=headers, json=QUIZ).status_code
             for _ in range(22)]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429
    assert codes[21] == 429


def test_rate_limit_is_per_user(client, auth_headers):
    headers_a, _ = auth_headers
    # Exhaust user A
    for _ in range(21):
        client.post("/api/v1/recommend", headers=headers_a, json=QUIZ)
    assert client.post("/api/v1/recommend", headers=headers_a, json=QUIZ).status_code == 429

    # A fresh user B is unaffected
    import uuid

    email = f"rl-{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post("/api/v1/auth/register",
                      json={"email": email, "password": "Password123!"})
    headers_b = {"Authorization": f"Bearer {reg.json()['data']['access_token']}"}
    assert client.post("/api/v1/recommend", headers=headers_b, json=QUIZ).status_code == 200
