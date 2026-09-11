"""Normalize capability records into canonical operations tables with lineage receipts."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


def _time(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        raise ValueError(f"{field} is required")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _required(record: dict, field: str) -> Any:
    value = record.get(field)
    if value is None or value == "":
        raise ValueError(f"{field} is required")
    return value


def _scoped(db: Session, model, tenant_id: str, plant_id: str, value: str,
            external_field: str | None = None):
    query = db.query(model).filter_by(tenant_id=tenant_id, plant_id=plant_id)
    row = query.filter(model.id == value).first()
    if row is None and external_field:
        row = query.filter(getattr(model, external_field) == value).first()
    if row is None and hasattr(model, "business_number"):
        row = query.filter(model.business_number == value).first()
    if row is None:
        raise ValueError(f"Referenced {model.__name__} was not found: {value}")
    return row


def _mapped(record: dict, mappings: dict) -> dict:
    if not mappings:
        return dict(record)
    output = dict(record)
    for target, source in mappings.items():
        if isinstance(source, str) and source in record:
            output[target] = record[source]
    return output


def _apply(db: Session, connection: models.IntegrationConnection, capability: str,
           record: dict, source_key: str):
    tenant_id, plant_id = connection.tenant_id, connection.plant_id
    source = f"connector:{connection.provider}"
    if capability == "read_business_events":
        event_type = str(_required(record, "event_type"))
        if event_type == "supplier.mail":
            supplier_id = record.get("supplier_id")
            if supplier_id:
                _scoped(db, models.Supplier, tenant_id, plant_id, str(supplier_id))
            row = models.SupplierChannelMessage(
                tenant_id=tenant_id, plant_id=plant_id, channel="email", direction="inbound",
                external_message_id=str(record.get("external_message_id") or source_key),
                sender=str(_required(record, "sender")), recipient=str(record.get("recipient") or "purchase@northstar-mobility.local"),
                subject=str(record.get("subject") or "Supplier update"), body_preview=str(record.get("body_preview") or ""),
                status="received", supplier_id=supplier_id, document_ids=[], canonical_record_ids=[])
        elif event_type == "customer.order":
            line = _scoped(db, models.ProductionLine, tenant_id, plant_id, str(_required(record, "line_id")), "code")
            shift = _scoped(db, models.PlantShift, tenant_id, plant_id, str(_required(record, "shift_id")))
            row = models.ProductionWorkOrder(
                tenant_id=tenant_id, plant_id=plant_id, line_id=line.id, shift_id=shift.id,
                business_number=str(_required(record, "order_number")), external_reference=str(record.get("external_reference") or source_key),
                product_code=str(_required(record, "product_code")), product_name=str(_required(record, "product_name")),
                target_quantity=float(_required(record, "target_quantity")),
                planned_start_at=_time(record.get("planned_start_at"), "planned_start_at"),
                planned_end_at=_time(record.get("planned_end_at"), "planned_end_at"), status="scheduled")
        else:
            owner_role = str(record.get("owner_role") or ("gate_operator" if event_type == "logistics.arrival" else "production_manager"))
            row = models.Task(
                tenant_id=tenant_id, plant_id=plant_id, title=str(_required(record, "title")), owner_role=owner_role,
                status="open", severity=str(record.get("severity") or "info"), priority=str(record.get("priority") or "normal"),
                entity_type="simulated_business_event", entity_id=source_key, task_type=event_type.replace(".", "_"),
                requested_outcome=str(record.get("requested_outcome") or "Review and act on the incoming business event."),
                due_at=_time(record["due_at"], "due_at") if record.get("due_at") else None,
                semantic_key=f"business-event:{connection.id}:{source_key}", business_impact=str(record.get("severity") or "normal"),
                production_impact=str(record.get("production_impact") or "indirect"))
        db.add(row); return row
    if capability in {"read_production_plan", "read_production_actual", "read_downtime",
                      "read_supplier_commitments", "read_inspections", "read_quality"}:
        work_order = _scoped(db, models.ProductionWorkOrder, tenant_id, plant_id,
                             str(_required(record, "work_order_id")), "external_reference")
    if capability == "read_production_plan":
        at = _time(record.get("recorded_at"), "recorded_at")
        row = db.query(models.ProductionPlanPoint).filter_by(
            work_order_id=work_order.id, recorded_at=at).first()
        if row is None:
            row = models.ProductionPlanPoint(tenant_id=tenant_id, plant_id=plant_id,
                work_order_id=work_order.id, recorded_at=at,
                cumulative_quantity=float(_required(record, "cumulative_quantity")), source=source)
            db.add(row)
        else:
            row.cumulative_quantity = float(_required(record, "cumulative_quantity"))
        return row
    if capability == "read_production_actual":
        row = models.ProductionActualPoint(tenant_id=tenant_id, plant_id=plant_id,
            work_order_id=work_order.id, recorded_at=_time(record.get("recorded_at"), "recorded_at"),
            good_quantity=float(_required(record, "good_quantity")),
            reject_quantity=float(record.get("reject_quantity") or 0), source=source,
            source_event_key=f"{connection.id}:{source_key}")
        db.add(row); return row
    if capability == "read_downtime":
        line_id = str(record.get("line_id") or work_order.line_id)
        _scoped(db, models.ProductionLine, tenant_id, plant_id, line_id)
        asset_id = record.get("asset_id")
        if asset_id:
            asset_id = _scoped(db, models.PlantAsset, tenant_id, plant_id, str(asset_id), "code").id
        row = models.ProductionDowntimeEvent(tenant_id=tenant_id, plant_id=plant_id,
            work_order_id=work_order.id, line_id=line_id, asset_id=asset_id,
            started_at=_time(record.get("started_at"), "started_at"),
            ended_at=_time(record["ended_at"], "ended_at") if record.get("ended_at") else None,
            category=str(record.get("category") or "unplanned"), reason=record.get("reason"),
            planned=bool(record.get("planned", False)))
        db.add(row); return row
    if capability == "read_inventory":
        row = models.MaterialInventoryPosition(tenant_id=tenant_id, plant_id=plant_id,
            material_code=str(_required(record, "material_code")),
            on_hand_quantity=float(record.get("on_hand_quantity") or 0),
            reserved_for_other_orders=float(record.get("reserved_for_other_orders") or 0),
            quality_hold_quantity=float(record.get("quality_hold_quantity") or 0),
            observed_at=_time(record.get("observed_at"), "observed_at"),
            source_system=source, source_reference=source_key)
        db.add(row); return row
    if capability == "read_supplier_commitments":
        row = models.ProductionSupplierCommitment(tenant_id=tenant_id, plant_id=plant_id,
            work_order_id=work_order.id, material_code=str(_required(record, "material_code")),
            supplier_id=record.get("supplier_id"),
            committed_quantity=float(_required(record, "committed_quantity")),
            committed_delivery_at=_time(record.get("committed_delivery_at"), "committed_delivery_at"),
            acknowledged=bool(record.get("acknowledged", False)),
            reliability_score=float(record.get("reliability_score", 1)),
            status=str(record.get("status") or "open"), v1_po_draft_id=record.get("v1_po_draft_id"),
            v1_acknowledgement_id=record.get("v1_acknowledgement_id"))
        db.add(row); return row
    if capability in {"read_inspections", "read_quality"}:
        row = models.ProductionQualityEvent(tenant_id=tenant_id, plant_id=plant_id,
            work_order_id=work_order.id, line_id=str(record.get("line_id") or work_order.line_id),
            occurred_at=_time(record.get("occurred_at"), "occurred_at"),
            inspected_quantity=float(record.get("inspected_quantity") or 0),
            rejected_quantity=float(record.get("rejected_quantity") or 0),
            defect_code=record.get("defect_code"), event_type=str(record.get("event_type") or "inspection"),
            asset_id=record.get("asset_id"), material_lot_id=record.get("material_lot_id"),
            measurement_name=record.get("measurement_name"), measurement_value=record.get("measurement_value"),
            lower_control_limit=record.get("lower_control_limit"), upper_control_limit=record.get("upper_control_limit"),
            severity=record.get("severity"), evidence={"connector_record": source_key},
            source=source)
        db.add(row); return row
    if capability == "read_machine_events":
        asset = _scoped(db, models.PlantAsset, tenant_id, plant_id,
                        str(_required(record, "asset_id")), "code")
        event_type = str(record.get("event_type") or "alarm")
        if event_type == "signal.sampled":
            row = models.MachineSignalSample(tenant_id=tenant_id, plant_id=plant_id, asset_id=asset.id,
                work_order_id=record.get("work_order_id"), occurred_at=_time(record.get("occurred_at"), "occurred_at"),
                signals=dict(record.get("signals") or {}), source_quality=str(record.get("source_quality") or "good"),
                source=source, source_event_key=f"{connection.id}:{source_key}")
        elif event_type == "production.good_count":
            work_order = _scoped(db, models.ProductionWorkOrder, tenant_id, plant_id,
                                 str(_required(record, "work_order_id")), "external_reference")
            row = models.ProductionActualPoint(tenant_id=tenant_id, plant_id=plant_id,
                work_order_id=work_order.id, recorded_at=_time(record.get("occurred_at"), "occurred_at"),
                good_quantity=float(_required(record, "good_quantity")),
                reject_quantity=float(record.get("reject_quantity") or 0), source=source,
                source_event_key=f"{connection.id}:{source_key}")
        elif event_type == "state" and str(record.get("fault_code")) == "RECOVERED":
            row = (db.query(models.AssetFaultEvent).filter_by(
                tenant_id=tenant_id, plant_id=plant_id, asset_id=asset.id, cleared_at=None)
                .order_by(models.AssetFaultEvent.occurred_at.desc()).first())
            if row is None:
                row = models.AssetFaultEvent(tenant_id=tenant_id, plant_id=plant_id, asset_id=asset.id,
                    work_order_id=record.get("work_order_id"), fault_code="RECOVERED",
                    message=str(record.get("message") or "Machine recovered"),
                    occurred_at=_time(record.get("occurred_at"), "occurred_at"), source=source,
                    source_event_key=f"{connection.id}:{source_key}")
            row.cleared_at = _time(record.get("occurred_at"), "occurred_at")
        else:
            row = models.AssetFaultEvent(tenant_id=tenant_id, plant_id=plant_id, asset_id=asset.id,
                work_order_id=record.get("work_order_id"), fault_code=str(record.get("fault_code") or "UNKNOWN"),
                message=str(record.get("message") or "Machine alarm"),
                occurred_at=_time(record.get("occurred_at"), "occurred_at"),
                cleared_at=_time(record["cleared_at"], "cleared_at") if record.get("cleared_at") else None,
                source=source, source_event_key=f"{connection.id}:{source_key}")
        db.add(row); return row
    if capability == "read_maintenance_work":
        asset = _scoped(db, models.PlantAsset, tenant_id, plant_id,
                        str(_required(record, "asset_id")), "code")
        row = models.MaintenanceWorkRecord(tenant_id=tenant_id, plant_id=plant_id,
            asset_id=asset.id, external_cmms_reference=record.get("external_reference") or source_key,
            title=str(_required(record, "title")), status=str(record.get("status") or "open"),
            owner_user_id=record.get("owner_user_id"), spare_code=record.get("spare_code"),
            spare_available=record.get("spare_available"),
            started_at=_time(record["started_at"], "started_at") if record.get("started_at") else None,
            completed_at=_time(record["completed_at"], "completed_at") if record.get("completed_at") else None,
            resolution=record.get("resolution"))
        db.add(row); return row
    raise ValueError(f"No canonical normalizer for {capability}")


def normalize_results(db: Session, job: models.IntegrationSyncJob,
                      connection: models.IntegrationConnection, results: dict[str, dict]) -> dict:
    mapping = db.query(models.IntegrationMappingProfile).filter_by(
        connection_id=connection.id, status="active").order_by(
        models.IntegrationMappingProfile.profile_version.desc()).first()
    counts = {"received": 0, "applied": 0, "duplicates": 0, "errors": 0}
    errors = []
    targets: dict[str, int] = {}
    applied_records = []
    for capability, result in results.items():
        for index, raw in enumerate(result.get("records") or []):
            counts["received"] += 1
            record = _mapped(dict(raw), mapping.mappings if mapping else {})
            source_key = str(record.get("source_record_key") or record.get("id") or
                             hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest())
            existing = db.query(models.IntegrationIngestionRecord).filter_by(
                connection_id=connection.id, capability=capability, source_record_key=source_key).first()
            if existing:
                counts["duplicates"] += 1
                continue
            try:
                with db.begin_nested():
                    target = _apply(db, connection, capability, record, source_key)
                    db.flush()
                    receipt = models.IntegrationIngestionRecord(
                        tenant_id=job.tenant_id, plant_id=job.plant_id, connection_id=connection.id,
                        capability=capability, source_record_key=source_key,
                        payload_hash=hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest(),
                        target_entity_type=target.__tablename__, target_entity_id=target.id,
                        source_cursor=result.get("cursor"))
                    db.add(receipt)
                    event_type = {
                        "production_actual_points": "production.actual.updated",
                        "production_downtime_events": "downtime.updated",
                        "production_quality_events": "quality.event.updated",
                        "material_inventory_positions": "inventory.position.updated",
                        "production_supplier_commitments": "supplier.commitment.updated",
                        "asset_fault_events": "machine.event.updated",
                        "machine_signal_samples": "machine.signal.updated",
                        "maintenance_work_records": "maintenance.work.updated",
                    }.get(target.__tablename__, "integration.record.accepted")
                    db.add(models.EventOutbox(
                        tenant_id=job.tenant_id, plant_id=job.plant_id, event_type=event_type,
                        aggregate_type=target.__tablename__, aggregate_id=target.id,
                        aggregate_version=1, correlation_id=f"ingest:{connection.id}:{source_key}"[:80],
                        payload={"entity_type": target.__tablename__, "entity_id": target.id,
                                 "capability": capability, "source_record_key": source_key},
                    ))
                    db.flush()
                counts["applied"] += 1
                applied_records.append(target)
                targets[target.__tablename__] = targets.get(target.__tablename__, 0) + 1
            except Exception as exc:
                counts["errors"] += 1
                errors.append({"capability": capability, "record": index + 1,
                               "source_record_key": source_key, "error": str(exc)[:300]})
    return {"counts": counts, "targets": targets, "errors": errors,
            "mapping_version": mapping.profile_version if mapping else None,
            "applied_records": applied_records}
