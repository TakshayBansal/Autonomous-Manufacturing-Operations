from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent_schemas import TaskCreateRequest, TaskFollowUpRequest, TaskTransitionRequest
from app.db import models
from app.domains import workflows


ACTIVE_TASK_STATES = {'open', 'accepted', 'in_progress', 'blocked', 'review', 'pending_approval'}
TRANSITIONS = {
    'open': {'accepted', 'in_progress', 'cancelled'},
    'accepted': {'in_progress', 'blocked', 'cancelled'},
    'in_progress': {'blocked', 'review', 'completed', 'cancelled'},
    'blocked': {'in_progress', 'cancelled'},
    'review': {'in_progress', 'completed', 'cancelled'},
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def membership_for_user(db: Session, user: models.User) -> models.WorkspaceMembership:
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status='active',
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail='Active workspace membership required')
    return membership


def descendants(db: Session, membership: models.WorkspaceMembership) -> set[str]:
    found: set[str] = set()
    frontier = {membership.id}
    while frontier:
        rows = db.query(models.WorkspaceMembership).filter(
            models.WorkspaceMembership.tenant_id == membership.tenant_id,
            models.WorkspaceMembership.manager_membership_id.in_(frontier),
            models.WorkspaceMembership.status == 'active',
        ).all()
        frontier = {row.id for row in rows if row.id not in found}
        found.update(frontier)
    return found


def task_for_actor(db: Session, user: models.User, task_id: str) -> tuple[models.Task, models.WorkspaceMembership]:
    actor = membership_for_user(db, user)
    task = db.query(models.Task).filter_by(
        id=task_id, tenant_id=user.tenant_id, plant_id=user.plant_id,
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail='Task not found')
    visible = task.owner_membership_id == actor.id or task.delegated_by_membership_id == actor.id
    visible = visible or actor.role == 'admin' or task.owner_membership_id in descendants(db, actor)
    if not visible:
        raise HTTPException(status_code=403, detail='Task is outside your reporting scope')
    return task, actor


def create_task(
    db: Session, user: models.User, payload: TaskCreateRequest, source_run_id: str | None = None,
) -> models.Task:
    actor = membership_for_user(db, user)
    assignee = db.query(models.WorkspaceMembership).filter_by(
        id=payload.assignee_membership_id, tenant_id=user.tenant_id,
        default_plant_id=user.plant_id, status='active',
    ).first()
    if assignee is None:
        raise HTTPException(status_code=422, detail='Choose an active employee in this plant')
    if assignee.id != actor.id and actor.role != 'admin' and assignee.id not in descendants(db, actor):
        raise HTTPException(status_code=403, detail='You may delegate only inside your reporting hierarchy')
    parent = None
    if payload.parent_task_id:
        parent, _actor = task_for_actor(db, user, payload.parent_task_id)
    semantic_key = ':'.join([
        user.tenant_id, user.plant_id, payload.task_type,
        payload.context_entity_type or '-', payload.context_entity_id or '-', assignee.id,
    ])
    # The session disables autoflush. A completed task earlier in the same
    # canonical workflow must not be mistaken for an active duplicate.
    db.flush()
    existing = db.query(models.Task).filter(
        models.Task.tenant_id == user.tenant_id,
        models.Task.semantic_key == semantic_key,
        models.Task.status.in_(ACTIVE_TASK_STATES),
    ).first()
    if existing:
        return existing
    task = models.Task(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        title=payload.title, task_type=payload.task_type,
        requested_outcome=payload.requested_outcome, instructions=payload.instructions,
        owner_role=assignee.role, owner_user_id=assignee.user_id,
        owner_membership_id=assignee.id, parent_task_id=parent.id if parent else None,
        creator_membership_id=actor.id, delegated_by_membership_id=actor.id,
        assignment_source='agent' if source_run_id else 'manual',
        acceptance_status='pending', due_at=payload.due_at,
        status='open', severity='critical' if payload.priority == 'urgent' else 'action',
        priority=payload.priority, entity_type=payload.context_entity_type,
        entity_id=payload.context_entity_id, expected_output=payload.expected_output,
        source_agent_run_id=source_run_id,
        semantic_key=semantic_key,
    )
    try:
        with db.begin_nested():
            db.add(task)
            db.flush()
    except IntegrityError:
        existing = db.query(models.Task).filter(
            models.Task.tenant_id == user.tenant_id,
            models.Task.semantic_key == semantic_key,
            models.Task.status.in_(ACTIVE_TASK_STATES),
        ).first()
        if existing:
            return existing
        raise
    assignee_user = db.get(models.User, assignee.user_id)
    notification_key = f'task_assigned:{task.id}:{assignee.id}'
    db.add(models.Notification(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=assignee.user_id,
        title='New task assigned', body=f'{payload.title} was assigned by {user.name}.',
        status='unread', category='task_assigned', severity='action',
        membership_id=assignee.id, task_id=task.id,
        linked_entity_type=task.entity_type, linked_entity_id=task.entity_id,
        navigation_target=f'/agent?work_item={task.id}',
        dedupe_key=notification_key,
    ))
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, 'task.delegated',
        'task', task.id, actor_user_id=user.id,
        meta={'assignee_membership_id': assignee.id, 'assignee': assignee_user.name if assignee_user else assignee.role},
    )
    return task


def transition_task(
    db: Session, user: models.User, task_id: str, payload: TaskTransitionRequest,
) -> models.Task:
    task, actor = task_for_actor(db, user, task_id)
    is_assignee = task.owner_membership_id == actor.id
    is_manager = task.delegated_by_membership_id == actor.id or actor.role == 'admin'
    if payload.status == 'cancelled' and not is_manager:
        raise HTTPException(status_code=403, detail='Only the delegator or Admin can cancel this task')
    if payload.status != 'cancelled' and not is_assignee:
        raise HTTPException(status_code=403, detail='Only the assignee can update task execution')
    allowed = TRANSITIONS.get(task.status, set())
    if payload.status not in allowed:
        raise HTTPException(status_code=409, detail=f'Cannot move task from {task.status} to {payload.status}')
    previous = task.status
    task.status = payload.status
    task.acceptance_status = 'accepted' if payload.status in {'accepted', 'in_progress'} else task.acceptance_status
    if payload.status == 'accepted':
        task.accepted_at = utcnow()
    if payload.status == 'blocked':
        if not payload.blocker_reason:
            raise HTTPException(status_code=422, detail='A blocker reason is required')
        task.blocker_reason = payload.blocker_reason
    elif payload.status == 'in_progress':
        task.blocker_reason = None
    if payload.status == 'completed':
        if not payload.summary:
            raise HTTPException(status_code=422, detail='A completion summary is required')
        task.completion_summary = payload.summary
        task.completed_at = utcnow()
    if payload.status in {'completed', 'blocked'} and task.delegated_by_membership_id:
        manager_membership = db.get(models.WorkspaceMembership, task.delegated_by_membership_id)
        if manager_membership:
            db.add(models.Notification(
                tenant_id=user.tenant_id, plant_id=user.plant_id,
                user_id=manager_membership.user_id, membership_id=manager_membership.id,
                title='Task completed' if payload.status == 'completed' else 'Task blocked',
                body=payload.summary or payload.blocker_reason or task.title,
                status='unread', category='team_update' if payload.status == 'completed' else 'task_blocked',
                severity='info' if payload.status == 'completed' else 'critical',
                task_id=task.id, linked_entity_type=task.entity_type,
                linked_entity_id=task.entity_id, navigation_target=f'/agent?work_item={task.id}',
            ))
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, 'task.transitioned',
        'task', task.id, actor_user_id=user.id,
        meta={'from': previous, 'to': task.status, 'summary': payload.summary},
    )
    return task


def request_follow_up(
    db: Session, user: models.User, task_id: str, payload: TaskFollowUpRequest,
) -> models.Task:
    task, actor = task_for_actor(db, user, task_id)
    can_follow_up = actor.role == 'admin' or task.delegated_by_membership_id == actor.id
    can_follow_up = can_follow_up or task.owner_membership_id in descendants(db, actor)
    if not can_follow_up:
        raise HTTPException(status_code=403, detail='Only the delegator or reporting manager can request an update')
    if task.status not in ACTIVE_TASK_STATES:
        raise HTTPException(status_code=409, detail='This task is no longer active')
    task.last_follow_up_at = utcnow()
    task.next_follow_up_at = payload.next_follow_up_at
    if task.due_at and as_utc(task.due_at) < utcnow():
        task.escalation_level += 1
    dedupe_key = f'task_update:{task.id}:{task.last_follow_up_at.isoformat()}'
    db.add(models.Notification(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=task.owner_user_id,
        title='Task update requested',
        body=payload.message or f'{user.name} requested an update on {task.title}.',
        status='unread', category='action_required', severity='action',
        membership_id=task.owner_membership_id, task_id=task.id,
        linked_entity_type=task.entity_type, linked_entity_id=task.entity_id,
        navigation_target=f'/agent?work_item={task.id}', dedupe_key=dedupe_key,
    ))
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, 'task.follow_up_requested',
        'task', task.id, actor_user_id=user.id,
        meta={'next_follow_up_at': payload.next_follow_up_at.isoformat() if payload.next_follow_up_at else None,
              'escalation_level': task.escalation_level},
    )
    return task


def task_payload(db: Session, task: models.Task) -> dict:
    owner = db.get(models.User, task.owner_user_id) if task.owner_user_id else None
    delegator = None
    if task.delegated_by_membership_id:
        membership = db.get(models.WorkspaceMembership, task.delegated_by_membership_id)
        delegator = db.get(models.User, membership.user_id) if membership else None
    return {
        column.name: getattr(task, column.name) for column in task.__table__.columns
    } | {
        'owner_name': owner.name if owner else task.owner_role.replace('_', ' ').title(),
        'delegated_by_name': delegator.name if delegator else None,
        'is_overdue': bool(task.due_at and as_utc(task.due_at) < utcnow() and task.status in ACTIVE_TASK_STATES),
    }


def manager_summary(db: Session, user: models.User) -> list[dict]:
    actor = membership_for_user(db, user)
    report_ids = descendants(db, actor)
    if actor.role != 'admin' and not report_ids:
        return []
    query = db.query(models.Task).filter(
        models.Task.tenant_id == user.tenant_id,
        models.Task.plant_id == user.plant_id,
        models.Task.owner_membership_id.in_(report_ids or {actor.id}),
        models.Task.status.in_(ACTIVE_TASK_STATES),
    )
    return [task_payload(db, task) for task in query.order_by(models.Task.due_at.asc()).all()]


def run_internal_followups(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    missed = db.query(models.Commitment).filter(
        models.Commitment.status == 'active', models.Commitment.promised_at < now,
    ).limit(500).all()
    for commitment in missed:
        commitment.status = 'missed'
        existing_event = db.query(models.EventOutbox).filter_by(
            aggregate_type='commitments', aggregate_id=commitment.id,
            event_type='commitment.missed', aggregate_version=commitment.version,
        ).first()
        if existing_event is None:
            db.add(models.EventOutbox(
                tenant_id=commitment.tenant_id, plant_id=commitment.plant_id,
                event_type='commitment.missed', aggregate_type='commitments', aggregate_id=commitment.id,
                aggregate_version=commitment.version, correlation_id=f'commitment:{commitment.id}',
                payload={'objective_id': commitment.objective_id, 'task_id': commitment.task_id},
            ))
    if now.weekday() >= 5:
        return len(missed)
    due_soon = now + __import__('datetime').timedelta(hours=24)
    tasks = db.query(models.Task).filter(
        models.Task.status.in_(ACTIVE_TASK_STATES),
        models.Task.due_at.is_not(None),
        models.Task.due_at <= due_soon,
    ).limit(500).all()
    created = 0
    for task in tasks:
        if task.status == 'blocked' and task.blocker_reason:
            blocker = db.get(models.WorkspaceMembership, task.blocker_owner_membership_id) if task.blocker_owner_membership_id else None
            blocker_user = db.get(models.User, blocker.user_id) if blocker else None
            dedupe_key = f'blocker_owner:{task.id}:{task.version}'
            if blocker_user and not db.query(models.Notification).filter_by(tenant_id=task.tenant_id, dedupe_key=dedupe_key).first():
                db.add(models.Notification(
                    tenant_id=task.tenant_id, plant_id=task.plant_id, user_id=blocker_user.id,
                    membership_id=blocker.id, title='Dependency requires your action',
                    body=f'{task.title}: {task.blocker_reason}', status='unread', category='dependency_blocker',
                    severity='critical' if task.production_impact in {'high', 'critical'} else 'action',
                    task_id=task.id, linked_entity_type=task.entity_type, linked_entity_id=task.entity_id,
                    navigation_target=f'/agent?work_item={task.id}', dedupe_key=dedupe_key,
                ))
                created += 1
            continue
        category = 'task_overdue' if task.due_at and task.due_at < now else 'task_due_soon'
        existing = db.query(models.Notification).filter_by(
            tenant_id=task.tenant_id, dedupe_key=f'{category}:{task.id}',
        ).first()
        if existing or not task.owner_user_id:
            continue
        db.add(models.Notification(
            tenant_id=task.tenant_id, plant_id=task.plant_id,
            user_id=task.owner_user_id, membership_id=task.owner_membership_id,
            title='Task overdue' if category == 'task_overdue' else 'Task due soon',
            body=task.title, status='unread', category=category,
            severity='critical' if category == 'task_overdue' else 'action',
            task_id=task.id, linked_entity_type=task.entity_type,
            linked_entity_id=task.entity_id, navigation_target=f'/agent?work_item={task.id}',
            dedupe_key=f'{category}:{task.id}',
        ))
        task.next_follow_up_at = now + __import__('datetime').timedelta(hours=24)
        created += 1
    return len(missed) + created + run_procurement_followups(db, now)


def _parse_business_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _role_recipient(
    db: Session, tenant_id: str, plant_id: str | None, roles: tuple[str, ...],
) -> models.WorkspaceMembership | None:
    return db.query(models.WorkspaceMembership).filter(
        models.WorkspaceMembership.tenant_id == tenant_id,
        models.WorkspaceMembership.default_plant_id == plant_id,
        models.WorkspaceMembership.role.in_(roles),
        models.WorkspaceMembership.status == 'active',
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()


def _notify_once(
    db: Session, *, tenant_id: str, plant_id: str | None,
    recipient: models.WorkspaceMembership | None, category: str, severity: str,
    title: str, body: str, dedupe_key: str, entity_type: str,
    entity_id: str, navigation_target: str,
) -> int:
    if recipient is None or db.query(models.Notification).filter_by(
        tenant_id=tenant_id, dedupe_key=dedupe_key,
    ).first():
        return 0
    db.add(models.Notification(
        tenant_id=tenant_id, plant_id=plant_id, user_id=recipient.user_id,
        membership_id=recipient.id, title=title, body=body, status='unread',
        category=category, severity=severity, linked_entity_type=entity_type,
        linked_entity_id=entity_id, navigation_target=navigation_target,
        dedupe_key=dedupe_key,
    ))
    return 1


def run_procurement_followups(db: Session, now: datetime | None = None) -> int:
    """Create bounded, factual and deduplicated procurement exception notifications."""
    now = now or utcnow()
    today = now.date()
    created = 0

    for rfq in db.query(models.RFQ).filter(models.RFQ.status.in_(['published', 'responses_open'])).limit(500):
        deadline = _parse_business_date(rfq.deadline)
        if deadline is None or deadline > today + timedelta(days=2):
            continue
        received = db.query(models.SupplierQuote).filter_by(
            tenant_id=rfq.tenant_id, plant_id=rfq.plant_id, rfq_id=rfq.id,
        ).count()
        expected = len(rfq.supplier_ids or [])
        if expected and received < expected:
            requirement = db.get(models.PurchaseRequirement, rfq.requirement_id)
            recipient = db.get(models.WorkspaceMembership, requirement.owner_membership_id) if requirement and requirement.owner_membership_id else _role_recipient(db, rfq.tenant_id, rfq.plant_id, ('purchase_executive', 'purchase_manager'))
            created += _notify_once(
                db, tenant_id=rfq.tenant_id, plant_id=rfq.plant_id, recipient=recipient,
                category='quotation_deadline', severity='critical' if deadline < today else 'action',
                title='Supplier responses need follow-up',
                body=f'{rfq.business_number or "Supplier request"} has {received} of {expected} expected quotations; deadline {rfq.deadline}.',
                dedupe_key=f'quotation_deadline:{rfq.id}:v{rfq.version}:{received}',
                entity_type='rfqs', entity_id=rfq.id,
                navigation_target=f'/rfq-builder?rfq={rfq.id}',
            )

    for quote in db.query(models.SupplierQuote).filter_by(verification_status='needs_review').limit(500):
        recipient = _role_recipient(db, quote.tenant_id, quote.plant_id, ('purchase_manager',))
        created += _notify_once(
            db, tenant_id=quote.tenant_id, plant_id=quote.plant_id, recipient=recipient,
            category='extraction_review_pending', severity='action',
            title='Quotation evidence needs review',
            body=f'{quote.quote_number} has extracted fields awaiting human verification.',
            dedupe_key=f'extraction_review:{quote.id}:v{quote.version}',
            entity_type='supplier_quotes', entity_id=quote.id,
            navigation_target=f'/quotes?quote={quote.id}',
        )
    for quote in db.query(models.SupplierQuote).filter_by(verification_status='verified').limit(500):
        validity = _parse_business_date(quote.validity_date)
        if validity is None or validity < today or validity > today + timedelta(days=7):
            continue
        recipient = _role_recipient(db, quote.tenant_id, quote.plant_id, ('purchase_manager',))
        created += _notify_once(
            db, tenant_id=quote.tenant_id, plant_id=quote.plant_id, recipient=recipient,
            category='quote_validity_expiring', severity='action',
            title='Supplier quotation validity is expiring',
            body=f'{quote.quote_number} is valid through {quote.validity_date}.',
            dedupe_key=f'quote_validity:{quote.id}:v{quote.version}:{quote.validity_date}',
            entity_type='supplier_quotes', entity_id=quote.id,
            navigation_target=f'/quotes?quote={quote.id}',
        )

    approval_cutoff = now - timedelta(hours=8)
    for approval in db.query(models.ComparisonApprovalRequest).filter(
        models.ComparisonApprovalRequest.status == 'pending',
        models.ComparisonApprovalRequest.created_at <= approval_cutoff,
    ).limit(500):
        recipient = db.get(models.WorkspaceMembership, approval.assignee_membership_id)
        comparison = db.get(models.BidComparison, approval.comparison_id)
        created += _notify_once(
            db, tenant_id=approval.tenant_id, plant_id=approval.plant_id, recipient=recipient,
            category='approval_overdue', severity='critical',
            title='Supplier recommendation approval is overdue',
            body=f'{comparison.business_number if comparison else "Comparison"} is waiting for your decision.',
            dedupe_key=f'approval_overdue:{approval.id}:v{approval.version}',
            entity_type='bid_comparison', entity_id=approval.comparison_id,
            navigation_target=f'/approvals?comparison={approval.comparison_id}',
        )

    acknowledgement_cutoff = now - timedelta(hours=24)
    for po in db.query(models.PODraft).filter(
        models.PODraft.status.in_(['approved_pending_outbox', 'simulated_posted', 'posted']),
        models.PODraft.approved_at.is_not(None), models.PODraft.approved_at <= acknowledgement_cutoff,
    ).limit(500):
        acknowledged = db.query(models.SupplierAcknowledgement).filter_by(
            tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id,
        ).first()
        if acknowledged:
            continue
        recipient = _role_recipient(db, po.tenant_id, po.plant_id, ('purchase_manager',))
        created += _notify_once(
            db, tenant_id=po.tenant_id, plant_id=po.plant_id, recipient=recipient,
            category='po_acknowledgement_overdue', severity='critical',
            title='Supplier acknowledgement is overdue',
            body=f'{po.business_number or "Purchase order"} has no supplier acknowledgement after 24 hours.',
            dedupe_key=f'po_ack_overdue:{po.id}:v{po.version}', entity_type='po_drafts', entity_id=po.id,
            navigation_target=f'/po-drafts?po={po.id}',
        )

    for inspection in db.query(models.InspectionResult).filter(
        (models.InspectionResult.rejected_quantity > 0) | (models.InspectionResult.held_quantity > 0),
    ).limit(500):
        recipient = _role_recipient(db, inspection.tenant_id, inspection.plant_id, ('plant_manager', 'purchase_manager'))
        created += _notify_once(
            db, tenant_id=inspection.tenant_id, plant_id=inspection.plant_id, recipient=recipient,
            category='quality_exception', severity='critical',
            title='Quality disposition needs coordination',
            body=f'{inspection.business_number or "Inspection"}: {inspection.rejected_quantity:g} rejected and {inspection.held_quantity:g} held.',
            dedupe_key=f'quality_exception:{inspection.id}:v{inspection.version}:{inspection.rejected_quantity}:{inspection.held_quantity}',
            entity_type='inspection_results', entity_id=inspection.id,
            navigation_target=f'/quality?inspection={inspection.id}',
        )

    for event in db.query(models.IntegrationOutboxEvent).filter_by(status='failed').limit(500):
        recipient = _role_recipient(db, event.tenant_id, event.plant_id, ('admin', 'purchase_manager'))
        created += _notify_once(
            db, tenant_id=event.tenant_id, plant_id=event.plant_id, recipient=recipient,
            category='integration_failure', severity='critical',
            title='External-system synchronization failed',
            body=f'{event.action.replace("_", " ").title()} needs review. No success has been reported.',
            dedupe_key=f'integration_failure:{event.id}:v{event.version}:{event.retry_count}',
            entity_type='integration_outbox_events', entity_id=event.id,
            navigation_target=f'/outbox?outbox={event.id}',
        )
    return created
