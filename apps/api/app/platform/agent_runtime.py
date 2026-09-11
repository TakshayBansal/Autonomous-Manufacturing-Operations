"""Policy-safe context and typed tools for all module agents."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import models
from app.platform import actions
from app.platform.context import for_user
from app.platform.state import factory_context
from app.platform.work import list_work


READ_TOOLS = frozenset({"factory_context.read", "work_queue.read", "case.read", "catalog.read"})
ACTION_TOOLS = frozenset({"action.propose"})


def build_agent_context(db: Session, user: models.User, *, entity_type: str | None = None,
                        entity_id: str | None = None) -> dict:
    context = for_user(db, user)
    return {"scope": context.__dict__, "factory": factory_context(db, context.tenant_id, context.plant_id,
                                                                    entity_type=entity_type, entity_id=entity_id),
            "work": [{"id": row.id, "title": row.title, "status": row.status, "due_at": row.due_at,
                      "entity_type": row.entity_type, "entity_id": row.entity_id} for row in list_work(
                          db, tenant_id=context.tenant_id, plant_id=context.plant_id, user_id=user.id)[:25]],
            "tool_contract": {"read": sorted(READ_TOOLS), "mutations": sorted(ACTION_TOOLS),
                              "direct_critical_writes": False}}


def propose_agent_action(db: Session, user: models.User, *, action_type: str, target_type: str,
                         target_id: str, payload: dict, rationale: str, idempotency_key: str):
    context = for_user(db, user)
    return actions.propose(db, tenant_id=context.tenant_id, plant_id=context.plant_id,
                           membership_id=context.membership_id, action_type=action_type,
                           target_type=target_type, target_id=target_id, payload=payload,
                           rationale=rationale, idempotency_key=idempotency_key)
