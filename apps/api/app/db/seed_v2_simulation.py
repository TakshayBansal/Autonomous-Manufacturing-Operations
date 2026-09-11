"""Idempotent Northstar factory seed. It never deletes another tenant."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import models
from app.db.tenant_lock import acquire_tenant_transaction_lock

TENANT_ID = "tenant-northstar-mobility"
CHAKAN_ID = "plant-northstar-chakan"
NASHIK_ID = "plant-northstar-nashik"
SEED_VERSION = "northstar-live@2"

# PostgreSQL protects these append-only compliance ledgers with a trigger. A
# simulation reset must rebuild operational state without rewriting history.
IMMUTABLE_LEDGER_TABLES = frozenset({"audit_events", "approval_decisions"})

PERSONAS = [
    ("corporate_operations_director", "Ananya Deshmukh", "corporate", [CHAKAN_ID, NASHIK_ID]),
    ("plant_manager", "Vikram Kulkarni", "leadership", [CHAKAN_ID]),
    ("production_manager", "Meera Jadhav", "production", [CHAKAN_ID]),
    ("production_supervisor", "Rohit Shinde", "production", [CHAKAN_ID]),
    ("production_operator", "Kavita Pawar", "production", [CHAKAN_ID]),
    ("maintenance_manager", "Suresh More", "maintenance", [CHAKAN_ID]),
    ("maintenance_technician", "Imran Shaikh", "maintenance", [CHAKAN_ID]),
    ("quality_manager", "Neha Bhosale", "quality", [CHAKAN_ID]),
    ("quality_inspector", "Pooja Salunkhe", "quality", [CHAKAN_ID]),
    ("purchase_manager", "Aditya Joshi", "purchase", [CHAKAN_ID, NASHIK_ID]),
    ("purchase_executive", "Snehal Patil", "purchase", [CHAKAN_ID]),
    ("store_manager", "Nitin Gaikwad", "stores", [CHAKAN_ID]),
    ("gate_operator", "Mahesh Chavan", "gate", [CHAKAN_ID]),
    ("admin", "Rhea Nair", "administration", [CHAKAN_ID, NASHIK_ID]),
]

PRODUCTS = [
    ("GH-220", "EPS Gear Housing GH-220", 920),
    ("BC-410", "Brake Caliper Carrier BC-410", 840),
    ("TSF-72", "Transmission Selector Fork TSF-72", 1100),
    ("MES-160", "Motor End Shield MES-160", 960),
]


def _current_shift_anchor(reference: datetime | None = None) -> tuple[datetime, int]:
    now = (reference or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Kolkata"))
    starts = (6, 14, 22)
    candidates = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in starts]
    start = max((candidate for candidate in candidates if candidate <= now), default=candidates[-1] - timedelta(days=1))
    return start.astimezone(timezone.utc), starts.index(start.astimezone(ZoneInfo("Asia/Kolkata")).hour)


def reset_northstar(db: Session) -> None:
    """Rebuild Northstar data while retaining its identity and immutable history."""
    acquire_tenant_transaction_lock(db, TENANT_ID)
    for table in reversed(models.Base.metadata.sorted_tables):
        if "tenant_id" in table.c and table.name not in IMMUTABLE_LEDGER_TABLES:
            db.execute(delete(table).where(table.c.tenant_id == TENANT_ID))
    db.execute(delete(models.Account).where(models.Account.email.like("%@northstar-mobility.local")))
    db.flush()


def seed_northstar(db: Session, *, reset: bool = False, reference: datetime | None = None) -> models.Tenant:
    existing = db.get(models.Tenant, TENANT_ID)
    if existing and not reset and (existing.feature_flags or {}).get("simulation_seed_version") == SEED_VERSION:
        return existing
    if existing:
        reset_northstar(db)
    password = os.getenv("V2_SIMULATION_PASSWORD", "Northstar@2026")
    anchor, active_index = _current_shift_anchor(reference)
    tenant = existing or models.Tenant(id=TENANT_ID)
    tenant.slug = "northstar-precision-mobility"
    tenant.name = "Northstar Precision Mobility Pvt Ltd"
    tenant.status = "active"
    tenant.workspace_kind = "simulation"
    tenant.onboarding_status = "complete"
    tenant.agent_enabled = True
    tenant.feature_flags = {"v2_operations": True, "factory_simulator": True,
                            "simulation_seed_version": SEED_VERSION}
    company = models.Company(id="co-northstar", tenant_id=TENANT_ID, name=tenant.name, erp_code="NSPM")
    plants = [
        models.Plant(id=CHAKAN_ID, tenant_id=TENANT_ID, company_id=company.id, name="Chakan Plant",
                     erp_location_code="NSPM-CHK", timezone="Asia/Kolkata", currency="INR", locale="en-IN"),
        models.Plant(id=NASHIK_ID, tenant_id=TENANT_ID, company_id=company.id, name="Nashik Plant",
                     erp_location_code="NSPM-NSK", timezone="Asia/Kolkata", currency="INR", locale="en-IN"),
    ]
    db.add_all([tenant, company, *plants]); db.flush()
    departments = {}
    for key in {row[2] for row in PERSONAS}:
        department = models.Department(id=f"dept-ns-{key}", tenant_id=TENANT_ID, plant_id=CHAKAN_ID, name=key.replace("_", " ").title())
        departments[key] = department; db.add(department)
    db.flush()

    users = {}
    manager_membership = None
    for idx, (role, name, dept, plant_ids) in enumerate(PERSONAS, 1):
        email = f"{name.lower().replace(' ', '.')}@northstar-mobility.local"
        account = models.Account(id=f"acct-ns-{idx:02}", email=email, name=name, password_hash=hash_password(password), email_verified_at=anchor)
        user = models.User(id=f"usr-ns-{idx:02}", account_id=account.id, tenant_id=TENANT_ID, plant_id=plant_ids[0],
                           department_id=departments[dept].id, name=name, email=email, role=role, password_hash=account.password_hash,
                           manager_id="usr-ns-02" if idx > 2 else None)
        membership = models.WorkspaceMembership(id=f"mem-ns-{idx:02}", account_id=account.id, tenant_id=TENANT_ID,
            user_id=user.id, default_plant_id=plant_ids[0], plant_ids=plant_ids, department_id=departments[dept].id,
            role=role, manager_membership_id=manager_membership, permissions=["workspace.owner"] if role == "admin" else [])
        if role == "plant_manager": manager_membership = membership.id
        users[role] = user
        db.add_all([account, user, membership])
        for plant_id in plant_ids:
            db.add(models.UserPlantAccess(id=f"upa-ns-{idx:02}-{plant_id[-3:]}", tenant_id=TENANT_ID,
                                          user_id=user.id, plant_id=plant_id, is_default=plant_id == plant_ids[0]))
        db.flush()

    areas = {}
    for key, label in (("machining", "Machining"), ("finishing", "Finishing"), ("inspection", "Inspection"),
                       ("assembly", "Assembly"), ("stores", "Stores"), ("maintenance", "Maintenance")):
        area = models.PlantArea(id=f"area-ns-{key}", tenant_id=TENANT_ID, plant_id=CHAKAN_ID, name=label, code=key.upper())
        areas[key] = area; db.add(area)
    db.flush()
    line_specs = [("L01", "Gear Housing Cell", "machining"), ("L02", "Caliper Carrier Cell", "machining"),
                  ("L03", "Selector Fork Cell", "finishing"), ("L04", "End Shield Cell", "machining"),
                  ("L05", "Final Inspection", "inspection"), ("L06", "Sub Assembly", "assembly")]
    lines = []
    for idx, (code, name, area) in enumerate(line_specs, 1):
        row = models.ProductionLine(id=f"line-ns-{idx:02}", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
            area_id=areas[area].id, name=name, code=code, standard_good_rate_per_minute=2.1 + idx * .08,
            contribution_per_good_unit=95 + idx * 7)
        lines.append(row); db.add(row)
    db.flush()
    assets = []
    asset_types = ("cnc", "vmc", "washer")
    for line_index, line in enumerate(lines):
        for machine_index in range(3):
            code = f"{asset_types[machine_index].upper()}-{line_index + 1:02}-{machine_index + 1:02}"
            asset = models.PlantAsset(id=f"asset-ns-{line_index+1:02}-{machine_index+1:02}", tenant_id=TENANT_ID,
                plant_id=CHAKAN_ID, area_id=line.area_id, line_id=line.id, name=code, code=code,
                asset_type=asset_types[machine_index], criticality="high" if machine_index == 0 else "normal")
            assets.append(asset); db.add(asset)
    db.flush()

    shifts = []
    current_day_shift_a = anchor - timedelta(hours=active_index * 8)
    for day_offset in range(-90, 2):
        day = current_day_shift_a + timedelta(days=day_offset)
        for shift_index, code in enumerate(("A", "B", "C")):
            start = day + timedelta(hours=shift_index * 8)
            shift = models.PlantShift(id=f"shift-ns-{day:%Y%m%d}-{code}", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
                name=f"Shift {code}", code=code, starts_at=start, ends_at=start + timedelta(hours=8),
                status="active" if day_offset == 0 and shift_index == active_index else "completed" if start < anchor else "scheduled")
            shifts.append(shift); db.add(shift)
    db.flush()
    active_shift = next((s for s in shifts if s.status == "active"), shifts[-3])
    shift_progress = min(max((anchor - active_shift.starts_at).total_seconds() / (8 * 3600), 0), 1)
    attainment_offsets = (-.008, .004, -.003, .007, -.005, .002)
    live_orders = []
    for idx, line in enumerate(lines):
        code, product, target = PRODUCTS[idx % len(PRODUCTS)]
        order = models.ProductionWorkOrder(id=f"wo-ns-live-{idx+1:02}", business_number=f"NS-WO-{anchor:%y%m%d}-{idx+1:03}",
            tenant_id=TENANT_ID, plant_id=CHAKAN_ID, line_id=line.id, shift_id=active_shift.id,
            external_reference=f"SAP-PP-{anchor:%Y%m%d}-{idx+1:04}", product_code=code, product_name=product,
            target_quantity=target, planned_start_at=active_shift.starts_at, planned_end_at=active_shift.ends_at,
            status="in_progress")
        db.add(order); db.flush(); live_orders.append(order)
        for hour in range(9):
            db.add(models.ProductionPlanPoint(tenant_id=TENANT_ID, plant_id=CHAKAN_ID, work_order_id=order.id,
                recorded_at=active_shift.starts_at + timedelta(hours=hour), cumulative_quantity=target * hour / 8, source="factory_simulator"))
        db.add(models.ProductionActualPoint(tenant_id=TENANT_ID, plant_id=CHAKAN_ID, work_order_id=order.id,
            recorded_at=anchor, good_quantity=target * min(max(shift_progress + attainment_offsets[idx], 0), 1), reject_quantity=3 + idx,
            source="factory_simulator", source_event_key=f"northstar:seed:{order.id}"))

    # Ninety complete days at shift/line grain. Values are deterministic and
    # deliberately include recurring downtime and quality patterns.
    historical_shifts = [row for row in shifts if row.status == "completed"]
    for shift_no, shift in enumerate(historical_shifts):
        for line_no, line in enumerate(lines):
            code, product, base_target = PRODUCTS[(shift_no + line_no) % len(PRODUCTS)]
            target = base_target + ((shift_no % 5) - 2) * 12
            attainment = .91 + ((shift_no * 7 + line_no * 3) % 9) / 100
            reject = 2 + ((shift_no + line_no) % 7)
            order = models.ProductionWorkOrder(id=f"wo-ns-h-{shift_no:03}-{line_no:02}",
                business_number=f"NS-WO-H{shift_no:03}-{line_no+1:02}", tenant_id=TENANT_ID,
                plant_id=CHAKAN_ID, line_id=line.id, shift_id=shift.id,
                external_reference=f"SAP-HIST-{shift_no:03}-{line_no+1:02}", product_code=code,
                product_name=product, target_quantity=target, planned_start_at=shift.starts_at,
                planned_end_at=shift.ends_at, status="completed")
            db.add(order); db.flush()
            db.add_all([
                models.ProductionPlanPoint(tenant_id=TENANT_ID, plant_id=CHAKAN_ID, work_order_id=order.id,
                    recorded_at=shift.ends_at, cumulative_quantity=target, source="sap_s4hana"),
                models.ProductionActualPoint(tenant_id=TENANT_ID, plant_id=CHAKAN_ID, work_order_id=order.id,
                    recorded_at=shift.ends_at-timedelta(minutes=2), good_quantity=round(target*attainment),
                    reject_quantity=reject, source="mes_gateway", source_event_key=f"hist:{order.id}:final"),
            ])
            if (shift_no + line_no) % 19 == 0:
                db.add(models.ProductionDowntimeEvent(tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
                    work_order_id=order.id, line_id=line.id, asset_id=assets[line_no*3].id,
                    started_at=shift.starts_at+timedelta(hours=3), ended_at=shift.starts_at+timedelta(hours=3, minutes=18+(shift_no%24)),
                    category="breakdown", reason=("Hydraulic pressure low" if line_no % 2 else "Tool life alarm"), planned=False))
            if (shift_no + line_no) % 13 == 0:
                db.add(models.ProductionQualityEvent(tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
                    work_order_id=order.id, line_id=line.id, asset_id=assets[line_no*3].id,
                    occurred_at=shift.starts_at+timedelta(hours=5), event_type="inspection",
                    inspected_quantity=80, rejected_quantity=reject, defect_code="DIMENSIONAL-DRIFT",
                    material_lot_id=f"LOT-{code}-{shift.starts_at:%y%m%d}-{shift.code}", source="qms"))
    nashik_area=models.PlantArea(id="area-ns-nashik-machining",tenant_id=TENANT_ID,plant_id=NASHIK_ID,name="Machining",code="MACHINING")
    db.add(nashik_area);db.flush()
    nashik_lines=[]
    for index,(code,name) in enumerate((("N01","Housing Cell"),("N02","Selector Cell")),1):
        line=models.ProductionLine(id=f"line-ns-nashik-{index:02}",tenant_id=TENANT_ID,plant_id=NASHIK_ID,
            area_id=nashik_area.id,name=name,code=code,standard_good_rate_per_minute=1.9+index*.1,contribution_per_good_unit=104+index*8)
        nashik_lines.append(line);db.add(line)
    db.flush()
    for day_offset in range(-30,0):
        start=current_day_shift_a+timedelta(days=day_offset)
        shift=models.PlantShift(id=f"shift-ns-nashik-{start:%Y%m%d}-A",tenant_id=TENANT_ID,plant_id=NASHIK_ID,
            name="Shift A",code="A",starts_at=start,ends_at=start+timedelta(hours=8),status="completed")
        db.add(shift);db.flush()
        for line_index,line in enumerate(nashik_lines):
            code,product,target=PRODUCTS[(day_offset+line_index)%len(PRODUCTS)]
            order=models.ProductionWorkOrder(id=f"wo-ns-nashik-{abs(day_offset):02}-{line_index}",business_number=f"NSK-WO-{start:%y%m%d}-{line_index+1}",
                tenant_id=TENANT_ID,plant_id=NASHIK_ID,line_id=line.id,shift_id=shift.id,external_reference=f"SAP-NSK-{start:%y%m%d}-{line_index+1}",
                product_code=code,product_name=product,target_quantity=target,planned_start_at=start,planned_end_at=start+timedelta(hours=8),status="completed")
            db.add(order);db.flush()
            db.add(models.ProductionPlanPoint(tenant_id=TENANT_ID,plant_id=NASHIK_ID,work_order_id=order.id,recorded_at=shift.ends_at,cumulative_quantity=target,source="sap_s4hana"))
            db.add(models.ProductionActualPoint(tenant_id=TENANT_ID,plant_id=NASHIK_ID,work_order_id=order.id,recorded_at=shift.ends_at-timedelta(minutes=2),
                good_quantity=round(target*(.93+(abs(day_offset)%5)/100)),reject_quantity=3+(abs(day_offset)%4),source="mes_gateway",source_event_key=f"nashik:{order.id}"))

    if db.get(models.Uom, "KG") is None: db.add(models.Uom(id="KG", label="Kilogram"))
    if db.get(models.Uom, "EA") is None: db.add(models.Uom(id="EA", label="Each"))
    materials = [
        ("RM-ADC12-INGOT", "ADC12 aluminium alloy ingot", "KG"),
        ("RM-SGIRON-450", "SG iron grade 450/10 casting blank", "EA"),
        ("RM-17-4PH-025", "17-4PH stainless bar 25 mm", "KG"),
        ("RM-AL6061-CAST", "Aluminium 6061 end-shield casting", "EA"),
        ("CLT-CARBIDE-12", "Coated carbide insert 12 mm", "EA"),
        ("BRG-HSK63-7212", "HSK63 spindle bearing cartridge", "EA"),
    ]
    for index, (code, name, uom) in enumerate(materials, 1):
        db.add(models.Item(id=f"item-ns-{index:02}", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
            code=code, name=name, uom_id=uom, erp_item_code=code))
    product_components = {
        "GH-220":[("RM-ADC12-INGOT","ADC12 aluminium alloy ingot",1.86,"KG","Pressure die casting"),("CLT-CARBIDE-12","Coated carbide insert",.018,"EA","Finish boring")],
        "BC-410":[("RM-SGIRON-450","SG iron casting blank",1,"EA","VMC machining"),("CLT-CARBIDE-12","Coated carbide insert",.024,"EA","Bore finishing")],
        "TSF-72":[("RM-17-4PH-025","17-4PH stainless bar",.62,"KG","Hot forging and milling")],
        "MES-160":[("RM-AL6061-CAST","Aluminium 6061 casting",1,"EA","Turning and drilling")],
    }
    for index,(code,name,_target) in enumerate(PRODUCTS,1):
        product=models.ManufacturingProduct(id=f"product-ns-{index:02}",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
            code=code,name=name,customer_program={"GH-220":"Electric steering","BC-410":"Passenger vehicle braking","TSF-72":"Six-speed transmission","MES-160":"Traction motor"}[code],revision="C",status="active")
        db.add(product);db.flush()
        for component_code,component_name,quantity,uom,operation in product_components[code]:
            db.add(models.ManufacturingBOMLine(tenant_id=TENANT_ID,plant_id=CHAKAN_ID,product_id=product.id,
                component_code=component_code,component_name=component_name,quantity_per=quantity,uom=uom,
                scrap_factor=.025,operation=operation,approved=True))
    suppliers = [
        ("sup-ns-alloy-metals", "Alloy Metals India Ltd", 94, 92),
        ("sup-ns-precision-forgings", "Sahyadri Precision Forgings Pvt Ltd", 91, 84),
        ("sup-ns-cutting-tools", "Vertex Cutting Tools India Pvt Ltd", 96, 95),
        ("sup-ns-industrial-spares", "Prime Industrial Spares LLP", 89, 90),
    ]
    for index, (supplier_id, name, quality, delivery) in enumerate(suppliers, 1):
        db.add(models.Supplier(id=supplier_id, tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
            name=name, status="approved", quality_score=quality, delivery_score=delivery,
            erp_vendor_id=f"NSV-{index:05}"))
    db.flush()
    material_by_code = {row.code: row for row in db.query(models.Item).filter_by(tenant_id=TENANT_ID).all()}
    for order, material_code, qty in ((live_orders[0],"RM-ADC12-INGOT",1840),(live_orders[1],"RM-SGIRON-450",900),
                                      (live_orders[2],"RM-17-4PH-025",420),(live_orders[3],"RM-AL6061-CAST",980)):
        db.add(models.ProductionMaterialRequirement(tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
            work_order_id=order.id, item_id=material_by_code[material_code].id, material_code=material_code,
            description=material_by_code[material_code].name, required_quantity=qty,
            uom=material_by_code[material_code].uom_id, required_at=order.planned_start_at+timedelta(hours=2)))
        db.add(models.MaterialInventoryPosition(tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
            item_id=material_by_code[material_code].id, material_code=material_code,
            on_hand_quantity=qty*.74, reserved_for_other_orders=qty*.08, quality_hold_quantity=0,
            observed_at=anchor, source_system="sap_s4hana", source_reference=f"MM-STOCK-{material_code}"))
    db.add(models.ProductionSupplierCommitment(tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        work_order_id=live_orders[2].id, material_code="RM-17-4PH-025", supplier_id="sup-ns-precision-forgings",
        committed_quantity=180, committed_delivery_at=anchor+timedelta(hours=1), acknowledged=True,
        reliability_score=.84, status="open"))

    all_capabilities = ["read_production_plan","read_production_actual","read_downtime","read_inventory",
        "read_supplier_commitments","read_quality","read_inspections","read_machine_events","read_maintenance_work","read_business_events"]
    db.add(models.IntegrationConnection(id="integration-ns-factory", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        provider="factory_simulator", provider_version="1.0", name="Northstar Manufacturing Integration Bus",
        mode="simulation", status="active", capabilities=all_capabilities,
        enabled_capabilities=all_capabilities, writes_enabled=False,
        config={"stale_after_seconds":15,"sync_interval_seconds":2}, secret_ref="env://FACTORY_SIMULATOR_TOKEN",
        last_checked_at=anchor))
    db.add(models.EdgeGateway(id="edge-ns-chakan", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        name="Chakan Machining Edge Gateway", runtime_version="2.1.0",
        certificate_fingerprint="northstar-edge-chakan-sha256", config_version=1,
        config_signature="northstar-edge-config-v1", status="online", transport="https_tls",
        outbound_only=True, buffer_depth=0, last_heartbeat_at=anchor))
    for index, key in enumerate(("production_behind_plan","downtime_exceeded_threshold","rejection_rate_high","spc_control_limit_breached")):
        db.add(models.OperationalDetectorRule(id=f"detector-ns-{index+1:02}", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
            detector_key=key, name=key.replace("_"," ").title(), enabled=True,
            parameters={"current_gap_ratio":.05,"projected_gap_ratio":.05,"default_minutes":15,
                        "high_criticality_minutes":10,"maximum_rejection_rate":.04,"use_event_control_limits":True},
            severity_bands=[{"severity":"high","threshold_multiple":1.5},{"severity":"critical","threshold_multiple":2.5}],
            owner_role="maintenance_manager" if "downtime" in key else "quality_manager" if key in {"rejection_rate_high","spc_control_limit_breached"} else "production_manager",
            source_domains=["mes","cmms","qms"], effective_from=anchor-timedelta(days=90), approved_by_user_id=users["plant_manager"].id))
    db.add(models.OperationalDetectorRule(id="detector-ns-05", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        detector_key="material_readiness_risk", name="Material Readiness Risk", enabled=True,
        parameters={"minimum_coverage_ratio":1}, severity_bands=[], owner_role="purchase_executive",
        source_domains=["erp","supplier_portal"], effective_from=anchor-timedelta(days=90), approved_by_user_id=users["plant_manager"].id))

    documents = [
        ("sop-cnc-recovery","CNC spindle over-temperature recovery","sop","R3",[assets[0].id],["GH-220"],"Isolate energy, verify lubrication flow, inspect HSK63 bearing cartridge, then complete a monitored no-load cycle."),
        ("manual-vmc","VMC preventive maintenance manual","maintenance_manual","R6",[assets[1].id],[],"Lubrication, spindle vibration, drawbar force and axis backlash inspection procedure."),
        ("quality-gh220","GH-220 control plan","quality_plan","R4",[],["GH-220"],"Bore diameter, datum flatness, porosity and leak-test inspection frequencies and reaction plan."),
        ("sop-material-hold","Material identification and hold procedure","sop","R2",[],[],"Quarantine, status labelling, ERP block, traceability and authorized release process."),
    ]
    for doc_id,title,kind,revision,asset_ids,product_codes,content in documents:
        db.add(models.KnowledgeDocument(id=doc_id, tenant_id=TENANT_ID, plant_id=CHAKAN_ID,title=title,
            source="Northstar Integrated Management System",content=content,approval_state="approved",document_version=int(revision[1:]),
            role_acl=[row[0] for row in PERSONAS],plant_acl=[CHAKAN_ID],document_type=kind,revision=revision,
            effective_from=anchor-timedelta(days=60),asset_ids=asset_ids,product_codes=product_codes,
            process_codes=["machining"],approved_by_user_id=users["quality_manager"].id,approved_at=anchor-timedelta(days=60)))
    db.add(models.KnowledgeDocument(id="sop-cnc-recovery-r2",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
        title="CNC spindle over-temperature recovery",source="Northstar Integrated Management System",
        content="Superseded restart procedure.",approval_state="retired",document_version=2,
        role_acl=["maintenance_manager","maintenance_technician","admin"],plant_acl=[CHAKAN_ID],document_type="sop",revision="R2",
        effective_from=anchor-timedelta(days=400),effective_to=anchor-timedelta(days=61),retired_at=anchor-timedelta(days=60),
        asset_ids=[assets[0].id],product_codes=["GH-220"],process_codes=["machining"]))
    live_quality=models.ProductionQualityEvent(id="quality-ns-open-01",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
        work_order_id=live_orders[1].id,line_id=lines[1].id,asset_id=assets[3].id,occurred_at=anchor-timedelta(minutes=35),
        inspected_quantity=60,rejected_quantity=7,defect_code="BORE-TAPER",event_type="hold",
        material_lot_id="LOT-BC410-OPEN-07",measurement_name="bore_taper_mm",measurement_value=.034,
        lower_control_limit=0,upper_control_limit=.025,severity="high",evidence={"gauge":"AIR-GAUGE-04"},source="qms")
    db.add(live_quality);db.flush()
    db.add(models.QualityContainmentRecord(id="containment-ns-01",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
        quality_event_id=live_quality.id,containment_type="lot_and_last_good_piece",affected_lot=live_quality.material_lot_id,
        status="in_progress",owner_user_id=users["quality_inspector"].id,evidence=[{"type":"hold_tag","reference":"QH-2608-017"}]))
    db.add(models.QualityRecoveryCase(id="ncr-ns-01",business_number=f"NS-NCR-{anchor:%y%m}-017",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
        case_type="ncr",quality_event_id=live_quality.id,title="BC-410 bore taper above control limit",status="investigating",
        severity="high",owner_user_id=users["quality_manager"].id,
        problem_statement="Bore taper exceeded 0.025 mm on lot LOT-BC410-OPEN-07 during patrol inspection.",
        containment_summary="Lot held; last-good-piece boundary established; 100 percent air-gauge screening started.",
        due_at=anchor+timedelta(hours=6),evidence=[{"type":"measurement","quality_event_id":live_quality.id}]))
    for index in range(12):
        fault=models.AssetFaultEvent(id=f"fault-ns-hist-{index:02}",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
            asset_id=assets[index%len(assets)].id,work_order_id=live_orders[index%len(live_orders)].id,
            fault_code=("HYD-P-LOW" if index%2 else "TOOL-LIFE"),message=("Hydraulic pressure below permissive" if index%2 else "Tool life counter reached"),
            occurred_at=anchor-timedelta(days=index+2,hours=2),cleared_at=anchor-timedelta(days=index+2,hours=1,minutes=35),
            source="cmms",source_event_key=f"cmms-history-{index:02}")
        db.add(fault);db.flush()
        db.add(models.MaintenanceWorkRecord(id=f"mw-ns-hist-{index:02}",business_number=f"NS-MW-{anchor:%y%m}-{index+1:03}",
            tenant_id=TENANT_ID,plant_id=CHAKAN_ID,asset_id=fault.asset_id,fault_event_id=fault.id,
            external_cmms_reference=f"CMMS-WO-{260800+index}",title=("Restore hydraulic pressure" if index%2 else "Replace indexed cutting edge"),
            status="completed",owner_user_id=users["maintenance_technician"].id,spare_code=("SEAL-KIT-H32" if index%2 else "CLT-CARBIDE-12"),
            spare_available=True,started_at=fault.occurred_at+timedelta(minutes=4),completed_at=fault.cleared_at,
            resolution="Repair completed and automatic cycle verified."))
    experiment=models.ImprovementExperiment(id="experiment-ns-01",business_number="NS-EXP-2608-004",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
        title="Reduce GH-220 finish-bore tool change loss",opportunity_key="gh220-tool-change-loss",
        owner_user_id=users["production_manager"].id,status="running",
        hypothesis="Preset sister tools and offset verification will reduce median change time without increasing bore variation.",
        baseline={"median_change_minutes":18.4,"sample_size":24},intervention="Offline preset cart and first-off automatic probing",
        target={"median_change_minutes":11.5},starts_at=anchor-timedelta(days=14),ends_at=anchor+timedelta(days=14),
        result={"current_median_minutes":12.7,"sample_size":11},statistical_confidence=.82,
        evidence=[{"type":"downtime_events","count":11}])
    db.add(experiment);db.flush()
    db.add(models.ImprovementBenefitMeasurement(tenant_id=TENANT_ID,plant_id=CHAKAN_ID,experiment_id=experiment.id,
        measured_at=anchor-timedelta(days=1),metric="changeover_minutes",baseline_value=18.4,observed_value=12.7,
        annualized_value=1840000,currency="INR",confidence_state="measured",calculation={"annual_changeovers":420}))
    db.add(models.BestPracticeTransfer(id="transfer-ns-01",business_number="NS-BPT-2608-002",tenant_id=TENANT_ID,plant_id=NASHIK_ID,
        title="Transfer offline tool preset method to Nashik",source_plant_id=CHAKAN_ID,target_plant_id=NASHIK_ID,
        source_experiment_id=experiment.id,status="proposed",hypothesis="The fixture and probing sequence is applicable to Nashik VMC cells.",
        applicability_context={"machine_family":"VMC","product_family":"machined_housings"},
        expected_benefit={"changeover_minutes_reduction":5.0,"annualized_value_inr":920000},owner_user_id=users["corporate_operations_director"].id))
    db.add(models.ShiftBriefing(id="briefing-ns-live-start",tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
        shift_id=active_shift.id,briefing_type="start",status="published",title=f"Shift {active_shift.code} Chakan operating briefing",
        summary="Protect BC-410 containment, maintain GH-220 trajectory and confirm TSF-72 material cover.",
        metrics={"planned_units":sum(row.target_quantity for row in live_orders),"active_lines":4},
        priorities=[{"title":"Complete BC-410 containment","entity_id":"ncr-ns-01"},{"title":"Confirm TSF-72 material cover","entity_id":live_orders[2].id}],
        losses=[],carry_over=[],evidence=[{"type":"shift","id":active_shift.id}],generated_at=anchor,
        verified_by_user_id=users["production_supervisor"].id,published_at=anchor+timedelta(minutes=2)))
    for role,title,body in (("quality_manager","BC-410 containment remains active","Lot screening is in progress on Final Inspection."),
                            ("purchase_executive","TSF-72 material confirmation due","Supplier commitment covers only part of required 17-4PH bar."),
                            ("maintenance_manager","Preventive work due on VMC-02-01","Spindle vibration route is due before Shift C.")):
        recipient=users[role]
        db.add(models.Notification(tenant_id=TENANT_ID,plant_id=CHAKAN_ID,user_id=recipient.id,category="operational",
            severity="high",title=title,body=body,status="unread",navigation_target="/v2/home",dedupe_key=f"northstar-seed:{role}"))

    all_line_ids = [line.id for line in lines]
    all_asset_ids = [asset.id for asset in assets]
    for idx, (role, *_rest) in enumerate(PERSONAS, 1):
        membership = db.get(models.WorkspaceMembership, f"mem-ns-{idx:02}")
        line_ids = all_line_ids if role not in {"production_operator", "production_supervisor"} else all_line_ids[:1 if role == "production_operator" else 2]
        authorities = {
            "admin": ["simulation.control", "scope.manage", "integration.manage"],
            "plant_manager": ["deviation.assign", "recovery.approve"],
            "production_manager": ["deviation.assign", "work_order.sequence"],
            "production_supervisor": ["deviation.acknowledge", "recovery.start"],
            "production_operator": ["production.record", "quality.hold"],
            "maintenance_manager": ["maintenance.assign", "maintenance.complete"],
            "maintenance_technician": ["maintenance.acknowledge", "maintenance.progress"],
            "quality_manager": ["quality.release", "capa.verify"], "quality_inspector": ["quality.inspect", "quality.hold"],
            "purchase_manager": ["purchase.approve"], "purchase_executive": ["supplier.followup"],
            "store_manager": ["inventory.stage", "receipt.accept"], "gate_operator": ["gate.record"],
            "corporate_operations_director": ["practice.transfer"],
        }.get(role, [])
        db.add(models.OperationalScope(tenant_id=TENANT_ID, membership_id=membership.id,
            plant_ids=membership.plant_ids, area_ids=[a.id for a in areas.values()], line_ids=line_ids,
            asset_ids=all_asset_ids if role not in {"production_operator", "production_supervisor"} else [a.id for a in assets if a.line_id in line_ids],
            authorities=authorities, financial_visibility=role in {"admin", "plant_manager", "purchase_manager", "corporate_operations_director"}))
    db.add(models.OperationalSetupProfile(id="setup-ns-chakan", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        activation_stage="live", primary_use_case="production_recovery",
        enabled_data_domains=["production", "machines", "quality", "maintenance", "inventory", "suppliers"],
        production_calendar={"timezone": "Asia/Kolkata", "shifts": ["A", "B", "C"], "scenario_clock": True},
        kpi_targets={"plan_attainment": .96, "rejection_rate": .025, "downtime_minutes": 12},
        loss_categories=[], escalation_rules=[], value_formulas=[], action_policies=[], completed_stages=["plant", "data", "use_case", "live"]))
    db.flush()
    return tenant
