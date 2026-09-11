"""Single gateway for all agent-originated effects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent_capabilities import CAPABILITY_REGISTRY
from app.agent_schemas import ExecutionReceipt
from app.core.config import get_settings
from app.db import models
from app.policy_decision import PolicyDecisionService


@dataclass(frozen=True)
class ExecutionContext:
    membership: models.WorkspaceMembership
    correlation_id: str
    idempotency_key: str
    capability_id: str
    resource_type: str
    resource_id: str | None
    expected_version: int | None
    workflow_stage: str | None = None
    spend: float | None = None
    risk: str = "low"
    external_effect: bool = False


class GovernedExecutionGateway:
    def __init__(self, db: Session):
        self.db = db

    def execute(self, context: ExecutionContext, resolver: Callable[[], Any],
                canonical_service: Callable[[Any], dict[str, Any]]) -> ExecutionReceipt:
        capability = CAPABILITY_REGISTRY.get(context.capability_id)
        if capability is None:
            raise HTTPException(status_code=422, detail="Unknown capability")
        existing = self.db.query(models.AgentActionReceipt).filter_by(idempotency_key=context.idempotency_key).first()
        if existing:
            return ExecutionReceipt(receipt_id=existing.id, correlation_id=context.correlation_id,
                capability_id=context.capability_id, status=existing.status,
                target_entity_type=existing.target_entity_type, target_entity_id=existing.target_entity_id,
                result=existing.result_summary)
        decision, decision_record = PolicyDecisionService(self.db).decide(
            actor=context.membership, capability_id=context.capability_id,
            resource_type=context.resource_type, resource_id=context.resource_id,
            context={"tenant_id": context.membership.tenant_id, "plant_id": context.membership.default_plant_id,
                     "workflow_stage": context.workflow_stage, "spend": context.spend, "risk": context.risk,
                     "autonomy_tier": capability.autonomy_ceiling, "reversible": capability.reversible,
                     "external_effect": context.external_effect}, read_only=capability.effect_type == "read",
            correlation_id=context.correlation_id)
        if get_settings().opa_mode == "enforce" and not decision.allow:
            raise HTTPException(status_code=403, detail=f"Policy denied execution: {decision.reason_code}")
        if decision.requires_confirmation or capability.controlled:
            raise HTTPException(status_code=409, detail="A fresh authorized human confirmation is required")
        entity = resolver()
        if entity is not None:
            if getattr(entity, "tenant_id", None) != context.membership.tenant_id:
                raise HTTPException(status_code=404, detail="Referenced entity was not found")
            if context.expected_version is not None and getattr(entity, "version", None) != context.expected_version:
                raise HTTPException(status_code=412, detail="Entity version is stale")
        result = canonical_service(entity)
        receipt = models.AgentActionReceipt(
            tenant_id=context.membership.tenant_id, plant_id=context.membership.default_plant_id,
            run_id="governed-execution", tool_name=context.capability_id, status="succeeded",
            target_entity_type=context.resource_type, target_entity_id=context.resource_id,
            result_summary={**result, "policy_decision_id": decision_record.id},
            executed_by_membership_id=context.membership.id, idempotency_key=context.idempotency_key,
        )
        self.db.add(receipt)
        self.db.flush()
        return ExecutionReceipt(receipt_id=receipt.id, correlation_id=context.correlation_id,
            capability_id=context.capability_id, status=receipt.status,
            target_entity_type=receipt.target_entity_type, target_entity_id=receipt.target_entity_id,
            policy_decision_id=decision_record.id, result=result)
