from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db import models as core_models
from app.domains import workflows
from app.scm import models
from app.scm.engine import ENGINE_VERSION, PlanningEvent, PlanningPolicy, decimal, plan_material


DEFAULT_POLICY_RULES: dict[str, Any] = {
    "horizon_days": 210,
    "availability_method": "EXPLICIT_AVAILABLE",
    "same_day_order": "DEMAND_BEFORE_SUPPLY",
    "stockout_inclusive_zero": True,
    "include_overdue_supply": False,
    "forecast_bucket_strategy": "START_DATE",
    "forecast_consumption": "REQUIRE_EXPLICIT_POLICY_ON_OVERLAP",
    "average_demand_window_days": 30,
    "severity": {"critical_days": 7, "red_days": 30},
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_event_source(value: str, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Preserve long external identities while fitting the indexed event key."""
    if len(value) <= 64:
        return value, metadata
    import hashlib
    return hashlib.sha256(value.encode()).hexdigest(), {
        **metadata, "original_source_entity_id": value,
    }


def ensure_default_policy(db: Session, user: core_models.User) -> models.SCMPlanningPolicySet:
    row = (
        db.query(models.SCMPlanningPolicySet)
        .filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, status="ACTIVE")
        .order_by(models.SCMPlanningPolicySet.policy_version.desc())
        .first()
    )
    if row:
        return row
    row = models.SCMPlanningPolicySet(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        name="Conservative scaffold",
        policy_version=1,
        status="ACTIVE",
        effective_from=utcnow(),
        rules=DEFAULT_POLICY_RULES,
        created_by_user_id=user.id,
        approved_by_user_id=user.id,
        approved_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def ensure_baseline_scenario(db: Session, user: core_models.User) -> models.SCMPlanningScenario:
    row = db.query(models.SCMPlanningScenario).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, scenario_type="BASELINE", status="ACTIVE"
    ).first()
    if row:
        return row
    row = models.SCMPlanningScenario(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        name="Baseline",
        scenario_type="BASELINE",
        created_by_user_id=user.id,
        status="ACTIVE",
    )
    db.add(row)
    db.flush()
    return row


def create_run(
    db: Session,
    user: core_models.User,
    *,
    as_of_at: datetime | None = None,
    scenario_id: str | None = None,
    trigger_key: str | None = None,
    demand_plan_id: str | None = None,
    trigger_type: str | None = None,
    correlation_id: str | None = None,
) -> models.SCMPlanningRun:
    from app.scm.planning import ensure_profile, latest_published_demand_plan
    policy = ensure_default_policy(db, user)
    profile = ensure_profile(db, user)
    demand_plan = (db.get(models.SCMDemandPlan, demand_plan_id) if demand_plan_id
                   else latest_published_demand_plan(db, user.tenant_id, user.plant_id))
    scenario = db.get(models.SCMPlanningScenario, scenario_id) if scenario_id else ensure_baseline_scenario(db, user)
    if not scenario or scenario.tenant_id != user.tenant_id or scenario.plant_id != user.plant_id:
        raise ValueError("Scenario is outside the selected SCM scope")
    as_of_at = as_of_at or utcnow()
    horizon_days = int((policy.rules or {}).get("horizon_days", profile.planning_horizon_days))
    run = models.SCMPlanningRun(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        scenario_id=scenario.id,
        policy_id=policy.id,
        as_of_at=as_of_at,
        horizon_start=as_of_at.date(),
        horizon_end=as_of_at.date() + timedelta(days=horizon_days - 1),
        input_version_summary={},
        engine_version=ENGINE_VERSION,
        policy_version=policy.policy_version,
        status="QUEUED",
        trigger_key=trigger_key,
        planning_profile_id=profile.id, demand_plan_id=demand_plan.id if demand_plan else None,
        trigger_type=trigger_type or ("EVENT_DRIVEN" if trigger_key else "MANUAL"),
        correlation_id=correlation_id,
    )
    db.add(run)
    db.flush()
    from app.scm.planning import assemble_input_snapshot
    snapshot = assemble_input_snapshot(db, run, profile, demand_plan)
    run.input_version_summary = {"snapshot_id": snapshot.id, "snapshot_hash": snapshot.payload_hash,
                                 "demand_plan_id": run.demand_plan_id,
                                 "materials": len(snapshot.payload.get("materials", []))}
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.email, "scm.planning_run.queued",
        "scm_planning_run", run.id, actor_user_id=user.id,
        meta={"scenario_id": scenario.id, "policy_version": policy.policy_version},
    )
    return run


def _latest_inventory(db: Session, run: models.SCMPlanningRun, material_id: str) -> models.SCMInventorySnapshot | None:
    return (
        db.query(models.SCMInventorySnapshot)
        .filter_by(tenant_id=run.tenant_id, plant_id=run.plant_id, material_id=material_id)
        .filter(models.SCMInventorySnapshot.snapshot_at <= run.as_of_at)
        .order_by(models.SCMInventorySnapshot.snapshot_at.desc())
        .first()
    )


def _material_policy(db: Session, run: models.SCMPlanningRun, material_id: str) -> models.SCMMaterialPlantPolicy | None:
    return db.query(models.SCMMaterialPlantPolicy).filter_by(
        tenant_id=run.tenant_id, plant_id=run.plant_id, material_id=material_id, active=True
    ).first()


def _source_events(db: Session, run: models.SCMPlanningRun, material_id: str) -> list[PlanningEvent]:
    events: list[PlanningEvent] = []
    requirements = (
        db.query(models.SCMMaterialRequirement)
        .filter_by(tenant_id=run.tenant_id, plant_id=run.plant_id, material_id=material_id)
        .filter(models.SCMMaterialRequirement.required_date.between(run.horizon_start, run.horizon_end))
        .all()
    )
    for row in requirements:
        events.append(PlanningEvent(
            str(uuid4()), row.requirement_type, row.required_date, -decimal(row.quantity),
            "scm_material_requirement", row.id, "FIRM", row.priority,
            {"finished_good_id": row.finished_good_id, "customer_id": row.customer_id, "lineage": row.lineage},
        ))
    # Until a forecast-consumption rule is selected, a firm/explicit material
    # requirement wins and forecasts are used only when no requirement exists.
    if not requirements:
        forecasts = (
            db.query(models.SCMDemandForecast)
            .filter_by(tenant_id=run.tenant_id, plant_id=run.plant_id, material_id=material_id)
            .filter(models.SCMDemandForecast.bucket_start.between(run.horizon_start, run.horizon_end))
            .all()
        )
        for row in forecasts:
            events.append(PlanningEvent(
                str(uuid4()), "FORECAST", row.bucket_start, -decimal(row.quantity),
                "scm_demand_forecast", row.id, "FORECAST", 500,
                {"customer_id": row.customer_id, "forecast_version": row.forecast_version},
            ))
    schedules = (
        db.query(models.SCMSupplyScheduleLine, models.SCMSupplyOrder)
        .join(models.SCMSupplyOrder, models.SCMSupplyOrder.id == models.SCMSupplyScheduleLine.supply_order_id)
        .filter(
            models.SCMSupplyScheduleLine.tenant_id == run.tenant_id,
            models.SCMSupplyScheduleLine.plant_id == run.plant_id,
            models.SCMSupplyOrder.material_id == material_id,
            models.SCMSupplyScheduleLine.status.in_(("OPEN", "PARTIAL", "CONFIRMED")),
            models.SCMSupplyScheduleLine.current_due_date <= run.horizon_end,
        ).all()
    )
    policy_row = db.get(models.SCMPlanningPolicySet, run.policy_id)
    include_overdue = bool((policy_row.rules or {}).get("include_overdue_supply", False))
    for schedule, order in schedules:
        event_date = schedule.current_due_date
        if event_date < run.horizon_start:
            if not include_overdue:
                continue
            event_date = run.horizon_start
        open_qty = max(decimal(schedule.scheduled_qty) - decimal(schedule.received_qty), Decimal("0"))
        if open_qty <= 0:
            continue
        supplier_rule = db.query(models.SCMMaterialSupplier).filter_by(
            tenant_id=run.tenant_id, plant_id=run.plant_id, material_id=material_id, supplier_id=order.supplier_id
        ).first() if order.supplier_id else None
        events.append(PlanningEvent(
            str(uuid4()), order.supply_type, event_date, open_qty,
            "scm_supply_schedule_line", schedule.id, order.firmness, 100,
            {
                "order_id": order.id, "order_number": order.order_number,
                "supplier_id": order.supplier_id,
                "cancellation_allowed": bool(supplier_rule and supplier_rule.cancellation_allowed),
                "pushout_allowed": bool(supplier_rule and supplier_rule.pushout_allowed),
                "expedite_allowed": bool(not supplier_rule or supplier_rule.expedite_allowed),
            },
        ))
    return events


def _clear_partial_results(db: Session, run_id: str) -> None:
    db.query(models.SCMRecommendation).filter_by(planning_run_id=run_id).delete(synchronize_session=False)
    db.query(models.SCMSupplyDemandPeg).filter_by(planning_run_id=run_id).delete(synchronize_session=False)
    db.query(models.SCMMaterialRiskSummary).filter_by(planning_run_id=run_id).delete(synchronize_session=False)
    db.query(models.SCMMaterialProjectionPoint).filter_by(planning_run_id=run_id).delete(synchronize_session=False)
    db.query(models.SCMPlanningEvent).filter_by(planning_run_id=run_id).delete(synchronize_session=False)


def execute_run(db: Session, run_id: str) -> models.SCMPlanningRun:
    """Execute only against the immutable input snapshot captured at queue time."""
    import hashlib
    from app.scm.engine import excess_windows, shortage_windows
    from app.scm.planning import assemble_input_snapshot, ensure_profile
    from app.scm.risks import build_product_readiness, build_run_deltas, reconcile_material_risks, synchronize_case_decisions

    run = db.query(models.SCMPlanningRun).filter_by(id=run_id).with_for_update().first()
    if not run:
        raise LookupError("SCM planning run not found")
    if run.status == "COMPLETED":
        return run
    user = db.query(core_models.User).filter_by(tenant_id=run.tenant_id, plant_id=run.plant_id,
                                                role="admin", is_active=True).first()
    profile = db.get(models.SCMPlanningProfile, run.planning_profile_id) if run.planning_profile_id else (ensure_profile(db, user) if user else None)
    demand_plan = db.get(models.SCMDemandPlan, run.demand_plan_id) if run.demand_plan_id else None
    if not profile:
        raise ValueError("Planning profile unavailable")
    snapshot = db.query(models.SCMPlanningInputSnapshot).filter_by(planning_run_id=run.id).first()
    snapshot = snapshot or assemble_input_snapshot(db, run, profile, demand_plan)
    _clear_partial_results(db, run.id)
    db.query(models.SCMShortageWindow).filter_by(planning_run_id=run.id).delete(synchronize_session=False)
    db.query(models.SCMPlanningRunDelta).filter_by(planning_run_id=run.id).delete(synchronize_session=False)
    run.status, run.started_at, run.error_summary = "RUNNING", utcnow(), None
    policy_row = db.get(models.SCMPlanningPolicySet, run.policy_id)
    exceptions = 0
    for material_input in snapshot.payload.get("materials", []):
        material_id = material_input["scm_material_id"]
        canonical_id = material_input.get("canonical_material_id")
        material_rules = material_input.get("policy") or {}
        policy = PlanningPolicy.from_rules({**(policy_row.rules or {}),
            "horizon_days": (run.horizon_end - run.horizon_start).days + 1,
            "minimum_order_qty": material_rules.get("minimum_order_qty", 0),
            "order_multiple": material_rules.get("order_multiple", 1),
            "maximum_coverage_days": material_rules.get("maximum_coverage_days")},
            safety_stock_qty=Decimal(material_rules.get("safety_stock_qty", "0")))
        source_events: list[PlanningEvent] = []
        for index, demand in enumerate(material_input.get("demands", [])):
            event_id = hashlib.sha256(f"{run.id}:demand:{demand['id']}:{index}".encode()).hexdigest()[:36]
            source_events.append(PlanningEvent(event_id, demand.get("demand_type", "DEMAND"),
                datetime.fromisoformat(demand["date"]).date(), -Decimal(demand["quantity"]),
                "demand_bucket", demand["id"], "FIRM", 50,
                {"canonical_material_id": canonical_id, "work_order_id": demand.get("work_order_id"),
                 "customer_id": demand.get("customer_id"), "lineage": demand.get("lineage") or {},
                 "suppressed_source_ids": demand.get("suppressed_source_ids", [])}))
        for index, supply in enumerate(material_input.get("supplies", [])):
            event_id = hashlib.sha256(f"{run.id}:supply:{supply['id']}:{index}".encode()).hexdigest()[:36]
            source_events.append(PlanningEvent(event_id, supply.get("event_type", "SUPPLY"),
                datetime.fromisoformat(supply["date"]).date(), Decimal(supply["quantity"]),
                "purchase_order" if supply.get("canonical_purchase_order_id") else "scm_supply_schedule_line",
                supply.get("canonical_purchase_order_id") or supply["id"], supply.get("firmness", "FIRM"), 100,
                {key: value for key, value in supply.items() if key not in {"date", "quantity"}}))
        opening = Decimal(material_input.get("opening_available", "0"))
        opening_id = hashlib.sha256(f"{run.id}:opening:{material_id}".encode()).hexdigest()[:36]
        result = plan_material(as_of=run.horizon_start, opening_available=opening,
            events=source_events, policy=policy, stale=bool(material_input.get("stale")), opening_event_id=opening_id)
        persisted_events = [models.SCMPlanningEvent(id=opening_id, tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, scenario_id=run.scenario_id, event_type="OPENING_INVENTORY",
            material_id=material_id, event_date=run.horizon_start, quantity_delta=opening,
            source_entity_type="scm_inventory_snapshot",
            source_entity_id=material_input.get("inventory_snapshot_id") or f"missing:{material_id}",
            firmness="FIRM", priority=0, evidence_type="DETECTED_FACT",
            metadata_json={"stale": material_input.get("stale"), "canonical_material_id": canonical_id})]
        for event in source_events:
            source_id, event_metadata = _bounded_event_source(str(event.source_entity_id), event.metadata)
            persisted_events.append(models.SCMPlanningEvent(id=event.event_id, tenant_id=run.tenant_id,
                plant_id=run.plant_id, planning_run_id=run.id, scenario_id=run.scenario_id,
                event_type=event.event_type, material_id=material_id, event_date=event.event_date,
                quantity_delta=event.quantity_delta, source_entity_type=event.source_entity_type,
                source_entity_id=source_id, firmness=event.firmness, priority=event.priority,
                evidence_type="DETECTED_FACT", metadata_json=event_metadata))
        db.add_all(persisted_events)
        db.flush()
        confirmed_by_date: dict = {}
        planned_by_date: dict = {}
        for event in source_events:
            if event.is_supply:
                target = confirmed_by_date if event.firmness == "FIRM" else planned_by_date
                target[event.event_date] = target.get(event.event_date, Decimal("0")) + event.quantity_delta
        average_daily = sum((event.quantity_delta * -1 for event in source_events if event.is_demand and
            event.event_date < run.horizon_start + timedelta(days=policy.average_demand_window_days)), Decimal("0")) / Decimal(policy.average_demand_window_days or 1)
        maximum_inventory = average_daily * Decimal(policy.maximum_coverage_days) if policy.maximum_coverage_days is not None else None
        for point in result.points:
            after_safety = point.closing_balance - point.safety_stock_qty
            shortage = max(-after_safety, Decimal("0"))
            excess = max(point.closing_balance - maximum_inventory, Decimal("0")) if maximum_inventory is not None else Decimal("0")
            status = ("UNKNOWN" if material_input.get("stale") else "CRITICAL" if point.closing_balance <= 0
                      else "AT_RISK" if after_safety < 0 else "EXCESS" if excess > 0 else "HEALTHY")
            db.add(models.SCMMaterialProjectionPoint(tenant_id=run.tenant_id, plant_id=run.plant_id,
                planning_run_id=run.id, material_id=material_id, canonical_material_id=canonical_id,
                projection_date=point.projection_date, opening_balance=point.opening_balance,
                supply_qty=point.supply_qty, demand_qty=point.demand_qty, closing_balance=point.closing_balance,
                safety_stock_qty=point.safety_stock_qty, risk_status=point.risk_status,
                confirmed_receipts=confirmed_by_date.get(point.projection_date, Decimal("0")),
                planned_receipts=planned_by_date.get(point.projection_date, Decimal("0")),
                gross_demand=point.demand_qty, reserved_demand=Decimal("0"),
                projected_after_safety=after_safety, shortage_qty=shortage, excess_qty=excess,
                runway_days=result.runway_days, planning_status=status,
                source_freshness={"inventory_observed_at": material_input.get("inventory_observed_at"),
                                  "stale": material_input.get("stale")}))
        windows = shortage_windows(result.points)
        for window in windows:
            if canonical_id:
                db.add(models.SCMShortageWindow(tenant_id=run.tenant_id, plant_id=run.plant_id,
                    planning_run_id=run.id, material_id=material_id, canonical_material_id=canonical_id,
                    start_date=window.start_date, end_date=window.end_date, duration_days=window.duration_days,
                    max_shortage_qty=window.peak_quantity, recovery_date=window.recovery_date))
        excess_ranges = excess_windows(result.points, maximum_inventory)
        affected_products = {
            event.metadata.get("lineage", {}).get("product_id")
            or event.metadata.get("lineage", {}).get("finished_good_code")
            for event in source_events
            if (event.metadata.get("lineage", {}).get("product_id")
                or event.metadata.get("lineage", {}).get("finished_good_code"))}
        affected_customers = {event.metadata.get("customer_id") for event in source_events
                              if event.metadata.get("customer_id")}
        explanation = {"classification": "CALCULATED_RESULT", "as_of_date": run.horizon_start.isoformat(),
            "opening_available_qty": str(opening), "inventory_snapshot_id": material_input.get("inventory_snapshot_id"),
            "first_threshold_breach_date": result.first_breach_date.isoformat() if result.first_breach_date else None,
            "first_stockout_date": result.stockout_date.isoformat() if result.stockout_date else None,
            "peak_shortage_qty": str(result.peak_shortage_qty),
            "next_recovery_date": result.recovery_date.isoformat() if result.recovery_date else None,
            "shortage_windows": [{"start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat(),
                                  "duration_days": row.duration_days, "max_shortage_qty": str(row.peak_quantity)} for row in windows],
            "excess_windows": [{"start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat(),
                                "duration_days": row.duration_days, "max_excess_qty": str(row.peak_quantity)} for row in excess_ranges],
            "policy_version": run.policy_version, "planning_run_id": run.id,
            "input_snapshot_id": snapshot.id, "input_snapshot_hash": snapshot.payload_hash,
            "data_stale": material_input.get("stale")}
        risk = models.SCMMaterialRiskSummary(tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, material_id=material_id, first_breach_date=result.first_breach_date,
            stockout_date=result.stockout_date, shortage_qty=result.peak_shortage_qty,
            recovery_date=result.recovery_date, severity=result.severity, priority_score=result.priority_score,
            priority_factors=result.priority_factors, affected_finished_goods_count=len(affected_products),
            affected_customers_count=len(affected_customers), recommended_action_count=len(result.recommendations), explanation=explanation)
        db.add(risk)
        db.flush()
        db.add_all(models.SCMSupplyDemandPeg(tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, scenario_id=run.scenario_id, material_id=material_id,
            supply_event_id=peg.supply_event_id, demand_event_id=peg.demand_event_id,
            pegged_qty=peg.quantity, peg_strategy=peg.strategy) for peg in result.pegs)
        db.add_all(models.SCMRecommendation(tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, risk_summary_id=risk.id, material_id=material_id,
            action_type=rec.action_type, quantity=rec.quantity, current_date=rec.current_date,
            proposed_date=rec.proposed_date, source_entity_type=rec.source_entity_type,
            source_entity_id=rec.source_entity_id, reason=rec.reason,
            constraints_checked=list(rec.constraints_checked),
            evidence=[{"classification": "RECOMMENDATION", "planning_run_id": run.id,
                       "input_snapshot_hash": snapshot.payload_hash}], status="PENDING") for rec in result.recommendations)
        if result.peak_shortage_qty > 0 and canonical_id:
            from app.platform.models import PlatformInventoryPosition
            origin = db.query(PlatformInventoryPosition).filter(
                PlatformInventoryPosition.tenant_id == run.tenant_id,
                PlatformInventoryPosition.material_id == canonical_id,
                PlatformInventoryPosition.plant_id != run.plant_id,
                PlatformInventoryPosition.freshness_status == "fresh").order_by(
                PlatformInventoryPosition.available_qty.desc()).first()
            if origin and Decimal(str(origin.available_qty)) > result.peak_shortage_qty:
                db.add(models.SCMRecommendation(tenant_id=run.tenant_id, plant_id=run.plant_id,
                    planning_run_id=run.id, risk_summary_id=risk.id, material_id=material_id,
                    action_type="INTERPLANT_TRANSFER", quantity=result.peak_shortage_qty,
                    current_date=None, proposed_date=max(run.horizon_start, result.stockout_date - timedelta(days=2)),
                    source_entity_type="inventory_position", source_entity_id=origin.id,
                    reason="Another plant retains sufficient fresh available inventory after this transfer.",
                    constraints_checked=[{"constraint": "origin_remains_positive", "passed": True},
                        {"constraint": "transfer_lead_time_days", "value": 2, "passed": True}],
                    evidence=[{"classification": "DETECTED_FACT", "origin_plant_id": origin.plant_id,
                               "origin_available_qty": str(origin.available_qty)}], status="PENDING"))
        if result.severity not in {"GREEN", "UNKNOWN"} or excess_ranges:
            exceptions += 1
    db.flush()
    run.status, run.completed_at = "COMPLETED", utcnow()
    run.materials_processed = len(snapshot.payload.get("materials", []))
    run.exceptions_generated = exceptions
    readiness_count = build_product_readiness(db, run, snapshot)
    db.flush()
    risk_count = reconcile_material_risks(db, run, snapshot)
    delta_count = build_run_deltas(db, run, snapshot)
    from app.scm.recommendations import rank_run_recommendations
    rank_run_recommendations(db, run.id)
    decision_count = synchronize_case_decisions(db, run, snapshot)
    run.summary_json = {"materials": run.materials_processed, "exceptions": exceptions,
                        "active_risks": risk_count, "product_readiness": readiness_count,
                        "case_decisions": decision_count, "changed_materials": delta_count,
                        "horizon_days": (run.horizon_end - run.horizon_start).days + 1,
                        "input_snapshot_hash": snapshot.payload_hash}
    from app.platform.events import DomainEvent, publish
    publish(db, DomainEvent("scm.planning.completed", run.tenant_id, run.plant_id,
        "scm_planning_run", run.id, {"planning_run_id": run.id,
        "materials_processed": run.materials_processed, "exceptions_generated": exceptions},
        correlation_id=run.correlation_id, causation_id=run.trigger_key, source_system="scm"))
    return run


def _execute_run_legacy(db: Session, run_id: str) -> models.SCMPlanningRun:
    run = db.query(models.SCMPlanningRun).filter_by(id=run_id).with_for_update().first()
    if not run:
        raise LookupError("SCM planning run not found")
    if run.status == "COMPLETED":
        return run
    _clear_partial_results(db, run.id)
    run.status = "RUNNING"
    run.started_at = utcnow()
    run.error_summary = None
    db.flush()
    policy_row = db.get(models.SCMPlanningPolicySet, run.policy_id)
    material_plants = db.query(models.SCMMaterialPlant).filter_by(
        tenant_id=run.tenant_id, plant_id=run.plant_id, active=True
    ).all()
    exceptions = 0
    for link in material_plants:
        material_policy = _material_policy(db, run, link.material_id)
        policy = PlanningPolicy.from_rules(
            policy_row.rules,
            safety_stock_qty=material_policy.safety_stock_qty if material_policy else None,
        )
        if material_policy:
            policy = PlanningPolicy.from_rules({
                **policy.as_dict(),
                "planned_lead_time_days": material_policy.planned_lead_time_days or policy.planned_lead_time_days,
                "planning_time_fence_days": material_policy.planning_time_fence_days or policy.planning_time_fence_days,
                "cancellation_window_days": material_policy.cancellation_window_days or policy.cancellation_window_days,
                "minimum_order_qty": str(material_policy.minimum_order_qty or policy.minimum_order_qty),
                "order_multiple": str(material_policy.order_multiple or policy.order_multiple),
                "maximum_coverage_days": material_policy.maximum_coverage_days or policy.maximum_coverage_days,
            }, safety_stock_qty=material_policy.safety_stock_qty)
        inventory = _latest_inventory(db, run, link.material_id)
        stale = inventory is None or inventory.available_qty is None
        if inventory and inventory.snapshot_at:
            observed = inventory.snapshot_at if inventory.snapshot_at.tzinfo else inventory.snapshot_at.replace(tzinfo=timezone.utc)
            stale = stale or (run.as_of_at - observed).total_seconds() > 90000
        opening = decimal(inventory.available_qty if inventory else 0)
        source_events = _source_events(db, run, link.material_id)
        opening_id = str(uuid4())
        result = plan_material(
            as_of=run.horizon_start,
            opening_available=opening,
            events=source_events,
            policy=policy,
            stale=stale,
            opening_event_id=opening_id,
        )
        persisted_events = [
            models.SCMPlanningEvent(
                id=opening_id, tenant_id=run.tenant_id, plant_id=run.plant_id,
                planning_run_id=run.id, scenario_id=run.scenario_id,
                event_type="OPENING_INVENTORY", material_id=link.material_id,
                event_date=run.horizon_start, quantity_delta=opening,
                source_entity_type="scm_inventory_snapshot",
                source_entity_id=inventory.id if inventory else f"missing:{link.material_id}",
                firmness="FIRM", priority=0, evidence_type="DETECTED_FACT",
                metadata_json={"stale": stale},
            )
        ]
        for event in source_events:
            source_id, event_metadata = _bounded_event_source(str(event.source_entity_id), event.metadata)
            persisted_events.append(models.SCMPlanningEvent(
                id=event.event_id, tenant_id=run.tenant_id, plant_id=run.plant_id,
                planning_run_id=run.id, scenario_id=run.scenario_id,
                event_type=event.event_type, material_id=link.material_id,
                event_date=event.event_date, quantity_delta=event.quantity_delta,
                source_entity_type=event.source_entity_type, source_entity_id=source_id,
                firmness=event.firmness, priority=event.priority,
                evidence_type="DETECTED_FACT", metadata_json=event_metadata,
            ))
        db.add_all(persisted_events)
        db.flush()
        db.add_all(models.SCMMaterialProjectionPoint(
            tenant_id=run.tenant_id, plant_id=run.plant_id, planning_run_id=run.id,
            material_id=link.material_id, projection_date=point.projection_date,
            opening_balance=point.opening_balance, supply_qty=point.supply_qty,
            demand_qty=point.demand_qty, closing_balance=point.closing_balance,
            safety_stock_qty=point.safety_stock_qty, risk_status=point.risk_status,
        ) for point in result.points)
        affected_finished_goods = {event.metadata.get("finished_good_id") for event in source_events if event.metadata.get("finished_good_id")}
        affected_customers = {event.metadata.get("customer_id") for event in source_events if event.metadata.get("customer_id")}
        explanation = {
            "classification": "CALCULATED_RESULT",
            "as_of_date": run.horizon_start.isoformat(),
            "opening_available_qty": str(opening),
            "inventory_snapshot_id": inventory.id if inventory else None,
            "first_threshold_breach_date": result.first_breach_date.isoformat() if result.first_breach_date else None,
            "first_stockout_date": result.stockout_date.isoformat() if result.stockout_date else None,
            "peak_shortage_qty": str(result.peak_shortage_qty),
            "next_recovery_date": result.recovery_date.isoformat() if result.recovery_date else None,
            "triggering_demands": [event.source_entity_id for event in source_events if event.is_demand],
            "expected_supplies": [event.source_entity_id for event in source_events if event.is_supply],
            "policy_version": run.policy_version,
            "planning_run_id": run.id,
            "data_stale": stale,
        }
        risk = models.SCMMaterialRiskSummary(
            tenant_id=run.tenant_id, plant_id=run.plant_id, planning_run_id=run.id,
            material_id=link.material_id, first_breach_date=result.first_breach_date,
            stockout_date=result.stockout_date, shortage_qty=result.peak_shortage_qty,
            recovery_date=result.recovery_date, severity=result.severity,
            priority_score=result.priority_score, priority_factors=result.priority_factors,
            affected_finished_goods_count=len(affected_finished_goods),
            affected_customers_count=len(affected_customers),
            recommended_action_count=len(result.recommendations), explanation=explanation,
        )
        db.add(risk)
        db.flush()
        db.add_all(models.SCMSupplyDemandPeg(
            tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, scenario_id=run.scenario_id,
            material_id=link.material_id, supply_event_id=peg.supply_event_id,
            demand_event_id=peg.demand_event_id, pegged_qty=peg.quantity,
            peg_strategy=peg.strategy,
        ) for peg in result.pegs)
        db.add_all(models.SCMRecommendation(
            tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, risk_summary_id=risk.id,
            material_id=link.material_id, action_type=rec.action_type,
            quantity=rec.quantity, current_date=rec.current_date,
            proposed_date=rec.proposed_date, source_entity_type=rec.source_entity_type,
            source_entity_id=rec.source_entity_id, reason=rec.reason,
            constraints_checked=list(rec.constraints_checked),
            evidence=[{"classification": "RECOMMENDATION", "planning_run_id": run.id}],
            status="PENDING",
        ) for rec in result.recommendations)
        if result.severity not in {"GREEN", "UNKNOWN"}:
            exceptions += 1
    run.status = "COMPLETED"
    run.completed_at = utcnow()
    run.materials_processed = len(material_plants)
    run.exceptions_generated = exceptions
    inventory_times = []
    for row in material_plants:
        latest = _latest_inventory(db, run, row.material_id)
        if latest:
            inventory_times.append(latest.snapshot_at)
    latest_inventory_at = max(inventory_times, default=None)
    run.input_version_summary = {
        "materials": len(material_plants),
        "inventory_latest_at": latest_inventory_at.isoformat() if latest_inventory_at else None,
    }
    # Publish only after the calculation has reached a stable, persisted
    # result.  The platform projection consumer is idempotent and reads this
    # result rather than owning SCM planning behaviour.
    from app.platform.events import DomainEvent, publish
    publish(db, DomainEvent(
        event_type="scm.planning.completed", tenant_id=run.tenant_id, plant_id=run.plant_id,
        subject_type="scm_planning_run", subject_id=run.id,
        payload={"planning_run_id": run.id, "materials_processed": run.materials_processed,
                 "exceptions_generated": run.exceptions_generated},
        source_system="scm",
        correlation_id=(db.query(core_models.EventOutbox.correlation_id).filter_by(event_id=run.trigger_key).scalar()
                        if run.trigger_key else None),
        causation_id=run.trigger_key,
    ))
    return run


def fail_run(db: Session, run_id: str, error: Exception) -> None:
    run = db.get(models.SCMPlanningRun, run_id)
    if run:
        run.status = "FAILED"
        run.completed_at = utcnow()
        run.error_summary = f"{type(error).__name__}: {str(error)[:1500]}"


def ensure_shortage_intervention(db: Session, risk: models.SCMMaterialRiskSummary) -> models.SCMRecommendation | None:
    """Produce one conservative PO-date intervention when the planner exposes a shortage but no candidate."""
    existing = db.query(models.SCMRecommendation).filter_by(risk_summary_id=risk.id).order_by(
        models.SCMRecommendation.created_at).first()
    if existing or not risk.stockout_date:
        return existing
    schedule, order = db.query(models.SCMSupplyScheduleLine, models.SCMSupplyOrder).join(
        models.SCMSupplyOrder, models.SCMSupplyOrder.id == models.SCMSupplyScheduleLine.supply_order_id).filter(
        models.SCMSupplyOrder.tenant_id == risk.tenant_id, models.SCMSupplyOrder.plant_id == risk.plant_id,
        models.SCMSupplyOrder.material_id == risk.material_id,
        models.SCMSupplyScheduleLine.current_due_date > risk.stockout_date,
        models.SCMSupplyScheduleLine.status.in_(["OPEN", "PARTIAL", "CONFIRMED"])).order_by(
        models.SCMSupplyScheduleLine.current_due_date).first() or (None, None)
    if not schedule:
        return None
    proposed = risk.stockout_date - timedelta(days=1)
    row = models.SCMRecommendation(tenant_id=risk.tenant_id, plant_id=risk.plant_id,
        planning_run_id=risk.planning_run_id, risk_summary_id=risk.id, material_id=risk.material_id,
        action_type="RESCHEDULE_PURCHASE_ORDER", quantity=max(schedule.scheduled_qty - schedule.received_qty, Decimal("0")),
        current_date=schedule.current_due_date, proposed_date=proposed,
        source_entity_type=order.source_entity_type or "scm_supply_order",
        source_entity_id=order.source_entity_id or order.id,
        reason=f"Confirmed supply arrives after projected stockout on {risk.stockout_date.isoformat()}",
        constraints_checked=[{"key": "before_stockout", "passed": True}],
        evidence=[{"classification": "RECOMMENDATION", "planning_run_id": risk.planning_run_id,
                   "risk_summary_id": risk.id}], status="PENDING")
    db.add(row)
    db.flush()
    risk.recommended_action_count = max(risk.recommended_action_count, 1)
    from app.scm.recommendations import rank_run_recommendations
    rank_run_recommendations(db, risk.planning_run_id)
    return row
