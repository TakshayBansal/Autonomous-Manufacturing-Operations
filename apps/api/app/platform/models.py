"""ORM records for the incremental GenuineGigs core platform."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, ScopedMixin, utcnow


class PlatformMaterial(Base, ScopedMixin):
    __tablename__ = "platform_materials"
    company_id: Mapped[str] = mapped_column(String(64), ForeignKey("companies.id"), index=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(300))
    material_type: Mapped[str] = mapped_column(String(32), default="OTHER", index=True)
    base_uom_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("uoms.id"), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_platform_material_company_code"),)


class PlatformMaterialSite(Base, ScopedMixin):
    __tablename__ = "platform_material_sites"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    planning_attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("material_id", "plant_id", name="uq_platform_material_site"),)


class PlatformProduct(Base, ScopedMixin):
    __tablename__ = "platform_products"
    company_id: Mapped[str] = mapped_column(String(64), ForeignKey("companies.id"), index=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(300))
    product_type: Mapped[str] = mapped_column(String(32), default="FINISHED_GOOD")
    base_uom_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("uoms.id"), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_platform_product_company_code"),)


class PlatformBOM(Base, ScopedMixin):
    __tablename__ = "platform_boms"
    company_id: Mapped[str] = mapped_column(String(64), ForeignKey("companies.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_products.id"), index=True)
    revision: Mapped[str] = mapped_column(String(48), default="A")
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    __table_args__ = (UniqueConstraint("product_id", "revision", name="uq_platform_bom_revision"),)


class PlatformBOMItem(Base, ScopedMixin):
    __tablename__ = "platform_bom_items"
    bom_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_boms.id", ondelete="CASCADE"), index=True)
    component_entity_type: Mapped[str] = mapped_column(String(32), default="material")
    component_id: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    uom_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("uoms.id"), nullable=True)
    scrap_factor: Mapped[float] = mapped_column(Float, default=0)
    alternate_group: Mapped[str | None] = mapped_column(String(80), nullable=True)
    line_number: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("bom_id", "line_number", name="uq_platform_bom_item_line"),)


class PlatformInventoryLocation(Base, ScopedMixin):
    __tablename__ = "platform_inventory_locations"
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180))
    location_type: Mapped[str] = mapped_column(String(48), default="warehouse")
    parent_location_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "code", name="uq_platform_inventory_location"),)


class PlatformInventoryPosition(Base, ScopedMixin):
    __tablename__ = "platform_inventory_positions"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id"), index=True)
    location_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_inventory_locations.id"), index=True)
    on_hand_qty: Mapped[float] = mapped_column(Float, default=0)
    available_qty: Mapped[float] = mapped_column(Float, default=0)
    reserved_qty: Mapped[float] = mapped_column(Float, default=0)
    blocked_qty: Mapped[float] = mapped_column(Float, default=0)
    in_transit_qty: Mapped[float] = mapped_column(Float, default=0)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_authority: Mapped[str] = mapped_column(String(100))
    freshness_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    __table_args__ = (UniqueConstraint("material_id", "location_id", name="uq_platform_inventory_position"),)


class EntityRelationship(Base, ScopedMixin):
    __tablename__ = "platform_entity_relationships"
    source_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    source_entity_id: Mapped[str] = mapped_column(String(64), index=True)
    relationship_type: Mapped[str] = mapped_column(String(80), index=True)
    target_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    target_entity_id: Mapped[str] = mapped_column(String(64), index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_system: Mapped[str] = mapped_column(String(100), default="genuinegigs", index=True)
    provenance_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", "relationship_type", "target_entity_type", "target_entity_id", name="uq_platform_entity_relationship"),)


class SourceSystem(Base, ScopedMixin):
    __tablename__ = "platform_source_systems"
    key: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(180))
    system_type: Mapped[str] = mapped_column(String(48), index=True)
    connection_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_connections.id"), nullable=True, index=True)
    authority: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    health: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_platform_source_system"),)


class PlatformStateSnapshot(Base, ScopedMixin):
    __tablename__ = "platform_state_snapshots"
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(48), index=True)
    observed: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    derived: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    predicted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    planned: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    freshness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    projection_version: Mapped[str] = mapped_column(String(80), default="platform-state@1")
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("tenant_id", "entity_type", "entity_id", "snapshot_type", "captured_at", name="uq_platform_state_snapshot"),)


class ExternalEntityReference(Base, ScopedMixin):
    __tablename__ = "external_entity_references"
    source_system: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    canonical_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    canonical_entity_id: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(240), index=True)
    external_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "entity_type", "external_id", name="uq_platform_external_entity"),)


class DataProvenance(Base, ScopedMixin):
    __tablename__ = "data_provenance"
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str] = mapped_column(String(100), index=True)
    source_reference: Mapped[str | None] = mapped_column(String(240), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    mapping_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transformation: Mapped[str | None] = mapped_column(String(160), nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), default="accepted", index=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)


class DataQualityIssue(Base, ScopedMixin):
    __tablename__ = "data_quality_issues"
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rule_key: Mapped[str] = mapped_column(String(120), index=True)
    severity: Mapped[str] = mapped_column(String(24), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MaterialStateProjection(Base, ScopedMixin):
    __tablename__ = "platform_material_state_projections"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id", ondelete="CASCADE"), index=True)
    observed: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    derived: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    planned: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    predicted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_freshness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    algorithm_version: Mapped[str] = mapped_column(String(80), default="platform-state@1")
    __table_args__ = (UniqueConstraint("material_id", "plant_id", name="uq_platform_material_state"),)


class ActionIntent(Base, ScopedMixin):
    __tablename__ = "platform_action_intents"
    action_type: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    requested_by_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    requested_by_type: Mapped[str] = mapped_column(String(32), default="human")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    originating_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    expected_impact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="medium", index=True)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_platform_action_idempotency"),)


class ActionPolicyEvaluation(Base, ScopedMixin):
    __tablename__ = "platform_action_policy_evaluations"
    action_intent_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_action_intents.id", ondelete="CASCADE"), index=True)
    allowed: Mapped[bool] = mapped_column(Boolean)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    policy_version: Mapped[str] = mapped_column(String(80), default="platform-policy@1")
    reason_code: Mapped[str] = mapped_column(String(120))
    obligations: Mapped[list[str]] = mapped_column(JSON, default=list)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ActionApproval(Base, ScopedMixin):
    __tablename__ = "platform_action_approvals"
    action_intent_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_action_intents.id", ondelete="CASCADE"), index=True)
    approver_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionExecution(Base, ScopedMixin):
    __tablename__ = "platform_action_executions"
    action_intent_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_action_intents.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(32), default="simulated")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    executor: Mapped[str] = mapped_column(String(120))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ActionOutcome(Base, ScopedMixin):
    __tablename__ = "platform_action_outcomes"
    action_intent_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_action_intents.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_action_executions.id", ondelete="CASCADE"), unique=True, index=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified", index=True)
    outcome_type: Mapped[str] = mapped_column(String(80), default="simulation_completed")
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationalCase(Base, ScopedMixin):
    __tablename__ = "platform_operational_cases"
    case_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(240))
    severity: Mapped[str] = mapped_column(String(24), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    owner_membership_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    canonical_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    canonical_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resolution_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_possible_detection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    expected_impact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    responsible_team: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    recovery_state: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    current_strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aggregation_key: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)


class PlatformPurchaseOrder(Base, ScopedMixin):
    __tablename__ = "platform_purchase_orders"
    order_number: Mapped[str] = mapped_column(String(120), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(48), default="OPEN", index=True)
    currency: Mapped[str] = mapped_column(String(16), default="USD")
    original_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_authority: Mapped[str] = mapped_column(String(100), default="genuinegigs")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "order_number", name="uq_platform_po_number"),)


class PlatformPurchaseOrderLine(Base, ScopedMixin):
    __tablename__ = "platform_purchase_order_lines"
    purchase_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_purchase_orders.id", ondelete="CASCADE"), index=True)
    line_number: Mapped[str] = mapped_column(String(48))
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    received_quantity: Mapped[float] = mapped_column(Float, default=0)
    uom_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("uoms.id"), nullable=True)
    __table_args__ = (UniqueConstraint("purchase_order_id", "line_number", name="uq_platform_po_line"),)


class PlatformWorkOrderReference(Base, ScopedMixin):
    __tablename__ = "platform_work_order_references"
    work_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_work_orders.id", ondelete="CASCADE"), unique=True, index=True)
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_products.id"), index=True)
    work_center_id: Mapped[str] = mapped_column(String(64), ForeignKey("production_lines.id"), index=True)
    equipment_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("plant_assets.id"), nullable=True, index=True)
    source_authority: Mapped[str] = mapped_column(String(100), default="genuinegigs")


class PlatformScenarioDefinition(Base, ScopedMixin):
    __tablename__ = "platform_scenario_definitions"
    domain: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(180))
    baseline_snapshot_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_state_snapshots.id"), nullable=True)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    horizon_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class PlatformSimulationRun(Base, ScopedMixin):
    __tablename__ = "platform_simulation_runs"
    scenario_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_scenario_definitions.id", ondelete="CASCADE"), index=True)
    algorithm: Mapped[str] = mapped_column(String(120))
    algorithm_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    predicted_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actual_outcome: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Keep additive vNext case tables in shared metadata when callers import only
# ``app.db.models`` (notably fresh development databases and the test harness).
from app.platform import case_models as _case_models  # noqa: E402,F401
