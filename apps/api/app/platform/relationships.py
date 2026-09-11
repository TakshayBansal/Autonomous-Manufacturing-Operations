"""PostgreSQL-backed canonical relationship graph and bounded traversal."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.platform.models import EntityRelationship


def connect(db: Session, *, tenant_id: str, plant_id: str | None, source_type: str,
            source_id: str, relationship: str, target_type: str, target_id: str,
            source_system: str = "genuinegigs", provenance_id: str | None = None,
            confidence: float = 1.0, valid_from: datetime | None = None,
            valid_to: datetime | None = None, metadata: dict | None = None) -> EntityRelationship:
    row = db.query(EntityRelationship).filter_by(
        tenant_id=tenant_id, source_entity_type=source_type, source_entity_id=source_id,
        relationship_type=relationship, target_entity_type=target_type, target_entity_id=target_id,
    ).first()
    if row is None:
        # Some bulk graph rebuild callers run with autoflush disabled. Reuse a
        # matching pending edge so a multi-line BOM cannot enqueue duplicate
        # product->BOM relationships before the final flush.
        row = next((candidate for candidate in db.new
            if isinstance(candidate, EntityRelationship)
            and candidate.tenant_id == tenant_id
            and candidate.source_entity_type == source_type
            and candidate.source_entity_id == source_id
            and candidate.relationship_type == relationship
            and candidate.target_entity_type == target_type
            and candidate.target_entity_id == target_id), None)
    if row is None:
        row = EntityRelationship(
            tenant_id=tenant_id, plant_id=plant_id, source_entity_type=source_type,
            source_entity_id=source_id, relationship_type=relationship,
            target_entity_type=target_type, target_entity_id=target_id,
        )
        db.add(row)
    row.plant_id = plant_id or row.plant_id
    row.source_system = source_system
    row.provenance_id = provenance_id
    row.confidence = max(0.0, min(float(confidence), 1.0))
    row.valid_from = valid_from or row.valid_from
    row.valid_to = valid_to
    row.attributes = metadata or {}
    return row


def _active(query):
    now = datetime.now(timezone.utc)
    return query.filter(
        or_(EntityRelationship.valid_from.is_(None), EntityRelationship.valid_from <= now),
        or_(EntityRelationship.valid_to.is_(None), EntityRelationship.valid_to > now),
    )


def get_neighbors(db: Session, tenant_id: str, entity_type: str, entity_id: str,
                  *, direction: str = "both", relationship_types: set[str] | None = None) -> list[dict]:
    query = db.query(EntityRelationship).filter(EntityRelationship.tenant_id == tenant_id)
    if direction == "out":
        query = query.filter_by(source_entity_type=entity_type, source_entity_id=entity_id)
    elif direction == "in":
        query = query.filter_by(target_entity_type=entity_type, target_entity_id=entity_id)
    else:
        query = query.filter(or_(
            (EntityRelationship.source_entity_type == entity_type) & (EntityRelationship.source_entity_id == entity_id),
            (EntityRelationship.target_entity_type == entity_type) & (EntityRelationship.target_entity_id == entity_id),
        ))
    if relationship_types:
        query = query.filter(EntityRelationship.relationship_type.in_(relationship_types))
    rows = _active(query).all()
    return [{"id": row.id, "source": {"type": row.source_entity_type, "id": row.source_entity_id},
             "relationship": row.relationship_type,
             "target": {"type": row.target_entity_type, "id": row.target_entity_id},
             "site_id": row.plant_id, "source_system": row.source_system,
             "provenance_id": row.provenance_id, "confidence": row.confidence,
             "metadata": row.attributes} for row in rows]


def traverse(db: Session, tenant_id: str, entity_type: str, entity_id: str, *,
             direction: str = "out", max_depth: int = 6) -> dict:
    start = (entity_type, entity_id)
    queue = deque([(start, 0)])
    seen = {start}
    nodes = [{"type": entity_type, "id": entity_id, "depth": 0}]
    edges: list[dict] = []
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in get_neighbors(db, tenant_id, *current, direction=direction):
            candidate = ((edge["target"]["type"], edge["target"]["id"])
                         if edge["source"] == {"type": current[0], "id": current[1]}
                         else (edge["source"]["type"], edge["source"]["id"]))
            edges.append(edge)
            if candidate not in seen:
                seen.add(candidate)
                nodes.append({"type": candidate[0], "id": candidate[1], "depth": depth + 1})
                queue.append((candidate, depth + 1))
    return {"root": {"type": entity_type, "id": entity_id}, "direction": direction,
            "nodes": nodes, "edges": edges}


def find_paths(db: Session, tenant_id: str, source_type: str, source_id: str,
               target_type: str, target_id: str, *, max_depth: int = 8) -> list[list[dict]]:
    target = (target_type, target_id)
    queue = deque([((source_type, source_id), [{"type": source_type, "id": source_id}])])
    paths: list[list[dict]] = []
    while queue:
        current, path = queue.popleft()
        if len(path) > max_depth:
            continue
        for edge in get_neighbors(db, tenant_id, *current, direction="out"):
            nxt = (edge["target"]["type"], edge["target"]["id"])
            if any(node["type"] == nxt[0] and node["id"] == nxt[1] for node in path):
                continue
            new_path = [*path, {"relationship": edge["relationship"], **edge["target"]}]
            if nxt == target:
                paths.append(new_path)
            else:
                queue.append((nxt, new_path))
    return paths


def get_dependencies(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> dict:
    return traverse(db, tenant_id, entity_type, entity_id, direction="out")


def get_dependents(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> dict:
    return traverse(db, tenant_id, entity_type, entity_id, direction="in")


def get_impact(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> dict:
    # Canonical edges are deliberately oriented in the business-readable
    # direction; impact is therefore bidirectional and bounded.
    return traverse(db, tenant_id, entity_type, entity_id, direction="both")


def sync_tenant_graph(db: Session, tenant_id: str) -> int:
    """Idempotently derive graph edges from canonical and mapped domain data."""
    from app.db import models as core
    from app.platform.models import (ExternalEntityReference, PlatformBOM, PlatformBOMItem,
        PlatformInventoryPosition, PlatformPurchaseOrder, PlatformPurchaseOrderLine,
        PlatformWorkOrderReference)
    before = db.query(EntityRelationship).filter_by(tenant_id=tenant_id).count()
    for item in db.query(PlatformBOMItem).filter_by(tenant_id=tenant_id).all():
        bom = db.get(PlatformBOM, item.bom_id)
        if not bom:
            continue
        connect(db, tenant_id=tenant_id, plant_id=item.plant_id, source_type="product", source_id=bom.product_id,
                relationship="has_bom", target_type="bom", target_id=bom.id, source_system="canonical_backfill")
        connect(db, tenant_id=tenant_id, plant_id=item.plant_id, source_type="bom", source_id=bom.id,
                relationship="requires", target_type=item.component_entity_type, target_id=item.component_id,
                source_system="canonical_backfill")
        if item.component_entity_type == "material":
            connect(db, tenant_id=tenant_id, plant_id=item.plant_id, source_type="material", source_id=item.component_id,
                    relationship="used_in", target_type="product", target_id=bom.product_id, source_system="canonical_backfill")
    for po in db.query(PlatformPurchaseOrder).filter_by(tenant_id=tenant_id).all():
        connect(db, tenant_id=tenant_id, plant_id=po.plant_id, source_type="purchase_order", source_id=po.id,
                relationship="placed_with", target_type="supplier", target_id=po.supplier_id, source_system=po.source_authority)
        for line in db.query(PlatformPurchaseOrderLine).filter_by(purchase_order_id=po.id).all():
            connect(db, tenant_id=tenant_id, plant_id=po.plant_id, source_type="purchase_order", source_id=po.id,
                    relationship="orders", target_type="material", target_id=line.material_id, source_system=po.source_authority)
    for position in db.query(PlatformInventoryPosition).filter_by(tenant_id=tenant_id).all():
        connect(db, tenant_id=tenant_id, plant_id=position.plant_id, source_type="inventory_position", source_id=position.id,
                relationship="stores", target_type="material", target_id=position.material_id,
                source_system=position.source_authority)
        connect(db, tenant_id=tenant_id, plant_id=position.plant_id, source_type="inventory_position", source_id=position.id,
                relationship="located_at", target_type="inventory_location", target_id=position.location_id,
                source_system=position.source_authority)
    for ref in db.query(PlatformWorkOrderReference).filter_by(tenant_id=tenant_id).all():
        connect(db, tenant_id=tenant_id, plant_id=ref.plant_id, source_type="work_order", source_id=ref.work_order_id,
                relationship="produces", target_type="product", target_id=ref.product_id, source_system=ref.source_authority)
        connect(db, tenant_id=tenant_id, plant_id=ref.plant_id, source_type="product", source_id=ref.product_id,
                relationship="scheduled_as", target_type="work_order", target_id=ref.work_order_id, source_system=ref.source_authority)
        connect(db, tenant_id=tenant_id, plant_id=ref.plant_id, source_type="work_order", source_id=ref.work_order_id,
                relationship="executed_on", target_type="work_center", target_id=ref.work_center_id, source_system=ref.source_authority)
        if ref.equipment_id:
            connect(db, tenant_id=tenant_id, plant_id=ref.plant_id, source_type="work_order", source_id=ref.work_order_id,
                    relationship="executed_on", target_type="equipment", target_id=ref.equipment_id, source_system=ref.source_authority)
        for requirement in db.query(core.ProductionMaterialRequirement).filter_by(work_order_id=ref.work_order_id).all():
            mapping = db.query(ExternalEntityReference).filter_by(tenant_id=tenant_id,
                canonical_entity_type="material", external_id=requirement.item_id).first() if requirement.item_id else None
            if mapping:
                connect(db, tenant_id=tenant_id, plant_id=ref.plant_id, source_type="work_order", source_id=ref.work_order_id,
                        relationship="consumes", target_type="material", target_id=mapping.canonical_entity_id,
                        source_system=ref.source_authority)
    for line in db.query(core.ProductionLine).filter_by(tenant_id=tenant_id).all():
        for asset in db.query(core.PlantAsset).filter_by(tenant_id=tenant_id, line_id=line.id).all():
            connect(db, tenant_id=tenant_id, plant_id=line.plant_id, source_type="work_center", source_id=line.id,
                    relationship="contains", target_type="equipment", target_id=asset.id, source_system="operations")
    db.flush()
    return db.query(EntityRelationship).filter_by(tenant_id=tenant_id).count() - before
