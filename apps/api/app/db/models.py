from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ScopedMixin:
    # UUIDs are stored in their canonical textual form so SQLite development and
    # PostgreSQL production use the same API representation.
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid4()))
    # Business references are unique inside a workspace, not globally across
    # unrelated customers. Migration 0027 enforces (tenant_id, business_number).
    business_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @declared_attr
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(32), default="active")
    slug: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    workspace_kind: Mapped[str] = mapped_column(String(32), default="demo")
    onboarding_status: Mapped[str] = mapped_column(String(48), default="complete")
    agent_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    feature_flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140))
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    backup_code_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    default_plant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    department_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64), index=True)
    manager_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("account_id", "tenant_id", name="uq_account_workspace_membership"),)


class OperationalScope(Base):
    """Explicit least-privilege scope for a workspace membership.

    Empty object lists mean all objects in an allowed plant.  Authorities are
    business actions (not UI flags) and are checked by V2 mutation endpoints.
    """
    __tablename__ = "operational_scopes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    membership_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace_memberships.id", ondelete="CASCADE"), unique=True, index=True)
    plant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    area_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    line_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    authorities: Mapped[list[str]] = mapped_column(JSON, default=list)
    financial_visibility: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    email: Mapped[str] = mapped_column(String(180), index=True)
    role: Mapped[str] = mapped_column(String(64))
    department_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    manager_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    invited_by_membership_id: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdentityToken(Base):
    __tablename__ = "identity_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(180), index=True)
    purpose: Mapped[str] = mapped_column(String(48), index=True)
    token_hash: Mapped[str] = mapped_column(String(160), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenantFeatureFlag(Base):
    __tablename__ = "tenant_feature_flags"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_by_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_feature_flag"),)


class BusinessNumberSequence(Base):
    __tablename__ = "business_number_sequences"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_id: Mapped[str] = mapped_column(String(64), index=True)
    prefix: Mapped[str] = mapped_column(String(24))
    year: Mapped[int] = mapped_column(Integer)
    next_value: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "plant_id", "prefix", "year", name="uq_business_number_scope"),
        CheckConstraint("next_value > 0", name="ck_business_number_next_positive"),
    )


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(180))
    erp_code: Mapped[str] = mapped_column(String(64))


class Plant(Base):
    __tablename__ = "plants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    company_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(180))
    erp_location_code: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    locale: Mapped[str] = mapped_column(String(32), default="en-US")
    status: Mapped[str] = mapped_column(String(24), default="active")


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120))


class RoleDefinition(Base):
    __tablename__ = "role_definitions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __mapper_args__ = {"version_id_col": version}


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_id: Mapped[str] = mapped_column(String(64), index=True)
    department_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(140))
    email: Mapped[str] = mapped_column(String(180), index=True)
    role: Mapped[str] = mapped_column(String(64), index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    manager_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __mapper_args__ = {"version_id_col": version}


class ReportingLine(Base):
    __tablename__ = "reporting_lines"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    manager_user_id: Mapped[str] = mapped_column(String(64))
    report_user_id: Mapped[str] = mapped_column(String(64))


class UserPlantAccess(Base):
    __tablename__ = "user_plant_access"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plant_id: Mapped[str] = mapped_column(String(64), ForeignKey("plants.id", ondelete="CASCADE"), index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "plant_id", name="uq_user_plant_access"),)
    __mapper_args__ = {"version_id_col": version}


class AgentProfile(Base):
    __tablename__ = "agent_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(180))
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    blocked_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    escalation_manager_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), default="role-playbook@1")
    policy_version: Mapped[str] = mapped_column(String(64), default="agent-policy@1")
    provider: Mapped[str] = mapped_column(String(48), default="groq")
    model_profile: Mapped[str] = mapped_column(String(120), default="openai/gpt-oss-120b")
    token_budget: Mapped[int] = mapped_column(Integer, default=8000)
    monthly_token_budget: Mapped[int] = mapped_column(Integer, default=1_000_000)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Task(Base, ScopedMixin):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(240))
    owner_role: Mapped[str] = mapped_column(String(64), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    parent_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    objective_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    delegation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    creator_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assignment_source: Mapped[str] = mapped_column(String(48), default="workflow")
    shared_queue: Mapped[bool] = mapped_column(Boolean, default=False)
    acceptance_status: Mapped[str] = mapped_column(String(32), default="accepted")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    linked_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), default='workflow', index=True)
    requested_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(24), default='normal', index=True)
    delegated_by_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    expected_output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    blocker_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    source_agent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    semantic_key: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_effort_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_impact: Mapped[str] = mapped_column(String(32), default="normal")
    production_impact: Mapped[str] = mapped_column(String(32), default="none")
    last_meaningful_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocker_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    blocker_owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_result: Mapped[str | None] = mapped_column(String(48), nullable=True)
    __table_args__ = (
        Index(
            'uq_tasks_active_semantic_key', 'tenant_id', 'semantic_key', unique=True,
            postgresql_where=text("semantic_key IS NOT NULL AND status IN ('open','accepted','in_progress','blocked','review','pending_approval')"),
            sqlite_where=text("semantic_key IS NOT NULL AND status IN ('open','accepted','in_progress','blocked','review','pending_approval')"),
        ),
    )


class ProcurementCycleObjective(Base, ScopedMixin):
    __tablename__ = "procurement_cycle_objectives"
    requirement_id: Mapped[str] = mapped_column(String(64), ForeignKey("purchase_requirements.id"), index=True)
    requirement_line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("purchase_requirement_lines.id"), nullable=True, index=True)
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    current_stage: Mapped[str] = mapped_column(String(48), default="requirement", index=True)
    health: Mapped[str] = mapped_column(String(32), default="on_track", index=True)
    need_by_date: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, default=1)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluation_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("requirement_id", "requirement_line_id", name="uq_cycle_objective_root"),
        Index("uq_cycle_objective_requirement_root", "requirement_id", unique=True,
              postgresql_where=text("requirement_line_id IS NULL"), sqlite_where=text("requirement_line_id IS NULL")),
    )


class CycleStageState(Base, ScopedMixin):
    __tablename__ = "cycle_stage_states"
    objective_id: Mapped[str] = mapped_column(String(64), ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), index=True)
    stage_key: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(32), default="not_started", index=True)
    owner_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("objective_id", "stage_key", name="uq_cycle_stage"),)


class CycleDependency(Base, ScopedMixin):
    __tablename__ = "cycle_dependencies"
    objective_id: Mapped[str] = mapped_column(String(64), ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    semantic_key: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("objective_id", "semantic_key", name="uq_cycle_dependency_semantic"),)


class CycleRisk(Base, ScopedMixin):
    __tablename__ = "cycle_risks"
    objective_id: Mapped[str] = mapped_column(String(64), ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), index=True)
    risk_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    semantic_key: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    __table_args__ = (UniqueConstraint("objective_id", "semantic_key", name="uq_cycle_risk_semantic"),)


class Commitment(Base, ScopedMixin):
    __tablename__ = "commitments"
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    objective_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("procurement_cycle_objectives.id"), nullable=True, index=True)
    commitment_type: Mapped[str] = mapped_column(String(32), default="employee", index=True)
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    promised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deliverable: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_commitment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    operational_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completion_condition: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    escalation_condition: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evidence_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_evaluation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dependency_state: Mapped[str] = mapped_column(String(32), default="INTERNAL", index=True)


class PreparedWorkItem(Base, ScopedMixin):
    __tablename__ = "agent_prepared_work_items"
    objective_id: Mapped[str] = mapped_column(String(64), ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=True, index=True)
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    work_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    semantic_key: Mapped[str] = mapped_column(String(240))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generating_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("objective_id", "semantic_key", name="uq_prepared_work_semantic"),)


class EventOutbox(Base, ScopedMixin):
    __tablename__ = "event_outbox"
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: str(uuid4()))
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    actor_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    causation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Platform envelope fields.  Existing module events remain valid and are
    # backfilled by the migration with conservative defaults.
    event_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    subject_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventConsumerReceipt(Base, ScopedMixin):
    __tablename__ = "event_consumer_receipts"
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    consumer_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("event_id", "consumer_name", name="uq_event_consumer_receipt"),)


class AgentRunAttempt(Base, ScopedMixin):
    __tablename__ = "agent_run_attempts"
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    checkpoint_sequence: Mapped[int] = mapped_column(Integer, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("run_id", "attempt_number", name="uq_agent_run_attempt"),)


class PolicyDecisionRecord(Base, ScopedMixin):
    __tablename__ = "policy_decisions"
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    actor_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    capability_id: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    allow: Mapped[bool] = mapped_column(Boolean)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean)
    autonomy_tier: Mapped[int] = mapped_column(Integer)
    obligations: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason_code: Mapped[str] = mapped_column(String(120), index=True)
    policy_version: Mapped[str] = mapped_column(String(80), index=True)
    shadow: Mapped[bool] = mapped_column(Boolean, default=True)
    input_digest: Mapped[str] = mapped_column(String(64))


class AutonomyPolicy(Base, ScopedMixin):
    __tablename__ = "autonomy_policies"
    name: Mapped[str] = mapped_column(String(180))
    capability_id: Mapped[str] = mapped_column(String(120), index=True)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    plant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    category_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    autonomy_ceiling: Mapped[int] = mapped_column(Integer, default=0)
    spend_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_limit: Mapped[str] = mapped_column(String(32), default="low")
    external_communication: Mapped[str] = mapped_column(String(32), default="confirm")
    confirmation_required: Mapped[bool] = mapped_column(Boolean, default=True)
    state: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    policy_version: Mapped[str] = mapped_column(String(80), default="draft-1")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PolicyBundle(Base, ScopedMixin):
    __tablename__ = "policy_bundles"
    bundle_version: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    signature: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), default="staged", index=True)
    created_by_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SandboxRun(Base, ScopedMixin):
    __tablename__ = "sandbox_runs"
    provider: Mapped[str] = mapped_column(String(48))
    profile: Mapped[str] = mapped_column(String(64), index=True)
    specialist_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(32), default="created", index=True)
    input_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    declared_outputs: Mapped[list[str]] = mapped_column(JSON, default=list)
    output_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


class OperationalReport(Base, ScopedMixin):
    __tablename__ = "operational_reports"
    period: Mapped[str] = mapped_column(String(48), index=True)
    period_start: Mapped[str] = mapped_column(String(32))
    period_end: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    employee_corrections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    manager_annotations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "period", name="uq_operational_report_period"),)


class Objective(Base, ScopedMixin):
    __tablename__ = "objectives"
    title: Mapped[str] = mapped_column(String(240))
    material: Mapped[str] = mapped_column(String(240))
    quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(24))
    need_by_date: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    owner_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(48), default="draft")
    created_by_membership_id: Mapped[str] = mapped_column(String(64))


class AgentThread(Base, ScopedMixin):
    __tablename__ = "agent_threads"
    membership_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_profile_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_type: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(240))
    work_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    objective_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    participant_membership_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_schema_version: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(32), default="active")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    module_context: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    conversation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMessage(Base, ScopedMixin):
    __tablename__ = "agent_messages"
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    membership_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    content_format: Mapped[str] = mapped_column(String(32), default="markdown")
    content_blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    visibility: Mapped[str] = mapped_column(String(32), default="private")
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class AgentMessageAttachment(Base, ScopedMixin):
    """Immutable evidence attached to a sent agent message.

    Processing and resolution fields may advance, but the message/document
    association itself is never removed when the composer is cleared.
    """
    __tablename__ = "agent_message_attachments"
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_messages.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), index=True)
    file_order: Mapped[int] = mapped_column(Integer, default=0)
    purpose: Mapped[str] = mapped_column(String(48), default="evidence")
    status: Mapped[str] = mapped_column(String(48), default="queued", index=True)
    document_job_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("document_jobs.id"), nullable=True, index=True)
    inferred_rfq_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confirmed_rfq_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    inferred_supplier_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confirmed_supplier_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    inference_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    inference_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    linked_quotation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("message_id", "document_id", name="uq_agent_message_document"),
    )


class AgentRun(Base, ScopedMixin):
    __tablename__ = "agent_runs"
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    membership_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_profile_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(48))
    model: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    context_hash: Mapped[str] = mapped_column(String(160))
    policy_version: Mapped[str] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(80), index=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    requested_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    read_tool_count: Mapped[int] = mapped_column(Integer, default=0)
    mutation_count: Mapped[int] = mapped_column(Integer, default=0)
    termination_reason: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    run_type: Mapped[str] = mapped_column(String(48), default="conversation", index=True)
    role_profile: Mapped[str] = mapped_column(String(64), default="operator", index=True)
    prompt_version: Mapped[str] = mapped_column(String(80), default="gigi-core@1")
    model_task_class: Mapped[str] = mapped_column(String(32), default="REASONING")
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentEvent(Base, ScopedMixin):
    __tablename__ = 'agent_events'
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    visibility: Mapped[str] = mapped_column(String(32), default='private')
    __table_args__ = (UniqueConstraint('run_id', 'sequence', name='uq_agent_event_sequence'),)


class AgentCheckpoint(Base, ScopedMixin):
    __tablename__ = 'agent_checkpoints'
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(80), index=True)
    state_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default='completed', index=True)
    __table_args__ = (
        UniqueConstraint('run_id', 'sequence', name='uq_agent_checkpoint_sequence'),
    )


class AgentToolCall(Base, ScopedMixin):
    __tablename__ = "agent_tool_calls"
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_profile_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(120))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_hash: Mapped[str | None] = mapped_column(String(160), nullable=True)
    target_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authorization_decision: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    tool_version: Mapped[str] = mapped_column(String(32), default="1")
    call_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentProposal(Base, ScopedMixin):
    __tablename__ = "agent_proposals"
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_profile_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(120))
    target_entity_type: Mapped[str] = mapped_column(String(80))
    target_entity_id: Mapped[str] = mapped_column(String(64))
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_effect: Mapped[str] = mapped_column(Text)
    required_authority: Mapped[str] = mapped_column(String(64))
    record_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmation_state: Mapped[str] = mapped_column(String(32), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_version: Mapped[str] = mapped_column(String(32), default='1')
    risk_class: Mapped[str] = mapped_column(String(8), default='R3', index=True)
    required_capability: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rejection_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True, index=True)


class AgentActionReceipt(Base, ScopedMixin):
    __tablename__ = 'agent_action_receipts'
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    target_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    executed_by_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)


class AgentDelegation(Base, ScopedMixin):
    __tablename__ = "agent_delegations"
    sender_agent_profile_id: Mapped[str] = mapped_column(String(64), index=True)
    sender_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    recipient_agent_profile_id: Mapped[str] = mapped_column(String(64), index=True)
    recipient_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    objective_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    work_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    requested_outcome: Mapped[str] = mapped_column(Text)
    context_packet: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    depth: Mapped[int] = mapped_column(Integer, default=1)
    contract_kind: Mapped[str] = mapped_column(String(32), default="collaboration_request")
    expected_deliverable: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    accountability_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    acceptance_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMemory(Base, ScopedMixin):
    __tablename__ = "agent_memories"
    membership_id: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    memory_type: Mapped[str] = mapped_column(String(48), default="preference", index=True)
    scope_type: Mapped[str] = mapped_column(String(48), default="user", index=True)
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    validation_state: Mapped[str] = mapped_column(String(32), default="verified", index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("membership_id", "key", name="uq_agent_memory_key"),)


class KnowledgeDocument(Base, ScopedMixin):
    __tablename__ = "knowledge_documents"
    title: Mapped[str] = mapped_column(String(240))
    source: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    approval_state: Mapped[str] = mapped_column(String(32), default="draft")
    document_version: Mapped[int] = mapped_column(Integer, default=1)
    role_acl: Mapped[list[str]] = mapped_column(JSON, default=list)
    plant_acl: Mapped[list[str]] = mapped_column(JSON, default=list)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_type: Mapped[str] = mapped_column(String(64), default="sop", index=True)
    revision: Mapped[str] = mapped_column(String(64), default="1")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    product_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    process_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    authoritative_source: Mapped[str | None] = mapped_column(String(240), nullable=True)


class KnowledgeChunk(Base, ScopedMixin):
    __tablename__ = "knowledge_chunks"
    knowledge_document_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    page_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    section_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("knowledge_document_id", "chunk_index", name="uq_knowledge_chunk_index"),)


class RetentionHold(Base, ScopedMixin):
    __tablename__ = "retention_holds"
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text)
    placed_by_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_active_retention_hold_entity"),)


class AgentFeedback(Base, ScopedMixin):
    __tablename__ = "agent_feedback"
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    membership_id: Mapped[str] = mapped_column(String(64), index=True)
    helpfulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correctness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    experience_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    feedback_type: Mapped[str] = mapped_column(String(48), default="response", index=True)


class PromptVersion(Base, ScopedMixin):
    __tablename__ = "ai_prompt_versions"
    name: Mapped[str] = mapped_column(String(120), index=True)
    version_label: Mapped[str] = mapped_column(String(48))
    task_class: Mapped[str] = mapped_column(String(32), index=True)
    template_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "name", "version_label", name="uq_ai_prompt_version"),)


class AIInvestigation(Base, ScopedMixin):
    __tablename__ = "ai_investigations"
    trigger_type: Mapped[str] = mapped_column(String(120), index=True)
    trigger_reference: Mapped[str] = mapped_column(String(160), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(24), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(180))
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    findings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "dedupe_key", name="uq_ai_investigation_dedupe"),)


class AIBriefing(Base, ScopedMixin):
    __tablename__ = "ai_briefings"
    membership_id: Mapped[str] = mapped_column(String(64), index=True)
    briefing_type: Mapped[str] = mapped_column(String(48), index=True)
    period_key: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(240))
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "membership_id", "briefing_type", "period_key", name="uq_ai_briefing_period"),)


class AgentExperience(Base, ScopedMixin):
    __tablename__ = "agent_experiences"
    domain: Mapped[str] = mapped_column(String(48), index=True)
    problem_type: Mapped[str] = mapped_column(String(80), index=True)
    problem_signature: Mapped[str] = mapped_column(String(160), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action_intent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    context_reference: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    selected_strategy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    predicted_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actual_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    effectiveness: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class KnowledgeDocumentEntityLink(Base, ScopedMixin):
    __tablename__ = "knowledge_document_entity_links"
    knowledge_document_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    relationship: Mapped[str] = mapped_column(String(48), default="about")
    __table_args__ = (UniqueConstraint("knowledge_document_id", "entity_type", "entity_id", name="uq_knowledge_document_entity"),)


class Case(Base, ScopedMixin):
    __tablename__ = "cases"
    title: Mapped[str] = mapped_column(String(240))
    requirement: Mapped[str] = mapped_column(String(240))
    supplier: Mapped[str] = mapped_column(String(180))
    owner_role: Mapped[str] = mapped_column(String(64))
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    value_amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    status: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    requirement_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rfq_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    po_draft_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    po_line_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    inspection_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    operational_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor: Mapped[str] = mapped_column(String(180))
    action: Mapped[str] = mapped_column(String(140), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    result: Mapped[str] = mapped_column(String(32))
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    payload_hash: Mapped[str] = mapped_column(String(160))
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base, ScopedMixin):
    category: Mapped[str] = mapped_column(String(48), default='action_required', index=True)
    severity: Mapped[str] = mapped_column(String(24), default='info')
    membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    linked_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linked_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    navigation_target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="unread")
    __table_args__ = (
        Index(
            'uq_notifications_unread_dedupe_key', 'tenant_id', 'dedupe_key', unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL AND status = 'unread'"),
            sqlite_where=text("dedupe_key IS NOT NULL AND status = 'unread'"),
        ),
    )


class CompanionPreference(Base, ScopedMixin):
    __tablename__ = "companion_preferences"
    membership_id: Mapped[str] = mapped_column(String(64), index=True)
    proactive_level: Mapped[str] = mapped_column(String(32), default="risk_tiered")
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    quiet_hours: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    animation_mode: Mapped[str] = mapped_column(String(32), default="system")
    login_briefing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    background_preparation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    default_execution_mode: Mapped[str] = mapped_column(String(32), default="prepare")
    category_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "membership_id", name="uq_companion_preference_membership"),)


class CompanionTriggerPolicy(Base, ScopedMixin):
    __tablename__ = "companion_trigger_policies"
    name: Mapped[str] = mapped_column(String(180))
    trigger_type: Mapped[str] = mapped_column(String(120), index=True)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    plant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    category_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    minimum_severity: Mapped[str] = mapped_column(String(24), default="info")
    preparation_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    specialist_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    autonomy_ceiling: Mapped[int] = mapped_column(Integer, default=1)
    delivery_mode: Mapped[str] = mapped_column(String(32), default="risk_tiered")
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=900)
    expiry_seconds: Mapped[int] = mapped_column(Integer, default=86400)
    state: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    policy_version: Mapped[str] = mapped_column(String(80), default="draft")


class CompanionIntervention(Base, ScopedMixin):
    __tablename__ = "companion_interventions"
    recipient_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    objective_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    prepared_work_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    trigger_type: Mapped[str] = mapped_column(String(120), index=True)
    severity: Mapped[str] = mapped_column(String(24), default="info", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    why_now: Mapped[str] = mapped_column(Text)
    current_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    responsible_authority: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_state: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    delivery_mode: Mapped[str] = mapped_column(String(32), default="badge")
    aggregate_version: Mapped[int] = mapped_column(Integer, default=1)
    semantic_key: Mapped[str] = mapped_column(String(240))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    selected_action: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outcome_receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "semantic_key", name="uq_companion_intervention_semantic"),)


class OutboxMessage(Base, ScopedMixin):
    __tablename__ = "outbox_messages"
    channel: Mapped[str] = mapped_column(String(32))
    recipient: Mapped[str] = mapped_column(String(240))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(48), index=True)
    payload_hash: Mapped[str] = mapped_column(String(160))
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attachment_document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class Supplier(Base, ScopedMixin):
    __tablename__ = "suppliers"
    company_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("companies.id"), nullable=True, index=True)
    code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(32))
    quality_score: Mapped[int] = mapped_column(Integer)
    delivery_score: Mapped[int] = mapped_column(Integer)
    erp_vendor_id: Mapped[str] = mapped_column(String(80))
    legal_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    default_lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SupplierSite(Base, ScopedMixin):
    __tablename__ = "supplier_sites"
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    payment_terms: Mapped[str] = mapped_column(String(120), default="")


class SupplierContact(Base, ScopedMixin):
    __tablename__ = "supplier_contacts"
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    name: Mapped[str] = mapped_column(String(140))
    email: Mapped[str] = mapped_column(String(180))
    phone: Mapped[str] = mapped_column(String(60), default="")


class SupplierComplianceRequirement(Base, ScopedMixin):
    __tablename__ = "supplier_compliance_requirements"
    certificate_type: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("items.id"), nullable=True, index=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "certificate_type", "item_id", name="uq_supplier_compliance_requirement"),)


class SupplierCertificate(Base, ScopedMixin):
    __tablename__ = "supplier_certificates"
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    certificate_type: Mapped[str] = mapped_column(String(120), index=True)
    certificate_number: Mapped[str] = mapped_column(String(160), default="")
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.id"), nullable=True, index=True)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    expires_on: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (CheckConstraint("status IN ('pending_review','verified','rejected','superseded')", name="ck_supplier_certificate_status"),)


class SupplierPerformanceEvent(Base, ScopedMixin):
    __tablename__ = "supplier_performance_events"
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    po_draft_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("po_drafts.id"), nullable=True, index=True)
    source_entity_type: Mapped[str] = mapped_column(String(64), index=True)
    source_entity_id: Mapped[str] = mapped_column(String(64), index=True)
    metric_type: Mapped[str] = mapped_column(String(48), index=True)
    numerator: Mapped[float] = mapped_column(Float)
    denominator: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", "metric_type", name="uq_supplier_performance_source_metric"),
        CheckConstraint("denominator > 0 AND score >= 0 AND score <= 100", name="ck_supplier_performance_score"),
    )


class SupplierCorrectiveAction(Base, ScopedMixin):
    __tablename__ = "supplier_corrective_actions"
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("cases.id"), nullable=True, index=True)
    source_entity_type: Mapped[str] = mapped_column(String(64), index=True)
    source_entity_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    problem_statement: Mapped[str] = mapped_column(Text)
    requested_response_by: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    corrective_action: Mapped[str] = mapped_column(Text, default="")
    preventive_action: Mapped[str] = mapped_column(Text, default="")
    effectiveness_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('open','awaiting_supplier','response_received','effectiveness_review','closed','cancelled')", name="ck_supplier_corrective_action_status"),)


class Uom(Base):
    __tablename__ = "uoms"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))


class Item(Base, ScopedMixin):
    __tablename__ = "items"
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    uom_id: Mapped[str] = mapped_column(String(32))
    erp_item_code: Mapped[str] = mapped_column(String(80))


class ItemSpecification(Base, ScopedMixin):
    __tablename__ = "item_specifications"
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    required_certificates: Mapped[list[str]] = mapped_column(JSON, default=list)
    inspection_required: Mapped[bool] = mapped_column(Boolean, default=True)


class TaxPolicy(Base, ScopedMixin):
    __tablename__ = "tax_policies"
    tax_code: Mapped[str] = mapped_column(String(48), index=True)
    recoverable: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(String(180), default="")
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "tax_code", name="uq_tax_policy_scope"),)


class ProcurementPolicy(Base, ScopedMixin):
    __tablename__ = "procurement_policies"
    name: Mapped[str] = mapped_column(String(180))
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "plant_id", "name", "policy_version", name="uq_procurement_policy_version"),
        CheckConstraint("status IN ('draft','active','retired')", name="ck_procurement_policy_status"),
    )


class ProcurementPolicyEvaluation(Base, ScopedMixin):
    __tablename__ = "procurement_policy_evaluations"
    policy_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("procurement_policies.id"), nullable=True, index=True)
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_version: Mapped[int] = mapped_column(Integer, default=1)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    required_approval_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    evaluated_by_user_id: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "entity_id", "entity_version", "policy_version", name="uq_procurement_policy_evaluation"),
        CheckConstraint("decision IN ('pass','requires_justification','blocked')", name="ck_procurement_policy_evaluation_decision"),
    )


class SupplierItemCapability(Base, ScopedMixin):
    __tablename__ = "supplier_item_capabilities"
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class MaterialMasterRequest(Base, ScopedMixin):
    __tablename__ = "material_master_requests"
    requested_name: Mapped[str] = mapped_column(String(180))
    requested_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    uom: Mapped[str] = mapped_column(String(32))
    specification: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    requested_by_user_id: Mapped[str] = mapped_column(String(64), index=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resulting_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")


class PurchaseRequirement(Base, ScopedMixin):
    __tablename__ = "purchase_requirements"
    source: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    need_by_date: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(48), index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64))
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_by_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    related_case_id: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_requirement_quantity_positive"),
        CheckConstraint("status IN ('draft','approved','rfq_drafted','cancelled','closed')", name="ck_requirement_status"),
    )


class PurchaseRequirementLine(Base, ScopedMixin):
    __tablename__ = "purchase_requirement_lines"
    requirement_id: Mapped[str] = mapped_column(String(64), ForeignKey("purchase_requirements.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    need_by_date: Mapped[str] = mapped_column(String(32))
    specification: Mapped[str] = mapped_column(Text, default="")
    inspection_required: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_requirement_line_quantity_positive"),)


class RFQ(Base, ScopedMixin):
    __tablename__ = "rfqs"
    requirement_id: Mapped[str] = mapped_column(String(64), ForeignKey("purchase_requirements.id"), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    deadline: Mapped[str] = mapped_column(String(32))
    supplier_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('draft','published','responses_open','closed','cancelled')", name="ck_rfq_status"),)


class RFQLine(Base, ScopedMixin):
    __tablename__ = "rfq_lines"
    rfq_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfqs.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    need_by_date: Mapped[str] = mapped_column(String(32))
    required_certificates: Mapped[list[str]] = mapped_column(JSON, default=list)
    requirement_line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("purchase_requirement_lines.id"), nullable=True, index=True)


class RFQSupplierInvitation(Base, ScopedMixin):
    __tablename__ = "rfq_supplier_invitations"
    rfq_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfqs.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(48), default="pending")
    portal_token_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id", name="uq_rfq_supplier_invitation"),)


class ExchangeRateObservation(Base, ScopedMixin):
    __tablename__ = "exchange_rate_observations"
    source_currency: Mapped[str] = mapped_column(String(16), index=True)
    target_currency: Mapped[str] = mapped_column(String(16), default="INR", index=True)
    rate: Mapped[float] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(160))
    source_reference: Mapped[str] = mapped_column(String(240), default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="verified", index=True)
    recorded_by_user_id: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint("rate > 0", name="ck_exchange_rate_positive"),)


class SupplierQuote(Base, ScopedMixin):
    __tablename__ = "supplier_quotes"
    rfq_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfqs.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    quote_number: Mapped[str] = mapped_column(String(80))
    quote_date: Mapped[str] = mapped_column(String(32))
    validity_date: Mapped[str] = mapped_column(String(32))
    payment_terms: Mapped[str] = mapped_column(String(120))
    parser_version: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(80))
    verification_status: Mapped[str] = mapped_column(String(48), index=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_quote_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    participation_status: Mapped[str] = mapped_column(String(32), default="complete", index=True)
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    exchange_rate_to_inr: Mapped[float] = mapped_column(Float, default=1)
    exchange_rate_observation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("exchange_rate_observations.id"), nullable=True, index=True)
    __table_args__ = (CheckConstraint("verification_status IN ('extracting','needs_review','needs_manual_entry','verified','rejected','superseded')", name="ck_quote_verification_status"),)


class QuoteLine(Base, ScopedMixin):
    __tablename__ = "quote_lines"
    quote_id: Mapped[str] = mapped_column(String(64), ForeignKey("supplier_quotes.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[float] = mapped_column(Float)
    gst_rate: Mapped[float] = mapped_column(Float)
    freight: Mapped[float] = mapped_column(Float)
    packaging: Mapped[float] = mapped_column(Float)
    lead_time_days: Mapped[int] = mapped_column(Integer)
    promised_date: Mapped[str] = mapped_column(String(32))
    moq: Mapped[float] = mapped_column(Float)
    technical_compliance: Mapped[str] = mapped_column(String(64))
    certificates: Mapped[list[str]] = mapped_column(JSON, default=list)
    rfq_line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("rfq_lines.id"), nullable=True, index=True)
    tax_recoverable: Mapped[bool] = mapped_column(Boolean, default=True)
    nonrecoverable_tax: Mapped[float] = mapped_column(Float, default=0)
    deviation_notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quote_line_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_quote_line_price_nonnegative"),
        CheckConstraint("gst_rate >= 0", name="ck_quote_line_gst_nonnegative"),
    )


class QuoteExtractionRun(Base, ScopedMixin):
    __tablename__ = "quote_extraction_runs"
    quote_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parser_version: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(48))
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class QuotationIntake(Base, ScopedMixin):
    __tablename__ = "quotation_intakes"
    mode: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    rfq_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfqs.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.id"), nullable=True, unique=True, index=True)
    document_job_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("document_jobs.id"), nullable=True, index=True)
    extraction_run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("quote_extraction_runs.id"), nullable=True, index=True)
    inferred_supplier_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("suppliers.id"), nullable=True, index=True)
    confirmed_supplier_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("suppliers.id"), nullable=True, index=True)
    quote_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("supplier_quotes.id"), nullable=True, index=True)
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    supplier_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(48), default="")
    provider_job_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    parser_version: Mapped[str] = mapped_column(String(80), default="")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(64), index=True)
    accepted_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("mode IN ('parsed','manual_comparison')", name="ck_quotation_intake_mode"),
        CheckConstraint(
            "status IN ('queued','extracting','needs_review','needs_manual_entry','failed','accepted')",
            name="ck_quotation_intake_status",
        ),
    )


class InvoiceExtractionRun(Base, ScopedMixin):
    __tablename__ = "invoice_extraction_runs"
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), index=True)
    po_draft_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("po_drafts.id"), nullable=True, index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("supplier_invoices.id"), nullable=True, index=True)
    parser_version: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(48), index=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verified_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BidComparison(Base, ScopedMixin):
    __tablename__ = "bid_comparisons"
    rfq_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfqs.id"), index=True)
    status: Mapped[str] = mapped_column(String(48))
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recommended_supplier_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recommendation_rationale: Mapped[str] = mapped_column(Text, default="")
    comparison_version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ComparisonApprovalRequest(Base, ScopedMixin):
    __tablename__ = "comparison_approval_requests"
    comparison_id: Mapped[str] = mapped_column(String(64), ForeignKey("bid_comparisons.id", ondelete="CASCADE"), index=True)
    comparison_version: Mapped[int] = mapped_column(Integer)
    required_role: Mapped[str] = mapped_column(String(64), index=True)
    assignee_membership_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    decided_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    __table_args__ = (
        UniqueConstraint("comparison_id", "comparison_version", "required_role", name="uq_comparison_version_role_approval"),
    )


class NegotiationRound(Base, ScopedMixin):
    __tablename__ = "negotiation_rounds"
    rfq_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfqs.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    target: Mapped[str] = mapped_column(Text)
    drafted_message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(48))
    revised_unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)


class NegotiationMessage(Base, ScopedMixin):
    __tablename__ = "negotiation_messages"
    negotiation_id: Mapped[str] = mapped_column(String(64), ForeignKey("negotiation_rounds.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(24))
    message_type: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    commercial_terms: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(48), default="draft")
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AwardDecision(Base, ScopedMixin):
    __tablename__ = "award_decisions"
    rfq_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfqs.id"), index=True)
    quote_id: Mapped[str] = mapped_column(String(64), ForeignKey("supplier_quotes.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    award_batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("award_batches.id"), nullable=True, index=True)


class AwardBatch(Base, ScopedMixin):
    __tablename__ = "award_batches"
    comparison_id: Mapped[str] = mapped_column(String(64), ForeignKey("bid_comparisons.id"), index=True)
    comparison_version: Mapped[int] = mapped_column(Integer)
    allocation_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="confirmed", index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(64), index=True)
    total_awarded_quantity: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("tenant_id", "comparison_id", "comparison_version", "allocation_hash", name="uq_award_batch_allocation"),
        CheckConstraint("total_awarded_quantity > 0", name="ck_award_batch_quantity_positive"),
    )


class AwardLine(Base, ScopedMixin):
    __tablename__ = "award_lines"
    award_id: Mapped[str] = mapped_column(String(64), ForeignKey("award_decisions.id", ondelete="CASCADE"), index=True)
    rfq_line_id: Mapped[str] = mapped_column(String(64), ForeignKey("rfq_lines.id"), index=True)
    quote_line_id: Mapped[str] = mapped_column(String(64), ForeignKey("quote_lines.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    awarded_quantity: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        UniqueConstraint("award_id", "rfq_line_id", name="uq_award_rfq_line"),
        CheckConstraint("awarded_quantity > 0", name="ck_award_line_quantity_positive"),
    )


class PODraft(Base, ScopedMixin):
    __tablename__ = "po_drafts"
    award_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("award_decisions.id"), nullable=True, index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    oracle_mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    simulated_posting_correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supplier_site_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("supplier_sites.id"), nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    payment_terms: Mapped[str] = mapped_column(String(120), default="")
    commercial_terms: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    root_po_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    previous_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    revision_kind: Mapped[str] = mapped_column(String(32), default="original", index=True)
    change_reason: Mapped[str] = mapped_column(Text, default="")
    change_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('pending_approval','approved_pending_outbox','posting','simulated_posted','posted','failed','rejected','superseded','cancelled')", name="ck_po_status"),)


class PODraftLine(Base, ScopedMixin):
    __tablename__ = "po_draft_lines"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id", ondelete="CASCADE"), index=True)
    award_line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("award_lines.id"), nullable=True, index=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[float] = mapped_column(Float)
    gst_rate: Mapped[float] = mapped_column(Float, default=0)
    need_by_date: Mapped[str] = mapped_column(String(32))
    inspection_required: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_po_line_quantity_positive"),)


class SupplierAcknowledgement(Base, ScopedMixin):
    __tablename__ = "supplier_acknowledgements"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    status: Mapped[str] = mapped_column(String(48))
    confirmed_quantity: Mapped[float] = mapped_column(Float)
    confirmed_delivery: Mapped[str] = mapped_column(String(32))
    response_notes: Mapped[str] = mapped_column(Text, default="")
    requested_changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_po_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('accepted','rejected','change_requested','change_prepared')", name="ck_ack_status"),
        CheckConstraint("confirmed_quantity >= 0", name="ck_ack_quantity_nonnegative"),
    )


class ASN(Base, ScopedMixin):
    __tablename__ = "asns"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    status: Mapped[str] = mapped_column(String(48))
    vehicle_number: Mapped[str] = mapped_column(String(80), default="")
    expected_quantity: Mapped[float] = mapped_column(Float)
    dispatch_reference: Mapped[str] = mapped_column(String(120), default="")
    expected_delivery: Mapped[str] = mapped_column(String(32), default="")
    source: Mapped[str] = mapped_column(String(32), default="internal")
    supplier_document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("expected_quantity > 0", name="ck_asn_quantity_positive"),)


class SupplierDeliveryUpdate(Base, ScopedMixin):
    __tablename__ = "supplier_delivery_updates"
    asn_id: Mapped[str] = mapped_column(String(64), ForeignKey("asns.id", ondelete="CASCADE"), index=True)
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    external_update_id: Mapped[str] = mapped_column(String(160))
    update_type: Mapped[str] = mapped_column(String(48), default="schedule_change", index=True)
    previous_expected_delivery: Mapped[str] = mapped_column(String(32), default="")
    revised_expected_delivery: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("tenant_id", "plant_id", "asn_id", "external_update_id", name="uq_supplier_delivery_update_external"),
        CheckConstraint("update_type IN ('schedule_change','delay','expedite')", name="ck_supplier_delivery_update_type"),
    )


class GateEntry(Base, ScopedMixin):
    __tablename__ = "gate_entries"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    asn_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("asns.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(48))
    vehicle_number: Mapped[str] = mapped_column(String(80), default="")
    supplier_challan: Mapped[str] = mapped_column(String(120), default="")
    packages_count: Mapped[int] = mapped_column(Integer, default=0)
    arrival_notes: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoreReceipt(Base, ScopedMixin):
    __tablename__ = "store_receipts"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    gate_entry_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("gate_entries.id"), nullable=True)
    # Deliberately not a database FK: SupplierReturn already points to an
    # InspectionResult which points back to StoreReceipt. Keeping this as a
    # scoped, indexed service-validated reference avoids a DDL/delete cycle.
    supplier_return_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(48))
    received_quantity: Mapped[float] = mapped_column(Float)
    short_quantity: Mapped[float] = mapped_column(Float, default=0)
    excess_quantity: Mapped[float] = mapped_column(Float, default=0)
    damaged_quantity: Mapped[float] = mapped_column(Float, default=0)
    exception_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    observed_item_code: Mapped[str] = mapped_column(String(80), default="")
    certificate_status: Mapped[str] = mapped_column(String(48), default="received")
    exception_notes: Mapped[str] = mapped_column(Text, default="")
    production_impact: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("received_quantity > 0", name="ck_receipt_quantity_positive"),
        CheckConstraint("short_quantity >= 0 AND excess_quantity >= 0 AND damaged_quantity >= 0", name="ck_receipt_quantities_nonnegative"),
        CheckConstraint("damaged_quantity <= received_quantity", name="ck_receipt_damage_cap"),
    )


class InspectionResult(Base, ScopedMixin):
    __tablename__ = "inspection_results"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    receipt_id: Mapped[str] = mapped_column(String(64), ForeignKey("store_receipts.id"), index=True)
    status: Mapped[str] = mapped_column(String(48))
    inspected_quantity: Mapped[float] = mapped_column(Float)
    accepted_quantity: Mapped[float] = mapped_column(Float)
    rejected_quantity: Mapped[float] = mapped_column(Float, default=0)
    held_quantity: Mapped[float] = mapped_column(Float, default=0)
    certificate_status: Mapped[str] = mapped_column(String(48), default="verified")
    defect_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    inspection_notes: Mapped[str] = mapped_column(Text, default="")
    production_impact: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("inspected_quantity >= 0 AND accepted_quantity >= 0 AND rejected_quantity >= 0 AND held_quantity >= 0", name="ck_inspection_quantities_nonnegative"),
        CheckConstraint("accepted_quantity + rejected_quantity + held_quantity <= inspected_quantity", name="ck_inspection_disposition_cap"),
    )


class InventoryImpact(Base, ScopedMixin):
    __tablename__ = "inventory_impacts"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    inspection_id: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    usable_quantity: Mapped[float] = mapped_column(Float)
    rejected_quantity: Mapped[float] = mapped_column(Float)
    held_quantity: Mapped[float] = mapped_column(Float)


class Document(Base, ScopedMixin):
    __tablename__ = "documents"
    filename: Mapped[str] = mapped_column(String(240))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(48))
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    linked_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linked_entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    storage_bucket: Mapped[str] = mapped_column(String(120), default="")
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    uploaded_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class GeneratedArtifact(Base, ScopedMixin):
    __tablename__ = "generated_artifacts"
    artifact_type: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_version: Mapped[int] = mapped_column(Integer, default=1)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    template_version: Mapped[str] = mapped_column(String(64), default="procurement-v2@1")
    source_snapshot_hash: Mapped[str] = mapped_column(String(64))
    generated_by_user_id: Mapped[str] = mapped_column(String(64))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "entity_id", "artifact_type", "artifact_version", name="uq_generated_artifact_version"),
    )


class SupplierReturn(Base, ScopedMixin):
    __tablename__ = "supplier_returns"
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    inspection_id: Mapped[str] = mapped_column(String(64), ForeignKey("inspection_results.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("cases.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    rejected_quantity: Mapped[float] = mapped_column(Float)
    return_quantity: Mapped[float] = mapped_column(Float)
    replacement_requested_quantity: Mapped[float] = mapped_column(Float, default=0)
    replacement_received_quantity: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("rejected_quantity > 0 AND return_quantity > 0", name="ck_supplier_return_quantities_positive"),
        CheckConstraint("return_quantity <= rejected_quantity", name="ck_supplier_return_quantity_cap"),
        CheckConstraint("replacement_requested_quantity >= 0 AND replacement_received_quantity >= 0", name="ck_supplier_replacement_quantities_nonnegative"),
    )


class SupplierInvoice(Base, ScopedMixin):
    __tablename__ = "supplier_invoices"
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    po_draft_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("po_drafts.id"), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.id"), nullable=True, index=True)
    invoice_number: Mapped[str] = mapped_column(String(120), index=True)
    invoice_date: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    subtotal: Mapped[float] = mapped_column(Float)
    tax_amount: Mapped[float] = mapped_column(Float, default=0)
    total_amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(48), index=True)
    source: Mapped[str] = mapped_column(String(48), default="manual")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "plant_id", "supplier_id", "invoice_number", name="uq_supplier_invoice_number_scope"),
        CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total_amount >= 0", name="ck_invoice_amounts_nonnegative"),
    )


class SupplierInvoiceLine(Base, ScopedMixin):
    __tablename__ = "supplier_invoice_lines"
    invoice_id: Mapped[str] = mapped_column(String(64), ForeignKey("supplier_invoices.id", ondelete="CASCADE"), index=True)
    po_line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("po_draft_lines.id"), nullable=True, index=True)
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("items.id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[float] = mapped_column(Float)
    tax_amount: Mapped[float] = mapped_column(Float, default=0)
    line_total: Mapped[float] = mapped_column(Float)
    __table_args__ = (CheckConstraint("quantity >= 0 AND unit_price >= 0 AND line_total >= 0", name="ck_invoice_line_amounts_nonnegative"),)


class InvoiceMatchResult(Base, ScopedMixin):
    __tablename__ = "invoice_match_results"
    invoice_id: Mapped[str] = mapped_column(String(64), ForeignKey("supplier_invoices.id"), index=True)
    po_draft_id: Mapped[str] = mapped_column(String(64), ForeignKey("po_drafts.id"), index=True)
    receipt_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("store_receipts.id"), nullable=True, index=True)
    match_type: Mapped[str] = mapped_column(String(32))
    result: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    variances: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    policy_version: Mapped[str] = mapped_column(String(32), default="1.0")
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinanceHandoff(Base, ScopedMixin):
    __tablename__ = "finance_handoffs"
    invoice_id: Mapped[str] = mapped_column(String(64), ForeignKey("supplier_invoices.id"), index=True)
    match_result_id: Mapped[str] = mapped_column(String(64), ForeignKey("invoice_match_results.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prepared_by_user_id: Mapped[str] = mapped_column(String(64))
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("invoice_id", "match_result_id", name="uq_invoice_match_finance_handoff"),)


class InvoicePaymentStatus(Base, ScopedMixin):
    __tablename__ = "invoice_payment_statuses"
    invoice_id: Mapped[str] = mapped_column(String(64), ForeignKey("supplier_invoices.id"), index=True)
    connection_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_connections.id"), index=True)
    external_key: Mapped[str] = mapped_column(String(180), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    external_version: Mapped[str] = mapped_column(String(80), default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_payload_hash: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("connection_id", "external_key", "external_version", "source_payload_hash", name="uq_invoice_payment_observation"),
        CheckConstraint("status IN ('not_released','scheduled','processing','paid','partially_paid','on_hold','rejected','unknown')", name="ck_invoice_payment_status"),
    )


class DocumentJob(Base, ScopedMixin):
    __tablename__ = "document_jobs"
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(48), default="validate_extract")
    status: Mapped[str] = mapped_column(String(48), default="queued", index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class DocumentValidationResult(Base, ScopedMixin):
    __tablename__ = "document_validation_results"
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    validator_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(48), index=True)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)


class QuoteFieldVerification(Base, ScopedMixin):
    __tablename__ = "quote_field_verifications"
    quote_id: Mapped[str] = mapped_column(String(64), index=True)
    field_name: Mapped[str] = mapped_column(String(120), index=True)
    extracted_value: Mapped[str] = mapped_column(Text, default="")
    verified_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(48), index=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowTransition(Base, ScopedMixin):
    __tablename__ = "workflow_transitions"
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    from_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_status: Mapped[str] = mapped_column(String(80), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")


class ApprovalDecision(Base, ScopedMixin):
    __tablename__ = "approval_decisions"
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    decision: Mapped[str] = mapped_column(String(48), index=True)
    decided_by_user_id: Mapped[str] = mapped_column(String(64), index=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    rationale: Mapped[str] = mapped_column(Text, default="")
    immutable_hash: Mapped[str] = mapped_column(String(160))


class SupplierPortalToken(Base, ScopedMixin):
    __tablename__ = "supplier_portal_tokens"
    rfq_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str] = mapped_column(String(48), default="rfq_quote")
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class IntegrationConnection(Base, ScopedMixin):
    __tablename__ = "integration_connections"
    provider: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(48), index=True)
    base_url: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    provider_version: Mapped[str] = mapped_column(String(32), default="1.0")
    enabled_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    writes_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    secret_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntegrationSyncJob(Base, ScopedMixin):
    __tablename__ = "integration_sync_jobs"
    connection_id: Mapped[str] = mapped_column(String(64), index=True)
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConnectorDefinition(Base, ScopedMixin):
    __tablename__ = "connector_definitions"
    connector_type: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    manifest_version: Mapped[str] = mapped_column(String(32))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector_type", "manifest_version", name="uq_connector_definition_version"),
    )


class IntegrationMappingProfile(Base, ScopedMixin):
    __tablename__ = "integration_mapping_profiles"
    connection_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_connections.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    workbook_schema_version: Mapped[str] = mapped_column(String(32), default="1.0")
    mappings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    transforms: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ownership: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    __table_args__ = (
        UniqueConstraint("connection_id", "name", "profile_version", name="uq_mapping_profile_version"),
    )


class IntegrationIngestionRecord(Base, ScopedMixin):
    """Idempotency and lineage receipt for connector records normalized into V2."""
    __tablename__ = "integration_ingestion_records"
    connection_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_connections.id"), index=True)
    capability: Mapped[str] = mapped_column(String(80), index=True)
    source_record_key: Mapped[str] = mapped_column(String(240), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    target_entity_type: Mapped[str] = mapped_column(String(80))
    target_entity_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="applied", index=True)
    source_cursor: Mapped[str | None] = mapped_column(String(240), nullable=True)
    __table_args__ = (UniqueConstraint("connection_id", "capability", "source_record_key",
                                      name="uq_integration_ingestion_source_record"),)


class IntegrationImportBatch(Base, ScopedMixin):
    __tablename__ = "integration_import_batches"
    connection_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_connections.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.id"), nullable=True, index=True)
    mapping_profile_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_mapping_profiles.id"), nullable=True, index=True)
    source_filename: Mapped[str] = mapped_column(String(240))
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    workbook_version: Mapped[str] = mapped_column(String(80), default="1")
    mode: Mapped[str] = mapped_column(String(32), default="dry_run")
    status: Mapped[str] = mapped_column(String(48), index=True)
    discovery: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)


class IntegrationImportRowResult(Base, ScopedMixin):
    __tablename__ = "integration_import_row_results"
    batch_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_import_batches.id", ondelete="CASCADE"), index=True)
    sheet_name: Mapped[str] = mapped_column(String(160))
    row_number: Mapped[int] = mapped_column(Integer)
    external_key: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32), index=True)
    canonical_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canonical_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source_cells: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    mapping_version: Mapped[str] = mapped_column(String(32), default="1")
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    __table_args__ = (UniqueConstraint("batch_id", "sheet_name", "row_number", name="uq_import_batch_source_row"),)


class IntegrationExportBatch(Base, ScopedMixin):
    __tablename__ = "integration_export_batches"
    connection_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_connections.id"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    export_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    output_version: Mapped[int] = mapped_column(Integer, default=1)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)


class IntegrationExternalRecordState(Base, ScopedMixin):
    __tablename__ = "integration_external_record_states"
    connection_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_connections.id"), index=True)
    external_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    external_key: Mapped[str] = mapped_column(String(240), index=True)
    canonical_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canonical_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    external_payload_hash: Mapped[str] = mapped_column(String(64))
    external_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canonical_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ownership: Mapped[str] = mapped_column(String(32), default="external_owned")
    sync_status: Mapped[str] = mapped_column(String(48), index=True)
    tombstoned: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("connection_id", "external_entity_type", "external_key", name="uq_connection_external_record"),
    )


class IntegrationExternalReference(Base, ScopedMixin):
    __tablename__ = "integration_external_references"
    provider: Mapped[str] = mapped_column(String(48), index=True)
    local_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    local_entity_id: Mapped[str] = mapped_column(String(80), index=True)
    external_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    external_id: Mapped[str] = mapped_column(String(160), index=True)
    sync_status: Mapped[str] = mapped_column(String(48), index=True)
    last_payload_hash: Mapped[str | None] = mapped_column(String(160), nullable=True)


class IntegrationOutboxEvent(Base, ScopedMixin):
    __tablename__ = "integration_outbox_events"
    provider: Mapped[str] = mapped_column(String(48), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload_diff: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (CheckConstraint("status IN ('pending_approval','approved','dispatching','simulated','dispatched','failed','rejected')", name="ck_integration_outbox_status"),)


class IntegrationAttempt(Base, ScopedMixin):
    __tablename__ = "integration_attempts"
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("integration_outbox_events.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(48), index=True)
    request_hash: Mapped[str] = mapped_column(String(160))
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupplierChannelMessage(Base, ScopedMixin):
    __tablename__ = "supplier_channel_messages"
    channel: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    external_message_id: Mapped[str] = mapped_column(String(240))
    sender: Mapped[str] = mapped_column(String(320), index=True)
    recipient: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body_preview: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(48), index=True)
    rfq_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("rfqs.id"), nullable=True, index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("suppliers.id"), nullable=True, index=True)
    document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    canonical_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", "external_message_id", name="uq_supplier_channel_external_message"),
    )


class ReconciliationResult(Base, ScopedMixin):
    __tablename__ = "reconciliation_results"
    provider: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    local_hash: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_hash: Mapped[str | None] = mapped_column(String(160), nullable=True)
    differences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_key: Mapped[str] = mapped_column(String(160), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(320))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="processing")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("actor_key", "idempotency_key", name="uq_actor_idempotency_key"),)

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    plant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(160), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    email: Mapped[str] = mapped_column(String(180), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# V2 plant intelligence and production-recovery domain. These tables are
# additive to the V1 procurement model and deliberately reuse tenant, plant,
# task, event, policy and audit primitives.
class PlantArea(Base, ScopedMixin):
    __tablename__ = "plant_areas"
    name: Mapped[str] = mapped_column(String(180))
    code: Mapped[str] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "code", name="uq_plant_area_code"),)


class ProductionLine(Base, ScopedMixin):
    __tablename__ = "production_lines"
    area_id: Mapped[str] = mapped_column(String(64), ForeignKey("plant_areas.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    code: Mapped[str] = mapped_column(String(80))
    standard_good_rate_per_minute: Mapped[float] = mapped_column(Float, default=0)
    contribution_per_good_unit: Mapped[float] = mapped_column(Float, default=0)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "code", name="uq_production_line_code"),)


class PlantAsset(Base, ScopedMixin):
    __tablename__ = "plant_assets"
    area_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("plant_areas.id"), nullable=True, index=True)
    line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_lines.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    code: Mapped[str] = mapped_column(String(80))
    asset_type: Mapped[str] = mapped_column(String(80), default="machine")
    criticality: Mapped[str] = mapped_column(String(32), default="normal")
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "code", name="uq_plant_asset_code"),)


class PlantShift(Base, ScopedMixin):
    __tablename__ = "plant_shifts"
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(32))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "code", "starts_at", name="uq_plant_shift_instance"),)


class ManufacturingProduct(Base, ScopedMixin):
    __tablename__ = "manufacturing_products"
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    customer_program: Mapped[str] = mapped_column(String(180), default="")
    revision: Mapped[str] = mapped_column(String(32), default="A")
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "code", "revision", name="uq_manufacturing_product_revision"),)


class ManufacturingBOMLine(Base, ScopedMixin):
    __tablename__ = "manufacturing_bom_lines"
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("manufacturing_products.id", ondelete="CASCADE"), index=True)
    component_code: Mapped[str] = mapped_column(String(120), index=True)
    component_name: Mapped[str] = mapped_column(String(240))
    quantity_per: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    scrap_factor: Mapped[float] = mapped_column(Float, default=0)
    operation: Mapped[str] = mapped_column(String(120), default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("product_id", "component_code", name="uq_manufacturing_bom_component"),)


class ProductionWorkOrder(Base, ScopedMixin):
    __tablename__ = "production_work_orders"
    line_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_lines.id"), index=True)
    shift_id: Mapped[str] = mapped_column(String(64), ForeignKey("plant_shifts.id"), index=True)
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    product_code: Mapped[str] = mapped_column(String(120))
    product_name: Mapped[str] = mapped_column(String(240))
    target_quantity: Mapped[float] = mapped_column(Float)
    planned_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)


class ProductionPlanPoint(Base, ScopedMixin):
    __tablename__ = "production_plan_points"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id", ondelete="CASCADE"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cumulative_quantity: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(48), default="manual")
    __table_args__ = (UniqueConstraint("work_order_id", "recorded_at", name="uq_production_plan_point"),)


class ProductionActualPoint(Base, ScopedMixin):
    __tablename__ = "production_actual_points"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id", ondelete="CASCADE"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    good_quantity: Mapped[float] = mapped_column(Float)
    reject_quantity: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(48), default="manual")
    source_event_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "source_event_key", name="uq_actual_source_event"),)


class ProductionDowntimeEvent(Base, ScopedMixin):
    __tablename__ = "production_downtime_events"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id"), index=True)
    line_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_lines.id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("plant_assets.id"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductionQualityEvent(Base, ScopedMixin):
    __tablename__ = "production_quality_events"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id"), index=True)
    line_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_lines.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    inspected_quantity: Mapped[float] = mapped_column(Float)
    rejected_quantity: Mapped[float] = mapped_column(Float)
    defect_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), default="inspection", index=True)
    asset_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("plant_assets.id"), nullable=True, index=True)
    material_lot_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    measurement_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    measurement_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_control_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_control_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(24), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(48), default="manual")


class QualityContainmentRecord(Base, ScopedMixin):
    __tablename__ = "quality_containment_records"
    quality_event_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_quality_events.id"), index=True)
    deviation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_deviations.id"), nullable=True, index=True)
    containment_type: Mapped[str] = mapped_column(String(80))
    affected_lot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QualityRecoveryCase(Base, ScopedMixin):
    __tablename__ = "quality_recovery_cases"
    case_type: Mapped[str] = mapped_column(String(24), index=True)  # ncr | capa
    parent_case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("quality_recovery_cases.id"), nullable=True, index=True)
    quality_event_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_quality_events.id"), nullable=True, index=True)
    deviation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_deviations.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    severity: Mapped[str] = mapped_column(String(24), default="medium")
    owner_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    problem_statement: Mapped[str] = mapped_column(Text)
    containment_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    effectiveness_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    effectiveness_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class StandardKPIDefinition(Base, ScopedMixin):
    __tablename__ = "standard_kpi_definitions"
    key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(48))
    formula: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(24), default="higher_is_better")
    context_dimensions: Mapped[list[str]] = mapped_column(JSON, default=list)
    version_label: Mapped[str] = mapped_column(String(48), default="1.0")
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "key", "version_label", name="uq_standard_kpi_version"),)


class BestPracticeTransfer(Base, ScopedMixin):
    __tablename__ = "best_practice_transfers"
    title: Mapped[str] = mapped_column(String(240))
    source_plant_id: Mapped[str] = mapped_column(String(64), ForeignKey("plants.id"), index=True)
    target_plant_id: Mapped[str] = mapped_column(String(64), ForeignKey("plants.id"), index=True)
    source_experiment_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("improvement_experiments.id"), nullable=True)
    source_deviation_pattern: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    hypothesis: Mapped[str] = mapped_column(Text)
    applicability_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_benefit: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    accepted_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class AssetFaultEvent(Base, ScopedMixin):
    __tablename__ = "asset_fault_events"
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("plant_assets.id"), index=True)
    work_order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_work_orders.id"), nullable=True, index=True)
    fault_code: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(String(240))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(48), default="manual")
    source_event_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "source_event_key", name="uq_asset_fault_source_event"),)


class MachineSignalSample(Base, ScopedMixin):
    __tablename__ = "machine_signal_samples"
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("plant_assets.id"), index=True)
    work_order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_work_orders.id"), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_quality: Mapped[str] = mapped_column(String(24), default="good")
    source: Mapped[str] = mapped_column(String(48), default="edge")
    source_event_key: Mapped[str] = mapped_column(String(180))
    __table_args__ = (UniqueConstraint("tenant_id", "source_event_key", name="uq_machine_signal_source_event"),)


class MaintenanceWorkRecord(Base, ScopedMixin):
    __tablename__ = "maintenance_work_records"
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("plant_assets.id"), index=True)
    fault_event_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("asset_fault_events.id"), nullable=True, index=True)
    deviation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_deviations.id"), nullable=True, index=True)
    external_cmms_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    spare_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    spare_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)


class MaterialReadinessSnapshot(Base, ScopedMixin):
    __tablename__ = "material_readiness_snapshots"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id"), index=True)
    material_code: Mapped[str] = mapped_column(String(120), index=True)
    required_quantity: Mapped[float] = mapped_column(Float)
    usable_now: Mapped[float] = mapped_column(Float, default=0)
    confirmed_inbound: Mapped[float] = mapped_column(Float, default=0)
    unconfirmed_inbound: Mapped[float] = mapped_column(Float, default=0)
    required_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    data_freshness: Mapped[str] = mapped_column(String(24), default="fresh")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("work_order_id", "material_code", "calculated_at", name="uq_material_readiness_snapshot"),)


class ProductionMaterialRequirement(Base, ScopedMixin):
    __tablename__ = "production_material_requirements"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id"), index=True)
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("items.id"), nullable=True, index=True)
    material_code: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(240), default="")
    required_quantity: Mapped[float] = mapped_column(Float)
    uom: Mapped[str] = mapped_column(String(32))
    required_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    v1_requirement_line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("purchase_requirement_lines.id"), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("work_order_id", "material_code", name="uq_work_order_material"),)


class MaterialInventoryPosition(Base, ScopedMixin):
    __tablename__ = "material_inventory_positions"
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("items.id"), nullable=True, index=True)
    material_code: Mapped[str] = mapped_column(String(120), index=True)
    on_hand_quantity: Mapped[float] = mapped_column(Float, default=0)
    reserved_for_other_orders: Mapped[float] = mapped_column(Float, default=0)
    quality_hold_quantity: Mapped[float] = mapped_column(Float, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_system: Mapped[str] = mapped_column(String(80), default="manual")
    source_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)


class ProductionSupplierCommitment(Base, ScopedMixin):
    __tablename__ = "production_supplier_commitments"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id"), index=True)
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("items.id"), nullable=True, index=True)
    material_code: Mapped[str] = mapped_column(String(120), index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("suppliers.id"), nullable=True, index=True)
    committed_quantity: Mapped[float] = mapped_column(Float)
    committed_delivery_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    reliability_score: Mapped[float] = mapped_column(Float, default=1)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    v1_po_draft_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("po_drafts.id"), nullable=True, index=True)
    v1_acknowledgement_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("supplier_acknowledgements.id"), nullable=True, index=True)


class OperationalDeviation(Base, ScopedMixin):
    __tablename__ = "operational_deviations"
    detector_key: Mapped[str] = mapped_column(String(80), index=True)
    line_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_lines.id"), nullable=True, index=True)
    shift_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("plant_shifts.id"), nullable=True, index=True)
    work_order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_work_orders.id"), nullable=True, index=True)
    asset_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("plant_assets.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    subtype: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(48), default="detected", index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[str] = mapped_column(String(24), default="high")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expected_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actual_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    forecast_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_lost_units: Mapped[float] = mapped_column(Float, default=0)
    estimated_time_impact_minutes: Mapped[float] = mapped_column(Float, default=0)
    estimated_financial_impact: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    owner_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recurrence_key: Mapped[str] = mapped_column(String(320))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        Index("uq_active_operational_deviation", "tenant_id", "recurrence_key", unique=True,
              postgresql_where=text("status NOT IN ('verified','learned','cancelled')"),
              sqlite_where=text("status NOT IN ('verified','learned','cancelled')")),
    )


class OperationalAction(Base, ScopedMixin):
    __tablename__ = "operational_actions"
    deviation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_deviations.id"), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=True, unique=True)
    action_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(24), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="system")
    expected_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completion_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationalActionDependency(Base, ScopedMixin):
    __tablename__ = "operational_action_dependencies"
    action_id: Mapped[str] = mapped_column(String(64), ForeignKey("operational_actions.id", ondelete="CASCADE"), index=True)
    predecessor_action_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_actions.id", ondelete="CASCADE"), nullable=True, index=True)
    dependency_type: Mapped[str] = mapped_column(String(48), default="finish_to_start")
    title: Mapped[str] = mapped_column(String(240))
    owner_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_required: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("action_id", "title", name="uq_operational_action_dependency"),)


class OperationalEvidenceRef(Base, ScopedMixin):
    __tablename__ = "operational_evidence_refs"
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    evidence_type: Mapped[str] = mapped_column(String(32))
    source_system: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    object_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class OperationalValueEntry(Base, ScopedMixin):
    __tablename__ = "operational_value_entries"
    deviation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_deviations.id"), nullable=True, index=True)
    action_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_actions.id"), nullable=True, index=True)
    value_type: Mapped[str] = mapped_column(String(48))
    confidence_state: Mapped[str] = mapped_column(String(24), default="estimated")
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    calculation_method: Mapped[str] = mapped_column(String(120))
    calculation_inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationalStateSnapshot(Base, ScopedMixin):
    __tablename__ = "operational_state_snapshots"
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_id: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_version: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    execution_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    performance_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    machine_health_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quality_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recovery_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active_work_order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_work_orders.id"), nullable=True, index=True)
    shift_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("plant_shifts.id"), nullable=True, index=True)
    target_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_now: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    material_readiness_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active_deviation_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    active_action_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    state_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_freshness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("tenant_id", "scope_type", "scope_id", "snapshot_version", name="uq_operational_snapshot_version"),
        Index("ix_operational_snapshot_latest", "tenant_id", "plant_id", "scope_type", "scope_id", "captured_at"),
    )


class RecoveryCase(Base, ScopedMixin):
    __tablename__ = "recovery_cases"
    deviation_id: Mapped[str] = mapped_column(String(64), ForeignKey("operational_deviations.id"), unique=True, index=True)
    operational_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(32))
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="assessing", index=True)
    source: Mapped[str] = mapped_column(String(40), default="live")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    target_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    baseline_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    baseline_snapshot_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_state_snapshots.id"), nullable=True)
    business_exposure_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    business_exposure_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Logical FK kept nullable to avoid a DDL cycle with recovery_strategies;
    # service methods always resolve it within the same tenant/case.
    selected_strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision_actor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monitoring_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_recovered_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_recovered_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_value_recovered: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_value_recovered: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_score_components: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recovery_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    root_cause_status: Mapped[str] = mapped_column(String(24), default="unknown")


class RecoveryStrategy(Base, ScopedMixin):
    __tablename__ = "recovery_strategies"
    recovery_case_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_cases.id", ondelete="CASCADE"), index=True)
    strategy_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="playbook")
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    expected_recovered_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_recovered_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_value_recovered: Mapped[float | None] = mapped_column(Float, nullable=True)
    direct_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    implementation_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    operational_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_effectiveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_success_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_components: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ranking_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    constraints: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    required_authorities: Mapped[list[str]] = mapped_column(JSON, default=list)
    input_freshness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class RecoveryStrategyAction(Base, ScopedMixin):
    __tablename__ = "recovery_strategy_actions"
    strategy_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_strategies.id", ondelete="CASCADE"), index=True)
    operational_action_id: Mapped[str] = mapped_column(String(64), ForeignKey("operational_actions.id", ondelete="CASCADE"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("strategy_id", "operational_action_id", name="uq_recovery_strategy_action"),)


class RecoveryOutcome(Base, ScopedMixin):
    __tablename__ = "recovery_outcomes"
    recovery_case_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_cases.id"), unique=True, index=True)
    strategy_id: Mapped[str] = mapped_column(String(64), ForeignKey("recovery_strategies.id"), index=True)
    baseline_snapshot_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_state_snapshots.id"), nullable=True)
    post_snapshot_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("operational_state_snapshots.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_recovered_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_recovered_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_value_recovered: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_value_recovered: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_value_recovered: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_to_first_response_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_to_recovery_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_achieved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    partial_recovery: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    quality_side_effect: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    safety_side_effect: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    delivery_side_effect: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recurred_within_7d: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recurred_within_30d: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outcome_rating: Mapped[str] = mapped_column(String(32), index=True)
    verification_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context_fingerprint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics_before: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics_after: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ImprovementInvestigation(Base, ScopedMixin):
    __tablename__ = "improvement_investigations"
    title: Mapped[str] = mapped_column(String(240))
    problem_signature: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    related_recovery_case_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    estimated_annual_loss: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    status: Mapped[str] = mapped_column(String(32), default="suggested", index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    countermeasure: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("improvement_experiments.id"), nullable=True)


class ForecastEvaluation(Base, ScopedMixin):
    __tablename__ = "forecast_evaluations"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id"), index=True)
    forecast_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    horizon_seconds: Mapped[int] = mapped_column(Integer)
    forecast_quantity: Mapped[float] = mapped_column(Float)
    actual_eventual_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ImprovementExperiment(Base, ScopedMixin):
    __tablename__ = "improvement_experiments"
    title: Mapped[str] = mapped_column(String(240))
    opportunity_key: Mapped[str] = mapped_column(String(160), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    hypothesis: Mapped[str] = mapped_column(Text)
    baseline: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    intervention: Mapped[str] = mapped_column(Text)
    target: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    statistical_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ImprovementBenefitMeasurement(Base, ScopedMixin):
    __tablename__ = "improvement_benefit_measurements"
    experiment_id: Mapped[str] = mapped_column(String(64), ForeignKey("improvement_experiments.id"), index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    metric: Mapped[str] = mapped_column(String(120))
    baseline_value: Mapped[float] = mapped_column(Float)
    observed_value: Mapped[float] = mapped_column(Float)
    annualized_value: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(16), default="INR")
    confidence_state: Mapped[str] = mapped_column(String(24), default="estimated")
    calculation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ShiftBriefing(Base, ScopedMixin):
    __tablename__ = "shift_briefings"
    shift_id: Mapped[str] = mapped_column(String(64), ForeignKey("plant_shifts.id"), index=True)
    briefing_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    title: Mapped[str] = mapped_column(String(180))
    summary: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    priorities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    losses: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    carry_over: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("shift_id", "briefing_type", name="uq_shift_briefing_type"),)


class OperationalSetupProfile(Base, ScopedMixin):
    __tablename__ = "operational_setup_profiles"
    activation_stage: Mapped[str] = mapped_column(String(32), default="plant")
    primary_use_case: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled_data_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    production_calendar: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    kpi_targets: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    loss_categories: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    escalation_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    value_formulas: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    action_policies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    completed_stages: Mapped[list[str]] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", name="uq_operational_setup_plant"),)


class OperationalDetectorRule(Base, ScopedMixin):
    __tablename__ = "operational_detector_rules"
    detector_key: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    severity_bands: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    owner_role: Mapped[str] = mapped_column(String(64))
    source_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "detector_key", name="uq_operational_detector_rule"),)


class EdgeGateway(Base, ScopedMixin):
    __tablename__ = "edge_gateways"
    name: Mapped[str] = mapped_column(String(180))
    runtime_version: Mapped[str] = mapped_column(String(64))
    certificate_fingerprint: Mapped[str] = mapped_column(String(160), unique=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    config_signature: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="configured", index=True)
    transport: Mapped[str] = mapped_column(String(32), default="https_tls")
    outbound_only: Mapped[bool] = mapped_column(Boolean, default=True)
    buffer_depth: Mapped[int] = mapped_column(Integer, default=0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EdgeSourceMapping(Base, ScopedMixin):
    __tablename__ = "edge_source_mappings"
    gateway_id: Mapped[str] = mapped_column(String(64), ForeignKey("edge_gateways.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("plant_assets.id"), index=True)
    protocol: Mapped[str] = mapped_column(String(32))
    source_address: Mapped[str] = mapped_column(String(240))
    canonical_signal: Mapped[str] = mapped_column(String(80))
    source_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    canonical_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scale: Mapped[float] = mapped_column(Float, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("gateway_id", "source_address", name="uq_edge_source_address"),)


class EdgeSourceHealth(Base, ScopedMixin):
    __tablename__ = "edge_source_health"
    gateway_id: Mapped[str] = mapped_column(String(64), ForeignKey("edge_gateways.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(180))
    protocol: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    __table_args__ = (UniqueConstraint("gateway_id", "source_name", name="uq_edge_source_health"),)


class EdgeIngestReceipt(Base, ScopedMixin):
    __tablename__ = "edge_ingest_receipts"
    gateway_id: Mapped[str] = mapped_column(String(64), ForeignKey("edge_gateways.id"), index=True)
    message_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(80))
    asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_hash: Mapped[str] = mapped_column(String(160))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("gateway_id", "message_id", name="uq_edge_message"),)


class V2PreparedAction(Base, ScopedMixin):
    __tablename__ = "v2_prepared_actions"
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(240))
    proposed_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="prepared", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# Register bounded-module ORM tables with the shared metadata.  This import is
# intentionally late: SCM models reuse Base and ScopedMixin declared here.
from app.scm import models as _scm_models  # noqa: E402,F401
from app.platform import models as _platform_models  # noqa: E402,F401


# Keep metadata-created development/test databases aligned with migration 0027.
# Several models define their own table constraints, so a mixin-level
# ``__table_args__`` would be silently replaced; append this invariant once all
# mapped tables have been constructed instead.
for _table in Base.metadata.tables.values():
    if "tenant_id" in _table.c and "business_number" in _table.c:
        _constraint_name = f"uq_{_table.name}_tenant_business_number"
        if not any(getattr(item, "name", None) == _constraint_name for item in _table.constraints):
            _table.append_constraint(UniqueConstraint("tenant_id", "business_number", name=_constraint_name))
