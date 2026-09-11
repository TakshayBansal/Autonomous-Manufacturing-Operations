from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, ScopedMixin


QTY = Numeric(20, 6)


class SCMMaterial(Base, ScopedMixin):
    __tablename__ = "scm_materials"
    company_id: Mapped[str] = mapped_column(String(64), ForeignKey("companies.id"), index=True)
    material_code: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    material_type: Mapped[str] = mapped_column(String(32), default="OTHER", index=True)
    base_uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    specification_text: Mapped[str] = mapped_column(Text, default="")
    manufacturer_part_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_part_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("company_id", "material_code", name="uq_scm_material_company_code"),)


class SCMMaterialPlant(Base, ScopedMixin):
    __tablename__ = "scm_material_plants"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("items.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("material_id", "plant_id", name="uq_scm_material_plant"),
        UniqueConstraint("tenant_id", "plant_id", "item_id", name="uq_scm_material_plant_item"),
    )


class SCMStorageLocation(Base, ScopedMixin):
    __tablename__ = "scm_storage_locations"
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180))
    external_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "code", name="uq_scm_storage_location_code"),)


class SCMMaterialPlantPolicy(Base, ScopedMixin):
    __tablename__ = "scm_material_plant_policies"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id", ondelete="CASCADE"), index=True)
    procurement_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    default_supplier_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("suppliers.id"), nullable=True)
    planned_lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goods_receipt_processing_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    safety_stock_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    minimum_order_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    order_multiple: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    minimum_coverage_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_coverage_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planning_time_fence_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancellation_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expedite_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("material_id", "plant_id", name="uq_scm_material_policy"),)


class SCMUOMConversion(Base, ScopedMixin):
    __tablename__ = "scm_uom_conversions"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id", ondelete="CASCADE"), index=True)
    from_uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    to_uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    factor: Mapped[Decimal] = mapped_column(QTY)
    __table_args__ = (UniqueConstraint("material_id", "from_uom_id", "to_uom_id", name="uq_scm_uom_conversion"),)


class SCMMaterialSupplier(Base, ScopedMixin):
    __tablename__ = "scm_material_suppliers"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(64), ForeignKey("suppliers.id"), index=True)
    supplier_material_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approved_status: Mapped[str] = mapped_column(String(32), default="APPROVED")
    priority_rank: Mapped[int] = mapped_column(Integer, default=1)
    contract_lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_order_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    order_multiple: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    cancellation_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pushout_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    cancellation_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    expedite_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    __table_args__ = (UniqueConstraint("material_id", "plant_id", "supplier_id", name="uq_scm_material_supplier"),)


class SCMCustomer(Base, ScopedMixin):
    __tablename__ = "scm_customers"
    company_id: Mapped[str] = mapped_column(String(64), ForeignKey("companies.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180))
    external_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_scm_customer_company_code"),)


class SCMMaterialCustomerUsage(Base, ScopedMixin):
    __tablename__ = "scm_material_customer_usage"
    finished_good_material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_customers.id"), index=True)
    customer_part_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    program_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    __table_args__ = (UniqueConstraint("finished_good_material_id", "plant_id", "customer_id", "program_name", name="uq_scm_customer_usage"),)


class SCMBOM(Base, ScopedMixin):
    __tablename__ = "scm_boms"
    company_id: Mapped[str] = mapped_column(String(64), ForeignKey("companies.id"), index=True)
    parent_material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    bom_code: Mapped[str] = mapped_column(String(100))
    revision: Mapped[str] = mapped_column(String(48), default="A")
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    source_system: Mapped[str] = mapped_column(String(80), default="manual")
    external_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_import_batches.id"), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "bom_code", "revision", name="uq_scm_bom_revision"),)


class SCMBOMLine(Base, ScopedMixin):
    __tablename__ = "scm_bom_lines"
    bom_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_boms.id", ondelete="CASCADE"), index=True)
    component_material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    quantity_per: Mapped[Decimal] = mapped_column(QTY)
    uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    scrap_factor: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    operation_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    line_number: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("bom_id", "line_number", name="uq_scm_bom_line_number"),)


class SCMInventorySnapshot(Base, ScopedMixin):
    __tablename__ = "scm_inventory_snapshots"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    storage_location_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_storage_locations.id"), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    on_hand_qty: Mapped[Decimal] = mapped_column(QTY)
    unrestricted_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    quality_hold_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    blocked_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    reserved_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    available_qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    source_system: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = mapped_column(String(240))
    import_batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_import_batches.id"), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "source_record_id", name="uq_scm_inventory_source"),)


class SCMDemandForecast(Base, ScopedMixin):
    __tablename__ = "scm_demand_forecasts"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_customers.id"), nullable=True)
    forecast_version: Mapped[str] = mapped_column(String(80))
    bucket_start: Mapped[date] = mapped_column(Date, index=True)
    bucket_end: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    forecast_type: Mapped[str] = mapped_column(String(48), default="BASELINE")
    source_system: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = mapped_column(String(240))
    import_batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_import_batches.id"), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "source_record_id", name="uq_scm_forecast_source"),)


class SCMMaterialRequirement(Base, ScopedMixin):
    __tablename__ = "scm_material_requirements"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    required_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    requirement_type: Mapped[str] = mapped_column(String(48), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    finished_good_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_materials.id"), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_customers.id"), nullable=True)
    source_system: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(240))
    import_batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_import_batches.id"), nullable=True)
    lineage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "external_id", name="uq_scm_requirement_source"),)


class SCMSupplyOrder(Base, ScopedMixin):
    __tablename__ = "scm_supply_orders"
    supply_type: Mapped[str] = mapped_column(String(48), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("suppliers.id"), nullable=True)
    order_number: Mapped[str] = mapped_column(String(120), index=True)
    line_number: Mapped[str] = mapped_column(String(48))
    ordered_qty: Mapped[Decimal] = mapped_column(QTY)
    received_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    status: Mapped[str] = mapped_column(String(32), index=True)
    firmness: Mapped[str] = mapped_column(String(32), default="FIRM")
    source_system: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = mapped_column(String(240))
    source_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_import_batches.id"), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "source_record_id", name="uq_scm_supply_order_source"),)


class SCMSupplyScheduleLine(Base, ScopedMixin):
    __tablename__ = "scm_supply_schedule_lines"
    supply_order_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_supply_orders.id", ondelete="CASCADE"), index=True)
    schedule_line_number: Mapped[str] = mapped_column(String(48))
    scheduled_qty: Mapped[Decimal] = mapped_column(QTY)
    received_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    original_due_date: Mapped[date] = mapped_column(Date)
    current_due_date: Mapped[date] = mapped_column(Date, index=True)
    supplier_commit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    source_record_id: Mapped[str] = mapped_column(String(240))
    __table_args__ = (UniqueConstraint("supply_order_id", "schedule_line_number", name="uq_scm_supply_schedule_line"),)


class SCMGoodsReceipt(Base, ScopedMixin):
    __tablename__ = "scm_goods_receipts"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    supply_order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_supply_orders.id"), nullable=True)
    receipt_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    uom_id: Mapped[str] = mapped_column(String(32), ForeignKey("uoms.id"))
    source_system: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = mapped_column(String(240))
    import_batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("integration_import_batches.id"), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "source_record_id", name="uq_scm_receipt_source"),)


class SCMDataSourceState(Base, ScopedMixin):
    __tablename__ = "scm_data_source_states"
    source_key: Mapped[str] = mapped_column(String(120))
    last_successful_import: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    expected_frequency_seconds: Mapped[int] = mapped_column(Integer, default=86400)
    stale_after_seconds: Mapped[int] = mapped_column(Integer, default=90000)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "source_key", name="uq_scm_source_state"),)


class SCMPlanningPolicySet(Base, ScopedMixin):
    __tablename__ = "scm_planning_policy_sets"
    name: Mapped[str] = mapped_column(String(160))
    policy_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "name", "policy_version", name="uq_scm_policy_version"),)


class SCMPlanningProfile(Base, ScopedMixin):
    __tablename__ = "scm_planning_profiles"
    name: Mapped[str] = mapped_column(String(160))
    planning_horizon_days: Mapped[int] = mapped_column(Integer, default=210)
    near_term_bucket: Mapped[str] = mapped_column(String(24), default="DAILY")
    long_term_bucket: Mapped[str] = mapped_column(String(24), default="WEEKLY")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency: Mapped[str] = mapped_column(String(16), default="USD")
    demand_precedence: Mapped[list[str]] = mapped_column(JSON, default=lambda: [
        "CUSTOMER_ORDER", "WORK_ORDER", "PRODUCTION_PLAN", "INDENT", "FORECAST"
    ])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "name", name="uq_scm_planning_profile"),)


class SCMDemandPlan(Base, ScopedMixin):
    __tablename__ = "scm_demand_plans"
    plan_version: Mapped[str] = mapped_column(String(80))
    source_system_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_source_systems.id"), nullable=True, index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("data_provenance.id"), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "plan_version", name="uq_scm_demand_plan_version"),)


class SCMDemandBucket(Base, ScopedMixin):
    __tablename__ = "scm_demand_buckets"
    demand_plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_demand_plans.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_products.id"), nullable=True, index=True)
    material_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_materials.id"), nullable=True, index=True)
    work_order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_work_orders.id"), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_customers.id"), nullable=True, index=True)
    oem_reference: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    bucket_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    demand_type: Mapped[str] = mapped_column(String(48), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    source_reference: Mapped[str] = mapped_column(String(240))
    provenance_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("data_provenance.id"), nullable=True, index=True)
    lineage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("demand_plan_id", "source_reference", name="uq_scm_demand_bucket_source"),)


class SCMPlanningScenario(Base, ScopedMixin):
    __tablename__ = "scm_planning_scenarios"
    name: Mapped[str] = mapped_column(String(180))
    scenario_type: Mapped[str] = mapped_column(String(32), default="BASELINE")
    base_scenario_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_planning_scenarios.id"), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    baseline_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    duplicated_from_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class SCMScenarioOverride(Base, ScopedMixin):
    __tablename__ = "scm_scenario_overrides"
    scenario_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_scenarios.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    override_type: Mapped[str] = mapped_column(String(48), index=True)
    source_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)


class SCMPlanningAdjustment(Base, ScopedMixin):
    __tablename__ = "scm_planning_adjustments"
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    adjustment_type: Mapped[str] = mapped_column(String(48), index=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_state: Mapped[str] = mapped_column(String(32), default="PENDING")


class SCMManualDataEntry(Base, ScopedMixin):
    """Append-only, human-authored planning fact or source overlay."""
    __tablename__ = "scm_manual_data_entries"
    entry_type: Mapped[str] = mapped_column(String(64), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    canonical_material_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_materials.id"), nullable=True, index=True)
    target_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("suppliers.id"), nullable=True, index=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    previous_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source_authority: Mapped[str] = mapped_column(String(80), default="genuinegigs_manual", index=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    created_by_membership_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("workspace_memberships.id"), nullable=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    supersedes_entry_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_manual_data_entries.id"), nullable=True)
    planning_run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_planning_runs.id"), nullable=True, index=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_scm_manual_entry_idempotency"),)


class SCMPlanningRun(Base, ScopedMixin):
    __tablename__ = "scm_planning_runs"
    scenario_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_scenarios.id"), index=True)
    policy_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_policy_sets.id"), index=True)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    horizon_start: Mapped[date] = mapped_column(Date)
    horizon_end: Mapped[date] = mapped_column(Date)
    input_version_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    engine_version: Mapped[str] = mapped_column(String(48))
    policy_version: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    materials_processed: Mapped[int] = mapped_column(Integer, default=0)
    exceptions_generated: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    planning_profile_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_planning_profiles.id"), nullable=True, index=True)
    demand_plan_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_demand_plans.id"), nullable=True, index=True)
    input_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), default="MANUAL", index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SCMPlanningInputSnapshot(Base, ScopedMixin):
    __tablename__ = "scm_planning_input_snapshots"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), unique=True, index=True)
    snapshot_version: Mapped[str] = mapped_column(String(80), default="scm-input@1")
    algorithm_version: Mapped[str] = mapped_column(String(80))
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_freshness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)


class SCMPlanningEvent(Base, ScopedMixin):
    __tablename__ = "scm_planning_events"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_scenarios.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(QTY)
    source_entity_type: Mapped[str] = mapped_column(String(80))
    source_entity_id: Mapped[str] = mapped_column(String(64))
    firmness: Mapped[str] = mapped_column(String(32), default="FIRM")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    evidence_type: Mapped[str] = mapped_column(String(32), default="DETECTED_FACT")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("planning_run_id", "source_entity_type", "source_entity_id", "event_type", name="uq_scm_run_source_event"),
        Index("ix_scm_event_run_material_date", "planning_run_id", "material_id", "plant_id", "event_date"),
    )


class SCMMaterialProjectionPoint(Base, ScopedMixin):
    __tablename__ = "scm_material_projection_points"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    projection_date: Mapped[date] = mapped_column(Date, index=True)
    opening_balance: Mapped[Decimal] = mapped_column(QTY)
    supply_qty: Mapped[Decimal] = mapped_column(QTY)
    demand_qty: Mapped[Decimal] = mapped_column(QTY)
    closing_balance: Mapped[Decimal] = mapped_column(QTY)
    safety_stock_qty: Mapped[Decimal] = mapped_column(QTY)
    risk_status: Mapped[str] = mapped_column(String(24), index=True)
    canonical_material_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_materials.id"), nullable=True, index=True)
    confirmed_receipts: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    planned_receipts: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    gross_demand: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    reserved_demand: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    projected_after_safety: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    shortage_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    excess_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    runway_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planning_status: Mapped[str] = mapped_column(String(24), default="UNKNOWN", index=True)
    source_freshness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("planning_run_id", "material_id", "plant_id", "projection_date", name="uq_scm_projection_point"),)


class SCMSupplyDemandPeg(Base, ScopedMixin):
    __tablename__ = "scm_supply_demand_pegs"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_scenarios.id"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    supply_event_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_events.id"), index=True)
    demand_event_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_events.id"), index=True)
    pegged_qty: Mapped[Decimal] = mapped_column(QTY)
    peg_strategy: Mapped[str] = mapped_column(String(48), default="FIFO_REQUIRED_DATE")
    __table_args__ = (UniqueConstraint("planning_run_id", "supply_event_id", "demand_event_id", name="uq_scm_supply_demand_peg"),)


class SCMMaterialRiskSummary(Base, ScopedMixin):
    __tablename__ = "scm_material_risk_summaries"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    first_breach_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    stockout_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    shortage_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    recovery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    severity: Mapped[str] = mapped_column(String(24), index=True)
    priority_score: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    priority_factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    affected_finished_goods_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_customers_count: Mapped[int] = mapped_column(Integer, default=0)
    recommended_action_count: Mapped[int] = mapped_column(Integer, default=0)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("planning_run_id", "material_id", "plant_id", name="uq_scm_risk_summary"),)


class SCMShortageWindow(Base, ScopedMixin):
    __tablename__ = "scm_shortage_windows"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    canonical_material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    duration_days: Mapped[int] = mapped_column(Integer)
    max_shortage_qty: Mapped[Decimal] = mapped_column(QTY)
    recovery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    __table_args__ = (UniqueConstraint("planning_run_id", "material_id", "start_date", name="uq_scm_shortage_window"),)


class SCMMaterialRisk(Base, ScopedMixin):
    __tablename__ = "scm_material_risks"
    latest_planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    canonical_material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id"), index=True)
    risk_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(24), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    business_impact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[Decimal] = mapped_column(QTY, default=Decimal("1"))
    root_causes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    affected_entities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="NEW", index=True)
    operational_case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("platform_operational_cases.id"), nullable=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    semantic_key: Mapped[str] = mapped_column(String(240), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "plant_id", "semantic_key", name="uq_scm_active_risk_semantic"),)


class SCMProductReadiness(Base, ScopedMixin):
    __tablename__ = "scm_product_readiness"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_products.id"), index=True)
    work_order_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("production_work_orders.id"), nullable=True, index=True)
    required_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    total_components: Mapped[int] = mapped_column(Integer)
    covered_components: Mapped[int] = mapped_column(Integer)
    at_risk_components: Mapped[int] = mapped_column(Integer)
    blocking_components: Mapped[int] = mapped_column(Integer)
    affected_quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("planning_run_id", "product_id", "work_order_id", "required_date", name="uq_scm_product_readiness"),)


class SCMComponentReadiness(Base, ScopedMixin):
    __tablename__ = "scm_component_readiness"
    readiness_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_product_readiness.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id"), index=True)
    required_qty: Mapped[Decimal] = mapped_column(QTY)
    projected_available_qty: Mapped[Decimal] = mapped_column(QTY)
    shortage_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), index=True)
    lineage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("readiness_id", "material_id", name="uq_scm_component_readiness"),)


class SCMPlanningRunDelta(Base, ScopedMixin):
    __tablename__ = "scm_planning_run_deltas"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    previous_run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scm_planning_runs.id"), nullable=True, index=True)
    canonical_material_id: Mapped[str] = mapped_column(String(64), ForeignKey("platform_materials.id"), index=True)
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    current_status: Mapped[str] = mapped_column(String(24))
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    effect: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("planning_run_id", "canonical_material_id", name="uq_scm_run_delta_material"),)


class SCMRecommendation(Base, ScopedMixin):
    __tablename__ = "scm_recommendations"
    planning_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id", ondelete="CASCADE"), index=True)
    risk_summary_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_material_risk_summaries.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_materials.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    current_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proposed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    constraints_checked: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    score: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    score_dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_impact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SCMRecommendationSimulation(Base, ScopedMixin):
    __tablename__ = "scm_recommendation_simulations"
    recommendation_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_recommendations.id", ondelete="CASCADE"), index=True)
    baseline_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("scm_planning_runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED", index=True)
    input_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    before_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolves_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    algorithm_version: Mapped[str] = mapped_column(String(80))


class SCMSavedView(Base, ScopedMixin):
    __tablename__ = "scm_saved_views"
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    view_type: Mapped[str] = mapped_column(String(48), index=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("user_id", "view_type", "name", name="uq_scm_saved_view"),)


class SCMPlannerNote(Base, ScopedMixin):
    __tablename__ = "scm_planner_notes"
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    body: Mapped[str] = mapped_column(Text)
    author_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(24), default="WORKSPACE")
    __table_args__ = (Index("ix_scm_note_entity", "tenant_id", "entity_type", "entity_id"),)
