from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import current_user, require_csrf
from app.core.permissions import workspace_capabilities, workspace_membership
from app.db import models as core_models
from app.db.session import get_db
from app.platform import actions
from app.platform.models import ActionApproval, ActionExecution, ActionIntent, ActionOutcome, ActionPolicyEvaluation, DataProvenance, DataQualityIssue, MaterialStateProjection, OperationalCase, PlatformBOM, PlatformBOMItem, PlatformInventoryLocation, PlatformInventoryPosition, PlatformMaterial, PlatformProduct
from app.feature_flags import enabled as feature_enabled
from app.scm import models as scm_models

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> core_models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def platform_enabled(db: Session = Depends(get_db), user: core_models.User = Depends(authenticated_user)) -> core_models.User:
    tenant = db.get(core_models.Tenant, user.tenant_id)
    if get_settings().app_env not in {"development", "dev", "test", "staging"} and tenant and tenant.workspace_kind in {"demo", "simulation"}:
        raise HTTPException(404, "Demo platform endpoints are unavailable in production")
    return user


def data_admin(user: core_models.User = Depends(platform_enabled)) -> core_models.User:
    if user.role not in {"admin", "plant_manager", "workspace_admin"}:
        raise HTTPException(403, "Factory data administration permission required")
    return user


@router.post("/factory-imports/preview", dependencies=[Depends(csrf_guard)])
async def preview_factory_import(file: UploadFile = File(...), db: Session = Depends(get_db),
                                 user: core_models.User = Depends(data_admin)):
    from app.platform import unified_imports
    maximum = get_settings().max_upload_bytes
    content = await file.read(maximum + 1)
    if len(content) > maximum:
        raise HTTPException(413, "Factory workbook exceeds the upload limit")
    batch = unified_imports.preview(db, user, file.filename or "factory.xlsx", content)
    db.commit(); db.refresh(batch)
    return unified_imports.payload(batch)


@router.get("/factory-imports/template")
def factory_import_template(user: core_models.User = Depends(data_admin)):
    from app.platform import unified_imports
    return Response(unified_imports.automotive_template(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="GenuineGigs_Connected_Automotive_Factory_v2.xlsx"'})


@router.post("/factory-imports/demo", dependencies=[Depends(csrf_guard)])
def load_factory_demo(db: Session = Depends(get_db), user: core_models.User = Depends(data_admin)):
    if get_settings().app_env not in {"development", "dev", "test", "staging"}:
        raise HTTPException(404, "Demo fixture is unavailable")
    from app.platform import unified_imports
    if not db.get(core_models.Uom, "EA"):
        db.add(core_models.Uom(id="EA", label="Each")); db.flush()
    demo_filename = "GenuineGigs_Connected_Automotive_Factory_v2.xlsx"
    batch = db.query(core_models.IntegrationImportBatch).filter_by(tenant_id=user.tenant_id,
        plant_id=user.plant_id, workbook_version=unified_imports.VERSION,
        source_filename=demo_filename, status="completed").order_by(
        core_models.IntegrationImportBatch.created_at.desc()).first()
    already_loaded = batch is not None
    batch = batch or unified_imports.preview(db, user, demo_filename, unified_imports.automotive_template())
    unified_imports.preserve_existing_demo_masters(db, batch)
    if batch.status != "completed":
        unified_imports.commit(db, user, batch)
    planning = None
    if not already_loaded:
        from app.scm.service import create_run, execute_run
        planning = create_run(db, user, trigger_key=f"factory-import:{batch.id}", trigger_type="IMPORT")
        execute_run(db, planning.id)
    else:
        planning = db.query(scm_models.SCMPlanningRun).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, status="COMPLETED").order_by(
            scm_models.SCMPlanningRun.completed_at.desc()).first()
    risk = db.query(scm_models.SCMMaterialRisk).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        latest_planning_run_id=planning.id if planning else None).order_by(
            scm_models.SCMMaterialRisk.quantity.desc()).first()
    case = db.get(OperationalCase, risk.operational_case_id) if risk and risk.operational_case_id else None
    db.commit(); db.refresh(batch)
    return {"import": unified_imports.payload(batch), "planning_run_id": planning.id if planning else None,
            "case_count": db.query(scm_models.SCMMaterialRisk).filter_by(
                tenant_id=user.tenant_id, plant_id=user.plant_id,
                latest_planning_run_id=planning.id if planning else None).count(),
            "case_id": case.id if case else None, "case_href": f"/cases/{case.id}" if case else "/cases"}


@router.get("/factory-imports")
def list_factory_imports(db: Session = Depends(get_db), user: core_models.User = Depends(data_admin)):
    from app.platform import unified_imports
    rows = db.query(core_models.IntegrationImportBatch).filter_by(tenant_id=user.tenant_id,
        plant_id=user.plant_id, workbook_version=unified_imports.VERSION).order_by(
        core_models.IntegrationImportBatch.created_at.desc()).limit(50).all()
    return [unified_imports.payload(row) for row in rows]


@router.get("/factory-imports/{batch_id}")
def get_factory_import(batch_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(data_admin)):
    from app.platform import unified_imports
    return unified_imports.payload(unified_imports.scoped_batch(db, user, batch_id))


@router.post("/factory-imports/{batch_id}/commit", dependencies=[Depends(csrf_guard)])
def commit_factory_import(batch_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(data_admin)):
    from app.platform import unified_imports
    batch = unified_imports.commit(db, user, unified_imports.scoped_batch(db, user, batch_id))
    db.commit(); db.refresh(batch)
    return unified_imports.payload(batch)


def _intent(row: ActionIntent, db: Session) -> dict[str, Any]:
    approval = db.query(ActionApproval).filter_by(action_intent_id=row.id).first()
    policy = db.query(ActionPolicyEvaluation).filter_by(action_intent_id=row.id).first()
    execution = db.query(ActionExecution).filter_by(action_intent_id=row.id).first()
    outcome = db.query(ActionOutcome).filter_by(action_intent_id=row.id).first()
    return {"id": row.id, "status": row.status, "action_type": row.action_type, "target_type": row.target_type,
            "target_id": row.target_id, "payload": row.payload, "rationale": row.rationale,
            "correlation_id": row.correlation_id, "originating_case_id": row.originating_case_id,
            "reason_code": row.reason_code, "evidence": row.evidence,
            "expected_impact": row.expected_impact, "confidence": row.confidence,
            "risk_level": row.risk_level,
            "policy": {"allowed": policy.allowed, "requires_approval": policy.requires_approval, "reason_code": policy.reason_code} if policy else None,
            "approval": {"decision": approval.decision, "comment": approval.comment, "decided_at": approval.decided_at} if approval else None,
            "execution": {"status": execution.status, "mode": execution.mode, "result": execution.result,
                          "external_reference": execution.external_reference, "error": execution.error,
                          "executed_at": execution.executed_at} if execution else None,
            "outcome": {"verification_status": outcome.verification_status, "outcome_type": outcome.outcome_type,
                        "evidence": outcome.evidence, "metrics": outcome.metrics, "verified_at": outcome.verified_at} if outcome else None}


class ActionProposal(BaseModel):
    action_type: str = Field(min_length=3, max_length=120)
    target_type: str = Field(min_length=3, max_length=80)
    target_id: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=3, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=160)


class ActionDecision(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=4000)


class OperationalContextRequest(BaseModel):
    plant_scope: list[str] = Field(default_factory=list, max_length=25)
    entity_ids: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    horizon: dict[str, Any] = Field(default_factory=dict)
    include: list[str] = Field(default_factory=lambda: ["state", "provenance", "data_quality"], max_length=12)
    as_of: datetime | None = None
    plan_version: str | None = Field(default=None, max_length=80)


@router.get("/context")
def context(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    tenant = db.get(core_models.Tenant, user.tenant_id)
    return {"tenant_id": user.tenant_id, "plant_id": user.plant_id, "workspace_kind": tenant.workspace_kind if tenant else None,
            "contracts": ["catalog", "provenance", "state", "events", "actions", "cases", "work", "agents", "integrations"],
            "execution_modes": ["simulated", "internal_governed"]}


@router.post("/operational-context")
def operational_context(payload: OperationalContextRequest, db: Session = Depends(get_db),
                        user: core_models.User = Depends(platform_enabled)):
    """Trusted, compressed context; callers cannot forge workspace scope."""
    from app.platform.state import FactoryStateService
    membership = workspace_membership(db, user)
    allowed_plants = set((membership.plant_ids or []) if membership else [user.plant_id])
    allowed_plants.add(user.plant_id)
    requested = set(payload.plant_scope or [user.plant_id])
    if not requested.issubset(allowed_plants):
        raise HTTPException(403, "Plant scope is not authorized")
    allowed_includes = {"state", "relationships", "plans", "commitments", "constraints", "cases", "work", "history", "provenance", "data_quality"}
    if not set(payload.include).issubset(allowed_includes):
        raise HTTPException(422, "Unsupported context include")
    facts = []
    for plant_id in sorted(requested):
        service = FactoryStateService(db, user.tenant_id, plant_id)
        for ref in payload.entity_ids:
            entity_type, entity_id = ref.get("type"), ref.get("id")
            state = service.at(entity_type, entity_id, payload.as_of) if payload.as_of else service.now(entity_type, entity_id)
            if state is None:
                continue
            # Keep the stable contract explicit and deterministic for UI/Gigi.
            facts.append({key: value for key, value in state.items()
                          if key in {"entity", "observed", "derived", "predicted", "planned", "freshness", "provenance", "relationships", "related_risks", "computed_at"}
                          and (key not in {"relationships"} or "relationships" in payload.include)})
    return {"tenant_id": user.tenant_id, "plant_scope": sorted(requested), "as_of": payload.as_of,
            "plan_version": payload.plan_version, "horizon": payload.horizon,
            "includes": payload.include, "facts": facts, "fact_count": len(facts)}


def _module_access(db: Session, user: core_models.User) -> dict[str, bool]:
    membership = workspace_membership(db, user)
    permissions = set(membership.permissions or []) if membership else set()
    procurement_roles = {"admin", "plant_manager", "purchase_manager", "purchase_executive",
                         "gate_operator", "store_manager", "quality_inspector"}
    operations_roles = {"admin", "plant_manager", "production_manager", "production_supervisor",
                        "operator", "maintenance_manager", "maintenance_technician", "quality_manager",
                        "quality_inspector", "purchase_manager", "purchase_executive", "store_manager",
                        "gate_operator", "corporate_operations_director"}
    scm_allowed = user.role in {"admin", "scm_planner"} or "scm.view" in permissions
    scm_enabled = feature_enabled(db, user.tenant_id, "scm_control_tower", default=get_settings().scm_enabled)
    return {
        "procurement": user.role in procurement_roles or "procurement.view" in permissions,
        "scm": scm_allowed and scm_enabled,
        "operations": user.role in operations_roles or "operations.view" in permissions,
        "platform": user.role == "admin" or "workspace.view_setup" in workspace_capabilities(db, user),
    }


@router.get("/app-context")
def app_context(db: Session = Depends(get_db), user: core_models.User = Depends(authenticated_user)):
    tenant = db.get(core_models.Tenant, user.tenant_id)
    plant = db.get(core_models.Plant, user.plant_id)
    membership = workspace_membership(db, user)
    access = _module_access(db, user)
    modules = [
        {"key": "procurement", "label": "Procurement", "enabled": access["procurement"], "default_route": "/procurement"},
        {"key": "scm", "label": "SCM", "enabled": access["scm"], "default_route": "/scm"},
        {"key": "operations", "label": "Operations", "enabled": access["operations"], "default_route": "/operations"},
        {"key": "platform", "label": "Platform", "enabled": access["platform"], "default_route": "/platform"},
    ]
    unread = db.query(core_models.Notification).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id, status="unread").count()
    return {
        "user": serialize_user_for_platform(user, db),
        "workspace": {"id": user.tenant_id, "name": tenant.name if tenant else "Workspace",
                      "kind": tenant.workspace_kind if tenant else None},
        "plant": {"id": plant.id, "name": plant.name, "timezone": plant.timezone,
                  "locale": getattr(plant, "locale", "en-US"), "currency": plant.currency} if plant else None,
        "modules": modules, "notification_count": unread,
        "source_health": "unknown",
    }


def serialize_user_for_platform(user: core_models.User, db: Session) -> dict[str, Any]:
    membership = workspace_membership(db, user)
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role,
            "membership_id": membership.id if membership else None,
            "permissions": list(membership.permissions or []) if membership else [],
            "capabilities": workspace_capabilities(db, user)}


@router.get("/home")
def platform_home(db: Session = Depends(get_db), user: core_models.User = Depends(authenticated_user)):
    access = _module_access(db, user)
    open_states = ("open", "accepted", "in_progress", "blocked", "pending")
    tasks = db.query(core_models.Task).filter(
        core_models.Task.tenant_id == user.tenant_id,
        core_models.Task.plant_id == user.plant_id,
        core_models.Task.status.in_(open_states),
        (core_models.Task.owner_user_id == user.id) | (core_models.Task.owner_role == user.role),
    ).order_by(core_models.Task.due_at.asc().nullslast(), core_models.Task.created_at.desc()).limit(12).all()
    summaries: dict[str, Any] = {}
    if access["procurement"]:
        requirements = db.query(core_models.PurchaseRequirement).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id).filter(
            core_models.PurchaseRequirement.status.notin_(("closed", "cancelled"))).count()
        summaries["procurement"] = {"state": "available", "primary_count": requirements,
                                     "primary_label": "active requirements", "href": "/procurement"}
    if access["scm"]:
        critical = db.query(scm_models.SCMMaterialRisk).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id).filter(
            scm_models.SCMMaterialRisk.status.notin_(("RESOLVED", "DISMISSED")),
            scm_models.SCMMaterialRisk.severity.in_(("CRITICAL", "HIGH", "critical", "high"))).count()
        summaries["scm"] = {"state": "available", "primary_count": critical,
                            "primary_label": "critical material risks", "href": "/scm"}
    if access["operations"]:
        deviations = db.query(core_models.OperationalDeviation).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id).filter(
            core_models.OperationalDeviation.status.notin_(("verified", "learned", "cancelled"))).count()
        summaries["operations"] = {"state": "available", "primary_count": deviations,
                                   "primary_label": "active deviations", "href": "/operations"}
    from app.platform.case_models import BusinessExposure, DecisionRecord, RecoveryVerification, ValueAttribution
    active_cases = db.query(OperationalCase).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).filter(
        OperationalCase.status.notin_(("closed", "resolved", "cancelled"))).order_by(
        OperationalCase.priority_score.desc(), OperationalCase.decision_deadline.asc()).limit(20).all()
    case_ids = [row.id for row in active_cases]
    pending_decisions = db.query(DecisionRecord).filter(DecisionRecord.tenant_id == user.tenant_id,
        DecisionRecord.plant_id == user.plant_id, DecisionRecord.decision == "PENDING").count()
    exposure = db.query(BusinessExposure).filter(BusinessExposure.case_id.in_(case_ids)).all() if case_ids else []
    recoveries = db.query(RecoveryVerification).filter(RecoveryVerification.tenant_id == user.tenant_id,
        RecoveryVerification.plant_id == user.plant_id, RecoveryVerification.status == "MONITORING").count()
    values = db.query(ValueAttribution).filter(ValueAttribution.tenant_id == user.tenant_id,
        ValueAttribution.plant_id == user.plant_id, ValueAttribution.verified_at.is_not(None)).all()
    from app.platform.case_service import _human_case_copy
    return {
        "attention": [{"id": row.id, "title": row.title, "status": row.status,
                       "priority": row.priority, "owner_role": row.owner_role,
                       "due_at": row.due_at, "entity_type": row.entity_type,
                       "entity_id": row.entity_id} for row in tasks],
        "module_summaries": summaries,
        "operational_cases": [{"id": row.id, "title": _human_case_copy(db, row)[0], "severity": row.severity,
            "priority_score": row.priority_score, "decision_deadline": row.decision_deadline,
            "expected_impact_at": row.expected_impact_at, "recovery_state": row.recovery_state,
            "responsible_team": row.responsible_team} for row in active_cases],
        "decision_count": pending_decisions,
        "recovery_count": recoveries,
        "exposure": [{"metric": row.metric, "delta": row.delta, "unit": row.unit,
            "currency": row.currency} for row in exposure],
        "verified_value": [{"metric": row.metric, "value": row.attributed_value,
            "unit": row.unit, "currency": row.currency} for row in values],
        "generated_at": datetime.now(timezone.utc),
    }


@router.get("/organizations")
def organizations(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(core_models.Company).filter_by(tenant_id=user.tenant_id).all()
    return [{"id": row.id, "name": row.name, "code": row.erp_code} for row in rows]


@router.get("/sites")
def sites(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(core_models.Plant).filter_by(tenant_id=user.tenant_id).all()
    return [{"id": row.id, "organization_id": row.company_id, "name": row.name,
             "code": row.erp_location_code, "timezone": row.timezone, "currency": row.currency,
             "status": row.status} for row in rows]


@router.get("/manufacturing-hierarchy")
def hierarchy(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    areas = db.query(core_models.PlantArea).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()
    lines = db.query(core_models.ProductionLine).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()
    assets = db.query(core_models.PlantAsset).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()
    return {"site_id": user.plant_id,
            "areas": [{"id": row.id, "code": row.code, "name": row.name} for row in areas],
            "work_centers": [{"id": row.id, "area_id": row.area_id, "code": row.code, "name": row.name} for row in lines],
            "equipment": [{"id": row.id, "area_id": row.area_id, "work_center_id": row.line_id,
                           "code": row.code, "name": row.name, "asset_type": row.asset_type,
                           "criticality": row.criticality} for row in assets]}


@router.get("/materials")
def materials(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(PlatformMaterial).filter_by(tenant_id=user.tenant_id).order_by(PlatformMaterial.code).all()
    return [{"id": row.id, "code": row.code, "name": row.name, "material_type": row.material_type, "lifecycle_status": row.lifecycle_status} for row in rows]


@router.get("/suppliers")
def suppliers(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(core_models.Supplier).filter_by(tenant_id=user.tenant_id).order_by(core_models.Supplier.name).all()
    return [{"id": row.id, "organization_id": row.company_id, "code": row.code or row.erp_vendor_id,
             "legal_name": row.legal_name or row.name, "display_name": row.name, "status": row.status,
             "default_lead_time_days": row.default_lead_time_days, "metadata": row.metadata_json} for row in rows]


@router.get("/products")
def products(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(PlatformProduct).filter_by(tenant_id=user.tenant_id).order_by(PlatformProduct.code).all()
    return [{"id": row.id, "organization_id": row.company_id, "code": row.code, "name": row.name,
             "product_type": row.product_type, "base_uom_id": row.base_uom_id,
             "status": row.lifecycle_status} for row in rows]


@router.get("/products/{product_id}/boms")
def product_boms(product_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(PlatformBOM).filter_by(tenant_id=user.tenant_id, product_id=product_id).all()
    return [{"id": row.id, "revision": row.revision, "effective_from": row.effective_from,
             "effective_to": row.effective_to, "status": row.status,
             "items": [{"id": item.id, "component_entity_type": item.component_entity_type,
                        "component_id": item.component_id, "quantity": item.quantity, "uom_id": item.uom_id,
                        "scrap_factor": item.scrap_factor, "alternate_group": item.alternate_group,
                        "line_number": item.line_number} for item in db.query(PlatformBOMItem).filter_by(bom_id=row.id).all()]}
            for row in rows]


@router.get("/materials/{material_id}/state")
def material_state(material_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.state import material_state as get_material_state
    row = get_material_state(db, user.tenant_id, user.plant_id, material_id)
    if not row:
        raise HTTPException(404, "Material state projection not found")
    return row


@router.get("/work-orders/{work_order_id}/state")
def work_order_state(work_order_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.state import work_order_state as get_work_order_state
    row = get_work_order_state(db, user.tenant_id, work_order_id, plant_id=user.plant_id)
    if not row: raise HTTPException(404, "Work order state not found")
    return row


@router.get("/factory-context")
def factory_context(entity_type: str | None = None, entity_id: str | None = None,
                    db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.state import factory_context as build_context
    return build_context(db, user.tenant_id, user.plant_id, entity_type=entity_type, entity_id=entity_id)


@router.get("/state/{entity_type}/{entity_id}")
def shared_state(entity_type: str, entity_id: str, at: datetime | None = None,
                 db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.state import FactoryStateService
    service = FactoryStateService(db, user.tenant_id, user.plant_id)
    row = service.at(entity_type, entity_id, at) if at else service.now(entity_type, entity_id)
    if not row: raise HTTPException(404, "Factory state not found")
    return row


@router.get("/state/{entity_type}/{entity_id}/history")
def shared_state_history(entity_type: str, entity_id: str, limit: int = 100,
                         db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.state import FactoryStateService
    return FactoryStateService(db, user.tenant_id, user.plant_id).history(entity_type, entity_id, limit=limit)


@router.get("/relationships/{entity_type}/{entity_id}")
def relationships(entity_type: str, entity_id: str, direction: str = "both", max_depth: int = 6,
                  db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.relationships import traverse
    if direction not in {"in", "out", "both"}: raise HTTPException(422, "direction must be in, out or both")
    return traverse(db, user.tenant_id, entity_type, entity_id, direction=direction, max_depth=min(max_depth, 10))


@router.get("/impact/{entity_type}/{entity_id}")
def impact(entity_type: str, entity_id: str, db: Session = Depends(get_db),
           user: core_models.User = Depends(platform_enabled)):
    from app.platform.relationships import get_impact
    return get_impact(db, user.tenant_id, entity_type, entity_id)


@router.get("/traces/{correlation_id}")
def trace(correlation_id: str, db: Session = Depends(get_db),
          user: core_models.User = Depends(platform_enabled)):
    from app.platform.trace import correlation_trace
    return correlation_trace(db, user.tenant_id, correlation_id)


@router.get("/integrity")
def integrity(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.integrity import check_tenant
    return {"tenant_id": user.tenant_id, "issues": check_tenant(db, user.tenant_id)}


@router.get("/data-quality")
def data_quality(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(DataQualityIssue).filter_by(tenant_id=user.tenant_id).order_by(DataQualityIssue.created_at.desc()).limit(100).all()
    return [{"id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id, "rule_key": row.rule_key,
             "severity": row.severity, "status": row.status, "message": row.message} for row in rows]


@router.get("/provenance")
def provenance(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(DataProvenance).filter_by(tenant_id=user.tenant_id).order_by(DataProvenance.recorded_at.desc()).limit(100).all()
    return [{"id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id, "source_system": row.source_system,
             "source_reference": row.source_reference, "observed_at": row.observed_at, "recorded_at": row.recorded_at,
             "quality_status": row.quality_status, "authoritative": row.authoritative} for row in rows]


@router.get("/cases")
def cases(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.cases import reconcile_domain_cases
    reconcile_domain_cases(db, user.tenant_id); db.flush()
    rows = db.query(OperationalCase).filter_by(tenant_id=user.tenant_id).order_by(OperationalCase.created_at.desc()).limit(100).all()
    return [{"id": row.id, "case_type": row.case_type, "title": row.title, "severity": row.severity,
             "status": row.status, "source_event_id": row.source_event_id, "context": row.context} for row in rows]


@router.get("/work")
def work(include_closed: bool = False, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.work import list_work
    rows = list_work(db, tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id, include_closed=include_closed)
    return [{"id": row.id, "title": row.title, "status": row.status, "priority": row.priority,
             "severity": row.severity, "owner_role": row.owner_role, "owner_user_id": row.owner_user_id,
             "due_at": row.due_at, "source_type": row.entity_type, "source_id": row.entity_id,
             "task_type": row.task_type, "requested_outcome": row.requested_outcome} for row in rows]


@router.get("/sources")
def sources(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.integrations import connector_health
    return connector_health(db, user.tenant_id)


@router.get("/agent-context")
def agent_context(entity_type: str | None = None, entity_id: str | None = None,
                  db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    from app.platform.agent_runtime import build_agent_context
    return build_agent_context(db, user, entity_type=entity_type, entity_id=entity_id)


@router.get("/actions")
def list_actions(db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    rows = db.query(ActionIntent).filter_by(tenant_id=user.tenant_id).order_by(ActionIntent.created_at.desc()).limit(100).all()
    return [_intent(row, db) for row in rows]


@router.post("/actions", dependencies=[Depends(csrf_guard)])
def propose_action(payload: ActionProposal, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    membership = workspace_membership(db, user)
    row = actions.propose(db, tenant_id=user.tenant_id, plant_id=user.plant_id, membership_id=membership.id if membership else None,
                          action_type=payload.action_type, target_type=payload.target_type, target_id=payload.target_id,
                          payload=payload.payload, rationale=payload.rationale, idempotency_key=payload.idempotency_key)
    db.commit(); return _intent(row, db)


@router.get("/actions/{action_id}")
def action(action_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    row = db.query(ActionIntent).filter_by(id=action_id, tenant_id=user.tenant_id).first()
    if not row: raise HTTPException(404, "Action intent not found")
    return _intent(row, db)


@router.post("/actions/{action_id}/decision", dependencies=[Depends(csrf_guard)])
def decide_action(action_id: str, payload: ActionDecision, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    row = db.query(ActionIntent).filter_by(id=action_id, tenant_id=user.tenant_id).first()
    if not row: raise HTTPException(404, "Action intent not found")
    membership = workspace_membership(db, user)
    try: actions.decide(db, row, membership.id if membership else None, payload.approved, payload.comment)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc
    db.commit(); return _intent(row, db)


@router.post("/actions/{action_id}/execute", dependencies=[Depends(csrf_guard)])
def execute_action(action_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(platform_enabled)):
    row = db.query(ActionIntent).filter_by(id=action_id, tenant_id=user.tenant_id).first()
    if not row: raise HTTPException(404, "Action intent not found")
    try: actions.execute_simulated(db, row)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc
    db.commit(); return _intent(row, db)
