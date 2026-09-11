from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db import models


ALLOWED_TYPES = {"preference", "procedure", "verified_episode", "factory_pattern", "team_decision"}


def remember_verified(db: Session, *, tenant_id: str, plant_id: str, membership_id: str,
                      key: str, value: str, memory_type: str, scope_type: str,
                      scope_id: str | None, provenance: dict, confidence: float = 1.0) -> models.AgentMemory:
    if memory_type not in ALLOWED_TYPES or not provenance.get("evidence_refs"):
        raise ValueError("Only evidence-backed, typed memory may be persisted")
    row = db.query(models.AgentMemory).filter_by(membership_id=membership_id, key=key).first()
    if row is None:
        row = models.AgentMemory(tenant_id=tenant_id, plant_id=plant_id, membership_id=membership_id, key=key, value=value)
        db.add(row)
    row.value, row.memory_type, row.scope_type, row.scope_id = value, memory_type, scope_type, scope_id
    row.provenance, row.confidence = provenance, confidence
    row.validation_state, row.valid_from, row.superseded_at = "verified", datetime.now(timezone.utc), None
    return row


def current_memories(db: Session, *, tenant_id: str, membership_id: str) -> list[models.AgentMemory]:
    now = datetime.now(timezone.utc)
    return db.query(models.AgentMemory).filter(models.AgentMemory.tenant_id == tenant_id,
        models.AgentMemory.membership_id == membership_id, models.AgentMemory.validation_state == "verified",
        models.AgentMemory.superseded_at.is_(None),
        (models.AgentMemory.expires_at.is_(None) | (models.AgentMemory.expires_at > now))).all()
