"""Reusable canonical SCM fixture for Phases 0-3 and later UI demos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.backfill import backfill_tenant
from app.platform.models import (ExternalEntityReference, PlatformBOM, PlatformBOMItem,
                                 PlatformProduct)
from app.platform.relationships import sync_tenant_graph
from app.scm import models
from app.scm.mock_data import load_mock_dataset


def load_acceptance_dataset(db: Session, user: core.User) -> dict:
    """Load a restartable canonical product/BOM/demand fixture over the SCM demo data.

    The older SCM tables remain populated for compatibility, but every planning
    target is resolved through a canonical platform identity.
    """
    summary = load_mock_dataset(db, user)
    db.flush()
    canonical = backfill_tenant(db, user.tenant_id)
    plant = db.get(core.Plant, user.plant_id)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    product = db.query(PlatformProduct).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, code="SCM-FG100").first()
    if product is None:
        product = PlatformProduct(tenant_id=user.tenant_id, plant_id=user.plant_id,
            company_id=plant.company_id, code="SCM-FG100", name="Lighting control assembly",
            base_uom_id="EA", attributes={"fixture": "scm-phases-0-3"})
        db.add(product)
        db.flush()
    bom = db.query(PlatformBOM).filter_by(product_id=product.id, revision="A").first()
    if bom is None:
        bom = PlatformBOM(tenant_id=user.tenant_id, plant_id=user.plant_id,
            company_id=plant.company_id, product_id=product.id, revision="A",
            effective_from=now.date(), status="ACTIVE")
        db.add(bom)
        db.flush()
    component_quantities = {"SCM-C100": Decimal("2"), "SCM-C200": Decimal("1"), "SCM-C300": Decimal("4")}
    for line_number, (code, quantity) in enumerate(component_quantities.items(), 1):
        legacy = db.query(models.SCMMaterial).filter_by(
            tenant_id=user.tenant_id, company_id=plant.company_id, material_code=code).one()
        reference = db.query(ExternalEntityReference).filter_by(tenant_id=user.tenant_id,
            source_system="legacy:scm", entity_type="material", external_id=legacy.id).one()
        if not db.query(PlatformBOMItem).filter_by(bom_id=bom.id, line_number=line_number * 10).first():
            db.add(PlatformBOMItem(tenant_id=user.tenant_id, plant_id=user.plant_id,
                bom_id=bom.id, component_entity_type="material",
                component_id=reference.canonical_entity_id, quantity=quantity,
                uom_id="EA", scrap_factor=Decimal("0"), line_number=line_number * 10))
    version = f"SCM-ACCEPTANCE-{now.date().isoformat()}"
    demand_plan = db.query(models.SCMDemandPlan).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, plan_version=version).first()
    if demand_plan is None:
        demand_plan = models.SCMDemandPlan(tenant_id=user.tenant_id, plant_id=user.plant_id,
            plan_version=version, period_start=now.date(), period_end=now.date() + timedelta(days=209),
            status="PUBLISHED", published_at=now, correlation_id=f"fixture:{version}")
        db.add(demand_plan)
        db.flush()
        # Both rows overlap deliberately: precedence must consume the firm plan,
        # not add the forecast and double-count demand.
        for demand_type, quantity, priority in (("PRODUCTION_PLAN", "60000", 10), ("FORECAST", "65000", 500)):
            db.add(models.SCMDemandBucket(tenant_id=user.tenant_id, plant_id=user.plant_id,
                demand_plan_id=demand_plan.id, product_id=product.id,
                bucket_date=now.date() + timedelta(days=10), quantity=Decimal(quantity),
                demand_type=demand_type, priority=priority,
                source_reference=f"{version}:{demand_type}",
                lineage={"overlap_key": "SCM-FG100:DAY10", "fixture": "scm-phases-0-3"}))
    db.flush()
    sync_tenant_graph(db, user.tenant_id)
    return {**summary, "canonical_materials": canonical.materials,
            "canonical_product_id": product.id, "canonical_bom_id": bom.id,
            "demand_plan_id": demand_plan.id, "horizon_days": 210}
