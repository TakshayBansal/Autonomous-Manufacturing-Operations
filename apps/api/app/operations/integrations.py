from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connector_sdk import registry_manifests
from app.db import models


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def connection_health(db: Session, connection: models.IntegrationConnection) -> dict[str, Any]:
    last_job = (db.query(models.IntegrationSyncJob).filter_by(connection_id=connection.id)
                .order_by(models.IntegrationSyncJob.created_at.desc()).first())
    observed = _aware(last_job.finished_at if last_job and last_job.finished_at else connection.last_checked_at)
    age_seconds = (utcnow() - observed).total_seconds() if observed else None
    stale_after = int((connection.config or {}).get("stale_after_seconds", 900))
    if connection.mode == "disconnected" or connection.status == "disabled":
        state = "disabled"
    elif last_job and last_job.status == "failed":
        state = "error"
    elif age_seconds is None:
        state = "unknown"
    elif age_seconds > stale_after:
        state = "stale"
    else:
        state = "healthy"
    return {"state": state, "last_observed_at": observed, "age_seconds": age_seconds,
            "stale_after_seconds": stale_after,
            "last_sync": {"id": last_job.id, "status": last_job.status, "job_type": last_job.job_type,
                          "summary": last_job.summary, "error": last_job.error} if last_job else None}


def serialize_connection(db: Session, connection: models.IntegrationConnection) -> dict[str, Any]:
    manifest = next((item for item in registry_manifests() if item.provider == connection.provider), None)
    mappings = (db.query(models.IntegrationMappingProfile).filter_by(connection_id=connection.id)
                .order_by(models.IntegrationMappingProfile.profile_version.desc()).all())
    return {
        "id": connection.id, "name": connection.name, "provider": connection.provider,
        "provider_version": connection.provider_version, "mode": connection.mode,
        "status": connection.status, "writes_enabled": connection.writes_enabled,
        "capabilities": connection.capabilities, "enabled_capabilities": connection.enabled_capabilities,
        "live_customer_verified": bool(manifest.live_customer_verified) if manifest else False,
        "protocols": list(manifest.protocols) if manifest else [],
        "health": connection_health(db, connection),
        "mappings": [{"id": row.id, "name": row.name, "version": row.profile_version,
                      "status": row.status, "mappings": row.mappings, "transforms": row.transforms,
                      "ownership": row.ownership, "created_at": row.created_at}
                     for row in mappings],
    }


def list_connections(db: Session, tenant_id: str, plant_id: str) -> list[dict[str, Any]]:
    return [serialize_connection(db, row) for row in db.query(models.IntegrationConnection).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).order_by(models.IntegrationConnection.name.asc()).all()]


def create_mapping_version(db: Session, connection: models.IntegrationConnection,
                           name: str, mappings: dict, transforms: dict,
                           ownership: dict) -> models.IntegrationMappingProfile:
    previous = (db.query(models.IntegrationMappingProfile).filter_by(
        connection_id=connection.id, name=name).order_by(
        models.IntegrationMappingProfile.profile_version.desc()).first())
    if previous:
        previous.status = "superseded"
    row = models.IntegrationMappingProfile(
        tenant_id=connection.tenant_id, plant_id=connection.plant_id,
        connection_id=connection.id, name=name,
        profile_version=(previous.profile_version + 1) if previous else 1,
        mappings=mappings, transforms=transforms, ownership=ownership,
        status="active",
    )
    db.add(row)
    return row


def plant_data_health(db: Session, tenant_id: str, plant_id: str) -> list[dict[str, Any]]:
    rows = list_connections(db, tenant_id, plant_id)
    return [{"connection_id": row["id"], "source": row["name"],
             "provider": row["provider"], **row["health"]} for row in rows]
