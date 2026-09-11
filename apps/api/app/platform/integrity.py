"""Conservative canonical-model integrity checks; never guesses mappings."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.models import (DataQualityIssue, ExternalEntityReference, PlatformBOMItem,
    PlatformMaterial, PlatformPurchaseOrder, PlatformPurchaseOrderLine, PlatformWorkOrderReference)
from app.scm import models as scm


def check_tenant(db: Session, tenant_id: str, *, persist: bool = False) -> list[dict]:
    issues: list[dict] = []
    def add(entity_type: str, entity_id: str | None, rule: str, message: str, details: dict | None = None):
        item = {"entity_type": entity_type, "entity_id": entity_id, "rule_key": rule,
                "severity": "error", "message": message, "details": details or {}}
        issues.append(item)
        if persist and not db.query(DataQualityIssue).filter_by(
                tenant_id=tenant_id, entity_id=entity_id, rule_key=rule, status="open").first():
            db.add(DataQualityIssue(tenant_id=tenant_id, plant_id=None, status="open", **item))

    duplicates = db.query(PlatformMaterial.company_id, PlatformMaterial.code, func.count(PlatformMaterial.id)).filter_by(
        tenant_id=tenant_id).group_by(PlatformMaterial.company_id, PlatformMaterial.code).having(func.count(PlatformMaterial.id) > 1).all()
    for company_id, code, count in duplicates:
        add("material", None, "duplicate_canonical_material", f"{count} canonical materials share {code}", {"company_id": company_id})
    for model, entity_type in ((core.Item, "material"), (scm.SCMMaterial, "material")):
        for row in db.query(model).filter_by(tenant_id=tenant_id).all():
            mapped = db.query(ExternalEntityReference).filter_by(tenant_id=tenant_id, external_id=row.id,
                                                                  canonical_entity_type=entity_type).first()
            if not mapped:
                add(entity_type, row.id, "orphan_module_entity", f"{model.__name__} has no canonical mapping")
            site_id = row.plant_id
            if model is scm.SCMMaterial and not site_id:
                site_id = db.query(scm.SCMMaterialPlant.plant_id).filter_by(material_id=row.id, tenant_id=tenant_id).scalar()
            if not site_id or not db.query(core.Plant).filter_by(id=site_id, tenant_id=tenant_id).first():
                add(entity_type, row.id, "missing_site_ownership", f"{model.__name__} has invalid site ownership")
    for po in db.query(PlatformPurchaseOrder).filter_by(tenant_id=tenant_id).all():
        if not db.query(core.Supplier).filter_by(id=po.supplier_id, tenant_id=tenant_id).first():
            add("purchase_order", po.id, "invalid_supplier_mapping", "Purchase order supplier is outside tenant")
    for line in db.query(PlatformPurchaseOrderLine).filter_by(tenant_id=tenant_id).all():
        if not db.query(PlatformMaterial).filter_by(id=line.material_id, tenant_id=tenant_id).first():
            add("purchase_order", line.purchase_order_id, "broken_po_material", "PO line material is not canonical")
    for item in db.query(PlatformBOMItem).filter_by(tenant_id=tenant_id).all():
        if item.component_entity_type == "material" and not db.query(PlatformMaterial).filter_by(id=item.component_id, tenant_id=tenant_id).first():
            add("bom", item.bom_id, "broken_bom_reference", "BOM component is not a canonical material")
    for ref in db.query(PlatformWorkOrderReference).filter_by(tenant_id=tenant_id).all():
        if not db.query(core.ProductionWorkOrder).filter_by(id=ref.work_order_id, tenant_id=tenant_id).first():
            add("work_order", ref.work_order_id, "broken_work_order_reference", "Canonical work-order reference is orphaned")
    return issues
