"""Versioned, shared interpretation of current operational state."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import models


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_readiness(db: Session, work_order_id: str):
    return (db.query(models.MaterialReadinessSnapshot)
            .filter_by(work_order_id=work_order_id)
            .order_by(models.MaterialReadinessSnapshot.calculated_at.desc()).first())


def derive_line_state(db: Session, line: models.ProductionLine, work_order: models.ProductionWorkOrder | None,
                      as_of: datetime) -> dict:
    from app.operations.service import ACTIVE_DEVIATION_STATUSES, production_forecast
    if work_order is None:
        return {"execution_state": "IDLE", "performance_state": "UNKNOWN",
                "machine_health_state": "UNKNOWN", "quality_state": "UNKNOWN",
                "recovery_state": "NONE", "material_readiness_state": "UNKNOWN"}
    deviations = (db.query(models.OperationalDeviation).filter_by(
        tenant_id=line.tenant_id, plant_id=line.plant_id, work_order_id=work_order.id)
        .filter(models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).all())
    open_down = db.query(models.ProductionDowntimeEvent).filter_by(
        tenant_id=line.tenant_id, line_id=line.id, ended_at=None).first()
    faults = (db.query(models.AssetFaultEvent).join(models.PlantAsset,
        models.AssetFaultEvent.asset_id == models.PlantAsset.id).filter(
        models.AssetFaultEvent.tenant_id == line.tenant_id,
        models.PlantAsset.line_id == line.id, models.AssetFaultEvent.cleared_at.is_(None)).all())
    signals = (db.query(models.MachineSignalSample).join(models.PlantAsset,
        models.MachineSignalSample.asset_id == models.PlantAsset.id).filter(
        models.MachineSignalSample.tenant_id == line.tenant_id,
        models.PlantAsset.line_id == line.id).order_by(models.MachineSignalSample.occurred_at.desc()).limit(3).all())
    readiness = _latest_readiness(db, work_order.id)
    quality_devs = [row for row in deviations if row.category == "quality"]
    recovery_case = (db.query(models.RecoveryCase).filter_by(deviation_id=deviations[0].id).first()
                     if deviations else None)
    forecast = production_forecast(db, work_order, as_of)
    mode = next((str((row.signals or {}).get("machine_mode", "")).lower() for row in signals
                 if (row.signals or {}).get("machine_mode")), "")
    execution = ("DOWN" if open_down or faults or mode in {"down", "alarm"} else
                 "CHANGEOVER" if work_order.status == "changeover" else
                 "BLOCKED_PHYSICALLY" if work_order.status == "blocked" else
                 "RUNNING" if work_order.status == "in_progress" else "IDLE")
    gap = float(forecast["gap_pct"])
    production_devs = [row for row in deviations if row.category == "production"]
    performance = ("RECOVERING" if recovery_case and recovery_case.status in {"executing", "monitoring"} else
                   "BEHIND" if gap <= -.10 else "WATCH" if gap <= -.05 else
                   "AHEAD" if gap >= .05 else "ON_PLAN")
    temps = [float((row.signals or {}).get("spindle_temperature_c") or 0) for row in signals]
    vibrations = [float((row.signals or {}).get("vibration_mm_s") or 0) for row in signals]
    machine = ("FAULT" if faults or mode in {"down", "alarm"} else
               "DEGRADED" if any(v >= 7.1 or t >= 82 for v, t in zip(vibrations, temps)) else
               "WATCH" if any(v >= 6 or t >= 78 for v, t in zip(vibrations, temps)) else
               "HEALTHY" if signals else "UNKNOWN")
    quality = ("CONTAINMENT" if any(row.status in {"action_in_progress", "monitoring"} for row in quality_devs) else
               "HOLD" if quality_devs else "NORMAL")
    recovery = ({"assessing": "ASSESSING", "options_ready": "ASSESSING",
                 "strategy_selected": "STRATEGY_SELECTED", "executing": "ACTION_IN_PROGRESS",
                 "monitoring": "MONITORING", "recovered": "RECOVERED", "verified": "RECOVERED",
                 "partially_recovered": "RECOVERED", "failed": "FAILED", "abandoned": "FAILED"}
                .get(recovery_case.status, "NONE") if recovery_case else "NONE")
    return {"execution_state": execution, "performance_state": performance,
            "machine_health_state": machine, "quality_state": quality,
            "recovery_state": recovery,
            "material_readiness_state": readiness.state if readiness else "UNKNOWN",
            "forecast": forecast, "deviations": deviations}


def build_operational_state_snapshot(db: Session, scope_type: str, scope_id: str,
                                     as_of: datetime | None = None) -> models.OperationalStateSnapshot:
    as_of = as_of or _now()
    if scope_type not in {"line", "work_order", "asset", "plant"}:
        raise ValueError("Unsupported operational state scope")
    work_order = None
    if scope_type == "line":
        line = db.get(models.ProductionLine, scope_id)
        if not line: raise LookupError("Line not found")
        work_order = (db.query(models.ProductionWorkOrder).filter_by(
            tenant_id=line.tenant_id, plant_id=line.plant_id, line_id=line.id)
            .filter(models.ProductionWorkOrder.planned_start_at <= as_of)
            .order_by(models.ProductionWorkOrder.planned_start_at.desc()).first())
    elif scope_type == "work_order":
        work_order = db.get(models.ProductionWorkOrder, scope_id)
        if not work_order: raise LookupError("Work order not found")
        line = db.get(models.ProductionLine, work_order.line_id)
    elif scope_type == "asset":
        asset = db.get(models.PlantAsset, scope_id)
        if not asset or not asset.line_id: raise LookupError("Scoped asset line not found")
        line = db.get(models.ProductionLine, asset.line_id)
        work_order = (db.query(models.ProductionWorkOrder).filter_by(line_id=line.id)
                      .order_by(models.ProductionWorkOrder.planned_start_at.desc()).first())
    else:
        plant = db.get(models.Plant, scope_id)
        if not plant: raise LookupError("Plant not found")
        line = db.query(models.ProductionLine).filter_by(tenant_id=plant.tenant_id, plant_id=plant.id).first()
        if not line: raise LookupError("Plant has no operational line")
        work_order = (db.query(models.ProductionWorkOrder).filter_by(plant_id=plant.id)
                      .order_by(models.ProductionWorkOrder.planned_start_at.desc()).first())
    state = derive_line_state(db, line, work_order, as_of)
    previous_version = (db.query(func.max(models.OperationalStateSnapshot.snapshot_version))
                        .filter_by(tenant_id=line.tenant_id, scope_type=scope_type, scope_id=scope_id).scalar() or 0)
    forecast = state.pop("forecast", {})
    deviations = state.pop("deviations", [])
    actions = (db.query(models.OperationalAction).filter(
        models.OperationalAction.deviation_id.in_([row.id for row in deviations]),
        models.OperationalAction.status.notin_(("completed", "cancelled"))).all() if deviations else [])
    actual = (db.query(models.ProductionActualPoint).filter_by(work_order_id=work_order.id)
              .order_by(models.ProductionActualPoint.recorded_at.desc()).first() if work_order else None)
    signal = (db.query(models.MachineSignalSample).join(models.PlantAsset,
              models.MachineSignalSample.asset_id == models.PlantAsset.id).filter(
              models.PlantAsset.line_id == line.id).order_by(models.MachineSignalSample.occurred_at.desc()).first())
    readiness = _latest_readiness(db, work_order.id) if work_order else None
    def age(value):
        if value is None: return None
        reference=as_of.replace(tzinfo=timezone.utc) if as_of.tzinfo is None else as_of
        compatible=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return max((reference-compatible).total_seconds(),0)
    freshness={"production_age_seconds":age(actual.recorded_at) if actual else None,
               "machine_age_seconds":age(signal.occurred_at) if signal else None,
               "material_age_seconds":age(readiness.calculated_at) if readiness else None}
    critical_ages=[value for value in freshness.values() if value is not None]
    freshness["state"]="stale" if not critical_ages or max(critical_ages)>3600 else "fresh"
    freshness["captured_at"]=as_of.isoformat()
    row = models.OperationalStateSnapshot(
        tenant_id=line.tenant_id, plant_id=line.plant_id, scope_type=scope_type, scope_id=scope_id,
        snapshot_version=previous_version + 1, captured_at=as_of,
        active_work_order_id=work_order.id if work_order else None,
        shift_id=work_order.shift_id if work_order else None,
        target_quantity=forecast.get("target_quantity"), expected_now=forecast.get("expected_now"),
        actual_quantity=forecast.get("actual_quantity"), forecast_quantity=forecast.get("forecast_quantity"),
        active_deviation_ids=[item.id for item in deviations], active_action_ids=[item.id for item in actions],
        source_freshness=freshness,
        state_payload={"forecast": forecast}, **state)
    db.add(row); db.flush()
    return row


def get_latest_operational_state(db: Session, tenant_id: str, scope_type: str, scope_id: str):
    return (db.query(models.OperationalStateSnapshot).filter_by(
        tenant_id=tenant_id, scope_type=scope_type, scope_id=scope_id)
        .order_by(models.OperationalStateSnapshot.captured_at.desc()).first())


def serialize_snapshot(row: models.OperationalStateSnapshot | None) -> dict | None:
    if not row: return None
    return {key: getattr(row, key) for key in (
        "id", "scope_type", "scope_id", "snapshot_version", "captured_at", "execution_state",
        "performance_state", "machine_health_state", "quality_state", "recovery_state",
        "active_work_order_id", "shift_id", "target_quantity", "expected_now", "actual_quantity",
        "forecast_quantity", "material_readiness_state", "active_deviation_ids", "active_action_ids",
        "state_payload", "source_freshness")}
