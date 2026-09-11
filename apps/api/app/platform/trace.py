"""Developer-facing, read-only correlation trace assembled from existing records."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.models import (ActionApproval, ActionExecution, ActionIntent, ActionOutcome,
    ActionPolicyEvaluation, DataProvenance, OperationalCase, PlatformStateSnapshot)
from app.scm import models as scm


def correlation_trace(db: Session, tenant_id: str, correlation_id: str) -> dict:
    steps: list[dict] = []
    def add(kind: str, at, entity_type: str, entity_id: str, status: str, data: dict):
        value = at or datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        steps.append({"kind": kind, "at": value, "entity_type": entity_type,
                      "entity_id": entity_id, "status": status, "data": data})
    provenance = db.query(DataProvenance).filter_by(tenant_id=tenant_id, correlation_id=correlation_id).all()
    for row in provenance:
        add("provenance", row.recorded_at, row.entity_type, row.entity_id, row.quality_status,
            {"source_system": row.source_system, "source_reference": row.source_reference,
             "mapping_version": row.mapping_version, "observed_at": row.observed_at,
             "transformation": row.transformation, "details": row.details})
    events = db.query(core.EventOutbox).filter_by(tenant_id=tenant_id, correlation_id=correlation_id).all()
    event_ids = [row.event_id for row in events]
    for row in events:
        add("canonical_event", row.recorded_at or row.created_at, row.subject_type or row.aggregate_type,
            row.subject_id or row.aggregate_id, row.status,
            {"event_id": row.event_id, "event_type": row.event_type, "schema_version": row.event_version,
             "source": row.source_system, "causation_id": row.causation_id, "payload": row.payload})
    if event_ids:
        for row in db.query(core.EventConsumerReceipt).filter(core.EventConsumerReceipt.event_id.in_(event_ids)).all():
            add("consumer", row.completed_at or row.updated_at, "event", row.event_id, row.status,
                {"consumer": row.consumer_name, "attempt_count": row.attempt_count, "error": row.error})
    for row in db.query(PlatformStateSnapshot).filter_by(tenant_id=tenant_id, correlation_id=correlation_id).all():
        add("factory_state", row.captured_at, row.entity_type, row.entity_id, row.snapshot_type,
            {"observed": row.observed, "derived": row.derived, "predicted": row.predicted,
             "freshness": row.freshness, "projection_version": row.projection_version})
    cases = db.query(OperationalCase).filter_by(tenant_id=tenant_id, correlation_id=correlation_id).all()
    run_ids = {(row.context or {}).get("planning_run_id") for row in cases} - {None}
    for row in cases:
        add("operational_case", row.created_at, "operational_case", row.id, row.status,
            {"case_type": row.case_type, "severity": row.severity, "context": row.context,
             "resolution_evidence": row.resolution_evidence})
    if run_ids:
        for run in db.query(scm.SCMPlanningRun).filter(scm.SCMPlanningRun.id.in_(run_ids)).all():
            add("planning_run", run.started_at or run.created_at, "scm_planning_run", run.id, run.status,
                {"engine_version": run.engine_version, "exceptions_generated": run.exceptions_generated})
        for rec in db.query(scm.SCMRecommendation).filter(scm.SCMRecommendation.planning_run_id.in_(run_ids)).all():
            add("recommendation", rec.created_at, "scm_recommendation", rec.id, rec.status,
                {"action_type": rec.action_type, "reason": rec.reason, "evidence": rec.evidence,
                 "source_entity_id": rec.source_entity_id})
    intents = db.query(ActionIntent).filter_by(tenant_id=tenant_id, correlation_id=correlation_id).all()
    for intent in intents:
        add("action_intent", intent.created_at, "action_intent", intent.id, intent.status,
            {"action_type": intent.action_type, "target_type": intent.target_type,
             "target_id": intent.target_id, "parameters": intent.payload, "reason": intent.rationale,
             "evidence": intent.evidence, "expected_impact": intent.expected_impact})
        policy = db.query(ActionPolicyEvaluation).filter_by(action_intent_id=intent.id).first()
        if policy:
            add("policy", policy.created_at, "action_intent", intent.id, "allowed" if policy.allowed else "rejected",
                {"requires_approval": policy.requires_approval, "reason_code": policy.reason_code,
                 "policy_version": policy.policy_version})
        approval = db.query(ActionApproval).filter_by(action_intent_id=intent.id).first()
        if approval:
            add("approval", approval.decided_at or approval.created_at, "action_intent", intent.id, approval.decision,
                {"approved_by": approval.approver_membership_id, "comment": approval.comment})
        execution = db.query(ActionExecution).filter_by(action_intent_id=intent.id).first()
        if execution:
            add("execution", execution.executed_at or execution.created_at, "action_intent", intent.id, execution.status,
                {"executor": execution.executor, "mode": execution.mode,
                 "external_reference": execution.external_reference, "result": execution.result, "error": execution.error})
        outcome = db.query(ActionOutcome).filter_by(action_intent_id=intent.id).first()
        if outcome:
            add("verification", outcome.verified_at or outcome.created_at, "action_intent", intent.id,
                outcome.verification_status, {"evidence": outcome.evidence, "metrics": outcome.metrics})
    for audit in db.query(core.AuditEvent).filter_by(tenant_id=tenant_id, correlation_id=correlation_id).all():
        add("audit", audit.created_at, audit.entity_type, audit.entity_id, audit.result,
            {"action": audit.action, "actor": audit.actor, "metadata": audit.meta})
    steps.sort(key=lambda item: (item["at"], item["kind"], item["entity_id"]))
    return {"tenant_id": tenant_id, "correlation_id": correlation_id,
            "step_count": len(steps), "steps": steps}

