from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models
from app.db.session import get_db
from app.core.metrics import OVERDUE_TASKS
from app.storage import object_storage


router = APIRouter(tags=["health"])


def migration_head() -> str:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "genuinegigs-api",
        "ai_provider": settings.ai_provider,
        "external_actions": settings.erp_write_mode,
        "email_actions": settings.smtp_mode,
    }


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
def health_ready(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    checks = {
        "database": False, "migration": False, "object_storage": False,
        "redis": False, "agent_provider": False, "document_tasks_registered": False,
    }
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        checks["migration"] = revision == migration_head()
    except Exception:
        pass
    checks["object_storage"] = object_storage.healthcheck()
    try:
        from redis import Redis

        checks["redis"] = bool(Redis.from_url(settings.redis_url, socket_timeout=0.25).ping())
    except Exception:
        checks["redis"] = settings.app_env in {"test", "development"}
    checks["agent_provider"] = (
        settings.ai_provider == "disabled"
        or bool(settings.groq_api_key)
    )
    try:
        from app.workers import REQUIRED_TASKS
        from app.celery_app import celery_app
        checks["document_tasks_registered"] = REQUIRED_TASKS.issubset(celery_app.tasks)
    except Exception:
        checks["document_tasks_registered"] = False
    if settings.app_env == "production" and settings.erp_write_mode == "live":
        checks["live_configuration"] = bool(
            settings.erp_live_enabled
            and settings.oracle_base_url
            and settings.oracle_token_url
            and settings.oracle_client_id
            and settings.oracle_client_secret
        )
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@router.get("/metrics", include_in_schema=False)
def metrics(db: Session = Depends(get_db)) -> Response:
    now = datetime.now(timezone.utc)
    rows = db.query(models.Task.tenant_id, models.Task.plant_id).filter(
        models.Task.status.in_(["open", "pending_approval"]),
        models.Task.due_at.is_not(None),
        models.Task.due_at < now,
    ).all()
    counts: dict[tuple[str, str], int] = {}
    for tenant_id, plant_id in rows:
        key = (tenant_id, plant_id or "unassigned")
        counts[key] = counts.get(key, 0) + 1
    for (tenant_id, plant_id), count in counts.items():
        OVERDUE_TASKS.labels(tenant_id, plant_id).set(count)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
