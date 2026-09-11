from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db import models

ACTIVE_DEVIATION_STATUSES = ("detected", "contextualized", "assigned", "investigating", "action_required", "action_in_progress", "monitoring", "resolved")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _queue_gigi_recovery_activity(db: Session, deviation: models.OperationalDeviation,
                                  agent_type: str, action_title: str) -> None:
    db.add(models.EventOutbox(
        tenant_id=deviation.tenant_id, plant_id=deviation.plant_id,
        event_type="gigi.activity.created", aggregate_type="operational_deviation",
        aggregate_id=deviation.id, aggregate_version=deviation.version,
        correlation_id=f"gigi:{agent_type}:{deviation.id}:{deviation.version}",
        causation_id=f"deviation:{deviation.id}", payload={
            "agent_type": agent_type, "deviation_id": deviation.id,
            "severity": deviation.severity,
            "what_changed": deviation.title,
            "why_it_matters": f"{deviation.estimated_lost_units:g} units are currently exposed.",
            "already_doing": "Created a governed recovery action with an accountable owner and SLA.",
            "user_action": action_title,
            "summary": f"Gigi prepared recovery coordination for {deviation.title.lower()}.",
            "confidence": deviation.confidence,
            "evidence": [{"type": "deviation", "id": deviation.id},
                         {"type": "work_order", "id": deviation.work_order_id}],
        }))


def _compatible_time(value: datetime, reference: datetime) -> datetime:
    """SQLite returns naive timestamps while PostgreSQL preserves timezone."""
    if value.tzinfo is None and reference.tzinfo is not None:
        return value.replace(tzinfo=timezone.utc)
    if value.tzinfo is not None and reference.tzinfo is None:
        return value.replace(tzinfo=None)
    return value


def detector_rule(db: Session, tenant_id: str, plant_id: str, detector_key: str) -> models.OperationalDetectorRule | None:
    return db.query(models.OperationalDetectorRule).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, detector_key=detector_key, enabled=True).first()


def _latest_plan(db: Session, work_order_id: str, at: datetime) -> models.ProductionPlanPoint | None:
    return (db.query(models.ProductionPlanPoint)
            .filter(models.ProductionPlanPoint.work_order_id == work_order_id,
                    models.ProductionPlanPoint.recorded_at <= at)
            .order_by(models.ProductionPlanPoint.recorded_at.desc()).first())


def _latest_actual(db: Session, work_order_id: str, at: datetime) -> models.ProductionActualPoint | None:
    return (db.query(models.ProductionActualPoint)
            .filter(models.ProductionActualPoint.work_order_id == work_order_id,
                    models.ProductionActualPoint.recorded_at <= at)
            .order_by(models.ProductionActualPoint.recorded_at.desc()).first())


def production_forecast(db: Session, work_order: models.ProductionWorkOrder, at: datetime | None = None) -> dict:
    at = at or utcnow()
    plan = _latest_plan(db, work_order.id, at)
    actual_points = (db.query(models.ProductionActualPoint)
                     .filter(models.ProductionActualPoint.work_order_id == work_order.id,
                             models.ProductionActualPoint.recorded_at <= at)
                     .order_by(models.ProductionActualPoint.recorded_at.desc()).limit(90).all())
    actual = actual_points[0] if actual_points else None
    actual_quantity = float(actual.good_quantity if actual else 0)
    expected_now = float(plan.cumulative_quantity if plan else 0)
    ordered = sorted(actual_points, key=lambda row: _compatible_time(row.recorded_at, at))
    # A source restart can legitimately reset its cumulative counter. Forecast
    # only from the newest monotonic segment so the old run is never joined to
    # the new run as one enormous production interval.
    window = ordered[-1:] if ordered else []
    for point in reversed(ordered[:-1]):
        if float(point.good_quantity) > float(window[0].good_quantity):
            break
        window.insert(0, point)
    if len(window) >= 2:
        minutes = (_compatible_time(window[-1].recorded_at, at) -
                   _compatible_time(window[0].recorded_at, at)).total_seconds() / 60
        quantity = float(window[-1].good_quantity) - float(window[0].good_quantity)
        # A longer weighted interval absorbs integer counter quantization and
        # concurrent connector completion without giving any tiny interval
        # enough influence to make the shift projection explode.
        net_rate = quantity / minutes if minutes > 0 and quantity >= 0 else 0
        confidence = "medium"
    else:
        line = db.get(models.ProductionLine, work_order.line_id)
        net_rate = float(line.standard_good_rate_per_minute if line else 0)
        confidence = "low"
    planned_end_at = _compatible_time(work_order.planned_end_at, at)
    remaining_minutes = max((planned_end_at - at).total_seconds() / 60, 0)
    planned_downtime = db.query(models.ProductionDowntimeEvent).filter(
        models.ProductionDowntimeEvent.work_order_id == work_order.id,
        models.ProductionDowntimeEvent.planned.is_(True),
        models.ProductionDowntimeEvent.started_at >= at,
        models.ProductionDowntimeEvent.started_at < work_order.planned_end_at,
    ).all()
    remaining_minutes -= sum(max((_compatible_time(row.ended_at or row.started_at, row.started_at) - row.started_at).total_seconds() / 60, 0)
                             for row in planned_downtime)
    target = float(work_order.target_quantity)
    line = db.get(models.ProductionLine, work_order.line_id)
    plausible_rate = float(line.standard_good_rate_per_minute if line else target / 480)
    net_rate = min(max(net_rate, 0), plausible_rate * 1.35)
    forecast = actual_quantity + net_rate * max(remaining_minutes, 0)
    # A forecast is a decision aid, not an unbounded mathematical projection.
    # Preserve over-attainment while preventing a corrupt interval from
    # producing four- or five-digit values for a shift-sized order.
    forecast = min(max(forecast, actual_quantity), max(target * 1.25, actual_quantity))
    return {
        "forecast_quantity": round(forecast, 2), "target_quantity": target,
        "expected_now": expected_now, "actual_quantity": actual_quantity,
        "gap_quantity": round(forecast - target, 2),
        "gap_pct": round((forecast - target) / max(target, 1), 4),
        "confidence": confidence,
        "drivers": [{"key": "recent_net_rate", "value": round(net_rate, 4)}],
    }


def recalculate_value_entries(db: Session, deviation: models.OperationalDeviation) -> int:
    """Reconcile deterministic impact without rewriting verified recovery."""
    persisted = db.query(models.OperationalValueEntry).filter_by(
        tenant_id=deviation.tenant_id, plant_id=deviation.plant_id,
        deviation_id=deviation.id, confidence_state="estimated").all()
    pending = [row for row in db.new if isinstance(row, models.OperationalValueEntry)
               and row.tenant_id == deviation.tenant_id
               and row.plant_id == deviation.plant_id
               and row.deviation_id == deviation.id
               and row.confidence_state == "estimated"]
    entries = persisted + [row for row in pending if row not in persisted]
    if not entries:
        entry = models.OperationalValueEntry(
            tenant_id=deviation.tenant_id, plant_id=deviation.plant_id,
            deviation_id=deviation.id,
            value_type=("downtime" if deviation.category == "downtime" else
                        "scrap" if deviation.category == "quality" else
                        "material" if deviation.category == "material" else "lost_output"),
            confidence_state="estimated", amount=0,
            calculation_method="canonical_deviation_impact", calculation_inputs={})
        db.add(entry)
        entries = [entry]
    inputs = {
        "detector_key": deviation.detector_key,
        "lost_units": float(deviation.estimated_lost_units or 0),
        "time_impact_minutes": float(deviation.estimated_time_impact_minutes or 0),
        "expected_state": deviation.expected_state or {},
        "actual_state": deviation.actual_state or {},
        "forecast_state": deviation.forecast_state or {},
    }
    for entry in entries:
        entry.amount = round(max(float(deviation.estimated_financial_impact or 0), 0), 2)
        entry.calculation_inputs = inputs
    return len(entries)


def evaluate_production_behind_plan(db: Session, work_order: models.ProductionWorkOrder,
                                    at: datetime | None = None) -> models.OperationalDeviation | None:
    at = at or utcnow()
    forecast = production_forecast(db, work_order, at)
    expected = forecast["expected_now"]
    actual = forecast["actual_quantity"]
    current_gap_pct = max((expected - actual) / max(expected, 1), 0)
    projected_gap_pct = max(-forecast["gap_pct"], 0)
    rule = detector_rule(db, work_order.tenant_id, work_order.plant_id, "production_behind_plan")
    parameters = rule.parameters if rule else {}
    current_threshold = float(parameters.get("current_gap_ratio", .05))
    projected_threshold = float(parameters.get("projected_gap_ratio", .05))
    recurrence_key = f"production_behind_plan:{work_order.line_id}:{work_order.shift_id}:{work_order.id}"
    if current_gap_pct < current_threshold and projected_gap_pct < projected_threshold:
        recovered = (db.query(models.OperationalDeviation)
                     .filter_by(tenant_id=work_order.tenant_id, recurrence_key=recurrence_key)
                     .filter(models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).first())
        if recovered:
            recovered.status = "verified"
            recovered.resolved_at = recovered.resolved_at or at
            recovered.verified_at = at
            recovered.verified_outcome = {
                "reason": "production_trajectory_recovered",
                "actual_quantity": actual,
                "forecast_quantity": forecast["forecast_quantity"],
            }
            for action in db.query(models.OperationalAction).filter_by(
                    tenant_id=work_order.tenant_id, deviation_id=recovered.id).filter(
                    models.OperationalAction.status.notin_(("completed", "cancelled"))).all():
                action.status = "completed"
                action.completed_at = at
            db.add(models.EventOutbox(
                tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
                event_type="deviation.resolved", aggregate_type="operational_deviation",
                aggregate_id=recovered.id, aggregate_version=recovered.version + 1,
                correlation_id=str(uuid4()), payload={"deviation_id": recovered.id, "automatic": True},
            ))
        return None
    bands = {row.get("severity"): row for row in (rule.severity_bands if rule else [])}
    critical_projected = float(bands.get("critical", {}).get("projected_gap_ratio", .15))
    high_current = float(bands.get("high", {}).get("current_gap_ratio", .10))
    severity = "critical" if projected_gap_pct >= critical_projected else "high" if current_gap_pct >= high_current else "watch"
    lost_units = max(expected - actual, -forecast["gap_quantity"], 0)
    line = db.get(models.ProductionLine, work_order.line_id)
    financial_impact = lost_units * float(line.contribution_per_good_unit if line else 0)
    deviation = (db.query(models.OperationalDeviation)
                 .filter_by(tenant_id=work_order.tenant_id, recurrence_key=recurrence_key)
                 .filter(models.OperationalDeviation.status.notin_(("verified", "learned", "cancelled"))).first())
    created = deviation is None
    if created:
        deviation = models.OperationalDeviation(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            detector_key="production_behind_plan", line_id=work_order.line_id,
            shift_id=work_order.shift_id, work_order_id=work_order.id,
            category="production", subtype="behind_plan",
            title=f"{line.name if line else 'Production line'} is behind plan",
            status="detected", severity=severity, recurrence_key=recurrence_key,
            owner_role=rule.owner_role if rule else "plant_manager", detected_at=at, started_at=at,
        )
        db.add(deviation)
        db.flush()
    deviation.severity = severity
    deviation.expected_state = {"expected_now": expected, "target": forecast["target_quantity"]}
    deviation.actual_state = {"actual_now": actual, "gap_pct": round(current_gap_pct, 4)}
    deviation.forecast_state = forecast
    deviation.estimated_lost_units = round(lost_units, 2)
    deviation.estimated_financial_impact = round(financial_impact, 2)
    if created:
        task = models.Task(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            title=f"Recover {deviation.title.lower()}", owner_role=deviation.owner_role or "plant_manager",
            status="open", severity=severity, priority="urgent" if severity == "critical" else "high",
            entity_type="operational_deviation", entity_id=deviation.id,
            task_type="operational_recovery", requested_outcome="Restore the work order trajectory and verify recovered output.",
            due_at=at + timedelta(minutes=30), semantic_key=f"v2-recovery:{deviation.id}",
            business_impact=severity, production_impact="direct",
        )
        db.add(task)
        db.flush()
        db.add(models.OperationalAction(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            deviation_id=deviation.id, task_id=task.id, action_type="production_recovery",
            title=task.title, owner_role=task.owner_role, status="open", priority=task.priority,
            due_at=task.due_at, expected_outcome={"restore_trajectory": True},
        ))
        db.add(models.OperationalValueEntry(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            deviation_id=deviation.id, value_type="lost_output", confidence_state="estimated",
            amount=financial_impact, calculation_method="lost_units_x_contribution",
            calculation_inputs={"lost_units": lost_units, "contribution_per_good_unit": float(line.contribution_per_good_unit if line else 0)},
        ))
        db.add(models.EventOutbox(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            event_type="deviation.created", aggregate_type="operational_deviation",
            aggregate_id=deviation.id, aggregate_version=1, correlation_id=str(uuid4()),
            payload={"deviation_id": deviation.id, "severity": severity, "work_order_id": work_order.id},
        ))
        _queue_gigi_recovery_activity(db, deviation, "production_recovery", task.title)
        tenant = db.get(models.Tenant, work_order.tenant_id)
        for recipient in (db.query(models.User).filter(
                models.User.tenant_id == work_order.tenant_id,
                models.User.plant_id == work_order.plant_id,
                models.User.is_active.is_(True),
                models.User.role.in_((deviation.owner_role, "plant_manager"))).all()
                if tenant and tenant.workspace_kind == "simulation" else []):
            db.add(models.Notification(
                tenant_id=work_order.tenant_id, plant_id=work_order.plant_id, user_id=recipient.id,
                category="operational_deviation", severity=severity, title=deviation.title,
                body="Current output and the end-of-shift forecast are below plan; recovery work is ready.",
                status="unread", linked_entity_type="operational_deviation", linked_entity_id=deviation.id,
                navigation_target=f"/v2/deviations/{deviation.id}",
                dedupe_key=f"v2-deviation:{deviation.id}:{recipient.id}"))
    recalculate_value_entries(db, deviation)
    if created:
        from app.operations.recovery.service import open_for_deviation
        open_for_deviation(db, deviation)
    return deviation


def _create_operational_deviation(
    db: Session, work_order: models.ProductionWorkOrder, *, detector_key: str,
    category: str, subtype: str, title: str, severity: str, recurrence_key: str,
    owner_role: str, expected_state: dict, actual_state: dict,
    lost_units: float, time_impact_minutes: float, financial_impact: float,
    at: datetime, asset_id: str | None = None,
) -> models.OperationalDeviation:
    deviation = (db.query(models.OperationalDeviation)
                 .filter_by(tenant_id=work_order.tenant_id, recurrence_key=recurrence_key)
                 .filter(models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).first())
    created = deviation is None
    if created:
        deviation = models.OperationalDeviation(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            detector_key=detector_key, line_id=work_order.line_id, shift_id=work_order.shift_id,
            work_order_id=work_order.id, asset_id=asset_id, category=category,
            subtype=subtype, title=title, status="detected", severity=severity,
            recurrence_key=recurrence_key, owner_role=owner_role,
            detected_at=at, started_at=at,
        )
        db.add(deviation)
        db.flush()
    deviation.severity = severity
    deviation.expected_state = expected_state
    deviation.actual_state = actual_state
    deviation.estimated_lost_units = round(max(lost_units, 0), 2)
    deviation.estimated_time_impact_minutes = round(max(time_impact_minutes, 0), 2)
    deviation.estimated_financial_impact = round(max(financial_impact, 0), 2)
    if created:
        priority = "urgent" if severity == "critical" else "high" if severity == "high" else "normal"
        task = models.Task(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            title=f"Recover {title.lower()}", owner_role=owner_role, status="open",
            severity=severity, priority=priority, entity_type="operational_deviation",
            entity_id=deviation.id, task_type="operational_recovery",
            requested_outcome="Remove the operational constraint and verify the recovered outcome.",
            due_at=at + timedelta(minutes=15 if severity == "critical" else 30),
            semantic_key=f"v2-recovery:{deviation.id}", business_impact=severity,
            production_impact="direct",
        )
        db.add(task)
        db.flush()
        db.add(models.OperationalAction(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            deviation_id=deviation.id, task_id=task.id, action_type=f"{category}_recovery",
            title=task.title, owner_role=owner_role, status="open", priority=priority,
            due_at=task.due_at, expected_outcome={"constraint_removed": True},
        ))
        db.add(models.OperationalValueEntry(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            deviation_id=deviation.id, value_type="lost_output", confidence_state="estimated",
            amount=max(financial_impact, 0), calculation_method="detector_impact_x_contribution",
            calculation_inputs={"lost_units": lost_units, "time_impact_minutes": time_impact_minutes},
        ))
        db.add(models.EventOutbox(
            tenant_id=work_order.tenant_id, plant_id=work_order.plant_id,
            event_type="deviation.created", aggregate_type="operational_deviation",
            aggregate_id=deviation.id, aggregate_version=1, correlation_id=str(uuid4()),
            payload={"deviation_id": deviation.id, "detector": detector_key, "severity": severity},
        ))
        agent_type = {"quality": "quality_recovery", "downtime": "reliability",
                      "material": "material_readiness"}.get(category, "production_recovery")
        _queue_gigi_recovery_activity(db, deviation, agent_type, task.title)
        tenant = db.get(models.Tenant, work_order.tenant_id)
        recipients = db.query(models.User).filter(
            models.User.tenant_id == work_order.tenant_id,
            models.User.plant_id == work_order.plant_id,
            models.User.is_active.is_(True),
            models.User.role.in_((owner_role, "plant_manager"))).all() if tenant and tenant.workspace_kind == "simulation" else []
        for recipient in recipients:
            db.add(models.Notification(
                tenant_id=work_order.tenant_id, plant_id=work_order.plant_id, user_id=recipient.id,
                category="operational_deviation", severity=severity, title=title,
                body=f"{title}. Recovery work has been assigned to {owner_role.replace('_', ' ')}.",
                status="unread", linked_entity_type="operational_deviation", linked_entity_id=deviation.id,
                navigation_target=f"/v2/deviations/{deviation.id}",
                dedupe_key=f"v2-deviation:{deviation.id}:{recipient.id}"))
    recalculate_value_entries(db, deviation)
    if created:
        from app.operations.recovery.service import open_for_deviation
        open_for_deviation(db, deviation)
    return deviation


def evaluate_downtime_threshold(db: Session, event: models.ProductionDowntimeEvent,
                                at: datetime | None = None) -> models.OperationalDeviation | None:
    at = at or event.ended_at or utcnow()
    start = _compatible_time(event.started_at, at)
    duration = max((at - start).total_seconds() / 60, 0)
    asset = db.get(models.PlantAsset, event.asset_id) if event.asset_id else None
    rule = detector_rule(db, event.tenant_id, event.plant_id, "downtime_exceeded_threshold")
    parameters = rule.parameters if rule else {}
    threshold = float(parameters.get("high_criticality_minutes", 10) if asset and asset.criticality == "high" else parameters.get("default_minutes", 20))
    if event.planned or duration < threshold:
        return None
    work_order = db.get(models.ProductionWorkOrder, event.work_order_id)
    line = db.get(models.ProductionLine, event.line_id)
    lost_units = duration * float(line.standard_good_rate_per_minute if line else 0)
    bands = {row.get("severity"): row for row in (rule.severity_bands if rule else [])}
    critical_multiple = float(bands.get("critical", {}).get("threshold_multiple", 3))
    high_multiple = float(bands.get("high", {}).get("threshold_multiple", 2))
    severity = "critical" if duration >= threshold * critical_multiple else "high" if duration >= threshold * high_multiple else "watch"
    return _create_operational_deviation(
        db, work_order, detector_key="downtime_exceeded_threshold", category="downtime",
        subtype=event.category, title=f"{asset.name if asset else 'Asset'} unplanned downtime",
        severity=severity, recurrence_key=f"downtime_exceeded_threshold:{event.id}",
        owner_role=rule.owner_role if rule else "maintenance_manager", expected_state={"maximum_minutes": threshold, "detector_rule_id": rule.id if rule else None},
        actual_state={"duration_minutes": round(duration, 2), "reason": event.reason},
        lost_units=lost_units, time_impact_minutes=duration,
        financial_impact=lost_units * float(line.contribution_per_good_unit if line else 0),
        at=at, asset_id=event.asset_id,
    )


def evaluate_machine_signals(db: Session, sample: models.MachineSignalSample) -> models.OperationalDeviation | None:
    """Infer a machine constraint from sustained raw telemetry, never a simulator label."""
    temperature = float((sample.signals or {}).get("spindle_temperature_c") or 0)
    vibration = float((sample.signals or {}).get("vibration_mm_s") or 0)
    mode = str((sample.signals or {}).get("machine_mode") or "unknown")
    recent = (db.query(models.MachineSignalSample).filter_by(
        tenant_id=sample.tenant_id, plant_id=sample.plant_id, asset_id=sample.asset_id)
        .order_by(models.MachineSignalSample.occurred_at.desc(),
                  models.MachineSignalSample.source_event_key.desc()).limit(3).all())
    sustained_heat = len(recent) >= 3 and all(float((row.signals or {}).get("spindle_temperature_c") or 0) >= 82 for row in recent)
    abnormal = sustained_heat or vibration >= 7.1 or mode in {"alarm", "down"}
    if not abnormal:
        sustained_normal = len(recent) >= 3 and all(
            float((row.signals or {}).get("spindle_temperature_c") or 0) < 78
            and float((row.signals or {}).get("vibration_mm_s") or 0) < 6
            and str((row.signals or {}).get("machine_mode") or "unknown") == "running"
            for row in recent)
        if sustained_normal:
            active = (db.query(models.OperationalDeviation).filter_by(
                tenant_id=sample.tenant_id, plant_id=sample.plant_id,
                asset_id=sample.asset_id, detector_key="machine_signal_threshold")
                .filter(models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).all())
            for deviation in active:
                deviation.status = "monitoring"
                deviation.resolved_at = sample.occurred_at
                deviation.verified_outcome = {"reason":"normal_machine_signals_observed","sample_count":len(recent)}
                for action in db.query(models.OperationalAction).filter_by(
                        tenant_id=sample.tenant_id, deviation_id=deviation.id).filter(
                        models.OperationalAction.status.notin_(("completed","cancelled"))).all():
                    action.status = "completed"; action.completed_at = sample.occurred_at
        return None
    work_order = db.get(models.ProductionWorkOrder, sample.work_order_id) if sample.work_order_id else None
    if not work_order: return None
    asset = db.get(models.PlantAsset, sample.asset_id); line = db.get(models.ProductionLine, work_order.line_id)
    severity = "critical" if mode == "down" or temperature >= 88 or vibration >= 9 else "high"
    lost_units = float(line.standard_good_rate_per_minute if line else 0) * 15
    return _create_operational_deviation(db, work_order, detector_key="machine_signal_threshold",
        category="downtime", subtype="machine_condition", title=f"{asset.code} abnormal machine condition",
        severity=severity, recurrence_key=f"machine_signal_threshold:{sample.asset_id}:{work_order.shift_id}",
        owner_role="maintenance_technician", expected_state={"spindle_temperature_c":"<82","vibration_mm_s":"<7.1","machine_mode":"running"},
        actual_state={"spindle_temperature_c":temperature,"vibration_mm_s":vibration,"machine_mode":mode,"sample_count":len(recent)},
        lost_units=lost_units, time_impact_minutes=15,
        financial_impact=lost_units * float(line.contribution_per_good_unit if line else 0), at=sample.occurred_at,
        asset_id=sample.asset_id)


def reconcile_asset_recovery(db: Session, fault: models.AssetFaultEvent) -> int:
    """Move inferred asset constraints forward when SCADA proves recovery."""
    if fault.cleared_at is None:
        return 0
    deviations = (db.query(models.OperationalDeviation).filter_by(
        tenant_id=fault.tenant_id, plant_id=fault.plant_id, asset_id=fault.asset_id,
        category="downtime").filter(
        models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).all())
    for deviation in deviations:
        deviation.status = "monitoring"
        deviation.resolved_at = fault.cleared_at
        deviation.verified_outcome = {"reason":"asset_recovery_observed","fault_event_id":fault.id}
        for action in db.query(models.OperationalAction).filter_by(
                tenant_id=fault.tenant_id, deviation_id=deviation.id).filter(
                models.OperationalAction.status.notin_(("completed","cancelled"))).all():
            action.status = "completed"; action.completed_at = fault.cleared_at
    return len(deviations)


def evaluate_rejection_rate(db: Session, event: models.ProductionQualityEvent,
                            threshold: float = .04) -> models.OperationalDeviation | None:
    rule = detector_rule(db, event.tenant_id, event.plant_id, "rejection_rate_high")
    threshold = float((rule.parameters if rule else {}).get("maximum_rejection_rate", threshold))
    rate = event.rejected_quantity / max(event.inspected_quantity, 1)
    if rate < threshold:
        return None
    work_order = db.get(models.ProductionWorkOrder, event.work_order_id)
    line = db.get(models.ProductionLine, event.line_id)
    bands = {row.get("severity"): row for row in (rule.severity_bands if rule else [])}
    severity = "critical" if rate >= threshold * float(bands.get("critical", {}).get("threshold_multiple", 2)) else "high" if rate >= threshold * float(bands.get("high", {}).get("threshold_multiple", 1.5)) else "watch"
    return _create_operational_deviation(
        db, work_order, detector_key="rejection_rate_high", category="quality",
        subtype=event.defect_code or "rejection", title=f"{line.name if line else 'Line'} rejection rate is high",
        severity=severity, recurrence_key=f"rejection_rate_high:{work_order.id}:{event.defect_code or 'all'}",
        owner_role=rule.owner_role if rule else "quality_manager", expected_state={"maximum_rejection_rate": threshold, "detector_rule_id": rule.id if rule else None},
        actual_state={"rejection_rate": round(rate, 4), "rejected_quantity": event.rejected_quantity},
        lost_units=event.rejected_quantity, time_impact_minutes=0,
        financial_impact=event.rejected_quantity * float(line.contribution_per_good_unit if line else 0),
        at=event.occurred_at,
    )


def evaluate_spc_control_limit(db: Session, event: models.ProductionQualityEvent) -> models.OperationalDeviation | None:
    rule = detector_rule(db, event.tenant_id, event.plant_id, "spc_control_limit_breached")
    if rule is not None and not bool(rule.parameters.get("use_event_control_limits", True)):
        return None
    value = event.measurement_value
    lower = event.lower_control_limit
    upper = event.upper_control_limit
    if value is None or (lower is None and upper is None):
        return None
    breached = (lower is not None and value < lower) or (upper is not None and value > upper)
    if not breached:
        return None
    work_order = db.get(models.ProductionWorkOrder, event.work_order_id)
    line = db.get(models.ProductionLine, event.line_id)
    distance = (lower - value) if lower is not None and value < lower else (value - upper) if upper is not None else 0
    span = max((upper or value) - (lower or value), abs(value) * .01, .001)
    bands = {row.get("severity"): row for row in (rule.severity_bands if rule else [])}
    severity = "critical" if distance / span >= float(bands.get("critical", {}).get("span_distance_ratio", .5)) else "high"
    return _create_operational_deviation(
        db, work_order, detector_key="spc_control_limit_breached", category="quality",
        subtype=event.measurement_name or "measurement",
        title=f"{event.measurement_name or 'Process measurement'} is outside control limits",
        severity=severity, recurrence_key=f"spc:{work_order.id}:{event.measurement_name or event.id}",
        owner_role=rule.owner_role if rule else "quality_manager", expected_state={"lower_control_limit": lower, "upper_control_limit": upper, "detector_rule_id": rule.id if rule else None},
        actual_state={"measurement_value": value, "material_lot_id": event.material_lot_id,
                      "quality_event_id": event.id}, lost_units=event.rejected_quantity,
        time_impact_minutes=0,
        financial_impact=event.rejected_quantity * float(line.contribution_per_good_unit if line else 0),
        at=event.occurred_at, asset_id=event.asset_id,
    )


def serialize_quality_case(row: models.QualityRecoveryCase) -> dict:
    return {
        "id": row.id, "number": row.business_number, "case_type": row.case_type,
        "parent_case_id": row.parent_case_id, "quality_event_id": row.quality_event_id,
        "deviation_id": row.deviation_id, "title": row.title, "status": row.status,
        "severity": row.severity, "owner_user_id": row.owner_user_id,
        "problem_statement": row.problem_statement, "containment_summary": row.containment_summary,
        "root_cause": row.root_cause, "corrective_action": row.corrective_action,
        "effectiveness_criteria": row.effectiveness_criteria,
        "effectiveness_result": row.effectiveness_result, "due_at": row.due_at,
        "verified_by_user_id": row.verified_by_user_id, "verified_at": row.verified_at,
        "closed_at": row.closed_at, "evidence": row.evidence, "version": row.version,
    }


def readiness_state(required: float, usable: float, confirmed: float, unconfirmed: float,
                    freshness: str = "fresh") -> str:
    if freshness != "fresh":
        return "UNKNOWN"
    if usable + confirmed >= required:
        return "READY"
    if usable + confirmed + unconfirmed >= required:
        return "WATCH"
    if usable + confirmed + unconfirmed > 0:
        return "AT_RISK"
    return "BLOCKED"


def evaluate_material_readiness(db: Session, snapshot: models.MaterialReadinessSnapshot) -> models.OperationalDeviation | None:
    state = readiness_state(snapshot.required_quantity, snapshot.usable_now,
                            snapshot.confirmed_inbound, snapshot.unconfirmed_inbound,
                            snapshot.data_freshness)
    snapshot.state = state
    if state in {"READY", "WATCH"}:
        return None
    work_order = db.get(models.ProductionWorkOrder, snapshot.work_order_id)
    line = db.get(models.ProductionLine, work_order.line_id)
    shortage = max(snapshot.required_quantity - snapshot.usable_now - snapshot.confirmed_inbound, 0)
    severity = "critical" if state == "BLOCKED" else "high" if state == "AT_RISK" else "watch"
    return _create_operational_deviation(
        db, work_order, detector_key="material_readiness_risk", category="material",
        subtype="shortage", title=f"{snapshot.material_code} threatens production readiness",
        severity=severity, recurrence_key=f"material_readiness_risk:{work_order.id}:{snapshot.material_code}",
        owner_role="purchase_executive", expected_state={"state": "READY", "required_quantity": snapshot.required_quantity},
        actual_state={"state": state, "projected_shortage": shortage}, lost_units=0,
        time_impact_minutes=0, financial_impact=0, at=snapshot.calculated_at,
    )


def recompute_material_readiness(db: Session, requirement: models.ProductionMaterialRequirement,
                                 at: datetime | None = None) -> models.MaterialReadinessSnapshot:
    at = at or utcnow()
    inventory = (db.query(models.MaterialInventoryPosition)
                 .filter_by(tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
                            material_code=requirement.material_code)
                 .filter(models.MaterialInventoryPosition.observed_at <= at)
                 .order_by(models.MaterialInventoryPosition.observed_at.desc()).first())
    usable = max(float(inventory.on_hand_quantity - inventory.reserved_for_other_orders - inventory.quality_hold_quantity), 0) if inventory else 0
    commitments = (db.query(models.ProductionSupplierCommitment)
                   .filter_by(tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
                              work_order_id=requirement.work_order_id, material_code=requirement.material_code,
                              status="open")
                   .filter(models.ProductionSupplierCommitment.committed_delivery_at <= requirement.required_at).all())
    confirmed = sum(float(row.committed_quantity) for row in commitments if row.acknowledged)
    unconfirmed = sum(float(row.committed_quantity) for row in commitments if not row.acknowledged)
    stale = not inventory or (at - _compatible_time(inventory.observed_at, at)).total_seconds() > 24 * 3600
    freshness = "stale" if stale else "fresh"
    state = readiness_state(requirement.required_quantity, usable, confirmed, unconfirmed, freshness)
    snapshot = models.MaterialReadinessSnapshot(
        tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
        work_order_id=requirement.work_order_id, material_code=requirement.material_code,
        required_quantity=requirement.required_quantity, usable_now=usable,
        confirmed_inbound=confirmed, unconfirmed_inbound=unconfirmed,
        required_at=requirement.required_at, state=state, data_freshness=freshness,
        calculated_at=at, inputs={"requirement_id": requirement.id,
                                 "inventory_position_id": inventory.id if inventory else None,
                                 "commitment_ids": [row.id for row in commitments]},
    )
    db.add(snapshot)
    db.flush()
    deviation = evaluate_material_readiness(db, snapshot)
    if state == "READY":
        active = (db.query(models.OperationalDeviation)
                  .filter_by(tenant_id=requirement.tenant_id,
                             recurrence_key=f"material_readiness_risk:{requirement.work_order_id}:{requirement.material_code}")
                  .filter(models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).first())
        if active:
            active.status = "monitoring"
    db.add(models.EventOutbox(
        tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
        event_type="material.readiness.updated", aggregate_type="material_readiness_snapshot",
        aggregate_id=snapshot.id, aggregate_version=1, correlation_id=str(uuid4()),
        payload={"work_order_id": requirement.work_order_id, "material_code": requirement.material_code,
                 "state": state, "deviation_id": deviation.id if deviation else None},
    ))
    return snapshot


def material_readiness_board(db: Session, tenant_id: str, plant_id: str,
                             horizon_days: int = 1, allowed_line_ids: set[str] | None = None) -> dict:
    cutoff = utcnow() + timedelta(days=horizon_days)
    requirements = (db.query(models.ProductionMaterialRequirement)
                    .filter_by(tenant_id=tenant_id, plant_id=plant_id)
                    .filter(models.ProductionMaterialRequirement.required_at <= cutoff)
                    .order_by(models.ProductionMaterialRequirement.required_at.asc()).all())
    # The canonical demonstration is dated explicitly; include it when current
    # wall-clock time has moved beyond the fixture horizon.
    if not requirements:
        requirements = (db.query(models.ProductionMaterialRequirement)
                        .filter_by(tenant_id=tenant_id, plant_id=plant_id)
                        .order_by(models.ProductionMaterialRequirement.required_at.asc()).all())
    if allowed_line_ids is not None:
        requirements=[row for row in requirements if (db.get(models.ProductionWorkOrder,row.work_order_id) and
                                                       db.get(models.ProductionWorkOrder,row.work_order_id).line_id in allowed_line_ids)]
    work_orders: dict[str, dict] = {}
    rank = {"BLOCKED": 0, "AT_RISK": 1, "UNKNOWN": 2, "WATCH": 3, "READY": 4}
    for requirement in requirements:
        snapshot = (db.query(models.MaterialReadinessSnapshot)
                    .filter_by(tenant_id=tenant_id, work_order_id=requirement.work_order_id,
                               material_code=requirement.material_code)
                    .order_by(models.MaterialReadinessSnapshot.calculated_at.desc()).first())
        if not snapshot:
            snapshot = recompute_material_readiness(db, requirement)
        wo = db.get(models.ProductionWorkOrder, requirement.work_order_id)
        group = work_orders.setdefault(wo.id, {"work_order": {"id": wo.id, "number": wo.business_number,
                                       "product": wo.product_name, "start": wo.planned_start_at},
                                      "state": "READY", "materials": []})
        group["materials"].append({"requirement_id": requirement.id, "material": requirement.material_code,
                                   "description": requirement.description, "required": snapshot.required_quantity,
                                   "usable_now": snapshot.usable_now, "confirmed_inbound": snapshot.confirmed_inbound,
                                   "unconfirmed_inbound": snapshot.unconfirmed_inbound,
                                   "need_by": snapshot.required_at, "state": snapshot.state,
                                   "freshness": snapshot.data_freshness,
                                   "v1_requirement_line_id": requirement.v1_requirement_line_id,
                                   "owner": "procurement" if snapshot.state in {"AT_RISK", "BLOCKED"} else "stores",
                                   "next_action": "Confirm supply or expedite sourcing" if snapshot.state == "AT_RISK" else
                                                  "Resolve material constraint" if snapshot.state == "BLOCKED" else
                                                  "Validate source data" if snapshot.state == "UNKNOWN" else
                                                  "Stage material for production"})
        if rank.get(snapshot.state, 0) < rank.get(group["state"], 0):
            group["state"] = snapshot.state
    for group in work_orders.values():
        total = len(group["materials"])
        ready = sum(1 for item in group["materials"] if item["state"] == "READY")
        group["readiness_pct"] = round(ready / max(total, 1) * 100)
        group["risky_materials"] = sum(1 for item in group["materials"] if item["state"] in {"AT_RISK", "BLOCKED", "UNKNOWN"})
        group["biggest_risk"] = next((item["material"] for item in group["materials"]
                                      if item["state"] in {"BLOCKED", "AT_RISK", "UNKNOWN"}), None)
    return {"horizon_days": horizon_days, "work_orders": list(work_orders.values())}


def procurement_lifecycle(db: Session, tenant_id: str, plant_id: str) -> list[dict]:
    requirements = db.query(models.PurchaseRequirement).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    rows = []
    for requirement in requirements:
        rfq = db.query(models.RFQ).filter_by(requirement_id=requirement.id, tenant_id=tenant_id).first()
        comparison = db.query(models.BidComparison).filter_by(rfq_id=rfq.id, tenant_id=tenant_id).first() if rfq else None
        award = db.query(models.AwardDecision).filter_by(rfq_id=rfq.id, tenant_id=tenant_id).first() if rfq else None
        po = db.query(models.PODraft).filter_by(award_id=award.id, tenant_id=tenant_id).first() if award else None
        acknowledgement = db.query(models.SupplierAcknowledgement).filter_by(po_draft_id=po.id, tenant_id=tenant_id).first() if po else None
        receipt = db.query(models.StoreReceipt).filter_by(po_draft_id=po.id, tenant_id=tenant_id).first() if po else None
        inspection = db.query(models.InspectionResult).filter_by(po_draft_id=po.id, tenant_id=tenant_id).first() if po else None
        quote_count = db.query(models.SupplierQuote).filter_by(rfq_id=rfq.id).count() if rfq else 0
        stages = [
            ("Requirement", requirement.status, "procurement", requirement),
            ("RFQ", rfq.status if rfq else "not_started", "procurement", rfq),
            ("Responses", "received" if quote_count else "waiting", "supplier", rfq),
            ("Comparison", comparison.status if comparison else "not_started", "procurement", comparison),
            ("Approval", award.status if award else "not_started", "approver", award),
            ("ERP PO", po.status if po else "not_started", "procurement", po),
            ("Supplier Acknowledgement", acknowledgement.status if acknowledgement else "waiting", "supplier", acknowledgement or po),
            ("Inbound", receipt.status if receipt else "waiting", "supplier", receipt or acknowledgement or po),
            ("Quality", inspection.status if inspection else "waiting", "quality", inspection or receipt),
            ("Ready", "ready" if inspection and inspection.accepted_quantity > 0 else "waiting", "stores", inspection),
        ]
        completed_states = {"approved", "completed", "received", "simulated_posted", "posted", "accepted", "ready", "closed"}
        stage_rows = []
        prior = None
        active_index = next((index for index, (_, state, _, _) in enumerate(stages)
                             if state not in completed_states), len(stages) - 1)
        for index, (label, state, owner, record) in enumerate(stages):
            entered_at = getattr(record, "updated_at", None) if record else None
            now = utcnow()
            wait_minutes = max(0, int((now - _compatible_time(entered_at, now)).total_seconds() / 60)) if entered_at and index == active_index else 0
            dependency = prior if index == active_index and state in {"waiting", "not_started", "pending_approval"} else None
            stage_rows.append({"label": label, "state": state, "owner": owner,
                               "entered_at": entered_at, "wait_minutes": wait_minutes,
                               "dependency": dependency})
            if state not in completed_states:
                prior = label
        active = stage_rows[active_index]
        rows.append({"id": requirement.id, "number": requirement.business_number, "status": requirement.status,
                     "current_stage": active["label"], "waiting_on": active["owner"],
                     "wait_minutes": active["wait_minutes"],
                     "next_action": f"Complete {active['label'].lower()}", "stages": stage_rows})
    return rows


def quality_workspace(db: Session, tenant_id: str, plant_id: str,
                      allowed_line_ids: set[str] | None = None) -> dict:
    event_query = db.query(models.ProductionQualityEvent).filter_by(tenant_id=tenant_id, plant_id=plant_id)
    if allowed_line_ids is not None: event_query=event_query.filter(models.ProductionQualityEvent.line_id.in_(allowed_line_ids))
    events = event_query.order_by(models.ProductionQualityEvent.occurred_at.desc()).all()
    inspected = sum(float(row.inspected_quantity) for row in events)
    rejected = sum(float(row.rejected_quantity) for row in events)
    rate = rejected / max(inspected, 1)
    deviations = (db.query(models.OperationalDeviation)
                  .filter_by(tenant_id=tenant_id, plant_id=plant_id, category="quality")
                  .filter(models.OperationalDeviation.line_id.in_(allowed_line_ids) if allowed_line_ids is not None else True)
                  .order_by(models.OperationalDeviation.detected_at.desc()).all())
    containments = db.query(models.QualityContainmentRecord).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).all()
    allowed_deviation_ids={row.id for row in deviations}
    if allowed_line_ids is not None:
        containments=[row for row in containments if row.deviation_id is None or row.deviation_id in allowed_deviation_ids]
    cases = (db.query(models.QualityRecoveryCase).filter_by(tenant_id=tenant_id, plant_id=plant_id)
             .order_by(models.QualityRecoveryCase.created_at.desc()).all())
    if allowed_line_ids is not None:
        cases=[row for row in cases if row.deviation_id is None or row.deviation_id in allowed_deviation_ids]
    pareto: dict[str, dict[str, float]] = {}
    for event in events:
        key = event.defect_code or "UNKNOWN"
        line = db.get(models.ProductionLine, event.line_id)
        entry = pareto.setdefault(key, {"quantity": 0, "value": 0})
        entry["quantity"] += float(event.rejected_quantity)
        entry["value"] += float(event.rejected_quantity) * float(line.contribution_per_good_unit if line else 0)
    return {
        "pulse": {"rejection_rate": round(rate, 4), "target_rejection_rate": .04,
                  "fpy": round(1 - rate, 4),
                  "active_holds": sum(1 for row in containments if row.status == "open"),
                  "scrap_rework_impact": round(sum(row.estimated_financial_impact for row in deviations), 2)},
        "pareto": [{"defect": key, **value} for key, value in sorted(
            pareto.items(), key=lambda item: item[1]["value"], reverse=True)],
        "deviations": [serialize_deviation(row) for row in deviations],
        "containments": [{"id": row.id, "quality_event_id": row.quality_event_id,
                          "deviation_id": row.deviation_id, "type": row.containment_type,
                          "affected_lot": row.affected_lot, "status": row.status,
                          "disposition": row.disposition, "evidence": row.evidence}
                         for row in containments],
        "spc_signals": [{"id": row.id, "measurement_name": row.measurement_name,
                         "measurement_value": row.measurement_value,
                         "lower_control_limit": row.lower_control_limit,
                         "upper_control_limit": row.upper_control_limit,
                         "material_lot_id": row.material_lot_id, "occurred_at": row.occurred_at,
                         "state": "breached" if ((row.lower_control_limit is not None and row.measurement_value is not None and row.measurement_value < row.lower_control_limit) or
                                                   (row.upper_control_limit is not None and row.measurement_value is not None and row.measurement_value > row.upper_control_limit)) else "stable"}
                        for row in events if row.measurement_value is not None],
        "recovery_cases": [serialize_quality_case(row) for row in cases],
    }


def maintenance_workspace(db: Session, tenant_id: str, plant_id: str,
                          allowed_asset_ids: set[str] | None = None) -> dict:
    asset_query = db.query(models.PlantAsset).filter_by(tenant_id=tenant_id, plant_id=plant_id)
    if allowed_asset_ids is not None: asset_query=asset_query.filter(models.PlantAsset.id.in_(allowed_asset_ids))
    assets = asset_query.all(); asset_ids={row.id for row in assets}
    faults = (db.query(models.AssetFaultEvent).filter_by(tenant_id=tenant_id, plant_id=plant_id)
              .filter(models.AssetFaultEvent.asset_id.in_(asset_ids))
              .order_by(models.AssetFaultEvent.occurred_at.desc()).all())
    work = db.query(models.MaintenanceWorkRecord).filter_by(tenant_id=tenant_id, plant_id=plant_id).filter(models.MaintenanceWorkRecord.asset_id.in_(asset_ids)).all()
    downtime = db.query(models.ProductionDowntimeEvent).filter_by(tenant_id=tenant_id, plant_id=plant_id).filter(models.ProductionDowntimeEvent.asset_id.in_(asset_ids)).all()
    open_fault_assets = {row.asset_id for row in faults if row.cleared_at is None}
    fault_counts: dict[tuple[str, str], int] = {}
    for fault in faults:
        key = (fault.asset_id, fault.fault_code)
        fault_counts[key] = fault_counts.get(key, 0) + 1
    cards = []
    for asset in assets:
        asset_faults = [row for row in faults if row.asset_id == asset.id]
        asset_work = [row for row in work if row.asset_id == asset.id and row.status not in {"completed", "cancelled"}]
        asset_downtime = [row for row in downtime if row.asset_id == asset.id and row.ended_at is None]
        deviation = (db.query(models.OperationalDeviation).filter_by(
            tenant_id=tenant_id, asset_id=asset.id, category="downtime")
            .filter(models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).first())
        cards.append({"asset": {"id": asset.id, "code": asset.code, "name": asset.name,
                                "criticality": asset.criticality},
                      "state": "down" if asset.id in open_fault_assets or asset_downtime else "available",
                      "production_impact": deviation.estimated_lost_units if deviation else 0,
                      "current_fault": {"id": asset_faults[0].id, "code": asset_faults[0].fault_code,
                                        "message": asset_faults[0].message,
                                        "occurred_at": asset_faults[0].occurred_at,
                                        "repeat_count": fault_counts.get((asset.id, asset_faults[0].fault_code), 0)} if asset_faults else None,
                      "work": [{"id": row.id, "title": row.title, "status": row.status,
                                "version": row.version, "owner_user_id": row.owner_user_id,
                                "spare_code": row.spare_code, "spare_available": row.spare_available,
                                "deviation_id": row.deviation_id, "resolution": row.resolution,
                                "started_at": row.started_at, "completed_at": row.completed_at}
                               for row in asset_work]})
    return {"pulse": {"assets_down": len(open_fault_assets),
                       "production_impact": sum(card["production_impact"] for card in cards),
                       "repeat_faults": sum(1 for count in fault_counts.values() if count > 1),
                       "waiting_for_spare": sum(1 for row in work if row.status == "waiting" and row.spare_available is False)},
            "assets": cards}


def improvement_workspace(db: Session, tenant_id: str, plant_id: str) -> dict:
    deviations = db.query(models.OperationalDeviation).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).all()
    faults = db.query(models.AssetFaultEvent).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    fault_groups: dict[tuple[str, str], list] = {}
    for fault in faults:
        fault_groups.setdefault((fault.asset_id, fault.fault_code), []).append(fault)
    opportunities = []
    for (asset_id, code), rows in fault_groups.items():
        if len(rows) < 2:
            continue
        asset = db.get(models.PlantAsset, asset_id)
        related = [row for row in deviations if row.asset_id == asset_id]
        observed_loss = sum(row.estimated_financial_impact for row in related)
        annualized = max(observed_loss * len(rows) * 6, 0)
        opportunities.append({"key": f"asset:{asset_id}:fault:{code}",
                              "title": f"Recurring {asset.code if asset else asset_id} fault {code}",
                              "category": "maintenance", "occurrences": len(rows),
                              "annualized_value": round(annualized, 2),
                              "evidence": [{"type": "fault", "id": row.id} for row in rows]})
    for detector, label in (("rejection_rate_high", "Recurring quality rejection"),
                            ("material_readiness_risk", "Material readiness disruption")):
        rows = [row for row in deviations if row.detector_key == detector]
        if rows:
            opportunities.append({"key": f"detector:{detector}", "title": label,
                                  "category": rows[0].category, "occurrences": len(rows),
                                  "annualized_value": round(sum(row.estimated_financial_impact for row in rows) * 12, 2),
                                  "evidence": [{"type": "deviation", "id": row.id} for row in rows]})
    opportunities.sort(key=lambda row: row["annualized_value"], reverse=True)
    experiments = db.query(models.ImprovementExperiment).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).all()
    benefits = db.query(models.ImprovementBenefitMeasurement).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).all()
    recovery_cases = db.query(models.RecoveryCase).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    recovery_groups: dict[str, list[models.RecoveryCase]] = {}
    for case in recovery_cases:
        deviation = db.get(models.OperationalDeviation, case.deviation_id)
        signature = f"{deviation.detector_key}:{deviation.asset_id or deviation.line_id or deviation.subtype}"
        recovery_groups.setdefault(signature, []).append(case)
    recurring_failures=[]
    for signature,cases in recovery_groups.items():
        if len(cases)<2: continue
        deviations_for_cases=[db.get(models.OperationalDeviation,row.deviation_id) for row in cases]
        recurring_failures.append({"signature":signature,"title":deviations_for_cases[0].title,
            "incidents":len(cases),"failed_recoveries":sum(row.status=="failed" or row.recovery_success is False for row in cases),
            "estimated_monthly_loss":round(sum(float(row.estimated_financial_impact or 0) for row in deviations_for_cases),2),
            "recurrence_rate":round((len(cases)-1)/len(cases),2),"case_ids":[row.id for row in cases],
            "recommendation":"Open a permanent improvement investigation"})
    investigations=db.query(models.ImprovementInvestigation).filter_by(tenant_id=tenant_id,plant_id=plant_id).all()
    return {"opportunities": opportunities,
            "recurring_recovery_failures":recurring_failures,
            "investigations":[{"id":row.id,"title":row.title,"status":row.status,"problem_signature":row.problem_signature,
                               "related_recovery_case_ids":row.related_recovery_case_ids,"estimated_annual_loss":row.estimated_annual_loss,
                               "currency":row.currency,"hypothesis":row.hypothesis,"countermeasure":row.countermeasure} for row in investigations],
            "experiments": [{"id": row.id, "title": row.title, "opportunity_key": row.opportunity_key,
                             "status": row.status, "hypothesis": row.hypothesis, "baseline": row.baseline,
                             "intervention": row.intervention, "target": row.target,
                             "starts_at": row.starts_at, "ends_at": row.ends_at,
                             "result": row.result, "statistical_confidence": row.statistical_confidence,
                             "evidence": row.evidence,
                             "benefits": [{"id": item.id, "metric": item.metric,
                                           "baseline_value": item.baseline_value,
                                           "observed_value": item.observed_value,
                                           "annualized_value": item.annualized_value,
                                           "confidence_state": item.confidence_state}
                                          for item in benefits if item.experiment_id == row.id]}
                            for row in experiments]}


def predictive_risks(db: Session, tenant_id: str, plant_id: str, at: datetime | None = None) -> list[dict]:
    at = at or utcnow()
    risks = []
    work_orders = db.query(models.ProductionWorkOrder).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, status="in_progress").all()
    for order in work_orders:
        forecast = production_forecast(db, order, at)
        if forecast["gap_pct"] < -.05:
            line = db.get(models.ProductionLine, order.line_id)
            risks.append({"key": f"output:{order.id}", "risk_type": "end_of_shift_output",
                          "severity": "critical" if forecast["gap_pct"] <= -.15 else "high",
                          "title": f"{line.name if line else order.line_id} likely to miss shift plan",
                          "probability": .86 if forecast["confidence"] == "high" else .68,
                          "time_horizon": order.planned_end_at, "predicted_impact": abs(forecast["gap_quantity"]),
                          "unit": "units", "confidence": forecast["confidence"],
                          "evidence": [{"type": "work_order", "id": order.id}],
                          "recommended_action": "Continue active recovery and validate the next hourly trajectory."})
    predicted_orders = {row["evidence"][0]["id"] for row in risks if row["risk_type"] == "end_of_shift_output"}
    behind = db.query(models.OperationalDeviation).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, detector_key="production_behind_plan").filter(
        models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).all()
    for deviation in behind:
        if deviation.work_order_id in predicted_orders:
            continue
        order = db.get(models.ProductionWorkOrder, deviation.work_order_id)
        line = db.get(models.ProductionLine, deviation.line_id)
        risks.append({"key": f"output:{deviation.work_order_id}", "risk_type": "end_of_shift_output",
                      "severity": deviation.severity, "title": f"{line.name if line else deviation.line_id} output remains at risk",
                      "probability": .65, "time_horizon": order.planned_end_at if order else at,
                      "predicted_impact": deviation.estimated_lost_units, "unit": "units",
                      "confidence": "medium", "evidence": [{"type": "deviation", "id": deviation.id}],
                      "recommended_action": "Validate recovery against the next plan checkpoint."})
    board = material_readiness_board(db, tenant_id, plant_id, 7)
    for group in board["work_orders"]:
        for material in group["materials"]:
            if material["state"] in {"AT_RISK", "BLOCKED"}:
                risks.append({"key": f"material:{material['requirement_id']}", "risk_type": "material_shortage",
                              "severity": "critical" if material["state"] == "BLOCKED" else "high",
                              "title": f"{material['material']} may constrain {group['work_order']['number']}",
                              "probability": .82, "time_horizon": material["need_by"],
                              "predicted_impact": max(material["required"] - material["usable_now"] - material["confirmed_inbound"], 0),
                              "unit": "material units", "confidence": "medium",
                              "evidence": [{"type": "material_requirement", "id": material["requirement_id"]}],
                              "recommended_action": "Confirm inbound quantity or authorize an alternate source."})
    return sorted(risks, key=lambda row: (row["severity"] != "critical", -row["probability"]))


def operational_notifications(db: Session, user: models.User) -> list[dict]:
    rows = db.query(models.Notification).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id, status="unread").all()
    return [{"id": row.id, "type": row.category, "severity": row.severity, "title": row.title,
             "summary": row.body, "entity_type": row.linked_entity_type,
             "entity_id": row.linked_entity_id, "href": row.navigation_target,
             "created_at": row.created_at} for row in rows]


def operational_search(db: Session, tenant_id: str, plant_id: str, query: str) -> dict:
    term = query.strip().lower()
    if not term:
        return {"query": query, "groups": []}
    groups = []
    lines = db.query(models.ProductionLine).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    line_hits = [{"id": row.id, "label": row.name, "context": row.code, "href": f"/v2/operations/lines/{row.id}"}
                 for row in lines if term in f"{row.name} {row.code}".lower()]
    assets = db.query(models.PlantAsset).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    asset_hits = [{"id": row.id, "label": row.name, "context": row.code, "href": "/v2/maintenance"}
                  for row in assets if term in f"{row.name} {row.code}".lower()]
    orders = db.query(models.ProductionWorkOrder).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    order_hits = [{"id": row.id, "label": row.external_reference or row.id, "context": row.product_name,
                   "href": f"/v2/operations/lines/{row.line_id}"} for row in orders
                  if term in f"{row.external_reference} {row.product_code} {row.product_name}".lower()]
    materials = db.query(models.ProductionMaterialRequirement).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    material_hits = [{"id": row.id, "label": row.material_code, "context": row.description, "href": "/v2/materials"}
                     for row in materials if term in f"{row.material_code} {row.description}".lower()]
    faults = db.query(models.AssetFaultEvent).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    fault_hits = [{"id": row.id, "label": f"Fault {row.fault_code}", "context": row.message,
                   "href": "/v2/maintenance"} for row in faults if term in f"fault {row.fault_code} {row.message}".lower()]
    for label, hits in (("Lines", line_hits), ("Assets", asset_hits), ("Work orders", order_hits),
                        ("Materials", material_hits), ("Faults", fault_hits)):
        if hits:
            groups.append({"entity": label, "results": hits[:8]})
    return {"query": query, "groups": groups}


def shift_briefing(db: Session, tenant_id: str, plant_id: str, shift_id: str, briefing_type: str) -> dict | None:
    row = db.query(models.ShiftBriefing).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, shift_id=shift_id, briefing_type=briefing_type).first()
    if not row:
        return None
    return {"id": row.id, "shift_id": row.shift_id, "type": row.briefing_type, "status": row.status,
            "title": row.title, "summary": row.summary, "metrics": row.metrics,
            "priorities": row.priorities, "losses": row.losses, "carry_over": row.carry_over,
            "evidence": row.evidence, "generated_at": row.generated_at,
            "verified_by_user_id": row.verified_by_user_id, "published_at": row.published_at}


def generate_shift_record(db: Session, tenant_id: str, plant_id: str, shift_id: str,
                          briefing_type: str, at: datetime | None = None) -> models.ShiftBriefing:
    shift = db.query(models.PlantShift).filter_by(
        id=shift_id, tenant_id=tenant_id, plant_id=plant_id).first()
    if shift is None:
        raise ValueError("Shift not found")
    at = at or shift.ends_at
    center = command_center(db, tenant_id, plant_id, shift_id, at)
    row = db.query(models.ShiftBriefing).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, shift_id=shift_id,
        briefing_type=briefing_type).first()
    if row is None:
        row = models.ShiftBriefing(tenant_id=tenant_id, plant_id=plant_id,
                                   shift_id=shift_id, briefing_type=briefing_type)
    row.status = "draft"
    row.title = f"{shift.name} {'handover' if briefing_type == 'handover' else 'operating briefing'}"
    row.summary = f"Plan {center['pulse']['target']:.0f}; actual {center['pulse']['actual']:.0f}; forecast {center['pulse']['forecast']:.0f}."
    row.metrics = center["pulse"]
    row.priorities = [{"title": item["title"], "entity_id": item["id"]}
                      for item in center["top_deviations"][:5]]
    row.losses = center["loss_breakdown"]
    row.carry_over = [{"title": item["title"], "entity_id": item["id"],
                       "owner_role": item.get("owner_role"), "status": item["status"]}
                      for item in center["top_deviations"] if item["status"] != "verified"]
    row.evidence = [{"type": "shift", "id": shift.id}] + [
        {"type": "deviation", "id": item["id"]} for item in center["top_deviations"]]
    row.generated_at = utcnow()
    row.verified_by_user_id = None
    row.published_at = None
    db.add(row)
    return row


def setup_workspace(db: Session, tenant_id: str, plant_id: str) -> dict:
    profile = db.query(models.OperationalSetupProfile).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).first()
    plant = db.get(models.Plant, plant_id)
    areas = db.query(models.PlantArea).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    lines = db.query(models.ProductionLine).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    detectors = db.query(models.OperationalDetectorRule).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).order_by(models.OperationalDetectorRule.name.asc()).all()
    return {"plant": {"id": plant.id, "name": plant.name, "timezone": plant.timezone,
                      "currency": plant.currency, "locale": plant.locale} if plant else None,
            "hierarchy": {"areas": len(areas), "lines": len(lines),
                          "area_records": [{"id": row.id, "name": row.name, "code": row.code,
                                            "version": row.version} for row in areas],
                          "line_records": [{"id": row.id, "area_id": row.area_id,
                                            "name": row.name, "code": row.code,
                                            "standard_good_rate_per_minute": row.standard_good_rate_per_minute,
                                            "contribution_per_good_unit": row.contribution_per_good_unit,
                                            "version": row.version} for row in lines]},
            "stage": profile.activation_stage if profile else "plant",
            "primary_use_case": profile.primary_use_case if profile else None,
            "enabled_data_domains": profile.enabled_data_domains if profile else [],
            "completed_stages": profile.completed_stages if profile else [],
            "detectors": [{"id": row.id, "detector_key": row.detector_key, "name": row.name,
                           "enabled": row.enabled, "parameters": row.parameters,
                           "severity_bands": row.severity_bands, "owner_role": row.owner_role,
                           "source_domains": row.source_domains, "effective_from": row.effective_from,
                           "approved_by_user_id": row.approved_by_user_id, "version": row.version}
                          for row in detectors],
            "configuration": {"production_calendar": profile.production_calendar,
                              "kpi_targets": profile.kpi_targets, "loss_categories": profile.loss_categories,
                              "escalation_rules": profile.escalation_rules, "value_formulas": profile.value_formulas,
                              "action_policies": profile.action_policies} if profile else {}}


def edge_workspace(db: Session, tenant_id: str, plant_id: str) -> dict:
    gateways = db.query(models.EdgeGateway).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    mappings = db.query(models.EdgeSourceMapping).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    health = db.query(models.EdgeSourceHealth).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    return {"gateways": [{"id": row.id, "name": row.name, "runtime_version": row.runtime_version,
                          "status": row.status, "transport": row.transport, "outbound_only": row.outbound_only,
                          "buffer_depth": row.buffer_depth, "last_heartbeat_at": row.last_heartbeat_at,
                          "config_version": row.config_version,
                          "mappings": [{"id": item.id, "asset_id": item.asset_id, "protocol": item.protocol,
                                        "source_address": item.source_address,
                                        "canonical_signal": item.canonical_signal}
                                       for item in mappings if item.gateway_id == row.id],
                          "sources": [{"name": item.source_name, "protocol": item.protocol,
                                       "status": item.status, "observed_at": item.observed_at,
                                       "message": item.message} for item in health if item.gateway_id == row.id]}
                         for row in gateways]}


def ingest_edge_canonical(db: Session, gateway: models.EdgeGateway, *, message_id: str,
                          event_type: str, asset: models.PlantAsset, source_timestamp: datetime,
                          payload: dict, payload_hash: str) -> tuple[models.EdgeIngestReceipt, bool]:
    existing = db.query(models.EdgeIngestReceipt).filter_by(
        gateway_id=gateway.id, message_id=message_id).first()
    if existing:
        return existing, False
    receipt = models.EdgeIngestReceipt(
        tenant_id=gateway.tenant_id, plant_id=gateway.plant_id, gateway_id=gateway.id,
        message_id=message_id, event_type=event_type, asset_id=asset.id,
        source_timestamp=source_timestamp, payload_hash=payload_hash)
    db.add(receipt)
    if event_type == "machine.alarm":
        fault_code = str(payload.get("fault_code") or "UNKNOWN")
        fault = models.AssetFaultEvent(
            tenant_id=gateway.tenant_id, plant_id=gateway.plant_id, asset_id=asset.id,
            fault_code=fault_code, message=str(payload.get("message") or "Machine alarm"),
            occurred_at=source_timestamp, source="edge", source_event_key=f"edge:{gateway.id}:{message_id}")
        work_order = db.query(models.ProductionWorkOrder).filter_by(
            tenant_id=gateway.tenant_id, plant_id=gateway.plant_id, line_id=asset.line_id,
            status="in_progress").first()
        fault.work_order_id = work_order.id if work_order else None
        db.add(fault)
        if work_order:
            line = db.get(models.ProductionLine, work_order.line_id)
            lost_units = float(payload.get("estimated_lost_units") or max(line.standard_good_rate_per_minute * 15, 0))
            _create_operational_deviation(
                db, work_order, detector_key="edge_machine_alarm", category="downtime",
                subtype="machine_alarm", title=f"{asset.code} fault {fault_code}", severity="high",
                recurrence_key=f"edge_machine_alarm:{asset.id}:{fault_code}:{work_order.shift_id}",
                owner_role="maintenance_technician", expected_state={"machine_state": "running"},
                actual_state={"machine_state": "alarm", "fault_code": fault_code},
                lost_units=lost_units, time_impact_minutes=15,
                financial_impact=lost_units * float(line.contribution_per_good_unit if line else 0),
                at=source_timestamp, asset_id=asset.id)
    gateway.last_heartbeat_at = utcnow()
    gateway.status = "connected"
    db.add(models.EventOutbox(
        tenant_id=gateway.tenant_id, plant_id=gateway.plant_id, event_type=event_type,
        aggregate_type="plant_asset", aggregate_id=asset.id, aggregate_version=1,
        correlation_id=f"edge:{gateway.id}:{message_id}",
        payload={"asset_id": asset.id, "source_timestamp": source_timestamp.isoformat(), **payload}))
    return receipt, True


def multi_plant_workspace(db: Session, tenant_id: str, at: datetime | None = None) -> dict:
    at = at or utcnow()
    plants = db.query(models.Plant).filter_by(tenant_id=tenant_id).all()
    rows = []
    for plant in plants:
        orders = db.query(models.ProductionWorkOrder).filter_by(
            tenant_id=tenant_id, plant_id=plant.id, status="in_progress").all()
        forecasts = [production_forecast(db, order, at) for order in orders]
        target = sum(item["target_quantity"] for item in forecasts)
        forecast = sum(item["forecast_quantity"] for item in forecasts)
        deviations = db.query(models.OperationalDeviation).filter_by(
            tenant_id=tenant_id, plant_id=plant.id).filter(
            models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES)).all()
        rows.append({"plant": {"id": plant.id, "name": plant.name},
                     "context": {"active_work_orders": len(orders), "data_available": bool(orders)},
                     "plan_attainment_forecast": round(forecast / max(target, 1), 4) if orders else None,
                     "active_deviations": len(deviations),
                     "addressable_value": round(sum(row.estimated_financial_impact for row in deviations), 2),
                     "systemic_losses": sorted({row.detector_key for row in deviations})})
    recurring: dict[str, dict] = {}
    for row in db.query(models.OperationalDeviation).filter_by(tenant_id=tenant_id).all():
        entry = recurring.setdefault(row.detector_key, {"occurrences": 0, "plant_ids": set(), "value": 0})
        entry["occurrences"] += 1
        entry["plant_ids"].add(row.plant_id)
        entry["value"] += float(row.estimated_financial_impact)
    kpis = db.query(models.StandardKPIDefinition).filter_by(tenant_id=tenant_id, status="active").all()
    transfers = (db.query(models.BestPracticeTransfer).filter_by(tenant_id=tenant_id)
                 .order_by(models.BestPracticeTransfer.created_at.desc()).all())
    plant_names = {row.id: row.name for row in plants}
    active_sites = sum(1 for row in rows if row["context"]["data_available"])
    systemic = [{"detector": key, "occurrences": value["occurrences"],
                 "plant_count": len(value["plant_ids"]), "addressable_value": round(value["value"], 2),
                 "cross_site_verified": len(value["plant_ids"]) > 1}
                for key, value in sorted(recurring.items(), key=lambda item: item[1]["value"], reverse=True)]
    verified_patterns = [row for row in systemic if row["cross_site_verified"]]
    briefing = {
        "title": "Corporate operating briefing",
        "summary": (f"{active_sites} of {len(plants)} plants currently have comparable active production data. "
                    f"{len(verified_patterns)} recurring loss patterns are evidenced across more than one site. "
                    f"{len(transfers)} practice transfer record(s) are under governance."),
        "limitations": ["Sites without active canonical work orders are excluded from KPI comparison.",
                        "Estimated value and product mix context must be reviewed before intervention transfer."],
        "evidence": [{"type": "plant_coverage", "active": active_sites, "total": len(plants)},
                     {"type": "standard_kpi_definitions", "count": len(kpis)}],
    }
    return {"plants": rows,
            "standard_kpis": [{"id": row.id, "key": row.key, "name": row.name,
                               "description": row.description, "unit": row.unit,
                               "formula": row.formula, "direction": row.direction,
                               "context_dimensions": row.context_dimensions,
                               "version": row.version_label, "approved_at": row.approved_at}
                              for row in kpis],
            "systemic_losses": systemic,
            "practice_transfers": [{"id": row.id, "number": row.business_number, "title": row.title,
                                    "source_plant": {"id": row.source_plant_id, "name": plant_names.get(row.source_plant_id, row.source_plant_id)},
                                    "target_plant": {"id": row.target_plant_id, "name": plant_names.get(row.target_plant_id, row.target_plant_id)},
                                    "status": row.status, "hypothesis": row.hypothesis,
                                    "applicability_context": row.applicability_context,
                                    "expected_benefit": row.expected_benefit,
                                    "source_experiment_id": row.source_experiment_id,
                                    "accepted_at": row.accepted_at, "completed_at": row.completed_at,
                                    "outcome": row.outcome, "evidence": row.evidence,
                                    "version": row.version} for row in transfers],
            "briefing": briefing,
            "comparison_note": "Standard definitions and coverage are visible; sites are not simplistically ranked where operational context differs."}


def deviation_evidence(db: Session, deviation: models.OperationalDeviation) -> list[dict]:
    refs = db.query(models.OperationalEvidenceRef).filter_by(
        tenant_id=deviation.tenant_id, entity_type="operational_deviation", entity_id=deviation.id).all()
    evidence = [{"id": row.id, "type": row.evidence_type, "source_system": row.source_system,
                 "source_reference": row.source_reference, "summary": row.summary,
                 "object_uri": row.object_uri, "metadata": row.evidence_metadata,
                 "created_at": row.created_at} for row in refs]
    for evidence_type, entity_id in (("work_order", deviation.work_order_id),
                                     ("line", deviation.line_id), ("asset", deviation.asset_id)):
        if entity_id:
            evidence.append({"id": entity_id, "type": evidence_type, "source_system": "canonical",
                             "source_reference": entity_id, "summary": f"Canonical {evidence_type} context",
                             "object_uri": None, "metadata": {}, "created_at": deviation.detected_at})
    return evidence


def deviation_timeline(db: Session, deviation: models.OperationalDeviation) -> list[dict]:
    items = [{"id": f"detected:{deviation.id}", "type": "deviation.detected",
              "occurred_at": deviation.detected_at, "summary": deviation.title,
              "actor": "Deviation Engine", "status": "completed"}]
    actions = db.query(models.OperationalAction).filter_by(
        tenant_id=deviation.tenant_id, deviation_id=deviation.id).all()
    for row in actions:
        action_created = _compatible_time(row.created_at, deviation.detected_at)
        detected_at = _compatible_time(deviation.detected_at, action_created)
        action_created = max(action_created, detected_at)
        items.append({"id": row.id, "type": "recovery.action", "occurred_at": action_created,
                      "summary": row.title, "actor": row.owner_role or row.owner_user_id or "Unassigned",
                      "status": row.status})
        if row.completed_at:
            items.append({"id": f"completed:{row.id}", "type": "action.completed",
                          "occurred_at": row.completed_at, "summary": str(row.completion_outcome.get("summary") or "Action completed"),
                          "actor": row.owner_user_id or row.owner_role or "Assigned owner", "status": "completed"})
    if deviation.resolved_at:
        items.append({"id": f"resolved:{deviation.id}", "type": "deviation.resolved",
                      "occurred_at": deviation.resolved_at, "summary": deviation.resolution or "Resolved",
                      "actor": deviation.owner_user_id or deviation.owner_role or "Owner", "status": deviation.status})
    return sorted(items, key=lambda row: _compatible_time(row["occurred_at"], deviation.detected_at))


def deviation_causal_context(db: Session, deviation: models.OperationalDeviation) -> dict:
    """Project evidence as a causal chain without upgrading hypotheses to facts."""
    actions = db.query(models.OperationalAction).filter_by(
        tenant_id=deviation.tenant_id, deviation_id=deviation.id).all()
    action_ids = [row.id for row in actions]
    dependencies = [] if not action_ids else db.query(models.OperationalActionDependency).filter(
        models.OperationalActionDependency.tenant_id == deviation.tenant_id,
        models.OperationalActionDependency.action_id.in_(action_ids)).all()
    similar = (db.query(models.OperationalDeviation)
               .filter(models.OperationalDeviation.tenant_id == deviation.tenant_id,
                       models.OperationalDeviation.plant_id == deviation.plant_id,
                       models.OperationalDeviation.id != deviation.id,
                       models.OperationalDeviation.detector_key == deviation.detector_key)
               .order_by(models.OperationalDeviation.detected_at.desc()).limit(5).all())
    contributors = []
    for key, value in (deviation.actual_state or {}).items():
        contributors.append({"label": key.replace("_", " ").title(), "value": value,
                             "state": "observed", "source": "detector evidence"})
    hypotheses = []
    if deviation.category == "downtime":
        hypotheses.append({"title": "Recurring equipment condition", "confidence": "medium",
                           "basis": "Matched asset/fault history; maintenance inspection must confirm cause."})
    elif deviation.category == "quality":
        hypotheses.append({"title": "Process or material variation", "confidence": "medium",
                           "basis": "Control/rejection signal correlation; Quality owns confirmed RCA."})
    elif deviation.category == "material":
        hypotheses.append({"title": "Inbound commitment uncertainty", "confidence": "high",
                           "basis": "Usable stock and acknowledged receipt evidence."})
    else:
        hypotheses.append({"title": "Recent production-rate constraint", "confidence": "medium",
                           "basis": "Plan/actual trajectory; investigation must confirm the physical cause."})
    return {
        "chain": [
            {"type": "signal", "label": deviation.detector_key.replace("_", " "), "state": "observed"},
            {"type": "deviation", "label": deviation.title, "state": deviation.status},
            *[{"type": "action", "id": row.id, "label": row.title, "state": row.status} for row in actions],
            {"type": "outcome", "label": f"{deviation.estimated_lost_units:g} units at risk", "state": "estimated"},
        ],
        "contributors": contributors,
        "hypotheses": hypotheses,
        "confirmed_cause": deviation.resolution if deviation.status in {"resolved", "verified"} else None,
        "dependencies": [{"id": row.id, "action_id": row.action_id, "title": row.title,
                          "type": row.dependency_type, "status": row.status,
                          "owner_role": row.owner_role, "owner_user_id": row.owner_user_id,
                          "due_at": row.due_at, "evidence_required": row.evidence_required}
                         for row in dependencies],
        "similar_incidents": [{"id": row.id, "title": row.title, "status": row.status,
                               "detected_at": row.detected_at, "resolution": row.resolution}
                              for row in similar],
    }


def value_summary(db: Session, tenant_id: str, plant_id: str) -> dict:
    rows = db.query(models.OperationalValueEntry).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    by_state: dict[str, float] = {}
    by_type: dict[str, float] = {}
    for row in rows:
        by_state[row.confidence_state] = by_state.get(row.confidence_state, 0) + row.amount
        by_type[row.value_type] = by_type.get(row.value_type, 0) + row.amount
    return {"currency": "INR", "total_estimated": round(by_state.get("estimated", 0), 2),
            "total_verified": round(by_state.get("verified", 0), 2),
            "by_confidence": [{"state": key, "amount": round(value, 2)} for key, value in by_state.items()],
            "by_type": [{"type": key, "amount": round(value, 2)} for key, value in by_type.items()],
            "entries": [serialize_value(row) for row in rows]}


def operational_kpis(db: Session, tenant_id: str, plant_id: str, shift_id: str | None,
                     at: datetime | None = None) -> dict:
    at = at or utcnow()
    order_query = db.query(models.ProductionWorkOrder).filter_by(tenant_id=tenant_id, plant_id=plant_id)
    if shift_id:
        order_query = order_query.filter_by(shift_id=shift_id)
    orders = order_query.all()
    forecasts = [production_forecast(db, row, at) for row in orders]
    order_ids = [row.id for row in orders]
    actuals = [] if not order_ids else db.query(models.ProductionActualPoint).filter(
        models.ProductionActualPoint.tenant_id == tenant_id,
        models.ProductionActualPoint.work_order_id.in_(order_ids),
        models.ProductionActualPoint.recorded_at <= at).all()
    latest_actuals = {}
    for row in sorted(actuals, key=lambda item: item.recorded_at):
        latest_actuals[row.work_order_id] = row
    good = sum(float(row.good_quantity) for row in latest_actuals.values())
    rejected = sum(float(row.reject_quantity) for row in latest_actuals.values())
    downtime_query = db.query(models.ProductionDowntimeEvent).filter_by(tenant_id=tenant_id, plant_id=plant_id)
    if order_ids:
        downtime_query = downtime_query.filter(models.ProductionDowntimeEvent.work_order_id.in_(order_ids))
    downtime_minutes = sum(max(((_compatible_time(row.ended_at, row.started_at) if row.ended_at else at) - row.started_at).total_seconds() / 60, 0)
                           for row in downtime_query.all() if not row.planned)
    deviations = db.query(models.OperationalDeviation).filter_by(tenant_id=tenant_id, plant_id=plant_id).all()
    acknowledgement_minutes, resolution_minutes = [], []
    for deviation in deviations:
        actions = db.query(models.OperationalAction).filter_by(deviation_id=deviation.id).all()
        started = min((row.created_at for row in actions if row.status != "open"), default=None)
        if started:
            acknowledgement_minutes.append(max((_compatible_time(started, deviation.detected_at) - deviation.detected_at).total_seconds() / 60, 0))
        if deviation.resolved_at:
            resolution_minutes.append(max((_compatible_time(deviation.resolved_at, deviation.detected_at) - deviation.detected_at).total_seconds() / 60, 0))
    readiness = material_readiness_board(db, tenant_id, plant_id, 7)
    material_rows = [item for group in readiness["work_orders"] for item in group["materials"]]
    ready_rows = [row for row in material_rows if row["state"] == "READY"]
    values = value_summary(db, tenant_id, plant_id)
    target = sum(row["target_quantity"] for row in forecasts)
    expected = sum(row["expected_now"] for row in forecasts)
    forecast_total = sum(row["forecast_quantity"] for row in forecasts)
    return {"at": at, "shift_id": shift_id, "groups": [
        {"key": "production", "label": "Production", "metrics": [
            {"key": "plan_attainment_now", "label": "Plan attainment now", "value": good / max(expected, 1), "unit": "ratio", "direction": "higher", "state": "watch" if good < expected * .95 else "healthy"},
            {"key": "forecast_attainment", "label": "Forecast attainment", "value": forecast_total / max(target, 1), "unit": "ratio", "direction": "higher", "state": "watch" if forecast_total < target * .95 else "healthy"},
            {"key": "good_output", "label": "Good output", "value": good, "unit": "units", "direction": "higher", "state": "neutral"},
        ]},
        {"key": "quality", "label": "Quality", "metrics": [
            {"key": "fpy", "label": "First-pass yield", "value": good / max(good + rejected, 1), "unit": "ratio", "direction": "higher", "state": "watch" if rejected / max(good + rejected, 1) > .04 else "healthy"},
            {"key": "rejected", "label": "Rejected", "value": rejected, "unit": "units", "direction": "lower", "state": "watch" if rejected else "healthy"},
        ]},
        {"key": "reliability", "label": "Reliability", "metrics": [
            {"key": "unplanned_downtime", "label": "Unplanned downtime", "value": round(downtime_minutes, 1), "unit": "minutes", "direction": "lower", "state": "high" if downtime_minutes > 30 else "watch" if downtime_minutes else "healthy"},
        ]},
        {"key": "materials", "label": "Materials", "metrics": [
            {"key": "readiness", "label": "Material readiness", "value": len(ready_rows) / max(len(material_rows), 1), "unit": "ratio", "direction": "higher", "state": "healthy" if len(ready_rows) == len(material_rows) else "high"},
        ]},
        {"key": "execution", "label": "Execution", "metrics": [
            {"key": "time_to_acknowledge", "label": "Avg. time to acknowledge", "value": round(sum(acknowledgement_minutes) / max(len(acknowledgement_minutes), 1), 1), "unit": "minutes", "direction": "lower", "state": "neutral"},
            {"key": "time_to_resolve", "label": "Avg. time to resolve", "value": round(sum(resolution_minutes) / max(len(resolution_minutes), 1), 1), "unit": "minutes", "direction": "lower", "state": "neutral"},
        ]},
        {"key": "value", "label": "Value", "metrics": [
            {"key": "estimated_loss", "label": "Estimated loss", "value": values["total_estimated"], "unit": "currency", "direction": "lower", "state": "watch"},
            {"key": "verified_recovery", "label": "Verified recovery", "value": values["total_verified"], "unit": "currency", "direction": "higher", "state": "healthy" if values["total_verified"] else "neutral"},
        ]},
    ]}


def forecast_evaluation(db: Session, tenant_id: str, plant_id: str) -> dict:
    """Rolling one-step backtest against the documented simple-rate baseline."""
    orders = db.query(models.ProductionWorkOrder).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).all()
    candidate_errors, baseline_errors, percentage_errors = [], [], []
    cases = []
    for order in orders:
        points = (db.query(models.ProductionActualPoint).filter_by(
            tenant_id=tenant_id, work_order_id=order.id)
                  .order_by(models.ProductionActualPoint.recorded_at.asc()).all())
        line = db.get(models.ProductionLine, order.line_id)
        baseline_rate = float(line.standard_good_rate_per_minute if line else 0)
        for index in range(2, len(points)):
            previous, current = points[index - 2], points[index - 1]
            observed = points[index]
            history_minutes = max((_compatible_time(current.recorded_at, previous.recorded_at) - previous.recorded_at).total_seconds() / 60, 1)
            horizon_minutes = max((_compatible_time(observed.recorded_at, current.recorded_at) - current.recorded_at).total_seconds() / 60, 1)
            recent_rate = max((current.good_quantity - previous.good_quantity) / history_minutes, 0)
            candidate = float(current.good_quantity) + recent_rate * horizon_minutes
            baseline = float(current.good_quantity) + baseline_rate * horizon_minutes
            candidate_error = abs(candidate - float(observed.good_quantity))
            baseline_error = abs(baseline - float(observed.good_quantity))
            candidate_errors.append(candidate_error)
            baseline_errors.append(baseline_error)
            if observed.good_quantity:
                percentage_errors.append(candidate_error / float(observed.good_quantity))
            cases.append({"work_order_id": order.id, "prediction_at": current.recorded_at,
                          "observed_at": observed.recorded_at, "observed": observed.good_quantity,
                          "candidate": round(candidate, 2), "baseline": round(baseline, 2),
                          "candidate_absolute_error": round(candidate_error, 2),
                          "baseline_absolute_error": round(baseline_error, 2)})
    sample_size = len(candidate_errors)
    candidate_mae = sum(candidate_errors) / max(sample_size, 1)
    baseline_mae = sum(baseline_errors) / max(sample_size, 1)
    return {"model": "recent_net_rate_v1", "baseline": "line_standard_rate",
            "sample_size": sample_size, "metrics": {
                "mae": round(candidate_mae, 3),
                "mape": round(sum(percentage_errors) / max(len(percentage_errors), 1), 4) if percentage_errors else None,
                "baseline_mae": round(baseline_mae, 3),
                "improvement_over_baseline": round((baseline_mae - candidate_mae) / max(baseline_mae, .0001), 4) if sample_size else None,
            }, "status": "insufficient_data" if sample_size < 10 else "candidate_better" if candidate_mae < baseline_mae else "baseline_better",
            "limitations": (["Fewer than 10 rolling observations; do not use this backtest as production model approval."] if sample_size < 10 else []),
            "cases": cases[-100:]}


def serialize_value(row: models.OperationalValueEntry) -> dict:
    return {"id": row.id, "deviation_id": row.deviation_id, "action_id": row.action_id,
            "value_type": row.value_type, "confidence_state": row.confidence_state,
            "amount": row.amount, "currency": row.currency,
            "calculation_method": row.calculation_method, "calculation_inputs": row.calculation_inputs,
            "captured_at": row.captured_at, "verified_by_user_id": row.verified_by_user_id,
            "verified_at": row.verified_at}


def _knowledge_visible(document: models.KnowledgeDocument, user: models.User, at: datetime) -> bool:
    if document.approval_state != "approved" or document.retired_at is not None:
        return False
    if document.role_acl and user.role not in document.role_acl:
        return False
    if document.plant_acl and user.plant_id not in document.plant_acl:
        return False
    if document.effective_from and _compatible_time(document.effective_from, at) > at:
        return False
    if document.effective_to and _compatible_time(document.effective_to, at) < at:
        return False
    return True


def knowledge_workspace(db: Session, user: models.User, query: str | None = None,
                        asset_id: str | None = None, document_type: str | None = None,
                        at: datetime | None = None) -> dict:
    at = at or utcnow()
    documents = db.query(models.KnowledgeDocument).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id).order_by(
        models.KnowledgeDocument.document_version.desc()).all()
    visible = [row for row in documents if _knowledge_visible(row, user, at)]
    if asset_id:
        visible = [row for row in visible if not row.asset_ids or asset_id in row.asset_ids]
    if document_type:
        visible = [row for row in visible if row.document_type == document_type]
    terms = {word for word in (query or "").lower().split() if len(word) > 1}
    results = []
    for document in visible:
        chunks = db.query(models.KnowledgeChunk).filter_by(
            tenant_id=user.tenant_id, knowledge_document_id=document.id).order_by(
            models.KnowledgeChunk.chunk_index.asc()).all()
        best = None
        score = 1.0 if not terms else 0.0
        for chunk in chunks:
            haystack = f"{document.title} {document.document_type} {chunk.content}".lower()
            lexical = sum(1 for term in terms if term in haystack) / max(len(terms), 1)
            structured = .15 if asset_id and asset_id in document.asset_ids else 0
            candidate_score = min(lexical + structured, 1)
            if candidate_score > score or best is None:
                score, best = candidate_score, chunk
        if terms and score <= 0:
            continue
        results.append({"document": {"id": document.id, "title": document.title,
                                     "document_type": document.document_type,
                                     "revision": document.revision,
                                     "document_version": document.document_version,
                                     "approval_state": document.approval_state,
                                     "effective_from": document.effective_from,
                                     "effective_to": document.effective_to,
                                     "asset_ids": document.asset_ids,
                                     "product_codes": document.product_codes,
                                     "process_codes": document.process_codes},
                        "match": {"score": round(score, 3),
                                  "excerpt": best.content[:500] if best else document.content[:500],
                                  "page": best.page_reference if best else None,
                                  "section": best.section_reference if best else None},
                        "warning": None})
    results.sort(key=lambda row: (row["match"]["score"], row["document"]["document_version"]), reverse=True)
    stale = [{"id": row.id, "title": row.title, "revision": row.revision,
              "approval_state": row.approval_state, "warning": "Superseded or unapproved; excluded from answers"}
             for row in documents if row.approval_state in {"retired", "draft"}]
    return {"query": query, "results": results, "excluded_revisions": stale,
            "retrieval_policy": "Active approved revisions only; keyword and structured scope ranking with visible citations."}


ACTION_TRANSITIONS = {
    "open": {"accept": "accepted", "start": "in_progress", "cancel": "cancelled"},
    "accepted": {"start": "in_progress", "cancel": "cancelled"},
    "in_progress": {"wait": "waiting", "complete": "completed", "fail": "failed", "cancel": "cancelled"},
    "waiting": {"start": "in_progress", "complete": "completed", "fail": "failed", "cancel": "cancelled"},
}


def transition_action(db: Session, action: models.OperationalAction, command: str,
                      outcome: dict | None = None) -> models.OperationalAction:
    if command in {"accept", "start"}:
        unresolved = db.query(models.OperationalActionDependency).filter_by(
            action_id=action.id).filter(models.OperationalActionDependency.status != "resolved").all()
        for dependency in unresolved:
            predecessor = db.get(models.OperationalAction, dependency.predecessor_action_id) if dependency.predecessor_action_id else None
            if predecessor and predecessor.status == "completed":
                dependency.status, dependency.resolved_at = "resolved", utcnow()
            else:
                raise ValueError(f"Action is waiting on: {dependency.title}")
    target = ACTION_TRANSITIONS.get(action.status, {}).get(command)
    if not target:
        raise ValueError(f"Cannot {command} an action in {action.status}")
    action.status = target
    task = db.get(models.Task, action.task_id) if action.task_id else None
    if task:
        task.status = target
        if command == "start" and not task.actual_start_at:
            task.actual_start_at = utcnow()
        if target == "completed":
            task.completed_at = utcnow()
            task.completion_summary = str((outcome or {}).get("summary") or "Operational action completed")
    deviation = db.get(models.OperationalDeviation, action.deviation_id) if action.deviation_id else None
    if deviation:
        mapping = {"accepted": "assigned", "in_progress": "action_in_progress", "waiting": "action_required", "completed": "monitoring"}
        if target in mapping:
            deviation.status = mapping[target]
    if target == "completed":
        action.completed_at = utcnow()
        action.completion_outcome = outcome or {}
        link = db.query(models.RecoveryStrategyAction).filter_by(operational_action_id=action.id).first()
        if link:
            strategy = db.get(models.RecoveryStrategy, link.strategy_id)
            case = db.get(models.RecoveryCase, strategy.recovery_case_id) if strategy else None
            links = db.query(models.RecoveryStrategyAction).filter_by(strategy_id=link.strategy_id).all()
            linked_actions = [db.get(models.OperationalAction, row.operational_action_id) for row in links]
            if case and all(row and (row.id == action.id or row.status == "completed") for row in linked_actions):
                from app.operations.recovery.service import begin_monitoring
                begin_monitoring(db, case)
    if target == "failed":
        action.completion_outcome = outcome or {}
        link = db.query(models.RecoveryStrategyAction).filter_by(operational_action_id=action.id).first()
        if link:
            strategy = db.get(models.RecoveryStrategy, link.strategy_id)
            case = db.get(models.RecoveryCase, strategy.recovery_case_id) if strategy else None
            if strategy: strategy.status = "failed"
            if case:
                alternatives = db.query(models.RecoveryStrategy).filter(
                    models.RecoveryStrategy.recovery_case_id == case.id,
                    models.RecoveryStrategy.id != strategy.id,
                    models.RecoveryStrategy.unavailable_reason.is_(None),
                    models.RecoveryStrategy.status.notin_(("failed", "rejected"))).count()
                case.status = "assessing" if alternatives else "failed"
                db.add(models.EventOutbox(tenant_id=case.tenant_id,plant_id=case.plant_id,
                    event_type="recovery.failed",aggregate_type="recovery_case",aggregate_id=case.id,
                    aggregate_version=case.version+1,correlation_id=f"recovery:{case.id}",
                    payload={"recovery_case_id":case.id,"strategy_id":strategy.id,"action_id":action.id,
                             "options_will_be_refreshed":bool(alternatives)}))
    db.add(models.EventOutbox(
        tenant_id=action.tenant_id, plant_id=action.plant_id, event_type="action.updated",
        aggregate_type="operational_action", aggregate_id=action.id,
        aggregate_version=action.version + 1, correlation_id=str(uuid4()),
        payload={"action_id": action.id, "status": target, "command": command},
    ))
    return action


def verify_deviation(db: Session, deviation: models.OperationalDeviation, outcome: dict,
                     user_id: str) -> models.OperationalDeviation:
    managed = db.query(models.RecoveryCase).filter_by(deviation_id=deviation.id).first()
    if managed and managed.status != "verified":
        raise ValueError("Verify the managed Recovery Case from observed operational state")
    if deviation.status not in {"monitoring", "resolved"}:
        raise ValueError("Deviation must be monitoring or resolved before verification")
    recovered = max(float(outcome.get("recovered_value", 0)), 0)
    deviation.status = "verified"
    deviation.resolved_at = deviation.resolved_at or utcnow()
    deviation.verified_at = utcnow()
    deviation.verified_outcome = outcome
    if recovered:
        db.add(models.OperationalValueEntry(
            tenant_id=deviation.tenant_id, plant_id=deviation.plant_id,
            deviation_id=deviation.id, value_type="lost_output", confidence_state="verified",
            amount=recovered, calculation_method="human_verified_recovery",
            calculation_inputs={"verification": outcome}, verified_by_user_id=user_id,
            verified_at=utcnow(),
        ))
    db.add(models.EventOutbox(
        tenant_id=deviation.tenant_id, plant_id=deviation.plant_id,
        event_type="deviation.resolved", aggregate_type="operational_deviation",
        aggregate_id=deviation.id, aggregate_version=deviation.version + 1,
        correlation_id=str(uuid4()), payload={"deviation_id": deviation.id, "verified": True},
    ))
    return deviation


def command_center(db: Session, tenant_id: str, plant_id: str, shift_id: str | None = None,
                   at: datetime | None = None, allowed_line_ids: set[str] | None = None) -> dict:
    at = at or utcnow()
    if shift_id is None:
        # Home is a current operating view. An omitted shift must never expand
        # into the full historical work-order population: besides producing a
        # meaningless plant total, that creates an N+1 forecast query for every
        # order in the retention window.
        shift = (db.query(models.PlantShift)
                 .filter(models.PlantShift.tenant_id == tenant_id,
                         models.PlantShift.plant_id == plant_id,
                         models.PlantShift.starts_at <= at,
                         models.PlantShift.ends_at > at)
                 .order_by(models.PlantShift.starts_at.desc()).first())
        if shift is None:
            shift = (db.query(models.PlantShift)
                     .filter(models.PlantShift.tenant_id == tenant_id,
                             models.PlantShift.plant_id == plant_id,
                             models.PlantShift.starts_at <= at)
                     .order_by(models.PlantShift.starts_at.desc()).first())
        shift_id = shift.id if shift else None
    query = db.query(models.ProductionWorkOrder).filter_by(tenant_id=tenant_id, plant_id=plant_id)
    if allowed_line_ids is not None:
        query = query.filter(models.ProductionWorkOrder.line_id.in_(allowed_line_ids))
    if shift_id:
        query = query.filter_by(shift_id=shift_id)
    work_orders = query.all()
    forecasts = [production_forecast(db, row, at) for row in work_orders]
    deviations = (db.query(models.OperationalDeviation)
                  .filter_by(tenant_id=tenant_id, plant_id=plant_id)
                  .filter(models.OperationalDeviation.status.notin_(("verified", "learned", "cancelled")))
                  .filter(models.OperationalDeviation.line_id.in_(allowed_line_ids) if allowed_line_ids is not None else True)
                  .order_by(models.OperationalDeviation.estimated_financial_impact.desc()).limit(7).all())
    loss_totals: dict[str, dict[str, float]] = {}
    for row in deviations:
        bucket = loss_totals.setdefault(row.category, {
            "lost_units": 0, "time_impact_minutes": 0, "financial_impact": 0})
        bucket["lost_units"] += float(row.estimated_lost_units or 0)
        bucket["time_impact_minutes"] += float(row.estimated_time_impact_minutes or 0)
        bucket["financial_impact"] += float(row.estimated_financial_impact or 0)
    from app.operations.integrations import plant_data_health
    data_health = plant_data_health(db, tenant_id, plant_id)
    decision_actions = (db.query(models.OperationalAction, models.OperationalDeviation)
                        .join(models.OperationalDeviation, models.OperationalAction.deviation_id == models.OperationalDeviation.id)
                        .filter(models.OperationalAction.tenant_id == tenant_id,
                                models.OperationalAction.plant_id == plant_id,
                                models.OperationalAction.status.in_(("open", "accepted", "waiting")),
                                models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES))
                        .filter(models.OperationalDeviation.line_id.in_(allowed_line_ids) if allowed_line_ids is not None else True)
                        .order_by(models.OperationalDeviation.estimated_financial_impact.desc(),
                                  models.OperationalAction.due_at.asc()).limit(5).all())
    recent_activity = (db.query(models.EventOutbox)
                       .filter(models.EventOutbox.tenant_id == tenant_id,
                               models.EventOutbox.plant_id == plant_id,
                               models.EventOutbox.event_type.in_((
                                   "deviation.created", "deviation.updated", "deviation.resolved",
                                   "action.created", "action.updated", "gigi.activity.created",
                                   "material.readiness.updated", "connector.health.changed")))
                       .order_by(models.EventOutbox.created_at.desc()).limit(6).all())
    from app.operations.recovery.service import opportunities
    recovery_opportunities = opportunities(db, tenant_id, plant_id)
    if allowed_line_ids is not None:
        recovery_opportunities = [row for row in recovery_opportunities
                                  if db.get(models.OperationalDeviation, row["deviation_id"]).line_id in allowed_line_ids]
    value_at_risk = sum(float(row.get("business_exposure_amount") or 0) for row in recovery_opportunities)
    addressed = sum(float(row.get("business_exposure_amount") or 0) for row in recovery_opportunities
                    if row.get("status") in {"strategy_selected", "executing", "monitoring", "recovered"})
    verified_today = (db.query(models.OperationalValueEntry).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, value_type="recovery_verified", confidence_state="verified")
        .filter(models.OperationalValueEntry.captured_at >= at.replace(hour=0, minute=0, second=0, microsecond=0))
        .with_entities(models.OperationalValueEntry.amount).all())
    return {
        "pulse": {
            "target": sum(item["target_quantity"] for item in forecasts),
            "actual": sum(item["actual_quantity"] for item in forecasts),
            "expected_now": sum(item["expected_now"] for item in forecasts),
            "forecast": sum(item["forecast_quantity"] for item in forecasts),
            "forecast_confidence": "medium" if forecasts else "unknown",
        },
        "loss_breakdown": [{"category": key,
                            "lost_units": round(value["lost_units"], 2),
                            "time_impact_minutes": round(value["time_impact_minutes"], 2),
                            "financial_impact": round(value["financial_impact"], 2),
                            "currency": next((row.currency for row in deviations if row.category == key), "USD")}
                           for key, value in sorted(loss_totals.items(),
                                                   key=lambda item: item[1]["financial_impact"], reverse=True)],
        "top_deviations": [{
            "id": row.id, "title": row.title, "category": row.category,
            "line_id": row.line_id, "asset_id": row.asset_id,
            "severity": row.severity, "status": row.status,
            "lost_units": row.estimated_lost_units, "financial_impact": row.estimated_financial_impact,
            "currency": row.currency, "owner_role": row.owner_role,
        } for row in deviations],
        "decisions_required": [{
            "id": action.id, "decision": action.title, "affected_object": deviation.title,
            "expected_impact": action.expected_outcome,
            "need_by": action.due_at, "priority": action.priority,
            "deviation_id": deviation.id, "action_id": action.id,
        } for action, deviation in decision_actions],
        "automation_activity": [{
            "id": row.event_id, "type": row.event_type, "at": row.created_at,
            "summary": str(row.payload.get("summary") or row.payload.get("title") or
                           row.event_type.replace(".", " ").replace("_", " ").capitalize()),
            "entity_id": row.aggregate_id,
        } for row in recent_activity],
        "data_health": data_health,
        "recovery_summary": {"value_at_risk": round(value_at_risk, 2), "value_addressed": round(addressed, 2),
                             "verified_recovered_value_today": round(sum(float(row[0]) for row in verified_today), 2)},
        "recovery_opportunities": recovery_opportunities,
    }


def role_command_center(payload: dict, role: str) -> dict:
    focus = {
        "plant_manager": ("Will the plant recover plan, and what needs my decision?", None),
        "admin": ("Can operators trust the plant model and its connected sources?", None),
        "quality_manager": ("Where is quality constraining output, and is containment effective?", {"quality"}),
        "quality_inspector": ("What must be contained, inspected or verified now?", {"quality"}),
        "maintenance_manager": ("Which reliability loss is constraining production now?", {"downtime", "maintenance"}),
        "maintenance_technician": ("Which asset recovery action should I execute next?", {"downtime", "maintenance"}),
        "purchase_manager": ("Which material or supplier commitment threatens production?", {"material"}),
        "purchase_executive": ("Which material commitment needs action before its need time?", {"material"}),
        "store_manager": ("Which staging, inventory or spare dependency blocks production?", {"material", "downtime"}),
        "production_supervisor": ("Which line needs intervention to recover this shift?", {"production", "downtime", "quality", "material"}),
        "operator": ("What changed on my line, and what should I do next?", {"production", "downtime", "quality"}),
    }.get(role, ("What needs my attention to protect the current operating plan?", None))
    question, categories = focus
    relevant = payload["top_deviations"] if categories is None else [
        row for row in payload["top_deviations"] if any(category in row.get("category", "") for category in categories)]
    # Summary rows created before this projection may not include category; resolve
    # relevance conservatively rather than hiding genuine high-impact work.
    if categories and not relevant:
        relevant = payload["top_deviations"][:3]
    payload["role_focus"] = {"role": role, "question": question,
                             "relevant_deviation_ids": [row["id"] for row in relevant],
                             "attention_count": len(relevant),
                             "show_financial_value": role in {"admin", "plant_manager", "purchase_manager"},
                             "show_data_health_first": role == "admin"}
    return payload


def operations_overview(db: Session, tenant_id: str, plant_id: str, shift_id: str | None,
                        at: datetime | None = None, allowed_line_ids: set[str] | None = None) -> dict:
    at = at or utcnow()
    if shift_id is None:
        shift = (db.query(models.PlantShift).filter(
            models.PlantShift.tenant_id == tenant_id, models.PlantShift.plant_id == plant_id,
            models.PlantShift.starts_at <= at, models.PlantShift.ends_at > at)
            .order_by(models.PlantShift.starts_at.desc()).first())
        shift_id = shift.id if shift else None
    query = db.query(models.ProductionWorkOrder).filter_by(tenant_id=tenant_id, plant_id=plant_id)
    if allowed_line_ids is not None:
        query = query.filter(models.ProductionWorkOrder.line_id.in_(allowed_line_ids))
    if shift_id:
        query = query.filter_by(shift_id=shift_id)
    rows = []
    for work_order in query.order_by(models.ProductionWorkOrder.line_id).all():
        forecast = production_forecast(db, work_order, at)
        line = db.get(models.ProductionLine, work_order.line_id)
        deviation = (db.query(models.OperationalDeviation)
                     .filter_by(tenant_id=tenant_id, work_order_id=work_order.id)
                     .filter(models.OperationalDeviation.status.in_(ACTIVE_DEVIATION_STATUSES))
                     .order_by(models.OperationalDeviation.estimated_financial_impact.desc()).first())
        from app.operations.state import derive_line_state
        dimensions = derive_line_state(db, line, work_order, at)
        rows.append({
            "line": {"id": line.id, "name": line.name, "code": line.code},
            "work_order": {"id": work_order.id, "number": work_order.business_number,
                           "product": work_order.product_name},
            "state": dimensions["performance_state"].lower(),
            "execution_state": dimensions["execution_state"], "performance_state": dimensions["performance_state"],
            "machine_health_state": dimensions["machine_health_state"], "quality_state": dimensions["quality_state"],
            "recovery_state": dimensions["recovery_state"], "material_readiness_state": dimensions["material_readiness_state"],
            "target": forecast["target_quantity"], "actual": forecast["actual_quantity"],
            "forecast": forecast["forecast_quantity"], "gap": forecast["gap_quantity"],
            "top_blocker": {"id": deviation.id, "title": deviation.title, "severity": deviation.severity} if deviation else None,
            "freshness": "seeded",
        })
    return {"lines": rows, "at": at}


def line_workspace(db: Session, tenant_id: str, line_id: str, shift_id: str | None,
                   at: datetime | None = None) -> dict | None:
    at = at or utcnow()
    line = db.query(models.ProductionLine).filter_by(id=line_id, tenant_id=tenant_id).first()
    if not line:
        return None
    query = db.query(models.ProductionWorkOrder).filter_by(tenant_id=tenant_id, line_id=line_id)
    if shift_id:
        query = query.filter_by(shift_id=shift_id)
    work_order = query.order_by(models.ProductionWorkOrder.planned_start_at.desc()).first()
    if not work_order:
        return {"line": {"id": line.id, "name": line.name, "code": line.code}, "work_order": None}
    forecast = production_forecast(db, work_order, at)
    deviations = (db.query(models.OperationalDeviation).filter_by(tenant_id=tenant_id, work_order_id=work_order.id)
                  .order_by(models.OperationalDeviation.detected_at.asc()).all())
    downtime = db.query(models.ProductionDowntimeEvent).filter_by(tenant_id=tenant_id, work_order_id=work_order.id).all()
    action = (db.query(models.OperationalAction).join(models.OperationalDeviation)
              .filter(models.OperationalDeviation.work_order_id == work_order.id,
                      models.OperationalAction.status.notin_(("completed", "cancelled"))).first())
    from app.operations.state import derive_line_state
    dimensions = derive_line_state(db, line, work_order, at)
    recovery_case = (db.query(models.RecoveryCase).filter(
        models.RecoveryCase.deviation_id.in_([row.id for row in deviations]),
        models.RecoveryCase.status.notin_(("verified", "failed", "abandoned")))
        .order_by(models.RecoveryCase.opened_at.desc()).first() if deviations else None)
    selected = db.get(models.RecoveryStrategy, recovery_case.selected_strategy_id) if recovery_case and recovery_case.selected_strategy_id else None
    losses: dict[str, float] = {}
    for row in deviations:
        losses[row.category] = losses.get(row.category, 0) + float(row.estimated_lost_units)
    plan_points = (db.query(models.ProductionPlanPoint)
                   .filter_by(tenant_id=tenant_id, work_order_id=work_order.id)
                   .order_by(models.ProductionPlanPoint.recorded_at.asc()).all())
    actual_points = (db.query(models.ProductionActualPoint)
                     .filter_by(tenant_id=tenant_id, work_order_id=work_order.id)
                     .order_by(models.ProductionActualPoint.recorded_at.asc()).all())
    # A PLC/MES restart begins a new cumulative counter epoch. Plotting the old
    # and new epochs as one series creates a false plunge to zero and makes the
    # browser render thousands of points. Keep the newest monotonic segment and
    # sample it evenly for the operational chart while preserving both ends.
    latest_segment: list[models.ProductionActualPoint] = []
    for point in actual_points:
        if latest_segment and float(point.good_quantity) < float(latest_segment[-1].good_quantity):
            latest_segment = []
        latest_segment.append(point)
    if len(latest_segment) > 180:
        step = (len(latest_segment) - 1) / 179
        indexes = sorted({0, len(latest_segment) - 1, *(round(index * step) for index in range(180))})
        latest_segment = [latest_segment[index] for index in indexes]
    if len(plan_points) > 180:
        step = (len(plan_points) - 1) / 179
        indexes = sorted({0, len(plan_points) - 1, *(round(index * step) for index in range(180))})
        plan_points = [plan_points[index] for index in indexes]
    trajectory_by_time: dict[datetime, dict] = {}
    for point in plan_points:
        trajectory_by_time.setdefault(point.recorded_at, {"at": point.recorded_at})["plan"] = point.cumulative_quantity
    for point in latest_segment:
        trajectory_by_time.setdefault(point.recorded_at, {"at": point.recorded_at}).update(
            {"actual": point.good_quantity, "reject": point.reject_quantity})
    trajectory = sorted(trajectory_by_time.values(), key=lambda point: point["at"])
    trajectory.append({"at": work_order.planned_end_at, "plan": forecast["target_quantity"],
                       "forecast": forecast["forecast_quantity"]})
    return {
        "line": {"id": line.id, "name": line.name, "code": line.code},
        "work_order": {"id": work_order.id, "number": work_order.business_number,
                       "product_code": work_order.product_code, "product_name": work_order.product_name},
        "forecast": forecast,
        "trajectory": trajectory,
        "state": dimensions["performance_state"].lower(),
        "execution_state": dimensions["execution_state"], "performance_state": dimensions["performance_state"],
        "machine_health_state": dimensions["machine_health_state"], "quality_state": dimensions["quality_state"],
        "recovery_state": dimensions["recovery_state"], "material_readiness_state": dimensions["material_readiness_state"],
        "recovery": ({"case_id":recovery_case.id,"status":recovery_case.status,
                      "strategy":selected.title if selected else None,
                      "expected_recovered_units":selected.expected_recovered_units if selected else None,
                      "remaining_expected_gap":max(-float(forecast["gap_quantity"]) - float(selected.expected_recovered_units or 0), 0) if selected else max(-float(forecast["gap_quantity"]),0)}
                     if recovery_case else None),
        "timeline": [{"id": row.id,
                      "type": row.category if row.category in {"changeover", "material_wait", "quality_hold"} else "planned_downtime" if row.planned else "downtime",
                      "start": row.started_at, "end": row.ended_at, "reason": row.reason,
                      "duration_minutes": round(max(((_compatible_time(row.ended_at, row.started_at) if row.ended_at else at) - row.started_at).total_seconds() / 60, 0), 1),
                      "impact": "Planned capacity window" if row.planned else "Production output at risk",
                      "deviation_id": next((item.id for item in deviations if item.asset_id == row.asset_id), None)} for row in downtime],
        "loss_tree": [{"category": key, "lost_units": value} for key, value in losses.items()],
        "deviations": [serialize_deviation(row) for row in deviations],
        "current_action": serialize_action(action) if action else None,
    }


def serialize_action(row: models.OperationalAction) -> dict:
    return {"id": row.id, "deviation_id": row.deviation_id, "task_id": row.task_id,
            "title": row.title, "description": row.description, "status": row.status,
            "priority": row.priority, "owner_role": row.owner_role, "owner_user_id": row.owner_user_id,
            "due_at": row.due_at, "expected_outcome": row.expected_outcome,
            "completion_outcome": row.completion_outcome, "version": row.version}


def serialize_deviation(row: models.OperationalDeviation) -> dict:
    return {"id": row.id, "category": row.category, "subtype": row.subtype, "title": row.title,
            "detector_key": row.detector_key, "severity": row.severity, "status": row.status,
            "line_id": row.line_id, "shift_id": row.shift_id, "work_order_id": row.work_order_id,
            "asset_id": row.asset_id, "detected_at": row.detected_at, "started_at": row.started_at,
            "expected_state": row.expected_state, "actual_state": row.actual_state,
            "forecast_state": row.forecast_state, "lost_units": row.estimated_lost_units,
            "time_impact_minutes": row.estimated_time_impact_minutes,
            "financial_impact": row.estimated_financial_impact, "currency": row.currency,
            "owner_role": row.owner_role, "owner_user_id": row.owner_user_id,
            "resolved_at": row.resolved_at, "verified_at": row.verified_at,
            "verified_outcome": row.verified_outcome, "version": row.version}
