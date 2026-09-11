"""Scoped business-record resolution for assistant tools."""

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import models
from app.domains import workflows


RECORD_MODELS = {
    'purchase_requirement': models.PurchaseRequirement,
    'rfq': models.RFQ,
    'supplier_quote': models.SupplierQuote,
    'bid_comparison': models.BidComparison,
    'negotiation_round': models.NegotiationRound,
    'award_decision': models.AwardDecision,
    'po_draft': models.PODraft,
    'supplier_acknowledgement': models.SupplierAcknowledgement,
    'asn': models.ASN,
    'gate_entry': models.GateEntry,
    'store_receipt': models.StoreReceipt,
    'inspection_result': models.InspectionResult,
    'case': models.Case,
    'supplier_certificate': models.SupplierCertificate,
    'supplier_invoice': models.SupplierInvoice,
}


def resolve_record(
    db: Session, user: models.User, entity_type: str, reference: str,
) -> object:
    model = RECORD_MODELS.get(entity_type)
    if model is None:
        raise HTTPException(status_code=422, detail='Unsupported record type')
    value = reference.strip()
    query = workflows.user_scope_query(db, model, user)
    record = query.filter(
        (model.id == value) | (func.lower(model.business_number) == value.casefold())
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail='Record not found in this workspace')
    return record


def resolve_material(db: Session, user: models.User, reference: str) -> models.Item:
    value = ' '.join(reference.casefold().split())
    # Canonical Item rows are created only after material-master approval; draft
    # requests remain in MaterialMasterRequest and never enter this table.
    scoped = workflows.user_scope_query(db, models.Item, user)
    exact = scoped.filter(
        (func.lower(models.Item.code) == value) | (func.lower(models.Item.name) == value)
    ).first()
    if exact:
        return exact
    candidates = [row for row in scoped.all() if value in row.name.casefold() or value in row.code.casefold()]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise HTTPException(status_code=404, detail='No approved material matched in this workspace')
    raise HTTPException(status_code=409, detail='More than one approved material matched')


def resolve_supplier(db: Session, user: models.User, reference: str) -> models.Supplier:
    value = ' '.join(reference.casefold().split())
    scoped = workflows.user_scope_query(db, models.Supplier, user)
    exact = scoped.filter(
        (models.Supplier.id == reference.strip())
        | (func.lower(models.Supplier.name) == value)
        | (func.lower(models.Supplier.erp_vendor_id) == value)
    ).first()
    if exact:
        return exact
    candidates = [row for row in scoped.all() if value and value in row.name.casefold()]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise HTTPException(status_code=404, detail='No supplier matched in this workspace')
    raise HTTPException(status_code=409, detail='More than one supplier matched')


def resolve_assignee(
    db: Session, user: models.User, *, role: str, reference: str | None = None,
) -> models.WorkspaceMembership:
    query = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, default_plant_id=user.plant_id, role=role, status='active',
    )
    rows = query.all()
    if reference:
        value = reference.casefold().strip()
        rows = [row for row in rows if (member := db.get(models.User, row.user_id)) and (
            member.name.casefold() == value or member.email.casefold() == value
        )]
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise HTTPException(status_code=404, detail=f'No active {role.replace("_", " ")} is available')
    raise HTTPException(status_code=409, detail=f'Choose one active {role.replace("_", " ")}')


def resolve_requirement_reference(
    db: Session,
    user: models.User,
    reference: str | None,
    *,
    thread_state: dict | None = None,
) -> models.PurchaseRequirement:
    """Resolve an exact id/number or the latest eligible scoped requirement."""
    value = (reference or "").strip()
    query = workflows.user_scope_query(db, models.PurchaseRequirement, user)

    if value and "latest" not in value.casefold():
        exact = query.filter(
            (models.PurchaseRequirement.id == value)
            | (func.lower(models.PurchaseRequirement.business_number) == value.casefold())
        ).first()
        if exact:
            return exact
        raise HTTPException(status_code=404, detail="Requirement not found in this workspace")

    state = thread_state or {}
    for recent in state.get("recent_entities") or []:
        recent_type = recent.get("entity_type") or recent.get("type")
        recent_id = recent.get("entity_id") or recent.get("id")
        if recent_type not in {"purchase_requirement", "purchase_requirements"} or not recent_id:
            continue
        candidate = query.filter_by(id=str(recent_id)).first()
        if candidate and candidate.status in {"approved", "rfq_drafted"}:
            return candidate

    selected = state.get("current_work_item") or state.get("selected_context") or {}
    selected_type = selected.get("entity_type") or selected.get("type")
    selected_id = selected.get("entity_id") or selected.get("id")
    if selected_type in {"purchase_requirement", "purchase_requirements"} and selected_id:
        candidate = query.filter_by(id=str(selected_id)).first()
        if candidate:
            return candidate

    candidate = query.filter(
        models.PurchaseRequirement.status.in_(["approved", "rfq_drafted"])
    ).order_by(models.PurchaseRequirement.created_at.desc()).first()
    if candidate:
        return candidate
    raise HTTPException(status_code=404, detail="No eligible requirement is available in this workspace")
