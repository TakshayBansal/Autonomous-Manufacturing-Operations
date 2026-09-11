"""One workbook envelope over existing Procurement, SCM and Operations processors.

No domain data is written during preview. Commit is atomic across all children;
the original source hash, normalized rows, domain receipts and lineage remain
in the existing integration tables.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from io import BytesIO

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import excel_connector
from app.db import models
from app.operations import workbook as operations
from app.scm import imports as scm_imports

VERSION = "factory-v2"
PROCUREMENT_SHEETS = {"Items", "Suppliers", "SupplierContacts", "SupplierCapabilities", "Requirements", "OpenPOs", "OpenPOLines"}


def automotive_template() -> bytes:
    """Connected, non-prescriptive EMS factory dataset.

    The workbook contains facts only.  It deliberately contains no cases,
    recommendations, scores, or recovery outcomes; those are calculated after
    ingestion by the normal SCM and shared-case services.
    """
    today = datetime.now(timezone.utc).date()
    observed_at = datetime.combine(today, datetime.min.time(), timezone.utc).replace(hour=8)
    purchased = [
        ("MAT-182", "Automotive-grade MCU"), ("MOS-220", "Power MOSFET"),
        ("CAP-450", "450V film capacitor"), ("PCB-101", "Multilayer control PCB"),
        ("CONN-88", "Sealed automotive connector"), ("SENSOR-7", "Current sensor"),
        ("WIRE-4", "4 mm copper cable"), ("SEAL-9", "IP67 enclosure seal"),
    ]
    subassemblies = [
        ("CTRL-CORE", "Control core assembly"), ("POWER-STAGE", "Power switching stage"),
        ("SENSOR-HUB", "Sensor interface hub"), ("HARNESS-ASSY", "Vehicle harness assembly"),
    ]
    finished = [
        ("ECU-A", "Honda ECU-A"), ("ECU-B", "Honda ECU-B"),
        ("ECU-C", "Tata ECU-C"), ("BMS-X", "Honda battery controller X"),
        ("BMS-Y", "Mahindra battery controller Y"), ("PDU-X", "Tata power distribution unit X"),
        ("PDU-Y", "Mahindra power distribution unit Y"), ("CHG-X", "Honda onboard charger X"),
    ]
    all_materials = purchased + subassemblies + finished
    customers = [("HONDA", "Honda"), ("TATA", "Tata Motors"), ("MAHINDRA", "Mahindra")]
    suppliers = [
        ("SUP-X", "Supplier X Semiconductors", 94, 78),
        ("SUP-Y", "Western Power Electronics", 91, 86),
        ("SUP-Z", "Precision Connect Systems", 96, 92),
        ("SUP-W", "CircuitWorks India", 89, 74),
    ]
    supplier_for = {"MAT-182": "SUP-X", "MOS-220": "SUP-Y", "CAP-450": "SUP-Y",
                    "PCB-101": "SUP-W", "CONN-88": "SUP-Z", "SENSOR-7": "SUP-X",
                    "WIRE-4": "SUP-Z", "SEAL-9": "SUP-Z"}
    bom_map = {
        "CTRL-CORE": [("MAT-182", 1), ("PCB-101", 1), ("CONN-88", 2)],
        "POWER-STAGE": [("MOS-220", 6), ("CAP-450", 2), ("SENSOR-7", 1)],
        "SENSOR-HUB": [("MAT-182", 1), ("SENSOR-7", 3), ("PCB-101", 1)],
        "HARNESS-ASSY": [("WIRE-4", 4), ("CONN-88", 3), ("SEAL-9", 2)],
        "ECU-A": [("CTRL-CORE", 1), ("SENSOR-HUB", 1), ("HARNESS-ASSY", 1), ("SEAL-9", 1)],
        "ECU-B": [("CTRL-CORE", 1), ("POWER-STAGE", 1), ("HARNESS-ASSY", 1)],
        "ECU-C": [("CTRL-CORE", 1), ("SENSOR-HUB", 1), ("CONN-88", 2)],
        "BMS-X": [("CTRL-CORE", 1), ("POWER-STAGE", 2), ("SENSOR-HUB", 2)],
        "BMS-Y": [("CTRL-CORE", 1), ("POWER-STAGE", 2), ("HARNESS-ASSY", 1)],
        "PDU-X": [("POWER-STAGE", 2), ("HARNESS-ASSY", 1), ("SEAL-9", 2)],
        "PDU-Y": [("POWER-STAGE", 3), ("SENSOR-HUB", 1), ("HARNESS-ASSY", 1)],
        "CHG-X": [("CTRL-CORE", 1), ("POWER-STAGE", 3), ("HARNESS-ASSY", 1), ("CAP-450", 2)],
    }
    demand = [
        ("H421", "ECU-A", "HONDA", 160, 3, "LINE-1"),
        ("H422", "ECU-B", "HONDA", 120, 5, "LINE-1"),
        ("T311", "ECU-C", "TATA", 140, 4, "LINE-2"),
        ("H510", "BMS-X", "HONDA", 90, 7, "LINE-3"),
        ("M220", "BMS-Y", "MAHINDRA", 110, 9, "LINE-3"),
        ("T405", "PDU-X", "TATA", 100, 8, "LINE-4"),
        ("M330", "PDU-Y", "MAHINDRA", 80, 11, "LINE-4"),
        ("H610", "CHG-X", "HONDA", 70, 13, "LINE-4"),
    ]
    # Component requirements are an ERP/MRP output.  Shared components aggregate
    # demand from every final product, making impact and pegging genuinely linked.
    def explode(code: str, qty: int) -> dict[str, int]:
        totals: dict[str, int] = {}
        for component, per in bom_map.get(code, []):
            if component in bom_map:
                for leaf, leaf_qty in explode(component, qty * per).items():
                    totals[leaf] = totals.get(leaf, 0) + leaf_qty
            else:
                totals[component] = totals.get(component, 0) + qty * per
        return totals

    inventory_qty = {"MAT-182": 300, "MOS-220": 2500, "CAP-450": 1200, "PCB-101": 500,
                     "CONN-88": 2500, "SENSOR-7": 1200, "WIRE-4": 3200, "SEAL-9": 1800}
    supply_qty = {"MAT-182": 3000, "MOS-220": 3000, "CAP-450": 900, "PCB-101": 500,
                  "CONN-88": 1400, "SENSOR-7": 700, "WIRE-4": 1800, "SEAL-9": 900}
    delay_days = {"MAT-182": 6, "MOS-220": 1, "CAP-450": 7, "PCB-101": 5,
                  "CONN-88": 0, "SENSOR-7": 4, "WIRE-4": 0, "SEAL-9": 2}
    sheets = {
        "Manifest": [{"schema_version": VERSION, "scenario": "Connected automotive factory / 20 SKUs"}],
        "PROC_Items": [{"external_key": f"ITEM-{code}", "code": code, "name": name, "uom": "EA"} for code, name in purchased],
        "PROC_Suppliers": [{"external_key": code, "name": name, "status": "approved", "quality_score": quality, "delivery_score": delivery} for code, name, quality, delivery in suppliers],
        "PROC_SupplierCapabilities": [{"external_key": f"CAP-{supplier_for[code]}-{code}", "supplier_external_key": supplier_for[code], "item_external_key": f"ITEM-{code}", "approved": True} for code, _ in purchased],
        "PROC_OpenPOs": [{"external_key": f"PO-{code}", "business_number": f"PO-{code}", "supplier_external_key": supplier_for[code], "status": "posted", "currency": "INR"} for code, _ in purchased],
        "PROC_OpenPOLines": [{"external_key": f"PO-{code}-L1", "po_external_key": f"PO-{code}", "item_external_key": f"ITEM-{code}", "quantity": supply_qty[code], "uom": "EA", "unit_price": 50 + index * 35, "need_by_date": (today + timedelta(days=2 + index % 3)).isoformat()} for index, (code, _) in enumerate(purchased)],
        "SCM_Materials": [{"external_id": f"SCM-{code}", "material_code": code, "description": name,
                           "material_type": "COMPONENT" if (code, name) in purchased else "SUBASSEMBLY" if (code, name) in subassemblies else "FINISHED_GOOD", "base_uom": "EA"} for code, name in all_materials],
        "SCM_MaterialPlantPolicies": [{"external_id": f"POL-{code}", "material_code": code, "safety_stock_qty": 50,
                                       "minimum_order_qty": 50, "order_multiple": 10, "planning_time_fence_days": 1,
                                       "maximum_coverage_days": 45, "procurement_type": "EXTERNAL"} for code, _ in purchased],
        "SCM_Customers": [{"external_id": f"CUST-{code}", "customer_code": code, "name": name} for code, name in customers],
        "SCM_CustomerUsage": [{"external_id": f"USE-{order}-{product}", "finished_good_code": product, "customer_code": customer,
                               "program_name": f"{customer} EV program", "customer_part_number": order} for order, product, customer, *_ in demand],
        "SCM_BOMs": [{"external_id": f"BOM-{parent}", "bom_code": f"BOM-{parent}", "revision": "A",
                      "parent_material_code": parent, "effective_from": (today - timedelta(days=30)).isoformat(), "status": "ACTIVE"} for parent in bom_map],
        "SCM_BOMLines": [{"external_id": f"BOM-{parent}-{line}", "bom_code": f"BOM-{parent}", "revision": "A", "line_number": line,
                          "component_material_code": component, "quantity_per": per, "uom": "EA", "scrap_factor": 0}
                         for parent, components in bom_map.items() for line, (component, per) in enumerate(components, 1)],
        "SCM_Inventory": [{"external_id": f"INV-A-{code}", "material_code": code, "snapshot_at": observed_at.isoformat(),
                           "on_hand_qty": inventory_qty.get(code, 0), "available_qty": inventory_qty.get(code, 0), "uom": "EA"} for code, _ in all_materials],
        "SCM_Requirements": [{"external_id": f"{order}-{component}", "material_code": component,
                              "required_date": (today + timedelta(days=offset)).isoformat(), "quantity": qty_required,
                              "uom": "EA", "requirement_type": "PRODUCTION_ORDER", "finished_good_code": product,
                              "customer_code": customer, "priority": 1 + offset}
                             for order, product, customer, qty, offset, _ in demand
                             for component, qty_required in explode(product, qty).items()],
        "SCM_SupplyOrders": [{"external_id": f"SCM-PO-{code}", "material_code": code, "supply_type": "PURCHASE_ORDER",
                              "order_number": f"PO-{code}", "line_number": "1", "ordered_qty": supply_qty[code], "received_qty": 0,
                              "uom": "EA", "status": "OPEN", "firmness": "FIRM", "supplier_code": supplier_for[code]} for code, _ in purchased],
        "SCM_SupplySchedules": [{"external_id": f"PO-{code}-S1", "supply_order_external_id": f"SCM-PO-{code}", "schedule_line_number": "1",
                                 "scheduled_qty": supply_qty[code], "received_qty": 0,
                                 "original_due_date": (today + timedelta(days=2 + index % 3)).isoformat(),
                                 "current_due_date": (today + timedelta(days=2 + index % 3 + delay_days[code])).isoformat(), "status": "CONFIRMED"}
                                for index, (code, _) in enumerate(purchased)],
        "OPS_Lines": [{"external_id": f"LINE-{number}", "code": f"LINE-{number}", "name": f"Assembly Line {number}",
                       "standard_good_rate_per_minute": 1.5 + number / 4} for number in range(1, 5)],
        "OPS_WorkOrders": [{"external_id": f"WO-{order}", "line_code": line, "product_code": product,
                            "product_name": next(name for code, name in finished if code == product), "quantity": qty,
                            "planned_start_at": datetime.combine(today + timedelta(days=offset), datetime.min.time(), timezone.utc).replace(hour=6).isoformat(),
                            "planned_end_at": datetime.combine(today + timedelta(days=offset), datetime.min.time(), timezone.utc).replace(hour=14).isoformat()}
                           for order, product, _, qty, offset, line in demand],
        "OPS_MaterialRequirements": [{"external_id": f"WO-{order}-{component}", "work_order_external_id": f"WO-{order}",
                                      "material_code": component, "quantity": qty_required, "uom": "EA",
                                      "required_at": datetime.combine(today + timedelta(days=offset), datetime.min.time(), timezone.utc).replace(hour=6).isoformat()}
                                     for order, product, _, qty, offset, _ in demand
                                     for component, qty_required in explode(product, qty).items()],
    }
    return workbook_bytes(sheets)


def workbook_bytes(sheets: dict[str, list[dict]]) -> bytes:
    workbook = Workbook()
    stable_metadata_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
    workbook.properties.created = stable_metadata_time
    workbook.properties.modified = stable_metadata_time
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        headers = list(dict.fromkeys(key for row in rows for key in row))
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(key) for key in headers])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def scoped_batch(db: Session, user: models.User, batch_id: str):
    batch = db.query(models.IntegrationImportBatch).filter_by(id=batch_id,
        tenant_id=user.tenant_id, plant_id=user.plant_id, workbook_version=VERSION).first()
    if not batch:
        raise HTTPException(404, "Factory import not found")
    return batch


def preserve_existing_demo_masters(db: Session, batch: models.IntegrationImportBatch) -> None:
    """Resolve only stale-master collisions for the built-in demo upgrade.

    A workspace that previously loaded factory-v1 may already own SUP-X.  The
    one-click v2 demo must preserve that local master rather than overwrite it
    or fail.  Uploaded customer workbooks never call this helper and retain the
    normal explicit conflict-review requirement.
    """
    procurement_id = (batch.summary or {}).get("children", {}).get("procurement")
    if not procurement_id:
        return
    rows = db.query(models.IntegrationImportRowResult).filter_by(
        batch_id=procurement_id, action="conflict").all()
    resolved = set()
    for row in rows:
        codes = {message.get("code") for message in (row.validation_messages or [])}
        if codes == {"stale_external_data"} and row.canonical_entity_type in {"supplier", "item"}:
            row.action = "unchanged"
            row.validation_messages = [{"code": "existing_demo_master_preserved",
                "message": "Existing workspace master retained during demo upgrade"}]
            resolved.add((row.sheet_name, row.row_number))
    if not resolved:
        return
    child = db.get(models.IntegrationImportBatch, procurement_id)
    if child:
        summary = dict(child.summary or {})
        summary["conflict"] = max(0, int(summary.get("conflict", 0)) - len(resolved))
        summary["unchanged"] = int(summary.get("unchanged", 0)) + len(resolved)
        child.summary = summary
    summary = dict(batch.summary or {})
    summary["errors"] = [issue for issue in summary.get("errors", []) if not (
        (issue.get("sheet"), issue.get("row")) in resolved
        and {message.get("code") for message in issue.get("messages", [])} == {"stale_external_data"})]
    batch.summary = summary


def preview(db: Session, user: models.User, filename: str, content: bytes):
    parsed = dict(excel_connector.parse_workbook(filename, content))
    manifest = parsed.pop("Manifest", [])
    if len(manifest) != 1 or manifest[0].get("schema_version") != VERSION:
        raise HTTPException(422, f"Manifest must declare schema_version {VERSION}")
    domains: dict[str, dict[str, list[dict]]] = {"PROC": {}, "SCM": {}, "OPS": {}}
    for sheet, rows in parsed.items():
        domain, _, name = sheet.partition("_")
        schemas = PROCUREMENT_SHEETS if domain == "PROC" else scm_imports.SCHEMAS if domain == "SCM" else operations.SCHEMAS if domain == "OPS" else {}
        if name not in schemas:
            raise HTTPException(422, f"Unsupported factory workbook sheet: {sheet}")
        if any(key.startswith("__formula_") and value for row in rows for key, value in row.items()):
            raise HTTPException(422, f"Formulas are not accepted in {sheet}")
        domains[domain][name] = [{key: value for key, value in row.items() if not key.startswith("__")} for row in rows]
    if not any(domains.values()):
        raise HTTPException(422, "Workbook contains no supported domain records")
    digest = hashlib.sha256(content).hexdigest()
    existing = db.query(models.IntegrationImportBatch).filter_by(tenant_id=user.tenant_id,
        plant_id=user.plant_id, workbook_version=VERSION, source_hash=digest).first()
    if existing:
        return existing
    connection = db.query(models.IntegrationConnection).filter_by(tenant_id=user.tenant_id,
        plant_id=user.plant_id, name="Unified Factory Workbook").first()
    if not connection:
        connection = models.IntegrationConnection(tenant_id=user.tenant_id, plant_id=user.plant_id,
            name="Unified Factory Workbook", provider="excel_csv", provider_version="1",
            mode="import_only", status="configured", writes_enabled=False,
            capabilities=["factory_workbook"], enabled_capabilities=["factory_workbook"])
        db.add(connection); db.flush()
    batch = models.IntegrationImportBatch(tenant_id=user.tenant_id, plant_id=user.plant_id,
        connection_id=connection.id, source_filename=filename, source_hash=digest,
        workbook_version=VERSION, status="previewed", mode="dry_run",
        correlation_id=f"factory:{digest[:32]}", discovery={"sheets": list(parsed)}, summary={})
    db.add(batch); db.flush()
    children = {}
    if domains["PROC"]:
        child = excel_connector.preview_import(db, user, connection, "procurement.xlsx", workbook_bytes(domains["PROC"]))
        children["procurement"] = child.id
    if domains["SCM"]:
        child = scm_imports.preview(db, user, "scm.xlsx", workbook_bytes(domains["SCM"]))
        children["scm"] = child.id
    errors = []
    line_codes = {str(row.get("code")) for row in domains["OPS"].get("Lines", [])}
    work_orders = {str(row.get("external_id")) for row in domains["OPS"].get("WorkOrders", [])}
    item_codes = {str(row.get("code")) for row in domains["PROC"].get("Items", [])}
    item_codes.update(row[0] for row in db.query(models.Item.code).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id).all())
    for sheet, rows in domains["OPS"].items():
        seen = set()
        for number, values in enumerate(rows, 2):
            try:
                normalized = operations.SCHEMAS[sheet].model_validate(values).model_dump(mode="json")
                if normalized["external_id"] in seen:
                    raise ValueError("Duplicate external_id in sheet")
                if sheet == "WorkOrders" and normalized["line_code"] not in line_codes:
                    raise ValueError(f"Unknown OPS_Lines code {normalized['line_code']}")
                if sheet == "MaterialRequirements" and normalized["work_order_external_id"] not in work_orders:
                    raise ValueError(f"Unknown OPS_WorkOrders external_id {normalized['work_order_external_id']}")
                if sheet == "MaterialRequirements" and normalized["material_code"] not in item_codes:
                    raise ValueError(f"Unknown PROC_Items code {normalized['material_code']}")
                seen.add(normalized["external_id"])
                messages = []
            except ValueError as exc:
                normalized = values
                messages = [{"code": "invalid_operations_record", "message": str(exc)}]
                errors.append({"sheet": f"OPS_{sheet}", "row": number, "messages": messages})
            db.add(models.IntegrationImportRowResult(tenant_id=user.tenant_id, plant_id=user.plant_id,
                batch_id=batch.id, sheet_name=f"OPS_{sheet}", row_number=number,
                external_key=str(values.get("external_id", "")), source_cells=normalized,
                payload_hash=excel_connector.payload_hash(normalized), action="error" if messages else "insert",
                validation_messages=messages, mapping_version=VERSION, correlation_id=batch.correlation_id,
                canonical_entity_type=f"operations_{sheet}"))
    db.flush()
    for child_id in children.values():
        for issue in db.query(models.IntegrationImportRowResult).filter(
                models.IntegrationImportRowResult.batch_id == child_id,
                models.IntegrationImportRowResult.action.in_(("error", "conflict"))).all():
            errors.append({"sheet": issue.sheet_name, "row": issue.row_number, "messages": issue.validation_messages})
    batch.summary = {"children": children, "errors": errors,
        "row_count": sum(len(rows) for sheets in domains.values() for rows in sheets.values()),
        "reference_validation": "References are revalidated atomically at commit"}
    return batch


def commit(db: Session, user: models.User, batch: models.IntegrationImportBatch):
    scoped_batch(db, user, batch.id)
    if batch.status == "completed":
        return batch
    if batch.status != "previewed" or batch.summary.get("errors"):
        raise HTTPException(409, "Resolve workbook validation errors before committing")
    try:
        with db.begin_nested():
            for domain, child_id in batch.summary.get("children", {}).items():
                child = db.query(models.IntegrationImportBatch).filter_by(id=child_id,
                    tenant_id=user.tenant_id, plant_id=user.plant_id).one()
                if child.status != "completed":
                    if domain == "procurement":
                        excel_connector.commit_import(db, user, child)
                    elif domain == "scm":
                        scm_imports.commit(db, user, child)
                db.flush()
                if child.status != "completed":
                    raise ValueError(f"{domain} import contains unresolved references or conflicts")
            rows = db.query(models.IntegrationImportRowResult).filter_by(batch_id=batch.id).all()
            order = {"OPS_Lines": 0, "OPS_WorkOrders": 1, "OPS_MaterialRequirements": 2}
            for result in sorted(rows, key=lambda row: (order[row.sheet_name], row.row_number)):
                entity = operations.apply_row(db, user, result.sheet_name.removeprefix("OPS_"), result.source_cells)
                result.canonical_entity_id, result.action = entity.id, "applied"
                from app.platform.integrations import record_ingestion
                record_ingestion(db, tenant_id=user.tenant_id, plant_id=user.plant_id,
                    source_key="factory_workbook", source_record_id=result.external_key,
                    entity_type=result.canonical_entity_type, canonical_entity_id=entity.id,
                    observed_at=None, mapping_version=VERSION, authoritative=True,
                    details={"batch_id": batch.id, "source_hash": batch.source_hash, "sheet": result.sheet_name, "row": result.row_number})
            from app.platform.backfill import backfill_tenant
            report = backfill_tenant(db, user.tenant_id)
            batch.summary = {**batch.summary, "canonical_reconciliation": report.as_dict()}
            batch.status, batch.mode, batch.approved_by_user_id = "completed", "commit", user.id
            batch.approved_at = excel_connector.utcnow()
            db.flush()
    except (ValueError, SQLAlchemyError) as exc:
        db.expire_all()
        raise HTTPException(409, f"Factory import rolled back: {exc}") from exc
    return batch


def payload(batch):
    return {"id": batch.id, "filename": batch.source_filename, "source_hash": batch.source_hash,
        "version": batch.workbook_version, "status": batch.status, "summary": batch.summary,
        "discovery": batch.discovery, "created_at": batch.created_at}
