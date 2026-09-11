from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import workspace_membership
from app.core.security import current_user, require_csrf
from app.db import models as core_models
from app.db.session import get_db
from app.platform.models import OperationalCase
from app.platform.case_models import CaseCause, CaseEntityLink, CaseEvidence, DecisionRecord, RecoveryObservation, RecoveryTarget, RecoveryVerification, ValueAttribution
from app.platform.case_service import case_detail, decision_options, select_alternative, serialize_case, verify_recovery

router = APIRouter(prefix="/api/v1", tags=["operational-cases"])


def user(request: Request, db: Session = Depends(get_db)) -> core_models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def scoped_case(db: Session, actor: core_models.User, case_id: str) -> OperationalCase:
    row = db.query(OperationalCase).filter_by(id=case_id, tenant_id=actor.tenant_id, plant_id=actor.plant_id).first()
    if row is None:
        raise HTTPException(404, "Case not found")
    return row


@router.get("/cases")
def cases(owner: str | None = None, team: str | None = None, severity: str | None = None,
          recovery_state: str | None = None, decision_required: bool | None = None,
          db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    query = db.query(OperationalCase).filter_by(tenant_id=actor.tenant_id, plant_id=actor.plant_id)
    if owner: query = query.filter_by(owner_membership_id=owner)
    if team: query = query.filter_by(responsible_team=team)
    if severity: query = query.filter_by(severity=severity)
    if recovery_state: query = query.filter_by(recovery_state=recovery_state)
    if decision_required: query = query.filter(OperationalCase.status == "decision_required")
    return [serialize_case(db, x) for x in query.order_by(OperationalCase.priority_score.desc(), OperationalCase.decision_deadline.asc()).all()]


@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    return case_detail(db, scoped_case(db, actor, case_id))


@router.get("/decision-inbox")
def decision_inbox(db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    """Read-only projection; selection and approval stay with owning services."""
    from app.platform.models import ActionIntent
    membership = workspace_membership(db, actor)
    if not membership:
        raise HTTPException(403, "Active workspace membership required")
    rows = []
    decisions = db.query(DecisionRecord, OperationalCase).join(
        OperationalCase, OperationalCase.id == DecisionRecord.case_id).filter(
        DecisionRecord.tenant_id == actor.tenant_id, DecisionRecord.plant_id == actor.plant_id,
        OperationalCase.tenant_id == actor.tenant_id, OperationalCase.plant_id == actor.plant_id,
        DecisionRecord.decision == "PENDING",
        OperationalCase.status.notin_(("closed", "resolved", "cancelled"))).all()
    for record, case in decisions:
        rows.append({"id": f"decision:{record.id}", "source_type": "recovery_decision", "source_id": record.id,
            "title": case.title, "status": record.decision, "href": f"/cases/{case.id}",
            "deadline": record.decision_deadline, "priority": case.priority_score,
            "case_id": case.id, "owner": case.responsible_team,
            "alternative_count": len(decision_options(db, record))})
    for approval in db.query(core_models.ComparisonApprovalRequest).filter_by(
            tenant_id=actor.tenant_id, plant_id=actor.plant_id,
            assignee_membership_id=membership.id, status="pending").all():
        rows.append({"id": f"procurement:{approval.id}", "source_type": "procurement_approval",
            "source_id": approval.id, "title": f"Supplier comparison · version {approval.comparison_version}",
            "status": approval.status, "href": "/procurement/approvals", "deadline": None,
            "priority": 50, "owner": approval.required_role, "case_id": None, "alternative_count": None})
    for task in db.query(core_models.Task).filter(
            core_models.Task.tenant_id == actor.tenant_id, core_models.Task.plant_id == actor.plant_id,
            core_models.Task.status == "pending_approval",
            (core_models.Task.owner_user_id == actor.id) | (core_models.Task.owner_role == actor.role)).all():
        rows.append({"id": f"work:{task.id}", "source_type": "work_approval", "source_id": task.id,
            "title": task.title, "status": task.status, "href": "/operations/my-work",
            "deadline": task.due_at, "priority": 50, "owner": task.owner_role,
            "case_id": task.linked_case_id, "alternative_count": None})
    # Do not expose another role's action queue merely because it has a session.
    from app.platform.context import for_user
    scope = for_user(db, actor)
    if "platform.admin" in scope.authorities or actor.role in {"admin", "plant_manager"}:
        for intent in db.query(ActionIntent).filter_by(tenant_id=actor.tenant_id,
                plant_id=actor.plant_id, status="awaiting_approval").all():
            rows.append({"id": f"action:{intent.id}", "source_type": "action_authorization", "source_id": intent.id,
                "title": intent.action_type.replace("_", " "), "status": intent.status,
                "href": f"/cases/{intent.originating_case_id}" if intent.originating_case_id else "/platform",
                "deadline": None, "priority": 80 if intent.risk_level == "critical" else 50,
                "owner": "Authorized approver", "case_id": intent.originating_case_id, "alternative_count": None})
    return sorted(rows, key=lambda row: (-float(row["priority"] or 0), str(row["deadline"] or "9999"), row["id"]))


@router.get("/cases/{case_id}/evidence")
def evidence(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    case = scoped_case(db, actor, case_id)
    return [{"id": x.id, "type": x.evidence_type, "source_entity_type": x.source_entity_type,
             "source_entity_id": x.source_entity_id, "source_event_id": x.source_event_id,
             "observed_at": x.observed_at, "freshness": x.freshness_state,
             "confidence": x.confidence, "payload": x.payload}
            for x in db.query(CaseEvidence).filter_by(case_id=case.id).order_by(CaseEvidence.observed_at).all()]


@router.get("/cases/{case_id}/timeline")
def timeline(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    case = scoped_case(db, actor, case_id)
    events = [{"type": "DETECTED", "at": case.detected_at, "title": case.title}]
    events += [{"type": row.evidence_type, "at": row.observed_at,
                "title": row.payload.get("type", row.evidence_type), "source_event_id": row.source_event_id}
               for row in db.query(CaseEvidence).filter_by(case_id=case.id).all()]
    if case.last_evaluated_at:
        events.append({"type": "EVALUATED", "at": case.last_evaluated_at, "title": "Case recalculated"})
    return sorted(events, key=lambda row: row["at"] or case.created_at)


@router.get("/cases/{case_id}/impact")
def impact(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    case = scoped_case(db, actor, case_id)
    links = db.query(CaseEntityLink).filter_by(case_id=case.id).order_by(CaseEntityLink.importance.desc()).all()
    causes = db.query(CaseCause).filter_by(case_id=case.id).all()
    evidence_rows = db.query(CaseEvidence).filter_by(case_id=case.id).all()
    freshness_states = {str(row.freshness_state or "UNKNOWN").upper() for row in evidence_rows}
    freshness = "STALE" if "STALE" in freshness_states else "FRESH" if evidence_rows and freshness_states == {"FRESH"} else "UNKNOWN"
    relationships = {row.relationship for row in links}
    required = {"MATERIAL", "PRODUCTION_ORDER", "CUSTOMER_COMMITMENT"} if case.case_type in {"SCM_MATERIAL_RISK", "material_shortage"} else set()
    missing = [{"relationship": relation, "reason": "No canonical link is recorded"} for relation in sorted(required - relationships)]
    return {"case_id": case.id, "expected_impact_at": case.expected_impact_at, "confidence": case.confidence,
            "root_causes": [{"type": row.cause_type, "entity_type": row.entity_type,
                "entity_id": row.entity_id, "description": row.description, "confidence": row.confidence} for row in causes],
            "affected": [{"entity_type": row.entity_type, "entity_id": row.entity_id,
                "relationship": row.relationship, "importance": row.importance} for row in links],
            "missing_mappings": missing, "freshness": freshness,
            "evidence_count": len(evidence_rows)}


@router.get("/cases/{case_id}/strategies")
def strategies(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    case = scoped_case(db, actor, case_id)
    record = db.query(DecisionRecord).filter_by(case_id=case.id).order_by(DecisionRecord.created_at.desc()).first()
    return {"decision_id": record.id, "status": record.decision, "recommended_alternative_id": record.recommended_alternative_id,
            "alternatives": decision_options(db, record)} if record else {"decision_id": None, "alternatives": []}


class Selection(BaseModel):
    alternative_id: str
    reason: str = Field(min_length=3, max_length=4000)
    override_reason: str | None = Field(default=None, max_length=4000)


class ScenarioRequest(BaseModel):
    strategy_type: str
    overrides: dict[str, Any] = Field(default_factory=dict)


@router.post("/cases/{case_id}/scenarios", dependencies=[Depends(csrf_guard)])
def scenario(case_id: str, payload: ScenarioRequest, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    from datetime import datetime, timezone
    from app.scm.material_recovery import evaluate_strategy
    case = scoped_case(db, actor, case_id)
    allowed = {"shortage_qty", "stale_inventory", "origin_available", "origin_future_demand", "transfer_qty", "lead_time_days"}
    values = {key: value for key, value in payload.overrides.items() if key in allowed}
    record = db.query(DecisionRecord).filter_by(case_id=case.id).order_by(DecisionRecord.created_at.desc()).first()
    if not record or not record.planning_run_id:
        raise HTTPException(409, "A planning baseline is required before comparing scenarios")
    if "shortage_qty" not in values:
        raise HTTPException(422, "An explicit shortage quantity is required; scenario assumptions are not factory facts")
    try:
        result = evaluate_strategy(strategy=payload.strategy_type, **values)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"case_id": case.id, "side_effect_free": True, "baseline": record.planning_run_id,
            "strategy_type": payload.strategy_type, "overrides": values,
            "result": result,
            "generated_at": datetime.now(timezone.utc)}


@router.post("/cases/{case_id}/decisions", dependencies=[Depends(csrf_guard)])
def decide_case(case_id: str, payload: Selection, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    case = scoped_case(db, actor, case_id)
    record = db.query(DecisionRecord).filter_by(case_id=case.id, decision="PENDING").order_by(DecisionRecord.created_at.desc()).first()
    if record is None: raise HTTPException(409, "No pending decision")
    membership = workspace_membership(db, actor)
    try:
        selected = select_alternative(db, record=record, alternative_id=payload.alternative_id,
                                      actor_id=membership.id if membership else None, reason=payload.reason,
                                      override_reason=payload.override_reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return {"decision_id": record.id, "status": record.decision, "selected_alternative_id": selected.id}


@router.get("/decisions/{decision_id}")
def decision(decision_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    row = db.query(DecisionRecord).filter_by(id=decision_id, tenant_id=actor.tenant_id, plant_id=actor.plant_id).first()
    if row is None: raise HTTPException(404, "Decision not found")
    return {"id": row.id, "case_id": row.case_id, "decision": row.decision,
            "recommended_alternative_id": row.recommended_alternative_id,
            "selected_alternative_id": row.selected_alternative_id, "decided_at": row.decided_at,
            "alternatives": decision_options(db, row)}


@router.get("/recoveries/{case_id}")
def recovery(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    case = scoped_case(db, actor, case_id)
    row = db.query(RecoveryVerification).filter_by(case_id=case.id).first()
    targets = db.query(RecoveryTarget).filter_by(case_id=case.id).all()
    return {"case_id": case.id, "status": row.status if row else "PENDING",
            "targets": [{"id": t.id, "metric": t.metric, "operator": t.operator, "threshold": t.threshold,
                         "required_observation_count": t.required_observation_count,
                         "required_duration_seconds": t.required_duration_seconds,
                         "observations": [{"id": observation.id, "value": observation.observed_value,
                             "observed_at": observation.observed_at, "freshness": observation.freshness,
                             "satisfied": observation.satisfied, "source": observation.source_entity,
                             "evidence": observation.evidence} for observation in db.query(RecoveryObservation).filter_by(
                                 target_id=t.id).order_by(RecoveryObservation.observed_at.desc()).limit(10).all()]}
                        for t in targets],
            "verification": {"evidence_completeness": row.evidence_completeness,
                "confidence": row.confidence, "failure_reason": row.failure_reason,
                "stability_window_start": row.stability_window_start,
                "stability_window_end": row.stability_window_end} if row else None}


@router.post("/recoveries/{case_id}/verify", dependencies=[Depends(csrf_guard)])
def verify(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    row = verify_recovery(db, scoped_case(db, actor, case_id)); db.commit()
    return {"case_id": case_id, "status": row.status, "evidence_completeness": row.evidence_completeness,
            "confidence": row.confidence, "completed_at": row.completed_at}


@router.get("/cases/{case_id}/value")
def value(case_id: str, db: Session = Depends(get_db), actor: core_models.User = Depends(user)):
    case = scoped_case(db, actor, case_id)
    return [{"metric": x.metric, "baseline": x.baseline, "counterfactual": x.counterfactual,
             "actual": x.actual, "attributed_value": x.attributed_value, "unit": x.unit,
             "currency": x.currency, "methodology": x.methodology,
             "confidence_level": x.confidence_level, "assumptions": x.assumptions}
            for x in db.query(ValueAttribution).filter_by(case_id=case.id).all()]


@router.get("/scm/suppliers/{supplier_id}/reliability")
def supplier_reliability(supplier_id: str, days: int = 90, db: Session = Depends(get_db),
                         actor: core_models.User = Depends(user)):
    from datetime import datetime, timedelta, timezone
    supplier = db.query(core_models.Supplier).filter_by(id=supplier_id, tenant_id=actor.tenant_id).first()
    if not supplier: raise HTTPException(404, "Supplier not found")
    start = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 730)))
    rows = db.query(core_models.SupplierPerformanceEvent).filter(
        core_models.SupplierPerformanceEvent.tenant_id == actor.tenant_id,
        core_models.SupplierPerformanceEvent.plant_id == actor.plant_id,
        core_models.SupplierPerformanceEvent.supplier_id == supplier.id,
        core_models.SupplierPerformanceEvent.occurred_at >= start).all()
    grouped: dict[str, list[float]] = {}
    for row in rows: grouped.setdefault(row.metric_type, []).append(row.score)
    metrics = {key: {"value": round(sum(values)/len(values), 2), "sample_count": len(values)}
               for key, values in grouped.items()}
    return {"supplier_id": supplier.id, "supplier_name": supplier.name,
        "period": {"start": start, "end": datetime.now(timezone.utc), "days": days},
        "sample_count": len(rows), "metrics": metrics,
        "limitations": [] if rows else ["No evidence-backed supplier events exist in the selected period."],
        "methodology": "Arithmetic mean of immutable supplier performance events grouped by metric."}
