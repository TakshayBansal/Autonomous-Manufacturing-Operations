"""Deterministic, restartable canonical-master backfill with conflict reporting."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.catalog import material_for_legacy
from app.platform.models import (ExternalEntityReference, PlatformBOM, PlatformBOMItem, PlatformProduct,
    PlatformPurchaseOrder, PlatformPurchaseOrderLine, PlatformWorkOrderReference)
from app.scm import models as scm


@dataclass
class BackfillReport:
    materials: int = 0
    products: int = 0
    boms: int = 0
    suppliers: int = 0
    conflicts: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"materials": self.materials, "products": self.products, "boms": self.boms,
                "suppliers": self.suppliers, "conflicts": self.conflicts}


def _company_for_plant(db: Session, plant_id: str | None) -> str | None:
    plant = db.get(core.Plant, plant_id) if plant_id else None
    return plant.company_id if plant else None


def backfill_tenant(db: Session, tenant_id: str) -> BackfillReport:
    """Map unambiguous legacy masters; report conflicts instead of guessing."""
    report = BackfillReport()
    suppliers = db.query(core.Supplier).filter_by(tenant_id=tenant_id).all()
    supplier_codes: dict[str, list[str]] = {}
    for supplier in suppliers:
        proposed = supplier.code or supplier.erp_vendor_id or supplier.business_number or supplier.id
        supplier_codes.setdefault(proposed, []).append(supplier.id)
    for supplier in suppliers:
        supplier.company_id = supplier.company_id or _company_for_plant(db, supplier.plant_id)
        supplier.code = supplier.code or supplier.erp_vendor_id or supplier.business_number or supplier.id
        supplier.legal_name = supplier.legal_name or supplier.name
        duplicates = supplier_codes[supplier.code]
        if len(duplicates) > 1:
            if supplier.id == sorted(duplicates)[0]:
                report.conflicts.append({"entity_type": "supplier", "code": supplier.code,
                                         "ids": sorted(duplicates), "reason": "duplicate canonical code"})
            continue
        report.suppliers += 1
    for item in db.query(core.Item).filter_by(tenant_id=tenant_id).all():
        company_id = _company_for_plant(db, item.plant_id)
        if not company_id:
            report.conflicts.append({"entity_type": "material", "id": item.id, "reason": "plant/company unavailable"})
            continue
        material_for_legacy(db, tenant_id=tenant_id, plant_id=item.plant_id, company_id=company_id,
                            source_system="legacy:procurement", legacy_id=item.id, code=item.code,
                            name=item.name, base_uom_id=item.uom_id)
        report.materials += 1
    for material in db.query(scm.SCMMaterial).filter_by(tenant_id=tenant_id).all():
        site = db.query(scm.SCMMaterialPlant).filter_by(material_id=material.id).first()
        plant_id = site.plant_id if site else db.query(core.Plant.id).filter_by(tenant_id=tenant_id).scalar()
        if not plant_id:
            report.conflicts.append({"entity_type": "material", "id": material.id, "reason": "site unavailable"})
            continue
        material_for_legacy(db, tenant_id=tenant_id, plant_id=plant_id, company_id=material.company_id,
                            source_system="legacy:scm", legacy_id=material.id, code=material.material_code,
                            name=material.description or material.material_code, material_type=material.material_type,
                            base_uom_id=material.base_uom_id)
        report.materials += 1
    for product in db.query(core.ManufacturingProduct).filter_by(tenant_id=tenant_id).all():
        company_id = _company_for_plant(db, product.plant_id)
        if not company_id:
            continue
        canonical = db.query(PlatformProduct).filter_by(company_id=company_id, code=product.code).first()
        if canonical is None:
            canonical = PlatformProduct(tenant_id=tenant_id, plant_id=product.plant_id, company_id=company_id,
                                        code=product.code, name=product.name, attributes={"customer_program": product.customer_program})
            db.add(canonical); db.flush()
        if not db.query(ExternalEntityReference).filter_by(tenant_id=tenant_id, source_system="legacy:operations", entity_type="product", external_id=product.id).first():
            db.add(ExternalEntityReference(tenant_id=tenant_id, plant_id=product.plant_id, source_system="legacy:operations",
                                           entity_type="product", canonical_entity_type="product", canonical_entity_id=canonical.id,
                                           external_id=product.id, external_code=product.code))
        report.products += 1
        lines = db.query(core.ManufacturingBOMLine).filter_by(product_id=product.id).all()
        if lines:
            bom = db.query(PlatformBOM).filter_by(product_id=canonical.id, revision=product.revision).first()
            if bom is None:
                bom = PlatformBOM(tenant_id=tenant_id, plant_id=product.plant_id, company_id=company_id,
                                  product_id=canonical.id, revision=product.revision, effective_from=date(2000, 1, 1))
                db.add(bom); db.flush()
            for index, line in enumerate(lines, 1):
                material = material_for_legacy(db, tenant_id=tenant_id, plant_id=product.plant_id, company_id=company_id,
                                               source_system="legacy:operations", legacy_id=line.id,
                                               code=line.component_code, name=line.component_name)
                if not db.query(PlatformBOMItem).filter_by(bom_id=bom.id, line_number=index).first():
                    db.add(PlatformBOMItem(tenant_id=tenant_id, plant_id=product.plant_id, bom_id=bom.id,
                                           component_entity_type="material", component_id=material.id,
                                           quantity=line.quantity_per, uom_id=line.uom if db.get(core.Uom, line.uom) else None,
                                           scrap_factor=line.scrap_factor, line_number=index))
            report.boms += 1
    # Procurement remains the behavior owner, while these records give SCM a
    # stable PO identity that does not expose Procurement's internal schema.
    for legacy_po in db.query(core.PODraft).filter_by(tenant_id=tenant_id).all():
        number = legacy_po.business_number or legacy_po.id
        po = db.query(PlatformPurchaseOrder).filter_by(
            tenant_id=tenant_id, plant_id=legacy_po.plant_id, order_number=number).first()
        lines = db.query(core.PODraftLine).filter_by(po_draft_id=legacy_po.id).all()
        dates = []
        for line in lines:
            try: dates.append(date.fromisoformat(line.need_by_date[:10]))
            except (TypeError, ValueError): pass
        if po is None:
            po = PlatformPurchaseOrder(tenant_id=tenant_id, plant_id=legacy_po.plant_id,
                order_number=number, supplier_id=legacy_po.supplier_id, status=legacy_po.status,
                currency=legacy_po.currency, original_delivery_date=min(dates) if dates else None,
                confirmed_delivery_date=min(dates) if dates else None, source_authority="legacy:procurement")
            db.add(po); db.flush()
        if not db.query(ExternalEntityReference).filter_by(tenant_id=tenant_id,
                source_system="legacy:procurement", entity_type="purchase_order", external_id=legacy_po.id).first():
            db.add(ExternalEntityReference(tenant_id=tenant_id, plant_id=legacy_po.plant_id,
                source_system="legacy:procurement", entity_type="purchase_order",
                canonical_entity_type="purchase_order", canonical_entity_id=po.id,
                external_id=legacy_po.id, external_code=number))
        for index, line in enumerate(lines, 1):
            mapping = db.query(ExternalEntityReference).filter_by(tenant_id=tenant_id,
                source_system="legacy:procurement", entity_type="material", external_id=line.item_id).first()
            if mapping and not db.query(PlatformPurchaseOrderLine).filter_by(
                    purchase_order_id=po.id, line_number=str(index)).first():
                db.add(PlatformPurchaseOrderLine(tenant_id=tenant_id, plant_id=legacy_po.plant_id,
                    purchase_order_id=po.id, line_number=str(index), material_id=mapping.canonical_entity_id,
                    quantity=line.quantity, uom_id=line.uom if db.get(core.Uom, line.uom) else None))
    for work_order in db.query(core.ProductionWorkOrder).filter_by(tenant_id=tenant_id).all():
        product = db.query(PlatformProduct).filter_by(tenant_id=tenant_id,
            plant_id=work_order.plant_id, code=work_order.product_code).first()
        if product and not db.query(PlatformWorkOrderReference).filter_by(work_order_id=work_order.id).first():
            equipment = db.query(core.PlantAsset).filter_by(tenant_id=tenant_id,
                plant_id=work_order.plant_id, line_id=work_order.line_id).first()
            db.add(PlatformWorkOrderReference(tenant_id=tenant_id, plant_id=work_order.plant_id,
                work_order_id=work_order.id, product_id=product.id, work_center_id=work_order.line_id,
                equipment_id=equipment.id if equipment else None, source_authority="legacy:operations"))
        if product and not db.query(ExternalEntityReference).filter_by(tenant_id=tenant_id,
                source_system="legacy:operations", entity_type="work_order", external_id=work_order.id).first():
            db.add(ExternalEntityReference(tenant_id=tenant_id, plant_id=work_order.plant_id,
                source_system="legacy:operations", entity_type="work_order", canonical_entity_type="work_order",
                canonical_entity_id=work_order.id, external_id=work_order.id,
                external_code=work_order.external_reference))
    db.flush()
    from app.platform.relationships import sync_tenant_graph
    sync_tenant_graph(db, tenant_id)
    return report
