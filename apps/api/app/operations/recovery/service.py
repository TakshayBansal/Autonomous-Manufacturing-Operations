"""Recovery case lifecycle, strategy execution, verification and learning."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core import metrics
from app.db import models
from app.operations.state import build_operational_state_snapshot, get_latest_operational_state, serialize_snapshot
from app.operations.recovery.effectiveness import fingerprint, find_similar_recovery_cases, get_effectiveness
from app.operations.recovery.playbooks import candidates_for
from app.operations.recovery.ranking import score
from app.operations.recovery.verification import evaluate

ACTIVE = {"assessing", "options_ready", "strategy_selected", "executing", "monitoring", "recovered", "partially_recovered"}
TERMINAL = {"verified", "failed", "abandoned"}


class RecoveryInputsStale(ValueError):
    """Selection was refused and the invalidated option should be persisted."""


def now(): return datetime.now(timezone.utc)
def _json(value): return json.loads(json.dumps(value, default=str))


def _event(db: Session, case: models.RecoveryCase, event_type: str, payload: dict | None = None):
    canonical = {
        "recovery.case.opened": "operations.recovery.case_opened",
        "recovery.strategy.selected": "operations.recovery.strategy_selected",
        "recovery.verified": "operations.recovery.verified",
    }.get(event_type)
    event_payload = {"recovery_case_id": case.id, **(payload or {})}
    if canonical:
        from app.platform.events import DomainEvent, publish
        publish(db, DomainEvent(
            canonical, case.tenant_id, case.plant_id, "recovery_case", case.id,
            event_payload, correlation_id=f"recovery:{case.id}"[:80],
            causation_id=f"deviation:{case.deviation_id}", source_system="operations",
        ))
    else:
        db.add(models.EventOutbox(tenant_id=case.tenant_id, plant_id=case.plant_id,
            event_type=event_type, aggregate_type="recovery_case", aggregate_id=case.id,
            aggregate_version=case.version, correlation_id=f"recovery:{case.id}"[:80],
            causation_id=f"deviation:{case.deviation_id}", payload=event_payload))
    from app.platform.cases import link_case
    deviation = db.get(models.OperationalDeviation, case.deviation_id)
    link_case(db, tenant_id=case.tenant_id, plant_id=case.plant_id, domain="operations",
              domain_case_type="operations_recovery", domain_case_id=case.id,
              title=deviation.title if deviation else f"Recovery {case.id}",
              status="closed" if case.status in TERMINAL else "open",
              severity=deviation.severity if deviation else "medium",
              context={"deviation_id": case.deviation_id, "recovery_status": case.status})


def eligible(deviation: models.OperationalDeviation) -> bool:
    return deviation.category in {"production", "downtime", "maintenance", "material", "quality", "supplier"} and (
        deviation.severity in {"watch", "high", "critical"} or
        float(deviation.estimated_financial_impact or 0) >= 5000 or
        float(deviation.estimated_lost_units or 0) > 0)


def open_for_deviation(db: Session, deviation: models.OperationalDeviation, generate: bool = True):
    existing = db.query(models.RecoveryCase).filter_by(deviation_id=deviation.id).first()
    if existing or not eligible(deviation): return existing
    scope_type, scope_id = ("line", deviation.line_id) if deviation.line_id else (
        "work_order", deviation.work_order_id) if deviation.work_order_id else ("asset", deviation.asset_id)
    snapshot = build_operational_state_snapshot(db, scope_type, scope_id, deviation.detected_at)
    case = models.RecoveryCase(tenant_id=deviation.tenant_id, plant_id=deviation.plant_id,
        deviation_id=deviation.id, scope_type=scope_type, scope_id=scope_id, status="assessing",
        target_state=deviation.expected_state or {}, baseline_snapshot_id=snapshot.id,
        baseline_state=_json(serialize_snapshot(snapshot) or {}), business_exposure_amount=deviation.estimated_financial_impact,
        business_exposure_currency=deviation.currency, root_cause_status="unknown")
    db.add(case); db.flush(); _event(db, case, "recovery.case.opened", {"deviation_id":deviation.id})
    metrics.RECOVERY_CASES.labels(deviation.category).inc()
    if generate: refresh_options(db, case)
    return case


def _context(db: Session, case: models.RecoveryCase, deviation: models.OperationalDeviation) -> dict:
    maintenance = (db.query(models.MaintenanceWorkRecord).filter_by(asset_id=deviation.asset_id)
                   .order_by(models.MaintenanceWorkRecord.created_at.desc()).first()) if deviation.asset_id else None
    snapshot = get_latest_operational_state(db, case.tenant_id, case.scope_type, case.scope_id) or db.get(models.OperationalStateSnapshot, case.baseline_snapshot_id)
    return {"snapshot": snapshot, "spare_available": maintenance.spare_available if maintenance and maintenance.spare_available is not None else True,
            "fingerprint": fingerprint(db, deviation, snapshot)}


def refresh_options(db: Session, case: models.RecoveryCase) -> list[models.RecoveryStrategy]:
    if case.status in {"executing", "monitoring", "recovered", "verified", "abandoned"}:
        raise ValueError("Recovery options cannot be replaced in the current state")
    deviation = db.get(models.OperationalDeviation, case.deviation_id)
    context = _context(db, case, deviation)
    for row in db.query(models.RecoveryStrategy).filter_by(recovery_case_id=case.id).filter(
            models.RecoveryStrategy.status.in_(("candidate", "evaluated", "recommended"))).all():
        row.status = "rejected"; row.unavailable_reason = "Options refreshed against newer canonical state"
    candidates = candidates_for(deviation.category, context)
    rows = []
    exposure = float(case.business_exposure_amount or 0)
    for candidate in candidates:
        history = get_effectiveness(db, case.tenant_id, case.plant_id, candidate.strategy_type, context["fingerprint"])
        if history["sample_size"]:
            metrics.RECOVERY_HISTORY_USED.inc()
        ranking, components = score(candidate, exposure, history)
        stale = bool(context["snapshot"] and context["snapshot"].source_freshness.get("state") != "fresh")
        unavailable = "Critical operational inputs are stale" if stale and any(
            req.get("freshness_required") for req in candidate.requirements) else None
        row = models.RecoveryStrategy(tenant_id=case.tenant_id, plant_id=case.plant_id,
            recovery_case_id=case.id, strategy_type=candidate.strategy_type, title=candidate.title,
            description=candidate.description, source="playbook", status="evaluated" if unavailable else "candidate",
            expected_recovered_units=max(float(deviation.estimated_lost_units or 0) * candidate.recovery_ratio, 0),
            expected_recovered_time_seconds=candidate.implementation_seconds,
            expected_value_recovered=components["expected_value_recovered"], direct_cost=candidate.direct_cost,
            implementation_time_seconds=candidate.implementation_seconds, quality_risk_score=candidate.quality_risk,
            safety_risk_score=candidate.safety_risk, operational_risk_score=candidate.operational_risk,
            uncertainty_score=min(candidate.uncertainty + (.2 if stale else 0), 1),
            historical_effectiveness_score=history["success_rate"], historical_sample_size=history["sample_size"],
            estimated_success_probability=candidate.success_probability, recovery_score=ranking,
            score_components=components, requirements=list(candidate.requirements), constraints=[],
            required_authorities=list(candidate.authorities), input_freshness=context["snapshot"].source_freshness if context["snapshot"] else {"state":"unknown"},
            evidence=[*candidate.evidence, {"type":"baseline_snapshot","id":case.baseline_snapshot_id},
                      {"type":"historical_effectiveness","sample_size":history["sample_size"]}],
            reasoning_summary=(f"Expected recovery {components['expected_value_recovered']:.0f} {case.business_exposure_currency or 'INR'}; "
                               f"success estimate {candidate.success_probability:.0%}; quality risk {candidate.quality_risk:.0%}."),
            unavailable_reason=unavailable)
        # Definitions are retained with the strategy as deterministic execution evidence.
        row.constraints = [{"type":"action_definition", **item} for item in candidate.actions]
        db.add(row); db.flush(); rows.append(row)
    available = sorted([row for row in rows if not row.unavailable_reason], key=lambda row: row.recovery_score or -1, reverse=True)
    for position, row in enumerate(available, 1): row.ranking_position = position
    if available:
        available[0].status = "recommended"; case.recommended_strategy_id = available[0].id
        case.estimated_recovered_units = available[0].expected_recovered_units
        case.estimated_value_recovered = available[0].expected_value_recovered
        _event(db, case, "recovery.strategy.recommended", {"strategy_id":available[0].id})
    case.status = "options_ready"
    _event(db, case, "recovery.options.generated", {"count":len(rows)})
    metrics.RECOVERY_STRATEGIES.labels(deviation.category).inc(len(rows))
    return rows


def select_strategy(db: Session, case: models.RecoveryCase, strategy: models.RecoveryStrategy,
                    actor_id: str, reason: str | None, actor_authorities: set[str]) -> list[models.OperationalAction]:
    if case.status != "options_ready" or strategy.recovery_case_id != case.id or strategy.unavailable_reason:
        raise ValueError("Strategy is not selectable")
    latest = get_latest_operational_state(db, case.tenant_id, case.scope_type, case.scope_id)
    if latest and latest.source_freshness.get("state") != "fresh" and any(
            requirement.get("freshness_required") for requirement in strategy.requirements or []):
        strategy.status = "evaluated"
        strategy.unavailable_reason = "Critical operational inputs became stale; refresh recovery options"
        case.status = "assessing"
        _event(db, case, "recovery.failed", {"strategy_id":strategy.id,"reason":"inputs_stale"})
        raise RecoveryInputsStale(strategy.unavailable_reason)
    missing = set(strategy.required_authorities or []) - actor_authorities
    if missing: raise PermissionError(f"Missing recovery authority: {', '.join(sorted(missing))}")
    if case.recommended_strategy_id and case.recommended_strategy_id != strategy.id and not reason:
        raise ValueError("An override reason is required when selecting an alternative")
    case.selected_strategy_id = strategy.id; case.selected_at = now(); case.status = "strategy_selected"
    case.decision_actor_type = "user"; case.decision_actor_id = actor_id; case.decision_reason = reason
    strategy.status = "selected"
    case.estimated_recovered_units = strategy.expected_recovered_units
    case.estimated_value_recovered = strategy.expected_value_recovered
    from app.platform import actions as platform_actions
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=case.tenant_id, user_id=actor_id, status="active").first()
    intent = platform_actions.propose(
        db, tenant_id=case.tenant_id, plant_id=case.plant_id,
        membership_id=membership.id if membership else None,
        action_type="recovery.strategy.select", target_type="recovery_case", target_id=case.id,
        payload={"strategy_id": strategy.id, "strategy_type": strategy.strategy_type},
        rationale=reason or strategy.reasoning_summary or "Selected recovery strategy",
        idempotency_key=f"recovery:{case.id}:strategy:{strategy.id}",
    )
    platform_actions.decide(db, intent, membership.id if membership else None, True,
                            reason or "Authorized through recovery strategy selection")
    # The detector's immediate triage action is superseded by the selected,
    # sequenced strategy; retain it for audit but keep it out of My Work.
    for legacy in db.query(models.OperationalAction).filter_by(deviation_id=case.deviation_id).filter(
            models.OperationalAction.source != "recovery_engine",
            models.OperationalAction.status.notin_(("completed", "cancelled"))).all():
        legacy.status = "cancelled"
        if legacy.task_id:
            legacy_task = db.get(models.Task, legacy.task_id)
            if legacy_task: legacy_task.status = "cancelled"
    if case.recommended_strategy_id and case.recommended_strategy_id != strategy.id:
        case.override_reason = reason; metrics.RECOVERY_OVERRIDES.inc()
    actions = []
    definitions = [item for item in (strategy.constraints or []) if item.get("type") == "action_definition"]
    previous = None
    deviation = db.get(models.OperationalDeviation, case.deviation_id)
    for sequence, definition in enumerate(definitions, 1):
        task = models.Task(tenant_id=case.tenant_id, plant_id=case.plant_id, title=definition["title"],
            owner_role=definition["owner_role"], status="open", severity=deviation.severity,
            priority="urgent" if deviation.severity == "critical" else "high",
            entity_type="recovery_case", entity_id=case.id, task_type="recovery_strategy_action",
            requested_outcome=f"Execute step {sequence} of {strategy.title}", semantic_key=f"recovery:{case.id}:{strategy.id}:{sequence}",
            business_impact=deviation.severity, production_impact="direct")
        db.add(task); db.flush()
        action = models.OperationalAction(tenant_id=case.tenant_id, plant_id=case.plant_id,
            deviation_id=case.deviation_id, task_id=task.id, action_type=strategy.strategy_type,
            title=definition["title"], owner_role=definition["owner_role"], status="open",
            priority=task.priority, source="recovery_engine",
            expected_outcome={"recovery_case_id":case.id,"strategy_id":strategy.id,
                              "expected_recovered_units":strategy.expected_recovered_units})
        db.add(action); db.flush(); actions.append(action)
        db.add(models.RecoveryStrategyAction(tenant_id=case.tenant_id, plant_id=case.plant_id,
            strategy_id=strategy.id, operational_action_id=action.id, sequence_no=sequence, required=True))
        if previous:
            db.add(models.OperationalActionDependency(tenant_id=case.tenant_id, plant_id=case.plant_id,
                action_id=action.id, predecessor_action_id=previous.id, dependency_type="finish_to_start",
                title=f"Complete {previous.title}", owner_role=action.owner_role, status="open"))
        previous = action
    _event(db, case, "recovery.strategy.selected", {"strategy_id":strategy.id,"override":bool(case.override_reason)})
    platform_actions.record_internal_execution(
        db, intent, executor="operations.recovery.select_strategy@1",
        result={"recovery_case_id": case.id, "strategy_id": strategy.id,
                "operational_action_ids": [row.id for row in actions]},
    )
    metrics.RECOVERY_SELECTED.labels(strategy.strategy_type).inc()
    return actions


def _suggest_recurring_investigation(db: Session, case: models.RecoveryCase,
                                     deviation: models.OperationalDeviation, outcome: models.RecoveryOutcome) -> None:
    """Turn repeated recovery demand into a durable improvement opportunity."""
    prior = (db.query(models.RecoveryOutcome, models.RecoveryCase, models.OperationalDeviation)
             .join(models.RecoveryCase, models.RecoveryOutcome.recovery_case_id == models.RecoveryCase.id)
             .join(models.OperationalDeviation, models.RecoveryCase.deviation_id == models.OperationalDeviation.id)
             .filter(models.RecoveryOutcome.tenant_id == case.tenant_id,
                     models.RecoveryOutcome.plant_id == case.plant_id,
                     models.OperationalDeviation.category == deviation.category).all())
    related = [recovery_case.id for _, recovery_case, prior_deviation in prior
               if (not deviation.asset_id or prior_deviation.asset_id == deviation.asset_id)]
    related.append(case.id)
    related = list(dict.fromkeys(related))
    if len(related) < 3:
        return
    signature = {"category": deviation.category, "asset_id": deviation.asset_id,
                 "line_id": deviation.line_id, "strategy_type": db.get(models.RecoveryStrategy, outcome.strategy_id).strategy_type}
    existing = db.query(models.ImprovementInvestigation).filter_by(
        tenant_id=case.tenant_id, plant_id=case.plant_id).all()
    if any(row.problem_signature == signature and row.status not in {"closed", "rejected"} for row in existing):
        return
    annual_loss = sum(float(recovery_case.business_exposure_amount or 0) for _, recovery_case, _ in prior)
    investigation = models.ImprovementInvestigation(tenant_id=case.tenant_id, plant_id=case.plant_id,
        title=f"Eliminate recurring {deviation.category} recovery demand",
        problem_signature=signature, related_recovery_case_ids=related,
        estimated_annual_loss=round(annual_loss * 12, 2), currency=case.business_exposure_currency or "INR",
        status="suggested", hypothesis="A recurring operating condition is repeatedly consuming recovery capacity.")
    db.add(investigation); db.flush()
    _event(db, case, "improvement.investigation.suggested", {"investigation_id":investigation.id,"occurrences":len(related)})


def start(db: Session, case: models.RecoveryCase):
    if case.status != "strategy_selected": raise ValueError("Select a strategy before starting recovery")
    case.status = "executing"; case.execution_started_at = now()
    opened = case.opened_at.replace(tzinfo=timezone.utc) if case.opened_at.tzinfo is None else case.opened_at
    metrics.RECOVERY_FIRST_ACTION.observe(max((case.execution_started_at-opened).total_seconds(), 0))
    _event(db, case, "recovery.execution.started", {"strategy_id":case.selected_strategy_id})
    return case


def begin_monitoring(db: Session, case: models.RecoveryCase):
    if case.status not in {"executing", "monitoring"}: raise ValueError("Recovery is not executing")
    case.status = "monitoring"; case.monitoring_started_at = case.monitoring_started_at or now()
    _event(db, case, "recovery.monitoring.started")
    return case


def verify(db: Session, case: models.RecoveryCase, user_id: str | None = None):
    if case.status not in {"executing", "monitoring", "recovered", "partially_recovered"}:
        raise ValueError("Recovery must execute before verification")
    deviation = db.get(models.OperationalDeviation, case.deviation_id)
    before = db.get(models.OperationalStateSnapshot, case.baseline_snapshot_id)
    current = build_operational_state_snapshot(db, case.scope_type, case.scope_id)
    result = evaluate(case, deviation, before, current)
    if result.result in {"NO_EFFECT", "WORSENED", "INCONCLUSIVE"}:
        strategy = db.get(models.RecoveryStrategy, case.selected_strategy_id)
        if result.result in {"NO_EFFECT", "WORSENED"}:
            case.status = "failed"; case.recovery_success = False; strategy.status = "failed"
            unsuccessful = models.RecoveryOutcome(tenant_id=case.tenant_id, plant_id=case.plant_id,
                recovery_case_id=case.id, strategy_id=strategy.id, baseline_snapshot_id=before.id,
                post_snapshot_id=current.id, started_at=case.execution_started_at, completed_at=now(),
                expected_recovered_units=strategy.expected_recovered_units, actual_recovered_units=result.recovered_units,
                expected_value_recovered=strategy.expected_value_recovered, estimated_value_recovered=0,
                verified_value_recovered=0, target_achieved=False, partial_recovery=False,
                quality_side_effect=bool(result.evidence.get("quality_side_effect")), safety_side_effect=False,
                delivery_side_effect=False, outcome_rating="unsuccessful", verification_method=result.method,
                verified_by_user_id=user_id, verified_at=now(),
                context_fingerprint=fingerprint(db, deviation, current, strategy.strategy_type),
                metrics_before=_json(serialize_snapshot(before)), metrics_after=_json(serialize_snapshot(current)))
            db.add(unsuccessful)
            metrics.RECOVERY_FAILED.labels(deviation.category).inc()
        else: case.status = "monitoring"
        _event(db, case, "recovery.failed" if case.status == "failed" else "recovery.outcome.detected", {"result":result.result})
        return case, unsuccessful if case.status == "failed" else None, result
    case.status = "verified"; case.recovered_at = now(); case.verified_at = case.recovered_at
    case.actual_recovered_units = result.recovered_units; case.recovery_success = result.result == "RECOVERED"
    case.actual_outcome = {"result":result.result, **result.evidence}
    strategy = db.get(models.RecoveryStrategy, case.selected_strategy_id); strategy.status = "executed"
    attributable = min(result.recovered_units, float(strategy.expected_recovered_units or result.recovered_units))
    line = db.get(models.ProductionLine, deviation.line_id) if deviation.line_id else None
    value = max(attributable * float(line.contribution_per_good_unit if line else 0), 0)
    net = max(value - float(strategy.direct_cost or 0), 0)
    case.verified_value_recovered = net; case.recovery_score = min(100, round(
        (50 if result.target_achieved else 30) + (25 if result.recovered_units > 0 else 0) +
        (15 if not result.evidence.get("quality_side_effect") else 0), 2))
    case.recovery_score_components = {"target":result.target_achieved,"recovered_units":result.recovered_units,"side_effect_penalty":0}
    outcome = models.RecoveryOutcome(tenant_id=case.tenant_id, plant_id=case.plant_id,
        recovery_case_id=case.id, strategy_id=strategy.id, baseline_snapshot_id=before.id,
        post_snapshot_id=current.id, started_at=case.execution_started_at, completed_at=case.recovered_at,
        expected_recovered_units=strategy.expected_recovered_units, actual_recovered_units=result.recovered_units,
        expected_value_recovered=strategy.expected_value_recovered, estimated_value_recovered=value,
        verified_value_recovered=net, time_to_first_response_seconds=int(((case.execution_started_at or now())-case.opened_at).total_seconds()),
        time_to_recovery_seconds=int((case.recovered_at-(case.execution_started_at or case.opened_at)).total_seconds()),
        target_achieved=result.target_achieved, partial_recovery=result.partial, quality_side_effect=False,
        safety_side_effect=False, delivery_side_effect=False, outcome_rating="successful" if case.recovery_success else "partially_successful",
        verification_method=result.method, verified_by_user_id=user_id, verified_at=case.verified_at,
        context_fingerprint=fingerprint(db, deviation, current, strategy.strategy_type),
        metrics_before=_json(serialize_snapshot(before)), metrics_after=_json(serialize_snapshot(current)))
    db.add(outcome)
    from app.platform.models import ActionIntent as PlatformActionIntent, ActionOutcome as PlatformActionOutcome
    intent = db.query(PlatformActionIntent).filter_by(
        tenant_id=case.tenant_id, idempotency_key=f"recovery:{case.id}:strategy:{strategy.id}").first()
    if intent:
        platform_outcome = db.query(PlatformActionOutcome).filter_by(action_intent_id=intent.id).first()
        if platform_outcome:
            platform_outcome.verification_status = "verified_effective" if case.recovery_success else "verified_partial"
            platform_outcome.outcome_type = "recovery_verified"
            platform_outcome.metrics = {"actual_recovered_units": result.recovered_units,
                                        "verified_value_recovered": net, "target_achieved": result.target_achieved}
            platform_outcome.evidence = [*(platform_outcome.evidence or []),
                                         {"type": "recovery_outcome", "id": outcome.id},
                                         {"type": "post_state_snapshot", "id": current.id}]
            platform_outcome.verified_at = now()
    for value_type, amount, confidence in (("recovery_expected", strategy.expected_value_recovered or 0, "estimated"),
        ("recovery_attributable", value, "estimated"), ("recovery_direct_cost", strategy.direct_cost or 0, "verified"),
        ("recovery_verified", value, "verified"), ("recovery_net_value", net, "verified")):
        db.add(models.OperationalValueEntry(tenant_id=case.tenant_id, plant_id=case.plant_id,
            deviation_id=deviation.id, value_type=value_type, confidence_state=confidence, amount=amount,
            currency=case.business_exposure_currency or "INR", calculation_method="v2_1_conservative_recovery_attribution",
            calculation_inputs={"recovery_case_id":case.id,"strategy_id":strategy.id,"attributable_units":attributable},
            verified_by_user_id=user_id if confidence == "verified" else None, verified_at=now() if confidence == "verified" else None))
    deviation.status = "verified"; deviation.verified_at = now(); deviation.verified_outcome = case.actual_outcome
    _suggest_recurring_investigation(db, case, deviation, outcome)
    _event(db, case, "recovery.verified", {"outcome_id":outcome.id,"verified_value":net})
    _event(db, case, "recovery.learning.updated", {"strategy_type":strategy.strategy_type})
    metrics.RECOVERY_SUCCESS.labels(strategy.strategy_type).inc(); metrics.RECOVERY_VALUE.inc(net)
    started = case.execution_started_at.replace(tzinfo=timezone.utc) if case.execution_started_at and case.execution_started_at.tzinfo is None else case.execution_started_at
    metrics.RECOVERY_VERIFICATION_LATENCY.observe(max((case.verified_at-(started or case.verified_at)).total_seconds(),0))
    return case, outcome, result


def abandon(db: Session, case: models.RecoveryCase, reason: str):
    if case.status in TERMINAL: raise ValueError("Recovery case is already terminal")
    case.status = "abandoned"; case.decision_reason = reason
    _event(db, case, "recovery.failed", {"reason":reason,"abandoned":True})
    return case


def serialize_strategy(row: models.RecoveryStrategy) -> dict:
    return {key:getattr(row,key) for key in ("id","recovery_case_id","strategy_type","title","description","source","status",
        "expected_recovered_units","expected_recovered_time_seconds","expected_value_recovered","direct_cost","implementation_time_seconds",
        "quality_risk_score","safety_risk_score","operational_risk_score","uncertainty_score","historical_effectiveness_score",
        "historical_sample_size","estimated_success_probability","recovery_score","score_components","ranking_position","requirements",
        "constraints","required_authorities","input_freshness","evidence","reasoning_summary","unavailable_reason","version")}


def serialize_case(db: Session, row: models.RecoveryCase, include_details: bool = True) -> dict:
    strategies = db.query(models.RecoveryStrategy).filter_by(recovery_case_id=row.id).order_by(
        models.RecoveryStrategy.ranking_position.asc().nullslast()).all() if include_details else []
    actions = (db.query(models.OperationalAction).filter_by(deviation_id=row.deviation_id).all() if include_details else [])
    return {key:getattr(row,key) for key in ("id","deviation_id","scope_type","scope_id","status","opened_at","target_state","baseline_state",
        "baseline_snapshot_id","business_exposure_amount","business_exposure_currency","selected_strategy_id","recommended_strategy_id",
        "decision_actor_type","decision_actor_id","decision_reason","override_reason","selected_at","execution_started_at","monitoring_started_at",
        "recovered_at","verified_at","actual_outcome","estimated_recovered_units","actual_recovered_units","estimated_value_recovered",
        "verified_value_recovered","recovery_score","recovery_score_components","recovery_success","root_cause_status","version")} | {
        "strategies":[serialize_strategy(item) for item in strategies],
        "actions":[{"id":item.id,"title":item.title,"owner_role":item.owner_role,"status":item.status,
                    "expected_outcome":item.expected_outcome,"due_at":item.due_at} for item in actions]}


def opportunities(db: Session, tenant_id: str, plant_id: str) -> list[dict]:
    rows = db.query(models.RecoveryCase).filter_by(tenant_id=tenant_id, plant_id=plant_id).filter(
        models.RecoveryCase.status.in_(ACTIVE)).order_by(models.RecoveryCase.business_exposure_amount.desc()).all()
    result=[]
    for case in rows:
        deviation=db.get(models.OperationalDeviation,case.deviation_id); selected=db.get(models.RecoveryStrategy,case.selected_strategy_id) if case.selected_strategy_id else None
        recommended=db.get(models.RecoveryStrategy,case.recommended_strategy_id) if case.recommended_strategy_id else None
        strategy=selected or recommended
        result.append({"id":case.id,"deviation_id":case.deviation_id,"title":deviation.title,"severity":deviation.severity,
            "status":case.status,"business_exposure_amount":case.business_exposure_amount,"currency":case.business_exposure_currency,
            "strategy":serialize_strategy(strategy) if strategy else None,"decision_required":case.status=="options_ready",
            "recoverability":strategy.estimated_success_probability if strategy else 0})
    severity_weight={"critical":3,"high":2,"watch":1}
    return sorted(result,key=lambda row:(float(row["business_exposure_amount"] or 0),
        int(row["decision_required"]),float(row["recoverability"] or 0),severity_weight.get(row["severity"],0)),reverse=True)
