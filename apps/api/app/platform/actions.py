"""Governed ActionIntent lifecycle.  Demo execution is deliberately simulated."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.platform.events import DomainEvent, publish
from app.platform.models import ActionApproval, ActionExecution, ActionIntent, ActionOutcome, ActionPolicyEvaluation


def propose(db: Session, *, tenant_id: str, plant_id: str, membership_id: str | None, action_type: str,
            target_type: str, target_id: str, payload: dict, rationale: str, idempotency_key: str,
            correlation_id: str | None = None, originating_case_id: str | None = None,
            reason_code: str | None = None, evidence: list[dict] | None = None,
            expected_impact: dict | None = None, confidence: float | None = None,
            risk_level: str = "medium") -> ActionIntent:
    existing = db.query(ActionIntent).filter_by(tenant_id=tenant_id, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    intent = ActionIntent(tenant_id=tenant_id, plant_id=plant_id, action_type=action_type, target_type=target_type,
                          target_id=target_id, requested_by_membership_id=membership_id, payload=payload,
                          rationale=rationale, idempotency_key=idempotency_key, correlation_id=correlation_id or str(uuid4()),
                          originating_case_id=originating_case_id, reason_code=reason_code,
                          evidence=evidence or [], expected_impact=expected_impact or {},
                          confidence=confidence, risk_level=risk_level)
    db.add(intent); db.flush()
    allowed = action_type in {"procurement.po.reschedule", "scm.supply.expedite", "recovery.strategy.select", "work_item.create",
                              "RESCHEDULE_PURCHASE_ORDER", "EXPEDITE_PURCHASE_ORDER", "TRANSFER_INVENTORY",
                              "CHANGE_SUPPLIER_ALLOCATION", "CANCEL_PURCHASE_ORDER", "CHANGE_PRODUCTION_PLAN",
                              "CREATE_RFQ", "SELECT_SUPPLIER", "CREATE_PURCHASE_ORDER", "REQUEST_NEGOTIATION",
                              "REROUTE_WORK_ORDER", "SCHEDULE_MAINTENANCE", "CHANGE_MACHINE_ASSIGNMENT", "START_RECOVERY_ACTION"}
    db.add(ActionPolicyEvaluation(tenant_id=tenant_id, plant_id=plant_id, action_intent_id=intent.id, allowed=allowed,
                                  requires_approval=True, reason_code="demo_simulation_requires_approval" if allowed else "unsupported_action"))
    db.add(ActionApproval(tenant_id=tenant_id, plant_id=plant_id, action_intent_id=intent.id))
    intent.status = "awaiting_approval" if allowed else "blocked"
    publish(db, DomainEvent("platform.action.proposed", tenant_id, plant_id, "action_intent", intent.id,
                            {"action_type": action_type, "target_type": target_type, "target_id": target_id}, membership_id, intent.correlation_id))
    from app.domains.workflows import create_audit
    create_audit(db, tenant_id, plant_id, f"membership:{membership_id}" if membership_id else "platform",
                 "platform.action.proposed", "action_intent", intent.id,
                 result="success" if allowed else "blocked",
                 meta={"action_type": action_type, "target_type": target_type, "target_id": target_id},
                 correlation_id=intent.correlation_id)
    return intent


def decide(db: Session, intent: ActionIntent, membership_id: str | None, approved: bool, comment: str | None) -> ActionIntent:
    # SessionLocal uses autoflush=False; make the proposal's approval request
    # visible when propose + decide happen in one authorized domain transaction.
    db.flush()
    approval = db.query(ActionApproval).filter_by(action_intent_id=intent.id).first()
    if approval is None or approval.decision != "pending":
        raise ValueError("Action is not awaiting a decision")
    if membership_id:
        from app.db import models as core
        membership = db.query(core.WorkspaceMembership).filter_by(
            id=membership_id, tenant_id=intent.tenant_id, status="active").first()
        if not membership or membership.role not in {"admin", "purchase_manager", "plant_manager", "manager"}:
            raise ValueError("Manager authority is required for this action")
    approval.approver_membership_id = membership_id; approval.decision = "approved" if approved else "rejected"
    approval.comment = comment; approval.decided_at = datetime.now(timezone.utc)
    intent.status = "approved" if approved else "rejected"
    publish(db, DomainEvent("platform.action.approved" if approved else "platform.action.rejected", intent.tenant_id, intent.plant_id,
                            "action_intent", intent.id, {"action_type": intent.action_type}, membership_id, intent.correlation_id))
    from app.domains.workflows import create_audit
    create_audit(db, intent.tenant_id, intent.plant_id,
                 f"membership:{membership_id}" if membership_id else "platform",
                 "platform.action.approved" if approved else "platform.action.rejected",
                 "action_intent", intent.id, result="success" if approved else "rejected",
                 meta={"comment": comment}, correlation_id=intent.correlation_id)
    return intent


def execute_simulated(db: Session, intent: ActionIntent) -> ActionExecution:
    if intent.status != "approved":
        raise ValueError("Only approved actions can be executed")
    prior = db.query(ActionExecution).filter_by(action_intent_id=intent.id).first()
    if prior:
        return prior
    execution = ActionExecution(tenant_id=intent.tenant_id, plant_id=intent.plant_id, action_intent_id=intent.id,
                                mode="simulated", status="succeeded", executor="platform.simulated_executor@1",
                                result={"simulated": True, "message": "No external ERP or supplier record was changed."}, executed_at=datetime.now(timezone.utc))
    db.add(execution); intent.status = "executed_simulated"
    db.flush()
    db.add(ActionOutcome(
        tenant_id=intent.tenant_id, plant_id=intent.plant_id,
        action_intent_id=intent.id, execution_id=execution.id,
        verification_status="verified_simulation", outcome_type="simulation_completed",
        evidence=[{"type": "simulation_receipt", "executor": execution.executor}],
        metrics={"external_records_changed": 0}, verified_at=datetime.now(timezone.utc),
    ))
    publish(db, DomainEvent("platform.action.executed", intent.tenant_id, intent.plant_id, "action_intent", intent.id,
                            {"action_type": intent.action_type, "mode": "simulated", "execution_result": execution.result},
                            intent.requested_by_membership_id, intent.correlation_id))
    from app.domains.workflows import create_audit
    create_audit(db, intent.tenant_id, intent.plant_id, "platform.simulated_executor",
                 "platform.action.executed", "action_intent", intent.id,
                 meta={"mode": "simulated", "external_records_changed": 0},
                 correlation_id=intent.correlation_id)
    return execution


def execute_external(db: Session, intent: ActionIntent, *, executor: str, execute) -> ActionExecution:
    """Execute only an approved intent through a connector adapter."""
    if intent.status != "approved":
        raise ValueError("Only approved actions can be executed")
    prior = db.query(ActionExecution).filter_by(action_intent_id=intent.id).first()
    if prior:
        return prior
    execution = ActionExecution(tenant_id=intent.tenant_id, plant_id=intent.plant_id,
        action_intent_id=intent.id, mode="connector", status="running", executor=executor)
    db.add(execution); db.flush()
    try:
        result = execute(intent)
        execution.status = "succeeded"
        execution.result = result
        execution.external_reference = result.get("external_reference")
        execution.executed_at = datetime.now(timezone.utc)
        intent.status = "executed_pending_verification"
        db.add(ActionOutcome(tenant_id=intent.tenant_id, plant_id=intent.plant_id,
            action_intent_id=intent.id, execution_id=execution.id,
            verification_status="pending", outcome_type="external_execution",
            evidence=[{"type": "connector_receipt", "reference": execution.external_reference}], metrics={}))
        publish(db, DomainEvent("platform.action.executed", intent.tenant_id, intent.plant_id,
            "action_intent", intent.id, {"action_type": intent.action_type, "mode": "connector",
            "execution_result": result}, intent.requested_by_membership_id, intent.correlation_id))
        result_status = "success"
    except Exception as exc:
        execution.status = "failed"
        execution.error = str(exc)[:2000]
        execution.executed_at = datetime.now(timezone.utc)
        intent.status = "execution_failed"
        publish(db, DomainEvent("platform.action.execution_failed", intent.tenant_id, intent.plant_id,
            "action_intent", intent.id, {"action_type": intent.action_type, "error": execution.error},
            intent.requested_by_membership_id, intent.correlation_id))
        result_status = "failed"
    from app.domains.workflows import create_audit
    create_audit(db, intent.tenant_id, intent.plant_id, executor, "platform.action.external_execution",
        "action_intent", intent.id, result=result_status,
        meta={"external_reference": execution.external_reference, "error": execution.error},
        correlation_id=intent.correlation_id)
    return execution


def verify_outcome(db: Session, intent: ActionIntent, *, recovered: bool,
                   evidence: list[dict], metrics: dict | None = None,
                   case=None) -> ActionOutcome:
    outcome = db.query(ActionOutcome).filter_by(action_intent_id=intent.id).first()
    if outcome is None:
        raise ValueError("Action has no execution outcome to verify")
    outcome.verification_status = "verified_recovered" if recovered else "verification_failed"
    outcome.evidence = evidence
    outcome.metrics = metrics or {}
    outcome.verified_at = datetime.now(timezone.utc)
    intent.status = "verified" if recovered else "not_recovered"
    if case is not None:
        case.status = "resolved" if recovered else "open"
        case.resolution_evidence = evidence
    publish(db, DomainEvent("platform.action.outcome_verified", intent.tenant_id, intent.plant_id,
        "action_intent", intent.id, {"verification_status": outcome.verification_status},
        intent.requested_by_membership_id, intent.correlation_id))
    from app.domains.workflows import create_audit
    create_audit(db, intent.tenant_id, intent.plant_id, "platform.verifier",
        "platform.action.outcome_verified", "action_intent", intent.id,
        result="success" if recovered else "not_recovered", meta={"evidence": evidence},
        correlation_id=intent.correlation_id)
    return outcome


def record_internal_execution(db: Session, intent: ActionIntent, *, executor: str, result: dict,
                              verification_status: str = "accepted_pending_outcome") -> ActionExecution:
    """Record an already-authorized in-process domain service execution."""
    if intent.status != "approved":
        raise ValueError("Only approved actions can be executed")
    prior = db.query(ActionExecution).filter_by(action_intent_id=intent.id).first()
    if prior:
        return prior
    now = datetime.now(timezone.utc)
    execution = ActionExecution(tenant_id=intent.tenant_id, plant_id=intent.plant_id,
                                action_intent_id=intent.id, mode="internal", status="succeeded",
                                executor=executor, result=result, executed_at=now)
    db.add(execution); db.flush()
    db.add(ActionOutcome(tenant_id=intent.tenant_id, plant_id=intent.plant_id,
                         action_intent_id=intent.id, execution_id=execution.id,
                         verification_status=verification_status, outcome_type="domain_service_accepted",
                         evidence=[{"type": "domain_service_receipt", "executor": executor}],
                         metrics={}, verified_at=now if verification_status.startswith("verified") else None))
    intent.status = "executed"
    publish(db, DomainEvent("platform.action.executed", intent.tenant_id, intent.plant_id,
                            "action_intent", intent.id,
                            {"action_type": intent.action_type, "mode": "internal", "execution_result": result},
                            intent.requested_by_membership_id, intent.correlation_id))
    from app.domains.workflows import create_audit
    create_audit(db, intent.tenant_id, intent.plant_id, executor,
                 "platform.action.executed", "action_intent", intent.id,
                 meta={"mode": "internal", "result": result}, correlation_id=intent.correlation_id)
    return execution
