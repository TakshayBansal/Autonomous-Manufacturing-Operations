from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import current_user, require_csrf
from app.db import models
from app.db.session import get_db
from app.intelligence.context import ContextEngine
from app.intelligence.runtime import GigiRuntime
from app.intelligence.schemas import ActionProposalRequest, ConversationCreate, FeedbackRequest, GigiMessageRequest
from app.intelligence.services import create_case_commitment, generate_briefing, propose_action, refresh_case_insights, search_knowledge
from app.platform.case_models import GigiInsight

router = APIRouter(prefix="/api/v1/gigi", tags=["gigi"])


def auth(request: Request, db: Session = Depends(get_db)) -> models.User:
    return current_user(db, request)


def csrf(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def _membership(db: Session, user: models.User) -> models.WorkspaceMembership:
    row = db.query(models.WorkspaceMembership).filter_by(tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    if not row:
        raise HTTPException(403, "Active workspace membership required")
    return row


def _thread(db: Session, user: models.User, thread_id: str) -> models.AgentThread:
    row = db.query(models.AgentThread).filter_by(id=thread_id, tenant_id=user.tenant_id,
        membership_id=_membership(db, user).id).first()
    if not row:
        raise HTTPException(404, "Conversation not found")
    return row


def _thread_payload(row: models.AgentThread) -> dict:
    return {"id": row.id, "title": row.title, "status": row.status, "module_context": row.module_context,
            "context": row.context_state, "created_at": row.created_at, "updated_at": row.updated_at}


def _insight(row: GigiInsight) -> dict:
    return {"id": row.id, "case_id": row.case_id, "category": row.category, "severity": row.severity,
        "title": row.title, "summary": row.summary, "evidence": row.evidence,
        "delivery_state": row.delivery_state, "acknowledged_at": row.acknowledged_at,
        "dismissed_at": row.dismissed_at, "snoozed_until": row.snoozed_until,
        "next_evaluation_at": row.next_evaluation_at, "escalation_state": row.escalation_state}


@router.get("/insights")
def insights(db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    member = _membership(db, user); refresh_case_insights(db, user=user, membership_id=member.id); db.commit()
    rows = db.query(GigiInsight).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id,
        membership_id=member.id).filter(GigiInsight.dismissed_at.is_(None)).order_by(GigiInsight.created_at.desc()).limit(100).all()
    return [_insight(row) for row in rows]


@router.get("/brief")
def current_brief(db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    now = datetime.now(timezone.utc); member = _membership(db, user)
    row = generate_briefing(db, user=user, membership_id=member.id, briefing_type="morning", period_key=now.date().isoformat())
    db.commit(); return {"id": row.id, "title": row.title, "items": row.items, "evidence": row.evidence, "generated_at": row.generated_at}


@router.post("/insights/{insight_id}/{command}", dependencies=[Depends(csrf)])
def update_insight(insight_id: str, command: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    if command not in {"acknowledge", "snooze", "dismiss"}: raise HTTPException(422, "Unsupported insight command")
    row = db.query(GigiInsight).filter_by(id=insight_id, tenant_id=user.tenant_id,
        plant_id=user.plant_id, membership_id=_membership(db, user).id).first()
    if not row: raise HTTPException(404, "Insight not found")
    now = datetime.now(timezone.utc)
    if command == "acknowledge": row.acknowledged_at = now; row.delivery_state = "ACKNOWLEDGED"
    elif command == "dismiss": row.dismissed_at = now; row.delivery_state = "DISMISSED"
    else: row.snoozed_until = now + timedelta(hours=2); row.delivery_state = "SNOOZED"
    db.commit(); return _insight(row)


class CommitmentRequest(BaseModel):
    case_id: str
    due_at: datetime
    deliverable: str = Field(min_length=3, max_length=1000)
    entity_type: str | None = None
    entity_id: str | None = None


@router.post("/commitments", dependencies=[Depends(csrf)])
def create_commitment(payload: CommitmentRequest, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    member = _membership(db, user)
    try: row = create_case_commitment(db, user=user, membership_id=member.id, **payload.model_dump())
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
    db.commit(); return {"id": row.id, "case_id": row.operational_case_id, "deliverable": row.deliverable,
        "due_at": row.promised_at, "status": row.status, "dependency_state": row.dependency_state}


@router.get("/commitments")
def commitments(db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    rows = db.query(models.Commitment).filter_by(tenant_id=user.tenant_id,
        owner_membership_id=_membership(db, user).id).order_by(models.Commitment.promised_at).all()
    return [{"id": row.id, "case_id": row.operational_case_id, "deliverable": row.deliverable,
        "due_at": row.promised_at, "status": row.status, "dependency_state": row.dependency_state,
        "evidence_requirement": row.evidence_requirement} for row in rows]


@router.post("/cases/{case_id}/investigate", dependencies=[Depends(csrf)])
def investigate_case(case_id: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    from app.platform.models import OperationalCase
    from app.platform.case_service import case_detail
    case = db.query(OperationalCase).filter_by(id=case_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not case: raise HTTPException(404, "Case not found")
    detail = case_detail(db, case)
    return {"case_id": case.id, "understood_problem": case.summary or case.title,
        "causes": detail["causes"], "affected_entities": detail["entities"],
        "exposures": detail["exposures"], "missing_information": [],
        "evidence": [{"ref": f"case:{case.id}", "classification": "DETERMINISTIC_CASE_CONTEXT"}],
        "numeric_source": "shared deterministic services"}


@router.post("/cases/{case_id}/plan", dependencies=[Depends(csrf)])
def plan_case(case_id: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    from app.platform.models import OperationalCase
    from app.platform.case_service import case_detail
    case = db.query(OperationalCase).filter_by(id=case_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not case: raise HTTPException(404, "Case not found")
    detail = case_detail(db, case); decision = detail.get("decision") or {}
    alternatives = decision.get("alternatives", [])
    recommended = next((row for row in alternatives if row["id"] == decision.get("recommended_alternative_id")), None)
    return {"case_id": case.id, "understood_problem": case.summary or case.title,
        "strategies_evaluated": alternatives, "recommended_plan": recommended,
        "approval_required": True, "action_plan": detail.get("action_plan"),
        "guardrails": ["Gigi cannot approve", "Gigi cannot execute external changes", "Stale facts require revalidation"]}


@router.post("/conversations", dependencies=[Depends(csrf)])
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    member = _membership(db, user)
    ContextEngine(db).build(user, payload.page_context)
    profile = GigiRuntime(db).ensure_profile(user, member.id)
    row = models.AgentThread(tenant_id=user.tenant_id, plant_id=user.plant_id, membership_id=member.id,
        agent_profile_id=profile.id, thread_type="gigi", title=payload.title or "New Gigi conversation",
        participant_membership_ids=[member.id], context_state=payload.page_context.model_dump(mode="json"),
        context_schema_version=1, status="active", module_context=payload.page_context.module,
        conversation_metadata={"created_from": payload.page_context.route})
    db.add(row); db.commit(); db.refresh(row)
    return _thread_payload(row)


@router.get("/conversations")
def conversations(db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    member = _membership(db, user)
    rows = db.query(models.AgentThread).filter_by(tenant_id=user.tenant_id, membership_id=member.id,
        thread_type="gigi").order_by(models.AgentThread.updated_at.desc()).limit(100).all()
    return [_thread_payload(row) for row in rows]


@router.get("/conversations/{thread_id}")
def conversation(thread_id: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    return _thread_payload(_thread(db, user, thread_id))


@router.get("/conversations/{thread_id}/messages")
def messages(thread_id: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    thread = _thread(db, user, thread_id)
    rows = db.query(models.AgentMessage).filter_by(tenant_id=user.tenant_id, thread_id=thread.id).order_by(models.AgentMessage.created_at).all()
    return [{"id": row.id, "type": row.message_type, "content": row.content, "blocks": row.content_blocks,
             "citations": row.citations, "run_id": row.run_id, "created_at": row.created_at} for row in rows]


@router.post("/conversations/{thread_id}/messages", dependencies=[Depends(csrf)])
def send_message(thread_id: str, payload: GigiMessageRequest, db: Session = Depends(get_db),
                 user: models.User = Depends(auth)) -> dict:
    thread = _thread(db, user, thread_id)
    member = _membership(db, user)
    if payload.idempotency_key:
        existing = db.query(models.AgentMessage).filter_by(tenant_id=user.tenant_id, thread_id=thread.id,
            message_type="user", business_number=payload.idempotency_key).first()
        if existing and existing.run_id:
            run = db.get(models.AgentRun, existing.run_id)
            return {"message_id": existing.id, "run_id": existing.run_id,
                    "response": run.result_summary if run else {}, "idempotent_replay": True}
    correlation_id = str(uuid4())
    question = models.AgentMessage(tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        membership_id=member.id, agent_profile_id=thread.agent_profile_id, message_type="user",
        content=payload.content, content_format="markdown", correlation_id=correlation_id,
        business_number=payload.idempotency_key)
    db.add(question); db.flush()
    run, response = GigiRuntime(db).run(user=user, thread=thread, question=payload.content,
        page=payload.page_context, correlation_id=correlation_id)
    question.run_id = run.id
    answer = models.AgentMessage(tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        membership_id=member.id, agent_profile_id=thread.agent_profile_id, message_type="assistant",
        content=response.answer, content_format="markdown", content_blocks=response.model_dump(mode="json").get("recommendations", []),
        citations=[item.model_dump(mode="json") for item in response.evidence], correlation_id=correlation_id, run_id=run.id)
    db.add(answer); thread.context_state = payload.page_context.model_dump(mode="json")
    if thread.title == "New Gigi conversation": thread.title = payload.content[:80]
    db.commit()
    return {"message_id": answer.id, "run_id": run.id, "response": response.model_dump(mode="json"), "idempotent_replay": False}


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    run = db.query(models.AgentRun).filter_by(id=run_id, tenant_id=user.tenant_id, membership_id=_membership(db, user).id).first()
    if not run: raise HTTPException(404, "Run not found")
    return {"id": run.id, "state": run.state, "role_profile": run.role_profile, "provider": run.provider,
        "model": run.model, "prompt_version": run.prompt_version, "usage": {"input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens, "cost_micros": run.cost_micros}, "latency_ms": run.latency_ms,
        "result": run.result_summary, "correlation_id": run.correlation_id}


@router.get("/runs/{run_id}/events")
def run_events(run_id: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    run = db.query(models.AgentRun).filter_by(id=run_id, tenant_id=user.tenant_id, membership_id=_membership(db, user).id).first()
    if not run: raise HTTPException(404, "Run not found")
    rows = db.query(models.AgentEvent).filter_by(run_id=run.id).order_by(models.AgentEvent.sequence).all()
    return [{"sequence": row.sequence, "type": row.event_type, "payload": row.payload, "created_at": row.created_at} for row in rows]


@router.get("/runs/{run_id}/stream")
def stream_events(run_id: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> StreamingResponse:
    events = run_events(run_id, db, user)
    def generate():
        for event in events:
            yield f"id: {event['sequence']}\nevent: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/runs/{run_id}/actions", dependencies=[Depends(csrf)])
def action(run_id: str, payload: ActionProposalRequest, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    run = db.query(models.AgentRun).filter_by(id=run_id, tenant_id=user.tenant_id, membership_id=_membership(db, user).id).first()
    if not run: raise HTTPException(404, "Run not found")
    intent = propose_action(db, user=user, membership_id=run.membership_id, candidate=payload.action,
        idempotency_key=payload.idempotency_key, correlation_id=run.correlation_id,
        originating_case_id=payload.originating_case_id)
    db.commit()
    return {"id": intent.id, "status": intent.status, "action_type": intent.action_type,
            "requires_approval": intent.status == "awaiting_approval", "correlation_id": intent.correlation_id}


@router.get("/knowledge/search")
def knowledge_search(q: str, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    return search_knowledge(db, user=user, query=q)


@router.post("/runs/{run_id}/feedback", dependencies=[Depends(csrf)])
def feedback(run_id: str, payload: FeedbackRequest, db: Session = Depends(get_db), user: models.User = Depends(auth)) -> dict:
    member = _membership(db, user)
    run = db.query(models.AgentRun).filter_by(id=run_id, tenant_id=user.tenant_id, membership_id=member.id).first()
    if not run: raise HTTPException(404, "Run not found")
    row = models.AgentFeedback(tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
        membership_id=member.id, helpfulness=payload.helpfulness, correctness=payload.correctness,
        citation_quality=payload.citation_quality, rejected=payload.rejected, comment=payload.comment,
        feedback_type="response")
    db.add(row); db.commit()
    return {"id": row.id, "recorded": True}


@router.get("/investigations")
def investigations(db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    rows = db.query(models.AIInvestigation).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).order_by(
        models.AIInvestigation.created_at.desc()).limit(100).all()
    return [{"id": row.id, "trigger_type": row.trigger_type, "entity_type": row.entity_type,
        "entity_id": row.entity_id, "severity": row.severity, "status": row.status,
        "findings": row.findings, "evidence": row.evidence, "correlation_id": row.correlation_id} for row in rows]


@router.post("/briefings/{briefing_type}", dependencies=[Depends(csrf)])
def briefing(briefing_type: str, period_key: str, db: Session = Depends(get_db),
             user: models.User = Depends(auth)) -> dict:
    if briefing_type not in {"morning", "end_of_day", "weekly", "shift_handoff"}:
        raise HTTPException(422, "Unsupported briefing type")
    row = generate_briefing(db, user=user, membership_id=_membership(db, user).id,
                            briefing_type=briefing_type, period_key=period_key)
    db.commit()
    return {"id": row.id, "type": row.briefing_type, "period_key": row.period_key,
            "title": row.title, "items": row.items, "evidence": row.evidence, "generated_at": row.generated_at}


@router.get("/briefings")
def briefings(db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    member = _membership(db, user)
    rows = db.query(models.AIBriefing).filter_by(tenant_id=user.tenant_id, membership_id=member.id).order_by(
        models.AIBriefing.generated_at.desc()).limit(100).all()
    return [{"id": row.id, "type": row.briefing_type, "period_key": row.period_key, "title": row.title,
             "items": row.items, "generated_at": row.generated_at, "viewed_at": row.viewed_at} for row in rows]


@router.get("/experiences")
def experiences(entity_type: str | None = None, entity_id: str | None = None,
                db: Session = Depends(get_db), user: models.User = Depends(auth)) -> list[dict]:
    query = db.query(models.AgentExperience).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id)
    if entity_type: query = query.filter_by(entity_type=entity_type)
    if entity_id: query = query.filter_by(entity_id=entity_id)
    rows = query.order_by(models.AgentExperience.verified_at.desc()).limit(50).all()
    return [{"id": row.id, "domain": row.domain, "problem_type": row.problem_type,
        "selected_strategy": row.selected_strategy, "predicted_outcome": row.predicted_outcome,
        "actual_outcome": row.actual_outcome, "effectiveness": row.effectiveness,
        "evidence": row.evidence, "verified_at": row.verified_at} for row in rows]
