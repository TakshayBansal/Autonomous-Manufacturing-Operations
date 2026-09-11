from typing import Any, TypeVar

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Query, Session

from app.core.permissions import ADMIN
from app.db import models

Scoped = TypeVar("Scoped", bound=models.ScopedMixin)


def authorized_plant_ids(db: Session, user: models.User) -> set[str]:
    rows = db.query(models.UserPlantAccess.plant_id).filter(
        models.UserPlantAccess.tenant_id == user.tenant_id,
        models.UserPlantAccess.user_id == user.id,
    ).all()
    return {row[0] for row in rows} or {user.plant_id}


def query_scoped(db: Session, model: type[Scoped], user: models.User, plant_id: str | None = None) -> Query:
    query = db.query(model).filter(model.tenant_id == user.tenant_id)
    requested_plant = plant_id or user.plant_id
    if requested_plant not in authorized_plant_ids(db, user):
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return query.filter(model.plant_id == requested_plant)


def get_scoped_or_404(
    db: Session,
    model: type[Scoped],
    user: models.User,
    object_id: str,
    label: str | None = None,
    plant_id: str | None = None,
) -> Scoped:
    record = query_scoped(db, model, user, plant_id).filter(
        (model.id == object_id) | (model.public_id == object_id) | (model.business_number == object_id)
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label or model.__name__} not found")
    return record


def require_if_match(request: Request, entity: models.ScopedMixin) -> None:
    supplied = request.headers.get("if-match")
    if supplied is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match header is required")
    normalized = supplied.strip().strip('W/').strip('"')
    if normalized != str(entity.version):
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED, detail="Entity version is stale")


def etag_for(entity: models.ScopedMixin) -> str:
    return f'"{entity.version}"'


def require_admin_plant_access(db: Session, user: models.User, plant_id: str) -> None:
    if user.role != ADMIN or plant_id not in authorized_plant_ids(db, user):
        raise HTTPException(status_code=403, detail="Plant administration access denied")


def record_dict(record: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in record.__table__.columns:
        value = getattr(record, column.name)
        result[column.name] = value.isoformat() if hasattr(value, "isoformat") else value
    return result
