"""Canonical event catalog and lightweight payload contract validation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventContract:
    event_type: str
    version: int
    owner: str
    required_payload: frozenset[str] = frozenset()


CONTRACTS = {
    item.event_type: item for item in (
        EventContract("platform.demo.workspace_seeded", 1, "platform", frozenset({"module"})),
        EventContract("master.material.mapped", 1, "platform", frozenset({"canonical_material_id", "source_system"})),
        EventContract("inventory.position.updated", 1, "platform", frozenset({"material_id", "as_of_at"})),
        EventContract("procurement.po.created", 1, "procurement", frozenset({"po_id"})),
        EventContract("procurement.po.delivery_rescheduled", 1, "procurement", frozenset({"po_revision_id", "date_changes"})),
        EventContract("requirement.created", 1, "procurement", frozenset({"requirement_id"})),
        EventContract("rfq.created", 1, "procurement", frozenset({"rfq_id"})),
        EventContract("supplier.quote_received", 1, "procurement", frozenset({"quote_id", "supplier_id"})),
        EventContract("purchase_order.created", 1, "procurement", frozenset({"purchase_order_id"})),
        EventContract("purchase_order.updated", 1, "procurement", frozenset({"purchase_order_id"})),
        EventContract("purchase_order.rescheduled", 1, "procurement", frozenset({"purchase_order_id", "material_id", "confirmed_delivery_date"})),
        EventContract("goods_receipt.recorded", 1, "procurement", frozenset({"material_id", "quantity"})),
        EventContract("forecast.updated", 1, "scm", frozenset({"material_id"})),
        EventContract("inventory.updated", 1, "scm", frozenset({"material_id"})),
        EventContract("supplier.commitment.updated", 1, "scm", frozenset({"supplier_id", "material_id"})),
        EventContract("scm.planning.completed", 1, "scm", frozenset({"planning_run_id"})),
        EventContract("scm.shortage.detected", 1, "scm", frozenset({"material_id", "planning_run_id"})),
        EventContract("material.shortage.predicted", 1, "scm", frozenset({"material_id", "planning_run_id"})),
        EventContract("material.excess.predicted", 1, "scm", frozenset({"material_id", "planning_run_id"})),
        EventContract("scm.intervention.recommended", 1, "scm", frozenset({"recommendation_id", "material_id"})),
        EventContract("scm.manual_data.recorded", 1, "scm", frozenset({"entry_id", "entry_type", "material_id"})),
        EventContract("scm.manual_data.voided", 1, "scm", frozenset({"entry_id", "material_id"})),
        EventContract("work_order.released", 1, "operations", frozenset({"work_order_id"})),
        EventContract("work_order.started", 1, "operations", frozenset({"work_order_id"})),
        EventContract("work_order.completed", 1, "operations", frozenset({"work_order_id"})),
        EventContract("production.recorded", 1, "operations", frozenset({"work_order_id", "quantity"})),
        EventContract("production.deviation.detected", 1, "operations", frozenset({"deviation_id"})),
        EventContract("downtime.started", 1, "operations", frozenset({"equipment_id"})),
        EventContract("downtime.ended", 1, "operations", frozenset({"equipment_id"})),
        EventContract("recovery.case.created", 1, "operations", frozenset({"recovery_case_id"})),
        EventContract("recovery.action.executed", 1, "operations", frozenset({"recovery_case_id", "action_intent_id"})),
        EventContract("recovery.verified", 1, "operations", frozenset({"recovery_case_id"})),
        EventContract("operations.material.readiness.changed", 1, "operations", frozenset({"work_order_id"})),
        EventContract("operations.recovery.case_opened", 1, "operations", frozenset({"recovery_case_id", "deviation_id"})),
        EventContract("operations.recovery.strategy_selected", 1, "operations", frozenset({"recovery_case_id", "strategy_id"})),
        EventContract("operations.recovery.verified", 1, "operations", frozenset({"recovery_case_id", "outcome_id"})),
        EventContract("platform.action.proposed", 1, "platform", frozenset({"action_type", "target_type", "target_id"})),
        EventContract("platform.action.approved", 1, "platform", frozenset({"action_type"})),
        EventContract("platform.action.rejected", 1, "platform", frozenset({"action_type"})),
        EventContract("platform.action.executed", 1, "platform", frozenset({"action_type", "mode"})),
        EventContract("platform.action.execution_failed", 1, "platform", frozenset({"action_type", "error"})),
        EventContract("platform.action.outcome_verified", 1, "platform", frozenset({"verification_status"})),
        EventContract("platform.work.created", 1, "platform", frozenset({"work_item_id", "source_domain"})),
        EventContract("purchase_order.eta_changed", 1, "procurement", frozenset({"purchase_order_id", "old_eta", "new_eta"})),
        EventContract("customer_order.changed", 1, "scm", frozenset({"customer_order_id"})),
        EventContract("material.risk_detected", 1, "scm", frozenset({"material_id"})),
        EventContract("material.risk_changed", 1, "scm", frozenset({"material_id"})),
        EventContract("material.risk_resolved", 1, "scm", frozenset({"material_id"})),
        EventContract("operational_case.created", 1, "platform", frozenset({"case_id"})),
        EventContract("operational_case.updated", 1, "platform", frozenset({"case_id"})),
        EventContract("decision.required", 1, "platform", frozenset({"case_id", "decision_id"})),
        EventContract("decision.recorded", 1, "platform", frozenset({"case_id", "decision_id"})),
        EventContract("action_plan.created", 1, "platform", frozenset({"case_id", "action_plan_id"})),
        EventContract("recovery.monitoring_started", 1, "platform", frozenset({"case_id"})),
        EventContract("recovery.verification_failed", 1, "platform", frozenset({"case_id"})),
        EventContract("value.attributed", 1, "platform", frozenset({"case_id", "metric"})),
        EventContract("commitment.due", 1, "platform", frozenset({"commitment_id"})),
        EventContract("commitment.overdue", 1, "platform", frozenset({"commitment_id"})),
    )
}


def validate(event_type: str, version: int, payload: dict) -> None:
    contract = CONTRACTS.get(event_type)
    if contract is None:
        raise ValueError(f"Unregistered canonical event type: {event_type}")
    if contract.version != version:
        raise ValueError(f"Unsupported {event_type} version {version}; expected {contract.version}")
    missing = contract.required_payload - payload.keys()
    if missing:
        raise ValueError(f"{event_type} payload is missing: {', '.join(sorted(missing))}")
