from __future__ import annotations

import hashlib
from datetime import timedelta
from datetime import datetime, timezone
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import models
from app.intelligence.schemas import ActionCandidate
from app.platform import actions
from app.platform.case_models import GigiInsight


def propose_action(db: Session, *, user: models.User, membership_id: str, candidate: ActionCandidate,
                   idempotency_key: str, correlation_id: str, originating_case_id: str | None = None):
    return actions.propose(db, tenant_id=user.tenant_id, plant_id=user.plant_id, membership_id=membership_id,
        action_type=candidate.action_type, target_type=candidate.target_type, target_id=candidate.target_id,
        payload=candidate.parameters, rationale=candidate.reason, idempotency_key=idempotency_key,
        correlation_id=correlation_id, originating_case_id=originating_case_id,
        evidence=[item.model_dump(mode="json") for item in candidate.evidence],
        expected_impact=candidate.expected_impact, risk_level=candidate.risk_level)


def search_knowledge(db: Session, *, user: models.User, query: str, limit: int = 8) -> list[dict]:
    now = datetime.now(timezone.utc)
    membership = db.query(models.WorkspaceMembership).filter_by(tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    allowed_plants = set(membership.plant_ids or [user.plant_id]) if membership else {user.plant_id}
    documents = db.query(models.KnowledgeDocument).filter(
        models.KnowledgeDocument.tenant_id == user.tenant_id,
        models.KnowledgeDocument.approval_state == "approved",
        models.KnowledgeDocument.retired_at.is_(None),
        or_(models.KnowledgeDocument.effective_from.is_(None), models.KnowledgeDocument.effective_from <= now),
        or_(models.KnowledgeDocument.effective_to.is_(None), models.KnowledgeDocument.effective_to > now),
    ).all()
    terms = [term.lower() for term in query.split() if len(term) > 2]
    ranked = []
    for document in documents:
        if document.role_acl and user.role not in document.role_acl:
            continue
        if document.plant_acl and not allowed_plants.intersection(document.plant_acl):
            continue
        for chunk in db.query(models.KnowledgeChunk).filter_by(knowledge_document_id=document.id).all():
            score = sum(chunk.content.lower().count(term) for term in terms)
            if score:
                ranked.append((score, {"document_id": document.id, "title": document.title,
                    "version": document.revision, "chunk_id": chunk.id, "content": chunk.content[:1200],
                    "page": chunk.page_reference, "section": chunk.section_reference}))
    return [item for _, item in sorted(ranked, key=lambda row: row[0], reverse=True)[:limit]]


def create_investigation(db: Session, *, tenant_id: str, plant_id: str, trigger_type: str,
                         trigger_reference: str, entity_type: str | None, entity_id: str | None,
                         severity: str, correlation_id: str) -> models.AIInvestigation:
    signature = f"{plant_id}:{trigger_type}:{entity_type}:{entity_id}:{trigger_reference}"
    dedupe = hashlib.sha256(signature.encode()).hexdigest()
    existing = db.query(models.AIInvestigation).filter_by(tenant_id=tenant_id, dedupe_key=dedupe).first()
    if existing:
        return existing
    row = models.AIInvestigation(tenant_id=tenant_id, plant_id=plant_id, trigger_type=trigger_type,
        trigger_reference=trigger_reference, entity_type=entity_type, entity_id=entity_id,
        severity=severity, status="queued", dedupe_key=dedupe, correlation_id=correlation_id)
    db.add(row)
    return row


def record_verified_experience(db: Session, *, action_intent_id: str) -> models.AgentExperience:
    from app.platform.models import ActionIntent, ActionOutcome
    intent = db.get(ActionIntent, action_intent_id)
    outcome = db.query(ActionOutcome).filter_by(action_intent_id=action_intent_id).first()
    if not intent or not outcome or outcome.verification_status not in {"verified", "recovered", "verified_recovered"}:
        raise ValueError("Only independently verified outcomes become experience")
    existing = db.query(models.AgentExperience).filter_by(tenant_id=intent.tenant_id, action_intent_id=intent.id).first()
    if existing:
        return existing
    effectiveness = 1.0
    row = models.AgentExperience(tenant_id=intent.tenant_id, plant_id=intent.plant_id, domain=intent.action_type.split(".")[0].lower(),
        problem_type=intent.reason_code or intent.action_type, problem_signature=f"{intent.target_type}:{intent.target_id}:{intent.action_type}",
        entity_type=intent.target_type, entity_id=intent.target_id, action_intent_id=intent.id,
        context_reference={"correlation_id": intent.correlation_id}, candidates=[],
        selected_strategy={"action_type": intent.action_type, "parameters": intent.payload},
        predicted_outcome=intent.expected_impact, actual_outcome=outcome.metrics,
        effectiveness=effectiveness, evidence=outcome.evidence)
    db.add(row)
    return row


def generate_briefing(db: Session, *, user: models.User, membership_id: str,
                      briefing_type: str, period_key: str) -> models.AIBriefing:
    existing = db.query(models.AIBriefing).filter_by(tenant_id=user.tenant_id,
        membership_id=membership_id, briefing_type=briefing_type, period_key=period_key).first()
    from app.platform.models import ActionIntent, OperationalCase
    cases = db.query(OperationalCase).filter(OperationalCase.tenant_id == user.tenant_id,
        OperationalCase.plant_id == user.plant_id,
        OperationalCase.status.notin_(["closed", "cancelled", "resolved"])).order_by(
        OperationalCase.priority_score.desc(), OperationalCase.decision_deadline.asc()).limit(20).all()
    approvals = db.query(ActionIntent).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id,
        status="awaiting_approval").order_by(ActionIntent.created_at.desc()).limit(20).all()
    items = ([{"kind": "case", "id": row.id, "title": row.title, "severity": row.severity,
               "href": f"/cases/{row.id}", "evidence_ref": f"case:{row.id}"} for row in cases] +
             [{"kind": "approval", "id": row.id, "title": row.action_type, "severity": row.risk_level,
               "href": "/platform/actions", "evidence_ref": f"action:{row.id}"} for row in approvals])
    if existing:
        existing.items = items
        existing.evidence = [{"ref": item["evidence_ref"], "kind": item["kind"], "id": item["id"]} for item in items]
        return existing
    row = models.AIBriefing(tenant_id=user.tenant_id, plant_id=user.plant_id, membership_id=membership_id,
        briefing_type=briefing_type, period_key=period_key, title=f"{briefing_type.replace('_', ' ').title()} briefing",
        items=items, evidence=[{"ref": item["evidence_ref"], "kind": item["kind"], "id": item["id"]} for item in items])
    db.add(row)
    return row


def refresh_case_insights(db: Session, *, user: models.User, membership_id: str) -> list[GigiInsight]:
    """Deterministic proactive insight projection over shared cases."""
    from app.platform.models import OperationalCase
    now = datetime.now(timezone.utc)
    cases = db.query(OperationalCase).filter(OperationalCase.tenant_id == user.tenant_id,
        OperationalCase.plant_id == user.plant_id, OperationalCase.status.notin_(("closed", "cancelled", "resolved"))).all()
    preference = db.query(models.CompanionPreference).filter_by(
        tenant_id=user.tenant_id, membership_id=membership_id).first()
    rows = []
    for case in cases:
        signature = hashlib.sha256(f"case:{case.id}:member:{membership_id}:attention".encode()).hexdigest()
        equivalents = db.query(GigiInsight).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id,
            membership_id=membership_id, case_id=case.id, category="CASE_ATTENTION").order_by(
            GigiInsight.created_at.desc()).all()
        row = next((item for item in equivalents if item.deduplication_signature == signature), None)
        if row is None and equivalents:
            row = equivalents[0]
            row.deduplication_signature = signature
        for duplicate in equivalents:
            if duplicate is not row:
                duplicate.delivery_state = "RESOLVED"
                duplicate.next_evaluation_at = None
        critical = case.severity.lower() == "critical"
        deadline = case.decision_deadline
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        deadline_close = bool(deadline and deadline <= now + timedelta(hours=8))
        delivery = "POPUP" if critical or deadline_close or case.recovery_state == "NOT_RECOVERED" else "TOAST" if case.severity.lower() in {"high", "medium"} else "FEED"
        if preference:
            from app.companion import _quiet_now
            if preference.proactive_level in {"muted", "mostly_silent"}:
                delivery = "FEED"
            elif _quiet_now(preference) and not (critical or deadline_close or case.recovery_state == "NOT_RECOVERED"):
                delivery = "FEED"
        from app.platform.case_service import _human_case_copy
        case_title, case_summary = _human_case_copy(db, case)
        summary = case_summary or case_title
        if row is None:
            row = GigiInsight(tenant_id=user.tenant_id, plant_id=user.plant_id, case_id=case.id,
                membership_id=membership_id, category="CASE_ATTENTION", severity=case.severity,
                title=f"Gigi noticed: {case_title}", summary=summary, evidence=[{"ref": f"case:{case.id}", "type": "operational_case"}],
                deduplication_signature=signature, delivery_state=delivery, next_evaluation_at=now + timedelta(minutes=15))
            db.add(row)
        else:
            row.title, row.summary, row.severity = f"Gigi noticed: {case_title}", summary, case.severity
            snooze = row.snoozed_until
            if snooze and snooze.tzinfo is None:
                snooze = snooze.replace(tzinfo=timezone.utc)
            if not row.acknowledged_at and not row.dismissed_at:
                if not snooze or snooze <= now:
                    row.snoozed_until = None
                    row.delivery_state = delivery
            row.next_evaluation_at = now + timedelta(minutes=15)
        rows.append(row)
    active_ids = {case.id for case in cases}
    for previous in db.query(GigiInsight).filter_by(tenant_id=user.tenant_id,
            plant_id=user.plant_id, membership_id=membership_id, category="CASE_ATTENTION").all():
        if previous.case_id not in active_ids:
            previous.delivery_state = "RESOLVED"
            previous.next_evaluation_at = None
    return rows


def create_case_commitment(db: Session, *, user: models.User, membership_id: str, case_id: str,
                           due_at: datetime, deliverable: str, entity_type: str | None,
                           entity_id: str | None) -> models.Commitment:
    from app.platform.models import OperationalCase
    case = db.query(OperationalCase).filter_by(id=case_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not case:
        raise ValueError("Case not found")
    semantic = hashlib.sha256(f"commitment:{case.id}:{membership_id}:{due_at.isoformat()}:{deliverable}".encode()).hexdigest()
    task = db.query(models.Task).filter_by(tenant_id=user.tenant_id, semantic_key=semantic).first()
    if task is None:
        task = models.Task(tenant_id=user.tenant_id, plant_id=user.plant_id, title=deliverable,
            owner_role=user.role, owner_user_id=user.id, owner_membership_id=membership_id,
            creator_membership_id=membership_id, status="open", severity=case.severity,
            linked_case_id=case.id, entity_type=entity_type, entity_id=entity_id,
            due_at=due_at, task_type="gigi_commitment", requested_outcome=deliverable,
            priority="urgent" if case.severity.lower() == "critical" else "high", semantic_key=semantic)
        db.add(task); db.flush()
    existing = db.query(models.Commitment).filter_by(task_id=task.id, operational_case_id=case.id, status="active").first()
    if existing: return existing
    row = models.Commitment(tenant_id=user.tenant_id, plant_id=user.plant_id, task_id=task.id,
        commitment_type="operational", owner_membership_id=membership_id, promised_at=due_at,
        deliverable=deliverable, status="active", operational_case_id=case.id,
        related_entity_type=entity_type, related_entity_id=entity_id,
        completion_condition={"type": "evidence_received"}, escalation_condition={"after_due_minutes": 0},
        evidence_requirement="Recorded response or fresh operational fact", next_evaluation_at=due_at,
        dependency_state="EXTERNAL" if entity_type == "supplier" else "INTERNAL")
    db.add(row)
    return row
