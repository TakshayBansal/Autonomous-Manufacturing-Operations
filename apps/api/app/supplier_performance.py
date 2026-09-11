from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import ADMIN, PURCHASE_MANAGER, require_role
from app.db import models
from app.domains import workflows


def record_quality_event(db: Session, user: models.User, inspection: models.InspectionResult, supplier_id: str) -> models.SupplierPerformanceEvent:
    if inspection.inspected_quantity <= 0:
        raise HTTPException(status_code=422, detail="A performance event requires a positive inspected quantity")
    existing = workflows.user_scope_query(db, models.SupplierPerformanceEvent, user).filter_by(
        source_entity_type="inspection_result", source_entity_id=inspection.id, metric_type="quality_acceptance",
    ).first()
    if existing:
        return existing
    score = round((inspection.accepted_quantity / inspection.inspected_quantity) * 100, 2) if inspection.inspected_quantity else 0
    event = models.SupplierPerformanceEvent(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        business_number=workflows.next_business_number(db, "SPE", user), supplier_id=supplier_id,
        po_draft_id=inspection.po_draft_id, source_entity_type="inspection_result", source_entity_id=inspection.id,
        metric_type="quality_acceptance", numerator=inspection.accepted_quantity,
        denominator=inspection.inspected_quantity, score=score, occurred_at=workflows.utcnow(),
        evidence={"accepted": inspection.accepted_quantity, "rejected": inspection.rejected_quantity, "held": inspection.held_quantity},
    )
    db.add(event)
    return event


def summary(db: Session, user: models.User, supplier_id: str) -> dict:
    supplier = workflows.get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
    events = workflows.user_scope_query(db, models.SupplierPerformanceEvent, user).filter_by(supplier_id=supplier.id).all()
    by_metric: dict[str, list[float]] = {}
    for event in events:
        by_metric.setdefault(event.metric_type, []).append(event.score)
    open_actions = workflows.user_scope_query(db, models.SupplierCorrectiveAction, user).filter(
        models.SupplierCorrectiveAction.supplier_id == supplier.id,
        models.SupplierCorrectiveAction.status.notin_(["closed", "cancelled"]),
    ).count()
    return {
        "supplier_id": supplier.id, "supplier_name": supplier.name, "event_count": len(events),
        "metrics": {key: round(sum(values) / len(values), 2) for key, values in by_metric.items()},
        "open_corrective_actions": open_actions,
        "evidence_backed": True,
    }


def open_corrective_action(db: Session, user: models.User, supplier_id: str, source_entity_type: str, source_entity_id: str, problem_statement: str, response_due_days: int) -> models.SupplierCorrectiveAction:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    supplier = workflows.get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
    source_models = {"inspection_result": models.InspectionResult, "supplier_return": models.SupplierReturn, "case": models.Case}
    source_model = source_models.get(source_entity_type)
    if source_model is None:
        raise HTTPException(status_code=422, detail="Corrective actions must be linked to an inspection, supplier return, or case")
    source = workflows.get_scoped_or_404(db, source_model, user, source_entity_id, "Corrective-action source")
    source_supplier_id = getattr(source, "supplier_id", None)
    if source_supplier_id is None and getattr(source, "po_draft_id", None):
        source_supplier_id = workflows.get_scoped_or_404(db, models.PODraft, user, source.po_draft_id, "Purchase order").supplier_id
    if source_supplier_id and source_supplier_id != supplier.id:
        raise HTTPException(status_code=409, detail="The evidence source belongs to a different supplier")
    if response_due_days < 1 or response_due_days > 90:
        raise HTTPException(status_code=422, detail="Supplier response due date must be between 1 and 90 days")
    duplicate = workflows.user_scope_query(db, models.SupplierCorrectiveAction, user).filter(
        models.SupplierCorrectiveAction.supplier_id == supplier.id,
        models.SupplierCorrectiveAction.source_entity_type == source_entity_type,
        models.SupplierCorrectiveAction.source_entity_id == source_entity_id,
        models.SupplierCorrectiveAction.status.notin_(["closed", "cancelled"]),
    ).first()
    if duplicate:
        return duplicate
    action = models.SupplierCorrectiveAction(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        business_number=workflows.next_business_number(db, "CAPA", user), supplier_id=supplier.id,
        source_entity_type=source_entity_type, source_entity_id=source_entity_id,
        status="open", problem_statement=problem_statement.strip(),
        requested_response_by=workflows.utcnow() + timedelta(days=response_due_days),
    )
    db.add(action); db.flush()
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, default_plant_id=user.plant_id, role=PURCHASE_MANAGER, status="active"
    ).first()
    db.add(models.Task(
        tenant_id=user.tenant_id, plant_id=user.plant_id, title=f"Manage corrective action {action.business_number} with {supplier.name}",
        owner_role=PURCHASE_MANAGER, owner_user_id=membership.user_id if membership else None,
        owner_membership_id=membership.id if membership else None, status="open", severity="action",
        entity_type="supplier_corrective_action", entity_id=action.id, due_at=action.requested_response_by,
        semantic_key=f"supplier-capa:{action.id}", requested_outcome="Obtain and verify supplier root cause and corrective action.",
    ))
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "supplier_corrective_action.opened", "supplier_corrective_action", action.id, actor_user_id=user.id)
    return action


def update_corrective_action(db: Session, user: models.User, action_id: str, status: str, root_cause: str, corrective_action: str, preventive_action: str, evidence: list[dict]) -> models.SupplierCorrectiveAction:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    action = workflows.get_scoped_or_404(db, models.SupplierCorrectiveAction, user, action_id, "Corrective action")
    allowed = {"awaiting_supplier", "response_received", "effectiveness_review", "closed", "cancelled"}
    if status not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported corrective-action state")
    if status == "closed" and (not corrective_action.strip() or not evidence):
        raise HTTPException(status_code=409, detail="Closing a corrective action requires the action taken and effectiveness evidence")
    action.status = status; action.root_cause = root_cause.strip(); action.corrective_action = corrective_action.strip()
    action.preventive_action = preventive_action.strip(); action.effectiveness_evidence = evidence
    if status == "closed":
        action.closed_at = workflows.utcnow(); action.closed_by_user_id = user.id
        workflows.complete_tasks_for_entity(db, user, "supplier_corrective_action", action.id)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, f"supplier_corrective_action.{status}", "supplier_corrective_action", action.id, actor_user_id=user.id)
    return action
