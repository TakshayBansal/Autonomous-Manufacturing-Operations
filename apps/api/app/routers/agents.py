import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import agent_service
from app.agent_capabilities import capabilities_for_role
from app.agent_schemas import (
    AgentFeedbackRequest,
    AgentMessageRequest,
    AttachmentResolutionRequest,
    AgentPolicyUpdateRequest,
    DelegationCreateRequest,
    DelegationResponseRequest,
    KnowledgeCreateRequest,
    KnowledgeDecisionRequest,
    ObjectiveCreateRequest,
    ObjectiveUpdateRequest,
    ProposalCreateRequest,
    ProposalDecisionRequest,
    ThreadCreateRequest,
    TaskCreateRequest,
    TaskFollowUpRequest,
    TaskTransitionRequest,
    WorkspaceCreateRequest,
    WorkspaceAgentPolicyRequest,
    WorkspaceSelectRequest,
)
from app.core.config import get_settings
from app.core.permissions import (
    ADMIN, PLANT_MANAGER, require_role, require_workspace_capability, workspace_capabilities,
)
from app.core.security import current_session, current_user, require_csrf, select_membership
from app.db import models
from app.db.session import get_db
from app.domains import workflows
from app import task_service


router = APIRouter()


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def rows(records: list[Any]) -> list[dict[str, Any]]:
    return [agent_service.record_dict(item) for item in records]


def message_payload(db: Session, message: models.AgentMessage) -> dict[str, Any]:
    payload = agent_service.record_dict(message)
    attachments = db.query(models.AgentMessageAttachment).filter_by(
        message_id=message.id, tenant_id=message.tenant_id,
    ).order_by(models.AgentMessageAttachment.file_order.asc()).all()
    payload["attachments"] = [{
        **agent_service.record_dict(item),
        "filename": getattr(db.get(models.Document, item.document_id), "filename", "Attachment"),
        "extraction_id": getattr(
            db.query(models.QuoteExtractionRun).filter_by(
                document_id=item.document_id,
            ).order_by(models.QuoteExtractionRun.created_at.desc()).first(),
            "id", None,
        ),
        "quotation_reference": (
            agent_service.record_dict(db.get(models.SupplierQuote, item.linked_quotation_id))
            if item.linked_quotation_id and db.get(models.SupplierQuote, item.linked_quotation_id)
            else None
        ),
        "authorized_next_actions": [
            *([{"id": "confirm_mapping"}] if item.status == "needs_mapping" else []),
            *([{"id": "retry"}] if item.status == "failed" else []),
            *([{"id": "review_extraction"}] if item.status in {"needs_review", "linked"} else []),
        ],
    } for item in attachments]
    return payload


@router.get("/workspaces")
def list_workspaces(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    session = current_session(db, request)
    memberships = db.query(models.WorkspaceMembership).filter_by(
        account_id=session.account_id, status="active"
    ).all()
    result = []
    for membership in memberships:
        tenant = db.get(models.Tenant, membership.tenant_id)
        plant = db.get(models.Plant, membership.default_plant_id)
        result.append({
            "membership_id": membership.id,
            "tenant_id": membership.tenant_id,
            "workspace_name": tenant.name if tenant else "Unavailable workspace",
            "workspace_kind": tenant.workspace_kind if tenant else "unknown",
            "onboarding_status": tenant.onboarding_status if tenant else "unknown",
            "agent_enabled": bool(tenant and tenant.agent_enabled),
            "deployment_agent_available": get_settings().agent_enabled,
            "agent_unavailable_reason": None if get_settings().agent_enabled else "The deployment model provider is not configured.",
            "plant_name": plant.name if plant else "Unavailable plant",
            "role": membership.role,
            "selected": membership.id == session.membership_id,
        })
    return result


@router.post("/workspaces", dependencies=[Depends(csrf_guard)])
def create_workspace(
    payload: WorkspaceCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_role(user, ADMIN)
    tenant, membership = agent_service.create_fresh_workspace(db, user, payload)
    db.commit()
    return {"workspace": agent_service.record_dict(tenant), "membership": agent_service.record_dict(membership)}


@router.get("/admin/workspace/agent-policy")
def workspace_agent_policy(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_workspace_capability(db, user, 'workspace.manage_agents')
    tenant = db.get(models.Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {
        "enabled": tenant.agent_enabled,
        "deployment_available": get_settings().agent_enabled,
        "normal_workflows_available": True,
    }


@router.patch("/admin/workspace/agent-policy", dependencies=[Depends(csrf_guard)])
def set_workspace_agent_policy(
    payload: WorkspaceAgentPolicyRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_workspace_capability(db, user, 'workspace.manage_agents')
    if payload.enabled and not get_settings().agent_enabled:
        raise HTTPException(status_code=409, detail="Agents are unavailable until the deployment model provider is configured")
    tenant = db.get(models.Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    tenant.agent_enabled = payload.enabled
    flags = dict(tenant.feature_flags or {})
    for key in ("role_agents", "knowledge", "multi_agent_delegation"):
        flags[key] = payload.enabled
        flag = db.query(models.TenantFeatureFlag).filter_by(
            tenant_id=user.tenant_id, key=key
        ).first()
        if flag is None:
            db.add(models.TenantFeatureFlag(
                tenant_id=user.tenant_id, key=key, enabled=payload.enabled,
                updated_by_membership_id=agent_service.membership_for_user(db, user).id,
            ))
        else:
            flag.enabled = payload.enabled
    tenant.feature_flags = flags
    db.query(models.AgentProfile).filter_by(tenant_id=user.tenant_id).update(
        {models.AgentProfile.enabled: payload.enabled}, synchronize_session=False
    )
    cancelled = 0
    if not payload.enabled:
        cancelled = db.query(models.AgentRun).filter(
            models.AgentRun.tenant_id == user.tenant_id,
            models.AgentRun.state.in_(["queued", "running"]),
        ).update({
            models.AgentRun.state: "cancelled",
            models.AgentRun.cancellation_requested: True,
            models.AgentRun.completed_at: datetime.now(timezone.utc),
        }, synchronize_session=False)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "agent.workspace_policy.updated",
        "tenant", user.tenant_id, actor_user_id=user.id,
        meta={"enabled": payload.enabled, "cancelled_runs": cancelled},
    )
    db.commit()
    return {"enabled": payload.enabled, "cancelled_runs": cancelled, "normal_workflows_available": True}


@router.post("/workspaces/select", dependencies=[Depends(csrf_guard)])
def switch_workspace(
    payload: WorkspaceSelectRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    selected = select_membership(db, request, payload.membership_id)
    session = current_session(db, request)
    workflows.create_audit(
        db, selected.tenant_id, selected.plant_id, selected.name,
        "workspace.selected", "workspace_membership", payload.membership_id,
        actor_user_id=selected.id,
    )
    db.commit()
    return {
        'user': {
            'id': selected.id, 'name': selected.name, 'email': selected.email,
            'role': selected.role, 'tenant_id': selected.tenant_id, 'plant_id': selected.plant_id,
            'membership_id': session.membership_id,
            'capabilities': workspace_capabilities(db, selected),
        },
        "csrf_token": session.csrf_token,
        "membership_id": session.membership_id,
    }


@router.get("/objectives")
def list_objectives(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    visible = {membership.id, *agent_service.reporting_descendants(db, membership)}
    return rows(db.query(models.Objective).filter(
        models.Objective.tenant_id == user.tenant_id,
        models.Objective.plant_id == user.plant_id,
        models.Objective.owner_membership_id.in_(visible),
    ).order_by(models.Objective.created_at.desc()).all())


@router.post("/objectives", dependencies=[Depends(csrf_guard)])
def create_objective(
    payload: ObjectiveCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    raise HTTPException(
        status_code=410,
        detail='Procurement objectives were retired. Create the canonical record at /procurement/requirements.',
    )
    objective = agent_service.create_objective(db, user, payload)
    db.commit()
    return agent_service.record_dict(objective)


@router.get("/objectives/{objective_id}")
def get_objective(
    objective_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    objective = db.query(models.Objective).filter_by(
        id=objective_id, tenant_id=user.tenant_id, plant_id=user.plant_id
    ).first()
    visible = {membership.id, *agent_service.reporting_descendants(db, membership)}
    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")
    assigned = db.query(models.Task).filter_by(
        objective_id=objective.id, owner_membership_id=membership.id
    ).first()
    if objective.owner_membership_id not in visible and assigned is None:
        raise HTTPException(status_code=403, detail="Objective access denied")
    return agent_service.record_dict(objective)


@router.patch("/objectives/{objective_id}", dependencies=[Depends(csrf_guard)])
def update_objective(
    objective_id: str,
    payload: ObjectiveUpdateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    objective = db.query(models.Objective).filter_by(
        id=objective_id, tenant_id=user.tenant_id, plant_id=user.plant_id,
        owner_membership_id=membership.id,
    ).first()
    if objective is None:
        raise HTTPException(status_code=404, detail="Owned objective not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(objective, key, value)
    db.commit()
    return agent_service.record_dict(objective)


@router.get("/agent/home")
def agent_home(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    profile = agent_service.profile_for_membership(db, membership)
    profile_payload = agent_service.record_dict(profile)
    profile_payload['allowed_actions'] = [
        capability.capability_id for capability in capabilities_for_role(membership.role)
    ]
    tenant = db.get(models.Tenant, user.tenant_id)
    threads = db.query(models.AgentThread).filter_by(
        tenant_id=user.tenant_id, membership_id=membership.id, status='active',
    ).order_by(models.AgentThread.updated_at.desc()).limit(8).all()
    titles_updated = [agent_service.ensure_thread_title(db, thread) for thread in threads]
    if any(titles_updated):
        db.commit()
    runs = db.query(models.AgentRun).filter_by(
        tenant_id=user.tenant_id, membership_id=membership.id
    ).order_by(models.AgentRun.created_at.desc()).limit(8).all()
    proposals = db.query(models.AgentProposal).filter_by(
        tenant_id=user.tenant_id, owner_membership_id=membership.id,
        confirmation_state="pending",
    ).all()
    delegations = db.query(models.AgentDelegation).filter(
        models.AgentDelegation.tenant_id == user.tenant_id,
        models.AgentDelegation.recipient_membership_id == membership.id,
        models.AgentDelegation.status.in_(["pending", "accepted", "in_progress", "clarification_requested"]),
    ).all()
    tasks = workflows.tasks_for_user(db, user)
    run_ids = [run.id for run in runs]
    receipts = db.query(models.AgentActionReceipt).filter(
        models.AgentActionReceipt.tenant_id == user.tenant_id,
        models.AgentActionReceipt.run_id.in_(run_ids or ['']),
    ).order_by(models.AgentActionReceipt.created_at.desc()).limit(20).all()
    recent_events = db.query(models.AgentEvent).filter(
        models.AgentEvent.tenant_id == user.tenant_id,
        models.AgentEvent.run_id.in_(run_ids or ['']),
    ).order_by(models.AgentEvent.created_at.desc()).limit(40).all()
    return {
        "enabled": bool(get_settings().agent_enabled and tenant and tenant.agent_enabled and profile.enabled),
        'provider_mode': (
            'groq' if profile.provider == 'groq' and bool(get_settings().groq_api_key)
            else 'limited'
        ),
        "profile": profile_payload,
        "queue": rows([item for item in tasks if item.status in {"open", "pending_approval"}]),
        "threads": rows(threads),
        "runs": rows(runs),
        "proposals": rows(proposals),
        "delegations": rows(delegations),
        "receipts": rows(receipts),
        "recent_events": rows(recent_events),
    }


@router.get("/agent/threads")
def list_threads(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    threads = db.query(models.AgentThread).filter_by(
        tenant_id=user.tenant_id, membership_id=membership.id, status='active',
    ).order_by(models.AgentThread.updated_at.desc()).all()
    titles_updated = [agent_service.ensure_thread_title(db, thread) for thread in threads]
    if any(titles_updated):
        db.commit()
    return rows(threads)


@router.post("/agent/threads", dependencies=[Depends(csrf_guard)])
def create_thread(
    payload: ThreadCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    thread = agent_service.create_thread(db, user, payload)
    db.commit()
    return agent_service.record_dict(thread)


@router.delete("/agent/threads/{thread_id}", dependencies=[Depends(csrf_guard)], status_code=204)
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    thread = agent_service.thread_for_membership(db, membership, thread_id)
    thread.status = 'deleted'
    db.query(models.AgentRun).filter(
        models.AgentRun.thread_id == thread.id,
        models.AgentRun.state.in_(['running', 'waiting_on_documents', 'paused_provider']),
    ).update({models.AgentRun.cancellation_requested: True}, synchronize_session=False)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, 'agent.thread.deleted',
        'agent_thread', thread.id, actor_user_id=user.id,
        meta={'membership_id': membership.id},
    )
    db.commit()
    return None


@router.get("/agent/threads/{thread_id}")
def get_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    thread = agent_service.thread_for_membership(db, membership, thread_id)
    messages = db.query(models.AgentMessage).filter_by(
        tenant_id=user.tenant_id, thread_id=thread.id, membership_id=membership.id
    ).order_by(models.AgentMessage.created_at.asc()).all()
    return {"thread": agent_service.record_dict(thread), "messages": [message_payload(db, row) for row in messages]}


@router.get("/agent/threads/{thread_id}/context")
def get_thread_context(
    thread_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    thread = agent_service.thread_for_membership(db, membership, thread_id)
    return agent_service.build_context_envelope(
        db, membership, thread, f"CTX-{thread.id}"
    ).model_dump()


@router.post("/agent/threads/{thread_id}/messages", dependencies=[Depends(csrf_guard)])
def send_message(
    thread_id: str,
    payload: AgentMessageRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    run, message = agent_service.run_message(db, user, thread_id, payload)
    db.commit()
    membership = agent_service.membership_for_user(db, user)
    thread = agent_service.thread_for_membership(db, membership, thread_id)
    state = agent_service.load_thread_state(thread.context_state)
    active_tasks = [task for task in workflows.tasks_for_user(db, user) if task.status in task_service.ACTIVE_TASK_STATES]
    unread_notifications = db.query(models.Notification).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id, status='unread',
    ).count()
    pending_approvals = db.query(models.ComparisonApprovalRequest).filter_by(
        tenant_id=user.tenant_id, assignee_membership_id=membership.id, status='pending',
    ).count()
    return {
        'run': agent_service.record_dict(run),
        'message': message_payload(db, message),
        'turn_status': (
            'needs_input' if run.termination_reason == 'needs_clarification' else
            'processing' if run.termination_reason == 'processing' else
            'failed' if run.termination_reason in {'failed', 'blocked'} else
            {
            'completed': 'completed', 'paused_provider': 'paused_provider',
            'waiting_on_documents': 'processing', 'failed': 'failed',
            }.get(run.state, 'processing')
        ),
        'attachments': message_payload(
            db,
            db.query(models.AgentMessage).filter_by(
                correlation_id=run.correlation_id, message_type='user',
            ).first(),
        ).get('attachments', []),
        'retryable_failure': (
            {'code': run.error_code, 'message': run.error, 'retryable': True}
            if run.state == 'paused_provider' else None
        ),
        'blocks': message.content_blocks,
        'current_work_item': state.selected_context.model_dump(exclude_none=True),
        'allowed_actions': [row.capability_id for row in agent_service.capabilities_for_role(membership.role)],
        'created_or_updated_records': [
            row.model_dump(mode='json', exclude_none=True) for row in state.recent_entities[:10]
        ],
        'job_status': None,
        'badge_counts': {
            'my_work': len(active_tasks), 'approvals': pending_approvals,
            'notifications': unread_notifications,
        },
    }


@router.patch("/agent/message-attachments/{attachment_id}/resolution", dependencies=[Depends(csrf_guard)])
def resolve_message_attachment(
    attachment_id: str,
    payload: AttachmentResolutionRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    attachment = db.query(models.AgentMessageAttachment).join(
        models.AgentMessage, models.AgentMessage.id == models.AgentMessageAttachment.message_id,
    ).filter(
        models.AgentMessageAttachment.id == attachment_id,
        models.AgentMessageAttachment.tenant_id == user.tenant_id,
        models.AgentMessage.membership_id == membership.id,
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Message attachment not found")
    if attachment.version != payload.version:
        raise HTTPException(status_code=409, detail="Attachment state changed; refresh before confirming")
    if payload.rfq_id:
        rfq = workflows.get_scoped_or_404(db, models.RFQ, user, payload.rfq_id, "RFQ")
        attachment.confirmed_rfq_id = rfq.id
    if payload.supplier_id:
        supplier = workflows.get_scoped_or_404(db, models.Supplier, user, payload.supplier_id, "Supplier")
        attachment.confirmed_supplier_id = supplier.id
    resolved_rfq_id = attachment.confirmed_rfq_id or attachment.inferred_rfq_id
    resolved_supplier_id = attachment.confirmed_supplier_id or attachment.inferred_supplier_id
    if (
        resolved_rfq_id and resolved_supplier_id
        and membership.role in {"purchase_manager", "purchase_executive", "admin"}
    ):
        linked = workflows.attach_uploaded_quote_documents(
            db, user, rfq_id=resolved_rfq_id, supplier_id=resolved_supplier_id,
            document_ids=[attachment.document_id],
        )[0]
        attachment.linked_quotation_id = linked["quote_id"]
        attachment.status = "linked"
    else:
        attachment.status = "queued"
    attachment.error_code = None
    attachment.user_explanation = None
    attachment.version += 1
    db.commit()
    return agent_service.record_dict(attachment)


@router.post("/agent/message-attachments/{attachment_id}/retry", dependencies=[Depends(csrf_guard)], status_code=202)
def retry_message_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    attachment = db.query(models.AgentMessageAttachment).join(
        models.AgentMessage, models.AgentMessage.id == models.AgentMessageAttachment.message_id,
    ).filter(
        models.AgentMessageAttachment.id == attachment_id,
        models.AgentMessageAttachment.tenant_id == user.tenant_id,
        models.AgentMessage.membership_id == membership.id,
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Message attachment not found")
    latest = db.query(models.DocumentJob).filter_by(
        document_id=attachment.document_id,
    ).order_by(models.DocumentJob.created_at.desc()).first()
    if latest and latest.status not in {"failed", "needs_manual_entry"}:
        raise HTTPException(status_code=409, detail="Document processing is already active or complete")
    job = models.DocumentJob(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        document_id=attachment.document_id, job_type=latest.job_type if latest else "validate_extract",
        status="queued",
    )
    db.add(job)
    attachment.document_job_id = job.id
    attachment.status = "retrying"
    attachment.error_code = None
    db.commit()
    from app.workers import process_document
    result = process_document.apply_async(args=[job.id], queue="documents")
    job.celery_task_id = result.id
    db.commit()
    return {"attachment": agent_service.record_dict(attachment), "job_id": job.id}


@router.get("/agent/runs/{run_id}")
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    run = db.query(models.AgentRun).filter_by(
        id=run_id, tenant_id=user.tenant_id, membership_id=membership.id
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return agent_service.record_dict(run)


@router.get("/agent/runs/{run_id}/events")
def stream_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    run = db.query(models.AgentRun).filter_by(
        id=run_id, tenant_id=user.tenant_id, membership_id=membership.id
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")

    def events():
        persisted = db.query(models.AgentEvent).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
        ).order_by(models.AgentEvent.sequence.asc()).all()
        for item in persisted:
            data = {'id': item.id, 'sequence': item.sequence, **(item.payload or {})}
            yield f'event: {item.event_type}\ndata: {json.dumps(data, default=str)}\n\n'
        state = {"run_id": run.id, "state": run.state, "provider": run.provider, "model": run.model}
        yield f"event: run_state\ndata: {json.dumps(state)}\n\n"
        messages = db.query(models.AgentMessage).filter_by(
            tenant_id=user.tenant_id, thread_id=run.thread_id,
            membership_id=membership.id, correlation_id=run.correlation_id,
        ).order_by(models.AgentMessage.created_at.asc()).all()
        for message in messages:
            event = "completion" if message.message_type == "agent" else "message"
            data = {"id": message.id, "type": message.message_type, "content": message.content,
                    "citations": message.citations}
            yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/agent/runs/{run_id}/activity")
def run_activity(
    run_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    run = db.query(models.AgentRun).filter_by(
        id=run_id, tenant_id=user.tenant_id, membership_id=membership.id
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    events = db.query(models.AgentEvent).filter_by(
        tenant_id=user.tenant_id, run_id=run.id
    ).order_by(models.AgentEvent.sequence.asc()).all()
    tools = db.query(models.AgentToolCall).filter_by(
        tenant_id=user.tenant_id, run_id=run.id
    ).order_by(models.AgentToolCall.created_at.asc()).all()
    proposals = db.query(models.AgentProposal).filter_by(
        tenant_id=user.tenant_id, run_id=run.id
    ).order_by(models.AgentProposal.created_at.asc()).all()
    receipts = db.query(models.AgentActionReceipt).filter_by(
        tenant_id=user.tenant_id, run_id=run.id
    ).order_by(models.AgentActionReceipt.created_at.asc()).all()
    checkpoints = db.query(models.AgentCheckpoint).filter_by(
        tenant_id=user.tenant_id, run_id=run.id
    ).order_by(models.AgentCheckpoint.sequence.asc()).all()
    attempts = db.query(models.AgentRunAttempt).filter_by(
        tenant_id=user.tenant_id, run_id=run.id
    ).order_by(models.AgentRunAttempt.attempt_number.asc()).all()
    return {
        "run": agent_service.record_dict(run),
        "events": rows(events),
        "tool_calls": rows(tools),
        "proposals": rows(proposals),
        "receipts": rows(receipts),
        "checkpoints": rows(checkpoints),
        "attempts": rows(attempts),
    }


@router.post("/agent/runs/{run_id}/cancel", dependencies=[Depends(csrf_guard)])
def cancel_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    run = db.query(models.AgentRun).filter_by(
        id=run_id, tenant_id=user.tenant_id, membership_id=membership.id
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    run.cancellation_requested = True
    if run.state in {"queued", "running"}:
        run.state = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
        agent_service.record_run_event(db, run, 'run_cancelled', {'requested_by': membership.id})
    db.commit()
    return agent_service.record_dict(run)


@router.get("/agent/proposals")
def list_proposals(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    return rows(db.query(models.AgentProposal).filter_by(
        tenant_id=user.tenant_id, owner_membership_id=membership.id
    ).order_by(models.AgentProposal.created_at.desc()).all())


@router.post("/agent/proposals", dependencies=[Depends(csrf_guard)])
def create_proposal(
    payload: ProposalCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    proposal = agent_service.create_proposal(db, user, payload)
    db.commit()
    return agent_service.record_dict(proposal)


@router.post("/agent/proposals/{proposal_id}/confirm", dependencies=[Depends(csrf_guard)])
def confirm_proposal(
    proposal_id: str,
    payload: ProposalDecisionRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    proposal = agent_service.confirm_proposal(db, user, proposal_id)
    db.commit()
    return agent_service.record_dict(proposal)


@router.post("/agent/proposals/{proposal_id}/reject", dependencies=[Depends(csrf_guard)])
def reject_proposal(
    proposal_id: str,
    payload: ProposalDecisionRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    proposal = db.query(models.AgentProposal).filter_by(
        id=proposal_id, tenant_id=user.tenant_id, owner_membership_id=membership.id
    ).first()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.confirmation_state != "pending":
        raise HTTPException(status_code=409, detail="Proposal was already decided")
    proposal.confirmation_state = "rejected"
    proposal.decided_by_membership_id = membership.id
    proposal.decided_at = datetime.now(timezone.utc)
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=422, detail='A rejection rationale is required')
    proposal.rejection_rationale = payload.reason.strip()
    proposal.preview = {**proposal.preview, "rejection_reason": payload.reason}
    thread = db.get(models.AgentThread, proposal.thread_id)
    if thread:
        state = agent_service.load_thread_state(thread.context_state)
        if state.pending_proposal_id == proposal.id:
            state.pending_proposal_id = None
        state.updated_at = datetime.now(timezone.utc)
        agent_service.persist_thread_state(thread, state)
    if proposal.run_id:
        run = db.get(models.AgentRun, proposal.run_id)
        if run:
            agent_service.record_run_event(db, run, 'proposal_rejected', {
                'proposal_id': proposal.id,
                'reason': proposal.rejection_rationale,
            })
            run.state = 'completed'
            run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return agent_service.record_dict(proposal)


@router.get("/agent/delegations")
def list_delegations(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    return rows(db.query(models.AgentDelegation).filter(
        models.AgentDelegation.tenant_id == user.tenant_id,
        (models.AgentDelegation.sender_membership_id == membership.id)
        | (models.AgentDelegation.recipient_membership_id == membership.id),
    ).order_by(models.AgentDelegation.created_at.desc()).all())


@router.post("/agent/delegations", dependencies=[Depends(csrf_guard)])
def create_delegation(
    payload: DelegationCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    delegation = agent_service.create_delegation(db, user, payload)
    db.commit()
    return agent_service.record_dict(delegation)


@router.post("/agent/delegations/{delegation_id}/respond", dependencies=[Depends(csrf_guard)])
def respond_delegation(
    delegation_id: str,
    payload: DelegationResponseRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    delegation = agent_service.respond_to_delegation(db, user, delegation_id, payload)
    db.commit()
    return agent_service.record_dict(delegation)


@router.get("/agent/team-status")
def team_status(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    return agent_service.team_status(db, user)


@router.post('/tasks', dependencies=[Depends(csrf_guard)])
def create_canonical_task(
    payload: TaskCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    task = task_service.create_task(db, user, payload)
    db.commit()
    return task_service.task_payload(db, task)


@router.get('/tasks/team')
def task_team_summary(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    return task_service.manager_summary(db, user)


@router.get('/tasks/{task_id}')
def task_detail(
    task_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    task, _actor = task_service.task_for_actor(db, user, task_id)
    return task_service.task_payload(db, task)


@router.post('/tasks/{task_id}/transition', dependencies=[Depends(csrf_guard)])
def transition_canonical_task(
    task_id: str,
    payload: TaskTransitionRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    task = task_service.transition_task(db, user, task_id, payload)
    db.commit()
    return task_service.task_payload(db, task)


@router.post('/tasks/{task_id}/request-update', dependencies=[Depends(csrf_guard)])
def request_task_update(
    task_id: str,
    payload: TaskFollowUpRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    task = task_service.request_follow_up(db, user, task_id, payload)
    db.commit()
    return task_service.task_payload(db, task)


@router.get('/notifications')
def list_notifications(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    return rows(db.query(models.Notification).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id,
    ).order_by(models.Notification.created_at.desc()).limit(50).all())


@router.get("/knowledge")
def list_knowledge(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    if user.role == ADMIN:
        return rows(db.query(models.KnowledgeDocument).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id,
        ).order_by(models.KnowledgeDocument.updated_at.desc()).all())
    return rows(agent_service.approved_knowledge(db, membership))


@router.post("/knowledge", dependencies=[Depends(csrf_guard)])
def create_knowledge(
    payload: KnowledgeCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_role(user, ADMIN)
    allowed_roles = {'plant_manager', 'purchase_manager', 'purchase_executive', 'gate_operator', 'store_manager', 'quality_inspector', 'admin'}
    if not set(payload.role_acl) <= allowed_roles:
        raise HTTPException(status_code=422, detail='Knowledge role visibility contains an unsupported role')
    if payload.plant_acl and any(plant_id != user.plant_id for plant_id in payload.plant_acl):
        raise HTTPException(status_code=403, detail='Knowledge may only be assigned inside the active plant')
    previous = db.query(models.KnowledgeDocument).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, title=payload.title, source=payload.source,
    ).order_by(models.KnowledgeDocument.document_version.desc()).first()
    document = models.KnowledgeDocument(
        tenant_id=user.tenant_id, plant_id=user.plant_id, title=payload.title,
        source=payload.source, content=payload.content, approval_state="draft",
        document_version=(previous.document_version + 1 if previous else 1), role_acl=payload.role_acl, plant_acl=payload.plant_acl,
        document_type=payload.document_type, revision=payload.revision,
        effective_from=payload.effective_from, effective_to=payload.effective_to,
        asset_ids=payload.asset_ids, product_codes=payload.product_codes,
        process_codes=payload.process_codes,
    )
    db.add(document)
    db.flush()
    chunks = [payload.content[index:index + 1200] for index in range(0, len(payload.content), 1200)]
    for index, content in enumerate(chunks):
        db.add(models.KnowledgeChunk(
            tenant_id=user.tenant_id, plant_id=user.plant_id,
            knowledge_document_id=document.id, chunk_index=index,
            content=content, embedding=[], token_count=max(1, len(content.split())),
        ))
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "knowledge.created",
        "knowledge_document", document.id, actor_user_id=user.id,
        meta={"role_acl": payload.role_acl, "plant_acl": payload.plant_acl},
    )
    db.commit()
    return agent_service.record_dict(document)


@router.post("/knowledge/{document_id}/decision", dependencies=[Depends(csrf_guard)])
def decide_knowledge(
    document_id: str,
    payload: KnowledgeDecisionRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_role(user, ADMIN)
    document = db.query(models.KnowledgeDocument).filter_by(
        id=document_id, tenant_id=user.tenant_id, plant_id=user.plant_id,
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    if payload.decision == "approve":
        prior = db.query(models.KnowledgeDocument).filter(
            models.KnowledgeDocument.tenant_id == user.tenant_id,
            models.KnowledgeDocument.plant_id == user.plant_id,
            models.KnowledgeDocument.title == document.title,
            models.KnowledgeDocument.source == document.source,
            models.KnowledgeDocument.id != document.id,
            models.KnowledgeDocument.approval_state == "approved",
        ).all()
        for item in prior:
            item.approval_state = "retired"
            item.retired_at = datetime.now(timezone.utc)
        document.approval_state = "approved"
        document.approved_by_user_id = user.id
        document.approved_at = datetime.now(timezone.utc)
    else:
        document.approval_state = "retired"
        document.retired_at = datetime.now(timezone.utc)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, f"knowledge.{payload.decision}",
        "knowledge_document", document.id, actor_user_id=user.id,
    )
    db.commit()
    return agent_service.record_dict(document)


@router.post("/agent/runs/{run_id}/feedback", dependencies=[Depends(csrf_guard)])
def submit_feedback(
    run_id: str,
    payload: AgentFeedbackRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    membership = agent_service.membership_for_user(db, user)
    run = db.query(models.AgentRun).filter_by(
        id=run_id, tenant_id=user.tenant_id, membership_id=membership.id
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    feedback = models.AgentFeedback(
        tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
        membership_id=membership.id, **payload.model_dump(),
    )
    db.add(feedback)
    db.commit()
    return agent_service.record_dict(feedback)


@router.patch("/admin/agents/{profile_id}", dependencies=[Depends(csrf_guard)])
def update_agent_policy(
    profile_id: str,
    payload: AgentPolicyUpdateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_role(user, ADMIN)
    profile = db.query(models.AgentProfile).filter_by(
        id=profile_id, tenant_id=user.tenant_id
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(profile, key, value)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "agent.policy.updated",
        "agent_profile", profile.id, actor_user_id=user.id,
        meta={"changed_fields": sorted(changes)},
    )
    db.commit()
    return agent_service.record_dict(profile)


@router.post("/admin/agents/emergency-stop", dependencies=[Depends(csrf_guard)])
def emergency_stop(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_role(user, ADMIN)
    tenant = db.get(models.Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    tenant.agent_enabled = False
    db.query(models.AgentProfile).filter_by(tenant_id=user.tenant_id).update(
        {models.AgentProfile.enabled: False}, synchronize_session=False
    )
    db.query(models.AgentRun).filter(
        models.AgentRun.tenant_id == user.tenant_id,
        models.AgentRun.state.in_(["queued", "running"]),
    ).update({
        models.AgentRun.state: "cancelled",
        models.AgentRun.cancellation_requested: True,
        models.AgentRun.completed_at: datetime.now(timezone.utc),
    }, synchronize_session=False)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "agent.emergency_stop",
        "tenant", user.tenant_id, actor_user_id=user.id,
    )
    db.commit()
    return {"status": "agents_disabled", "normal_workflows_available": True}
