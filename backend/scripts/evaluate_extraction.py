"""Evaluate AI feature extraction against the 50-image benchmark.

Usage:
    python scripts/evaluate_extraction.py            # provider from AI_PROVIDER
    python scripts/evaluate_extraction.py --real     # force real provider
    python scripts/evaluate_extraction.py --sample 5 # limit images (REAL mode
                                                     # cost control)

Modes
-----
MOCK (CI default): `AI_PROVIDER=mock` — the deterministic heuristic extractor.
    Keeps CI hermetic and offline; the 100% score is a harness baseline, NOT a
    claim about vision-model quality.

REAL: set `AI_PROVIDER=gemini` + `GEMINI_API_KEY` (or openai + key) — the same
    50 images and ground truth are scored against the live vision model. Use
    `--sample N` to evaluate a subset first (API cost control). If accuracy
    lands below 80%, the script prints a graceful-degradation notice instead
    of masking the number.

Scoring per image (matches docs/ARCHITECTURE.md §Benchmarks):
    style_hit   (0.5): at least one predicted style in ground-truth styles
    material    (0.5): precision of predicted materials (a hallucinated
                       material is an error; missing a secondary material
                       is not, since the primary drives recommendations)

Acceptance criterion: mean accuracy >= 0.80.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.feature_extractor import FeatureExtractor  # noqa: E402
from app.core.config import settings  # noqa: E402

BENCHMARK = Path(__file__).resolve().parents[1] / "tests" / "benchmark_50_images.json"
REPORT = Path(__file__).resolve().parents[1] / ".." / "docs" / "reports" / "extraction_report.json"


def score_item(pred: dict, truth: dict) -> float:
    """Score one prediction against ground truth (0..1)."""
    style_hit = 0.5 if set(pred.get("style", [])) & set(truth["style"]) else 0.0
    pm, tm = set(pred.get("material", [])), set(truth["material"])
    material = 0.5 * (len(pm & tm) / len(pm)) if pm else 0.0
    return style_hit + material


def resolve_mode(force_real: bool) -> str:
    """Determine whether we run against a real vision provider or the mock."""
    if settings.AI_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        return "REAL:gemini"
    if settings.AI_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return "REAL:openai"
    if force_real:
        raise SystemExit(
            "ERROR: --real requires AI_PROVIDER=gemini|openai and the matching "
            "API key in the environment."
        )
    return "MOCK"


def main() -> int:
    force_real = "--real" in sys.argv
    sample = 0
    if "--sample" in sys.argv:
        sample = int(sys.argv[sys.argv.index("--sample") + 1])

    mode = resolve_mode(force_real)
    data = json.loads(BENCHMARK.read_text())
    items = data["items"][:sample] if sample else data["items"]

    extractor = FeatureExtractor()
    scores: list[float] = []
    failures: list[int] = []
    for item in items:
        pred = extractor.extract(item["image_url"])
        s = score_item(pred, item["ground_truth"])
        scores.append(s)
        if s < 0.8:
            failures.append(item["id"])

    accuracy = sum(scores) / len(scores)
    print(f"mode             : {mode}")
    print(f"images evaluated : {len(scores)}")
    print(f"mean accuracy    : {accuracy:.1%}")
    print(f"images >= 0.8    : {sum(1 for s in scores if s >= 0.8)}/{len(scores)}")
    if failures:
        print(f"below threshold  : {failures}")

    try:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({
            "mode": mode, "images": len(scores),
            "accuracy": round(accuracy, 4), "failures": failures,
        }, indent=2))
    except OSError:
        pass

    if accuracy >= 0.80:
        print("RESULT: PASS (>= 80% required)")
        return 0
    if mode.startswith("REAL"):
        print(
            "RESULT: BELOW TARGET — graceful degradation active: low-confidence "
            "extractions stay unverified and require human review before entering "
            "recommendations (human-in-the-loop gate). Tune the prompt or switch "
            "provider via AI_PROVIDER."
        )
    else:
        print("RESULT: FAIL (< 80%)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
