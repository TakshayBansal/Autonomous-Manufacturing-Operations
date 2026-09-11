"""Phase 1 planning input assembly and deterministic demand normalization."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.models import ExternalEntityReference, PlatformBOM, PlatformBOMItem, PlatformProduct
from app.scm import models
from app.scm.engine import ENGINE_VERSION


DEFAULT_PRECEDENCE = ["CUSTOMER_ORDER", "WORK_ORDER", "PRODUCTION_PLAN", "INDENT", "FORECAST"]


def canonical_material_id(db: Session, tenant_id: str, scm_material_id: str) -> str | None:
    return db.query(ExternalEntityReference.canonical_entity_id).filter_by(
        tenant_id=tenant_id, source_system="legacy:scm", entity_type="material",
        external_id=scm_material_id, canonical_entity_type="material").scalar()


def scm_material_id(db: Session, tenant_id: str, canonical_id: str) -> str | None:
    return db.query(ExternalEntityReference.external_id).filter_by(
        tenant_id=tenant_id, source_system="legacy:scm", entity_type="material",
        canonical_entity_id=canonical_id, canonical_entity_type="material").scalar()


def ensure_profile(db: Session, user: core.User) -> models.SCMPlanningProfile:
    row = db.query(models.SCMPlanningProfile).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, is_active=True).first()
    if row:
        return row
    plant = db.get(core.Plant, user.plant_id)
    row = models.SCMPlanningProfile(tenant_id=user.tenant_id, plant_id=user.plant_id,
        name="Default 210-day plan", planning_horizon_days=210,
        timezone=plant.timezone if plant else "UTC", currency=plant.currency if plant else "USD",
        demand_precedence=DEFAULT_PRECEDENCE)
    db.add(row)
    db.flush()
    return row


def latest_published_demand_plan(db: Session, tenant_id: str, plant_id: str) -> models.SCMDemandPlan | None:
    return db.query(models.SCMDemandPlan).filter_by(tenant_id=tenant_id, plant_id=plant_id,
        status="PUBLISHED").order_by(models.SCMDemandPlan.published_at.desc()).first()


def normalize_buckets(rows: list[models.SCMDemandBucket], precedence: list[str]) -> list[dict[str, Any]]:
    """Select the highest-precedence overlapping source for each target/day."""
    rank = {kind: index for index, kind in enumerate(precedence)}
    grouped: dict[tuple, list[models.SCMDemandBucket]] = defaultdict(list)
    for row in rows:
        overlap_key = (row.lineage or {}).get("overlap_key")
        key = (row.bucket_date, row.product_id, row.material_id, row.work_order_id,
               row.customer_id, overlap_key or "default")
        grouped[key].append(row)
    selected = []
    for candidates in grouped.values():
        winner = min(candidates, key=lambda row: (rank.get(row.demand_type, len(rank)), row.priority, row.id))
        selected.append({"id": winner.id, "date": winner.bucket_date.isoformat(),
            "quantity": str(winner.quantity), "demand_type": winner.demand_type,
            "product_id": winner.product_id, "material_id": winner.material_id,
            "work_order_id": winner.work_order_id, "customer_id": winner.customer_id,
            "oem_reference": winner.oem_reference, "source_reference": winner.source_reference,
            "provenance_id": winner.provenance_id, "lineage": winner.lineage,
            "suppressed_source_ids": [row.id for row in candidates if row.id != winner.id]})
    return sorted(selected, key=lambda item: (item["date"], item["product_id"] or item["material_id"] or "", item["id"]))


def _effective_bom(db: Session, tenant_id: str, plant_id: str, product_id: str, at: date) -> PlatformBOM | None:
    return db.query(PlatformBOM).filter(PlatformBOM.tenant_id == tenant_id,
        PlatformBOM.plant_id == plant_id, PlatformBOM.product_id == product_id,
        PlatformBOM.status == "ACTIVE", PlatformBOM.effective_from <= at,
        (PlatformBOM.effective_to.is_(None) | (PlatformBOM.effective_to >= at))).order_by(
        PlatformBOM.effective_from.desc(), PlatformBOM.revision.desc()).first()


def explode_product_demand(db: Session, *, tenant_id: str, plant_id: str, product_id: str,
                           quantity: Decimal, required_date: date, source_id: str,
                           path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    if product_id in path:
        raise ValueError(f"Canonical BOM cycle: {' -> '.join((*path, product_id))}")
    bom = _effective_bom(db, tenant_id, plant_id, product_id, required_date)
    if not bom:
        raise ValueError(f"No effective canonical BOM for product {product_id} on {required_date}")
    results: list[dict[str, Any]] = []
    for item in db.query(PlatformBOMItem).filter_by(bom_id=bom.id).order_by(PlatformBOMItem.line_number).all():
        required = quantity * Decimal(str(item.quantity)) * (Decimal("1") + Decimal(str(item.scrap_factor or 0)))
        lineage = {"source_demand_id": source_id, "product_id": product_id, "bom_id": bom.id,
                   "bom_item_id": item.id, "path": [*path, product_id, item.component_id]}
        if item.component_entity_type == "product":
            results.extend(explode_product_demand(db, tenant_id=tenant_id, plant_id=plant_id,
                product_id=item.component_id, quantity=required, required_date=required_date,
                source_id=source_id, path=(*path, product_id)))
        elif item.component_entity_type == "material":
            results.append({"canonical_material_id": item.component_id, "quantity": required,
                            "date": required_date.isoformat(), "lineage": lineage})
    return results


def _legacy_demands(db: Session, tenant_id: str, plant_id: str, start: date, end: date) -> list[dict]:
    requirements = db.query(models.SCMMaterialRequirement).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).filter(
        models.SCMMaterialRequirement.required_date.between(start, end)).all()
    output = []
    for row in requirements:
        finished = db.get(models.SCMMaterial, row.finished_good_id) if row.finished_good_id else None
        finished_code = finished.material_code if finished else (row.lineage or {}).get("finished_good_code")
        product = db.query(PlatformProduct).filter_by(tenant_id=tenant_id,
            code=finished_code).first() if finished_code else None
        order_reference = f"WO-{row.external_id.split('-', 1)[0]}" if row.external_id else None
        work_order = db.query(core.ProductionWorkOrder).filter_by(tenant_id=tenant_id,
            plant_id=plant_id, external_reference=order_reference).first() if order_reference else None
        lineage = {**(row.lineage or {})}
        if product:
            lineage["product_id"] = product.id
        if finished_code:
            lineage["finished_good_code"] = finished_code
        output.append({"id": row.id, "date": row.required_date.isoformat(), "quantity": str(row.quantity),
            "demand_type": row.requirement_type, "canonical_material_id": canonical_material_id(db, tenant_id, row.material_id),
            "scm_material_id": row.material_id, "work_order_id": work_order.id if work_order else lineage.get("work_order_id"),
            "customer_id": row.customer_id, "source_reference": row.external_id, "lineage": lineage,
            "suppressed_source_ids": []})
    if requirements:
        return output
    forecasts = db.query(models.SCMDemandForecast).filter_by(tenant_id=tenant_id, plant_id=plant_id).filter(
        models.SCMDemandForecast.bucket_start.between(start, end)).all()
    return [{"id": row.id, "date": row.bucket_start.isoformat(), "quantity": str(row.quantity),
        "demand_type": "FORECAST", "canonical_material_id": canonical_material_id(db, tenant_id, row.material_id),
        "scm_material_id": row.material_id, "customer_id": row.customer_id,
        "source_reference": row.source_record_id, "lineage": {}, "suppressed_source_ids": []} for row in forecasts]


def _snapshot_json(value):
    if isinstance(value, Decimal):
        normalized = format(value.normalize(), "f")
        return normalized if "." in normalized else f"{normalized}.0"
    return str(value)


def assemble_input_snapshot(db: Session, run: models.SCMPlanningRun,
                            profile: models.SCMPlanningProfile,
                            demand_plan: models.SCMDemandPlan | None) -> models.SCMPlanningInputSnapshot:
    existing = db.query(models.SCMPlanningInputSnapshot).filter_by(planning_run_id=run.id).first()
    if existing:
        return existing
    scenario = db.get(models.SCMPlanningScenario, run.scenario_id)
    baseline_snapshot = None
    if scenario and scenario.scenario_type == "WHAT_IF" and scenario.baseline_run_id:
        baseline_snapshot = db.query(models.SCMPlanningInputSnapshot).filter_by(
            planning_run_id=scenario.baseline_run_id).first()
    if baseline_snapshot:
        payload = json.loads(json.dumps(baseline_snapshot.payload))
        payload.update({"as_of_at": run.as_of_at.isoformat(),
            "horizon_start": run.horizon_start.isoformat(), "horizon_end": run.horizon_end.isoformat(),
            "scenario_id": scenario.id, "baseline_snapshot_id": baseline_snapshot.id})
        for override in db.query(models.SCMScenarioOverride).filter_by(scenario_id=scenario.id).all():
            material = next((row for row in payload["materials"] if row["scm_material_id"] == override.material_id), None)
            if not material:
                continue
            values = override.values or {}
            if override.override_type == "INVENTORY":
                material["opening_available"] = str(values.get("quantity", values.get("opening_available", 0)))
            elif override.override_type == "SAFETY_STOCK":
                material["policy"]["safety_stock_qty"] = str(values.get("quantity", 0))
            elif override.override_type == "DEMAND":
                factor = Decimal(str(values.get("factor", 1)))
                adjustment = Decimal(str(values.get("quantity_delta", 0)))
                for demand in material["demands"]:
                    demand["quantity"] = str(Decimal(demand["quantity"]) * factor + adjustment)
            elif override.override_type in {"SUPPLY_DATE", "SUPPLY_QUANTITY"}:
                supplies = [row for row in material["supplies"] if not override.source_entity_id
                            or row.get("canonical_purchase_order_id") == override.source_entity_id
                            or row.get("id") == override.source_entity_id]
                for supply in supplies:
                    if override.override_type == "SUPPLY_DATE" and values.get("date"):
                        supply["date"] = values["date"]
                    if override.override_type == "SUPPLY_QUANTITY":
                        supply["quantity"] = str(values.get("quantity", supply["quantity"]))
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_snapshot_json)
        payload = json.loads(encoded)
        snapshot = models.SCMPlanningInputSnapshot(tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, algorithm_version=ENGINE_VERSION,
            payload_hash=hashlib.sha256(encoded.encode()).hexdigest(), payload=payload,
            source_freshness=baseline_snapshot.source_freshness, captured_at=datetime.now(timezone.utc),
            correlation_id=run.correlation_id)
        db.add(snapshot)
        db.flush()
        run.input_snapshot_id = snapshot.id
        return snapshot
    if demand_plan:
        rows = db.query(models.SCMDemandBucket).filter_by(demand_plan_id=demand_plan.id).filter(
            models.SCMDemandBucket.bucket_date.between(run.horizon_start, run.horizon_end)).all()
        normalized = normalize_buckets(rows, profile.demand_precedence or DEFAULT_PRECEDENCE)
        demands: list[dict] = []
        for row in normalized:
            if row["product_id"]:
                exploded = explode_product_demand(db, tenant_id=run.tenant_id, plant_id=run.plant_id,
                    product_id=row["product_id"], quantity=Decimal(row["quantity"]),
                    required_date=date.fromisoformat(row["date"]), source_id=row["id"])
                for item in exploded:
                    item.update({"id": f"{row['id']}:{item['canonical_material_id']}",
                        "demand_type": row["demand_type"], "work_order_id": row["work_order_id"],
                        "customer_id": row["customer_id"], "source_reference": row["source_reference"],
                        "suppressed_source_ids": row["suppressed_source_ids"]})
                    item["scm_material_id"] = scm_material_id(db, run.tenant_id, item["canonical_material_id"])
                    demands.append(item)
            else:
                row["canonical_material_id"] = row["material_id"]
                row["scm_material_id"] = scm_material_id(db, run.tenant_id, row["material_id"])
                demands.append(row)
        # A published platform demand plan remains authoritative for materials
        # it covers. File/ERP requirements still supply demand for newly
        # onboarded materials that are not yet represented in that plan.
        covered_materials = {row.get("scm_material_id") for row in demands if row.get("scm_material_id")}
        demands.extend(row for row in _legacy_demands(
            db, run.tenant_id, run.plant_id, run.horizon_start, run.horizon_end)
            if row.get("scm_material_id") not in covered_materials)
    else:
        demands = _legacy_demands(db, run.tenant_id, run.plant_id, run.horizon_start, run.horizon_end)
    demand_by_material: dict[str, list[dict]] = defaultdict(list)
    for row in demands:
        if row.get("scm_material_id"):
            demand_by_material[row["scm_material_id"]].append(row)
    material_rows = db.query(models.SCMMaterialPlant).filter_by(
        tenant_id=run.tenant_id, plant_id=run.plant_id, active=True).all()
    materials = []
    freshness: dict[str, Any] = {}
    for link in material_rows:
        canonical_id = canonical_material_id(db, run.tenant_id, link.material_id)
        inventory = db.query(models.SCMInventorySnapshot).filter_by(tenant_id=run.tenant_id,
            plant_id=run.plant_id, material_id=link.material_id).filter(
            models.SCMInventorySnapshot.snapshot_at <= run.as_of_at).order_by(
            models.SCMInventorySnapshot.snapshot_at.desc()).first()
        policy = db.query(models.SCMMaterialPlantPolicy).filter_by(tenant_id=run.tenant_id,
            plant_id=run.plant_id, material_id=link.material_id, active=True).first()
        supplies = []
        schedule_rows = db.query(models.SCMSupplyScheduleLine, models.SCMSupplyOrder).join(
            models.SCMSupplyOrder, models.SCMSupplyOrder.id == models.SCMSupplyScheduleLine.supply_order_id).filter(
            models.SCMSupplyOrder.tenant_id == run.tenant_id, models.SCMSupplyOrder.plant_id == run.plant_id,
            models.SCMSupplyOrder.material_id == link.material_id,
            models.SCMSupplyScheduleLine.status.in_(["OPEN", "PARTIAL", "CONFIRMED"])).all()
        for schedule, order in schedule_rows:
            supplier_rule = db.query(models.SCMMaterialSupplier).filter_by(tenant_id=run.tenant_id,
                plant_id=run.plant_id, material_id=link.material_id, supplier_id=order.supplier_id).first() if order.supplier_id else None
            supplies.append({"id": schedule.id, "date": schedule.current_due_date.isoformat(), "source_type": order.supply_type,
                "quantity": str(max(schedule.scheduled_qty - schedule.received_qty, Decimal("0"))),
                "event_type": order.supply_type, "firmness": order.firmness,
                "status": schedule.status, "order_id": order.id, "order_number": order.order_number,
                "canonical_purchase_order_id": order.source_entity_id if order.source_entity_type == "purchase_order" else None,
                "supplier_id": order.supplier_id, "cancellation_allowed": bool(supplier_rule and supplier_rule.cancellation_allowed),
                "pushout_allowed": bool(supplier_rule and supplier_rule.pushout_allowed),
                "expedite_allowed": bool(not supplier_rule or supplier_rule.expedite_allowed)})
        observed_at = inventory.snapshot_at if inventory else None
        run_as_of = run.as_of_at if run.as_of_at.tzinfo else run.as_of_at.replace(tzinfo=timezone.utc)
        observed_utc = observed_at if observed_at and observed_at.tzinfo else (
            observed_at.replace(tzinfo=timezone.utc) if observed_at else None)
        stale = observed_utc is None or (run_as_of - observed_utc).total_seconds() > 90000
        materials.append({"material_id": link.material_id, "scm_material_id": link.material_id, "canonical_material_id": canonical_id,
            "opening_available": str(inventory.available_qty if inventory and inventory.available_qty is not None else 0),
            "inventory_snapshot_id": inventory.id if inventory else None,
            "inventory_observed_at": observed_at.isoformat() if observed_at else None,
            "stale": stale, "demands": demand_by_material.get(link.material_id, []), "supplies": supplies,
            "policy": {"safety_stock_qty": str(policy.safety_stock_qty or 0) if policy else "0",
                "minimum_order_qty": str(policy.minimum_order_qty or 0) if policy else "0",
                "order_multiple": str(policy.order_multiple or 1) if policy else "1",
                "maximum_coverage_days": policy.maximum_coverage_days if policy else None}})
    # Approved operational overrides are a transparent planning input layer;
    # source records remain untouched and the snapshot preserves the reason.
    adjustments = db.query(models.SCMPlanningAdjustment).filter_by(
        tenant_id=run.tenant_id, plant_id=run.plant_id, approval_state="APPROVED").filter(
        (models.SCMPlanningAdjustment.expires_at.is_(None)) |
        (models.SCMPlanningAdjustment.expires_at >= run.as_of_at)).all()
    for adjustment in adjustments:
        material = next((row for row in materials if row["scm_material_id"] == adjustment.material_id), None)
        if not material:
            continue
        values = adjustment.values or {}
        if adjustment.adjustment_type == "SAFETY_STOCK":
            material["policy"]["safety_stock_qty"] = str(values.get("quantity", 0))
        elif adjustment.adjustment_type == "DEMAND":
            factor = Decimal(str(values.get("factor", 1)))
            for demand in material["demands"]:
                demand["quantity"] = str(Decimal(demand["quantity"]) * factor)
        elif adjustment.adjustment_type in {"EXPECTED_RECEIPT_DATE", "SUPPLIER_COMMITMENT"}:
            for supply in material["supplies"]:
                if not values.get("source_entity_id") or values["source_entity_id"] in {
                        supply["id"], supply.get("canonical_purchase_order_id")}:
                    if values.get("date"):
                        supply["date"] = values["date"]
        material.setdefault("manual_overrides", []).append({"id": adjustment.id,
            "type": adjustment.adjustment_type, "reason": adjustment.reason,
            "values": values, "created_by_user_id": adjustment.created_by_user_id})
    # First-class manual entries supersede source fields without mutating the
    # imported facts. Every applied value is captured in the immutable input
    # snapshot so a run remains exactly reproducible.
    manual_entries = db.query(models.SCMManualDataEntry).filter_by(
        tenant_id=run.tenant_id, plant_id=run.plant_id, status="ACTIVE").filter(
        models.SCMManualDataEntry.effective_at <= run.as_of_at,
        (models.SCMManualDataEntry.expires_at.is_(None)) |
        (models.SCMManualDataEntry.expires_at >= run.as_of_at)).order_by(
        models.SCMManualDataEntry.created_at).all()
    for entry in manual_entries:
        material = next((row for row in materials if row["scm_material_id"] == entry.material_id), None)
        if not material:
            continue
        values = entry.values or {}
        if entry.entry_type == "INVENTORY_CORRECTION_RECORDED":
            material["opening_available"] = str(values.get("available_qty", material["opening_available"]))
            material["inventory_observed_at"] = entry.effective_at.isoformat()
            material["stale"] = False
        elif entry.entry_type == "EXPECTED_DELIVERY_CREATED":
            material["supplies"].append({"id": entry.id, "date": values["delivery_date"],
                "quantity": str(values["quantity"]), "event_type": "MANUAL_EXPECTED_DELIVERY", "source_type": "MANUAL_EXPECTED_DELIVERY",
                "firmness": values.get("firmness", "FIRM"), "status": values.get("status", "CONFIRMED"),
                "order_id": entry.id, "order_number": values.get("order_number", f"MANUAL-{entry.id[:8]}"),
                "supplier_id": entry.supplier_id, "canonical_purchase_order_id": None,
                "manual_entry_id": entry.id})
        elif entry.entry_type in {"SUPPLY_SCHEDULE_CHANGED", "SUPPLY_QUANTITY_CHANGED"}:
            for supply in material["supplies"]:
                if entry.target_entity_id in {supply.get("id"), supply.get("canonical_purchase_order_id")}:
                    if values.get("delivery_date"):
                        supply["date"] = values["delivery_date"]
                    if values.get("quantity") is not None:
                        supply["quantity"] = str(values["quantity"])
                    supply["manual_entry_id"] = entry.id
        elif entry.entry_type == "GOODS_RECEIPT_RECORDED":
            receipt_date = date.fromisoformat(values["receipt_date"])
            if receipt_date <= run.horizon_start:
                material["opening_available"] = str(Decimal(material["opening_available"]) + Decimal(str(values["quantity"])))
            else:
                material["supplies"].append({"id": entry.id, "date": values["receipt_date"],
                    "quantity": str(values["quantity"]), "event_type": "GOODS_RECEIPT",
                    "firmness": "FIRM", "status": "RECEIVED",
                    "canonical_purchase_order_id": None, "manual_entry_id": entry.id})
        elif entry.entry_type == "DEMAND_CREATED":
            material["demands"].append({"id": entry.id, "date": values["required_date"],
                "quantity": str(values["quantity"]), "demand_type": values.get("demand_type", "INDENT"),
                "material_id": entry.canonical_material_id, "source_reference": entry.id,
                "lineage": {"manual_entry_id": entry.id}, "suppressed_source_ids": []})
        elif entry.entry_type == "DEMAND_CHANGED":
            for demand in material["demands"]:
                if demand.get("id") == entry.target_entity_id or demand.get("source_reference") == entry.target_entity_id:
                    demand["quantity"] = str(values["quantity"])
                    if values.get("required_date"):
                        demand["date"] = values["required_date"]
                    demand.setdefault("lineage", {})["manual_entry_id"] = entry.id
        material.setdefault("manual_entries", []).append({"id": entry.id, "type": entry.entry_type,
            "reason": entry.reason, "values": values, "source": entry.source_authority})
    # Apply horizon eligibility after overlays. This is essential when a manual
    # schedule change pulls a previously out-of-horizon PO into the active plan.
    for material in materials:
        material["supplies"] = [supply for supply in material["supplies"]
            if run.horizon_start <= date.fromisoformat(str(supply["date"])) <= run.horizon_end]
    for row in db.query(models.SCMDataSourceState).filter_by(tenant_id=run.tenant_id, plant_id=run.plant_id).all():
        freshness[row.source_key] = {"status": row.status,
            "last_successful_import": row.last_successful_import.isoformat() if row.last_successful_import else None,
            "stale_after_seconds": row.stale_after_seconds}
    payload = {"version": "scm-input@1", "tenant_id": run.tenant_id, "plant_id": run.plant_id,
        "as_of_at": run.as_of_at.isoformat(), "horizon_start": run.horizon_start.isoformat(),
        "horizon_end": run.horizon_end.isoformat(), "planning_profile_id": profile.id,
        "demand_plan_id": demand_plan.id if demand_plan else None, "materials": materials}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_snapshot_json)
    # PostgreSQL JSON serializers do not accept Decimal/date objects. The same
    # canonical representation used for the reproducibility hash is therefore
    # also the value persisted in the snapshot.
    payload = json.loads(encoded)
    snapshot = models.SCMPlanningInputSnapshot(tenant_id=run.tenant_id, plant_id=run.plant_id,
        planning_run_id=run.id, algorithm_version=ENGINE_VERSION,
        payload_hash=hashlib.sha256(encoded.encode()).hexdigest(), payload=payload,
        source_freshness=freshness, captured_at=datetime.now(timezone.utc), correlation_id=run.correlation_id)
    db.add(snapshot)
    db.flush()
    run.input_snapshot_id = snapshot.id
    return snapshot
