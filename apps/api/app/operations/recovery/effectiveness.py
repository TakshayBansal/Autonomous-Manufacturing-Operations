"""Tenant-isolated Action–Outcome memory and effectiveness aggregation."""
from __future__ import annotations

from statistics import median

from sqlalchemy.orm import Session

from app.db import models


def _similarity(left: dict, right: dict) -> float:
    weights = {"deviation_type": 4, "deviation_subtype": 4, "asset_family": 3,
               "fault_code": 4, "product_family": 2, "line_id": 2, "shift": 1,
               "material_state": 2, "quality_state": 2, "strategy_type": 3}
    total = matched = 0.0
    for key, weight in weights.items():
        if left.get(key) is None or right.get(key) is None: continue
        total += weight
        if left[key] == right[key]: matched += weight
    return matched / total if total else 0


def find_similar_recovery_cases(db: Session, tenant_id: str, plant_id: str,
                                fingerprint: dict, strategy_type: str | None = None,
                                limit: int = 10) -> list[models.RecoveryOutcome]:
    query = db.query(models.RecoveryOutcome).filter_by(tenant_id=tenant_id)
    if strategy_type:
        query = query.join(models.RecoveryStrategy).filter(models.RecoveryStrategy.strategy_type == strategy_type)
    rows = query.limit(500).all()  # strict tenant boundary; plant similarity is part of ranking
    ranked = sorted(rows, key=lambda row: (
        _similarity(fingerprint, row.context_fingerprint or {}), row.plant_id == plant_id,
        row.verified_at or row.created_at), reverse=True)
    return [row for row in ranked if _similarity(fingerprint, row.context_fingerprint or {}) >= .25][:limit]


def get_effectiveness(db: Session, tenant_id: str, plant_id: str, strategy_type: str,
                      context: dict | None = None, minimum_sample: int = 3) -> dict:
    rows = find_similar_recovery_cases(db, tenant_id, plant_id,
                                       {**(context or {}), "strategy_type": strategy_type}, strategy_type, 100)
    sample = len(rows)
    successful = sum(row.outcome_rating == "successful" for row in rows)
    partial = sum(row.outcome_rating == "partially_successful" for row in rows)
    values = lambda name: [float(getattr(row, name)) for row in rows if getattr(row, name) is not None]
    return {"strategy_type": strategy_type, "sample_size": sample,
            "sufficient_history": sample >= minimum_sample,
            "success_rate": successful / sample if sample else None,
            "partial_success_rate": partial / sample if sample else None,
            "median_recovered_units": median(values("actual_recovered_units")) if values("actual_recovered_units") else None,
            "median_recovery_time_seconds": median(values("time_to_recovery_seconds")) if values("time_to_recovery_seconds") else None,
            "median_net_value": median(values("verified_value_recovered")) if values("verified_value_recovered") else None,
            "quality_side_effect_rate": sum(bool(row.quality_side_effect) for row in rows) / sample if sample else None,
            "recurrence_30d_rate": sum(bool(row.recurred_within_30d) for row in rows) / sample if sample else None}


def fingerprint(db: Session, deviation: models.OperationalDeviation, snapshot: models.OperationalStateSnapshot | None,
                strategy_type: str | None = None) -> dict:
    work_order = db.get(models.ProductionWorkOrder, deviation.work_order_id) if deviation.work_order_id else None
    asset = db.get(models.PlantAsset, deviation.asset_id) if deviation.asset_id else None
    return {"deviation_type": deviation.category, "deviation_subtype": deviation.subtype,
            "asset_family": asset.asset_type if asset else None,
            "fault_code": (deviation.actual_state or {}).get("fault_code"),
            "product_family": work_order.product_code.split("-")[0] if work_order else None,
            "line_id": deviation.line_id, "shift": deviation.shift_id,
            "material_state": snapshot.material_readiness_state if snapshot else None,
            "quality_state": snapshot.quality_state if snapshot else None,
            "initial_gap_pct": (deviation.actual_state or {}).get("gap_pct"),
            "strategy_type": strategy_type}
