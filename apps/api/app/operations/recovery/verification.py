"""Observed-state verification; action completion alone never proves recovery."""
from __future__ import annotations

from dataclasses import dataclass

from app.db import models


@dataclass(frozen=True)
class Result:
    result: str
    recovered_units: float
    target_achieved: bool
    partial: bool
    method: str
    evidence: dict


def evaluate(case: models.RecoveryCase, deviation: models.OperationalDeviation,
             before: models.OperationalStateSnapshot, current: models.OperationalStateSnapshot) -> Result:
    baseline_forecast = float(before.forecast_quantity or 0)
    current_forecast = float(current.forecast_quantity or current.actual_quantity or 0)
    recovered = max(current_forecast - baseline_forecast, 0)
    target = float(current.target_quantity or before.target_quantity or 0)
    target_achieved = current_forecast >= target if target else False
    if deviation.category == "downtime":
        healthy = current.machine_health_state == "HEALTHY" and current.execution_state == "RUNNING"
        result = "RECOVERED" if healthy and recovered > 0 else "PARTIALLY_RECOVERED" if healthy else "INCONCLUSIVE"
        method = "healthy_machine_window_and_production_resume"
    elif deviation.category == "material":
        ready = current.material_readiness_state == "READY"
        result = "RECOVERED" if ready else "PARTIALLY_RECOVERED" if current.material_readiness_state == "WATCH" else "NO_EFFECT"
        method = "material_readiness_or_protected_schedule"
    elif deviation.category == "quality":
        normal = current.quality_state == "NORMAL"
        result = "RECOVERED" if normal and current.execution_state == "RUNNING" else "INCONCLUSIVE"
        method = "containment_and_stable_quality_window"
    else:
        result = "RECOVERED" if target_achieved or recovered > 0 else "NO_EFFECT"
        method = "forecast_and_actual_trajectory"
    partial = result == "PARTIALLY_RECOVERED"
    return Result(result, recovered, target_achieved, partial, method,
                  {"baseline_forecast": baseline_forecast, "current_forecast": current_forecast,
                   "execution_state": current.execution_state, "machine_health_state": current.machine_health_state,
                   "quality_state": current.quality_state, "material_readiness_state": current.material_readiness_state})
