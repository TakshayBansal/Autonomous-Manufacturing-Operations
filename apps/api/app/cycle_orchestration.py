"""Durable, deterministic procurement-cycle evaluation.

The evaluator derives facts from canonical business records. It never mutates
issued business records; repeated runs only reconcile orchestration state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models
from app.domains import workflows


STAGES = (
    "requirement", "specification", "rfq", "supplier_response", "quotation_review",
    "comparison", "approval", "negotiation", "po", "fulfilment", "receipt",
    "quality", "invoice", "closure",
)
PRESENTATION = {
    "requirement": "Requirement", "specification": "Requirement", "rfq": "RFQ",
    "supplier_response": "Quotations", "quotation_review": "Quotations",
    "comparison": "Comparison", "approval": "Approval", "negotiation": "Approval",
    "po": "PO", "fulfilment": "PO", "receipt": "Receipt", "quality": "Receipt",
    "invoice": "Invoice", "closure": "Invoice",
}
_EVALUATION_LOCK = RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_objective(db: Session, requirement: models.PurchaseRequirement) -> models.ProcurementCycleObjective:
    objective = db.query(models.ProcurementCycleObjective).filter_by(
        tenant_id=requirement.tenant_id, requirement_id=requirement.id, requirement_line_id=None,
    ).first()
    if objective is None:
        objective = models.ProcurementCycleObjective(
            tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
            requirement_id=requirement.id, owner_membership_id=requirement.owner_membership_id,
            need_by_date=requirement.need_by_date, business_number=requirement.business_number,
        )
        try:
            # Multiple live panels can project the same procurement cycle at
            # once. Keep the get-or-create race inside a savepoint so the
            # request transaction remains usable when another request wins.
            with db.begin_nested():
                db.add(objective)
                db.flush()
        except IntegrityError:
            objective = db.query(models.ProcurementCycleObjective).filter_by(
                tenant_id=requirement.tenant_id,
                requirement_id=requirement.id,
                requirement_line_id=None,
            ).first()
            if objective is None:
                raise
    return objective


def _evaluate(db: Session, requirement: models.PurchaseRequirement, actor_membership_id: str | None = None,
              correlation_id: str | None = None) -> models.ProcurementCycleObjective:
    objective = ensure_objective(db, requirement)
    user = db.query(models.User).filter_by(tenant_id=requirement.tenant_id, id=requirement.owner_user_id).first()
    def scope(model):
        return workflows.user_scope_query(db, model, user) if user else db.query(model).filter_by(tenant_id=requirement.tenant_id)
    rfq = scope(models.RFQ).filter(models.RFQ.requirement_id == requirement.id).order_by(models.RFQ.created_at.desc()).first()
    quotes = scope(models.SupplierQuote).filter(models.SupplierQuote.rfq_id == rfq.id, models.SupplierQuote.verification_status != "superseded").all() if rfq else []
    comparison = scope(models.BidComparison).filter(models.BidComparison.rfq_id == rfq.id).order_by(models.BidComparison.created_at.desc()).first() if rfq else None
    award = scope(models.AwardDecision).filter(models.AwardDecision.rfq_id == rfq.id).order_by(models.AwardDecision.created_at.desc()).first() if rfq else None
    negotiation = scope(models.NegotiationRound).filter(models.NegotiationRound.rfq_id == rfq.id).order_by(models.NegotiationRound.created_at.desc()).first() if rfq else None
    po = scope(models.PODraft).filter(models.PODraft.award_id == award.id).order_by(models.PODraft.created_at.desc()).first() if award else None
    asn = scope(models.ASN).filter(models.ASN.po_draft_id == po.id).first() if po else None
    receipt = scope(models.StoreReceipt).filter(models.StoreReceipt.po_draft_id == po.id).first() if po else None
    inspection = scope(models.InspectionResult).filter(models.InspectionResult.po_draft_id == po.id).first() if po else None
    invoice = scope(models.SupplierInvoice).filter(models.SupplierInvoice.po_draft_id == po.id).first() if po else None
    specification = db.query(models.ItemSpecification).filter_by(item_id=requirement.item_id, tenant_id=requirement.tenant_id).first()
    complete = {
        "requirement": requirement.status in {"approved", "rfq_drafted", "closed"},
        "specification": bool(specification or requirement.reason.strip()),
        "rfq": bool(rfq and rfq.status in {"published", "responses_open", "closed"}),
        "supplier_response": bool(quotes),
        "quotation_review": bool(quotes and all(row.verification_status == "verified" for row in quotes)),
        "comparison": bool(comparison and comparison.status in {"submitted", "approved"}),
        "approval": bool(comparison and comparison.status == "approved" and award),
        "negotiation": bool(not negotiation or negotiation.status in {"approved", "accepted", "closed"}) if award else False,
        "po": bool(po and po.status in {"approved_pending_outbox", "posted", "simulated_posted"}),
        "fulfilment": bool(asn), "receipt": bool(receipt), "quality": bool(inspection),
        "invoice": bool(invoice), "closure": requirement.status == "closed",
    }
    owners = {
        "requirement": "purchase_executive", "specification": "purchase_executive", "rfq": "purchase_executive",
        "supplier_response": "purchase_executive", "quotation_review": "purchase_manager",
        "comparison": "purchase_manager", "approval": "plant_manager", "negotiation": "purchase_manager",
        "po": "purchase_manager", "fulfilment": "purchase_manager", "receipt": "store_manager",
        "quality": "quality_inspector", "invoice": "purchase_manager", "closure": "plant_manager",
    }
    first_incomplete = next((index for index, key in enumerate(STAGES) if not complete[key]), len(STAGES) - 1)
    first_current = None
    now = _now()
    for position, key in enumerate(STAGES):
        status = "done" if complete[key] else "current" if position == first_incomplete else "waiting"
        row = db.query(models.CycleStageState).filter_by(objective_id=objective.id, stage_key=key).first()
        if row is None:
            row = models.CycleStageState(tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
                objective_id=objective.id, stage_key=key)
            db.add(row)
        row.status = status
        row.owner_role = owners[key]
        if status == "done" and row.completed_at is None:
            row.completed_at = now
        if status in {"current", "blocked"} and first_current is None:
            first_current = (position, key, row.owner_role)

    position, current, owner_role = first_current or (len(STAGES) - 1, "closure", None)
    overdue = bool(requirement.need_by_date and requirement.need_by_date < now.date().isoformat())
    missing_owner = not objective.owner_membership_id
    next_health = "at_risk" if overdue else "attention" if missing_owner else "on_track"
    next_status = "completed" if requirement.status == "closed" else "active"
    next_summary = {
        "current_stage": current, "presentation_stage": PRESENTATION[current], "owner_role": owner_role,
        "conditions_to_advance": ["Complete the current stage and attach required evidence"],
        "missing_assignment": missing_owner, "need_by_date": requirement.need_by_date,
        "production_risk": "need_by_date_missed" if overdue else "none",
        "completion_percentage": round(position / (len(STAGES) - 1) * 100),
        "required_coordination": "assignment" if missing_owner else "proposal" if current in {"approval", "po"} else "task",
    }
    changed = (objective.current_stage, objective.health, objective.status, objective.evaluation_summary) != (
        current, next_health, next_status, next_summary,
    )
    objective.current_stage = current
    objective.health = next_health
    objective.status = next_status
    objective.last_evaluated_at = now
    objective.evaluation_summary = next_summary
    if changed:
        objective.aggregate_version += 1
    risk_key = "need-by-date-missed"
    risk = db.query(models.CycleRisk).filter_by(objective_id=objective.id, semantic_key=risk_key).first()
    if overdue and risk is None:
        db.add(models.CycleRisk(tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
            objective_id=objective.id, risk_type="production", severity="critical",
            summary="The requirement need-by date has passed", semantic_key=risk_key,
            evidence=[{"type": "requirement", "id": requirement.id}]))
    elif risk is not None and not overdue:
        risk.status = "resolved"
    dependency = db.query(models.CycleDependency).filter_by(
        objective_id=objective.id, semantic_key="missing-cycle-owner",
    ).first()
    if missing_owner and dependency is None:
        db.add(models.CycleDependency(tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
            objective_id=objective.id, dependency_type="assignment", description="Assign an accountable cycle owner",
            semantic_key="missing-cycle-owner"))
    elif dependency is not None and not missing_owner and dependency.status == "open":
        dependency.status = "resolved"
        dependency.resolved_at = now
    correlation = correlation_id or str(uuid4())
    existing_event = db.query(models.EventOutbox).filter_by(
        aggregate_id=objective.id, aggregate_version=objective.aggregate_version,
        event_type="procurement.cycle.evaluated",
    ).first()
    if changed and existing_event is None:
        db.add(models.EventOutbox(tenant_id=requirement.tenant_id, plant_id=requirement.plant_id,
            event_type="procurement.cycle.evaluated", aggregate_type="procurement_cycle_objective",
            aggregate_id=objective.id, aggregate_version=objective.aggregate_version,
            actor_membership_id=actor_membership_id, correlation_id=correlation,
            payload={"requirement_id": requirement.id, "stage": current, "health": objective.health}))
    db.flush()
    return objective


def evaluate(db: Session, requirement: models.PurchaseRequirement, actor_membership_id: str | None = None,
             correlation_id: str | None = None) -> models.ProcurementCycleObjective:
    # Read models can be requested concurrently by the shell, manager view and
    # live refresh. Serialize this deterministic projection within an API
    # worker so its unique semantic rows are never created twice. Database
    # constraints remain the cross-worker authority.
    with _EVALUATION_LOCK:
        return _evaluate(db, requirement, actor_membership_id, correlation_id)


def serialize(db: Session, objective: models.ProcurementCycleObjective) -> dict:
    stages = db.query(models.CycleStageState).filter_by(objective_id=objective.id).all()
    by_key = {row.stage_key: row for row in stages}
    dependencies = db.query(models.CycleDependency).filter_by(objective_id=objective.id, status="open").all()
    risks = db.query(models.CycleRisk).filter_by(objective_id=objective.id, status="open").all()
    prepared = db.query(models.PreparedWorkItem).filter_by(objective_id=objective.id, status="ready").all()
    return {
        "id": objective.id, "business_number": objective.business_number,
        "requirement_id": objective.requirement_id, "current_stage": objective.current_stage,
        "presentation_stage": PRESENTATION.get(objective.current_stage, objective.current_stage),
        "health": objective.health, "need_by_date": objective.need_by_date,
        "status": objective.status, "version": objective.version,
        "evaluation": objective.evaluation_summary,
        "stages": [{"key": key, "label": PRESENTATION[key], "status": by_key[key].status,
                    "owner_role": by_key[key].owner_role, "evidence": by_key[key].evidence} for key in STAGES if key in by_key],
        "dependencies": [{"id": row.id, "type": row.dependency_type, "description": row.description,
                           "owner_membership_id": row.owner_membership_id} for row in dependencies],
        "risks": [{"id": row.id, "type": row.risk_type, "severity": row.severity,
                    "summary": row.summary, "evidence": row.evidence} for row in risks],
        "prepared_work": [{"id": row.id, "type": row.work_type, "title": row.title,
                            "confidence": row.confidence, "evidence": row.evidence} for row in prepared],
    }
