"""Governed, append-only manual SCM observations and automatic replanning."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import models as core
from app.domains import workflows
from app.platform.events import DomainEvent, publish
from app.platform.models import DataProvenance, DataQualityIssue
from app.scm import models, service
from app.scm.planning import canonical_material_id


ENTRY_TYPES = {
    "EXPECTED_DELIVERY_CREATED", "SUPPLY_SCHEDULE_CHANGED", "SUPPLY_QUANTITY_CHANGED",
    "GOODS_RECEIPT_RECORDED", "INVENTORY_CORRECTION_RECORDED", "DEMAND_CREATED", "DEMAND_CHANGED",
}


def _decimal(values: dict[str, Any], key: str, *, required: bool = True,
             allow_zero: bool = False) -> Decimal | None:
    value = values.get(key)
    if value in (None, "") and not required:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise HTTPException(422, f"{key} must be numeric")
    if parsed < 0 or (parsed == 0 and not allow_zero):
        raise HTTPException(422, f"{key} must be {'non-negative' if allow_zero else 'positive'}")
    return parsed


def _date(values: dict[str, Any], key: str) -> date:
    try:
        return date.fromisoformat(str(values.get(key) or ""))
    except ValueError:
        raise HTTPException(422, f"{key} must use YYYY-MM-DD")


def validate(db: Session, user: core.User, entry_type: str, material_id: str,
             target_entity_type: str | None, target_entity_id: str | None,
             supplier_id: str | None, values: dict[str, Any]) -> models.SCMMaterial:
    if entry_type not in ENTRY_TYPES:
        raise HTTPException(422, "Unsupported manual SCM entry type")
    material = db.query(models.SCMMaterial).join(models.SCMMaterialPlant).filter(
        models.SCMMaterial.id == material_id, models.SCMMaterial.tenant_id == user.tenant_id,
        models.SCMMaterialPlant.plant_id == user.plant_id, models.SCMMaterialPlant.active.is_(True)).first()
    if not material:
        raise HTTPException(404, "Material not found in selected plant")
    uom = str(values.get("uom") or material.base_uom_id).upper()
    if uom != material.base_uom_id:
        raise HTTPException(422, f"Manual entry UOM must be {material.base_uom_id}")
    if supplier_id and not db.query(core.Supplier.id).filter_by(
            id=supplier_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first():
        raise HTTPException(404, "Supplier not found in selected plant")
    if entry_type in {"EXPECTED_DELIVERY_CREATED", "GOODS_RECEIPT_RECORDED", "DEMAND_CREATED"}:
        _decimal(values, "quantity")
        key = "receipt_date" if entry_type == "GOODS_RECEIPT_RECORDED" else "required_date" if entry_type == "DEMAND_CREATED" else "delivery_date"
        parsed_date = _date(values, key)
        if entry_type == "GOODS_RECEIPT_RECORDED" and parsed_date > datetime.now(timezone.utc).date():
            raise HTTPException(422, "Actual goods receipt date cannot be in the future")
    if entry_type == "INVENTORY_CORRECTION_RECORDED":
        available = _decimal(values, "available_qty", allow_zero=True)
        on_hand = _decimal(values, "on_hand_qty", required=False, allow_zero=True)
        if on_hand is not None and available is not None and available > on_hand:
            raise HTTPException(422, "available_qty cannot exceed on_hand_qty")
    if entry_type in {"SUPPLY_SCHEDULE_CHANGED", "SUPPLY_QUANTITY_CHANGED"}:
        if target_entity_type != "scm_supply_schedule_line" or not target_entity_id:
            raise HTTPException(422, "A supply schedule line target is required")
        schedule = db.query(models.SCMSupplyScheduleLine).filter_by(
            id=target_entity_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
        if not schedule:
            raise HTTPException(404, "Supply schedule line not found")
        if entry_type == "SUPPLY_SCHEDULE_CHANGED":
            _date(values, "delivery_date")
        if "quantity" in values:
            _decimal(values, "quantity")
    if entry_type == "DEMAND_CHANGED":
        if target_entity_type not in {"scm_material_requirement", "scm_demand_bucket"} or not target_entity_id:
            raise HTTPException(422, "A demand target is required")
        _decimal(values, "quantity")
        if values.get("required_date"):
            _date(values, "required_date")
    return material


def previous_values(db: Session, entry_type: str, target_id: str | None) -> dict[str, Any]:
    if not target_id:
        return {}
    if entry_type in {"SUPPLY_SCHEDULE_CHANGED", "SUPPLY_QUANTITY_CHANGED"}:
        row = db.get(models.SCMSupplyScheduleLine, target_id)
        return {"delivery_date": row.current_due_date.isoformat(), "quantity": str(row.scheduled_qty)} if row else {}
    if entry_type == "DEMAND_CHANGED":
        row = db.get(models.SCMMaterialRequirement, target_id)
        return {"required_date": row.required_date.isoformat(), "quantity": str(row.quantity)} if row else {}
    return {}


def create(db: Session, user: core.User, *, entry_type: str, material_id: str,
           target_entity_type: str | None, target_entity_id: str | None,
           supplier_id: str | None, values: dict[str, Any], reason: str,
           effective_at: datetime | None, expires_at: datetime | None,
           evidence: list[dict[str, Any]], idempotency_key: str) -> tuple[models.SCMManualDataEntry, models.SCMPlanningRun, bool]:
    existing = db.query(models.SCMManualDataEntry).filter_by(
        tenant_id=user.tenant_id, idempotency_key=idempotency_key).first()
    if existing:
        return existing, db.get(models.SCMPlanningRun, existing.planning_run_id), True
    material = validate(db, user, entry_type, material_id, target_entity_type, target_entity_id, supplier_id, values)
    now = datetime.now(timezone.utc)
    correlation_id = f"SCM-MANUAL-{uuid4()}"
    membership = db.query(core.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    prior = None
    if target_entity_id:
        prior = db.query(models.SCMManualDataEntry).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, target_entity_id=target_entity_id,
            entry_type=entry_type, status="ACTIVE").order_by(models.SCMManualDataEntry.created_at.desc()).first()
        if prior:
            prior.status, prior.superseded_at = "SUPERSEDED", now
    entry = models.SCMManualDataEntry(
        tenant_id=user.tenant_id, plant_id=user.plant_id, entry_type=entry_type,
        material_id=material.id, canonical_material_id=canonical_material_id(db, user.tenant_id, material.id),
        target_entity_type=target_entity_type, target_entity_id=target_entity_id, supplier_id=supplier_id,
        values={**values, "uom": str(values.get("uom") or material.base_uom_id).upper()},
        previous_values=previous_values(db, entry_type, target_entity_id), reason=reason,
        evidence=evidence, effective_at=effective_at or now, expires_at=expires_at,
        status="ACTIVE", created_by_user_id=user.id,
        created_by_membership_id=membership.id if membership else None,
        correlation_id=correlation_id, idempotency_key=idempotency_key,
        supersedes_entry_id=prior.id if prior else None,
    )
    db.add(entry)
    db.flush()
    db.add(DataProvenance(
        tenant_id=user.tenant_id, plant_id=user.plant_id, entity_type="scm_manual_data_entry",
        entity_id=entry.id, source_system="genuinegigs_manual", source_reference=entry.id,
        observed_at=entry.effective_at, mapping_version="scm-manual@1", transformation=entry_type,
        authoritative=True, details={"material_id": material.id, "values": entry.values, "reason": reason},
        correlation_id=correlation_id,
    ))
    publish(db, DomainEvent(
        "scm.manual_data.recorded", user.tenant_id, user.plant_id, "scm_manual_data_entry", entry.id,
        {"entry_id": entry.id, "entry_type": entry.entry_type, "material_id": material.id,
         "canonical_material_id": entry.canonical_material_id, "values": entry.values},
        actor_membership_id=membership.id if membership else None, correlation_id=correlation_id,
        source_system="genuinegigs_manual", occurred_at=entry.effective_at,
    ))
    run = service.create_run(db, user, trigger_key=entry.id, trigger_type="MANUAL_CHANGE", correlation_id=correlation_id)
    entry.planning_run_id = run.id
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email,
        "scm.manual_data.recorded", "scm_manual_data_entry", entry.id, actor_user_id=user.id,
        meta={"entry_type": entry_type, "material_id": material.id, "planning_run_id": run.id})
    return entry, run, False


def serialize(row: models.SCMManualDataEntry, db: Session) -> dict[str, Any]:
    material = db.get(models.SCMMaterial, row.material_id)
    run = db.get(models.SCMPlanningRun, row.planning_run_id) if row.planning_run_id else None
    return {"id": row.id, "entry_type": row.entry_type, "material": {
        "id": row.material_id, "code": material.material_code if material else row.material_id,
        "description": material.description if material else ""}, "target_entity_type": row.target_entity_type,
        "target_entity_id": row.target_entity_id, "supplier_id": row.supplier_id,
        "values": row.values, "previous_values": row.previous_values, "reason": row.reason,
        "evidence": row.evidence, "source_authority": row.source_authority,
        "effective_at": row.effective_at, "expires_at": row.expires_at, "status": row.status,
        "correlation_id": row.correlation_id, "planning_run_id": row.planning_run_id,
        "planning_status": run.status if run else None, "created_at": row.created_at}


def create_import_conflicts(db: Session, batch: core.IntegrationImportBatch) -> int:
    """Preserve manual precedence and surface overlapping imported observations."""
    applied = db.query(core.IntegrationImportRowResult).filter_by(batch_id=batch.id, action="applied").all()
    created = 0
    for result in applied:
        entity = None
        if result.canonical_entity_type and result.canonical_entity_id:
            model = {"scm_inventory_snapshot": models.SCMInventorySnapshot,
                     "scm_supply_order": models.SCMSupplyOrder,
                     "scm_supply_schedule": models.SCMSupplyScheduleLine,
                     "scm_material_requirement": models.SCMMaterialRequirement}.get(result.canonical_entity_type)
            entity = db.get(model, result.canonical_entity_id) if model else None
        material_id = getattr(entity, "material_id", None)
        if not material_id and isinstance(entity, models.SCMSupplyScheduleLine):
            order = db.get(models.SCMSupplyOrder, entity.supply_order_id)
            material_id = order.material_id if order else None
        if not material_id:
            continue
        for entry in db.query(models.SCMManualDataEntry).filter_by(
                tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=material_id, status="ACTIVE").all():
            duplicate = db.query(DataQualityIssue).filter_by(
                tenant_id=batch.tenant_id, plant_id=batch.plant_id, rule_key="scm_manual_source_conflict",
                entity_id=entry.id, status="open").first()
            if duplicate:
                continue
            db.add(DataQualityIssue(tenant_id=batch.tenant_id, plant_id=batch.plant_id,
                entity_type="scm_manual_data_entry", entity_id=entry.id,
                rule_key="scm_manual_source_conflict", severity="warning", status="open",
                message="Imported data overlaps an active manual planning value",
                details={"entry_id": entry.id, "batch_id": batch.id, "import_row_id": result.id,
                         "manual_values": entry.values, "imported_values": result.source_cells}))
            created += 1
    return created
