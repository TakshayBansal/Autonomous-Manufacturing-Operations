from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import task_service
from app.db import models
from app.domains import workflows


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _scoped(db: Session, model, user: models.User):
    return workflows.user_scope_query(db, model, user)


def readiness(db: Session, user: models.User) -> dict[str, Any]:
    memberships = db.query(models.WorkspaceMembership).filter_by(tenant_id=user.tenant_id, status="active").all()
    roles = {row.role for row in memberships}
    required_roles = {"plant_manager", "purchase_executive", "purchase_manager", "gate_operator", "store_manager", "quality_inspector", "admin"}
    checks = [
        ("plant", bool(db.get(models.Plant, user.plant_id)), "Plant configured", "/workspace/setup"),
        ("roles", required_roles <= roles, f"{len(required_roles & roles)}/{len(required_roles)} operating roles assigned", "/workspace/setup"),
        ("reporting", all(row.role == "admin" or row.manager_membership_id or row.role == "plant_manager" for row in memberships), "Reporting lines configured", "/workspace/setup"),
        ("materials", _scoped(db, models.Item, user).count() > 0, "Approved materials available", "/workspace/setup"),
        ("suppliers", _scoped(db, models.Supplier, user).count() > 0, "Suppliers configured", "/workspace/setup"),
        ("capabilities", _scoped(db, models.SupplierItemCapability, user).filter_by(approved=True).count() > 0, "Supplier-material capabilities configured", "/workspace/setup"),
        ("connection", _scoped(db, models.IntegrationConnection, user).filter(models.IntegrationConnection.mode != "disconnected").count() > 0, "External-system connection configured", "/integrations"),
        ("mapping", _scoped(db, models.IntegrationMappingProfile, user).filter_by(status="active").count() > 0, "Active import mapping profile available", "/integrations"),
        ("agents", db.query(models.AgentProfile).filter_by(tenant_id=user.tenant_id, enabled=True).count() > 0, "Role agents enabled", "/workspace/setup"),
        ("knowledge", _scoped(db, models.KnowledgeDocument, user).filter_by(approval_state="approved").count() > 0, "Approved SOP or policy available", "/workspace/setup"),
    ]
    items = [{"key": key, "ready": ready, "label": label, "evidence_href": href} for key, ready, label, href in checks]
    completed = sum(item["ready"] for item in items)
    return {"status": "ready" if completed == len(items) else "needs_configuration", "completed": completed, "total": len(items), "percent": round(completed / len(items) * 100), "checks": items}


def analytics(db: Session, user: models.User) -> dict[str, Any]:
    now = utcnow()
    requirements = _scoped(db, models.PurchaseRequirement, user).all()
    closed = [row for row in requirements if row.status == "closed"]
    cycle_hours = [
        max(
            0,
            (
                task_service.as_utc(row.updated_at)
                - task_service.as_utc(row.created_at)
            ).total_seconds() / 3600,
        )
        for row in closed
    ]
    tasks = _scoped(db, models.Task, user).all()
    active = [row for row in tasks if row.status in task_service.ACTIVE_TASK_STATES]
    blocked = [row for row in active if row.status == "blocked"]
    blocker_hours = [max(0, (now - task_service.as_utc(row.updated_at)).total_seconds() / 3600) for row in blocked]
    supplier_events = _scoped(db, models.SupplierPerformanceEvent, user).all()
    quality_numerator = sum(row.numerator for row in supplier_events if row.metric_type == "quality_acceptance")
    quality_denominator = sum(row.denominator for row in supplier_events if row.metric_type == "quality_acceptance")
    jobs = _scoped(db, models.IntegrationSyncJob, user).all()
    runs = db.query(models.AgentRun).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()
    feedback = _scoped(db, models.AgentFeedback, user).all()
    rated = [row.correctness for row in feedback if row.correctness is not None]
    metrics = [
        {"key": "requirement_cycle_time", "label": "Average closed requirement cycle", "value": round(sum(cycle_hours) / len(cycle_hours), 1) if cycle_hours else None, "unit": "hours", "sample_size": len(cycle_hours), "evidence_href": "/procurement"},
        {"key": "active_workload", "label": "Active work items", "value": len(active), "unit": "tasks", "sample_size": len(tasks), "evidence_href": "/control-centre"},
        {"key": "blocker_age", "label": "Oldest active blocker", "value": round(max(blocker_hours), 1) if blocker_hours else 0, "unit": "hours", "sample_size": len(blocked), "evidence_href": "/control-centre"},
        {"key": "supplier_quality_acceptance", "label": "Evidence-linked supplier quality acceptance", "value": round(quality_numerator / quality_denominator * 100, 2) if quality_denominator else None, "unit": "percent", "sample_size": len(supplier_events), "evidence_href": "/workspace/setup"},
        {"key": "integration_success", "label": "Integration job success", "value": round(sum(row.status == "completed" for row in jobs) / len(jobs) * 100, 2) if jobs else None, "unit": "percent", "sample_size": len(jobs), "evidence_href": "/integrations"},
        {"key": "agent_run_success", "label": "Agent run success", "value": round(sum(row.state == "completed" for row in runs) / len(runs) * 100, 2) if runs else None, "unit": "percent", "sample_size": len(runs), "evidence_href": "/audit"},
        {"key": "agent_correctness_feedback", "label": "Agent correctness feedback", "value": round(sum(rated) / len(rated), 2) if rated else None, "unit": "out_of_5", "sample_size": len(rated), "evidence_href": "/audit"},
        {"key": "savings", "label": "Validated savings", "value": None, "unit": "currency", "sample_size": 0, "evidence_href": "/comparison", "note": "Unavailable until a customer-approved baseline-price policy is configured"},
    ]
    return {"generated_at": now.isoformat(), "metrics": metrics, "opaque_employee_score": False}


def brief(db: Session, user: models.User, period: str) -> dict[str, Any]:
    own = [task_service.task_payload(db, row) for row in workflows.tasks_for_user(db, user) if row.status in task_service.ACTIVE_TASK_STATES]
    team = task_service.manager_summary(db, user)
    overdue = [row for row in [*own, *team] if row.get("is_overdue")]
    blocked = [row for row in [*own, *team] if row.get("status") == "blocked"]
    completed_today = _scoped(db, models.Task, user).filter(models.Task.status == "completed", models.Task.completed_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).all()
    return {
        "period": period, "generated_at": utcnow().isoformat(),
        "summary": f"{len(own)} active assignments, {len(overdue)} overdue items, {len(blocked)} blockers, and {len(completed_today)} completions today.",
        "priorities": own[:5], "overdue": overdue[:10], "blockers": blocked[:10],
        "completed_today": [task_service.task_payload(db, row) for row in completed_today[:10]],
        "sources": [{"type": "task", "id": row["id"], "href": f"/control-centre?task={row['id']}"} for row in [*own, *team][:20]],
        "employee_score": None,
    }


def configuration_export(db: Session, user: models.User) -> dict[str, Any]:
    tenant = db.get(models.Tenant, user.tenant_id)
    plant = db.get(models.Plant, user.plant_id)
    memberships = db.query(models.WorkspaceMembership).filter_by(tenant_id=user.tenant_id, status="active").all()
    connections = _scoped(db, models.IntegrationConnection, user).all()
    profiles = db.query(models.AgentProfile).filter_by(tenant_id=user.tenant_id).all()
    return {
        "schema_version": "1.0", "exported_at": utcnow().isoformat(),
        "workspace": {"id": tenant.id if tenant else None, "name": tenant.name if tenant else None},
        "plant": {"id": plant.id if plant else None, "name": plant.name if plant else None},
        "memberships": [{"membership_id": row.id, "role": row.role, "manager_membership_id": row.manager_membership_id, "status": row.status} for row in memberships],
        "connections": [{"id": row.id, "provider": row.provider, "mode": row.mode, "enabled_capabilities": row.enabled_capabilities, "writes_enabled": row.writes_enabled, "status": row.status} for row in connections],
        "agents": [{"membership_id": row.membership_id, "enabled": row.enabled, "provider": row.provider, "model_profile": row.model_profile, "policy_version": row.policy_version, "prompt_version": row.prompt_version} for row in profiles],
        "retention": {"thread_retention_configured": db.query(models.AgentThread).filter(models.AgentThread.tenant_id == user.tenant_id, models.AgentThread.retention_until.is_not(None)).count() > 0},
        "secrets_included": False,
    }
