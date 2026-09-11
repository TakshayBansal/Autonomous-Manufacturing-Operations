from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Iterable

from app.scm.engine import decimal


class BOMCycleError(ValueError):
    pass


@dataclass(frozen=True)
class BOMComponent:
    component_material_id: str
    quantity_per: Decimal
    scrap_factor: Decimal = Decimal("0")
    uom_id: str = "EA"


@dataclass(frozen=True)
class ExplodedRequirement:
    material_id: str
    quantity: Decimal
    uom_id: str
    path: tuple[str, ...]


def explode_bom(
    parent_material_id: str,
    quantity: Decimal,
    effective_date: date,
    plant_id: str,
    children_for: Callable[[str, date, str], Iterable[BOMComponent]],
) -> tuple[ExplodedRequirement, ...]:
    output: list[ExplodedRequirement] = []

    def walk(material_id: str, required: Decimal, path: tuple[str, ...]) -> None:
        if material_id in path:
            raise BOMCycleError("BOM cycle detected: " + " -> ".join((*path, material_id)))
        children = tuple(children_for(material_id, effective_date, plant_id))
        if not children:
            output.append(ExplodedRequirement(material_id, required, "", (*path, material_id)))
            return
        next_path = (*path, material_id)
        for child in children:
            child_qty = required * decimal(child.quantity_per) * (Decimal("1") + decimal(child.scrap_factor))
            grandchildren = tuple(children_for(child.component_material_id, effective_date, plant_id))
            if grandchildren:
                walk(child.component_material_id, child_qty, next_path)
            else:
                output.append(ExplodedRequirement(child.component_material_id, child_qty, child.uom_id, (*next_path, child.component_material_id)))

    walk(parent_material_id, decimal(quantity), tuple())
    return tuple(output)

