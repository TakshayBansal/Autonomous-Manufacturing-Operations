"""Deterministic, user-scoped orchestration for the proactive companion."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app import agent_service
from app.agent_schemas import SpecialistRequest
from app.db import models
from app.core.metrics import COMPANION_INTERVENTIONS, COMPANION_SUPPRESSIONS
from app.feature_flags import enabled as feature_enabled

OPEN_STATES = {"queued", "delivered", "opened", "snoozed", "acted"}
SEVERITY_PRIORITY = {"critical": 0, "action": 20, "warning": 35, "info": 60, "success": 80}
SEVERITY_LEVEL = {"info": 0, "success": 0, "action": 1, "warning": 2, "critical": 3}
STAGE_SPECIALISTS = {
    "requirement": "requirement_specification",
    "specification": "requirement_specification",
    "rfq": "supplier_rfq",
    "supplier_response": "quotation_normalization",
    "quotation_review": "quotation_normalization",
    "comparison": "comparison_award",
    "fulfilment": "fulfilment_monitor",
    "receipt": "receipt_quality",
    "quality": "receipt_quality",
    "invoice": "invoice_reconciliation",
}
STAGE_WORKFLOWS = {
    "requirement": ("/procurement", "Open requirement"),
    "specification": ("/procurement", "Complete requirement"),
    "rfq": ("/rfq-builder", "Create RFQ"),
    "supplier_response": ("/quotes", "Review responses"),
    "quotation_review": ("/quotes", "Review quotations"),
    "comparison": ("/comparison", "Compare quotations"),
    "approval": ("/approvals", "Review approval"),
    "negotiation": ("/negotiations", "Open negotiation"),
    "po": ("/po-drafts", "Review PO"),
    "fulfilment": ("/inbound", "Track fulfilment"),
    "receipt": ("/store", "Receive material"),
    "quality": ("/quality", "Inspect material"),
    "invoice": ("/invoices", "Review invoice"),
    "closure": ("/control-centre", "Close cycle"),
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def preference_for(db: Session, membership: models.WorkspaceMembership) -> models.CompanionPreference:
    row = db.query(models.CompanionPreference).filter_by(
        tenant_id=membership.tenant_id, membership_id=membership.id,
    ).first()
    if row is None:
        row = models.CompanionPreference(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            membership_id=membership.id,
        )
        db.add(row)
        db.flush()
    return row


def _delivery_mode(severity: str, proactive_level: str) -> str:
    if proactive_level == "muted":
        return "inbox"
    if proactive_level == "mostly_silent":
        return "panel" if severity == "critical" else "badge"
    return "panel" if severity == "critical" else "bubble" if severity in {"action", "warning"} else "badge"


def _quiet_now(preference: models.CompanionPreference) -> bool:
    start, end = preference.quiet_hours.get("start"), preference.quiet_hours.get("end")
    if not start or not end:
        return False
    try:
        local = now().astimezone(ZoneInfo(preference.timezone)).strftime("%H:%M")
    except ZoneInfoNotFoundError:
        local = now().strftime("%H:%M")
    return start <= local < end if start < end else local >= start or local < end


def _event_context(db: Session, event: models.EventOutbox) -> tuple[models.ProcurementCycleObjective | None, models.Task | None]:
    task = db.get(models.Task, event.aggregate_id) if event.aggregate_type == "tasks" else None
    objective = db.get(models.ProcurementCycleObjective, task.objective_id) if task and task.objective_id else None
    requirement_id = event.payload.get("requirement_id")
    if not requirement_id and task and task.entity_type == "purchase_requirements":
        requirement_id = task.entity_id
    if objective is None and requirement_id:
        objective = db.query(models.ProcurementCycleObjective).filter_by(
            tenant_id=event.tenant_id, requirement_id=requirement_id,
        ).first()
    return objective, task


def _requirement_record_copy(db: Session, requirement: models.PurchaseRequirement,
                             actor_membership_id: str | None = None) -> tuple[str, str]:
    if requirement is None:
        return "New procurement work assigned to you", "A procurement cycle is ready for action."
    actor_name = None
    actor_id = actor_membership_id or requirement.created_by_membership_id
    actor = db.get(models.WorkspaceMembership, actor_id) if actor_id else None
    actor_user = db.get(models.User, actor.user_id) if actor else None
    actor_name = actor_user.name if actor_user else "A colleague"
    lines = db.query(models.PurchaseRequirementLine).filter_by(requirement_id=requirement.id).all()
    material_parts: list[str] = []
    for line in lines[:2]:
        item = db.get(models.Item, line.item_id)
        material_parts.append(f"{item.name if item else line.item_id} — {line.quantity:g} {line.uom}")
    if not material_parts:
        item = db.get(models.Item, requirement.item_id)
        material_parts.append(f"{item.name if item else requirement.item_id} — {requirement.quantity:g} {requirement.uom}")
    if len(lines) > 2:
        material_parts.append(f"{len(lines) - 2} more material lines")
    number = requirement.business_number or requirement.id
    return (
        f"New requirement {number} assigned to you",
        f"{actor_name} created {number} for {', '.join(material_parts)}, needed by {requirement.need_by_date}.",
    )


def _requirement_copy(db: Session, objective: models.ProcurementCycleObjective,
                      actor_membership_id: str | None = None) -> tuple[str, str]:
    requirement = db.get(models.PurchaseRequirement, objective.requirement_id)
    if requirement is None:
        return "New procurement work assigned to you", f"{objective.business_number or 'A procurement cycle'} is ready for action."
    return _requirement_record_copy(db, requirement, actor_membership_id)


def _recipients(db: Session, event: models.EventOutbox, objective: models.ProcurementCycleObjective | None,
                task: models.Task | None) -> list[models.WorkspaceMembership]:
    ids = {task.owner_membership_id} if task and task.owner_membership_id else set()
    accountable_role = (task.owner_role if task else None) or (
        objective.evaluation_summary.get("owner_role") if objective else None
    )
    if objective and objective.owner_membership_id:
        cycle_owner = db.get(models.WorkspaceMembership, objective.owner_membership_id)
        if cycle_owner and (not accountable_role or cycle_owner.role == accountable_role):
            ids.add(cycle_owner.id)
    if accountable_role and not ids:
        role_members = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=event.tenant_id, default_plant_id=event.plant_id,
            role=accountable_role, status="active",
        ).all()
        ids.update(row.id for row in role_members)
    # For unassigned/non-workflow records, keep the actor informed. A real
    # handoff targets only the next accountable person rather than echoing the
    # creator's own action back to them.
    if not ids and event.actor_membership_id:
        ids.add(event.actor_membership_id)
    if event.aggregate_type == "agent_proposals":
        proposal = db.get(models.AgentProposal, event.aggregate_id)
        if proposal:
            ids.add(proposal.owner_membership_id)
    elif event.aggregate_type == "agent_prepared_work_items":
        prepared = db.get(models.PreparedWorkItem, event.aggregate_id)
        if prepared and prepared.owner_membership_id:
            ids.add(prepared.owner_membership_id)
    elif event.aggregate_type == "commitments":
        commitment = db.get(models.Commitment, event.aggregate_id)
        if commitment and commitment.owner_membership_id:
            ids.add(commitment.owner_membership_id)
    return db.query(models.WorkspaceMembership).filter(
        models.WorkspaceMembership.tenant_id == event.tenant_id,
        models.WorkspaceMembership.id.in_(ids),
        models.WorkspaceMembership.status == "active",
    ).all() if ids else []


def _trigger(db: Session, event: models.EventOutbox, objective: models.ProcurementCycleObjective | None,
             task: models.Task | None) -> tuple[str, str, str, str]:
    if event.event_type == "agent.proposal.changed":
        proposal = db.get(models.AgentProposal, event.aggregate_id)
        if proposal and proposal.confirmation_state == "pending":
            return "decision.required", "action", "A prepared decision needs you", "Review the proposal before it expires."
        return "decision.updated", "success", "Decision recorded", "The proposal is no longer waiting for confirmation."
    if event.event_type == "prepared_work.changed":
        return "prepared_work.ready", "action", "Prepared work is ready", "Review the evidence-backed draft before applying it."
    if event.event_type == "commitment.changed":
        return "commitment.changed", "action", "A commitment changed", "Review the updated promise and downstream impact."
    if task and task.status == "blocked":
        return "task.blocked", "warning", "Work is blocked", task.blocker_reason or "A dependency needs attention."
    if task and task.status == "pending_approval":
        return "decision.required", "action", "A decision needs you", task.title
    if objective:
        risk = objective.health in {"at_risk", "blocked"}
        stage = objective.evaluation_summary.get("presentation_stage") or objective.current_stage.replace("_", " ").title()
        if not risk:
            title, message = _requirement_copy(db, objective, event.actor_membership_id)
            if objective.current_stage not in {"requirement", "specification", "rfq"}:
                title = f"{stage} work is ready for you"
            return "work.handoff", "action", title, message
        return (
            "cycle.risk_changed",
            "critical" if objective.health == "blocked" else "warning",
            "Production risk needs attention",
            objective.evaluation_summary.get("production_risk", "The procurement cycle has changed."),
        )
    if task:
        return "task.changed", "action", "Your work changed", task.title
    return "workspace.updated", "info", "Workspace updated", "A procurement record changed."


def _actions(objective: models.ProcurementCycleObjective | None, task: models.Task | None,
             specialist: str | None) -> list[dict[str, Any]]:
    if objective:
        manual_href, manual_label = STAGE_WORKFLOWS.get(
            objective.current_stage, (f"/control-centre?cycle={objective.id}", "Open work")
        )
        manual_href = f"{manual_href}?cycle={objective.id}"
    elif task:
        manual_href, manual_label = f"/agent?work_item={task.id}", "Do it myself"
    else:
        manual_href, manual_label = "/control-centre", "Open work"
    result = [{"id": "manual", "label": manual_label, "mode": "manual", "href": manual_href}]
    if specialist:
        result.append({"id": f"prepare:{specialist}", "label": "Ask Gigi to prepare", "mode": "prepare"})
    result.append({"id": "explain", "label": "Why now?", "mode": "explain"})
    return result


def process_event(db: Session, event: models.EventOutbox) -> int:
    """Create at most one current intervention per recipient/resource version."""
    if not feature_enabled(db, event.tenant_id, "proactive_companion"):
        return 0
    if event.event_type == "prepared_work.changed":
        prepared = db.get(models.PreparedWorkItem, event.aggregate_id)
        existing = db.query(models.CompanionIntervention).filter_by(
            tenant_id=event.tenant_id, run_id=prepared.generating_run_id,
        ).first() if prepared and prepared.generating_run_id else None
        if existing:
            existing.prepared_work_id = prepared.id
            existing.delivery_state, existing.delivery_mode = "delivered", "bubble"
            existing.title, existing.message = "Prepared work is ready", prepared.title
            existing.confidence, existing.evidence = prepared.confidence, prepared.evidence
            return 0
    objective, task = _event_context(db, event)
    proposal = db.get(models.AgentProposal, event.aggregate_id) if event.aggregate_type == "agent_proposals" else None
    prepared_item = db.get(models.PreparedWorkItem, event.aggregate_id) if event.aggregate_type == "agent_prepared_work_items" else None
    if proposal and proposal.confirmation_state != "pending":
        pending = db.query(models.CompanionIntervention).filter_by(
            tenant_id=event.tenant_id, proposal_id=proposal.id, trigger_type="decision.required",
        ).filter(models.CompanionIntervention.delivery_state.in_(OPEN_STATES)).all()
        for item in pending:
            item.delivery_state, item.resolved_at = "resolved", now()
    recipients = _recipients(db, event, objective, task)
    trigger_type, severity, title, message = _trigger(db, event, objective, task)
    specialist = STAGE_SPECIALISTS.get(objective.current_stage) if objective else None
    created = 0
    for membership in recipients:
        recipient_user = db.get(models.User, membership.user_id)
        recipient_name = recipient_user.name.split()[0] if recipient_user and recipient_user.name else None
        preference = preference_for(db, membership)
        policies = db.query(models.CompanionTriggerPolicy).filter_by(
            tenant_id=event.tenant_id, trigger_type=trigger_type, state="published",
        ).order_by(models.CompanionTriggerPolicy.updated_at.desc()).all()
        policy = next((candidate for candidate in policies
            if (not candidate.roles or membership.role in candidate.roles)
            and (not candidate.plant_ids or event.plant_id in candidate.plant_ids)), None)
        if policy and SEVERITY_LEVEL.get(severity, 0) < SEVERITY_LEVEL.get(policy.minimum_severity, 0):
            COMPANION_SUPPRESSIONS.labels("below_policy_severity").inc()
            continue
        selected_specialist = policy.specialist_name if policy and policy.specialist_name else specialist
        preparation_allowed = policy.preparation_allowed if policy else True
        version = objective.aggregate_version if objective else task.version if task else event.aggregate_version
        resource = objective.id if objective else task.id if task else event.aggregate_id
        semantic_key = f"{trigger_type}:{membership.id}:{resource}:v{version}"
        if db.query(models.CompanionIntervention).filter_by(
            tenant_id=event.tenant_id, semantic_key=semantic_key,
        ).first():
            continue
        superseded = db.query(models.CompanionIntervention).filter(
            models.CompanionIntervention.tenant_id == event.tenant_id,
            models.CompanionIntervention.recipient_membership_id == membership.id,
            models.CompanionIntervention.trigger_type == trigger_type,
            models.CompanionIntervention.delivery_state.in_(OPEN_STATES),
        )
        superseded = superseded.filter_by(objective_id=objective.id) if objective else superseded.filter_by(task_id=task.id) if task else superseded
        for previous in superseded.all():
            previous.delivery_state = "resolved"
            previous.resolved_at = now()
        delivery_mode = (policy.delivery_mode if policy and policy.delivery_mode != "risk_tiered"
                         else _delivery_mode(severity, preference.proactive_level))
        if _quiet_now(preference) and severity != "critical":
            delivery_mode = "inbox"
            COMPANION_SUPPRESSIONS.labels("quiet_hours").inc()
        recent_interruptions = db.query(models.CompanionIntervention).filter(
            models.CompanionIntervention.tenant_id == event.tenant_id,
            models.CompanionIntervention.recipient_membership_id == membership.id,
            models.CompanionIntervention.delivery_mode.in_(["bubble", "panel"]),
            models.CompanionIntervention.created_at >= now() - timedelta(hours=1),
        ).count()
        if recent_interruptions >= 3 and severity != "critical" and trigger_type != "work.handoff":
            delivery_mode = "badge"
            COMPANION_SUPPRESSIONS.labels("hourly_budget").inc()
        if trigger_type == "work.handoff":
            # Assigned work is a direct person-to-person handoff, not an
            # ambient insight. It must visibly arrive beside Gigi.
            delivery_mode = "bubble"
        row = models.CompanionIntervention(
            tenant_id=event.tenant_id, plant_id=event.plant_id,
            recipient_membership_id=membership.id, source_event_id=event.event_id,
            correlation_id=event.correlation_id, objective_id=objective.id if objective else None,
            task_id=task.id if task else None, proposal_id=proposal.id if proposal else None,
            prepared_work_id=prepared_item.id if prepared_item else None,
            trigger_type=trigger_type, severity=severity,
            # Fresh accountable work must outrank the daily login summary;
            # otherwise the summary remains the popup even after an SSE
            # handoff arrives for this employee.
            priority=5 if trigger_type == "work.handoff" else SEVERITY_PRIORITY[severity],
            title=title,
            message=(f"{recipient_name}, {str(message)[:1].lower()}{str(message)[1:]}" if recipient_name else str(message)).replace("_", " "),
            why_now=(f"{objective.business_number or 'This cycle'} changed to {objective.current_stage.replace('_', ' ')}."
                     if objective else "An assigned record changed and may require your attention."),
            current_owner=objective.evaluation_summary.get("owner_role") if objective else None,
            responsible_authority=objective.evaluation_summary.get("owner_role") if objective else membership.role,
            actions=_actions(objective, task, selected_specialist if preparation_allowed else None), evidence=[], confidence=1.0,
            delivery_mode=delivery_mode,
            aggregate_version=version, semantic_key=semantic_key,
            expires_at=now() + timedelta(seconds=policy.expiry_seconds if policy else 604800),
        )
        db.add(row)
        db.flush()
        COMPANION_INTERVENTIONS.labels(trigger_type, severity, delivery_mode).inc()
        profile_exists = db.query(models.AgentProfile.id).filter_by(
            tenant_id=membership.tenant_id, membership_id=membership.id, user_id=membership.user_id, enabled=True,
        ).first()
        if (objective and trigger_type != "work.handoff" and selected_specialist and preparation_allowed
                and preference.background_preparation_enabled and profile_exists):
            try:
                start_preparation(db, membership, row, selected_specialist)
                row.delivery_mode = "badge"
                row.title = "I am preparing the next step"
                row.message = f"{selected_specialist.replace('_', ' ').title()} is running in the background."
            except (LookupError, ValueError):
                # The actionable manual intervention remains useful if this
                # membership has no runnable specialist profile.
                pass
        created += 1
    return created


def create_login_briefing(db: Session, membership: models.WorkspaceMembership) -> None:
    preference = preference_for(db, membership)
    if not preference.login_briefing_enabled or preference.proactive_level == "muted":
        return
    day = now().date().isoformat()
    key = f"login_briefing:{membership.id}:{day}"
    if db.query(models.CompanionIntervention).filter_by(tenant_id=membership.tenant_id, semantic_key=key).first():
        return
    pending = db.query(models.CompanionIntervention).filter(
        models.CompanionIntervention.tenant_id == membership.tenant_id,
        models.CompanionIntervention.recipient_membership_id == membership.id,
        models.CompanionIntervention.delivery_state.in_(OPEN_STATES),
    ).count()
    tasks = db.query(models.Task).filter(
        models.Task.tenant_id == membership.tenant_id,
        models.Task.plant_id == membership.default_plant_id,
        models.Task.owner_membership_id == membership.id,
        models.Task.status.in_(["open", "accepted", "in_progress", "pending_approval", "blocked"]),
    ).order_by(models.Task.due_at.asc()).limit(3).all()
    cycles = db.query(models.ProcurementCycleObjective).filter(
        models.ProcurementCycleObjective.tenant_id == membership.tenant_id,
        models.ProcurementCycleObjective.plant_id == membership.default_plant_id,
        models.ProcurementCycleObjective.status == "active",
    ).order_by(models.ProcurementCycleObjective.need_by_date.asc()).limit(3).all()
    relevant_cycles = [row for row in cycles if row.owner_membership_id == membership.id
        or row.evaluation_summary.get("owner_role") == membership.role]
    total = pending + len(tasks) + len(relevant_cycles)
    urgent = next((row for row in relevant_cycles if row.health in {"at_risk", "blocked"}), None)
    lead = tasks[0].title if tasks else (
        f"{relevant_cycles[0].business_number or 'A procurement cycle'} is at {relevant_cycles[0].current_stage.replace('_', ' ')}"
        if relevant_cycles else None
    )
    severity = "critical" if urgent else "action" if total else "info"
    message = (f"Start with {lead}. {max(total - 1, 0)} other item{'s' if total - 1 != 1 else ''} are in your briefing."
               if lead else "No urgent procurement intervention needs you right now.")
    delivery_mode = _delivery_mode(severity, preference.proactive_level)
    if preference.proactive_level == "risk_tiered" and severity == "info":
        delivery_mode = "bubble"
    if _quiet_now(preference) and severity != "critical":
        delivery_mode = "inbox"
    db.add(models.CompanionIntervention(
        tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
        recipient_membership_id=membership.id, correlation_id=f"LOGIN-{uuid4().hex[:16].upper()}",
        trigger_type="login.briefing", severity=severity,
        priority=0 if urgent else 10 if total else 70, title="Your procurement briefing is ready",
        message=message,
        why_now="This is your first workspace briefing today.",
        responsible_authority=membership.role,
        actions=[{"id": "open_centre", "label": "Review my day", "mode": "manual", "href": "/control-centre"}],
        evidence=[], confidence=1.0, delivery_mode=delivery_mode,
        semantic_key=key, expires_at=now() + timedelta(days=1),
    ))
    db.flush()


def serialize(row: models.CompanionIntervention) -> dict[str, Any]:
    return agent_service.record_dict(row)


def reconcile_assigned_work(db: Session, membership: models.WorkspaceMembership) -> int:
    """Repair a missed outbox delivery from canonical assigned task state."""
    tasks = db.query(models.Task).filter(
        models.Task.tenant_id == membership.tenant_id,
        models.Task.plant_id == membership.default_plant_id,
        models.Task.owner_membership_id == membership.id,
        models.Task.status.in_(["open", "accepted", "in_progress", "pending_approval", "blocked"]),
    ).order_by(models.Task.created_at.desc()).limit(25).all()
    created = 0
    for task in tasks:
        objective = db.get(models.ProcurementCycleObjective, task.objective_id) if task.objective_id else None
        requirement = None
        if task.entity_type == "purchase_requirements" and task.entity_id:
            requirement = db.query(models.PurchaseRequirement).filter_by(
                tenant_id=membership.tenant_id, id=task.entity_id,
            ).first()
            if objective is None and requirement:
                objective = db.query(models.ProcurementCycleObjective).filter_by(
                    tenant_id=membership.tenant_id, requirement_id=requirement.id,
                ).first()
            if objective is None and requirement:
                # A task and its cycle projection can be observed a few
                # milliseconds apart. Reconcile the deterministic projection
                # now so the employee never receives a context-free handoff.
                from app import cycle_orchestration
                objective = cycle_orchestration.evaluate(db, requirement)
        if objective:
            # Retire the early generic task fallback once the canonical cycle
            # projection is available. The cycle-aware intervention carries
            # the REQ number, material context and useful workflow actions.
            generic_rows = db.query(models.CompanionIntervention).filter(
                models.CompanionIntervention.tenant_id == membership.tenant_id,
                models.CompanionIntervention.recipient_membership_id == membership.id,
                models.CompanionIntervention.task_id == task.id,
                models.CompanionIntervention.objective_id.is_(None),
                models.CompanionIntervention.trigger_type == "work.handoff",
                models.CompanionIntervention.delivery_state.in_(OPEN_STATES),
            ).all()
            for index, generic in enumerate(generic_rows):
                if index == 0:
                    # Upgrade the already-delivered row in place so its ID
                    # remains valid for the browser/SSE notification.
                    generic.objective_id = objective.id
                else:
                    generic.delivery_state, generic.resolved_at = "resolved", now()
        existing = db.query(models.CompanionIntervention).filter(
            models.CompanionIntervention.tenant_id == membership.tenant_id,
            models.CompanionIntervention.recipient_membership_id == membership.id,
            models.CompanionIntervention.trigger_type == "work.handoff",
            models.CompanionIntervention.delivery_state.in_(OPEN_STATES),
            ((models.CompanionIntervention.task_id == task.id) |
             (models.CompanionIntervention.objective_id == objective.id if objective else False)),
        ).first()
        if existing:
            if objective:
                title, detailed_message = _requirement_copy(db, objective)
                recipient_user = db.get(models.User, membership.user_id)
                recipient_name = recipient_user.name.split()[0] if recipient_user and recipient_user.name else None
                existing.title = title
                existing.message = (f"{recipient_name}, {detailed_message[:1].lower()}{detailed_message[1:]}"
                                    if recipient_name else detailed_message)
                existing.task_id = existing.task_id or task.id
                existing.actions = _actions(objective, task, STAGE_SPECIALISTS.get(objective.current_stage))
                existing.priority = 5
            continue
        specialist = STAGE_SPECIALISTS.get(objective.current_stage) if objective else None
        business_number = objective.business_number if objective else None
        source_name = None
        if objective:
            requirement = db.get(models.PurchaseRequirement, objective.requirement_id)
            creator = db.get(models.WorkspaceMembership, requirement.created_by_membership_id) if requirement and requirement.created_by_membership_id else None
            creator_user = db.get(models.User, creator.user_id) if creator else None
            source_name = creator_user.name if creator_user else None
        semantic_key = f"work.handoff:{membership.id}:{task.id}:v{task.version}"
        if db.query(models.CompanionIntervention.id).filter_by(
            tenant_id=membership.tenant_id, semantic_key=semantic_key,
        ).first():
            continue
        recipient_user = db.get(models.User, membership.user_id)
        recipient_name = recipient_user.name.split()[0] if recipient_user and recipient_user.name else None
        if objective:
            title, message = _requirement_copy(db, objective)
        elif requirement:
            title, message = _requirement_record_copy(db, requirement)
        else:
            title = task.title
            message = f"{business_number or task.title}"
            if source_name:
                message += f" from {source_name}"
            message += " is assigned to you and ready for action."
        if recipient_name:
            message = f"{recipient_name}, {message[:1].lower()}{message[1:]}"
        db.add(models.CompanionIntervention(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            recipient_membership_id=membership.id, correlation_id=f"RECON-{uuid4().hex[:16].upper()}",
            objective_id=objective.id if objective else None, task_id=task.id,
            trigger_type="work.handoff", severity="action", priority=5,
            title=title, message=message,
            why_now="This open task is assigned to you and has no completed handoff acknowledgement.",
            current_owner=task.owner_role, responsible_authority=task.owner_role,
            actions=_actions(objective, task, specialist), evidence=[{"type": "task", "id": task.id}],
            confidence=1.0, delivery_mode="bubble", aggregate_version=task.version,
            semantic_key=semantic_key, expires_at=now() + timedelta(days=7),
        ))
        created += 1
    if created:
        db.flush()
    return created


def state(db: Session, membership: models.WorkspaceMembership) -> dict[str, Any]:
    create_login_briefing(db, membership)
    reconcile_assigned_work(db, membership)
    current_time = now()
    # Reconcile handoffs created by earlier releases so already-assigned work
    # becomes visible immediately after deployment, without requiring the
    # manager to recreate the requirement.
    db.query(models.CompanionIntervention).filter(
        models.CompanionIntervention.tenant_id == membership.tenant_id,
        models.CompanionIntervention.recipient_membership_id == membership.id,
        models.CompanionIntervention.trigger_type == "work.handoff",
        models.CompanionIntervention.priority > 5,
        models.CompanionIntervention.delivery_state.in_(OPEN_STATES),
    ).update({models.CompanionIntervention.priority: 5}, synchronize_session=False)
    query = db.query(models.CompanionIntervention).filter(
        models.CompanionIntervention.tenant_id == membership.tenant_id,
        models.CompanionIntervention.recipient_membership_id == membership.id,
        models.CompanionIntervention.delivery_state.in_(OPEN_STATES),
        (models.CompanionIntervention.expires_at.is_(None) | (models.CompanionIntervention.expires_at > current_time)),
        (models.CompanionIntervention.snoozed_until.is_(None) | (models.CompanionIntervention.snoozed_until <= current_time)),
    ).order_by(models.CompanionIntervention.priority.asc(), models.CompanionIntervention.created_at.desc())
    rows = query.limit(50).all()
    for row in rows:
        if row.delivery_state == "queued":
            row.delivery_state = "delivered"
            row.delivered_at = current_time
    preference = preference_for(db, membership)
    db.commit()
    running = db.query(models.AgentRun).filter_by(
        tenant_id=membership.tenant_id, membership_id=membership.id,
    ).filter(models.AgentRun.state.in_(["queued", "running"])).count()
    top = rows[0] if rows else None
    visual_state = "thinking" if running else "urgent" if top and top.severity == "critical" else "new" if top else "idle"
    return {
        "state": visual_state, "unresolved_count": len(rows), "running_count": running,
        "top_intervention": serialize(top) if top else None,
        "interventions": [serialize(row) for row in rows],
        "preferences": agent_service.record_dict(preference),
    }


def start_preparation(db: Session, membership: models.WorkspaceMembership,
                      intervention: models.CompanionIntervention, specialist: str) -> models.AgentRun:
    if not intervention.objective_id:
        raise ValueError("This intervention has no procurement cycle to prepare")
    profile = agent_service.profile_for_membership(db, membership)
    thread = db.query(models.AgentThread).filter_by(
        tenant_id=membership.tenant_id, membership_id=membership.id,
        objective_id=intervention.objective_id, status="active",
    ).first()
    if thread is None:
        thread = models.AgentThread(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            membership_id=membership.id, agent_profile_id=profile.id, thread_type="specialist",
            title=f"Companion · {intervention.title}", objective_id=intervention.objective_id,
            participant_membership_ids=[membership.id],
        )
        db.add(thread)
        db.flush()
    correlation_id = intervention.correlation_id or str(uuid4())
    request = SpecialistRequest(
        specialist=specialist, objective_id=intervention.objective_id,
        task_id=intervention.task_id, requested_outcome=intervention.title,
        authorized_artifact_ids=[], constraints={"source": "companion"}, correlation_id=correlation_id,
    )
    run = models.AgentRun(
        tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
        thread_id=thread.id, membership_id=membership.id, agent_profile_id=profile.id,
        state="queued", provider="deterministic", model="specialist-v1",
        context_hash=hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
        policy_version=profile.policy_version, trace_id=f"trace-{uuid4().hex[:16]}",
        correlation_id=correlation_id, intent=f"specialist:{specialist}",
        requested_outcome=request.requested_outcome,
        active_context={"specialist_request": request.model_dump(mode="json")},
    )
    db.add(run)
    db.flush()
    intervention.run_id = run.id
    intervention.delivery_state = "acted"
    intervention.selected_action = f"prepare:{specialist}"
    return run


def publish(membership_id: str, payload: dict[str, Any]) -> None:
    """Best-effort wake-up; persisted state is authoritative."""
    try:
        import redis
        from app.core.config import get_settings
        redis.Redis.from_url(get_settings().redis_url).publish(
            f"companion:{membership_id}", json.dumps(payload, default=str),
        )
    except Exception:
        return
