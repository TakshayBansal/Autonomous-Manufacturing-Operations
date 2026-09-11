"""Deterministic shared-case lifecycle services."""
from __future__ import annotations

from datetime import datetime, timezone
from operator import ge, gt, le, lt, eq
from typing import Any

from sqlalchemy.orm import Session

from app.platform.models import OperationalCase
from app.platform.case_models import (
    ActionPlan, ActionPlanStep, BusinessExposure, CaseCause, CaseEntityLink, CaseEvidence, ConstraintResult,
    DecisionAlternative, DecisionRecord, FeasibilityEvaluation, RecoveryObservation,
    RecoveryTarget, RecoveryVerification, ValueAttribution,
)


ACTIVE = ("open", "active", "decision_required", "monitoring")
OPS = {">=": ge, ">": gt, "<=": le, "<": lt, "==": eq}


def aggregate_case(db: Session, *, tenant_id: str, plant_id: str, aggregation_key: str,
                   title: str, case_type: str, source_event_id: str, evidence: dict[str, Any],
                   severity: str = "high", decision_deadline: datetime | None = None) -> OperationalCase:
    """Replay-safe aggregation: one active case, every distinct event retained."""
    case = db.query(OperationalCase).filter(
        OperationalCase.tenant_id == tenant_id, OperationalCase.plant_id == plant_id,
        OperationalCase.aggregation_key == aggregation_key, OperationalCase.status.in_(ACTIVE),
    ).first()
    now = datetime.now(timezone.utc)
    if case is None:
        case = OperationalCase(tenant_id=tenant_id, plant_id=plant_id, aggregation_key=aggregation_key,
                               title=title, summary=title, case_type=case_type, severity=severity,
                               status="open", detected_at=now, decision_deadline=decision_deadline,
                               recovery_state="PENDING", source_event_id=source_event_id)
        db.add(case)
        db.flush()
    existing = db.query(CaseEvidence).filter_by(case_id=case.id, source_event_id=source_event_id).first()
    if existing is None:
        db.add(CaseEvidence(tenant_id=tenant_id, plant_id=plant_id, case_id=case.id,
                            evidence_type=evidence.get("type", "DOMAIN_EVENT"),
                            source_entity_type=evidence.get("entity_type", case_type),
                            source_entity_id=evidence.get("entity_id", aggregation_key),
                            source_event_id=source_event_id, observed_at=evidence.get("observed_at", now),
                            recorded_at=now, freshness_state=evidence.get("freshness", "FRESH"),
                            confidence=float(evidence.get("confidence", 1)), payload=evidence))
    case.last_evaluated_at = now
    return case


def serialize_case(db: Session, case: OperationalCase) -> dict[str, Any]:
    decision = db.query(DecisionRecord).filter_by(case_id=case.id).order_by(DecisionRecord.created_at.desc()).first()
    title, summary = _human_case_copy(db, case)
    return {
        "id": case.id, "case_type": case.case_type, "title": title, "summary": summary,
        "severity": case.severity, "status": case.status, "priority_score": case.priority_score,
        "confidence": case.confidence, "decision_deadline": case.decision_deadline,
        "expected_impact_at": case.expected_impact_at, "recovery_state": case.recovery_state,
        "responsible_team": case.responsible_team,
        "decision": {"id": decision.id, "status": decision.decision,
                     "recommended_alternative_id": decision.recommended_alternative_id,
                     "selected_alternative_id": decision.selected_alternative_id,
                     "alternatives": decision_options(db, decision)} if decision else None,
        "entities": [{"type": x.entity_type, "id": x.entity_id,
                      "label": _entity_label(db, x.entity_type, x.entity_id),
                      "relationship": x.relationship, "importance": x.importance}
                     for x in db.query(CaseEntityLink).filter_by(case_id=case.id).all()],
    }


def _entity_label(db: Session, entity_type: str, entity_id: str) -> str:
    """Resolve canonical storage ids into operator-facing identity."""
    from app.db.models import PODraft, ProductionLine, ProductionWorkOrder, Supplier
    from app.platform.models import PlatformMaterial, PlatformProduct, PlatformPurchaseOrder

    kind = entity_type.casefold().replace("-", "_").replace(" ", "_")
    if kind == "material":
        row = db.get(PlatformMaterial, entity_id)
        return f"{row.code} — {row.name}" if row else "Material reference unavailable"
    if kind == "product":
        row = db.get(PlatformProduct, entity_id)
        return f"{row.code} — {row.name}" if row else "Product reference unavailable"
    if kind in {"purchase_order", "po"}:
        row = db.get(PlatformPurchaseOrder, entity_id)
        if row:
            return row.order_number
        draft = db.get(PODraft, entity_id)
        return (draft.business_number or "Purchase order") if draft else "Purchase order reference unavailable"
    if kind == "work_order":
        row = db.get(ProductionWorkOrder, entity_id)
        if row:
            return row.business_number or row.external_reference or f"Work order · {row.product_code}"
        return "Work order reference unavailable"
    if kind in {"work_center", "line", "production_line"}:
        row = db.get(ProductionLine, entity_id)
        return f"{row.code} — {row.name}" if row else "Work center reference unavailable"
    if kind == "supplier":
        row = db.get(Supplier, entity_id)
        return row.name if row else "Supplier reference unavailable"
    return entity_type.replace("_", " ").title()


def _human_case_copy(db: Session, case: OperationalCase) -> tuple[str, str | None]:
    """Never expose canonical storage identifiers as operator-facing names."""
    if case.canonical_entity_type != "material" or not case.canonical_entity_id:
        return case.title, case.summary
    from app.platform.models import PlatformMaterial
    material = db.get(PlatformMaterial, case.canonical_entity_id)
    if material is None:
        return case.title, case.summary
    title = case.title
    summary = case.summary
    if case.canonical_entity_id in title:
        title = f"Material shortage: {material.code}"
    if summary and case.canonical_entity_id in summary:
        summary = f"Supply coverage for {material.code} · {material.name} requires a coordinated response."
    return title, summary


def decision_options(db: Session, record: DecisionRecord) -> list[dict[str, Any]]:
    rows = db.query(DecisionAlternative).filter_by(decision_record_id=record.id).order_by(DecisionAlternative.ranking).all()
    return [{"id": x.id, "strategy_type": x.strategy_type, "parameters": x.parameters,
             "expected_impact": x.expected_impact, "cost": x.cost, "time_to_effect_hours": x.time_to_effect_hours,
             "success_probability": x.success_probability, "side_effects": x.side_effects, "score": x.score,
             "score_dimensions": x.score_dimensions, "ranking": x.ranking, "evidence": x.evidence,
             "feasibility": evaluation.status if (evaluation := db.get(FeasibilityEvaluation, x.feasibility_evaluation_id)) else "REQUIRES_CONFIRMATION"} for x in rows]


def select_alternative(db: Session, *, record: DecisionRecord, alternative_id: str, actor_id: str | None,
                       reason: str, override_reason: str | None = None) -> DecisionAlternative:
    if record.decision != "PENDING":
        raise ValueError("Decision is finalized and immutable")
    alternative = db.get(DecisionAlternative, alternative_id)
    if alternative is None or alternative.decision_record_id != record.id:
        raise ValueError("Alternative does not belong to this decision")
    evaluation = db.get(FeasibilityEvaluation, alternative.feasibility_evaluation_id)
    if evaluation is None:
        raise ValueError("Feasibility evaluation is missing; regenerate options")
    blockers = db.query(ConstraintResult).filter_by(feasibility_evaluation_id=evaluation.id, state="VIOLATED", blocking=True).count()
    if blockers or evaluation.status == "UNAVAILABLE":
        raise ValueError("Alternative has a blocking constraint violation")
    if evaluation.freshness_state != "FRESH":
        raise ValueError("Feasibility inputs are not fresh; regenerate options before selection")
    unknowns = db.query(ConstraintResult).filter_by(feasibility_evaluation_id=evaluation.id, state="UNKNOWN", blocking=True).count()
    if unknowns and not override_reason:
        raise ValueError("Critical unknown constraints require confirmation")
    if alternative.id != record.recommended_alternative_id and not override_reason:
        raise ValueError("Selecting a non-recommended alternative requires an override reason")
    now = datetime.now(timezone.utc)
    record.selected_alternative_id, record.decision = alternative.id, "SELECTED"
    record.decision_reason, record.override_reason = reason, override_reason
    record.actor_membership_id, record.decided_at = actor_id, now
    for item in db.query(DecisionAlternative).filter_by(decision_record_id=record.id):
        item.immutable = True
    case = db.get(OperationalCase, record.case_id)
    case.current_strategy_id, case.status, case.recovery_state = alternative.id, "active", "PENDING"
    plan = db.query(ActionPlan).filter_by(decision_record_id=record.id).first()
    if plan is None:
        plan = ActionPlan(tenant_id=record.tenant_id, plant_id=record.plant_id, case_id=case.id,
            decision_record_id=record.id, status="PENDING", strategy_type=alternative.strategy_type,
            objective=f"Protect the commitments affected by {case.title}", expected_outcome=alternative.expected_impact)
        db.add(plan); db.flush()
        steps = _strategy_steps(alternative.strategy_type)
        for sequence, (title, team, action_type) in enumerate(steps, 1):
            from app.platform import actions
            intent = actions.propose(db, tenant_id=record.tenant_id, plant_id=record.plant_id,
                membership_id=actor_id, action_type=action_type, target_type="operational_case", target_id=case.id,
                payload={**alternative.parameters, "decision_record_id": record.id, "strategy": alternative.strategy_type},
                rationale=reason, idempotency_key=f"case:{case.id}:decision:{record.id}:step:{sequence}",
                correlation_id=case.correlation_id, originating_case_id=case.id,
                reason_code="selected_recovery_strategy", evidence=alternative.evidence,
                expected_impact=alternative.expected_impact, confidence=alternative.success_probability,
                risk_level=case.severity)
            db.add(ActionPlanStep(tenant_id=record.tenant_id, plant_id=record.plant_id,
                action_plan_id=plan.id, sequence=sequence, title=title, owner_team=team,
                action_intent_id=intent.id, evidence_requirement="Execution receipt and fresh replanning evidence"))
    return alternative


def _strategy_steps(strategy: str) -> list[tuple[str, str, str]]:
    return {
        "SUPPLIER_PULL_IN": [("Confirm revised supplier commitment", "PROCUREMENT", "scm.supply.expedite")],
        "INTERPLANT_TRANSFER": [("Approve protected stock transfer", "SCM", "TRANSFER_INVENTORY")],
        "PRODUCTION_RESEQUENCE": [("Publish revised production sequence", "OPERATIONS", "CHANGE_PRODUCTION_PLAN")],
    }.get(strategy, [(f"Execute {strategy.replace('_', ' ').lower()}", "SCM", "START_RECOVERY_ACTION")])


def verify_recovery(db: Session, case: OperationalCase) -> RecoveryVerification:
    """Recovery depends on fresh operational observations, never action completion."""
    verification = db.query(RecoveryVerification).filter_by(case_id=case.id).first()
    if verification is None:
        verification = RecoveryVerification(tenant_id=case.tenant_id, plant_id=case.plant_id,
                                            case_id=case.id, status="PENDING")
        db.add(verification); db.flush()
    targets = db.query(RecoveryTarget).filter_by(case_id=case.id).all()
    now = datetime.now(timezone.utc)
    passed, complete, windows, failed = True, bool(targets), [], False
    for target in targets:
        observations = db.query(RecoveryObservation).filter_by(target_id=target.id).order_by(RecoveryObservation.observed_at.desc()).all()
        eligible, seen_cycles = [], set()
        for observation in observations:
            if observation.freshness != target.freshness_requirement:
                continue
            compare = OPS.get(target.operator)
            if not compare or not observation.satisfied or not compare(observation.observed_value, target.threshold):
                failed = True
                break
            cycle = observation.source_entity.get("planning_run") or observation.source_entity.get("planning_run_id")
            if not cycle or cycle in seen_cycles:
                continue
            seen_cycles.add(cycle)
            eligible.append(observation)
            if len(eligible) >= target.required_observation_count:
                break
        if eligible and target.required_duration_seconds:
            duration = (eligible[0].observed_at - eligible[-1].observed_at).total_seconds()
            if duration < target.required_duration_seconds:
                eligible = []
        if len(eligible) < target.required_observation_count:
            passed = False
        complete = complete and len(eligible) >= target.required_observation_count
        windows.extend(o.observed_at for o in eligible)
    verification.evidence_completeness = 1.0 if complete else 0.0
    verification.confidence = 1.0 if passed and complete else 0.5 if complete else 0.0
    if passed and complete:
        verification.status, verification.completed_at = "RECOVERED", now
        verification.stability_window_start, verification.stability_window_end = min(windows), max(windows)
        case.status, case.recovery_state = "closed", "RECOVERED"
        # Coverage proves a target, not a counterfactual business outcome.
        # Attribution must be recorded separately from reconciled actual units
        # and a validated baseline; never turn projected exposure into savings.
    else:
        verification.status = "NOT_RECOVERED" if failed else "MONITORING" if targets else "INDETERMINATE"
        verification.completed_at = None
        verification.stability_window_start = verification.stability_window_end = None
        verification.failure_reason = "Fresh observation violates the recovery target" if failed else None
        verification.started_at = verification.started_at or now
        case.recovery_state = verification.status
        if case.status == "closed":
            case.status = "monitoring"
    return verification


def case_detail(db: Session, case: OperationalCase) -> dict[str, Any]:
    result = serialize_case(db, case)
    result.update({
        "causes": [{"type": x.cause_type, "description": x.description, "confidence": x.confidence}
                   for x in db.query(CaseCause).filter_by(case_id=case.id).all()],
        "exposures": [{"metric": x.metric, "baseline": x.baseline, "projected": x.projected,
                       "delta": x.delta, "unit": x.unit, "methodology": x.methodology,
                       "confidence": x.confidence} for x in db.query(BusinessExposure).filter_by(case_id=case.id).all()],
    })
    decision = db.query(DecisionRecord).filter_by(case_id=case.id).order_by(DecisionRecord.created_at.desc()).first()
    plan = db.query(ActionPlan).filter_by(case_id=case.id).order_by(ActionPlan.created_at.desc()).first()
    result["decision"] = ({"id": decision.id, "status": decision.decision,
        "recommended_alternative_id": decision.recommended_alternative_id,
        "selected_alternative_id": decision.selected_alternative_id,
        "alternatives": decision_options(db, decision)} if decision else None)
    result["action_plan"] = ({"id": plan.id, "status": plan.status, "strategy_type": plan.strategy_type,
        "objective": plan.objective, "steps": [{"id": step.id, "sequence": step.sequence,
            "title": step.title, "owner_team": step.owner_team, "status": step.status,
            "action_intent_id": step.action_intent_id} for step in db.query(ActionPlanStep).filter_by(
                action_plan_id=plan.id).order_by(ActionPlanStep.sequence).all()]} if plan else None)
    return result
