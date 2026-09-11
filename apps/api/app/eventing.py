"""Transactional outbox dispatch with consumer idempotency and replay safety."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextvars import ContextVar
from typing import Callable

from sqlalchemy.orm import Session

from app import cycle_orchestration
from app.db import models

Consumer = Callable[[Session, models.EventOutbox], None]
CONSUMERS: dict[str, list[tuple[str, Consumer]]] = {}
MAX_ATTEMPTS = 5
correlation_context: ContextVar[str | None] = ContextVar("event_correlation_id", default=None)


def subscribe(event_type: str, name: str):
    def decorator(consumer: Consumer) -> Consumer:
        CONSUMERS.setdefault(event_type, []).append((name, consumer))
        return consumer
    return decorator


@subscribe("*", "cycle_evaluator")
def evaluate_cycle_consumer(db: Session, event: models.EventOutbox) -> None:
    requirement_id = event.payload.get("requirement_id")
    if not requirement_id and event.payload.get("objective_id"):
        objective = db.get(models.ProcurementCycleObjective, event.payload["objective_id"])
        requirement_id = objective.requirement_id if objective else None
    requirement = db.query(models.PurchaseRequirement).filter_by(
        id=requirement_id, tenant_id=event.tenant_id,
    ).with_for_update().first()
    if requirement is not None:
        cycle_orchestration.evaluate(db, requirement, event.actor_membership_id, event.correlation_id)


@subscribe("*", "companion_orchestrator")
def companion_consumer(db: Session, event: models.EventOutbox) -> None:
    from app.companion import process_event
    process_event(db, event)


@subscribe("gigi.activity.created", "v2_objective_agent")
def v2_objective_agent_consumer(db: Session, event: models.EventOutbox) -> None:
    from app.operations.agents import run
    agent_type = event.payload.get("agent_type")
    if not agent_type:
        return
    run(db, agent_type, {**event.payload, "tenant_id": event.tenant_id,
                         "plant_id": event.plant_id, "event_id": event.event_id,
                         "correlation_id": event.correlation_id})


SCM_RECOMPUTE_EVENTS = {
    "InventoryImported", "ForecastChanged", "RequirementCreated", "POCreated",
    "PODueDateChanged", "SupplierCommitChanged", "GoodsReceiptPosted", "BOMChanged",
    "PlanningPolicyChanged", "material.readiness.updated", "integration.sync.completed",
    # Versioned platform event names.  The legacy names above are retained so
    # imported data and current integrations do not need a flag-day migration.
    "procurement.po.delivery_rescheduled", "purchase_order.rescheduled", "platform.supply.commitment_changed",
}


@subscribe("*", "scm_impacted_set")
def scm_recompute_consumer(db: Session, event: models.EventOutbox) -> None:
    if event.event_type not in SCM_RECOMPUTE_EVENTS:
        return
    from app.scm import models as scm_models
    from app.scm import service as scm_service
    existing = db.query(scm_models.SCMPlanningRun).filter_by(
        tenant_id=event.tenant_id, plant_id=event.plant_id, trigger_key=event.event_id,
    ).first()
    if existing:
        return
    if event.event_type == "purchase_order.rescheduled":
        from datetime import date
        from app.platform.models import ExternalEntityReference
        from app.scm import models as scm_models
        canonical_material_id = event.payload.get("material_id")
        mapping = db.query(ExternalEntityReference).filter_by(
            tenant_id=event.tenant_id, source_system="legacy:scm", entity_type="material",
            canonical_entity_id=canonical_material_id).first()
        supply = db.query(scm_models.SCMSupplyOrder).filter_by(
            tenant_id=event.tenant_id, plant_id=event.plant_id,
            source_entity_type="purchase_order", source_entity_id=event.payload.get("purchase_order_id")).first()
        if mapping and supply:
            schedule = db.query(scm_models.SCMSupplyScheduleLine).filter_by(supply_order_id=supply.id).first()
            if schedule:
                schedule.current_due_date = date.fromisoformat(event.payload["confirmed_delivery_date"])
    user = db.query(models.User).filter_by(
        tenant_id=event.tenant_id, plant_id=event.plant_id, role="admin", is_active=True,
    ).first()
    if user:
        run = scm_service.create_run(db, user, trigger_key=event.event_id,
                                     trigger_type="EVENT_DRIVEN", correlation_id=event.correlation_id)
        scm_service.execute_run(db, run.id)


@subscribe("scm.planning.completed", "platform_material_state")
def platform_material_state_consumer(db: Session, event: models.EventOutbox) -> None:
    """Refresh canonical read projections after a planning run, not during it."""
    from app.platform.state import refresh_scm_plant_projections
    refresh_scm_plant_projections(db, event.tenant_id, event.plant_id)
    from app.platform.models import ExternalEntityReference, OperationalCase
    from app.scm.models import SCMMaterial, SCMMaterialRiskSummary
    risks = db.query(SCMMaterialRiskSummary).filter_by(
        tenant_id=event.tenant_id, plant_id=event.plant_id,
        planning_run_id=event.payload.get("planning_run_id"),
    ).filter(SCMMaterialRiskSummary.severity.in_(["CRITICAL", "RED"])).all()
    for risk in risks:
        from app.scm.models import SCMMaterialRisk
        lifecycle_risk = db.query(SCMMaterialRisk).filter_by(
            tenant_id=event.tenant_id, plant_id=event.plant_id,
            latest_planning_run_id=risk.planning_run_id, material_id=risk.material_id).first()
        existing = db.get(OperationalCase, lifecycle_risk.operational_case_id) if lifecycle_risk and lifecycle_risk.operational_case_id else next((row for row in db.query(OperationalCase).filter_by(
            tenant_id=event.tenant_id, source_event_id=event.event_id,
        ).all() if (row.context or {}).get("risk_summary_id") == risk.id), None)
        if existing:
            case = existing
        else:
            material = db.get(SCMMaterial, risk.material_id)
            case = OperationalCase(
                tenant_id=event.tenant_id, plant_id=event.plant_id,
                case_type="material_shortage", severity="critical" if risk.severity == "CRITICAL" else "high",
                title=f"Material risk: {material.material_code if material else risk.material_id}",
                source_event_id=event.event_id, correlation_id=event.correlation_id,
                canonical_entity_type="material",
                context={"risk_summary_id": risk.id, "planning_run_id": risk.planning_run_id,
                         "scm_material_id": risk.material_id, "stockout_date": risk.stockout_date.isoformat() if risk.stockout_date else None},
            )
        from app.platform.models import PlatformPurchaseOrderLine
        mapping = db.query(ExternalEntityReference).filter_by(tenant_id=event.tenant_id,
            source_system="legacy:scm", entity_type="material", external_id=risk.material_id).first()
        case.canonical_entity_id = case.canonical_entity_id or (mapping.canonical_entity_id if mapping else None)
        case.context = {**case.context, "risk_summary_id": risk.id, "planning_run_id": risk.planning_run_id,
                        "scm_material_id": risk.material_id,
                        "stockout_date": risk.stockout_date.isoformat() if risk.stockout_date else None}
        db.add(case)
        db.flush()
        from app.scm.service import ensure_shortage_intervention
        recommendation = ensure_shortage_intervention(db, risk)
        po_line = db.query(PlatformPurchaseOrderLine).filter_by(
            tenant_id=event.tenant_id, material_id=case.canonical_entity_id).first() if case.canonical_entity_id else None
        if recommendation and po_line:
            from app.platform import actions
            intent = actions.propose(db, tenant_id=event.tenant_id, plant_id=event.plant_id,
                membership_id=None, action_type="RESCHEDULE_PURCHASE_ORDER",
                target_type="purchase_order", target_id=po_line.purchase_order_id,
                payload={"target_delivery_date": recommendation.proposed_date.isoformat() if recommendation.proposed_date else None,
                         "recommendation_id": recommendation.id}, rationale=recommendation.reason,
                idempotency_key=f"scm-recommendation:{recommendation.id}", correlation_id=event.correlation_id,
                originating_case_id=case.id, reason_code="material_shortage_predicted",
                evidence=recommendation.evidence, expected_impact={"risk_summary_id": risk.id,
                "shortage_qty": str(risk.shortage_qty)}, confidence=0.9, risk_level="high")
            case.context = {**case.context, "purchase_order_id": po_line.purchase_order_id,
                            "recommendation_id": recommendation.id, "action_intent_id": intent.id}
    from app.platform.models import MaterialStateProjection, PlatformStateSnapshot
    for projection in db.query(MaterialStateProjection).filter_by(
            tenant_id=event.tenant_id, plant_id=event.plant_id).all():
        db.add(PlatformStateSnapshot(tenant_id=event.tenant_id, plant_id=event.plant_id,
            entity_type="material", entity_id=projection.material_id, snapshot_type="planning",
            observed=projection.observed, derived=projection.derived, predicted=projection.predicted,
            planned=projection.planned, provenance=[], freshness=projection.source_freshness,
            captured_at=projection.calculated_at, projection_version=projection.algorithm_version,
            correlation_id=event.correlation_id))
    # Verification is based on post-action shared state, never connector success.
    from app.platform.models import ActionIntent, OperationalCase
    for intent in db.query(ActionIntent).filter_by(tenant_id=event.tenant_id,
            correlation_id=event.correlation_id, status="executed_pending_verification").all():
        case = db.get(OperationalCase, intent.originating_case_id) if intent.originating_case_id else None
        if not case or not case.canonical_entity_id:
            continue
        mapping = db.query(ExternalEntityReference).filter_by(tenant_id=event.tenant_id,
            source_system="legacy:scm", entity_type="material",
            canonical_entity_id=case.canonical_entity_id).first()
        latest_risk = db.query(SCMMaterialRiskSummary).filter_by(tenant_id=event.tenant_id,
            plant_id=event.plant_id, material_id=mapping.external_id).order_by(
            SCMMaterialRiskSummary.created_at.desc()).first() if mapping else None
        from app.platform import actions
        recovered = bool(latest_risk and latest_risk.severity in {"GREEN", "UNKNOWN"})
        actions.verify_outcome(db, intent, recovered=recovered,
            evidence=[{"type": "post_action_scm_planning", "planning_run_id": latest_risk.planning_run_id if latest_risk else None,
                       "severity": latest_risk.severity if latest_risk else "MISSING"}],
            metrics={"shortage_qty": str(latest_risk.shortage_qty) if latest_risk else None}, case=case)


@subscribe("inventory.position.updated", "platform_inventory_state")
def platform_inventory_state_consumer(db: Session, event: models.EventOutbox) -> None:
    from app.platform.models import PlatformInventoryLocation, PlatformInventoryPosition
    from app.scm.models import SCMInventorySnapshot
    snapshot = db.get(SCMInventorySnapshot, event.payload.get("inventory_snapshot_id"))
    if snapshot is None:
        return
    code = snapshot.storage_location_id or "DEFAULT"
    location = db.query(PlatformInventoryLocation).filter_by(
        tenant_id=event.tenant_id, plant_id=event.plant_id, code=code).first()
    if location is None:
        location = PlatformInventoryLocation(tenant_id=event.tenant_id, plant_id=event.plant_id,
                                             code=code, name="Default inventory" if code == "DEFAULT" else code)
        db.add(location); db.flush()
    position = db.query(PlatformInventoryPosition).filter_by(
        material_id=event.payload["material_id"], location_id=location.id).first()
    if position is None:
        position = PlatformInventoryPosition(tenant_id=event.tenant_id, plant_id=event.plant_id,
                                             material_id=event.payload["material_id"], location_id=location.id,
                                             as_of_at=snapshot.snapshot_at, source_authority=snapshot.source_system)
        db.add(position)
    # Ignore late observations so replay cannot roll current state backwards.
    if position.as_of_at and snapshot.snapshot_at < position.as_of_at:
        return
    position.on_hand_qty = float(snapshot.on_hand_qty)
    position.available_qty = float(snapshot.available_qty or 0)
    position.reserved_qty = float(snapshot.reserved_qty or 0)
    position.blocked_qty = float(snapshot.blocked_qty or 0) + float(snapshot.quality_hold_qty or 0)
    position.as_of_at = snapshot.snapshot_at
    position.source_authority = snapshot.source_system
    position.freshness_status = "fresh"


def dispatch_one(db: Session, event_id: str) -> str:
    event = db.query(models.EventOutbox).filter_by(event_id=event_id).with_for_update().first()
    if event is None:
        raise LookupError("Outbox event not found")
    if event.status == "completed":
        return "completed"
    active_consumer = "dispatcher"
    try:
        consumers = [*CONSUMERS.get(event.event_type, []), *CONSUMERS.get("*", [])]
        for consumer_name, consumer in consumers:
            active_consumer = consumer_name
            receipt = db.query(models.EventConsumerReceipt).filter_by(
                event_id=event.event_id, consumer_name=consumer_name,
            ).first()
            if receipt and receipt.status == "completed":
                continue
            if receipt is None:
                receipt = models.EventConsumerReceipt(
                    tenant_id=event.tenant_id, plant_id=event.plant_id,
                    event_id=event.event_id, consumer_name=consumer_name,
                )
                db.add(receipt)
            else:
                receipt.attempt_count += 1
            consumer(db, event)
            receipt.status = "completed"
            receipt.completed_at = datetime.now(timezone.utc)
            receipt.error = None
        event.status = "completed"
        event.processed_at = datetime.now(timezone.utc)
        event.last_error = None
        event.next_attempt_at = None
        db.commit()
        return event.status
    except Exception as exc:
        db.rollback()
        event = db.query(models.EventOutbox).filter_by(event_id=event_id).with_for_update().one()
        event.attempts += 1
        event.last_error = str(exc)[:2000]
        event.status = "dead_letter" if event.attempts >= MAX_ATTEMPTS else "retry"
        event.next_attempt_at = None if event.status == "dead_letter" else datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** event.attempts))
        event.dead_lettered_at = datetime.now(timezone.utc) if event.status == "dead_letter" else None
        receipt = db.query(models.EventConsumerReceipt).filter_by(
            event_id=event.event_id, consumer_name=active_consumer).first()
        if receipt is None:
            receipt = models.EventConsumerReceipt(tenant_id=event.tenant_id, plant_id=event.plant_id,
                event_id=event.event_id, consumer_name=active_consumer, status="failed")
            db.add(receipt)
        else:
            receipt.attempt_count += 1
        receipt.status = "failed"
        receipt.error = str(exc)[:2000]
        db.commit()
        raise


def pending_event_ids(db: Session, limit: int = 100) -> list[str]:
    now = datetime.now(timezone.utc)
    return [row.event_id for row in db.query(models.EventOutbox).filter(
        models.EventOutbox.status.in_(["pending", "retry"]),
        (models.EventOutbox.next_attempt_at.is_(None) | (models.EventOutbox.next_attempt_at <= now)),
    ).order_by(models.EventOutbox.created_at.asc()).limit(limit).all()]


def replay(db: Session, event_id: str) -> models.EventOutbox:
    event = db.query(models.EventOutbox).filter_by(event_id=event_id).with_for_update().first()
    if event is None:
        raise LookupError("Outbox event not found")
    event.status = "pending"
    event.attempts = 0
    event.last_error = None
    event.processed_at = None
    event.next_attempt_at = None
    event.dead_lettered_at = None
    db.commit()
    return event
