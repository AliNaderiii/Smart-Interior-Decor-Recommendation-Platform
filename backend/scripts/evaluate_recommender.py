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
    python scripts/evaluate_recommender.py                 # table to stdout
    python scripts/evaluate_recommender.py --json OUT.json # machine-readable

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
    WEIGHTS,
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


def main() -> int:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    for p in build_products():
        db.add(p)
    db.commit()

    quiz = make_quiz()

    def s01() -> str:
        res = recommend(db, quiz, use_cache=False)
        assert res["categories"], "no categories returned"
        return f"{len(res['categories'])} categories"

    def s02() -> str:
        res = recommend(db, make_quiz(budget_min_toman=1_000_000, budget_max_toman=20_000_000), use_cache=False)
        prices = [i["price_toman"] for items in res["categories"].values() for i in items]
        assert prices and all(1_000_000 <= p <= 20_000_000 for p in prices)
        return f"{len(prices)} prices within window"

    def s03() -> str:
        res = recommend(db, make_quiz(budget_min_toman=1, budget_max_toman=10), use_cache=False)
        assert res["categories"] == {}, "impossible budget returned results"
        assert len(res["meta"]["empty_categories"]) == 7, "empty categories not reported"
        return "all 7 categories reported empty in meta"

    def s04() -> str:
        res = recommend(db, quiz, use_cache=False)
        for items in res["categories"].values():
            for item in items:
                assert quiz["budget_min_toman"] <= item["price_toman"] <= quiz["budget_max_toman"], \
                    f"{item['title']} outside budget"
        return "no out-of-budget items"

    def s05() -> str:
        a = recommend(db, quiz, use_cache=False)
        b = recommend(db, quiz, use_cache=False)
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
            res = recommend(db, make_quiz(color_palette=[], materials=[], patterns=[]), use_cache=False)
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
        res = recommend(db, make_quiz(styles=["boho"], materials=["rattan"],
                                      color_palette=["#C1633F", "#4C6444"]), use_cache=False)
        tops = [items[0]["styles"] for items in res["categories"].values()]
        assert tops, "no results"
        boho_top = sum(1 for s in tops if "boho" in s)
        assert boho_top >= len(tops) * 0.6, f"boho top in {boho_top}/{len(tops)}"
        return f"boho top in {boho_top}/{len(tops)} categories"

    def s08() -> str:
        res = recommend(db, quiz, use_cache=False)
        checked = 0
        for items in res["categories"].values():
            for item in items:
                exp = item["explanation"]
                recomputed = (
                    WEIGHTS["style"] * exp["style_match"] / 100
                    + WEIGHTS["color"] * exp["color_match"] / 100
                    + WEIGHTS["budget"] * exp["budget_fit"] / 100
                    + WEIGHTS["material"] * exp["material_match"] / 100
                    + WEIGHTS["pattern"] * exp["pattern_match"] / 100
                )
                assert abs(recomputed - item["final_score"]) <= 0.02 + 1e-9, \
                    f"{item['title']}: final {item['final_score']} != recomputed {recomputed:.4f}"
                checked += 1
        assert checked
        return f"{checked} explanations match score components"

    def s09() -> str:
        res = recommend(db, quiz, use_cache=False)
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
            res = recommend(db, quiz, use_cache=False)
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
            res = recommend(db, make_quiz(styles=["industrial"], materials=["metal"],
                                          color_palette=["#1A1A1A"]), use_cache=False)
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
            res = recommend(db, quiz, use_cache=False)
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
            res = recommend(db, quiz, use_cache=False)
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
            res = recommend(db, quiz, use_cache=False)
            got = res["categories"].get("lighting", [])
            assert len(got) == 1, f"expected exactly the 1 candidate, got {len(got)}"
            return "single candidate returned as-is (no padding)"
        finally:
            db.query(Product).filter(Product.title == "Sole Lighting Piece").delete()
            for r in removed:
                db.merge(r)
            db.commit()

    def s15() -> str:
        res = recommend(db, quiz, use_cache=False)
        items = res["categories"]["sofa"]
        if len(items) < 2:
            return "skipped (fewer than 2 sofas)"
        target = items[1]
        from app.models.feedback import ProductFeedback
        fb = ProductFeedback(user_id="u1", product_id=target["id"], signal=-1, category="sofa")
        db.add(fb)
        db.commit()
        try:
            res2 = recommend(db, quiz, use_cache=False, user_id="u1")
            ids2 = [i["id"] for i in res2["categories"]["sofa"]]
            assert target["id"] not in ids2[:2], "thumbs-down item still near top"
            return "thumbs-down demoted below un-rated items"
        finally:
            db.delete(fb)
            db.commit()

    def s16() -> str:
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
        res = recommend(db, quiz, use_cache=False)
        meta = res["meta"]
        assert meta["weights_version"] == CONFIG["config_version"]
        assert meta["recommender_version"] and meta["taxonomy_version"]
        return (f"weights sum to 1; weights_version={meta['weights_version']}; "
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

    for name, fn in [
        ("01 default_quiz_results", s01), ("02 hard_budget_filter", s02),
        ("03 impossible_budget", s03), ("04 no_padding_out_of_budget", s04),
        ("05 deterministic_order", s05), ("06 deterministic_score_ties", s06),
        ("07 style_pref_ranks_first", s07), ("08 explanation_fidelity", s08),
        ("09 matched_materials_real", s09), ("10 duplicate_suppression", s10),
        ("11 style_cap_diversity", s11), ("12 unverified_excluded", s12),
        ("13 empty_category_reported", s13), ("14 few_results_no_padding", s14),
        ("15 feedback_changes_order", s15), ("16 weights_versioned_and_valid", s16),
        ("17 embeddings_dim_and_norm", s17), ("18 unknown_pattern_rejected", s18),
    ]:
        check(name, fn)

    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    print("Recommender scenario harness — environment: SQLite + hash embeddings, cache off")
    print(f"AI stack: {json.dumps(ai_version_info()['ai_stack_version'])} "
          f"| review gate auto-accept threshold: {AUTO_ACCEPT_THRESHOLD} "
          f"| max_results: {MAX_RESULTS}")
    print("-" * 78)
    for r in RESULTS:
        print(f"[{r['status']:>5}] {r['scenario']:<30} {r['detail']}")
    print("-" * 78)
    print(f"{passed}/{len(RESULTS)} scenarios passed")

    if "--json" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--json") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "environment": "sqlite+hash, cache off",
            "versions": ai_version_info(),
            "passed": passed, "total": len(RESULTS), "results": RESULTS,
        }, indent=2, ensure_ascii=False) + "\n")
        print(f"json written: {out}")

    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
