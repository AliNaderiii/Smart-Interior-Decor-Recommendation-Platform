"""Read committed product policy datasets with safe offline defaults."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SEED_DATA = Path(__file__).resolve().parents[2] / "seed_data"


@lru_cache
def subscription_plans() -> dict[str, Any]:
    try:
        return json.loads((SEED_DATA / "subscription_plans.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"homeowner_plans": [], "designer_plans": []}


def homeowner_plan(plan_id: str) -> dict[str, Any]:
    return next((plan for plan in subscription_plans()["homeowner_plans"] if plan["id"] == plan_id), {})


def recommendation_limit(plan_id: str) -> int:
    return int(homeowner_plan(plan_id).get("limits", {}).get("recommendations_per_category", 1))
