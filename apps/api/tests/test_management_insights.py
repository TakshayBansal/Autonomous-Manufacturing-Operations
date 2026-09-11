import pytest

from app import management_insights
from app.agent_schemas import KnowledgeCreateRequest, KnowledgeDecisionRequest
from app.agent_schemas import AgentMessageRequest, ThreadCreateRequest
from app import agent_service
from app.routers import agents as agent_routes
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db); db.commit()


def test_readiness_is_measurable_and_every_check_has_evidence_navigation() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        result = management_insights.readiness(db, admin)
        assert result["total"] == len(result["checks"])
        assert 0 <= result["percent"] <= 100
        assert all(item["key"] and item["label"] and item["evidence_href"].startswith("/") for item in result["checks"])
        assert result["status"] in {"ready", "needs_configuration"}


def test_management_analytics_reconcile_to_sources_and_never_score_employees() -> None:
    with SessionLocal() as db:
        manager = db.query(models.User).filter_by(email="plant.manager@genuinegigs.local").one()
        result = management_insights.analytics(db, manager)
        assert result["opaque_employee_score"] is False
        metrics = {row["key"]: row for row in result["metrics"]}
        assert metrics["active_workload"]["value"] == db.query(models.Task).filter(
            models.Task.tenant_id == manager.tenant_id,
            models.Task.plant_id == manager.plant_id,
            models.Task.status.in_({'open', 'accepted', 'in_progress', 'blocked', 'review', 'pending_approval'}),
        ).count()
        assert metrics["savings"]["value"] is None
        assert "baseline-price policy" in metrics["savings"]["note"]
        assert all(row["evidence_href"].startswith("/") and row["sample_size"] >= 0 for row in result["metrics"])


def test_briefs_are_task_sourced_and_configuration_export_excludes_secrets() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        brief = management_insights.brief(db, admin, "morning")
        assert brief["employee_score"] is None
        assert all(source["type"] == "task" and source["href"].startswith("/control-centre") for source in brief["sources"])
        exported = management_insights.configuration_export(db, admin)
        assert exported["secrets_included"] is False
        assert all("secret_ref" not in row and "config" not in row for row in exported["connections"])
        assert all(set(row) == {"membership_id", "role", "manager_membership_id", "status"} for row in exported["memberships"])


def test_knowledge_is_role_scoped_versioned_and_only_latest_approved_source_remains_active() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        first = agent_routes.create_knowledge(KnowledgeCreateRequest(
            title="Supplier approval SOP", source="SOP-PUR-01", content="Use verified supplier evidence before sending a request.",
            role_acl=["purchase_manager"], plant_acl=[admin.plant_id],
        ), db, admin)
        agent_routes.decide_knowledge(first["id"], KnowledgeDecisionRequest(decision="approve"), db, admin)
        second = agent_routes.create_knowledge(KnowledgeCreateRequest(
            title="Supplier approval SOP", source="SOP-PUR-01", content="Use current verified evidence and record the review decision.",
            role_acl=["purchase_manager"], plant_acl=[admin.plant_id],
        ), db, admin)
        assert second["document_version"] == 2
        agent_routes.decide_knowledge(second["id"], KnowledgeDecisionRequest(decision="approve"), db, admin)
        active = db.query(models.KnowledgeDocument).filter_by(
            tenant_id=admin.tenant_id, plant_id=admin.plant_id, title="Supplier approval SOP", approval_state="approved",
        ).all()
        assert [row.id for row in active] == [second["id"]]
        purchase_manager = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=admin.tenant_id, role="purchase_manager", status="active",
        ).one()
        assert second["id"] in {row.id for row in __import__('app.agent_service', fromlist=['approved_knowledge']).approved_knowledge(db, purchase_manager)}


def test_role_agents_return_sourced_brief_metrics_and_readiness_without_employee_score() -> None:
    with SessionLocal() as db:
        manager = db.query(models.User).filter_by(email="plant.manager@genuinegigs.local").one()
        thread = agent_service.create_thread(db, manager, ThreadCreateRequest(thread_type="personal", title="Management brief")); db.flush()
        _run, brief = agent_service.run_message(db, manager, thread.id, AgentMessageRequest(content="Give me my morning brief", requested_capability="get_daily_brief"))
        assert "active assignments" in brief.content
        task_citations = [citation for citation in brief.citations if citation["type"] == "task"]
        assert all(citation["href"].startswith("/control-centre") for citation in task_citations)
        _run, metrics = agent_service.run_message(db, manager, thread.id, AgentMessageRequest(content="Summarize operating metrics", requested_capability="summarize_management_metrics"))
        assert "No employee score" in metrics.content
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        admin_thread = agent_service.create_thread(db, admin, ThreadCreateRequest(thread_type="personal", title="Readiness")); db.flush()
        _run, readiness_message = agent_service.run_message(db, admin, admin_thread.id, AgentMessageRequest(content="Check readiness", requested_capability="review_workspace_readiness"))
        assert "Workspace readiness is" in readiness_message.content
