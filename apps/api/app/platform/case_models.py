"""Shared case, decision, recovery, and attribution persistence.

Domain detections remain in their owning modules.  These records are the
cross-domain, user-facing envelope and deliberately contain no SCM engine
logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, ScopedMixin


VALUE = Numeric(20, 6)


class CaseEntityLink(Base, ScopedMixin):
    __tablename__ = "platform_case_entity_links"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    relationship: Mapped[str] = mapped_column(String(48), index=True)
    importance: Mapped[float] = mapped_column(Float, default=1.0)
    __table_args__ = (UniqueConstraint("case_id", "entity_type", "entity_id", "relationship", name="uq_case_entity_link"),)


class CaseEvidence(Base, ScopedMixin):
    __tablename__ = "platform_case_evidence"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(80), index=True)
    source_entity_type: Mapped[str] = mapped_column(String(80))
    source_entity_id: Mapped[str] = mapped_column(String(64))
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    freshness_state: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("case_id", "source_event_id", name="uq_case_source_event"),)


class CaseCause(Base, ScopedMixin):
    __tablename__ = "platform_case_causes"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    cause_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class BusinessExposure(Base, ScopedMixin):
    __tablename__ = "platform_business_exposures"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(80), index=True)
    baseline: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    projected: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    delta: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    unit: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    time_horizon_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_horizon_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    methodology: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    attribution_state: Mapped[str] = mapped_column(String(32), default="PROJECTED")
    calculation_version: Mapped[str] = mapped_column(String(80), default="exposure@1")
    input_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NetworkConstraint(Base, ScopedMixin):
    """Effective-dated constraint for the first recovery slice.

    ``constraint_type`` distinguishes lane, transfer, qualification, sourcing,
    lot-size, reschedule-window, routing, and work-center capability contracts.
    """
    __tablename__ = "platform_network_constraints"
    constraint_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(120))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    freshness_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CustomerOrder(Base, ScopedMixin):
    __tablename__ = "platform_customer_orders"
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    order_number: Mapped[str] = mapped_column(String(120), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    source_system: Mapped[str] = mapped_column(String(80), default="manual")
    source_record_id: Mapped[str] = mapped_column(String(180))
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "source_record_id", name="uq_platform_customer_order_source"),)


class CustomerOrderLine(Base, ScopedMixin):
    __tablename__ = "platform_customer_order_lines"
    customer_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_customer_orders.id", ondelete="CASCADE"), index=True)
    line_number: Mapped[str] = mapped_column(String(48))
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_products.id"), index=True)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    quantity: Mapped[float] = mapped_column(VALUE)
    uom: Mapped[str] = mapped_column(String(32), default="EA")
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    __table_args__ = (UniqueConstraint("customer_order_id", "line_number", name="uq_platform_customer_order_line"),)


class ActionPlan(Base, ScopedMixin):
    __tablename__ = "platform_action_plans"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    decision_record_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_decision_records.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    strategy_type: Mapped[str] = mapped_column(String(80))
    objective: Mapped[str] = mapped_column(Text)
    expected_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ActionPlanStep(Base, ScopedMixin):
    __tablename__ = "platform_action_plan_steps"
    action_plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_action_plans.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    owner_team: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dependency_step_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    action_intent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_action_intents.id"), nullable=True, index=True)
    evidence_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("action_plan_id", "sequence", name="uq_platform_action_plan_step"),)


class FeasibilityEvaluation(Base, ScopedMixin):
    __tablename__ = "platform_feasibility_evaluations"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    strategy_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    estimated_cost: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    time_to_effect_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    approval_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    freshness_state: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    simulation_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ConstraintResult(Base, ScopedMixin):
    __tablename__ = "platform_constraint_results"
    feasibility_evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_feasibility_evaluations.id", ondelete="CASCADE"), index=True)
    constraint_key: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(24), index=True)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DecisionRecord(Base, ScopedMixin):
    __tablename__ = "platform_decision_records"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    baseline_state_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    planning_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recommended_alternative_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_alternative_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approver_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version: Mapped[str] = mapped_column(String(80), default="decision-policy@1")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DecisionAlternative(Base, ScopedMixin):
    __tablename__ = "platform_decision_alternatives"
    decision_record_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_decision_records.id", ondelete="CASCADE"), index=True)
    strategy_type: Mapped[str] = mapped_column(String(80), index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_impact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cost: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    time_to_effect_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    success_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    side_effects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    feasibility_evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_feasibility_evaluations.id"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ranking: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    simulation_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    immutable: Mapped[bool] = mapped_column(Boolean, default=False)


class RecoveryTarget(Base, ScopedMixin):
    __tablename__ = "platform_recovery_targets"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    metric: Mapped[str] = mapped_column(String(80))
    operator: Mapped[str] = mapped_column(String(8))
    threshold: Mapped[float] = mapped_column(VALUE)
    required_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    required_observation_count: Mapped[int] = mapped_column(Integer, default=2)
    freshness_requirement: Mapped[str] = mapped_column(String(24), default="FRESH")
    baseline: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    target: Mapped[float] = mapped_column(VALUE)


class RecoveryObservation(Base, ScopedMixin):
    __tablename__ = "platform_recovery_observations"
    target_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_recovery_targets.id", ondelete="CASCADE"), index=True)
    source_entity: Mapped[dict[str, Any]] = mapped_column(JSON)
    observed_value: Mapped[float] = mapped_column(VALUE)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    freshness: Mapped[str] = mapped_column(String(24))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    satisfied: Mapped[bool] = mapped_column(Boolean)


class RecoveryVerification(Base, ScopedMixin):
    __tablename__ = "platform_recovery_verifications"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stability_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stability_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_completeness: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ValueAttribution(Base, ScopedMixin):
    __tablename__ = "platform_value_attributions"
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), index=True)
    action_intent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_action_intents.id"), nullable=True)
    metric: Mapped[str] = mapped_column(String(80), index=True)
    baseline: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    counterfactual: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    actual: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    attributed_value: Mapped[float | None] = mapped_column(VALUE, nullable=True)
    unit: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    methodology: Mapped[str] = mapped_column(Text)
    confidence_level: Mapped[str] = mapped_column(String(32))
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GigiInsight(Base, ScopedMixin):
    __tablename__ = "gigi_insights"
    case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), nullable=True, index=True)
    membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(24), index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    deduplication_signature: Mapped[str] = mapped_column(String(180))
    delivery_state: Mapped[str] = mapped_column(String(32), default="FEED")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_evaluation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalation_state: Mapped[str] = mapped_column(String(32), default="NONE")
    __table_args__ = (UniqueConstraint("tenant_id", "deduplication_signature", name="uq_gigi_insight_signature"),)
