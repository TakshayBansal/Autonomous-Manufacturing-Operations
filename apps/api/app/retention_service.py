from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.domains import workflows
from app.core.config import get_settings
from app.core.metrics import RETENTION_ACTIONS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def preview(db: Session, user: models.User) -> dict[str, Any]:
    now = _now()
    held_thread_ids = {
        row.entity_id for row in db.query(models.RetentionHold).filter_by(
            tenant_id=user.tenant_id, entity_type="agent_thread", released_at=None,
        ).all()
    }
    expired_threads = db.query(models.AgentThread).filter(
        models.AgentThread.tenant_id == user.tenant_id,
        models.AgentThread.retention_until.is_not(None),
        models.AgentThread.retention_until <= now,
    ).all()
    eligible_ids = [row.id for row in expired_threads if row.id not in held_thread_ids]
    expired_memories = db.query(models.AgentMemory).filter(
        models.AgentMemory.tenant_id == user.tenant_id,
        models.AgentMemory.expires_at.is_not(None),
        models.AgentMemory.expires_at <= now,
    ).count()
    expired_knowledge = db.query(models.KnowledgeDocument).filter(
        models.KnowledgeDocument.tenant_id == user.tenant_id,
        models.KnowledgeDocument.retention_until.is_not(None),
        models.KnowledgeDocument.retention_until <= now,
        models.KnowledgeDocument.retired_at.is_not(None),
    ).count()
    message_count = db.query(models.AgentMessage).filter(models.AgentMessage.thread_id.in_(eligible_ids)).count() if eligible_ids else 0
    checkpoint_cutoff = now - timedelta(days=get_settings().agent_checkpoint_retention_days)
    expired_checkpoints = db.query(models.AgentCheckpoint).filter(
        models.AgentCheckpoint.tenant_id == user.tenant_id,
        models.AgentCheckpoint.created_at <= checkpoint_cutoff,
        ~models.AgentCheckpoint.thread_id.in_(held_thread_ids or {""}),
    ).count()
    return {
        "generated_at": now.isoformat(), "dry_run": True,
        "eligible": {"threads": len(eligible_ids), "messages": message_count, "memories": expired_memories, "retired_knowledge": expired_knowledge, "checkpoints": expired_checkpoints},
        "held_threads": len(expired_threads) - len(eligible_ids),
        "preserved": ["audit_events", "agent_action_receipts", "agent_proposals", "business_records"],
    }


def enforce(db: Session, user: models.User, confirmation: str) -> dict[str, Any]:
    if confirmation != "ENFORCE_RETENTION":
        raise ValueError("Explicit ENFORCE_RETENTION confirmation is required")
    report = preview(db, user)
    now = _now()
    held = {
        row.entity_id for row in db.query(models.RetentionHold).filter_by(
            tenant_id=user.tenant_id, entity_type="agent_thread", released_at=None,
        ).all()
    }
    threads = db.query(models.AgentThread).filter(
        models.AgentThread.tenant_id == user.tenant_id,
        models.AgentThread.retention_until.is_not(None),
        models.AgentThread.retention_until <= now,
    ).all()
    thread_ids = [row.id for row in threads if row.id not in held]
    run_ids = [row.id for row in db.query(models.AgentRun).filter(models.AgentRun.thread_id.in_(thread_ids)).all()] if thread_ids else []
    if thread_ids:
        db.query(models.AgentMessage).filter(models.AgentMessage.thread_id.in_(thread_ids)).update({
            models.AgentMessage.content: "[expired by retention policy]", models.AgentMessage.content_blocks: [], models.AgentMessage.citations: [],
        }, synchronize_session=False)
        for thread in threads:
            if thread.id in thread_ids:
                thread.context_state = {}
                thread.status = "retention_expired"
    if run_ids:
        db.query(models.AgentCheckpoint).filter(models.AgentCheckpoint.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(models.AgentEvent).filter(models.AgentEvent.run_id.in_(run_ids)).update({models.AgentEvent.payload: {}}, synchronize_session=False)
        db.query(models.AgentToolCall).filter(models.AgentToolCall.run_id.in_(run_ids)).update({models.AgentToolCall.arguments: {}}, synchronize_session=False)
        db.query(models.AgentRun).filter(models.AgentRun.id.in_(run_ids)).update({
            models.AgentRun.active_context: {}, models.AgentRun.requested_outcome: None, models.AgentRun.error: None,
        }, synchronize_session=False)
    checkpoint_cutoff = now - timedelta(days=get_settings().agent_checkpoint_retention_days)
    expired_checkpoints = db.query(models.AgentCheckpoint).filter(
        models.AgentCheckpoint.tenant_id == user.tenant_id,
        models.AgentCheckpoint.created_at <= checkpoint_cutoff,
        ~models.AgentCheckpoint.thread_id.in_(held or {""}),
    ).delete(synchronize_session=False)
    memories = db.query(models.AgentMemory).filter(
        models.AgentMemory.tenant_id == user.tenant_id, models.AgentMemory.expires_at.is_not(None), models.AgentMemory.expires_at <= now,
    ).delete(synchronize_session=False)
    knowledge = db.query(models.KnowledgeDocument).filter(
        models.KnowledgeDocument.tenant_id == user.tenant_id,
        models.KnowledgeDocument.retention_until.is_not(None), models.KnowledgeDocument.retention_until <= now,
        models.KnowledgeDocument.retired_at.is_not(None),
    ).all()
    knowledge_ids = [row.id for row in knowledge]
    if knowledge_ids:
        db.query(models.KnowledgeChunk).filter(models.KnowledgeChunk.knowledge_document_id.in_(knowledge_ids)).delete(synchronize_session=False)
        db.query(models.KnowledgeDocument).filter(models.KnowledgeDocument.id.in_(knowledge_ids)).update(
            {models.KnowledgeDocument.content: "[expired by retention policy]"}, synchronize_session=False,
        )
    report["dry_run"] = False
    report["executed"] = {"threads_redacted": len(thread_ids), "memories_deleted": memories, "knowledge_redacted": len(knowledge_ids), "checkpoints_deleted": expired_checkpoints}
    for record_type, count in report["executed"].items():
        if count:
            RETENTION_ACTIONS.labels(record_type).inc(count)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email, "retention.enforced", "tenant", user.tenant_id,
                           actor_user_id=user.id, meta=report["executed"])
    return report


def place_hold(db: Session, user: models.User, thread_id: str, reason: str) -> models.RetentionHold:
    thread = db.query(models.AgentThread).filter_by(id=thread_id, tenant_id=user.tenant_id).first()
    if thread is None:
        raise LookupError("Agent thread not found")
    membership = db.query(models.WorkspaceMembership).filter_by(user_id=user.id, tenant_id=user.tenant_id, status="active").first()
    existing = db.query(models.RetentionHold).filter_by(tenant_id=user.tenant_id, entity_type="agent_thread", entity_id=thread_id).first()
    if existing:
        existing.reason, existing.released_at, existing.released_by_membership_id = reason, None, None
        hold = existing
    else:
        hold = models.RetentionHold(tenant_id=user.tenant_id, plant_id=thread.plant_id, entity_type="agent_thread", entity_id=thread_id,
                                    reason=reason, placed_by_membership_id=membership.id)
        db.add(hold)
    db.flush()
    workflows.create_audit(db, user.tenant_id, thread.plant_id, user.email, "retention.hold_placed", "agent_thread", thread_id,
                           actor_user_id=user.id, meta={"reason": reason})
    return hold
