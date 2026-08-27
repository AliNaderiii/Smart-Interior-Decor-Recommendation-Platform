"""Stage 1 (T-1.2) — validated, switchable recommender weight profiles.

The client ad states pattern 10% on top of the existing weights (which sums
to 1.05 — invalid). The config therefore ships two validated profiles:

* ``current``   — the ADR-005 baseline (style .30 / color .30 / budget .20 /
  material .15 / pattern .05), the active default;
* ``client-ad`` — the normalised ad weights (material reduced to .10).

This suite proves: validation (fail-fast on bad profiles), switchability
(``recommend(profile=...)`` + ``RECOMMENDER_WEIGHT_PROFILE``), cache-key
separation between profiles, meta stamping, determinism, and that the full
18-scenario acceptance harness passes under BOTH profiles (the comparison
harness ``--compare-profiles`` writes docs/reports/weights_profiles.md).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ai.model_registry import RECOMMENDER_CONFIG_VERSION
from app.services import recommender as rec


# ---------------------------------------------------------------------------
# Config structure & validation
# ---------------------------------------------------------------------------
def test_config_ships_both_validated_profiles():
    cfg = rec.CONFIG
    assert set(cfg["profiles"]) >= {"current", "client-ad"}
    for name in ("current", "client-ad"):
        w = cfg["profiles"][name]["weights"]
        assert set(w) == {"style", "color", "budget", "material", "pattern"}
        assert abs(sum(w.values()) - 1.0) < 1e-9
    assert cfg["default_profile"] == "current"
    # Top-level weights must mirror the default profile (drift guard).
    assert cfg["weights"] == cfg["profiles"]["current"]["weights"]


def test_client_ad_weights_are_the_normalised_ad():
    w = rec.PROFILES["client-ad"]
    assert w == {
        "style": 0.30, "color": 0.30, "budget": 0.20, "material": 0.10, "pattern": 0.10
    }
    # And the ad as literally stated (pattern .10 on top of the old weights)
    # must be REJECTED by the validator — that is the 1.05 sum.
    ad_as_stated = {"style": 0.30, "color": 0.30, "budget": 0.20,
                    "material": 0.15, "pattern": 0.10}
    assert abs(sum(ad_as_stated.values()) - 1.05) < 1e-9
    bad = json.loads(json.dumps(rec.CONFIG))
    bad["profiles"]["client-ad"]["weights"] = ad_as_stated
    with pytest.raises(RuntimeError, match="weights sum to 1.05"):
        rec.load_recommender_config(_tmp_config(bad))


def _tmp_config(cfg: dict) -> Path:
    f = Path(tempfile.mktemp(suffix=".json"))
    f.write_text(json.dumps(cfg), encoding="utf-8")
    return f


def test_profile_with_bad_sum_is_rejected_at_load():
    bad = json.loads(json.dumps(rec.CONFIG))
    bad["profiles"]["client-ad"]["weights"]["pattern"] = 0.30  # sum 1.2
    with pytest.raises(RuntimeError, match="profile 'client-ad' weights sum to 1.2"):
        rec.load_recommender_config(_tmp_config(bad))


def test_missing_default_profile_is_rejected():
    bad = json.loads(json.dumps(rec.CONFIG))
    del bad["default_profile"]
    with pytest.raises(RuntimeError, match="default_profile"):
        rec.load_recommender_config(_tmp_config(bad))


def test_top_level_weight_drift_is_rejected():
    bad = json.loads(json.dumps(rec.CONFIG))
    bad["weights"]["pattern"] = 0.99  # drift vs profiles[current]
    with pytest.raises(RuntimeError, match="must mirror"):
        rec.load_recommender_config(_tmp_config(bad))


def test_unknown_env_profile_name_is_rejected():
    """A typo in RECOMMENDER_WEIGHT_PROFILE must refuse to boot, not silently
    fall back to the baseline (module-level guard, exercised via the same
    function the import path calls)."""
    from app.core.config import settings

    saved = settings.RECOMMENDER_WEIGHT_PROFILE
    object.__setattr__(settings, "RECOMMENDER_WEIGHT_PROFILE", "nope")
    try:
        with pytest.raises(RuntimeError, match="not one of the configured"):
            rec.select_active_profile()
    finally:
        object.__setattr__(settings, "RECOMMENDER_WEIGHT_PROFILE", saved)


def test_active_profile_matches_settings():
    from app.core.config import settings

    assert rec.ACTIVE_PROFILE == settings.RECOMMENDER_WEIGHT_PROFILE
    assert rec.WEIGHTS == rec.PROFILES[rec.ACTIVE_PROFILE]


def test_get_weights_validates_names():
    assert rec.get_weights() == rec.PROFILES[rec.ACTIVE_PROFILE]
    assert rec.get_weights("client-ad") == rec.PROFILES["client-ad"]
    assert rec.get_weights("current") == rec.PROFILES["current"]
    with pytest.raises(KeyError, match="unknown weight profile"):
        rec.get_weights("does-not-exist")


# ---------------------------------------------------------------------------
# Switchable behaviour at the API level
# ---------------------------------------------------------------------------
def test_recommend_stamps_profile_in_meta(db):
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E", "#FFFFFF"],
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000,
        "materials": ["wood"],
        "patterns": ["solid"],
    }
    for profile in ("current", "client-ad"):
        res = rec.recommend(db, quiz, use_cache=False, profile=profile)
        meta = res["meta"]
        assert meta["weights_profile"] == profile
        assert meta["weights"] == rec.PROFILES[profile]
        assert meta["weights_version"] == RECOMMENDER_CONFIG_VERSION


def test_profiles_can_rank_differently_but_deterministically(db):
    """The canonical harness quiz (the one whose delta is documented in
    docs/reports/weights_profiles.md) must produce a VISIBLE ranking
    difference between profiles — otherwise the decision item C-6 would be
    decorative — and each profile must be deterministic."""
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E", "#FFFFFF"],
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000,
        "materials": ["wood"],
        "patterns": ["solid"],
    }
    a1 = rec.recommend(db, quiz, use_cache=False, profile="current")
    a2 = rec.recommend(db, quiz, use_cache=False, profile="current")
    b1 = rec.recommend(db, quiz, use_cache=False, profile="client-ad")
    b2 = rec.recommend(db, quiz, use_cache=False, profile="client-ad")

    def order(res):
        return {c: [i["id"] for i in items] for c, items in res["categories"].items()}

    assert order(a1) == order(a2)  # deterministic within a profile
    assert order(b1) == order(b2)
    differ = any(
        order(a1).get(c) != order(b1).get(c)
        for c in set(order(a1)) | set(order(b1))
    )
    assert differ, "profiles rank the canonical catalog identically — the C-6 " \
        "decision would have no effect; check the weight deltas"


def test_cache_keys_separate_profiles(db):
    """Two profiles, same quiz: the second must NOT be served from the first
    profile's cache entry (cache identity includes the profile name)."""
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E"],
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000,
        "materials": ["wood"],
        "patterns": ["solid"],
    }
    first = rec.recommend(db, quiz, use_cache=True, profile="current")
    assert first["cached"] is False
    second = rec.recommend(db, quiz, use_cache=True, profile="client-ad")
    assert second["cached"] is False, "client-ad must not read the current-profile cache"
    assert second["meta"]["weights_profile"] == "client-ad"
    third = rec.recommend(db, quiz, use_cache=True, profile="current")
    assert third["cached"] is True, "same profile+quiz must hit the cache"


# ---------------------------------------------------------------------------
# Acceptance parity: the 18-scenario harness under both profiles
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("profile", ["current", "client-ad"])
def test_full_scenario_harness_passes_under_profile(profile):
    """Every acceptance scenario passes under both profiles (or the deviation
    is itemised in docs/reports/weights_profiles.md — the harness prints it)."""
    import scripts.evaluate_recommender as harness

    db = harness.fresh_db()
    for name, fn in harness.build_scenarios(db, profile):
        harness.check(name, fn)
    failures = [r for r in harness.RESULTS if r["status"] != "PASS"]
    detail = "\n".join(f"{r['scenario']}: {r['detail']}" for r in failures)
    assert not failures, f"scenario failures under {profile!r}:\n{detail}"
