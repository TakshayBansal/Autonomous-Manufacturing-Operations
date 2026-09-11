"""Canonical catalogue adapters; legacy masters are not rewritten in place."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.platform.models import DataProvenance, ExternalEntityReference, PlatformMaterial, PlatformMaterialSite


def material_for_legacy(
    db: Session, *, tenant_id: str, plant_id: str, company_id: str, source_system: str,
    legacy_id: str, code: str, name: str, material_type: str = "OTHER", base_uom_id: str | None = None,
) -> PlatformMaterial:
    """Resolve or create a canonical material and an explicit legacy mapping."""
    ref = db.query(ExternalEntityReference).filter_by(
        tenant_id=tenant_id, source_system=source_system, entity_type="material", external_id=legacy_id,
    ).first()
    material = db.get(PlatformMaterial, ref.canonical_entity_id) if ref else None
    if material is None:
        material = db.query(PlatformMaterial).filter_by(company_id=company_id, code=code).first()
    if material is None:
        material = PlatformMaterial(tenant_id=tenant_id, company_id=company_id, code=code, name=name,
                                    material_type=material_type, base_uom_id=base_uom_id)
        db.add(material)
        db.flush()
    if ref is None:
        ref = ExternalEntityReference(
            tenant_id=tenant_id, plant_id=plant_id, source_system=source_system, entity_type="material",
            canonical_entity_type="material", canonical_entity_id=material.id, external_id=legacy_id,
            external_code=code,
        )
        db.add(ref)
        db.add(DataProvenance(
            tenant_id=tenant_id, plant_id=plant_id, entity_type="material", entity_id=material.id,
            source_system=source_system, source_reference=legacy_id, mapping_version="catalog-adapter@1",
            transformation="legacy material identity mapping", quality_status="accepted", authoritative=False,
            details={"external_code": code},
        ))
        from app.platform.events import DomainEvent, publish
        publish(db, DomainEvent(
            event_type="master.material.mapped", tenant_id=tenant_id, plant_id=plant_id,
            subject_type="material", subject_id=material.id,
            payload={"canonical_material_id": material.id, "source_system": source_system,
                     "external_id": legacy_id, "code": code}, source_system=source_system,
        ))
    site = db.query(PlatformMaterialSite).filter_by(material_id=material.id, plant_id=plant_id).first()
    if site is None:
        db.add(PlatformMaterialSite(tenant_id=tenant_id, plant_id=plant_id, material_id=material.id))
    return material


def canonical_material(db: Session, tenant_id: str, material_id: str) -> PlatformMaterial | None:
    return db.query(PlatformMaterial).filter_by(id=material_id, tenant_id=tenant_id).first()
