from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import models
from app.intelligence.roles import profile_for
from app.intelligence.schemas import EvidenceReference, FactoryContextPacket, PageContext
from app.platform.context import for_user
from app.platform.state import factory_context


ALLOWED_ENTITY_TYPES = {"material", "supplier", "purchase_order", "product", "work_order", "work_center", "equipment", "site", "operational_case"}


class ContextEngine:
    def __init__(self, db: Session, *, max_serialized_bytes: int = 180_000):
        self.db = db
        self.max_serialized_bytes = max_serialized_bytes

    def build(self, user: models.User, page: PageContext) -> FactoryContextPacket:
        scope = for_user(self.db, user)
        if not scope.membership_id:
            raise HTTPException(403, "Active workspace membership required")
        if page.entity_type and page.entity_type not in ALLOWED_ENTITY_TYPES:
            raise HTTPException(422, "Unsupported entity context")
        if page.entity_id and not page.entity_type:
            raise HTTPException(422, "entity_type is required with entity_id")
        # FactoryStateService performs tenant-scoped lookup; a forged entity ID
        # becomes unavailable rather than crossing scope.
        state = factory_context(self.db, scope.tenant_id, scope.plant_id,
                                entity_type=page.entity_type, entity_id=page.entity_id)
        if page.entity_type == "operational_case" and page.entity_id:
            from app.platform.models import OperationalCase
            from app.platform.case_service import serialize_case
            case = self.db.query(OperationalCase).filter_by(id=page.entity_id,
                tenant_id=scope.tenant_id, plant_id=scope.plant_id).first()
            state["entity_state"] = serialize_case(self.db, case) if case else None
        if page.entity_id and not state.get("entity_state"):
            raise HTTPException(404, "Entity is unavailable in this workspace and plant")
        evidence: list[EvidenceReference] = []
        if state.get("case_attention"):
            evidence.append(EvidenceReference(ref="context.active_cases", source_type="operational_case",
                label="Active operational cases", path="factory.case_attention"))
        if state.get("recent_planning_runs"):
            evidence.append(EvidenceReference(ref="context.recent_planning_runs", source_type="scm_planning",
                label="Two most recent completed planning runs", path="factory.recent_planning_runs"))
        if page.entity_id:
            evidence.append(EvidenceReference(ref="context.entity", source_type=page.entity_type or "entity",
                source_id=page.entity_id, label="Selected canonical entity", path="factory.entity_state"))
        packet = FactoryContextPacket(tenant_id=scope.tenant_id, plant_id=scope.plant_id,
            user_id=user.id, membership_id=scope.membership_id, role=user.role,
            role_profile=profile_for(user.role).key, authorities=sorted(scope.authorities),
            page=page, factory=state, evidence=evidence)
        if len(json.dumps(packet.model_dump(mode="json"), default=str).encode()) > self.max_serialized_bytes:
            packet.factory = {"tenant_id": scope.tenant_id, "plant": state.get("plant"),
                              "case_attention": state.get("case_attention", [])[:20],
                              "recent_planning_runs": state.get("recent_planning_runs", [])[:2], "entity_type": page.entity_type,
                              "entity_id": page.entity_id, "entity_state": state.get("entity_state")}
            packet.warnings.append("Context was compressed to the configured safety budget.")
        return packet
