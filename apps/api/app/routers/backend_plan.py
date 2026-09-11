from datetime import datetime, timezone
import hashlib
from threading import RLock
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import agent_service, task_service, management_insights, retention_service, cycle_orchestration, eventing
from app.policy_decision import simulate_template
from app.agent_schemas import SpecialistRequest
from app.feature_flags import enabled as feature_enabled
from app import policy_bundles
from app.api_schemas import RetentionEnforceRequest, RetentionHoldRequest
from app.core.config import get_settings
from app.core.permissions import ADMIN
from app.core.security import current_user, require_csrf
from app.db import models
from app.db.session import get_db
from app.domains import workflows

router = APIRouter()
_CYCLE_SYNC_LOCK = RLock()


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def rows(records: list[Any]) -> list[dict[str, Any]]:
    return [agent_service.record_dict(item) for item in records]


def require_demo_owner(db: Session, user: models.User, workspace_id: str) -> None:
    settings = get_settings()
    if not settings.demo_bootstrap_enabled or settings.app_env.lower() == 'production':
        raise HTTPException(status_code=404, detail='Demo access is disabled')
    actor = agent_service.membership_for_user(db, user)
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=workspace_id, account_id=actor.account_id, status='active',
    ).first()
    if membership is None or (membership.role != ADMIN and 'workspace.owner' not in (membership.permissions or [])):
        raise HTTPException(status_code=403, detail='Workspace owner or Admin access required')


@router.get('/workspaces/{workspace_id}/demo-access')
def demo_access(workspace_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_demo_owner(db, user, workspace_id)
    return {'demo_mode': True, 'workspace_id': workspace_id, 'accounts': agent_service.demo_access_rows(db, workspace_id)}


@router.post('/workspaces/{workspace_id}/demo-access/reconcile', dependencies=[Depends(csrf_guard)])
def reconcile_demo_access(workspace_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_demo_owner(db, user, workspace_id)
    accounts = agent_service.reconcile_demo_access(db, workspace_id)
    db.commit()
    return {'demo_mode': True, 'workspace_id': workspace_id, 'accounts': accounts}


@router.get('/agent/threads/{thread_id}/context-summary')
def context_summary(thread_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    membership = agent_service.membership_for_user(db, user)
    thread = agent_service.thread_for_membership(db, membership, thread_id)
    state = dict(thread.context_state or {})
    return {
        'active_intent': state.get('active_intent') or state.get('intent'),
        'draft_fields': state.get('draft_fields') or state.get('procurement') or {},
        'recent_entities': list(state.get('recent_entities') or [])[-10:],
        'current_work_item': state.get('current_work_item'),
        'attachments': list(state.get('attachments') or [])[-20:],
        'allowed_capabilities': [row.capability_id for row in agent_service.capabilities_for_role(membership.role)],
        'updated_at': state.get('updated_at'),
    }


@router.post('/notifications/{notification_id}/read', dependencies=[Depends(csrf_guard)])
def read_notification(notification_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    notification = db.query(models.Notification).filter_by(
        id=notification_id, tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id,
    ).first()
    if notification is None:
        raise HTTPException(status_code=404, detail='Notification not found')
    notification.status = 'read'
    db.commit()
    return agent_service.record_dict(notification)


@router.post('/notifications/read-all', dependencies=[Depends(csrf_guard)])
def read_all_notifications(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    updated = db.query(models.Notification).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id, status='unread',
    ).update({models.Notification.status: 'read'}, synchronize_session=False)
    db.commit()
    return {'updated': updated}


def home_payload(db: Session, user: models.User) -> dict[str, Any]:
    membership = agent_service.membership_for_user(db, user)
    my_tasks = workflows.tasks_for_user(db, user)
    active = [task for task in my_tasks if task.status in task_service.ACTIVE_TASK_STATES]
    notifications = db.query(models.Notification).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id,
    ).order_by(models.Notification.created_at.desc()).limit(20).all()
    approvals = db.query(models.ComparisonApprovalRequest).filter_by(
        tenant_id=user.tenant_id, assignee_membership_id=membership.id, status='pending',
    ).count()
    quotes = 0
    if user.role in {'purchase_manager', 'purchase_executive', ADMIN}:
        quotes = workflows.user_scope_query(db, models.SupplierQuote, user).filter(
            models.SupplierQuote.verification_status.in_(['extracting', 'needs_review', 'needs_manual_entry'])
        ).count()
    team = task_service.manager_summary(db, user)
    cycles = workflows.procurement_cycle_summaries(db, user)
    cycle_by_case = {
        requirement.related_case_id: cycle
        for requirement, cycle in zip(
            workflows.user_scope_query(db, models.PurchaseRequirement, user).filter(
                models.PurchaseRequirement.status.notin_(['cancelled', 'closed'])
            ).order_by(models.PurchaseRequirement.created_at.desc()).all(),
            cycles,
        ) if requirement.related_case_id
    }
    actionable = []
    seen_semantic: set[tuple[str, str, str]] = set()
    for task in active:
        cycle = cycle_by_case.get(task.linked_case_id)
        if cycle is None:
            continue
        semantic_key = (cycle['id'], task.entity_type or '', task.title.casefold().strip())
        if semantic_key in seen_semantic:
            continue
        seen_semantic.add(semantic_key)
        stage = cycle['current_stage']
        material = cycle['materials'][0] if cycle['materials'] else None
        rfq = cycle['rfqs'][0] if cycle['rfqs'] else None
        owned = task.owner_user_id == user.id or task.owner_role == user.role or task.shared_queue
        actionable.append({
            'id': task.id,
            'title': task.title,
            'cycle': {
                'id': cycle['id'], 'business_number': cycle['business_number'],
                'label': cycle['title'], 'secondary_context': material['label'] if material else None,
                'status': cycle['health'], 'route': f"/control-centre?cycle={cycle['id']}",
            },
            'material': material, 'rfq': rfq, 'supplier': None,
            'stage_index': cycle['current_stage_index'], 'stage_count': 8,
            'stage_label': stage['label'],
            'due_state': (
                'Overdue'
                if task.due_at and (
                    task.due_at.replace(tzinfo=timezone.utc) if task.due_at.tzinfo is None else task.due_at
                ) < workflows.utcnow()
                else 'Due soon' if task.due_at else 'No due date'
            ),
            'blocker': task.blocker_reason or cycle['blocked_dependency'],
            'current_owner': workflows.role_label(task.owner_role),
            'required_authority': workflows.role_label(task.owner_role),
            'required_evidence': workflows.work_item_from_task(task, db, user).required_evidence,
            'allowed_actions': workflows.work_item_from_task(task, db, user).allowed_human_actions if owned else [],
            'primary_route': workflows.work_item_from_task(task, db, user).href if owned else f"/control-centre?cycle={cycle['id']}",
        })
    mine = [cycle for cycle in cycles if cycle['next_owner'] == user.role]
    waiting = [cycle for cycle in cycles if cycle['next_owner'] != user.role]
    at_risk = [cycle for cycle in cycles if cycle['health'] in {'at_risk', 'blocked'}]
    result = {
        'badge_counts': {
            'my_work': len(active), 'approvals': approvals, 'quotations': quotes,
            'inbound': sum(1 for task in active if task.entity_type in {'gate_entries', 'store_receipts', 'inspection_results'}),
            'notifications': sum(1 for row in notifications if row.status == 'unread'),
        },
        'attention_items': [task_service.task_payload(db, task) for task in active if task.severity == 'critical' or task.status == 'blocked'],
        'assistant_prepared': rows(db.query(models.Notification).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id, category='assistant_prepared',
        ).order_by(models.Notification.created_at.desc()).limit(10).all()),
        'my_tasks': [task_service.task_payload(db, task) for task in active],
        'waiting_on_others': team,
        'team_followups': [row for row in team if row.get('is_overdue') or row.get('status') == 'blocked'],
        'recent_notifications': rows(notifications),
        'daily_brief': management_insights.brief(db, user, 'morning'),
        'next_action': actionable[0] if actionable else None,
        'actionable_work_items': actionable,
        'cycles': cycles,
        'cycle_groups': {'mine_now': mine, 'waiting': waiting, 'at_risk': at_risk, 'all_active': cycles},
    }
    return result


@router.get('/workspace/home')
def workspace_home(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return home_payload(db, user)


def _visible_objective(db: Session, user: models.User, objective_id: str) -> models.ProcurementCycleObjective:
    row = db.query(models.ProcurementCycleObjective).filter_by(
        id=objective_id, tenant_id=user.tenant_id, plant_id=user.plant_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail='Procurement cycle not found')
    return row


def _sync_cycles(db: Session, user: models.User) -> list[models.ProcurementCycleObjective]:
    with _CYCLE_SYNC_LOCK:
        requirements = workflows.user_scope_query(db, models.PurchaseRequirement, user).filter(
            models.PurchaseRequirement.status.notin_(['cancelled'])
        ).all()
        objectives = [cycle_orchestration.evaluate(db, requirement) for requirement in requirements]
        # Lazy backfill is a rollout bridge; objective and outbox rows commit in the
        # same transaction. Scheduled/event consumers use the same evaluator.
        db.commit()
        return objectives


@router.get('/workbench/my-day')
def my_day(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if not feature_enabled(db, user.tenant_id, 'agentic_procurement_cycles'):
        legacy = home_payload(db, user)
        return {'decisions_required': legacy['attention_items'], 'prepared_for_you': legacy['assistant_prepared'],
                'do_now': legacy['my_tasks'], 'waiting_on_others': [], 'watching': [], 'at_risk': [],
                'completed_today': [], 'cycles': []}
    membership = agent_service.membership_for_user(db, user)
    objectives = _sync_cycles(db, user)
    cycles = [cycle_orchestration.serialize(db, row) for row in objectives]
    tasks = workflows.tasks_for_user(db, user)
    prepared = db.query(models.PreparedWorkItem).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, owner_membership_id=membership.id, status='ready',
    ).all()
    return {
        'decisions_required': [task_service.task_payload(db, row) for row in tasks if row.status == 'pending_approval'],
        'prepared_for_you': [agent_service.record_dict(row) for row in prepared],
        'do_now': [task_service.task_payload(db, row) for row in tasks if row.status in {'open', 'accepted', 'in_progress'}],
        'waiting_on_others': [cycle for cycle in cycles if cycle['evaluation'].get('owner_role') != user.role],
        'watching': [cycle for cycle in cycles if cycle['health'] == 'on_track'],
        'at_risk': [cycle for cycle in cycles if cycle['health'] in {'at_risk', 'blocked'}],
        'completed_today': [task_service.task_payload(db, row) for row in tasks if row.status == 'completed' and row.completed_at and row.completed_at.date() == datetime.now(timezone.utc).date()],
        'cycles': cycles,
    }


@router.get('/workbench/prepared')
def prepared_work(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    membership = agent_service.membership_for_user(db, user)
    return rows(db.query(models.PreparedWorkItem).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, owner_membership_id=membership.id).all())


@router.get('/workbench/decisions')
def workbench_decisions(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return [task_service.task_payload(db, row) for row in workflows.tasks_for_user(db, user) if row.status == 'pending_approval']


@router.get('/workbench/watching')
def workbench_watching(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return [cycle_orchestration.serialize(db, row) for row in _sync_cycles(db, user) if row.health == 'on_track']


@router.get('/workbench/risks')
def workbench_risks(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return [cycle_orchestration.serialize(db, row) for row in _sync_cycles(db, user) if row.health in {'at_risk', 'blocked'}]


@router.get('/procurement/cycles/{objective_id}/timeline')
def durable_cycle_timeline(objective_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    objective = _visible_objective(db, user, objective_id)
    return rows(db.query(models.EventOutbox).filter_by(aggregate_id=objective.id).order_by(models.EventOutbox.created_at.desc()).all())


@router.get('/procurement/cycles/{objective_id}/next-actions')
def durable_cycle_actions(objective_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    objective = _visible_objective(db, user, objective_id)
    return {'cycle_id': objective.id, **objective.evaluation_summary}


@router.post('/procurement/cycles/{objective_id}/re-evaluate', dependencies=[Depends(csrf_guard)])
def reevaluate_cycle(objective_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    objective = _visible_objective(db, user, objective_id)
    membership = agent_service.membership_for_user(db, user)
    requirement = workflows.user_scope_query(db, models.PurchaseRequirement, user).filter_by(id=objective.requirement_id).first()
    if requirement is None:
        raise HTTPException(status_code=404, detail='Root requirement not found')
    result = cycle_orchestration.evaluate(db, requirement, membership.id)
    db.commit()
    return cycle_orchestration.serialize(db, result)


def _owned_task(db: Session, user: models.User, task_id: str) -> models.Task:
    membership = agent_service.membership_for_user(db, user)
    task = db.query(models.Task).filter_by(id=task_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail='Task not found')
    if task.owner_membership_id != membership.id and user.role != ADMIN:
        raise HTTPException(status_code=403, detail='Task belongs to another employee')
    return task


@router.post('/tasks/{task_id}/accept', dependencies=[Depends(csrf_guard)])
def accept_task(task_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    task = _owned_task(db, user, task_id)
    task.acceptance_status, task.accepted_at, task.status = 'accepted', datetime.now(timezone.utc), 'accepted'
    task.last_meaningful_activity_at = task.accepted_at
    db.commit()
    return task_service.task_payload(db, task)


@router.post('/tasks/{task_id}/commitments', dependencies=[Depends(csrf_guard)])
def create_commitment(task_id: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    task = _owned_task(db, user, task_id)
    membership = agent_service.membership_for_user(db, user)
    try:
        promised_at = datetime.fromisoformat(str(payload['promised_at']).replace('Z', '+00:00'))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail='promised_at must be an ISO timestamp') from exc
    commitment = models.Commitment(tenant_id=user.tenant_id, plant_id=user.plant_id, task_id=task.id,
        objective_id=task.objective_id, owner_membership_id=membership.id, promised_at=promised_at,
        deliverable=str(payload.get('deliverable') or task.requested_outcome or task.title),
        commitment_type=str(payload.get('commitment_type') or 'employee'))
    db.add(commitment)
    db.commit()
    return agent_service.record_dict(commitment)


@router.post('/tasks/{task_id}/commitments/{commitment_id}/revise', dependencies=[Depends(csrf_guard)])
def revise_commitment(task_id: str, commitment_id: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    task = _owned_task(db, user, task_id)
    previous = db.query(models.Commitment).filter_by(
        id=commitment_id, task_id=task.id, tenant_id=user.tenant_id, plant_id=user.plant_id,
    ).first()
    if previous is None:
        raise HTTPException(status_code=404, detail='Commitment not found')
    reason = str(payload.get('reason') or '').strip()
    if not reason:
        raise HTTPException(status_code=422, detail='A revision reason is required')
    try:
        promised_at = datetime.fromisoformat(str(payload['promised_at']).replace('Z', '+00:00'))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail='promised_at must be an ISO timestamp') from exc
    previous.status = 'revised'
    revision = models.Commitment(
        tenant_id=user.tenant_id, plant_id=user.plant_id, task_id=task.id,
        objective_id=previous.objective_id, commitment_type=previous.commitment_type,
        owner_membership_id=previous.owner_membership_id, promised_at=promised_at,
        deliverable=str(payload.get('deliverable') or previous.deliverable), revision=previous.revision + 1,
        revision_reason=reason, supersedes_commitment_id=previous.id,
    )
    db.add(revision)
    task.last_meaningful_activity_at = datetime.now(timezone.utc)
    db.commit()
    return agent_service.record_dict(revision)


@router.post('/tasks/{task_id}/blockers', dependencies=[Depends(csrf_guard)])
def set_blocker(task_id: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    task = _owned_task(db, user, task_id)
    if payload.get('resolved'):
        previous_owner = task.blocker_owner_membership_id
        task.blocker_type = task.blocker_reason = task.blocker_owner_membership_id = None
        task.status = 'in_progress'
        task.last_meaningful_activity_at = datetime.now(timezone.utc)
        if task.objective_id:
            downstream = db.query(models.Task).filter(
                models.Task.tenant_id == user.tenant_id, models.Task.objective_id == task.objective_id,
                models.Task.id != task.id, models.Task.status.in_(['open', 'accepted', 'in_progress']),
            ).all()
            for row in downstream:
                if row.owner_user_id:
                    db.add(models.Notification(tenant_id=user.tenant_id, plant_id=user.plant_id,
                        user_id=row.owner_user_id, membership_id=row.owner_membership_id,
                        title='Dependency resolved', body=f'{task.title} is moving again.', status='unread',
                        category='dependency_resolved', severity='info', task_id=row.id,
                        linked_entity_type=row.entity_type, linked_entity_id=row.entity_id,
                        navigation_target=f'/agent?work_item={row.id}',
                        dedupe_key=f'dependency_resolved:{task.id}:{task.version}:{row.id}'))
        db.commit()
        return {**task_service.task_payload(db, task), 'previous_blocker_owner_membership_id': previous_owner}
    task.blocker_type = str(payload.get('blocker_type') or 'dependency')
    task.blocker_reason = str(payload.get('reason') or '').strip()
    if not task.blocker_reason:
        raise HTTPException(status_code=422, detail='A blocker reason is required')
    task.blocker_owner_membership_id = payload.get('blocker_owner_membership_id')
    task.status = 'blocked'
    task.last_meaningful_activity_at = datetime.now(timezone.utc)
    db.commit()
    return task_service.task_payload(db, task)


@router.get('/admin/events')
def admin_events(status: str | None = None, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail='Only Admin can inspect domain events')
    query = db.query(models.EventOutbox).filter_by(tenant_id=user.tenant_id)
    if status:
        query = query.filter_by(status=status)
    return rows(query.order_by(models.EventOutbox.created_at.desc()).limit(200).all())


@router.post('/admin/events/{event_id}/replay', dependencies=[Depends(csrf_guard)])
def replay_event(event_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail='Only Admin can replay domain events')
    event = db.query(models.EventOutbox).filter_by(event_id=event_id, tenant_id=user.tenant_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail='Domain event not found')
    eventing.replay(db, event_id)
    from app.workers import dispatch_domain_event
    dispatch_domain_event.apply_async(args=[event_id], queue='events')
    return {'event_id': event_id, 'status': 'queued', 'completed_consumers_will_not_repeat': True}


def _require_manager(user: models.User) -> None:
    if user.role not in {'plant_manager', 'purchase_manager', ADMIN}:
        raise HTTPException(status_code=403, detail='Manager authority is required')


@router.get('/manager/operations')
def manager_operations(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_manager(user)
    cycles = [cycle_orchestration.serialize(db, row) for row in _sync_cycles(db, user)]
    team = task_service.manager_summary(db, user)
    return {
        'cycle_health': {state: sum(row['health'] == state for row in cycles) for state in ('on_track', 'attention', 'at_risk', 'blocked')},
        'production_risks': [row for row in cycles if row['health'] in {'at_risk', 'blocked'}],
        'unaccepted_work': [row for row in team if row.get('acceptance_status') in {'assigned', 'pending'}],
        'missed_commitments': [row for row in team if row.get('is_overdue')],
        'approval_bottlenecks': [row for row in team if row.get('status') == 'pending_approval'],
        'workload': team,
    }


@router.get('/manager/exceptions')
def manager_exceptions(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_manager(user)
    team = task_service.manager_summary(db, user)
    return [{
        'task': row, 'impact': row.get('production_impact') or row.get('business_impact') or 'normal',
        'current_owner': row.get('owner_name'), 'blocker_owner_membership_id': row.get('blocker_owner_membership_id'),
        'evidence': row.get('expected_output') or {},
        'recommended_intervention': 'Contact the blocker owner' if row.get('status') == 'blocked' else 'Review the missed commitment',
    } for row in team if row.get('status') == 'blocked' or row.get('is_overdue')]


@router.get('/manager/workload')
def manager_workload(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_manager(user)
    team = task_service.manager_summary(db, user)
    grouped: dict[str, dict[str, Any]] = {}
    for row in team:
        key = str(row.get('owner_membership_id') or row.get('owner_name'))
        summary = grouped.setdefault(key, {'membership_id': row.get('owner_membership_id'), 'name': row.get('owner_name'), 'active': 0, 'overdue': 0, 'blocked': 0, 'estimated_effort_minutes': 0})
        summary['active'] += 1
        summary['overdue'] += int(bool(row.get('is_overdue')))
        summary['blocked'] += int(row.get('status') == 'blocked')
        summary['estimated_effort_minutes'] += int(row.get('estimated_effort_minutes') or 0)
    return list(grouped.values())


@router.get('/manager/reports/{period}')
def manager_report(period: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_manager(user)
    if period not in {'week', 'month', 'quarter'}:
        raise HTTPException(status_code=422, detail='Period must be week, month, or quarter')
    operations = manager_operations(db, user)
    today = datetime.now(timezone.utc).date()
    report_key = f'{period}:{today.isoformat()}'
    report = db.query(models.OperationalReport).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, period=report_key).first()
    if report is None:
        report = models.OperationalReport(tenant_id=user.tenant_id, plant_id=user.plant_id,
            period=report_key, period_start=today.isoformat(), period_end=today.isoformat(),
            metrics={key: value for key, value in operations.items() if key == 'cycle_health'},
            sources=[{'type': 'procurement_cycle_objective', 'count': sum(operations['cycle_health'].values())}])
        db.add(report)
        db.commit()
    return agent_service.record_dict(report)


@router.get('/admin/autonomy-policies')
def autonomy_policies(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    return rows(db.query(models.AutonomyPolicy).filter_by(tenant_id=user.tenant_id).order_by(models.AutonomyPolicy.created_at.desc()).all())


@router.put('/admin/autonomy-policies/{policy_id}', dependencies=[Depends(csrf_guard)])
def update_autonomy_policy(policy_id: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    policy = db.query(models.AutonomyPolicy).filter_by(id=policy_id, tenant_id=user.tenant_id).first()
    if policy is None:
        policy = models.AutonomyPolicy(id=policy_id, tenant_id=user.tenant_id, plant_id=user.plant_id,
            name=str(payload.get('name') or 'Autonomy policy'), capability_id=str(payload.get('capability_id') or ''))
        db.add(policy)
    if policy.state == 'published':
        raise HTTPException(status_code=409, detail='Published policy versions are immutable; create a new draft')
    for field in ('name', 'capability_id', 'roles', 'plant_ids', 'category_ids', 'autonomy_ceiling', 'spend_limit', 'risk_limit', 'external_communication', 'confirmation_required'):
        if field in payload:
            setattr(policy, field, payload[field])
    if not policy.capability_id or not 0 <= policy.autonomy_ceiling <= 4:
        raise HTTPException(status_code=422, detail='Capability and autonomy ceiling from 0 to 4 are required')
    db.commit()
    return agent_service.record_dict(policy)


@router.post('/admin/autonomy-policies/{policy_id}/publish', dependencies=[Depends(csrf_guard)])
def publish_autonomy_policy(policy_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    policy = db.query(models.AutonomyPolicy).filter_by(id=policy_id, tenant_id=user.tenant_id, state='draft').first()
    if policy is None:
        raise HTTPException(status_code=404, detail='Draft policy not found')
    policy.state = 'published'
    policy.policy_version = f'{policy.id}@{policy.version}'
    policy.published_at = datetime.now(timezone.utc)
    membership = agent_service.membership_for_user(db, user)
    db.flush()
    bundle = policy_bundles.build(db, user.tenant_id, user.plant_id, membership.id)
    db.commit()
    return {**agent_service.record_dict(policy), 'bundle': agent_service.record_dict(bundle)}


@router.get('/admin/autonomy-policies/bundles')
def list_policy_bundles(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    return rows(db.query(models.PolicyBundle).filter_by(tenant_id=user.tenant_id).order_by(models.PolicyBundle.created_at.desc()).all())


@router.post('/admin/autonomy-policies/bundles/{bundle_id}/activate', dependencies=[Depends(csrf_guard)])
def activate_policy_bundle(bundle_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    bundle = db.query(models.PolicyBundle).filter_by(id=bundle_id, tenant_id=user.tenant_id).first()
    if bundle is None:
        raise HTTPException(status_code=404, detail='Policy bundle not found')
    try:
        policy_bundles.activate(db, bundle)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return agent_service.record_dict(bundle)


@router.post('/admin/autonomy-policies/simulate', dependencies=[Depends(csrf_guard)])
def simulate_autonomy_policy(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    policy = db.query(models.AutonomyPolicy).filter_by(id=payload.get('policy_id'), tenant_id=user.tenant_id).first()
    if policy is None:
        raise HTTPException(status_code=404, detail='Policy not found')
    decision = simulate_template(policy, role=str(payload.get('role') or ''),
        plant_id=str(payload.get('plant_id') or user.plant_id),
        capability_id=str(payload.get('capability_id') or policy.capability_id),
        spend=float(payload.get('spend') or 0), risk=str(payload.get('risk') or 'low'),
        external_effect=bool(payload.get('external_effect')))
    return decision.model_dump()


@router.post('/procurement/cycles/{objective_id}/specialists/{specialist_name}', dependencies=[Depends(csrf_guard)], status_code=202)
def start_specialist(objective_id: str, specialist_name: str, payload: dict[str, Any] = Body(default={}), db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if not feature_enabled(db, user.tenant_id, 'async_specialists'):
        raise HTTPException(status_code=404, detail='Asynchronous specialists are not enabled for this workspace')
    objective = _visible_objective(db, user, objective_id)
    membership = agent_service.membership_for_user(db, user)
    profile = agent_service.profile_for_membership(db, membership)
    thread = db.query(models.AgentThread).filter_by(
        tenant_id=user.tenant_id, membership_id=membership.id, objective_id=objective.id, status='active',
    ).first()
    if thread is None:
        thread = models.AgentThread(tenant_id=user.tenant_id, plant_id=user.plant_id,
            membership_id=membership.id, agent_profile_id=profile.id, thread_type='specialist',
            title=f'{specialist_name.replace("_", " ").title()} · {objective.business_number or "Procurement cycle"}',
            objective_id=objective.id, participant_membership_ids=[membership.id])
        db.add(thread)
        db.flush()
    correlation_id = str(uuid4())
    request = SpecialistRequest(specialist=specialist_name, objective_id=objective.id,
        task_id=payload.get('task_id'), requested_outcome=str(payload.get('requested_outcome') or 'Prepare the next review item'),
        authorized_artifact_ids=list(payload.get('authorized_artifact_ids') or []),
        constraints=dict(payload.get('constraints') or {}), correlation_id=correlation_id)
    run = models.AgentRun(tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        membership_id=membership.id, agent_profile_id=profile.id, state='queued', provider='deterministic',
        model='specialist-v1', context_hash=hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
        policy_version=profile.policy_version, trace_id=f'trace-{uuid4().hex[:16]}', correlation_id=correlation_id,
        intent=f'specialist:{specialist_name}', requested_outcome=request.requested_outcome,
        active_context={'specialist_request': request.model_dump(mode='json')})
    db.add(run)
    db.commit()
    from app.workers import run_specialist
    result = run_specialist.apply_async(args=[run.id], queue='specialists')
    return {'run_id': run.id, 'state': run.state, 'celery_task_id': result.id, 'correlation_id': correlation_id}


@router.get('/workspace/readiness')
def workspace_readiness(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return management_insights.readiness(db, user)


@router.get('/workspace/analytics')
def workspace_analytics(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role not in {'plant_manager', 'purchase_manager', ADMIN}:
        raise HTTPException(status_code=403, detail='Management analytics require manager authority')
    return management_insights.analytics(db, user)


@router.get('/workspace/brief')
def workspace_brief(period: str = 'morning', db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if period not in {'morning', 'end_of_day'}:
        raise HTTPException(status_code=422, detail='Brief period must be morning or end_of_day')
    return management_insights.brief(db, user, period)


@router.get('/workspace/configuration-export')
def workspace_configuration_export(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail='Only Admin can export workspace configuration')
    return management_insights.configuration_export(db, user)


def require_admin(user: models.User) -> None:
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail='Only Admin can manage retention')


@router.get('/workspace/retention/preview')
def retention_preview(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    return retention_service.preview(db, user)


@router.post('/workspace/retention/enforce', dependencies=[Depends(csrf_guard)])
def retention_enforce(payload: RetentionEnforceRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    result = retention_service.enforce(db, user, payload.confirmation)
    db.commit()
    return result


@router.post('/workspace/retention/holds', dependencies=[Depends(csrf_guard)])
def retention_hold(payload: RetentionHoldRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_admin(user)
    try:
        hold = retention_service.place_hold(db, user, payload.thread_id, payload.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return agent_service.record_dict(hold)
