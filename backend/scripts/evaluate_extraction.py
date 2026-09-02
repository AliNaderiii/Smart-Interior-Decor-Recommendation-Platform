#!/usr/bin/env python
"""Evaluate AI feature extraction against the 50-image benchmark.

Usage:
    python scripts/evaluate_extraction.py                 # provider from AI_PROVIDER
    python scripts/evaluate_extraction.py --real          # force real provider
    python scripts/evaluate_extraction.py --sample 5      # limit images (REAL mode
                                                          # cost control)
    python scripts/evaluate_extraction.py --json OUT.json # machine-readable report
    python scripts/evaluate_extraction.py --images-dir D  # real local images for
                                                          # REAL mode (see below)

Modes
-----
MOCK (CI default): ``AI_PROVIDER=mock`` — the deterministic heuristic extractor.
The score is a **harness baseline only**. It is NOT a claim about vision-model
quality and every artifact this script writes labels the mode explicitly.

REAL: ``AI_PROVIDER=gemini`` + ``GEMINI_API_KEY`` (or openai + key) — the same
50 images and ground truth scored against the live vision model. Use
``--sample N`` to evaluate a subset first (API cost control). If accuracy lands
below 80%, the script prints a graceful-degradation notice instead of masking
the number: low-confidence extractions stay unverified and require human review.

The committed fixture (``tests/benchmark_50_images.json``) carries **synthetic
reference URLs** (``images.smartdecor.dev``) plus human ground truth. In MOCK
mode the filename-keyword heuristic reads those URLs directly. A REAL run needs
actual pixels: pass ``--images-dir DIR`` containing files named
``{id:02d}-*.jpg|png|webp``; the harness uploads/sends the local bytes and
scores them against the same ground truth. Without a key **or** without real
images the REAL run is BLOCKED and says so — it is never simulated.

Scoring per image (matches docs/ARCHITECTURE.md §Benchmarks):
    style_hit   (0.5): at least one predicted style in ground-truth styles
    material    (0.5): precision of predicted materials (a hallucinated
                       material is an error; missing a secondary material
                       is not, since the primary drives recommendations)

Also reported: per-feature micro precision/recall, confidence calibration
(expected calibration error), per-call latency percentiles, failure rate,
human-review rate and an estimated provider cost for REAL mode.

Acceptance criterion: mean accuracy >= 0.80 in REAL mode.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.feature_extractor import FeatureExtractor  # noqa: E402
from ai.model_registry import ai_version_info  # noqa: E402
from app.core.config import settings  # noqa: E402

BENCHMARK = Path(__file__).resolve().parents[1] / "tests" / "benchmark_50_images.json"
REPORT = Path(__file__).resolve().parents[1] / ".." / "docs" / "reports" / "extraction_report.json"

#: Per-image token assumptions for the REAL cost estimate (Gemini bills images
#: as input tokens; a 768x768 image ≈ 258 tokens at standard detail). Prices
#: must be re-verified before budgeting — see docs/ai/privacy-cost-assessment.md.
#: Stage 04 remediation (IR-AI-004): the GEMINI_MODEL default is now
#: gemini-3.5-flash (gemini-2.0-flash shut down 2026-06-01; gemini-2.5-flash
#: is scheduled to shut down 2026-10-16). Token counts below are unchanged;
#: 3.5-generation pricing is UNVERIFIED (no credential in this environment —
#: the real benchmark is BLOCKED), so the $ figures are an order-of-magnitude
#: estimate based on the flash-lite tier until a real run re-measures them.
COST_ASSUMPTIONS = {
    "gemini": {
        "input_tokens_per_image": 258,
        "prompt_tokens": 120,
        "output_tokens": 120,
        "price_per_1m_input_usd": 0.10,
        "price_per_1m_output_usd": 0.40,
        "source": "https://ai.google.dev/gemini-api/docs/pricing (default model is now gemini-3.5-flash; prices shown are the flash-lite tier and are UNVERIFIED for 3.5-flash — re-verify with a real run before budgeting)",
    },
    "openai": {
        "input_tokens_per_image": 853,  # gpt-4o-mini low-detail image tokens
        "prompt_tokens": 120,
        "output_tokens": 120,
        "price_per_1m_input_usd": 0.15,
        "price_per_1m_output_usd": 0.60,
        "source": "https://openai.com/api/pricing/ (verify at budget time)",
    },
}

CALIBRATION_BUCKETS = [(0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


def score_item(pred: dict, truth: dict) -> float:
    """Score one prediction against ground truth (0..1)."""
    style_hit = 0.5 if set(pred.get("style", [])) & set(truth["style"]) else 0.0
    pm, tm = set(pred.get("material", [])), set(truth["material"])
    material = 0.5 * (len(pm & tm) / len(pm)) if pm else 0.0
    return style_hit + material


def _prf(pairs: list[tuple[set, set]]) -> dict:
    """Micro precision/recall/F1 over (predicted, truth) label sets."""
    tp = fp = fn = 0
    for pred, truth in pairs:
        tp += len(pred & truth)
        fp += len(pred - truth)
        fn += len(truth - pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}


def resolve_mode(force_real: bool) -> str:
    """Determine whether we run against a real vision provider or the mock."""
    if settings.AI_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        return "REAL:gemini"
    if settings.AI_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return "REAL:openai"
    if force_real:
        raise SystemExit(
            "ERROR: --real requires AI_PROVIDER=gemini|openai and the matching "
            "API key in the environment.\n"
            f"Blocked command was: AI_PROVIDER={settings.AI_PROVIDER} "
            f"GEMINI_API_KEY={'<set>' if settings.GEMINI_API_KEY else '<empty>'} "
            f"OPENAI_API_KEY={'<set>' if settings.OPENAI_API_KEY else '<empty>'} "
            "python scripts/evaluate_extraction.py --real"
        )
    return "MOCK"


def _local_image(images_dir: Path, item_id: int) -> str | None:
    if not images_dir.is_dir():
        return None
    for ext in ("jpg", "jpeg", "png", "webp"):
        matches = list(images_dir.glob(f"{item_id:02d}-*.{ext}"))
        if matches:
            return str(matches[0])
    return None


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


def estimate_cost(mode: str, images: int) -> dict:
    provider = mode.split(":")[1] if ":" in mode else None
    if provider not in COST_ASSUMPTIONS:
        return {"estimated_cost_usd": 0.0, "basis": "mock provider — no external calls"}
    a = COST_ASSUMPTIONS[provider]
    inp = images * (a["input_tokens_per_image"] + a["prompt_tokens"])
    out = images * a["output_tokens"]
    cost = inp / 1e6 * a["price_per_1m_input_usd"] + out / 1e6 * a["price_per_1m_output_usd"]
    return {
        "estimated_cost_usd": round(cost, 4),
        "basis": (
            f"ESTIMATE: {images} images x ({a['input_tokens_per_image']} image + "
            f"{a['prompt_tokens']} prompt) input tokens @ ${a['price_per_1m_input_usd']}/1M "
            f"+ {a['output_tokens']} output tokens @ ${a['price_per_1m_output_usd']}/1M"
        ),
        "source": a["source"],
    }


def main() -> int:
    force_real = "--real" in sys.argv
    sample = 0
    if "--sample" in sys.argv:
        sample = int(sys.argv[sys.argv.index("--sample") + 1])
    json_out = ""
    if "--json" in sys.argv:
        json_out = sys.argv[sys.argv.index("--json") + 1]
    images_dir = Path("")
    if "--images-dir" in sys.argv:
        images_dir = Path(sys.argv[sys.argv.index("--images-dir") + 1])
    sleep_s = 0.0
    if "--sleep" in sys.argv:
        sleep_s = float(sys.argv[sys.argv.index("--sleep") + 1])

    mode = resolve_mode(force_real)
    is_mock = mode == "MOCK"
    data = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    items = data["items"][:sample] if sample else data["items"]

    extractor = FeatureExtractor()
    per_item: list[dict] = []
    latencies: list[float] = []
    failures: list[dict] = []
    style_pairs: list[tuple[set, set]] = []
    material_pairs: list[tuple[set, set]] = []

    for idx, item in enumerate(items):
        target = item["image_url"]
        if not is_mock:
            local = _local_image(images_dir, item["id"])
            if local:
                target = f"file://{local}" if False else local
        t0 = time.perf_counter()
        try:
            pred = extractor.extract(target)
        except Exception as exc:  # a provider failure is data, not a crash
            failures.append({"id": item["id"], "error": f"{type(exc).__name__}: {exc}"})
            pred = {"style": [], "material": [], "patterns": [], "colors": [],
                    "confidence": 0.0, "provider": "exception", "needs_review": True}
        dt = time.perf_counter() - t0
        latencies.append(dt)
        s = score_item(pred, item["ground_truth"])
        style_pairs.append((set(pred.get("style", [])), set(item["ground_truth"]["style"])))
        material_pairs.append((set(pred.get("material", [])), set(item["ground_truth"]["material"])))
        per_item.append({
            "id": item["id"], "score": round(s, 4),
            "correct": s >= 0.8,
            "confidence": round(float(pred.get("confidence", 0.0)), 4),
            "provider": pred.get("provider", "?"),
            "provider_error": pred.get("provider_error"),
            "needs_review": bool(pred.get("needs_review")),
            "predicted_style": pred.get("style", []),
            "predicted_material": pred.get("material", []),
            "unknown_taxonomy_values": pred.get("unknown_taxonomy_values"),
        })
        # Pace calls for provider rate limits (free-tier Gemini per-minute
        # quota). The provider's own 429 retry handles bursts; --sleep keeps
        # the whole run under the cap in the first place.
        if sleep_s and idx < len(items) - 1:
            time.sleep(sleep_s)

    accuracy = sum(p["score"] for p in per_item) / len(per_item)
    below = [p["id"] for p in per_item if p["score"] < 0.8]

    # --- calibration: predicted confidence vs actual per-item correctness ---
    buckets = []
    ece_n = 0.0
    for lo, hi in CALIBRATION_BUCKETS:
        members = [p for p in per_item if lo <= p["confidence"] < hi]
        if not members:
            continue
        acc = sum(1 for p in members if p["correct"]) / len(members)
        conf = statistics.mean(p["confidence"] for p in members)
        buckets.append({
            "confidence_range": [round(lo, 2), round(min(hi, 1.0), 2)],
            "n": len(members), "actual_accuracy": round(acc, 4),
            "mean_confidence": round(conf, 4),
            "gap": round(abs(acc - conf), 4),
        })
        ece_n += len(members) / len(per_item) * abs(acc - conf)

    needs_review_count = sum(1 for p in per_item if p["needs_review"])
    report = {
        "mode": mode,
        "is_mock": is_mock,
        "mock_disclaimer": (
            "MOCK MODE — provider is the deterministic filename heuristic. "
            "This number is a harness baseline and is NOT vision-model accuracy."
        ) if is_mock else None,
        "versions": ai_version_info(),
        "images": len(per_item),
        "mean_accuracy": round(accuracy, 4),
        "images_at_or_above_0_8": sum(1 for p in per_item if p["score"] >= 0.8),
        "below_threshold_ids": below,
        "style_micro": _prf(style_pairs),
        "material_micro": _prf(material_pairs),
        "calibration": {"buckets": buckets, "expected_calibration_error": round(ece_n, 4)},
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50) * 1000, 1),
            "p95": round(_percentile(latencies, 0.95) * 1000, 1),
            "max": round(max(latencies) * 1000, 1),
        },
        "failures": {"count": len(failures), "rate": round(len(failures) / len(per_item), 4),
                     "items": failures},
        "human_review": {"count": needs_review_count,
                         "rate": round(needs_review_count / len(per_item), 4)},
        "items": per_item,
        "cost": estimate_cost(mode, len(per_item)),
        "per_item": per_item,
    }

    # --- human-readable summary ---
    print("=" * 72)
    print(f"MODE             : {mode}" + ("   ** NOT a vision-model accuracy claim **" if is_mock else ""))
    print(f"AI stack         : {report['versions']['ai_stack_version']} "
          f"(prompt {report['versions']['extraction']['prompt_version']}, "
          f"taxonomy {report['versions']['extraction']['taxonomy_version']})")
    print(f"images evaluated : {len(per_item)}")
    if not is_mock:
        print(f"pacing           : {sleep_s:g}s inter-call sleep, provider retry "
              f"(429/5xx/transport, max {os.getenv('GEMINI_MAX_ATTEMPTS', '5')} attempts)")
    print(f"mean accuracy    : {accuracy:.1%}   (contract: >= 80% in REAL mode)")
    print(f"images >= 0.8    : {report['images_at_or_above_0_8']}/{len(per_item)}")
    print(f"style micro P/R/F1     : {report['style_micro']['precision']:.3f} / "
          f"{report['style_micro']['recall']:.3f} / {report['style_micro']['f1']:.3f}")
    print(f"material micro P/R/F1  : {report['material_micro']['precision']:.3f} / "
          f"{report['material_micro']['recall']:.3f} / {report['material_micro']['f1']:.3f}")
    print(f"calibration ECE  : {report['calibration']['expected_calibration_error']:.4f}")
    for b in buckets:
        print(f"  conf {b['confidence_range'][0]:.2f}-{b['confidence_range'][1]:.2f}: "
              f"n={b['n']:<3} actual={b['actual_accuracy']:.2f} predicted={b['mean_confidence']:.2f}")
    print(f"latency p50/p95  : {report['latency_ms']['p50']:.0f} / {report['latency_ms']['p95']:.0f} ms")
    print(f"failures         : {len(failures)}/{len(per_item)}")
    print(f"needs review     : {needs_review_count}/{len(per_item)} "
          f"({report['human_review']['rate']:.0%})")
    print(f"cost             : {report['cost']['estimated_cost_usd']:.4f} USD "
          f"({report['cost']['basis']})")
    if below:
        print(f"below threshold  : {below}")
    print("=" * 72)

    payloads = [REPORT, Path(json_out)] if json_out else [REPORT]
    for path in payloads:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            slim = {k: v for k, v in report.items() if k != "per_item"}
            path.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"report written   : {path}")
        except OSError:
            pass

    if is_mock:
        print("RESULT: MOCK BASELINE — " + ("harness sane (>= 0.80)" if accuracy >= 0.80 else "HARNESS REGRESSION (< 0.80)"))
        return 0 if accuracy >= 0.80 else 1

    # --- B-5 guard (added 2026-09-01): a REAL-mode run is only meaningful if
    # the live vision provider actually analyzed pixels for EVERY image.
    # Previously, when image fetching failed (the committed fixture URLs are
    # synthetic — images.smartdecor.dev — and --images-dir was not passed),
    # every item silently degraded to the filename-keyword fallback; because
    # the ground truth is encoded in those slugs, the run printed a perfect
    # but fabricated "100% PASS". That must be impossible: degrade → INVALID.
    real_labels = {"gemini", "openai"}
    degraded = [p["id"] for p in per_item if p.get("provider") not in real_labels]
    if degraded:
        shown = degraded[:6]
        print(
            f"RESULT: INVALID REAL RUN — {len(degraded)}/{len(per_item)} images "
            f"were NOT analyzed by the vision provider "
            f"(labels seen: {sorted({p['provider'] for p in per_item if p.get('provider') not in real_labels})}; "
            f"ids {shown}{'...' if len(degraded) > 6 else ''}). The accuracy above "
            "comes from the filename-keyword fallback, NOT from the model — do "
            "not quote it. Remedy: (1) ensure the provider key is set correctly "
            "(no extra whitespace), (2) pass --images-dir DIR with real photos "
            "named {id:02d}-*.jpg matching tests/benchmark_50_images.json, and "
            "(3) rerun --real."
        )
        return 2

    if accuracy >= 0.80:
        print("RESULT: PASS (>= 80% required)")
        return 0
    print(
        "RESULT: BELOW TARGET — graceful degradation active: low-confidence "
        "extractions stay unverified and require human review before entering "
        "recommendations (human-in-the-loop gate). Tune the prompt or switch "
        "provider via AI_PROVIDER."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
