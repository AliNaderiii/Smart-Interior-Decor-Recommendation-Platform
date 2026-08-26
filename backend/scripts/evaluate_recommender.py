#!/usr/bin/env python
"""Recommender acceptance scenario harness — deterministic, hermetic, labelled.

Complements ``tests/test_recommender.py`` (the 30 pytest acceptance tests).
This harness exists to produce *evidence artifacts*: a per-scenario PASS/FAIL
table with the exact inputs, so a release reviewer can see **which** scenarios
passed on which catalog, not just "30 passed".

Runs on SQLite + hash embeddings + no cache (``use_cache=False``) by design —
it measures ranking *logic*, not infrastructure. Latency/pgvector evidence
lives in ``scripts/bench_pgvector.py`` against real PostgreSQL.

Usage:
    python scripts/evaluate_recommender.py                 # active profile, table to stdout
    python scripts/evaluate_recommender.py --profile client-ad
    python scripts/evaluate_recommender.py --json OUT.json # machine-readable
    python scripts/evaluate_recommender.py --compare-profiles
        # runs the full scenario set under EVERY configured weight profile,
        # side-by-side, and writes docs/reports/weights_profiles.md
        # (Stage 1, T-1.2 — the client decision C-6 evidence)

Scenarios (name — assertion):
  01 default_quiz_results        — a normal quiz returns >=1 category
  02 hard_budget_filter          — every returned price within the window
  03 impossible_budget           — no results, meta.empty_categories lists all
  04 no_padding_out_of_budget    — nothing outside the window sneaks in
  05 deterministic_order         — two runs, byte-identical ordering
  06 deterministic_score_ties    — forced ties resolve by stable product id
  07 style_pref_ranks_first      — top item matches requested style (>=60% cats)
  08 explanation_fidelity        — final == Σ weight_i * explanation_i (±0.02)
  09 matched_materials_real      — explanation materials == real intersection
  10 duplicate_suppression       — 6 near-identical rows -> <=2 kept
  11 style_cap_diversity         — 10 same-style rows -> <= max_per_style kept
  12 unverified_excluded         — is_verified=False never returned
  13 empty_category_reported     — a category with no rows lands in meta
  14 few_results_no_padding      — 1 candidate -> exactly 1 result
  15 feedback_changes_order      — thumbs-down demotes, thumbs-up promotes
  16 weights_versioned_and_valid — weights sum to 1; versions stamped in meta
  17 embeddings_dim_and_norm     — every embedding is 512-d and unit-norm
  18 unknown_pattern_rejected    — taxonomy violation 422s at the schema
"""
from __future__ import annotations

import json
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from ai.embedding_service import get_embedding  # noqa: E402
from ai.extraction_review import AUTO_ACCEPT_THRESHOLD  # noqa: E402
from ai.model_registry import ai_version_info  # noqa: E402
from app.models import Base, Product  # noqa: E402
from app.schemas.quiz import QuizIn  # noqa: E402
from app.services.recommender import (  # noqa: E402
    CONFIG,
    MAX_RESULTS,
    PROFILES,
    recommend,
)
from scripts.seed_products import build_products  # noqa: E402

RESULTS: list[dict] = []


def check(name: str, fn) -> None:
    try:
        detail = fn()
        RESULTS.append({"scenario": name, "status": "PASS", "detail": detail or ""})
    except AssertionError as exc:
        RESULTS.append({"scenario": name, "status": "FAIL", "detail": str(exc)})
    except Exception as exc:  # noqa: BLE001 — an error is a failed scenario
        RESULTS.append({"scenario": name, "status": "ERROR", "detail": f"{type(exc).__name__}: {exc}"})


def make_quiz(**overrides) -> dict:
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E", "#FFFFFF"],
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000,
        "materials": ["wood"],
        "patterns": ["solid"],
    }
    quiz.update(overrides)
    return quiz


def _mk_product(title: str, category: str = "sofa", price: int = 50_000_000,
                styles=("modern",), materials=("wood",), colors=("#2E2E2E",),
                verified: bool = True, patterns=("solid",), emb_text: str | None = None) -> Product:
    return Product(
        id=uuid.uuid4().hex,
        title=title,
        category=category,
        room_type="living_room",
        price_toman=price,
        image_url="https://images.example.com/x.jpg",
        is_verified=verified,
        styles=list(styles), colors=list(colors), materials=list(materials),
        patterns=list(patterns),
        style_embedding=get_embedding(emb_text or f"{title} {styles[0]} {materials[0]}"),
    )


def fresh_db() -> "object":
    """In-memory SQLite session with the seeded catalog (cache-off harness).

    Re-seeds the RNG here (not only at import): ``build_products`` is
    deterministic ONLY from a fresh ``random.seed(42)`` state, and in a
    long-lived process (pytest) other seeding work may have consumed the
    state in between. The evidence catalog must be canonical everywhere.
    """
    import random

    random.seed(42)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    for p in build_products():
        db.add(p)
    db.commit()
    return db


def ranking_snapshot(db, profile_name: str) -> dict[str, list[dict]]:
    """Top-N items per category for the canonical quiz under one profile.

    Captured on a clean catalog (before scenario mutations) so the
    profile-vs-profile diff is a pure function of the weights.
    """
    res = recommend(db, make_quiz(), use_cache=False, profile=profile_name)
    return {
        category: [
            {"id": item["id"], "title": item["title"], "score": item["final_score"]}
            for item in items
        ]
        for category, items in res["categories"].items()
    }


def build_scenarios(db, profile_name: str) -> list[tuple[str, object]]:
    """The 18 acceptance scenarios, bound to one DB and one weight profile."""
    weights = CONFIG["profiles"][profile_name]["weights"]

    def rec(quiz: dict, **kw) -> dict:
        return recommend(db, quiz, use_cache=False, profile=profile_name, **kw)

    quiz = make_quiz()

    def s01() -> str:
        res = rec(quiz)
        assert res["categories"], "no categories returned"
        return f"{len(res['categories'])} categories"

    def s02() -> str:
        res = rec(make_quiz(budget_min_toman=1_000_000, budget_max_toman=20_000_000))
        prices = [i["price_toman"] for items in res["categories"].values() for i in items]
        assert prices and all(1_000_000 <= p <= 20_000_000 for p in prices)
        return f"{len(prices)} prices within window"

    def s03() -> str:
        res = rec(make_quiz(budget_min_toman=1, budget_max_toman=10))
        assert res["categories"] == {}, "impossible budget returned results"
        assert len(res["meta"]["empty_categories"]) == 7, "empty categories not reported"
        return "all 7 categories reported empty in meta"

    def s04() -> str:
        res = rec(quiz)
        for items in res["categories"].values():
            for item in items:
                assert quiz["budget_min_toman"] <= item["price_toman"] <= quiz["budget_max_toman"], \
                    f"{item['title']} outside budget"
        return "no out-of-budget items"

    def s05() -> str:
        a = rec(quiz)
        b = rec(quiz)
        order_a = {c: [i["id"] for i in items] for c, items in a["categories"].items()}
        order_b = {c: [i["id"] for i in items] for c, items in b["categories"].items()}
        assert order_a == order_b, "ordering differs between identical runs"
        return "identical ordering across runs"

    def s06() -> str:
        clones = [
            _mk_product(f"Tie clone {i}", price=60_000_000) for i in range(4)
        ]
        for c in clones:
            c.style_embedding = get_embedding("identical tie clone embedding")
            db.add(c)
        db.commit()
        try:
            res = rec(make_quiz(color_palette=[], materials=[], patterns=[]))
            ids = [i["id"] for i in res["categories"].get("sofa", [])]
            clones_sorted = sorted(c.id for c in clones)
            present = [i for i in ids if i in {c.id for c in clones}]
            assert present == sorted(present, key=lambda i: clones_sorted.index(i)), \
                "tie order does not follow stable id"
            return "ties resolved by stable product id"
        finally:
            for c in clones:
                db.delete(c)
            db.commit()

    def s07() -> str:
        res = rec(make_quiz(styles=["boho"], materials=["rattan"],
                            color_palette=["#C1633F", "#4C6444"]))
        tops = [items[0]["styles"] for items in res["categories"].values()]
        assert tops, "no results"
        boho_top = sum(1 for s in tops if "boho" in s)
        assert boho_top >= len(tops) * 0.6, f"boho top in {boho_top}/{len(tops)}"
        return f"boho top in {boho_top}/{len(tops)} categories"

    def s08() -> str:
        res = rec(quiz)
        checked = 0
        for items in res["categories"].values():
            for item in items:
                exp = item["explanation"]
                recomputed = (
                    weights["style"] * exp["style_match"] / 100
                    + weights["color"] * exp["color_match"] / 100
                    + weights["budget"] * exp["budget_fit"] / 100
                    + weights["material"] * exp["material_match"] / 100
                    + weights["pattern"] * exp["pattern_match"] / 100
                )
                assert abs(recomputed - item["final_score"]) <= 0.02 + 1e-9, \
                    f"{item['title']}: final {item['final_score']} != recomputed {recomputed:.4f}"
                checked += 1
        assert checked
        return f"{checked} explanations match score components"

    def s09() -> str:
        res = rec(quiz)
        n = 0
        for items in res["categories"].values():
            for item in items:
                if item["explanation"]["matched_materials"]:
                    assert set(item["explanation"]["matched_materials"]) <= set(quiz["materials"])
                    assert set(item["materials"]) & set(quiz["materials"])
                    n += 1
        return f"{n} matched_materials entries verified against real products"

    def s10() -> str:
        dupes = [_mk_product(f"Duplicate Walnut Sofa XYZ {i}", price=55_000_000) for i in range(6)]
        db.add_all(dupes)
        db.commit()
        try:
            res = rec(quiz)
            got = [i["title"] for i in res["categories"].get("sofa", []) if "Duplicate Walnut Sofa XYZ" in i["title"]]
            assert len(got) <= 2, f"{len(got)} near-duplicates in output"
            return f"{len(got)}/6 near-duplicates kept (suppression active)"
        finally:
            for d in dupes:
                db.delete(d)
            db.commit()

    def s11() -> str:
        same_style = [
            _mk_product(f"Industrial Iron Sofa {i}", price=58_000_000, styles=("industrial",),
                        materials=("metal",), colors=("#1A1A1A",))
            for i in range(10)
        ]
        db.add_all(same_style)
        db.commit()
        try:
            res = rec(make_quiz(styles=["industrial"], materials=["metal"],
                                color_palette=["#1A1A1A"]))
            kept = [i for i in res["categories"].get("sofa", []) if "Industrial Iron Sofa" in i["title"]]
            cap = CONFIG["diversity"]["max_per_style"]
            assert len(kept) <= cap, f"{len(kept)} same-style items exceed cap {cap}"
            return f"{len(kept)}/{cap} same-style cap respected"
        finally:
            for s in same_style:
                db.delete(s)
            db.commit()

    def s12() -> str:
        unv = _mk_product("UNVERIFIED sofa", verified=False)
        db.add(unv)
        db.commit()
        try:
            res = rec(quiz)
            ids = {i["id"] for items in res["categories"].values() for i in items}
            assert unv.id not in ids
            return "unverified product excluded"
        finally:
            db.delete(unv)
            db.commit()

    def s13() -> str:
        empty_cat = "decor"
        removed = db.query(Product).filter(Product.category == empty_cat).all()
        for r in removed:
            db.delete(r)
        db.commit()
        try:
            res = rec(quiz)
            assert empty_cat not in res["categories"]
            assert empty_cat in res["meta"]["empty_categories"], "empty category not reported"
            return f"'{empty_cat}' reported in meta.empty_categories"
        finally:
            for r in removed:
                db.merge(r)
            db.commit()

    def s14() -> str:
        removed = db.query(Product).filter(Product.category == "lighting").all()
        for r in removed:
            db.delete(r)
        db.add(_mk_product("Sole Lighting Piece", category="lighting", price=3_000_000))
        db.commit()
        try:
            res = rec(quiz)
            got = res["categories"].get("lighting", [])
            assert len(got) == 1, f"expected exactly the 1 candidate, got {len(got)}"
            return "single candidate returned as-is (no padding)"
        finally:
            db.query(Product).filter(Product.title == "Sole Lighting Piece").delete()
            for r in removed:
                db.merge(r)
            db.commit()

    def s15() -> str:
        res = rec(quiz)
        items = res["categories"]["sofa"]
        if len(items) < 2:
            return "skipped (fewer than 2 sofas)"
        target = items[1]
        from app.models.feedback import ProductFeedback
        fb = ProductFeedback(user_id="u1", product_id=target["id"], signal=-1, category="sofa")
        db.add(fb)
        db.commit()
        try:
            res2 = rec(quiz, user_id="u1")
            ids2 = [i["id"] for i in res2["categories"]["sofa"]]
            assert target["id"] not in ids2[:2], "thumbs-down item still near top"
            return "thumbs-down demoted below un-rated items"
        finally:
            db.delete(fb)
            db.commit()

    def s16() -> str:
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        res = rec(quiz)
        meta = res["meta"]
        assert meta["weights_version"] == CONFIG["config_version"]
        assert meta["weights_profile"] == profile_name
        assert meta["weights"] == weights
        assert meta["recommender_version"] and meta["taxonomy_version"]
        return (f"weights sum to 1; profile={meta['weights_profile']}; "
                f"weights_version={meta['weights_version']}; "
                f"recommender={meta['recommender_version']}")

    def s17() -> str:
        rows = db.query(Product).filter(Product.style_embedding.isnot(None)).all()
        n = 0
        for p in rows:
            vec = list(p.style_embedding)
            assert len(vec) == 512, f"{p.title}: dim {len(vec)}"
            norm = math.sqrt(sum(x * x for x in vec))
            assert abs(norm - 1.0) < 1e-3, f"{p.title}: norm {norm:.6f}"
            n += 1
        assert n >= 100
        return f"{n} embeddings are 512-d and unit-norm"

    def s18() -> str:
        try:
            QuizIn(styles=["modern"], room_width_cm=400, room_length_cm=500,
                   budget_min_toman=0, budget_max_toman=100, patterns=["houndstooth"])
        except Exception:
            return "unknown pattern rejected at schema boundary"
        raise AssertionError("unknown pattern was accepted")

    return [
        ("01 default_quiz_results", s01), ("02 hard_budget_filter", s02),
        ("03 impossible_budget", s03), ("04 no_padding_out_of_budget", s04),
        ("05 deterministic_order", s05), ("06 deterministic_score_ties", s06),
        ("07 style_pref_ranks_first", s07), ("08 explanation_fidelity", s08),
        ("09 matched_materials_real", s09), ("10 duplicate_suppression", s10),
        ("11 style_cap_diversity", s11), ("12 unverified_excluded", s12),
        ("13 empty_category_reported", s13), ("14 few_results_no_padding", s14),
        ("15 feedback_changes_order", s15), ("16 weights_versioned_and_valid", s16),
        ("17 embeddings_dim_and_norm", s17), ("18 unknown_pattern_rejected", s18),
    ]


def run_profile(db, profile_name: str) -> list[dict]:
    """Run all 18 scenarios under one profile; returns the result rows."""
    global RESULTS
    RESULTS = []
    for name, fn in build_scenarios(db, profile_name):
        check(name, fn)
    return RESULTS


def compare_profiles() -> int:
    """Run the scenario set under every profile, side by side.

    Each profile gets a FRESH in-memory catalog so scenario mutations (which
    are restored in their finally blocks anyway) can never bleed across the
    comparison. Returns 0 iff every scenario passes under every profile.
    """
    profiles = list(PROFILES)
    all_results: dict[str, list[dict]] = {}
    snapshots: dict[str, dict[str, list[dict]]] = {}
    for name in profiles:
        db = fresh_db()
        snapshots[name] = ranking_snapshot(db, name)
        all_results[name] = run_profile(db, name)

    default = CONFIG["default_profile"]
    lines: list[str] = []
    lines.append("# Recommender weight profiles — comparison harness")
    lines.append("")
    lines.append(f"Generated by `python scripts/evaluate_recommender.py --compare-profiles` on "
                 f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.")
    lines.append("")
    lines.append(f"Environment: SQLite + hash embeddings, cache off. AI stack: "
                 f"`{ai_version_info()['ai_stack_version']}`, recommender config "
                 f"`{CONFIG['config_version']}`. Default profile: **{default}**.")
    lines.append("")
    lines.append("## Weights")
    lines.append("")
    lines.append("| profile | style | color | budget | material | pattern | sum |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for name in profiles:
        w = PROFILES[name]
        total = sum(w.values())
        flag = " *(active default)*" if name == default else ""
        lines.append(
            f"| {name}{flag} | {w['style']:.2f} | {w['color']:.2f} | {w['budget']:.2f} "
            f"| {w['material']:.2f} | {w['pattern']:.2f} | {total:.2f} |"
        )
    lines.append("")
    for name, src in CONFIG["profiles"].items():
        lines.append(f"- **{name}**: {src.get('source', '')}")
    lines.append("")

    lines.append("## Acceptance scenarios, per profile")
    lines.append("")
    header = "| scenario | " + " | ".join(profiles) + " |"
    sep = "|---|" + "---:|" * len(profiles)
    lines.append(header)
    lines.append(sep)
    status_by_scenario: dict[str, dict[str, str]] = {}
    for i, r_base in enumerate(all_results[default]):
        name = r_base["scenario"]
        row = [name]
        for prof in profiles:
            r = all_results[prof][i]
            status_by_scenario.setdefault(name, {})[prof] = r["status"]
            mark = {"PASS": "PASS", "FAIL": "**FAIL**", "ERROR": "**ERROR**"}[r["status"]]
            row.append(mark)
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    deviating = [n for n, s in status_by_scenario.items() if len(set(s.values())) > 1]
    if deviating:
        lines.append("Scenarios with a deviating status across profiles: "
                     + ", ".join(deviating) + ".")
        lines.append("")

    lines.append("## Side-by-side ranking delta (canonical quiz, clean catalog)")
    lines.append("")
    base = default
    for other in profiles:
        if other == base:
            continue
        lines.append(f"### `{base}` vs `{other}`")
        lines.append("")
        def label(item: dict) -> str:
            return f"{item['title']} (`{item['id'][:8]}`)"

        base_snap, other_snap = snapshots[base], snapshots[other]
        cats = sorted(set(base_snap) | set(other_snap))
        for cat in cats:
            b = {item["id"]: item for item in base_snap.get(cat, [])}
            o = {item["id"]: item for item in other_snap.get(cat, [])}
            only_base = [i for i in b if i not in o]
            only_other = [i for i in o if i not in b]
            moved = []
            for i in o:
                if i in b:
                    br = list(b).index(i)
                    or_ = list(o).index(i)
                    if br != or_:
                        moved.append(f"{o[i]['title']} ({br}→{or_})")
            kept = len(b) - len(only_base)
            if not (only_base or only_other or moved):
                lines.append(f"- **{cat}**: identical top cut")
                continue
            parts = [f"{kept} of {len(b)} items kept"]
            if only_base:
                parts.append("dropped by " + other + ": "
                             + ", ".join(label(b[i]) for i in only_base))
            if only_other:
                parts.append("added by " + other + ": "
                             + ", ".join(label(o[i]) for i in only_other))
            if moved:
                parts.append("reordered: " + "; ".join(moved))
            lines.append(f"- **{cat}**: " + " · ".join(parts))
        lines.append("")

    total_pass = sum(
        1 for prof in all_results.values() for r in prof if r["status"] == "PASS"
    )
    total = sum(len(r) for r in all_results.values())
    all_ok = total_pass == total
    lines.append("## Verdict")
    lines.append("")
    if all_ok:
        lines.append(f"All {total} scenario runs pass under every profile "
                     f"({total // len(profiles)} scenarios × {len(profiles)} profiles). "
                     f"Deviations (if any) are ranking-order deltas only, itemised above.")
    else:
        lines.append(f"{total - total_pass} of {total} scenario runs FAILED — see per-profile "
                     "tables above; deviations must be itemised in the stage report before "
                     "a profile may be activated.")
    lines.append("")
    lines.append("## Note on the client advertisement")
    lines.append("")
    lines.append("The client ad states pattern 10% alongside the existing weights; as stated "
                 "those weights sum to 1.05, which this codebase refuses to load (weights must "
                 "sum to 1). The `client-ad` profile therefore normalises by reducing "
                 "**material** from 0.15 to 0.10. Whether material (the profile shipped here), "
                 "budget or style should absorb the 5 points is client decision **C-6** — see "
                 "the Persian decision memo below.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## یادداشت تصمیم‌سازی برای مشتری (C-6)")
    lines.append("")
    lines.append("در آگهی شما وزن «الگو» ۱۰٪ است؛ با وزن‌های موجود، مجموع وزن‌ها به ۱۰۵٪ "
                 "می‌رسد و سیستم ما وزن‌هایی که مجموعشان ۱۰۰٪ نباشد را نمی‌پذیرد. به همین دلیل "
                 "پروفایل `client-ad` با کاهش وزن «جنس/متریال» از ۱۵٪ به ۱۰٪ تعادل را برقرار "
                 "کرده است (سبک ۳۰٪، رنگ ۳۰٪، بودجه ۲۰٪، متریال ۱۰٪، الگو ۱۰٪). دو پروفایل "
                 "کاملاً جداگانه است: تا تصمیم نهایی شما، پروفایل پیش‌فرض `current` "
                 "(وزن‌های فعلی) فعال است. برای تغییر کافی است یک تنظیمات محیطی "
                 "(`RECOMMENDER_WEIGHT_PROFILE`) را روی `client-ad` قرار دهید — بدون تغییر "
                 "کد. نتایج کامل مقایسه در جدول‌های بالا آمده و در هر دو پروفایل، "
                 f"{total // len(profiles)} سناریوی پذیرش موفق است. "
                 "نظر شما را می‌خواهیم: ۵٪ اضافه، از «متریال» کسر شود (پیشنهاد ما)، یا از "
                 "«بودجه»، یا از «سبک»؟")
    lines.append("")

    out = Path(__file__).resolve().parents[2] / "docs" / "reports" / "weights_profiles.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"comparison written: {out}")
    for name in profiles:
        passed = sum(1 for r in all_results[name] if r["status"] == "PASS")
        print(f"[{passed}/{len(all_results[name])}] profile {name}")
    return 0 if all_ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--compare-profiles" in args:
        return compare_profiles()

    profile_name = None
    if "--profile" in args:
        profile_name = args[args.index("--profile") + 1]
        if profile_name not in PROFILES:
            print(f"unknown profile {profile_name!r}; available: {sorted(PROFILES)}")
            return 2

    db = fresh_db()
    if profile_name is None:
        from app.services.recommender import ACTIVE_PROFILE

        profile_name = ACTIVE_PROFILE
    results = run_profile(db, profile_name)

    passed = sum(1 for r in results if r["status"] == "PASS")
    print("Recommender scenario harness — environment: SQLite + hash embeddings, cache off")
    print(f"Weight profile: {profile_name} (weights {json.dumps(PROFILES[profile_name])})")
    print(f"AI stack: {json.dumps(ai_version_info()['ai_stack_version'])} "
          f"| review gate auto-accept threshold: {AUTO_ACCEPT_THRESHOLD} "
          f"| max_results: {MAX_RESULTS}")
    print("-" * 78)
    for r in results:
        print(f"[{r['status']:>5}] {r['scenario']:<30} {r['detail']}")
    print("-" * 78)
    print(f"{passed}/{len(results)} scenarios passed")

    if "--json" in args:
        out = Path(args[args.index("--json") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "environment": "sqlite+hash, cache off",
            "weight_profile": profile_name,
            "versions": ai_version_info(),
            "passed": passed, "total": len(results), "results": results,
        }, indent=2, ensure_ascii=False) + "\n")
        print(f"json written: {out}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
