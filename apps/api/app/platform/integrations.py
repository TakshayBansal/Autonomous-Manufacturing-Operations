"""Source registry, canonical lineage, checkpoints, and connector health facade."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.models import DataProvenance, ExternalEntityReference, SourceSystem


def ensure_source_system(db: Session, *, tenant_id: str, plant_id: str | None, key: str,
                         name: str, system_type: str, connection_id: str | None = None,
                         authority: dict | None = None) -> SourceSystem:
    row = db.query(SourceSystem).filter_by(tenant_id=tenant_id, key=key).first()
    if row is None:
        row = SourceSystem(tenant_id=tenant_id, plant_id=plant_id, key=key, name=name,
                           system_type=system_type, connection_id=connection_id,
                           authority=authority or {}, status="active")
        db.add(row)
    elif connection_id and not row.connection_id:
        row.connection_id = connection_id
    return row


def record_ingestion(db: Session, *, tenant_id: str, plant_id: str | None,
                     source_key: str, source_record_id: str, entity_type: str,
                     canonical_entity_id: str, observed_at: datetime | None = None,
                     mapping_version: str = "1", authoritative: bool = False,
                     details: dict | None = None, correlation_id: str | None = None) -> None:
    source = ensure_source_system(db, tenant_id=tenant_id, plant_id=plant_id, key=source_key,
                                  name=source_key.replace("_", " ").title(), system_type="connector")
    source.last_success_at = datetime.now(timezone.utc)
    source.checkpoint = {"last_record_id": source_record_id, "mapping_version": mapping_version,
                         "updated_at": source.last_success_at.isoformat()}
    source.health = {"status": "healthy", "checked_at": source.last_success_at.isoformat()}
    reference = db.query(ExternalEntityReference).filter_by(
        tenant_id=tenant_id, source_system=source_key, entity_type=entity_type,
        external_id=source_record_id).first()
    if reference is None:
        db.add(ExternalEntityReference(tenant_id=tenant_id, plant_id=plant_id,
                                       source_system=source_key, entity_type=entity_type,
                                       canonical_entity_type=entity_type,
                                       canonical_entity_id=canonical_entity_id,
                                       external_id=source_record_id,
                                       metadata_json=details or {}))
    elif reference.canonical_entity_id != canonical_entity_id or reference.canonical_entity_type != entity_type:
        raise ValueError("External entity is already mapped to a different canonical identity")
    else:
        reference.last_seen_at = datetime.now(timezone.utc)
        reference.external_version = mapping_version
    db.add(DataProvenance(tenant_id=tenant_id, plant_id=plant_id, entity_type=entity_type,
                          entity_id=canonical_entity_id, source_system=source_key,
                          source_reference=source_record_id, observed_at=observed_at,
                          mapping_version=mapping_version, transformation="connector normalization",
                          authoritative=authoritative, details=details or {}, correlation_id=correlation_id))


def connector_health(db: Session, tenant_id: str) -> list[dict]:
    sources = db.query(SourceSystem).filter_by(tenant_id=tenant_id).all()
    return [{"id": row.id, "key": row.key, "name": row.name, "system_type": row.system_type,
             "status": row.status, "checkpoint": row.checkpoint, "health": row.health,
             "last_success_at": row.last_success_at, "connection_id": row.connection_id} for row in sources]
