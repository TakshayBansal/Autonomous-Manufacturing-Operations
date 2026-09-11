from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.db import models


class BusinessScope(Protocol):
    tenant_id: str
    plant_id: str | None


def next_business_number(db: Session, prefix: str, scope: BusinessScope) -> str:
    """Allocate a plant-scoped number under a locked sequence row."""
    if not scope.plant_id:
        raise ValueError("A plant is required for a business number")
    year = datetime.now(timezone.utc).year
    normalized = prefix.upper().strip()
    sequence = next(
        (
            candidate
            for candidate in db.new
            if isinstance(candidate, models.BusinessNumberSequence)
            and candidate.tenant_id == scope.tenant_id
            and candidate.plant_id == scope.plant_id
            and candidate.prefix == normalized
            and candidate.year == year
        ),
        None,
    )
    if sequence is None:
        sequence = db.query(models.BusinessNumberSequence).filter_by(
            tenant_id=scope.tenant_id,
            plant_id=scope.plant_id,
            prefix=normalized,
            year=year,
        ).with_for_update().first()
    if sequence is None:
        highest = 0
        prefix_pattern = f"{normalized}-{year}-%"
        for mapper in models.Base.registry.mappers:
            entity = mapper.class_
            if not isinstance(entity, type) or not issubclass(entity, models.ScopedMixin):
                continue
            existing_numbers = db.query(entity.business_number).filter(
                entity.tenant_id == scope.tenant_id,
                entity.plant_id == scope.plant_id,
                entity.business_number.like(prefix_pattern),
            ).all()
            for (number,) in existing_numbers:
                try:
                    highest = max(highest, int(str(number).rsplit("-", 1)[-1]))
                except (TypeError, ValueError):
                    continue
        value = highest + 1
        # Most business numbers are tenant/plant scoped, but a few legacy
        # tables (notably documents) still have a database-wide unique index.
        # A newly created tenant can therefore otherwise generate DOC-YYYY-0001
        # again and fail during an upload preview. Skip any already-used number
        # across the mapped tables while preserving the tenant-local sequence.
        while _business_number_exists(db, f"{normalized}-{year}-{value:04d}"):
            value += 1
        sequence = models.BusinessNumberSequence(
            tenant_id=scope.tenant_id,
            plant_id=scope.plant_id,
            prefix=normalized,
            year=year,
            next_value=value + 1,
        )
        db.add(sequence)
    else:
        value = sequence.next_value
        while _business_number_exists(db, f"{normalized}-{year}-{value:04d}"):
            value += 1
        sequence.next_value = value + 1
    return f"{normalized}-{year}-{value:04d}"


def _business_number_exists(db: Session, candidate: str) -> bool:
    """Return whether a candidate is already persisted or pending in any table."""
    for pending in db.new:
        if isinstance(pending, models.ScopedMixin) and getattr(pending, "business_number", None) == candidate:
            return True
    for mapper in models.Base.registry.mappers:
        entity = mapper.class_
        if not isinstance(entity, type) or not issubclass(entity, models.ScopedMixin):
            continue
        if db.query(entity.id).filter(entity.business_number == candidate).first() is not None:
            return True
    return False
