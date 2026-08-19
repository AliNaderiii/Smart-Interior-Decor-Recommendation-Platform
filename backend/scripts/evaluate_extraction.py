"""Evaluate AI feature extraction against the 50-image benchmark.

Usage:
    python scripts/evaluate_extraction.py

Scoring per image (matches docs/ARCHITECTURE.md §Benchmarks):
    style_hit   (0.5): at least one predicted style in ground-truth styles
    material    (0.5): precision of predicted materials (a hallucinated
                       material is an error; missing a secondary material
                       is not, since the primary drives recommendations)

Acceptance criterion: mean accuracy >= 0.80 across all 50 images.
Works with any provider selected via AI_PROVIDER (gemini | openai | mock).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.feature_extractor import FeatureExtractor  # noqa: E402

BENCHMARK = Path(__file__).resolve().parents[1] / "tests" / "benchmark_50_images.json"


def score_item(pred: dict, truth: dict) -> float:
    """Score one prediction against ground truth (0..1)."""
    style_hit = 0.5 if set(pred.get("style", [])) & set(truth["style"]) else 0.0
    pm, tm = set(pred.get("material", [])), set(truth["material"])
    material = 0.5 * (len(pm & tm) / len(pm)) if pm else 0.0
    return style_hit + material


def main() -> int:
    data = json.loads(BENCHMARK.read_text())
    extractor = FeatureExtractor()
    scores: list[float] = []
    failures: list[int] = []

    for item in data["items"]:
        pred = extractor.extract(item["image_url"])
        s = score_item(pred, item["ground_truth"])
        scores.append(s)
        if s < 0.8:
            failures.append(item["id"])

    accuracy = sum(scores) / len(scores)
    print(f"images evaluated : {len(scores)}")
    print(f"mean accuracy    : {accuracy:.1%}")
    print(f"images >= 0.8    : {sum(1 for s in scores if s >= 0.8)}/{len(scores)}")
    if failures:
        print(f"below threshold  : {failures}")
    if accuracy >= 0.80:
        print("RESULT: PASS (>= 80% required)")
        return 0
    print("RESULT: FAIL (< 80%)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
