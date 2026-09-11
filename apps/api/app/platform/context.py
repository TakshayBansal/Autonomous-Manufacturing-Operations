"""Typed tenant/site context shared by APIs, workers, connectors, and agents."""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.db import models


@dataclass(frozen=True)
class PlatformContext:
    tenant_id: str
    plant_id: str
    company_id: str
    user_id: str | None
    membership_id: str | None
    role: str | None
    authorities: frozenset[str]


def for_user(db: Session, user: models.User) -> PlatformContext:
    plant = db.get(models.Plant, user.plant_id)
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    scope = db.query(models.OperationalScope).filter_by(membership_id=membership.id).first() if membership else None
    authorities = set(membership.permissions or []) if membership else set()
    authorities.update(scope.authorities or [] if scope else [])
    return PlatformContext(user.tenant_id, user.plant_id, plant.company_id if plant else "",
                           user.id, membership.id if membership else None, user.role, frozenset(authorities))
