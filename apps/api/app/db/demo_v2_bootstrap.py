from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.operations import service as operational_v2
from app.db import models


def bootstrap_apex_v2(db: Session, tenant: models.Tenant, reference: datetime | None = None) -> bool:
    """Add the operational demo to a legacy Apex workspace without touching others."""
    if tenant.workspace_kind != "demo":
        return False
    plant = db.query(models.Plant).filter_by(tenant_id=tenant.id).order_by(models.Plant.id).first()
    manager = db.query(models.User).filter_by(tenant_id=tenant.id, role="plant_manager").first()
    if not plant or not manager or db.query(models.ProductionWorkOrder).filter_by(tenant_id=tenant.id).count():
        return False
    now = (reference or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    start, end = now - timedelta(hours=4), now + timedelta(hours=4)
    area = models.PlantArea(id="area-machining", tenant_id=tenant.id, plant_id=plant.id,
                            name="Machining", code="MACHINING")
    db.add(area)
    lines = []
    for index, (code, rate, contribution) in enumerate((("L1", 2.1, 78), ("L2", 2.0, 82), ("L3", 1.95, 91), ("L4", 2.2, 76)), 1):
        line = models.ProductionLine(id=f"line-l{index}", tenant_id=tenant.id, plant_id=plant.id,
            area_id=area.id, name=f"Line {index}", code=code,
            standard_good_rate_per_minute=rate, contribution_per_good_unit=contribution)
        lines.append(line); db.add(line)
    db.flush()
    asset = models.PlantAsset(id="asset-cnc-04", tenant_id=tenant.id, plant_id=plant.id,
        area_id=area.id, line_id="line-l3", name="CNC-04", code="CNC-04",
        asset_type="cnc", criticality="high")
    shift = models.PlantShift(id="shift-b-2026-08-12", tenant_id=tenant.id, plant_id=plant.id,
        name="Shift B", code="B", starts_at=start, ends_at=end, status="active")
    db.add_all([asset, shift]); db.flush()
    targets, actuals = (930, 900, 930, 940), (505, 474, 381, 526)
    orders = []
    for index, line in enumerate(lines):
        order = models.ProductionWorkOrder(id=f"wo-v2-l{index+1}", business_number=f"WO-48{index+1}",
            tenant_id=tenant.id, plant_id=plant.id, line_id=line.id, shift_id=shift.id,
            external_reference=f"ERP-WO-48{index+1}", product_code=f"AX-10{index+7}",
            product_name=f"Precision assembly AX-10{index+7}", target_quantity=targets[index],
            planned_start_at=start, planned_end_at=end, status="in_progress")
        orders.append(order); db.add(order); db.flush()
        for hour in range(9):
            db.add(models.ProductionPlanPoint(tenant_id=tenant.id, plant_id=plant.id,
                work_order_id=order.id, recorded_at=start + timedelta(hours=hour),
                cumulative_quantity=round(targets[index] * hour / 8, 2), source="seed"))
        for hour in range(1, 5):
            db.add(models.ProductionActualPoint(tenant_id=tenant.id, plant_id=plant.id,
                work_order_id=order.id, recorded_at=start + timedelta(hours=hour),
                good_quantity=round(actuals[index] * hour / 4, 2),
                reject_quantity=5 if index == 2 else 2, source="seed",
                source_event_key=f"bootstrap:{line.code}:{hour}"))
    downtime = models.ProductionDowntimeEvent(id="down-cnc04-001", tenant_id=tenant.id,
        plant_id=plant.id, work_order_id=orders[2].id, line_id=lines[2].id, asset_id=asset.id,
        started_at=start + timedelta(hours=3, minutes=17), category="breakdown",
        reason="Bearing temperature trip", planned=False)
    quality = models.ProductionQualityEvent(id="quality-l2-001", tenant_id=tenant.id,
        plant_id=plant.id, work_order_id=orders[1].id, line_id=lines[1].id,
        occurred_at=start + timedelta(hours=3, minutes=45), event_type="inspection",
        inspected_quantity=80, rejected_quantity=11, defect_code="DIMENSIONAL",
        material_lot_id="LOT-QL-284", source="seed")
    db.add_all([downtime, quality]); db.flush()
    operational_v2.evaluate_production_behind_plan(db, orders[2], now)
    operational_v2.evaluate_downtime_threshold(db, downtime, now)
    operational_v2.evaluate_rejection_rate(db, quality)
    db.add(models.OperationalSetupProfile(id="setup-pune-v2", tenant_id=tenant.id, plant_id=plant.id,
        activation_stage="use_case", primary_use_case="production_loss",
        enabled_data_domains=["production", "machines", "quality", "maintenance"],
        production_calendar={"timezone": plant.timezone},
        kpi_targets={"plan_attainment": .95, "rejection_rate": .04, "downtime_minutes": 15},
        loss_categories=[], escalation_rules=[], value_formulas=[], action_policies=[],
        completed_stages=["plant", "data", "use_case"]))
    db.add(models.Notification(tenant_id=tenant.id, plant_id=plant.id, user_id=manager.id,
        category="critical", severity="critical", title="CNC-04 recovery requires attention",
        body="Bearing temperature downtime is constraining Line 3 output.", status="unread",
        linked_entity_type="plant_asset", linked_entity_id=asset.id,
        navigation_target="/v2/operations/lines/line-l3", dedupe_key="bootstrap:v2:cnc04"))
    return True
