from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.intelligence.schemas import EvidenceReference, FactoryContextPacket, SideEffect
from app.platform.relationships import get_impact, get_neighbors
from app.platform.state import FactoryStateService


class EntityInput(BaseModel):
    entity_type: str = Field(max_length=80)
    entity_id: str = Field(max_length=64)


class ToolResult(BaseModel):
    data: dict[str, Any]
    evidence: list[EvidenceReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


Handler = Callable[[Session, FactoryContextPacket, BaseModel], ToolResult]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    domain: str
    side_effect: SideEffect
    input_schema: type[BaseModel]
    handler: Handler
    roles: frozenset[str]
    timeout_seconds: float = 10


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Duplicate tool: {definition.name}")
        if definition.side_effect == SideEffect.EXTERNAL_ACTION:
            raise ValueError("Gigi must never receive an external-action tool")
        self._tools[definition.name] = definition

    def available(self, context: FactoryContextPacket) -> list[ToolDefinition]:
        return [tool for tool in self._tools.values() if not tool.roles or context.role_profile in tool.roles]

    def execute(self, name: str, db: Session, context: FactoryContextPacket, arguments: dict[str, Any]) -> tuple[ToolResult, int, str]:
        tool = self._tools.get(name)
        if not tool or tool not in self.available(context):
            raise PermissionError(f"Tool is unavailable: {name}")
        parsed = tool.input_schema.model_validate(arguments)
        started = time.monotonic()
        result = tool.handler(db, context, parsed)
        latency = int((time.monotonic() - started) * 1000)
        digest = hashlib.sha256(json.dumps(result.model_dump(mode="json"), sort_keys=True, default=str).encode()).hexdigest()
        return result, latency, digest


def _state(db: Session, context: FactoryContextPacket, payload: EntityInput) -> ToolResult:
    value = FactoryStateService(db, context.tenant_id, context.plant_id).now(payload.entity_type, payload.entity_id)
    if value is None:
        return ToolResult(data={}, warnings=["No authorized current state was found."])
    return ToolResult(data=value, evidence=[EvidenceReference(ref=f"state:{payload.entity_type}:{payload.entity_id}",
        source_type="factory_state", source_id=payload.entity_id, label=f"Current {payload.entity_type} state",
        path="data", freshness=str(value.get("freshness", {}).get("status", "unknown")))])


def _neighbors(db: Session, context: FactoryContextPacket, payload: EntityInput) -> ToolResult:
    rows = get_neighbors(db, context.tenant_id, payload.entity_type, payload.entity_id)
    return ToolResult(data={"relationships": rows}, evidence=[EvidenceReference(
        ref=f"graph:{payload.entity_type}:{payload.entity_id}", source_type="relationship_graph",
        source_id=payload.entity_id, label="Canonical relationship graph", path="data.relationships")])


def _impact(db: Session, context: FactoryContextPacket, payload: EntityInput) -> ToolResult:
    value = get_impact(db, context.tenant_id, payload.entity_type, payload.entity_id)
    return ToolResult(data=value, evidence=[EvidenceReference(ref=f"impact:{payload.entity_type}:{payload.entity_id}",
        source_type="relationship_graph", source_id=payload.entity_id, label="Downstream impact traversal", path="data")])


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    roles = frozenset({"scm_planner", "procurement_buyer", "manager", "leadership", "operator"})
    registry.register(ToolDefinition("factory.entity_state", "1", "factory", SideEffect.READ_ONLY, EntityInput, _state, roles))
    registry.register(ToolDefinition("factory.relationships", "1", "factory", SideEffect.READ_ONLY, EntityInput, _neighbors, roles))
    registry.register(ToolDefinition("factory.downstream_impact", "1", "factory", SideEffect.READ_ONLY, EntityInput, _impact, roles))
    return registry


REGISTRY = default_registry()
