from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from app.agent_schemas import IntentEnvelope


@dataclass(frozen=True)
class Capability:
    capability_id: str
    roles: frozenset[str]
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    controlled: bool = False
    attachment_types: tuple[str, ...] = ()
    adapter: str = ''
    response_card: str = 'record_summary'
    effect_type: str = 'read'
    autonomy_ceiling: int = 0
    resource_type: str = 'workspace'
    reversible: bool = True
    confirmation_behavior: str = 'never'
    sandbox_profile: str | None = None


ALL_ROLES = frozenset({
    'plant_manager', 'purchase_manager', 'purchase_executive', 'gate_operator',
    'store_manager', 'quality_inspector', 'admin',
})
PROCUREMENT = frozenset({'plant_manager', 'purchase_manager', 'purchase_executive', 'admin'})
MANAGERS = frozenset({'plant_manager', 'purchase_manager', 'admin'})


def _c(capability_id: str, roles: frozenset[str], **kwargs) -> Capability:
    if kwargs.get('controlled'):
        kwargs.setdefault('effect_type', 'consequential')
        kwargs.setdefault('autonomy_ceiling', 4)
        kwargs.setdefault('reversible', False)
        kwargs.setdefault('confirmation_behavior', 'always')
    elif capability_id.startswith(('create_', 'delegate_', 'request_', 'open_', 'record_', 'apply_')):
        kwargs.setdefault('effect_type', 'internal_mutation')
        kwargs.setdefault('autonomy_ceiling', 2)
        kwargs.setdefault('confirmation_behavior', 'policy')
    elif capability_id.startswith(('prepare_', 'preview_', 'export_')):
        kwargs.setdefault('effect_type', 'prepared_work')
        kwargs.setdefault('autonomy_ceiling', 1)
        kwargs.setdefault('confirmation_behavior', 'before_external_effect')
    if kwargs.get('attachment_types'):
        kwargs.setdefault('sandbox_profile', 'document_extraction')
    return Capability(capability_id, roles, **kwargs)


CAPABILITY_REGISTRY = {
    row.capability_id: row for row in (
        _c('answer_work_context', ALL_ROLES, adapter='answer_work_context'),
        _c('list_my_tasks', ALL_ROLES, adapter='list_my_tasks', response_card='task_update'),
        _c('list_team_tasks', MANAGERS, adapter='list_team_tasks', response_card='team_summary'),
        _c('get_record', ALL_ROLES, required_fields=('entity_id',), adapter='get_record'),
        _c('list_approved_materials', PROCUREMENT, adapter='list_approved_materials'),
        _c('search_approved_material', PROCUREMENT, required_fields=('material_query',), adapter='search_approved_material'),
        _c('review_supplier_compliance', PROCUREMENT, required_fields=('supplier_id',), optional_fields=('item_ids',), adapter='review_supplier_compliance', response_card='field_review'),
        _c('summarize_supplier_performance', PROCUREMENT, required_fields=('supplier_id',), adapter='summarize_supplier_performance', response_card='record_summary'),
        _c('open_supplier_corrective_action', frozenset({'purchase_manager', 'admin'}), required_fields=('supplier_id', 'source_entity_type', 'source_entity_id', 'problem_statement'), optional_fields=('response_due_days',), adapter='open_supplier_corrective_action', response_card='record_created'),
        _c('review_supplier_certificate_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('certificate_id', 'decision'), optional_fields=('notes',), controlled=True, adapter='review_supplier_certificate_proposal', response_card='approval_request'),
        _c('create_material_master_request', PROCUREMENT, required_fields=('material_query', 'uom', 'reason'), controlled=True, adapter='create_material_master_request'),
        _c('create_purchase_requirement', PROCUREMENT, required_fields=('item_id', 'quantity', 'uom', 'need_by_date', 'reason', 'assignee_membership_id'), adapter='create_purchase_requirement', response_card='record_created'),
        _c('review_requirement_lifecycle', PROCUREMENT, required_fields=('requirement_id',), adapter='review_requirement_lifecycle', response_card='record_summary'),
        _c('close_requirement_lifecycle_proposal', frozenset({'plant_manager', 'admin'}), required_fields=('requirement_id',), controlled=True, adapter='close_requirement_lifecycle_proposal', response_card='approval_request'),
        _c('prepare_rfq_draft', frozenset({'purchase_executive', 'admin'}), required_fields=('requirement_id',), adapter='prepare_rfq_draft', response_card='prepared_artifact'),
        _c('publish_rfq_proposal', frozenset({'purchase_executive', 'admin'}), required_fields=('rfq_id',), controlled=True, adapter='publish_rfq_proposal', response_card='approval_request'),
        _c('upload_supplier_quotes', PROCUREMENT, required_fields=('rfq_id',), attachment_types=('application/pdf', 'image/png', 'image/jpeg', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'), adapter='upload_supplier_quotes', response_card='field_review'),
        _c('review_quote_extraction', frozenset({'purchase_manager', 'admin'}), required_fields=('quote_id',), adapter='review_quote_extraction', response_card='field_review'),
        _c('record_exchange_rate', frozenset({'purchase_manager', 'admin'}), required_fields=('source_currency', 'rate', 'source_name', 'observed_at'), optional_fields=('source_reference',), adapter='record_exchange_rate', response_card='record_created'),
        _c('apply_exchange_rate', frozenset({'purchase_manager', 'admin'}), required_fields=('quote_id', 'observation_id'), adapter='apply_exchange_rate', response_card='record_summary'),
        _c('verify_quote_fields_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('quote_id', 'decisions'), controlled=True, adapter='verify_quote_fields_proposal', response_card='approval_request'),
        _c('prepare_supplier_comparison', frozenset({'purchase_manager', 'admin'}), required_fields=('rfq_id',), adapter='prepare_supplier_comparison', response_card='comparison_preview'),
        _c('submit_comparison_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('comparison_id',), controlled=True, adapter='submit_comparison_proposal', response_card='approval_request'),
        _c('record_comparison_decision_proposal', frozenset({'plant_manager', 'purchase_executive'}), required_fields=('comparison_id', 'decision'), controlled=True, adapter='record_comparison_decision_proposal', response_card='approval_request'),
        _c('confirm_purchase_order_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('comparison_id',), controlled=True, adapter='confirm_purchase_order_proposal', response_card='approval_request'),
        _c('prepare_negotiation_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('rfq_id', 'supplier_id', 'target', 'drafted_message'), controlled=True, adapter='prepare_negotiation_proposal', response_card='approval_request'),
        _c('prepare_po_supplier_email_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('po_id',), controlled=True, adapter='prepare_po_supplier_email_proposal', response_card='approval_request'),
        _c('prepare_po_change', frozenset({'purchase_manager', 'admin'}), required_fields=('po_id', 'change_type', 'reason'), optional_fields=('line_changes', 'acknowledgement_id'), adapter='prepare_po_change', response_card='record_created'),
        _c('approve_po_change_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('po_id',), controlled=True, adapter='approve_po_change_proposal', response_card='approval_request'),
        _c('prepare_asn_proposal', frozenset({'store_manager', 'admin'}), required_fields=('po_id', 'expected_quantity'), controlled=True, adapter='prepare_asn_proposal', response_card='approval_request'),
        _c('close_exception_proposal', frozenset({'plant_manager', 'admin'}), required_fields=('case_id', 'resolution'), controlled=True, adapter='close_exception_proposal', response_card='approval_request'),
        _c('prepare_supplier_followup', frozenset({'purchase_manager', 'purchase_executive', 'admin'}), required_fields=('rfq_id', 'supplier_id', 'message'), controlled=True, adapter='prepare_supplier_followup', response_card='approval_request'),
        _c('request_task_update', MANAGERS, required_fields=('task_id',), adapter='request_task_update', response_card='task_update'),
        _c('delegate_task', MANAGERS, required_fields=('requested_outcome', 'assignee_membership_id'), adapter='delegate_task', response_card='task_update'),
        _c('summarize_procurement_risks', PROCUREMENT, adapter='summarize_procurement_risks'),
        _c('explain_procurement_policy', PROCUREMENT, optional_fields=('comparison_id',), adapter='explain_procurement_policy', response_card='field_review'),
        _c('summarize_team_status', MANAGERS, adapter='summarize_team_status', response_card='team_summary'),
        _c('get_daily_brief', ALL_ROLES, optional_fields=('period',), adapter='get_daily_brief', response_card='team_summary'),
        _c('summarize_management_metrics', MANAGERS, adapter='summarize_management_metrics', response_card='record_summary'),
        _c('review_workspace_readiness', frozenset({'admin'}), adapter='review_workspace_readiness', response_card='field_review'),
        _c('preview_excel_import', frozenset({'admin'}), attachment_types=('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',), adapter='preview_excel_import', response_card='field_review'),
        _c('review_excel_import', frozenset({'admin'}), optional_fields=('batch_id',), adapter='review_excel_import', response_card='field_review'),
        _c('approve_excel_import_proposal', frozenset({'admin'}), optional_fields=('batch_id',), controlled=True, adapter='approve_excel_import_proposal', response_card='approval_request'),
        _c('export_excel_exchange', frozenset({'purchase_manager', 'admin'}), adapter='export_excel_exchange', response_card='prepared_artifact'),
        _c('prepare_invoice_from_attachment', frozenset({'purchase_manager', 'admin'}), required_fields=('po_id',), attachment_types=('application/pdf', 'image/png', 'image/jpeg', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'), adapter='prepare_invoice_from_attachment', response_card='field_review'),
        _c('match_supplier_invoice', frozenset({'purchase_manager', 'admin'}), required_fields=('invoice_id',), adapter='match_supplier_invoice', response_card='record_summary'),
        _c('check_invoice_payment_status', frozenset({'purchase_manager', 'plant_manager', 'admin'}), required_fields=('invoice_id',), adapter='check_invoice_payment_status', response_card='record_summary'),
        _c('list_supplier_deliveries', frozenset({'store_manager', 'gate_operator', 'purchase_manager', 'admin'}), optional_fields=('po_id',), adapter='list_supplier_deliveries', response_card='record_summary'),
        _c('prepare_finance_handoff_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('match_id',), controlled=True, adapter='prepare_finance_handoff_proposal', response_card='approval_request'),
        _c('prepare_gate_entry_proposal', frozenset({'gate_operator', 'admin'}), required_fields=('po_id', 'supplier_challan'), controlled=True, adapter='prepare_gate_entry_proposal', response_card='approval_request'),
        _c('prepare_store_receipt_proposal', frozenset({'store_manager', 'admin'}), required_fields=('po_id', 'received_quantity'), optional_fields=('damaged_quantity', 'observed_item_code', 'certificate_status', 'exception_notes', 'production_impact'), controlled=True, adapter='prepare_store_receipt_proposal', response_card='approval_request'),
        _c('prepare_quality_inspection_proposal', frozenset({'quality_inspector', 'admin'}), required_fields=('receipt_id', 'inspected_quantity', 'accepted_quantity'), optional_fields=('rejected_quantity', 'held_quantity', 'certificate_status', 'defect_codes', 'inspection_notes', 'production_impact'), controlled=True, adapter='prepare_quality_inspection_proposal', response_card='approval_request'),
        _c('prepare_supplier_return', frozenset({'purchase_manager', 'admin'}), required_fields=('inspection_id', 'return_quantity', 'reason'), adapter='prepare_supplier_return', response_card='record_created'),
        _c('request_supplier_replacement_proposal', frozenset({'purchase_manager', 'admin'}), required_fields=('supplier_return_id', 'replacement_quantity', 'requested_delivery'), controlled=True, adapter='request_supplier_replacement_proposal', response_card='approval_request'),
        _c('prepare_replacement_receipt_proposal', frozenset({'store_manager', 'admin'}), required_fields=('supplier_return_id', 'received_quantity', 'supplier_challan'), controlled=True, adapter='prepare_replacement_receipt_proposal', response_card='approval_request'),
    )
}


CapabilityAdapter = Callable[..., Any]
CAPABILITY_ADAPTERS: dict[str, CapabilityAdapter] = {}


def register_capability_adapter(adapter_name: str, adapter: CapabilityAdapter) -> None:
    if adapter_name not in {row.adapter for row in CAPABILITY_REGISTRY.values()}:
        raise ValueError(f'Adapter {adapter_name} is not declared by a capability')
    CAPABILITY_ADAPTERS[adapter_name] = adapter


def execute_capability_adapter(capability: Capability, *args, **kwargs):
    adapter = CAPABILITY_ADAPTERS.get(capability.adapter)
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail='This assistant action is temporarily unavailable',
        )
    return adapter(*args, **kwargs)


def unregistered_capability_adapters() -> list[str]:
    return sorted({
        capability.adapter for capability in CAPABILITY_REGISTRY.values()
        if capability.adapter not in CAPABILITY_ADAPTERS
    })


def capabilities_for_role(role: str) -> list[Capability]:
    return [capability for capability in CAPABILITY_REGISTRY.values() if role in capability.roles]


def validate_intent(envelope: IntentEnvelope, role: str) -> Capability:
    capability = CAPABILITY_REGISTRY.get(envelope.intent)
    if capability is None:
        raise HTTPException(status_code=422, detail='Unknown assistant capability')
    if role not in capability.roles:
        raise HTTPException(status_code=403, detail='Assistant capability is not allowed for this membership')
    envelope.requires_confirmation = capability.controlled
    return capability
