"""Idempotent isolated demo workspaces for module-level development and QA.

These tenants are deliberately small.  They provide a common login and core
masters; each bounded module can add its own fixture set without contaminating
another module's verification workspace.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import models
from app.platform.catalog import material_for_legacy
from app.platform.events import DomainEvent, publish

DEMO_EMAIL = "demo.admin@genuinegigs.local"
DEMO_PASSWORD = "Password@123"
WORKSPACES = {
    "procurement-demo": ("Procurement Demo", "procurement"),
    "operations-demo": ("Operations Demo", "operations"),
    "scm-demo": ("SCM Demo", "scm"),
    "core-integration-demo": ("Core Integration Demo", "core"),
}


def _seed_procurement_fixture(db: Session, slug: str) -> None:
    tenant_id, plant_id = f"tenant-{slug}", f"plant-{slug}"
    user = db.get(models.User, f"usr-{slug}-admin")
    item = db.get(models.Item, f"item-{slug}-core")
    if not user or not item or db.get(models.PurchaseRequirement, f"req-{slug}-001"):
        return
    case = models.Case(id=f"case-{slug}-001", tenant_id=tenant_id, plant_id=plant_id,
                       title="Critical component sourcing", requirement="Replenish shared demo component",
                       supplier="Demo Component Supplier", owner_role="admin", owner_user_id=user.id,
                       due_at=datetime.now(timezone.utc) + timedelta(days=5), value_amount=25000,
                       currency="USD", status="sourcing", severity="high",
                       timeline=[{"title": "Shortage detected", "source": "platform"}],
                       evidence=[{"type": "canonical_material", "code": item.code}])
    requirement = models.PurchaseRequirement(
        id=f"req-{slug}-001", business_number="DEMO-REQ-001", tenant_id=tenant_id, plant_id=plant_id,
        source="material_shortage", item_id=item.id, quantity=250, uom="EA",
        need_by_date=(datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat(),
        reason="Core integration shortage scenario", status="approved", owner_user_id=user.id,
        related_case_id=case.id)
    case.requirement_id = requirement.id
    db.add_all([case, requirement, models.PurchaseRequirementLine(
        id=f"req-line-{slug}-001", business_number="DEMO-REQL-001", tenant_id=tenant_id,
        plant_id=plant_id, requirement_id=requirement.id, item_id=item.id, quantity=250,
        uom="EA", need_by_date=requirement.need_by_date, specification="Approved demo component")])


def _seed_operations_fixture(db: Session, slug: str) -> None:
    tenant_id, plant_id = f"tenant-{slug}", f"plant-{slug}"
    if db.get(models.ProductionWorkOrder, f"wo-{slug}-001"):
        return
    now = datetime.now(timezone.utc)
    area = models.PlantArea(id=f"area-{slug}-assembly", tenant_id=tenant_id, plant_id=plant_id,
                            code="ASSEMBLY", name="Assembly")
    line = models.ProductionLine(id=f"line-{slug}-01", tenant_id=tenant_id, plant_id=plant_id,
                                 area_id=area.id, code="LINE-01", name="Demo Assembly Line",
                                 standard_good_rate_per_minute=2, contribution_per_good_unit=18)
    asset = models.PlantAsset(id=f"asset-{slug}-01", tenant_id=tenant_id, plant_id=plant_id,
                              area_id=area.id, line_id=line.id, code="ASM-01", name="Assembly Cell 01",
                              asset_type="assembly_cell", criticality="high")
    shift = models.PlantShift(id=f"shift-{slug}-01", tenant_id=tenant_id, plant_id=plant_id,
                              code="A", name="Shift A", starts_at=now - timedelta(hours=2),
                              ends_at=now + timedelta(hours=6), status="active")
    product = models.ManufacturingProduct(id=f"product-{slug}-01", tenant_id=tenant_id, plant_id=plant_id,
                                          code="DEMO-FG-001", name="Demo Finished Assembly", revision="A")
    order = models.ProductionWorkOrder(id=f"wo-{slug}-001", business_number="DEMO-WO-001",
                                       tenant_id=tenant_id, plant_id=plant_id, line_id=line.id, shift_id=shift.id,
                                       external_reference="DEMO-MES-WO-001", product_code=product.code,
                                       product_name=product.name, target_quantity=500,
                                       planned_start_at=shift.starts_at, planned_end_at=shift.ends_at,
                                       status="in_progress")
    db.add(area); db.flush()
    db.add_all([line, shift, product]); db.flush()
    db.add(asset); db.add(order); db.flush()
    db.add_all([models.ManufacturingBOMLine(
        id=f"mbom-{slug}-001", tenant_id=tenant_id, plant_id=plant_id, product_id=product.id,
        component_code="DEMO-COMP-001", component_name="Demo Shared Component",
        quantity_per=2, uom="EA", operation="Assembly"), order,
        models.ProductionPlanPoint(tenant_id=tenant_id, plant_id=plant_id, work_order_id=order.id,
                                   recorded_at=now, cumulative_quantity=125, source="demo"),
        models.ProductionActualPoint(tenant_id=tenant_id, plant_id=plant_id, work_order_id=order.id,
                                     recorded_at=now, good_quantity=112, reject_quantity=3,
                                     source="demo", source_event_key=f"demo:{slug}:actual:1"),
        models.ProductionMaterialRequirement(tenant_id=tenant_id, plant_id=plant_id,
                                             work_order_id=order.id, item_id=f"item-{slug}-core",
                                             material_code="DEMO-COMP-001", description="Demo Shared Component",
                                             required_quantity=1000, uom="EA", required_at=now + timedelta(hours=4)),
        models.MaterialInventoryPosition(tenant_id=tenant_id, plant_id=plant_id,
                                         item_id=f"item-{slug}-core", material_code="DEMO-COMP-001",
                                         on_hand_quantity=720, reserved_for_other_orders=50,
                                         quality_hold_quantity=10, observed_at=now, source_system="demo_erp",
                                         source_reference=f"demo:{slug}:inventory:1")])


def seed_demo_workspaces(db: Session) -> dict[str, int]:
    account = db.query(models.Account).filter_by(email=DEMO_EMAIL).first()
    if account is None:
        account = models.Account(email=DEMO_EMAIL, name="GenuineGigs Demo Administrator", password_hash=hash_password(DEMO_PASSWORD))
        db.add(account); db.flush()
    if db.get(models.Uom, "EA") is None:
        db.add(models.Uom(id="EA", label="Each"))
    counts = {"created": 0, "existing": 0, "scm_datasets": 0}
    for slug, (name, module) in WORKSPACES.items():
        tenant = db.query(models.Tenant).filter_by(slug=slug).first()
        if tenant:
            counts["existing"] += 1
            continue
        tenant_id, company_id, plant_id = f"tenant-{slug}", f"co-{slug}", f"plant-{slug}"
        dept_id, user_id, membership_id = f"dept-{slug}", f"usr-{slug}-admin", f"mem-{slug}-admin"
        # Account is the cross-workspace login identity. User remains a
        # tenant-local persona and legacy databases enforce users.email as
        # globally unique, so use a stable internal alias for each workspace.
        user_email = f"demo.admin+{slug}@genuinegigs.local"
        tenant = models.Tenant(id=tenant_id, name=name, slug=slug, workspace_kind="demo", agent_enabled=False,
                               feature_flags={"scm_control_tower": module in {"scm", "core"}, "platform_core": True})
        db.add_all([
            tenant, models.Company(id=company_id, tenant_id=tenant_id, name=f"{name} Manufacturing", erp_code=slug.upper()[:12]),
            models.Plant(id=plant_id, tenant_id=tenant_id, company_id=company_id, name=f"{name} Plant", erp_location_code=slug.upper()[:12]),
            models.Department(id=dept_id, tenant_id=tenant_id, plant_id=plant_id, name="Demo Administration"),
            models.User(id=user_id, account_id=account.id, tenant_id=tenant_id, plant_id=plant_id, department_id=dept_id,
                        name="Demo Administrator", email=user_email, role="admin", password_hash=account.password_hash),
            models.WorkspaceMembership(id=membership_id, account_id=account.id, tenant_id=tenant_id, user_id=user_id,
                                       default_plant_id=plant_id, plant_ids=[plant_id], department_id=dept_id, role="admin",
                                       permissions=["*"], status="active"),
            models.UserPlantAccess(id=f"upa-{slug}-admin", tenant_id=tenant_id, user_id=user_id, plant_id=plant_id, is_default=True),
            models.TenantFeatureFlag(id=f"flag-{slug}-scm", tenant_id=tenant_id, key="scm_control_tower", enabled=module in {"scm", "core"}),
        ])
        db.flush()
        item = models.Item(id=f"item-{slug}-core", tenant_id=tenant_id, plant_id=plant_id, code="DEMO-COMP-001",
                           name="Demo Shared Component", uom_id="EA", erp_item_code="DEMO-COMP-001")
        supplier = models.Supplier(id=f"supplier-{slug}-core", tenant_id=tenant_id, plant_id=plant_id, name="Demo Component Supplier",
                                   status="approved", quality_score=92, delivery_score=88, erp_vendor_id="DEMO-SUP-001")
        db.add_all([item, supplier]); db.flush()
        canonical = material_for_legacy(db, tenant_id=tenant_id, plant_id=plant_id, company_id=company_id, source_system="legacy:procurement",
                                        legacy_id=item.id, code=item.code, name=item.name, base_uom_id=item.uom_id)
        publish(db, DomainEvent("platform.demo.workspace_seeded", tenant_id, plant_id, "tenant", tenant_id,
                                {"module": module, "canonical_material_id": canonical.id, "demo_login": DEMO_EMAIL}, membership_id))
        if module in {"scm", "core"}:
            from app.platform.state import refresh_scm_plant_projections
            from app.platform.integrations import ensure_source_system
            from app.scm.mock_data import load_mock_dataset
            from app.scm.service import create_run, execute_run
            load_mock_dataset(db, db.get(models.User, user_id))
            ensure_source_system(db, tenant_id=tenant_id, plant_id=plant_id,
                                 key="mock_erp", name="Deterministic Mock ERP",
                                 system_type="erp", authority={"inventory": True, "supply": True})
            run = create_run(db, db.get(models.User, user_id), trigger_key=f"demo-seed:{tenant_id}")
            execute_run(db, run.id)
            refresh_scm_plant_projections(db, tenant_id, plant_id)
            counts["scm_datasets"] += 1
        counts["created"] += 1
    for slug, (_, module) in WORKSPACES.items():
        if module in {"procurement", "core"}:
            _seed_procurement_fixture(db, slug)
        if module in {"operations", "core"}:
            _seed_operations_fixture(db, slug)
    db.flush()
    from app.platform.backfill import backfill_tenant
    counts["backfilled"] = 0
    for slug in WORKSPACES:
        tenant = db.query(models.Tenant).filter_by(slug=slug).first()
        if tenant:
            report = backfill_tenant(db, tenant.id)
            counts["backfilled"] += report.materials + report.products + report.suppliers
    return counts
