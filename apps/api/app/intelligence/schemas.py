from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelClass(StrEnum):
    FAST = "FAST"
    REASONING = "REASONING"
    EXTRACTION = "EXTRACTION"
    EMBEDDING = "EMBEDDING"


class SideEffect(StrEnum):
    READ_ONLY = "READ_ONLY"
    SIMULATION = "SIMULATION"
    WORK_MUTATION = "WORK_MUTATION"
    ACTION_PROPOSAL = "ACTION_PROPOSAL"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"


class EvidenceReference(BaseModel):
    ref: str
    source_type: str
    source_id: str | None = None
    label: str
    observed_at: datetime | None = None
    freshness: str | None = None
    path: str | None = None


class PageContext(BaseModel):
    module: Literal["home", "cases", "work", "decisions", "procurement", "scm", "operations", "platform"] | None = None
    route: str | None = Field(default=None, max_length=300)
    entity_type: str | None = Field(default=None, max_length=80)
    entity_id: str | None = Field(default=None, max_length=64)
    filters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class FactoryContextPacket(BaseModel):
    tenant_id: str
    plant_id: str
    user_id: str
    membership_id: str
    role: str
    role_profile: str
    authorities: list[str]
    page: PageContext
    factory: dict[str, Any]
    evidence: list[EvidenceReference]
    warnings: list[str] = Field(default_factory=list)


class GigiMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    page_context: PageContext = Field(default_factory=PageContext)
    idempotency_key: str | None = Field(default=None, max_length=160)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    page_context: PageContext = Field(default_factory=PageContext)


class ActionCandidate(BaseModel):
    action_type: str
    target_type: str
    target_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str
    expected_impact: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    risk_level: str = "medium"
    requires_approval: bool = True


class GigiResponse(BaseModel):
    answer: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    available_actions: list[ActionCandidate] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)


class ActionProposalRequest(BaseModel):
    action: ActionCandidate
    idempotency_key: str = Field(min_length=8, max_length=160)
    originating_case_id: str | None = None


class FeedbackRequest(BaseModel):
    helpfulness: int | None = Field(default=None, ge=1, le=5)
    correctness: int | None = Field(default=None, ge=1, le=5)
    citation_quality: int | None = Field(default=None, ge=1, le=5)
    rejected: bool = False
    comment: str | None = Field(default=None, max_length=2000)
