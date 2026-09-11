from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import excel_connector
from app.db import models as core_models
from app.scm import models


SCHEMAS: dict[str, dict[str, Any]] = {
    "Materials": {"entity": "scm_material", "required": ("external_id", "material_code", "description", "material_type", "base_uom")},
    "MaterialPlantPolicies": {"entity": "scm_material_plant_policy", "required": ("external_id", "material_code")},
    "MaterialSuppliers": {"entity": "scm_material_supplier", "required": ("external_id", "material_code", "supplier_code")},
    "Customers": {"entity": "scm_customer", "required": ("external_id", "customer_code", "name")},
    "CustomerUsage": {"entity": "scm_customer_usage", "required": ("external_id", "finished_good_code", "customer_code")},
    "BOMs": {"entity": "scm_bom", "required": ("external_id", "bom_code", "revision", "parent_material_code", "effective_from")},
    "BOMLines": {"entity": "scm_bom_line", "required": ("external_id", "bom_code", "revision", "line_number", "component_material_code", "quantity_per", "uom")},
    "Inventory": {"entity": "scm_inventory_snapshot", "required": ("external_id", "material_code", "snapshot_at", "on_hand_qty", "available_qty", "uom")},
    "Forecasts": {"entity": "scm_demand_forecast", "required": ("external_id", "material_code", "forecast_version", "bucket_start", "bucket_end", "quantity", "uom")},
    "Requirements": {"entity": "scm_material_requirement", "required": ("external_id", "material_code", "required_date", "quantity", "uom", "requirement_type")},
    "SupplyOrders": {"entity": "scm_supply_order", "required": ("external_id", "material_code", "supply_type", "order_number", "line_number", "ordered_qty", "received_qty", "uom", "status")},
    "SupplySchedules": {"entity": "scm_supply_schedule", "required": ("external_id", "supply_order_external_id", "schedule_line_number", "scheduled_qty", "received_qty", "original_due_date", "current_due_date", "status")},
    "GoodsReceipts": {"entity": "scm_goods_receipt", "required": ("external_id", "material_code", "receipt_date", "quantity", "uom")},
}

ENTITY_ORDER = {name: index for index, name in enumerate((
    "scm_material", "scm_customer", "scm_material_plant_policy", "scm_material_supplier",
    "scm_customer_usage", "scm_bom", "scm_bom_line", "scm_inventory_snapshot",
    "scm_demand_forecast", "scm_material_requirement", "scm_supply_order",
    "scm_supply_schedule", "scm_goods_receipt",
))}


def _hash(payload: Any) -> str:
    return hashlib.sha256(str(payload).encode()).hexdigest()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _decimal(value: Any, field: str, messages: list[dict[str, Any]], *, positive: bool = False) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError):
        messages.append({"field": field, "code": "invalid_number", "message": f"{field} must be numeric"})
        return None
    if positive and parsed <= 0:
        messages.append({"field": field, "code": "must_be_positive", "message": f"{field} must be positive"})
    return parsed


def _date(value: Any, field: str, messages: list[dict[str, Any]]) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_clean(value))
    except ValueError:
        messages.append({"field": field, "code": "invalid_date", "message": f"{field} must use YYYY-MM-DD"})
        return None


def _datetime(value: Any, field: str, messages: list[dict[str, Any]]) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(_clean(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        messages.append({"field": field, "code": "invalid_datetime", "message": f"{field} must be an ISO-8601 timestamp"})
        return None


def _apply_mapping(sheet: str, row: dict[str, Any], mappings: dict[str, dict[str, str]]) -> dict[str, Any]:
    if sheet not in mappings:
        return row
    return {target: row.get(excel_connector._clean_header(source)) for target, source in mappings[sheet].items()}


def ensure_file_connection(db: Session, user: core_models.User) -> core_models.IntegrationConnection:
    row = db.query(core_models.IntegrationConnection).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, provider="excel_csv", name="SCM File Upload"
    ).first()
    if row:
        return row
    row = core_models.IntegrationConnection(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        provider="excel_csv", provider_version="1.0", name="SCM File Upload",
        mode="import_only", status="configured",
        capabilities=["read_materials", "read_boms", "read_inventory", "read_forecasts", "read_requirements", "read_purchase_orders", "read_receipts"],
        enabled_capabilities=["read_materials", "read_boms", "read_inventory", "read_forecasts", "read_requirements", "read_purchase_orders", "read_receipts"],
        writes_enabled=False, config={"scm": True, "stale_after_seconds": 90000},
    )
    db.add(row)
    db.flush()
    return row


def preview(
    db: Session,
    user: core_models.User,
    filename: str,
    content: bytes,
    mappings: dict[str, dict[str, str]] | None = None,
    *,
    csv_entity: str | None = None,
) -> core_models.IntegrationImportBatch:
    connection = ensure_file_connection(db, user)
    source_hash = hashlib.sha256(content).hexdigest()
    duplicate = db.query(core_models.IntegrationImportBatch).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id,
        source_hash=source_hash, status="completed",
    ).order_by(core_models.IntegrationImportBatch.completed_at.desc() if hasattr(core_models.IntegrationImportBatch, "completed_at") else core_models.IntegrationImportBatch.created_at.desc()).first()
    if duplicate:
        return duplicate
    parsed = excel_connector.parse_workbook(filename, content)
    if filename.casefold().endswith(".csv"):
        if not csv_entity or csv_entity not in SCHEMAS:
            raise HTTPException(422, "CSV uploads require a supported csv_entity sheet name")
        parsed = [(csv_entity, parsed[0][1])]
    correlation = f"SCM-IMP-{str(hashlib.sha256(content).hexdigest())[:12].upper()}"
    batch = core_models.IntegrationImportBatch(
        tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id,
        source_filename=filename, source_hash=source_hash, workbook_version="scm-v1",
        mode="dry_run", status="previewed", correlation_id=correlation,
        discovery={"sheets": [{"name": name, "row_count": len(rows)} for name, rows in parsed]}, summary={},
    )
    db.add(batch)
    db.flush()
    counts = {"valid": 0, "warning": 0, "rejected": 0, "ignored": 0}
    seen: set[tuple[str, str]] = set()
    mappings = mappings or {}
    for sheet, rows in parsed:
        schema = SCHEMAS.get(sheet)
        for number, source in enumerate(rows, 2):
            row = _apply_mapping(sheet, source, mappings)
            messages: list[dict[str, Any]] = []
            external_id = _clean(row.get("external_id")) or None
            if not schema:
                action, counts_key = "ignored", "ignored"
            else:
                for field in schema["required"]:
                    if row.get(field) in (None, ""):
                        messages.append({"field": field, "code": "required", "message": f"{field} is required"})
                formula_fields = [key.removeprefix("__formula_") for key, value in source.items() if key.startswith("__formula_") and value]
                messages.extend({"field": field, "code": "formula_rejected", "message": "Use a literal value"} for field in formula_fields)
                identity = (schema["entity"], external_id or "")
                if external_id and identity in seen:
                    messages.append({"field": "external_id", "code": "duplicate_source_key", "message": "Source key is duplicated in this batch"})
                seen.add(identity)
                action, counts_key = ("error", "rejected") if messages else ("insert", "valid")
            counts[counts_key] += 1
            db.add(core_models.IntegrationImportRowResult(
                tenant_id=user.tenant_id, plant_id=user.plant_id, batch_id=batch.id,
                sheet_name=sheet, row_number=number, external_key=external_id,
                payload_hash=_hash(row), action=action,
                canonical_entity_type=schema["entity"] if schema else None,
                validation_messages=messages,
                source_cells={key: value for key, value in row.items() if not key.startswith("__")},
                mapping_version="scm-v1", correlation_id=correlation,
            ))
    batch.summary = counts
    return batch


def _material(db: Session, batch: core_models.IntegrationImportBatch, code: str) -> models.SCMMaterial | None:
    plant = db.get(core_models.Plant, batch.plant_id)
    return db.query(models.SCMMaterial).filter_by(
        tenant_id=batch.tenant_id, company_id=plant.company_id, material_code=_clean(code).upper()
    ).first()


def _supplier(db: Session, batch: core_models.IntegrationImportBatch, code: str) -> core_models.Supplier | None:
    return db.query(core_models.Supplier).filter_by(
        tenant_id=batch.tenant_id, plant_id=batch.plant_id, erp_vendor_id=_clean(code)
    ).first()


def _customer(db: Session, batch: core_models.IntegrationImportBatch, code: str) -> models.SCMCustomer | None:
    plant = db.get(core_models.Plant, batch.plant_id)
    return db.query(models.SCMCustomer).filter_by(tenant_id=batch.tenant_id, company_id=plant.company_id, code=_clean(code).upper()).first()


def _uom(db: Session, value: Any) -> core_models.Uom | None:
    return db.get(core_models.Uom, _clean(value).upper())


def _reject(result: core_models.IntegrationImportRowResult, field: str, code: str, message: str) -> None:
    result.action = "error"
    result.validation_messages = [*(result.validation_messages or []), {"field": field, "code": code, "message": message}]


def commit(db: Session, user: core_models.User, batch: core_models.IntegrationImportBatch) -> core_models.IntegrationImportBatch:
    if batch.tenant_id != user.tenant_id or batch.plant_id != user.plant_id:
        raise HTTPException(404, "SCM import not found")
    if batch.status == "completed":
        return batch
    if batch.status != "previewed":
        raise HTTPException(409, "Only a previewed SCM import can be committed")
    batch.status, batch.mode = "running", "commit"
    batch.approved_by_user_id, batch.approved_at = user.id, datetime.now(timezone.utc)
    rows = db.query(core_models.IntegrationImportRowResult).filter_by(batch_id=batch.id).all()
    rows.sort(key=lambda row: (ENTITY_ORDER.get(row.canonical_entity_type or "", 99), row.row_number))
    applied = unchanged = rejected = 0
    for result in rows:
        if result.action not in {"insert", "update"}:
            rejected += result.action == "error"
            continue
        row = result.source_cells
        entity_type = result.canonical_entity_type
        existing_receipt = db.query(core_models.IntegrationIngestionRecord).filter_by(
            connection_id=batch.connection_id, capability=entity_type, source_record_key=result.external_key
        ).first()
        if existing_receipt and existing_receipt.payload_hash == result.payload_hash:
            result.action = "unchanged"
            unchanged += 1
            continue
        try:
            entity = _apply_entity(db, batch, result, row)
        except ValueError as exc:
            _reject(result, "row", "invalid_value", str(exc))
            rejected += 1
            continue
        if entity is None:
            rejected += 1
            continue
        db.flush()
        result.canonical_entity_id = entity.id
        result.action = "applied"
        from app.platform.integrations import record_ingestion
        record_ingestion(
            db, tenant_id=batch.tenant_id, plant_id=batch.plant_id,
            source_key="scm_file_upload", source_record_id=result.external_key,
            entity_type=entity_type or "unknown", canonical_entity_id=entity.id,
            observed_at=getattr(entity, "snapshot_at", None), mapping_version=result.mapping_version,
            authoritative=entity_type in {"scm_inventory_snapshot", "scm_goods_receipt"},
            details={"batch_id": batch.id, "sheet": result.sheet_name, "row_number": result.row_number},
        )
        if entity_type == "scm_inventory_snapshot":
            from app.platform.catalog import material_for_legacy
            from app.platform.events import DomainEvent, publish
            legacy_material = db.get(models.SCMMaterial, entity.material_id)
            plant = db.get(core_models.Plant, batch.plant_id)
            canonical = material_for_legacy(
                db, tenant_id=batch.tenant_id, plant_id=batch.plant_id, company_id=plant.company_id,
                source_system="legacy:scm", legacy_id=legacy_material.id,
                code=legacy_material.material_code, name=legacy_material.description or legacy_material.material_code,
                material_type=legacy_material.material_type, base_uom_id=legacy_material.base_uom_id,
            )
            publish(db, DomainEvent(
                "inventory.position.updated", batch.tenant_id, batch.plant_id,
                "material", canonical.id,
                {"material_id": canonical.id, "legacy_scm_material_id": legacy_material.id,
                 "inventory_snapshot_id": entity.id, "as_of_at": entity.snapshot_at.isoformat(),
                 "available_qty": str(entity.available_qty), "source_system": entity.source_system},
                source_system="scm_file_upload",
            ))
        if existing_receipt:
            existing_receipt.payload_hash = result.payload_hash
            existing_receipt.target_entity_type = entity_type
            existing_receipt.target_entity_id = entity.id
            existing_receipt.status = "applied"
        else:
            db.add(core_models.IntegrationIngestionRecord(
                tenant_id=batch.tenant_id, plant_id=batch.plant_id,
                connection_id=batch.connection_id, capability=entity_type,
                source_record_key=result.external_key, payload_hash=result.payload_hash,
                target_entity_type=entity_type, target_entity_id=entity.id, status="applied",
            ))
        applied += 1
    batch.status = "completed" if rejected == 0 else "partially_completed"
    batch.summary = {"applied": applied, "unchanged": unchanged, "rejected": rejected, "total": len(rows)}
    state = db.query(models.SCMDataSourceState).filter_by(
        tenant_id=batch.tenant_id, plant_id=batch.plant_id, source_key="scm_file_upload"
    ).first()
    if not state:
        state = models.SCMDataSourceState(
            tenant_id=batch.tenant_id, plant_id=batch.plant_id, source_key="scm_file_upload",
            status="HEALTHY", expected_frequency_seconds=86400, stale_after_seconds=90000,
        )
        db.add(state)
    state.last_attempt = datetime.now(timezone.utc)
    if applied or unchanged:
        state.last_successful_import = state.last_attempt
    state.status = "HEALTHY" if rejected == 0 else "WARNING"
    state.records_processed = applied + unchanged
    state.error_summary = f"{rejected} rows rejected" if rejected else None
    # Keep canonical identities and graph edges synchronized as part of the
    # same import transaction; application developers never hand-create edges.
    from app.platform.backfill import backfill_tenant
    backfill_tenant(db, batch.tenant_id)
    from app.scm.manual_entries import create_import_conflicts
    batch.summary = {**batch.summary, "manual_conflicts": create_import_conflicts(db, batch)}
    return batch


def _apply_entity(db: Session, batch: core_models.IntegrationImportBatch, result: core_models.IntegrationImportRowResult, row: dict[str, Any]):
    entity_type = result.canonical_entity_type
    plant = db.get(core_models.Plant, batch.plant_id)
    messages: list[dict[str, Any]] = []
    if entity_type == "scm_material":
        uom = _uom(db, row.get("base_uom"))
        if not uom:
            _reject(result, "base_uom", "unknown_uom", "UOM is not in the approved UOM master")
            return None
        code = _clean(row["material_code"]).upper()
        entity = _material(db, batch, code)
        if not entity:
            entity = models.SCMMaterial(
                tenant_id=batch.tenant_id, plant_id=None, company_id=plant.company_id,
                material_code=code, base_uom_id=uom.id,
            )
            db.add(entity)
            db.flush()
        entity.description = _clean(row.get("description"))
        entity.material_type = _clean(row.get("material_type")).upper() or "OTHER"
        entity.base_uom_id = uom.id
        entity.specification_text = _clean(row.get("specification_text"))
        entity.external_id = result.external_key
        item = db.query(core_models.Item).filter_by(tenant_id=batch.tenant_id, plant_id=batch.plant_id, code=code).first()
        link = db.query(models.SCMMaterialPlant).filter_by(material_id=entity.id, plant_id=batch.plant_id).first()
        if not link:
            db.add(models.SCMMaterialPlant(tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=entity.id, item_id=item.id if item else None))
        return entity
    if entity_type == "scm_customer":
        code = _clean(row["customer_code"]).upper()
        entity = _customer(db, batch, code)
        if not entity:
            entity = models.SCMCustomer(tenant_id=batch.tenant_id, plant_id=None, company_id=plant.company_id, code=code, name=_clean(row["name"]), external_id=result.external_key)
            db.add(entity)
        else:
            entity.name = _clean(row["name"])
        return entity
    material_code = row.get("material_code") or row.get("finished_good_code") or row.get("parent_material_code")
    material = _material(db, batch, material_code) if material_code else None
    if material_code and not material:
        _reject(result, "material_code", "unknown_material", f"Material {_clean(material_code)} must be imported first")
        return None
    if entity_type == "scm_material_plant_policy":
        entity = db.query(models.SCMMaterialPlantPolicy).filter_by(material_id=material.id, plant_id=batch.plant_id).first()
        if not entity:
            entity = models.SCMMaterialPlantPolicy(tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=material.id)
            db.add(entity)
        for field in ("planned_lead_time_days", "goods_receipt_processing_days", "minimum_coverage_days", "maximum_coverage_days", "planning_time_fence_days", "cancellation_window_days", "expedite_window_days"):
            if row.get(field) not in (None, ""):
                setattr(entity, field, int(row[field]))
        for field in ("safety_stock_qty", "minimum_order_qty", "order_multiple"):
            if row.get(field) not in (None, ""):
                setattr(entity, field, Decimal(str(row[field])))
        entity.procurement_type = _clean(row.get("procurement_type")) or None
        return entity
    if entity_type == "scm_material_supplier":
        supplier = _supplier(db, batch, row["supplier_code"])
        if not supplier:
            _reject(result, "supplier_code", "unknown_supplier", "Supplier must exist in procurement master")
            return None
        entity = db.query(models.SCMMaterialSupplier).filter_by(material_id=material.id, plant_id=batch.plant_id, supplier_id=supplier.id).first()
        if not entity:
            entity = models.SCMMaterialSupplier(tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=material.id, supplier_id=supplier.id)
            db.add(entity)
        entity.contract_lead_time_days = int(row["contract_lead_time_days"]) if row.get("contract_lead_time_days") not in (None, "") else None
        entity.minimum_order_qty = Decimal(str(row["minimum_order_qty"])) if row.get("minimum_order_qty") not in (None, "") else None
        entity.order_multiple = Decimal(str(row["order_multiple"])) if row.get("order_multiple") not in (None, "") else None
        entity.expedite_allowed = _clean(row.get("expedite_allowed", "true")).lower() not in {"false", "0", "no"}
        entity.pushout_allowed = _clean(row.get("pushout_allowed")).lower() in {"true", "1", "yes"}
        entity.cancellation_allowed = _clean(row.get("cancellation_allowed")).lower() in {"true", "1", "yes"}
        return entity
    if entity_type == "scm_customer_usage":
        customer = _customer(db, batch, row["customer_code"])
        if not customer:
            _reject(result, "customer_code", "unknown_customer", "Customer must be imported first")
            return None
        entity = db.query(models.SCMMaterialCustomerUsage).filter_by(finished_good_material_id=material.id, plant_id=batch.plant_id, customer_id=customer.id, program_name=_clean(row.get("program_name")) or None).first()
        if not entity:
            entity = models.SCMMaterialCustomerUsage(tenant_id=batch.tenant_id, plant_id=batch.plant_id, finished_good_material_id=material.id, customer_id=customer.id, program_name=_clean(row.get("program_name")) or None)
            db.add(entity)
        entity.customer_part_number = _clean(row.get("customer_part_number")) or None
        return entity
    if entity_type == "scm_bom":
        effective = _date(row["effective_from"], "effective_from", messages)
        if not effective:
            _reject(result, "effective_from", "invalid_date", "effective_from must use YYYY-MM-DD")
            return None
        entity = db.query(models.SCMBOM).filter_by(tenant_id=batch.tenant_id, plant_id=batch.plant_id, bom_code=_clean(row["bom_code"]), revision=_clean(row["revision"])).first()
        if not entity:
            entity = models.SCMBOM(tenant_id=batch.tenant_id, plant_id=batch.plant_id, company_id=plant.company_id, parent_material_id=material.id, bom_code=_clean(row["bom_code"]), revision=_clean(row["revision"]), effective_from=effective, source_system="file", external_id=result.external_key, import_batch_id=batch.id)
            db.add(entity)
        entity.status = _clean(row.get("status")).upper() or "ACTIVE"
        if row.get("effective_to"):
            entity.effective_to = _date(row["effective_to"], "effective_to", messages)
        return entity
    if entity_type == "scm_bom_line":
        bom = db.query(models.SCMBOM).filter_by(tenant_id=batch.tenant_id, plant_id=batch.plant_id, bom_code=_clean(row["bom_code"]), revision=_clean(row["revision"])).first()
        component = _material(db, batch, row["component_material_code"])
        uom = _uom(db, row["uom"])
        if not bom or not component or not uom:
            _reject(result, "row", "reference_not_found", "BOM, component material, and UOM must exist")
            return None
        if bom.parent_material_id == component.id:
            _reject(result, "component_material_code", "bom_cycle", "A material cannot directly consume itself")
            return None
        entity = db.query(models.SCMBOMLine).filter_by(bom_id=bom.id, line_number=int(row["line_number"])).first()
        if not entity:
            entity = models.SCMBOMLine(tenant_id=batch.tenant_id, plant_id=batch.plant_id, bom_id=bom.id, line_number=int(row["line_number"]), component_material_id=component.id, quantity_per=Decimal(str(row["quantity_per"])), uom_id=uom.id)
            db.add(entity)
        entity.scrap_factor = Decimal(str(row.get("scrap_factor") or 0))
        return entity
    if entity_type == "scm_inventory_snapshot":
        uom = _uom(db, row["uom"])
        observed = _datetime(row["snapshot_at"], "snapshot_at", messages)
        if not uom or not observed:
            _reject(result, "row", "invalid_inventory", "Inventory requires a known UOM and ISO timestamp")
            return None
        entity = db.query(models.SCMInventorySnapshot).filter_by(tenant_id=batch.tenant_id, source_system="file", source_record_id=result.external_key).first()
        if not entity:
            entity = models.SCMInventorySnapshot(tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=material.id, snapshot_at=observed, on_hand_qty=Decimal(str(row["on_hand_qty"])), available_qty=Decimal(str(row["available_qty"])), uom_id=uom.id, source_system="file", source_record_id=result.external_key, import_batch_id=batch.id)
            db.add(entity)
        return entity
    if entity_type == "scm_demand_forecast":
        uom = _uom(db, row["uom"])
        start = _date(row["bucket_start"], "bucket_start", messages)
        end = _date(row["bucket_end"], "bucket_end", messages)
        if not uom or not start or not end or end < start:
            _reject(result, "row", "invalid_forecast", "Forecast requires a known UOM and ordered dates")
            return None
        entity = db.query(models.SCMDemandForecast).filter_by(tenant_id=batch.tenant_id, source_system="file", source_record_id=result.external_key).first()
        if not entity:
            entity = models.SCMDemandForecast(tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=material.id, forecast_version=_clean(row["forecast_version"]), bucket_start=start, bucket_end=end, quantity=Decimal(str(row["quantity"])), uom_id=uom.id, forecast_type=_clean(row.get("forecast_type")).upper() or "BASELINE", source_system="file", source_record_id=result.external_key, import_batch_id=batch.id)
            db.add(entity)
        return entity
    if entity_type == "scm_material_requirement":
        uom = _uom(db, row["uom"])
        required = _date(row["required_date"], "required_date", messages)
        if not uom or not required:
            _reject(result, "row", "invalid_requirement", "Requirement requires a known UOM and date")
            return None
        entity = db.query(models.SCMMaterialRequirement).filter_by(tenant_id=batch.tenant_id, source_system="file", external_id=result.external_key).first()
        if not entity:
            finished = _material(db, batch, row.get("finished_good_code")) if row.get("finished_good_code") else None
            customer = _customer(db, batch, row.get("customer_code")) if row.get("customer_code") else None
            entity = models.SCMMaterialRequirement(tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=material.id, required_date=required, quantity=Decimal(str(row["quantity"])), uom_id=uom.id, requirement_type=_clean(row["requirement_type"]).upper(), priority=int(row.get("priority") or 100), finished_good_id=finished.id if finished else None, customer_id=customer.id if customer else None, source_system="file", external_id=result.external_key, import_batch_id=batch.id, lineage={"finished_good_code": _clean(row.get("finished_good_code")).upper() or None})
            db.add(entity)
        return entity
    if entity_type == "scm_supply_order":
        uom = _uom(db, row["uom"])
        if not uom:
            _reject(result, "uom", "unknown_uom", "Supply order UOM is unknown")
            return None
        entity = db.query(models.SCMSupplyOrder).filter_by(tenant_id=batch.tenant_id, source_system="file", source_record_id=result.external_key).first()
        if not entity:
            supplier = _supplier(db, batch, row.get("supplier_code")) if row.get("supplier_code") else None
            entity = models.SCMSupplyOrder(tenant_id=batch.tenant_id, plant_id=batch.plant_id, supply_type=_clean(row["supply_type"]).upper(), material_id=material.id, supplier_id=supplier.id if supplier else None, order_number=_clean(row["order_number"]), line_number=_clean(row["line_number"]), ordered_qty=Decimal(str(row["ordered_qty"])), received_qty=Decimal(str(row["received_qty"])), uom_id=uom.id, status=_clean(row["status"]).upper(), firmness=_clean(row.get("firmness")).upper() or "FIRM", source_system="file", source_record_id=result.external_key, import_batch_id=batch.id)
            db.add(entity)
        return entity
    if entity_type == "scm_supply_schedule":
        order = db.query(models.SCMSupplyOrder).filter_by(tenant_id=batch.tenant_id, source_system="file", source_record_id=_clean(row["supply_order_external_id"])).first()
        original = _date(row["original_due_date"], "original_due_date", messages)
        current = _date(row["current_due_date"], "current_due_date", messages)
        if not order or not original or not current:
            _reject(result, "row", "invalid_schedule", "Schedule requires an imported order and valid dates")
            return None
        entity = db.query(models.SCMSupplyScheduleLine).filter_by(supply_order_id=order.id, schedule_line_number=_clean(row["schedule_line_number"])).first()
        if not entity:
            entity = models.SCMSupplyScheduleLine(tenant_id=batch.tenant_id, plant_id=batch.plant_id, supply_order_id=order.id, schedule_line_number=_clean(row["schedule_line_number"]), scheduled_qty=Decimal(str(row["scheduled_qty"])), received_qty=Decimal(str(row["received_qty"])), original_due_date=original, current_due_date=current, status=_clean(row["status"]).upper(), source_record_id=result.external_key)
            db.add(entity)
        if entity.received_qty > entity.scheduled_qty:
            _reject(result, "received_qty", "receipt_exceeds_schedule", "Received quantity exceeds scheduled quantity")
            return None
        return entity
    if entity_type == "scm_goods_receipt":
        uom = _uom(db, row["uom"])
        received = _date(row["receipt_date"], "receipt_date", messages)
        if not uom or not received:
            _reject(result, "row", "invalid_receipt", "Receipt requires a known UOM and date")
            return None
        entity = db.query(models.SCMGoodsReceipt).filter_by(tenant_id=batch.tenant_id, source_system="file", source_record_id=result.external_key).first()
        if not entity:
            order = db.query(models.SCMSupplyOrder).filter_by(tenant_id=batch.tenant_id, source_system="file", source_record_id=_clean(row.get("supply_order_external_id"))).first() if row.get("supply_order_external_id") else None
            entity = models.SCMGoodsReceipt(tenant_id=batch.tenant_id, plant_id=batch.plant_id, material_id=material.id, supply_order_id=order.id if order else None, receipt_date=received, quantity=Decimal(str(row["quantity"])), uom_id=uom.id, source_system="file", source_record_id=result.external_key, import_batch_id=batch.id)
            db.add(entity)
        return entity
    raise ValueError(f"Unsupported SCM entity type {entity_type}")


def serialize_batch(db: Session, batch: core_models.IntegrationImportBatch, *, include_rows: bool = True) -> dict[str, Any]:
    payload = {
        "id": batch.id, "filename": batch.source_filename, "source_hash": batch.source_hash,
        "status": batch.status, "mode": batch.mode, "summary": batch.summary,
        "discovery": batch.discovery, "created_at": batch.created_at,
        "approved_at": batch.approved_at,
    }
    if include_rows:
        rows = db.query(core_models.IntegrationImportRowResult).filter_by(batch_id=batch.id).order_by(core_models.IntegrationImportRowResult.sheet_name, core_models.IntegrationImportRowResult.row_number).all()
        payload["rows"] = [{
            "id": row.id, "sheet": row.sheet_name, "row_number": row.row_number,
            "external_key": row.external_key, "action": row.action,
            "entity_type": row.canonical_entity_type,
            "canonical_entity_id": row.canonical_entity_id,
            "messages": row.validation_messages, "source": row.source_cells,
        } for row in rows]
    return payload
