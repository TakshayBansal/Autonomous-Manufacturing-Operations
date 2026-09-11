import hashlib
import json
import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, TypedDict

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agent_schemas import (
    AgentContextEnvelope,
    AgentMessageRequest,
    AgentProcurementFacts,
    AgentResponseBlock,
    AgentTurnDecision,
    IntentEnvelope,
    DelegationCreateRequest,
    DelegationResponseRequest,
    ObjectiveCreateRequest,
    ProposalCreateRequest,
    ToolResult,
    ThreadCreateRequest,
    WorkspaceCreateRequest,
)
from app.agent_capabilities import (
    CAPABILITY_REGISTRY, capabilities_for_role, execute_capability_adapter,
    register_capability_adapter, validate_intent,
)
from app.agent_resolution import resolve_requirement_reference
from app.agent_runtime import run_bounded_tool_loop
from app.agent_state import (
    apply_intent, attach_documents, load_thread_state, persist_thread_state,
    remember_entity, select_context,
)
from app.core.config import get_settings
from app.core.metrics import AGENT_RUNS, AGENT_RUN_LATENCY, AGENT_TOOL_CALLS
from app.core.permissions import ADMIN, GATE_OPERATOR, PLANT_MANAGER, PURCHASE_EXECUTIVE
from app.db import models
from app.domains import workflows


logger = logging.getLogger(__name__)


READ_CAPABILITIES = {
    'answer_work_context', 'list_my_tasks', 'list_team_tasks', 'get_record',
    'list_approved_materials', 'search_approved_material',
    'review_quote_extraction', 'summarize_procurement_risks',
    'summarize_team_status', 'request_task_update',
    'review_excel_import',
    'review_supplier_compliance',
    'summarize_supplier_performance',
    'check_invoice_payment_status',
    'list_supplier_deliveries',
    'review_requirement_lifecycle',
    'get_daily_brief', 'summarize_management_metrics', 'review_workspace_readiness',
    'explain_procurement_policy',
}
PROPOSAL_CAPABILITIES = {
    capability.capability_id for capability in capabilities_for_role('admin')
    if capability.controlled
} | {
    'publish_rfq_proposal', 'submit_comparison_proposal',
    'record_comparison_decision_proposal', 'confirm_purchase_order_proposal',
    'prepare_gate_entry_proposal', 'prepare_store_receipt_proposal',
    'prepare_quality_inspection_proposal', 'create_material_master_request',
}


def capability_category(capability_id: str) -> str:
    if capability_id in READ_CAPABILITIES:
        return 'read'
    if capability_id in PROPOSAL_CAPABILITIES:
        return 'proposal'
    return 'mutation'


CONTROLLED_ACTIONS = {
    "publish_rfq": ("rfqs", "purchase_executive"),
    "submit_comparison": ("bid_comparison", "purchase_manager"),
    "decide_comparison": ("bid_comparison", "comparison_approver"),
    "record_gate_entry": ("po_drafts", GATE_OPERATOR),
    "record_store_receipt": ("po_drafts", "store_manager"),
    "confirm_purchase_order": ("bid_comparison", "purchase_manager"),
    "approve_negotiation": ("negotiation_rounds", "purchase_manager"),
    "approve_award": ("award_decisions", "purchase_manager"),
    "approve_po_draft": ("po_drafts", "purchase_manager"),
    "prepare_po_supplier_email": ("po_drafts", "purchase_manager"),
    "approve_po_change": ("po_drafts", "purchase_manager"),
    "create_asn": ("po_drafts", "store_manager"),
    "dispatch_outbox": ("integration_outbox_events", "purchase_manager"),
    "record_inspection": ("store_receipts", "quality_inspector"),
    "close_case": ("cases", "plant_manager"),
    "prepare_supplier_followup": ("rfqs", "supplier_followup_owner"),
    "verify_quote_fields": ("supplier_quotes", "purchase_manager"),
    "prepare_finance_handoff": ("invoice_match_results", "purchase_manager"),
    "approve_excel_import": ("integration_import_batches", ADMIN),
    "request_supplier_replacement": ("supplier_returns", "purchase_manager"),
    "record_replacement_receipt": ("supplier_returns", "store_manager"),
    "decide_supplier_certificate": ("supplier_certificates", "purchase_manager"),
    "close_requirement_lifecycle": ("purchase_requirements", "plant_manager"),
}

ROLE_DRAFT_TOOLS = {
    "plant_manager": ["decompose_objective", "prepare_follow_up", "summarize_team_status"],
    "purchase_executive": ["draft_rfq", "explain_comparison", "prepare_approval_review"],
    "purchase_manager": ["extract_quote", "prepare_comparison", "draft_negotiation", "prepare_purchase_order", "summarize_approval_risk"],
    GATE_OPERATOR: ["lookup_purchase_order", "prepare_gate_entry_checklist"],
    "store_manager": ["prepare_inbound_checklist", "collect_discrepancy_evidence"],
    "quality_inspector": ["prepare_inspection_checklist", "review_certificates", "draft_disposition"],
    "admin": ["configuration_diagnostics", "explain_policy"],
}

RESTRICTED_ACTIONS = [
    "approve", "publish", "post_to_erp", "update_inventory", "change_master_data",
    "change_permissions", "close_exception", "impersonate_user", "unrestricted_http", "generic_sql",
]

IMPLEMENTED_AGENT_TOOLS = {
    PLANT_MANAGER: [
        'read_assigned_work', 'lookup_material', 'list_capable_suppliers',
        'list_purchase_executives', 'create_requirement_and_delegate',
    ],
    PURCHASE_EXECUTIVE: [
        'read_assigned_work', 'read_linked_records', 'prepare_rfq_draft',
    ],
    'purchase_manager': [
        'read_assigned_work', 'read_linked_records',
        'prepare_verified_comparison', 'prepare_purchase_order_proposal',
    ],
    GATE_OPERATOR: ['read_assigned_work', 'read_linked_records'],
    'store_manager': ['read_assigned_work', 'read_linked_records'],
    'quality_inspector': ['read_assigned_work', 'read_linked_records'],
    ADMIN: ['read_assigned_work', 'read_linked_records'],
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_run_event(
    db: Session, run: models.AgentRun, event_type: str, payload: dict[str, Any] | None = None,
) -> models.AgentEvent:
    sequence = db.query(models.AgentEvent).filter_by(
        tenant_id=run.tenant_id, run_id=run.id,
    ).count() + 1
    event = models.AgentEvent(
        tenant_id=run.tenant_id, plant_id=run.plant_id, run_id=run.id,
        sequence=sequence, event_type=event_type, payload=payload or {},
        visibility='private',
    )
    db.add(event)
    db.flush()
    return event


def record_run_checkpoint(
    db: Session,
    run: models.AgentRun,
    step_name: str,
    state_data: dict[str, Any],
    status: str = 'completed',
) -> models.AgentCheckpoint:
    serialized = json.dumps(state_data, sort_keys=True, default=str)
    maximum = get_settings().agent_max_context_bytes
    if len(serialized.encode()) > maximum:
        raise HTTPException(
            status_code=413,
            detail='Agent checkpoint exceeds the configured safety budget.',
        )
    sequence = db.query(models.AgentCheckpoint).filter_by(
        tenant_id=run.tenant_id, run_id=run.id,
    ).count() + 1
    checkpoint = models.AgentCheckpoint(
        tenant_id=run.tenant_id,
        plant_id=run.plant_id,
        run_id=run.id,
        thread_id=run.thread_id,
        sequence=sequence,
        step_name=step_name,
        state_data=json.loads(serialized),
        state_hash=hashlib.sha256(serialized.encode()).hexdigest(),
        status=status,
    )
    db.add(checkpoint)
    db.flush()
    return checkpoint


def enforce_agent_run_limits(db: Session, membership: models.WorkspaceMembership) -> None:
    settings = get_settings()
    window_start = utcnow() - timedelta(minutes=1)
    recent_runs = db.query(models.AgentRun).filter(
        models.AgentRun.tenant_id == membership.tenant_id,
        models.AgentRun.membership_id == membership.id,
        models.AgentRun.created_at >= window_start,
    ).count()
    if recent_runs >= settings.agent_requests_per_minute:
        raise HTTPException(
            status_code=429,
            detail='Agent request rate exceeded. Normal workflows remain available.',
        )


def record_dict(record: Any) -> dict[str, Any]:
    """Return ORM records safe for JSON columns as well as HTTP responses.

    Agent blocks persist this representation in a JSON column.  SQLAlchemy
    exposes timestamp columns as ``datetime`` objects, which PostgreSQL's JSON
    serializer deliberately does not accept.
    """
    return jsonable_encoder({
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
    })


def exact_supplier_identity_from_text(
    text: str, suppliers: list[Any],
) -> tuple[Any | None, str | None]:
    """Resolve unique exact supplier identity evidence in document text."""
    normalized_text = re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()
    if not normalized_text:
        return None, None
    padded_text = f' {normalized_text} '
    vendor_matches = [
        supplier for supplier in suppliers
        if (vendor_id := re.sub(
            r'[^a-z0-9]+', ' ', str(supplier.erp_vendor_id or '').casefold(),
        ).strip())
        and f' {vendor_id} ' in padded_text
    ]
    if len(vendor_matches) == 1:
        return vendor_matches[0], 'exact_document_erp_vendor_id'
    name_matches = [
        supplier for supplier in suppliers
        if (name := re.sub(
            r'[^a-z0-9]+', ' ', str(supplier.name or '').casefold(),
        ).strip())
        and f' {name} ' in padded_text
    ]
    if len(name_matches) == 1:
        return name_matches[0], 'exact_document_supplier_name'
    return None, None


def membership_for_user(db: Session, user: models.User) -> models.WorkspaceMembership:
    membership = db.query(models.WorkspaceMembership).filter_by(
        user_id=user.id, tenant_id=user.tenant_id, status="active"
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="Workspace membership is required")
    return membership


def profile_for_membership(db: Session, membership: models.WorkspaceMembership) -> models.AgentProfile:
    profile = db.query(models.AgentProfile).filter_by(
        tenant_id=membership.tenant_id, membership_id=membership.id, user_id=membership.user_id
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="No role agent is configured for this membership")
    return profile


def assert_agent_available(db: Session, membership: models.WorkspaceMembership) -> models.AgentProfile:
    if not get_settings().agent_enabled:
        raise HTTPException(status_code=503, detail="Agents are disabled for this deployment; normal workflows remain available")
    tenant = db.get(models.Tenant, membership.tenant_id)
    if tenant is None or not tenant.agent_enabled:
        raise HTTPException(status_code=503, detail="Agents are disabled for this workspace; normal workflows remain available")
    profile = profile_for_membership(db, membership)
    if not profile.enabled:
        raise HTTPException(status_code=503, detail="This role agent is currently disabled")
    return profile


def reporting_descendants(db: Session, membership: models.WorkspaceMembership) -> list[str]:
    descendants: list[str] = []
    frontier = [membership.id]
    while frontier:
        rows = db.query(models.WorkspaceMembership).filter(
            models.WorkspaceMembership.tenant_id == membership.tenant_id,
            models.WorkspaceMembership.manager_membership_id.in_(frontier),
            models.WorkspaceMembership.status == "active",
        ).all()
        frontier = [row.id for row in rows if row.id not in descendants]
        descendants.extend(frontier)
    return descendants


def task_for_membership(db: Session, membership: models.WorkspaceMembership, task_id: str) -> models.Task:
    task = db.query(models.Task).filter_by(
        id=task_id, tenant_id=membership.tenant_id, plant_id=membership.default_plant_id
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Work item not found")
    owned = task.owner_membership_id == membership.id or task.owner_user_id == membership.user_id
    shared = task.shared_queue and task.owner_role == membership.role
    if not owned and not shared:
        raise HTTPException(status_code=403, detail="Work item is outside this employee agent's scope")
    return task


def thread_for_membership(db: Session, membership: models.WorkspaceMembership, thread_id: str) -> models.AgentThread:
    thread = db.query(models.AgentThread).filter_by(
        id=thread_id, tenant_id=membership.tenant_id,
        plant_id=membership.default_plant_id, status='active',
    ).first()
    if thread is None:
        raise HTTPException(status_code=404, detail="Agent thread not found")
    if thread.membership_id != membership.id and membership.id not in set(thread.participant_membership_ids or []):
        raise HTTPException(status_code=403, detail="Private agent thread access denied")
    return thread


GENERIC_THREAD_TITLES = {
    'my work assistant', 'new conversation', 'chat', 'agent chat',
    'personal conversation', 'untitled conversation',
}


def conversation_title(content: str) -> str:
    """Create a concise, differentiating label from the employee's first turn."""
    clean = re.sub(r'\s+', ' ', content).strip()
    rfq = re.search(r'\bRFQ-[A-Z0-9-]+\b', clean, re.I)
    if rfq and re.search(r'\b(?:quote|quotation|supplier)\w*\b', clean, re.I):
        return f'Quotation intake · {rfq.group(0).upper()}'
    requirement = re.search(r'\bREQ-[A-Z0-9-]+\b', clean, re.I)
    if requirement:
        return f'Requirement · {requirement.group(0).upper()}'
    if not clean:
        return 'New conversation'
    words = clean.split()
    shortened = ' '.join(words[:10])
    if len(words) > 10:
        shortened += '…'
    return shortened[:96]


def ensure_thread_title(db: Session, thread: models.AgentThread) -> bool:
    if thread.thread_type != 'personal' or thread.title.strip().casefold() not in GENERIC_THREAD_TITLES:
        return False
    first_message = db.query(models.AgentMessage).filter_by(
        tenant_id=thread.tenant_id, thread_id=thread.id, message_type='user',
    ).order_by(models.AgentMessage.created_at.asc()).first()
    if first_message is None:
        return False
    thread.title = conversation_title(first_message.content)
    return True


def approved_knowledge(db: Session, membership: models.WorkspaceMembership) -> list[models.KnowledgeDocument]:
    candidates = db.query(models.KnowledgeDocument).filter(
        models.KnowledgeDocument.tenant_id == membership.tenant_id,
        models.KnowledgeDocument.approval_state == "approved",
        models.KnowledgeDocument.retired_at.is_(None),
    ).all()
    return [
        item for item in candidates
        if (not item.role_acl or membership.role in item.role_acl)
        and (not item.plant_acl or membership.default_plant_id in item.plant_acl)
    ]


def build_context_envelope(
    db: Session,
    membership: models.WorkspaceMembership,
    thread: models.AgentThread,
    correlation_id: str,
) -> AgentContextEnvelope:
    profile = assert_agent_available(db, membership)
    allowed_entities: dict[str, list[str]] = {}
    if thread.work_item_id:
        task = task_for_membership(db, membership, thread.work_item_id)
        if task.entity_type and task.entity_id:
            allowed_entities[task.entity_type] = [task.entity_id]
        allowed_entities["tasks"] = [task.id]
    if thread.objective_id:
        objective = db.query(models.Objective).filter_by(
            id=thread.objective_id, tenant_id=membership.tenant_id, plant_id=membership.default_plant_id
        ).first()
        visible_objectives = {membership.id, *reporting_descendants(db, membership)}
        if objective is None or objective.owner_membership_id not in visible_objectives:
            raise HTTPException(status_code=403, detail="Objective is outside this agent context")
        allowed_entities["objectives"] = [objective.id]
    settings = get_settings()
    authorized_tools = IMPLEMENTED_AGENT_TOOLS.get(
        membership.role, ['read_assigned_work'],
    )
    role_capabilities = capabilities_for_role(membership.role)
    capability_ids = {row.capability_id for row in role_capabilities}
    authorized_tools = sorted({*authorized_tools, *capability_ids})
    return AgentContextEnvelope(
        tenant_id=membership.tenant_id,
        workspace_id=membership.tenant_id,
        plant_id=membership.default_plant_id,
        membership_id=membership.id,
        role=membership.role,
        reporting_scope=reporting_descendants(db, membership) if membership.role in {PLANT_MANAGER, ADMIN} else [],
        thread_id=thread.id,
        thread_type=thread.thread_type,
        thread_owner_membership_id=thread.membership_id,
        objective_id=thread.objective_id,
        work_item_id=thread.work_item_id,
        allowed_entity_ids=allowed_entities,
        approved_knowledge_ids=[item.id for item in approved_knowledge(db, membership)],
        read_tools=[
            name for name in authorized_tools
            if name.startswith(('read_', 'lookup_', 'list_'))
        ],
        draft_tools=[
            name for name in authorized_tools if name.startswith('prepare_')
        ],
        delegation_tools=[
            name for name in authorized_tools
            if name == 'create_requirement_and_delegate'
        ],
        proposal_tools=[key for key, (_entity, role) in CONTROLLED_ACTIONS.items() if role == membership.role],
        restricted_actions=RESTRICTED_ACTIONS,
        token_budget=profile.token_budget,
        maximum_run_seconds=settings.agent_max_run_seconds,
        maximum_handoffs=settings.agent_max_handoffs,
        maximum_delegation_depth=settings.agent_max_delegation_depth,
        correlation_id=correlation_id,
        policy_version=profile.policy_version,
    )


def create_thread(db: Session, user: models.User, payload: ThreadCreateRequest) -> models.AgentThread:
    membership = membership_for_user(db, user)
    profile = assert_agent_available(db, membership)
    if payload.work_item_id:
        task_for_membership(db, membership, payload.work_item_id)
    if payload.objective_id:
        objective = db.query(models.Objective).filter_by(
            id=payload.objective_id, tenant_id=user.tenant_id, plant_id=user.plant_id
        ).first()
        if objective is None:
            raise HTTPException(status_code=404, detail="Objective not found")
        visible = {membership.id, *reporting_descendants(db, membership)}
        if objective.owner_membership_id not in visible:
            raise HTTPException(status_code=403, detail="Objective thread access denied")
    thread = models.AgentThread(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        membership_id=membership.id,
        agent_profile_id=profile.id,
        thread_type=payload.thread_type,
        title=payload.title,
        work_item_id=payload.work_item_id,
        objective_id=payload.objective_id,
        participant_membership_ids=[membership.id],
        retention_until=utcnow() + timedelta(days=get_settings().agent_conversation_retention_days),
    )
    db.add(thread)
    db.flush()
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, profile.display_name, "agent.thread.created",
        "agent_thread", thread.id, actor_user_id=user.id,
        meta={"membership_id": membership.id, "thread_type": thread.thread_type},
    )
    return thread


def context_payload(db: Session, envelope: AgentContextEnvelope) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload: dict[str, Any] = {
        "role": envelope.role,
        "thread_type": envelope.thread_type,
        "allowed_tools": envelope.read_tools + envelope.draft_tools + envelope.delegation_tools + envelope.proposal_tools,
        "restricted_actions": envelope.restricted_actions,
        'correlation_id': envelope.correlation_id,
    }
    citations: list[dict[str, Any]] = []
    task_ids = envelope.allowed_entity_ids.get("tasks", [])
    if task_ids:
        task = db.get(models.Task, task_ids[0])
        if task:
            payload["work_item"] = {
                "id": task.id, "title": task.title, "status": task.status, "severity": task.severity,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "entity_type": task.entity_type, "entity_id": task.entity_id,
            }
            citations.append({
                "type": "work_item", "id": task.id, "label": task.title,
                "href": f"/workspace/work-items/{task.id}/context",
            })
    objective_ids = envelope.allowed_entity_ids.get("objectives", [])
    if objective_ids:
        objective = db.get(models.Objective, objective_ids[0])
        if objective:
            payload["objective"] = {
                "id": objective.id, "material": objective.material, "quantity": objective.quantity,
                "uom": objective.uom, "need_by_date": objective.need_by_date, "reason": objective.reason,
                "constraints": objective.constraints, "state": objective.state,
            }
            citations.append({
                "type": "objective", "id": objective.id, "label": objective.title,
                "href": f"/objectives/{objective.id}",
            })
    knowledge = db.query(models.KnowledgeDocument).filter(
        models.KnowledgeDocument.id.in_(envelope.approved_knowledge_ids or [""])
    ).all()
    payload["approved_knowledge"] = [
        {"id": item.id, "title": item.title, "content": item.content[:4000]} for item in knowledge
    ]
    citations.extend({
        "type": "knowledge", "id": item.id, "label": item.title, "href": f"/workspace/setup?knowledge={item.id}"
    } for item in knowledge)
    return payload, citations


def deterministic_response(role: str, context: dict[str, Any]) -> str:
    task = context.get("work_item")
    objective = context.get("objective")
    if task:
        next_step = {
            "purchase_executive": "Review the linked need and evidence, fill missing details, then prepare the record for human review.",
            "purchase_manager": "Check recommendation, evidence, exceptions, and authority before making the human-controlled decision.",
            "gate_operator": "Find the issued PO, verify the vehicle and supplier challan, then prepare the gate entry for Stores.",
            "store_manager": "Verify the posted order and inbound references, then record the physical event and discrepancies.",
            "quality_inspector": "Prepare the inspection checklist, verify certificates, and record accepted, rejected, and held quantities.",
            "plant_manager": "Review ownership, commitments, blockers, and overdue dependencies; request a formal update where needed.",
            "admin": "Check workspace configuration, access scope, and policy state without silently changing permissions.",
        }.get(role, "Open the linked record and complete the assigned evidence-backed step.")
        return (
            f"Your task is: {task['title']}. It is {task['status']} with {task['severity']} priority. "
            f"{next_step} I can explain, summarize evidence, or prepare a draft, but controlled actions remain yours to confirm."
        )
    if objective:
        return (
            f"This objective is to procure {objective['quantity']:g} {objective['uom']} of {objective['material']} by "
            f"{objective['need_by_date']}. Work remains scoped to named assignees, and every controlled action stops for human confirmation."
        )
    return (
        f"I am your {role.replace('_', ' ')} agent. I can explain assigned work, use approved knowledge, prepare drafts, "
        "and coordinate typed follow-ups. I cannot inspect another employee's private conversations or exercise human authority."
    )


def response_blocks(answer: str, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = answer.strip()
    paragraphs = [item.strip() for item in clean.split("\n\n") if item.strip()]
    blocks = [AgentResponseBlock(type="summary", title="Answer", text=paragraphs[0] if paragraphs else clean)]
    if len(paragraphs) > 1:
        blocks.append(AgentResponseBlock(type="section", title="Details", text="\n\n".join(paragraphs[1:])))
    if citations:
        blocks.append(AgentResponseBlock(
            type="sources", title="Sources",
            items=[f"{item['label']} ({item['type']}:{item['id']})" for item in citations],
        ))
    if any(word in clean.lower() for word in ("approve", "publish", "confirm", "post to erp", "issue the po")):
        blocks.append(AgentResponseBlock(
            type="confirmation", title="Human decision required",
            text="I can prepare this work, but the authorized employee must review and confirm the controlled action.",
        ))
    return [block.model_dump() for block in blocks]


class GraphState(TypedDict, total=False):
    question: str
    context: dict[str, Any]
    validated: bool
    resolved_entities: dict[str, Any]
    intent_hint: str
    workflow: str
    plan_steps: list[str]
    warnings: list[str]
    response: str


def thread_history(db: Session, thread: models.AgentThread, limit: int = 20) -> list[dict[str, str]]:
    rows = db.query(models.AgentMessage).filter_by(
        tenant_id=thread.tenant_id, thread_id=thread.id, visibility='private'
    ).order_by(models.AgentMessage.created_at.desc()).limit(limit).all()
    return [
        {'id': row.id, 'role': row.message_type, 'content': row.content[:8000]}
        for row in reversed(rows)
    ]


def normalize_need_by_date(text: str, *, today: date | None = None) -> str | None:
    """Normalize the small, deterministic date vocabulary accepted by procurement."""
    value = text.strip().casefold()
    current = today or utcnow().date()
    iso = re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b', value)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).isoformat()
        except ValueError:
            return None
    indian = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b', value)
    if indian:
        try:
            return date(int(indian.group(3)), int(indian.group(2)), int(indian.group(1))).isoformat()
        except ValueError:
            return None
    days = re.search(r'\b(?:in\s+)?(\d+)\s+days?\b', value)
    if days:
        return (current + timedelta(days=int(days.group(1)))).isoformat()
    if re.search(r'\b(?:in\s+)?(?:1|one|a)\s+month\b|\ba month from (?:now|today)\b', value):
        return (current + timedelta(days=30)).isoformat()
    if 'month-end' in value or 'month end' in value or 'end of this month' in value:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        return (next_month - timedelta(days=1)).isoformat()
    if 'next friday' in value:
        distance = (4 - current.weekday()) % 7
        return (current + timedelta(days=distance or 7)).isoformat()
    return None


def extract_procurement_entities(question: str) -> dict[str, Any]:
    """Normalize fields after a capability is evident; it is not an authorization layer."""
    lowered = question.casefold()
    entities: dict[str, Any] = {}
    # Business namespaces are disjoint. In particular, RFQ-2026-0001 must
    # never enter material resolution merely because it resembles an item code.
    namespace_fields = {
        'RFQ': 'rfq_number', 'REQ': 'requirement_number',
        'PO': 'po_number', 'QTN': 'quotation_number',
    }
    business_numbers: set[str] = set()
    for prefix, field in namespace_fields.items():
        match = re.search(rf'\b({prefix}-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b', question, re.I)
        if match:
            value = match.group(1).upper()
            entities[field] = value
            business_numbers.add(value)
    quantity = re.search(
        r'\b(\d+(?:\.\d+)?)\s*(kg|kgs|kilograms?|g|grams?|tonnes?|tons?|mt|ea|units?|m)\b',
        lowered,
    )
    if quantity:
        uom = quantity.group(2).upper()
        uom = {'KGS': 'KG', 'KILOGRAM': 'KG', 'KILOGRAMS': 'KG', 'GRAM': 'G', 'GRAMS': 'G'}.get(uom, uom)
        entities.update(quantity=float(quantity.group(1)), uom=uom)
    code = re.search(r'\b([A-Z]{2,}[A-Z0-9]*-\d{2,})\b', question)
    if (
        code
        and code.group(1).upper() not in business_numbers
        and code.group(1).split('-', 1)[0].upper() not in namespace_fields
    ):
        entities['item_code'] = code.group(1).upper()
    material_patterns = (
        r'(?:find|show|check|do\s+we\s+have)\s+(?:item\s+)?([a-z][a-z0-9 -]*?(?:ingot|sleeve|belt|steel|aluminium|aluminum|copper))(?=\s+in\s+(?:the\s+)?material\s+master|\s*[,.;?]|$)',
        r'(?:name\s+is|material\s+is)\s+([a-z][a-z0-9 -]*?(?:ingot|sleeve|belt|steel|aluminium|aluminum|copper))(?=\s*[,.;]|\s+\d|$)',
        r'[a-z]{2,}[a-z0-9]*-\d{2,}\s*[,]\s*([a-z][a-z0-9 -]*?(?:ingot|sleeve|belt|steel|aluminium|aluminum|copper))(?=\s*[,.;]|\s+\d|$)',
        r'(?:of|for)\s+([a-z][a-z0-9 -]*?(?:ingot|sleeve|belt|steel|aluminium|aluminum|copper))(?=\s*[,.;]|\s+needed\b|\s+need\b|\s+by\b|$)',
        r'(?:buy|procure|purchase|buying)\s+(?:a\s+)?(?:raw[- ]material\s+)?(?:requirement\s+for\s+)?([a-z][a-z0-9 -]*?)(?=\s+\d|\s*[,.;]|$)',
        r'(?:material|master)\s+(?:for\s+)?([a-z][a-z0-9 -]*?(?:ingot|sleeve|belt|steel|aluminium|aluminum|copper))(?=\s*[,.;]|$)',
    )
    for pattern in material_patterns:
        match = re.search(pattern, lowered)
        if match:
            material = re.sub(r'\b(?:raw material|item|new)\b', ' ', match.group(1))
            material = ' '.join(material.split()).strip(' -')
            # Role phrases such as "delegate this to the Purchase Executive"
            # contain the verb "purchase" but are not material references.
            if material and material.casefold() not in {
                'executive', 'manager', 'purchase executive', 'purchase manager',
                'supplier', 'team',
            }:
                entities['material_query'] = material
                break
    need_by = normalize_need_by_date(question)
    if need_by:
        entities['need_by_date'] = need_by
    reason = re.search(r'\b(?:because|reason(?: is|:)?|for the purpose of)\s+(.+?)(?:[.;]|$)', question, re.I)
    if reason:
        entities['reason'] = reason.group(1).strip()
    elif 'raw-material requirement' in lowered or 'raw material requirement' in lowered:
        entities['reason'] = 'Raw material requirement'
    specification = re.search(r'\b(?:specification|spec)(?: is|:)?\s+(.+?)(?:[.;]|$)', question, re.I)
    if specification:
        entities['specification'] = specification.group(1).strip()
    return entities


def catalog_entities_from_message(
    db: Session, user: models.User, question: str,
) -> dict[str, Any]:
    """Resolve explicit catalog names from free text without asking the model to copy IDs.

    This is grounding, not intent routing: only persisted tenant/plant items can be
    returned.  It lets a message such as "ALU-102, Aluminium Ingot" use the exact
    master name even when the supplied code contains a typo.
    """
    normalized_message = ' '.join(re.findall(r'[a-z0-9]+', question.casefold()))
    matches: list[models.Item] = []
    for item in workflows.user_scope_query(db, models.Item, user).all():
        normalized_name = ' '.join(re.findall(r'[a-z0-9]+', item.name.casefold()))
        if normalized_name and re.search(rf'\b{re.escape(normalized_name)}\b', normalized_message):
            matches.append(item)
    if len(matches) != 1:
        return {}
    item = matches[0]
    return {
        'item_id': item.id,
        'item_code': item.code,
        'material_query': item.name,
        'uom': item.uom_id,
    }


def deterministic_intent(
    question: str, current: dict[str, Any], attachment_ids: list[str] | None = None,
) -> IntentEnvelope:
    """Provider-outage continuation for clear capabilities only."""
    lowered = question.casefold()
    entities = extract_procurement_entities(question)
    if re.search(r'\bwhat\s+(?:material\s+)?masters?\b|\blist\s+(?:approved\s+)?materials?\b', lowered):
        intent = 'list_approved_materials' if 'material' in lowered else 'answer_work_context'
    elif re.search(r'\b(?:prepare|create|draft|generate|genrate)\b.*\brfqs?\b', lowered):
        intent = 'prepare_rfq_draft'
    elif re.search(r'\b(?:compare|comparison|comparision)\b.*\b(?:quotes?|quotations?|supplier)', lowered):
        intent = 'prepare_supplier_comparison'
    elif re.search(r'\b(?:create|request|raise)\b.*\b(?:new\s+)?(?:material\s+)?masters?\b', lowered):
        intent = 'create_material_master_request'
    elif re.search(r'\b(?:create|make|raise|complete)\b.*\b(?:requirements?|requirments?|reqirements?|prs?)\b', lowered):
        intent = 'create_purchase_requirement'
    elif entities.get('material_query') or entities.get('item_code'):
        intent = 'search_approved_material'
    elif attachment_ids and re.search(r'\b(?:upload|attach|quote|quotation)\b', lowered):
        intent = 'upload_supplier_quotes'
    else:
        intent = 'answer_work_context'
    return IntentEnvelope(
        intent=intent,
        requested_outcome=question.strip(),
        entities=entities,
        attachment_ids=list(attachment_ids or []),
        confidence=0.9 if intent != 'answer_work_context' else 0.6,
        is_topic_change=bool(
            entities.get('material_query')
            and current.get('material_query')
            and entities['material_query'].casefold() != str(current['material_query']).casefold()
        ),
    )


def decision_as_intent(
    value: IntentEnvelope | AgentTurnDecision, question: str, attachment_ids: list[str] | None = None,
) -> IntentEnvelope:
    if isinstance(value, IntentEnvelope):
        return value
    mapping = {
        'answer': 'answer_work_context',
        'procurement': 'search_approved_material',
        'delegate_procurement': 'create_purchase_requirement',
        'prepare_rfq': 'prepare_rfq_draft',
        'prepare_comparison': 'prepare_supplier_comparison',
        'prepare_po': 'confirm_purchase_order_proposal',
        'task_follow_up': 'request_task_update',
    }
    return IntentEnvelope(
        intent=mapping[value.intent], requested_outcome=value.answer,
        entities=value.facts.model_dump(exclude_none=True),
        attachment_ids=list(attachment_ids or []), confidence=1,
        requires_confirmation=False,
    )


def safe_provider_intent(
    candidate: IntentEnvelope, question: str, current: dict[str, Any], role: str,
) -> tuple[IntentEnvelope, bool]:
    """Keep an invalid model-selected capability from becoming an API error.

    The registry remains the authority. This only handles untrusted provider output;
    direct API validation still rejects unknown capability IDs.
    """
    try:
        validate_intent(candidate, role)
        return candidate, False
    except HTTPException:
        fallback = deterministic_intent(question, current, candidate.attachment_ids)
        try:
            validate_intent(fallback, role)
            return fallback, True
        except HTTPException:
            return IntentEnvelope(
                intent='answer_work_context', requested_outcome=question,
                confidence=0.0,
            ), True


def deterministic_decision(question: str, current: dict[str, Any]) -> AgentTurnDecision:
    lowered = question.lower()
    facts: dict[str, Any] = {}
    quantity = re.search(r'\b(\d+(?:\.\d+)?)\s*(kg|kgs|kilograms?|g|tonnes?|tons?|mt|ea|units?|m)\b', lowered)
    if quantity:
        facts['quantity'] = float(quantity.group(1))
        facts['uom'] = quantity.group(2).upper().replace('KGS', 'KG').replace('KILOGRAMS', 'KG').replace('KILOGRAM', 'KG')
    code = re.search(r'(?:item\s*code\s*(?:is|:)?\s*)?\b([A-Z]{2,}[A-Z0-9]*-\d{2,})\b', question)
    if code:
        facts['item_code'] = code.group(1).upper()
    material = re.search(r'(?:buy|procure|purchase|buying)\s+([a-z][a-z0-9\s-]*?)(?:\s+\d|,|\.|$)', lowered)
    if material:
        facts['material_query'] = material.group(1).strip()
    iso_date = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', question)
    if iso_date:
        facts['need_by_date'] = iso_date.group(1)
    elif re.search(r'\b(?:1|one)\s+month\b', lowered):
        facts['need_by_date'] = (utcnow() + timedelta(days=30)).date().isoformat()
    elif 'end of this month' in lowered:
        today = utcnow().date()
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        facts['need_by_date'] = (next_month - timedelta(days=1)).isoformat()
    elif 'next friday' in lowered:
        today = utcnow().date()
        days = (4 - today.weekday()) % 7
        facts['need_by_date'] = (today + timedelta(days=days or 7)).isoformat()
    if 'master list is fine' in lowered or 'approved supplier' in lowered:
        facts['supplier_master_confirmed'] = True
    explicit = bool(re.search(r'\b(delegate|assign|go ahead|proceed|create the requirement)\b', lowered))
    procurement = bool(facts or any(word in lowered for word in ('procure', 'purchase', 'quotation', 'supplier', 'requirement')))
    assisted_intent = None
    if re.search(r'\\b(prepare|create|draft|generate)\\b.*\\brfq\\b', lowered):
        assisted_intent = 'prepare_rfq'
    elif re.search(r'\\b(compare|comparison)\\b.*\\b(quote|quotation|supplier)', lowered):
        assisted_intent = 'prepare_comparison'
    elif re.search(r'\\b(prepare|create|generate|issue)\\b.*\\b(po|purchase order)\\b', lowered):
        assisted_intent = 'prepare_po'
    elif re.search(r'\\b(follow up|request update|status update)\\b', lowered):
        assisted_intent = 'task_follow_up'
    return AgentTurnDecision(
        intent=assisted_intent or ('delegate_procurement' if explicit else 'procurement' if procurement else 'answer'),
        facts=AgentProcurementFacts(**facts), explicit_execute=explicit,
        answer=(
            'I retained the procurement details from this conversation. '
            'I can create and assign the requirement when the approved material, quantity, need-by date, and assignee are unambiguous.'
            if procurement else
            'The model provider is unavailable, so I can only explain scoped records in limited mode. No operational action was taken.'
        ),
    )


def validate_model_decision(question: str, decision: AgentTurnDecision) -> AgentTurnDecision:
    """Backfill deterministic facts and normalize intent before any tool authorization."""
    parsed = deterministic_decision(question, {})
    facts = decision.facts.model_dump(exclude_none=True)
    for key, value in parsed.facts.model_dump(exclude_none=True).items():
        facts.setdefault(key, value)
    explicit = bool(decision.explicit_execute or parsed.explicit_execute)
    intent = decision.intent
    if parsed.intent in {'procurement', 'delegate_procurement'} and intent == 'answer':
        intent = parsed.intent
    if explicit and parsed.intent in {'procurement', 'delegate_procurement'}:
        intent = 'delegate_procurement'
    return decision.model_copy(update={
        'intent': intent,
        'explicit_execute': explicit,
        'facts': AgentProcurementFacts(**facts),
    })


def merge_procurement_facts(
    thread: models.AgentThread, decision: AgentTurnDecision, message_id: str
) -> dict[str, Any]:
    state = dict(thread.context_state or {})
    current = dict(state.get('procurement') or {})
    provenance = dict(state.get('provenance') or {})
    incoming = decision.facts.model_dump(exclude_none=True)
    prior_material = str(current.get('item_code') or current.get('material_query') or '').casefold()
    next_material = str(incoming.get('item_code') or incoming.get('material_query') or '').casefold()
    if next_material and prior_material and next_material != prior_material:
        for key in ('item_code', 'material_query', 'item_id', 'material_error', 'material_candidates'):
            current.pop(key, None)
            provenance.pop(key, None)
    for key, value in incoming.items():
        current[key] = value
        provenance[key] = {'message_id': message_id, 'source': 'user'}
    state['procurement'] = current
    state['draft_fields'] = current
    state['provenance'] = provenance
    state['field_provenance'] = provenance
    state['intent'] = decision.intent
    state['active_intent'] = decision.intent
    state['updated_at'] = utcnow().isoformat()
    persist_thread_state(thread, load_thread_state(state))
    return current


def merge_intent_entities(
    thread: models.AgentThread, envelope: IntentEnvelope, message_id: str,
) -> dict[str, Any]:
    state = apply_intent(
        load_thread_state(thread.context_state), envelope,
        provenance_message_id=message_id,
    )
    persist_thread_state(thread, state)
    return dict(state.draft_fields)


def approved_material_records(db: Session, user: models.User) -> list[dict[str, Any]]:
    items = workflows.user_scope_query(db, models.Item, user).order_by(models.Item.code.asc()).all()
    specifications = {
        row.item_id: row for row in workflows.user_scope_query(db, models.ItemSpecification, user).all()
    }
    return [{
        'id': item.id,
        'code': item.code,
        'name': item.name,
        'uom': item.uom_id,
        'specification': specifications[item.id].description if item.id in specifications else '',
        'approval_status': 'approved',
    } for item in items]


def material_candidates(
    db: Session, user: models.User, entities: dict[str, Any], limit: int = 5,
) -> list[dict[str, Any]]:
    query = str(entities.get('material_query') or '').strip().casefold()
    code = str(entities.get('item_code') or '').strip().casefold()
    if not query and not code:
        return []
    records = approved_material_records(db, user)
    normalized_query = ' '.join(re.findall(r'[a-z0-9]+', query))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for record in records:
        item_code = str(record['code']).casefold()
        name = str(record['name']).casefold()
        normalized_name = ' '.join(re.findall(r'[a-z0-9]+', name))
        score = 0.0
        if code and item_code == code:
            score = 1.0
        if query and name == query:
            score = max(score, 0.99)
        if normalized_query and normalized_name == normalized_query:
            score = max(score, 0.98)
        if normalized_query:
            tokens = normalized_query.split()
            if tokens and all(token in normalized_name for token in tokens):
                score = max(score, 0.92)
            score = max(score, SequenceMatcher(None, normalized_query, normalized_name).ratio())
        if score >= 0.72:
            ranked.append((score, record))
    ranked.sort(key=lambda row: (-row[0], str(row[1]['code'])))
    return [record for _score, record in ranked[:limit]]


def estimate_provider_tokens(value: Any) -> int:
    """Conservative provider-independent estimate for JSON, prompts, and schemas."""
    serialized = value if isinstance(value, str) else json.dumps(
        value, default=str, separators=(',', ':'),
    )
    return max(1, (len(serialized.encode('utf-8')) + 2) // 3)


def compact_provider_context(context: dict[str, Any]) -> dict[str, Any]:
    """Keep planning state while omitting UI payloads and full knowledge bodies."""
    compact = {
        key: context[key]
        for key in ('role', 'thread_type', 'work_item', 'objective', 'current_work_item')
        if context.get(key) is not None
    }
    if context.get('approved_knowledge'):
        compact['approved_knowledge'] = [
            {'id': row.get('id'), 'title': row.get('title')}
            for row in context['approved_knowledge'][:8]
        ]
    if context.get('attachments'):
        compact['attachments'] = [{
            key: row.get(key) for key in (
                'id', 'document_id', 'filename', 'content_type', 'validation_status', 'status',
                'linked_entity_type', 'linked_entity_id',
                'inferred_supplier_id', 'confirmed_supplier_id',
            ) if row.get(key) is not None
        } for row in context['attachments'][:20]]
    if context.get('entity_candidates'):
        compact['entity_candidates'] = context['entity_candidates'][:5]
    state = context.get('thread_state') or {}
    compact['thread_state'] = {
        key: (
            state.get(key)[:10]
            if key == 'recent_entities' and isinstance(state.get(key), list)
            else state.get(key)
        ) for key in (
            'selected_context', 'active_goal', 'draft_fields', 'unresolved_fields',
            'candidate_mappings', 'continuation_status', 'attachment_refs',
            'pending_confirmation', 'recent_entities',
        ) if state.get(key) not in (None, [], {})
    }
    if context.get('runtime_observations'):
        compact['runtime_observations'] = [{
            key: row.get(key) for key in (
                'tool', 'status', 'business_summary', 'records', 'candidates',
            ) if row.get(key) not in (None, [], {})
        } for row in context['runtime_observations'][-5:]]
    return compact


def lifecycle_capability_ids(
    question: str, context: dict[str, Any], allowed: list[str],
) -> list[str]:
    """Expose the current lifecycle tools; fall back to all tools if the topic is unclear."""
    lowered = question.casefold()
    selected_context = (
        (context.get('thread_state') or {}).get('selected_context') or {}
    )
    selected_type = str(
        selected_context.get('entity_type') or ''
    ).casefold()
    groups = {
        'requirements': {
            'list_approved_materials', 'search_approved_material', 'create_material_master_request',
            'create_purchase_requirement', 'review_requirement_lifecycle',
            'close_requirement_lifecycle_proposal', 'prepare_rfq_draft',
        },
        'quotations': {
            'prepare_rfq_draft', 'publish_rfq_proposal', 'upload_supplier_quotes',
            'review_quote_extraction', 'verify_quote_fields_proposal',
            'record_exchange_rate', 'apply_exchange_rate', 'prepare_supplier_comparison',
            'prepare_supplier_followup', 'review_supplier_compliance',
            'summarize_supplier_performance',
        },
        'award_po': {
            'prepare_supplier_comparison', 'submit_comparison_proposal',
            'record_comparison_decision_proposal', 'confirm_purchase_order_proposal',
            'prepare_negotiation_proposal', 'prepare_po_supplier_email_proposal',
            'prepare_po_change', 'approve_po_change_proposal',
        },
        'delivery_quality': {
            'list_supplier_deliveries', 'prepare_asn_proposal', 'prepare_gate_entry_proposal',
            'prepare_store_receipt_proposal', 'prepare_quality_inspection_proposal',
            'prepare_supplier_return', 'request_supplier_replacement_proposal',
            'prepare_replacement_receipt_proposal', 'close_exception_proposal',
        },
        'invoice': {
            'prepare_invoice_from_attachment', 'match_supplier_invoice',
            'check_invoice_payment_status', 'prepare_finance_handoff_proposal',
        },
        'admin': {
            'review_workspace_readiness', 'preview_excel_import', 'review_excel_import',
            'approve_excel_import_proposal', 'export_excel_exchange',
        },
    }
    signals = {
        'requirements': ('material', 'requirement', 'requisition', 'req-', 'procure', 'purchase'),
        'quotations': ('rfq', 'quotation', 'quote', 'bid', 'supplier', 'qtn-'),
        'award_po': ('comparison', 'award', 'negotiat', 'purchase order', 'po-'),
        'delivery_quality': ('delivery', 'dispatch', 'asn', 'gate', 'receipt', 'quality', 'inspect', 'reject', 'replacement'),
        'invoice': ('invoice', 'payment', 'finance', 'three-way', 'three way'),
        'admin': ('excel', 'import', 'export', 'readiness', 'integration', 'workspace'),
    }
    baseline = {
        'answer_work_context', 'get_record', 'list_my_tasks', 'list_team_tasks',
        'request_task_update', 'delegate_task', 'get_daily_brief',
    }
    chosen = set(baseline)
    matched = False
    for group, words in signals.items():
        if any(word in lowered or word in selected_type for word in words):
            chosen.update(groups[group])
            matched = True
    has_documents = context.get('attachments') and any(
        str(row.get('content_type') or '') !=
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        for row in context['attachments']
    )
    if has_documents:
        quote_signal = any(word in lowered for word in signals['quotations'])
        invoice_signal = any(word in lowered for word in signals['invoice'])
        if quote_signal or not invoice_signal:
            chosen.update(groups['quotations'])
        if invoice_signal or not quote_signal:
            chosen.update(groups['invoice'])
        matched = True
    return [item for item in allowed if item in chosen] if matched else allowed


def provider_response(
    profile: models.AgentProfile, question: str, context: dict[str, Any],
    history: list[dict[str, str]], current_facts: dict[str, Any],
) -> tuple[IntentEnvelope, str, str, str | None]:
    settings = get_settings()
    provider = profile.provider if profile.provider != "disabled" else settings.ai_provider
    if provider == "groq" and settings.groq_api_key:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_groq import ChatGroq

            model = ChatGroq(
                api_key=settings.groq_api_key,
                model=profile.model_profile or settings.agent_primary_model,
                temperature=0.5,
                max_tokens=min(profile.token_budget, settings.agent_planning_max_output_tokens),
                timeout=settings.agent_max_run_seconds,
                max_retries=2,
            )
            descriptions = {
                'answer_work_context': 'Answer or converse using the employee’s authorized work context.',
                'list_my_tasks': 'Read the employee’s current assigned tasks, priorities, or what they should work on next.',
                'list_team_tasks': 'Read tasks inside the manager’s reporting scope.',
                'get_record': 'Read one known business record by its persisted ID.',
                'list_approved_materials': 'List real approved materials in this plant.',
                'search_approved_material': 'Resolve or check one specific material name/code against the approved catalog, including “is X approved?”.',
                'create_material_master_request': 'Prepare or confirm a request for a material that is not in the catalog.',
                'create_purchase_requirement': 'Create a purchase requirement once material, quantity and need-by date are known.',
                'prepare_rfq_draft': 'Prepare an RFQ draft for an exact, selected, recent, or latest eligible persisted requirement.',
                'upload_supplier_quotes': 'Attach the supplied quotation documents to an exact, selected, recent, or safely resolved RFQ and supplier.',
                'review_quote_extraction': 'Read extracted quotation fields and evidence.',
                'record_exchange_rate': 'Record a buyer-sourced currency conversion observation with source and observation time.',
                'apply_exchange_rate': 'Link matching verified exchange-rate evidence to a foreign-currency quotation.',
                'prepare_supplier_comparison': 'Prepare a comparison from verified quotations.',
                'prepare_negotiation_proposal': 'Draft a governed supplier negotiation and request explicit approval.',
                'prepare_po_supplier_email_proposal': 'Prepare the final PO supplier email behind confirmation.',
                'prepare_asn_proposal': 'Prepare an advance shipping notice record behind confirmation.',
                'close_exception_proposal': 'Prepare evidence-backed exception closure behind confirmation.',
                'request_task_update': 'Ask the owner of a reporting-scope task for progress.',
                'delegate_task': 'Assign a governed task down the reporting hierarchy.',
                'summarize_procurement_risks': 'Summarize grounded procurement risks.',
                'summarize_team_status': 'Ask scoped employee agents for grounded progress updates.',
                'preview_excel_import': 'Inspect an attached XLSX external-system workbook and persist a safe dry-run preview.',
                'review_excel_import': 'Explain the latest or selected spreadsheet import counts, conflicts, and row errors.',
                'approve_excel_import_proposal': 'Prepare a clean spreadsheet import for explicit administrator confirmation.',
                'export_excel_exchange': 'Create and verify a new immutable Excel external-system exchange version.',
                'prepare_invoice_from_attachment': 'Classify a validated invoice attachment against a purchase order and prepare extracted values for human review.',
                'match_supplier_invoice': 'Deterministically compare a captured invoice with its purchase order and receipt evidence.',
                'prepare_finance_handoff_proposal': 'Prepare a matched invoice for finance review behind explicit confirmation; never release payment.',
                'prepare_supplier_return': 'Prepare a traceable return for rejected material.',
                'request_supplier_replacement_proposal': 'Prepare a governed replacement request to the supplier behind confirmation.',
                'prepare_replacement_receipt_proposal': 'Prepare receipt of replacement material for confirmation and quality reinspection.',
            }
            allowed_capabilities = list(context.get('allowed_capability_ids', []))
            selected_capabilities = lifecycle_capability_ids(
                question, context, allowed_capabilities,
            )
            tool_specs = [{
                'type': 'function',
                'function': {
                    'name': capability_id,
                    'description': descriptions.get(capability_id, capability_id.replace('_', ' ')),
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'requested_outcome': {'type': 'string'},
                            'entities': ({
                                'type': 'object',
                                'description': (
                                    'Canonical quotation intake arguments understood from natural language. '
                                    'For each file the employee maps, emit one independent attachment mapping.'
                                ),
                                'properties': {
                                    'rfq_reference': {'type': 'string'},
                                    'supplier_reference': {'type': 'string'},
                                    'attachment_mappings': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'properties': {
                                                'attachment_reference': {
                                                    'type': 'string',
                                                    'description': 'Exact filename, attachment ID, or document ID from authorized context.',
                                                },
                                                'supplier_reference': {
                                                    'type': 'string',
                                                    'description': 'Supplier name, supplier ID, or ERP vendor ID understood from the employee.',
                                                },
                                            },
                                            'required': ['attachment_reference', 'supplier_reference'],
                                        },
                                    },
                                },
                                'additionalProperties': True,
                            } if capability_id == 'upload_supplier_quotes' else {
                                'type': 'object',
                                'description': 'Only facts stated by the employee or present in confirmed state.',
                                'additionalProperties': True,
                            }),
                            'referenced_entity_ids': {'type': 'array', 'items': {'type': 'string'}},
                            'is_topic_change': {'type': 'boolean'},
                        },
                        'required': ['requested_outcome'],
                    },
                },
            } for capability_id in selected_capabilities]
            system_prompt = (
                'You are the employee’s capable, conversational work agent. Decide what to do from the whole '
                'conversation, retain confirmed facts across turns, and call the next best authorized tool. '
                'You may use several read tools to resolve the request. Once the supplied runtime observations '
                'are sufficient, answer directly without another tool call. '
                'If the employee asks to create a requirement and material, quantity, and need-by date are known, '
                'call create_purchase_requirement immediately, even if the material code may need server normalization. '
                'A request to prepare an RFQ for the latest eligible requirement must call prepare_rfq_draft. '
                'A request to attach supplied quotation files must call upload_supplier_quotes. '
                'When the employee describes which supplier belongs to which quotation file in any wording or '
                'format, understand the meaning and call upload_supplier_quotes with entities.attachment_mappings. '
                'Use the exact authorized filename/document reference from context for attachment_reference and '
                'the employee’s supplier wording for supplier_reference. Never require a special phrase or syntax. '
                'A question about whether one named/code material is approved must call search_approved_material. '
                'Never ask for supplier, location, commercial terms, '
                'or any field the selected tool does not require. Material candidates are real server records; use '
                'their canonical IDs and codes. A mistyped code plus one exact material name means use the exact-name '
                'record. For greetings or explanations call answer_work_context. Never invent a record or success.'
            )
            recent_history = [{
                **row, 'content': str(row.get('content') or '')[:1500],
            } for row in history[-settings.agent_recent_raw_turns:]]
            provider_payload = {
                'latest_message': question,
                'confirmed_facts': current_facts,
                'recent_conversation': recent_history,
                'authorized_context': compact_provider_context(context),
            }
            request_tokens = (
                estimate_provider_tokens(system_prompt)
                + estimate_provider_tokens(provider_payload)
                + estimate_provider_tokens(tool_specs)
                + min(profile.token_budget, settings.agent_planning_max_output_tokens)
            )
            if request_tokens > settings.agent_provider_request_target_tokens:
                provider_payload['recent_conversation'] = [{
                    **row, 'content': str(row.get('content') or '')[:800],
                } for row in recent_history[-2:]]
                provider_payload['authorized_context'].pop('approved_knowledge', None)
                request_tokens = (
                    estimate_provider_tokens(system_prompt)
                    + estimate_provider_tokens(provider_payload)
                    + estimate_provider_tokens(tool_specs)
                    + min(profile.token_budget, settings.agent_planning_max_output_tokens)
                )
            if request_tokens > settings.agent_provider_request_target_tokens:
                raise HTTPException(
                    status_code=503,
                    detail='Agent context could not be compacted within the provider safety budget',
                )
            context['_provider_request_tokens'] = request_tokens
            result = model.bind_tools(tool_specs, tool_choice='auto').invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=json.dumps(provider_payload, default=str)),
            ])
            if result.tool_calls:
                call = result.tool_calls[0]
                arguments = dict(call.get('args') or {})
                decision = IntentEnvelope(
                    intent=str(call['name']),
                    requested_outcome=str(arguments.pop('requested_outcome', question)),
                    entities=dict(arguments.pop('entities', {}) or {}),
                    referenced_entity_ids=list(arguments.pop('referenced_entity_ids', []) or []),
                    attachment_ids=list(context.get('attachments') and [row['document_id'] for row in context['attachments']] or []),
                    confidence=0.95,
                    is_topic_change=bool(arguments.pop('is_topic_change', False)),
                )
            else:
                content = str(result.content or '').strip()
                decision = IntentEnvelope(
                    intent='answer_work_context',
                    requested_outcome=content or question,
                    entities={'_runtime_final': content} if context.get('runtime_observations') else {},
                    confidence=0.8,
                )
            return decision, 'groq', profile.model_profile or settings.agent_primary_model, None
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception('Agent provider failed; correlation_id=%s', context.get('correlation_id'))
            raise HTTPException(status_code=503, detail="Agent provider unavailable") from exc
    selected = (context.get('thread_state') or {}).get('selected_context') or {}
    if selected.get('business_number') and re.search(r'\b(?:id|identifier|reference|number)\b', question, re.I):
        value = str(selected['business_number'])
        return IntentEnvelope(intent='answer_work_context', requested_outcome=value,
            entities={'_runtime_final': value}, confidence=1), 'deterministic', 'context-reference@1', None
    if getattr(settings, 'agent_allow_deterministic_fallback', False):
        fallback = deterministic_intent(question, current_facts)
        return fallback, 'deterministic', 'intent-fallback@1', 'ProviderUnavailable'
    raise HTTPException(status_code=503, detail="No workspace-approved agent provider is configured")


def compose_grounded_answer(
    profile: models.AgentProfile, question: str, answer: str,
    blocks: list[dict[str, Any]], provider: str,
) -> str:
    """Let the model speak naturally, never let it invent the business result.

    Tool execution and record creation have already happened by the time this is
    called.  The model only receives the small, persisted result packet and is
    therefore a narrator, not an ungoverned executor.
    """
    settings = get_settings()
    if provider != 'groq' or not settings.groq_api_key:
        return answer
    # Missing-field cards are already a precise contract from the selected
    # server tool. Rewriting them is how the old UI started asking for invented
    # fields such as preferred supplier and delivery location.
    if any(block.get('type') in {
        'clarification', 'missing_information', 'run_progress',
    } for block in blocks):
        return answer
    facts = []
    for block in blocks:
        if block.get('text'):
            facts.append(str(block['text']))
        if block.get('record'):
            facts.append(json.dumps(block['record'], default=str))
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_groq import ChatGroq
        model = ChatGroq(
            api_key=settings.groq_api_key,
            model=profile.model_profile or settings.agent_primary_model,
            temperature=0.2,
            max_tokens=settings.agent_response_max_output_tokens,
            timeout=settings.agent_max_run_seconds,
            max_retries=1,
        )
        response = model.invoke([
            SystemMessage(content=(
                'You are a concise procurement work assistant. Rewrite the grounded result into a direct, '
                'helpful response to the employee. Use only the supplied facts. Do not mention tools, prompts, '
                'agents, policies, or hidden reasoning. Do not claim an action unless it is explicitly stated. '
                'If a confirmation is needed, make that clear. Keep it under 110 words.'
            )),
            HumanMessage(content=json.dumps({
                'employee_message': question,
                'grounded_result': answer,
                'persisted_facts': facts[:8],
            }, default=str)),
        ])
        text = str(response.content).strip()
        return text[:2000] if text else answer
    except Exception:
        logger.info('Grounded response composition unavailable', exc_info=True)
        return answer


def preserve_business_identifiers(
    answer: str, blocks: list[dict[str, Any]],
) -> str:
    """Keep model typography from corrupting exact persisted business numbers."""
    normalized = answer.translate({
        ord('\u2010'): '-',
        ord('\u2011'): '-',
        ord('\u2212'): '-',
    })
    identifiers: list[str] = []
    for block in blocks:
        record = block.get('record')
        if not isinstance(record, dict):
            continue
        for key in (
            'display_id', 'business_number', 'requirement_number', 'rfq_number',
            'po_number', 'invoice_number',
        ):
            value = record.get(key)
            if isinstance(value, str) and value and value not in identifiers:
                identifiers.append(value)
    missing = [value for value in identifiers if value not in normalized]
    if missing:
        normalized = f"{normalized.rstrip()} {' · '.join(missing)}"
    return normalized


def team_agent_activity(
    db: Session, user: models.User, membership: models.WorkspaceMembership,
) -> list[dict[str, Any]]:
    """Produce auditable, read-only employee-agent updates for a manager.

    Each entry is derived only from the recipient's owned tasks and their latest
    formal delegation update.  It intentionally cannot mutate a task or make a
    commitment on behalf of the employee.
    """
    entries: list[dict[str, Any]] = []
    for member_id in reporting_descendants(db, membership):
        employee_membership = db.get(models.WorkspaceMembership, member_id)
        if employee_membership is None:
            continue
        employee = db.get(models.User, employee_membership.user_id)
        tasks = db.query(models.Task).filter(
            models.Task.tenant_id == user.tenant_id,
            models.Task.plant_id == user.plant_id,
            models.Task.owner_membership_id == member_id,
            models.Task.status.in_(['open', 'accepted', 'in_progress', 'blocked', 'review', 'pending_approval']),
        ).order_by(models.Task.due_at.asc()).all()
        latest = db.query(models.AgentDelegation).filter_by(
            tenant_id=user.tenant_id, recipient_membership_id=member_id,
        ).order_by(models.AgentDelegation.created_at.desc()).first()
        blocker = next((task.blocker_reason for task in tasks if task.blocker_reason), None)
        if not blocker and latest:
            blocker = (latest.response or {}).get('blocker')
        next_task = tasks[0] if tasks else None
        state = 'blocked' if blocker else ('on_track' if tasks else 'clear')
        summary = (
            f'{len(tasks)} active work item' + ('s' if len(tasks) != 1 else '')
            if tasks else 'No active work items'
        )
        if next_task:
            summary += f'. Next: {next_task.title} ({next_task.status.replace("_", " ")}).'
        if blocker:
            summary += f' Blocker: {blocker}.'
        entries.append({
            'employee_name': employee.name if employee else employee_membership.role.replace('_', ' ').title(),
            'membership_id': member_id,
            'role': employee_membership.role,
            'state': state,
            'summary': summary,
            'task_id': next_task.id if next_task else None,
            'task_title': next_task.title if next_task else None,
            'updated_at': (latest.response or {}).get('updated_at') if latest else None,
            'evidence': [{'type': 'task', 'id': task.id, 'label': task.title} for task in tasks[:3]],
        })
    return entries


def resolve_procurement_action(
    db: Session, user: models.User, membership: models.WorkspaceMembership,
    facts: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {'missing': [], 'ambiguities': []}
    item_id = str(facts.get('item_id') or '').strip()
    material_query = str(facts.get('material_query') or '').strip()
    item_code = str(facts.get('item_code') or '').strip()
    if not item_id and not material_query and not item_code:
        result['missing'].append('material name or item code')
        return result
    items = workflows.user_scope_query(db, models.Item, user).all()
    normalized = material_query.casefold()
    tokenized = ' '.join(re.findall(r'[a-z0-9]+', normalized))
    id_matches = [item for item in items if item.id == item_id] if item_id else []
    code_matches = [item for item in items if item.code.casefold() == item_code.casefold()] if item_code else []
    name_matches = [item for item in items if item.name.casefold() == normalized] if normalized else []
    normalized_matches = [
        item for item in items
        if tokenized and tokenized == ' '.join(re.findall(r'[a-z0-9]+', item.name.casefold()))
    ]
    contains = [
        item for item in items
        if tokenized and all(token in item.name.casefold() for token in tokenized.split())
    ]
    fuzzy_code_matches: list[models.Item] = []
    if item_code and not code_matches:
        ranked_codes = sorted(
            ((SequenceMatcher(None, item_code.casefold(), item.code.casefold()).ratio(), item) for item in items),
            key=lambda row: -row[0],
        )
        if ranked_codes and ranked_codes[0][0] >= 0.8:
            runner_up = ranked_codes[1][0] if len(ranked_codes) > 1 else 0.0
            if ranked_codes[0][0] - runner_up >= 0.08:
                fuzzy_code_matches = [ranked_codes[0][1]]
    # Exact grounded ID/name outranks a mistyped code. A unique close code is
    # accepted only when there is a safe margin over the next candidate.
    matches = id_matches or code_matches or name_matches or normalized_matches or contains or fuzzy_code_matches
    if not matches:
        result['missing'].append('material')
        result['material_query'] = material_query or item_code
        return result
    if len(matches) > 1:
        result['ambiguities'].append({
            'field': 'material',
            'choices': [{'id': item.id, 'code': item.code, 'name': item.name} for item in matches[:5]],
        })
        return result
    item = matches[0]
    result['item'] = item
    result['canonical_code_corrected'] = bool(item_code and item.code.casefold() != item_code.casefold())
    for field, label in (
        ('quantity', 'quantity'), ('uom', 'unit of measure'), ('need_by_date', 'need-by date'),
    ):
        if not facts.get(field):
            result['missing'].append(label)
    descendants = set(reporting_descendants(db, membership))
    executives = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, default_plant_id=user.plant_id,
        role=PURCHASE_EXECUTIVE, status='active',
    ).all()
    if membership.role == PLANT_MANAGER:
        executives = [candidate for candidate in executives if candidate.id in descendants]
    if not executives:
        result['missing'].append('named Purchase Executive in the reporting tree')
    elif len(executives) > 1:
        result['ambiguities'].append({
            'field': 'assignee',
            'choices': [
                {'membership_id': candidate.id, 'name': db.get(models.User, candidate.user_id).name}
                for candidate in executives
            ],
        })
    else:
        result['assignee'] = executives[0]
    capabilities = workflows.user_scope_query(db, models.SupplierItemCapability, user).filter_by(
        item_id=item.id, approved=True
    ).all()
    approved_supplier_ids = {
        supplier.id for supplier in workflows.user_scope_query(db, models.Supplier, user).filter(
            models.Supplier.status.in_(['approved', 'conditional'])
        ).all()
    }
    result['supplier_count'] = len({row.supplier_id for row in capabilities if row.supplier_id in approved_supplier_ids})
    return result


def requirement_clarification(
    missing: list[str], *, item: models.Item | None = None,
) -> str:
    """Turn deterministic validation into a concise business conversation."""
    readable = [str(value).strip() for value in missing if str(value).strip()]
    if not readable:
        return 'I have enough information to continue.'
    if len(readable) == 1:
        fields = readable[0]
    elif len(readable) == 2:
        fields = f'{readable[0]} and {readable[1]}'
    else:
        fields = f'{", ".join(readable[:-1])}, and {readable[-1]}'
    matched = f'I found {item.code} · {item.name}. ' if item is not None else ''
    return f'{matched}What {fields} should I use?'


def procurement_fingerprint(facts: dict[str, Any], item_id: str, assignee_id: str) -> str:
    payload = {key: facts.get(key) for key in ('quantity', 'uom', 'need_by_date', 'reason', 'specification')}
    payload.update({'item_id': item_id, 'assignee_id': assignee_id})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def execute_procurement_delegation(
    db: Session, user: models.User, membership: models.WorkspaceMembership,
    profile: models.AgentProfile, thread: models.AgentThread, run: models.AgentRun,
    facts: dict[str, Any], resolution: dict[str, Any], correlation_id: str,
) -> dict[str, Any]:
    item: models.Item = resolution['item']
    assignee: models.WorkspaceMembership = resolution['assignee']
    fingerprint = procurement_fingerprint(facts, item.id, assignee.id)
    prior = dict((thread.context_state or {}).get('last_execution') or {})
    reusable = prior.get('fingerprint') == fingerprint or bool(prior) and all((
        str(prior.get('assignee_membership_id')) == assignee.id,
        str(prior.get('item_id')) == item.id,
        float(prior.get('quantity') or 0) == float(facts.get('quantity') or 0),
        str(prior.get('uom') or '').casefold() == str(facts.get('uom') or '').casefold(),
    ))
    if reusable:
        requirement_id = str(prior.get('requirement_id') or '')
        requirement = workflows.get_scoped_or_404(
            db, models.PurchaseRequirement, user, requirement_id, 'Requirement',
        )
        result = {**prior, 'reused': True, 'supplier_count': resolution['supplier_count']}
        record_run_event(db, run, 'tool_completed', {
            'tool': 'reuse_purchase_requirement', 'target_type': 'purchase_requirements',
            'target_id': requirement.id, 'status': 'succeeded', 'reused': True,
        })
        return result
    quantity = float(facts['quantity'])
    uom = str(facts['uom']).upper()
    need_by_date = str(facts['need_by_date'])
    reason = str(facts.get('reason') or f'Plant Manager requested procurement of {item.name}.')
    requirement = workflows.create_requirement(
        db, user, item.id, quantity, need_by_date, source='agent', uom=uom,
        title=f'Procure {item.name}',
        lines=[{
            'item_id': item.id, 'quantity': quantity, 'need_by_date': need_by_date,
            'uom': uom, 'specification': str(facts.get('specification') or ''),
            'inspection_required': True,
        }],
        reason=reason, assignee_membership_id=assignee.id,
        source_thread_id=thread.id, source_run_id=run.id, correlation_id=correlation_id,
    )
    db.flush()
    task = db.query(models.Task).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        entity_type='purchase_requirements', entity_id=requirement.id,
    ).first()
    recipient_profile = profile_for_membership(db, assignee)
    try:
        due_at = datetime.fromisoformat(need_by_date).replace(tzinfo=timezone.utc)
    except ValueError:
        due_at = utcnow() + timedelta(days=30)
    delegation = models.AgentDelegation(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        sender_agent_profile_id=profile.id, sender_membership_id=membership.id,
        recipient_agent_profile_id=recipient_profile.id, recipient_membership_id=assignee.id,
        work_item_id=task.id if task else None,
        requested_outcome=(
            f'Prepare an RFQ for {quantity:g} {uom} of {item.name} and request quotations '
            'from every approved capable supplier. The Purchase Manager will own quote verification and comparison.'
        ),
        context_packet={
            'requirement_id': requirement.id, 'item_id': item.id,
            'quantity': quantity, 'uom': uom, 'need_by_date': need_by_date,
            'allowed_entity_ids': {'purchase_requirements': [requirement.id], 'tasks': [task.id] if task else []},
        },
        due_at=due_at, status='pending', depth=1,
    )
    db.add(delegation)
    db.flush()
    tool_call = models.AgentToolCall(
        tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
        agent_profile_id=profile.id, tool_name='create_requirement_and_delegate',
        arguments={'item_id': item.id, 'quantity': quantity, 'uom': uom, 'need_by_date': need_by_date, 'assignee_membership_id': assignee.id},
        result_hash=hashlib.sha256(f'{requirement.id}:{task.id if task else ""}:{delegation.id}'.encode()).hexdigest(),
        target_entity_type='purchase_requirements', target_entity_id=requirement.id,
        authorization_decision='allowed', latency_ms=0, correlation_id=correlation_id,
    )
    db.add(tool_call)
    db.add(models.AgentActionReceipt(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        run_id=run.id, tool_name='create_requirement_and_delegate',
        status='succeeded', target_entity_type='purchase_requirements',
        target_entity_id=requirement.id,
        result_summary={
            'requirement_number': requirement.business_number,
            'task_id': task.id if task else None,
            'delegation_id': delegation.id,
            'assignee_membership_id': assignee.id,
        },
        executed_by_membership_id=membership.id,
        started_at=utcnow(), completed_at=utcnow(),
        idempotency_key=f'{correlation_id}:create_requirement_and_delegate',
    ))
    record_run_event(db, run, 'tool_completed', {
        'tool': 'create_requirement_and_delegate',
        'target_type': 'purchase_requirements',
        'target_id': requirement.id,
        'status': 'succeeded',
    })
    assignee_user = db.get(models.User, assignee.user_id)
    receipt = {
        'fingerprint': fingerprint, 'requirement_id': requirement.id,
        'requirement_number': requirement.business_number, 'task_id': task.id if task else None,
        'delegation_id': delegation.id, 'assignee_membership_id': assignee.id,
        'item_id': item.id, 'quantity': quantity, 'uom': uom,
        'assignee_name': assignee_user.name if assignee_user else 'Purchase Executive',
        'need_by_date': need_by_date, 'supplier_count': resolution['supplier_count'],
    }
    state = dict(thread.context_state or {})
    state['last_execution'] = receipt
    recent = list(state.get('recent_entities') or [])
    state['recent_entities'] = [
        {'type': 'purchase_requirement', 'id': requirement.id, 'display_id': requirement.business_number},
        *[row for row in recent if row.get('id') != requirement.id],
    ][:10]
    state['current_work_item'] = {'type': 'purchase_requirement', 'id': requirement.id}
    action_receipt = db.query(models.AgentActionReceipt).filter_by(run_id=run.id, target_entity_id=requirement.id).first()
    state['last_action_receipt_id'] = action_receipt.id if action_receipt else None
    state['updated_at'] = utcnow().isoformat()
    persist_thread_state(thread, load_thread_state(state))
    return receipt


def execute_contextual_procurement_workflow(
    db: Session,
    user: models.User,
    membership: models.WorkspaceMembership,
    profile: models.AgentProfile,
    thread: models.AgentThread,
    run: models.AgentRun,
    intent: str,
    correlation_id: str,
    citations: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    state = dict(thread.context_state or {})
    has_resolved_context = bool(thread.work_item_id or state.get('current_work_item') or state.get('attachments'))
    if not thread.work_item_id and not has_resolved_context:
        answer = 'Open the assigned task before asking me to prepare this procurement step.'
        return answer, [AgentResponseBlock(
            type='warning', title='Task context required', text=answer,
        ).model_dump()], citations
    task = task_for_membership(db, membership, thread.work_item_id) if thread.work_item_id else None
    from app import procurement_v2

    artifact = None
    target_type = ''
    target_id = ''
    tool_name = ''
    result_summary: dict[str, Any] = {}
    href = '/control-centre'

    if intent == 'prepare_rfq':
        if membership.role != PURCHASE_EXECUTIVE:
            raise HTTPException(status_code=403, detail='Only the assigned Purchase Executive can prepare an RFQ')
        if task.entity_type != 'purchase_requirements' or not task.entity_id:
            raise HTTPException(status_code=409, detail='This task is not linked to a purchase requirement')
        rfq = workflows.create_rfq_from_requirement(db, user, task.entity_id)
        artifact = procurement_v2.generate_artifact(db, user, 'rfq', rfq.id, final=False)
        tool_name = 'prepare_rfq_draft'
        target_type = 'rfqs'
        target_id = rfq.id
        href = '/rfq-builder'
        result_summary = {
            'rfq_id': rfq.id,
            'rfq_number': rfq.business_number,
            'supplier_count': len(rfq.supplier_ids or []),
            'artifact_id': artifact.id,
            'document_id': artifact.document_id,
            'status': rfq.status,
        }
        answer = (
            f'RFQ {rfq.business_number or rfq.id} is prepared for '
            f'{len(rfq.supplier_ids or [])} approved capable suppliers. '
            'Review the draft PDF before the separate publication confirmation.'
        )
    elif intent == 'prepare_comparison':
        if membership.role != 'purchase_manager':
            raise HTTPException(status_code=403, detail='Only the assigned Purchase Manager can prepare a comparison')
        rfq_ids: set[str] = set()
        if task and task.entity_type == 'rfqs' and task.entity_id:
            rfq_ids.add(task.entity_id)
        if task and task.entity_type == 'supplier_quotes' and task.entity_id:
            quote = workflows.get_scoped_or_404(db, models.SupplierQuote, user, task.entity_id, 'Quotation')
            rfq_ids.add(quote.rfq_id)
        current = state.get('current_work_item') or {}
        if current.get('type') in {'rfq', 'rfqs'} and current.get('id'):
            rfq_ids.add(current['id'])
        for attachment in state.get('attachments') or []:
            entity_type = attachment.get('linked_entity_type')
            entity_id = attachment.get('linked_entity_id')
            if entity_type in {'rfq', 'rfqs'} and entity_id:
                rfq_ids.add(entity_id)
            elif entity_type in {'supplier_quote', 'supplier_quotes'} and entity_id:
                quote = workflows.get_scoped_or_404(db, models.SupplierQuote, user, entity_id, 'Quotation')
                rfq_ids.add(quote.rfq_id)
        if len(rfq_ids) > 1:
            answer = 'The attachments refer to more than one RFQ. Choose one RFQ before preparing the comparison.'
            return answer, [AgentResponseBlock(type='clarification', text=answer).model_dump()], citations
        rfq_id = next(iter(rfq_ids), None)
        if not rfq_id:
            raise HTTPException(status_code=409, detail='This task is not linked to an RFQ or supplier quotation')
        comparison = workflows.generate_comparison(db, user, rfq_id)
        artifact = procurement_v2.generate_artifact(
            db, user, 'comparison', comparison.id, final=False,
        )
        tool_name = 'prepare_verified_comparison'
        target_type = 'bid_comparison'
        target_id = comparison.id
        href = '/comparison'
        result_summary = {
            'comparison_id': comparison.id,
            'comparison_number': comparison.business_number,
            'row_count': len(comparison.rows or []),
            'recommended_supplier_id': comparison.recommended_supplier_id,
            'artifact_id': artifact.id,
            'document_id': artifact.document_id,
            'status': comparison.status,
        }
        state['recent_entities'] = [
            {'type': 'bid_comparison', 'id': comparison.id, 'display_id': comparison.business_number},
            *[row for row in state.get('recent_entities') or [] if row.get('id') != comparison.id],
        ][:10]
        state['current_work_item'] = {'type': 'bid_comparison', 'id': comparison.id}
        state['updated_at'] = utcnow().isoformat()
        persist_thread_state(thread, load_thread_state(state))
        answer = (
            f'Comparison {comparison.business_number or comparison.id} was prepared from verified quotation data. '
            'Review landed cost, delivery, specification deviations, and the draft PDF before submission.'
        )
    elif intent == 'prepare_po':
        if membership.role != 'purchase_manager':
            raise HTTPException(status_code=403, detail='Only the assigned Purchase Manager can prepare the PO action')
        if task.entity_type != 'bid_comparison' or not task.entity_id:
            raise HTTPException(status_code=409, detail='This task is not linked to an approved comparison')
        comparison = workflows.get_scoped_or_404(
            db, models.BidComparison, user, task.entity_id, 'Comparison',
        )
        proposal_authority = membership.role if membership.role == ADMIN else authority
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id,
            run_id=run.id,
            action='confirm_purchase_order',
            target_entity_type='bid_comparison',
            target_entity_id=comparison.id,
            preview={
                'comparison_number': comparison.business_number,
                'comparison_version': comparison.comparison_version,
                'recommended_supplier_id': comparison.recommended_supplier_id,
                'status': comparison.status,
                'allocations': __import__(
                    'app.procurement_v2', fromlist=['recommended_award_allocations']
                ).recommended_award_allocations(db, user, comparison),
            },
            expected_effect='Create the final immutable purchase order PDF from the approved comparison.',
            required_authority='purchase_manager',
            record_version=comparison.version,
        ))
        answer = 'The purchase-order commitment is prepared and waiting for your explicit confirmation.'
        blocks = [
            AgentResponseBlock(
                type='action_proposal', title='Purchase order confirmation',
                text=answer,
                items=[
                    f'Proposal: {proposal.id}',
                    f'Comparison: {comparison.business_number or comparison.id}',
                    f'Risk class: {proposal.risk_class}',
                ],
            ),
            AgentResponseBlock(
                type='approval_request', title='Human authority required',
                text='Confirm only after verifying the approved supplier, comparison version, commercial totals, and delivery terms.',
            ),
        ]
        return answer, [block.model_dump() for block in blocks], citations
    else:
        raise HTTPException(status_code=422, detail='Unsupported contextual procurement workflow')

    result_hash = hashlib.sha256(
        json.dumps(result_summary, sort_keys=True, default=str).encode()
    ).hexdigest()
    db.add(models.AgentToolCall(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        run_id=run.id,
        agent_profile_id=profile.id,
        tool_name=tool_name,
        arguments={
            'work_item_id': task.id if task else None,
            'entity_type': task.entity_type if task else None,
            'entity_id': task.entity_id if task else None,
        },
        result_hash=result_hash,
        target_entity_type=target_type,
        target_entity_id=target_id,
        authorization_decision='allowed',
        latency_ms=0,
        correlation_id=correlation_id,
    ))
    receipt = models.AgentActionReceipt(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        run_id=run.id,
        tool_name=tool_name,
        status='succeeded',
        target_entity_type=target_type,
        target_entity_id=target_id,
        result_summary=result_summary,
        executed_by_membership_id=membership.id,
        started_at=utcnow(),
        completed_at=utcnow(),
        idempotency_key=f'{correlation_id}:{tool_name}',
    )
    db.add(receipt)
    db.flush()
    record_run_event(db, run, 'tool_completed', {
        'tool': tool_name,
        'target_type': target_type,
        'target_id': target_id,
        'status': 'succeeded',
    })
    record_run_event(db, run, 'artifact_generated', {
        'artifact_id': artifact.id if artifact else None,
        'document_id': artifact.document_id if artifact else None,
        'target_type': target_type,
        'target_id': target_id,
    })
    citations.append({
        'type': target_type,
        'id': target_id,
        'label': result_summary.get('rfq_number') or result_summary.get('comparison_number') or target_id,
        'href': href,
    })
    blocks = [
        AgentResponseBlock(type='record_summary', title='Prepared from canonical data', text=answer),
        AgentResponseBlock(
            type='prepared_artifact', title='Draft PDF available',
            text='The generated draft is stored privately and is available from the linked workbench.',
            items=['Open the linked workbench to review the draft PDF.'] if artifact else [],
        ),
        AgentResponseBlock(
            type='action_receipt', title='Prepared work saved',
            text='The requested work was saved successfully.',
        ),
    ]
    return answer, [block.model_dump() for block in blocks], citations


def process_agent_decision(
    db: Session, user: models.User, membership: models.WorkspaceMembership,
    profile: models.AgentProfile, thread: models.AgentThread, run: models.AgentRun,
    decision: AgentTurnDecision, facts: dict[str, Any], provider: str,
    citations: list[dict[str, Any]], correlation_id: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    blocks: list[AgentResponseBlock] = []
    latest_user = db.query(models.AgentMessage).filter_by(
        tenant_id=user.tenant_id, thread_id=thread.id,
        message_type='user', correlation_id=correlation_id,
    ).first()
    question = latest_user.content.casefold() if latest_user else ''
    recent = list((thread.context_state or {}).get('recent_entities') or [])
    asks_for_id = ' id' in f' {question}' or 'identifier' in question or 'number' in question
    if decision.intent == 'answer' and asks_for_id and recent:
        entity = recent[0]
        display_id = entity.get('display_id') or entity.get('id')
        answer = str(display_id)
        return answer, [AgentResponseBlock(
            type='record_summary', text=answer,
            items=[f"Persisted record: {entity.get('type')}:{entity.get('id')}"],
        ).model_dump()], [{
            'type': entity.get('type'), 'id': entity.get('id'),
            'label': display_id, 'href': '/procurement',
        }]
    if decision.intent in {'prepare_rfq', 'prepare_comparison', 'prepare_po'}:
        state = dict(thread.context_state or {})
        if provider != 'groq' and not (thread.work_item_id or state.get('current_work_item') or state.get('attachments')):
            answer = 'This operational request is unavailable in Limited mode. Open the linked workbench to continue manually.'
            blocks.extend([
                AgentResponseBlock(type='limited_mode', title='Groq / Limited mode', text=answer),
                AgentResponseBlock(type='warning', title='No action taken', text='No draft, proposal, or record was created.'),
            ])
            return answer, [block.model_dump() for block in blocks], citations
        return execute_contextual_procurement_workflow(
            db, user, membership, profile, thread, run,
            decision.intent, correlation_id, citations,
        )
    if decision.explicit_execute and decision.intent == 'delegate_procurement':
        if provider != 'groq' and not facts:
            answer = 'I retained the request, but the agent is in Limited mode. No requirement or delegation was created.'
            blocks.extend([
                AgentResponseBlock(type='summary', title='No action taken', text=answer),
                AgentResponseBlock(
                    type='limited_mode', title='Groq / Limited mode',
                    text='Connect the configured Groq model or use New requirement. Limited mode never executes free-form commands.',
                ),
            ])
            return answer, [block.model_dump() for block in blocks], citations
        if membership.role != PLANT_MANAGER:
            answer = 'This conversation cannot assign Plant Manager work from your current role.'
            blocks.append(AgentResponseBlock(type='summary', title='Action not authorized', text=answer))
            return answer, [block.model_dump() for block in blocks], citations
        resolution = resolve_procurement_action(db, user, membership, facts)
        if resolution['ambiguities']:
            ambiguity = resolution['ambiguities'][0]
            choices = [
                choice.get('name') or choice.get('code') or choice.get('membership_id')
                for choice in ambiguity['choices']
            ]
            answer = f'Please choose one {ambiguity["field"]} before I create and assign the requirement.'
            blocks.extend([
                AgentResponseBlock(type='summary', title='One choice needed', text=answer),
                AgentResponseBlock(type='missing_information', title='Available choices', items=choices),
            ])
            return answer, [block.model_dump() for block in blocks], citations
        if resolution['missing']:
            answer = requirement_clarification(
                resolution['missing'], item=resolution.get('item'),
            )
            note = None
            if 'material' in resolution['missing']:
                note = 'The material is not in the approved master. Use the separate material-master request from New requirement.'
            blocks.extend([
                AgentResponseBlock(type='summary', title='Not delegated yet', text=answer),
                AgentResponseBlock(type='missing_information', title='Still needed', items=resolution['missing'], text=note),
            ])
            return answer, [block.model_dump() for block in blocks], citations
        receipt = execute_procurement_delegation(
            db, user, membership, profile, thread, run, facts, resolution, correlation_id
        )
        answer = f"Created {receipt['requirement_number']} and assigned it to {receipt['assignee_name']}."
        blocks.extend([
            AgentResponseBlock(type='summary', title='Requirement delegated', text=answer),
            AgentResponseBlock(
                type='record_summary', title='Canonical requirement', text=receipt['requirement_number'],
                record={
                    'type': 'purchase_requirement',
                    'id': receipt['requirement_id'],
                    'display_id': receipt['requirement_number'],
                    'need_by_date': receipt['need_by_date'],
                    'assignee_name': receipt['assignee_name'],
                },
            ),
            AgentResponseBlock(type='action_receipt', title='Created records', items=[
                f"Requirement: {receipt['requirement_number']}",
                f"Purchase Executive: {receipt['assignee_name']}",
                f"Need by: {receipt['need_by_date']}",
                f"Approved capable suppliers: {receipt['supplier_count']}",
                'A Purchase Executive task has been assigned.',
            ]),
            AgentResponseBlock(
                type='role_handoff', title='What happens next',
                text='The Purchase Executive prepares the RFQ and requests quotations from approved capable suppliers. The Purchase Manager verifies returned quotes and creates the supplier comparison.',
            ),
        ])
        citations.extend([
            {'type': 'purchase_requirement', 'id': receipt['requirement_id'], 'label': receipt['requirement_number'], 'href': '/procurement'},
            {'type': 'work_item', 'id': receipt['task_id'], 'label': 'Purchase Executive task', 'href': f"/agent?work_item={receipt['task_id']}"},
        ])
        return answer, [block.model_dump() for block in blocks], citations
    answer = decision.answer.strip()
    blocks.append(AgentResponseBlock(type='summary', title='Answer', text=answer))
    if decision.intent in {'procurement', 'delegate_procurement'}:
        blocks.append(AgentResponseBlock(
            type='role_handoff', title='Role ownership',
            text='Purchase Executive owns RFQ preparation and supplier outreach. Purchase Manager owns quotation verification and comparison.',
        ))
    return answer, [block.model_dump() for block in blocks], citations


def process_intent_envelope(
    db: Session, user: models.User, membership: models.WorkspaceMembership,
    profile: models.AgentProfile, thread: models.AgentThread, run: models.AgentRun,
    envelope: IntentEnvelope, facts: dict[str, Any], provider: str,
    citations: list[dict[str, Any]], correlation_id: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Authorize and dispatch one schema-constrained capability."""
    capability = validate_intent(envelope, membership.role)
    intent = capability.capability_id
    latest = db.query(models.AgentMessage).filter_by(
        tenant_id=user.tenant_id, thread_id=thread.id, message_type='user',
        correlation_id=correlation_id,
    ).first()
    question = latest.content.casefold() if latest else ''
    state = dict(thread.context_state or {})
    attachment_refs = set(load_thread_state(state).attachment_refs)
    live_attachment_rows = db.query(models.AgentMessageAttachment).join(
        models.AgentMessage,
        models.AgentMessage.id == models.AgentMessageAttachment.message_id,
    ).filter(
        models.AgentMessage.thread_id == thread.id,
        models.AgentMessageAttachment.tenant_id == user.tenant_id,
    ).order_by(
        models.AgentMessage.created_at.asc(),
        models.AgentMessageAttachment.file_order.asc(),
    ).all()
    state['attachments'] = [{
        **record_dict(row),
        'filename': getattr(db.get(models.Document, row.document_id), 'filename', 'Attachment'),
        'content_type': getattr(db.get(models.Document, row.document_id), 'content_type', None),
        'validation_status': getattr(db.get(models.Document, row.document_id), 'status', None),
    } for row in live_attachment_rows if (
        not attachment_refs
        or row.id in attachment_refs
        or row.document_id in attachment_refs
    )]
    recent = list(state.get('recent_entities') or [])

    if intent == 'answer_work_context':
        if re.search(r'\b(?:its?|that|the\s+\w+)\s+(?:id|identifier|number)\b|\bwhat\s+is\s+its\s+id\b', question) and recent:
            entity = recent[0]
            entity_type = entity.get('entity_type') or entity.get('type')
            entity_id = entity.get('entity_id') or entity.get('id')
            display_id = str(entity.get('business_number') or entity.get('display_id') or entity_id)
            return display_id, [AgentResponseBlock(
                type='record_summary', text=display_id,
                record={'type': entity_type, 'id': entity_id, 'display_id': display_id},
                actions=[{'id': 'open_record', 'label': 'Open requirement', 'href': '/procurement'}],
            ).model_dump()], [{
                'type': entity_type, 'id': entity_id,
                'label': display_id, 'href': '/procurement',
            }]
        if 'master' in question:
            answer = 'Implemented masters are Materials, Suppliers, supplier capabilities, UOMs, and tax policies.'
        elif provider == 'groq' and envelope.requested_outcome.strip() and envelope.requested_outcome.strip().casefold() != question.strip().casefold():
            answer = envelope.requested_outcome.strip()
        else:
            answer = deterministic_response(membership.role, context_payload(
                db, build_context_envelope(db, membership, thread, correlation_id)
            )[0])
        return answer, [AgentResponseBlock(type='message', text=answer).model_dump()], citations

    if intent == 'list_approved_materials':
        records = approved_material_records(db, user)
        answer = f"Found {len(records)} approved material{'s' if len(records) != 1 else ''}."
        blocks = [AgentResponseBlock(
            type='record_summary', text=answer,
            items=[f"{row['code']} · {row['name']} · {row['uom']}" for row in records],
            record={'domain': 'materials', 'count': len(records), 'records': records},
        ).model_dump()]
        return answer, blocks, citations

    if intent == 'preview_excel_import':
        if not envelope.attachment_ids:
            answer = 'Attach the XLSX external-system workbook you want me to inspect.'
            return answer, [AgentResponseBlock(type='clarification', text=answer, items=['XLSX workbook']).model_dump()], citations
        from app import excel_connector
        from app.storage import object_storage
        document = workflows.user_scope_query(db, models.Document, user).filter(
            models.Document.id.in_(envelope.attachment_ids),
            models.Document.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ).first()
        if document is None:
            raise HTTPException(422, 'Attach a validated XLSX workbook from this workspace')
        workflows.ensure_default_connections(db, user)
        db.flush()
        connection = workflows.user_scope_query(db, models.IntegrationConnection, user).filter_by(provider='local').first()
        if connection is None:
            raise HTTPException(409, 'Excel connector is not configured')
        content = object_storage.get_bytes(document.storage_bucket, document.storage_key)
        batch = excel_connector.preview_import(db, user, connection, document.filename, content, document_id=document.id)
        receipt = models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='preview_excel_import', status='succeeded',
            target_entity_type='integration_import_batch', target_entity_id=batch.id,
            result_summary={'status': batch.status, 'summary': batch.summary},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:preview_excel_import',
        )
        db.add(receipt)
        remember = remember_entity(load_thread_state(thread.context_state), entity_type='integration_import_batch', entity_id=batch.id, business_number=batch.business_number)
        persist_thread_state(thread, remember)
        summary = batch.summary
        answer = f"Workbook preview ready: {summary.get('insert', 0)} new, {summary.get('update', 0)} updates, {summary.get('unchanged', 0)} unchanged, {summary.get('conflict', 0)} conflicts, and {summary.get('error', 0)} errors."
        return answer, [AgentResponseBlock(
            type='field_review', text=answer,
            items=[f"{sheet['name']} · {sheet['row_count']} rows" for sheet in batch.discovery.get('sheets', [])],
            record={'type': 'excel_import', 'status': batch.status, **summary},
            actions=[{'id': 'review_excel_import', 'label': 'Review row issues', 'href': f'/integrations?import={batch.id}'}],
        ).model_dump()], citations

    if intent == 'prepare_po_change':
        from app.agent_resolution import resolve_record
        po = resolve_record(db, user, 'po_draft', str(facts.get('po_id') or (envelope.referenced_entity_ids or [''])[0]))
        revision = __import__('app.procurement_v2', fromlist=['prepare_po_change']).prepare_po_change(
            db, user, po.id, str(facts.get('change_type') or ''), str(facts.get('reason') or ''),
            list(facts.get('line_changes') or []), str(facts.get('acknowledgement_id') or '') or None,
        )
        db.flush()
        result = {
            'po_id': revision.id, 'po_number': revision.business_number,
            'revision_number': revision.revision_number, 'revision_kind': revision.revision_kind,
            'status': revision.status, 'previous_version_id': revision.previous_version_id,
        }
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='prepare_po_change', status='succeeded', target_entity_type='po_draft',
            target_entity_id=revision.id, result_summary=result,
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:prepare_po_change',
        ))
        answer = f'{revision.business_number} is prepared as an immutable {revision.revision_kind} and is waiting for approval.'
        return answer, [AgentResponseBlock(
            type='record_created', text=answer, record=result,
            actions=[{'id': 'review_po_change', 'label': 'Review PO change', 'href': f'/po-drafts?po={revision.id}'}],
        ).model_dump()], citations

    if intent == 'review_supplier_compliance':
        from app.agent_resolution import resolve_supplier
        supplier = resolve_supplier(db, user, str(facts.get('supplier_id') or ''))
        requested_items = set(str(value) for value in (facts.get('item_ids') or []) if value)
        if not requested_items:
            requested_items = {
                row.item_id for row in workflows.user_scope_query(
                    db, models.SupplierItemCapability, user
                ).filter_by(supplier_id=supplier.id, approved=True).all()
            }
        readiness = workflows.supplier_compliance_readiness(db, user, supplier, requested_items)
        gaps = [
            f"{row['certificate_type']}: {row['status'].replace('_', ' ')}"
            for row in readiness.get('requirements', []) if row.get('status') != 'verified'
        ]
        if readiness['eligible']:
            answer = f'{supplier.name} has current verified evidence for the requested materials.'
        else:
            answer = f'{supplier.name} is not currently eligible. ' + ('; '.join(gaps) or 'Supplier approval is blocked.')
        return answer, [AgentResponseBlock(
            type='field_review', text=answer, items=gaps,
            record={'type': 'supplier_compliance', 'supplier_id': supplier.id, 'supplier_name': supplier.name, **readiness},
            actions=[{'id': 'open_supplier_compliance', 'label': 'Review supplier evidence', 'href': '/workspace/setup'}],
        ).model_dump()], citations

    if intent == 'summarize_supplier_performance':
        from app.agent_resolution import resolve_supplier
        supplier = resolve_supplier(db, user, str(facts.get('supplier_id') or ''))
        summary = __import__('app.supplier_performance', fromlist=['summary']).summary(db, user, supplier.id)
        metrics = [f"{name.replace('_', ' ').title()}: {value:.1f}%" for name, value in summary['metrics'].items()]
        answer = f"{supplier.name} has {summary['event_count']} evidence-linked performance events and {summary['open_corrective_actions']} open corrective actions."
        return answer, [AgentResponseBlock(type='record_summary', text=answer, items=metrics, record={'type': 'supplier_performance', **summary}).model_dump()], citations

    if intent == 'list_supplier_deliveries':
        query = workflows.user_scope_query(db, models.ASN, user).filter_by(source='supplier_portal')
        po_reference = str(facts.get('po_id') or '')
        if po_reference:
            from app.agent_resolution import resolve_record
            po = resolve_record(db, user, 'po_draft', po_reference)
            query = query.filter_by(po_draft_id=po.id)
        deliveries = query.order_by(models.ASN.submitted_at.desc()).limit(5).all()
        if not deliveries:
            answer = 'No supplier-submitted deliveries are waiting in this plant.'
            return answer, [AgentResponseBlock(type='record_summary', text=answer, record={'type': 'supplier_deliveries', 'count': 0}, actions=[{'id': 'open_inbound', 'label': 'Open inbound work', 'href': '/store'}]).model_dump()], citations
        items = []
        changed = 0
        for row in deliveries:
            latest_update = workflows.user_scope_query(db, models.SupplierDeliveryUpdate, user).filter_by(
                asn_id=row.id,
            ).order_by(models.SupplierDeliveryUpdate.submitted_at.desc()).first()
            change = ""
            if latest_update:
                changed += 1
                change = f"; {latest_update.update_type.replace('_', ' ')} from {latest_update.previous_expected_delivery}: {latest_update.reason}"
            items.append(f"{row.business_number}: {row.expected_quantity} expected {row.expected_delivery}; dispatch {row.dispatch_reference}; {len(row.supplier_document_ids)} document(s){change}")
        answer = f'{len(deliveries)} supplier delivery notice(s) need inbound coordination.'
        if changed:
            answer += f' {changed} have a revised supplier commitment.'
        return answer, [AgentResponseBlock(type='record_summary', text=answer, items=items, record={'type': 'supplier_deliveries', 'count': len(deliveries)}, actions=[{'id': 'open_inbound', 'label': 'Review delivery evidence', 'href': '/store'}]).model_dump()], citations

    if intent == 'check_invoice_payment_status':
        from app.agent_resolution import resolve_record
        invoice = resolve_record(db, user, 'supplier_invoice', str(facts.get('invoice_id') or ''))
        observation = workflows.user_scope_query(db, models.InvoicePaymentStatus, user).filter_by(
            invoice_id=invoice.id
        ).order_by(models.InvoicePaymentStatus.observed_at.desc()).first()
        if observation is None:
            answer = f'No external payment status has been synchronized for {invoice.business_number or invoice.invoice_number}.'
            record = {'type': 'invoice_payment_status', 'invoice_id': invoice.id, 'invoice_number': invoice.business_number or invoice.invoice_number, 'status': 'not_synchronized'}
        else:
            answer = f'{invoice.business_number or invoice.invoice_number} is {observation.status.replace("_", " ")} according to the latest read-only external-system observation.'
            record = {'type': 'invoice_payment_status', 'invoice_id': invoice.id, 'invoice_number': invoice.business_number or invoice.invoice_number, 'status': observation.status, 'observed_at': observation.observed_at.isoformat(), 'external_version': observation.external_version}
        return answer, [AgentResponseBlock(type='record_summary', text=answer, record=record, actions=[{'id': 'open_invoice', 'label': 'Review invoice', 'href': f'/invoices?invoice={invoice.id}'}]).model_dump()], citations

    if intent == 'review_requirement_lifecycle':
        requirement = resolve_requirement_reference(db, user, str(facts.get('requirement_id') or ''), thread_state=thread.context_state)
        state = workflows.requirement_lifecycle_state(db, user, requirement.id)
        if state['eligible_to_close']:
            answer = f"{requirement.business_number} is fully reconciled and eligible to close."
        else:
            answer = f"{requirement.business_number} is not ready to close: " + '; '.join(state['blockers'])
        return answer, [AgentResponseBlock(type='record_summary', text=answer, items=state['blockers'], record={'type': 'requirement_lifecycle', **state}, actions=[{'id': 'open_requirement', 'label': 'Review requirement', 'href': f'/procurement?requirement={requirement.id}'}]).model_dump()], citations

    if intent == 'open_supplier_corrective_action':
        from app.agent_resolution import resolve_supplier
        supplier = resolve_supplier(db, user, str(facts.get('supplier_id') or ''))
        action = __import__('app.supplier_performance', fromlist=['open_corrective_action']).open_corrective_action(
            db, user, supplier.id, str(facts.get('source_entity_type') or ''),
            str(facts.get('source_entity_id') or ''), str(facts.get('problem_statement') or ''),
            int(facts.get('response_due_days') or 7),
        )
        db.flush()
        result = {'id': action.id, 'display_id': action.business_number, 'status': action.status, 'supplier_name': supplier.name}
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id, tool_name=intent,
            status='succeeded', target_entity_type='supplier_corrective_action', target_entity_id=action.id,
            result_summary=result, executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:open_supplier_corrective_action',
        ))
        answer = f'{action.business_number} is open for {supplier.name}; the Purchase Manager follow-up is assigned.'
        return answer, [AgentResponseBlock(type='record_created', text=answer, record=result, actions=[{'id': 'open_capa', 'label': 'Review corrective action', 'href': '/workspace/setup'}]).model_dump()], citations

    if intent == 'review_excel_import':
        batch_id = str(facts.get('batch_id') or '')
        query = workflows.user_scope_query(db, models.IntegrationImportBatch, user)
        batch = query.filter_by(id=batch_id).first() if batch_id else query.order_by(models.IntegrationImportBatch.created_at.desc()).first()
        if batch is None:
            answer = 'There is no spreadsheet import preview in this workspace yet.'
            return answer, [AgentResponseBlock(type='message', text=answer).model_dump()], citations
        errors = workflows.user_scope_query(db, models.IntegrationImportRowResult, user).filter(
            models.IntegrationImportRowResult.batch_id == batch.id,
            models.IntegrationImportRowResult.action.in_(['error', 'conflict']),
        ).order_by(models.IntegrationImportRowResult.sheet_name, models.IntegrationImportRowResult.row_number).limit(20).all()
        answer = f"{batch.source_filename}: {batch.summary.get('conflict', 0)} conflicts and {batch.summary.get('error', 0)} validation errors."
        items = [f"{row.sheet_name} row {row.row_number}: {'; '.join(message.get('message', message.get('code', 'Review required')) for message in row.validation_messages)}" for row in errors]
        if not items:
            items = ['No conflicting or invalid rows were found.']
        return answer, [AgentResponseBlock(
            type='field_review', text=answer, items=items,
            record={'type': 'excel_import', 'status': batch.status, **batch.summary},
            actions=[{'id': 'open_integrations', 'label': 'Open import review', 'href': f'/integrations?import={batch.id}'}],
        ).model_dump()], citations

    if intent == 'export_excel_exchange':
        from app import excel_connector
        result = excel_connector.create_exchange_export(db, user)
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='export_excel_exchange', status='succeeded',
            target_entity_type='integration_export_batch', target_entity_id=result['export_batch_id'],
            result_summary={'status': result['status'], 'filename': result['filename'], 'reconciliation': result['reconciliation']},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:export_excel_exchange',
        ))
        verification = result['reconciliation']
        answer = f"Created {result['filename']} and verified {verification.get('verified', 0)} external records."
        return answer, [AgentResponseBlock(
            type='prepared_artifact', text=answer,
            record={'type': 'excel_export', 'status': result['status'], 'filename': result['filename'], 'verified_records': verification.get('verified', 0)},
            actions=[{'id': 'open_integrations', 'label': 'Open Integration Centre', 'href': '/integrations'}],
        ).model_dump()], citations

    if intent == 'approve_excel_import_proposal':
        query = workflows.user_scope_query(db, models.IntegrationImportBatch, user)
        batch_id = str(facts.get('batch_id') or '')
        batch = query.filter_by(id=batch_id).first() if batch_id else query.order_by(models.IntegrationImportBatch.created_at.desc()).first()
        if batch is None:
            raise HTTPException(404, 'Spreadsheet import preview not found')
        if batch.status != 'previewed':
            raise HTTPException(409, 'Only a pending spreadsheet preview can be approved')
        if int(batch.summary.get('error', 0)) or int(batch.summary.get('conflict', 0)):
            answer = 'Resolve the invalid or conflicting rows before approving this import.'
            return answer, [AgentResponseBlock(
                type='field_review', text=answer,
                items=[f"{batch.summary.get('error', 0)} invalid rows", f"{batch.summary.get('conflict', 0)} conflicting rows"],
                actions=[{'id': 'open_integrations', 'label': 'Review row issues', 'href': f'/integrations?import={batch.id}'}],
            ).model_dump()], citations
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action='approve_excel_import',
            target_entity_type='integration_import_batches', target_entity_id=batch.id,
            preview={'filename': batch.source_filename, 'summary': batch.summary, 'source_hash': batch.source_hash},
            expected_effect='Import the reviewed clean rows into canonical procurement records while preserving source lineage.',
            required_authority=ADMIN, record_version=batch.version,
        ))
        answer = f'{batch.source_filename} is clean and ready for your confirmation.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={'proposal_id': proposal.id, 'filename': batch.source_filename, 'status': 'awaiting confirmation', **batch.summary},
            actions=[{'id': 'confirm_proposal', 'label': 'Approve import', 'proposal_id': proposal.id}],
        ).model_dump()], citations

    if intent == 'record_exchange_rate':
        from app import currency_service
        observation = currency_service.record_rate(db, user, facts)
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name=intent, status='succeeded', target_entity_type='exchange_rate_observation', target_entity_id=observation.id,
            result_summary={'pair': f'{observation.source_currency}/{observation.target_currency}', 'rate': observation.rate, 'source': observation.source_name},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(), idempotency_key=f'{correlation_id}:{intent}',
        ))
        answer = f'Recorded sourced {observation.source_currency}/INR rate {observation.rate} as {observation.business_number}.'
        return answer, [AgentResponseBlock(type='record_created', text=answer, record={'type': 'exchange_rate', 'display_id': observation.business_number, 'rate': observation.rate, 'source': observation.source_name}, actions=[{'id': 'open_quotes', 'label': 'Apply to quotation', 'href': '/quotes'}]).model_dump()], citations

    if intent == 'apply_exchange_rate':
        from app import currency_service
        from app.agent_resolution import resolve_record
        quote = resolve_record(db, user, 'supplier_quote', str(facts.get('quote_id') or ''))
        observation = workflows.get_scoped_or_404(db, models.ExchangeRateObservation, user, str(facts.get('observation_id') or ''), 'Exchange-rate evidence')
        currency_service.apply_rate(db, user, quote.id, observation.id)
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name=intent, status='succeeded', target_entity_type='supplier_quote', target_entity_id=quote.id,
            result_summary={'quote_number': quote.quote_number, 'rate_observation': observation.business_number, 'rate': observation.rate},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(), idempotency_key=f'{correlation_id}:{intent}',
        ))
        answer = f'Applied sourced rate {observation.rate} to quotation {quote.quote_number}.'
        return answer, [AgentResponseBlock(type='record_summary', text=answer, record={'type': 'supplier_quote', 'display_id': quote.quote_number, 'currency': quote.currency, 'rate': observation.rate}, actions=[{'id': 'open_comparison', 'label': 'Review comparison', 'href': f'/comparison?rfq={quote.rfq_id}'}]).model_dump()], citations

    if intent == 'prepare_invoice_from_attachment':
        from app import invoice_service
        from app.agent_resolution import resolve_record
        attachment_ids = envelope.attachment_ids or []
        if not attachment_ids:
            raise HTTPException(422, 'Attach the supplier invoice before asking me to prepare it')
        po = resolve_record(db, user, 'po_draft', str(facts.get('po_id') or ''))
        extraction = invoice_service.prepare_invoice_extraction(db, user, attachment_ids[0], po.id)
        db.flush()
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='prepare_invoice_from_attachment', status='succeeded',
            target_entity_type='invoice_extraction_run', target_entity_id=extraction.id,
            result_summary={'status': extraction.status, 'po_number': po.business_number, 'document_id': attachment_ids[0]},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:prepare_invoice_from_attachment:{attachment_ids[0]}',
        ))
        fields = extraction.extracted_fields or {}
        answer = f'Invoice evidence for {po.business_number} is ready for your review.'
        missing = next((item.get('missing_fields', []) for item in extraction.evidence if item.get('field') == 'invoice_extraction_summary'), [])
        return answer, [AgentResponseBlock(
            type='field_review', text=answer,
            items=[f"Invoice number: {fields.get('invoice_number') or 'verify'}", f"Total: {fields.get('total_amount') or 'verify'}", *[f"Still needed: {field.replace('_', ' ')}" for field in missing]],
            record={'type': 'invoice_extraction', 'display_id': po.business_number, 'status': extraction.status, 'extraction_id': extraction.id},
            actions=[{'id': 'open_invoice_review', 'label': 'Review invoice evidence', 'href': f'/invoices?extraction={extraction.id}'}],
        ).model_dump()], citations

    if intent == 'match_supplier_invoice':
        from app import invoice_service
        reference = str(facts.get('invoice_id') or (envelope.referenced_entity_ids or [''])[0])
        invoice = workflows.user_scope_query(db, models.SupplierInvoice, user).filter(
            (models.SupplierInvoice.id == reference) | (models.SupplierInvoice.business_number == reference) | (models.SupplierInvoice.invoice_number == reference)
        ).first()
        if invoice is None:
            raise HTTPException(404, 'Supplier invoice not found')
        match = invoice_service.match_invoice(db, user, invoice.id)
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='match_supplier_invoice', status='succeeded', target_entity_type='invoice_match_result',
            target_entity_id=match.id, result_summary={'result': match.result, 'match_type': match.match_type, 'variances': match.variances},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(), idempotency_key=f'{correlation_id}:match_supplier_invoice',
        ))
        answer = f"{match.match_type.replace('_', '-').title()} match {'passed' if match.result == 'matched' else 'found exceptions'} for {invoice.business_number}."
        return answer, [AgentResponseBlock(
            type='record_summary' if match.result == 'matched' else 'warning', text=answer,
            items=[f"Amount variance: {match.variances.get('amount', 0)}", *[str(item).replace('_', ' ') for item in match.variances.get('exceptions', [])]],
            record={'type': 'invoice_match', 'display_id': match.business_number, 'result': match.result, 'match_type': match.match_type, 'status': match.status},
            actions=[{'id': 'prepare_finance_handoff_proposal', 'label': 'Prepare finance review'}] if match.result == 'matched' else [{'id': 'open_invoice', 'label': 'Resolve variances', 'href': f'/invoices?invoice={invoice.id}'}],
        ).model_dump()], citations

    if intent == 'prepare_finance_handoff_proposal':
        reference = str(facts.get('match_id') or (envelope.referenced_entity_ids or [''])[0])
        match = workflows.user_scope_query(db, models.InvoiceMatchResult, user).filter(
            (models.InvoiceMatchResult.id == reference) | (models.InvoiceMatchResult.business_number == reference)
        ).first()
        if match is None:
            raise HTTPException(404, 'Invoice match not found')
        if match.result != 'matched' or match.status != 'current':
            raise HTTPException(409, 'Resolve invoice matching exceptions before finance handoff')
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action='prepare_finance_handoff',
            target_entity_type='invoice_match_results', target_entity_id=match.id,
            preview={'match_number': match.business_number, 'match_type': match.match_type, 'result': match.result, 'payment_release': False},
            expected_effect='Create a finance-review handoff. This does not release payment or post accounting entries.',
            required_authority=membership.role, record_version=match.version,
        ))
        answer = 'The matched invoice is ready for your confirmation before finance review handoff. No payment will be released.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={'type': 'finance_handoff', 'proposal_id': proposal.id, 'match_number': match.business_number, 'status': 'awaiting_confirmation'},
            actions=[{'id': 'confirm_proposal', 'label': 'Confirm finance review handoff', 'proposal_id': proposal.id}],
        ).model_dump()], citations

    if intent == 'summarize_procurement_risks':
        cases = workflows.user_scope_query(db, models.Case, user).filter(
            models.Case.status.notin_(['closed', 'resolved'])
        ).order_by(models.Case.due_at.asc()).limit(10).all()
        records = [{
            'id': row.id, 'title': row.title, 'status': row.status,
            'severity': row.severity, 'due_at': row.due_at.isoformat() if row.due_at else None,
        } for row in cases]
        critical = sum(1 for row in records if row['severity'] == 'critical')
        answer = f"There are {len(records)} open procurement risk{'s' if len(records) != 1 else ''}."
        if critical:
            answer += f" {critical} need immediate attention."
        return answer, [AgentResponseBlock(
            type='team_summary', text=answer,
            items=[f"{row['title']} · {row['status']}" for row in records],
            record={'count': len(records), 'critical_count': critical, 'risks': records},
        ).model_dump()], citations

    if intent == 'get_daily_brief':
        insights = __import__('app.management_insights', fromlist=['brief'])
        period = str(facts.get('period') or ('end_of_day' if 'end of day' in envelope.requested_outcome.casefold() else 'morning'))
        if period not in {'morning', 'end_of_day'}:
            period = 'morning'
        report = insights.brief(db, user, period)
        report = json.loads(json.dumps(report, default=str))
        for source in report['sources']:
            citations.append({'type': source['type'], 'id': source['id'], 'label': 'Assigned work', 'href': source['href']})
        return report['summary'], [AgentResponseBlock(
            type='team_summary', text=report['summary'],
            items=[f"{row['title']} · {row['status'].replace('_', ' ')}" for row in report['priorities']],
            record={'type': 'daily_brief', **report},
            actions=[{'id': 'open_my_work', 'label': 'Open my work', 'href': '/control-centre'}],
        ).model_dump()], citations

    if intent == 'summarize_management_metrics':
        report = __import__('app.management_insights', fromlist=['analytics']).analytics(db, user)
        measurable = [row for row in report['metrics'] if row['value'] is not None]
        answer = f"I calculated {len(measurable)} evidence-linked operating metrics. No employee score is generated."
        return answer, [AgentResponseBlock(
            type='record_summary', text=answer,
            items=[f"{row['label']}: {row['value']} {row['unit']} ({row['sample_size']} source records)" for row in measurable],
            record={'type': 'management_metrics', **report},
            actions=[{'id': 'open_analytics', 'label': 'Review metric evidence', 'href': '/admin'}],
        ).model_dump()], citations

    if intent == 'review_workspace_readiness':
        report = __import__('app.management_insights', fromlist=['readiness']).readiness(db, user)
        missing = [row for row in report['checks'] if not row['ready']]
        answer = f"Workspace readiness is {report['percent']}%: {report['completed']} of {report['total']} checks complete."
        return answer, [AgentResponseBlock(
            type='field_review', text=answer,
            items=[row['label'] for row in missing], record={'type': 'workspace_readiness', **report},
            actions=[{'id': 'open_setup', 'label': 'Complete setup', 'href': '/workspace/setup'}],
        ).model_dump()], citations

    if intent == 'explain_procurement_policy':
        policy_service = __import__('app.procurement_policy', fromlist=['active_policy', 'policy_rules', 'evaluate_comparison'])
        policy = policy_service.active_policy(db, user)
        rules = policy_service.policy_rules(policy)
        comparison_reference = str(facts.get('comparison_id') or '')
        evaluation = None
        if comparison_reference:
            comparison = workflows.user_scope_query(db, models.BidComparison, user).filter(
                (models.BidComparison.id == comparison_reference) | (models.BidComparison.business_number == comparison_reference)
            ).first()
            if comparison is None:
                raise HTTPException(status_code=404, detail='Supplier comparison not found')
            evaluation = policy_service.evaluate_comparison(db, user, comparison, persist=False)
            citations.append({'type': 'bid_comparison', 'id': comparison.id, 'label': comparison.business_number or 'Supplier comparison', 'href': f'/comparison?comparison={comparison.id}'})
        name = policy.name if policy else 'Safe default procurement policy'
        version = policy.policy_version if policy else 1
        answer = f'{name} version {version} is active.'
        if evaluation:
            answer += f" This comparison is {evaluation['decision'].replace('_', ' ')} under the current rules."
        items = [
            f"Minimum verified quotations: {rules['minimum_quotation_count']}",
            f"Allowed currencies: {', '.join(rules['allowed_currencies'])}",
            f"Current quote validity required: {'Yes' if rules['require_unexpired_quotes'] else 'No'}",
            f"Split supplier awards allowed: {'Yes' if rules['allow_split_awards'] else 'No'}",
        ]
        if evaluation:
            items.extend(str(row['message']) for row in evaluation['findings'])
        return answer, [AgentResponseBlock(
            type='field_review', text=answer, items=items,
            record={'type': 'procurement_policy', 'display_id': name, 'status': 'active', 'policy_version': version, 'evaluation': evaluation},
            actions=[{'id': 'open_policy', 'label': 'Review purchasing rules', 'href': '/admin'}] if membership.role == ADMIN else [],
        ).model_dump()], citations

    if intent in {'list_my_tasks', 'list_team_tasks', 'summarize_team_status'}:
        if intent == 'list_my_tasks':
            tasks = [
                task for task in workflows.tasks_for_user(db, user)
                if task.status in {'open', 'in_progress', 'blocked'}
            ][:5]
        else:
            visible = set(reporting_descendants(db, membership))
            tasks = db.query(models.Task).filter(
                models.Task.tenant_id == user.tenant_id,
                models.Task.plant_id == user.plant_id,
                models.Task.owner_membership_id.in_(visible or {''}),
            ).order_by(models.Task.due_at.asc()).all()
        records = []
        for task in tasks:
            business_context = None
            if task.entity_type == 'purchase_requirements' and task.entity_id:
                linked = workflows.user_scope_query(db, models.PurchaseRequirement, user).filter_by(id=task.entity_id).first()
                business_context = linked.business_number if linked else None
            elif task.entity_type == 'rfqs' and task.entity_id:
                linked = workflows.user_scope_query(db, models.RFQ, user).filter_by(id=task.entity_id).first()
                business_context = linked.business_number if linked else None
            records.append({
                'id': task.id, 'title': task.title, 'status': task.status,
                'priority': task.severity, 'due_at': task.due_at.isoformat() if task.due_at else None,
                'owner_membership_id': task.owner_membership_id, 'business_context': business_context,
            })
        answer = 'Here is your actionable work.' if records else 'You have no actionable work right now.'
        block = AgentResponseBlock(
            type='team_summary' if intent != 'list_my_tasks' else 'task_update',
            text=answer,
            items=[f"{row['title']} · {row['business_context'] or 'Linked work'} · {row['status'].replace('_', ' ')}" for row in records],
            record={'tasks': records},
        )
        if intent == 'summarize_team_status':
            activity = team_agent_activity(db, user, membership)
            blockers = sum(1 for row in activity if row['state'] == 'blocked')
            answer = f"I checked the scoped work of {len(activity)} team agent{'s' if len(activity) != 1 else ''}."
            if blockers:
                answer += f" {blockers} reported a blocker."
            block.text = answer
            activity_block = AgentResponseBlock(
                type='agent_activity', title='Team agent updates', text='Updates are grounded in each employee’s assigned work and formal status.',
                record={'agents': activity, 'blocked_count': blockers},
                items=[f"{row['employee_name']} · {row['state'].replace('_', ' ')} · {row['summary']}" for row in activity],
                actions=[
                    {'id': 'list_team_tasks', 'label': 'Open team work'},
                    *([{'id': 'request_task_update', 'label': 'Request update'}] if any(row['task_id'] for row in activity) else []),
                ],
            )
            return answer, [block.model_dump(), activity_block.model_dump()], citations
        return answer, [block.model_dump()], citations

    if intent == 'get_record':
        entity_id = str(facts.get('entity_id') or (envelope.referenced_entity_ids or [''])[0])
        model_types = (
            ('purchase_requirement', models.PurchaseRequirement, '/procurement'),
            ('rfq', models.RFQ, '/rfq-builder'),
            ('supplier_quote', models.SupplierQuote, '/quotes'),
            ('bid_comparison', models.BidComparison, '/comparison'),
            ('negotiation_round', models.NegotiationRound, '/negotiations'),
            ('award_decision', models.AwardDecision, '/approvals'),
            ('po_draft', models.PODraft, '/po-drafts'),
            ('supplier_acknowledgement', models.SupplierAcknowledgement, '/po-drafts'),
            ('asn', models.ASN, '/inbound'),
            ('gate_entry', models.GateEntry, '/gate'),
            ('store_receipt', models.StoreReceipt, '/store'),
            ('inspection_result', models.InspectionResult, '/quality'),
            ('case', models.Case, '/cases'),
            ('material_master_request', models.MaterialMasterRequest, '/procurement'),
        )
        for entity_type, model, href in model_types:
            record = workflows.user_scope_query(db, model, user).filter(
                (model.id == entity_id)
                | (func.lower(model.business_number) == entity_id.casefold())
            ).first()
            if record:
                data = record_dict(record)
                display_id = data.get('business_number') or record.id
                return str(display_id), [AgentResponseBlock(
                    type='record_summary', text=str(display_id), record={'type': entity_type, **data},
                    actions=[{'id': 'open_record', 'label': 'Open record', 'href': href}],
                ).model_dump()], [{'type': entity_type, 'id': record.id, 'label': display_id, 'href': href}]
        raise HTTPException(status_code=404, detail='Record not found in this workspace')

    if intent == 'upload_supplier_quotes':
        attachments = list(state.get('attachments') or [])
        if not attachments:
            answer = 'Attach one or more PDF, PNG, JPG, or XLSX supplier quotations.'
            return answer, [AgentResponseBlock(type='clarification', text=answer).model_dump()], citations
        # A continuation may contain only an RFQ number (or only a supplier
        # name).  Its facts were already persisted by ``apply_intent``; merge
        # them with this execution's facts instead of treating an omitted
        # model argument as a request to start over.
        batch_facts = {
            **load_thread_state(thread.context_state).draft_fields,
            **{key: value for key, value in facts.items() if value not in (None, '')},
        }
        from app.agent_resolution import resolve_record, resolve_supplier

        rfq_references: set[str] = set()
        current = state.get('selected_context') or state.get('current_work_item') or {}
        current_type = current.get('entity_type') or current.get('type')
        current_id = current.get('entity_id') or current.get('id')
        if current_type in {'rfq', 'rfqs'} and current_id:
            rfq_references.add(str(current_id))
        if batch_facts.get('rfq_id'):
            rfq_references.add(str(batch_facts['rfq_id']))
        for attachment in attachments:
            if attachment.get('linked_entity_type') in {'rfq', 'rfqs'} and attachment.get('linked_entity_id'):
                rfq_references.add(str(attachment['linked_entity_id']))
            if attachment.get('confirmed_rfq_id') or attachment.get('inferred_rfq_id'):
                rfq_references.add(str(
                    attachment.get('confirmed_rfq_id') or attachment.get('inferred_rfq_id')
                ))
        rfq_reference = (
            batch_facts.get('rfq_id') or batch_facts.get('rfq_reference')
            or batch_facts.get('rfq_number')
        )
        if rfq_reference:
            rfq_references.add(str(rfq_reference))
        # IDs, business numbers, selected context, and attachment inference may
        # all refer to the same RFQ. Resolve first, then count canonical IDs.
        rfq_ids: set[str] = set()
        unresolved_rfq_references: list[str] = []
        for reference in rfq_references:
            try:
                rfq_ids.add(resolve_record(db, user, 'rfq', reference).id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                unresolved_rfq_references.append(reference)
        # A single active RFQ is an unambiguous workspace context even when an
        # employee mistypes its sequence number. Never guess when alternatives
        # exist; the normal clarification path below then presents choices.
        if not rfq_ids and unresolved_rfq_references:
            candidates = workflows.user_scope_query(db, models.RFQ, user).filter(
                models.RFQ.status.notin_(("closed", "cancelled"))).all()
            if len(candidates) == 1:
                rfq_ids.add(candidates[0].id)
        if len(rfq_ids) != 1:
            rfq_choices = [{
                'id': item.id,
                'business_number': item.business_number,
                'label': item.business_number,
                'status': item.status,
            } for item in workflows.user_scope_query(db, models.RFQ, user).order_by(
                models.RFQ.updated_at.desc(),
            ).limit(5).all()]
            answer = 'Choose one RFQ for this quotation batch.'
            return answer, [AgentResponseBlock(
                type='clarification', text=answer, attachments=attachments,
                items=['rfq_id'],
                fields=[{'name': 'rfq_id', 'choices': rfq_choices}],
            ).model_dump()], citations
        rfq = resolve_record(db, user, 'rfq', next(iter(rfq_ids)))
        eligible = workflows.user_scope_query(db, models.Supplier, user).filter(
            models.Supplier.id.in_(list(rfq.supplier_ids or [])),
        ).all()
        by_id = {row.id: row for row in eligible}
        contact_supplier_ids: dict[str, set[str]] = {}
        for contact in workflows.user_scope_query(db, models.SupplierContact, user).filter(
            models.SupplierContact.supplier_id.in_(list(by_id)),
        ).all():
            domain = str(contact.email or '').rsplit('@', 1)[-1].casefold()
            if domain:
                contact_supplier_ids.setdefault(domain, set()).add(contact.supplier_id)
        explicit_reference = (
            batch_facts.get('supplier_id') or batch_facts.get('supplier_reference')
            or batch_facts.get('supplier_query') or batch_facts.get('supplier_name')
        )
        try:
            explicit_supplier = (
                resolve_supplier(db, user, str(explicit_reference))
                if explicit_reference else None
            )
        except HTTPException:
            explicit_supplier = None
        # The model understands the employee's wording and emits structured
        # mappings. The service only resolves its attachment references against
        # this authorized persisted batch.
        per_file_supplier_references: dict[str, str] = {}
        for mapping in batch_facts.get('attachment_mappings') or []:
            if not isinstance(mapping, dict):
                continue
            attachment_reference = str(
                mapping.get('attachment_reference') or ''
            ).strip().casefold()
            supplier_reference = str(
                mapping.get('supplier_reference') or ''
            ).strip()
            if not attachment_reference or not supplier_reference:
                continue
            matches = [
                attachment for attachment in attachments
                if attachment_reference in {
                    str(attachment.get('id') or '').casefold(),
                    str(attachment.get('document_id') or '').casefold(),
                    str(attachment.get('filename') or '').casefold(),
                }
            ]
            if len(matches) == 1:
                per_file_supplier_references[
                    str(matches[0]['document_id'])
                ] = supplier_reference
        if per_file_supplier_references:
            # Do not let a global supplier alias leak onto an
            # unmentioned file in the same clarification reply.
            explicit_supplier = None
        linked: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        processing: list[dict[str, Any]] = []
        extraction_failures: list[dict[str, Any]] = []
        for attachment in attachments:
            row = next(
                (item for item in live_attachment_rows if item.id == attachment.get('id')),
                None,
            )
            if row is None:
                continue
            if row.linked_quotation_id:
                quote = workflows.user_scope_query(db, models.SupplierQuote, user).filter_by(
                    id=row.linked_quotation_id,
                ).first()
                if quote:
                    linked.append({
                        'quote_id': quote.id, 'quote_number': quote.business_number,
                        'document_id': row.document_id, 'filename': attachment['filename'],
                        'verification_status': quote.verification_status,
                    })
                    continue
            extraction = workflows.user_scope_query(db, models.QuoteExtractionRun, user).filter_by(
                document_id=row.document_id,
            ).order_by(models.QuoteExtractionRun.created_at.desc()).first()
            fields = dict(extraction.extracted_fields or {}) if extraction else {}
            extracted_document_text = '\n'.join(
                str(item.get('original_text') or '')
                for item in ((extraction.evidence or []) if extraction else [])
                if str(item.get('source') or '').startswith(('pdf:', 'ocr:', 'xlsx:'))
            )
            evidence = {
                key: fields.get(key) for key in (
                    'supplier_legal_name', 'erp_vendor_id',
                    'supplier_contact_email', 'supplier_contact_domain', 'quote_number',
                ) if fields.get(key)
            }
            supplier = by_id.get(row.confirmed_supplier_id or '')
            match_kind = 'confirmed' if supplier else None
            file_reference = per_file_supplier_references.get(row.document_id)
            if supplier is None and file_reference:
                try:
                    file_supplier = resolve_supplier(db, user, file_reference)
                except HTTPException:
                    file_supplier = None
                    evidence['mapping_error'] = (
                        f'No unique eligible supplier matched {file_reference}'
                    )
                if file_supplier and file_supplier.id in by_id:
                    supplier, match_kind = file_supplier, 'user_file_mapping'
            if supplier is None and explicit_supplier and explicit_supplier.id in by_id:
                supplier, match_kind = explicit_supplier, 'user_reference'
            if supplier is None and extracted_document_text:
                supplier, match_kind = exact_supplier_identity_from_text(
                    extracted_document_text, eligible,
                )
                if supplier:
                    fields.setdefault('supplier_legal_name', supplier.name)
                    evidence['supplier_legal_name'] = supplier.name
                    evidence['document_identity_match'] = match_kind
            vendor_id = str(fields.get('erp_vendor_id') or '').strip().casefold()
            if supplier is None and vendor_id:
                matches = [
                    item for item in eligible
                    if str(item.erp_vendor_id or '').strip().casefold() == vendor_id
                ]
                if len(matches) == 1:
                    supplier, match_kind = matches[0], 'exact_erp_vendor_id'
            normalized_name = re.sub(
                r'[^a-z0-9]+', ' ',
                str(fields.get('supplier_legal_name') or '').casefold(),
            ).strip()
            contact_domain = str(
                fields.get('supplier_contact_domain')
                or str(fields.get('supplier_contact_email') or '').rsplit('@', 1)[-1]
            ).casefold()
            contact_matches = contact_supplier_ids.get(contact_domain, set())
            if supplier is None and normalized_name and not vendor_id:
                exact = [
                    item for item in eligible
                    if re.sub(r'[^a-z0-9]+', ' ', item.name.casefold()).strip() == normalized_name
                ]
                if len(exact) == 1:
                    supplier, match_kind = exact[0], 'exact_normalized_name'
            scored = sorted([
                (SequenceMatcher(
                    None, normalized_name,
                    re.sub(r'[^a-z0-9]+', ' ', item.name.casefold()).strip(),
                ).ratio(), item)
                for item in eligible
            ], key=lambda pair: pair[0], reverse=True) if normalized_name else []
            if supplier is None and scored:
                lead = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0)
                contact_conflict_for_top = bool(
                    contact_matches and scored[0][1].id not in contact_matches
                )
                if (
                    scored[0][0] >= 0.92 and lead >= 0.15
                    and not vendor_id and not contact_conflict_for_top
                ):
                    supplier, match_kind = scored[0][1], 'high_confidence_name'
            if supplier is not None and contact_matches and supplier.id not in contact_matches:
                supplier, match_kind = None, None
            row.inferred_rfq_id = rfq.id
            row.inference_evidence = {'match_kind': match_kind, **evidence}
            if supplier:
                row.inferred_supplier_id = supplier.id
                row.inference_confidence = 1.0 if match_kind.startswith(('exact_', 'confirmed', 'user_')) else scored[0][0]
                if membership.role == PLANT_MANAGER:
                    row.status = 'needs_review'
                    continue
                result = workflows.attach_uploaded_quote_documents(
                    db, user, rfq_id=rfq.id, supplier_id=supplier.id,
                    document_ids=[row.document_id],
                )[0]
                row.linked_quotation_id = result['quote_id']
                row.status = 'linked'
                linked.append(result)
            elif extraction is None and row.status in {'failed', 'needs_review'}:
                extraction_failures.append({
                    **attachment,
                    'error': row.user_explanation or (
                        'Extraction did not produce reviewable quotation fields.'
                    ),
                })
            elif extraction is None:
                row.status = 'extracting'
                processing.append(attachment)
            else:
                choices = [{
                    'supplier_id': item.id, 'label': item.name,
                    'confidence': round(score, 4),
                } for score, item in scored[:5]]
                row.status = 'needs_mapping'
                row.inference_confidence = scored[0][0] if scored else 0
                unresolved.append({
                    **attachment, 'evidence': evidence, 'candidates': choices,
                })
        db.flush()
        intake_state = load_thread_state(thread.context_state)
        intake_state.unresolved_fields = [
            {
                'name': 'supplier_id',
                'attachment_id': item.get('id'),
                'document_id': item.get('document_id'),
            }
            for item in unresolved
        ]
        intake_state.candidate_mappings = {
            str(item.get('id') or item.get('document_id')): item['candidates']
            for item in unresolved
        }
        intake_state.continuation_status = (
            'failed' if extraction_failures else
            'needs_input' if unresolved else
            'processing' if processing else
            'completed'
        )
        intake_state.active_goal.status = (
            'blocked' if extraction_failures or unresolved else
            'resolving' if processing else
            'completed'
        )
        persist_thread_state(thread, intake_state)
        if membership.role == PLANT_MANAGER:
            answer = 'Validated the quotation batch and preserved supplier inferences for Procurement review.'
            return answer, [AgentResponseBlock(
                type='role_handoff', text=answer, attachments=attachments,
                actions=[{'id': 'open_quotes', 'label': 'Open Procurement review', 'href': '/quotes'}],
            ).model_dump()], citations
        if extraction_failures:
            answer = (
                f"Linked {len(linked)} quotation{'s' if len(linked) != 1 else ''}; "
                f"{len(extraction_failures)} file{'s' if len(extraction_failures) != 1 else ''} "
                "need extraction retry or manual review."
            )
            return answer, [AgentResponseBlock(
                type='warning', text=answer, attachments=extraction_failures,
                actions=[{'id': 'open_quotes', 'label': 'Review quotation files', 'href': '/quotes'}],
            ).model_dump()], citations
        if unresolved:
            answer = (
                f"Linked {len(linked)} quotation{'s' if len(linked) != 1 else ''}; "
                f"{len(unresolved)} file{'s' if len(unresolved) != 1 else ''} need supplier mapping."
            )
            return answer, [AgentResponseBlock(
                type='clarification', text=answer, attachments=unresolved,
                fields=[{'name': 'supplier_id', 'choices': item['candidates']} for item in unresolved],
            ).model_dump()], citations
        if processing:
            answer = f'Extracting supplier identity from {len(processing)} quotation file{"s" if len(processing) != 1 else ""}.'
            return answer, [AgentResponseBlock(
                type='run_progress', text=answer, attachments=attachments,
            ).model_dump()], citations
        if not linked:
            answer = 'No quotation files were eligible to link.'
            return answer, [AgentResponseBlock(type='warning', text=answer).model_dump()], citations
        receipt = models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='upload_supplier_quotes', status='succeeded',
            target_entity_type='supplier_quotes', target_entity_id=linked[0]['quote_id'],
            result_summary={'rfq_id': rfq.id, 'quotes': linked},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:upload_supplier_quotes',
        )
        db.add(receipt)
        answer = f"Linked {len(linked)} supplier quotation{'s' if len(linked) != 1 else ''} to {rfq.business_number}."
        record = {
            'type': 'supplier_quote_batch', 'id': linked[0]['quote_id'],
            'rfq_id': rfq.id, 'rfq_number': rfq.business_number,
            'quotes': linked,
        }
        return answer, [
            AgentResponseBlock(
                type='field_review', text=answer, attachments=linked, record=record,
                actions=[{'id': 'review_quote_extraction', 'label': 'Review extracted fields', 'href': '/quotes'}],
            ).model_dump(),
            AgentResponseBlock(type='action_receipt', text='Quotation documents were saved.', record=record).model_dump(),
        ], citations

    if intent == 'review_quote_extraction':
        quote_id = str(facts.get('quote_id') or '')
        quote = workflows.get_scoped_or_404(db, models.SupplierQuote, user, quote_id, 'Quotation')
        fields = workflows.quote_field_verifications(db, user, quote.id)
        answer = f"Quotation {quote.business_number or quote.id} is {quote.verification_status.replace('_', ' ')}."
        return answer, [AgentResponseBlock(
            type='field_review', text=answer, record={'id': quote.id, 'status': quote.verification_status},
            fields=fields, actions=[{'id': 'open_quote', 'label': 'Review fields', 'href': '/quotes'}],
        ).model_dump()], citations

    if intent == 'verify_quote_fields_proposal':
        from app.agent_resolution import resolve_record
        quote = resolve_record(db, user, 'supplier_quote', str(facts.get('quote_id') or ''))
        decisions = facts.get('decisions')
        if not isinstance(decisions, list) or not decisions:
            answer = 'Choose Accept, Correct, or Reject for at least one extracted field.'
            return answer, [AgentResponseBlock(
                type='clarification', text=answer,
                actions=[{'id': 'open_quote', 'label': 'Review extracted fields', 'href': f'/quotes?quote={quote.id}'}],
            ).model_dump()], citations
        available = {
            row.field_name for row in workflows.user_scope_query(
                db, models.QuoteFieldVerification, user,
            ).filter(models.QuoteFieldVerification.quote_id == quote.id).all()
        }
        normalized: list[dict[str, Any]] = []
        for raw in decisions:
            if not isinstance(raw, dict):
                raise HTTPException(status_code=422, detail='Each field decision must be an object')
            field_name = str(raw.get('field_name') or '')
            decision = str(raw.get('decision') or '').casefold()
            if field_name not in available:
                raise HTTPException(status_code=422, detail=f'Unknown extracted field {field_name}')
            if decision not in {'accept', 'correct', 'reject'}:
                raise HTTPException(status_code=422, detail=f'Invalid decision for {field_name}')
            if decision == 'correct' and raw.get('verified_value') is None:
                raise HTTPException(status_code=422, detail=f'Corrected value is required for {field_name}')
            normalized.append({
                'field_name': field_name, 'decision': decision,
                **({'verified_value': raw.get('verified_value')} if decision == 'correct' else {}),
            })
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action='verify_quote_fields',
            target_entity_type='supplier_quotes', target_entity_id=quote.id,
            preview={
                'business_number': quote.business_number or quote.quote_number,
                'quote_number': quote.quote_number, 'decisions': normalized,
            },
            expected_effect='Apply these human-reviewed evidence decisions to the canonical supplier quotation.',
            required_authority=membership.role, record_version=quote.version,
        ))
        state['pending_proposal_id'] = proposal.id
        persist_thread_state(thread, load_thread_state(state))
        answer = f'{len(normalized)} evidence decision{"s" if len(normalized) != 1 else ""} for {quote.quote_number} are ready for confirmation.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={
                'type': 'supplier_quote', 'id': quote.id,
                'display_id': quote.quote_number, 'proposal_id': proposal.id,
                'decision_count': len(normalized), 'status': quote.verification_status,
            },
            fields=normalized,
            actions=[
                {'id': 'confirm_proposal', 'label': 'Confirm evidence decisions', 'proposal_id': proposal.id},
                {'id': 'open_quote', 'label': 'Review source evidence', 'href': f'/quotes?quote={quote.id}'},
            ],
        ).model_dump()], citations

    if intent == 'search_approved_material':
        resolution = resolve_procurement_action(db, user, membership, facts)
        if resolution.get('item'):
            item = resolution['item']
            state = dict(thread.context_state or {})
            draft = dict(state.get('draft_fields') or {})
            draft.update({
                'item_id': item.id,
                'item_code': item.code,
                'material_query': item.name,
                'uom': draft.get('uom') or item.uom_id,
            })
            state['draft_fields'] = state['procurement'] = draft
            state.pop('material_error', None)
            persist_thread_state(thread, load_thread_state(state))
            missing = [row for row in resolution['missing'] if not row.startswith('named Purchase Executive')]
            text = f"Matched {item.code} · {item.name} · {item.uom_id}."
            if resolution.get('canonical_code_corrected'):
                text += f" I used the canonical code {item.code}."
            blocks = [AgentResponseBlock(
                type='record_summary', text=text,
                record={'type': 'material', 'id': item.id, 'code': item.code, 'name': item.name, 'uom': item.uom_id},
            )]
            if missing:
                blocks.append(AgentResponseBlock(
                    type='clarification',
                    text=requirement_clarification(missing, item=item),
                    items=missing,
                ))
            return text, [block.model_dump() for block in blocks], citations
        if resolution['ambiguities']:
            choices = resolution['ambiguities'][0]['choices']
            answer = 'Choose one approved material.'
            return answer, [AgentResponseBlock(
                type='clarification', text=answer,
                items=[f"{row['code']} · {row['name']}" for row in choices],
                fields=[{'name': 'material', 'choices': choices}],
            ).model_dump()], citations
        answer = 'No approved material matched. You can request a new material master here.'
        state['material_error'] = facts.get('material_query') or facts.get('item_code')
        persist_thread_state(thread, load_thread_state(state))
        return answer, [AgentResponseBlock(
            type='action_required', text=answer,
            actions=[{'id': 'create_material_master_request', 'label': 'Request new material'}],
        ).model_dump()], citations

    if intent == 'create_material_master_request':
        pending = dict(state.get('pending_confirmation') or {})
        confirmed = bool(pending and re.search(r'\b(confirm|yes|proceed|go ahead)\b', question))
        if confirmed:
            from app import procurement_v2
            request = procurement_v2.create_material_request(
                db, user, str(pending['item_code']), str(pending['description']),
                str(pending['uom']), str(pending.get('specification') or ''), str(pending['reason']),
            )
            db.flush()
            receipt = models.AgentActionReceipt(
                tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
                tool_name='create_material_master_request', status='succeeded',
                target_entity_type='material_master_request', target_entity_id=request.id,
                result_summary={'material_master_request_id': request.id, 'status': request.status},
                executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
                idempotency_key=f'{correlation_id}:create_material_master_request',
            )
            db.add(receipt)
            state.pop('pending_confirmation', None)
            state['material_master_request_id'] = request.id
            state['blocked_on'] = 'material_approval'
            state['recent_entities'] = [
                {'type': 'material_master_request', 'id': request.id, 'display_id': request.id},
                *[row for row in recent if row.get('id') != request.id],
            ][:10]
            state['last_action_receipt_id'] = receipt.id
            persist_thread_state(thread, load_thread_state(state))
            answer = f'Created material request {request.id}. Status: pending.'
            return answer, [AgentResponseBlock(
                type='action_required', text=answer,
                record={'type': 'material_master_request', 'id': request.id, 'status': request.status},
            ).model_dump()], citations
        description = str(facts.get('material_query') or '').strip()
        item_code = str(facts.get('item_code') or '').strip()
        required = []
        if not description:
            required.append('material name')
        if not item_code:
            required.append('requested item code')
        if not facts.get('uom'):
            required.append('unit of measure')
        if not facts.get('reason'):
            required.append('business reason')
        if required:
            answer = requirement_clarification(required)
            return answer, [AgentResponseBlock(type='clarification', text=answer, items=required).model_dump()], citations
        pending = {
            'item_code': item_code, 'description': description, 'uom': str(facts['uom']).upper(),
            'specification': str(facts.get('specification') or ''), 'reason': str(facts['reason']),
        }
        state['pending_confirmation'] = pending
        state['blocked_on'] = 'material_request_confirmation'
        persist_thread_state(thread, load_thread_state(state))
        answer = f"Confirm the new material request for {item_code} · {description} · {pending['uom']}."
        return answer, [AgentResponseBlock(
            type='confirmation', text=answer,
            record={'type': 'material_master_request_draft', **pending},
            actions=[
                {'id': 'confirm', 'label': 'Confirm request'},
                {'id': 'reject', 'label': 'Cancel'},
            ],
        ).model_dump()], citations

    if intent == 'create_purchase_requirement':
        request_id = state.get('material_master_request_id')
        if request_id:
            material_request = workflows.user_scope_query(db, models.MaterialMasterRequest, user).filter_by(id=request_id).first()
            if material_request and material_request.status == 'pending':
                answer = f'Material request {material_request.id} is pending approval. The requirement draft is saved.'
                return answer, [AgentResponseBlock(
                    type='action_required', text=answer,
                    record={'type': 'material_master_request', 'id': material_request.id, 'status': 'pending'},
                ).model_dump()], citations
            if material_request and material_request.status == 'approved' and material_request.resulting_item_id:
                facts['item_id'] = material_request.resulting_item_id
                item = db.get(models.Item, material_request.resulting_item_id)
                if item:
                    facts.update({'item_code': item.code, 'material_query': item.name, 'uom': facts.get('uom') or item.uom_id})
                state.pop('blocked_on', None)
                persist_thread_state(thread, load_thread_state(state))
            elif material_request and material_request.status == 'rejected':
                state.pop('material_master_request_id', None)
                state.pop('blocked_on', None)
                persist_thread_state(thread, load_thread_state(state))
                answer = f'Material request {material_request.id} was rejected. Quantity, date, and reason remain in the draft.'
                return answer, [AgentResponseBlock(type='warning', text=answer).model_dump()], citations
        resolution = resolve_procurement_action(db, user, membership, facts)
        if resolution['ambiguities']:
            choices = resolution['ambiguities'][0]['choices']
            answer = f"Choose one {resolution['ambiguities'][0]['field']} before creating the requirement."
            return answer, [AgentResponseBlock(type='clarification', text=answer, fields=[{'choices': choices}]).model_dump()], citations
        if resolution['missing']:
            missing = resolution['missing']
            material_missing = 'material' in missing
            answer = (
                'I could not find that material in the approved catalog. '
                'You can request a new material, or tell me another material name or item code.'
                if material_missing else
                requirement_clarification(missing, item=resolution.get('item'))
            )
            return answer, [AgentResponseBlock(
                type='clarification', text=answer, items=missing,
                actions=[{'id': 'create_material_master_request', 'label': 'Request new material'}] if material_missing else [],
            ).model_dump()], citations
        receipt = execute_procurement_delegation(
            db, user, membership, profile, thread, run, facts, resolution, correlation_id,
        )
        item = resolution['item']
        requirement = db.get(models.PurchaseRequirement, receipt['requirement_id'])
        answer = (
            f"Requirement {receipt['requirement_number']} already exists, so I kept its current assignment."
            if receipt.get('reused') else
            f"Created requirement {receipt['requirement_number']}."
        )
        details = f"{item.name} · {float(facts['quantity']):g} {str(facts['uom']).upper()} · Need by {facts['need_by_date']}"
        block = AgentResponseBlock(
            type='record_summary' if receipt.get('reused') else 'record_created', text=answer,
            items=[details, f"Assigned to {receipt['assignee_name']}. Status: {requirement.status if requirement else 'approved'}."],
            record={
                'type': 'purchase_requirement', 'id': receipt['requirement_id'],
                'display_id': receipt['requirement_number'], 'status': requirement.status if requirement else 'approved',
                'item_code': item.code, 'material': item.name, 'quantity': facts['quantity'],
                'uom': facts['uom'], 'need_by_date': facts['need_by_date'],
                'assignee': receipt['assignee_name'],
            },
            actions=[{'id': 'open_requirement', 'label': 'Open requirement', 'href': '/procurement'}],
        )
        citations.append({'type': 'purchase_requirement', 'id': receipt['requirement_id'], 'label': receipt['requirement_number'], 'href': '/procurement'})
        response_blocks = [block.model_dump()]
        if not receipt.get('reused'):
            response_blocks.append(AgentResponseBlock(
                type='record_summary', text=details, record=block.record,
                actions=block.actions,
            ).model_dump())
            response_blocks.append(AgentResponseBlock(
                type='action_receipt', text=f"Persisted as {receipt['requirement_number']}.",
                record=block.record,
            ).model_dump())
        response_blocks.append(AgentResponseBlock(
                type='role_handoff',
                text='The assigned Purchase Executive can prepare the RFQ; verified quotations can then be used for comparison.',
            ).model_dump())
        return answer, response_blocks, citations

    if intent == 'request_task_update':
        task_id = str(facts.get('task_id') or (envelope.referenced_entity_ids or [''])[0])
        if not task_id:
            return 'Choose the team task that needs an update.', [AgentResponseBlock(
                type='clarification', text='Choose the team task that needs an update.'
            ).model_dump()], citations
        from app import task_service
        task = task_service.request_follow_up(
            db, user, task_id, task_service.TaskFollowUpRequest(
                message=envelope.requested_outcome if envelope.requested_outcome else None,
            ),
        )
        employee = db.get(models.User, task.owner_user_id) if task.owner_user_id else None
        answer = f"Asked {employee.name if employee else 'the assignee'} for an update on {task.title}."
        return answer, [AgentResponseBlock(
            type='agent_activity', text=answer,
            record={'task_id': task.id, 'task_title': task.title, 'status': task.status, 'recipient': employee.name if employee else None},
            actions=[{'id': 'summarize_team_status', 'label': 'Check team status'}],
        ).model_dump()], citations

    if intent == 'prepare_rfq_draft':
        if membership.role not in {PURCHASE_EXECUTIVE, ADMIN}:
            raise HTTPException(status_code=403, detail='You are not authorized to prepare supplier requests')
        task_requirement_id = None
        if thread.work_item_id:
            linked_task = task_for_membership(db, membership, thread.work_item_id)
            if linked_task and linked_task.entity_type == 'purchase_requirements':
                task_requirement_id = linked_task.entity_id
        reference = str(
            facts.get('requirement_id')
            or (envelope.referenced_entity_ids or [''])[0]
            or task_requirement_id
            or envelope.requested_outcome
        )
        requirement = resolve_requirement_reference(
            db, user, reference, thread_state=state,
        )
        from app import procurement_v2
        rfq = workflows.create_rfq_from_requirement(db, user, requirement.id)
        artifact = procurement_v2.generate_artifact(db, user, 'rfq', rfq.id, final=False)
        result = {
            'requirement_id': requirement.id,
            'requirement_number': requirement.business_number,
            'rfq_id': rfq.id,
            'rfq_number': rfq.business_number,
            'supplier_count': len(rfq.supplier_ids or []),
            'deadline': rfq.deadline,
            'artifact_id': artifact.id,
            'document_id': artifact.document_id,
            'status': rfq.status,
        }
        db.add(models.AgentToolCall(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            agent_profile_id=profile.id, tool_name='prepare_rfq_draft',
            arguments={'requirement_reference': reference},
            result_hash=hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest(),
            target_entity_type='rfqs', target_entity_id=rfq.id,
            authorization_decision='allowed', latency_ms=0, correlation_id=correlation_id,
        ))
        receipt = models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='prepare_rfq_draft', status='succeeded',
            target_entity_type='rfqs', target_entity_id=rfq.id,
            result_summary=result, executed_by_membership_id=membership.id,
            started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:prepare_rfq_draft',
        )
        db.add(receipt)
        db.flush()
        state['recent_entities'] = [
            {'type': 'rfq', 'id': rfq.id, 'display_id': rfq.business_number},
            {'type': 'purchase_requirement', 'id': requirement.id, 'display_id': requirement.business_number},
            *[row for row in recent if row.get('id') not in {rfq.id, requirement.id}],
        ][:12]
        state['current_work_item'] = {'type': 'rfq', 'id': rfq.id}
        state['last_action_receipt_id'] = receipt.id
        state['updated_at'] = utcnow().isoformat()
        persist_thread_state(thread, load_thread_state(state))
        answer = f'Supplier request {rfq.business_number} is ready for review.'
        detail = (
            f'{requirement.business_number} · {len(rfq.supplier_ids or [])} approved suppliers · '
            f'Response deadline {rfq.deadline}'
        )
        record = {
            'type': 'rfq', 'id': rfq.id, 'display_id': rfq.business_number,
            'requirement_id': requirement.id, 'requirement_number': requirement.business_number,
            'supplier_count': len(rfq.supplier_ids or []), 'deadline': rfq.deadline,
            'artifact_id': artifact.id, 'document_id': artifact.document_id, 'status': rfq.status,
        }
        citations.append({'type': 'rfq', 'id': rfq.id, 'label': rfq.business_number, 'href': f'/rfq-builder?rfq={rfq.id}'})
        record_run_event(db, run, 'tool_completed', {'tool': 'prepare_rfq_draft', 'target_id': rfq.id, 'status': 'succeeded'})
        return answer, [
            AgentResponseBlock(
                type='prepared_artifact', text=answer, items=[detail, 'This request has not been sent to suppliers.'],
                record=record,
                actions=[
                    {'id': 'review_rfq', 'label': 'Review draft', 'href': f'/rfq-builder?rfq={rfq.id}'},
                    {'id': 'edit_suppliers', 'label': 'Edit suppliers', 'href': f'/rfq-builder?rfq={rfq.id}'},
                ],
            ).model_dump(),
            AgentResponseBlock(type='action_receipt', text=f'Persisted as {rfq.business_number}.', record=record).model_dump(),
        ], citations

    if intent == 'prepare_supplier_comparison':
        if membership.role not in {'purchase_manager', ADMIN}:
            raise HTTPException(status_code=403, detail='You are not authorized to compare supplier quotations')
        from app import procurement_v2
        from app.agent_resolution import resolve_record
        reference = str(facts.get('rfq_id') or (envelope.referenced_entity_ids or [''])[0])
        rfq = resolve_record(db, user, 'rfq', reference)
        comparison = workflows.generate_comparison(db, user, rfq.id)
        artifact = procurement_v2.generate_artifact(db, user, 'comparison', comparison.id, final=False)
        verified_quotes = workflows.user_scope_query(db, models.SupplierQuote, user).filter_by(
            rfq_id=rfq.id, verification_status='verified',
        ).count()
        recommended_row = next(
            (row for row in (comparison.rows or []) if row.get('recommendation') == 'Recommended'),
            None,
        )
        risks = list(dict.fromkeys(
            reason
            for row in (comparison.rows or [])
            if row.get('disqualified') or row.get('recommendation') != 'Recommended'
            for reason in (row.get('reasons') or [])
        ))[:4]
        result = {
            'comparison_id': comparison.id, 'comparison_number': comparison.business_number,
            'rfq_id': rfq.id, 'rfq_number': rfq.business_number,
            'recommended_supplier_id': comparison.recommended_supplier_id,
            'recommended_supplier_name': recommended_row.get('supplier_name') if recommended_row else None,
            'recommendation_rationale': comparison.recommendation_rationale,
            'verified_quote_count': verified_quotes, 'risks': risks,
            'artifact_id': artifact.id, 'document_id': artifact.document_id,
            'status': comparison.status,
        }
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='prepare_supplier_comparison', status='succeeded',
            target_entity_type='bid_comparison', target_entity_id=comparison.id,
            result_summary=result, executed_by_membership_id=membership.id,
            started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:prepare_supplier_comparison',
        ))
        state['recent_entities'] = [
            {'type': 'bid_comparison', 'id': comparison.id, 'display_id': comparison.business_number},
            *[row for row in recent if row.get('id') != comparison.id],
        ][:12]
        state['current_work_item'] = {'type': 'bid_comparison', 'id': comparison.id}
        persist_thread_state(thread, load_thread_state(state))
        answer = f'Comparison {comparison.business_number} is ready for review.'
        record = {'type': 'bid_comparison', 'id': comparison.id, 'display_id': comparison.business_number, **result}
        return answer, [
            AgentResponseBlock(
                type='comparison_preview', text=answer, record=record,
                items=[
                    comparison.recommendation_rationale,
                    f'{verified_quotes} verified supplier quotation{"s" if verified_quotes != 1 else ""} compared.',
                    *([f'Risks to review: {"; ".join(risks)}'] if risks else []),
                ],
                actions=[{'id': 'review_comparison', 'label': 'Review comparison', 'href': f'/comparison?comparison={comparison.id}'}],
            ).model_dump(),
            AgentResponseBlock(type='action_receipt', text=f'Persisted as {comparison.business_number}.', record=record).model_dump(),
        ], citations

    if intent in {'publish_rfq_proposal', 'submit_comparison_proposal', 'confirm_purchase_order_proposal'}:
        from app.agent_resolution import resolve_record
        definitions = {
            'publish_rfq_proposal': ('rfq', 'rfqs', 'rfq_id', 'publish_rfq', 'purchase_executive', 'Send this immutable supplier request and prepare supplier deliveries.'),
            'submit_comparison_proposal': ('bid_comparison', 'bid_comparison', 'comparison_id', 'submit_comparison', 'purchase_manager', 'Freeze this comparison version and send the recommendation for approval.'),
            'confirm_purchase_order_proposal': ('bid_comparison', 'bid_comparison', 'comparison_id', 'confirm_purchase_order', 'purchase_manager', 'Create the final immutable purchase order from the approved comparison.'),
        }
        model_type, target_type, field, action, authority, effect = definitions[intent]
        reference = str(facts.get(field) or (envelope.referenced_entity_ids or [''])[0])
        target = resolve_record(db, user, model_type, reference)
        preview = {
            'business_number': target.business_number, 'status': target.status,
            'version': target.version,
        }
        if action == 'publish_rfq':
            preview.update({'supplier_ids': target.supplier_ids, 'deadline': target.deadline})
        if action == 'submit_comparison':
            preview['rationale'] = str(facts.get('rationale') or getattr(target, 'recommendation_rationale', '') or 'Recommendation reviewed')
        if action == 'confirm_purchase_order':
            preview['allocations'] = __import__(
                'app.procurement_v2', fromlist=['recommended_award_allocations']
            ).recommended_award_allocations(db, user, target)
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action=action,
            target_entity_type=target_type, target_entity_id=target.id,
            preview=preview, expected_effect=effect,
            required_authority=membership.role if membership.role == ADMIN else authority,
            record_version=target.version,
        ))
        state['pending_proposal_id'] = proposal.id
        persist_thread_state(thread, load_thread_state(state))
        answer = f'{target.business_number} is ready for your confirmation.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={'proposal_id': proposal.id, 'action': action, **preview},
            actions=[{'id': 'confirm_proposal', 'label': 'Confirm', 'proposal_id': proposal.id}],
        ).model_dump()], citations

    if intent == 'record_comparison_decision_proposal':
        from app.agent_resolution import resolve_record
        reference = str(facts.get('comparison_id') or (envelope.referenced_entity_ids or [''])[0])
        comparison = resolve_record(db, user, 'bid_comparison', reference)
        decision = str(facts.get('decision') or '').casefold()
        if decision not in {'approve', 'reject', 'request_changes'}:
            answer = 'Choose Approve, Reject, or Request changes for this comparison.'
            return answer, [AgentResponseBlock(type='clarification', text=answer).model_dump()], citations
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action='decide_comparison',
            target_entity_type='bid_comparison', target_entity_id=comparison.id,
            preview={'business_number': comparison.business_number, 'decision': decision, 'rationale': str(facts.get('rationale') or envelope.requested_outcome)},
            expected_effect=f'{decision.replace("_", " ").title()} comparison version {comparison.comparison_version}.',
            required_authority=membership.role, record_version=comparison.version,
        ))
        answer = f'{decision.replace("_", " ").title()} is ready for confirmation on {comparison.business_number}.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={'proposal_id': proposal.id, **proposal.preview},
            actions=[{'id': 'confirm_proposal', 'label': 'Confirm decision', 'proposal_id': proposal.id}],
        ).model_dump()], citations

    if intent == 'prepare_negotiation_proposal':
        from app.agent_resolution import resolve_record, resolve_supplier
        rfq = resolve_record(db, user, 'rfq', str(facts.get('rfq_id') or ''))
        supplier = resolve_supplier(db, user, str(facts.get('supplier_id') or ''))
        negotiation = workflows.create_negotiation(
            db, user, rfq.id, supplier.id, str(facts.get('target') or ''),
            str(facts.get('drafted_message') or ''),
        )
        workflows.submit_negotiation(db, user, negotiation.id)
        # Capture the concurrency token after the submitted-state mutation has
        # been flushed; otherwise the proposal is stale at the instant it is
        # presented to the human approver.
        db.flush()
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action='approve_negotiation',
            target_entity_type='negotiation_rounds', target_entity_id=negotiation.id,
            preview={
                'business_number': negotiation.business_number,
                'rfq_number': rfq.business_number, 'supplier_name': supplier.name,
                'target': negotiation.target, 'message': negotiation.drafted_message,
            },
            expected_effect='Approve this reviewed negotiation message for the supplier communication queue.',
            required_authority=membership.role, record_version=negotiation.version,
        ))
        receipt = models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='prepare_negotiation_proposal', status='succeeded',
            target_entity_type='negotiation_rounds', target_entity_id=negotiation.id,
            result_summary={'negotiation_id': negotiation.id, 'proposal_id': proposal.id},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:prepare_negotiation_proposal',
        )
        db.add(receipt)
        answer = f'Negotiation {negotiation.business_number} is ready for your review.'
        record = {
            'type': 'negotiation_round', 'id': negotiation.id,
            'display_id': negotiation.business_number, 'status': negotiation.status,
            'supplier_name': supplier.name, 'proposal_id': proposal.id,
        }
        return answer, [
            AgentResponseBlock(
                type='action_proposal', text=answer, record=record,
                actions=[{'id': 'confirm_proposal', 'label': 'Approve message', 'proposal_id': proposal.id}],
            ).model_dump(),
            AgentResponseBlock(type='action_receipt', text='Negotiation draft was saved.', record=record).model_dump(),
        ], citations

    if intent in {'prepare_po_supplier_email_proposal', 'approve_po_change_proposal', 'prepare_asn_proposal', 'close_exception_proposal', 'review_supplier_certificate_proposal', 'close_requirement_lifecycle_proposal'}:
        from app.agent_resolution import resolve_record
        definitions = {
            'prepare_po_supplier_email_proposal': (
                'po_draft', 'po_id', 'po_drafts', 'prepare_po_supplier_email',
                'Prepare the final purchase-order email in the controlled supplier queue.',
            ),
            'approve_po_change_proposal': (
                'po_draft', 'po_id', 'po_drafts', 'approve_po_change',
                'Approve this immutable purchase-order change and prepare its separate external action.',
            ),
            'prepare_asn_proposal': (
                'po_draft', 'po_id', 'po_drafts', 'create_asn',
                'Record the verified advance shipping notice for this purchase order.',
            ),
            'close_exception_proposal': (
                'case', 'case_id', 'cases', 'close_case',
                'Close this exception with the supplied evidence-backed resolution.',
            ),
            'review_supplier_certificate_proposal': (
                'supplier_certificate', 'certificate_id', 'supplier_certificates', 'decide_supplier_certificate',
                'Apply the reviewed supplier-certificate evidence decision and recalculate supplier eligibility.',
            ),
            'close_requirement_lifecycle_proposal': (
                'purchase_requirement', 'requirement_id', 'purchase_requirements', 'close_requirement_lifecycle',
                'Close this procurement lifecycle only after all delivery, quality, finance, and payment evidence reconciles.',
            ),
        }
        model_type, field, target_type, action, effect = definitions[intent]
        target = resolve_record(db, user, model_type, str(facts.get(field) or ''))
        preview = {key: value for key, value in facts.items() if value is not None}
        preview['business_number'] = target.business_number
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action=action,
            target_entity_type=target_type, target_entity_id=target.id,
            preview=preview, expected_effect=effect,
            required_authority=membership.role, record_version=target.version,
        ))
        answer = f'{target.business_number} is ready for confirmation.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={'proposal_id': proposal.id, 'action': action, **preview},
            actions=[{'id': 'confirm_proposal', 'label': 'Confirm', 'proposal_id': proposal.id}],
        ).model_dump()], citations

    if intent == 'prepare_supplier_followup':
        from app.agent_resolution import resolve_record, resolve_supplier
        rfq = resolve_record(db, user, 'rfq', str(facts.get('rfq_id') or ''))
        supplier = resolve_supplier(db, user, str(facts.get('supplier_id') or ''))
        if supplier.id not in (rfq.supplier_ids or []):
            raise HTTPException(status_code=409, detail='Choose a supplier included in this supplier request')
        message = str(facts.get('message') or '').strip()
        if not message:
            return 'What should the supplier be asked to confirm?', [AgentResponseBlock(
                type='clarification', text='What should the supplier be asked to confirm?',
                items=['Follow-up message'],
            ).model_dump()], citations
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action='prepare_supplier_followup',
            target_entity_type='rfqs', target_entity_id=rfq.id,
            preview={
                'business_number': rfq.business_number, 'supplier_id': supplier.id,
                'supplier_name': supplier.name, 'message': message,
            },
            expected_effect='Place this reviewed follow-up in the controlled supplier delivery queue. It is not sent until the delivery queue dispatches it.',
            required_authority=membership.role, record_version=rfq.version,
        ))
        state['pending_proposal_id'] = proposal.id
        persist_thread_state(thread, load_thread_state(state))
        answer = f'Your follow-up to {supplier.name} is ready for review.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={
                'type': 'supplier_followup', 'proposal_id': proposal.id,
                'rfq_id': rfq.id, 'rfq_number': rfq.business_number,
                'supplier_id': supplier.id, 'supplier_name': supplier.name,
                'message': message, 'status': 'awaiting confirmation',
            },
            actions=[
                {'id': 'confirm_proposal', 'label': 'Approve follow-up', 'proposal_id': proposal.id},
                {'id': 'open_rfq', 'label': 'Review supplier request', 'href': f'/rfq-builder?rfq={rfq.id}'},
            ],
        ).model_dump()], citations

    if intent in {'prepare_gate_entry_proposal', 'prepare_store_receipt_proposal', 'prepare_quality_inspection_proposal'}:
        from app.agent_resolution import resolve_record
        definitions = {
            'prepare_gate_entry_proposal': ('po_draft', 'po_id', 'po_drafts', 'record_gate_entry', GATE_OPERATOR),
            'prepare_store_receipt_proposal': ('po_draft', 'po_id', 'po_drafts', 'record_store_receipt', 'store_manager'),
            'prepare_quality_inspection_proposal': ('store_receipt', 'receipt_id', 'store_receipts', 'record_inspection', 'quality_inspector'),
        }
        model_type, field, target_type, action, authority = definitions[intent]
        target = resolve_record(db, user, model_type, str(facts.get(field) or ''))
        preview = {key: value for key, value in facts.items() if value is not None}
        preview['business_number'] = target.business_number
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action=action,
            target_entity_type=target_type, target_entity_id=target.id,
            preview=preview, expected_effect='Record the verified operational facts in the canonical inbound workflow.',
            required_authority=membership.role if membership.role == ADMIN else authority,
            record_version=target.version,
        ))
        answer = f'{target.business_number} is ready for confirmation.'
        hrefs = {
            'prepare_gate_entry_proposal': '/gate',
            'prepare_store_receipt_proposal': '/store',
            'prepare_quality_inspection_proposal': '/quality',
        }
        record = {
            'type': model_type, 'id': target.id, 'display_id': target.business_number,
            'proposal_id': proposal.id, **preview,
        }
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer, record=record,
            actions=[
                {'id': 'confirm_proposal', 'label': 'Confirm', 'proposal_id': proposal.id},
                {'id': 'open_record', 'label': 'Review record', 'href': hrefs[intent]},
            ],
        ).model_dump()], citations

    if intent == 'prepare_supplier_return':
        supplier_return = workflows.create_supplier_return(
            db, user, str(facts.get('inspection_id') or ''),
            float(facts.get('return_quantity') or 0), str(facts.get('reason') or ''),
        )
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='prepare_supplier_return', status='succeeded',
            target_entity_type='supplier_return', target_entity_id=supplier_return.id,
            result_summary={'business_number': supplier_return.business_number, 'status': supplier_return.status, 'return_quantity': supplier_return.return_quantity},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:prepare_supplier_return',
        ))
        answer = f'Return {supplier_return.business_number} is prepared for {supplier_return.return_quantity:g} rejected units.'
        record = {'type': 'supplier_return', 'id': supplier_return.id, 'display_id': supplier_return.business_number, 'status': supplier_return.status, 'return_quantity': supplier_return.return_quantity}
        return answer, [AgentResponseBlock(
            type='record_created', text=answer, record=record,
            actions=[{'id': 'open_quality', 'label': 'Review return', 'href': '/quality'}],
        ).model_dump()], citations

    if intent in {'request_supplier_replacement_proposal', 'prepare_replacement_receipt_proposal'}:
        supplier_return_id = str(facts.get('supplier_return_id') or (envelope.referenced_entity_ids or [''])[0])
        supplier_return = workflows.user_scope_query(db, models.SupplierReturn, user).filter(
            (models.SupplierReturn.id == supplier_return_id) | (models.SupplierReturn.business_number == supplier_return_id)
        ).first()
        if supplier_return is None:
            raise HTTPException(404, 'Supplier return not found')
        action = 'request_supplier_replacement' if intent == 'request_supplier_replacement_proposal' else 'record_replacement_receipt'
        authority = 'purchase_manager' if intent == 'request_supplier_replacement_proposal' else 'store_manager'
        preview = {key: value for key, value in facts.items() if value is not None}
        preview['business_number'] = supplier_return.business_number
        proposal = create_proposal(db, user, ProposalCreateRequest(
            thread_id=thread.id, run_id=run.id, action=action,
            target_entity_type='supplier_returns', target_entity_id=supplier_return.id,
            preview=preview,
            expected_effect='Request supplier replacement through the governed communication queue.' if action == 'request_supplier_replacement' else 'Record replacement arrival and create a mandatory quality reinspection task.',
            required_authority=membership.role if membership.role == ADMIN else authority,
            record_version=supplier_return.version,
        ))
        answer = f'{supplier_return.business_number} is ready for confirmation.'
        return answer, [AgentResponseBlock(
            type='action_proposal', text=answer,
            record={'type': 'supplier_return', 'id': supplier_return.id, 'display_id': supplier_return.business_number, 'status': supplier_return.status, 'proposal_id': proposal.id},
            actions=[{'id': 'confirm_proposal', 'label': 'Confirm', 'proposal_id': proposal.id}, {'id': 'open_quality', 'label': 'Review return', 'href': '/quality'}],
        ).model_dump()], citations

    if intent == 'delegate_task':
        from app import task_service
        assignee_id = str(facts.get('assignee_membership_id') or '')
        outcome = str(facts.get('requested_outcome') or envelope.requested_outcome)
        task = task_service.create_task(db, user, TaskCreateRequest(
            title=outcome[:120], requested_outcome=outcome,
            assignee_membership_id=assignee_id,
            due_at=facts.get('due_at'), priority=str(facts.get('priority') or 'normal'),
            context_entity_type=facts.get('entity_type'), context_entity_id=facts.get('entity_id'),
        ), source_run_id=run.id)
        db.add(models.AgentActionReceipt(
            tenant_id=user.tenant_id, plant_id=user.plant_id, run_id=run.id,
            tool_name='delegate_task', status='succeeded', target_entity_type='task',
            target_entity_id=task.id, result_summary={'task_id': task.id, 'title': task.title},
            executed_by_membership_id=membership.id, started_at=utcnow(), completed_at=utcnow(),
            idempotency_key=f'{correlation_id}:delegate_task',
        ))
        answer = f'Assigned “{task.title}” to the selected employee.'
        record = {'type': 'task', 'id': task.id, 'title': task.title, 'status': task.status}
        return answer, [AgentResponseBlock(type='task_update', text=answer, record=record).model_dump(), AgentResponseBlock(type='action_receipt', text='The assignment was saved.', record=record).model_dump()], citations

    raise HTTPException(status_code=422, detail='This assistant capability is not implemented yet')


def resume_quotation_batch_after_document(db: Session, document_job_id: str) -> bool:
    """Resume a waiting quotation batch after its final document becomes terminal."""
    attachment = db.query(models.AgentMessageAttachment).filter_by(
        document_job_id=document_job_id,
    ).first()
    if attachment is None or attachment.purpose != 'quotation':
        return False
    source_message = db.get(models.AgentMessage, attachment.message_id)
    if source_message is None:
        return False
    thread = db.query(models.AgentThread).filter_by(
        id=source_message.thread_id, tenant_id=attachment.tenant_id,
    ).with_for_update().first()
    if thread is None:
        return False
    state = load_thread_state(thread.context_state)
    if (
        state.active_goal.capability != 'upload_supplier_quotes'
        or state.continuation_status != 'processing'
    ):
        return False
    attachment_refs = state.attachment_refs or [attachment.document_id]
    batch_rows = db.query(models.AgentMessageAttachment).join(
        models.AgentMessage,
        models.AgentMessage.id == models.AgentMessageAttachment.message_id,
    ).filter(
        models.AgentMessage.thread_id == thread.id,
        models.AgentMessageAttachment.tenant_id == attachment.tenant_id,
        models.AgentMessageAttachment.purpose == 'quotation',
        (
            models.AgentMessageAttachment.id.in_(attachment_refs)
            | models.AgentMessageAttachment.document_id.in_(attachment_refs)
        ),
    ).all()
    if not batch_rows or any(
        row.status in {'uploading', 'queued', 'extracting', 'retrying'}
        for row in batch_rows
    ):
        return False
    membership = db.get(models.WorkspaceMembership, thread.membership_id)
    user = db.get(models.User, membership.user_id) if membership else None
    profile = db.get(models.AgentProfile, thread.agent_profile_id)
    if membership is None or user is None or profile is None:
        state.continuation_status = 'failed'
        state.active_goal.status = 'blocked'
        state.blocked_on = 'agent_identity'
        persist_thread_state(thread, state)
        return False

    # Claim the continuation under the thread lock. The adapter replaces this
    # with completed/needs_input before the transaction commits.
    state.continuation_status = 'resolving'
    state.active_goal.status = 'resolving'
    persist_thread_state(thread, state)
    correlation_id = f'AGT-CONT-{secrets.token_hex(10)}'
    intent = IntentEnvelope(
        intent='upload_supplier_quotes',
        requested_outcome='Continue the quotation batch after document extraction.',
        entities=dict(state.draft_fields),
        attachment_ids=[row.document_id for row in batch_rows], confidence=1,
    )
    run = models.AgentRun(
        tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        membership_id=membership.id, agent_profile_id=profile.id,
        state='running', provider='document-continuation',
        model='quotation-continuation@1',
        context_hash=hashlib.sha256(
            json.dumps(intent.model_dump(mode='json'), sort_keys=True).encode()
        ).hexdigest(),
        policy_version=profile.policy_version,
        trace_id=f'trace-{secrets.token_hex(8)}', correlation_id=correlation_id,
        intent='upload_supplier_quotes', requested_outcome=intent.requested_outcome,
    )
    db.add(run)
    db.flush()
    record_run_event(db, run, 'run_resumed', {
        'trigger': 'document_batch_completed',
        'document_job_id': document_job_id,
        'attachment_count': len(batch_rows),
    })
    validate_intent(intent, membership.role)
    answer, blocks, citations = process_intent_envelope(
        db, user, membership, profile, thread, run, intent,
        dict(state.draft_fields), 'document-continuation', [], correlation_id,
    )
    db.flush()
    block_types = {block.get('type') for block in blocks}
    receipt = db.query(models.AgentActionReceipt).filter_by(
        run_id=run.id, status='succeeded',
    ).first()
    run.state = 'completed'
    run.completed_at = utcnow()
    run.output_tokens = max(1, len(answer.split()))
    run.mutation_count = 1 if receipt else 0
    run.termination_reason = (
        'mutation_completed' if receipt else
        'needs_clarification' if 'clarification' in block_types else
        'processing' if 'run_progress' in block_types else
        'blocked' if 'warning' in block_types or 'error' in block_types else
        'completed'
    )
    db.add(models.AgentMessage(
        tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        membership_id=membership.id, agent_profile_id=profile.id,
        message_type='agent', content=answer, content_format='blocks',
        content_blocks=blocks, citations=citations, visibility='private',
        correlation_id=correlation_id,
    ))
    record_run_event(db, run, 'run_completed', {
        'state': run.state, 'termination_reason': run.termination_reason,
        'block_types': sorted(value for value in block_types if value),
    })
    return True


def resume_ready_quotation_batches(db: Session, limit: int = 100) -> int:
    """Recover terminal quotation batches missed by an earlier worker callback."""
    resumed = 0
    threads = db.query(models.AgentThread).filter_by(status='active').order_by(
        models.AgentThread.updated_at.asc(),
    ).limit(limit).all()
    for thread in threads:
        state = load_thread_state(thread.context_state)
        if (
            state.active_goal.capability != 'upload_supplier_quotes'
            or state.continuation_status != 'processing'
        ):
            continue
        attachment = db.query(models.AgentMessageAttachment).join(
            models.AgentMessage,
            models.AgentMessage.id == models.AgentMessageAttachment.message_id,
        ).filter(
            models.AgentMessage.thread_id == thread.id,
            models.AgentMessageAttachment.purpose == 'quotation',
            models.AgentMessageAttachment.document_job_id.is_not(None),
        ).order_by(models.AgentMessageAttachment.updated_at.desc()).first()
        if attachment and resume_quotation_batch_after_document(
            db, attachment.document_job_id,
        ):
            resumed += 1
    return resumed


def _registered_capability_dispatch(*args, **kwargs):
    """Executable adapter entry while capability branches are extracted.

    Registration makes missing adapters fail at startup/test time rather than
    surfacing as a user-facing "not implemented" response. Individual adapters
    continue to call the same canonical services in ``process_intent_envelope``.
    """
    return process_intent_envelope(*args, **kwargs)


for _capability in CAPABILITY_REGISTRY.values():
    register_capability_adapter(_capability.adapter, _registered_capability_dispatch)


def validate_grounded_response(
    db: Session, run: models.AgentRun, answer: str, blocks: list[dict[str, Any]],
    correlation_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Prevent a generated or adapter response from claiming an unreceipted mutation."""
    mutation_blocks = [row for row in blocks if row.get('type') in {'record_created', 'action_receipt'}]
    if mutation_blocks:
        receipts = db.query(models.AgentActionReceipt).filter_by(
            tenant_id=run.tenant_id, run_id=run.id, status='succeeded',
        ).all()
        receipt_targets = {row.target_entity_id for row in receipts}
        claimed_ids = {
            str(row.get('record', {}).get('id'))
            for row in mutation_blocks if isinstance(row.get('record'), dict) and row['record'].get('id')
        }
        if claimed_ids and not claimed_ids.issubset(receipt_targets):
            prior_receipts = db.query(models.AgentActionReceipt).filter(
                models.AgentActionReceipt.tenant_id == run.tenant_id,
                models.AgentActionReceipt.status == 'succeeded',
                models.AgentActionReceipt.target_entity_id.in_(claimed_ids),
            ).all()
            receipt_targets.update(row.target_entity_id for row in prior_receipts)
        if (not receipts and not receipt_targets) or (claimed_ids and not claimed_ids.issubset(receipt_targets)):
            safe = f'The action could not be verified, so no completion is being claimed. Reference {correlation_id}.'
            return safe, [AgentResponseBlock(type='error', text=safe).model_dump()]
    if re.search(r'\b(?:shortly|later I will|will notify you in the future)\b', answer, re.I):
        safe = 'No action was completed. Use an available action when you are ready to continue.'
        return safe, [AgentResponseBlock(type='warning', text=safe).model_dump()]
    return answer, blocks


def run_message(
    db: Session, user: models.User, thread_id: str, payload: AgentMessageRequest
) -> tuple[models.AgentRun, models.AgentMessage]:
    membership = membership_for_user(db, user)
    enforce_agent_run_limits(db, membership)
    profile = assert_agent_available(db, membership)
    thread = thread_for_membership(db, membership, thread_id)
    if (
        thread.thread_type == 'personal'
        and thread.title.strip().casefold() in GENERIC_THREAD_TITLES
    ):
        thread.title = conversation_title(payload.content)
    if payload.selected_context and payload.selected_context.entity_type and payload.selected_context.entity_id:
        from app.agent_resolution import resolve_record
        aliases = {
            'requirement': 'purchase_requirement', 'purchase_requirements': 'purchase_requirement',
            'rfqs': 'rfq', 'quote': 'supplier_quote', 'supplier_quotes': 'supplier_quote',
            'comparison': 'bid_comparison', 'bid_comparisons': 'bid_comparison',
            'negotiation': 'negotiation_round', 'negotiation_rounds': 'negotiation_round',
            'award': 'award_decision', 'award_decisions': 'award_decision',
            'po': 'po_draft', 'po_drafts': 'po_draft',
            'acknowledgement': 'supplier_acknowledgement',
            'asns': 'asn', 'gate_entries': 'gate_entry',
            'receipt': 'store_receipt', 'store_receipts': 'store_receipt',
            'inspection': 'inspection_result', 'inspection_results': 'inspection_result',
            'cases': 'case',
        }
        canonical_type = aliases.get(
            payload.selected_context.entity_type, payload.selected_context.entity_type,
        )
        selected = resolve_record(
            db, user, canonical_type, payload.selected_context.entity_id,
        )
        state = select_context(
            load_thread_state(thread.context_state),
            entity_type=canonical_type, entity_id=selected.id,
            business_number=getattr(selected, 'business_number', None), source='page',
        )
        persist_thread_state(thread, state)
    attachments = []
    for document_id in dict.fromkeys(payload.attachment_ids):
        document = db.query(models.Document).filter_by(
            id=document_id, tenant_id=user.tenant_id, plant_id=user.plant_id,
        ).first()
        if document is None:
            raise HTTPException(status_code=404, detail=f'Attachment {document_id} is unavailable')
        if document.uploaded_by_user_id not in (None, user.id) and membership.role != ADMIN:
            raise HTTPException(status_code=403, detail='Attachment is outside your document scope')
        attachments.append({
            'document_id': document.id, 'filename': document.filename,
            'content_type': document.content_type, 'validation_status': document.status,
            'linked_entity_type': document.linked_entity_type, 'linked_entity_id': document.linked_entity_id,
        })
    if attachments:
        state = attach_documents(load_thread_state(thread.context_state), attachments)
        persist_thread_state(thread, state)
    correlation_id = f'AGT-{secrets.token_hex(10)}'
    envelope = build_context_envelope(db, membership, thread, correlation_id)
    context, citations = context_payload(db, envelope)
    context['allowed_capability_ids'] = [
        row.capability_id for row in capabilities_for_role(membership.role)
    ]
    typed_state = load_thread_state(thread.context_state)
    context['thread_state'] = typed_state.model_dump(mode='json', exclude_none=True)
    parsed_entities = extract_procurement_entities(payload.content)
    parsed_entities.update(catalog_entities_from_message(db, user, payload.content))
    context['entity_candidates'] = material_candidates(db, user, parsed_entities)
    context['attachments'] = attachments
    context_bytes = len(json.dumps(context, default=str).encode())
    if context_bytes > get_settings().agent_max_context_bytes:
        raise HTTPException(
            status_code=413,
            detail='Authorized agent context exceeds the configured safety budget.',
        )
    context_hash = hashlib.sha256(
        json.dumps(envelope.model_dump(), sort_keys=True, default=str).encode()
    ).hexdigest()
    user_message = models.AgentMessage(
        tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        membership_id=membership.id, message_type='user', content=payload.content,
        visibility='private', correlation_id=correlation_id,
    )
    run = models.AgentRun(
        tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        membership_id=membership.id, agent_profile_id=profile.id, state='running',
        provider=profile.provider, model=profile.model_profile, context_hash=context_hash,
        policy_version=profile.policy_version, trace_id=f'trace-{secrets.token_hex(8)}',
        correlation_id=correlation_id,
    )
    db.add_all([user_message, run])
    db.flush()
    for file_order, attachment in enumerate(attachments):
        job = db.query(models.DocumentJob).filter_by(
            document_id=attachment['document_id'],
        ).order_by(models.DocumentJob.created_at.desc()).first()
        status = {
            'quarantined': 'queued', 'validating': 'extracting',
            'validated': 'needs_review', 'verified': 'linked',
            'failed': 'failed', 'needs_manual_entry': 'needs_review',
        }.get(attachment['validation_status'], attachment['validation_status'])
        db.add(models.AgentMessageAttachment(
            tenant_id=user.tenant_id, plant_id=user.plant_id,
            message_id=user_message.id, document_id=attachment['document_id'],
            file_order=file_order,
            purpose='quotation' if 'quot' in payload.content.casefold() else 'evidence',
            status=status, document_job_id=job.id if job else None,
        ))
    db.flush()
    # The model must see persisted attachment identities on continuation turns;
    # the current request normally has an empty attachment_ids list.
    live_provider_attachments = db.query(models.AgentMessageAttachment).join(
        models.AgentMessage,
        models.AgentMessage.id == models.AgentMessageAttachment.message_id,
    ).filter(
        models.AgentMessage.thread_id == thread.id,
        models.AgentMessageAttachment.tenant_id == user.tenant_id,
    ).order_by(
        models.AgentMessage.created_at.asc(),
        models.AgentMessageAttachment.file_order.asc(),
    ).all()
    attachment_refs = set(load_thread_state(thread.context_state).attachment_refs)
    context['attachments'] = [{
        **record_dict(row),
        'filename': getattr(db.get(models.Document, row.document_id), 'filename', 'Attachment'),
        'content_type': getattr(db.get(models.Document, row.document_id), 'content_type', None),
        'validation_status': getattr(db.get(models.Document, row.document_id), 'status', None),
    } for row in live_provider_attachments if (
        not attachment_refs
        or row.id in attachment_refs
        or row.document_id in attachment_refs
    )]
    history = thread_history(db, thread)
    run.active_context = {
        'thread_type': thread.thread_type,
        'work_item_id': thread.work_item_id,
        'objective_id': thread.objective_id,
        'allowed_entity_ids': envelope.allowed_entity_ids,
    }
    record_run_event(db, run, 'run_started', {
        'provider': run.provider, 'model': run.model,
        'thread_id': thread.id,
    })
    record_run_event(db, run, 'context_resolved', {
        'role': membership.role,
        'source_count': len(citations),
        'tool_count': len(envelope.read_tools + envelope.proposal_tools),
    })
    record_run_checkpoint(db, run, 'resolve_identity_and_context', {
        'membership_id': membership.id,
        'role': membership.role,
        'thread_id': thread.id,
        'allowed_entity_ids': envelope.allowed_entity_ids,
        'source_ids': [item['id'] for item in citations],
    })
    current_facts = dict(typed_state.draft_fields)
    try:
        if payload.requested_capability:
            # Buttons carry a capability id rather than relying on the model to
            # reinterpret a label such as "Request new material".
            provider = 'direct-action'
            model = 'server-action@1'
            provider_error = None
            intent = IntentEnvelope(
                intent=payload.requested_capability,
                requested_outcome=payload.content or payload.requested_capability.replace('_', ' '),
                entities={}, attachment_ids=payload.attachment_ids, confidence=1,
            )
            model_intent_rejected = False
        else:
            provider_result, provider, model, provider_error = provider_response(
                profile, payload.content, context, history, current_facts
            )
            intent = decision_as_intent(provider_result, payload.content, payload.attachment_ids)
            intent, model_intent_rejected = safe_provider_intent(
                intent, payload.content, current_facts, membership.role,
            )
            deterministic = deterministic_intent(payload.content, current_facts, payload.attachment_ids)
            # A provider may occasionally answer conversationally instead of
            # selecting the quotation tool (especially near its time budget).
            # Persisted attachments plus the employee's explicit upload action
            # are authoritative workflow input: do not let a generic answer
            # bypass extraction, continuation, and receipt handling.
            if (
                deterministic.intent == 'upload_supplier_quotes'
                and intent.intent != 'upload_supplier_quotes'
            ):
                intent = deterministic.model_copy(update={
                    'entities': {**intent.entities, **deterministic.entities},
                    'confidence': 1.0,
                })
                provider_error = provider_error or 'QuotationToolSelectionCorrected'
            if deterministic.intent == 'create_purchase_requirement' and intent.intent in {
                'search_approved_material', 'answer_work_context',
            }:
                intent = intent.model_copy(update={
                    'intent': 'create_purchase_requirement',
                    'requested_outcome': payload.content,
                })
        # Capability buttons and model-selected tools share the same grounded
        # argument path. Explicit facts in the latest employee message win over
        # an omitted or paraphrased model field.
        intent = intent.model_copy(update={
            # Deterministic parsing fills omissions; a schema-constrained
            # provider's more precise normalized value wins when both exist.
            'entities': {**parsed_entities, **intent.entities},
        })
        if model_intent_rejected:
            provider_error = provider_error or 'ModelIntentRejected'
        pending = dict(load_thread_state(thread.context_state).pending_confirmation or {})
        if pending and re.search(r'\b(confirm|yes|proceed|go ahead)\b', payload.content, re.I):
            intent = IntentEnvelope(
                intent='create_material_master_request',
                requested_outcome='Confirm the pending material-master request.',
                entities={}, confidence=1, requires_confirmation=True,
            )
        validate_intent(intent, membership.role)
        facts = merge_intent_entities(thread, intent, user_message.id)
        run.intent = intent.intent
        run.requested_outcome = intent.requested_outcome[:2000]
        record_run_event(db, run, 'intent_resolved', {
            'intent': intent.intent,
            'confidence': intent.confidence,
        })
        record_run_checkpoint(db, run, 'validate_result', {
            'intent': intent.intent,
            'requires_confirmation': intent.requires_confirmation,
            'facts': facts,
            'provider': provider,
            'model': model,
        })
        first_request = True
        runtime_provider = provider
        runtime_model = model
        runtime_provider_error = provider_error

        def decide_runtime(runtime_state: dict[str, Any]) -> dict[str, Any]:
            nonlocal first_request, runtime_provider, runtime_model, runtime_provider_error
            if first_request:
                first_request = False
                selected = intent
            elif runtime_provider != 'groq':
                observations = runtime_state.get('observations') or []
                return {
                    'type': 'final',
                    'content': observations[-1].get('business_summary', '') if observations else '',
                }
            else:
                prior_observations = runtime_state.get('observations') or []
                prior_block_types = {
                    item.get('block_type')
                    for observation in prior_observations
                    for item in (observation.get('observations') or [])
                }
                if 'action_receipt' in prior_block_types and len(prior_observations) > 1:
                    return {
                        'type': 'final',
                        'content': prior_observations[-1].get('business_summary', ''),
                    }
                followup_context = {
                    **context,
                    'thread_state': load_thread_state(thread.context_state).model_dump(
                        mode='json', exclude_none=True,
                    ),
                    'runtime_observations': [
                        {
                            key: value for key, value in observation.items()
                            if not key.startswith('_')
                        }
                        for observation in (runtime_state.get('observations') or [])
                    ],
                }
                selected, next_provider, next_model, next_error = provider_response(
                    profile, payload.content, followup_context, history,
                    dict(load_thread_state(thread.context_state).draft_fields),
                )
                runtime_provider = next_provider
                runtime_model = next_model
                runtime_provider_error = runtime_provider_error or next_error
                # A consequential adapter may use a legacy-named receipt tool
                # while the capability has a newer canonical id. Give the
                # provider one read-only synthesis turn over that grounded tool
                # result, but never execute a second mutation from the follow-up.
                if 'action_receipt' in prior_block_types:
                    final_answer = getattr(selected, 'answer', None)
                    return {
                        'type': 'final',
                        'content': final_answer or prior_observations[-1].get('business_summary', ''),
                    }
                selected = decision_as_intent(selected, payload.content, payload.attachment_ids)
                selected, rejected = safe_provider_intent(
                    selected, payload.content,
                    dict(load_thread_state(thread.context_state).draft_fields), membership.role,
                )
                if rejected:
                    runtime_provider_error = runtime_provider_error or 'ModelIntentRejected'
                final_text = selected.entities.get('_runtime_final')
                if final_text is not None:
                    return {'type': 'final', 'content': str(final_text)}
            return {'type': 'tool', 'tool': selected.intent, 'envelope': selected.model_dump()}

        def execute_runtime(request: dict[str, Any]) -> dict[str, Any]:
            nonlocal citations
            selected = IntentEnvelope.model_validate(request['envelope'])
            selected_capability = validate_intent(selected, membership.role)
            selected_facts = merge_intent_entities(thread, selected, user_message.id)
            run.intent = selected.intent
            run.requested_outcome = selected.requested_outcome[:2000]
            from app.policy_decision import PolicyDecisionService
            policy_decision, _policy_record = PolicyDecisionService(db).decide(
                actor=membership, capability_id=selected_capability.capability_id,
                resource_type=selected_capability.resource_type,
                resource_id=str(selected_facts.get('entity_id') or selected_facts.get('requirement_id') or '') or None,
                context={
                    'tenant_id': user.tenant_id, 'plant_id': user.plant_id,
                    'workflow_stage': selected_facts.get('workflow_stage'),
                    'spend': selected_facts.get('spend'), 'risk': selected_facts.get('risk'),
                    'autonomy_tier': selected_capability.autonomy_ceiling,
                    'reversible': selected_capability.reversible,
                    'external_effect': selected_capability.effect_type == 'consequential',
                },
                read_only=selected_capability.effect_type == 'read', correlation_id=correlation_id,
            )
            if get_settings().opa_mode == 'enforce' and not policy_decision.allow:
                raise HTTPException(status_code=403, detail=f'Policy denied this action: {policy_decision.reason_code}')
            if get_settings().opa_mode == 'enforce' and policy_decision.requires_confirmation and not selected_capability.controlled:
                raise HTTPException(status_code=409, detail='Policy requires a confirmation-bound proposal')
            try:
                selected_answer, selected_blocks, citations = execute_capability_adapter(
                    selected_capability,
                    db, user, membership, profile, thread, run, selected, selected_facts,
                    runtime_provider, citations, correlation_id,
                )
                AGENT_TOOL_CALLS.labels(selected.intent, "succeeded").inc()
            except Exception:
                AGENT_TOOL_CALLS.labels(selected.intent, "failed").inc()
                raise
            # The session intentionally disables autoflush. Grounding and
            # receipt validation must observe adapter writes from this turn.
            db.flush()
            receipt = db.query(models.AgentActionReceipt).filter_by(
                run_id=run.id, tool_name=selected.intent, status='succeeded',
            ).order_by(models.AgentActionReceipt.created_at.desc()).first()
            proposal = db.query(models.AgentProposal).filter_by(
                run_id=run.id, confirmation_state='pending',
            ).order_by(models.AgentProposal.created_at.desc()).first()
            block_types = {block.get('type') for block in selected_blocks}
            if proposal:
                result_status = 'proposal_created'
            elif receipt:
                result_status = 'completed'
            elif 'action_receipt' in block_types:
                # Continue once for grounded natural-language synthesis. The
                # decision step above makes this continuation read-only.
                result_status = 'observed'
            elif 'clarification' in block_types or 'missing_information' in block_types:
                result_status = 'needs_clarification'
            elif 'run_progress' in block_types:
                result_status = 'processing'
            elif 'error' in block_types:
                result_status = 'failed'
            elif 'warning' in block_types or 'role_handoff' in block_types:
                result_status = 'blocked'
            else:
                result_status = 'observed'
            result = ToolResult(
                status=result_status,
                business_summary=selected_answer,
                records=[],
                observations=[
                    {'block_type': block.get('type'), 'text': block.get('text')}
                    for block in selected_blocks
                ],
                missing_fields=[
                    {'name': item}
                    for block in selected_blocks
                    for item in (block.get('items') or [])
                ] if result_status == 'needs_clarification' else [],
                proposal=record_dict(proposal) if proposal else None,
                receipt=record_dict(receipt) if receipt else None,
            ).model_dump(mode='json', exclude_none=True)
            return {
                'tool': selected.intent,
                **result,
                'candidates': [
                    choice
                    for block in selected_blocks
                    for field in (block.get('fields') or [])
                    for choice in (field.get('choices') or [])
                ],
                '_result': (selected_answer, selected_blocks),
            }

        runtime = run_bounded_tool_loop(
            {'messages': history, 'observations': []},
            decide=decide_runtime,
            execute=execute_runtime,
            tool_categories={
                capability_id: capability_category(capability_id)
                for capability_id in CAPABILITY_REGISTRY
            },
            max_decisions=get_settings().agent_max_graph_steps,
            max_reads=get_settings().agent_max_tool_calls,
            max_tool_calls=get_settings().agent_max_tool_calls,
            max_candidates=5,
            max_seconds=get_settings().agent_max_run_seconds,
        )
        observations = runtime.get('observations') or []
        if not observations or '_result' not in observations[-1]:
            raise HTTPException(status_code=422, detail='The assistant could not resolve this request safely')
        answer, blocks = observations[-1]['_result']
        if runtime.get('final', {}).get('content'):
            answer = str(runtime['final']['content'])
        provider, model, provider_error = (
            runtime_provider, runtime_model, runtime_provider_error,
        )
        run.step_count = int(runtime.get('decision_count') or 0)
        run.read_tool_count = int(runtime.get('read_count') or 0)
        run.mutation_count = int(runtime.get('mutation_count') or 0)
        run.termination_reason = runtime.get('termination_reason')
        answer = compose_grounded_answer(profile, payload.content, answer, blocks, provider)
        answer = preserve_business_identifiers(answer, blocks)
        # Keep the first visible business card aligned with the conversational
        # answer while preserving record/action fields generated by the server.
        if blocks and blocks[0].get('type') not in {'error', 'warning'}:
            blocks[0]['text'] = answer
        answer, blocks = validate_grounded_response(
            db, run, answer, blocks, correlation_id,
        )
        run.provider = provider
        run.model = model
        run.error = f'Degraded provider: {provider_error}' if provider_error else None
        run.output_tokens = max(1, len(answer.split()))
        run.input_tokens = int(context.get('_provider_request_tokens') or max(
            1, len(json.dumps({'history': history, 'context': context}, default=str).split()),
        ))
        run.state = 'completed'
        run.step_count = max(
            run.step_count or 0,
            db.query(models.AgentEvent).filter_by(run_id=run.id).count(),
        )
        persisted_mutations = db.query(models.AgentActionReceipt).filter_by(
            run_id=run.id, status='succeeded',
        ).count()
        run.mutation_count = persisted_mutations
        proposal_count = db.query(models.AgentProposal).filter_by(run_id=run.id, confirmation_state='pending').count()
        if persisted_mutations:
            run.termination_reason = 'mutation_completed'
        elif proposal_count:
            run.termination_reason = 'proposal_created'
        # Adapters may update an in-memory compatibility shape while they are
        # being migrated.  The live request boundary always validates and
        # persists the single canonical V2 representation.
        persist_thread_state(thread, load_thread_state(thread.context_state))
        run.completed_at = utcnow()
        run.latency_ms = max(0, int((run.completed_at - run.created_at).total_seconds() * 1000))
        AGENT_RUNS.labels(provider, "completed").inc()
        AGENT_RUN_LATENCY.labels(provider).observe(run.latency_ms / 1000)
        record_run_event(db, run, 'run_completed', {
            'state': run.state, 'provider': provider, 'model': model,
            'block_types': [block.get('type') for block in blocks],
        })
        record_run_checkpoint(db, run, 'persist_summary_and_metrics', {
            'state': run.state,
            'provider': provider,
            'model': model,
            'input_tokens': run.input_tokens,
            'output_tokens': run.output_tokens,
            'block_types': [block.get('type') for block in blocks],
        })
        message = models.AgentMessage(
            tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
            membership_id=membership.id, agent_profile_id=profile.id, message_type='agent',
            content=answer, content_format='blocks', content_blocks=blocks,
            citations=citations, visibility='private', correlation_id=correlation_id,
        )
        db.add(message)
        workflows.create_audit(
            db, user.tenant_id, user.plant_id, profile.display_name, 'agent.run.completed',
            'agent_run', run.id, actor_user_id=user.id,
            meta={
                'membership_id': membership.id, 'context_hash': context_hash,
                'policy_version': profile.policy_version, 'provider': provider,
                'model': model, 'provider_error': provider_error,
                'source_ids': [item['id'] for item in citations],
            },
        )
        return run, message
    except HTTPException as exc:
        if exc.status_code == 503:
            logger.warning(
                'Agent run paused; correlation_id=%s detail=%s',
                correlation_id, exc.detail,
            )
            run.state = 'paused_provider'
            run.error = 'All workspace-approved model providers are unavailable'
            run.error_code = 'all_providers_unavailable'
            run.completed_at = None
            text = (
                'I saved your message and attachments, but the assistant service is temporarily '
                'unavailable. Retry this request, or continue in the procurement workbench.'
            )
            message = models.AgentMessage(
                tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
                membership_id=membership.id, agent_profile_id=profile.id, message_type='agent',
                content=text, content_format='blocks',
                content_blocks=[{
                    'type': 'warning', 'text': text,
                    'actions': [
                        {'id': 'retry_run', 'label': 'Retry'},
                        {'id': 'continue_manually', 'label': 'Open workbench', 'href': '/procurement'},
                    ],
                }],
                citations=[], visibility='private', correlation_id=correlation_id,
            )
            db.add(message)
            record_run_event(db, run, 'run_paused', {'error_code': run.error_code})
            return run, message
        run.state = 'failed'
        run.error = 'Provider or policy unavailable'
        run.error_code = 'provider_or_policy_unavailable'
        run.completed_at = utcnow()
        AGENT_RUNS.labels(run.provider, "failed").inc()
        record_run_event(db, run, 'run_failed', {'error_code': run.error_code})
        record_run_checkpoint(
            db, run, 'run_failed', {'error_code': run.error_code}, status='failed',
        )
        raise
    except Exception as exc:
        logger.exception('Agent run failed; correlation_id=%s', correlation_id)
        run.state = 'failed'
        run.error = type(exc).__name__
        run.error_code = type(exc).__name__
        run.completed_at = utcnow()
        AGENT_RUNS.labels(run.provider, "failed").inc()
        record_run_event(db, run, 'run_failed', {'error_code': run.error_code})
        record_run_checkpoint(
            db, run, 'run_failed', {'error_code': run.error_code}, status='failed',
        )
        raise HTTPException(status_code=500, detail=f'Agent run failed. Reference {correlation_id}') from exc


def create_objective(db: Session, user: models.User, payload: ObjectiveCreateRequest) -> models.Objective:
    membership = membership_for_user(db, user)
    if membership.role != PLANT_MANAGER:
        raise HTTPException(status_code=403, detail="Only the Plant Manager can create a plant objective")
    sender_profile = assert_agent_available(db, membership)
    descendants = reporting_descendants(db, membership)
    query = db.query(models.WorkspaceMembership).filter(
        models.WorkspaceMembership.tenant_id == user.tenant_id,
        models.WorkspaceMembership.default_plant_id == user.plant_id,
        models.WorkspaceMembership.role == PURCHASE_EXECUTIVE,
        models.WorkspaceMembership.status == "active",
    )
    assignee = query.filter(
        models.WorkspaceMembership.id == payload.assignee_membership_id
    ).first() if payload.assignee_membership_id else query.first()
    if assignee is None or assignee.id not in descendants:
        raise HTTPException(status_code=422, detail="Choose a Purchase Executive in the Plant Manager reporting tree")
    recipient_profile = profile_for_membership(db, assignee)
    objective = models.Objective(
        tenant_id=user.tenant_id, plant_id=user.plant_id, title=f"Procure {payload.material}",
        material=payload.material, quantity=payload.quantity, uom=payload.uom.upper(),
        need_by_date=payload.need_by_date, reason=payload.reason, constraints=payload.constraints,
        owner_membership_id=membership.id, created_by_membership_id=membership.id, state="active",
    )
    db.add(objective)
    db.flush()
    try:
        due_at = datetime.fromisoformat(payload.need_by_date.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="need_by_date must be an ISO date") from exc
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    task = models.Task(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        title=f"Clarify requirement and prepare RFQ for {payload.material}",
        owner_role=PURCHASE_EXECUTIVE, owner_user_id=assignee.user_id,
        owner_membership_id=assignee.id, due_at=due_at, status="open", severity="action",
        entity_type="objectives", entity_id=objective.id, objective_id=objective.id,
        creator_membership_id=membership.id, assignment_source="manager_agent",
        acceptance_status="assigned",
    )
    db.add(task)
    db.flush()
    delegation = models.AgentDelegation(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        sender_agent_profile_id=sender_profile.id, sender_membership_id=membership.id,
        recipient_agent_profile_id=recipient_profile.id, recipient_membership_id=assignee.id,
        objective_id=objective.id, work_item_id=task.id,
        requested_outcome="Clarify the material need and prepare an RFQ draft for human review.",
        context_packet={
            "objective_id": objective.id, "material": objective.material,
            "quantity": objective.quantity, "uom": objective.uom,
            "need_by_date": objective.need_by_date, "reason": objective.reason,
            "constraints": objective.constraints,
            "allowed_entity_ids": {"objectives": [objective.id], "tasks": [task.id]},
        },
        due_at=due_at, status="pending", depth=1,
    )
    db.add(delegation)
    db.flush()
    task.delegation_id = delegation.id
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, sender_profile.display_name,
        "agent.objective.delegated", "objective", objective.id, actor_user_id=user.id,
        meta={"sender_membership_id": membership.id, "recipient_membership_id": assignee.id,
              "task_id": task.id, "delegation_id": delegation.id,
              "automatic_effect": "low_risk_assignment"},
    )
    return objective


def create_delegation(
    db: Session, user: models.User, payload: DelegationCreateRequest
) -> models.AgentDelegation:
    sender = membership_for_user(db, user)
    sender_profile = assert_agent_available(db, sender)
    recipient = db.get(models.WorkspaceMembership, payload.recipient_membership_id)
    if recipient is None or recipient.tenant_id != sender.tenant_id or recipient.status != "active":
        raise HTTPException(status_code=404, detail="Recipient membership not found")
    descendants = reporting_descendants(db, sender)
    if payload.kind == "assignment" and recipient.id not in descendants:
        raise HTTPException(status_code=403, detail="Agents can assign work only down the reporting hierarchy")
    if payload.kind == "collaboration_request" and recipient.id == sender.id:
        raise HTTPException(status_code=422, detail="Choose another employee for collaboration")
    if payload.work_item_id:
        task_for_membership(db, sender, payload.work_item_id)
    depth = 1
    if payload.objective_id:
        parent = db.query(models.AgentDelegation).filter_by(
            objective_id=payload.objective_id, recipient_membership_id=sender.id
        ).order_by(models.AgentDelegation.created_at.desc()).first()
        depth = parent.depth + 1 if parent else 1
    if depth > get_settings().agent_max_delegation_depth:
        raise HTTPException(status_code=409, detail="Maximum delegation depth reached; escalate to the human manager")
    recipient_profile = profile_for_membership(db, recipient)
    delegation = models.AgentDelegation(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        sender_agent_profile_id=sender_profile.id, sender_membership_id=sender.id,
        recipient_agent_profile_id=recipient_profile.id, recipient_membership_id=recipient.id,
        objective_id=payload.objective_id, work_item_id=payload.work_item_id,
        requested_outcome=payload.requested_outcome,
        context_packet={"kind": payload.kind, "objective_id": payload.objective_id,
                        "work_item_id": payload.work_item_id, "constraints": payload.constraints},
        due_at=payload.due_at, status="pending", depth=depth,
        contract_kind=payload.kind,
        expected_deliverable=payload.expected_deliverable or payload.requested_outcome,
        required_evidence=payload.required_evidence,
        constraints=payload.constraints,
        accountability_membership_id=recipient.id if payload.kind == "assignment" else sender.id,
        acceptance_status="pending",
    )
    db.add(delegation)
    db.flush()
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, sender_profile.display_name,
        "agent.delegation.created", "agent_delegation", delegation.id, actor_user_id=user.id,
        meta={"kind": payload.kind, "recipient_membership_id": recipient.id, "depth": depth},
    )
    return delegation


def respond_to_delegation(
    db: Session, user: models.User, delegation_id: str, payload: DelegationResponseRequest
) -> models.AgentDelegation:
    membership = membership_for_user(db, user)
    delegation = db.query(models.AgentDelegation).filter_by(
        id=delegation_id, tenant_id=user.tenant_id, plant_id=user.plant_id
    ).first()
    if delegation is None:
        raise HTTPException(status_code=404, detail="Delegation not found")
    if delegation.recipient_membership_id != membership.id:
        raise HTTPException(status_code=403, detail="Only the recipient can update this delegation")
    delegation.status = payload.status
    if payload.status in {"accepted", "in_progress"}:
        delegation.acceptance_status = "accepted"
        delegation.accepted_at = delegation.accepted_at or utcnow()
    elif payload.status == "declined":
        delegation.acceptance_status = "declined"
    delegation.response = {
        "summary": payload.summary,
        "commitment_at": payload.commitment_at.isoformat() if payload.commitment_at else None,
        "blocker": payload.blocker,
        "updated_at": utcnow().isoformat(),
    }
    task = db.get(models.Task, delegation.work_item_id) if delegation.work_item_id else None
    if task and task.owner_membership_id == membership.id:
        if payload.status in {"accepted", "in_progress"}:
            task.acceptance_status = payload.status
            task.accepted_at = task.accepted_at or utcnow()
        elif payload.status == "completed":
            task.status = "completed"
            task.completed_at = utcnow()
        if payload.commitment_at:
            active_commitment = db.query(models.Commitment).filter_by(
                task_id=task.id, owner_membership_id=membership.id, status="active",
            ).order_by(models.Commitment.revision.desc()).first()
            if active_commitment is None or active_commitment.promised_at != payload.commitment_at:
                if active_commitment:
                    active_commitment.status = "revised"
                durable_objective = db.get(models.ProcurementCycleObjective, task.objective_id) if task.objective_id else None
                db.add(models.Commitment(
                    tenant_id=user.tenant_id, plant_id=user.plant_id, task_id=task.id,
                    objective_id=durable_objective.id if durable_objective else None,
                    commitment_type="employee", owner_membership_id=membership.id,
                    promised_at=payload.commitment_at,
                    deliverable=delegation.expected_deliverable or delegation.requested_outcome,
                    revision=(active_commitment.revision + 1) if active_commitment else 1,
                    revision_reason="Updated through delegation response" if active_commitment else None,
                    supersedes_commitment_id=active_commitment.id if active_commitment else None,
                ))
    return delegation


def create_proposal(
    db: Session, user: models.User, payload: ProposalCreateRequest
) -> models.AgentProposal:
    membership = membership_for_user(db, user)
    profile = assert_agent_available(db, membership)
    thread = thread_for_membership(db, membership, payload.thread_id)
    expected_entity, expected_role = CONTROLLED_ACTIONS[payload.action]
    if expected_role == 'comparison_approver':
        allowed_roles = {'plant_manager', PURCHASE_EXECUTIVE}
    elif expected_role == 'supplier_followup_owner':
        allowed_roles = {PURCHASE_EXECUTIVE, 'purchase_manager', ADMIN}
    else:
        allowed_roles = {expected_role, ADMIN}
    if payload.target_entity_type != expected_entity or payload.required_authority not in allowed_roles:
        raise HTTPException(status_code=422, detail="Proposal authority or entity type does not match the controlled action")
    if membership.role not in allowed_roles or payload.required_authority != membership.role:
        raise HTTPException(status_code=403, detail="This agent cannot prepare a proposal outside its employee's role")
    proposal = models.AgentProposal(
        tenant_id=user.tenant_id, plant_id=user.plant_id, thread_id=thread.id,
        run_id=payload.run_id, agent_profile_id=profile.id, owner_membership_id=membership.id,
        action=payload.action, target_entity_type=payload.target_entity_type,
        target_entity_id=payload.target_entity_id, preview=payload.preview,
        expected_effect=payload.expected_effect, required_authority=payload.required_authority,
        record_version=payload.record_version, confirmation_state="pending",
        expires_at=utcnow() + timedelta(hours=24),
        action_version='1',
        risk_class='R4' if payload.action in {'publish_rfq', 'dispatch_outbox'} else 'R5',
        required_capability=payload.action,
        idempotency_key=hashlib.sha256(
            f'{payload.run_id}:{payload.action}:{payload.target_entity_id}:{payload.record_version}'.encode()
        ).hexdigest(),
    )
    db.add(proposal)
    db.flush()
    typed_state = load_thread_state(thread.context_state)
    typed_state.pending_proposal_id = proposal.id
    typed_state.updated_at = utcnow()
    persist_thread_state(thread, typed_state)
    if proposal.run_id:
        run = db.get(models.AgentRun, proposal.run_id)
        if run and run.membership_id == membership.id:
            run.state = 'awaiting_approval'
            record_run_event(db, run, 'proposal_ready', {
                'proposal_id': proposal.id,
                'action': proposal.action,
                'risk_class': proposal.risk_class,
            })
            record_run_event(db, run, 'awaiting_approval', {
                'proposal_id': proposal.id,
                'required_authority': proposal.required_authority,
            })
            record_run_checkpoint(db, run, 'human_interrupt', {
                'proposal_id': proposal.id,
                'action': proposal.action,
                'risk_class': proposal.risk_class,
                'required_authority': proposal.required_authority,
            }, status='interrupted')
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, profile.display_name, "agent.proposal.created",
        "agent_proposal", proposal.id, actor_user_id=user.id,
        meta={"action": proposal.action, "target_entity_id": proposal.target_entity_id},
    )
    return proposal


def confirm_proposal(db: Session, user: models.User, proposal_id: str) -> models.AgentProposal:
    membership = membership_for_user(db, user)
    proposal = db.query(models.AgentProposal).filter_by(
        id=proposal_id, tenant_id=user.tenant_id, plant_id=user.plant_id
    ).first()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.owner_membership_id != membership.id or proposal.required_authority != membership.role:
        raise HTTPException(status_code=403, detail="Only the authorized human owner can confirm this proposal")
    if proposal.confirmation_state != "pending" or proposal.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(status_code=409, detail="Proposal is no longer available for confirmation")
    target_models = {
        "rfqs": models.RFQ, "bid_comparisons": models.BidComparison,
        "comparison_records": models.BidComparison, "po_drafts": models.PODraft,
        "asns": models.ASN, "cases": models.Case, "supplier_quotes": models.SupplierQuote,
        "store_receipts": models.StoreReceipt, "inspection_results": models.InspectionResult,
        "supplier_returns": models.SupplierReturn, "supplier_certificates": models.SupplierCertificate,
        "integration_import_batches": models.IntegrationImportBatch,
        "award_decisions": models.AwardDecision, "negotiation_rounds": models.NegotiationRound,
        "outbox_events": models.IntegrationOutboxEvent, "invoice_match_results": models.InvoiceMatchResult,
        "purchase_requirements": models.PurchaseRequirement,
    }
    target_model = target_models.get(proposal.target_entity_type)
    target = db.query(target_model).filter_by(id=proposal.target_entity_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first() if target_model else None
    if target_model and target is None:
        raise HTTPException(status_code=404, detail="Proposal target is no longer available")
    if target is not None and proposal.record_version is not None and target.version != proposal.record_version:
        raise HTTPException(status_code=412, detail="Proposal target changed after preparation; prepare a fresh proposal")
    from app.policy_decision import PolicyDecisionService
    policy, _policy_record = PolicyDecisionService(db).decide(
        actor=membership, capability_id=proposal.required_capability or proposal.action,
        resource_type=proposal.target_entity_type, resource_id=proposal.target_entity_id,
        context={"tenant_id": user.tenant_id, "plant_id": user.plant_id,
                 "resource_version": getattr(target, "version", None), "risk": proposal.risk_class,
                 "autonomy_tier": 4, "reversible": False, "external_effect": True},
        read_only=False, correlation_id=(db.get(models.AgentRun, proposal.run_id).correlation_id if proposal.run_id and db.get(models.AgentRun, proposal.run_id) else f'proposal:{proposal.id}'),
    )
    if get_settings().opa_mode == 'enforce' and not policy.allow:
        raise HTTPException(status_code=403, detail=f'Policy denied confirmation: {policy.reason_code}')
    action_map = {
        "publish_rfq": lambda: workflows.publish_rfq(db, user, proposal.target_entity_id),
        "submit_comparison": lambda: __import__(
            'app.procurement_v2', fromlist=['submit_comparison']
        ).submit_comparison(db, user, proposal.target_entity_id, str(proposal.preview.get('rationale') or 'Recommendation reviewed')),
        "decide_comparison": lambda: __import__(
            'app.procurement_v2', fromlist=['decide_comparison']
        ).decide_comparison(
            db, user, proposal.target_entity_id,
            'reject' if proposal.preview.get('decision') == 'request_changes' else str(proposal.preview.get('decision')),
            str(proposal.preview.get('rationale') or 'Decision confirmed'),
        ),
        "record_gate_entry": lambda: workflows.record_gate_entry(
            db, user, proposal.target_entity_id,
            str(proposal.preview.get('asn_id') or '') or None,
            str(proposal.preview.get('vehicle_number') or ''),
            str(proposal.preview.get('supplier_challan') or ''),
            int(proposal.preview.get('packages_count') or 0),
            str(proposal.preview.get('arrival_notes') or ''),
        ),
        "record_store_receipt": lambda: workflows.record_receipt(
            db, user, proposal.target_entity_id,
            float(proposal.preview.get('received_quantity') or 0),
            float(proposal.preview.get('damaged_quantity') or 0),
            str(proposal.preview.get('observed_item_code') or ''),
            str(proposal.preview.get('certificate_status') or 'received'),
            str(proposal.preview.get('exception_notes') or ''),
            bool(proposal.preview.get('production_impact') or False),
        ),
        "confirm_purchase_order": lambda: __import__(
            'app.procurement_v2', fromlist=['confirm_split_purchase_orders']
        ).confirm_split_purchase_orders(
            db, user, proposal.target_entity_id, list(proposal.preview.get('allocations') or []),
        ),
        "approve_negotiation": lambda: workflows.approve_negotiation(db, user, proposal.target_entity_id),
        "approve_award": lambda: workflows.approve_award(db, user, proposal.target_entity_id),
        "approve_po_draft": lambda: workflows.approve_po_draft(db, user, proposal.target_entity_id),
        "prepare_po_supplier_email": lambda: __import__(
            'app.procurement_v2', fromlist=['prepare_po_supplier_email']
        ).prepare_po_supplier_email(db, user, proposal.target_entity_id),
        "approve_po_change": lambda: __import__(
            'app.procurement_v2', fromlist=['approve_po_change']
        ).approve_po_change(db, user, proposal.target_entity_id),
        "create_asn": lambda: workflows.create_asn(
            db, user, proposal.target_entity_id,
            float(proposal.preview.get('expected_quantity') or 0),
            str(proposal.preview.get('vehicle_number') or ''),
        ),
        "dispatch_outbox": lambda: workflows.dispatch_integration_outbox_event(db, user, proposal.target_entity_id),
        "record_inspection": lambda: workflows.record_inspection(
            db, user, proposal.target_entity_id,
            float(proposal.preview["inspected_quantity"]),
            float(proposal.preview["accepted_quantity"]),
            float(proposal.preview.get("rejected_quantity", 0)),
            float(proposal.preview.get("held_quantity", 0)),
            str(proposal.preview.get("certificate_status") or "verified"),
            list(proposal.preview.get("defect_codes") or []),
            str(proposal.preview.get("inspection_notes") or ""),
            bool(proposal.preview.get("production_impact") or False),
        ),
        "close_case": lambda: workflows.close_case(
            db, user, proposal.target_entity_id,
            str(proposal.preview.get("resolution", "Closed after human review")),
        ),
        "prepare_supplier_followup": lambda: __import__(
            'app.procurement_v2', fromlist=['prepare_supplier_followup']
        ).prepare_supplier_followup(
            db, user, proposal.target_entity_id,
            str(proposal.preview.get('supplier_id') or ''),
            str(proposal.preview.get('message') or ''),
        ),
        "verify_quote_fields": lambda: workflows.verify_quote_fields(
            db, user, proposal.target_entity_id,
            list(proposal.preview.get('decisions') or []),
        ),
        "prepare_finance_handoff": lambda: __import__(
            'app.invoice_service', fromlist=['prepare_finance_handoff']
        ).prepare_finance_handoff(db, user, proposal.target_entity_id),
        "approve_excel_import": lambda: __import__(
            'app.excel_connector', fromlist=['commit_import']
        ).commit_import(
            db, user, workflows.get_scoped_or_404(
                db, models.IntegrationImportBatch, user, proposal.target_entity_id, 'Import batch'
            ),
        ),
        "request_supplier_replacement": lambda: workflows.request_supplier_replacement(
            db, user, proposal.target_entity_id,
            float(proposal.preview.get('replacement_quantity') or 0),
            str(proposal.preview.get('requested_delivery') or ''),
        ),
        "record_replacement_receipt": lambda: workflows.record_replacement_receipt(
            db, user, proposal.target_entity_id,
            float(proposal.preview.get('received_quantity') or 0),
            str(proposal.preview.get('supplier_challan') or ''),
            str(proposal.preview.get('vehicle_number') or ''),
            int(proposal.preview.get('packages_count') or 0),
        ),
        "decide_supplier_certificate": lambda: __import__(
            'app.procurement_v2', fromlist=['decide_supplier_certificate']
        ).decide_supplier_certificate(
            db, user, proposal.target_entity_id,
            str(proposal.preview.get('decision') or ''),
            str(proposal.preview.get('notes') or ''),
        ),
        "close_requirement_lifecycle": lambda: workflows.close_requirement_lifecycle(
            db, user, proposal.target_entity_id,
        ),
    }
    result = action_map[proposal.action]()
    proposal.confirmation_state = "confirmed"
    proposal.decided_by_membership_id = membership.id
    proposal.decided_at = utcnow()
    authoritative_result = result[0] if isinstance(result, tuple) else result
    generated_artifact = result[1] if isinstance(result, tuple) and len(result) > 1 else None
    result_id = getattr(authoritative_result, 'id', None)
    receipt = models.AgentActionReceipt(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        proposal_id=proposal.id, run_id=proposal.run_id or f'proposal:{proposal.id}',
        tool_name=proposal.action, status='succeeded',
        target_entity_type=proposal.target_entity_type,
        target_entity_id=result_id or proposal.target_entity_id,
        result_summary={
            'proposal_id': proposal.id,
            'authoritative_result_id': result_id or proposal.target_entity_id,
            'action': proposal.action,
            'artifact_id': getattr(generated_artifact, 'id', None),
            'document_id': getattr(generated_artifact, 'document_id', None),
        },
        executed_by_membership_id=membership.id,
        started_at=utcnow(), completed_at=utcnow(),
        idempotency_key=proposal.idempotency_key or f'proposal:{proposal.id}',
    )
    db.add(receipt)
    db.flush()
    thread = db.get(models.AgentThread, proposal.thread_id)
    if thread:
        typed_state = load_thread_state(thread.context_state)
        if typed_state.pending_proposal_id == proposal.id:
            typed_state.pending_proposal_id = None
        typed_state.last_receipt = {
            'receipt_id': receipt.id, 'action': proposal.action,
            'target_entity_type': receipt.target_entity_type,
            'target_entity_id': receipt.target_entity_id,
            'completed_at': receipt.completed_at.isoformat() if receipt.completed_at else utcnow().isoformat(),
        }
        typed_state.updated_at = utcnow()
        persist_thread_state(thread, typed_state)
    if proposal.run_id:
        run = db.get(models.AgentRun, proposal.run_id)
        if run:
            record_run_event(db, run, 'run_resumed', {
                'proposal_id': proposal.id,
                'decided_by_membership_id': membership.id,
            })
            record_run_checkpoint(db, run, 'execute_action', {
                'proposal_id': proposal.id,
                'action': proposal.action,
                'decided_by_membership_id': membership.id,
            })
            record_run_event(db, run, 'receipt_recorded', {
                'receipt_id': receipt.id, 'action': proposal.action,
                'target_id': receipt.target_entity_id,
            })
            run.state = 'completed'
            run.completed_at = utcnow()
            record_run_event(db, run, 'run_completed', {
                'state': run.state,
                'proposal_id': proposal.id,
                'receipt_id': receipt.id,
            })
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "agent.proposal.confirmed",
        "agent_proposal", proposal.id, actor_user_id=user.id,
        meta={"agent_profile_id": proposal.agent_profile_id, "action": proposal.action},
    )
    return proposal


def team_status(db: Session, user: models.User) -> list[dict[str, Any]]:
    membership = membership_for_user(db, user)
    descendant_ids = reporting_descendants(db, membership)
    if membership.role not in {PLANT_MANAGER, ADMIN} and not descendant_ids:
        return []
    members = db.query(models.WorkspaceMembership).filter(
        models.WorkspaceMembership.id.in_(descendant_ids or [""])
    ).all()
    result: list[dict[str, Any]] = []
    for member in members:
        employee = db.get(models.User, member.user_id)
        tasks = db.query(models.Task).filter(
            models.Task.tenant_id == user.tenant_id,
            models.Task.owner_membership_id == member.id,
            models.Task.status.in_(["open", "pending_approval"]),
        ).order_by(models.Task.due_at.asc()).all()
        latest = db.query(models.AgentDelegation).filter_by(
            tenant_id=user.tenant_id, recipient_membership_id=member.id
        ).order_by(models.AgentDelegation.created_at.desc()).first()
        due = tasks[0].due_at if tasks else None
        result.append({
            "membership_id": member.id,
            "employee_name": employee.name if employee else "Unavailable employee",
            "role": member.role,
            "manager_membership_id": member.manager_membership_id,
            "open_work": len(tasks),
            "next_commitment": due.isoformat() if due else None,
            "risk": "overdue" if due and due.replace(tzinfo=timezone.utc) < utcnow() else "on_track",
            "blocker": latest.response.get("blocker") if latest else None,
            "last_formal_update": latest.response.get("updated_at") if latest else None,
            "latest_status": latest.status if latest else "no_update",
        })
    return result


DEMO_SEATS = (
    ('plant_manager', 'plant.manager@genuinegigs.local'),
    ('purchase_manager', 'purchase.manager@genuinegigs.local'),
    ('purchase_executive', 'purchase.exec@genuinegigs.local'),
    ('gate_operator', 'gate.operator@genuinegigs.local'),
    ('store_manager', 'store.manager@genuinegigs.local'),
    ('quality_inspector', 'quality.inspector@genuinegigs.local'),
    ('admin', 'admin@genuinegigs.local'),
)


def demo_access_rows(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    rows = []
    for role, email in DEMO_SEATS:
        account = db.query(models.Account).filter_by(email=email).first()
        membership = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=tenant_id, account_id=account.id if account else '', status='active',
        ).first()
        profile = db.query(models.AgentProfile).filter_by(
            tenant_id=tenant_id, membership_id=membership.id if membership else '',
        ).first()
        rows.append({
            'role': role, 'display_name': account.name if account else role.replace('_', ' ').title(),
            'email': email, 'membership_ready': membership is not None,
            'workspace_selectable': membership is not None,
            'plant_ids': membership.plant_ids if membership else [],
            'manager_membership_id': membership.manager_membership_id if membership else None,
            'agent_profile_ready': profile is not None and profile.enabled,
        })
    return rows


def reconcile_demo_access(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.demo_bootstrap_enabled or settings.app_env.lower() == 'production':
        raise HTTPException(status_code=404, detail='Demo access is disabled')
    tenant = db.get(models.Tenant, tenant_id)
    plant = db.query(models.Plant).filter_by(tenant_id=tenant_id).first()
    if tenant is None or plant is None:
        raise HTTPException(status_code=404, detail='Workspace not found')
    departments = db.query(models.Department).filter_by(tenant_id=tenant_id, plant_id=plant.id).all()
    def department_for(role: str) -> models.Department:
        needle = {'purchase_manager': 'proc', 'purchase_executive': 'proc', 'gate_operator': 'gate', 'store_manager': 'store', 'quality_inspector': 'quality'}.get(role, 'lead')
        return next((row for row in departments if needle in row.name.casefold()), departments[0])
    existing = {row.role: row for row in db.query(models.WorkspaceMembership).filter_by(tenant_id=tenant_id, status='active').all()}
    plant_manager = existing.get('plant_manager')
    for role, email in DEMO_SEATS:
        account = db.query(models.Account).filter_by(email=email).first()
        if account is None:
            continue
        membership = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=tenant_id, account_id=account.id,
        ).first()
        if membership is not None:
            membership.status = 'active'
            membership.default_plant_id = plant.id
            membership.plant_ids = sorted(set(membership.plant_ids or []) | {plant.id})
            membership.role = role
            membership.department_id = department_for(role).id
            member_user = db.get(models.User, membership.user_id)
            if member_user:
                member_user.role = role
                member_user.plant_id = plant.id
                member_user.department_id = membership.department_id
            profile = db.query(models.AgentProfile).filter_by(
                tenant_id=tenant_id, membership_id=membership.id,
            ).first()
            if profile is None:
                db.add(models.AgentProfile(
                    id=f'agt-{secrets.token_hex(6)}', tenant_id=tenant_id, plant_id=plant.id,
                    user_id=membership.user_id, membership_id=membership.id, role=role,
                    display_name=f'{account.name.split()[0]} Assistant',
                    allowed_actions=ROLE_DRAFT_TOOLS.get(role, []), blocked_actions=RESTRICTED_ACTIONS,
                    provider='groq', model_profile=settings.agent_primary_model,
                    enabled=bool(tenant.agent_enabled), escalation_policy={},
                ))
            else:
                profile.plant_id = plant.id
                profile.role = role
                profile.enabled = bool(tenant.agent_enabled)
            if member_user and not db.query(models.UserPlantAccess).filter_by(
                tenant_id=tenant_id, user_id=member_user.id, plant_id=plant.id,
            ).first():
                db.add(models.UserPlantAccess(
                    id=f'upa-{secrets.token_hex(6)}', tenant_id=tenant_id,
                    user_id=member_user.id, plant_id=plant.id, is_default=True,
                ))
            existing[role] = membership
            if role == 'plant_manager':
                plant_manager = membership
            continue
        suffix = secrets.token_hex(6)
        department = department_for(role)
        user = models.User(
            id=f'usr-{suffix}', account_id=account.id, tenant_id=tenant_id, plant_id=plant.id,
            department_id=department.id, name=account.name, email=account.email, role=role,
            password_hash=account.password_hash,
        )
        manager = existing.get('purchase_manager') if role == 'purchase_executive' else plant_manager
        membership = models.WorkspaceMembership(
            id=f'mem-{suffix}', account_id=account.id, tenant_id=tenant_id, user_id=user.id,
            default_plant_id=plant.id, plant_ids=[plant.id], department_id=department.id,
            role=role, manager_membership_id=manager.id if manager else None,
            permissions=[], status='active',
        )
        db.add_all([user, membership, models.UserPlantAccess(
            id=f'upa-{suffix}', tenant_id=tenant_id, user_id=user.id, plant_id=plant.id, is_default=True,
        )])
        db.flush()
        db.add(models.AgentProfile(
            id=f'agt-{suffix}', tenant_id=tenant_id, plant_id=plant.id, user_id=user.id,
            membership_id=membership.id, role=role,
            display_name=f'{account.name.split()[0]} Assistant',
            allowed_actions=ROLE_DRAFT_TOOLS.get(role, []), blocked_actions=RESTRICTED_ACTIONS,
            provider='groq', model_profile=settings.agent_primary_model,
            enabled=bool(tenant.agent_enabled), escalation_policy={},
        ))
        existing[role] = membership
        if role == 'plant_manager':
            plant_manager = membership
    plant_manager = existing.get('plant_manager')
    purchase_manager = existing.get('purchase_manager')
    for role, membership in existing.items():
        if role == 'plant_manager':
            membership.manager_membership_id = None
        elif role == 'purchase_executive' and purchase_manager:
            membership.manager_membership_id = purchase_manager.id
        elif plant_manager:
            membership.manager_membership_id = plant_manager.id
    return demo_access_rows(db, tenant_id)


def create_fresh_workspace(
    db: Session, user: models.User, payload: WorkspaceCreateRequest
) -> tuple[models.Tenant, models.WorkspaceMembership]:
    current = membership_for_user(db, user)
    account = db.get(models.Account, current.account_id)
    if account is None:
        raise HTTPException(status_code=409, detail="Account migration is incomplete")
    settings = get_settings()
    if payload.agent_enabled and not settings.agent_enabled:
        raise HTTPException(
            status_code=409,
            detail="Role agents are unavailable in this deployment. Configure the model provider first or create the workspace with agents disabled.",
        )
    agent_enabled = bool(payload.agent_enabled and settings.agent_enabled)
    suffix = secrets.token_hex(5)
    tenant_id = f"tenant-{suffix}"
    company_id = f"company-{suffix}"
    plant_id = f"plant-{suffix}"
    department_id = f"dept-leadership-{suffix}"
    procurement_department_id = f"dept-procurement-{suffix}"
    gate_department_id = f"dept-gate-{suffix}"
    stores_department_id = f"dept-stores-{suffix}"
    quality_department_id = f"dept-quality-{suffix}"
    new_user_id = f"usr-{suffix}"
    membership_id = f"mem-{suffix}"
    tenant = models.Tenant(
        id=tenant_id, name=payload.workspace_name,
        slug=f"{payload.workspace_name.lower().replace(' ', '-')}-{suffix}",
        status="active", workspace_kind="fresh", onboarding_status="needs_master_data",
        agent_enabled=agent_enabled,
        feature_flags={"procurement_v2": True, "role_agents": agent_enabled,
                       "agentic_procurement_cycles": True, "prepared_work": True,
                       "opa_governance": True, "sandbox_execution": True,
                       "async_specialists": True, "manager_cockpit": True,
                       "autonomy_centre": True, "temporal_procurement_workflow": False,
                       "tier2_automation": False, "tier3_automation": False, "proactive_companion": True,
                       "multi_agent_delegation": agent_enabled, "knowledge": agent_enabled},
    )
    new_user = models.User(
        id=new_user_id, account_id=account.id, tenant_id=tenant_id, plant_id=plant_id,
        department_id=department_id, name=user.name, email=f"{suffix}+{account.email}",
        role=ADMIN, password_hash=account.password_hash,
    )
    membership = models.WorkspaceMembership(
        id=membership_id, account_id=account.id, tenant_id=tenant_id, user_id=new_user_id,
        default_plant_id=plant_id, plant_ids=[plant_id], department_id=department_id,
        role=ADMIN, permissions=['workspace.owner'], status='active',
    )
    db.add_all([
        tenant,
        models.Company(id=company_id, tenant_id=tenant_id, name=payload.company_name,
                       erp_code=f"FRESH-{suffix.upper()}"),
        models.Plant(id=plant_id, tenant_id=tenant_id, company_id=company_id,
                     name=payload.plant_name, erp_location_code=payload.plant_code),
        models.Department(id=department_id, tenant_id=tenant_id, plant_id=plant_id,
                           name="Plant Leadership"),
        models.Department(id=procurement_department_id, tenant_id=tenant_id, plant_id=plant_id,
                          name='Procurement'),
        models.Department(id=gate_department_id, tenant_id=tenant_id, plant_id=plant_id,
                          name='Gate and Security'),
        models.Department(id=stores_department_id, tenant_id=tenant_id, plant_id=plant_id,
                          name='Stores'),
        models.Department(id=quality_department_id, tenant_id=tenant_id, plant_id=plant_id,
                          name='Quality'),
        new_user,
        membership,
        models.UserPlantAccess(id=f"upa-{suffix}", tenant_id=tenant_id,
                               user_id=new_user_id, plant_id=plant_id, is_default=True),
        models.AgentProfile(
            id=f"agt-{suffix}", tenant_id=tenant_id, plant_id=plant_id,
            user_id=new_user_id, membership_id=membership_id, role=ADMIN,
            display_name=f"{user.name.split(' ')[0]}'s Admin Agent",
            allowed_actions=ROLE_DRAFT_TOOLS[ADMIN],
            blocked_actions=RESTRICTED_ACTIONS, prompt_version="admin-playbook@1",
            policy_version="agent-policy@1", provider="groq",
            model_profile=settings.agent_primary_model, enabled=agent_enabled,
            escalation_policy={},
        ),
    ])
    for key, enabled in tenant.feature_flags.items():
        db.add(models.TenantFeatureFlag(
            tenant_id=tenant_id, key=key, enabled=bool(enabled),
            updated_by_membership_id=membership_id,
        ))
    db.flush()
    workflows.create_audit(
        db, tenant_id, plant_id, user.name, "workspace.fresh.created", "tenant", tenant_id,
        actor_user_id=new_user_id,
        meta={"workspace_kind": "fresh", "source_membership_id": current.id,
              "agent_enabled": agent_enabled, "owner_role": ADMIN,
              "standard_role_seats": []},
    )
    return tenant, membership
