"""Explainable deterministic recovery strategy ranking."""
from __future__ import annotations

from app.operations.recovery.playbooks.base import Candidate

DEFAULT_WEIGHTS = {"value": .27, "effectiveness": .18, "speed": .13, "success": .20,
                   "quality": .08, "safety": .12, "disruption": .08, "uncertainty": .08}


def score(candidate: Candidate, exposure: float, historical: dict, weights: dict | None = None) -> tuple[float, dict]:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    expected_value = max(exposure * candidate.recovery_ratio, 0)
    net_value = max(expected_value - candidate.direct_cost, 0)
    value_score = min(net_value / max(exposure, 1), 1)
    effectiveness = (historical.get("success_rate") if historical.get("sufficient_history") else
                     candidate.success_probability)
    speed = max(1 - candidate.implementation_seconds / 28800, 0)
    components = {"expected_value_recovered": round(expected_value, 2), "expected_net_value": round(net_value, 2),
                  "value": round(value_score, 4), "historical_effectiveness": round(float(effectiveness), 4),
                  "speed": round(speed, 4), "success_probability": candidate.success_probability,
                  "quality_risk": candidate.quality_risk, "safety_risk": candidate.safety_risk,
                  "operational_disruption": candidate.operational_risk, "uncertainty": candidate.uncertainty}
    if candidate.safety_risk >= .8:
        return -1, {**components, "veto": "Safety risk exceeds the configured limit"}
    total = (weights["value"] * value_score + weights["effectiveness"] * float(effectiveness) +
             weights["speed"] * speed + weights["success"] * candidate.success_probability -
             weights["quality"] * candidate.quality_risk - weights["safety"] * candidate.safety_risk -
             weights["disruption"] * candidate.operational_risk - weights["uncertainty"] * candidate.uncertainty)
    return round(total * 100, 2), components
