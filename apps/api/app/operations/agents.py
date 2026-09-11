"""Deterministic, evidence-recorded operations objective-agent coordination.

The model layer may explain these records, but operational facts and prepared
work are produced from canonical data and never parsed back from free text.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import time

from sqlalchemy.orm import Session

from app.db import models
from app.core import metrics


ALLOWED_AGENTS = {"production_recovery", "material_readiness", "quality_recovery",
                  "reliability", "supplier_commitment", "continuous_improvement"}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def run(db: Session, agent_type: str, trigger: dict) -> models.AgentRun:
    if agent_type not in ALLOWED_AGENTS:
        raise ValueError("Unknown or unbounded V2 agent type")
    tenant_id, plant_id = trigger["tenant_id"], trigger["plant_id"]
    correlation = trigger.get("correlation_id") or f"agent:{agent_type}:{trigger.get('deviation_id') or trigger.get('event_id') or _digest(trigger)[:16]}"
    existing = db.query(models.AgentRun).filter_by(
        tenant_id=tenant_id, plant_id=plant_id, correlation_id=correlation).first()
    if existing:
        return existing

    started = time.perf_counter()
    deviation = None
    if trigger.get("deviation_id"):
        deviation = db.query(models.OperationalDeviation).filter_by(
            id=trigger["deviation_id"], tenant_id=tenant_id, plant_id=plant_id).first()
    deviations = db.query(models.OperationalDeviation).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).filter(
        models.OperationalDeviation.status.in_(("detected", "contextualized", "assigned", "investigating", "action_required", "action_in_progress"))).all()
    actions = db.query(models.OperationalAction).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).filter(
        models.OperationalAction.status.in_(("open", "accepted", "in_progress", "waiting"))).all()
    material_risks = db.query(models.MaterialReadinessSnapshot).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).filter(
        models.MaterialReadinessSnapshot.state.in_(("AT_RISK", "BLOCKED", "UNKNOWN"))).all()
    unhealthy_connections = db.query(models.IntegrationConnection).filter_by(
        tenant_id=tenant_id, plant_id=plant_id).filter(
        models.IntegrationConnection.status.notin_(("active", "available"))).all()
    evidence = ([{"type": "deviation", "id": deviation.id}] if deviation else []) + [
        {"type": "operational_action", "id": action.id} for action in actions
        if not deviation or action.deviation_id == deviation.id]
    recovery_case = (db.query(models.RecoveryCase).filter_by(deviation_id=deviation.id).first()
                     if deviation else None)
    strategies = (db.query(models.RecoveryStrategy).filter_by(recovery_case_id=recovery_case.id)
                  .order_by(models.RecoveryStrategy.ranking_position).all() if recovery_case else [])
    selected = next((row for row in strategies if row.id == recovery_case.selected_strategy_id), None) if recovery_case else None
    recommended = next((row for row in strategies if row.id == recovery_case.recommended_strategy_id), None) if recovery_case else None
    context = {
        "user": {"id": trigger.get("user_id") or "system", "role": trigger.get("role") or "system", "permissions": []},
        "plant": {"id": plant_id}, "time": {"now": datetime.now(timezone.utc).isoformat(), "shift": trigger.get("shift_id")},
        "focus_entities": [{"type": "deviation", "id": deviation.id}] if deviation else [],
        "active_deviations": [{"id": row.id, "category": row.category, "severity": row.severity, "status": row.status} for row in deviations],
        "open_actions": [{"id": row.id, "status": row.status, "owner_role": row.owner_role,
                          "due_at": row.due_at.isoformat() if row.due_at else None} for row in actions],
        "material_risks": [{"id": row.id, "material": row.material_code, "state": row.state} for row in material_risks],
        "production_state": {"lost_units": deviation.estimated_lost_units if deviation else 0},
        "data_health": [{"connection_id": row.id, "state": row.status} for row in unhealthy_connections],
        "knowledge_refs": trigger.get("knowledge_refs", []),
        "recovery": ({"case_id": recovery_case.id, "status": recovery_case.status,
                      "recommended_strategy_id": recovery_case.recommended_strategy_id,
                      "selected_strategy_id": recovery_case.selected_strategy_id,
                      "strategies": [{"id":row.id,"type":row.strategy_type,"score":row.recovery_score,
                                      "expected_units":row.expected_recovered_units} for row in strategies]}
                     if recovery_case else None),
    }
    action_labels = {
        "production_recovery": "Review and execute the accountable recovery action",
        "material_readiness": "Confirm inbound quantity or prepare supplier follow-up",
        "quality_recovery": "Contain affected output and begin evidence-based investigation",
        "reliability": "Inspect the asset and prepare governed maintenance recovery",
        "supplier_commitment": "Request a dated supplier commitment",
        "continuous_improvement": "Open an evidence-backed improvement experiment",
    }
    summary = deviation.title if deviation else f"{agent_type.replace('_', ' ').title()} context evaluated"
    preferred = selected or recommended
    result = {"summary": summary, "situation": summary,
              "severity": "urgent" if deviation and deviation.severity in {"high", "critical"} else "watch",
              "facts": ([{"label": "Lost units", "value": deviation.estimated_lost_units}] if deviation else []),
              "hypotheses": [], "recommended_actions": [{"label": action_labels[agent_type], "mode": "prepare"}],
              "business_impact": ({"lost_units":deviation.estimated_lost_units,
                                   "financial_exposure":deviation.estimated_financial_impact} if deviation else {}),
              "current_handling": [{"id":row.id,"title":row.title,"status":row.status} for row in actions
                                   if not deviation or row.deviation_id == deviation.id],
              "recommended_strategy": ({"id":preferred.id,"title":preferred.title,
                  "expected_recovery_units":preferred.expected_recovered_units,
                  "reason":[preferred.reasoning_summary]} if preferred else None),
              "alternatives": [{"id":row.id,"title":row.title,"expected_recovery_units":row.expected_recovered_units}
                               for row in strategies if not preferred or row.id != preferred.id],
              "decision_required": ({"type":"select_recovery_strategy","recovery_case_id":recovery_case.id}
                                    if recovery_case and recovery_case.status == "options_ready" else None),
              "evidence_refs": evidence + ([{"type":"recovery_case","id":recovery_case.id}] if recovery_case else []),
              "confidence": deviation.confidence if deviation else "medium"}
    run = models.AgentRun(
        tenant_id=tenant_id, plant_id=plant_id, thread_id=f"v2:{plant_id}:{agent_type}",
        membership_id=trigger.get("membership_id") or trigger.get("user_id") or "system",
        agent_profile_id=f"v2:{agent_type}", state="completed", provider="deterministic",
        model="v2-objective-agent-1", context_hash=_digest(context), policy_version="v2-bounded-1",
        trace_id=trigger.get("trace_id") or correlation, correlation_id=correlation,
        completed_at=datetime.now(timezone.utc), intent=agent_type,
        requested_outcome=action_labels[agent_type], active_context=context,
        latency_ms=max(1, int((time.perf_counter() - started) * 1000)), step_count=5,
        read_tool_count=5, mutation_count=0, termination_reason="recommendation_prepared")
    db.add(run)
    db.flush()
    observations = [("get_active_deviations", {"count": len(deviations)}),
                    ("get_open_actions", {"count": len(actions)}),
                    ("get_connector_health", {"degraded": len(unhealthy_connections)}),
                    ("get_recovery_case", {"id": recovery_case.id, "status": recovery_case.status} if recovery_case else {}),
                    ("get_recovery_strategies", {"count":len(strategies),"recommended":recovery_case.recommended_strategy_id if recovery_case else None})]
    for sequence, (tool, output) in enumerate(observations, 1):
        db.add(models.AgentToolCall(
            tenant_id=tenant_id, plant_id=plant_id, run_id=run.id,
            agent_profile_id=run.agent_profile_id, tool_name=tool,
            arguments={"plant_id": plant_id}, result_hash=_digest(output),
            target_entity_type="plant", target_entity_id=plant_id,
            authorization_decision="read_allowed", latency_ms=0,
            correlation_id=correlation))
        db.add(models.AgentEvent(tenant_id=tenant_id, plant_id=plant_id, run_id=run.id,
                                 sequence=sequence, event_type="observation", payload={"tool": tool, "result_summary": output}, visibility="plant"))
    db.add(models.AgentEvent(tenant_id=tenant_id, plant_id=plant_id, run_id=run.id,
                             sequence=len(observations) + 1, event_type="recommendation", payload=result, visibility="plant"))
    db.add(models.EventOutbox(
        tenant_id=tenant_id, plant_id=plant_id, event_type="gigi.recommendation.created",
        aggregate_type="agent_run", aggregate_id=run.id, aggregate_version=1,
        correlation_id=f"{correlation}:recommendation", causation_id=trigger.get("event_id"),
        payload={"run_id": run.id, "agent_type": agent_type, **result}))
    if preferred:
        metrics.GIGI_RECOVERY_RECOMMENDATIONS.inc()
    return run
