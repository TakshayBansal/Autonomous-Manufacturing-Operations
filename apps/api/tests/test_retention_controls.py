from datetime import datetime, timedelta, timezone

import pytest

from app import agent_service, retention_service
from app.agent_schemas import ThreadCreateRequest
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def _expired_thread(db, admin):
    thread = agent_service.create_thread(db, admin, ThreadCreateRequest(thread_type="personal", title="Expired private conversation"))
    thread.retention_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.add(models.AgentMessage(
        tenant_id=admin.tenant_id, plant_id=admin.plant_id, thread_id=thread.id,
        membership_id=agent_service.membership_for_user(db, admin).id, message_type="user",
        content="private supplier negotiation note", correlation_id="RETENTION-TEST",
    ))
    db.add(models.AgentCheckpoint(
        tenant_id=admin.tenant_id, plant_id=admin.plant_id, run_id="expired-run",
        thread_id=thread.id, sequence=1, step_name="old_context",
        state_data={"private": "context"}, state_hash="old", status="completed",
        created_at=datetime.now(timezone.utc) - timedelta(days=60),
    ))
    db.flush()
    return thread


def test_retention_preview_is_non_mutating_and_enforcement_redacts_private_content() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        thread = _expired_thread(db, admin)
        before = retention_service.preview(db, admin)
        assert before["dry_run"] is True and before["eligible"]["threads"] == 1
        assert db.query(models.AgentMessage).filter_by(thread_id=thread.id).one().content.startswith("private")
        result = retention_service.enforce(db, admin, "ENFORCE_RETENTION")
        db.flush()
        assert result["executed"]["threads_redacted"] == 1
        assert db.query(models.AgentMessage).filter_by(thread_id=thread.id).one().content == "[expired by retention policy]"
        assert db.get(models.AgentThread, thread.id).status == "retention_expired"
        assert db.query(models.AgentCheckpoint).filter_by(thread_id=thread.id).count() == 0
        assert db.query(models.AuditEvent).filter_by(action="retention.enforced", entity_id=admin.tenant_id).count() == 1


def test_legal_hold_excludes_expired_thread_from_retention() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        thread = _expired_thread(db, admin)
        retention_service.place_hold(db, admin, thread.id, "Customer investigation")
        report = retention_service.preview(db, admin)
        assert report["eligible"]["threads"] == 0 and report["held_threads"] == 1
        retention_service.enforce(db, admin, "ENFORCE_RETENTION")
        assert db.query(models.AgentMessage).filter_by(thread_id=thread.id).one().content.startswith("private")
        assert db.query(models.AgentCheckpoint).filter_by(thread_id=thread.id).count() == 1
