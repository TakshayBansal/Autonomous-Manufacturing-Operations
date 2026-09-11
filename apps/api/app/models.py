from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Role(StrEnum):
    PLANT_MANAGER = "plant_manager"
    PURCHASE_MANAGER = "purchase_manager"
    PURCHASE_EXECUTIVE = "purchase_executive"
    GATE_OPERATOR = "gate_operator"
    STORE_MANAGER = "store_manager"
    QUALITY_INSPECTOR = "quality_inspector"
    ADMIN = "admin"
    PRODUCTION_SUPERVISOR = "production_supervisor"
    PRODUCTION_MANAGER = "production_manager"
    MAINTENANCE_TECHNICIAN = "maintenance_technician"
    MAINTENANCE_MANAGER = "maintenance_manager"
    QUALITY_MANAGER = "quality_manager"
    CORPORATE_OPERATIONS = "corporate_operations"


class Severity(StrEnum):
    INFO = "info"
    ACTION = "action"
    CRITICAL = "critical"
    GOOD = "good"


class WorkflowStatus(StrEnum):
    OPEN = "open"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SIMULATED_POSTED = "simulated_posted"
    RESOLVED = "resolved"
    BLOCKED = "blocked"
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    MONITORING = "monitoring"
    VERIFIED = "verified"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


    ACCEPTED = 'accepted'
    REVIEW = 'review'


class User(BaseModel):
    id: str
    name: str
    role: Role
    department: str
    plant_id: str
    manager_id: str | None = None


class AgentProfile(BaseModel):
    id: str
    user_id: str
    role: Role
    display_name: str
    allowed_actions: list[str]
    blocked_actions: list[str]
    escalation_manager_id: str | None = None


class ProcurementCase(BaseModel):
    id: str
    requirement: str
    supplier: str
    owner_role: Role
    due_label: str
    value_label: str
    status: str
    severity: Severity


class Task(BaseModel):
    id: str
    title: str
    owner_role: Role
    owner_name: str
    due_label: str
    ageing_label: str
    status: WorkflowStatus
    severity: Severity
    linked_case_id: str


class Supplier(BaseModel):
    id: str
    name: str
    status: Literal["approved", "blocked", "conditional"]
    quality_score: int = Field(ge=0, le=100)
    delivery_score: int = Field(ge=0, le=100)
    contact_email: str


class PurchaseRequirement(BaseModel):
    id: str
    source: Literal["material_shortage", "manual"]
    item_id: str
    item_name: str
    quantity: float
    uom: str
    need_by_date: str
    plant_id: str
    status: WorkflowStatus
    owner: str
    related_case_id: str


class RFQLine(BaseModel):
    id: str
    item_id: str
    description: str
    quantity: float
    uom: str
    need_by_date: str
    required_certificates: list[str]


class RFQ(BaseModel):
    id: str
    requirement_id: str
    status: str
    deadline: str
    supplier_ids: list[str]
    lines: list[RFQLine]


class QuoteEvidence(BaseModel):
    field: str
    source: str
    original_text: str
    confidence: float = Field(ge=0, le=1)
    verification_status: Literal["verified", "needs_review", "rejected"]


class QuoteLine(BaseModel):
    id: str
    item_id: str
    quantity: float
    uom: str
    unit_price: float
    gst_rate: float
    freight: float
    packaging: float
    lead_time_days: int
    promised_date: str
    moq: float
    technical_compliance: Literal["compliant", "deviation", "missing_certificate"]
    certificates: list[str]


class SupplierQuote(BaseModel):
    id: str
    rfq_id: str
    supplier_id: str
    quote_number: str
    quote_date: str
    validity_date: str
    payment_terms: str
    parser_version: str
    model_version: str
    verification_status: Literal["verified", "needs_review"]
    lines: list[QuoteLine]
    evidence: list[QuoteEvidence]


class QuoteComparisonRow(BaseModel):
    supplier: str
    landed_cost_label: str
    delivery_status: str
    quality_score_label: str
    commercial_terms: str
    decision: str
    severity: Severity
    disqualification_reason: str | None = None


class BidScore(BaseModel):
    quote_id: str
    supplier_id: str
    supplier_name: str
    net_landed_unit_cost: float
    total_net_landed_cost: float
    delivery_compliant: bool
    technical_compliant: bool
    quality_score: int
    delivery_score: int
    score: float
    disqualified: bool
    reasons: list[str]
    recommendation: str
    base_cost: float = 0
    freight: float = 0
    packaging: float = 0
    recoverable_tax: float = 0
    nonrecoverable_tax: float = 0
    score_components: dict[str, float] = Field(default_factory=dict)
    rfq_line_id: str | None = None
    quote_line_id: str | None = None
    offered_quantity: float = 0
    requested_quantity: float = 0
    source_currency: str = "INR"
    exchange_rate_to_inr: float = 1
    exchange_rate_source: str | None = None
    exchange_rate_observed_at: str | None = None


class EvidenceItem(BaseModel):
    label: str
    value: str
    source: Literal["document", "erp", "audit", "manual"]
    meta: str


class TimelineEvent(BaseModel):
    title: str
    occurred_at_label: str
    actor: str
    body: str


class AgentRecommendation(BaseModel):
    agent_role: Role
    recommended_supplier: str
    primary_reason: str
    tradeoff_label: str
    next_action: str
    requires_human_approval: bool = True
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)


class ControlTowerSnapshot(BaseModel):
    tenant_name: str
    plant_name: str
    erp_mode: Literal["simulated", "read_only", "write_enabled"]
    open_cases: int
    pending_approvals: int
    supplier_exceptions: int
    ai_disabled_ready: bool
    cases: list[ProcurementCase]
    quote_comparison: list[QuoteComparisonRow]
    evidence: list[EvidenceItem]
    timeline: list[TimelineEvent]
    recommendation: AgentRecommendation




class NavItem(BaseModel):
    key: str
    href: str
    label: str
    group: Literal['my_work', 'process_records'] = 'process_records'


class RoleMetric(BaseModel):
    label: str
    value: str
    tone: Literal["critical", "action", "good", "neutral"] = "neutral"
    detail: str | None = None


class WorkflowStage(BaseModel):
    key: str
    label: str
    plain_label: str
    technical_label: str
    status: Literal["done", "current", "blocked", "waiting", "not_started"]
    owner_role: str | None = None
    summary: str | None = None
    href: str
    blocked_reason: str | None = None


class NextAction(BaseModel):
    id: str
    title: str
    description: str
    role: str
    severity: Severity = Severity.ACTION
    entity_type: str | None = None
    entity_id: str | None = None
    path: str | None = None
    body: dict[str, Any] | None = None
    version: int | None = None


class WorkItem(BaseModel):
    id: str
    title: str
    plain_language_goal: str
    technical_term: str
    why_now: str
    expected_result: str
    owner_role: str
    due_at: str | None = None
    severity: Severity = Severity.ACTION
    status: str
    cycle_id: str | None = None
    stage_key: str
    entity_type: str | None = None
    entity_id: str | None = None
    href: str
    required_evidence: list[str] = Field(default_factory=list)
    blocked_by: str | None = None
    allowed_human_actions: list[str] = Field(default_factory=list)
    agent_capabilities: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False


class WorkItemContext(BaseModel):
    work_item: WorkItem
    stage: WorkflowStage | None = None
    linked_object: dict[str, Any] | None = None
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    timeline_references: list[dict[str, Any]] = Field(default_factory=list)
    permitted_agent_capabilities: list[str] = Field(default_factory=list)
    restricted_actions: list[str] = Field(default_factory=list)
    escalation_owner: str | None = None


class WorkflowCycle(BaseModel):
    id: str
    title: str
    subtitle: str
    current_stage: str
    current_owner_role: str
    next_step: str
    severity: Severity
    due_label: str
    stages: list[WorkflowStage]


class BusinessReference(BaseModel):
    id: str
    business_number: str
    label: str
    secondary_context: str | None = None
    status: str | None = None
    route: str | None = None


class ActionableWorkItem(BaseModel):
    id: str
    title: str
    cycle: BusinessReference
    material: BusinessReference | None = None
    rfq: BusinessReference | None = None
    supplier: BusinessReference | None = None
    stage_index: int
    stage_count: int = 8
    stage_label: str
    due_state: str
    blocker: str | None = None
    current_owner: str
    required_authority: str
    required_evidence: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    primary_route: str


class ProcurementCycleSummary(BaseModel):
    id: str
    business_number: str
    title: str
    materials: list[BusinessReference] = Field(default_factory=list)
    rfqs: list[BusinessReference] = Field(default_factory=list)
    health: Literal["on_track", "attention", "at_risk", "blocked"]
    current_stage: WorkflowStage
    current_stage_index: int
    next_stage: str | None = None
    next_owner: str
    blocked_dependency: str | None = None
    completion_percentage: int
    need_by_date: str | None = None
    due_at: str | None = None
    role_visible_actions: list[str] = Field(default_factory=list)
    stages: list[WorkflowStage] = Field(default_factory=list)


class WorkloadBar(BaseModel):
    label: str
    value: int
    total: int
    tone: Literal["critical", "action", "good", "neutral"] = "neutral"


class WorkspaceOverview(BaseModel):
    role: Role
    default_route: str
    nav_items: list[NavItem]
    capabilities: list[str] = Field(default_factory=list)
    metrics: list[RoleMetric]
    cycles: list[WorkflowCycle]
    next_actions: list[NextAction]
    work_items: list[WorkItem]
    waiting_on: list[NextAction]
    team_workload: list[WorkloadBar] = Field(default_factory=list)
    team_queue: list[Task] = Field(default_factory=list)
    delegated_tasks: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    assistant_status: dict[str, Any] = Field(default_factory=dict)
    delegation_targets: list[dict[str, Any]] = Field(default_factory=list)

class NegotiationRound(BaseModel):
    id: str
    rfq_id: str
    supplier_id: str
    round_number: int
    target: str
    drafted_message: str
    status: Literal["draft", "manager_approved", "supplier_countered"]
    revised_unit_price: float | None = None


class PODraft(BaseModel):
    id: str
    award_id: str
    supplier_id: str
    status: WorkflowStatus
    oracle_mapping: dict[str, Any]
    simulated_posting_correlation_id: str | None = None


class InboundEvent(BaseModel):
    id: str
    po_draft_id: str
    event_type: Literal["acknowledgement", "asn", "gate_entry", "store_receipt", "inspection"]
    status: str
    details: dict[str, Any]
    timestamp: str


class OutboxMessage(BaseModel):
    id: str
    channel: Literal["email", "erp", "internal"]
    recipient: str
    subject: str
    status: Literal["approved_pending_send", "simulated", "pending_approval", "sent", "failed", "blocked"]
    payload_hash: str
    correlation_id: str | None = None


class AuditEvent(BaseModel):
    id: str
    actor: str
    action: str
    entity: str
    result: Literal["success", "blocked", "simulated"]
    timestamp: str
    correlation_id: str
    payload_hash: str


class AgentActionRequest(BaseModel):
    agent_id: str
    action: str
    context_id: str


class AgentActionResponse(BaseModel):
    agent_id: str
    action: str
    allowed: bool
    result: str
    created_task_id: str | None = None
    audit_event_id: str
