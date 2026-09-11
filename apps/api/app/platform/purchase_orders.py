"""Canonical purchase-order ingestion and safe shared execution boundary."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.events import DomainEvent, publish
from app.platform.integrations import record_ingestion
from app.platform.models import (DataProvenance, DataQualityIssue, ExternalEntityReference,
    PlatformPurchaseOrder, PlatformPurchaseOrderLine, PlatformStateSnapshot)
from app.platform.relationships import connect


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _resolve(db: Session, tenant_id: str, source_key: str, entity_type: str, external_id: str) -> ExternalEntityReference | None:
    return db.query(ExternalEntityReference).filter_by(
        tenant_id=tenant_id, source_system=source_key, entity_type=entity_type, external_id=external_id).first()


def ingest_delivery_update(db: Session, *, tenant_id: str, plant_id: str, connection_id: str,
                           source_key: str, source_record_id: str, purchase_order_external_id: str,
                           supplier_external_id: str, material_external_id: str,
                           confirmed_delivery_date: date, observed_at: datetime,
                           mapping_version: str, correlation_id: str,
                           causation_id: str | None = None) -> tuple[PlatformPurchaseOrder, core.EventOutbox, bool]:
    payload = {"purchase_order_external_id": purchase_order_external_id,
               "supplier_external_id": supplier_external_id, "material_external_id": material_external_id,
               "confirmed_delivery_date": confirmed_delivery_date.isoformat(),
               "mapping_version": mapping_version}
    prior = db.query(core.IntegrationIngestionRecord).filter_by(
        connection_id=connection_id, capability="purchase_order.delivery_update",
        source_record_key=source_record_id).first()
    if prior:
        po = db.query(PlatformPurchaseOrder).filter_by(id=prior.target_entity_id, tenant_id=tenant_id).one()
        event = db.query(core.EventOutbox).filter_by(correlation_id=correlation_id,
            event_type="purchase_order.rescheduled", subject_id=po.id).first()
        if not event:
            event = db.query(core.EventOutbox).filter_by(event_type="purchase_order.rescheduled", subject_id=po.id).order_by(core.EventOutbox.created_at.desc()).first()
        return po, event, True

    po_ref = _resolve(db, tenant_id, source_key, "purchase_order", purchase_order_external_id)
    supplier_ref = _resolve(db, tenant_id, source_key, "supplier", supplier_external_id)
    material_ref = _resolve(db, tenant_id, source_key, "material", material_external_id)
    if not (po_ref and supplier_ref and material_ref):
        missing = [name for name, value in (("purchase_order", po_ref), ("supplier", supplier_ref), ("material", material_ref)) if not value]
        db.add(core.IntegrationIngestionRecord(tenant_id=tenant_id, plant_id=plant_id,
            connection_id=connection_id, capability="purchase_order.delivery_update",
            source_record_key=source_record_id, payload_hash=_hash(payload), target_entity_type="mapping_error",
            target_entity_id=f"unmapped:{source_record_id}", status="rejected"))
        db.add(DataProvenance(tenant_id=tenant_id, plant_id=plant_id, entity_type="ingestion_error",
            entity_id=f"unmapped:{source_record_id}", source_system=source_key, source_reference=source_record_id,
            observed_at=observed_at, mapping_version=mapping_version, transformation="purchase_order.delivery_update",
            quality_status="rejected", details={"missing_mappings": missing, "payload": payload}, correlation_id=correlation_id))
        db.add(DataQualityIssue(tenant_id=tenant_id, plant_id=plant_id, entity_type="purchase_order",
            entity_id=None, rule_key="invalid_canonical_mapping", severity="error", status="open",
            message=f"External delivery update has missing mappings: {', '.join(missing)}",
            details={"source_record_id": source_record_id, "correlation_id": correlation_id}))
        raise ValueError(f"Canonical mapping missing for: {', '.join(missing)}")
    po = db.query(PlatformPurchaseOrder).filter_by(id=po_ref.canonical_entity_id, tenant_id=tenant_id).one()
    if po.supplier_id != supplier_ref.canonical_entity_id:
        raise ValueError("Supplier mapping conflicts with canonical purchase order")
    line = db.query(PlatformPurchaseOrderLine).filter_by(
        purchase_order_id=po.id, material_id=material_ref.canonical_entity_id).first()
    if not line:
        raise ValueError("Material mapping is not present on the canonical purchase order")
    previous = po.confirmed_delivery_date
    po.confirmed_delivery_date = confirmed_delivery_date
    provenance = DataProvenance(tenant_id=tenant_id, plant_id=plant_id, entity_type="purchase_order",
        entity_id=po.id, source_system=source_key, source_reference=source_record_id,
        observed_at=observed_at, mapping_version=mapping_version, transformation="purchase_order.delivery_update",
        authoritative=True, details={"before": previous.isoformat() if previous else None,
                                     "after": confirmed_delivery_date.isoformat()}, correlation_id=correlation_id)
    db.add(provenance); db.flush()
    db.add(core.IntegrationIngestionRecord(tenant_id=tenant_id, plant_id=plant_id,
        connection_id=connection_id, capability="purchase_order.delivery_update",
        source_record_key=source_record_id, payload_hash=_hash(payload), target_entity_type="purchase_order",
        target_entity_id=po.id, status="applied"))
    record_ingestion(db, tenant_id=tenant_id, plant_id=plant_id, source_key=source_key,
        source_record_id=source_record_id, entity_type="purchase_order", canonical_entity_id=po.id,
        observed_at=observed_at, mapping_version=mapping_version, authoritative=True,
        details={"correlation_id": correlation_id, "capability": "purchase_order.delivery_update"},
        correlation_id=correlation_id)
    connect(db, tenant_id=tenant_id, plant_id=plant_id, source_type="purchase_order", source_id=po.id,
            relationship="orders", target_type="material", target_id=line.material_id,
            source_system=source_key, provenance_id=provenance.id)
    connect(db, tenant_id=tenant_id, plant_id=plant_id, source_type="purchase_order", source_id=po.id,
            relationship="placed_with", target_type="supplier", target_id=po.supplier_id,
            source_system=source_key, provenance_id=provenance.id)
    snapshot = PlatformStateSnapshot(tenant_id=tenant_id, plant_id=plant_id,
        entity_type="purchase_order", entity_id=po.id, snapshot_type="current",
        observed={"status": po.status, "confirmed_delivery_date": confirmed_delivery_date.isoformat()},
        derived={}, predicted={}, planned={}, provenance=[{"id": provenance.id, "source": source_key}],
        freshness={"status": "fresh", "observed_at": observed_at.isoformat()},
        captured_at=datetime.now(timezone.utc), correlation_id=correlation_id)
    db.add(snapshot)
    event = publish(db, DomainEvent(event_type="purchase_order.rescheduled", tenant_id=tenant_id,
        plant_id=plant_id, subject_type="purchase_order", subject_id=po.id,
        payload={"purchase_order_id": po.id, "material_id": line.material_id,
                 "supplier_id": po.supplier_id, "previous_delivery_date": previous.isoformat() if previous else None,
                 "confirmed_delivery_date": confirmed_delivery_date.isoformat(), "source_record_id": source_record_id},
        correlation_id=correlation_id, causation_id=causation_id or source_record_id,
        source_system=source_key, occurred_at=observed_at))
    return po, event, False


def apply_simulated_reschedule(db: Session, *, po: PlatformPurchaseOrder, target_date: date,
                               correlation_id: str, source_record_id: str) -> dict:
    previous = po.confirmed_delivery_date
    po.confirmed_delivery_date = target_date
    receipt = f"SIM-ERP-{po.order_number}-{target_date.isoformat()}"
    publish(db, DomainEvent("purchase_order.rescheduled", po.tenant_id, po.plant_id,
        "purchase_order", po.id, {"purchase_order_id": po.id,
        "material_id": db.query(PlatformPurchaseOrderLine.material_id).filter_by(purchase_order_id=po.id).scalar(),
        "supplier_id": po.supplier_id, "previous_delivery_date": previous.isoformat() if previous else None,
        "confirmed_delivery_date": target_date.isoformat(), "source_record_id": source_record_id,
        "execution_receipt": receipt}, correlation_id=correlation_id,
        causation_id=source_record_id, source_system="simulated_erp"))
    return {"purchase_order_id": po.id, "confirmed_delivery_date": target_date.isoformat(),
            "external_reference": receipt}
