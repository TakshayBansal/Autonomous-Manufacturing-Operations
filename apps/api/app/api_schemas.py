from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str
    otp: str | None = None
    membership_id: str | None = None


class WorkspaceResetRequest(BaseModel):
    confirmation: Literal["RESET"]


class RetentionEnforceRequest(BaseModel):
    confirmation: Literal["ENFORCE_RETENTION"]


class RetentionHoldRequest(BaseModel):
    thread_id: str
    reason: str = Field(min_length=3, max_length=2000)


class QuotationThresholdRule(BaseModel):
    minimum_amount: float = Field(ge=0)
    count: int = Field(ge=1, le=20)


class ApprovalMatrixRule(BaseModel):
    minimum_amount: float = Field(ge=0)
    roles: list[Literal["plant_manager", "purchase_executive"]] = Field(min_length=1)


class SegregationRules(BaseModel):
    requester_cannot_submit_comparison: bool = False


class ProcurementPolicyRules(BaseModel):
    minimum_quotation_count: int = Field(default=1, ge=1, le=20)
    quotation_thresholds: list[QuotationThresholdRule] = Field(default_factory=list)
    allowed_currencies: list[str] = Field(default_factory=lambda: ["INR"], min_length=1)
    require_unexpired_quotes: bool = False
    allow_split_awards: bool = True
    require_single_source_justification: bool = True
    segregation: SegregationRules = Field(default_factory=SegregationRules)
    approval_matrix: list[ApprovalMatrixRule] = Field(default_factory=lambda: [ApprovalMatrixRule(minimum_amount=0, roles=["plant_manager", "purchase_executive"])])
    over_delivery_tolerance_percent: float = Field(default=0, ge=0, le=100)
    invoice_quantity_tolerance_percent: float = Field(default=0, ge=0, le=100)
    invoice_price_tolerance_percent: float = Field(default=0, ge=0, le=100)


class ProcurementPolicyCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    rules: ProcurementPolicyRules


class ProcurementPolicyActivateRequest(BaseModel):
    confirmation: Literal["ACTIVATE_POLICY"]


class ReceiptRequest(BaseModel):
    po_draft_id: str
    received_quantity: float = Field(gt=0)
    damaged_quantity: float = Field(default=0, ge=0)
    observed_item_code: str = Field(default="", max_length=80)
    certificate_status: Literal["received", "missing", "invalid"] = "received"
    exception_notes: str = Field(default="", max_length=4000)
    production_impact: bool = False


class InspectionRequest(BaseModel):
    receipt_id: str
    inspected_quantity: float
    accepted_quantity: float
    rejected_quantity: float
    held_quantity: float
    certificate_status: Literal["verified", "missing", "invalid", "pending"] = "verified"
    defect_codes: list[str] = Field(default_factory=list, max_length=20)
    inspection_notes: str = Field(default="", max_length=4000)
    production_impact: bool = False


class RequirementLineRequest(BaseModel):
    item_id: str
    quantity: float
    need_by_date: str
    uom: str | None = None
    specification: str = ""
    inspection_required: bool = True


class RequirementRequest(BaseModel):
    item_id: str | None = None
    quantity: float | None = None
    need_by_date: str | None = None
    source: str = "manual"
    uom: str | None = None
    title: str | None = None
    reason: str = Field(default="", max_length=2000)
    assignee_membership_id: str | None = None
    lines: list[RequirementLineRequest] = Field(default_factory=list)


class SupplierQuoteRequest(BaseModel):
    quote_number: str | None = None
    quote_date: str | None = None
    validity_date: str | None = None
    payment_terms: str | None = None
    currency: str = Field(default="INR", min_length=3, max_length=16)
    exchange_rate_to_inr: float = Field(default=1, gt=0)
    line: dict[str, Any] | None = None
    lines: list[dict[str, Any]] = Field(default_factory=list)


class SupplierNoBidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class RFQUpdateRequest(BaseModel):
    deadline: str | None = None
    supplier_ids: list[str] | None = None
    line: dict[str, Any] | None = None


class AwardCreateRequest(BaseModel):
    rfq_id: str
    quote_id: str
    supplier_id: str
    rationale: str = "Buyer recommended supplier for manager approval"


class DecisionRationaleRequest(BaseModel):
    rationale: str


class PODraftCreateRequest(BaseModel):
    award_id: str


class AwardAllocationRequest(BaseModel):
    rfq_line_id: str
    quote_line_id: str
    awarded_quantity: float = Field(gt=0)
    rationale: str = Field(default="", max_length=2000)


class SplitAwardConfirmRequest(BaseModel):
    confirmation: Literal["CONFIRM_SPLIT_AWARD"]
    allocations: list[AwardAllocationRequest] = Field(min_length=1)


class POAmendmentLineRequest(BaseModel):
    line_id: str
    quantity: float | None = Field(default=None, gt=0)
    unit_price: float | None = Field(default=None, ge=0)
    need_by_date: str | None = None


class POChangeRequest(BaseModel):
    change_type: Literal["amendment", "cancellation"]
    reason: str = Field(min_length=3, max_length=2000)
    lines: list[POAmendmentLineRequest] = Field(default_factory=list)
    acknowledgement_id: str | None = None


class FieldVerificationDecision(BaseModel):
    field_name: str
    decision: Literal["accept", "correct", "reject"]
    verified_value: Any | None = None
    comment: str | None = None


class VerifyFieldsRequest(BaseModel):
    decisions: list[FieldVerificationDecision] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)


class NegotiationRequest(BaseModel):
    rfq_id: str
    supplier_id: str
    target: str
    drafted_message: str


class NegotiationCounterofferRequest(BaseModel):
    revised_unit_price: float
    message: str
    commercial_terms: dict[str, Any] = Field(default_factory=dict)


class ASNRequest(BaseModel):
    po_draft_id: str
    expected_quantity: float
    vehicle_number: str = ""


class GateEntryRequest(BaseModel):
    po_draft_id: str
    asn_id: str | None = None
    vehicle_number: str = ""
    supplier_challan: str = ""
    packages_count: int = Field(default=0, ge=0)
    arrival_notes: str = ""


class MaterialMasterRequestCreate(BaseModel):
    item_code: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=2, max_length=240)
    uom: str = Field(min_length=1, max_length=24)
    specification: str = Field(default="", max_length=4000)
    reason: str = Field(min_length=3, max_length=2000)


class MaterialMasterDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=2000)


class SupplierMasterCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    vendor_id: str = Field(min_length=1, max_length=80)
    contact_name: str = Field(min_length=2, max_length=140)
    email: str = Field(min_length=3, max_length=180)
    phone: str = Field(default="", max_length=60)
    site_name: str = Field(default="Primary site", max_length=160)
    currency: str = Field(default="INR", max_length=16)
    payment_terms: str = Field(default="30 days", max_length=120)
    item_ids: list[str] = Field(default_factory=list)


class MaterialSupplierAssignment(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)
    supplier_ids: list[str] = Field(min_length=1, max_length=100)
    notes: str = Field(default="Approved for this material", max_length=1000)


class SupplierContactCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    email: str = Field(min_length=3, max_length=180, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str = Field(default="", max_length=60)


class ComplianceRequirementCreate(BaseModel):
    certificate_type: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    item_id: str | None = None
    mandatory: bool = True


class SupplierCertificateCreate(BaseModel):
    supplier_id: str
    certificate_type: str = Field(min_length=2, max_length=120)
    certificate_number: str = Field(default="", max_length=160)
    document_id: str | None = None
    valid_from: str = ""
    expires_on: str


class SupplierCertificateDecision(BaseModel):
    decision: Literal["verify", "reject"]
    notes: str = Field(default="", max_length=2000)


class SupplierCorrectiveActionCreate(BaseModel):
    supplier_id: str
    source_entity_type: str = Field(min_length=2, max_length=64)
    source_entity_id: str = Field(min_length=1, max_length=64)
    problem_statement: str = Field(min_length=5, max_length=4000)
    response_due_days: int = Field(default=7, ge=1, le=90)


class SupplierCorrectiveActionUpdate(BaseModel):
    status: Literal["awaiting_supplier", "response_received", "effectiveness_review", "closed", "cancelled"]
    root_cause: str = Field(default="", max_length=4000)
    corrective_action: str = Field(default="", max_length=4000)
    preventive_action: str = Field(default="", max_length=4000)
    effectiveness_evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


class ComparisonSubmitRequest(BaseModel):
    recommendation_rationale: str = Field(min_length=3, max_length=4000)


class ComparisonDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    rationale: str = Field(min_length=3, max_length=4000)


class POConfirmRequest(BaseModel):
    confirmation: Literal["CONFIRM_PO"]


class CaseCloseRequest(BaseModel):
    resolution: str = "Closed by owner"
    override: bool = False
    override_reason: str | None = None


class SupplierAcknowledgementRequest(BaseModel):
    status: Literal["accepted", "rejected", "change_requested"]
    confirmed_quantity: float = Field(ge=0)
    confirmed_delivery: str = Field(min_length=1, max_length=32)
    notes: str = Field(default="", max_length=4000)


class SupplierDeliveryNoticeRequest(BaseModel):
    expected_quantity: float = Field(gt=0)
    expected_delivery: str = Field(min_length=1, max_length=32)
    dispatch_reference: str = Field(min_length=1, max_length=120)
    vehicle_number: str = Field(default="", max_length=80)


class SupplierDeliveryUpdateRequest(BaseModel):
    external_update_id: str = Field(min_length=1, max_length=160)
    revised_expected_delivery: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=3, max_length=2000)


class SupplierClarificationResponseRequest(BaseModel):
    external_message_id: str = Field(min_length=1, max_length=240)
    subject: str = Field(default="", max_length=500)
    message: str = Field(min_length=1, max_length=4000)


class SupplierReturnCreateRequest(BaseModel):
    inspection_id: str
    return_quantity: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=2000)


class ReplacementRequest(BaseModel):
    replacement_quantity: float = Field(gt=0)
    requested_delivery: str


class ReplacementReceiptRequest(BaseModel):
    received_quantity: float = Field(gt=0)
    supplier_challan: str = Field(min_length=1, max_length=120)
    vehicle_number: str = Field(default="", max_length=80)
    packages_count: int = Field(default=0, ge=0)


class ReconciliationRequest(BaseModel):
    entity_type: str
    entity_id: str


class SyncJobRequest(BaseModel):
    connection_id: str
    job_type: Literal["master_data", "material_needs", "open_purchase_orders", "receipts", "inspections", "invoices", "payment_status", "production_plan", "production_actual", "downtime", "inventory", "supplier_commitments", "quality_events", "machine_events", "maintenance_work"]


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    email: str = Field(min_length=3, max_length=180)
    role: Literal[
        "plant_manager", "purchase_manager", "purchase_executive",
        "gate_operator", "store_manager", "quality_inspector", "admin",
    ]
    department_id: str = Field(min_length=1, max_length=64)
    plant_ids: list[str] = Field(min_length=1)
    password: str = Field(min_length=12, max_length=256)
    manager_id: str | None = None


class UserUpdateRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    manager_id: str | None = None
    is_active: bool | None = None
    plant_ids: list[str] | None = None


class RoleUpdateRequest(BaseModel):
    label: str
    permissions: list[str]


class ConnectionUpdateRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    mode: Literal["disconnected", "read_only", "simulation", "shadow", "uat", "limited_production_write", "production_write"] | None = None
    enabled_capabilities: list[str] | None = None
    writes_enabled: bool | None = None
    write_enable_confirmation: Literal["ENABLE_EXTERNAL_WRITES"] | None = None
    acceptance_reference: str | None = Field(default=None, min_length=3, max_length=240)


class ConnectionCreateRequest(BaseModel):
    provider: Literal["excel_csv", "generic_rest", "generic_odata", "sftp_file", "generic_soap", "ipaas", "private_bridge", "oracle_fusion", "sap_s4hana", "dynamics_365", "odoo"]
    name: str
    mode: Literal["disconnected", "read_only", "simulation", "shadow", "uat"] = "read_only"
    enabled_capabilities: list[str] = Field(default_factory=list)
    secret_ref: str | None = None


class MappingProfileRequest(BaseModel):
    connection_id: str
    name: str
    workbook_schema_version: str = "1.0"
    mappings: dict[str, dict[str, str]]
    transforms: dict[str, dict[str, str]] = Field(default_factory=dict)
    ownership: dict[str, str] = Field(default_factory=dict)


class InvoiceLineRequest(BaseModel):
    po_line_id: str
    description: str = ""
    quantity: float = Field(gt=0)
    uom: str
    unit_price: float = Field(ge=0)
    tax_amount: float = Field(ge=0, default=0)
    line_total: float = Field(ge=0)


class SupplierInvoiceCreateRequest(BaseModel):
    supplier_id: str
    po_draft_id: str
    document_id: str | None = None
    invoice_number: str
    invoice_date: str
    currency: str = "INR"
    total_amount: float = Field(ge=0)
    source: Literal["manual", "upload", "email", "portal", "excel", "erp"] = "manual"
    lines: list[InvoiceLineRequest]


class InvoiceExtractionVerifyRequest(SupplierInvoiceCreateRequest):
    """Human-verified values used to create the canonical invoice."""
    source: Literal["upload"] = "upload"


class ExchangeRateCreateRequest(BaseModel):
    source_currency: str = Field(min_length=3, max_length=16)
    target_currency: str = Field(default="INR", min_length=3, max_length=16)
    rate: float = Field(gt=0)
    source_name: str = Field(min_length=2, max_length=160)
    source_reference: str = Field(default="", max_length=240)
    observed_at: str


class QuoteExchangeRateRequest(BaseModel):
    observation_id: str


class InboundSupplierEmailRequest(BaseModel):
    external_message_id: str = Field(min_length=1, max_length=240)
    sender_email: str = Field(min_length=3, max_length=320)
    message_type: Literal["quotation", "invoice", "po_acknowledgement", "delivery_notice"] = "quotation"
    rfq_reference: str | None = Field(default=None, max_length=120)
    po_reference: str | None = Field(default=None, max_length=120)
    subject: str = Field(default="", max_length=500)
    body_preview: str = Field(default="", max_length=2000)
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    acknowledgement_status: Literal["accepted", "rejected", "change_requested"] | None = None
    confirmed_quantity: float | None = Field(default=None, ge=0)
    confirmed_delivery: str | None = Field(default=None, max_length=32)
    expected_quantity: float | None = Field(default=None, gt=0)
    expected_delivery: str | None = Field(default=None, max_length=32)
    dispatch_reference: str | None = Field(default=None, max_length=120)
    vehicle_number: str = Field(default="", max_length=80)
    attachment_purpose: Literal["supplier_dispatch_document", "supplier_certificate"] = "supplier_dispatch_document"
