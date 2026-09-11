
import hmac
import base64
import hashlib
import json
import secrets
from uuid import uuid4
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import (
    ADMIN,
    GATE_OPERATOR,
    PLANT_MANAGER,
    PURCHASE_EXECUTIVE,
    PURCHASE_MANAGER,
    QUALITY_INSPECTOR,
    STORE_MANAGER,
    require_role,
    workspace_capabilities,
)
from app.db import models
from app import documents as document_service
from app.domains.state_machine import ensure_transition
from app.identifiers import next_business_number
from app.repositories import get_scoped_or_404 as repository_get_scoped_or_404
from app.repositories import query_scoped as repository_query_scoped
from app.models import (
    AgentActionRequest,
    AgentActionResponse,
    AgentRecommendation,
    BidScore,
    ControlTowerSnapshot,
    EvidenceItem,
    NavItem,
    NextAction,
    WorkItem,
    WorkItemContext,
    ProcurementCase,
    QuoteComparisonRow,
    Role,
    RoleMetric,
    Severity,
    Task,
    TimelineEvent,
    WorkflowCycle,
    WorkflowStage,
    WorkloadBar,
    WorkspaceOverview,
    WorkflowStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def payload_hash(value: Any) -> str:
    """Hash strings and canonical structured payloads without type-dependent crashes."""
    encoded = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def normalized_payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def next_id(db: Session, model: type[models.Base], prefix: str) -> str:
    del db, model, prefix
    return str(uuid4())


def create_audit(
    db: Session,
    tenant_id: str,
    plant_id: str | None,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    result: str = "success",
    actor_user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> models.AuditEvent:
    audit = models.AuditEvent(
        id=next_id(db, models.AuditEvent, "AUD"),
        tenant_id=tenant_id,
        plant_id=plant_id,
        actor_user_id=actor_user_id,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        result=result,
        correlation_id=correlation_id or f"CORR-{secrets.token_hex(5).upper()}",
        payload_hash=payload_hash(f"{actor}:{action}:{entity_id}:{utcnow().isoformat()}"),
        meta=meta or {},
    )
    db.add(audit)
    return audit


def user_scope_query(db: Session, model: type[models.ScopedMixin], user: models.User):
    # Tenant administration does not bypass the explicitly selected plant.
    return repository_query_scoped(db, model, user)


def list_for_user(db: Session, model: type[models.ScopedMixin], user: models.User) -> list[Any]:
    return user_scope_query(db, model, user).all()


def get_scoped_or_404(db: Session, model: type[models.ScopedMixin], user: models.User, object_id: str, label: str | None = None):
    return repository_get_scoped_or_404(db, model, user, object_id, label)



def record_to_dict(record: Any | None) -> dict[str, Any] | None:
    if record is None:
        return None
    payload: dict[str, Any] = {}
    for column in record.__table__.columns:
        value = getattr(record, column.name)
        payload[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return payload


def records_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [record_to_dict(record) or {} for record in records]

def record_transition(db: Session, user: models.User, entity_type: str, entity_id: str, from_status: str | None, to_status: str, reason: str = "") -> models.WorkflowTransition:
    transition = models.WorkflowTransition(
        id=next_id(db, models.WorkflowTransition, "TRN"),
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=user.id,
        reason=reason,
    )
    db.add(transition)
    return transition


def record_approval(db: Session, user: models.User, entity_type: str, entity_id: str, decision: str, rationale: str = "") -> models.ApprovalDecision:
    existing = (
        user_scope_query(db, models.ApprovalDecision, user)
        .filter(models.ApprovalDecision.entity_type == entity_type, models.ApprovalDecision.entity_id == entity_id)
        .first()
    )
    if existing:
        return existing
    fingerprint = payload_hash(f"{user.id}:{entity_type}:{entity_id}:{decision}:{rationale}")
    approval = models.ApprovalDecision(
        id=next_id(db, models.ApprovalDecision, "APR"),
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        decision=decision,
        decided_by_user_id=user.id,
        rationale=rationale,
        immutable_hash=fingerprint,
    )
    db.add(approval)
    return approval


def create_supplier_portal_token(db: Session, user: models.User, rfq: models.RFQ, supplier_id: str) -> str:
    raw_token = secrets.token_urlsafe(32)
    token = models.SupplierPortalToken(
        id=next_id(db, models.SupplierPortalToken, "SPT"),
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        rfq_id=rfq.id,
        supplier_id=supplier_id,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        status="active",
        expires_at=utcnow() + timedelta(days=14),
        purpose="rfq_quote",
        entity_id=rfq.id,
    )
    db.add(token)
    return raw_token


def get_supplier_portal_token(db: Session, raw_token: str) -> models.SupplierPortalToken:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token = db.query(models.SupplierPortalToken).filter(models.SupplierPortalToken.token_hash == token_hash).first()
    if token is None or token.status != "active" or token.expires_at.replace(tzinfo=timezone.utc) < utcnow():
        raise HTTPException(status_code=404, detail="Supplier RFQ link is invalid or expired")
    return token


def sign_download_url(document: models.Document) -> str:
    expires_at = int((utcnow() + timedelta(minutes=5)).timestamp())
    payload = f"{document.id}:{expires_at}"
    signature = hmac.new(get_settings().session_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(f"{payload}:".encode("utf-8") + signature).decode("ascii")
    return f"/documents/{document.id}/content?token={token}"


def create_integration_outbox_event(
    db: Session,
    user: models.User,
    provider: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    approved: bool = False,
) -> models.IntegrationOutboxEvent:
    idempotency_key = f"{provider}:{action}:{entity_type}:{entity_id}"
    pending = next((
        item for item in db.new
        if isinstance(item, models.IntegrationOutboxEvent)
        and item.idempotency_key == idempotency_key
    ), None)
    if pending:
        return pending
    existing = user_scope_query(db, models.IntegrationOutboxEvent, user).filter(models.IntegrationOutboxEvent.idempotency_key == idempotency_key).first()
    if existing:
        return existing
    event = models.IntegrationOutboxEvent(
        id=next_id(db, models.IntegrationOutboxEvent, "IOE"),
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        provider=provider,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        status="approved" if approved else "pending_approval",
        idempotency_key=idempotency_key,
        correlation_id=f"ERP-{secrets.token_hex(5).upper()}",
        request_payload=payload,
        payload_diff={"local_payload": payload, "external_payload": {}},
        approved_by_user_id=user.id if approved else None,
        approved_at=utcnow() if approved else None,
    )
    db.add(event)
    return event



NAV_ITEMS = {
    "agent": NavItem(key="agent", href="/agent", label="My agent"),
    "control": NavItem(key="control", href="/control-centre", label="Team control"),
    "procurement": NavItem(key="procurement", href="/procurement", label="Requirements"),
    "approvals": NavItem(key="approvals", href="/approvals", label="Approvals"),
    "rfq": NavItem(key="rfq", href="/rfq-builder", label="RFQs"),
    "quotes": NavItem(key="quotes", href="/quotes", label="Quotations"),
    "evidence": NavItem(key="evidence", href="/evidence", label="Evidence review"),
    "comparison": NavItem(key="comparison", href="/comparison", label="Comparison & approvals"),
    "negotiations": NavItem(key="negotiations", href="/negotiations", label="Negotiations"),
    "po": NavItem(key="po", href="/po-drafts", label="Purchase orders"),
    "inbound": NavItem(key="inbound", href="/inbound", label="Inbound status"),
    "gate": NavItem(key="gate", href="/gate", label="Receive at gate"),
    "store": NavItem(key="store", href="/store", label="Store receipt"),
    "quality": NavItem(key="quality", href="/quality", label="Quality inspection"),
    "invoices": NavItem(key="invoices", href="/invoices", label="Invoices & matching"),
    "cases": NavItem(key="cases", href="/cases", label="My exceptions"),
    "outbox": NavItem(key="outbox", href="/outbox", label="External delivery"),
    "integrations": NavItem(key="integrations", href="/integrations", label="Integrations"),
    "audit": NavItem(key="audit", href="/audit", label="Audit ledger"),
    "admin": NavItem(key="admin", href="/admin", label="Admin workspace"),
    'setup': NavItem(key='setup', href='/workspace/setup', label='Workspace setup'),
}

ROLE_NAV_KEYS = {
    PLANT_MANAGER: ["procurement", "comparison", "approvals", "cases"],
    PURCHASE_EXECUTIVE: ["procurement", "rfq", "comparison", "cases"],
    PURCHASE_MANAGER: ["quotes", "evidence", "comparison", "approvals", "negotiations", "po", "invoices", "cases", "outbox"],
    GATE_OPERATOR: ["gate", "cases"],
    STORE_MANAGER: ["store", "cases"],
    QUALITY_INSPECTOR: ["quality", "cases"],
    ADMIN: ["control", "setup", "procurement", "rfq", "quotes", "evidence", "comparison", "approvals", "negotiations", "po", "inbound", "gate", "store", "quality", "invoices", "cases", "outbox", "integrations", "admin", "audit"],
}

DEFAULT_ROUTES = {
    PLANT_MANAGER: "/procurement",
    PURCHASE_EXECUTIVE: "/procurement",
    PURCHASE_MANAGER: "/quotes",
    GATE_OPERATOR: "/gate",
    STORE_MANAGER: "/store",
    QUALITY_INSPECTOR: "/quality",
    ADMIN: "/control-centre",
}

NAV_ITEMS['control'] = NavItem(key='control', href='/control-centre', label='My work')
for _role_key in (
    PLANT_MANAGER, PURCHASE_EXECUTIVE, PURCHASE_MANAGER,
    GATE_OPERATOR, STORE_MANAGER, QUALITY_INSPECTOR,
):
    if 'control' not in ROLE_NAV_KEYS[_role_key]:
        ROLE_NAV_KEYS[_role_key].insert(0, 'control')
for _role_key in DEFAULT_ROUTES:
    DEFAULT_ROUTES[_role_key] = '/control-centre'


ROLE_LABELS = {
    PLANT_MANAGER: "Plant Manager",
    PURCHASE_EXECUTIVE: "Purchase Executive",
    PURCHASE_MANAGER: "Purchase Manager",
    GATE_OPERATOR: "Gate Operator",
    STORE_MANAGER: "Store Manager",
    QUALITY_INSPECTOR: "Quality Inspector",
    ADMIN: "Admin",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace("_", " ").title())


def tasks_for_user(db: Session, user: models.User) -> list[models.Task]:
    query = user_scope_query(db, models.Task, user)
    if user.role != ADMIN:
        membership = (
            db.query(models.WorkspaceMembership)
            .filter_by(user_id=user.id, tenant_id=user.tenant_id, status="active")
            .first()
        )
        query = query.filter(
            or_(
                models.Task.owner_user_id == user.id,
                models.Task.owner_membership_id == (membership.id if membership else ""),
                and_(models.Task.shared_queue.is_(True), models.Task.owner_role == user.role),
            )
        )
    return query.order_by(models.Task.due_at.asc()).all()


def nav_for_user(user: models.User) -> list[NavItem]:
    my_work = {'control', 'procurement', 'rfq', 'quotes', 'comparison', 'po', 'gate', 'store', 'quality', 'admin'}
    keys = list(ROLE_NAV_KEYS.get(user.role, ['cases']))
    return [NAV_ITEMS[key].model_copy(update={'group': 'my_work' if key in my_work else 'process_records'}) for key in keys]


def metric(label: str, value: int | str, tone: str = "neutral", detail: str | None = None) -> RoleMetric:
    return RoleMetric(label=label, value=str(value).zfill(2) if isinstance(value, int) else value, tone=tone, detail=detail)


def presentation_severity(value: str | None) -> Severity:
    """Project richer V2 priorities into the stable V1 presentation contract."""
    normalized = (value or "action").casefold()
    if normalized in {"critical", "urgent"}:
        return Severity.CRITICAL
    if normalized in {"good", "healthy", "resolved", "completed"}:
        return Severity.GOOD
    if normalized in {"info", "normal", "low"}:
        return Severity.INFO
    return Severity.ACTION


def task_next_action(task: models.Task, db: Session, executable: bool = True) -> NextAction:
    path: str | None = None
    body: dict[str, Any] | None = None
    entity_version: int | None = None
    entity_models = {"supplier_quotes": models.SupplierQuote, "rfqs": models.RFQ, "award_decisions": models.AwardDecision, "po_drafts": models.PODraft, "cases": models.Case, "negotiation_rounds": models.NegotiationRound}
    if task.entity_id and task.entity_type in entity_models:
        entity = db.get(entity_models[task.entity_type], task.entity_id)
        entity_version = entity.version if entity else None
    if executable:
        if task.entity_type == "supplier_quotes" and task.entity_id:
            path = f"/procurement/quotes/{task.entity_id}/verify"
        elif task.entity_type == "rfqs" and task.entity_id:
            path = f"/procurement/rfqs/{task.entity_id}/publish"
        elif task.entity_type == "award_decisions" and task.entity_id:
            path = f"/procurement/awards/{task.entity_id}/approve"
        elif task.entity_type == "po_drafts" and task.entity_id:
            path = f"/procurement/po-drafts/{task.entity_id}/approve"
        elif task.entity_type == "negotiation_rounds" and task.entity_id:
            path = f"/procurement/negotiations/{task.entity_id}/approve"
        elif task.entity_type == "cases" and task.linked_case_id:
            path = "/agents/actions"
            body = {"agent_id": "agt-purchase-exec", "action": "create_follow_up_task", "context_id": task.linked_case_id}
    return NextAction(
        id=task.id,
        title=task.title,
        description=f"{role_label(task.owner_role)} · {task.status.replace('_', ' ')}",
        role=task.owner_role,
        severity=presentation_severity(task.severity),
        entity_type=task.entity_type,
        entity_id=task.entity_id,
        path=path,
        body=body,
        version=entity_version,
    )


def complete_tasks_for_entity(db: Session, user: models.User, entity_type: str, entity_id: str | None) -> None:
    if not entity_id:
        return
    tasks = (
        user_scope_query(db, models.Task, user)
        .filter(
            models.Task.entity_type == entity_type,
            models.Task.entity_id == entity_id,
            models.Task.status.in_(["open", "pending_approval"]),
        )
        .all()
    )
    for task in tasks:
        task.status = "completed"
        task.completed_at = utcnow()


def complete_case_tasks(db: Session, user: models.User, case_id: str | None, owner_role: str | None = None) -> None:
    if not case_id:
        return
    query = user_scope_query(db, models.Task, user).filter(
        models.Task.entity_type == "cases",
        or_(models.Task.entity_id == case_id, models.Task.linked_case_id == case_id),
        models.Task.status.in_(["open", "pending_approval"]),
    )
    if owner_role:
        query = query.filter(models.Task.owner_role == owner_role)
    for task in query.all():
        task.status = "completed"
        task.completed_at = utcnow()


def workflow_stages(db: Session, user: models.User, case_id: str | None = None) -> list[WorkflowStage]:
    case = get_scoped_or_404(db, models.Case, user, case_id, "Case") if case_id else user_scope_query(db, models.Case, user).order_by(models.Case.created_at.desc()).first()
    requirement = user_scope_query(db, models.PurchaseRequirement, user).filter(models.PurchaseRequirement.related_case_id == case.id).first() if case else None
    rfq = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id == requirement.id).first() if requirement else None
    quotes = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id == rfq.id).all() if rfq else []
    comparison = user_scope_query(db, models.BidComparison, user).filter(models.BidComparison.rfq_id == rfq.id).first() if rfq else None
    awards = user_scope_query(db, models.AwardDecision, user).filter(models.AwardDecision.rfq_id == rfq.id).all() if rfq else []
    award = awards[0] if awards else None
    award_ids = [item.id for item in awards]
    po = user_scope_query(db, models.PODraft, user).filter(models.PODraft.award_id.in_(award_ids or [""])).first() if awards else None
    gate = user_scope_query(db, models.GateEntry, user).filter(models.GateEntry.po_draft_id == po.id).first() if po else None
    receipt = user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.po_draft_id == po.id).first() if po else None
    inspection = user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.po_draft_id == po.id).first() if po else None
    pending_tasks = [task for task in user_scope_query(db, models.Task, user).filter(models.Task.linked_case_id == case.id if case else False).all() if task.status in {"open", "pending_approval"}]
    pending_by_entity = {task.entity_type: task for task in pending_tasks}

    stages = [
        WorkflowStage(key="requirement", label="Requirement", status="done" if requirement else "not_started", owner_role="purchase_executive", summary="Material need captured" if requirement else "No requirement"),
        WorkflowStage(key="rfq", label="RFQ", status="done" if rfq else "not_started", owner_role="purchase_executive", summary=rfq.status.replace("_", " ") if rfq else "Not started"),
        WorkflowStage(key="quotes", label="Quotes", status="current" if "supplier_quotes" in pending_by_entity else "done" if quotes else "not_started", owner_role="purchase_manager", summary=f"{len(quotes)} responses"),
        WorkflowStage(key="comparison", label="Comparison", status="done" if comparison and comparison.status == "approved" else "current" if comparison else "waiting" if quotes else "not_started", owner_role="purchase_manager", summary=comparison.status.replace("_", " ") if comparison else "Waiting for quotes"),
        WorkflowStage(key="award", label="Award", status="current" if "award_decisions" in pending_by_entity else "done" if award and award.status == "approved" else "waiting", owner_role="purchase_manager", summary="Manager approval required" if "award_decisions" in pending_by_entity else award.status.replace("_", " ") if award else "Waiting"),
        WorkflowStage(key="po", label="PO", status="done" if po and po.status in {"simulated_posted", "posted"} else "current" if po else "waiting", owner_role="purchase_manager", summary=po.status.replace("_", " ") if po else "Waiting for award"),
        WorkflowStage(key="inbound", label="Gate entry", status="done" if gate else "waiting", owner_role=GATE_OPERATOR, summary=gate.status.replace("_", " ") if gate else "Waiting for dispatch"),
        WorkflowStage(key="receipt", label="Receipt", status="done" if receipt else "waiting", owner_role="store_manager", summary=receipt.status.replace("_", " ") if receipt else "Not received"),
        WorkflowStage(key="inspection", label="Inspection", status="done" if inspection else "waiting", owner_role="quality_inspector", summary=inspection.status.replace("_", " ") if inspection else "Awaiting quality"),
        WorkflowStage(key="recovery", label="Recovery", status="blocked" if case and case.status not in {"closed", "resolved"} else "done", owner_role="purchase_executive", summary=case.status.replace("_", " ") if case else "No exception"),
    ]
    return stages


WORK_ITEM_DEFINITIONS = {
    'objectives': ('requirement', 'Clarify the procurement objective', 'Manager objective', '/procurement', 'Create a complete material requirement that can become an RFQ.', ['Objective, material, quantity, need-by date, and constraints'], ['explain_task', 'draft_rfq']),
    'purchase_requirements': ('requirement', 'Capture the material need', 'Requirement', '/procurement', 'Generate an RFQ that suppliers can respond to.', ['Item, quantity, need-by date'], ['draft_rfq']),
    'rfqs': ('rfq', 'Ask suppliers for prices', 'RFQ', '/rfq-builder', 'Release a clear request to the approved supplier shortlist.', ['Requirement and supplier shortlist'], ['draft_rfq']),
    'supplier_quotes': ('quotes', 'Review a supplier offer', 'Quotation verification', '/evidence', 'Create a verified offer that can safely enter comparison.', ['Supplier quotation and extracted field evidence'], ['extract_quote']),
    'bid_comparison': ('comparison', 'Review the supplier comparison', 'Bid comparison approval', '/comparison', 'Approve or reject the frozen comparison version.', ['Comparison PDF, verified quotes, and recommendation rationale'], ['explain_comparison']),
    'negotiation_rounds': ('negotiation', 'Improve commercial terms', 'Negotiation', '/negotiations', 'Record an approved supplier position for the next decision.', ['Comparison and supplier response'], ['draft_negotiation']),
    'award_decisions': ('award', 'Choose the supplier', 'Award', '/approvals', 'Authorize the selected supplier before an order is prepared.', ['Verified quote, comparison, and rationale'], ['explain_comparison']),
    'po_drafts': ('po', 'Prepare the purchase order', 'PO draft', '/po-drafts', 'Create an approved order event for controlled ERP dispatch.', ['Approved award and ERP mapping'], []),
    'gate_entries': ('inbound', 'Receive the vehicle at the gate', 'Gate entry', '/gate', 'Hand the admitted delivery to Stores for quantity receipt.', ['Issued PO, vehicle, and supplier challan'], ['lookup_purchase_order', 'prepare_gate_entry_checklist']),
    'store_receipts': ('inbound', 'Record the material received', 'Store receipt', '/store', 'Make the received quantity available for quality inspection.', ['Posted PO and received quantities'], []),
    'inspection_results': ('quality', 'Check the received material', 'Quality inspection', '/quality', 'Record accepted, rejected, and held quantities.', ['Store receipt and inspection result'], []),
    'cases': ('exception', 'Resolve the workflow problem', 'Exception case', '/cases', 'Remove the blocker with an auditable resolution.', ['Case evidence and resolution rationale'], ['create_follow_up_task', 'summarize_risks']),
    'outbox_messages': ('po', 'Send the approved record', 'External delivery', '/outbox', 'Deliver the approved record to the connected system.', ['Approval and destination details'], []),
}

WORK_ITEM_QUERY_KEYS = {
    'objectives': 'objective',
    'purchase_requirements': 'requirement', 'rfqs': 'rfq', 'supplier_quotes': 'quote', 'bid_comparison': 'comparison',
    'negotiation_rounds': 'negotiation', 'award_decisions': 'award', 'po_drafts': 'po',
    'gate_entries': 'gate', 'store_receipts': 'receipt', 'inspection_results': 'inspection', 'cases': 'case',
    'outbox_messages': 'outbox',
}


def work_item_from_task(task: models.Task, db: Session, user: models.User) -> WorkItem:
    fallback = ('exception', task.title, 'Assigned task', '/cases', 'Complete the assigned work so the workflow can continue.', ['Linked workflow record'], [])
    stage_key, goal, term, route, expected, evidence, capabilities = WORK_ITEM_DEFINITIONS.get(task.entity_type or '', fallback)
    query_key = WORK_ITEM_QUERY_KEYS.get(task.entity_type or '', 'task')
    query = [f'work_item={task.id}']
    if task.linked_case_id:
        query.append(f'cycle={task.linked_case_id}')
    if task.entity_id:
        query.append(f'{query_key}={task.entity_id}')
    consequential = task.entity_type in {'rfqs', 'award_decisions', 'po_drafts', 'negotiation_rounds', 'cases', 'outbox_messages'}
    human_action = {
        'purchase_requirements': 'Generate RFQ', 'rfqs': 'Review and publish RFQ',
        'supplier_quotes': 'Verify quotation', 'bid_comparison': 'Review comparison', 'negotiation_rounds': 'Review negotiation',
        'award_decisions': 'Review supplier award', 'po_drafts': 'Review purchase order',
        'gate_entries': 'Record gate entry', 'store_receipts': 'Record receipt', 'inspection_results': 'Record inspection',
        'cases': 'Review exception', 'outbox_messages': 'Review external dispatch',
    }.get(task.entity_type or '', 'Open task')
    status_label = task.status.replace('_', ' ')
    return WorkItem(
        id=task.id, title=task.title, plain_language_goal=goal, technical_term=term,
        why_now=f'This {term.lower()} is assigned to {role_label(task.owner_role)} and is currently {status_label}.',
        expected_result=expected, owner_role=task.owner_role,
        due_at=task.due_at.isoformat() if task.due_at else None,
        severity=presentation_severity(task.severity), status=task.status, cycle_id=task.linked_case_id,
        stage_key=stage_key, entity_type=task.entity_type, entity_id=task.entity_id,
        href=f'{route}?' + '&'.join(query), required_evidence=evidence,
        allowed_human_actions=[human_action], agent_capabilities=capabilities,
        requires_confirmation=consequential,
    )


def work_items_for_user(db: Session, user: models.User) -> list[WorkItem]:
    active = {'open', 'accepted', 'in_progress', 'blocked', 'review', 'pending_approval'}
    return [work_item_from_task(task, db, user) for task in tasks_for_user(db, user) if task.status in active]


def canonical_workflow_stages(db: Session, user: models.User, case_id: str | None = None) -> list[WorkflowStage]:
    case = get_scoped_or_404(db, models.Case, user, case_id, 'Case') if case_id else user_scope_query(db, models.Case, user).order_by(models.Case.created_at.desc()).first()
    requirement = user_scope_query(db, models.PurchaseRequirement, user).filter(models.PurchaseRequirement.related_case_id == case.id).first() if case else None
    rfq = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id == requirement.id).first() if requirement else None
    quotes = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id == rfq.id).all() if rfq else []
    comparison = user_scope_query(db, models.BidComparison, user).filter(models.BidComparison.rfq_id == rfq.id).first() if rfq else None
    award = user_scope_query(db, models.AwardDecision, user).filter(models.AwardDecision.rfq_id == rfq.id).first() if rfq else None
    po = user_scope_query(db, models.PODraft, user).filter(models.PODraft.award_id == award.id).first() if award else None
    gate = user_scope_query(db, models.GateEntry, user).filter(models.GateEntry.po_draft_id == po.id).first() if po else None
    receipt = user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.po_draft_id == po.id).first() if po else None
    inspection = user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.po_draft_id == po.id).first() if po else None

    def stage(key: str, plain: str, technical: str, owner: str, href: str, done: bool, ready: bool, summary: str, blocked_reason: str | None = None) -> WorkflowStage:
        status = 'done' if done else 'blocked' if blocked_reason else 'current' if ready else 'waiting'
        return WorkflowStage(key=key, label=f'{plain} ({technical})', plain_label=plain, technical_label=technical, status=status, owner_role=owner, summary=summary, href=href, blocked_reason=blocked_reason)

    rfq_summary = rfq.status.replace('_', ' ') if rfq else 'Waiting for the material need'
    comparison_summary = comparison.status.replace('_', ' ') if comparison else 'Waiting for verified offers'
    po_summary = po.status.replace('_', ' ') if po else 'Waiting for an approved supplier'
    inbound_summary = receipt.status.replace('_', ' ') if receipt else gate.status.replace('_', ' ') if gate else 'Waiting for a posted order'
    quality_summary = inspection.status.replace('_', ' ') if inspection else 'Waiting for store receipt'
    stages = [
        stage('requirement', 'Capture the material need', 'Requirement', PURCHASE_EXECUTIVE, '/procurement', bool(requirement), True, 'Material need captured' if requirement else 'Start by recording what the plant needs'),
        stage('rfq', 'Ask suppliers for prices', 'RFQ', PURCHASE_EXECUTIVE, '/rfq-builder', bool(rfq and rfq.status != 'draft'), bool(requirement), rfq_summary),
        stage('quotes', 'Upload and verify quotations', 'Quotation verification', PURCHASE_MANAGER, '/quotes', bool(quotes and all(item.verification_status == 'verified' for item in quotes)), bool(rfq), f'{len(quotes)} supplier response(s)'),
        stage('comparison', 'Compare and approve suppliers', 'Bid comparison', PURCHASE_MANAGER, '/comparison', bool(comparison and comparison.status == 'approved'), bool(quotes), comparison_summary),
        stage('po', 'Prepare the purchase order', 'Purchase order', PURCHASE_MANAGER, '/po-drafts', bool(po and po.status in {'approved_pending_outbox', 'simulated_posted', 'posted'}), bool(comparison and comparison.status == 'approved'), po_summary),
        stage('gate', 'Admit the delivery', 'Gate entry', GATE_OPERATOR, '/gate', bool(gate), bool(po and po.status in {'approved_pending_outbox', 'simulated_posted', 'posted'}), gate.status.replace('_', ' ') if gate else 'Waiting for a final PO'),
        stage('store', 'Record material receipt', 'Store receipt', STORE_MANAGER, '/store', bool(receipt), bool(gate), inbound_summary),
        stage('quality', 'Check received material', 'Quality inspection', QUALITY_INSPECTOR, '/quality', bool(inspection), bool(receipt), quality_summary),
    ]
    first_current = next((item for item in stages if item.status == 'current'), None)
    if first_current:
        for item in stages:
            if item is not first_current and item.status == 'current':
                item.status = 'waiting'
    return stages


def role_metrics(db: Session, user: models.User, user_tasks: list[models.Task]) -> list[RoleMetric]:
    all_tasks = user_scope_query(db, models.Task, user).all()
    open_cases = len([case for case in user_scope_query(db, models.Case, user).all() if case.status not in {"closed", "resolved"}])
    pending_approvals = len([task for task in all_tasks if task.status == "pending_approval"])
    quotes_need_review = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.verification_status == "needs_review").count()
    outbox_waiting = user_scope_query(db, models.OutboxMessage, user).filter(models.OutboxMessage.status == "approved_pending_send").count()
    receipts = user_scope_query(db, models.StoreReceipt, user).count()
    inspections = user_scope_query(db, models.InspectionResult, user).count()
    if user.role in {PLANT_MANAGER, ADMIN}:
        return [metric("Open exceptions", open_cases, "critical"), metric("Pending approvals", pending_approvals, "action"), metric("Open role tasks", len([task for task in all_tasks if task.status in {"open", "pending_approval"}]), "action"), metric("Outbox waiting", outbox_waiting, "good")]
    if user.role == PURCHASE_EXECUTIVE:
        return [metric("My open tasks", len([task for task in user_tasks if task.status == "open"]), "critical"), metric("RFQs to publish", user_scope_query(db, models.RFQ, user).filter(models.RFQ.status == "draft").count(), "action"), metric("My approvals", len([task for task in user_tasks if task.status == "pending_approval"]), "critical"), metric("Active RFQs", user_scope_query(db, models.RFQ, user).count(), "good")]
    if user.role == PURCHASE_MANAGER:
        return [metric("Quotes to verify", quotes_need_review, "critical"), metric("Comparisons", user_scope_query(db, models.BidComparison, user).count(), "action"), metric("PO drafts", user_scope_query(db, models.PODraft, user).count(), "action"), metric("Outbox waiting", outbox_waiting, "action")]
    if user.role == GATE_OPERATOR:
        entries = user_scope_query(db, models.GateEntry, user).count()
        issued_pos = user_scope_query(db, models.PODraft, user).filter(
            models.PODraft.status.in_(["approved_pending_outbox", "posted", "simulated_posted"])
        ).count()
        return [metric("Waiting vehicles", len([task for task in user_tasks if task.status == "open"]), "critical"), metric("Issued POs", issued_pos, "action"), metric("Gate entries", entries, "good"), metric("Exceptions", open_cases, "critical")]
    if user.role == STORE_MANAGER:
        shortages = user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.short_quantity > 0).count()
        return [metric("Receipts", receipts, "good"), metric("Shortages", shortages, "critical"), metric("Gate entries", user_scope_query(db, models.GateEntry, user).count(), "action"), metric("Open cases", open_cases, "critical")]
    if user.role == QUALITY_INSPECTOR:
        held_or_rejected = user_scope_query(db, models.InspectionResult, user).filter(or_(models.InspectionResult.rejected_quantity > 0, models.InspectionResult.held_quantity > 0)).count()
        return [metric("Inspections", inspections, "good"), metric("Held/rejected", held_or_rejected, "critical"), metric("Inventory impacts", user_scope_query(db, models.InventoryImpact, user).count(), "action"), metric("Open cases", open_cases, "critical")]
    return [metric("Assigned tasks", len(user_tasks), "action"), metric("Open cases", open_cases, "critical")]


def work_item_context(db: Session, user: models.User, work_item_id: str) -> WorkItemContext:
    item = next((row for row in work_items_for_user(db, user) if row.id == work_item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail='Work item is not in this role queue')
    entity_models = {
        'purchase_requirements': models.PurchaseRequirement, 'rfqs': models.RFQ,
        'supplier_quotes': models.SupplierQuote, 'negotiation_rounds': models.NegotiationRound,
        'bid_comparison': models.BidComparison, 'gate_entries': models.GateEntry,
        'award_decisions': models.AwardDecision, 'po_drafts': models.PODraft,
        'store_receipts': models.StoreReceipt, 'inspection_results': models.InspectionResult,
        'cases': models.Case, 'outbox_messages': models.OutboxMessage,
    }
    model = entity_models.get(item.entity_type or '')
    entity = get_scoped_or_404(db, model, user, item.entity_id, item.technical_term) if model and item.entity_id else None
    linked = {column.name: getattr(entity, column.name) for column in entity.__table__.columns} if entity else None
    documents = user_scope_query(db, models.Document, user).filter(models.Document.linked_entity_id == item.entity_id).all() if item.entity_id else []
    transition_type = {
        'supplier_quotes': 'supplier_quote', 'award_decisions': 'award_decision',
        'po_drafts': 'po_draft', 'negotiation_rounds': 'negotiation_round',
        'cases': 'case', 'rfqs': 'rfq',
    }.get(item.entity_type or '', item.entity_type or '')
    transitions = user_scope_query(db, models.WorkflowTransition, user).filter(
        models.WorkflowTransition.entity_type == transition_type,
        models.WorkflowTransition.entity_id == item.entity_id,
    ).order_by(models.WorkflowTransition.created_at.desc()).all() if item.entity_id else []
    agent = user_scope_query(db, models.AgentProfile, user).filter(models.AgentProfile.role == user.role).first()
    manager = db.get(models.User, agent.escalation_manager_id) if agent and agent.escalation_manager_id else None
    stages = canonical_workflow_stages(db, user, item.cycle_id)
    return WorkItemContext(
        work_item=item, stage=next((row for row in stages if row.key == item.stage_key), None),
        linked_object=linked,
        evidence_references=[{'id': row.id, 'filename': row.filename, 'status': row.status} for row in documents],
        timeline_references=[{'id': row.id, 'from_status': row.from_status, 'to_status': row.to_status, 'reason': row.reason} for row in transitions],
        permitted_agent_capabilities=[value for value in item.agent_capabilities if not agent or value in agent.allowed_actions],
        restricted_actions=agent.blocked_actions if agent else ['approve', 'post_to_erp', 'update_inventory', 'alter_master_data', 'close_exception'],
        escalation_owner=manager.name if manager else 'Authorized manager',
    )


def workspace_overview(db: Session, user: models.User) -> WorkspaceOverview:
    work_items = work_items_for_user(db, user)
    user_tasks = tasks_for_user(db, user)
    all_tasks = user_scope_query(db, models.Task, user).all()
    next_actions = role_specific_actions(db, user, user_tasks)
    waiting_tasks = [task for task in all_tasks if task.status in {"open", "pending_approval"} and not (task.owner_user_id == user.id or task.owner_role == user.role)]
    waiting_on = [task_next_action(task, db, False) for task in waiting_tasks[:5]]
    cases = user_scope_query(db, models.Case, user).all()
    stages = canonical_workflow_stages(db, user, cases[0].id if cases else None)
    active_stage = next((stage for stage in reversed(stages) if stage.status in {"blocked", "current"}), stages[0])
    next_step = next_actions[0].title if next_actions else f"Waiting on {role_label(waiting_on[0].role)}" if waiting_on else "No immediate action required"
    current_owner_role = next_actions[0].role if next_actions else waiting_on[0].role if waiting_on else active_stage.owner_role or user.role
    active_stage = next((stage for stage in stages if stage.status == 'current'), next((stage for stage in stages if stage.status == 'blocked'), stages[0]))
    team_workload: list[WorkloadBar] = []
    team_queue: list[Task] = []
    if user.role in {PLANT_MANAGER, ADMIN}:
        open_tasks = [task for task in all_tasks if task.status in {"open", "pending_approval"}]
        total = max(1, len(open_tasks))
        for role in [PURCHASE_EXECUTIVE, PURCHASE_MANAGER, STORE_MANAGER, QUALITY_INSPECTOR]:
            count = len([task for task in open_tasks if task.owner_role == role])
            team_workload.append(WorkloadBar(label=role_label(role), value=count, total=total, tone="critical" if count else "good"))
        team_queue = [task_to_schema(task, db) for task in open_tasks]
    cycle = WorkflowCycle(
        id=cases[0].id if cases else "cycle-rm-304",
        title=cases[0].title if cases else "Line shaft bearing sleeve workflow",
        subtitle=cases[0].requirement if cases else "Material need to recovery workflow",
        current_stage=active_stage.label,
        current_owner_role=current_owner_role,
        next_step=next_step,
        severity=Severity(cases[0].severity) if cases else Severity.ACTION,
        due_label="Today 17:00" if cases else "No due date",
        stages=stages,
    )
    capabilities = workspace_capabilities(db, user)
    navigation = nav_for_user(user)
    if (
        'workspace.view_setup' in capabilities
        and not any(item.key == 'setup' for item in navigation)
    ):
        navigation.insert(1, NAV_ITEMS['setup'].model_copy(update={'group': 'my_work'}))
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status='active',
    ).first()
    delegated_rows = db.query(models.Task).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        delegated_by_membership_id=membership.id if membership else None,
    ).order_by(models.Task.due_at.asc()).limit(20).all()
    delegated_tasks = [{
        'id': task.id, 'title': task.title, 'status': task.status,
        'priority': task.priority, 'owner_role': task.owner_role,
        'owner_membership_id': task.owner_membership_id,
        'due_at': task.due_at.isoformat() if task.due_at else None,
        'blocker_reason': task.blocker_reason,
        'last_follow_up_at': task.last_follow_up_at.isoformat() if task.last_follow_up_at else None,
        'escalation_level': task.escalation_level,
        'entity_type': task.entity_type, 'entity_id': task.entity_id,
    } for task in delegated_rows]
    notification_rows = db.query(models.Notification).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id,
    ).order_by(models.Notification.created_at.desc()).limit(8).all()
    notifications = [{
        'id': item.id, 'title': item.title, 'body': item.body,
        'status': item.status, 'created_at': item.created_at.isoformat(),
    } for item in notification_rows]
    tenant = db.get(models.Tenant, user.tenant_id)
    profile = db.query(models.AgentProfile).filter_by(
        tenant_id=user.tenant_id, membership_id=membership.id if membership else None,
    ).first()
    assistant_enabled = bool(
        get_settings().agent_enabled and tenant and tenant.agent_enabled
        and profile and profile.enabled
    )
    assistant_status = {
        'enabled': assistant_enabled,
        'mode': 'groq' if assistant_enabled and bool(get_settings().groq_api_key) else 'limited',
        'model': profile.model_profile if profile else None,
        'normal_workflows_available': True,
    }
    target_memberships: list[models.WorkspaceMembership] = []
    if membership:
        all_memberships = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=user.tenant_id, default_plant_id=user.plant_id, status='active',
        ).all()
        if membership.role == ADMIN:
            target_memberships = [row for row in all_memberships if row.id != membership.id]
        else:
            frontier = {membership.id}
            seen: set[str] = set()
            while frontier:
                direct = [
                    row for row in all_memberships
                    if row.manager_membership_id in frontier and row.id not in seen
                ]
                frontier = {row.id for row in direct}
                seen.update(frontier)
                target_memberships.extend(direct)
    delegation_targets = []
    for target in target_memberships:
        target_user = db.get(models.User, target.user_id)
        delegation_targets.append({
            'membership_id': target.id,
            'name': target_user.name if target_user else role_label(target.role),
            'role': target.role,
            'manager_membership_id': target.manager_membership_id,
        })
    return WorkspaceOverview(
        role=Role(user.role),
        default_route=DEFAULT_ROUTES.get(user.role, "/cases"),
        nav_items=navigation,
        capabilities=capabilities,
        metrics=role_metrics(db, user, user_tasks),
        cycles=[cycle],
        next_actions=next_actions,
        work_items=work_items,
        waiting_on=waiting_on,
        team_workload=team_workload,
        team_queue=team_queue,
        delegated_tasks=delegated_tasks,
        notifications=notifications,
        assistant_status=assistant_status,
        delegation_targets=delegation_targets,
    )

def task_to_schema(task: models.Task, db: Session) -> Task:
    owner = db.get(models.User, task.owner_user_id) if task.owner_user_id else None
    due_label = "No due date"
    ageing = "0d"
    if task.due_at:
        due_label = "Today" if task.due_at.date() <= utcnow().date() else task.due_at.strftime("%d %b")
        ageing_days = max(0, (utcnow().date() - task.created_at.date()).days)
        ageing = f"{ageing_days}d"
    return Task(
        id=task.id,
        title=task.title,
        owner_role=Role(task.owner_role),
        owner_name=owner.name if owner else task.owner_role.replace("_", " ").title(),
        due_label=due_label,
        ageing_label=ageing,
        status=WorkflowStatus(task.status),
        severity=presentation_severity(task.severity),
        linked_case_id=task.linked_case_id or "",
    )


def calculate_landed_cost(line: Any) -> tuple[float, float]:
    breakdown = landed_cost_breakdown(line)
    if float(getattr(line, "quantity")) <= 0:
        raise ValueError("Quantity must be positive")
    return breakdown["net_landed_unit_cost"], breakdown["total_net_landed_cost"]


def landed_cost_breakdown(line: Any) -> dict[str, float]:
    quantity = float(getattr(line, "quantity"))
    base_cost = round(float(getattr(line, "unit_price")) * quantity, 2)
    gst = round(base_cost * float(getattr(line, "gst_rate", 0) or 0) / 100, 2)
    tax_recoverable = bool(getattr(line, "tax_recoverable", True))
    explicit_nonrecoverable = float(getattr(line, "nonrecoverable_tax", 0) or 0)
    nonrecoverable = round(explicit_nonrecoverable + (0 if tax_recoverable else gst), 2)
    freight = round(float(getattr(line, "freight", 0) or 0), 2)
    packaging = round(float(getattr(line, "packaging", 0) or 0), 2)
    total = round(base_cost + freight + packaging + nonrecoverable, 2)
    return {
        "base_cost": base_cost,
        "freight": freight,
        "packaging": packaging,
        "recoverable_tax": gst if tax_recoverable else 0,
        "nonrecoverable_tax": nonrecoverable,
        "total_net_landed_cost": total,
        "net_landed_unit_cost": round(total / quantity, 2) if quantity else 0,
    }


def comparison_rows(db: Session, rfq_id: str, user: models.User) -> list[QuoteComparisonRow]:
    rows: list[QuoteComparisonRow] = []
    for score in compare_quotes(db, rfq_id, user):
        quote = db.get(models.SupplierQuote, score.quote_id)
        rows.append(
            QuoteComparisonRow(
                supplier=score.supplier_name,
                landed_cost_label=f"Rs. {score.net_landed_unit_cost:.2f}/kg",
                delivery_status="On time" if score.delivery_compliant else "Late against need-by",
                quality_score_label=f"{score.quality_score}%",
                commercial_terms=quote.payment_terms if quote else "",
                decision=score.recommendation,
                severity=Severity.CRITICAL if score.disqualified else Severity.GOOD if score.recommendation == "Recommended" else Severity.ACTION,
                disqualification_reason="; ".join(score.reasons) if score.disqualified else None,
            )
        )
    return rows


# Production hardening overrides: scoped workflow services.

def need_by_to_deadline(need_by_date: str) -> str:
    try:
        return (date.fromisoformat(need_by_date) - timedelta(days=3)).isoformat()
    except ValueError:
        return need_by_date


def create_requirement(
    db: Session, user: models.User, item_id: str, quantity: float, need_by_date: str,
    source: str = "manual", uom: str | None = None, title: str | None = None,
    lines: list[dict[str, Any]] | None = None, reason: str = "",
    assignee_membership_id: str | None = None, source_thread_id: str | None = None,
    source_run_id: str | None = None, correlation_id: str | None = None,
) -> models.PurchaseRequirement:
    require_role(user, PLANT_MANAGER, PURCHASE_EXECUTIVE, ADMIN)
    requested_lines = lines or [{"item_id": item_id, "quantity": quantity, "need_by_date": need_by_date, "uom": uom}]
    if not requested_lines:
        raise HTTPException(status_code=422, detail="At least one requirement line is required")
    resolved: list[tuple[models.Item, dict[str, Any]]] = []
    for line in requested_lines:
        if float(line.get("quantity", 0)) <= 0:
            raise HTTPException(status_code=422, detail="Requirement quantities must be positive")
        resolved.append((get_scoped_or_404(db, models.Item, user, str(line["item_id"]), "Item"), line))
    item = resolved[0][0]
    summary = "; ".join(f"{float(line['quantity']):g} {line.get('uom') or resolved_item.uom_id} {resolved_item.name}" for resolved_item, line in resolved)
    executive_membership = db.query(models.WorkspaceMembership).filter_by(
        id=assignee_membership_id, tenant_id=user.tenant_id, default_plant_id=user.plant_id,
        role=PURCHASE_EXECUTIVE, status="active",
    ).first() if assignee_membership_id else None
    if assignee_membership_id and executive_membership is None:
        raise HTTPException(status_code=422, detail="Choose an active Purchase Executive in this plant")
    executive = db.get(models.User, executive_membership.user_id) if executive_membership else (
        user if user.role == PURCHASE_EXECUTIVE else db.query(models.User).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, role=PURCHASE_EXECUTIVE, is_active=True
        ).first()
    )
    if executive is None:
        raise HTTPException(status_code=409, detail="An active Purchase Executive is required before creating a requirement")
    executive_membership = executive_membership or db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=executive.id, status="active"
    ).first()
    creator_membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active"
    ).first()
    case = models.Case(id=next_id(db, models.Case, "CASE"), business_number=next_business_number(db, "CASE", user), tenant_id=user.tenant_id, plant_id=user.plant_id, title=title or f"{item.name} purchase requirement", requirement=f"{summary} needed by {need_by_date}", supplier="Supplier not awarded", owner_role=PURCHASE_EXECUTIVE, owner_user_id=executive.id, due_at=utcnow() + timedelta(days=2), value_amount=0, currency="INR", status="requirement_created", severity="action", timeline=[{"title": "Requirement created", "time": utcnow().strftime("%H:%M"), "actor": user.name, "body": reason or "Material need captured for procurement execution."}], evidence=[{"label": "Material", "value": resolved_item.name, "source": "manual", "meta": resolved_item.erp_item_code} for resolved_item, _line in resolved])
    db.add(case)
    requirement = models.PurchaseRequirement(
        id=next_id(db, models.PurchaseRequirement, "REQ"), business_number=next_business_number(db, "REQ", user),
        tenant_id=user.tenant_id, plant_id=user.plant_id, source=source, item_id=item.id,
        quantity=sum(float(line["quantity"]) for _, line in resolved), uom=uom or item.uom_id,
        need_by_date=min(str(line["need_by_date"]) for _, line in resolved), reason=reason,
        status="approved", owner_user_id=executive.id,
        owner_membership_id=executive_membership.id if executive_membership else None,
        created_by_membership_id=creator_membership.id if creator_membership else None,
        source_thread_id=source_thread_id, source_run_id=source_run_id,
        correlation_id=correlation_id, related_case_id=case.id,
    )
    db.add(requirement)
    db.flush()
    case.requirement_id = requirement.id
    for resolved_item, line in resolved:
        specification = user_scope_query(db, models.ItemSpecification, user).filter(models.ItemSpecification.item_id == resolved_item.id).first()
        db.add(models.PurchaseRequirementLine(id=next_id(db, models.PurchaseRequirementLine, "REQL"), business_number=next_business_number(db, "REQL", user), tenant_id=user.tenant_id, plant_id=user.plant_id, requirement_id=requirement.id, item_id=resolved_item.id, quantity=float(line["quantity"]), uom=str(line.get("uom") or resolved_item.uom_id), need_by_date=str(line["need_by_date"]), specification=str(line.get("specification") or (specification.description if specification else "")), inspection_required=bool(line.get("inspection_required", specification.inspection_required if specification else True))))
    db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id, title="Prepare and publish supplier RFQ", owner_role=PURCHASE_EXECUTIVE, owner_user_id=executive.id, owner_membership_id=executive_membership.id if executive_membership else None, due_at=utcnow() + timedelta(hours=4), status="open", severity="action", linked_case_id=case.id, entity_type="purchase_requirements", entity_id=requirement.id))
    record_transition(db, user, "purchase_requirement", requirement.id, None, "approved", "Material need accepted")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "requirement.created", "purchase_requirement", requirement.id, actor_user_id=user.id)
    return requirement


def supplier_compliance_readiness(
    db: Session, user: models.User, supplier: models.Supplier, item_ids: set[str] | None = None,
) -> dict[str, Any]:
    item_ids = item_ids or set()
    requirements = user_scope_query(db, models.SupplierComplianceRequirement, user).filter(
        models.SupplierComplianceRequirement.active.is_(True),
        models.SupplierComplianceRequirement.mandatory.is_(True),
    ).all()
    requirements = [row for row in requirements if row.item_id is None or row.item_id in item_ids]
    certificates = user_scope_query(db, models.SupplierCertificate, user).filter_by(supplier_id=supplier.id).all()
    today = date.today()
    valid: list[str] = []
    missing: list[str] = []
    expired: list[str] = []
    pending: list[str] = []
    requirement_states: list[dict[str, str]] = []
    for requirement in requirements:
        matches = [row for row in certificates if row.certificate_type.strip().casefold() == requirement.certificate_type.strip().casefold()]
        verified = []
        for certificate in matches:
            try:
                within_dates = (not certificate.valid_from or date.fromisoformat(certificate.valid_from) <= today) and date.fromisoformat(certificate.expires_on) >= today
            except ValueError:
                within_dates = False
            if certificate.status == "verified" and within_dates:
                verified.append(certificate)
        if verified:
            valid.append(requirement.certificate_type); state = "verified"
        elif any(row.status == "pending_review" for row in matches):
            pending.append(requirement.certificate_type); state = "pending_review"
        elif matches:
            expired.append(requirement.certificate_type); state = "expired_or_rejected"
        else:
            missing.append(requirement.certificate_type); state = "missing"
        requirement_states.append({"certificate_type": requirement.certificate_type, "status": state})
    return {
        "supplier_id": supplier.id, "supplier_name": supplier.name,
        "eligible": supplier.status != "blocked" and not (missing or expired or pending),
        "required": [row.certificate_type for row in requirements],
        "valid": valid, "missing": missing, "expired": expired, "pending": pending,
        "requirements": requirement_states,
    }


_create_requirement_base = create_requirement


def create_requirement(
    db: Session, user: models.User, item_id: str, quantity: float, need_by_date: str,
    source: str = 'manual', uom: str | None = None, title: str | None = None,
    lines: list[dict[str, Any]] | None = None, reason: str = '',
    assignee_membership_id: str | None = None, source_thread_id: str | None = None,
    source_run_id: str | None = None, correlation_id: str | None = None,
) -> models.PurchaseRequirement:
    return _create_requirement_base(
        db, user, item_id, quantity, need_by_date, source, uom, title, lines, reason,
        assignee_membership_id, source_thread_id, source_run_id, correlation_id,
    )


def create_rfq_from_requirement(db: Session, user: models.User, requirement_id: str) -> models.RFQ:
    require_role(user, PURCHASE_EXECUTIVE, ADMIN)
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, requirement_id, "Requirement")
    existing = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id == requirement.id).first()
    if existing:
        return existing
    requirement_lines = user_scope_query(db, models.PurchaseRequirementLine, user).filter(models.PurchaseRequirementLine.requirement_id == requirement.id).all()
    if not requirement_lines:
        requirement_lines = [models.PurchaseRequirementLine(id="legacy", tenant_id=user.tenant_id, plant_id=user.plant_id, requirement_id=requirement.id, item_id=requirement.item_id, quantity=requirement.quantity, uom=requirement.uom, need_by_date=requirement.need_by_date, specification="", inspection_required=True)]
    item_ids = {line.item_id for line in requirement_lines}
    suppliers = []
    for supplier in user_scope_query(db, models.Supplier, user).filter(models.Supplier.status.in_(["approved", "conditional"])).all():
        capable = {row.item_id for row in user_scope_query(db, models.SupplierItemCapability, user).filter(models.SupplierItemCapability.supplier_id == supplier.id, models.SupplierItemCapability.approved.is_(True)).all()}
        if item_ids.issubset(capable) and supplier_compliance_readiness(db, user, supplier, item_ids)["eligible"]:
            suppliers.append(supplier)
    if not suppliers:
        raise HTTPException(status_code=400, detail="No approved supplier capability exists for this material")
    rfq = models.RFQ(id=next_id(db, models.RFQ, "RFQ"), business_number=next_business_number(db, "RFQ", user), tenant_id=user.tenant_id, plant_id=user.plant_id, requirement_id=requirement.id, status="draft", deadline=need_by_to_deadline(min(line.need_by_date for line in requirement_lines)), supplier_ids=[supplier.id for supplier in suppliers])
    db.add(rfq)
    db.flush()
    for requirement_line in requirement_lines:
        spec = user_scope_query(db, models.ItemSpecification, user).filter(models.ItemSpecification.item_id == requirement_line.item_id).first()
        db.add(models.RFQLine(id=next_id(db, models.RFQLine, "RFQL"), business_number=next_business_number(db, "RFQL", user), tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id, requirement_line_id=None if requirement_line.id == "legacy" else requirement_line.id, item_id=requirement_line.item_id, description=requirement_line.specification or (spec.description if spec else "Requirement line"), quantity=requirement_line.quantity, uom=requirement_line.uom, need_by_date=requirement_line.need_by_date, required_certificates=spec.required_certificates if spec else []))
    for supplier in suppliers:
        db.add(models.RFQSupplierInvitation(id=next_id(db, models.RFQSupplierInvitation, "INVITE"), tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id, supplier_id=supplier.id, status="pending"))
    linked_case = get_scoped_or_404(db, models.Case, user, requirement.related_case_id, "Case")
    linked_case.rfq_id = rfq.id
    requirement.status = "rfq_drafted"
    complete_tasks_for_entity(db, user, "purchase_requirements", requirement.id)
    db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id, title="Review PDF and publish RFQ", owner_role=PURCHASE_EXECUTIVE, owner_user_id=user.id, due_at=utcnow() + timedelta(hours=6), status="open", severity="action", linked_case_id=requirement.related_case_id, entity_type="rfqs", entity_id=rfq.id))
    record_transition(db, user, "rfq", rfq.id, None, "draft", "Generated from approved requirement")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "rfq.created", "rfq", rfq.id, actor_user_id=user.id)
    return rfq

def publish_rfq(db: Session, user: models.User, rfq_id: str) -> dict:
    require_role(user, PURCHASE_EXECUTIVE, ADMIN)
    rfq = get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    if rfq.status == "published":
        outbox_ids = [msg.id for msg in user_scope_query(db, models.OutboxMessage, user).all() if msg.meta.get("rfq_id") == rfq.id]
        return {"rfq_id": rfq.id, "status": rfq.status, "outbox_ids": outbox_ids}
    if rfq.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft RFQs can be published")
    rfq_item_ids = {line.item_id for line in user_scope_query(db, models.RFQLine, user).filter_by(rfq_id=rfq.id).all()}
    noncompliant = []
    for supplier_id in rfq.supplier_ids:
        supplier = get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
        readiness = supplier_compliance_readiness(db, user, supplier, rfq_item_ids)
        if not readiness["eligible"]:
            noncompliant.append({"supplier": supplier.name, "missing": readiness["missing"], "expired": readiness["expired"], "pending": readiness["pending"]})
    if noncompliant:
        raise HTTPException(status_code=409, detail={"message": "Supplier compliance must be current before sending this request", "suppliers": noncompliant})
    from_status = rfq.status
    ensure_transition("rfq", from_status, "published")
    rfq.status = "published"
    rfq.published_at = utcnow()
    from app.procurement_v2 import generate_artifact
    artifact = generate_artifact(db, user, "rfq", rfq.id, final=True)
    outbox_ids: list[str] = []
    portal_links: list[dict[str, str]] = []
    for supplier_id in rfq.supplier_ids:
        supplier = get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
        contact = user_scope_query(db, models.SupplierContact, user).filter(models.SupplierContact.supplier_id == supplier_id).first()
        if not contact:
            continue
        raw_token = create_supplier_portal_token(db, user, rfq, supplier_id)
        portal_url = f"{get_settings().web_base_url.rstrip('/')}/supplier/portal?token={raw_token}"
        invitation = user_scope_query(db, models.RFQSupplierInvitation, user).filter(models.RFQSupplierInvitation.rfq_id == rfq.id, models.RFQSupplierInvitation.supplier_id == supplier_id).first()
        if invitation:
            invitation.status = "sent"
            invitation.sent_at = utcnow()
        portal_links.append({"supplier_id": supplier_id, "token": raw_token})
        idempotency_key = f"rfq:{rfq.id}:{supplier_id}:publish"
        outbox = user_scope_query(db, models.OutboxMessage, user).filter(models.OutboxMessage.idempotency_key == idempotency_key).first()
        if outbox is None:
            outbox = models.OutboxMessage(id=next_id(db, models.OutboxMessage, "OUT"), tenant_id=user.tenant_id, plant_id=user.plant_id, channel="email", recipient=contact.email, subject=f"RFQ {rfq.business_number or rfq.id} for {supplier.name}", body=f"Please review the attached supplier request and respond securely: {portal_url}", status="approved_pending_send", payload_hash=payload_hash(f"{rfq.id}:{supplier_id}"), correlation_id=f"MSG-{secrets.token_hex(4).upper()}", idempotency_key=idempotency_key, approved_by_user_id=user.id, approved_at=utcnow(), attachment_document_ids=[artifact.document_id], meta={"rfq_id": rfq.id, "supplier_id": supplier_id, "portal_token_preview": raw_token[:8], "portal_url": portal_url, "artifact_id": artifact.id})
            db.add(outbox)
        outbox_ids.append(outbox.id)
    complete_tasks_for_entity(db, user, "rfqs", rfq.id)
    record_approval(db, user, "rfq", rfq.id, "approved", "Supplier RFQ communication approved")
    record_transition(db, user, "rfq", rfq.id, from_status, "published", "Supplier outbox and portal links created")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "rfq.publish.email_approved", "rfq", rfq.id, actor_user_id=user.id, meta={"outbox_ids": outbox_ids})
    return {"rfq_id": rfq.id, "status": rfq.status, "outbox_ids": outbox_ids, "supplier_portal_links": portal_links, "artifact_id": artifact.id}


def _add_quote_lines_and_verifications(
    db: Session,
    quote: models.SupplierQuote,
    rfq_lines: list[models.RFQLine],
    payload: dict[str, Any],
    source: str,
    confidence: float,
) -> list[dict[str, Any]]:
    supplied_lines = payload.get("lines") or [payload.get("line") or payload]
    supplied_lines = [line for line in supplied_lines if isinstance(line, dict) and line]
    known_line_ids = {line.id for line in rfq_lines}
    known_item_ids = {line.item_id for line in rfq_lines}
    seen_targets: set[str] = set()
    for line in supplied_lines:
        explicit_line_id = line.get("rfq_line_id")
        explicit_item_id = line.get("item_id")
        if explicit_line_id and explicit_line_id not in known_line_ids:
            raise HTTPException(status_code=422, detail="Quoted line does not belong to this supplier request")
        if explicit_item_id and explicit_item_id not in known_item_ids:
            raise HTTPException(status_code=422, detail="Quoted material does not belong to this supplier request")
        target = str(explicit_line_id or explicit_item_id or "")
        if target and target in seen_targets:
            raise HTTPException(status_code=422, detail="A supplier-request line may only be quoted once per revision")
        seen_targets.add(target)
    evidence: list[dict[str, Any]] = []
    created_lines: list[models.QuoteLine] = []
    for index, rfq_line in enumerate(rfq_lines):
        line_payload = next((item for item in supplied_lines if item.get("rfq_line_id") == rfq_line.id or item.get("item_id") == rfq_line.item_id), supplied_lines[index] if index < len(supplied_lines) and not (supplied_lines[index].get("rfq_line_id") or supplied_lines[index].get("item_id")) else None)
        if line_payload is None:
            continue
        quoted_quantity = float(line_payload.get("quantity") or rfq_line.quantity)
        if quoted_quantity <= 0 or quoted_quantity > rfq_line.quantity:
            raise HTTPException(status_code=422, detail="Quoted quantity must be positive and cannot exceed the requested quantity")
        gst_rate = float(line_payload.get("gst_rate", 18))
        tax_policy = db.query(models.TaxPolicy).filter_by(
            tenant_id=quote.tenant_id,
            plant_id=quote.plant_id,
            tax_code=f"GST{gst_rate:g}",
        ).first()
        tax_recoverable = bool(line_payload.get("tax_recoverable", tax_policy.recoverable if tax_policy else True))
        quote_line = models.QuoteLine(
            id=next_id(db, models.QuoteLine, "QL"), business_number=next_business_number(db, "QL", quote), tenant_id=quote.tenant_id,
            plant_id=quote.plant_id, quote_id=quote.id, rfq_line_id=rfq_line.id, item_id=rfq_line.item_id,
            quantity=quoted_quantity, uom=str(line_payload.get("uom") or rfq_line.uom),
            unit_price=float(line_payload.get("unit_price", 0)), gst_rate=gst_rate,
            freight=float(line_payload.get("freight", 0)), packaging=float(line_payload.get("packaging", 0)),
            lead_time_days=int(line_payload.get("lead_time_days", 0)), promised_date=str(line_payload.get("promised_date") or rfq_line.need_by_date),
            moq=float(line_payload.get("moq") or rfq_line.quantity), technical_compliance=str(line_payload.get("technical_compliance", "compliant")),
            certificates=list(line_payload.get("certificates", [])), tax_recoverable=tax_recoverable,
            nonrecoverable_tax=float(line_payload.get("nonrecoverable_tax", 0)), deviation_notes=str(line_payload.get("deviation_notes", "")),
        )
        db.add(quote_line)
        created_lines.append(quote_line)
        for field in ["unit_price", "promised_date", "certificates"]:
            raw_value = getattr(quote_line, field)
            field_name = f"line:{quote_line.id}:{field}"
            evidence.append({"field": field_name, "source": source, "original_text": str(raw_value), "confidence": confidence, "verification_status": "needs_review"})
            db.add(models.QuoteFieldVerification(id=next_id(db, models.QuoteFieldVerification, "QFV"), tenant_id=quote.tenant_id, plant_id=quote.plant_id, quote_id=quote.id, field_name=field_name, extracted_value=str(raw_value), confidence=confidence, source=source, status="needs_review"))
    for field in ["quote_number", "quote_date", "validity_date", "payment_terms"]:
        raw_value = getattr(quote, field)
        evidence.append({"field": field, "source": source, "original_text": str(raw_value), "confidence": confidence, "verification_status": "needs_review"})
        db.add(models.QuoteFieldVerification(id=next_id(db, models.QuoteFieldVerification, "QFV"), tenant_id=quote.tenant_id, plant_id=quote.plant_id, quote_id=quote.id, field_name=field, extracted_value=str(raw_value), confidence=confidence, source=source, status="needs_review"))
    return evidence


def receive_supplier_quote(db: Session, token: str, payload: dict[str, Any]) -> models.SupplierQuote:
    portal_token = get_supplier_portal_token(db, token)
    if portal_token.purpose != "rfq_quote":
        raise HTTPException(status_code=404, detail="Supplier RFQ link is invalid or expired")
    rfq = db.query(models.RFQ).filter_by(id=portal_token.rfq_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id).first()
    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if rfq.status not in {"published", "responses_open"}:
        raise HTTPException(status_code=409, detail="RFQ is not accepting responses")
    rfq_lines = db.query(models.RFQLine).filter_by(rfq_id=rfq.id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id).all()
    if not rfq_lines:
        raise HTTPException(status_code=400, detail="RFQ has no lines")
    previous = db.query(models.SupplierQuote).filter_by(
        rfq_id=rfq.id, supplier_id=portal_token.supplier_id,
        tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
    ).filter(models.SupplierQuote.verification_status != "superseded").order_by(models.SupplierQuote.revision_number.desc()).first()
    revision_number = (previous.revision_number + 1) if previous else 1
    quote = models.SupplierQuote(id=next_id(db, models.SupplierQuote, "Q"), business_number=next_business_number(db, "QUOTE", portal_token), tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id, rfq_id=rfq.id, supplier_id=portal_token.supplier_id, quote_number=str(payload.get("quote_number") or f"SUP-{secrets.token_hex(3).upper()}"), quote_date=str(payload.get("quote_date") or date.today().isoformat()), validity_date=str(payload.get("validity_date") or (date.today() + timedelta(days=30)).isoformat()), payment_terms=str(payload.get("payment_terms") or "30 days"), parser_version="supplier-portal@2.0", model_version="deterministic@2.0", verification_status="needs_review", revision_number=revision_number, supersedes_quote_id=previous.id if previous else None, participation_status="complete", currency=str(payload.get("currency") or "INR").upper(), exchange_rate_to_inr=float(payload.get("exchange_rate_to_inr") or 1))
    db.add(quote)
    db.flush()
    evidence = _add_quote_lines_and_verifications(db, quote, rfq_lines, payload, "supplier_portal", 0.86)
    db.flush()
    submitted_lines = db.query(models.QuoteLine).filter_by(quote_id=quote.id).all()
    requested_by_id = {line.id: line.quantity for line in rfq_lines}
    quote.participation_status = "complete" if (
        len(submitted_lines) == len(rfq_lines)
        and all(line.rfq_line_id and line.quantity == requested_by_id[line.rfq_line_id] for line in submitted_lines)
    ) else "partial"
    if previous:
        previous.verification_status = "superseded"
    db.add(models.QuoteExtractionRun(id=next_id(db, models.QuoteExtractionRun, "EXT"), tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id, quote_id=quote.id, document_id=None, parser_version="supplier-portal@1.0", model_version="deterministic@1.0", status="needs_review", evidence=evidence, extracted_fields=payload))
    portal_token.used_at = utcnow()
    invitation = db.query(models.RFQSupplierInvitation).filter_by(
        tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        rfq_id=rfq.id, supplier_id=portal_token.supplier_id,
    ).first()
    if invitation:
        invitation.status = "responded"
    # The scoped link remains active until expiry so the supplier can submit an
    # immutable revision. `used_at` records first/last use without consuming it.
    rfq.status = "responses_open"
    requirement = db.query(models.PurchaseRequirement).filter_by(id=rfq.requirement_id, tenant_id=rfq.tenant_id, plant_id=rfq.plant_id).first()
    manager_membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=portal_token.tenant_id, default_plant_id=portal_token.plant_id,
        role=PURCHASE_MANAGER, status="active",
    ).first()
    db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id, title=f"Verify quotation {quote.quote_number}", owner_role=PURCHASE_MANAGER, owner_user_id=manager_membership.user_id if manager_membership else None, owner_membership_id=manager_membership.id if manager_membership else None, shared_queue=manager_membership is None, due_at=utcnow() + timedelta(hours=4), status="open", severity="action", linked_case_id=requirement.related_case_id if requirement else None, entity_type="supplier_quotes", entity_id=quote.id))
    create_audit(db, portal_token.tenant_id, portal_token.plant_id, "Supplier Portal", "quote.received", "supplier_quote", quote.id, meta={"rfq_id": rfq.id, "supplier_id": portal_token.supplier_id, "revision_number": revision_number, "supersedes_quote_id": previous.id if previous else None, "participation_status": quote.participation_status})
    return quote


def _coerce_verified_value(current: Any, value: Any) -> Any:
    if isinstance(current, bool):
        return value if isinstance(value, bool) else str(value).lower() in {"true", "1", "yes"}
    if isinstance(current, float):
        return float(value)
    if isinstance(current, int):
        return int(value)
    if isinstance(current, list):
        return value if isinstance(value, list) else [item.strip() for item in str(value).split(",") if item.strip()]
    return str(value)


def verify_quote_fields(db: Session, user: models.User, quote_id: str, decisions: list[dict[str, Any]] | None = None) -> models.SupplierQuote:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    quote = get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote")
    rows = user_scope_query(db, models.QuoteFieldVerification, user).filter(models.QuoteFieldVerification.quote_id == quote.id).all()
    by_name = {row.field_name: row for row in rows}
    quote_line = user_scope_query(db, models.QuoteLine, user).filter(models.QuoteLine.quote_id == quote.id).first()
    decisions = decisions or []
    if not decisions:
        raise HTTPException(status_code=422, detail="At least one field verification decision is required")
    for decision in decisions:
        field_name = str(decision.get("field_name", ""))
        verification = by_name.get(field_name)
        if verification is None:
            raise HTTPException(status_code=422, detail=f"Unknown verification field {field_name}")
        action = decision.get("decision")
        if action not in {"accept", "correct", "reject"}:
            raise HTTPException(status_code=422, detail=f"Invalid decision for {field_name}")
        if action == "correct":
            if decision.get("verified_value") is None:
                raise HTTPException(status_code=422, detail=f"Corrected value is required for {field_name}")
            target_field = field_name
            target = quote if hasattr(quote, field_name) else None
            if field_name.startswith("line:"):
                try:
                    _prefix, line_id, target_field = field_name.split(":", 2)
                except ValueError:
                    raise HTTPException(status_code=422, detail=f"Invalid quote line field {field_name}")
                target = get_scoped_or_404(db, models.QuoteLine, user, line_id, "Quote line")
                if target.quote_id != quote.id:
                    raise HTTPException(status_code=422, detail=f"Field {field_name} is not part of this quote")
            elif target is None and quote_line and hasattr(quote_line, field_name):
                target = quote_line
            if target is None:
                raise HTTPException(status_code=422, detail=f"Field {field_name} cannot be corrected")
            corrected = _coerce_verified_value(getattr(target, target_field), decision["verified_value"])
            setattr(target, target_field, corrected)
            verification.verified_value = str(corrected)
        elif action == "accept":
            verification.verified_value = verification.extracted_value
        verification.status = "rejected" if action == "reject" else "verified"
        verification.verified_by_user_id = user.id
        verification.verified_at = utcnow()

    quote_lines = user_scope_query(db, models.QuoteLine, user).filter(models.QuoteLine.quote_id == quote.id).all()
    dynamic_fields = {f"line:{line.id}:{field}" for line in quote_lines for field in ("unit_price", "promised_date", "certificates")}
    required_fields = {"payment_terms"} | dynamic_fields
    if not dynamic_fields.issubset(by_name):  # Seeded/legacy single-line evidence.
        required_fields = {"unit_price", "promised_date", "payment_terms", "certificates"}
    statuses = {row.field_name: row.status for row in rows}
    if any(field_status == "rejected" for field_status in statuses.values()):
        quote.verification_status = "rejected"
    elif required_fields.issubset(statuses) and all(statuses[field] == "verified" for field in required_fields):
        quote.verification_status = "verified"
    else:
        quote.verification_status = "needs_review"
    extraction = user_scope_query(db, models.QuoteExtractionRun, user).filter(models.QuoteExtractionRun.quote_id == quote.id).first()
    if extraction:
        extraction.status = quote.verification_status
        extraction.evidence = [
            {**item, "verification_status": statuses.get(item.get("field"), item.get("verification_status", "needs_review"))}
            for item in extraction.evidence
        ]
    if quote.verification_status in {"verified", "rejected"}:
        complete_tasks_for_entity(db, user, "supplier_quotes", quote.id)
    record_transition(db, user, "supplier_quote", quote.id, "needs_review", quote.verification_status, "Buyer reviewed quote fields")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "quote.fields_reviewed", "supplier_quote", quote.id, actor_user_id=user.id, meta={"decisions": [item.get("field_name") for item in decisions], "status": quote.verification_status})
    return quote


def verify_quote(db: Session, user: models.User, quote_id: str) -> models.SupplierQuote:
    quote = get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote")
    decisions = [
        {"field_name": row.field_name, "decision": "accept"}
        for row in user_scope_query(db, models.QuoteFieldVerification, user).filter(
            models.QuoteFieldVerification.quote_id == quote.id,
            models.QuoteFieldVerification.status == "needs_review",
        ).all()
    ]
    return verify_quote_fields(db, user, quote_id, decisions)

def compare_quotes(db: Session, rfq_id: str, user: models.User | None = None) -> list[BidScore]:
    if user:
        rfq = get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
        rfq_lines = user_scope_query(db, models.RFQLine, user).filter(models.RFQLine.rfq_id == rfq.id).all()
        quotes = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id == rfq.id, models.SupplierQuote.verification_status != "superseded").all()
    else:
        rfq = db.get(models.RFQ, rfq_id)
        if rfq is None:
            raise KeyError(f"Unknown RFQ {rfq_id}")
        rfq_lines = db.query(models.RFQLine).filter(models.RFQLine.rfq_id == rfq.id, models.RFQLine.tenant_id == rfq.tenant_id, models.RFQLine.plant_id == rfq.plant_id).all()
        quotes = db.query(models.SupplierQuote).filter(models.SupplierQuote.rfq_id == rfq.id, models.SupplierQuote.verification_status != "superseded").all()
    if not rfq_lines:
        return []
    rfq_by_id = {line.id: line for line in rfq_lines}
    quote_lines: list[tuple[models.SupplierQuote, models.QuoteLine, models.RFQLine]] = []
    for quote in quotes:
        for line in db.query(models.QuoteLine).filter_by(quote_id=quote.id, tenant_id=quote.tenant_id, plant_id=quote.plant_id).all():
            rfq_line = rfq_by_id.get(line.rfq_line_id or "") or next((item for item in rfq_lines if item.item_id == line.item_id), None)
            if rfq_line:
                quote_lines.append((quote, line, rfq_line))
    observations = {
        row.id: row for row in db.query(models.ExchangeRateObservation).filter(
            models.ExchangeRateObservation.tenant_id == rfq.tenant_id,
            models.ExchangeRateObservation.plant_id == rfq.plant_id,
            models.ExchangeRateObservation.status == "verified",
        ).all()
    }

    def verified_fx(quote: models.SupplierQuote) -> float | None:
        if quote.currency.upper() == "INR":
            return 1.0
        observation = observations.get(quote.exchange_rate_observation_id or "")
        if not observation or observation.source_currency.upper() != quote.currency.upper() or observation.target_currency.upper() != "INR":
            return None
        return observation.rate

    anchors = {
        rfq_line.id: min(
            [landed_cost_breakdown(line)["net_landed_unit_cost"] * fx for quote, line, matched in quote_lines if matched.id == rfq_line.id and (fx := verified_fx(quote)) is not None] or [0]
        )
        for rfq_line in rfq_lines
    }
    results: list[BidScore] = []
    for quote, line, rfq_line in quote_lines:
        supplier = db.query(models.Supplier).filter_by(id=quote.supplier_id, tenant_id=quote.tenant_id, plant_id=quote.plant_id).first()
        if supplier is None or line is None:
            continue
        quality_events = user_scope_query(db, models.SupplierPerformanceEvent, user).filter_by(
            supplier_id=supplier.id, metric_type="quality_acceptance"
        ).all() if user else []
        evidence_quality_score = round(
            sum(event.numerator for event in quality_events) / sum(event.denominator for event in quality_events) * 100, 2
        ) if quality_events and sum(event.denominator for event in quality_events) else supplier.quality_score
        breakdown = landed_cost_breakdown(line)
        verified_rate = verified_fx(quote)
        fx = verified_rate if verified_rate is not None else 1.0
        breakdown = {key: round(value * fx, 2) for key, value in breakdown.items()}
        net_unit, total = breakdown["net_landed_unit_cost"], breakdown["total_net_landed_cost"]
        try:
            delivery_compliant = date.fromisoformat(line.promised_date) <= date.fromisoformat(rfq_line.need_by_date)
        except ValueError:
            delivery_compliant = False
        technical_compliant = line.technical_compliance == "compliant" and all(cert in line.certificates for cert in rfq_line.required_certificates)
        reasons: list[str] = []
        if supplier.status == "blocked":
            reasons.append("Supplier is blocked")
        compliance = supplier_compliance_readiness(db, user, supplier, {rfq_line.item_id}) if user else {"eligible": True, "missing": [], "expired": [], "pending": []}
        if not compliance["eligible"]:
            gaps = compliance["missing"] + compliance["expired"] + compliance["pending"]
            reasons.append(f"Supplier compliance is incomplete: {', '.join(gaps)}")
        if quote.verification_status != "verified":
            reasons.append("Commercial fields still need buyer verification")
        if verified_rate is None:
            reasons.append(f"{quote.currency.upper()} conversion rate lacks verified source evidence")
        if not delivery_compliant:
            reasons.append("Promised delivery misses mandatory need-by date")
        if not technical_compliant:
            reasons.append("Mandatory certificate or technical compliance is missing")
        if line.moq > rfq_line.quantity:
            reasons.append("MOQ exceeds requirement quantity")
        disqualified = bool(reasons)
        cost_score = max(0, 100 - max(0, net_unit - anchors[rfq_line.id]) * 4)
        delivery_score = 100 if delivery_compliant else 20
        technical_score = 100 if technical_compliant else 0
        score = round((cost_score * 0.38) + (delivery_score * 0.24) + (evidence_quality_score * 0.16) + (technical_score * 0.12) + (supplier.delivery_score * 0.10), 2)
        rate_evidence = observations.get(quote.exchange_rate_observation_id or "")
        results.append(BidScore(quote_id=quote.id, quote_line_id=line.id, rfq_line_id=rfq_line.id, supplier_id=supplier.id, supplier_name=supplier.name, net_landed_unit_cost=net_unit, total_net_landed_cost=total, delivery_compliant=delivery_compliant, technical_compliant=technical_compliant, quality_score=evidence_quality_score, delivery_score=supplier.delivery_score, score=score, disqualified=disqualified, reasons=reasons or ["Meets mandatory delivery, verification, and certificate rules"], recommendation="Disqualified" if disqualified else "Review", base_cost=breakdown["base_cost"], freight=breakdown["freight"], packaging=breakdown["packaging"], recoverable_tax=breakdown["recoverable_tax"], nonrecoverable_tax=breakdown["nonrecoverable_tax"], offered_quantity=line.quantity, requested_quantity=rfq_line.quantity, source_currency=quote.currency.upper(), exchange_rate_to_inr=fx, exchange_rate_source=rate_evidence.source_name if rate_evidence else ("Canonical INR" if quote.currency.upper() == "INR" else None), exchange_rate_observed_at=rate_evidence.observed_at.isoformat() if rate_evidence else None, score_components={"cost": round(cost_score * 0.38, 2), "delivery": round(delivery_score * 0.24, 2), "quality": round(evidence_quality_score * 0.16, 2), "technical": round(technical_score * 0.12, 2), "history": round(supplier.delivery_score * 0.10, 2), "quality_evidence_events": len(quality_events)}))
    line_order = {line.id: index for index, line in enumerate(rfq_lines)}
    sorted_results = sorted(results, key=lambda result: (line_order.get(result.rfq_line_id or "", 999), result.disqualified, -result.score, result.net_landed_unit_cost))
    for rfq_line in rfq_lines:
        candidates = [result for result in sorted_results if result.rfq_line_id == rfq_line.id and not result.disqualified]
        if candidates:
            candidates[0].recommendation = "Recommended"
    if user:
        comparison = user_scope_query(db, models.BidComparison, user).filter(models.BidComparison.rfq_id == rfq_id).first()
        if comparison:
            rows = [score.model_dump() for score in sorted_results]
            comparison.rows = rows
            comparison.recommended_supplier_id = next((row["supplier_id"] for row in rows if row["recommendation"] == "Recommended"), None)
    return sorted_results


def generate_comparison(db: Session, user: models.User, rfq_id: str) -> models.BidComparison:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    rfq = get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    quotations = user_scope_query(db, models.SupplierQuote, user).filter(
        models.SupplierQuote.rfq_id == rfq.id,
        models.SupplierQuote.verification_status != "superseded",
    ).all()
    unverified = [quote for quote in quotations if quote.verification_status != "verified"]
    if unverified:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Verify every eligible supplier quotation before generating the comparison",
                "quote_ids": [quote.id for quote in unverified],
            },
        )
    scores = compare_quotes(db, rfq.id, user)
    if not scores:
        raise HTTPException(status_code=400, detail="At least one quote is required before comparison")
    rows = [score.model_dump() for score in scores]
    recommended_scores = [score for score in scores if score.recommendation == "Recommended"]
    recommended = recommended_scores[0] if recommended_scores else None
    rationale = (
        f"{recommended.supplier_name} has the highest eligible weighted score "
        f"({recommended.score:.1f}) at a net landed unit cost of "
        f"{recommended.net_landed_unit_cost:.2f}; delivery, technical, quality, and supplier-history gates were applied."
        if recommended else
        "No supplier currently satisfies every mandatory eligibility gate."
    )
    comparison = user_scope_query(db, models.BidComparison, user).filter(models.BidComparison.rfq_id == rfq.id).first()
    if comparison is None:
        comparison = models.BidComparison(id=next_id(db, models.BidComparison, "CMP"), business_number=next_business_number(db, "CMP", user), tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id, status="draft", rows=rows, recommended_supplier_id=recommended.supplier_id if recommended else None, recommendation_rationale=rationale)
        db.add(comparison)
    else:
        if comparison.status in {"approved", "partially_approved", "ready_for_approval"}:
            comparison.comparison_version += 1
            db.query(models.ComparisonApprovalRequest).filter_by(
                tenant_id=user.tenant_id, comparison_id=comparison.id, status="pending"
            ).update({models.ComparisonApprovalRequest.status: "superseded"}, synchronize_session=False)
        comparison.status = "draft"
        comparison.rows = rows
        comparison.recommended_supplier_id = recommended.supplier_id if recommended else None
        comparison.recommendation_rationale = rationale
    rfq_line_ids = {line.id for line in user_scope_query(db, models.RFQLine, user).filter(models.RFQLine.rfq_id == rfq.id).all()}
    if {score.rfq_line_id for score in recommended_scores} != rfq_line_ids:
        comparison.status = "no_eligible_supplier"
    record_transition(db, user, "bid_comparison", comparison.id, None, comparison.status, "Comparison generated")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "comparison.generated", "rfq", rfq.id, actor_user_id=user.id, meta={"recommended_supplier_id": comparison.recommended_supplier_id})
    return comparison


def create_negotiation(db: Session, user: models.User, rfq_id: str, supplier_id: str, target: str, drafted_message: str) -> models.NegotiationRound:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    rfq = get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
    round_number = user_scope_query(db, models.NegotiationRound, user).filter(models.NegotiationRound.rfq_id == rfq.id, models.NegotiationRound.supplier_id == supplier_id).count() + 1
    negotiation = models.NegotiationRound(id=next_id(db, models.NegotiationRound, "NEG"), business_number=next_business_number(db, "NEG", user), tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id, supplier_id=supplier_id, round_number=round_number, target=target, drafted_message=drafted_message, status="draft", revised_unit_price=None)
    db.add(negotiation)
    db.flush()
    db.add(models.NegotiationMessage(id=next_id(db, models.NegotiationMessage, "NMSG"), tenant_id=user.tenant_id, plant_id=user.plant_id, negotiation_id=negotiation.id, direction="outbound", message_type="proposal", body=drafted_message, commercial_terms={"target": target}, status="draft"))
    create_audit(db, user.tenant_id, user.plant_id, user.name, "negotiation.created", "negotiation_round", negotiation.id, actor_user_id=user.id)
    return negotiation


def submit_negotiation(db: Session, user: models.User, negotiation_id: str) -> models.NegotiationRound:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    negotiation = get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation")
    if negotiation.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft negotiations can be submitted")
    ensure_transition("negotiation", negotiation.status, "pending_approval")
    negotiation.status = "pending_approval"
    rfq = get_scoped_or_404(db, models.RFQ, user, negotiation.rfq_id, "RFQ")
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, rfq.requirement_id, "Requirement")
    db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id, title="Approve negotiation message", owner_role=PURCHASE_MANAGER, owner_user_id=None, due_at=utcnow() + timedelta(hours=2), status="pending_approval", severity="action", linked_case_id=requirement.related_case_id, entity_type="negotiation_rounds", entity_id=negotiation.id))
    record_transition(db, user, "negotiation_round", negotiation.id, "draft", "pending_approval", "Buyer submitted negotiation")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "negotiation.submitted", "negotiation_round", negotiation.id, actor_user_id=user.id)
    return negotiation


def approve_negotiation(db: Session, user: models.User, negotiation_id: str) -> models.NegotiationRound:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    negotiation = get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation")
    if negotiation.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Negotiation is not pending approval")
    supplier = get_scoped_or_404(db, models.Supplier, user, negotiation.supplier_id, "Supplier")
    contact = user_scope_query(db, models.SupplierContact, user).filter(models.SupplierContact.supplier_id == supplier.id).first()
    if contact is None:
        raise HTTPException(status_code=409, detail="Supplier contact is required")
    message = user_scope_query(db, models.NegotiationMessage, user).filter(models.NegotiationMessage.negotiation_id == negotiation.id, models.NegotiationMessage.direction == "outbound").first()
    ensure_transition("negotiation", negotiation.status, "manager_approved")
    negotiation.status = "manager_approved"
    if message:
        message.status = "approved"
        message.approved_by_user_id = user.id
    outbox = models.OutboxMessage(id=next_id(db, models.OutboxMessage, "OUT"), tenant_id=user.tenant_id, plant_id=user.plant_id, channel="email", recipient=contact.email, subject=f"Negotiation for RFQ {negotiation.rfq_id}", body=negotiation.drafted_message, status="approved_pending_send", payload_hash=payload_hash(negotiation.drafted_message), correlation_id=f"MSG-{secrets.token_hex(5).upper()}", idempotency_key=f"negotiation:{negotiation.id}:send", approved_by_user_id=user.id, approved_at=utcnow(), meta={"negotiation_id": negotiation.id})
    db.add(outbox)
    record_approval(db, user, "negotiation_round", negotiation.id, "approved", negotiation.target)
    complete_tasks_for_entity(db, user, "negotiation_rounds", negotiation.id)
    record_transition(db, user, "negotiation_round", negotiation.id, "pending_approval", "manager_approved", "Manager approved negotiation")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "negotiation.approved", "negotiation_round", negotiation.id, actor_user_id=user.id, meta={"outbox_id": outbox.id})
    return negotiation


def record_negotiation_counteroffer(db: Session, user: models.User, negotiation_id: str, revised_unit_price: float, message_body: str, commercial_terms: dict[str, Any]) -> models.NegotiationRound:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    negotiation = get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation")
    if negotiation.status != "manager_approved":
        raise HTTPException(status_code=409, detail="Counteroffer requires an approved outbound negotiation")
    if revised_unit_price <= 0:
        raise HTTPException(status_code=422, detail="Revised unit price must be positive")
    ensure_transition("negotiation", negotiation.status, "supplier_countered")
    negotiation.status = "supplier_countered"
    negotiation.revised_unit_price = revised_unit_price
    db.add(models.NegotiationMessage(id=next_id(db, models.NegotiationMessage, "NMSG"), tenant_id=user.tenant_id, plant_id=user.plant_id, negotiation_id=negotiation.id, direction="inbound", message_type="counteroffer", body=message_body, commercial_terms={**commercial_terms, "unit_price": revised_unit_price}, status="received"))
    create_audit(db, user.tenant_id, user.plant_id, user.name, "negotiation.counteroffer_recorded", "negotiation_round", negotiation.id, actor_user_id=user.id)
    return negotiation


def accept_negotiation(db: Session, user: models.User, negotiation_id: str) -> models.NegotiationRound:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    negotiation = get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation")
    if negotiation.status != "supplier_countered" or negotiation.revised_unit_price is None:
        raise HTTPException(status_code=409, detail="Negotiation has no counteroffer to accept")
    quote = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id == negotiation.rfq_id, models.SupplierQuote.supplier_id == negotiation.supplier_id).order_by(models.SupplierQuote.created_at.desc()).first()
    if quote is None:
        raise HTTPException(status_code=409, detail="Supplier quote not found")
    lines = user_scope_query(db, models.QuoteLine, user).filter(models.QuoteLine.quote_id == quote.id).all()
    for line in lines:
        line.unit_price = negotiation.revised_unit_price
        verification_name = f"line:{line.id}:unit_price"
        verification = user_scope_query(db, models.QuoteFieldVerification, user).filter(models.QuoteFieldVerification.quote_id == quote.id, models.QuoteFieldVerification.field_name.in_([verification_name, "unit_price"])).first()
        if verification:
            verification.extracted_value = str(negotiation.revised_unit_price)
            verification.verified_value = None
            verification.status = "needs_review"
            verification.verified_by_user_id = None
            verification.verified_at = None
    quote.verification_status = "needs_review"
    ensure_transition("negotiation", negotiation.status, "accepted_pending_reverification")
    negotiation.status = "accepted_pending_reverification"
    record_approval(db, user, "negotiation_counteroffer", negotiation.id, "accepted", f"Unit price {negotiation.revised_unit_price}")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "negotiation.counteroffer_accepted", "negotiation_round", negotiation.id, actor_user_id=user.id, meta={"quote_id": quote.id})
    return negotiation

def create_po_draft_for_award(db: Session, user: models.User, award: models.AwardDecision) -> models.PODraft:
    existing = user_scope_query(db, models.PODraft, user).filter(models.PODraft.award_id == award.id).first()
    if existing:
        return existing
    quote = get_scoped_or_404(db, models.SupplierQuote, user, award.quote_id, "Quote")
    award_lines = user_scope_query(db, models.AwardLine, user).filter(models.AwardLine.award_id == award.id).all()
    quote_lines = []
    if award_lines:
        quote_lines = [get_scoped_or_404(db, models.QuoteLine, user, award_line.quote_line_id, "Quote line") for award_line in award_lines]
    else:
        quote_lines = user_scope_query(db, models.QuoteLine, user).filter(models.QuoteLine.quote_id == quote.id).all()
    supplier = get_scoped_or_404(db, models.Supplier, user, award.supplier_id, "Supplier")
    site = user_scope_query(db, models.SupplierSite, user).filter(models.SupplierSite.supplier_id == supplier.id).first()
    mapped_lines = []
    for index, line in enumerate(quote_lines):
        item = get_scoped_or_404(db, models.Item, user, line.item_id, "Item")
        award_line = award_lines[index] if index < len(award_lines) else None
        mapped_lines.append({"item_code": item.erp_item_code, "quantity": award_line.awarded_quantity if award_line else line.quantity, "uom": line.uom, "unit_price": line.unit_price, "need_by_date": line.promised_date, "tax_code": f"GST{line.gst_rate:g}"})
    mapping = {"vendor_id": supplier.erp_vendor_id, "supplier_name": supplier.name, "supplier_site": site.name if site else None, "ship_to_location": user.plant_id, "currency": site.currency if site else "INR", "payment_terms": quote.payment_terms, "lines": mapped_lines}
    if len(mapped_lines) == 1:
        mapping.update(mapped_lines[0])
    po = models.PODraft(id=next_id(db, models.PODraft, "PO-DRAFT"), business_number=next_business_number(db, "PO", user), tenant_id=user.tenant_id, plant_id=user.plant_id, award_id=award.id, supplier_id=award.supplier_id, supplier_site_id=site.id if site else None, currency=site.currency if site else "INR", payment_terms=quote.payment_terms, commercial_terms={"quote_id": quote.id, "technical_compliance": sorted({line.technical_compliance for line in quote_lines}), "deviations": [line.deviation_notes for line in quote_lines if line.deviation_notes]}, status="pending_approval", oracle_mapping=mapping, simulated_posting_correlation_id=None)
    db.add(po)
    db.flush()
    for index, line in enumerate(quote_lines):
        specification = user_scope_query(db, models.ItemSpecification, user).filter(models.ItemSpecification.item_id == line.item_id).first()
        award_line = award_lines[index] if index < len(award_lines) else None
        db.add(models.PODraftLine(id=next_id(db, models.PODraftLine, "POL"), business_number=next_business_number(db, "POL", user), tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id, award_line_id=award_line.id if award_line else None, item_id=line.item_id, quantity=award_line.awarded_quantity if award_line else line.quantity, uom=line.uom, unit_price=line.unit_price, gst_rate=line.gst_rate, need_by_date=line.promised_date, inspection_required=specification.inspection_required if specification else True))
    # SessionLocal intentionally disables autoflush. Artifact generation queries
    # these rows immediately, so make the commercial snapshot visible first.
    db.flush()
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, get_scoped_or_404(db, models.RFQ, user, award.rfq_id, "RFQ").requirement_id, "Requirement")
    linked_case = get_scoped_or_404(db, models.Case, user, requirement.related_case_id, "Case")
    # A case retains its first PO as the primary navigation target. Split-award
    # POs remain canonically discoverable through their award batch/RFQ.
    if linked_case.po_draft_id is None:
        linked_case.po_draft_id = po.id
    db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id, title="Approve PO draft for ERP posting", owner_role=PURCHASE_MANAGER, owner_user_id=None, due_at=utcnow() + timedelta(hours=4), status="pending_approval", severity="critical", linked_case_id=linked_case.id, entity_type="po_drafts", entity_id=po.id))
    return po


def approve_award(db: Session, user: models.User, award_id: str) -> models.AwardDecision:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    award = get_scoped_or_404(db, models.AwardDecision, user, award_id, "Award")
    if award.status != "approved":
        from_status = award.status
        ensure_transition("award", from_status, "approved")
        award.status = "approved"
        award.approved_by_user_id = user.id
        award.approved_at = utcnow()
        record_approval(db, user, "award_decision", award.id, "approved", award.rationale)
        record_transition(db, user, "award_decision", award.id, from_status, "approved", "Purchase Manager approved supplier award")
    create_po_draft_for_award(db, user, award)
    complete_tasks_for_entity(db, user, "award_decisions", award.id)
    create_audit(db, user.tenant_id, user.plant_id, user.name, "award.approved", "award_decision", award.id, actor_user_id=user.id)
    return award


def reject_award(db: Session, user: models.User, award_id: str, rationale: str) -> models.AwardDecision:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    award = get_scoped_or_404(db, models.AwardDecision, user, award_id, "Award")
    if award.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Only pending awards can be rejected")
    award.status = "rejected"
    ensure_transition("award", "pending_approval", "rejected")
    award.rationale = rationale
    award.approved_by_user_id = user.id
    award.approved_at = utcnow()
    record_approval(db, user, "award_decision", award.id, "rejected", rationale)
    record_transition(db, user, "award_decision", award.id, "pending_approval", "rejected", rationale)
    complete_tasks_for_entity(db, user, "award_decisions", award.id)
    create_audit(db, user.tenant_id, user.plant_id, user.name, "award.rejected", "award_decision", award.id, actor_user_id=user.id)
    return award


def approve_po_draft(db: Session, user: models.User, po_draft_id: str) -> models.PODraft:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    po = get_scoped_or_404(db, models.PODraft, user, po_draft_id, "PO draft")
    if po.status not in {"approved_pending_outbox", "simulated_posted", "posted"}:
        from_status = po.status
        if po.status != "pending_approval":
            raise HTTPException(status_code=409, detail="Only pending PO drafts can be approved")
        ensure_transition("po", po.status, "approved_pending_outbox")
        po.status = "approved_pending_outbox"
        po.approved_by_user_id = user.id
        po.approved_at = utcnow()
        record_approval(db, user, "po_draft", po.id, "approved", "PO draft approved for ERP outbox")
        create_integration_outbox_event(db, user, get_settings().erp_provider or "local", "push_purchase_order", "po_draft", po.id, po.oracle_mapping, approved=False)
        record_transition(db, user, "po_draft", po.id, from_status, po.status, "PO approved and integration outbox prepared")
    complete_tasks_for_entity(db, user, "po_drafts", po.id)
    create_audit(db, user.tenant_id, user.plant_id, user.name, "po_draft.approved_pending_outbox", "po_draft", po.id, actor_user_id=user.id)
    return po


def _ordered_quantity(db: Session, user: models.User, po: models.PODraft) -> float:
    lines = user_scope_query(db, models.PODraftLine, user).filter(models.PODraftLine.po_draft_id == po.id).all()
    return sum(line.quantity for line in lines) if lines else float(po.oracle_mapping.get("quantity", 0))


def _case_for_po(db: Session, user: models.User, po_id: str) -> models.Case | None:
    case = user_scope_query(db, models.Case, user).filter(models.Case.po_draft_id == po_id).first()
    if case:
        return case
    po = get_scoped_or_404(db, models.PODraft, user, po_id, "PO draft")
    award = get_scoped_or_404(db, models.AwardDecision, user, po.award_id, "Award")
    rfq = get_scoped_or_404(db, models.RFQ, user, award.rfq_id, "RFQ")
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, rfq.requirement_id, "Requirement")
    return user_scope_query(db, models.Case, user).filter(models.Case.id == requirement.related_case_id).first()


def receive_supplier_acknowledgement(
    db: Session, raw_token: str | None, status_value: str, confirmed_quantity: float,
    confirmed_delivery: str, notes: str = "", *, po_context: models.PODraft | None = None,
    supplier_id: str | None = None, source: str = "Supplier Portal",
) -> models.SupplierAcknowledgement:
    portal_token = get_supplier_portal_token(db, raw_token) if raw_token else None
    if portal_token and (portal_token.purpose != "po_acknowledgement" or not portal_token.entity_id):
        raise HTTPException(status_code=404, detail="Supplier PO link is invalid or expired")
    if status_value not in {"accepted", "rejected", "change_requested"}:
        raise HTTPException(status_code=422, detail="Acknowledgement must accept, reject, or request a change")
    if status_value == "change_requested" and len(notes.strip()) < 3:
        raise HTTPException(status_code=422, detail="Explain the requested purchase-order change")
    po = po_context or (db.query(models.PODraft).filter_by(
        id=portal_token.entity_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
    ).first() if portal_token else None)
    expected_supplier_id = portal_token.supplier_id if portal_token else supplier_id
    if po is None or not expected_supplier_id or po.supplier_id != expected_supplier_id:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    existing = db.query(models.SupplierAcknowledgement).filter_by(
        tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id,
    ).order_by(models.SupplierAcknowledgement.created_at.desc()).first()
    if existing:
        same_response = (
            existing.status == status_value and existing.confirmed_quantity == confirmed_quantity
            and existing.confirmed_delivery == confirmed_delivery and existing.response_notes == notes
        )
        if same_response:
            if portal_token:
                portal_token.used_at = utcnow()
            return existing
        raise HTTPException(status_code=409, detail="This purchase order already has a supplier response")
    ordered = sum(line.quantity for line in db.query(models.PODraftLine).filter_by(po_draft_id=po.id, tenant_id=po.tenant_id, plant_id=po.plant_id).all()) or float(po.oracle_mapping.get("quantity", 0))
    if confirmed_quantity < 0 or confirmed_quantity > ordered:
        raise HTTPException(status_code=422, detail="Confirmed quantity exceeds purchase order quantity")
    requested_changes = ({"confirmed_quantity": confirmed_quantity, "confirmed_delivery": confirmed_delivery, "supplier_reason": notes.strip()} if status_value == "change_requested" else {})
    acknowledgement = models.SupplierAcknowledgement(id=next_id(db, models.SupplierAcknowledgement, "ACK"), business_number=next_business_number(db, "ACK", po), tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id, status=status_value, confirmed_quantity=confirmed_quantity, confirmed_delivery=confirmed_delivery, response_notes=notes, requested_changes=requested_changes, responded_at=utcnow())
    db.add(acknowledgement)
    if portal_token:
        portal_token.used_at = utcnow()
    if status_value in {"rejected", "change_requested"}:
        case = db.query(models.Case).filter_by(tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id).first()
        if case:
            case.status = "supplier_rejected_po" if status_value == "rejected" else "supplier_requested_po_change"
            case.severity = "critical" if status_value == "rejected" else "action"
            title = "Supplier rejected PO" if status_value == "rejected" else "Supplier requested a PO change"
            case.timeline = case.timeline + [{"title": title, "time": utcnow().strftime("%H:%M"), "actor": source, "body": notes or title}]
        membership = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=po.tenant_id, default_plant_id=po.plant_id, role=PURCHASE_MANAGER, status="active"
        ).order_by(models.WorkspaceMembership.created_at.asc()).first()
        manager = db.get(models.User, membership.user_id) if membership else None
        if membership and manager:
            task = models.Task(
                id=next_id(db, models.Task, "TASK"), tenant_id=po.tenant_id, plant_id=po.plant_id,
                title=("Review supplier rejection" if status_value == "rejected" else "Review supplier-requested PO change"),
                requested_outcome=("Resolve the rejected purchase order with the supplier." if status_value == "rejected" else "Review the supplier's requested quantity/date and prepare an amendment or decline it with rationale."),
                owner_role=PURCHASE_MANAGER, owner_user_id=manager.id, owner_membership_id=membership.id,
                due_at=utcnow() + timedelta(hours=4), status="open", severity="critical" if status_value == "rejected" else "action",
                entity_type="supplier_acknowledgements", entity_id=acknowledgement.id,
                semantic_key=f"supplier_ack:{acknowledgement.id}:review", assignment_source=source.casefold().replace(" ", "_"),
            )
            db.add(task)
            db.add(models.Notification(
                tenant_id=po.tenant_id, plant_id=po.plant_id, user_id=manager.id, membership_id=membership.id,
                category="supplier_response", severity=task.severity,
                title=task.title, body=f"{po.business_number or 'Purchase order'} needs review: {notes or status_value.replace('_', ' ')}.",
                linked_entity_type="supplier_acknowledgement", linked_entity_id=acknowledgement.id,
                navigation_target=f"/po-drafts?po={po.id}", dedupe_key=f"supplier_ack:{acknowledgement.id}:review",
            ))
    create_audit(db, po.tenant_id, po.plant_id, source, "po.acknowledged", "supplier_acknowledgement", acknowledgement.id, meta={"po_draft_id": po.id, "status": status_value, "requested_changes": requested_changes, "source": source})
    db.flush()
    return acknowledgement


def receive_supplier_delivery_notice(
    db: Session, raw_token: str | None, expected_quantity: float, expected_delivery: str,
    dispatch_reference: str, vehicle_number: str = "", *, po_context: models.PODraft | None = None,
    supplier_id: str | None = None, source: str = "supplier_portal",
) -> models.ASN:
    portal_token = get_supplier_portal_token(db, raw_token) if raw_token else None
    if portal_token and (portal_token.purpose != "po_acknowledgement" or not portal_token.entity_id):
        raise HTTPException(404, "Supplier PO link is invalid or expired")
    po = po_context or (db.query(models.PODraft).filter_by(
        id=portal_token.entity_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
    ).first() if portal_token else None)
    expected_supplier_id = portal_token.supplier_id if portal_token else supplier_id
    if not po or not expected_supplier_id or po.supplier_id != expected_supplier_id:
        raise HTTPException(404, "Purchase order not found")
    acknowledgement = db.query(models.SupplierAcknowledgement).filter_by(
        tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id, status="accepted",
    ).first()
    if not acknowledgement:
        raise HTTPException(409, "Accept the purchase order before submitting delivery details")
    existing = db.query(models.ASN).filter_by(
        tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id,
        dispatch_reference=dispatch_reference,
    ).first()
    if existing:
        if existing.expected_quantity == expected_quantity and existing.expected_delivery == expected_delivery and existing.vehicle_number == vehicle_number:
            if portal_token:
                portal_token.used_at = utcnow()
            return existing
        raise HTTPException(409, "This dispatch reference already has different delivery details")
    ordered = sum(line.quantity for line in db.query(models.PODraftLine).filter_by(
        tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id,
    ).all()) or float(po.oracle_mapping.get("quantity", 0))
    already_notified = sum(row.expected_quantity for row in db.query(models.ASN).filter_by(
        tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id,
    ).filter(models.ASN.status.notin_(["cancelled", "rejected"])).all())
    if expected_quantity > max(0, ordered - already_notified):
        raise HTTPException(422, "Delivery quantity exceeds the remaining purchase-order quantity")
    asn = models.ASN(
        id=next_id(db, models.ASN, "ASN"), business_number=next_business_number(db, "ASN", po),
        tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id,
        status="supplier_submitted", vehicle_number=vehicle_number,
        expected_quantity=expected_quantity, dispatch_reference=dispatch_reference,
        expected_delivery=expected_delivery, source=source,
        supplier_document_ids=[], submitted_at=utcnow(),
    )
    db.add(asn); db.flush()
    if portal_token:
        portal_token.used_at = utcnow()
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=po.tenant_id, default_plant_id=po.plant_id, role=STORE_MANAGER, status="active",
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()
    store_user = db.get(models.User, membership.user_id) if membership else None
    if membership and store_user:
        semantic_key = f"supplier_asn:{asn.id}:receive"
        db.add(models.Task(
            id=next_id(db, models.Task, "TASK"), tenant_id=po.tenant_id, plant_id=po.plant_id,
            title=f"Prepare inbound receipt for {asn.business_number}",
            requested_outcome="Review supplier dispatch evidence and prepare Gate/Stores receipt context.",
            owner_role=STORE_MANAGER, owner_user_id=store_user.id, owner_membership_id=membership.id,
            due_at=utcnow() + timedelta(hours=4), status="open", severity="action",
            entity_type="asns", entity_id=asn.id, semantic_key=semantic_key,
            assignment_source=source,
        ))
        db.add(models.Notification(
            tenant_id=po.tenant_id, plant_id=po.plant_id, user_id=store_user.id, membership_id=membership.id,
            category="supplier_delivery_notice", severity="action",
            title="Supplier submitted delivery details",
            body=f"{asn.business_number} expects {expected_quantity} by {expected_delivery}; dispatch {dispatch_reference}.",
            linked_entity_type="asn", linked_entity_id=asn.id,
            navigation_target=f"/store?asn={asn.id}", dedupe_key=semantic_key,
        ))
    create_audit(db, po.tenant_id, po.plant_id, "Supplier Portal" if source == "supplier_portal" else "Supplier Email", "asn.supplier_submitted", "asn", asn.id, meta={"po_id": po.id, "dispatch_reference": dispatch_reference, "expected_quantity": expected_quantity, "source": source})
    return asn


def receive_supplier_delivery_update(
    db: Session, raw_token: str, asn_id: str, external_update_id: str,
    revised_expected_delivery: str, reason: str,
) -> models.SupplierDeliveryUpdate:
    portal_token = get_supplier_portal_token(db, raw_token)
    if portal_token.purpose != "po_acknowledgement" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier PO link is invalid or expired")
    asn = db.query(models.ASN).filter_by(
        id=asn_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        po_draft_id=portal_token.entity_id, source="supplier_portal",
    ).first()
    if not asn:
        raise HTTPException(404, "Supplier delivery notice not found")
    po = db.query(models.PODraft).filter_by(
        id=asn.po_draft_id, tenant_id=asn.tenant_id, plant_id=asn.plant_id,
        supplier_id=portal_token.supplier_id,
    ).first()
    if not po:
        raise HTTPException(404, "Purchase order not found")
    if db.query(models.GateEntry).filter_by(
        tenant_id=asn.tenant_id, plant_id=asn.plant_id, asn_id=asn.id,
    ).first():
        raise HTTPException(409, "This delivery has already arrived at Gate")
    try:
        revised = date.fromisoformat(revised_expected_delivery)
        previous = date.fromisoformat(asn.expected_delivery) if asn.expected_delivery else revised
    except ValueError as exc:
        raise HTTPException(422, "Use a valid delivery date") from exc
    normalized_external_id = external_update_id.strip()
    normalized_reason = reason.strip()
    existing = db.query(models.SupplierDeliveryUpdate).filter_by(
        tenant_id=asn.tenant_id, plant_id=asn.plant_id, asn_id=asn.id,
        external_update_id=normalized_external_id,
    ).first()
    if existing:
        if existing.revised_expected_delivery == revised.isoformat() and existing.reason == normalized_reason:
            portal_token.used_at = utcnow()
            return existing
        raise HTTPException(409, "This delivery update reference was already used")
    update_type = "delay" if revised > previous else "expedite" if revised < previous else "schedule_change"
    update = models.SupplierDeliveryUpdate(
        id=next_id(db, models.SupplierDeliveryUpdate, "DUPD"),
        business_number=next_business_number(db, "DUPD", asn),
        tenant_id=asn.tenant_id, plant_id=asn.plant_id, asn_id=asn.id,
        po_draft_id=asn.po_draft_id, supplier_id=portal_token.supplier_id,
        external_update_id=normalized_external_id, update_type=update_type,
        previous_expected_delivery=asn.expected_delivery,
        revised_expected_delivery=revised.isoformat(), reason=normalized_reason,
        submitted_at=utcnow(),
    )
    db.add(update)
    asn.expected_delivery = revised.isoformat()
    asn.status = "supplier_schedule_changed"
    portal_token.used_at = utcnow()
    db.flush()
    semantic_key = f"supplier_delivery_update:{update.id}:coordinate"
    purchase_membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=asn.tenant_id, default_plant_id=asn.plant_id,
        role=PURCHASE_MANAGER, status="active",
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()
    store_membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=asn.tenant_id, default_plant_id=asn.plant_id,
        role=STORE_MANAGER, status="active",
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()
    db.add(models.Task(
        id=next_id(db, models.Task, "TASK"), tenant_id=asn.tenant_id, plant_id=asn.plant_id,
        title=f"Coordinate changed delivery {asn.business_number}",
        requested_outcome=f"Review the supplier's {update_type.replace('_', ' ')} to {revised.isoformat()} and update affected teams.",
        owner_role=PURCHASE_MANAGER, owner_user_id=purchase_membership.user_id if purchase_membership else None,
        owner_membership_id=purchase_membership.id if purchase_membership else None,
        shared_queue=purchase_membership is None, due_at=utcnow(), status="open",
        severity="critical" if update_type == "delay" else "action",
        entity_type="supplier_delivery_updates", entity_id=update.id,
        semantic_key=semantic_key, assignment_source="supplier_portal",
    ))
    for membership in [purchase_membership, store_membership]:
        if membership:
            db.add(models.Notification(
                tenant_id=asn.tenant_id, plant_id=asn.plant_id,
                user_id=membership.user_id, membership_id=membership.id,
                category="supplier_delivery_changed",
                severity="critical" if update_type == "delay" else "action",
                title=f"Supplier delivery {update_type.replace('_', ' ')}",
                body=f"{asn.business_number} is now expected {revised.isoformat()}. {normalized_reason}",
                linked_entity_type="supplier_delivery_update", linked_entity_id=update.id,
                navigation_target=f"/store?asn={asn.id}",
                dedupe_key=f"{semantic_key}:{membership.id}",
            ))
    create_audit(
        db, asn.tenant_id, asn.plant_id, "Supplier Portal",
        "asn.delivery_schedule_changed", "supplier_delivery_update", update.id,
        meta={"asn_id": asn.id, "previous": update.previous_expected_delivery, "revised": revised.isoformat(), "update_type": update_type},
    )
    return update


def attach_supplier_delivery_document(
    db: Session, raw_token: str, asn_id: str, document: models.Document,
) -> models.ASN:
    portal_token = get_supplier_portal_token(db, raw_token)
    if portal_token.purpose != "po_acknowledgement" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier PO link is invalid or expired")
    asn = db.query(models.ASN).filter_by(
        id=asn_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        po_draft_id=portal_token.entity_id, source="supplier_portal",
    ).first()
    if not asn:
        raise HTTPException(404, "Supplier delivery notice not found")
    asn = link_supplier_delivery_document(db, asn, document, document.linked_entity_type or "supplier_dispatch_document", "Supplier Portal")
    portal_token.used_at = utcnow()
    return asn


def link_supplier_delivery_document(
    db: Session, asn: models.ASN, document: models.Document, purpose: str,
    source: str,
) -> models.ASN:
    if purpose not in {"supplier_dispatch_document", "supplier_certificate"}:
        raise HTTPException(422, "Unsupported supplier delivery evidence type")
    if document.tenant_id != asn.tenant_id or document.plant_id != asn.plant_id:
        raise HTTPException(403, "Document is outside this supplier delivery")
    if document.linked_entity_id and document.linked_entity_id != asn.id:
        raise HTTPException(409, "Document is already linked to another business record")
    document.linked_entity_type = purpose
    document.linked_entity_id = asn.id
    if document.id not in asn.supplier_document_ids:
        asn.supplier_document_ids = [*asn.supplier_document_ids, document.id]
    create_audit(db, asn.tenant_id, asn.plant_id, source, "asn.document_attached", "asn", asn.id, meta={"document_id": document.id, "purpose": purpose, "source": source})
    return asn


def receive_supplier_clarification(
    db: Session, raw_token: str, external_message_id: str, subject: str, message: str,
) -> models.SupplierChannelMessage:
    portal_token = get_supplier_portal_token(db, raw_token)
    existing = db.query(models.SupplierChannelMessage).filter_by(
        tenant_id=portal_token.tenant_id, channel="portal", external_message_id=external_message_id,
    ).first()
    if existing:
        if existing.supplier_id == portal_token.supplier_id and existing.body_preview == message:
            portal_token.used_at = utcnow(); return existing
        raise HTTPException(409, "This supplier message reference is already in use")
    rfq_id = portal_token.entity_id if portal_token.purpose == "rfq_quote" else None
    canonical_ids = [portal_token.entity_id] if portal_token.entity_id else []
    channel_message = models.SupplierChannelMessage(
        tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        channel="portal", direction="inbound", external_message_id=external_message_id,
        sender=f"supplier:{portal_token.supplier_id}", recipient="GenuineGigs",
        subject=subject, body_preview=message, status="processed",
        rfq_id=rfq_id, supplier_id=portal_token.supplier_id,
        document_ids=[], canonical_record_ids=canonical_ids,
    )
    db.add(channel_message); db.flush(); portal_token.used_at = utcnow()
    role = PURCHASE_EXECUTIVE if rfq_id else PURCHASE_MANAGER
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=portal_token.tenant_id, default_plant_id=portal_token.plant_id,
        role=role, status="active",
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()
    owner = db.get(models.User, membership.user_id) if membership else None
    if membership and owner:
        semantic_key = f"supplier_clarification:{channel_message.id}:respond"
        db.add(models.Task(
            id=next_id(db, models.Task, "TASK"), tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
            title="Respond to supplier clarification", requested_outcome="Review the supplier message and prepare a governed response.",
            owner_role=role, owner_user_id=owner.id, owner_membership_id=membership.id,
            due_at=utcnow() + timedelta(hours=4), status="open", severity="action",
            entity_type="supplier_channel_messages", entity_id=channel_message.id,
            semantic_key=semantic_key, assignment_source="supplier_portal",
        ))
        db.add(models.Notification(
            tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
            user_id=owner.id, membership_id=membership.id, category="supplier_clarification", severity="action",
            title="Supplier clarification received", body=message[:500],
            linked_entity_type="supplier_channel_message", linked_entity_id=channel_message.id,
            navigation_target="/integrations", dedupe_key=semantic_key,
        ))
    create_audit(db, portal_token.tenant_id, portal_token.plant_id, "Supplier Portal", "supplier.clarification_received", "supplier_channel_message", channel_message.id, meta={"supplier_id": portal_token.supplier_id, "purpose": portal_token.purpose})
    return channel_message


def _ensure_no_pending_po_change(db: Session, user: models.User, po: models.PODraft) -> None:
    root_id = po.root_po_id or po.id
    pending = user_scope_query(db, models.PODraft, user).filter(
        models.PODraft.root_po_id == root_id,
        models.PODraft.status.in_(["pending_approval", "approved_pending_outbox", "posting"]),
    ).first()
    if pending:
        raise HTTPException(status_code=409, detail="Inbound activity is paused while a purchase-order change is awaiting approval or dispatch")


def create_asn(db: Session, user: models.User, po_draft_id: str, expected_quantity: float, vehicle_number: str = "") -> models.ASN:
    require_role(user, STORE_MANAGER, ADMIN)
    po = get_scoped_or_404(db, models.PODraft, user, po_draft_id, "PO draft")
    if po.status not in {"posted", "simulated_posted"}:
        raise HTTPException(status_code=409, detail="ASN requires a posted purchase order")
    _ensure_no_pending_po_change(db, user, po)
    acknowledgement = user_scope_query(db, models.SupplierAcknowledgement, user).filter(models.SupplierAcknowledgement.po_draft_id == po.id, models.SupplierAcknowledgement.status == "accepted").order_by(models.SupplierAcknowledgement.created_at.desc()).first()
    if acknowledgement is None:
        raise HTTPException(status_code=409, detail="ASN requires supplier acceptance")
    existing_quantity = sum(row.expected_quantity for row in user_scope_query(db, models.ASN, user).filter(models.ASN.po_draft_id == po.id).with_for_update().all())
    if expected_quantity <= 0 or existing_quantity + expected_quantity > acknowledgement.confirmed_quantity:
        raise HTTPException(status_code=409, detail="ASN quantity exceeds supplier-confirmed quantity")
    asn = models.ASN(id=next_id(db, models.ASN, "ASN"), tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id, status="in_transit", vehicle_number=vehicle_number, expected_quantity=expected_quantity)
    db.add(asn)
    create_audit(db, user.tenant_id, user.plant_id, user.name, "asn.created", "asn", asn.id, actor_user_id=user.id)
    return asn


def record_gate_entry(
    db: Session, user: models.User, po_draft_id: str, asn_id: str | None = None,
    vehicle_number: str = "", supplier_challan: str = "", packages_count: int = 0,
    arrival_notes: str = "",
) -> models.GateEntry:
    require_role(user, GATE_OPERATOR, ADMIN)
    po = get_scoped_or_404(db, models.PODraft, user, po_draft_id, "PO draft")
    if po.status not in {"approved_pending_outbox", "posted", "simulated_posted"}:
        raise HTTPException(status_code=409, detail="Gate entry requires an issued purchase order")
    _ensure_no_pending_po_change(db, user, po)
    if asn_id:
        asn = get_scoped_or_404(db, models.ASN, user, asn_id, "ASN")
        if asn.po_draft_id != po.id:
            raise HTTPException(status_code=409, detail="ASN does not belong to the purchase order")
    if not supplier_challan.strip():
        raise HTTPException(status_code=422, detail="Supplier challan is required")
    gate = models.GateEntry(
        id=next_id(db, models.GateEntry, "GATE"), tenant_id=user.tenant_id,
        plant_id=user.plant_id, po_draft_id=po.id, asn_id=asn_id,
        status="vehicle_admitted", vehicle_number=vehicle_number,
        supplier_challan=supplier_challan, packages_count=packages_count,
        arrival_notes=arrival_notes, received_at=utcnow(),
    )
    db.add(gate)
    store_membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, default_plant_id=user.plant_id,
        role=STORE_MANAGER, status="active"
    ).first()
    db.add(models.Task(
        id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id,
        plant_id=user.plant_id, title=f"Receive material against {po.business_number or po.id}",
        owner_role=STORE_MANAGER,
        owner_user_id=store_membership.user_id if store_membership else None,
        owner_membership_id=store_membership.id if store_membership else None,
        due_at=utcnow() + timedelta(hours=2), status="open", severity="action",
        entity_type="gate_entries", entity_id=gate.id,
    ))
    create_audit(db, user.tenant_id, user.plant_id, user.name, "gate_entry.recorded", "gate_entry", gate.id, actor_user_id=user.id)
    return gate


def _record_inbound_exception(
    db: Session, user: models.User, po: models.PODraft, source_type: str,
    source_id: str, exception_types: list[str], evidence: dict[str, Any],
    production_impact: bool,
) -> None:
    if not exception_types:
        return
    owner_role = PURCHASE_EXECUTIVE if source_type == "store_receipt" else PURCHASE_MANAGER
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, default_plant_id=user.plant_id,
        role=owner_role, status="active",
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()
    employee = db.get(models.User, membership.user_id) if membership else None
    case = _case_for_po(db, user, po.id)
    label = ", ".join(value.replace("_", " ") for value in exception_types)
    if case:
        case.status = "inbound_exception"
        case.severity = "critical" if production_impact or any(value in {"wrong_material", "missing_certificate", "quality_rejection"} for value in exception_types) else "action"
        case.evidence = list(case.evidence or []) + [{
            "source_type": source_type, "source_id": source_id,
            "exception_types": exception_types, "details": evidence,
            "production_impact": production_impact, "recorded_at": utcnow().isoformat(),
        }]
        case.timeline = list(case.timeline or []) + [{
            "title": "Inbound exception recorded", "time": utcnow().strftime("%H:%M"),
            "actor": user.name, "body": f"{label}. Owner: {owner_role.replace('_', ' ')}.",
        }]
        if source_type == "store_receipt":
            case.receipt_id = source_id
        else:
            case.inspection_id = source_id
    semantic_key = f"inbound_exception:{source_type}:{source_id}"
    task = user_scope_query(db, models.Task, user).filter_by(semantic_key=semantic_key).filter(
        models.Task.status.in_(["open", "accepted", "in_progress", "blocked", "review"])
    ).first()
    if task is None:
        task = models.Task(
            id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id,
            title=f"Resolve inbound exception: {label}",
            requested_outcome="Review the evidence, coordinate the supplier response, and record the disposition or recovery plan.",
            owner_role=owner_role, owner_user_id=employee.id if employee else None,
            owner_membership_id=membership.id if membership else None,
            due_at=utcnow() + timedelta(hours=4), status="open",
            severity="critical" if production_impact else "action",
            linked_case_id=case.id if case else None, entity_type=source_type + "s", entity_id=source_id,
            semantic_key=semantic_key, assignment_source="inbound_exception",
        )
        db.add(task)
    if employee:
        db.add(models.Notification(
            tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=employee.id,
            membership_id=membership.id if membership else None, category="inbound_exception",
            severity=task.severity, title=task.title,
            body=f"{po.business_number or 'Purchase order'}: {label}.",
            linked_entity_type=source_type, linked_entity_id=source_id,
            navigation_target="/cases", dedupe_key=semantic_key,
        ))
    if production_impact:
        plant_membership = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=user.tenant_id, default_plant_id=user.plant_id,
            role=PLANT_MANAGER, status="active",
        ).first()
        plant_manager = db.get(models.User, plant_membership.user_id) if plant_membership else None
        if plant_manager:
            db.add(models.Notification(
                tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=plant_manager.id,
                membership_id=plant_membership.id, category="production_impact", severity="critical",
                title="Inbound issue may affect production",
                body=f"{po.business_number or 'Purchase order'}: {label}. {evidence.get('notes') or 'Review the recovery owner and due time.'}",
                linked_entity_type=source_type, linked_entity_id=source_id,
                navigation_target="/cases", dedupe_key=semantic_key + ":production",
            ))

def record_receipt(
    db: Session, user: models.User, po_draft_id: str, received_quantity: float,
    damaged_quantity: float = 0, observed_item_code: str = "",
    certificate_status: str = "received", exception_notes: str = "",
    production_impact: bool = False,
) -> models.StoreReceipt:
    require_role(user, STORE_MANAGER, ADMIN)
    po = get_scoped_or_404(db, models.PODraft, user, po_draft_id, "PO draft")
    _ensure_no_pending_po_change(db, user, po)
    if received_quantity <= 0 or damaged_quantity < 0 or damaged_quantity > received_quantity:
        raise HTTPException(status_code=422, detail="Receipt quantities are invalid")
    if certificate_status not in {"received", "missing", "invalid"}:
        raise HTTPException(status_code=422, detail="Certificate status must be received, missing, or invalid")
    ordered = _ordered_quantity(db, user, po)
    gate = user_scope_query(db, models.GateEntry, user).filter(models.GateEntry.po_draft_id == po.id).order_by(models.GateEntry.created_at.desc()).first()
    if gate is None:
        raise HTTPException(status_code=409, detail="Receipt requires a Gate Operator entry")
    if gate.asn_id:
        get_scoped_or_404(db, models.ASN, user, gate.asn_id, "ASN")
    existing_receipts = user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.po_draft_id == po.id).with_for_update().all()
    cumulative = sum(row.received_quantity for row in existing_receipts) + received_quantity
    asn_total = sum(row.expected_quantity for row in user_scope_query(db, models.ASN, user).filter(models.ASN.po_draft_id == po.id).all())
    authorized_quantity = asn_total if asn_total else ordered
    policy_service = __import__('app.procurement_policy', fromlist=['active_policy', 'policy_rules'])
    rules = policy_service.policy_rules(policy_service.active_policy(db, user))
    maximum_receipt = authorized_quantity * (1 + float(rules.get('over_delivery_tolerance_percent', 0)) / 100)
    if cumulative > maximum_receipt:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cumulative receipt exceeds the authorized inbound quantity "
                f"({maximum_receipt:g}) allowed by the active procurement policy"
            ),
        )
    po_lines = user_scope_query(db, models.PODraftLine, user).filter(models.PODraftLine.po_draft_id == po.id).all()
    expected_codes = {item.code for item in (db.get(models.Item, line.item_id) for line in po_lines) if item}
    wrong_material = bool(observed_item_code.strip() and expected_codes and observed_item_code.strip().casefold() not in {code.casefold() for code in expected_codes})
    exception_types = []
    if cumulative < ordered: exception_types.append("backorder")
    if cumulative > ordered: exception_types.append("excess_delivery")
    if damaged_quantity: exception_types.append("damage")
    if wrong_material: exception_types.append("wrong_material")
    if certificate_status in {"missing", "invalid"}: exception_types.append("missing_certificate" if certificate_status == "missing" else "invalid_certificate")
    receipt_status = "short_received" if cumulative < ordered else "excess_received" if cumulative > ordered else "exception" if exception_types else "received"
    receipt = models.StoreReceipt(id=next_id(db, models.StoreReceipt, "REC"), business_number=next_business_number(db, "REC", user), tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id, gate_entry_id=gate.id, status=receipt_status, received_quantity=received_quantity, short_quantity=max(0, ordered - cumulative), excess_quantity=max(0, cumulative - ordered), damaged_quantity=damaged_quantity, exception_types=exception_types, observed_item_code=observed_item_code.strip(), certificate_status=certificate_status, exception_notes=exception_notes.strip(), production_impact=production_impact)
    db.add(receipt)
    db.flush()
    _record_inbound_exception(db, user, po, "store_receipt", receipt.id, exception_types, {
        "received_quantity": received_quantity, "short_quantity": receipt.short_quantity,
        "excess_quantity": receipt.excess_quantity, "damaged_quantity": damaged_quantity,
        "observed_item_code": observed_item_code, "expected_item_codes": sorted(expected_codes),
        "certificate_status": certificate_status, "notes": exception_notes,
    }, production_impact)
    create_integration_outbox_event(db, user, get_settings().erp_provider or "local", "push_receipt", "store_receipt", receipt.id, {"po_draft_id": po.id, "received_quantity": received_quantity, "damaged_quantity": damaged_quantity, "exception_types": exception_types, "certificate_status": certificate_status, "observed_item_code": observed_item_code}, approved=False)
    if po_lines and not any(line.inspection_required for line in po_lines):
        receipt.status = "accepted_no_inspection"
        for line in po_lines:
            proportional = received_quantity * (line.quantity / max(ordered, 1))
            db.add(models.InventoryImpact(id=next_id(db, models.InventoryImpact, "INV"), business_number=next_business_number(db, "INV", user), tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id, inspection_id=f"not-required:{receipt.id}", item_id=line.item_id, usable_quantity=max(0, proportional - damaged_quantity), rejected_quantity=damaged_quantity, held_quantity=0))
    else:
        db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id, title=f"Inspect receipt {receipt.business_number or receipt.id}", owner_role=QUALITY_INSPECTOR, owner_user_id=None, due_at=utcnow() + timedelta(hours=4), status="open", severity="action", linked_case_id=_case_for_po(db, user, po.id).id if _case_for_po(db, user, po.id) else None, entity_type="store_receipts", entity_id=receipt.id))
    create_audit(db, user.tenant_id, user.plant_id, user.name, "store_receipt.recorded", "store_receipt", receipt.id, actor_user_id=user.id)
    return receipt


def record_inspection(
    db: Session, user: models.User, receipt_id: str, inspected_quantity: float,
    accepted_quantity: float, rejected_quantity: float, held_quantity: float,
    certificate_status: str = "verified", defect_codes: list[str] | None = None,
    inspection_notes: str = "", production_impact: bool = False,
) -> models.InspectionResult:
    require_role(user, QUALITY_INSPECTOR, ADMIN)
    receipt = get_scoped_or_404(db, models.StoreReceipt, user, receipt_id, "Receipt")
    if min(inspected_quantity, accepted_quantity, rejected_quantity, held_quantity) < 0:
        raise HTTPException(status_code=422, detail="Inspection quantities cannot be negative")
    if accepted_quantity + rejected_quantity + held_quantity > inspected_quantity:
        raise HTTPException(status_code=422, detail="Inspection quantities exceed inspected quantity")
    if certificate_status not in {"verified", "missing", "invalid", "pending"}:
        raise HTTPException(status_code=422, detail="Certificate status is invalid")
    if certificate_status != "verified" and accepted_quantity > 0:
        raise HTTPException(status_code=409, detail="Material cannot be accepted until required certificate evidence is verified; record it as held or rejected")
    if "wrong_material" in (receipt.exception_types or []) and accepted_quantity > 0:
        raise HTTPException(status_code=409, detail="Material recorded with the wrong item code cannot enter usable inventory")
    existing_inspections = user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.receipt_id == receipt.id).with_for_update().all()
    already_inspected = sum(row.inspected_quantity for row in existing_inspections)
    if already_inspected + inspected_quantity > receipt.received_quantity:
        raise HTTPException(status_code=409, detail="Cannot inspect more than received quantity")
    defects = list(dict.fromkeys(str(value).strip() for value in (defect_codes or []) if str(value).strip()))
    inspection = models.InspectionResult(id=next_id(db, models.InspectionResult, "INSP"), business_number=next_business_number(db, "INSP", user), tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=receipt.po_draft_id, receipt_id=receipt.id, status="partial_acceptance" if rejected_quantity or held_quantity or certificate_status != "verified" else "accepted", inspected_quantity=inspected_quantity, accepted_quantity=accepted_quantity, rejected_quantity=rejected_quantity, held_quantity=held_quantity, certificate_status=certificate_status, defect_codes=defects, inspection_notes=inspection_notes.strip(), production_impact=production_impact)
    db.add(inspection)
    po = get_scoped_or_404(db, models.PODraft, user, receipt.po_draft_id, "PO draft")
    po_line = user_scope_query(db, models.PODraftLine, user).filter(models.PODraftLine.po_draft_id == po.id).first()
    item_id = po_line.item_id if po_line else None
    if item_id is None and po.award_id:
        award = get_scoped_or_404(db, models.AwardDecision, user, po.award_id, "Award")
        quote_line = user_scope_query(db, models.QuoteLine, user).filter(models.QuoteLine.quote_id == award.quote_id).first()
        item_id = quote_line.item_id if quote_line else None
    if item_id is None:
        raise HTTPException(status_code=409, detail="Purchase order line is required before quality inspection")
    db.add(models.InventoryImpact(id=next_id(db, models.InventoryImpact, "INV"), tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=receipt.po_draft_id, inspection_id=inspection.id, item_id=item_id, usable_quantity=accepted_quantity, rejected_quantity=rejected_quantity, held_quantity=held_quantity))
    complete_tasks_for_entity(db, user, "store_receipts", receipt.id)
    exception_types = []
    if rejected_quantity: exception_types.append("quality_rejection")
    if held_quantity: exception_types.append("quality_hold")
    if accepted_quantity < inspected_quantity - rejected_quantity - held_quantity: exception_types.append("undisposed_quantity")
    if certificate_status in {"missing", "invalid", "pending"}: exception_types.append(f"certificate_{certificate_status}")
    if defects: exception_types.append("technical_deviation")
    db.flush()
    _record_inbound_exception(db, user, po, "inspection_result", inspection.id, exception_types, {
        "receipt_id": receipt.id, "inspected_quantity": inspected_quantity,
        "accepted_quantity": accepted_quantity, "rejected_quantity": rejected_quantity,
        "held_quantity": held_quantity, "certificate_status": certificate_status,
        "defect_codes": defects, "notes": inspection_notes,
    }, production_impact)
    create_integration_outbox_event(db, user, get_settings().erp_provider or "local", "push_quality_disposition", "inspection_result", inspection.id, {
        "po_draft_id": po.id, "receipt_id": receipt.id, "accepted_quantity": accepted_quantity,
        "rejected_quantity": rejected_quantity, "held_quantity": held_quantity,
        "certificate_status": certificate_status, "defect_codes": defects,
    }, approved=False)
    if receipt.supplier_return_id:
        supplier_return = get_scoped_or_404(db, models.SupplierReturn, user, receipt.supplier_return_id, "Supplier return")
        replacement_receipts = user_scope_query(db, models.StoreReceipt, user).filter(
            models.StoreReceipt.supplier_return_id == supplier_return.id,
        ).all()
        replacement_receipt_ids = [row.id for row in replacement_receipts]
        replacement_inspections = user_scope_query(db, models.InspectionResult, user).filter(
            models.InspectionResult.receipt_id.in_(replacement_receipt_ids or [""]),
            models.InspectionResult.id != inspection.id,
        ).all()
        accepted_replacement = sum(row.accepted_quantity for row in replacement_inspections) + accepted_quantity
        rejected_replacement = sum(row.rejected_quantity for row in replacement_inspections) + rejected_quantity
        if rejected_replacement > 0:
            supplier_return.status = "replacement_rejected"
        elif accepted_replacement >= supplier_return.replacement_requested_quantity:
            supplier_return.status = "replacement_accepted"
            supplier_return.completed_at = utcnow()
        else:
            supplier_return.status = "replacement_partially_accepted"
        linked_case = get_scoped_or_404(db, models.Case, user, supplier_return.case_id, "Case") if supplier_return.case_id else None
        if linked_case:
            linked_case.timeline = linked_case.timeline + [{
                "title": "Replacement quality inspection", "time": utcnow().strftime("%H:%M"),
                "actor": user.name,
                "body": f"Accepted {accepted_quantity:g}; rejected {rejected_quantity:g}; held {held_quantity:g}.",
            }]
    __import__('app.supplier_performance', fromlist=['record_quality_event']).record_quality_event(
        db, user, inspection, po.supplier_id
    )
    create_audit(db, user.tenant_id, user.plant_id, user.name, "inspection.recorded", "inspection_result", inspection.id, actor_user_id=user.id)
    return inspection


def create_supplier_return(db: Session, user: models.User, inspection_id: str, return_quantity: float, reason: str) -> models.SupplierReturn:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    inspection = get_scoped_or_404(db, models.InspectionResult, user, inspection_id, "Inspection")
    if inspection.rejected_quantity <= 0:
        raise HTTPException(status_code=409, detail="Only rejected material can be returned")
    existing = user_scope_query(db, models.SupplierReturn, user).filter(
        models.SupplierReturn.inspection_id == inspection.id,
        models.SupplierReturn.status.notin_(["cancelled"]),
    ).all()
    available = inspection.rejected_quantity - sum(row.return_quantity for row in existing)
    if return_quantity <= 0 or return_quantity > available:
        raise HTTPException(status_code=409, detail=f"Return quantity exceeds the remaining rejected quantity ({available:g})")
    po = get_scoped_or_404(db, models.PODraft, user, inspection.po_draft_id, "Purchase order")
    case = _case_for_po(db, user, po.id)
    supplier_return = models.SupplierReturn(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        business_number=next_business_number(db, "RET", user), po_draft_id=po.id,
        inspection_id=inspection.id, supplier_id=po.supplier_id, case_id=case.id if case else None,
        status="draft", rejected_quantity=inspection.rejected_quantity,
        return_quantity=return_quantity, replacement_requested_quantity=0,
        replacement_received_quantity=0, reason=reason,
    )
    db.add(supplier_return)
    db.flush()
    if case:
        case.status = "supplier_return_prepared"
        case.timeline = case.timeline + [{"title": "Supplier return prepared", "time": utcnow().strftime("%H:%M"), "actor": user.name, "body": f"{return_quantity:g} units: {reason}"}]
    create_audit(db, user.tenant_id, user.plant_id, user.name, "supplier_return.created", "supplier_return", supplier_return.id, actor_user_id=user.id)
    return supplier_return


def request_supplier_replacement(db: Session, user: models.User, supplier_return_id: str, replacement_quantity: float, requested_delivery: str) -> models.SupplierReturn:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    supplier_return = get_scoped_or_404(db, models.SupplierReturn, user, supplier_return_id, "Supplier return")
    if supplier_return.status == "replacement_requested":
        return supplier_return
    if supplier_return.status != "draft":
        raise HTTPException(status_code=409, detail="Only a prepared supplier return can request replacement")
    if replacement_quantity <= 0 or replacement_quantity > supplier_return.return_quantity:
        raise HTTPException(status_code=422, detail="Replacement quantity cannot exceed the return quantity")
    supplier = get_scoped_or_404(db, models.Supplier, user, supplier_return.supplier_id, "Supplier")
    contact = user_scope_query(db, models.SupplierContact, user).filter_by(supplier_id=supplier.id).first()
    if contact is None:
        raise HTTPException(status_code=409, detail="Supplier contact is required before requesting replacement")
    outbox = user_scope_query(db, models.OutboxMessage, user).filter_by(
        idempotency_key=f"supplier-return:{supplier_return.id}:replacement",
    ).first()
    if outbox is None:
        outbox = models.OutboxMessage(
            tenant_id=user.tenant_id, plant_id=user.plant_id, channel="email", recipient=contact.email,
            subject=f"Replacement request {supplier_return.business_number}",
            body=f"Please replace {replacement_quantity:g} units by {requested_delivery}. Reason: {supplier_return.reason}",
            status="approved_pending_send", payload_hash=payload_hash(f"{supplier_return.id}:{replacement_quantity}:{requested_delivery}"),
            correlation_id=f"RET-{supplier_return.id[:8]}",
            idempotency_key=f"supplier-return:{supplier_return.id}:replacement",
            approved_by_user_id=user.id, approved_at=utcnow(), attachment_document_ids=[],
            meta={"supplier_return_id": supplier_return.id, "po_draft_id": supplier_return.po_draft_id},
        )
        db.add(outbox)
    supplier_return.status = "replacement_requested"
    supplier_return.replacement_requested_quantity = replacement_quantity
    supplier_return.requested_at = utcnow()
    create_audit(db, user.tenant_id, user.plant_id, user.name, "supplier_replacement.requested", "supplier_return", supplier_return.id, actor_user_id=user.id, meta={"outbox_id": outbox.id})
    return supplier_return


def record_replacement_receipt(db: Session, user: models.User, supplier_return_id: str, received_quantity: float, supplier_challan: str, vehicle_number: str = "", packages_count: int = 0) -> models.StoreReceipt:
    require_role(user, STORE_MANAGER, ADMIN)
    supplier_return = get_scoped_or_404(db, models.SupplierReturn, user, supplier_return_id, "Supplier return")
    if supplier_return.status not in {"replacement_requested", "replacement_partially_received"}:
        raise HTTPException(status_code=409, detail="Replacement must be requested before receipt")
    remaining = supplier_return.replacement_requested_quantity - supplier_return.replacement_received_quantity
    if received_quantity <= 0 or received_quantity > remaining:
        raise HTTPException(status_code=409, detail=f"Replacement receipt exceeds the remaining quantity ({remaining:g})")
    if not supplier_challan.strip():
        raise HTTPException(status_code=422, detail="Supplier challan is required")
    gate = models.GateEntry(
        tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=supplier_return.po_draft_id,
        status="replacement_admitted", vehicle_number=vehicle_number, supplier_challan=supplier_challan,
        packages_count=packages_count, arrival_notes=f"Replacement for {supplier_return.business_number}", received_at=utcnow(),
    )
    db.add(gate); db.flush()
    receipt = models.StoreReceipt(
        tenant_id=user.tenant_id, plant_id=user.plant_id, business_number=next_business_number(db, "REC", user),
        po_draft_id=supplier_return.po_draft_id, gate_entry_id=gate.id, supplier_return_id=supplier_return.id,
        status="replacement_received", received_quantity=received_quantity,
        short_quantity=0, excess_quantity=0, damaged_quantity=0,
    )
    db.add(receipt); db.flush()
    supplier_return.replacement_received_quantity += received_quantity
    supplier_return.status = "replacement_received" if supplier_return.replacement_received_quantity >= supplier_return.replacement_requested_quantity else "replacement_partially_received"
    quality_membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, default_plant_id=user.plant_id, role=QUALITY_INSPECTOR, status="active",
    ).first()
    db.add(models.Task(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        title=f"Reinspect replacement {receipt.business_number}", owner_role=QUALITY_INSPECTOR,
        owner_user_id=quality_membership.user_id if quality_membership else None,
        owner_membership_id=quality_membership.id if quality_membership else None,
        due_at=utcnow() + timedelta(hours=4), status="open", severity="critical",
        linked_case_id=supplier_return.case_id, entity_type="store_receipts", entity_id=receipt.id,
    ))
    create_audit(db, user.tenant_id, user.plant_id, user.name, "supplier_replacement.received", "store_receipt", receipt.id, actor_user_id=user.id, meta={"supplier_return_id": supplier_return.id})
    return receipt


def close_case(db: Session, user: models.User, case_id: str, resolution: str = "Closed by owner", override: bool = False, override_reason: str | None = None) -> models.Case:
    case = get_scoped_or_404(db, models.Case, user, case_id, "Case")
    if user.role not in {ADMIN, PLANT_MANAGER, case.owner_role}:
        raise HTTPException(status_code=403, detail="Role is not allowed to close this case")
    unresolved: list[str] = []
    if case.po_draft_id:
        po = get_scoped_or_404(db, models.PODraft, user, case.po_draft_id, "PO draft")
        ordered = _ordered_quantity(db, user, po)
        receipts = user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.po_draft_id == po.id).all()
        original_receipts = [receipt for receipt in receipts if not receipt.supplier_return_id]
        if sum(receipt.received_quantity for receipt in original_receipts) < ordered:
            unresolved.append("purchase order shortage remains")
        inspections = user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.po_draft_id == po.id).all()
        inspections_by_receipt = {receipt.id: [row for row in inspections if row.receipt_id == receipt.id] for receipt in original_receipts}
        for receipt in original_receipts:
            if receipt.exception_types and not inspections_by_receipt[receipt.id]:
                unresolved.append(f"{receipt.business_number or 'receipt'} exception evidence has not been inspected")
            if any(value in {"missing_certificate", "invalid_certificate"} for value in (receipt.exception_types or [])) and not any(row.certificate_status == "verified" for row in inspections_by_receipt[receipt.id]):
                unresolved.append(f"{receipt.business_number or 'receipt'} certificate evidence remains unresolved")
        if sum(item.held_quantity for item in inspections) > 0:
            unresolved.append("quality hold remains")
        original_receipt_ids = {receipt.id for receipt in original_receipts}
        original_rejected = sum(item.rejected_quantity for item in inspections if item.receipt_id in original_receipt_ids)
        accepted_returns = sum(
            row.return_quantity for row in user_scope_query(db, models.SupplierReturn, user).filter(
                models.SupplierReturn.po_draft_id == po.id,
                models.SupplierReturn.status == "replacement_accepted",
            ).all()
        )
        if original_rejected > accepted_returns:
            unresolved.append("rejected quantity has not been replaced")
    if unresolved:
        if not override:
            raise HTTPException(status_code=409, detail={"message": "Case still has unresolved exceptions", "reasons": unresolved})
        if user.role not in {ADMIN, PLANT_MANAGER} or not override_reason:
            raise HTTPException(status_code=403, detail="Plant Manager/Admin override with rationale is required")
    from_status = case.status
    case.status = "closed"
    case.severity = "good"
    case.resolution = resolution
    case.override_reason = override_reason if override else None
    case.timeline = case.timeline + [{"title": "Case closed", "time": utcnow().strftime("%H:%M"), "actor": user.name, "body": resolution}]
    complete_case_tasks(db, user, case.id)
    record_transition(db, user, "case", case.id, from_status, "closed", resolution)
    create_audit(db, user.tenant_id, user.plant_id, user.name, "case.closed", "case", case.id, actor_user_id=user.id)
    return case


def requirement_lifecycle_state(db: Session, user: models.User, requirement_id: str) -> dict[str, Any]:
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, requirement_id, "Requirement")
    rfqs = user_scope_query(db, models.RFQ, user).filter_by(requirement_id=requirement.id).all()
    rfq_ids = [row.id for row in rfqs]
    quotes = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id.in_(rfq_ids or [""])).all()
    quote_ids = [row.id for row in quotes]
    awards = user_scope_query(db, models.AwardDecision, user).filter(models.AwardDecision.quote_id.in_(quote_ids or [""])).all()
    award_ids = [row.id for row in awards]
    pos = user_scope_query(db, models.PODraft, user).filter(models.PODraft.award_id.in_(award_ids or [""])).filter(
        models.PODraft.status.notin_(["cancelled", "superseded"]),
    ).all()
    blockers: list[str] = []
    records: list[dict[str, Any]] = []
    if not pos:
        blockers.append("No active purchase order exists")
    for po in pos:
        ordered = _ordered_quantity(db, user, po)
        receipts = user_scope_query(db, models.StoreReceipt, user).filter_by(po_draft_id=po.id, supplier_return_id=None).all()
        received = sum(row.received_quantity for row in receipts)
        inspections = user_scope_query(db, models.InspectionResult, user).filter_by(po_draft_id=po.id).all()
        held = sum(row.held_quantity for row in inspections)
        original_receipt_ids = {row.id for row in receipts}
        rejected = sum(row.rejected_quantity for row in inspections if row.receipt_id in original_receipt_ids)
        recovered = sum(row.return_quantity for row in user_scope_query(db, models.SupplierReturn, user).filter_by(
            po_draft_id=po.id, status="replacement_accepted",
        ).all())
        invoices = user_scope_query(db, models.SupplierInvoice, user).filter_by(po_draft_id=po.id).all()
        finance_ready = bool(invoices) and all(user_scope_query(db, models.FinanceHandoff, user).filter_by(invoice_id=invoice.id).first() for invoice in invoices)
        payment_states = []
        for invoice in invoices:
            latest = user_scope_query(db, models.InvoicePaymentStatus, user).filter_by(invoice_id=invoice.id).order_by(models.InvoicePaymentStatus.observed_at.desc()).first()
            payment_states.append(latest.status if latest else "not_synchronized")
        remaining = max(0.0, ordered - received)
        unrecovered = max(0.0, rejected - recovered)
        if remaining > 1e-6: blockers.append(f"{po.business_number or po.id} has {remaining:g} quantity remaining")
        if held > 1e-6: blockers.append(f"{po.business_number or po.id} has {held:g} quantity on quality hold")
        if unrecovered > 1e-6: blockers.append(f"{po.business_number or po.id} has {unrecovered:g} rejected quantity unrecovered")
        if not finance_ready: blockers.append(f"{po.business_number or po.id} is not prepared for finance review")
        if not payment_states or any(status != "paid" for status in payment_states):
            blockers.append(f"{po.business_number or po.id} does not have paid status for every invoice")
        records.append({
            "po_id": po.id, "po_number": po.business_number, "ordered_quantity": ordered,
            "received_quantity": received, "remaining_quantity": remaining, "held_quantity": held,
            "unrecovered_rejected_quantity": unrecovered, "finance_ready": finance_ready,
            "payment_statuses": payment_states,
        })
    open_cases = user_scope_query(db, models.Case, user).filter(
        models.Case.requirement_id == requirement.id, models.Case.status.notin_(["closed", "resolved"]),
    ).count()
    po_ids = [row.id for row in pos]
    inspection_ids = [row.id for row in user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.po_draft_id.in_(po_ids or [""])).all()]
    return_ids = [row.id for row in user_scope_query(db, models.SupplierReturn, user).filter(models.SupplierReturn.po_draft_id.in_(po_ids or [""])).all()]
    case_ids = [row.id for row in user_scope_query(db, models.Case, user).filter(models.Case.requirement_id == requirement.id).all()]
    corrective_sources = [*po_ids, *inspection_ids, *return_ids, *case_ids]
    open_capa = user_scope_query(db, models.SupplierCorrectiveAction, user).filter(
        models.SupplierCorrectiveAction.source_entity_id.in_(corrective_sources or [""]),
        models.SupplierCorrectiveAction.status.notin_(["closed", "cancelled"]),
    ).count()
    if open_cases: blockers.append(f"{open_cases} linked exception case(s) remain open")
    if open_capa: blockers.append(f"{open_capa} supplier corrective action(s) remain open")
    return {
        "requirement_id": requirement.id, "requirement_number": requirement.business_number,
        "status": requirement.status, "eligible_to_close": not blockers,
        "blockers": blockers, "purchase_orders": records,
    }


def close_requirement_lifecycle(db: Session, user: models.User, requirement_id: str) -> models.PurchaseRequirement:
    require_role(user, PLANT_MANAGER, ADMIN)
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, requirement_id, "Requirement")
    if requirement.status == "closed":
        return requirement
    state = requirement_lifecycle_state(db, user, requirement.id)
    if not state["eligible_to_close"]:
        raise HTTPException(status_code=409, detail={"message": "Procurement lifecycle is not ready to close", "blockers": state["blockers"]})
    previous = requirement.status
    requirement.status = "closed"
    record_transition(db, user, "purchase_requirement", requirement.id, previous, "closed", "All procurement, quality, finance, and external payment evidence reconciled")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "requirement.lifecycle_closed", "purchase_requirement", requirement.id, actor_user_id=user.id, meta={"reconciliation": state})
    return requirement


def validate_document_content(filename: str, content_type: str, content: bytes) -> tuple[str, list[str], list[dict[str, Any]]]:
    if len(content) > get_settings().max_upload_bytes:
        errors = ["File exceeds upload limit"]
        return "quarantined_rejected", errors, [{"name": "size", "status": "failed"}]
    errors, checks = document_service.validate_document_bytes(filename, content_type, content)
    return ("quarantined_rejected" if errors else "quarantined_ready_for_extraction", errors, checks)

async def upload_document(db: Session, user: models.User, file: UploadFile, linked_entity_type: str | None, linked_entity_id: str | None) -> models.Document:
    require_role(user, PURCHASE_EXECUTIVE, PURCHASE_MANAGER, STORE_MANAGER, QUALITY_INSPECTOR, ADMIN)
    document, job = await document_service.create_upload(db, user, file, linked_entity_type, linked_entity_id)
    create_audit(db, user.tenant_id, user.plant_id, user.name, "document.uploaded", "document", document.id, actor_user_id=user.id, meta={"job_id": job.id, "storage": "private-object-storage"})
    return document


def document_download_url(db: Session, user: models.User, document_id: str) -> dict[str, Any]:
    document = get_scoped_or_404(db, models.Document, user, document_id, "Document")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "document.download_url_issued", "document", document.id, actor_user_id=user.id)
    return document_service.presigned_download(db, user, document_id)


def ensure_default_connections(db: Session, user: models.User) -> None:
    defaults = [("local", "Local PostgreSQL ERP Simulator", ["master_data", "material_needs", "po_posting", "receipts", "inspections"]), ("oracle_fusion", "Oracle Fusion Procurement", ["draftPurchaseOrders", "lines", "attachments", "validateDocument", "submit"]), ("sap_s4hana", "SAP S/4HANA Procurement", ["API_PURCHASEORDER_PROCESS_SRV", "API_PURCHASEREQ_PROCESS_SRV", "API_MATERIAL_DOCUMENT_SRV"])]
    for provider, name, capabilities in defaults:
        if user_scope_query(db, models.IntegrationConnection, user).filter_by(provider=provider).first():
            continue
        db.add(models.IntegrationConnection(id=next_id(db, models.IntegrationConnection, "CONN"), tenant_id=user.tenant_id, plant_id=user.plant_id, provider=provider, name=name, mode="simulation" if provider == "local" else "configured_when_credentials_present", base_url=None, status="active" if provider == "local" else "not_configured", capabilities=capabilities, secret_ref=f"{provider.upper()}_CREDENTIALS"))


def approve_integration_outbox_event(db: Session, user: models.User, event_id: str) -> models.IntegrationOutboxEvent:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    event = get_scoped_or_404(db, models.IntegrationOutboxEvent, user, event_id, "Integration outbox event")
    if event.status == "pending_approval":
        ensure_transition("outbox", event.status, "approved")
        event.status = "approved"
        event.approved_by_user_id = user.id
        event.approved_at = utcnow()
        create_audit(db, user.tenant_id, user.plant_id, user.name, "integration_outbox.approved", "integration_outbox_event", event.id, actor_user_id=user.id)
    return event


def dispatch_integration_outbox_event(db: Session, user: models.User, event_id: str) -> models.IntegrationOutboxEvent:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    event = get_scoped_or_404(db, models.IntegrationOutboxEvent, user, event_id, "Integration outbox event")
    if event.status not in {"approved", "dispatching", "dispatched", "simulated"}:
        raise HTTPException(status_code=400, detail="Integration event must be approved before dispatch")
    if event.status in {"dispatched", "simulated"}:
        return event
    if event.status == "approved":
        ensure_transition("outbox", event.status, "dispatching")
    event.status = "dispatching"
    event.last_error = None
    create_audit(db, user.tenant_id, user.plant_id, user.name, "integration_outbox.dispatch_queued", "integration_outbox_event", event.id, actor_user_id=user.id, meta={"provider": event.provider})
    return event



def scoped_quote_payload(db: Session, user: models.User, quote: models.SupplierQuote) -> dict[str, Any]:
    lines = user_scope_query(db, models.QuoteLine, user).filter(models.QuoteLine.quote_id == quote.id).all()
    extraction = user_scope_query(db, models.QuoteExtractionRun, user).filter(models.QuoteExtractionRun.quote_id == quote.id).order_by(models.QuoteExtractionRun.created_at.desc()).first()
    verifications = user_scope_query(db, models.QuoteFieldVerification, user).filter(models.QuoteFieldVerification.quote_id == quote.id).all()
    documents = user_scope_query(db, models.Document, user).filter(models.Document.linked_entity_type == "supplier_quote", models.Document.linked_entity_id == quote.id).all()
    payload = record_to_dict(quote) or {}
    payload["lines"] = records_to_dicts(lines)
    payload["evidence"] = extraction.evidence if extraction else []
    payload["extraction"] = record_to_dict(extraction)
    rfq = user_scope_query(db, models.RFQ, user).filter(models.RFQ.id == quote.rfq_id).first()
    supplier = user_scope_query(db, models.Supplier, user).filter(models.Supplier.id == quote.supplier_id).first()
    current = user_scope_query(db, models.SupplierQuote, user).filter(
        models.SupplierQuote.rfq_id == quote.rfq_id,
        models.SupplierQuote.supplier_id == quote.supplier_id,
        models.SupplierQuote.verification_status != "superseded",
    ).order_by(models.SupplierQuote.revision_number.desc(), models.SupplierQuote.created_at.desc()).first()
    def field_metadata(row: models.QuoteFieldVerification) -> dict[str, Any]:
        raw = row.field_name
        field = raw.split(":")[-1]
        labels = {
            "promised_date": "Delivery date", "unit_price": "Unit price", "quantity": "Offered quantity",
            "payment_terms": "Payment terms", "validity_date": "Quotation validity", "quote_date": "Quotation date",
            "quote_number": "Quotation number", "currency": "Currency", "supplier_name": "Supplier name",
        }
        section = "Line items" if raw.startswith("line:") else "Delivery" if "date" in field else "Supplier" if "supplier" in field else "Commercial terms"
        line_reference = None
        if raw.startswith("line:"):
            line_id = raw.split(":")[1]
            line = next((item for item in lines if item.id == line_id), None)
            material = db.get(models.Item, line.item_id) if line else None
            line_reference = material.name if material else "Quotation line"
        data = record_to_dict(row) or {}
        data.update({
            "field_path": raw,
            "display_label": labels.get(field, field.replace("_", " ").title()) + (f" — Material: {line_reference}" if line_reference else ""),
            "section": section,
            "line_reference": line_reference,
            "provenance": {"source": row.source},
            "conflict_state": "conflict" if row.status == "needs_review" and row.confidence < .7 else "none",
        })
        return data
    payload["field_verifications"] = [field_metadata(row) for row in verifications]
    payload["documents"] = records_to_dicts(documents)
    payload["rfq_reference"] = business_reference(rfq, rfq.business_number or "Supplier request", "/rfq-builder", rfq.deadline) if rfq else None
    payload["supplier_reference"] = business_reference(supplier, supplier.name, "/quotes") if supplier else None
    payload["revision_state"] = {"revision": quote.revision_number, "is_current": bool(current and current.id == quote.id), "supersedes_quote_id": quote.supersedes_quote_id}
    payload["document_readiness"] = "ready" if documents else "missing"
    payload["line_summary"] = {"count": len(lines), "total_offered_quantity": sum(float(line.quantity) for line in lines)}
    payload["field_review_counts"] = {
        "total": len(verifications), "needs_review": sum(row.status == "needs_review" for row in verifications),
        "verified": sum(row.status in {"accepted", "verified"} for row in verifications),
    }
    return payload


def rfq_payload(db: Session, user: models.User, rfq: models.RFQ) -> dict[str, Any]:
    lines = user_scope_query(db, models.RFQLine, user).filter(models.RFQLine.rfq_id == rfq.id).all()
    suppliers = user_scope_query(db, models.Supplier, user).filter(models.Supplier.id.in_(rfq.supplier_ids or [""])).all()
    quotes = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id == rfq.id).all()
    outbox = user_scope_query(db, models.OutboxMessage, user).filter(models.OutboxMessage.meta["rfq_id"].as_string() == rfq.id).all()
    payload = record_to_dict(rfq) or {}
    payload["lines"] = records_to_dicts(lines)
    payload["suppliers"] = records_to_dicts(suppliers)
    payload["quotes"] = [scoped_quote_payload(db, user, quote) for quote in quotes]
    payload["comparison_rows"] = [row.model_dump() for row in compare_quotes(db, rfq.id, user)]
    payload["outbox"] = records_to_dicts(outbox)
    payload["invitations"] = records_to_dicts(user_scope_query(db, models.RFQSupplierInvitation, user).filter(models.RFQSupplierInvitation.rfq_id == rfq.id).all())
    return payload


def po_draft_payload(db: Session, user: models.User, po: models.PODraft) -> dict[str, Any]:
    supplier = get_scoped_or_404(db, models.Supplier, user, po.supplier_id, "Supplier")
    award = get_scoped_or_404(db, models.AwardDecision, user, po.award_id, "Award") if po.award_id else None
    quote = get_scoped_or_404(db, models.SupplierQuote, user, award.quote_id, "Quote") if award else None
    asns = user_scope_query(db, models.ASN, user).filter(models.ASN.po_draft_id == po.id).all()
    gates = user_scope_query(db, models.GateEntry, user).filter(models.GateEntry.po_draft_id == po.id).all()
    receipts = user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.po_draft_id == po.id).all()
    inspections = user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.po_draft_id == po.id).all()
    impacts = user_scope_query(db, models.InventoryImpact, user).filter(models.InventoryImpact.po_draft_id == po.id).all()
    events = user_scope_query(db, models.IntegrationOutboxEvent, user).filter(models.IntegrationOutboxEvent.entity_id == po.id).all()
    payload = record_to_dict(po) or {}
    payload["award"] = record_to_dict(award)
    payload["supplier"] = record_to_dict(supplier)
    payload["quote"] = scoped_quote_payload(db, user, quote) if quote else None
    payload["provenance"] = "external_system" if not award else "genuinegigs_award"
    payload["asns"] = records_to_dicts(asns)
    payload["gate_entries"] = records_to_dicts(gates)
    payload["receipts"] = records_to_dicts(receipts)
    payload["inspections"] = records_to_dicts(inspections)
    payload["inventory_impact"] = records_to_dicts(impacts)
    payload["integration_outbox"] = records_to_dicts(events)
    payload["lines"] = records_to_dicts(user_scope_query(db, models.PODraftLine, user).filter(models.PODraftLine.po_draft_id == po.id).all())
    payload["acknowledgements"] = records_to_dicts(user_scope_query(db, models.SupplierAcknowledgement, user).filter(models.SupplierAcknowledgement.po_draft_id == po.id).all())
    return payload


def procurement_cycle_summaries(db: Session, user: models.User) -> list[dict[str, Any]]:
    requirements = user_scope_query(db, models.PurchaseRequirement, user).filter(
        models.PurchaseRequirement.status.notin_(["cancelled", "closed"])
    ).order_by(models.PurchaseRequirement.created_at.desc()).all()
    return [procurement_cycle_summary(db, user, requirement) for requirement in requirements]


def business_reference(record: Any, label: str, route: str, secondary: str | None = None) -> dict[str, Any]:
    """One display contract for selectors, cards, tasks, and audit navigation."""
    return {
        "id": record.id,
        "business_number": getattr(record, "business_number", None) or label,
        "label": label,
        "secondary_context": secondary,
        "status": getattr(record, "status", None) or getattr(record, "verification_status", None),
        "route": route,
    }


def requirement_cycle_stages(db: Session, user: models.User, requirement: models.PurchaseRequirement) -> list[WorkflowStage]:
    rfq = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id == requirement.id).order_by(models.RFQ.created_at.desc()).first()
    quotes = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id == rfq.id, models.SupplierQuote.verification_status != "superseded").all() if rfq else []
    comparison = user_scope_query(db, models.BidComparison, user).filter(models.BidComparison.rfq_id == rfq.id).order_by(models.BidComparison.created_at.desc()).first() if rfq else None
    award = user_scope_query(db, models.AwardDecision, user).filter(models.AwardDecision.rfq_id == rfq.id).order_by(models.AwardDecision.created_at.desc()).first() if rfq else None
    po = user_scope_query(db, models.PODraft, user).filter(models.PODraft.award_id == award.id).order_by(models.PODraft.created_at.desc()).first() if award else None
    gate = user_scope_query(db, models.GateEntry, user).filter(models.GateEntry.po_draft_id == po.id).first() if po else None
    receipt = user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.po_draft_id == po.id).first() if po else None
    inspection = user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.po_draft_id == po.id).first() if po else None
    facts = [
        ("requirement", "Requirement", PURCHASE_EXECUTIVE, "/procurement", True, "Material need captured"),
        ("rfq", "RFQ", PURCHASE_EXECUTIVE, "/rfq-builder", bool(rfq and rfq.status != "draft"), rfq.status.replace("_", " ") if rfq else "Supplier request not started"),
        ("quotes", "Quotations", PURCHASE_MANAGER, "/quotes", bool(quotes and all(q.verification_status == "verified" for q in quotes)), f"{len(quotes)} current response(s)"),
        ("comparison", "Comparison", PURCHASE_MANAGER, "/comparison", bool(comparison and comparison.status == "approved"), comparison.status.replace("_", " ") if comparison else "Waiting for verified quotations"),
        ("po", "Purchase order", PURCHASE_MANAGER, "/po-drafts", bool(po and po.status in {"approved_pending_outbox", "posted", "simulated_posted"}), po.status.replace("_", " ") if po else "Waiting for approved comparison"),
        ("gate", "Gate entry", GATE_OPERATOR, "/gate", bool(gate), gate.status.replace("_", " ") if gate else "Waiting for issued order"),
        ("store", "Receipt", STORE_MANAGER, "/store", bool(receipt), receipt.status.replace("_", " ") if receipt else "Waiting for gate entry"),
        ("quality", "Inspection", QUALITY_INSPECTOR, "/quality", bool(inspection), inspection.status.replace("_", " ") if inspection else "Waiting for receipt"),
    ]
    stages: list[WorkflowStage] = []
    first_incomplete = next((index for index, row in enumerate(facts) if not row[4]), len(facts))
    for index, (key, label, owner, href, done, summary) in enumerate(facts):
        status = "done" if done else "current" if index == first_incomplete else "waiting"
        stages.append(WorkflowStage(key=key, label=label, plain_label=label, technical_label=label, status=status, owner_role=owner, summary=summary, href=href))
    return stages


def procurement_cycle_summary(db: Session, user: models.User, requirement: models.PurchaseRequirement) -> dict[str, Any]:
    item = db.get(models.Item, requirement.item_id)
    rfqs = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id == requirement.id).order_by(models.RFQ.created_at.desc()).all()
    stages = requirement_cycle_stages(db, user, requirement)
    current_index = next((index for index, stage in enumerate(stages) if stage.status in {"current", "blocked"}), 7)
    current = stages[current_index]
    case = user_scope_query(db, models.Case, user).filter(models.Case.id == requirement.related_case_id).first() if requirement.related_case_id else None
    blocked = case if case and case.status not in {"closed", "resolved"} else None
    overdue = bool(requirement.need_by_date and requirement.need_by_date < utcnow().date().isoformat())
    health = "blocked" if blocked else "at_risk" if overdue else "attention" if current.status == "current" and current.owner_role == user.role else "on_track"
    allowed = [current.href] if current.owner_role == user.role or user.role == ADMIN else []
    material_label = item.name if item else "Material"
    return {
        "id": requirement.id,
        "business_number": requirement.business_number or "Requirement",
        "title": f"{material_label} procurement",
        "materials": [business_reference(item, material_label, "/procurement", f"{requirement.quantity:g} {requirement.uom}")] if item else [],
        "rfqs": [business_reference(rfq, rfq.business_number or "Supplier request", "/rfq-builder", rfq.deadline) for rfq in rfqs],
        "health": health,
        "current_stage": current.model_dump(),
        "current_stage_index": current_index + 1,
        "next_stage": stages[current_index + 1].label if current_index + 1 < len(stages) else None,
        "next_owner": current.owner_role or user.role,
        "blocked_dependency": blocked.title if blocked else None,
        "completion_percentage": round(sum(stage.status == "done" for stage in stages) / len(stages) * 100),
        "need_by_date": requirement.need_by_date,
        "due_at": case.due_at.isoformat() if case and case.due_at else None,
        "role_visible_actions": allowed,
        "stages": [stage.model_dump() for stage in stages],
        # Compatibility aliases during the presentation-contract rollout.
        "requirement": requirement.reason,
        "status": requirement.status,
        "severity": "critical" if health in {"blocked", "at_risk"} else "action",
        "owner_role": current.owner_role,
    }


def procurement_cycle_detail(db: Session, user: models.User, cycle_id: str | None = None) -> dict[str, Any]:
    requirement_by_id = user_scope_query(db, models.PurchaseRequirement, user).filter(models.PurchaseRequirement.id == cycle_id).first() if cycle_id else None
    case_query = user_scope_query(db, models.Case, user).order_by(models.Case.created_at.desc())
    case = case_query.filter(models.Case.id == cycle_id).first() if cycle_id and not requirement_by_id else case_query.first() if not cycle_id else None
    if cycle_id and case is None and requirement_by_id is None:
        raise HTTPException(status_code=404, detail="Procurement cycle not found")
    requirements_query = user_scope_query(db, models.PurchaseRequirement, user).order_by(models.PurchaseRequirement.created_at.desc())
    if requirement_by_id:
        requirements_query = requirements_query.filter(models.PurchaseRequirement.id == requirement_by_id.id)
    elif case:
        requirements_query = requirements_query.filter(models.PurchaseRequirement.related_case_id == case.id)
    requirements = requirements_query.all()
    requirement_ids = [requirement.id for requirement in requirements]
    rfqs = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id.in_(requirement_ids or [""])).order_by(models.RFQ.created_at.desc()).all()
    rfq_ids = [rfq.id for rfq in rfqs]
    quotes = user_scope_query(db, models.SupplierQuote, user).filter(models.SupplierQuote.rfq_id.in_(rfq_ids or [""])).order_by(models.SupplierQuote.created_at.desc()).all()
    awards = user_scope_query(db, models.AwardDecision, user).filter(models.AwardDecision.rfq_id.in_(rfq_ids or [""])).order_by(models.AwardDecision.created_at.desc()).all()
    award_ids = [award.id for award in awards]
    po_drafts = user_scope_query(db, models.PODraft, user).filter(models.PODraft.award_id.in_(award_ids or [""])).order_by(models.PODraft.created_at.desc()).all()
    po_ids = [po.id for po in po_drafts]
    audit_query = user_scope_query(db, models.AuditEvent, user).order_by(models.AuditEvent.created_at.desc()).limit(80)
    stages = [stage.model_dump() for stage in (
        requirement_cycle_stages(db, user, requirement_by_id)
        if requirement_by_id else canonical_workflow_stages(db, user, case.id if case else None)
    )]
    procurement_visible = user.role in {PLANT_MANAGER, PURCHASE_MANAGER, PURCHASE_EXECUTIVE, ADMIN}
    inbound_visible = user.role in {PLANT_MANAGER, PURCHASE_MANAGER, GATE_OPERATOR, STORE_MANAGER, QUALITY_INSPECTOR, ADMIN}
    document_visible = user.role in {PLANT_MANAGER, PURCHASE_MANAGER, PURCHASE_EXECUTIVE, QUALITY_INSPECTOR, ADMIN}
    outbox_visible = user.role in {PURCHASE_MANAGER, ADMIN}
    audit_visible = user.role in {PLANT_MANAGER, ADMIN}
    visible_pos = po_drafts
    if user.role in {STORE_MANAGER, QUALITY_INSPECTOR}:
        visible_pos = [po for po in po_drafts if po.status in {"approved_pending_outbox", "posted", "simulated_posted"}]
    return {
        "case": record_to_dict(case),
        "cycle": procurement_cycle_summary(db, user, requirement_by_id) if requirement_by_id else None,
        "stages": stages,
        "requirements": records_to_dicts(requirements) if procurement_visible else [],
        "rfqs": [rfq_payload(db, user, rfq) for rfq in rfqs] if procurement_visible else [],
        "quotes": [scoped_quote_payload(db, user, quote) for quote in quotes] if procurement_visible else [],
        "comparisons": records_to_dicts(user_scope_query(db, models.BidComparison, user).filter(models.BidComparison.rfq_id.in_(rfq_ids or [""])).all()) if procurement_visible else [],
        "awards": records_to_dicts(awards) if procurement_visible else [],
        "po_drafts": [po_draft_payload(db, user, po) for po in visible_pos] if procurement_visible or inbound_visible else [],
        "negotiations": records_to_dicts(user_scope_query(db, models.NegotiationRound, user).filter(models.NegotiationRound.rfq_id.in_(rfq_ids or [""])).all()) if procurement_visible else [],
        "asns": records_to_dicts(user_scope_query(db, models.ASN, user).filter(models.ASN.po_draft_id.in_(po_ids or [""])).all()) if inbound_visible else [],
        "gate_entries": records_to_dicts(user_scope_query(db, models.GateEntry, user).filter(models.GateEntry.po_draft_id.in_(po_ids or [""])).all()) if inbound_visible else [],
        "receipts": records_to_dicts(user_scope_query(db, models.StoreReceipt, user).filter(models.StoreReceipt.po_draft_id.in_(po_ids or [""])).all()) if inbound_visible else [],
        "inspections": records_to_dicts(user_scope_query(db, models.InspectionResult, user).filter(models.InspectionResult.po_draft_id.in_(po_ids or [""])).all()) if inbound_visible else [],
        "inventory_impact": records_to_dicts(user_scope_query(db, models.InventoryImpact, user).filter(models.InventoryImpact.po_draft_id.in_(po_ids or [""])).all()) if inbound_visible else [],
        "documents": records_to_dicts(user_scope_query(db, models.Document, user).order_by(models.Document.created_at.desc()).all()) if document_visible else [],
        "outbox": records_to_dicts(user_scope_query(db, models.OutboxMessage, user).order_by(models.OutboxMessage.created_at.desc()).all()) if outbox_visible else [],
        "integration_outbox": records_to_dicts(user_scope_query(db, models.IntegrationOutboxEvent, user).order_by(models.IntegrationOutboxEvent.created_at.desc()).all()) if outbox_visible else [],
        "audit": records_to_dicts(list(audit_query)) if audit_visible else [],
        "timeline": case.timeline if case else [],
    }


def requirement_detail(db: Session, user: models.User, requirement_id: str) -> dict[str, Any]:
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, requirement_id, "Requirement")
    rfqs = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id == requirement.id).all()
    lines = user_scope_query(db, models.PurchaseRequirementLine, user).filter(models.PurchaseRequirementLine.requirement_id == requirement.id).all()
    return {"requirement": record_to_dict(requirement), "lines": records_to_dicts(lines), "rfqs": [rfq_payload(db, user, rfq) for rfq in rfqs]}


def rfq_detail(db: Session, user: models.User, rfq_id: str) -> dict[str, Any]:
    return rfq_payload(db, user, get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ"))


def quote_detail(db: Session, user: models.User, quote_id: str) -> dict[str, Any]:
    return scoped_quote_payload(db, user, get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote"))


def po_draft_detail(db: Session, user: models.User, po_draft_id: str) -> dict[str, Any]:
    return po_draft_payload(db, user, get_scoped_or_404(db, models.PODraft, user, po_draft_id, "PO draft"))


def quote_field_verifications(db: Session, user: models.User, quote_id: str) -> list[dict[str, Any]]:
    get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote")
    return records_to_dicts(user_scope_query(db, models.QuoteFieldVerification, user).filter(models.QuoteFieldVerification.quote_id == quote_id).all())


def update_rfq(db: Session, user: models.User, rfq_id: str, payload: dict[str, Any]) -> models.RFQ:
    require_role(user, PURCHASE_EXECUTIVE, ADMIN)
    rfq = get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    if rfq.status == "published":
        raise HTTPException(status_code=400, detail="Published RFQs cannot be edited; create a revision instead")
    from_status = rfq.status
    if payload.get("deadline"):
        rfq.deadline = str(payload["deadline"])
    if "supplier_ids" in payload:
        supplier_ids = [str(item) for item in payload.get("supplier_ids") or []]
        for supplier_id in supplier_ids:
            get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
        rfq.supplier_ids = supplier_ids
    line_payload = payload.get("line") or {}
    line = user_scope_query(db, models.RFQLine, user).filter(models.RFQLine.rfq_id == rfq.id).first()
    if line and isinstance(line_payload, dict):
        if line_payload.get("description"):
            line.description = str(line_payload["description"])
        if line_payload.get("quantity") is not None:
            line.quantity = float(line_payload["quantity"])
        if line_payload.get("uom"):
            line.uom = str(line_payload["uom"])
        if line_payload.get("need_by_date"):
            line.need_by_date = str(line_payload["need_by_date"])
        if "required_certificates" in line_payload:
            line.required_certificates = [str(item) for item in line_payload.get("required_certificates") or []]
    record_transition(db, user, "rfq", rfq.id, from_status, rfq.status, "RFQ builder fields updated")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "rfq.updated", "rfq", rfq.id, actor_user_id=user.id)
    return rfq


def receive_buyer_quote(db: Session, user: models.User, payload: dict[str, Any]) -> models.SupplierQuote:
    require_role(user, PURCHASE_EXECUTIVE, PURCHASE_MANAGER, ADMIN)
    rfq = get_scoped_or_404(db, models.RFQ, user, str(payload.get("rfq_id", "")), "RFQ")
    supplier = get_scoped_or_404(db, models.Supplier, user, str(payload.get("supplier_id", "")), "Supplier")
    rfq_lines = user_scope_query(db, models.RFQLine, user).filter(models.RFQLine.rfq_id == rfq.id).all()
    if not rfq_lines:
        raise HTTPException(status_code=400, detail="RFQ has no lines")
    previous = user_scope_query(db, models.SupplierQuote, user).filter(
        models.SupplierQuote.rfq_id == rfq.id, models.SupplierQuote.supplier_id == supplier.id,
        models.SupplierQuote.verification_status != "superseded",
    ).order_by(models.SupplierQuote.revision_number.desc(), models.SupplierQuote.created_at.desc()).first()
    revision_number = previous.revision_number + 1 if previous else 1
    quote = models.SupplierQuote(id=next_id(db, models.SupplierQuote, "Q"), business_number=next_business_number(db, "QUOTE", user), tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id, supplier_id=supplier.id, quote_number=str(payload.get("quote_number") or f"BUYER-{secrets.token_hex(3).upper()}"), quote_date=str(payload.get("quote_date") or date.today().isoformat()), validity_date=str(payload.get("validity_date") or (date.today() + timedelta(days=30)).isoformat()), payment_terms=str(payload.get("payment_terms") or "30 days from GRN"), parser_version=str(payload.get("parser_version") or "buyer-upload@2.0"), model_version="deterministic@2.0", verification_status="needs_review", revision_number=revision_number, supersedes_quote_id=previous.id if previous else None, currency=str(payload.get("currency") or "INR").upper(), exchange_rate_to_inr=1)
    db.add(quote)
    db.flush()
    if previous:
        previous.verification_status = "superseded"
        for task in user_scope_query(db, models.Task, user).filter(
            models.Task.entity_type == "supplier_quotes", models.Task.entity_id == previous.id,
            models.Task.status.in_(["open", "accepted", "in_progress", "review", "pending_approval"]),
        ).all():
            task.status = "completed"
    evidence = _add_quote_lines_and_verifications(db, quote, rfq_lines, payload, "buyer_upload", 0.82)
    db.add(models.QuoteExtractionRun(id=next_id(db, models.QuoteExtractionRun, "EXT"), tenant_id=user.tenant_id, plant_id=user.plant_id, quote_id=quote.id, document_id=None, parser_version="buyer-upload@2.0", model_version="deterministic@2.0", status="needs_review", evidence=evidence, extracted_fields=payload))
    rfq.status = "responses_open"
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, rfq.requirement_id, "Requirement")
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active"
    ).first()
    db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id, title=f"Verify quotation {quote.quote_number}", owner_role=PURCHASE_MANAGER, owner_user_id=user.id, owner_membership_id=membership.id if membership else None, due_at=utcnow() + timedelta(hours=4), status="open", severity="action", linked_case_id=requirement.related_case_id, entity_type="supplier_quotes", entity_id=quote.id))
    record_transition(db, user, "supplier_quote", quote.id, None, "needs_review", "Buyer uploaded supplier quote")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "quote.uploaded", "supplier_quote", quote.id, actor_user_id=user.id, meta={"supplier_id": supplier.id, "rfq_id": rfq.id})
    return quote


def receive_supplier_no_bid(db: Session, raw_token: str, reason: str) -> models.RFQSupplierInvitation:
    portal_token = get_supplier_portal_token(db, raw_token)
    if portal_token.purpose != "rfq_quote" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier RFQ link is invalid or expired")
    invitation = db.query(models.RFQSupplierInvitation).filter_by(
        tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        rfq_id=portal_token.entity_id, supplier_id=portal_token.supplier_id,
    ).first()
    if not invitation:
        raise HTTPException(404, "Supplier invitation not found")
    external_id = f"no-bid:{invitation.rfq_id}:{invitation.supplier_id}"
    existing = db.query(models.SupplierChannelMessage).filter_by(
        tenant_id=portal_token.tenant_id, external_message_id=external_id,
    ).first()
    normalized = reason.strip()
    if existing:
        if existing.body_preview != normalized:
            raise HTTPException(409, "A no-bid response has already been recorded")
        portal_token.used_at = utcnow()
        return invitation
    if invitation.status not in {"sent", "pending", "no_bid"}:
        raise HTTPException(409, "This supplier request already has a response")
    invitation.status = "no_bid"
    portal_token.used_at = utcnow()
    message = models.SupplierChannelMessage(
        tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        channel="portal", direction="inbound", external_message_id=external_id,
        sender=f"supplier:{portal_token.supplier_id}", recipient="GenuineGigs",
        subject="Supplier declined to quote", body_preview=normalized,
        rfq_id=invitation.rfq_id, supplier_id=invitation.supplier_id,
        status="processed", canonical_record_ids=[invitation.rfq_id], document_ids=[],
    )
    db.add(message); db.flush()
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=portal_token.tenant_id, default_plant_id=portal_token.plant_id,
        role=PURCHASE_EXECUTIVE, status="active",
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()
    if membership:
        db.add(models.Notification(
            tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
            user_id=membership.user_id, membership_id=membership.id,
            category="supplier_no_bid", severity="action", title="Supplier declined to quote",
            body=normalized, linked_entity_type="rfq", linked_entity_id=invitation.rfq_id,
            navigation_target=f"/rfq-builder?rfq={invitation.rfq_id}", dedupe_key=external_id,
        ))
    create_audit(db, portal_token.tenant_id, portal_token.plant_id, "Supplier Portal", "rfq.no_bid_received", "rfq_supplier_invitation", invitation.id, meta={"rfq_id": invitation.rfq_id, "supplier_id": invitation.supplier_id})
    return invitation


def attach_uploaded_quote_documents(
    db: Session,
    user: models.User,
    *,
    rfq_id: str,
    supplier_id: str,
    document_ids: list[str],
) -> list[dict[str, Any]]:
    """Link assistant uploads through the canonical buyer-quote workflow.

    One document represents one supplier quotation/revision. Replaying the same
    document is idempotent and returns its existing quotation.
    """
    rfq = get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    supplier = get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
    if supplier.id not in set(rfq.supplier_ids or []):
        raise HTTPException(status_code=422, detail="Supplier is not selected for this supplier request")
    requirement = get_scoped_or_404(
        db, models.PurchaseRequirement, user, rfq.requirement_id, "Requirement",
    )
    capable = user_scope_query(db, models.SupplierItemCapability, user).filter_by(
        supplier_id=supplier.id, item_id=requirement.item_id, approved=True,
    ).first()
    if capable is None:
        raise HTTPException(status_code=422, detail="Supplier is not approved for this material")
    rfq_line = user_scope_query(db, models.RFQLine, user).filter_by(rfq_id=rfq.id).first()
    results: list[dict[str, Any]] = []
    for document_id in dict.fromkeys(document_ids):
        document = get_scoped_or_404(db, models.Document, user, document_id, "Document")
        existing = None
        if document.linked_entity_type == "supplier_quote" and document.linked_entity_id:
            existing = user_scope_query(db, models.SupplierQuote, user).filter_by(
                id=document.linked_entity_id,
            ).first()
        if existing is None:
            quote = receive_buyer_quote(db, user, {
                "rfq_id": rfq.id,
                "supplier_id": supplier.id,
                "quote_number": f"UPLOAD-{document.business_number or document.id}",
                "parser_version": "assistant-upload@2.0",
                "line": {
                    "quantity": float(rfq_line.quantity if rfq_line else 0),
                    "unit_price": 0,
                    "gst_rate": 0,
                    "freight": 0,
                    "packaging": 0,
                    "lead_time_days": 0,
                    "promised_date": "",
                    "moq": float(rfq_line.quantity if rfq_line else 0),
                    "technical_compliance": "pending_verification",
                    "certificates": [],
                },
            })
            document.linked_entity_type = "supplier_quote"
            document.linked_entity_id = quote.id
            extractions = user_scope_query(db, models.QuoteExtractionRun, user).filter_by(
                document_id=document.id,
            ).all()
            for extraction in extractions:
                extraction.quote_id = quote.id
            existing = quote
        job = user_scope_query(db, models.DocumentJob, user).filter_by(
            document_id=document.id,
        ).order_by(models.DocumentJob.created_at.desc()).first()
        results.append({
            "quote_id": existing.id,
            "quote_number": existing.business_number,
            "verification_status": existing.verification_status,
            "document_id": document.id,
            "filename": document.filename,
            "document_status": document.status,
            "job_id": job.id if job else None,
            "job_status": job.status if job else None,
        })
    return results


def store_supplier_document_bytes(db: Session, quote: models.SupplierQuote, filename: str, content_type: str, content: bytes) -> models.Document:
    document, job = document_service.create_upload_bytes(db, quote, filename, content_type, content)
    create_audit(db, quote.tenant_id, quote.plant_id, "Supplier Portal", "document.uploaded", "document", document.id, meta={"quote_id": quote.id, "job_id": job.id})
    return document


async def stream_supplier_document(db: Session, quote: models.SupplierQuote, file: UploadFile) -> models.Document:
    document, job = await document_service.create_quote_upload(db, quote, file)
    create_audit(
        db,
        quote.tenant_id,
        quote.plant_id,
        "Supplier Portal",
        "document.uploaded",
        "document",
        document.id,
        meta={"quote_id": quote.id, "job_id": job.id},
    )
    return document


def create_award_decision(db: Session, user: models.User, rfq_id: str, quote_id: str, supplier_id: str, rationale: str = "Buyer recommended supplier for manager approval") -> models.AwardDecision:
    require_role(user, PURCHASE_EXECUTIVE, ADMIN)
    rfq = get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    quote = get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote")
    get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
    if quote.rfq_id != rfq.id or quote.supplier_id != supplier_id:
        raise HTTPException(status_code=400, detail="Award supplier must match the selected quote")
    if quote.verification_status != "verified":
        raise HTTPException(status_code=409, detail="Only verified quotations can be recommended")
    score = next((item for item in compare_quotes(db, rfq.id, user) if item.quote_id == quote.id and not item.disqualified), None)
    if score is None:
        raise HTTPException(status_code=409, detail="Disqualified quotation cannot be awarded")
    existing = user_scope_query(db, models.AwardDecision, user).filter(models.AwardDecision.rfq_id == rfq.id, models.AwardDecision.quote_id == quote.id).first()
    if existing:
        return existing
    award = models.AwardDecision(id=next_id(db, models.AwardDecision, "AWARD"), tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id, quote_id=quote.id, supplier_id=supplier_id, status="pending_approval", rationale=rationale)
    db.add(award)
    requirement = get_scoped_or_404(db, models.PurchaseRequirement, user, rfq.requirement_id, "Requirement")
    db.add(models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=user.tenant_id, plant_id=user.plant_id, title="Approve recommended supplier award", owner_role=PURCHASE_MANAGER, owner_user_id=None, due_at=utcnow() + timedelta(hours=4), status="pending_approval", severity="critical", linked_case_id=requirement.related_case_id, entity_type="award_decisions", entity_id=award.id))
    record_transition(db, user, "award_decision", award.id, None, "pending_approval", "Buyer submitted award recommendation")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "award.recommended", "award_decision", award.id, actor_user_id=user.id)
    return award


def create_po_draft_from_award_request(db: Session, user: models.User, award_id: str) -> models.PODraft:
    require_role(user, PURCHASE_MANAGER, ADMIN)
    award = get_scoped_or_404(db, models.AwardDecision, user, award_id, "Award")
    if award.status != "approved":
        raise HTTPException(status_code=400, detail="Award must be approved before PO generation")
    po = create_po_draft_for_award(db, user, award)
    record_transition(db, user, "po_draft", po.id, None, po.status, "PO draft generated from approved award")
    create_audit(db, user.tenant_id, user.plant_id, user.name, "po_draft.generated", "po_draft", po.id, actor_user_id=user.id)
    return po
def run_reconciliation(db: Session, user: models.User, entity_type: str, entity_id: str) -> dict[str, Any]:
    from app.erp import get_erp_adapter
    from app.core.metrics import RECONCILIATIONS

    local_payload: dict[str, Any] = {}
    if entity_type == "po_draft":
        local_payload = get_scoped_or_404(db, models.PODraft, user, entity_id, "PO draft").oracle_mapping
    reference = user_scope_query(db, models.IntegrationExternalReference, user).filter(
        models.IntegrationExternalReference.local_entity_type == entity_type,
        models.IntegrationExternalReference.local_entity_id == entity_id,
    ).order_by(models.IntegrationExternalReference.created_at.desc()).first()
    provider = reference.provider if reference else get_settings().erp_provider
    result = get_erp_adapter(provider).reconcile_external_reference(db, user.tenant_id, user.plant_id, entity_type, entity_id)
    external_payload = result.get("payload", {}) if isinstance(result, dict) else {}
    local_hash = normalized_payload_hash(local_payload)
    external_hash = normalized_payload_hash(external_payload) if external_payload else None
    status_value = "matched" if external_hash and local_hash == external_hash else result.get("status", "unmatched")
    differences = {} if status_value == "matched" else {"local": local_payload, "external": external_payload}
    reconciliation = models.ReconciliationResult(id=next_id(db, models.ReconciliationResult, "RECON"), tenant_id=user.tenant_id, plant_id=user.plant_id, provider=result.get("provider", provider), entity_type=entity_type, entity_id=entity_id, status=status_value, local_hash=local_hash, external_hash=external_hash, differences=differences)
    db.add(reconciliation)
    RECONCILIATIONS.labels(provider, status_value).inc()
    connection = user_scope_query(db, models.IntegrationConnection, user).filter(models.IntegrationConnection.provider == provider).first()
    job = models.IntegrationSyncJob(id=next_id(db, models.IntegrationSyncJob, "SYNC"), tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id if connection else provider, job_type="reconciliation", status="completed", started_at=utcnow(), finished_at=utcnow(), summary={"reconciliation_id": reconciliation.id, "status": status_value, "provider": provider, "differences": differences})
    db.add(job)
    create_audit(db, user.tenant_id, user.plant_id, user.name, "integration.reconciled", entity_type, entity_id, actor_user_id=user.id)
    return {"job_id": job.id, "reconciliation_id": reconciliation.id, "status": status_value, "provider": provider, "differences": differences}

def control_tower_snapshot(db: Session, user: models.User) -> ControlTowerSnapshot:
    tenant = db.get(models.Tenant, user.tenant_id)
    plant = db.get(models.Plant, user.plant_id)
    cases = user_scope_query(db, models.Case, user).order_by(models.Case.created_at.desc()).all()
    tasks = user_scope_query(db, models.Task, user).all()
    evidence: list[EvidenceItem] = []
    timeline: list[TimelineEvent] = []
    if cases:
        for item in cases[0].evidence:
            evidence.append(EvidenceItem(label=item["label"], value=item["value"], source=item["source"], meta=item["meta"]))
        for event in cases[0].timeline:
            timeline.append(TimelineEvent(title=event["title"], occurred_at_label=event.get("time", ""), actor=event.get("actor", "System"), body=event.get("body", "")))
    active_case = cases[0] if cases else None
    requirement = user_scope_query(db, models.PurchaseRequirement, user).filter(models.PurchaseRequirement.related_case_id == active_case.id).first() if active_case else None
    rfq = user_scope_query(db, models.RFQ, user).filter(models.RFQ.requirement_id == requirement.id).order_by(models.RFQ.created_at.desc()).first() if requirement else None
    comparison = comparison_rows(db, rfq.id, user) if rfq else []
    agent = user_scope_query(db, models.AgentProfile, user).filter(models.AgentProfile.role == PURCHASE_EXECUTIVE).first()
    recommended = next((row.supplier for row in comparison if row.decision == "Recommended"), "Awaiting verified quotes")
    return ControlTowerSnapshot(tenant_name=tenant.name if tenant else "Unknown Tenant", plant_name=plant.name if plant else "Unknown Plant", erp_mode="simulated" if get_settings().erp_write_mode != "live" else "write_enabled", open_cases=len([case for case in cases if case.status not in {"closed", "resolved"}]), pending_approvals=len([task for task in tasks if task.status == "pending_approval"]), supplier_exceptions=len([case for case in cases if case.severity in {"critical", "action"}]), ai_disabled_ready=True, cases=[ProcurementCase(id=case.id, requirement=case.requirement, supplier=case.supplier, owner_role=Role(case.owner_role), due_label="Today" if case.due_at and case.due_at.date() <= utcnow().date() else case.due_at.strftime("%d %b") if case.due_at else "No due date", value_label=f"Rs. {case.value_amount / 100000:.1f}L", status=case.status.replace("_", " "), severity=Severity(case.severity)) for case in cases], quote_comparison=comparison, evidence=evidence, timeline=timeline, recommendation=AgentRecommendation(agent_role=Role.PURCHASE_EXECUTIVE, recommended_supplier=recommended, primary_reason="Recommendation is generated from verified landed cost, delivery, certificate, quality, and delivery-history gates.", tradeoff_label="Human approval required before award or ERP action", next_action="Complete the next role queue item", requires_human_approval=True, allowed_actions=agent.allowed_actions if agent else [], blocked_actions=agent.blocked_actions if agent else []))


def role_specific_actions(db: Session, user: models.User, user_tasks: list[models.Task]) -> list[NextAction]:
    actions = [task_next_action(task, db, True) for task in user_tasks if task.status in {"open", "pending_approval"}]
    if user.role == PLANT_MANAGER:
        case = user_scope_query(db, models.Case, user).filter(models.Case.status.notin_(["closed", "resolved"])).first()
        if case:
            actions.insert(0, NextAction(id="plant-risk-summary", title="Summarize open material risks", description="See what each department must do next before the commitment slips.", role=PLANT_MANAGER, severity=Severity.CRITICAL, entity_type="cases", entity_id=case.id, path="/agents/actions", body={"agent_id": "agt-plant-manager", "action": "summarize_risks", "context_id": case.id}))
    if user.role == STORE_MANAGER and not actions:
        po = user_scope_query(db, models.PODraft, user).filter(models.PODraft.status.in_(["simulated_posted", "posted"])).first()
        if po:
            actions.append(NextAction(id=f"store-receipt-{po.id}", title="Record store receipt", description="Confirm received quantity, shortage, excess, and damage.", role=STORE_MANAGER, severity=Severity.ACTION, entity_type="po_drafts", entity_id=po.id, path="/inbound/receipts", body={"po_draft_id": po.id, "received_quantity": po.oracle_mapping.get("quantity", 0), "damaged_quantity": 0}))
    if user.role == QUALITY_INSPECTOR and not actions:
        receipt = user_scope_query(db, models.StoreReceipt, user).first()
        if receipt:
            actions.append(NextAction(id=f"quality-inspection-{receipt.id}", title="Record quality inspection", description="Confirm accepted, rejected, and held material before inventory impact.", role=QUALITY_INSPECTOR, severity=Severity.ACTION, entity_type="store_receipts", entity_id=receipt.id, path="/inbound/inspections", body={"receipt_id": receipt.id, "inspected_quantity": receipt.received_quantity, "accepted_quantity": receipt.received_quantity, "rejected_quantity": 0, "held_quantity": 0}))
    return actions


def run_agent_action(db: Session, request: AgentActionRequest, user: models.User | None = None) -> AgentActionResponse:
    agent = user_scope_query(db, models.AgentProfile, user).filter(models.AgentProfile.id == request.agent_id).first() if user else db.get(models.AgentProfile, request.agent_id)
    actor = user.name if user else (agent.display_name if agent else "Unknown Agent")
    tenant_id = user.tenant_id if user else (agent.tenant_id if agent else "tenant-apex")
    plant_id = user.plant_id if user else (agent.plant_id if agent else "plant-pune-01")
    if agent is None:
        audit = create_audit(db, tenant_id, plant_id, actor, request.action, "agent_context", request.context_id, "blocked")
        return AgentActionResponse(agent_id=request.agent_id, action=request.action, allowed=False, result="Unknown or out-of-scope agent", audit_event_id=audit.id)
    if request.action in agent.blocked_actions or request.action not in agent.allowed_actions:
        audit = create_audit(db, tenant_id, plant_id, agent.display_name, request.action, "agent_context", request.context_id, "blocked", meta={"provider": get_settings().ai_provider, "model": "policy-engine@1.0"})
        return AgentActionResponse(agent_id=agent.id, action=request.action, allowed=False, result="Action blocked by role-bound agent policy", audit_event_id=audit.id)
    created_task_id = None
    if request.action == "create_follow_up_task":
        case = db.query(models.Case).filter_by(id=request.context_id, tenant_id=agent.tenant_id, plant_id=agent.plant_id).first()
        if case is None:
            audit = create_audit(db, agent.tenant_id, agent.plant_id, agent.display_name, request.action, "agent_context", request.context_id, "blocked")
            return AgentActionResponse(agent_id=agent.id, action=request.action, allowed=False, result="Case is outside agent scope", audit_event_id=audit.id)
        existing_task = db.query(models.Task).filter_by(tenant_id=agent.tenant_id, plant_id=agent.plant_id, owner_user_id=agent.user_id, entity_type="supplier_follow_up", linked_case_id=case.id, status="open").first()
        if existing_task:
            created_task_id = existing_task.id
        else:
            task = models.Task(id=next_id(db, models.Task, "TASK"), tenant_id=agent.tenant_id, plant_id=agent.plant_id, title=f"Follow up recovery for {case.title}", owner_role=PURCHASE_EXECUTIVE, owner_user_id=agent.user_id, due_at=utcnow() + timedelta(hours=4), status="open", severity="critical", linked_case_id=case.id, entity_type="supplier_follow_up", entity_id=case.id)
            db.add(task)
            created_task_id = task.id
    messages = {"draft_rfq": "Drafted RFQ from approved requirement, supplier shortlist, certificates, and need-by date.", "extract_quote": "Queued deterministic extraction with evidence markers and manual verification gates.", "explain_comparison": "Explained supplier tradeoffs from landed cost, delivery, certificates, quality, and delivery history.", "draft_negotiation": "Drafted negotiation request preserving promised delivery and certificates.", "create_follow_up_task": "Created recovery follow-up task for the open exception.", "summarize_risks": "Summarized open material risk, owner, due date, and next required role action.", "request_updates": "Prepared update request for purchase, store, and quality owners.", "escalate_overdue_case": "Escalation summary prepared for Plant Manager review."}
    audit = create_audit(db, agent.tenant_id, agent.plant_id, agent.display_name, f"agent.{request.action}", "agent_context", request.context_id, meta={"provider": get_settings().ai_provider, "model": "ai-disabled-template@1.0"})
    return AgentActionResponse(agent_id=agent.id, action=request.action, allowed=True, result=messages.get(request.action, "Agent action completed"), created_task_id=created_task_id, audit_event_id=audit.id)
