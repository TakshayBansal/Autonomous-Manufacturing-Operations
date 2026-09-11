from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import agent_service, companion
from app.core.permissions import ADMIN
from app.core.security import current_user, require_csrf
from app.db import models
from app.db.session import SessionLocal, get_db
from app.feature_flags import enabled as feature_enabled
from app.core.metrics import COMPANION_ACTIONS

router = APIRouter(prefix="/agent/companion", tags=["companion"])
admin_router = APIRouter(prefix="/admin/companion-trigger-policies", tags=["companion-admin"])


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def _membership(db: Session, user: models.User) -> models.WorkspaceMembership:
    return agent_service.membership_for_user(db, user)


def _intervention(db: Session, user: models.User, intervention_id: str) -> models.CompanionIntervention:
    membership = _membership(db, user)
    row = db.query(models.CompanionIntervention).filter_by(
        id=intervention_id, tenant_id=user.tenant_id,
        recipient_membership_id=membership.id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Companion intervention not found")
    return row


@router.get("/state")
def companion_state(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    membership = _membership(db, user)
    if not feature_enabled(db, user.tenant_id, "proactive_companion"):
        preference = companion.preference_for(db, membership)
        return {"state": "offline", "unresolved_count": 0, "running_count": 0,
                "top_intervention": None, "interventions": [],
                "preferences": agent_service.record_dict(preference)}
    return companion.state(db, membership)


@router.get("/interventions")
def list_interventions(state: str | None = None, db: Session = Depends(get_db),
                       user: models.User = Depends(authenticated_user)):
    membership = _membership(db, user)
    query = db.query(models.CompanionIntervention).filter_by(
        tenant_id=user.tenant_id, recipient_membership_id=membership.id,
    )
    if state:
        query = query.filter_by(delivery_state=state)
    return [companion.serialize(row) for row in query.order_by(
        models.CompanionIntervention.created_at.desc(),
    ).limit(200).all()]


@router.get("/interventions/{intervention_id}")
def get_intervention(intervention_id: str, db: Session = Depends(get_db),
                     user: models.User = Depends(authenticated_user)):
    return companion.serialize(_intervention(db, user, intervention_id))


@router.post("/interventions/{intervention_id}/open", dependencies=[Depends(csrf_guard)])
def open_intervention(intervention_id: str, db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    row = _intervention(db, user, intervention_id)
    row.delivery_state = "opened"
    row.opened_at = datetime.now(timezone.utc)
    db.commit()
    return companion.serialize(row)


@router.post("/interventions/{intervention_id}/snooze", dependencies=[Depends(csrf_guard)])
def snooze_intervention(intervention_id: str, payload: dict[str, Any] = Body(default={}),
                        db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    row = _intervention(db, user, intervention_id)
    minutes = max(5, min(int(payload.get("minutes", 60)), 1440))
    if row.severity == "critical":
        minutes = min(minutes, 60)
    row.delivery_state = "snoozed"
    row.snoozed_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    db.commit()
    return companion.serialize(row)


@router.post("/interventions/{intervention_id}/dismiss", dependencies=[Depends(csrf_guard)])
def dismiss_intervention(intervention_id: str, payload: dict[str, Any] = Body(default={}),
                         db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    row = _intervention(db, user, intervention_id)
    reason = str(payload.get("reason") or "").strip()
    if row.severity in {"critical", "warning"} and not reason:
        raise HTTPException(status_code=422, detail="A reason is required to dismiss a high-risk intervention")
    row.delivery_state = "dismissed"
    row.selected_action = f"dismissed:{reason}" if reason else "dismissed"
    row.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return companion.serialize(row)


@router.post("/interventions/{intervention_id}/actions", dependencies=[Depends(csrf_guard)])
def choose_action(intervention_id: str, payload: dict[str, Any] = Body(...),
                  db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    row = _intervention(db, user, intervention_id)
    membership = _membership(db, user)
    action_id = str(payload.get("action_id") or "")
    mode = str(payload.get("execution_mode") or "")
    available = next((item for item in row.actions if item.get("id") == action_id and item.get("mode") == mode), None)
    if available is None:
        COMPANION_ACTIONS.labels(mode or "unknown", "denied").inc()
        raise HTTPException(status_code=403, detail="That action or execution mode is not available")
    if payload.get("resource_version") is not None and int(payload["resource_version"]) != row.aggregate_version:
        raise HTTPException(status_code=409, detail="The underlying record changed; refresh the companion item")
    if mode == "manual":
        COMPANION_ACTIONS.labels("manual", "opened").inc()
        row.delivery_state, row.selected_action, row.opened_at = "opened", action_id, datetime.now(timezone.utc)
        db.commit()
        return {"kind": "navigation", "href": available.get("href", "/control-centre"), "intervention": companion.serialize(row)}
    if mode == "explain":
        COMPANION_ACTIONS.labels("explain", "opened").inc()
        row.delivery_state, row.opened_at = "opened", datetime.now(timezone.utc)
        db.commit()
        return {"kind": "explanation", "title": row.title, "why_now": row.why_now,
                "evidence": row.evidence, "responsible_authority": row.responsible_authority}
    if mode == "prepare":
        if not feature_enabled(db, user.tenant_id, "async_specialists"):
            raise HTTPException(status_code=503, detail="AI preparation is not enabled; use the manual workflow")
        existing_run = db.get(models.AgentRun, row.run_id) if row.run_id else None
        if existing_run and existing_run.state in {"queued", "running"}:
            COMPANION_ACTIONS.labels("prepare", "already_running").inc()
            return {"kind": "run", "run_id": existing_run.id, "correlation_id": existing_run.correlation_id,
                    "state": existing_run.state, "already_running": True}
        specialist = action_id.removeprefix("prepare:")
        try:
            run = companion.start_preparation(db, membership, row, specialist)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        db.commit()
        from app.workers import run_specialist
        task = run_specialist.apply_async(args=[run.id], queue="specialists")
        COMPANION_ACTIONS.labels("prepare", "queued").inc()
        return {"kind": "run", "run_id": run.id, "celery_task_id": task.id,
                "correlation_id": run.correlation_id, "state": run.state}
    raise HTTPException(status_code=403, detail="Automatic execution is not enabled for this intervention")


@router.post("/interventions/{intervention_id}/cancel", dependencies=[Depends(csrf_guard)])
def cancel_action(intervention_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(authenticated_user)):
    row = _intervention(db, user, intervention_id)
    run = db.get(models.AgentRun, row.run_id) if row.run_id else None
    if run and run.membership_id == row.recipient_membership_id and run.state in {"queued", "running"}:
        run.cancellation_requested = True
        run.state = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
    row.delivery_state = "opened"
    db.commit()
    return {"state": run.state if run else "not_running", "intervention": companion.serialize(row)}


@router.get("/preferences")
def get_preferences(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return agent_service.record_dict(companion.preference_for(db, _membership(db, user)))


@router.put("/preferences", dependencies=[Depends(csrf_guard)])
def update_preferences(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                       user: models.User = Depends(authenticated_user)):
    row = companion.preference_for(db, _membership(db, user))
    enums = {
        "proactive_level": {"risk_tiered", "mostly_silent", "muted"},
        "animation_mode": {"system", "full", "reduced"},
        "default_execution_mode": {"manual", "prepare"},
    }
    for field, allowed in enums.items():
        if field in payload:
            if payload[field] not in allowed:
                raise HTTPException(status_code=422, detail=f"Invalid {field}")
            setattr(row, field, payload[field])
    for field in ("login_briefing_enabled", "sound_enabled", "background_preparation_enabled"):
        if field in payload:
            setattr(row, field, bool(payload[field]))
    if "quiet_hours" in payload:
        row.quiet_hours = dict(payload["quiet_hours"] or {})
    if "category_preferences" in payload:
        row.category_preferences = dict(payload["category_preferences"] or {})
    db.commit()
    return agent_service.record_dict(row)


@router.get("/stream")
def stream(last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
           db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    membership = _membership(db, user)
    membership_id, tenant_id = membership.id, membership.tenant_id

    def events():
        sequence = 0
        yield f"id: {sequence}\nevent: companion.state\ndata: {json.dumps({'refresh': True, 'resume_from': last_event_id})}\n\n"
        try:
            import redis
            from app.core.config import get_settings
            client = redis.Redis.from_url(get_settings().redis_url)
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(f"companion:{membership_id}")
            while True:
                message = pubsub.get_message(timeout=15)
                sequence += 1
                if message:
                    payload = message["data"].decode() if isinstance(message["data"], bytes) else str(message["data"])
                    yield f"id: {sequence}\nevent: companion.update\ndata: {payload}\n\n"
                else:
                    with SessionLocal() as stream_db:
                        count = stream_db.query(models.CompanionIntervention).filter(
                            models.CompanionIntervention.tenant_id == tenant_id,
                            models.CompanionIntervention.recipient_membership_id == membership_id,
                            models.CompanionIntervention.delivery_state.in_(companion.OPEN_STATES),
                        ).count()
                    yield f"id: {sequence}\nevent: companion.counts\ndata: {json.dumps({'unresolved_count': count})}\n\n"
        except GeneratorExit:
            return
        except Exception:
            while True:
                time.sleep(10)
                sequence += 1
                yield f"id: {sequence}\nevent: companion.state\ndata: {json.dumps({'refresh': True})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _admin(user: models.User) -> None:
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Admin authority is required")


@admin_router.get("")
def policies(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _admin(user)
    return [agent_service.record_dict(row) for row in db.query(models.CompanionTriggerPolicy).filter_by(
        tenant_id=user.tenant_id,
    ).order_by(models.CompanionTriggerPolicy.updated_at.desc()).all()]


@admin_router.put("/{policy_id}", dependencies=[Depends(csrf_guard)])
def save_policy(policy_id: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                user: models.User = Depends(authenticated_user)):
    _admin(user)
    row = db.query(models.CompanionTriggerPolicy).filter_by(id=policy_id, tenant_id=user.tenant_id).first()
    if row is None:
        row = models.CompanionTriggerPolicy(id=policy_id, tenant_id=user.tenant_id, plant_id=user.plant_id,
            name=str(payload.get("name") or "Companion trigger"), trigger_type=str(payload.get("trigger_type") or "cycle.stage_changed"))
        db.add(row)
    for field in ("name", "trigger_type", "minimum_severity", "specialist_name", "delivery_mode"):
        if field in payload:
            setattr(row, field, payload[field])
    for field in ("roles", "plant_ids", "category_ids"):
        if field in payload:
            setattr(row, field, list(payload[field] or []))
    for field in ("autonomy_ceiling", "cooldown_seconds", "expiry_seconds"):
        if field in payload:
            setattr(row, field, int(payload[field]))
    if "preparation_allowed" in payload:
        row.preparation_allowed = bool(payload["preparation_allowed"])
    row.state = "draft"
    db.commit()
    return agent_service.record_dict(row)


@admin_router.post("/{policy_id}/publish", dependencies=[Depends(csrf_guard)])
def publish_policy(policy_id: str, db: Session = Depends(get_db),
                   user: models.User = Depends(authenticated_user)):
    _admin(user)
    row = db.query(models.CompanionTriggerPolicy).filter_by(id=policy_id, tenant_id=user.tenant_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Trigger policy not found")
    row.state = "published"
    row.policy_version = f"companion-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    db.commit()
    return agent_service.record_dict(row)


@admin_router.post("/simulate", dependencies=[Depends(csrf_guard)])
def simulate_policy(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db),
                    user: models.User = Depends(authenticated_user)):
    _admin(user)
    trigger = str(payload.get("trigger_type") or "cycle.stage_changed")
    role = str(payload.get("role") or "purchase_executive")
    matching = db.query(models.CompanionTriggerPolicy).filter_by(
        tenant_id=user.tenant_id, trigger_type=trigger, state="published",
    ).all()
    matched = [row for row in matching if not row.roles or role in row.roles]
    return {"matched": bool(matched), "trigger_type": trigger, "role": role,
            "delivery_mode": matched[0].delivery_mode if matched else "risk_tiered",
            "background_preparation": bool(matched and matched[0].preparation_allowed),
            "specialist": matched[0].specialist_name if matched else None,
            "policy_version": matched[0].policy_version if matched else "default"}
