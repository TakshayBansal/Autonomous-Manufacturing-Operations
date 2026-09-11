"""Versioned assistant thread state and centralized merge rules."""

from datetime import datetime, timezone
from typing import Any

from app.agent_schemas import AgentThreadStateV3, IntentEnvelope, RecentBusinessEntity


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_thread_state(raw: dict[str, Any] | None) -> AgentThreadStateV3:
    value = dict(raw or {})
    recent = []
    for item in value.get('recent_entities') or []:
        entity_type = item.get('entity_type') or item.get('type')
        entity_id = item.get('entity_id') or item.get('id')
        if entity_type and entity_id:
            recent.append(RecentBusinessEntity(
                entity_type=str(entity_type), entity_id=str(entity_id),
                business_number=item.get('business_number') or item.get('display_id'),
                label=item.get('label'), created_or_used_at=utcnow(),
            ))
    selected = value.get('selected_context') or value.get('current_work_item') or {}
    canonical = {
        **value,
        'schema_version': 3,
        'selected_context': {
            'entity_type': selected.get('entity_type') or selected.get('type'),
            'entity_id': selected.get('entity_id') or selected.get('id'),
            'business_number': selected.get('business_number') or selected.get('display_id'),
            'source': selected.get('source') or ('legacy' if selected else None),
        },
        'recent_entities': [item.model_dump() for item in recent[:12]],
        'draft_fields': value.get('draft_fields') or value.get('procurement') or {},
        'field_provenance': value.get('field_provenance') or value.get('provenance') or {},
        'pending_proposal_id': value.get('pending_proposal_id'),
        'pending_confirmation': value.get('pending_confirmation'),
        'last_receipt': value.get('last_receipt'),
        'last_execution': value.get('last_execution'),
        'material_master_request_id': value.get('material_master_request_id'),
        'attachment_refs': list(dict.fromkeys([
            *list(value.get('attachment_refs') or []),
            *[
                str(row.get('attachment_id') or row.get('document_id'))
                for row in (value.get('attachments') or [])
                if row.get('attachment_id') or row.get('document_id')
            ],
        ]))[-20:],
        'unresolved_fields': value.get('unresolved_fields') or [],
        'candidate_mappings': value.get('candidate_mappings') or {},
        'continuation_status': value.get('continuation_status') or (
            'needs_input' if value.get('blocked_on') else 'idle'
        ),
        'blocked_on': value.get('blocked_on'),
        'updated_at': utcnow(),
    }
    # V2 attachment snapshots are intentionally discarded after their stable
    # identifiers have been migrated above.
    canonical.pop('attachments', None)
    return AgentThreadStateV3.model_validate(canonical)


def persist_thread_state(thread: Any, state: AgentThreadStateV3) -> AgentThreadStateV3:
    """Persist the canonical typed representation.

    Legacy keys are accepted only by ``load_thread_state``.  Writers must pass a
    validated V2 value through this function so malformed or parallel state
    shapes cannot be introduced by an adapter.
    """
    validated = AgentThreadStateV3.model_validate(state)
    validated.updated_at = utcnow()
    thread.context_state = validated.model_dump(mode='json', exclude_none=True)
    thread.context_schema_version = 3
    return validated


def apply_intent(
    state: AgentThreadStateV3,
    envelope: IntentEnvelope,
    *,
    provenance_message_id: str,
) -> AgentThreadStateV3:
    """Merge user-grounded arguments while clearing incompatible topic state."""
    updated = state.model_copy(deep=True)
    incoming = {
        key: value for key, value in envelope.entities.items()
        if value not in (None, '')
    }
    aliases = {
        'supplier_name': 'supplier_reference',
        'supplier_query': 'supplier_reference',
        'vendor_code': 'supplier_reference',
        'erp_vendor_id': 'supplier_reference',
        'rfq_number': 'rfq_reference',
    }
    for alias, canonical in aliases.items():
        if alias in incoming and canonical not in incoming:
            incoming[canonical] = incoming[alias]
    prior_item = str(updated.draft_fields.get('item_id') or '')
    next_item = str(incoming.get('item_id') or '')
    prior_name = str(updated.draft_fields.get('material_query') or '').casefold()
    next_name = str(incoming.get('material_query') or '').casefold()
    incompatible = bool(
        (prior_item and next_item and prior_item != next_item)
        or (
            envelope.is_topic_change and not prior_item and not next_item
            and prior_name and next_name and prior_name != next_name
        )
    )
    if incompatible:
        for key in (
            'material_query', 'item_code', 'item_id', 'material_error',
            'material_candidates', 'material_master_request_id',
        ):
            updated.draft_fields.pop(key, None)
        updated.candidate_set = []
        updated.blocked_on = None
        updated.pending_proposal_id = None
    updated.draft_fields.update(incoming)
    updated.active_goal.capability = envelope.intent
    updated.active_goal.status = 'resolving'
    updated.continuation_status = 'resolving'
    updated.active_goal.started_at = updated.active_goal.started_at or utcnow()
    updated.field_provenance.update({
        key: {'message_id': provenance_message_id, 'source': 'user'}
        for key in incoming
    })
    updated.updated_at = utcnow()
    return updated


def attach_documents(
    state: AgentThreadStateV3, attachments: list[dict[str, Any]],
) -> AgentThreadStateV3:
    updated = state.model_copy(deep=True)
    updated.attachment_refs = list(dict.fromkeys([
        *updated.attachment_refs,
        *[
            str(row.get('attachment_id') or row.get('document_id'))
            for row in attachments
            if row.get('attachment_id') or row.get('document_id')
        ],
    ]))[-20:]
    updated.updated_at = utcnow()
    return updated


def select_context(
    state: AgentThreadStateV3,
    *,
    entity_type: str,
    entity_id: str,
    business_number: str | None = None,
    source: str = 'page',
) -> AgentThreadStateV3:
    updated = state.model_copy(deep=True)
    updated.selected_context.entity_type = entity_type
    updated.selected_context.entity_id = entity_id
    updated.selected_context.business_number = business_number
    updated.selected_context.source = source
    updated.recent_entities = [
        RecentBusinessEntity(
            entity_type=entity_type, entity_id=entity_id,
            business_number=business_number, created_or_used_at=utcnow(),
        ),
        *[
            row for row in updated.recent_entities
            if not (row.entity_type == entity_type and row.entity_id == entity_id)
        ],
    ][:12]
    updated.updated_at = utcnow()
    return updated


def merge_thread_state(
    state: AgentThreadStateV3,
    *,
    facts: dict[str, Any] | None = None,
    topic_change: bool = False,
    correction: dict[str, Any] | None = None,
) -> AgentThreadStateV3:
    updated = state.model_copy(deep=True)
    if topic_change:
        updated.active_goal.capability = None
        updated.active_goal.status = 'idle'
        updated.candidate_set = []
        updated.blocked_on = None
        updated.draft_fields = {}
        updated.pending_proposal_id = None
        updated.unresolved_fields = []
        updated.candidate_mappings = {}
        updated.continuation_status = 'idle'
    if facts:
        updated.draft_fields.update({key: value for key, value in facts.items() if value is not None})
    if correction:
        updated.draft_fields.update(correction)
        updated.last_user_correction = correction
    updated.updated_at = utcnow()
    return updated


def remember_entity(
    state: AgentThreadStateV3,
    *,
    entity_type: str,
    entity_id: str,
    business_number: str | None = None,
    label: str | None = None,
) -> AgentThreadStateV3:
    updated = state.model_copy(deep=True)
    entity = RecentBusinessEntity(
        entity_type=entity_type, entity_id=entity_id,
        business_number=business_number, label=label,
        created_or_used_at=utcnow(),
    )
    updated.recent_entities = [entity, *[
        item for item in updated.recent_entities
        if not (item.entity_type == entity_type and item.entity_id == entity_id)
    ]][:12]
    updated.selected_context.entity_type = entity_type
    updated.selected_context.entity_id = entity_id
    updated.selected_context.business_number = business_number
    updated.selected_context.source = 'assistant'
    updated.updated_at = utcnow()
    return updated
