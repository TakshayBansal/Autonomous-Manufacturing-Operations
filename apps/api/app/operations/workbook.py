"""Operations-owned workbook records consumed by the shared ingestion surface."""
from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.db import models


class SourceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=120)


class LineRow(SourceRow):
    code: str
    name: str
    standard_good_rate_per_minute: float = Field(gt=0)


class OrderRow(SourceRow):
    line_code: str
    product_code: str
    product_name: str
    quantity: float = Field(gt=0)
    planned_start_at: datetime
    planned_end_at: datetime

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.planned_start_at.tzinfo is None or self.planned_end_at.tzinfo is None:
            raise ValueError("Production timestamps require an explicit timezone")
        if self.planned_end_at <= self.planned_start_at:
            raise ValueError("Production end must follow start")
        return self


class RequirementRow(SourceRow):
    work_order_external_id: str
    material_code: str
    quantity: float = Field(gt=0)
    uom: str
    required_at: datetime


SCHEMAS = {"Lines": LineRow, "WorkOrders": OrderRow, "MaterialRequirements": RequirementRow}


def source_id(user: models.User, sheet: str, external_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"unified:{user.tenant_id}:{user.plant_id}:{sheet}:{external_id}"))


def apply_row(db: Session, user: models.User, sheet: str, values: dict):
    row = SCHEMAS[sheet].model_validate(values)
    identity = source_id(user, sheet, row.external_id)
    scope = {"tenant_id": user.tenant_id, "plant_id": user.plant_id}
    if isinstance(row, LineRow):
        area_id = source_id(user, "area", "workbook")
        if not db.get(models.PlantArea, area_id):
            db.add(models.PlantArea(id=area_id, **scope, code="WORKBOOK", name="Imported production")); db.flush()
        entity = db.get(models.ProductionLine, identity)
        if not entity:
            entity = models.ProductionLine(id=identity, **scope, area_id=area_id, code=row.code, name=row.name)
            db.add(entity)
        entity.code, entity.name = row.code, row.name
        entity.standard_good_rate_per_minute = row.standard_good_rate_per_minute
    elif isinstance(row, OrderRow):
        line = db.query(models.ProductionLine).filter_by(**scope, code=row.line_code).one_or_none()
        if not line:
            raise ValueError(f"Unknown production line {row.line_code}")
        shift_id = source_id(user, "shift", f"{row.planned_start_at.isoformat()}:{row.planned_end_at.isoformat()}")
        shift = db.get(models.PlantShift, shift_id)
        if not shift:
            shift = models.PlantShift(id=shift_id, **scope, code="IMPORTED",
                name="Imported production window", starts_at=row.planned_start_at,
                ends_at=row.planned_end_at, status="scheduled")
            db.add(shift); db.flush()
        entity = db.get(models.ProductionWorkOrder, identity)
        if not entity:
            entity = models.ProductionWorkOrder(id=identity, **scope, line_id=line.id, shift_id=shift.id,
                external_reference=row.external_id, product_code=row.product_code,
                product_name=row.product_name, target_quantity=row.quantity,
                planned_start_at=row.planned_start_at, planned_end_at=row.planned_end_at, status="planned")
            db.add(entity)
        entity.line_id, entity.shift_id, entity.product_code, entity.product_name = line.id, shift.id, row.product_code, row.product_name
        entity.target_quantity = row.quantity
        entity.planned_start_at, entity.planned_end_at = row.planned_start_at, row.planned_end_at
    else:
        order = db.get(models.ProductionWorkOrder, source_id(user, "WorkOrders", row.work_order_external_id))
        item = db.query(models.Item).filter_by(**scope, code=row.material_code).one_or_none()
        if not order or not item:
            raise ValueError("Production requirement must reference an imported order and item")
        if item.uom_id != row.uom:
            raise ValueError("Production requirement UOM must match the item master")
        entity = db.get(models.ProductionMaterialRequirement, identity)
        if not entity:
            entity = models.ProductionMaterialRequirement(id=identity, **scope, work_order_id=order.id,
                item_id=item.id, material_code=row.material_code, required_quantity=row.quantity,
                uom=row.uom, required_at=row.required_at)
            db.add(entity)
        entity.required_quantity, entity.required_at = row.quantity, row.required_at
    db.flush()
    return entity
