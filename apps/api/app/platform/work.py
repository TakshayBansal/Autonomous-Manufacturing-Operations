"""Shared work queue facade over the existing cross-domain Task record."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session

from app.db import models
from app.platform.events import DomainEvent, publish


def create_work_item(db: Session, *, tenant_id: str, plant_id: str, title: str,
                     source_domain: str, source_type: str, source_id: str,
                     owner_role: str, owner_user_id: str | None = None,
                     owner_membership_id: str | None = None, due_at: datetime | None = None,
                     priority: str = "normal", severity: str = "normal",
                     requested_outcome: str = "", semantic_key: str) -> models.Task:
    existing = db.query(models.Task).filter_by(tenant_id=tenant_id, semantic_key=semantic_key).first()
    if existing:
        return existing
    row = models.Task(tenant_id=tenant_id, plant_id=plant_id, title=title, owner_role=owner_role,
                      owner_user_id=owner_user_id, owner_membership_id=owner_membership_id,
                      due_at=due_at, priority=priority, severity=severity, status="open",
                      entity_type=source_type, entity_id=source_id, task_type=f"{source_domain}_work",
                      assignment_source="platform", requested_outcome=requested_outcome,
                      semantic_key=semantic_key)
    db.add(row); db.flush()
    publish(db, DomainEvent("platform.work.created", tenant_id, plant_id, "work_item", row.id,
                            {"work_item_id": row.id, "source_domain": source_domain,
                             "source_type": source_type, "source_id": source_id}, owner_membership_id))
    return row


def list_work(db: Session, *, tenant_id: str, plant_id: str | None = None,
              user_id: str | None = None, include_closed: bool = False) -> list[models.Task]:
    query = db.query(models.Task).filter_by(tenant_id=tenant_id)
    if plant_id:
        query = query.filter(models.Task.plant_id == plant_id)
    if user_id:
        user = db.get(models.User, user_id)
        query = query.filter((models.Task.owner_user_id == user_id) | (models.Task.owner_role == user.role))
    if not include_closed:
        query = query.filter(models.Task.status.notin_(["completed", "cancelled", "closed"]))
    return query.order_by(models.Task.due_at.asc().nullslast(), models.Task.created_at.desc()).all()
