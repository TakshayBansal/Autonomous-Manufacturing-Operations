from typing import Any
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from fastapi.responses import JSONResponse

from app.core.permissions import ADMIN, require_read_role, require_role, workspace_capabilities, workspace_membership
from app.core.config import get_settings
from app.core.security import (
    clear_session,
    create_session,
    current_session,
    current_user,
    ensure_not_locked,
    record_login_attempt,
    require_csrf,
    verify_mfa_code,
    verify_password,
)
from app.core.rate_limit import enforce_login_rate_limit, record_login_result
from app.core.middleware import IdempotencyMiddleware, RequestLogMiddleware, SecurityHeadersMiddleware
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import engine, get_db
from app.domains import workflows
from app.erp import erp_adapter
from app import documents as document_service
from app import procurement_v2
from app import agent_service
from app import excel_connector, invoice_service, supplier_performance, procurement_policy, currency_service
from app import quotation_intake as quotation_intake_service
from app.connector_sdk import ConnectorContext, ConnectorMode, CONNECTOR_REGISTRY, SYNC_JOB_CAPABILITIES, get_connector, registry_manifests, run_conformance_report
from app.repositories import etag_for, require_if_match
from app.models import AgentActionRequest, ControlTowerSnapshot, WorkspaceOverview, WorkItemContext
from app.api_schemas import (
    ASNRequest,
    AwardCreateRequest,
    CaseCloseRequest,
    ConnectionUpdateRequest,
    ConnectionCreateRequest,
    DecisionRationaleRequest,
    GateEntryRequest,
    MaterialMasterDecision,
    MaterialMasterRequestCreate,
    MappingProfileRequest,
    InboundSupplierEmailRequest,
    SupplierMasterCreate,
    MaterialSupplierAssignment,
    SupplierContactCreate,
    ComplianceRequirementCreate,
    SupplierCertificateCreate,
    SupplierCertificateDecision,
    SupplierCorrectiveActionCreate,
    SupplierCorrectiveActionUpdate,
    SupplierInvoiceCreateRequest,
    InvoiceExtractionVerifyRequest,
    ExchangeRateCreateRequest,
    QuoteExchangeRateRequest,
    ComparisonDecisionRequest,
    ComparisonSubmitRequest,
    POConfirmRequest,
    POChangeRequest,
    InspectionRequest,
    LoginRequest,
    NegotiationCounterofferRequest,
    NegotiationRequest,
    PODraftCreateRequest,
    ReceiptRequest,
    ReconciliationRequest,
    RequirementRequest,
    RFQUpdateRequest,
    RoleUpdateRequest,
    SupplierAcknowledgementRequest,
    SupplierDeliveryNoticeRequest,
    SupplierDeliveryUpdateRequest,
    SupplierClarificationResponseRequest,
    SupplierReturnCreateRequest,
    ReplacementRequest,
    ReplacementReceiptRequest,
    SupplierQuoteRequest,
    SupplierNoBidRequest,
    SplitAwardConfirmRequest,
    SyncJobRequest,
    UserCreateRequest,
    UserUpdateRequest,
    VerifyFieldsRequest,
    WorkspaceResetRequest,
    ProcurementPolicyCreateRequest,
    ProcurementPolicyActivateRequest,
)
from app.routers.health import router as health_router
from app.routers.agents import router as agents_router
from app.routers.backend_plan import router as backend_plan_router
from app.routers.identity import router as identity_router
from app.routers.companion import router as companion_router, admin_router as companion_admin_router
from app.operations.router import router as operational_v2_router
from app.routers.devtools import router as devtools_router
from app.operations.recovery.router import router as recovery_router
from app.scm.router import router as scm_router
from app.platform.router import router as platform_router
from app.intelligence.router import router as gigi_router
from app.platform.case_router import router as case_router

workflows.get_settings().validate_runtime_safety()

app = FastAPI(
    title="GenuineGigs Manufacturing Agent OS API",
    version="1.0.0",
    description="Industrial procurement workflow API with auth, audit, documents, integrations, and role-bound agents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=workflows.get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(health_router)
app.include_router(agents_router)
app.include_router(backend_plan_router)
app.include_router(identity_router)
app.include_router(companion_router)
app.include_router(companion_admin_router)
app.include_router(operational_v2_router)
app.include_router(recovery_router)
app.include_router(devtools_router)
app.include_router(scm_router)
app.include_router(platform_router)
app.include_router(gigi_router)
app.include_router(case_router)
from app.telemetry import configure_fastapi
configure_fastapi(app, engine)


@app.exception_handler(StaleDataError)
async def stale_write_handler(_request: Request, _error: StaleDataError) -> JSONResponse:
    return JSONResponse(status_code=412, content={"detail": "Entity version is stale"})


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def serialize_user(user: models.User, db: Session | None = None) -> dict[str, Any]:
    payload = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "plant_id": user.plant_id,
    }
    if db is not None:
        membership = workspace_membership(db, user)
        payload['membership_id'] = membership.id if membership else None
        payload['permissions'] = list(membership.permissions or []) if membership else []
        payload['capabilities'] = workspace_capabilities(db, user)
    return payload


@app.post("/auth/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    email = payload.email.lower().strip()
    try:
        enforce_login_rate_limit(request, email)
        ensure_not_locked(db, email)
    except HTTPException as exc:
        workflows.create_audit(
            db,
            "external",
            None,
            email,
            "auth.login_denied",
            "user",
            email,
            "blocked",
            meta={"status_code": exc.status_code},
        )
        db.commit()
        raise
    account = db.query(models.Account).filter(models.Account.email == email).first()
    memberships = (
        db.query(models.WorkspaceMembership)
        .filter_by(account_id=account.id, status="active")
        .order_by(models.WorkspaceMembership.created_at.asc())
        .all()
        if account else []
    )
    membership = next((row for row in memberships if row.id == payload.membership_id), None) if payload.membership_id else (memberships[0] if memberships else None)
    if payload.membership_id and membership is None:
        raise HTTPException(status_code=403, detail="Workspace membership access denied")
    user = db.get(models.User, membership.user_id) if membership else db.query(models.User).filter(models.User.email == email).first()
    password_hash = account.password_hash if account else user.password_hash if user else ""
    if user is None or not verify_password(payload.password, password_hash):
        record_login_attempt(db, email, False)
        record_login_result(request, email, False)
        workflows.create_audit(
            db,
            user.tenant_id if user else "external",
            user.plant_id if user else None,
            email,
            "auth.login_failed",
            "user",
            user.id if user else email,
            "blocked",
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if account and not verify_mfa_code(account, payload.otp):
        workflows.create_audit(
            db, user.tenant_id, user.plant_id, email, "auth.mfa_required",
            "account", account.id, "blocked", actor_user_id=user.id,
        )
        db.commit()
        raise HTTPException(status_code=401, detail={"code": "mfa_required", "message": "A valid MFA code is required"})
    if account and len(memberships) > 1 and not payload.membership_id:
        options = []
        for row in memberships:
            tenant = db.get(models.Tenant, row.tenant_id)
            plant = db.get(models.Plant, row.default_plant_id)
            options.append({
                "membership_id": row.id,
                "workspace_name": tenant.name if tenant else "Workspace",
                "plant_name": plant.name if plant else "Plant",
                "role": row.role,
                "workspace_kind": tenant.workspace_kind if tenant else "unknown",
                "onboarding_status": tenant.onboarding_status if tenant else "unknown",
            })
        record_login_attempt(db, email, True)
        db.commit()
        return {"requires_workspace_selection": True, "workspaces": options}
    record_login_attempt(db, email, True)
    record_login_result(request, email, True)
    session_payload = create_session(db, response, user)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "auth.login", "user", user.id, actor_user_id=user.id)
    db.commit()
    return {'user': serialize_user(user, db), **session_payload}


@app.post("/auth/logout", dependencies=[Depends(csrf_guard)])
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)) -> dict[str, str]:
    clear_session(db, request, response)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "auth.logout", "user", user.id, actor_user_id=user.id)
    db.commit()
    return {"status": "signed_out"}


@app.get("/auth/me")
def me(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)) -> dict[str, Any]:
    return {'user': serialize_user(user, db)}


@app.get("/auth/csrf")
def csrf(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    session = current_session(db, request)
    return {"csrf_token": session.csrf_token}


@app.post("/admin/reset-workspace", dependencies=[Depends(csrf_guard)])
def admin_reset_workspace(payload: WorkspaceResetRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)) -> dict[str, str]:
    require_role(user, ADMIN)
    if workflows.get_settings().app_env not in {"development", "test"}:
        raise HTTPException(status_code=403, detail="Workspace reset is disabled outside development/test")
    if db.query(models.Tenant).count() != 1:
        raise HTTPException(status_code=409, detail="Guarded reset refuses to operate when multiple tenants exist")
    reset_workspace_database(db, v2_reference_time=datetime.now(timezone.utc))
    workflows.create_audit(db, user.tenant_id, user.plant_id, "Workspace Reset", "workspace.reset", "tenant", user.tenant_id, actor_user_id=None)
    db.commit()
    return {"status": "reset_complete"}



@app.get("/workspace/overview", response_model=WorkspaceOverview)
def workspace_overview(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)) -> WorkspaceOverview:
    return workflows.workspace_overview(db, user)


@app.get('/workspace/work-items/{work_item_id}/context', response_model=WorkItemContext)
def workspace_work_item_context(work_item_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)) -> WorkItemContext:
    return workflows.work_item_context(db, user, work_item_id)

@app.get("/procurement/control-tower", response_model=ControlTowerSnapshot)
def get_control_tower(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)) -> ControlTowerSnapshot:
    return workflows.control_tower_snapshot(db, user)



@app.get("/procurement/cycles")
def procurement_cycles(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.procurement_cycle_summaries(db, user)


@app.get("/procurement/cycles/{cycle_id}")
def procurement_cycle(cycle_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.procurement_cycle_detail(db, user, cycle_id)


@app.get("/procurement/active-cycle")
def procurement_active_cycle(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.procurement_cycle_detail(db, user)
@app.get("/org/users")
def list_users(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role == ADMIN:
        return db.query(models.User).filter(
            models.User.tenant_id == user.tenant_id,
            models.User.plant_id == user.plant_id,
        ).all()
    return [user]


@app.get("/org/agents")
def list_agents(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.list_for_user(db, models.AgentProfile, user)


@app.get("/org/roles")
def list_roles(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    return db.query(models.RoleDefinition).all()


@app.get("/org/plants")
def list_authorized_plants(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    plant_ids = [row.plant_id for row in db.query(models.UserPlantAccess).filter_by(user_id=user.id, tenant_id=user.tenant_id).all()]
    return db.query(models.Plant).filter(models.Plant.tenant_id == user.tenant_id, models.Plant.id.in_(plant_ids or [""])).all()


@app.get("/org/departments")
def list_departments(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    return db.query(models.Department).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()


@app.post("/org/users", dependencies=[Depends(csrf_guard)])
def create_user(payload: UserCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    from app.core.security import hash_password
    if db.query(models.Account).filter(models.Account.email == payload.email.lower().strip()).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    role = db.get(models.RoleDefinition, payload.role)
    if role is None:
        raise HTTPException(status_code=422, detail="Unknown role")
    department = db.get(models.Department, payload.department_id)
    if department is None or department.tenant_id != user.tenant_id or department.plant_id not in payload.plant_ids:
        raise HTTPException(status_code=422, detail="Choose a department in an authorized plant")
    allowed_plants = {row.plant_id for row in db.query(models.UserPlantAccess).filter_by(user_id=user.id, tenant_id=user.tenant_id).all()}
    if not payload.plant_ids or not set(payload.plant_ids).issubset(allowed_plants):
        raise HTTPException(status_code=403, detail="Plant administration access denied")
    password_hash = hash_password(payload.password)
    account = models.Account(
        id=workflows.next_id(db, models.Account, "ACCT"),
        email=payload.email.lower().strip(),
        name=payload.name,
        password_hash=password_hash,
        email_verified_at=workflows.utcnow(),
    )
    created = models.User(id=workflows.next_id(db, models.User, "USR"), account_id=account.id, tenant_id=user.tenant_id, plant_id=payload.plant_ids[0], department_id=payload.department_id, name=payload.name, email=account.email, role=payload.role, password_hash=password_hash, manager_id=payload.manager_id)
    db.add_all([account, created])
    db.flush()
    manager_membership = db.query(models.WorkspaceMembership).filter_by(
        user_id=payload.manager_id, tenant_id=user.tenant_id
    ).first() if payload.manager_id else None
    if payload.manager_id and manager_membership is None:
        raise HTTPException(status_code=422, detail="Choose a manager in this workspace")
    membership = models.WorkspaceMembership(
        id=workflows.next_id(db, models.WorkspaceMembership, "MEM"),
        account_id=account.id,
        tenant_id=user.tenant_id,
        user_id=created.id,
        default_plant_id=payload.plant_ids[0],
        plant_ids=payload.plant_ids,
        department_id=payload.department_id,
        role=payload.role,
        manager_membership_id=manager_membership.id if manager_membership else None,
        permissions=[],
        status="active",
    )
    db.add(membership)
    for index, plant_id in enumerate(payload.plant_ids):
        db.add(models.UserPlantAccess(id=workflows.next_id(db, models.UserPlantAccess, "UPA"), tenant_id=user.tenant_id, user_id=created.id, plant_id=plant_id, is_default=index == 0))
    if payload.manager_id:
        db.add(models.ReportingLine(
            id=workflows.next_id(db, models.ReportingLine, "RL"),
            tenant_id=user.tenant_id,
            manager_user_id=payload.manager_id,
            report_user_id=created.id,
        ))
    tenant = db.get(models.Tenant, user.tenant_id)
    db.add(models.AgentProfile(
        id=workflows.next_id(db, models.AgentProfile, "AGT"),
        tenant_id=user.tenant_id,
        plant_id=payload.plant_ids[0],
        user_id=created.id,
        membership_id=membership.id,
        role=payload.role,
        display_name=f"{payload.name.split(' ')[0]}'s {payload.role.replace('_', ' ').title()} Agent",
        allowed_actions=agent_service.ROLE_DRAFT_TOOLS.get(payload.role, ["explain_task"]),
        blocked_actions=agent_service.RESTRICTED_ACTIONS,
        escalation_manager_id=payload.manager_id,
        prompt_version=f"{payload.role}-playbook@1",
        policy_version="agent-policy@1",
        provider="groq",
        model_profile=get_settings().agent_primary_model,
        enabled=bool(tenant and tenant.agent_enabled and get_settings().agent_enabled),
        escalation_policy={"manager_membership_id": manager_membership.id if manager_membership else None},
    ))
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "user.created", "user", created.id, actor_user_id=user.id)
    db.commit()
    return workflows.record_to_dict(created)


@app.patch("/org/users/{user_id}", dependencies=[Depends(csrf_guard)])
def update_user(user_id: str, payload: UserUpdateRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    target = db.query(models.User).filter_by(id=user_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    supplied = request.headers.get("if-match")
    if supplied is None:
        raise HTTPException(status_code=428, detail="If-Match header is required")
    if supplied.strip().strip('"') != str(target.version):
        raise HTTPException(status_code=412, detail="Entity version is stale")
    updates = payload.model_dump(exclude_none=True, exclude={"plant_ids"})
    for key, value in updates.items():
        setattr(target, key, value)
    if payload.plant_ids is not None:
        allowed_plants = {row.plant_id for row in db.query(models.UserPlantAccess).filter_by(user_id=user.id, tenant_id=user.tenant_id).all()}
        if not payload.plant_ids or not set(payload.plant_ids).issubset(allowed_plants):
            raise HTTPException(status_code=403, detail="Plant administration access denied")
        db.query(models.UserPlantAccess).filter_by(user_id=target.id, tenant_id=user.tenant_id).delete()
        for index, plant_id in enumerate(payload.plant_ids):
            db.add(models.UserPlantAccess(id=workflows.next_id(db, models.UserPlantAccess, "UPA"), tenant_id=user.tenant_id, user_id=target.id, plant_id=plant_id, is_default=index == 0))
        target.plant_id = payload.plant_ids[0]
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "user.updated", "user", target.id, actor_user_id=user.id)
    db.commit()
    return workflows.record_to_dict(target)


@app.put("/org/roles/{role_id}", dependencies=[Depends(csrf_guard)])
def update_role(role_id: str, payload: RoleUpdateRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    role = db.get(models.RoleDefinition, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    supplied = request.headers.get("if-match")
    if supplied is None:
        raise HTTPException(status_code=428, detail="If-Match header is required")
    if supplied.strip().strip('W/').strip('"') != str(role.version):
        raise HTTPException(status_code=412, detail="Entity version is stale")
    role.label = payload.label
    role.permissions = payload.permissions
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "role.updated", "role", role.id, actor_user_id=user.id)
    db.commit()
    return {"id": role.id, "label": role.label, "permissions": role.permissions}


@app.get("/org/plant-access")
def plant_access(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    return db.query(models.UserPlantAccess).filter(
        models.UserPlantAccess.tenant_id == user.tenant_id,
        models.UserPlantAccess.plant_id == user.plant_id,
    ).all()


@app.get("/tasks")
def list_tasks(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.tasks_for_user(db, user)


@app.get("/cases")
def list_cases(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.list_for_user(db, models.Case, user)


@app.get("/audit")
def list_audit(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "audit")
    query = db.query(models.AuditEvent).filter(
        models.AuditEvent.tenant_id == user.tenant_id,
        models.AuditEvent.plant_id == user.plant_id,
    )
    return query.order_by(models.AuditEvent.created_at.desc()).all()


@app.get("/procurement/suppliers")
def list_suppliers(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.Supplier, user)


@app.post("/procurement/suppliers", dependencies=[Depends(csrf_guard)])
def create_supplier(payload: SupplierMasterCreate, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    supplier = procurement_v2.create_supplier_master(
        db, user, name=payload.name, vendor_id=payload.vendor_id,
        contact_name=payload.contact_name, email=payload.email,
        phone=payload.phone, site_name=payload.site_name,
        currency=payload.currency, payment_terms=payload.payment_terms,
        item_ids=payload.item_ids,
    )
    db.commit()
    return workflows.record_to_dict(supplier)


@app.get("/procurement/supplier-item-capabilities")
def list_supplier_item_capabilities(
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.SupplierItemCapability, user)


@app.post("/procurement/materials/{item_id}/suppliers", dependencies=[Depends(csrf_guard)])
def assign_material_suppliers(
    item_id: str,
    payload: MaterialSupplierAssignment,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    if payload.item_id != item_id:
        raise HTTPException(status_code=422, detail="Material identifier does not match the route")
    capabilities = procurement_v2.assign_suppliers_to_material(
        db, user, item_id=item_id, supplier_ids=payload.supplier_ids,
        notes=payload.notes,
    )
    db.commit()
    return workflows.records_to_dicts(capabilities)


@app.get("/procurement/supplier-contacts")
def list_supplier_contacts(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.records_to_dicts(
        workflows.user_scope_query(db, models.SupplierContact, user)
        .order_by(models.SupplierContact.name)
        .all()
    )


@app.post("/procurement/suppliers/{supplier_id}/contacts", dependencies=[Depends(csrf_guard)])
def create_supplier_contact(
    supplier_id: str,
    payload: SupplierContactCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    contact = procurement_v2.create_supplier_contact(
        db, user, supplier_id=supplier_id, name=payload.name,
        email=payload.email, phone=payload.phone,
    )
    db.commit()
    return workflows.record_to_dict(contact)


@app.get("/procurement/supplier-compliance/requirements")
def list_compliance_requirements(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.SupplierComplianceRequirement, user)


@app.post("/procurement/supplier-compliance/requirements", dependencies=[Depends(csrf_guard)])
def create_compliance_requirement(payload: ComplianceRequirementCreate, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    requirement = procurement_v2.create_compliance_requirement(db, user, payload.certificate_type, payload.description, payload.item_id, payload.mandatory)
    db.commit()
    return workflows.record_to_dict(requirement)


@app.get("/procurement/supplier-certificates")
def list_supplier_certificates(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.SupplierCertificate, user)


@app.post("/procurement/supplier-certificates", dependencies=[Depends(csrf_guard)])
def submit_supplier_certificate(payload: SupplierCertificateCreate, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    certificate = procurement_v2.submit_supplier_certificate(db, user, payload.supplier_id, payload.certificate_type, payload.certificate_number, payload.document_id, payload.valid_from, payload.expires_on)
    db.commit()
    return workflows.record_to_dict(certificate)


@app.post("/procurement/supplier-certificates/{certificate_id}/decision", dependencies=[Depends(csrf_guard)])
def decide_supplier_certificate(certificate_id: str, payload: SupplierCertificateDecision, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.SupplierCertificate, user, certificate_id, "Supplier certificate"))
    certificate = procurement_v2.decide_supplier_certificate(db, user, certificate_id, payload.decision, payload.notes)
    db.commit()
    return workflows.record_to_dict(certificate)


@app.get("/procurement/suppliers/{supplier_id}/compliance")
def supplier_compliance(supplier_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    supplier = workflows.get_scoped_or_404(db, models.Supplier, user, supplier_id, "Supplier")
    item_ids = {row.item_id for row in workflows.user_scope_query(db, models.SupplierItemCapability, user).filter_by(supplier_id=supplier.id, approved=True).all()}
    return workflows.supplier_compliance_readiness(db, user, supplier, item_ids)


@app.get("/procurement/suppliers/{supplier_id}/performance")
def supplier_performance_summary(supplier_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return supplier_performance.summary(db, user, supplier_id)


@app.get("/procurement/supplier-corrective-actions")
def list_supplier_corrective_actions(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.SupplierCorrectiveAction, user)


@app.post("/procurement/supplier-corrective-actions", dependencies=[Depends(csrf_guard)])
def create_supplier_corrective_action(payload: SupplierCorrectiveActionCreate, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    action = supplier_performance.open_corrective_action(db, user, payload.supplier_id, payload.source_entity_type, payload.source_entity_id, payload.problem_statement, payload.response_due_days)
    db.commit()
    return workflows.record_to_dict(action)


@app.post("/procurement/supplier-corrective-actions/{action_id}/status", dependencies=[Depends(csrf_guard)])
def update_supplier_corrective_action(action_id: str, payload: SupplierCorrectiveActionUpdate, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.SupplierCorrectiveAction, user, action_id, "Corrective action"))
    action = supplier_performance.update_corrective_action(db, user, action_id, payload.status, payload.root_cause, payload.corrective_action, payload.preventive_action, payload.effectiveness_evidence)
    db.commit()
    return workflows.record_to_dict(action)



@app.get("/procurement/items")
def list_items(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.Item, user)


@app.get("/procurement/requirements/{requirement_id}/lifecycle")
def requirement_lifecycle(requirement_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.requirement_lifecycle_state(db, user, requirement_id)


@app.post("/procurement/requirements/{requirement_id}/close", dependencies=[Depends(csrf_guard)])
def close_requirement_lifecycle(requirement_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.PurchaseRequirement, user, requirement_id, "Requirement"))
    requirement = workflows.close_requirement_lifecycle(db, user, requirement_id)
    db.commit()
    return workflows.record_to_dict(requirement)


@app.get('/procurement/assignees')
def list_procurement_assignees(
    db: Session = Depends(get_db), user: models.User = Depends(authenticated_user),
):
    require_read_role(user, 'procurement')
    memberships = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, default_plant_id=user.plant_id,
        role='purchase_executive', status='active',
    ).all()
    return [{
        'membership_id': membership.id,
        'user_id': membership.user_id,
        'name': db.get(models.User, membership.user_id).name,
        'role': membership.role,
    } for membership in memberships]


@app.get("/procurement/material-requests")
def list_material_requests(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.MaterialMasterRequest, user)


@app.post("/procurement/material-requests", dependencies=[Depends(csrf_guard)])
def create_material_request(payload: MaterialMasterRequestCreate, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    request = procurement_v2.create_material_request(
        db, user, payload.item_code, payload.description, payload.uom,
        payload.specification, payload.reason,
    )
    db.commit()
    return workflows.record_to_dict(request)


@app.post("/procurement/material-requests/{request_id}/decision", dependencies=[Depends(csrf_guard)])
def decide_material_request(request_id: str, payload: MaterialMasterDecision, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    request = procurement_v2.decide_material_request(
        db, user, request_id, payload.decision, payload.reason
    )
    db.commit()
    return workflows.record_to_dict(request)
@app.get("/procurement/requirements")
def list_requirements(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.PurchaseRequirement, user)



@app.get("/procurement/requirements/{requirement_id}")
def get_requirement(requirement_id: str, response: Response, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    entity = workflows.get_scoped_or_404(db, models.PurchaseRequirement, user, requirement_id, "Requirement")
    response.headers["ETag"] = etag_for(entity)
    return workflows.requirement_detail(db, user, requirement_id)
@app.post("/procurement/requirements/{requirement_id}/rfqs", dependencies=[Depends(csrf_guard)])
def create_rfq(requirement_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    rfq = workflows.create_rfq_from_requirement(db, user, requirement_id)
    db.commit()
    return rfq


@app.get("/procurement/rfqs")
def list_rfqs(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.RFQ, user)



@app.get("/procurement/rfqs/{rfq_id}")
def get_rfq(rfq_id: str, response: Response, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    entity = workflows.get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    response.headers["ETag"] = etag_for(entity)
    return workflows.rfq_detail(db, user, rfq_id)


@app.patch("/procurement/rfqs/{rfq_id}", dependencies=[Depends(csrf_guard)])
def update_rfq(rfq_id: str, payload: RFQUpdateRequest, request: Request, response: Response, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    current = workflows.get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    require_if_match(request, current)
    rfq = workflows.update_rfq(db, user, rfq_id, payload.model_dump(exclude_none=True))
    db.commit()
    response.headers["ETag"] = etag_for(rfq)
    return rfq
@app.post("/procurement/rfqs/{rfq_id}/publish", dependencies=[Depends(csrf_guard)])
def publish_rfq(rfq_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ"))
    result = workflows.publish_rfq(db, user, rfq_id)
    db.commit()
    return result


@app.post("/procurement/rfqs/{rfq_id}/pdf-preview", dependencies=[Depends(csrf_guard)])
def preview_rfq_pdf(rfq_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_executive", ADMIN)
    artifact = procurement_v2.generate_artifact(db, user, "rfq", rfq_id, final=False)
    db.commit()
    return procurement_v2.artifact_record(db, user, artifact)


@app.get("/procurement/rfqs/{rfq_id}/artifacts")
def rfq_artifacts(rfq_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return procurement_v2.list_artifacts(db, user, "rfq", rfq_id)


@app.get("/procurement/quotes")
def list_quotes(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    quotes = workflows.list_for_user(db, models.SupplierQuote, user)
    return [workflows.scoped_quote_payload(db, user, quote) for quote in quotes]


@app.get("/procurement/exchange-rates")
def list_exchange_rates(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.ExchangeRateObservation, user)


@app.post("/procurement/exchange-rates", dependencies=[Depends(csrf_guard)])
def create_exchange_rate(payload: ExchangeRateCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    result = currency_service.record_rate(db, user, payload.model_dump())
    db.commit()
    return result


@app.post("/procurement/quotes/{quote_id}/exchange-rate", dependencies=[Depends(csrf_guard)])
def apply_quote_exchange_rate(quote_id: str, payload: QuoteExchangeRateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    result = currency_service.apply_rate(db, user, quote_id, payload.observation_id)
    db.commit()
    return workflows.scoped_quote_payload(db, user, result)



@app.post("/procurement/quotes/upload", dependencies=[Depends(csrf_guard)], status_code=202)
async def buyer_quote_upload(
    rfq_id: str = Form(...),
    supplier_id: str = Form(...),
    quote_number: str = Form(""),
    quote_date: str = Form(""),
    validity_date: str = Form(""),
    payment_terms: str = Form("30 days from GRN"),
    currency: str = Form("INR"),
    quantity: float = Form(0),
    unit_price: float = Form(0),
    gst_rate: float = Form(18),
    freight: float = Form(0),
    packaging: float = Form(0),
    lead_time_days: int = Form(0),
    promised_date: str = Form(""),
    moq: float = Form(0),
    technical_compliance: str = Form("compliant"),
    certificates: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    payload = {
        "rfq_id": rfq_id,
        "supplier_id": supplier_id,
        "quote_number": quote_number or None,
        "quote_date": quote_date or None,
        "validity_date": validity_date or None,
        "payment_terms": payment_terms,
        "currency": currency.upper(),
        "line": {
            "quantity": quantity,
            "unit_price": unit_price,
            "gst_rate": gst_rate,
            "freight": freight,
            "packaging": packaging,
            "lead_time_days": lead_time_days,
            "promised_date": promised_date,
            "moq": moq or quantity,
            "technical_compliance": technical_compliance,
            "certificates": [item.strip() for item in certificates.split(",") if item.strip()],
        },
    }
    quote = workflows.receive_buyer_quote(db, user, payload)
    document = None
    if file is not None:
        document = await workflows.upload_document(db, user, file, "supplier_quote", quote.id)
        db.flush()
        manual_intake = models.QuotationIntake(
            tenant_id=user.tenant_id,
            plant_id=user.plant_id,
            mode="manual_comparison",
            status="queued",
            rfq_id=rfq_id,
            document_id=document.id,
            quote_id=quote.id,
            confirmed_supplier_id=supplier_id,
            created_by_user_id=user.id,
            extracted_fields={},
            evidence=[],
            supplier_candidates=[],
        )
        db.add(manual_intake)
        db.flush()
        manual_job = db.query(models.DocumentJob).filter_by(document_id=document.id).order_by(models.DocumentJob.created_at.desc()).first()
        manual_intake.document_job_id = manual_job.id if manual_job else None
    db.commit()
    job = document_service.enqueue_document_job(db, document.id) if document else None
    if document:
        db.refresh(document)
    if job:
        db.refresh(job)
    return {"quote": workflows.quote_detail(db, user, quote.id), "document": workflows.record_to_dict(document), "job": workflows.record_to_dict(job)}


@app.post("/procurement/quotation-intakes", dependencies=[Depends(csrf_guard)], status_code=202)
async def create_quotation_intake(
    rfq_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_role(user, "purchase_executive", "purchase_manager", ADMIN)
    workflows.get_scoped_or_404(db, models.RFQ, user, rfq_id, "RFQ")
    intake = models.QuotationIntake(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        mode="parsed",
        status="queued",
        rfq_id=rfq_id,
        created_by_user_id=user.id,
        extracted_fields={},
        evidence=[],
        supplier_candidates=[],
    )
    db.add(intake)
    db.flush()
    document = await workflows.upload_document(db, user, file, "quotation_intake", intake.id)
    db.flush()
    job = db.query(models.DocumentJob).filter_by(document_id=document.id).order_by(models.DocumentJob.created_at.desc()).first()
    intake.document_id = document.id
    intake.document_job_id = job.id if job else None
    db.commit()
    if job:
        document_service.enqueue_document_job(db, document.id)
        db.refresh(intake)
    return quotation_intake_service.intake_payload(db, intake)


@app.get("/procurement/quotation-intakes/{intake_id}")
def get_quotation_intake(
    intake_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_read_role(user, "procurement")
    intake = workflows.get_scoped_or_404(db, models.QuotationIntake, user, intake_id, "Quotation intake")
    return quotation_intake_service.intake_payload(db, intake)


@app.post("/procurement/quotation-intakes/{intake_id}/accept", dependencies=[Depends(csrf_guard)])
def accept_quotation_intake(
    intake_id: str,
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    intake = workflows.get_scoped_or_404(db, models.QuotationIntake, user, intake_id, "Quotation intake")
    require_if_match(request, intake)
    intake, quote = quotation_intake_service.accept_intake(db, user, intake_id, payload)
    db.commit()
    return {"intake": quotation_intake_service.intake_payload(db, intake), "quote": workflows.quote_detail(db, user, quote.id)}


@app.post("/procurement/quotation-intakes/{intake_id}/retry", dependencies=[Depends(csrf_guard)], status_code=202)
def retry_quotation_intake(
    intake_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    intake = workflows.get_scoped_or_404(db, models.QuotationIntake, user, intake_id, "Quotation intake")
    require_if_match(request, intake)
    if intake.status == "accepted":
        raise HTTPException(409, "Accepted quotation intake cannot be retried")
    existing = db.get(models.DocumentJob, intake.document_job_id) if intake.document_job_id else None
    if existing and existing.status in {"queued", "processing"}:
        return quotation_intake_service.intake_payload(db, intake)
    job = models.DocumentJob(
        tenant_id=intake.tenant_id,
        plant_id=intake.plant_id,
        document_id=str(intake.document_id),
        job_type="validate_extract",
        status="queued",
    )
    db.add(job)
    db.flush()
    intake.document_job_id = job.id
    intake.status = "queued"
    intake.error_code = None
    intake.error_detail = None
    db.commit()
    document_service.enqueue_document_job(db, str(intake.document_id))
    db.refresh(intake)
    return quotation_intake_service.intake_payload(db, intake)


@app.get("/procurement/quotes/{quote_id}")
def get_quote(quote_id: str, response: Response, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    entity = workflows.get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote")
    response.headers["ETag"] = etag_for(entity)
    return workflows.quote_detail(db, user, quote_id)


@app.get("/procurement/quotes/{quote_id}/verifications")
def get_quote_verifications(quote_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.quote_field_verifications(db, user, quote_id)
@app.post("/procurement/quotes/{quote_id}/verify", dependencies=[Depends(csrf_guard)])
def verify_quote(quote_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote"))
    quote = workflows.verify_quote(db, user, quote_id)
    db.commit()
    return quote


@app.get("/procurement/comparisons/{rfq_id}")
def get_comparison(rfq_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    try:
        return workflows.compare_quotes(db, rfq_id, user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/procurement/negotiations")
def list_negotiations(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.NegotiationRound, user)


@app.get("/procurement/awards")
def list_awards(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.AwardDecision, user)



@app.post("/procurement/awards", dependencies=[Depends(csrf_guard)])
def create_award(payload: AwardCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    award = workflows.create_award_decision(db, user, payload.rfq_id, payload.quote_id, payload.supplier_id, payload.rationale)
    db.commit()
    return award
@app.post("/procurement/awards/{award_id}/approve", dependencies=[Depends(csrf_guard)])
def approve_award(award_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.AwardDecision, user, award_id, "Award"))
    award = workflows.approve_award(db, user, award_id)
    db.commit()
    return award


@app.post("/procurement/awards/{award_id}/reject", dependencies=[Depends(csrf_guard)])
def reject_award(award_id: str, payload: DecisionRationaleRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.AwardDecision, user, award_id, "Award"))
    award = workflows.reject_award(db, user, award_id, payload.rationale)
    db.commit()
    return award


@app.get("/procurement/po-drafts")
def list_po_drafts(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "po")
    return workflows.list_for_user(db, models.PODraft, user)



@app.post("/procurement/po-drafts", dependencies=[Depends(csrf_guard)])
def create_po_draft(payload: PODraftCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    po = workflows.create_po_draft_from_award_request(db, user, payload.award_id)
    db.commit()
    return po


@app.get("/procurement/po-drafts/{po_draft_id}")
def get_po_draft(po_draft_id: str, response: Response, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    entity = workflows.get_scoped_or_404(db, models.PODraft, user, po_draft_id, "PO draft")
    response.headers["ETag"] = etag_for(entity)
    return workflows.po_draft_detail(db, user, po_draft_id)


@app.post("/procurement/po-drafts/{po_draft_id}/pdf-preview", dependencies=[Depends(csrf_guard)])
def preview_po_pdf(po_draft_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", ADMIN)
    artifact = procurement_v2.generate_artifact(db, user, "po", po_draft_id, final=False)
    db.commit()
    return procurement_v2.artifact_record(db, user, artifact)


@app.get("/procurement/po-drafts/{po_draft_id}/artifacts")
def po_artifacts(po_draft_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "po")
    return procurement_v2.list_artifacts(db, user, "po", po_draft_id)


@app.post("/procurement/po-drafts/{po_draft_id}/supplier-email", dependencies=[Depends(csrf_guard)])
def prepare_po_supplier_email(po_draft_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    message = procurement_v2.prepare_po_supplier_email(db, user, po_draft_id)
    db.commit()
    return workflows.record_to_dict(message)


@app.post("/procurement/po-drafts/{po_draft_id}/approve", dependencies=[Depends(csrf_guard)])
def approve_po(po_draft_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.PODraft, user, po_draft_id, "PO draft"))
    po = workflows.approve_po_draft(db, user, po_draft_id)
    procurement_v2.generate_artifact(db, user, "po", po.id, final=True)
    db.commit()
    return po


@app.post("/procurement/po-drafts/{po_draft_id}/changes", dependencies=[Depends(csrf_guard)])
def prepare_po_change(po_draft_id: str, payload: POChangeRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.PODraft, user, po_draft_id, "Purchase order"))
    revision = procurement_v2.prepare_po_change(
        db, user, po_draft_id, payload.change_type, payload.reason,
        [line.model_dump(exclude_none=True) for line in payload.lines], payload.acknowledgement_id,
    )
    db.commit()
    return workflows.po_draft_payload(db, user, revision)


@app.post("/procurement/po-drafts/{revision_id}/approve-change", dependencies=[Depends(csrf_guard)])
def approve_po_change(revision_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.PODraft, user, revision_id, "Purchase-order change"))
    revision = procurement_v2.approve_po_change(db, user, revision_id)
    db.commit()
    return workflows.po_draft_payload(db, user, revision)


@app.get("/inbound/gate-entries")
def gate_entries(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "inbound")
    return workflows.list_for_user(db, models.GateEntry, user)


@app.get("/inbound/receipts")
def receipts(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "inbound")
    return workflows.list_for_user(db, models.StoreReceipt, user)


@app.post("/inbound/receipts", dependencies=[Depends(csrf_guard)])
def record_receipt(payload: ReceiptRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    receipt = workflows.record_receipt(
        db, user, payload.po_draft_id, payload.received_quantity, payload.damaged_quantity,
        payload.observed_item_code, payload.certificate_status, payload.exception_notes,
        payload.production_impact,
    )
    db.commit()
    return receipt


@app.get("/inbound/inspections")
def inspections(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "inbound")
    return workflows.list_for_user(db, models.InspectionResult, user)


@app.post("/inbound/inspections", dependencies=[Depends(csrf_guard)])
def record_inspection(payload: InspectionRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    inspection = workflows.record_inspection(
        db, user, payload.receipt_id, payload.inspected_quantity, payload.accepted_quantity,
        payload.rejected_quantity, payload.held_quantity, payload.certificate_status,
        payload.defect_codes, payload.inspection_notes, payload.production_impact,
    )
    db.commit()
    return inspection


@app.get("/quality/supplier-returns")
def supplier_returns(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "quality")
    return workflows.list_for_user(db, models.SupplierReturn, user)


@app.post("/quality/supplier-returns", dependencies=[Depends(csrf_guard)])
def create_supplier_return(payload: SupplierReturnCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    result = workflows.create_supplier_return(db, user, payload.inspection_id, payload.return_quantity, payload.reason)
    db.commit()
    return result


@app.post("/quality/supplier-returns/{supplier_return_id}/request-replacement", dependencies=[Depends(csrf_guard)])
def request_supplier_replacement(supplier_return_id: str, payload: ReplacementRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    result = workflows.request_supplier_replacement(db, user, supplier_return_id, payload.replacement_quantity, payload.requested_delivery)
    db.commit()
    return result


@app.post("/quality/supplier-returns/{supplier_return_id}/receive", dependencies=[Depends(csrf_guard)])
def receive_supplier_replacement(supplier_return_id: str, payload: ReplacementReceiptRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    receipt = workflows.record_replacement_receipt(
        db, user, supplier_return_id, payload.received_quantity, payload.supplier_challan,
        payload.vehicle_number, payload.packages_count,
    )
    db.commit()
    return receipt


@app.get("/inbound/inventory-impact")
def inventory_impact(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.list_for_user(db, models.InventoryImpact, user)


@app.post("/documents/upload", dependencies=[Depends(csrf_guard)], status_code=202)
async def document_upload(
    file: UploadFile = File(...),
    linked_entity_type: str | None = Form(None),
    linked_entity_id: str | None = Form(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    document = await workflows.upload_document(db, user, file, linked_entity_type, linked_entity_id)
    db.commit()
    job = document_service.enqueue_document_job(db, document.id)
    db.refresh(document)
    if job:
        db.refresh(job)
    return {"document": workflows.record_to_dict(document), "job": workflows.record_to_dict(job)}


@app.get("/documents")
def documents(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "documents")
    return workflows.list_for_user(db, models.Document, user)


@app.get("/documents/{document_id}")
def document_detail(document_id: str, response: Response, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "documents")
    document = workflows.get_scoped_or_404(db, models.Document, user, document_id, "Document")
    response.headers["ETag"] = etag_for(document)
    job = workflows.user_scope_query(db, models.DocumentJob, user).filter(models.DocumentJob.document_id == document.id).order_by(models.DocumentJob.created_at.desc()).first()
    validations = workflows.user_scope_query(db, models.DocumentValidationResult, user).filter(models.DocumentValidationResult.document_id == document.id).all()
    extractions = workflows.user_scope_query(db, models.QuoteExtractionRun, user).filter(models.QuoteExtractionRun.document_id == document.id).all()
    invoice_extractions = workflows.user_scope_query(db, models.InvoiceExtractionRun, user).filter(models.InvoiceExtractionRun.document_id == document.id).all()
    return {"document": workflows.record_to_dict(document), "job": workflows.record_to_dict(job), "validations": workflows.records_to_dicts(validations), "extractions": workflows.records_to_dicts(extractions), "invoice_extractions": workflows.records_to_dicts(invoice_extractions)}


@app.get("/documents/{document_id}/validation")
def document_validation(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "documents")
    document = workflows.get_scoped_or_404(db, models.Document, user, document_id, "Document")
    return workflows.records_to_dicts(workflows.user_scope_query(db, models.DocumentValidationResult, user).filter(models.DocumentValidationResult.document_id == document.id).all())


@app.get("/documents/{document_id}/download-url")
def document_url(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.document_download_url(db, user, document_id)


@app.get("/documents/{document_id}/content")
def document_content(document_id: str, token: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    document, content = document_service.verified_local_content(db, user, document_id, token)
    disposition = "inline" if document.content_type == "application/pdf" else "attachment"
    safe_filename = document.filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/documents/{document_id}/reprocess", dependencies=[Depends(csrf_guard)], status_code=202)
def reprocess_document(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", ADMIN)
    document = workflows.get_scoped_or_404(db, models.Document, user, document_id, "Document")
    job = models.DocumentJob(id=workflows.next_id(db, models.DocumentJob, "DJOB"), tenant_id=user.tenant_id, plant_id=user.plant_id, document_id=document.id, status="queued")
    db.add(job)
    document.status = "quarantined"
    db.commit()
    document_service.enqueue_document_job(db, document.id)
    return {"document_id": document.id, "job_id": job.id, "status": job.status}


@app.get("/integrations/outbox")
def get_outbox(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    events = workflows.list_for_user(db, models.IntegrationOutboxEvent, user)
    emails = workflows.list_for_user(db, models.OutboxMessage, user)
    return [
        {**(workflows.record_to_dict(event) or {}), "outbox_type": "erp"}
        for event in events
    ] + [
        {**(workflows.record_to_dict(message) or {}), "outbox_type": "email"}
        for message in emails
    ]


@app.get("/integrations/outbox/erp")
def get_erp_outbox(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    return workflows.list_for_user(db, models.IntegrationOutboxEvent, user)


@app.get("/integrations/outbox/email")
def get_email_outbox(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    return workflows.list_for_user(db, models.OutboxMessage, user)


@app.get("/integrations/supplier-messages")
def get_supplier_channel_messages(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    return workflows.list_for_user(db, models.SupplierChannelMessage, user)


@app.post("/integrations/email/inbound/simulate", dependencies=[Depends(csrf_guard)])
def simulate_inbound_supplier_email(payload: InboundSupplierEmailRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", "purchase_executive", ADMIN)
    from app.integrations import process_inbound_supplier_email
    try:
        message, records = process_inbound_supplier_email(db, user, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {"message_id": message.id, "status": message.status, "rfq_id": message.rfq_id, "supplier_id": message.supplier_id, "records": records, "quotes": records if payload.message_type == "quotation" else []}


@app.post("/integrations/email/{outbox_id}/send", dependencies=[Depends(csrf_guard)])
def send_email(outbox_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", ADMIN)
    outbox = workflows.get_scoped_or_404(db, models.OutboxMessage, user, outbox_id, "Email outbox message")
    require_if_match(request, outbox)
    if outbox.channel != "email":
        raise HTTPException(status_code=404, detail="Email outbox message not found")
    if outbox.status not in {"approved_pending_send", "failed"}:
        raise HTTPException(status_code=409, detail="Email is not approved for sending")
    outbox.status = "sending"
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "email.send_queued", "outbox_message", outbox.id, actor_user_id=user.id)
    db.commit()
    from app.workers import send_email as send_email_task
    task = send_email_task.apply_async(args=[outbox.id], queue="email")
    return {"message_id": outbox.id, "job_id": task.id, "status": "queued"}


@app.get("/integrations/imports/master-data")
def import_master_data(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return erp_adapter.import_master_data(db, user.tenant_id, user.plant_id)


@app.get("/integrations/excel/manifest")
def excel_connector_manifest(user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    return excel_connector.connector_manifest()


@app.post("/integrations/excel/preview", dependencies=[Depends(csrf_guard)])
async def preview_excel_import(
    file: UploadFile = File(...), mapping_profile_id: str | None = Form(None), db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_role(user, ADMIN)
    filename = file.filename or "external-system.xlsx"
    settings = workflows.get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "External-system file exceeds the upload limit")
    discovery = excel_connector.discover(filename, content)
    workflows.ensure_default_connections(db, user)
    db.flush()
    connection = workflows.user_scope_query(db, models.IntegrationConnection, user).filter(
        models.IntegrationConnection.provider == "local",
    ).first()
    if connection is None:
        raise HTTPException(409, "Excel connector is not configured")
    mapping_profile = None
    if mapping_profile_id:
        mapping_profile = workflows.get_scoped_or_404(db, models.IntegrationMappingProfile, user, mapping_profile_id, "Mapping profile")
        if mapping_profile.connection_id != connection.id or mapping_profile.status != "active":
            raise HTTPException(422, "Choose an active mapping profile for this connection")
    import hashlib
    import io
    import secrets
    from app.storage import object_storage
    key = f"{user.tenant_id}/{user.plant_id}/excel-imports/{secrets.token_hex(12)}-{filename}"
    object_storage.put_file(settings.object_storage_evidence_bucket, key, io.BytesIO(content), file.content_type or "application/octet-stream")
    document = models.Document(
        id=workflows.next_id(db, models.Document, "DOC"), business_number=workflows.next_business_number(db, "DOC", user),
        tenant_id=user.tenant_id, plant_id=user.plant_id, filename=filename,
        content_type=file.content_type or "application/octet-stream", size_bytes=len(content),
        storage_key=key, storage_bucket=settings.object_storage_evidence_bucket,
        checksum_sha256=hashlib.sha256(content).hexdigest(), status="validated_import",
        validation_errors=[], linked_entity_type="integration_import", uploaded_by_user_id=user.id,
    )
    db.add(document)
    db.flush()
    batch = excel_connector.preview_import(db, user, connection, filename, content, document_id=document.id, mapping_profile=mapping_profile)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "excel_import.previewed", "integration_import_batch", batch.id, actor_user_id=user.id, meta={"source_hash": discovery["source_hash"], "summary": batch.summary})
    issues = workflows.user_scope_query(db, models.IntegrationImportRowResult, user).filter(
        models.IntegrationImportRowResult.batch_id == batch.id,
        models.IntegrationImportRowResult.action.in_(["error", "conflict"]),
    ).order_by(models.IntegrationImportRowResult.sheet_name, models.IntegrationImportRowResult.row_number).limit(100).all()
    db.commit()
    return {"batch_id": batch.id, "status": batch.status, "summary": batch.summary, "discovery": batch.discovery, "row_issues": [{"sheet": row.sheet_name, "row": row.row_number, "external_key": row.external_key, "action": row.action, "messages": row.validation_messages} for row in issues]}


@app.get("/integrations/excel/mapping-profiles")
def list_excel_mapping_profiles(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    return workflows.list_for_user(db, models.IntegrationMappingProfile, user)


@app.post("/integrations/excel/mapping-profiles", dependencies=[Depends(csrf_guard)])
def create_excel_mapping_profile(payload: MappingProfileRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    connection = workflows.get_scoped_or_404(db, models.IntegrationConnection, user, payload.connection_id, "Integration connection")
    excel_connector.validate_mapping_contract(payload.mappings, payload.transforms)
    previous = workflows.user_scope_query(db, models.IntegrationMappingProfile, user).filter_by(
        connection_id=connection.id, name=payload.name,
    ).order_by(models.IntegrationMappingProfile.profile_version.desc()).first()
    if previous:
        previous.status = "superseded"
    profile = models.IntegrationMappingProfile(
        tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id,
        name=payload.name, profile_version=(previous.profile_version + 1 if previous else 1),
        workbook_schema_version=payload.workbook_schema_version, mappings=payload.mappings,
        transforms=payload.transforms, ownership=payload.ownership, status="active",
    )
    db.add(profile)
    db.flush()
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "excel_mapping.version_created", "integration_mapping_profile", profile.id, actor_user_id=user.id, meta={"name": profile.name, "version": profile.profile_version})
    db.commit()
    return profile


@app.get("/integrations/excel/imports/{batch_id}")
def excel_import_detail(batch_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    batch = workflows.get_scoped_or_404(db, models.IntegrationImportBatch, user, batch_id, "Import batch")
    rows = workflows.user_scope_query(db, models.IntegrationImportRowResult, user).filter_by(batch_id=batch.id).order_by(models.IntegrationImportRowResult.sheet_name, models.IntegrationImportRowResult.row_number).all()
    return {"batch": batch, "rows": rows}


@app.get("/integrations/excel/imports/{batch_id}/reconciliation.csv")
def download_excel_import_reconciliation(batch_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    batch = workflows.get_scoped_or_404(db, models.IntegrationImportBatch, user, batch_id, "Import batch")
    content = excel_connector.import_reconciliation_report(db, user, batch)
    return Response(
        content=content, media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="import-reconciliation-{batch.business_number or batch.id}.csv"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/integrations/excel/imports/{batch_id}/approve", dependencies=[Depends(csrf_guard)])
def approve_excel_import(batch_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    batch = workflows.get_scoped_or_404(db, models.IntegrationImportBatch, user, batch_id, "Import batch")
    batch = excel_connector.commit_import(db, user, batch)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "excel_import.committed", "integration_import_batch", batch.id, actor_user_id=user.id, meta={"summary": batch.summary})
    db.commit()
    return {"batch_id": batch.id, "status": batch.status, "summary": batch.summary}


@app.post("/integrations/excel/export", dependencies=[Depends(csrf_guard)])
def export_excel_external_system(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", ADMIN)
    result = excel_connector.create_exchange_export(db, user)
    db.commit()
    return result


@app.post("/integrations/imports/master-data", dependencies=[Depends(csrf_guard)], status_code=202)
async def queue_master_data_import(file: UploadFile = File(...), db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Master data import requires CSV")
    settings = workflows.get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Import exceeds upload limit")
    import hashlib
    import io
    import secrets
    from app.storage import object_storage
    key = f"{user.tenant_id}/{user.plant_id}/imports/{secrets.token_hex(12)}-{file.filename}"
    object_storage.put_file(settings.object_storage_evidence_bucket, key, io.BytesIO(content), "text/csv")
    document = models.Document(id=workflows.next_id(db, models.Document, "DOC"), business_number=workflows.next_business_number(db, "DOC", user), tenant_id=user.tenant_id, plant_id=user.plant_id, filename=file.filename or "master-data.csv", content_type="text/csv", size_bytes=len(content), storage_key=key, storage_bucket=settings.object_storage_evidence_bucket, checksum_sha256=hashlib.sha256(content).hexdigest(), status="validated_import", validation_errors=[], linked_entity_type="integration_import", uploaded_by_user_id=user.id)
    workflows.ensure_default_connections(db, user)
    db.flush()
    connection = workflows.user_scope_query(db, models.IntegrationConnection, user).filter(models.IntegrationConnection.provider == "local").first()
    job = models.IntegrationSyncJob(id=workflows.next_id(db, models.IntegrationSyncJob, "SYNC"), business_number=workflows.next_business_number(db, "SYNC", user), tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id, job_type="master_data_import", status="queued", summary={"document_id": document.id})
    db.add_all([document, job])
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "master_data_import.queued", "integration_sync_job", job.id, actor_user_id=user.id)
    db.commit()
    from app.workers import import_master_data as import_task
    task = import_task.apply_async(args=[job.id, document.id], queue="sync")
    return {"job_id": job.id, "document_id": document.id, "celery_task_id": task.id, "status": job.status}


@app.get("/integrations/imports/open-pos")
def import_open_pos(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return erp_adapter.import_open_pos(db, user.tenant_id, user.plant_id)


@app.get("/integrations/imports/receipts")
def import_receipts(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return erp_adapter.import_receipts(db, user.tenant_id, user.plant_id)


@app.get("/integrations/imports/inspections")
def import_inspections(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return erp_adapter.import_inspections(db, user.tenant_id, user.plant_id)


@app.get("/integrations/events/po-posting/{po_draft_id}")
def simulate_po_posting(po_draft_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    try:
        return erp_adapter.simulate_po_posting(db, po_draft_id, user.tenant_id, user.plant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/agents/actions", dependencies=[Depends(csrf_guard)])
def agent_action(request: AgentActionRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    response = workflows.run_agent_action(db, request, user)
    db.commit()
    return response






@app.post("/procurement/requirements", dependencies=[Depends(csrf_guard)])
def create_requirement(payload: RequirementRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    lines = [line.model_dump() for line in payload.lines]
    if not lines and (not payload.item_id or payload.quantity is None or not payload.need_by_date):
        raise HTTPException(status_code=422, detail="Provide at least one requirement line")
    requirement = workflows.create_requirement(db, user, payload.item_id or lines[0]['item_id'], payload.quantity or lines[0]['quantity'], payload.need_by_date or lines[0]['need_by_date'], payload.source, payload.uom, payload.title, lines=lines or None, reason=payload.reason, assignee_membership_id=payload.assignee_membership_id)
    task = db.query(models.Task).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        entity_type='purchase_requirements', entity_id=requirement.id,
    ).first()
    assignment = {
        'membership_id': requirement.owner_membership_id,
        'task_id': task.id if task else None,
        'owner_user_id': requirement.owner_user_id,
        'status': task.acceptance_status if task else 'assigned',
    }
    db.commit()
    return {**workflows.record_to_dict(requirement), 'assignment': assignment}


@app.post("/supplier/rfqs/{token}/quotes")
def supplier_submit_quote(token: str, payload: SupplierQuoteRequest, db: Session = Depends(get_db)):
    quote = workflows.receive_supplier_quote(db, token, payload.model_dump(exclude_none=True))
    db.commit()
    return quote


@app.get("/supplier/rfqs/{token}")
def supplier_rfq_context(token: str, db: Session = Depends(get_db)):
    portal_token = workflows.get_supplier_portal_token(db, token)
    if portal_token.purpose != "rfq_quote" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier RFQ link is invalid or expired")
    rfq = db.query(models.RFQ).filter_by(
        id=portal_token.entity_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
    ).first()
    if not rfq or portal_token.supplier_id not in (rfq.supplier_ids or []):
        raise HTTPException(404, "Supplier request not found")
    lines = db.query(models.RFQLine).filter_by(tenant_id=rfq.tenant_id, plant_id=rfq.plant_id, rfq_id=rfq.id).all()
    invitation = db.query(models.RFQSupplierInvitation).filter_by(
        tenant_id=rfq.tenant_id, plant_id=rfq.plant_id, rfq_id=rfq.id, supplier_id=portal_token.supplier_id,
    ).first()
    artifact = db.query(models.GeneratedArtifact).filter_by(
        tenant_id=rfq.tenant_id, plant_id=rfq.plant_id, entity_id=rfq.id,
        artifact_type="rfq", status="final",
    ).order_by(models.GeneratedArtifact.artifact_version.desc()).first()
    return {"supplier_request": {"business_number": rfq.business_number, "status": rfq.status, "deadline": rfq.deadline, "document_available": artifact is not None}, "lines": workflows.records_to_dicts(lines), "response_status": invitation.status if invitation else "unknown", "expires_at": portal_token.expires_at}


@app.get("/supplier/rfqs/{token}/document")
def supplier_rfq_document(token: str, db: Session = Depends(get_db)):
    portal_token = workflows.get_supplier_portal_token(db, token)
    if portal_token.purpose != "rfq_quote" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier RFQ link is invalid or expired")
    artifact = db.query(models.GeneratedArtifact).filter_by(
        tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        entity_id=portal_token.entity_id, artifact_type="rfq", status="final",
    ).order_by(models.GeneratedArtifact.artifact_version.desc()).first()
    if not artifact:
        raise HTTPException(404, "Final supplier-request document is not available")
    document = db.query(models.Document).filter_by(
        id=artifact.document_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
    ).first()
    if not document or document.content_type != "application/pdf":
        raise HTTPException(404, "Final supplier-request document is not available")
    content = document_service.object_storage.get_bytes(document.storage_bucket, document.storage_key)
    safe_filename = document.filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{safe_filename}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@app.post("/supplier/rfqs/{token}/no-bid")
def supplier_no_bid(token: str, payload: SupplierNoBidRequest, db: Session = Depends(get_db)):
    invitation = workflows.receive_supplier_no_bid(db, token, payload.reason)
    db.commit()
    return invitation


@app.post("/supplier/rfqs/{token}/quotes/evidence", status_code=202)
async def supplier_upload_quote_evidence(
    token: str, file: UploadFile = File(...), db: Session = Depends(get_db),
):
    portal_token = workflows.get_supplier_portal_token(db, token)
    if portal_token.purpose != "rfq_quote" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier RFQ link is invalid or expired")
    quote = db.query(models.SupplierQuote).filter_by(
        tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
        rfq_id=portal_token.entity_id, supplier_id=portal_token.supplier_id,
    ).filter(models.SupplierQuote.verification_status != "superseded").order_by(
        models.SupplierQuote.revision_number.desc(),
    ).first()
    if not quote:
        raise HTTPException(409, "Submit quotation values before uploading supporting evidence")
    document, _job = await document_service.create_supplier_portal_upload(
        db, quote, file, "supplier_quote", quote.id,
    )
    db.commit()
    job = document_service.enqueue_document_job(db, document.id)
    db.refresh(document)
    if job: db.refresh(job)
    return {"document": workflows.record_to_dict(document), "job": workflows.record_to_dict(job), "quote": workflows.record_to_dict(quote)}



@app.post("/supplier/rfqs/{token}/quotes/upload", status_code=202)
async def supplier_submit_quote_upload(
    token: str,
    quote_number: str = Form(""),
    quote_date: str = Form(""),
    validity_date: str = Form(""),
    payment_terms: str = Form("30 days from GRN"),
    quantity: float = Form(0),
    unit_price: float = Form(0),
    gst_rate: float = Form(18),
    freight: float = Form(0),
    packaging: float = Form(0),
    lead_time_days: int = Form(0),
    promised_date: str = Form(""),
    moq: float = Form(0),
    technical_compliance: str = Form("compliant"),
    certificates: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    payload = {
        "quote_number": quote_number or None,
        "quote_date": quote_date or None,
        "validity_date": validity_date or None,
        "payment_terms": payment_terms,
        "line": {
            "quantity": quantity,
            "unit_price": unit_price,
            "gst_rate": gst_rate,
            "freight": freight,
            "packaging": packaging,
            "lead_time_days": lead_time_days,
            "promised_date": promised_date,
            "moq": moq or quantity,
            "technical_compliance": technical_compliance,
            "certificates": [item.strip() for item in certificates.split(",") if item.strip()],
        },
    }
    quote = workflows.receive_supplier_quote(db, token, payload)
    document = None
    if file is not None:
        document = await workflows.stream_supplier_document(db, quote, file)
    db.commit()
    job = document_service.enqueue_document_job(db, document.id) if document else None
    return {"quote_id": quote.id, "document_id": document.id if document else None, "job_id": job.id if job else None, "status": quote.verification_status}
@app.post("/procurement/quotes/{quote_id}/verify-fields", dependencies=[Depends(csrf_guard)])
def verify_quote_fields(quote_id: str, payload: VerifyFieldsRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Quote"))
    decisions = [decision.model_dump() for decision in payload.decisions]
    if payload.fields:
        decisions.extend({"field_name": field, "decision": "correct", "verified_value": value} for field, value in payload.fields.items())
    quote = workflows.verify_quote_fields(db, user, quote_id, decisions)
    db.commit()
    return quote


@app.post("/procurement/comparisons/{rfq_id}/generate", dependencies=[Depends(csrf_guard)])
def generate_comparison(rfq_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    comparison = workflows.generate_comparison(db, user, rfq_id)
    db.commit()
    return comparison


@app.get("/procurement/comparison-records")
def list_comparison_records(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.BidComparison, user)


@app.post("/procurement/comparison-records/{comparison_id}/pdf-preview", dependencies=[Depends(csrf_guard)])
def preview_comparison_pdf(comparison_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", ADMIN)
    artifact = procurement_v2.generate_artifact(db, user, "comparison", comparison_id, final=False)
    db.commit()
    return procurement_v2.artifact_record(db, user, artifact)


@app.get("/procurement/comparison-records/{comparison_id}/artifacts")
def comparison_artifacts(comparison_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return procurement_v2.list_artifacts(db, user, "comparison", comparison_id)


@app.get("/procurement/comparison-records/{comparison_id}/approvals")
def comparison_approvals(comparison_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    workflows.get_scoped_or_404(db, models.BidComparison, user, comparison_id, "Comparison")
    approvals = workflows.user_scope_query(db, models.ComparisonApprovalRequest, user).filter_by(
        comparison_id=comparison_id
    ).order_by(models.ComparisonApprovalRequest.comparison_version.desc()).all()
    return workflows.records_to_dicts(approvals)


@app.get("/procurement/policies")
def list_procurement_policies(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.records_to_dicts(
        workflows.user_scope_query(db, models.ProcurementPolicy, user).order_by(
            models.ProcurementPolicy.created_at.desc()
        ).all()
    )


@app.post("/procurement/policies", dependencies=[Depends(csrf_guard)])
def create_procurement_policy(payload: ProcurementPolicyCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    policy = procurement_policy.create_policy(db, user, payload.name, payload.rules.model_dump())
    db.commit()
    return workflows.record_to_dict(policy)


@app.post("/procurement/policies/{policy_id}/activate", dependencies=[Depends(csrf_guard)])
def activate_procurement_policy(policy_id: str, payload: ProcurementPolicyActivateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    del payload
    policy = procurement_policy.activate_policy(db, user, policy_id)
    db.commit()
    return workflows.record_to_dict(policy)


@app.get("/procurement/comparison-records/{comparison_id}/policy-evaluation")
def comparison_policy_evaluation(comparison_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    comparison = workflows.get_scoped_or_404(db, models.BidComparison, user, comparison_id, "Comparison")
    return procurement_policy.evaluate_comparison(db, user, comparison, persist=False)


@app.post("/procurement/comparison-records/{comparison_id}/submit", dependencies=[Depends(csrf_guard)])
def submit_comparison(comparison_id: str, payload: ComparisonSubmitRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    comparison = procurement_v2.submit_comparison(
        db, user, comparison_id, payload.recommendation_rationale
    )
    db.commit()
    return workflows.record_to_dict(comparison)


@app.post("/procurement/comparison-records/{comparison_id}/decision", dependencies=[Depends(csrf_guard)])
def decide_comparison(comparison_id: str, payload: ComparisonDecisionRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    comparison = procurement_v2.decide_comparison(
        db, user, comparison_id, payload.decision, payload.rationale
    )
    db.commit()
    return workflows.record_to_dict(comparison)


@app.post("/procurement/comparison-records/{comparison_id}/confirm-po", dependencies=[Depends(csrf_guard)])
def confirm_comparison_po(comparison_id: str, payload: POConfirmRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    del payload
    po, artifact = procurement_v2.confirm_purchase_order(db, user, comparison_id)
    db.commit()
    return {
        "po": workflows.record_to_dict(po),
        "artifact": procurement_v2.artifact_record(db, user, artifact),
        "supplier_sent": False,
        "erp_posted": False,
    }


@app.post("/procurement/comparison-records/{comparison_id}/confirm-split-award", dependencies=[Depends(csrf_guard)])
def confirm_split_award(comparison_id: str, payload: SplitAwardConfirmRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    batch, purchase_orders = procurement_v2.confirm_split_purchase_orders(
        db, user, comparison_id, [allocation.model_dump() for allocation in payload.allocations],
    )
    db.commit()
    return {
        "award_batch": workflows.record_to_dict(batch),
        "purchase_orders": [workflows.po_draft_payload(db, user, po) for po in purchase_orders],
        "supplier_sent": False,
        "erp_posted": False,
    }


@app.post("/procurement/negotiations", dependencies=[Depends(csrf_guard)])
def create_negotiation(payload: NegotiationRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    negotiation = workflows.create_negotiation(db, user, payload.rfq_id, payload.supplier_id, payload.target, payload.drafted_message)
    db.commit()
    return negotiation


@app.post("/procurement/negotiations/{negotiation_id}/submit", dependencies=[Depends(csrf_guard)])
def submit_negotiation(negotiation_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation"))
    negotiation = workflows.submit_negotiation(db, user, negotiation_id)
    db.commit()
    return negotiation


@app.post("/procurement/negotiations/{negotiation_id}/approve", dependencies=[Depends(csrf_guard)])
def approve_negotiation(negotiation_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation"))
    negotiation = workflows.approve_negotiation(db, user, negotiation_id)
    db.commit()
    return negotiation


@app.post("/procurement/negotiations/{negotiation_id}/counteroffer", dependencies=[Depends(csrf_guard)])
def counteroffer_negotiation(negotiation_id: str, payload: NegotiationCounterofferRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation"))
    negotiation = workflows.record_negotiation_counteroffer(db, user, negotiation_id, payload.revised_unit_price, payload.message, payload.commercial_terms)
    db.commit()
    return negotiation


@app.post("/procurement/negotiations/{negotiation_id}/accept", dependencies=[Depends(csrf_guard)])
def accept_negotiation(negotiation_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.NegotiationRound, user, negotiation_id, "Negotiation"))
    negotiation = workflows.accept_negotiation(db, user, negotiation_id)
    db.commit()
    return negotiation


@app.get("/inbound/asns")
def asns(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.list_for_user(db, models.ASN, user)


@app.get("/inbound/delivery-updates")
def supplier_delivery_updates(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "inbound")
    return workflows.list_for_user(db, models.SupplierDeliveryUpdate, user)


@app.get("/inbound/acknowledgements")
def acknowledgements(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "inbound")
    return workflows.list_for_user(db, models.SupplierAcknowledgement, user)


@app.post("/supplier/pos/{token}/acknowledgements")
def supplier_acknowledge_po(token: str, payload: SupplierAcknowledgementRequest, db: Session = Depends(get_db)):
    acknowledgement = workflows.receive_supplier_acknowledgement(db, token, payload.status, payload.confirmed_quantity, payload.confirmed_delivery, payload.notes)
    db.commit()
    return acknowledgement


@app.get("/supplier/pos/{token}")
def supplier_po_context(token: str, db: Session = Depends(get_db)):
    portal_token = workflows.get_supplier_portal_token(db, token)
    if portal_token.purpose != "po_acknowledgement" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier PO link is invalid or expired")
    po = db.query(models.PODraft).filter_by(id=portal_token.entity_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id, supplier_id=portal_token.supplier_id).first()
    if not po:
        raise HTTPException(404, "Purchase order not found")
    lines = db.query(models.PODraftLine).filter_by(tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id).all()
    acknowledgement = db.query(models.SupplierAcknowledgement).filter_by(tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id).order_by(models.SupplierAcknowledgement.created_at.desc()).first()
    asns = db.query(models.ASN).filter_by(tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id, source="supplier_portal").all()
    delivery_rows = []
    for asn in asns:
        updates = db.query(models.SupplierDeliveryUpdate).filter_by(
            tenant_id=po.tenant_id, plant_id=po.plant_id, asn_id=asn.id,
        ).order_by(models.SupplierDeliveryUpdate.submitted_at.asc()).all()
        delivery_rows.append({**(workflows.record_to_dict(asn) or {}), "updates": workflows.records_to_dicts(updates)})
    final_artifact = db.query(models.GeneratedArtifact).filter(
        models.GeneratedArtifact.tenant_id == po.tenant_id,
        models.GeneratedArtifact.plant_id == po.plant_id,
        models.GeneratedArtifact.entity_id == po.id,
        models.GeneratedArtifact.status == "final",
        models.GeneratedArtifact.artifact_type.in_(["po", "po_pdf"]),
    ).order_by(models.GeneratedArtifact.artifact_version.desc()).first()
    return {"purchase_order": {"business_number": po.business_number, "status": po.status, "currency": po.currency, "payment_terms": po.payment_terms, "document_available": final_artifact is not None}, "lines": workflows.records_to_dicts(lines), "acknowledgement": workflows.record_to_dict(acknowledgement), "deliveries": delivery_rows, "expires_at": portal_token.expires_at}


@app.get("/supplier/pos/{token}/document")
def supplier_po_document(token: str, db: Session = Depends(get_db)):
    portal_token = workflows.get_supplier_portal_token(db, token)
    if portal_token.purpose != "po_acknowledgement" or not portal_token.entity_id:
        raise HTTPException(404, "Supplier PO link is invalid or expired")
    artifact = db.query(models.GeneratedArtifact).filter(
        models.GeneratedArtifact.tenant_id == portal_token.tenant_id,
        models.GeneratedArtifact.plant_id == portal_token.plant_id,
        models.GeneratedArtifact.entity_id == portal_token.entity_id,
        models.GeneratedArtifact.status == "final",
        models.GeneratedArtifact.artifact_type.in_(["po", "po_pdf"]),
    ).order_by(models.GeneratedArtifact.artifact_version.desc()).first()
    if not artifact:
        raise HTTPException(404, "Final purchase-order document is not available")
    document = db.query(models.Document).filter_by(
        id=artifact.document_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id,
    ).first()
    if not document or document.content_type != "application/pdf":
        raise HTTPException(404, "Final purchase-order document is not available")
    content = document_service.object_storage.get_bytes(document.storage_bucket, document.storage_key)
    safe_filename = document.filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{safe_filename}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@app.post("/supplier/pos/{token}/deliveries")
def supplier_submit_delivery(token: str, payload: SupplierDeliveryNoticeRequest, db: Session = Depends(get_db)):
    asn = workflows.receive_supplier_delivery_notice(db, token, payload.expected_quantity, payload.expected_delivery, payload.dispatch_reference, payload.vehicle_number)
    db.commit()
    return asn


@app.post("/supplier/pos/{token}/deliveries/{asn_id}/updates")
def supplier_update_delivery(
    token: str, asn_id: str, payload: SupplierDeliveryUpdateRequest,
    db: Session = Depends(get_db),
):
    update = workflows.receive_supplier_delivery_update(
        db, token, asn_id, payload.external_update_id,
        payload.revised_expected_delivery, payload.reason,
    )
    db.commit()
    return update


@app.post("/supplier/portal/{token}/clarifications")
def supplier_submit_clarification(token: str, payload: SupplierClarificationResponseRequest, db: Session = Depends(get_db)):
    message = workflows.receive_supplier_clarification(db, token, payload.external_message_id, payload.subject, payload.message)
    db.commit()
    return message


@app.post("/supplier/pos/{token}/deliveries/{asn_id}/documents", status_code=202)
async def supplier_upload_delivery_document(
    token: str, asn_id: str, purpose: str = Form("supplier_dispatch_document"),
    file: UploadFile = File(...), db: Session = Depends(get_db),
):
    portal_token = workflows.get_supplier_portal_token(db, token)
    if portal_token.purpose != "po_acknowledgement" or portal_token.entity_id is None:
        raise HTTPException(404, "Supplier PO link is invalid or expired")
    asn = db.query(models.ASN).filter_by(id=asn_id, tenant_id=portal_token.tenant_id, plant_id=portal_token.plant_id, po_draft_id=portal_token.entity_id, source="supplier_portal").first()
    if not asn:
        raise HTTPException(404, "Supplier delivery notice not found")
    document, _job = await document_service.create_supplier_portal_upload(db, asn, file, purpose, asn.id)
    workflows.attach_supplier_delivery_document(db, token, asn.id, document)
    db.commit()
    job = document_service.enqueue_document_job(db, document.id)
    db.refresh(document)
    if job: db.refresh(job)
    return {"document": workflows.record_to_dict(document), "job": workflows.record_to_dict(job), "delivery": workflows.record_to_dict(asn)}


@app.post("/supplier/pos/{token}/invoices", status_code=202)
async def supplier_upload_invoice(
    token: str, file: UploadFile = File(...), db: Session = Depends(get_db),
):
    portal_token = workflows.get_supplier_portal_token(db, token)
    if portal_token.purpose != "po_acknowledgement" or portal_token.entity_id is None:
        raise HTTPException(404, "Supplier PO link is invalid or expired")
    po = db.query(models.PODraft).filter_by(
        id=portal_token.entity_id, tenant_id=portal_token.tenant_id,
        plant_id=portal_token.plant_id, supplier_id=portal_token.supplier_id,
    ).first()
    if not po:
        raise HTTPException(404, "Purchase order not found")
    acknowledgement = db.query(models.SupplierAcknowledgement).filter_by(
        tenant_id=po.tenant_id, plant_id=po.plant_id, po_draft_id=po.id, status="accepted",
    ).first()
    if not acknowledgement:
        raise HTTPException(409, "Accept the purchase order before submitting an invoice")
    document, _job = await document_service.create_supplier_portal_upload(
        db, po, file, "supplier_invoice_draft", po.id,
    )
    db.commit()
    job = document_service.enqueue_document_job(db, document.id)
    db.refresh(document)
    if job: db.refresh(job)
    return {"document": workflows.record_to_dict(document), "job": workflows.record_to_dict(job)}


@app.post("/inbound/asns", dependencies=[Depends(csrf_guard)])
def create_asn(payload: ASNRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    asn = workflows.create_asn(db, user, payload.po_draft_id, payload.expected_quantity, payload.vehicle_number)
    db.commit()
    return asn


@app.post("/inbound/gate-entries", dependencies=[Depends(csrf_guard)])
def create_gate_entry(payload: GateEntryRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    gate = workflows.record_gate_entry(
        db, user, payload.po_draft_id, payload.asn_id, payload.vehicle_number,
        payload.supplier_challan, payload.packages_count, payload.arrival_notes,
    )
    db.commit()
    return gate


@app.post("/cases/{case_id}/close", dependencies=[Depends(csrf_guard)])
def close_case(case_id: str, payload: CaseCloseRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.Case, user, case_id, "Case"))
    case = workflows.close_case(db, user, case_id, payload.resolution, payload.override, payload.override_reason)
    db.commit()
    return case


@app.get("/procurement/invoices")
def list_supplier_invoices(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.SupplierInvoice, user)


@app.get("/procurement/invoice-extractions")
def list_invoice_extractions(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.InvoiceExtractionRun, user)


@app.get("/procurement/po-lines")
def list_purchase_order_lines(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.PODraftLine, user)


@app.get("/procurement/invoice-matches")
def list_invoice_matches(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.InvoiceMatchResult, user)


@app.get("/procurement/finance-handoffs")
def list_finance_handoffs(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.FinanceHandoff, user)


@app.get("/procurement/invoice-payment-statuses")
def list_invoice_payment_statuses(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "procurement")
    return workflows.list_for_user(db, models.InvoicePaymentStatus, user)


@app.post("/procurement/invoices", dependencies=[Depends(csrf_guard)])
def capture_supplier_invoice(payload: SupplierInvoiceCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    invoice = invoice_service.create_invoice(db, user, payload.model_dump())
    db.commit()
    return invoice


@app.post("/procurement/invoice-extractions/{extraction_id}/verify", dependencies=[Depends(csrf_guard)])
def verify_invoice_extraction(extraction_id: str, payload: InvoiceExtractionVerifyRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    invoice = invoice_service.verify_invoice_extraction(db, user, extraction_id, payload.model_dump())
    db.commit()
    return invoice


@app.post("/procurement/invoices/{invoice_id}/match", dependencies=[Depends(csrf_guard)])
def run_invoice_match(invoice_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    result = invoice_service.match_invoice(db, user, invoice_id)
    db.commit()
    return result


@app.post("/procurement/invoice-matches/{match_id}/finance-handoff", dependencies=[Depends(csrf_guard)])
def create_finance_handoff(match_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    handoff = invoice_service.prepare_finance_handoff(db, user, match_id)
    db.commit()
    return handoff


@app.get("/integrations/connections")
def integration_connections(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    workflows.ensure_default_connections(db, user)
    db.commit()
    return workflows.list_for_user(db, models.IntegrationConnection, user)


@app.post("/integrations/connections", dependencies=[Depends(csrf_guard)])
def create_integration_connection(payload: ConnectionCreateRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    connector = get_connector(payload.provider)
    enabled = set(payload.enabled_capabilities or connector.manifest.tested_capabilities)
    unsupported = enabled - connector.manifest.tested_capabilities
    if unsupported:
        raise HTTPException(422, f"Adapter has not contract-tested: {', '.join(sorted(unsupported))}")
    if payload.secret_ref and (" " in payload.secret_ref or not payload.secret_ref.startswith(("vault://", "secret://", "env://"))):
        raise HTTPException(422, "Provide a secret-manager reference, never raw credentials")
    connection = models.IntegrationConnection(
        tenant_id=user.tenant_id, plant_id=user.plant_id, provider=payload.provider,
        provider_version=connector.manifest.adapter_version, name=payload.name, mode=payload.mode,
        status="disabled" if payload.mode == "disconnected" else "configured" if connector.manifest.tested_capabilities else "customer_validation_required",
        capabilities=sorted(connector.manifest.capabilities), enabled_capabilities=sorted(enabled),
        writes_enabled=False, config={}, secret_ref=payload.secret_ref,
    )
    db.add(connection)
    db.flush()
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "integration_connection.created", "integration_connection", connection.id, actor_user_id=user.id, meta={"provider": payload.provider, "mode": payload.mode, "writes_enabled": False})
    db.commit()
    return connection


@app.get("/integrations/connectors")
def integration_connector_catalog(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_read_role(user, "integrations")
    return [
        {
            "provider": manifest.provider, "display_name": manifest.display_name,
            "adapter_version": manifest.adapter_version,
            "protocols": manifest.protocols,
            "capabilities": sorted(manifest.capabilities),
            "tested_capabilities": sorted(manifest.tested_capabilities),
            "live_customer_verified": manifest.live_customer_verified,
        }
        for manifest in registry_manifests()
    ]


@app.get("/integrations/connectors/conformance-report")
def integration_connector_conformance_report(user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    return run_conformance_report()


@app.get("/integrations/connectors/conformance-report.csv")
def download_integration_connector_conformance_report(user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    report = run_conformance_report()
    import csv
    import io
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["provider", "adapter_version", "live_customer_verified", "check", "passed"])
    for adapter in report["adapters"]:
        for check, passed in adapter["checks"].items():
            writer.writerow([adapter["provider"], adapter["adapter_version"], adapter["live_customer_verified"], check, passed])
    return Response(
        content=output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="connector-conformance-report.csv"', "Cache-Control": "private, no-store"},
    )


@app.patch("/integrations/connections/{connection_id}", dependencies=[Depends(csrf_guard)])
def update_integration_connection(connection_id: str, payload: ConnectionUpdateRequest, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    connection = workflows.get_scoped_or_404(db, models.IntegrationConnection, user, connection_id, "Integration connection")
    require_if_match(request, connection)
    changes = payload.model_dump(exclude_none=True)
    confirmation = changes.pop("write_enable_confirmation", None)
    acceptance_reference = changes.pop("acceptance_reference", None)
    if "enabled_capabilities" in changes:
        connector = get_connector(connection.provider)
        tested = set(connector.manifest.tested_capabilities)
        unsupported = set(changes["enabled_capabilities"]) - tested
        if unsupported:
            raise HTTPException(422, f"Adapter has not contract-tested: {', '.join(sorted(unsupported))}")
    resulting_mode = str(changes.get("mode") or connection.mode)
    if changes.get("writes_enabled") is True:
        if confirmation != "ENABLE_EXTERNAL_WRITES" or not acceptance_reference:
            raise HTTPException(422, "Enabling external writes requires explicit confirmation and an acceptance reference")
        if resulting_mode not in {"uat", "limited_production_write", "production_write"}:
            raise HTTPException(409, "External writes can be enabled only in UAT or an approved production-write mode")
        connector = get_connector(connection.provider)
        if not connector.manifest.tested_capabilities:
            raise HTTPException(409, "This adapter has no verified write capability")
        if resulting_mode == "production_write" and not workflows.get_settings().erp_live_enabled:
            raise HTTPException(409, "Production integration writes are disabled for this deployment")
        config = dict(connection.config or {})
        config["write_acceptance"] = {
            "reference": acceptance_reference, "enabled_by_user_id": user.id,
            "enabled_at": workflows.utcnow().isoformat(), "mode": resulting_mode,
        }
        connection.config = config
    for key, value in changes.items():
        setattr(connection, key, value)
    if connection.mode == "disconnected":
        connection.status = "disabled"
        connection.writes_enabled = False
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "integration_connection.updated", "integration_connection", connection.id, actor_user_id=user.id, meta={
        "changed_fields": sorted(changes), "mode": connection.mode,
        "writes_enabled": connection.writes_enabled,
        "acceptance_reference": acceptance_reference if changes.get("writes_enabled") is True else None,
    })
    db.commit()
    return connection


@app.get("/integrations/sync-jobs")
def integration_sync_jobs(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return workflows.list_for_user(db, models.IntegrationSyncJob, user)


@app.post("/integrations/outbox/{event_id}/approve", dependencies=[Depends(csrf_guard)])
def approve_integration_outbox(event_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.IntegrationOutboxEvent, user, event_id, "Integration outbox event"))
    event = workflows.approve_integration_outbox_event(db, user, event_id)
    db.commit()
    return event


@app.post("/integrations/outbox/{event_id}/dispatch", dependencies=[Depends(csrf_guard)], status_code=202)
def dispatch_integration_outbox(event_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_if_match(request, workflows.get_scoped_or_404(db, models.IntegrationOutboxEvent, user, event_id, "Integration outbox event"))
    event = workflows.dispatch_integration_outbox_event(db, user, event_id)
    db.commit()
    from app.workers import dispatch_integration
    task = dispatch_integration.apply_async(args=[event.id], queue="integrations")
    return {"event_id": event.id, "job_id": task.id, "status": event.status}


@app.post("/integrations/outbox/{event_id}/retry", dependencies=[Depends(csrf_guard)], status_code=202)
def retry_integration_outbox(event_id: str, request: Request, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", ADMIN)
    event = workflows.get_scoped_or_404(db, models.IntegrationOutboxEvent, user, event_id, "Integration outbox event")
    require_if_match(request, event)
    if event.status != "failed" or not event.approved_at:
        raise HTTPException(status_code=409, detail="Only previously approved failed events can be retried")
    event.status = "dispatching"
    event.last_error = None
    db.commit()
    from app.workers import dispatch_integration
    task = dispatch_integration.apply_async(args=[event.id], queue="integrations")
    return {"event_id": event.id, "job_id": task.id, "status": event.status}


@app.post("/integrations/reconciliation", dependencies=[Depends(csrf_guard)])
def reconcile(payload: ReconciliationRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    result = workflows.run_reconciliation(db, user, payload.entity_type, payload.entity_id)
    db.commit()
    return result


@app.post("/integrations/sync-jobs", dependencies=[Depends(csrf_guard)], status_code=202)
def create_sync_job(payload: SyncJobRequest, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, "purchase_manager", ADMIN)
    connection = workflows.get_scoped_or_404(db, models.IntegrationConnection, user, payload.connection_id, "Integration connection")
    if connection.mode == "disconnected":
        raise HTTPException(409, "Connection is disabled")
    if connection.provider in CONNECTOR_REGISTRY:
        required = set(SYNC_JOB_CAPABILITIES[payload.job_type])
        missing = required - set(connection.enabled_capabilities or [])
        if missing:
            raise HTTPException(422, f"Connection has not enabled: {', '.join(sorted(missing))}")
    job = models.IntegrationSyncJob(id=workflows.next_id(db, models.IntegrationSyncJob, "SYNC"), business_number=workflows.next_business_number(db, "SYNC", user), tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id, job_type=payload.job_type, status="queued", summary={})
    db.add(job)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "integration_sync.queued", "integration_sync_job", job.id, actor_user_id=user.id)
    db.commit()
    from app.workers import run_sync_job
    task = run_sync_job.apply_async(args=[job.id], queue="sync")
    return {"job_id": job.id, "celery_task_id": task.id, "status": job.status}


@app.post("/integrations/connections/{connection_id}/test", dependencies=[Depends(csrf_guard)])
def test_integration_connection(connection_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    require_role(user, ADMIN)
    connection = workflows.get_scoped_or_404(db, models.IntegrationConnection, user, connection_id, "Integration connection")
    if connection.provider in CONNECTOR_REGISTRY:
        connector = get_connector(connection.provider)
        result = connector.test_connection(ConnectorContext(
            connection_id=connection.id, tenant_id=user.tenant_id, plant_id=user.plant_id,
            mode=ConnectorMode(connection.mode), enabled_capabilities=frozenset(connection.enabled_capabilities or []),
            writes_enabled=connection.writes_enabled, secret_ref=connection.secret_ref,
        ))
    else:
        from app.erp import get_erp_adapter
        adapter = get_erp_adapter(connection.provider)
        result = adapter.pull_master_data(db, user.tenant_id, user.plant_id) if connection.provider == "local" else {"provider": connection.provider, "status": "configured" if connection.base_url else "not_configured"}
    connection.last_checked_at = workflows.utcnow()
    connection.status = result.get("status", "active")
    db.commit()
    return result
