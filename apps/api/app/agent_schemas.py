from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AgentContextEnvelope(BaseModel):
    tenant_id: str
    workspace_id: str
    plant_id: str
    membership_id: str
    role: str
    reporting_scope: list[str] = Field(default_factory=list)
    thread_id: str
    thread_type: str
    thread_owner_membership_id: str
    objective_id: str | None = None
    work_item_id: str | None = None
    allowed_entity_ids: dict[str, list[str]] = Field(default_factory=dict)
    approved_knowledge_ids: list[str] = Field(default_factory=list)
    read_tools: list[str] = Field(default_factory=list)
    draft_tools: list[str] = Field(default_factory=list)
    delegation_tools: list[str] = Field(default_factory=list)
    proposal_tools: list[str] = Field(default_factory=list)
    restricted_actions: list[str] = Field(default_factory=list)
    token_budget: int
    maximum_run_seconds: int
    maximum_handoffs: int
    maximum_delegation_depth: int
    correlation_id: str
    policy_version: str


class WorkspaceCreateRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=180)
    workspace_name: str = Field(min_length=2, max_length=180)
    plant_name: str = Field(min_length=2, max_length=180)
    plant_code: str = Field(min_length=2, max_length=64)
    agent_enabled: bool = False


class WorkspaceSelectRequest(BaseModel):
    membership_id: str


class WorkspaceAgentPolicyRequest(BaseModel):
    enabled: bool


class ObjectiveCreateRequest(BaseModel):
    material: str = Field(min_length=2, max_length=240)
    quantity: float = Field(gt=0)
    uom: str = Field(min_length=1, max_length=24)
    need_by_date: str = Field(min_length=8, max_length=32)
    reason: str = Field(min_length=3, max_length=4000)
    constraints: dict[str, Any] = Field(default_factory=dict)
    assignee_membership_id: str | None = None


class ObjectiveUpdateRequest(BaseModel):
    reason: str | None = Field(default=None, min_length=3, max_length=4000)
    constraints: dict[str, Any] | None = None
    state: Literal["draft", "active", "paused", "completed", "cancelled"] | None = None


class ThreadCreateRequest(BaseModel):
    thread_type: Literal["personal", "work_item", "objective", "team_follow_up"]
    title: str = Field(min_length=2, max_length=240)
    work_item_id: str | None = None
    objective_id: str | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.thread_type == "work_item" and not self.work_item_id:
            raise ValueError("work_item_id is required for a work-item thread")
        if self.thread_type == "objective" and not self.objective_id:
            raise ValueError("objective_id is required for an objective thread")
        return self


class SelectedAgentContext(BaseModel):
    entity_type: str | None = None
    entity_id: str | None = None
    business_number: str | None = None
    source: str | None = None


class AgentMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=20)
    # UI actions are capabilities, not prose prompts.  The server still validates
    # the capability against the active membership before it is executed.
    requested_capability: str | None = Field(default=None, max_length=120)
    selected_context: SelectedAgentContext | None = None


class AttachmentResolutionRequest(BaseModel):
    rfq_id: str | None = Field(default=None, max_length=64)
    supplier_id: str | None = Field(default=None, max_length=64)
    version: int = Field(ge=1)


class IntentEnvelope(BaseModel):
    intent: str = Field(min_length=2, max_length=120)
    requested_outcome: str = Field(min_length=1, max_length=4000)
    entities: dict[str, Any] = Field(default_factory=dict)
    referenced_entity_ids: list[str] = Field(default_factory=list, max_length=20)
    attachment_ids: list[str] = Field(default_factory=list, max_length=20)
    missing_fields: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)
    is_topic_change: bool = False
    requires_confirmation: bool = False


class AgentGoalState(BaseModel):
    capability: str | None = None
    status: Literal['idle', 'resolving', 'ready', 'blocked', 'completed'] = 'idle'
    started_at: datetime | None = None


class RecentBusinessEntity(BaseModel):
    entity_type: str
    entity_id: str
    business_number: str | None = None
    label: str | None = None
    created_or_used_at: datetime | None = None


class AgentThreadStateV3(BaseModel):
    schema_version: Literal[3] = 3
    active_goal: AgentGoalState = Field(default_factory=AgentGoalState)
    selected_context: SelectedAgentContext = Field(default_factory=SelectedAgentContext)
    recent_entities: list[RecentBusinessEntity] = Field(default_factory=list, max_length=12)
    draft_fields: dict[str, Any] = Field(default_factory=dict)
    field_provenance: dict[str, dict[str, Any]] = Field(default_factory=dict)
    candidate_set: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
    pending_proposal_id: str | None = None
    pending_confirmation: dict[str, Any] | None = None
    last_receipt: dict[str, Any] | None = None
    last_execution: dict[str, Any] | None = None
    material_master_request_id: str | None = None
    # Message attachments are the source of truth.  State retains stable
    # references only; lifecycle and inference fields are hydrated from rows.
    attachment_refs: list[str] = Field(default_factory=list, max_length=20)
    unresolved_fields: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    candidate_mappings: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    continuation_status: Literal[
        'idle', 'resolving', 'processing', 'needs_input', 'completed', 'blocked', 'failed'
    ] = 'idle'
    blocked_on: str | None = None
    last_user_correction: dict[str, Any] | None = None
    updated_at: datetime | None = None


# Import compatibility while callers migrate to the V3 name.
AgentThreadStateV2 = AgentThreadStateV3


class BusinessRecordRef(BaseModel):
    entity_type: str
    entity_id: str
    business_number: str | None = None
    label: str | None = None


class AllowedActionRef(BaseModel):
    id: str
    label: str
    href: str | None = None
    controlled: bool = False


class ToolResult(BaseModel):
    status: Literal['observed', 'completed', 'needs_clarification', 'blocked', 'proposal_created', 'processing', 'failed']
    business_summary: str
    records: list[BusinessRecordRef] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    allowed_next_actions: list[AllowedActionRef] = Field(default_factory=list)
    proposal: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    job: dict[str, Any] | None = None

    @model_validator(mode='after')
    def mutation_requires_receipt(self):
        if self.status == 'completed' and not self.receipt:
            raise ValueError('Completed mutations require a persisted receipt')
        return self


class AgentResponseBlock(BaseModel):
    type: Literal[
        'text', 'source_list', 'record_summary', 'field_review',
        'comparison_preview', 'task_preview', 'artifact_preview',
        'action_proposal', 'approval_request', 'run_progress',
        'warning', 'error', 'limited_mode',
        "summary", "section", "bullets", "table", "missing_information",
        "sources", "proposed_actions", "confirmation",
        'action_receipt', 'role_handoff',
        'message', 'clarification', 'record_created', 'action_required',
        'prepared_artifact', 'task_update', 'team_summary',
        'agent_activity',
    ]
    title: str | None = Field(default=None, max_length=180)
    text: str | None = Field(default=None, max_length=8000)
    items: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    record: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[dict[str, Any]] = Field(default_factory=list)


class ProposalCreateRequest(BaseModel):
    thread_id: str
    run_id: str | None = None
    action: Literal[
        "publish_rfq",
        "submit_comparison",
        "decide_comparison",
        "record_gate_entry",
        "record_store_receipt",
        "confirm_purchase_order",
        "approve_negotiation",
        "approve_award",
        "approve_po_draft",
        "prepare_po_supplier_email",
        "approve_po_change",
        "prepare_supplier_followup",
        "verify_quote_fields",
        "create_asn",
        "dispatch_outbox",
        "record_inspection",
        "close_case",
        "prepare_finance_handoff",
        "approve_excel_import",
        "request_supplier_replacement",
        "record_replacement_receipt",
        "decide_supplier_certificate",
        "close_requirement_lifecycle",
    ]
    target_entity_type: str
    target_entity_id: str
    preview: dict[str, Any] = Field(default_factory=dict)
    expected_effect: str = Field(min_length=3, max_length=2000)
    required_authority: str
    record_version: int | None = None


class ProposalDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class DelegationCreateRequest(BaseModel):
    recipient_membership_id: str
    objective_id: str | None = None
    work_item_id: str | None = None
    requested_outcome: str = Field(min_length=3, max_length=4000)
    due_at: datetime | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    expected_deliverable: str | None = Field(default=None, max_length=4000)
    required_evidence: list[str] = Field(default_factory=list)
    kind: Literal["assignment", "collaboration_request"] = "collaboration_request"


class DelegationResponseRequest(BaseModel):
    status: Literal["accepted", "clarification_requested", "in_progress", "completed", "declined", "escalated"]
    summary: str = Field(min_length=1, max_length=4000)
    commitment_at: datetime | None = None
    blocker: str | None = Field(default=None, max_length=2000)


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    requested_outcome: str = Field(min_length=3, max_length=4000)
    assignee_membership_id: str
    due_at: datetime | None = None
    priority: Literal['low', 'normal', 'high', 'urgent'] = 'normal'
    task_type: str = Field(default='delegated', min_length=2, max_length=64)
    instructions: str | None = Field(default=None, max_length=8000)
    context_entity_type: str | None = Field(default=None, max_length=64)
    context_entity_id: str | None = Field(default=None, max_length=64)
    expected_output: dict[str, Any] = Field(default_factory=dict)
    parent_task_id: str | None = None


class TaskTransitionRequest(BaseModel):
    status: Literal[
        'accepted', 'in_progress', 'blocked', 'review',
        'completed', 'cancelled',
    ]
    summary: str | None = Field(default=None, max_length=4000)
    blocker_reason: str | None = Field(default=None, max_length=4000)


class TaskFollowUpRequest(BaseModel):
    message: str | None = Field(default=None, max_length=4000)
    next_follow_up_at: datetime | None = None


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    source: str = Field(min_length=2, max_length=240)
    content: str = Field(min_length=10, max_length=250000)
    role_acl: list[str] = Field(default_factory=list)
    plant_acl: list[str] = Field(default_factory=list)
    document_type: Literal["sop", "machine_manual", "maintenance_manual", "fmea", "control_plan", "work_instruction", "quality_procedure", "incident_report", "supplier_spec"] = "sop"
    revision: str = Field(default="1", min_length=1, max_length=64)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    asset_ids: list[str] = Field(default_factory=list)
    product_codes: list[str] = Field(default_factory=list)
    process_codes: list[str] = Field(default_factory=list)


class KnowledgeDecisionRequest(BaseModel):
    decision: Literal["approve", "retire"]


class AgentPolicyUpdateRequest(BaseModel):
    enabled: bool | None = None
    provider: str | None = Field(default=None, max_length=48)
    model_profile: str | None = Field(default=None, max_length=120)
    token_budget: int | None = Field(default=None, ge=100, le=100000)
    monthly_token_budget: int | None = Field(default=None, ge=1000)
    prompt_version: str | None = Field(default=None, max_length=64)
    policy_version: str | None = Field(default=None, max_length=64)


class AgentFeedbackRequest(BaseModel):
    helpfulness: int | None = Field(default=None, ge=1, le=5)
    correctness: int | None = Field(default=None, ge=1, le=5)
    citation_quality: int | None = Field(default=None, ge=1, le=5)
    rejected: bool = False
    comment: str | None = Field(default=None, max_length=4000)


class InvitationCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=180)
    role: str
    department_id: str | None = None
    plant_ids: list[str] = Field(default_factory=list)
    manager_membership_id: str | None = None


class AgentProcurementFacts(BaseModel):
    material_query: str | None = Field(default=None, max_length=240)
    item_code: str | None = Field(default=None, max_length=80)
    quantity: float | None = Field(default=None, gt=0)
    uom: str | None = Field(default=None, max_length=24)
    need_by_date: str | None = Field(default=None, max_length=32)
    reason: str | None = Field(default=None, max_length=2000)
    specification: str | None = Field(default=None, max_length=2000)
    supplier_master_confirmed: bool | None = None


class AgentTurnDecision(BaseModel):
    intent: Literal[
        'answer', 'procurement', 'delegate_procurement',
        'prepare_rfq', 'prepare_comparison', 'prepare_po',
        'task_follow_up',
    ] = 'answer'
    facts: AgentProcurementFacts = Field(default_factory=AgentProcurementFacts)
    explicit_execute: bool = False
    answer: str = Field(min_length=1, max_length=8000)


class InvitationAcceptRequest(BaseModel):
    token: str
    name: str = Field(min_length=2, max_length=140)
    password: str = Field(min_length=10, max_length=256)


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=180)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    password: str = Field(min_length=10, max_length=256)


class EvidenceCitation(BaseModel):
    entity_type: str
    entity_id: str
    label: str
    version: int | None = None
    excerpt: str | None = Field(default=None, max_length=1000)


class SpecialistRequest(BaseModel):
    specialist: str
    objective_id: str
    task_id: str | None = None
    requested_outcome: str = Field(min_length=3, max_length=4000)
    authorized_artifact_ids: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str


class ProposedEffect(BaseModel):
    capability_id: str
    target_entity_type: str
    target_entity_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_effect: str
    reversible: bool


class SpecialistFinding(BaseModel):
    finding_type: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceCitation] = Field(min_length=1)


class SpecialistResult(BaseModel):
    findings: list[SpecialistFinding] = Field(default_factory=list)
    prepared_work: list[dict[str, Any]] = Field(default_factory=list)
    proposed_effects: list[ProposedEffect] = Field(default_factory=list)
    deterministic_outputs: dict[str, Any] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    allow: bool
    requires_confirmation: bool
    autonomy_tier: int = Field(ge=0, le=4)
    obligations: list[str] = Field(default_factory=list)
    reason_code: str
    policy_version: str
    shadow: bool = False


class ExecutionReceipt(BaseModel):
    receipt_id: str
    correlation_id: str
    capability_id: str
    status: str
    target_entity_type: str | None = None
    target_entity_id: str | None = None
    policy_decision_id: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
