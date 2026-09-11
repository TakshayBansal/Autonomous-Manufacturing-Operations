from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import models as core_models
from app.scm import models
from app.scm.service import ensure_baseline_scenario, ensure_default_policy


def load_mock_dataset(db: Session, user: core_models.User) -> dict[str, int]:
    """Idempotently load a small, dated control-tower demonstration."""
    plant = db.get(core_models.Plant, user.plant_id)
    if not plant:
        raise ValueError("Selected plant is unavailable")
    for uom_id, label in (("EA", "Each"), ("KG", "Kilogram")):
        if not db.get(core_models.Uom, uom_id):
            db.add(core_models.Uom(id=uom_id, label=label))
    db.flush()
    definitions = (
        ("SCM-FG100", "Lighting control assembly", "FINISHED_GOOD"),
        ("SCM-C100", "Connector housing", "COMPONENT"),
        ("SCM-C200", "LED driver board", "COMPONENT"),
        ("SCM-C300", "Mounting clip", "COMPONENT"),
        ("SCM-C400", "Power terminal block", "COMPONENT"),
        ("SCM-C500", "Thermal interface pad", "COMPONENT"),
    )
    material_by_code: dict[str, models.SCMMaterial] = {}
    for code, description, material_type in definitions:
        material = db.query(models.SCMMaterial).filter_by(company_id=plant.company_id, material_code=code).first()
        if not material:
            material = models.SCMMaterial(
                tenant_id=user.tenant_id, plant_id=None, company_id=plant.company_id,
                material_code=code, description=description, material_type=material_type,
                base_uom_id="EA", external_id=f"MOCK-{code}", metadata_json={"fixture": "scm-v1"},
            )
            db.add(material)
            db.flush()
        material_by_code[code] = material
        if not db.query(models.SCMMaterialPlant).filter_by(material_id=material.id, plant_id=user.plant_id).first():
            item = db.query(core_models.Item).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, code=code).first()
            db.add(models.SCMMaterialPlant(tenant_id=user.tenant_id, plant_id=user.plant_id, material_id=material.id, item_id=item.id if item else None))
    supplier = db.query(core_models.Supplier).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, erp_vendor_id="SCM-MOCK-SUP").first()
    if not supplier:
        supplier = core_models.Supplier(
            tenant_id=user.tenant_id, plant_id=user.plant_id, name="Mock Precision Components",
            status="active", quality_score=94, delivery_score=82, erp_vendor_id="SCM-MOCK-SUP",
        )
        db.add(supplier)
        db.flush()
    customer = db.query(models.SCMCustomer).filter_by(company_id=plant.company_id, code="OEM-DEMO").first()
    if not customer:
        customer = models.SCMCustomer(tenant_id=user.tenant_id, plant_id=None, company_id=plant.company_id, code="OEM-DEMO", name="Demo OEM", external_id="MOCK-OEM")
        db.add(customer)
        db.flush()
    fg = material_by_code["SCM-FG100"]
    if not db.query(models.SCMMaterialCustomerUsage).filter_by(finished_good_material_id=fg.id, plant_id=user.plant_id, customer_id=customer.id).first():
        db.add(models.SCMMaterialCustomerUsage(tenant_id=user.tenant_id, plant_id=user.plant_id, finished_good_material_id=fg.id, customer_id=customer.id, program_name="Demo Lighting", customer_part_number="OEM-LAMP-100"))
    bom = db.query(models.SCMBOM).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, bom_code="SCM-FG100-BOM", revision="A").first()
    if not bom:
        bom = models.SCMBOM(
            tenant_id=user.tenant_id, plant_id=user.plant_id, company_id=plant.company_id,
            parent_material_id=fg.id, bom_code="SCM-FG100-BOM", revision="A",
            effective_from=date(2020, 1, 1), status="ACTIVE", source_system="mock_erp", external_id="MOCK-BOM-FG100-A",
        )
        db.add(bom)
        db.flush()
        for line, code, quantity in ((10, "SCM-C100", "2"), (20, "SCM-C200", "1"), (30, "SCM-C300", "4")):
            db.add(models.SCMBOMLine(
                tenant_id=user.tenant_id, plant_id=user.plant_id, bom_id=bom.id,
                component_material_id=material_by_code[code].id, quantity_per=Decimal(quantity),
                uom_id="EA", scrap_factor=Decimal("0"), line_number=line,
            ))
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)
    inventory_values = {"SCM-C100": "30000", "SCM-C200": "90000", "SCM-C300": "400000",
                        "SCM-C400": "10000", "SCM-C500": "20000"}
    demand_values = {"SCM-C100": "48000", "SCM-C200": "60000", "SCM-C300": "220000",
                     "SCM-C400": "50000", "SCM-C500": "40000"}
    for code, value in inventory_values.items():
        material = material_by_code[code]
        source_id = f"MOCK-INV-{code}-{today.isoformat()}"
        if not db.query(models.SCMInventorySnapshot).filter_by(tenant_id=user.tenant_id, source_system="mock_erp", source_record_id=source_id).first():
            db.add(models.SCMInventorySnapshot(
                tenant_id=user.tenant_id, plant_id=user.plant_id, material_id=material.id,
                snapshot_at=now, on_hand_qty=Decimal(value), unrestricted_qty=Decimal(value),
                available_qty=Decimal(value), uom_id="EA", source_system="mock_erp", source_record_id=source_id,
            ))
        requirement_id = f"MOCK-REQ-{code}-{today.isoformat()}"
        if not db.query(models.SCMMaterialRequirement).filter_by(tenant_id=user.tenant_id, source_system="mock_erp", external_id=requirement_id).first():
            db.add(models.SCMMaterialRequirement(
                tenant_id=user.tenant_id, plant_id=user.plant_id, material_id=material.id,
                required_date=today + timedelta(days=10), quantity=Decimal(demand_values[code]),
                uom_id="EA", requirement_type="PRODUCTION", priority=10,
                finished_good_id=fg.id, customer_id=customer.id,
                source_system="mock_erp", external_id=requirement_id,
                lineage={"path": ["OEM-DEMO", "SCM-FG100", code]},
            ))
        policy = db.query(models.SCMMaterialPlantPolicy).filter_by(material_id=material.id, plant_id=user.plant_id).first()
        if not policy:
            db.add(models.SCMMaterialPlantPolicy(
                tenant_id=user.tenant_id, plant_id=user.plant_id, material_id=material.id,
                default_supplier_id=supplier.id, planned_lead_time_days=14,
                safety_stock_qty=Decimal("5000"), minimum_order_qty=Decimal("1000"),
                order_multiple=Decimal("500"), maximum_coverage_days=45,
                planning_time_fence_days=3, cancellation_window_days=7, expedite_window_days=14,
            ))
        relationship = db.query(models.SCMMaterialSupplier).filter_by(material_id=material.id, plant_id=user.plant_id, supplier_id=supplier.id).first()
        if not relationship:
            db.add(models.SCMMaterialSupplier(
                tenant_id=user.tenant_id, plant_id=user.plant_id, material_id=material.id,
                supplier_id=supplier.id, approved_status="APPROVED", contract_lead_time_days=14,
                minimum_order_qty=Decimal("1000"), order_multiple=Decimal("500"),
                expedite_allowed=True, pushout_allowed=True, cancellation_allowed=True,
            ))
    # Three receipt patterns: insufficient late supply, persistent critical
    # exposure, and receipt-driven recovery. They are planning inputs, not UI mocks.
    supply_patterns = (("SCM-C100", "30000", 18, "45000123"),
                       ("SCM-C400", "10000", 18, "45000400"),
                       ("SCM-C500", "50000", 15, "45000500"))
    for code, quantity, due_days, order_number in supply_patterns:
        material = material_by_code[code]
        order_source = f"MOCK-PO-{code.removeprefix('SCM-')}-{today.isoformat()}"
        order = db.query(models.SCMSupplyOrder).filter_by(
            tenant_id=user.tenant_id, source_system="mock_erp", source_record_id=order_source).first()
        if not order:
            order = models.SCMSupplyOrder(
                tenant_id=user.tenant_id, plant_id=user.plant_id, supply_type="PURCHASE_ORDER",
                material_id=material.id, supplier_id=supplier.id, order_number=order_number, line_number="20",
                ordered_qty=Decimal(quantity), received_qty=Decimal("0"), uom_id="EA",
                status="OPEN", firmness="FIRM", source_system="mock_erp", source_record_id=order_source,
            )
            db.add(order)
            db.flush()
            db.add(models.SCMSupplyScheduleLine(
                tenant_id=user.tenant_id, plant_id=user.plant_id, supply_order_id=order.id,
                schedule_line_number="1", scheduled_qty=Decimal(quantity), received_qty=Decimal("0"),
                original_due_date=today + timedelta(days=due_days),
                current_due_date=today + timedelta(days=due_days),
                supplier_commit_date=today + timedelta(days=due_days), status="CONFIRMED",
                source_record_id=f"{order_source}-1",
            ))
    source_state = db.query(models.SCMDataSourceState).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, source_key="mock_erp").first()
    if not source_state:
        source_state = models.SCMDataSourceState(tenant_id=user.tenant_id, plant_id=user.plant_id, source_key="mock_erp", status="HEALTHY", expected_frequency_seconds=3600, stale_after_seconds=7200)
        db.add(source_state)
    source_state.last_attempt = source_state.last_successful_import = now
    source_state.records_processed = 12
    ensure_default_policy(db, user)
    ensure_baseline_scenario(db, user)
    return {"materials": len(definitions), "customers": 1, "boms": 1,
            "inventory_snapshots": len(inventory_values), "requirements": len(demand_values),
            "supply_orders": len(supply_patterns)}
