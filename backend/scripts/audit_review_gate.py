#!/usr/bin/env python
"""Replay the human-review gate against a committed REAL benchmark artefact.

Usage:
    python scripts/audit_review_gate.py                       # docs/reports/extraction_report.json
    python scripts/audit_review_gate.py --report PATH.json    # another artefact
    python scripts/audit_review_gate.py --json OUT.json       # machine-readable summary

Why this exists
---------------
``scripts/evaluate_extraction.py`` measures *accuracy*; this script measures
the *gate* — the only thing standing between a wrong extraction and a
recommendation. It needs no API key: it re-runs ``review_decision`` over the
per-item predictions already embedded in the artefact and reports, for the
items the gate would let through unflagged, how many were actually wrong.

It answers the question a reviewer of the 2026-09-02 run should have asked:
"the model said 0.95 on 48/50 images and 21/50 were below the bar — what did
the confidence threshold actually catch?" (Answer: nothing. Hence
``ambiguous_style``.)

Exit codes: 0 = report produced; 1 = artefact missing or not a REAL run
(a MOCK artefact says nothing about the gate).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.extraction_review import review_decision  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = BACKEND / ".." / "docs" / "reports" / "extraction_report.json"
BENCHMARK = BACKEND / "tests" / "benchmark_50_images.json"
ITEM_BAR = 0.8  # per-item "correct" bar used by evaluate_extraction.py


def replay(report: dict, truth_by_id: dict[int, dict]) -> dict:
    """Pure function: gate decisions + outcome split for one artefact."""
    rows = []
    for item in report["items"]:
        decision = review_decision({
            "confidence": item.get("confidence", 0.0),
            "style": item.get("predicted_style") or [],
            "material": item.get("predicted_material") or [],
            "provider_error": item.get("provider_error"),
            "provider": item.get("provider"),
            "unknown_taxonomy_values": item.get("unknown_taxonomy_values") or [],
        })
        truth = truth_by_id[item["id"]]["ground_truth"]
        style_hit = bool(set(item.get("predicted_style") or []) & set(truth["style"]))
        rows.append({
            "id": item["id"],
            "score": item["score"],
            "correct": item["score"] >= ITEM_BAR,
            "style_hit": style_hit,
            "flagged": decision["needs_review"],
            "reasons": decision["review_reasons"],
            "flagged_in_artefact": bool(item.get("needs_review")),
        })

    def _summary(members: list[dict]) -> dict:
        n = len(members)
        return {
            "n": n,
            "correct": sum(r["correct"] for r in members),
            "style_hit": sum(r["style_hit"] for r in members),
            "mean_score": round(sum(r["score"] for r in members) / n, 4) if n else None,
            "wrong_style_ids": [r["id"] for r in members if not r["style_hit"]],
        }

    passed = [r for r in rows if not r["flagged"]]
    flagged = [r for r in rows if r["flagged"]]
    return {
        "items": len(rows),
        "flagged_by_artefact": sum(r["flagged_in_artefact"] for r in rows),
        "flagged_by_current_gate": len(flagged),
        "reason_frequency": dict(Counter(reason for r in flagged for reason in r["reasons"])),
        "passed_unflagged": _summary(passed),
        "flagged": _summary(flagged),
        # A style miss that the gate did not flag is the failure mode that
        # matters: it would enter the catalogue looking trustworthy.
        "unflagged_style_misses": [r["id"] for r in passed if not r["style_hit"]],
        "rows": rows,
    }


def main() -> int:
    report_path = DEFAULT_REPORT
    if "--report" in sys.argv:
        report_path = Path(sys.argv[sys.argv.index("--report") + 1])
    json_out = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else None

    if not report_path.is_file():
        print(f"ERROR: no artefact at {report_path}")
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("is_mock") or not str(report.get("mode", "")).startswith("REAL"):
        print(f"ERROR: {report_path} is not a REAL run (mode={report.get('mode')!r}); "
              "the gate replay is only meaningful on vision-model output.")
        return 1
    truth = {i["id"]: i for i in json.loads(BENCHMARK.read_text(encoding="utf-8"))["items"]}
    out = replay(report, truth)

    ext = report["versions"]["extraction"]
    print("=" * 72)
    print(f"artefact         : {report_path.name}  ({report['mode']}, {ext['model']}, "
          f"prompt {ext['prompt_version']}, taxonomy {ext['taxonomy_version']})")
    print(f"items            : {out['items']}   mean accuracy in artefact: {report['mean_accuracy']:.1%}")
    print(f"flagged          : {out['flagged_by_artefact']} at run time  ->  "
          f"{out['flagged_by_current_gate']} with the current gate")
    print(f"reasons          : {out['reason_frequency'] or '-'}")
    p, f = out["passed_unflagged"], out["flagged"]
    print(f"passed unflagged : n={p['n']:<3} style-hit {p['style_hit']}/{p['n']}  "
          f">=0.8: {p['correct']}/{p['n']}  mean {p['mean_score']}")
    if f["n"]:
        print(f"flagged          : n={f['n']:<3} style-hit {f['style_hit']}/{f['n']}  "
              f">=0.8: {f['correct']}/{f['n']}  mean {f['mean_score']}")
    print(f"unflagged style misses: {out['unflagged_style_misses'] or 'none'}")
    print("=" * 72)

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(f"summary written  : {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
