"""Versioned envelope over the existing transactional outbox."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db import models


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    tenant_id: str
    plant_id: str | None
    subject_type: str
    subject_id: str
    payload: dict
    actor_membership_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    source_system: str = "genuinegigs"
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


def publish(db: Session, event: DomainEvent) -> models.EventOutbox:
    """Persist an idempotent-compatible event; dispatch remains asynchronous."""
    from app.platform.event_registry import validate
    validate(event.event_type, event.version, event.payload)
    row = models.EventOutbox(
        tenant_id=event.tenant_id, plant_id=event.plant_id, event_type=event.event_type,
        aggregate_type=event.subject_type, aggregate_id=event.subject_id, aggregate_version=event.version,
        actor_membership_id=event.actor_membership_id, correlation_id=event.correlation_id or str(uuid4()),
        causation_id=event.causation_id, payload=event.payload, event_version=event.version,
        occurred_at=event.occurred_at, recorded_at=datetime.now(timezone.utc), source_system=event.source_system,
        subject_type=event.subject_type, subject_id=event.subject_id,
    )
    db.add(row)
    return row
