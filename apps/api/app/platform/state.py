"""Read projection adapters shared by modules, beginning with SCM material risk."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.platform.catalog import material_for_legacy
from app.platform.models import MaterialStateProjection
from app.scm import models as scm


class FactoryStateService:
    """Stable shared state contract over domain-optimized projections."""
    def __init__(self, db: Session, tenant_id: str, plant_id: str):
        self.db, self.tenant_id, self.plant_id = db, tenant_id, plant_id

    def now(self, entity_type: str, entity_id: str) -> dict | None:
        from app.db import models as core
        from app.platform.models import PlatformPurchaseOrder, PlatformProduct
        from app.platform.relationships import get_neighbors
        if entity_type == "material":
            result = material_state(self.db, self.tenant_id, self.plant_id, entity_id)
        elif entity_type == "work_order":
            result = work_order_state(self.db, self.tenant_id, entity_id, plant_id=self.plant_id)
        else:
            model_map = {"supplier": core.Supplier, "site": core.Plant, "product": PlatformProduct,
                         "purchase_order": PlatformPurchaseOrder, "work_center": core.ProductionLine,
                         "equipment": core.PlantAsset}
            model = model_map.get(entity_type)
            row = self.db.query(model).filter_by(id=entity_id, tenant_id=self.tenant_id).first() if model else None
            if row is None:
                return None
            if (entity_type == "site" and row.id != self.plant_id) or (entity_type != "site" and getattr(row, "plant_id", None) != self.plant_id):
                return None
            observed = {column.name: getattr(row, column.name) for column in row.__table__.columns
                        if column.name not in {"tenant_id", "created_at", "updated_at"}}
            result = {"entity": {"type": entity_type, "id": entity_id}, "observed": observed,
                      "derived": {}, "predicted": {}, "planned": {},
                      "freshness": freshness(getattr(row, "updated_at", None)), "provenance": []}
        if result is not None:
            result["relationships"] = get_neighbors(self.db, self.tenant_id, entity_type, entity_id)
            from app.platform.models import OperationalCase
            risks = self.db.query(OperationalCase).filter_by(tenant_id=self.tenant_id,
                plant_id=self.plant_id,
                canonical_entity_type=entity_type, canonical_entity_id=entity_id).filter(
                OperationalCase.status.notin_(["resolved", "closed", "cancelled"])).all()
            result["related_risks"] = [{"id": row.id, "type": row.case_type,
                                         "severity": row.severity, "status": row.status} for row in risks]
            result["computed_at"] = datetime.now(timezone.utc)
        return result

    def at(self, entity_type: str, entity_id: str, at: datetime) -> dict | None:
        from app.platform.models import PlatformStateSnapshot
        row = self.db.query(PlatformStateSnapshot).filter_by(tenant_id=self.tenant_id,
            plant_id=self.plant_id,
            entity_type=entity_type, entity_id=entity_id).filter(
            PlatformStateSnapshot.captured_at <= at).order_by(PlatformStateSnapshot.captured_at.desc()).first()
        return self._snapshot(row) if row else None

    def history(self, entity_type: str, entity_id: str, *, limit: int = 100) -> list[dict]:
        from app.platform.models import PlatformStateSnapshot
        rows = self.db.query(PlatformStateSnapshot).filter_by(tenant_id=self.tenant_id,
            plant_id=self.plant_id,
            entity_type=entity_type, entity_id=entity_id).order_by(
            PlatformStateSnapshot.captured_at.desc()).limit(min(limit, 500)).all()
        return [self._snapshot(row) for row in rows]

    @staticmethod
    def _snapshot(row) -> dict:
        return {"id": row.id, "entity": {"type": row.entity_type, "id": row.entity_id},
                "observed": row.observed, "derived": row.derived, "predicted": row.predicted,
                "planned": row.planned, "freshness": row.freshness, "provenance": row.provenance,
                "computed_at": row.captured_at, "projection_version": row.projection_version,
                "correlation_id": row.correlation_id}


def refresh_scm_material_projection(db: Session, *, tenant_id: str, plant_id: str, scm_material_id: str) -> MaterialStateProjection | None:
    material = db.query(scm.SCMMaterial).filter_by(id=scm_material_id, tenant_id=tenant_id).first()
    if material is None:
        return None
    canonical = material_for_legacy(
        db, tenant_id=tenant_id, plant_id=plant_id, company_id=material.company_id, source_system="legacy:scm",
        legacy_id=material.id, code=material.material_code, name=material.description or material.material_code,
        material_type=material.material_type, base_uom_id=material.base_uom_id,
    )
    risk = db.query(scm.SCMMaterialRiskSummary).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, material_id=material.id,
    ).order_by(scm.SCMMaterialRiskSummary.created_at.desc()).first()
    inventory = db.query(scm.SCMInventorySnapshot).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, material_id=material.id).order_by(
        scm.SCMInventorySnapshot.snapshot_at.desc()).first()
    if inventory:
        from app.platform.models import DataProvenance
        source_reference = inventory.source_record_id
        if not db.query(DataProvenance).filter_by(tenant_id=tenant_id, entity_type="material",
                entity_id=canonical.id, source_system=inventory.source_system,
                source_reference=source_reference).first():
            db.add(DataProvenance(tenant_id=tenant_id, plant_id=plant_id, entity_type="material",
                entity_id=canonical.id, source_system=inventory.source_system,
                source_reference=source_reference, observed_at=inventory.snapshot_at,
                mapping_version="scm-inventory@1", transformation="SCM inventory projection",
                authoritative=True, details={"inventory_snapshot_id": inventory.id}))
    next_supply = db.query(scm.SCMSupplyScheduleLine).join(
        scm.SCMSupplyOrder, scm.SCMSupplyOrder.id == scm.SCMSupplyScheduleLine.supply_order_id).filter(
        scm.SCMSupplyOrder.tenant_id == tenant_id, scm.SCMSupplyOrder.plant_id == plant_id,
        scm.SCMSupplyOrder.material_id == material.id,
        scm.SCMSupplyScheduleLine.status.in_(["OPEN", "PARTIAL", "CONFIRMED"])).order_by(
        scm.SCMSupplyScheduleLine.current_due_date).first()
    projection = db.query(MaterialStateProjection).filter_by(material_id=canonical.id, plant_id=plant_id).first()
    if projection is None:
        projection = MaterialStateProjection(tenant_id=tenant_id, plant_id=plant_id, material_id=canonical.id)
        db.add(projection)
    projection.observed = {"legacy_scm_material_id": material.id,
                           "available_qty": float(inventory.available_qty or 0) if inventory else None,
                           "inventory_observed_at": inventory.snapshot_at.isoformat() if inventory else None,
                           "next_confirmed_supply": next_supply.current_due_date.isoformat() if next_supply else None}
    risk_run = db.get(scm.SCMPlanningRun, risk.planning_run_id) if risk else None
    runway = ((risk.stockout_date - risk_run.horizon_start).days if risk and risk.stockout_date and risk_run else None)
    shortage_gap = ((next_supply.current_due_date - risk.stockout_date).days
                    if next_supply and risk and risk.stockout_date else None)
    projection.derived = {"severity": risk.severity, "priority_score": float(risk.priority_score),
                          "recommended_action_count": risk.recommended_action_count,
                          "runway_days": runway, "shortage_gap_days": shortage_gap,
                          "risk_state": "UNKNOWN" if risk.severity == "UNKNOWN" else "SAFE" if risk.severity == "GREEN" else "AT_RISK"} if risk else {}
    projection.planned = {"first_breach_date": risk.first_breach_date.isoformat() if risk and risk.first_breach_date else None,
                          "stockout_date": risk.stockout_date.isoformat() if risk and risk.stockout_date else None} if risk else {}
    projection.source_freshness = {"source": "scm_planning", "refreshed_at": datetime.now(timezone.utc).isoformat()}
    projection.calculated_at = datetime.now(timezone.utc)
    return projection


def refresh_scm_plant_projections(db: Session, tenant_id: str, plant_id: str) -> int:
    rows = db.query(scm.SCMMaterialRiskSummary.material_id).filter_by(tenant_id=tenant_id, plant_id=plant_id).distinct().all()
    for (material_id,) in rows:
        refresh_scm_material_projection(db, tenant_id=tenant_id, plant_id=plant_id, scm_material_id=material_id)
    return len(rows)


def freshness(observed_at: datetime | None, *, stale_after_seconds: int = 90000) -> dict:
    if observed_at is None:
        return {"status": "missing", "observed_at": None, "age_seconds": None}
    value = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
    age = max((datetime.now(timezone.utc) - value).total_seconds(), 0)
    return {"status": "fresh" if age <= stale_after_seconds else "stale",
            "observed_at": value.isoformat(), "age_seconds": round(age)}


def material_state(db: Session, tenant_id: str, plant_id: str, material_id: str) -> dict | None:
    from app.platform.models import DataProvenance, PlatformInventoryPosition, PlatformMaterial
    material = db.query(PlatformMaterial).filter_by(id=material_id, tenant_id=tenant_id).first()
    if not material:
        return None
    projection = db.query(MaterialStateProjection).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, material_id=material_id).first()
    inventory = db.query(PlatformInventoryPosition).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, material_id=material_id).all()
    provenance = db.query(DataProvenance).filter_by(tenant_id=tenant_id, entity_type="material", entity_id=material_id).all()
    return {"entity": {"id": material.id, "code": material.code, "name": material.name,
                       "material_type": material.material_type, "base_uom_id": material.base_uom_id},
            "observed": {"inventory": [{"location_id": row.location_id, "on_hand_qty": row.on_hand_qty,
                                           "available_qty": row.available_qty, "reserved_qty": row.reserved_qty,
                                           "blocked_qty": row.blocked_qty, "in_transit_qty": row.in_transit_qty,
                                           "as_of_at": row.as_of_at, "source_authority": row.source_authority,
                                           "freshness": freshness(row.as_of_at)} for row in inventory],
                         **(projection.observed if projection else {})},
            "derived": projection.derived if projection else {}, "predicted": projection.predicted if projection else {},
            "planned": projection.planned if projection else {},
            "freshness": projection.source_freshness if projection else {"status": "missing"},
            "provenance": [{"source_system": row.source_system, "source_reference": row.source_reference,
                            "observed_at": row.observed_at, "recorded_at": row.recorded_at,
                            "quality_status": row.quality_status, "authoritative": row.authoritative,
                            "mapping_version": row.mapping_version} for row in provenance]}


def work_order_state(db: Session, tenant_id: str, work_order_id: str, *, plant_id: str) -> dict | None:
    from app.db import models as core
    from app.operations.state import get_latest_operational_state, serialize_snapshot
    order = db.query(core.ProductionWorkOrder).filter_by(id=work_order_id, tenant_id=tenant_id, plant_id=plant_id).first()
    if not order:
        return None
    snapshot = get_latest_operational_state(db, tenant_id, "line", order.line_id)
    requirements = db.query(core.ProductionMaterialRequirement).filter_by(work_order_id=order.id).all()
    return {"entity": {"id": order.id, "external_reference": order.external_reference,
                       "product_code": order.product_code, "product_name": order.product_name,
                       "status": order.status, "target_quantity": order.target_quantity,
                       "planned_start_at": order.planned_start_at, "planned_end_at": order.planned_end_at},
            "state": serialize_snapshot(snapshot),
            "material_requirements": [{"material_code": row.material_code, "required_quantity": row.required_quantity,
                                       "uom": row.uom, "required_at": row.required_at, "item_id": row.item_id} for row in requirements],
            "freshness": (snapshot.source_freshness if snapshot else {"status": "missing"})}


def factory_context(db: Session, tenant_id: str, plant_id: str, *, entity_type: str | None = None,
                    entity_id: str | None = None) -> dict:
    from app.db import models as core
    from app.platform.models import OperationalCase
    from app.scm.models import SCMPlanningRun
    plant = db.query(core.Plant).filter_by(id=plant_id, tenant_id=tenant_id).first()
    if not plant:
        return {"tenant_id": tenant_id, "plant_id": plant_id, "available": False}
    entity_state = (material_state(db, tenant_id, plant_id, entity_id) if entity_type == "material" and entity_id else
                    work_order_state(db, tenant_id, entity_id, plant_id=plant_id) if entity_type == "work_order" and entity_id else None)
    cases = db.query(OperationalCase).filter(
        OperationalCase.tenant_id == tenant_id, OperationalCase.plant_id == plant_id,
        OperationalCase.status.notin_(["closed", "cancelled", "resolved"])).order_by(
        OperationalCase.priority_score.desc(), OperationalCase.updated_at.desc()).limit(12).all()
    planning_runs = db.query(SCMPlanningRun).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, status="COMPLETED").order_by(
        SCMPlanningRun.completed_at.desc()).limit(2).all()
    return {"tenant_id": tenant_id, "plant": {"id": plant.id, "name": plant.name, "timezone": plant.timezone,
                                                "currency": plant.currency, "company_id": plant.company_id},
            "active_cases": len(cases),
            "case_attention": [{"id": row.id, "title": row.title, "summary": row.summary,
                "severity": row.severity, "priority_score": row.priority_score,
                "status": row.status, "recovery_state": row.recovery_state,
                "decision_deadline": row.decision_deadline, "expected_impact_at": row.expected_impact_at,
                "updated_at": row.updated_at} for row in cases],
            "recent_planning_runs": [{"id": row.id, "completed_at": row.completed_at,
                "as_of_at": row.as_of_at, "materials_processed": row.materials_processed,
                "exceptions_generated": row.exceptions_generated, "summary": row.summary_json,
                "input_versions": row.input_version_summary} for row in planning_runs],
            "entity_type": entity_type, "entity_id": entity_id, "entity_state": entity_state,
            "semantics": {"ai_output_is_truth": False, "critical_writes_require_action_intent": True}}
