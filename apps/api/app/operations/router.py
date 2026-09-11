from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.security import current_user, require_csrf
from app.db import models
from app.db.session import SessionLocal, get_db
from app.operations import service as operational_v2
from app.operations import integrations as integrations_v2
from app.identifiers import next_business_number
from app.connector_sdk import ConnectorContext, ConnectorMode, SYNC_JOB_CAPABILITIES, get_connector, registry_manifests

router = APIRouter(prefix="/api/v2", tags=["operational-v2"])

FINANCIAL_ROLES = {"admin", "plant_manager", "purchase_manager", "corporate_operations_director"}
FINANCIAL_FIELDS = {"financial_impact", "scrap_rework_impact", "annualized_value",
                    "addressable_value", "addressable_loss_value", "business_exposure_amount",
                    "expected_value_recovered", "verified_value_recovered", "direct_cost",
                    "value_at_risk", "value_addressed", "verified_recovered_value_today"}

ROLE_HOME_KIND = {
    "plant_manager": "plant_manager", "production_manager": "production_manager",
    "production_supervisor": "supervisor", "production_operator": "operator",
    "maintenance_manager": "maintenance", "maintenance_technician": "maintenance",
    "quality_manager": "quality", "quality_inspector": "quality",
    "purchase_manager": "purchase", "purchase_executive": "purchase",
    "store_manager": "stores", "gate_operator": "gate", "admin": "admin",
    "corporate_operations_director": "corporate",
}


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def _scope(db: Session, user: models.User) -> models.OperationalScope | None:
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    return db.query(models.OperationalScope).filter_by(
        tenant_id=user.tenant_id, membership_id=membership.id).first() if membership else None


def _assert_operational_scope(db: Session, user: models.User, *, plant_id: str | None = None,
                              line_id: str | None = None, asset_id: str | None = None,
                              authority: str | None = None) -> models.OperationalScope | None:
    scope = _scope(db, user)
    if scope is None:  # backwards-compatible rollout for existing workspaces
        if plant_id and plant_id != user.plant_id:
            raise HTTPException(403, "Plant access denied")
        return None
    if plant_id and plant_id not in (scope.plant_ids or []):
        raise HTTPException(403, "Plant access denied")
    if line_id and scope.line_ids and line_id not in scope.line_ids:
        raise HTTPException(403, "Production line access denied")
    if asset_id and scope.asset_ids and asset_id not in scope.asset_ids:
        raise HTTPException(403, "Asset access denied")
    if authority and authority not in (scope.authorities or []):
        raise HTTPException(403, f"Authority {authority} is required")
    return scope


def _require_v2_module(user: models.User, module: str) -> None:
    allowed = {
        "materials": {"admin","plant_manager","production_manager","production_supervisor","purchase_manager","purchase_executive","store_manager"},
        "quality": {"admin","plant_manager","production_manager","quality_manager","quality_inspector"},
        "maintenance": {"admin","plant_manager","production_manager","maintenance_manager","maintenance_technician"},
        "improvement": {"admin","plant_manager","production_manager","maintenance_manager","quality_manager","corporate_operations_director"},
    }.get(module, set())
    if user.role not in allowed:
        raise HTTPException(403, f"Role {user.role} cannot read the {module} workspace")


def _role_scoped_payload(payload, user: models.User):
    """Redact V2 operational value fields unless the role owns financial context."""
    if user.role in FINANCIAL_ROLES:
        return payload
    if isinstance(payload, list):
        return [_role_scoped_payload(row, user) for row in payload]
    if isinstance(payload, dict):
        financial_pareto = "defect" in payload and "quantity" in payload and "value" in payload
        return {key: (None if key in FINANCIAL_FIELDS or (financial_pareto and key == "value") else _role_scoped_payload(value, user))
                for key, value in payload.items()}
    return payload


@router.get("/home")
def role_home(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    """A stable discriminated projection; never return a shared superset to the browser."""
    kind = ROLE_HOME_KIND.get(user.role, "operator")
    scope = _assert_operational_scope(db, user, plant_id=user.plant_id)
    allowed_lines = set(scope.line_ids or []) if scope else set()
    base = operational_v2.command_center(db, user.tenant_id, user.plant_id, None, None,
                                         allowed_lines if scope and scope.line_ids else None)
    deviations = base.get("top_deviations", [])
    if allowed_lines:
        deviations = [row for row in deviations if not row.get("line_id") or row.get("line_id") in allowed_lines]
    common = {
        "kind": kind, "role": user.role, "generated_at": datetime.now(timezone.utc),
        "plant_id": user.plant_id, "simulation": db.get(models.Tenant, user.tenant_id).workspace_kind == "simulation",
        "attention": deviations[:6], "data_health": base.get("data_health", []),
    }
    role_tasks = db.query(models.Task).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, owner_role=user.role).filter(
        models.Task.status.in_(("open", "accepted", "in_progress", "blocked"))).order_by(models.Task.created_at.desc()).limit(12).all()
    supplier_updates = db.query(models.SupplierChannelMessage).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, direction="inbound").order_by(
        models.SupplierChannelMessage.created_at.desc()).limit(10).all()
    projections = {
        "plant_manager": {"trajectory": base.get("pulse"), "losses": base.get("loss_breakdown", []), "decisions": base.get("decisions_required", [])},
        "production_manager": {"trajectory": base.get("pulse"), "bottlenecks": deviations, "supervisor_actions": base.get("decisions_required", []) + [{"id":row.id,"title":row.title,"status":row.status} for row in role_tasks]},
        "supervisor": {"trajectory": base.get("pulse"), "assigned_line_ids": sorted(allowed_lines), "recovery_tasks": base.get("decisions_required", [])},
        "operator": {"assigned_line_ids": sorted(allowed_lines), "immediate_actions": base.get("decisions_required", [])[:3]},
        "maintenance": {"assets": operational_v2.maintenance_workspace(db, user.tenant_id, user.plant_id,
            set(scope.asset_ids) if scope and scope.asset_ids else None).get("assets", [])},
        "quality": {"quality": operational_v2.quality_workspace(db, user.tenant_id, user.plant_id,
            allowed_lines if scope and scope.line_ids else None)},
        "purchase": {"material_risks": operational_v2.material_readiness_board(db, user.tenant_id, user.plant_id, 7,
            allowed_lines if scope and scope.line_ids else None).get("work_orders", []),
                     "supplier_updates": [{"id":row.id,"title":row.subject,"sender":row.sender,"status":row.status} for row in supplier_updates]},
        "stores": {"material_risks": operational_v2.material_readiness_board(db, user.tenant_id, user.plant_id, 2,
            allowed_lines if scope and scope.line_ids else None).get("work_orders", [])},
        "gate": {"expected_arrivals": [{"id":row.id,"title":row.title,"status":row.status,"due_at":row.due_at} for row in role_tasks], "pending_gate_entries": []},
        "admin": {"integration_health": base.get("data_health", []), "simulator_controls": common["simulation"]},
        "corporate": {"plants": operational_v2.multi_plant_workspace(db, user.tenant_id).get("plants", [])},
    }
    return _role_scoped_payload({**common, **projections[kind]}, user)


class ActualPointRequest(BaseModel):
    recorded_at: datetime
    good_quantity: float = Field(ge=0)
    reject_quantity: float = Field(default=0, ge=0)
    source_event_key: str | None = None


class GigiQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    deviation_id: str | None = None


class V2IntegrationCreate(BaseModel):
    provider: str
    name: str = Field(min_length=2, max_length=160)
    mode: str = Field(default="read_only", pattern="^(disconnected|read_only|simulation|shadow|uat)$")
    secret_ref: str | None = None
    enabled_capabilities: list[str] = Field(default_factory=list)


class V2MappingUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mappings: dict
    transforms: dict = Field(default_factory=dict)
    ownership: dict = Field(default_factory=dict)


class ImprovementExperimentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    opportunity_key: str
    hypothesis: str = Field(min_length=5)
    baseline: dict
    intervention: str = Field(min_length=5)
    target: dict
    starts_at: datetime
    ends_at: datetime


class SetupUpdate(BaseModel):
    activation_stage: str
    primary_use_case: str | None = None
    enabled_data_domains: list[str] = Field(default_factory=list)
    production_calendar: dict = Field(default_factory=dict)
    kpi_targets: dict = Field(default_factory=dict)
    loss_categories: list[dict] = Field(default_factory=list)
    escalation_rules: list[dict] = Field(default_factory=list)
    value_formulas: list[dict] = Field(default_factory=list)
    action_policies: list[dict] = Field(default_factory=list)
    completed_stages: list[str] = Field(default_factory=list)


class SetupAreaUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=1, max_length=80)


class SetupLineUpsert(BaseModel):
    area_id: str
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=1, max_length=80)
    standard_good_rate_per_minute: float = Field(gt=0)
    contribution_per_good_unit: float = Field(ge=0)


class DetectorRuleUpdate(BaseModel):
    version: int = Field(ge=1)
    enabled: bool
    parameters: dict = Field(default_factory=dict)
    severity_bands: list[dict] = Field(default_factory=list)
    owner_role: str = Field(min_length=2, max_length=64)


class EdgeCanonicalEvent(BaseModel):
    message_id: str = Field(min_length=1, max_length=160)
    event_type: str = Field(pattern="^(machine.state|production.good_count|machine.alarm)$")
    asset_id: str
    source_timestamp: datetime
    payload: dict


class PreparedActionRequest(BaseModel):
    action_type: str = Field(pattern="^(acknowledge_deviation|start_action|prepare_recovery_strategy_selection|prepare_recovery_action_sequence|prepare_reroute_request|prepare_overtime_request|prepare_material_reallocation|prepare_quality_containment|prepare_supplier_expedite|prepare_improvement_investigation)$")
    target_id: str


class PreparedActionExecute(BaseModel):
    confirmed: bool


class ShiftHandoverUpdate(BaseModel):
    summary: str = Field(min_length=5, max_length=4000)
    priorities: list[dict] = Field(default_factory=list)
    losses: list[dict] = Field(default_factory=list)
    carry_over: list[dict] = Field(default_factory=list)


class SimulationControl(BaseModel):
    action: str = Field(pattern="^(start|pause|reset|speed)$")
    speed: int | None = None


def _simulator_request(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    base = os.getenv("FACTORY_SIMULATOR_URL", "http://factory-simulator:8090").rstrip("/")
    token = os.getenv("FACTORY_SIMULATOR_TOKEN", "northstar-local-simulator-token")
    request = urllib.request.Request(base + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(503, "Factory simulator is unavailable") from exc


def _require_sim_admin(db: Session, user: models.User) -> None:
    tenant = db.get(models.Tenant, user.tenant_id)
    if not tenant or tenant.workspace_kind != "simulation":
        raise HTTPException(404, "Simulation controls are unavailable")
    _assert_operational_scope(db, user, authority="simulation.control")


def _operational_at(db: Session, user: models.User, requested: datetime | None) -> datetime | None:
    """Use the source clock for live simulation views, including accelerated runs."""
    if requested is not None:
        return requested
    tenant = db.get(models.Tenant, user.tenant_id)
    if tenant and tenant.workspace_kind == "simulation":
        try:
            return datetime.fromisoformat(_simulator_request("/sim/v1/state")["scenario_time"])
        except (KeyError, TypeError, ValueError, HTTPException):
            pass
    return None


@router.get("/simulation/state")
def simulation_state(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_sim_admin(db, user)
    return _simulator_request("/sim/v1/state")


@router.post("/simulation/control", dependencies=[Depends(csrf_guard)])
def simulation_control(payload: SimulationControl, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_sim_admin(db, user)
    return _simulator_request("/sim/v1/control", "POST", payload.model_dump(exclude_none=True))


@router.post("/simulation/scenarios/{scenario_key}", dependencies=[Depends(csrf_guard)])
def simulation_scenario(scenario_key: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_sim_admin(db, user)
    result = _simulator_request(f"/sim/v1/scenarios/{scenario_key}", "POST", {})
    from app.workers import sync_factory_simulators
    sync_factory_simulators.apply_async(queue="sync")
    return result


class QualityEventCreate(BaseModel):
    work_order_id: str
    line_id: str
    asset_id: str | None = None
    material_lot_id: str | None = None
    occurred_at: datetime
    event_type: str = Field(pattern="^(inspection|measurement|defect|rejection|hold|release)$")
    inspected_quantity: float = Field(default=0, ge=0)
    rejected_quantity: float = Field(default=0, ge=0)
    defect_code: str | None = None
    measurement_name: str | None = None
    measurement_value: float | None = None
    lower_control_limit: float | None = None
    upper_control_limit: float | None = None
    evidence: dict = Field(default_factory=dict)


class QualityCaseCreate(BaseModel):
    case_type: str = Field(pattern="^(ncr|capa)$")
    parent_case_id: str | None = None
    quality_event_id: str | None = None
    deviation_id: str | None = None
    title: str = Field(min_length=3, max_length=240)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    problem_statement: str = Field(min_length=5, max_length=4000)
    containment_summary: str | None = Field(default=None, max_length=4000)
    corrective_action: str | None = Field(default=None, max_length=4000)
    effectiveness_criteria: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None


class QualityCaseUpdate(BaseModel):
    version: int = Field(ge=1)
    status: str = Field(pattern="^(open|investigating|action_in_progress|effectiveness_review)$")
    containment_summary: str | None = Field(default=None, max_length=4000)
    root_cause: str | None = Field(default=None, max_length=4000)
    corrective_action: str | None = Field(default=None, max_length=4000)
    effectiveness_criteria: str | None = Field(default=None, max_length=2000)
    effectiveness_result: str | None = Field(default=None, max_length=2000)
    evidence: list[dict] = Field(default_factory=list)


class QualityCaseVerify(BaseModel):
    version: int = Field(ge=1)
    effectiveness_result: str = Field(min_length=5, max_length=2000)


class MaintenanceWorkCreate(BaseModel):
    asset_id: str
    fault_event_id: str | None = None
    deviation_id: str | None = None
    title: str = Field(min_length=3, max_length=240)
    owner_user_id: str | None = None
    spare_code: str | None = Field(default=None, max_length=80)
    spare_available: bool | None = None


class MaintenanceWorkTransition(BaseModel):
    version: int = Field(ge=1)
    note: str = Field(default="", max_length=4000)
    spare_available: bool | None = None


class PracticeTransferUpdate(BaseModel):
    version: int = Field(ge=1)
    status: str = Field(pattern="^(accepted|piloting|completed|rejected)$")
    outcome: dict = Field(default_factory=dict)


@router.get("/me/context")
def my_context(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    plant = db.get(models.Plant, user.plant_id)
    shifts = (db.query(models.PlantShift).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id)
              .order_by(models.PlantShift.starts_at.desc()).limit(5).all())
    return {"user": {"id": user.id, "name": user.name, "role": user.role},
            "plant": {"id": plant.id, "name": plant.name, "timezone": plant.timezone,
                      "currency": plant.currency, "locale": plant.locale} if plant else None,
            "shifts": [{"id": row.id, "name": row.name, "code": row.code,
                        "starts_at": row.starts_at, "ends_at": row.ends_at, "status": row.status} for row in shifts]}


@router.get("/plants")
def plants(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    scope = _scope(db, user)
    query = db.query(models.Plant).filter_by(tenant_id=user.tenant_id)
    if scope:
        query = query.filter(models.Plant.id.in_(scope.plant_ids or [user.plant_id]))
    return [{"id": row.id, "name": row.name, "code": row.erp_location_code} for row in query.all()]


@router.get("/plants/{plant_id}/areas")
def areas(plant_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    scope = _assert_operational_scope(db, user, plant_id=plant_id)
    query = db.query(models.PlantArea).filter_by(tenant_id=user.tenant_id, plant_id=plant_id)
    if scope and scope.area_ids: query = query.filter(models.PlantArea.id.in_(scope.area_ids))
    return [{"id": row.id, "name": row.name, "code": row.code} for row in query.all()]


@router.get("/plants/{plant_id}/lines")
def lines(plant_id: str, db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    scope = _assert_operational_scope(db, user, plant_id=plant_id)
    query = db.query(models.ProductionLine).filter_by(tenant_id=user.tenant_id, plant_id=plant_id)
    if scope and scope.line_ids: query = query.filter(models.ProductionLine.id.in_(scope.line_ids))
    return [{"id": row.id, "area_id": row.area_id, "name": row.name, "code": row.code}
            for row in query.all()]


@router.get("/plants/{plant_id}/command-center")
def get_command_center(plant_id: str, shift_id: str | None = None, at: datetime | None = Query(default=None),
                       db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if plant_id != user.plant_id:
        raise HTTPException(403, "Plant access denied")
    scope = _assert_operational_scope(db, user, plant_id=plant_id)
    at = _operational_at(db, user, at)
    payload = operational_v2.role_command_center(operational_v2.command_center(
        db, user.tenant_id, plant_id, shift_id, at,
        set(scope.line_ids) if scope and scope.line_ids else None), user.role)
    return _role_scoped_payload(payload, user)


@router.get("/plants/{plant_id}/operations/overview")
def get_operations_overview(plant_id: str, shift_id: str | None = None, at: datetime | None = Query(default=None),
                            db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    scope = _assert_operational_scope(db, user, plant_id=plant_id)
    payload = operational_v2.operations_overview(db, user.tenant_id, plant_id, shift_id,
        _operational_at(db, user, at), set(scope.line_ids) if scope and scope.line_ids else None)
    return payload


@router.get("/plants/{plant_id}/kpis")
def get_plant_kpis(plant_id: str, shift_id: str | None = None, at: datetime | None = Query(default=None),
                   db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if plant_id != user.plant_id:
        raise HTTPException(403, "Plant access denied")
    return _role_scoped_payload(operational_v2.operational_kpis(
        db, user.tenant_id, plant_id, shift_id, _operational_at(db, user, at)), user)


@router.get("/lines/{line_id}/workspace")
def get_line_workspace(line_id: str, shift_id: str | None = None, at: datetime | None = Query(default=None),
                       db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _assert_operational_scope(db, user, line_id=line_id)
    payload = operational_v2.line_workspace(db, user.tenant_id, line_id, shift_id, _operational_at(db, user, at))
    if payload is None:
        raise HTTPException(404, "Line not found")
    return _role_scoped_payload(payload, user)


def _line_workspace_or_404(db: Session, user: models.User, line_id: str,
                           shift_id: str | None = None) -> dict:
    _assert_operational_scope(db, user, line_id=line_id)
    payload = operational_v2.line_workspace(db, user.tenant_id, line_id, shift_id)
    if payload is None:
        raise HTTPException(404, "Line not found")
    return payload


@router.get("/lines/{line_id}/timeline")
def get_line_timeline(line_id: str, shift_id: str | None = None,
                      from_at: datetime | None = Query(default=None, alias="from"),
                      to_at: datetime | None = Query(default=None, alias="to"),
                      db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    rows = _line_workspace_or_404(db, user, line_id, shift_id).get("timeline", [])
    return [row for row in rows
            if (from_at is None or row.get("end") is None or row["end"] >= from_at)
            and (to_at is None or row.get("start") is None or row["start"] <= to_at)]


@router.get("/lines/{line_id}/loss-tree")
def get_line_loss_tree(line_id: str, shift_id: str | None = None,
                       from_at: datetime | None = Query(default=None, alias="from"),
                       to_at: datetime | None = Query(default=None, alias="to"),
                       db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    # The current loss tree is shift/work-order scoped. Date parameters are accepted as
    # the stable contract and will scope event aggregation as historical data matures.
    del from_at, to_at
    return _line_workspace_or_404(db, user, line_id, shift_id).get("loss_tree", [])


def _deviation(db: Session, user: models.User, deviation_id: str) -> models.OperationalDeviation:
    row = db.query(models.OperationalDeviation).filter_by(
        id=deviation_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Deviation not found")
    if row.line_id:
        _assert_operational_scope(db, user, line_id=row.line_id)
    if row.asset_id:
        _assert_operational_scope(db, user, asset_id=row.asset_id)
    return row


@router.get("/deviations")
def deviations(status: str | None = None, severity: str | None = None,
               db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    query = db.query(models.OperationalDeviation).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id)
    scope = _scope(db, user)
    if scope and scope.line_ids:
        query = query.filter((models.OperationalDeviation.line_id.is_(None)) |
                             (models.OperationalDeviation.line_id.in_(scope.line_ids)))
    if status:
        query = query.filter_by(status=status)
    if severity:
        query = query.filter_by(severity=severity)
    return _role_scoped_payload([operational_v2.serialize_deviation(row) for row in query.order_by(
        models.OperationalDeviation.estimated_financial_impact.desc()).all()], user)


@router.get("/deviations/{deviation_id}")
def get_deviation(deviation_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(authenticated_user)):
    row = _deviation(db, user, deviation_id)
    actions = db.query(models.OperationalAction).filter_by(deviation_id=row.id, tenant_id=user.tenant_id).all()
    evidence = db.query(models.OperationalEvidenceRef).filter_by(
        tenant_id=user.tenant_id, entity_type="operational_deviation", entity_id=row.id).all()
    payload = operational_v2.serialize_deviation(row)
    payload["actions"] = [operational_v2.serialize_action(item) for item in actions]
    payload["evidence"] = [{"id": item.id, "type": item.evidence_type, "summary": item.summary,
                            "source_system": item.source_system, "source_reference": item.source_reference,
                            "metadata": item.evidence_metadata} for item in evidence]
    payload["causal_context"] = operational_v2.deviation_causal_context(db, row)
    return _role_scoped_payload(payload, user)


@router.get("/deviations/{deviation_id}/timeline")
def get_deviation_timeline(deviation_id: str, db: Session = Depends(get_db),
                           user: models.User = Depends(authenticated_user)):
    return operational_v2.deviation_timeline(db, _deviation(db, user, deviation_id))


@router.get("/deviations/{deviation_id}/evidence")
def get_deviation_evidence(deviation_id: str, db: Session = Depends(get_db),
                           user: models.User = Depends(authenticated_user)):
    return operational_v2.deviation_evidence(db, _deviation(db, user, deviation_id))


@router.post("/deviations/{deviation_id}/assign", dependencies=[Depends(csrf_guard)])
def assign_deviation(deviation_id: str, owner_user_id: str | None = Body(default=None),
                     owner_role: str | None = Body(default=None), db: Session = Depends(get_db),
                     user: models.User = Depends(authenticated_user)):
    row = _deviation(db, user, deviation_id)
    if not owner_user_id and not owner_role:
        raise HTTPException(422, "An owner user or role is required")
    if owner_user_id:
        owner = db.query(models.User).filter_by(
            id=owner_user_id, tenant_id=user.tenant_id, plant_id=user.plant_id, is_active=True).first()
        if not owner:
            raise HTTPException(422, "Owner is outside the active plant scope")
    row.owner_user_id, row.owner_role, row.status = owner_user_id, owner_role, "assigned"
    for action in db.query(models.OperationalAction).filter_by(deviation_id=row.id).all():
        action.owner_user_id, action.owner_role = owner_user_id, owner_role
    db.add(models.EventOutbox(tenant_id=user.tenant_id, plant_id=user.plant_id,
        event_type="deviation.updated", aggregate_type="operational_deviation", aggregate_id=row.id,
        aggregate_version=row.version + 1, correlation_id=f"assign:{row.id}:{row.version + 1}",
        payload={"deviation_id": row.id, "owner_user_id": owner_user_id, "owner_role": owner_role}))
    db.commit()
    return operational_v2.serialize_deviation(row)


@router.post("/deviations/{deviation_id}/acknowledge", dependencies=[Depends(csrf_guard)])
def acknowledge_deviation(deviation_id: str, db: Session = Depends(get_db),
                          user: models.User = Depends(authenticated_user)):
    row = _deviation(db, user, deviation_id)
    if row.status not in {"detected", "contextualized", "assigned"}:
        raise HTTPException(409, f"Cannot acknowledge a deviation in {row.status}")
    row.status = "investigating"
    row.owner_user_id = user.id
    db.commit()
    return operational_v2.serialize_deviation(row)


@router.post("/deviations/{deviation_id}/resolve", dependencies=[Depends(csrf_guard)])
def resolve_deviation(deviation_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    row = _deviation(db, user, deviation_id)
    if row.status not in {"action_in_progress", "monitoring", "action_required", "investigating"}:
        raise HTTPException(409, f"Cannot resolve a deviation in {row.status}")
    row.status = "resolved"
    row.resolved_at = datetime.now(row.started_at.tzinfo)
    row.resolution = str(payload.get("resolution") or "Recovery completed; outcome awaiting verification")
    db.commit()
    return operational_v2.serialize_deviation(row)


@router.post("/deviations/{deviation_id}/verify", dependencies=[Depends(csrf_guard)])
def verify_deviation(deviation_id: str, payload: dict = Body(...), db: Session = Depends(get_db),
                     user: models.User = Depends(authenticated_user)):
    row = _deviation(db, user, deviation_id)
    try:
        operational_v2.verify_deviation(db, row, payload, user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return operational_v2.serialize_deviation(row)


def _action(db: Session, user: models.User, action_id: str) -> models.OperationalAction:
    row = db.query(models.OperationalAction).filter_by(
        id=action_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Action not found")
    if row.deviation_id:
        _deviation(db, user, row.deviation_id)
    return row


@router.get("/my-work")
def my_work(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    rows = (db.query(models.OperationalAction).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id)
            .filter((models.OperationalAction.owner_user_id == user.id) |
                    ((models.OperationalAction.owner_user_id.is_(None)) & (models.OperationalAction.owner_role == user.role)))
            .order_by(models.OperationalAction.due_at.asc()).all())
    groups = {"now": [], "next": [], "waiting": [], "done_today": []}
    for row in rows:
        item = operational_v2.serialize_action(row)
        dependencies = db.query(models.OperationalActionDependency).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, action_id=row.id).all()
        item["dependencies"] = [{"id": dependency.id, "title": dependency.title,
                                  "owner_role": dependency.owner_role,
                                  "status": dependency.status, "due_at": dependency.due_at,
                                  "resolved_at": dependency.resolved_at}
                                 for dependency in dependencies]
        open_dependencies = [dependency for dependency in dependencies if dependency.status != "resolved"]
        item["blocked_by"] = [{"title": dependency.title,
                                "owner_role": dependency.owner_role,
                                "elapsed_minutes": max(0, int((datetime.now(timezone.utc) -
                                    (dependency.updated_at.replace(tzinfo=timezone.utc) if dependency.updated_at.tzinfo is None else dependency.updated_at)).total_seconds() / 60))}
                               for dependency in open_dependencies]
        if row.status == "completed":
            groups["done_today"].append(item)
        elif row.status == "waiting":
            groups["waiting"].append(item)
        elif row.priority in {"urgent", "high"} or row.status in {"accepted", "in_progress"}:
            groups["now"].append(item)
        else:
            groups["next"].append(item)
    return groups


@router.get("/actions/{action_id}")
def get_action(action_id: str, db: Session = Depends(get_db),
               user: models.User = Depends(authenticated_user)):
    return operational_v2.serialize_action(_action(db, user, action_id))


@router.post("/actions/{action_id}/evidence", dependencies=[Depends(csrf_guard)], status_code=201)
def add_action_evidence(action_id: str, evidence_type: str = Body(embed=True),
                        summary: str = Body(embed=True), source_reference: str | None = Body(default=None, embed=True),
                        db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    action = _action(db, user, action_id)
    row = models.OperationalEvidenceRef(
        tenant_id=user.tenant_id, plant_id=user.plant_id, entity_type="operational_action",
        entity_id=action.id, evidence_type=evidence_type, source_system="user",
        source_reference=source_reference, summary=summary,
        evidence_metadata={"submitted_by": user.id})
    db.add(row)
    db.commit()
    return {"id": row.id, "type": row.evidence_type, "summary": row.summary}


def _command_action(action_id: str, command: str, payload: dict, db: Session, user: models.User):
    row = _action(db, user, action_id)
    try:
        operational_v2.transition_action(db, row, command, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return operational_v2.serialize_action(row)


@router.post("/actions/{action_id}/accept", dependencies=[Depends(csrf_guard)])
def accept_action(action_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db),
                  user: models.User = Depends(authenticated_user)):
    return _command_action(action_id, "accept", payload, db, user)


@router.post("/actions/{action_id}/start", dependencies=[Depends(csrf_guard)])
def start_action(action_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db),
                 user: models.User = Depends(authenticated_user)):
    return _command_action(action_id, "start", payload, db, user)


@router.post("/actions/{action_id}/wait", dependencies=[Depends(csrf_guard)])
def wait_action(action_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db),
                user: models.User = Depends(authenticated_user)):
    return _command_action(action_id, "wait", payload, db, user)


@router.post("/actions/{action_id}/complete", dependencies=[Depends(csrf_guard)])
def complete_action(action_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db),
                    user: models.User = Depends(authenticated_user)):
    return _command_action(action_id, "complete", payload, db, user)


@router.post("/actions/{action_id}/fail", dependencies=[Depends(csrf_guard)])
def fail_action(action_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db),
                user: models.User = Depends(authenticated_user)):
    return _command_action(action_id, "fail", payload, db, user)


@router.get("/stream")
def stream(plant_id: str, user: models.User = Depends(authenticated_user)):
    if plant_id != user.plant_id:
        raise HTTPException(403, "Plant access denied")
    tenant_id = user.tenant_id

    def events():
        cursor = datetime.now(timezone.utc)
        yield f"event: v2.ready\ndata: {json.dumps({'plant_id': plant_id})}\n\n"
        while True:
            db = SessionLocal()
            try:
                rows = (db.query(models.EventOutbox)
                        .filter(models.EventOutbox.tenant_id == tenant_id,
                                models.EventOutbox.plant_id == plant_id,
                                models.EventOutbox.created_at > cursor,
                                models.EventOutbox.event_type.in_((
                                    "deviation.created", "deviation.updated", "deviation.resolved",
                                    "action.created", "action.updated", "production.actual.updated",
                                    "downtime.updated", "quality.event.updated", "inventory.position.updated",
                                    "supplier.commitment.updated", "machine.event.updated", "maintenance.work.updated",
                                    "material.readiness.updated", "connector.health.changed", "gigi.activity.created",
                                    "machine.signal.updated",
                                    "recovery.case.opened", "recovery.options.generated", "recovery.strategy.recommended",
                                    "recovery.strategy.selected", "recovery.execution.started", "recovery.monitoring.started",
                                    "recovery.outcome.detected", "recovery.verified", "recovery.failed", "recovery.learning.updated",
                                )))
                        .order_by(models.EventOutbox.created_at.asc()).limit(100).all())
                for row in rows:
                    cursor = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
                    yield f"id: {row.event_id}\nevent: {row.event_type}\ndata: {json.dumps(row.payload)}\n\n"
                if not rows:
                    yield ": keepalive\n\n"
            finally:
                try:
                    db.close()
                except DBAPIError:
                    # A disconnected SSE client may be finalized after the test
                    # or worker process has already disposed its DB connection.
                    # Cleanup is idempotent; no transaction is left to commit.
                    pass
            time.sleep(2)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/work-orders/{work_order_id}/actuals", dependencies=[Depends(csrf_guard)])
def record_actual(work_order_id: str, payload: ActualPointRequest, db: Session = Depends(get_db),
                  user: models.User = Depends(authenticated_user)):
    work_order = db.query(models.ProductionWorkOrder).filter_by(
        id=work_order_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not work_order:
        raise HTTPException(404, "Work order not found")
    existing = None
    if payload.source_event_key:
        existing = db.query(models.ProductionActualPoint).filter_by(
            tenant_id=user.tenant_id, source_event_key=payload.source_event_key).first()
    if existing:
        return {"id": existing.id, "idempotent": True}
    point = models.ProductionActualPoint(
        tenant_id=user.tenant_id, plant_id=user.plant_id, work_order_id=work_order.id,
        recorded_at=payload.recorded_at, good_quantity=payload.good_quantity,
        reject_quantity=payload.reject_quantity, source="api", source_event_key=payload.source_event_key,
    )
    db.add(point)
    db.flush()
    deviation = operational_v2.evaluate_production_behind_plan(db, work_order, payload.recorded_at)
    db.commit()
    return {"id": point.id, "idempotent": False, "deviation_id": deviation.id if deviation else None}


@router.get("/gigi/briefing")
def gigi_briefing(shift_id: str | None = None, db: Session = Depends(get_db),
                  user: models.User = Depends(authenticated_user)):
    scope=_assert_operational_scope(db,user,plant_id=user.plant_id)
    center = operational_v2.command_center(db, user.tenant_id, user.plant_id, shift_id,
        _operational_at(db,user,None),set(scope.line_ids) if scope and scope.line_ids else None)
    urgent = [row for row in center["top_deviations"] if row["severity"] in {"high", "critical"}]
    role_focus = {
        "plant_manager": "I have prioritized only production-threatening deviations and decisions.",
        "quality_inspector": "I have prioritized containment, affected lots and verification work.",
        "maintenance_technician": "I have prioritized active faults, repeat history and spare dependencies.",
        "purchase_manager": "I have prioritized material risk and supplier commitment uncertainty.",
    }.get(user.role, "I have prioritized the actions assigned to your operating role.")
    top = urgent[0] if urgent else None
    return {
        "summary": f"{len(urgent)} significant deviations need coordinated recovery. {len(center['recovery_opportunities'])} recovery opportunities are active. Forecast output is {center['pulse']['forecast']:.0f} against a {center['pulse']['target']:.0f} target. {role_focus}",
        "severity": "urgent" if urgent else "normal",
        "facts": [{"label": "Forecast", "value": center["pulse"]["forecast"]},
                  {"label": "Target", "value": center["pulse"]["target"]}],
        "recommended_actions": [{"label": "Open highest-impact deviation", "deviation_id": urgent[0]["id"]}] if urgent else [],
        "evidence_refs": [{"type": "command_center", "plant_id": user.plant_id}],
        "confidence": "high",
        "recovery_summary": center["recovery_summary"],
        "recovery_opportunities": center["recovery_opportunities"][:3],
        "proactive_insight": ({"what_changed": top["title"],
                               "why_it_matters": f"{top['lost_units']:g} units are exposed if recovery does not hold.",
                               "already_doing": "The deviation engine created owned recovery work and is monitoring its SLA.",
                               "user_action": "Review the recovery owner and blocking dependencies.",
                               "deviation_id": top["id"]} if top else None),
    }


@router.post("/gigi/query")
def gigi_query(payload: GigiQueryRequest, db: Session = Depends(get_db),
               user: models.User = Depends(authenticated_user)):
    if payload.deviation_id:
        row = _deviation(db, user, payload.deviation_id)
        from app.operations.recovery.service import serialize_case
        recovery_case=db.query(models.RecoveryCase).filter_by(deviation_id=row.id).first()
        recovery=serialize_case(db,recovery_case) if recovery_case else None
        recommended=next((item for item in (recovery or {}).get("strategies",[]) if item["id"]==recovery_case.recommended_strategy_id),None) if recovery_case else None
        result = {
            "summary": f"{row.title}. It is {row.severity} and currently {row.status.replace('_', ' ')}.",
            "severity": "urgent" if row.severity in {"high", "critical"} else "watch",
            "facts": ([{"label": "Lost units", "value": row.estimated_lost_units}] +
                      ([{"label": "Estimated impact", "value": row.estimated_financial_impact,
                         "currency": row.currency}] if user.role in FINANCIAL_ROLES else [])),
            "hypotheses": [],
            "recommended_actions": [{"label": "Continue current recovery", "deviation_id": row.id}],
            "evidence_refs": [{"type": "deviation", "id": row.id},
                              {"type": "work_order", "id": row.work_order_id}],
            "confidence": "high",
            "recovery_case": recovery,
            "recommended_strategy": recommended,
            "decision_required": ({"type":"select_recovery_strategy","recovery_case_id":recovery_case.id}
                                  if recovery_case and recovery_case.status=="options_ready" else None),
        }
        return _role_scoped_payload(result, user)
    briefing = gigi_briefing(None, db, user)
    briefing["query"] = payload.query
    return briefing


@router.post("/gigi/prepare-action", dependencies=[Depends(csrf_guard)], status_code=201)
def prepare_gigi_action(payload: PreparedActionRequest, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    if payload.action_type == "acknowledge_deviation":
        target = _deviation(db, user, payload.target_id)
        if target.status not in {"detected", "contextualized", "assigned"}:
            raise HTTPException(409, f"Deviation is already {target.status}")
        title, target_type = f"Acknowledge {target.title}", "operational_deviation"
    elif payload.action_type == "start_action":
        target = _action(db, user, payload.target_id)
        if target.status not in {"open", "accepted", "waiting"}:
            raise HTTPException(409, f"Action is already {target.status}")
        title, target_type = f"Start {target.title}", "operational_action"
    else:
        recovery_case=db.query(models.RecoveryCase).filter_by(
            id=payload.target_id,tenant_id=user.tenant_id,plant_id=user.plant_id).first()
        if not recovery_case: raise HTTPException(404,"Recovery case not found")
        if recovery_case.scope_type=="line": _assert_operational_scope(db,user,line_id=recovery_case.scope_id)
        target=recovery_case; target_type="recovery_case"
        titles={"prepare_recovery_strategy_selection":"Select recommended recovery strategy",
                "prepare_recovery_action_sequence":"Prepare the selected action sequence",
                "prepare_reroute_request":"Prepare governed work-order reroute",
                "prepare_overtime_request":"Prepare overtime authorization",
                "prepare_material_reallocation":"Prepare material reallocation",
                "prepare_quality_containment":"Prepare quality containment",
                "prepare_supplier_expedite":"Prepare supplier expedite",
                "prepare_improvement_investigation":"Prepare permanent improvement investigation"}
        title=titles[payload.action_type]
    row = models.V2PreparedAction(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id,
        action_type=payload.action_type, target_type=target_type, target_id=payload.target_id,
        title=title, proposed_payload={}, confidence=1,
        evidence=[{"type": target_type, "id": payload.target_id}],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15))
    db.add(row)
    db.flush()
    db.add(models.EventOutbox(tenant_id=user.tenant_id, plant_id=user.plant_id,
        event_type="gigi.activity.created", aggregate_type="v2_prepared_action", aggregate_id=row.id,
        aggregate_version=1, correlation_id=f"gigi-prepare:{row.id}",
        payload={"prepared_action_id": row.id, "status": "prepared"}))
    db.commit()
    return {"id": row.id, "title": row.title, "status": row.status,
            "action_type": row.action_type, "target_id": row.target_id,
            "confidence": row.confidence, "evidence": row.evidence, "expires_at": row.expires_at}


@router.post("/gigi/actions/{prepared_action_id}/execute", dependencies=[Depends(csrf_guard)])
def execute_gigi_action(prepared_action_id: str, payload: PreparedActionExecute,
                        db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    row = db.query(models.V2PreparedAction).filter_by(
        id=prepared_action_id, tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Prepared action not found")
    now = datetime.now(timezone.utc)
    expires = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
    if row.status != "prepared" or expires < now:
        raise HTTPException(409, "Prepared action is no longer executable")
    if not payload.confirmed:
        raise HTTPException(422, "Explicit confirmation is required")
    if row.action_type == "acknowledge_deviation":
        target = _deviation(db, user, row.target_id)
        target.status, target.owner_user_id = "investigating", user.id
        result = {"deviation_id": target.id, "status": target.status}
    elif row.action_type == "start_action":
        target = _action(db, user, row.target_id)
        operational_v2.transition_action(db, target, "start")
        result = {"action_id": target.id, "status": target.status}
    elif row.action_type == "prepare_recovery_strategy_selection":
        from app.operations.recovery import service as recovery_service
        case=db.query(models.RecoveryCase).filter_by(id=row.target_id,tenant_id=user.tenant_id).first()
        strategy=db.get(models.RecoveryStrategy,case.recommended_strategy_id) if case else None
        if not case or not strategy: raise HTTPException(409,"No recommended recovery strategy is ready")
        scope=_scope(db,user); authorities=set(scope.authorities or []) if scope else set()
        if user.role in {"admin","plant_manager"}: authorities|=set(strategy.required_authorities or [])
        try: actions=recovery_service.select_strategy(db,case,strategy,user.id,"Gigi-prepared recommendation confirmed",authorities)
        except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
        result={"recovery_case_id":case.id,"strategy_id":strategy.id,"actions_created":len(actions)}
    else:
        # These prepare tools create governed proposals only. Execution is
        # delegated to the selected recovery actions and their authorities.
        result={"recovery_case_id":row.target_id,"prepared_request":row.action_type,"status":"prepared_for_owner"}
    row.status, row.executed_at, row.execution_result = "executed", now, result
    audit_payload = json.dumps({"prepared_action_id": row.id, "result": result}, sort_keys=True)
    db.add(models.AuditEvent(id=f"audit-{row.id}", tenant_id=user.tenant_id, plant_id=user.plant_id,
        actor_user_id=user.id, actor=user.email, action="v2.gigi.prepared_action.execute",
        entity_type=row.target_type, entity_id=row.target_id, result="success",
        correlation_id=f"gigi-execute:{row.id}", payload_hash=hashlib.sha256(audit_payload.encode()).hexdigest(),
        meta={"prepared_action_id": row.id, "human_confirmed": True}))
    db.commit()
    return {"id": row.id, "status": row.status, "result": result}


@router.get("/gigi/activity")
def gigi_activity(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    rows = db.query(models.V2PreparedAction).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id).order_by(
        models.V2PreparedAction.created_at.desc()).limit(50).all()
    prepared = [{"id": row.id, "title": row.title, "action_type": row.action_type,
             "target_id": row.target_id, "status": row.status, "confidence": row.confidence,
             "evidence": row.evidence, "created_at": row.created_at,
             "executed_at": row.executed_at, "result": row.execution_result} for row in rows]
    activities = (db.query(models.EventOutbox).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id).filter(
        models.EventOutbox.event_type.in_(("gigi.activity.created", "gigi.recommendation.created")),
        # Prepared actions already have a richer lifecycle projection above.
        # Returning their creation outbox event as a separate "active" row
        # would conceal the later human-confirmed execution state.
        models.EventOutbox.aggregate_type != "v2_prepared_action")
        .order_by(models.EventOutbox.created_at.desc()).limit(50).all())
    projected = [{"id": row.event_id, "title": row.payload.get("what_changed") or row.payload.get("summary") or "Gigi activity",
                  "action_type": row.payload.get("agent_type") or "coordination",
                  "target_id": row.payload.get("deviation_id") or row.aggregate_id,
                  "status": "active", "confidence": row.payload.get("confidence"),
                  "evidence": row.payload.get("evidence", []), "created_at": row.created_at,
                  "insight": {key: row.payload.get(key) for key in ("what_changed", "why_it_matters", "already_doing", "user_action")},
                  "executed_at": None, "result": {}} for row in activities]
    return sorted(prepared + projected, key=lambda row: row["created_at"], reverse=True)[:50]


def _financial_authority(user: models.User) -> None:
    if user.role not in {"admin", "plant_manager", "purchase_manager"}:
        raise HTTPException(403, "Financial value authority required")


@router.get("/value/summary")
def get_value_summary(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _financial_authority(user)
    return operational_v2.value_summary(db, user.tenant_id, user.plant_id)


@router.get("/deviations/{deviation_id}/value")
def get_deviation_value(deviation_id: str, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    _financial_authority(user)
    deviation = _deviation(db, user, deviation_id)
    return [operational_v2.serialize_value(row) for row in db.query(models.OperationalValueEntry).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, deviation_id=deviation.id).all()]


@router.post("/value/{entry_id}/verify", dependencies=[Depends(csrf_guard)])
def verify_value_entry(entry_id: str, db: Session = Depends(get_db),
                       user: models.User = Depends(authenticated_user)):
    _financial_authority(user)
    row = db.query(models.OperationalValueEntry).filter_by(
        id=entry_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Value entry not found")
    row.confidence_state, row.verified_by_user_id = "verified", user.id
    row.verified_at = datetime.now(timezone.utc)
    db.add(models.EventOutbox(tenant_id=user.tenant_id, plant_id=user.plant_id,
        event_type="value.verified", aggregate_type="operational_value_entry", aggregate_id=row.id,
        aggregate_version=row.version + 1, correlation_id=f"value-verify:{row.id}:{row.version + 1}",
        payload={"entry_id": row.id, "verified_by": user.id}))
    db.commit()
    return operational_v2.serialize_value(row)


@router.get("/materials/readiness")
def materials_readiness(horizon: int = Query(default=1, ge=1, le=30),
                        db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "materials")
    scope=_scope(db,user)
    return operational_v2.material_readiness_board(db, user.tenant_id, user.plant_id, horizon,
        set(scope.line_ids) if scope and scope.line_ids else None)


@router.get("/work-orders/{work_order_id}/material-readiness")
def work_order_readiness(work_order_id: str, db: Session = Depends(get_db),
                         user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "materials")
    scope=_scope(db,user);board = operational_v2.material_readiness_board(db, user.tenant_id, user.plant_id, 30,
        set(scope.line_ids) if scope and scope.line_ids else None)
    row = next((item for item in board["work_orders"] if item["work_order"]["id"] == work_order_id), None)
    if row is None:
        raise HTTPException(404, "Material readiness not found")
    return row


@router.get("/materials/{material_code}/risk")
def material_risk(material_code: str, db: Session = Depends(get_db),
                  user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "materials")
    scope=_scope(db,user);board = operational_v2.material_readiness_board(db, user.tenant_id, user.plant_id, 30,
        set(scope.line_ids) if scope and scope.line_ids else None)
    rows = [{"work_order": group["work_order"], **material}
            for group in board["work_orders"] for material in group["materials"]
            if material["material"] == material_code]
    if not rows:
        raise HTTPException(404, "Material risk not found")
    return {"material": material_code, "work_orders": rows}


@router.post("/material-requirements/{requirement_id}/recompute", dependencies=[Depends(csrf_guard)])
def recompute_readiness(requirement_id: str, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "materials")
    requirement = db.query(models.ProductionMaterialRequirement).filter_by(
        id=requirement_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not requirement:
        raise HTTPException(404, "Material requirement not found")
    snapshot = operational_v2.recompute_material_readiness(db, requirement)
    db.commit()
    return {"id": snapshot.id, "state": snapshot.state, "calculated_at": snapshot.calculated_at}


@router.get("/materials/procurement")
def procurement_v2(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "materials")
    return operational_v2.procurement_lifecycle(db, user.tenant_id, user.plant_id)


def _integration(db: Session, user: models.User, connection_id: str) -> models.IntegrationConnection:
    row = db.query(models.IntegrationConnection).filter_by(
        id=connection_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Integration not found")
    return row


@router.get("/integrations")
def v2_integrations(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return integrations_v2.list_connections(db, user.tenant_id, user.plant_id)


@router.get("/integration-catalog")
def v2_integration_catalog(user: models.User = Depends(authenticated_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")
    return [{"provider": row.provider, "display_name": row.display_name,
             "adapter_version": row.adapter_version,
             "capabilities": sorted(row.capabilities),
             "tested_capabilities": sorted(row.tested_capabilities),
             "protocols": list(row.protocols),
             "live_customer_verified": row.live_customer_verified}
            for row in registry_manifests()]


@router.post("/integrations", dependencies=[Depends(csrf_guard)])
def create_v2_integration(payload: V2IntegrationCreate, db: Session = Depends(get_db),
                          user: models.User = Depends(authenticated_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")
    try:
        connector = get_connector(payload.provider)
    except KeyError as exc:
        raise HTTPException(422, "Unknown connector provider") from exc
    enabled = set(payload.enabled_capabilities or connector.manifest.tested_capabilities)
    unsupported = enabled - connector.manifest.tested_capabilities
    if unsupported:
        raise HTTPException(422, f"Adapter has not contract-tested: {', '.join(sorted(unsupported))}")
    if payload.secret_ref and not payload.secret_ref.startswith(("vault://", "secret://", "env://")):
        raise HTTPException(422, "Use a secret-manager reference, never raw credentials")
    row = models.IntegrationConnection(
        tenant_id=user.tenant_id, plant_id=user.plant_id, provider=payload.provider,
        provider_version=connector.manifest.adapter_version, name=payload.name,
        mode=payload.mode, status="configured", capabilities=sorted(connector.manifest.capabilities),
        enabled_capabilities=sorted(enabled), writes_enabled=False,
        config={"stale_after_seconds": 900}, secret_ref=payload.secret_ref,
    )
    db.add(row)
    db.flush()
    _audit_setup_change(db, user, "integration_connection", row.id, "integration.created",
                        {"provider": row.provider, "mode": row.mode,
                         "enabled_capabilities": row.enabled_capabilities})
    db.commit()
    return integrations_v2.serialize_connection(db, row)


@router.post("/integrations/{connection_id}/test", dependencies=[Depends(csrf_guard)])
def test_v2_integration(connection_id: str, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")
    row = _integration(db, user, connection_id)
    connector = get_connector(row.provider)
    result = connector.test_connection(ConnectorContext(
        connection_id=row.id, tenant_id=user.tenant_id, plant_id=user.plant_id,
        mode=ConnectorMode(row.mode), enabled_capabilities=frozenset(row.enabled_capabilities or []),
        writes_enabled=row.writes_enabled, secret_ref=row.secret_ref,
    ))
    row.last_checked_at = datetime.now(timezone.utc)
    row.status = str(result.get("status") or "active")
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=user.plant_id, event_type="connector.health.changed",
        aggregate_type="integration_connection", aggregate_id=row.id,
        aggregate_version=row.version + 1, correlation_id=f"connector-test:{row.id}:{row.version + 1}",
        payload={"connection_id": row.id, "status": row.status},
    ))
    db.commit()
    return {"result": result, "connection": integrations_v2.serialize_connection(db, row)}


@router.post("/integrations/{connection_id}/sync", dependencies=[Depends(csrf_guard)], status_code=202)
def sync_v2_integration(connection_id: str, job_type: str = Body(embed=True),
                        db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role not in {"admin", "purchase_manager"}:
        raise HTTPException(403, "Integration sync authority required")
    row = _integration(db, user, connection_id)
    if row.mode == "disconnected":
        raise HTTPException(409, "Connection is disabled")
    required = SYNC_JOB_CAPABILITIES.get(job_type)
    if required is None:
        raise HTTPException(422, "Unsupported integration dataset")
    missing = set(required) - set(row.enabled_capabilities or [])
    if missing:
        raise HTTPException(422, f"Connection has not enabled: {', '.join(sorted(missing))}")
    job = models.IntegrationSyncJob(
        tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=row.id,
        job_type=job_type, status="queued", summary={},
    )
    db.add(job)
    db.flush()
    _audit_setup_change(db, user, "integration_sync_job", job.id, "integration_sync.queued",
                        {"connection_id": row.id, "job_type": job_type})
    db.commit()
    from app.workers import run_sync_job
    task = run_sync_job.apply_async(args=[job.id], queue="sync")
    return {"job_id": job.id, "celery_task_id": task.id, "status": job.status}


@router.get("/integrations/{connection_id}/health")
def v2_integration_health(connection_id: str, db: Session = Depends(get_db),
                          user: models.User = Depends(authenticated_user)):
    return integrations_v2.connection_health(db, _integration(db, user, connection_id))


@router.get("/integrations/{connection_id}/mappings")
def v2_integration_mappings(connection_id: str, db: Session = Depends(get_db),
                            user: models.User = Depends(authenticated_user)):
    return integrations_v2.serialize_connection(db, _integration(db, user, connection_id))["mappings"]


@router.put("/integrations/{connection_id}/mappings", dependencies=[Depends(csrf_guard)])
def update_v2_integration_mappings(connection_id: str, payload: V2MappingUpdate,
                                   db: Session = Depends(get_db),
                                   user: models.User = Depends(authenticated_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")
    connection = _integration(db, user, connection_id)
    row = integrations_v2.create_mapping_version(
        db, connection, payload.name, payload.mappings, payload.transforms, payload.ownership)
    db.commit()
    return {"id": row.id, "name": row.name, "version": row.profile_version, "status": row.status}


@router.get("/quality/workspace")
def quality_workspace(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "quality")
    scope=_scope(db,user)
    return _role_scoped_payload(operational_v2.quality_workspace(db, user.tenant_id, user.plant_id,
        set(scope.line_ids) if scope and scope.line_ids else None), user)


def _quality_authority(user: models.User) -> None:
    if user.role not in {"admin", "plant_manager", "quality_manager", "quality_inspector"}:
        raise HTTPException(403, "Quality recovery authority required")


def _quality_case(db: Session, user: models.User, case_id: str) -> models.QualityRecoveryCase:
    row = db.query(models.QualityRecoveryCase).filter_by(
        id=case_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Quality recovery case not found")
    return row


def _quality_event_and_audit(db: Session, user: models.User, row: models.QualityRecoveryCase,
                             action: str) -> None:
    db.flush()
    content = json.dumps({"case_id": row.id, "status": row.status,
                          "version": row.version}, sort_keys=True)
    correlation_id = f"quality:{row.id}:{action}:{row.version}"
    db.add(models.AuditEvent(
        id=f"audit-quality-{row.id}-{action}-{row.version}", tenant_id=user.tenant_id,
        plant_id=user.plant_id, actor_user_id=user.id, actor=user.email,
        action=f"v2.quality_case.{action}", entity_type="quality_recovery_case",
        entity_id=row.id, result="success", correlation_id=correlation_id,
        payload_hash=hashlib.sha256(content.encode()).hexdigest(),
        meta={"case_type": row.case_type, "status": row.status, "human_confirmed": True}))
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        event_type=f"quality.{row.case_type}.{action}", aggregate_type="quality_recovery_case",
        aggregate_id=row.id, aggregate_version=row.version, correlation_id=correlation_id,
        payload={"case_id": row.id, "case_number": row.business_number, "status": row.status}))


@router.post("/quality/events", dependencies=[Depends(csrf_guard)], status_code=201)
def create_quality_event(payload: QualityEventCreate, db: Session = Depends(get_db),
                         user: models.User = Depends(authenticated_user)):
    _quality_authority(user)
    work_order = db.query(models.ProductionWorkOrder).filter_by(
        id=payload.work_order_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    line = db.query(models.ProductionLine).filter_by(
        id=payload.line_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not work_order or not line or work_order.line_id != line.id:
        raise HTTPException(404, "Scoped work order and line were not found")
    if payload.event_type == "measurement" and (payload.measurement_name is None or payload.measurement_value is None):
        raise HTTPException(422, "Measurement name and value are required")
    row = models.ProductionQualityEvent(
        tenant_id=user.tenant_id, plant_id=user.plant_id, work_order_id=work_order.id,
        line_id=line.id, asset_id=payload.asset_id, material_lot_id=payload.material_lot_id,
        occurred_at=payload.occurred_at, event_type=payload.event_type,
        inspected_quantity=payload.inspected_quantity, rejected_quantity=payload.rejected_quantity,
        defect_code=payload.defect_code, measurement_name=payload.measurement_name,
        measurement_value=payload.measurement_value, lower_control_limit=payload.lower_control_limit,
        upper_control_limit=payload.upper_control_limit, evidence=payload.evidence,
        source="manual")
    db.add(row)
    db.flush()
    deviation = operational_v2.evaluate_spc_control_limit(db, row)
    if deviation is None and row.rejected_quantity:
        deviation = operational_v2.evaluate_rejection_rate(db, row)
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=user.plant_id, event_type="quality.event.recorded",
        aggregate_type="production_quality_event", aggregate_id=row.id, aggregate_version=1,
        correlation_id=f"quality-event:{row.id}",
        payload={"quality_event_id": row.id, "event_type": row.event_type,
                 "deviation_id": deviation.id if deviation else None}))
    db.commit()
    return {"id": row.id, "event_type": row.event_type,
            "deviation": operational_v2.serialize_deviation(deviation) if deviation else None}


@router.post("/quality/cases", dependencies=[Depends(csrf_guard)], status_code=201)
def create_quality_case(payload: QualityCaseCreate, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    _quality_authority(user)
    if payload.case_type == "capa" and not payload.parent_case_id:
        raise HTTPException(422, "CAPA must be linked to an NCR")
    parent = _quality_case(db, user, payload.parent_case_id) if payload.parent_case_id else None
    if parent and parent.case_type != "ncr":
        raise HTTPException(422, "CAPA parent must be an NCR")
    if payload.quality_event_id and not db.query(models.ProductionQualityEvent).filter_by(
            id=payload.quality_event_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first():
        raise HTTPException(404, "Quality event not found")
    if payload.deviation_id:
        _deviation(db, user, payload.deviation_id)
    row = models.QualityRecoveryCase(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        business_number=next_business_number(db, payload.case_type.upper(), user),
        case_type=payload.case_type, parent_case_id=payload.parent_case_id,
        quality_event_id=payload.quality_event_id, deviation_id=payload.deviation_id,
        title=payload.title, severity=payload.severity, owner_user_id=user.id,
        problem_statement=payload.problem_statement,
        containment_summary=payload.containment_summary,
        corrective_action=payload.corrective_action,
        effectiveness_criteria=payload.effectiveness_criteria, due_at=payload.due_at,
        status="open")
    db.add(row)
    _quality_event_and_audit(db, user, row, "created")
    db.commit()
    return operational_v2.serialize_quality_case(row)


@router.put("/quality/cases/{case_id}", dependencies=[Depends(csrf_guard)])
def update_quality_case(case_id: str, payload: QualityCaseUpdate, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    _quality_authority(user)
    row = _quality_case(db, user, case_id)
    if row.status in {"verified", "closed"}:
        raise HTTPException(409, "Verified or closed cases are immutable")
    if row.version != payload.version:
        raise HTTPException(412, "Quality case version is stale")
    allowed = {
        "open": {"open", "investigating"},
        "investigating": {"investigating", "action_in_progress"},
        "action_in_progress": {"action_in_progress", "effectiveness_review"},
        "effectiveness_review": {"effectiveness_review"},
    }
    if payload.status not in allowed.get(row.status, set()):
        raise HTTPException(409, f"Cannot move quality case from {row.status} to {payload.status}")
    row.status = payload.status
    row.containment_summary = payload.containment_summary
    row.root_cause = payload.root_cause
    row.corrective_action = payload.corrective_action
    row.effectiveness_criteria = payload.effectiveness_criteria
    row.effectiveness_result = payload.effectiveness_result
    row.evidence = payload.evidence
    _quality_event_and_audit(db, user, row, "updated")
    db.commit()
    return operational_v2.serialize_quality_case(row)


@router.post("/quality/cases/{case_id}/verify", dependencies=[Depends(csrf_guard)])
def verify_quality_case(case_id: str, payload: QualityCaseVerify, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    if user.role not in {"admin", "plant_manager", "quality_manager"}:
        raise HTTPException(403, "Quality manager verification required")
    row = _quality_case(db, user, case_id)
    if row.version != payload.version:
        raise HTTPException(412, "Quality case version is stale")
    if row.status != "effectiveness_review" or not row.root_cause or not row.corrective_action or not row.effectiveness_criteria:
        raise HTTPException(409, "Root cause, corrective action, criteria and effectiveness review are required")
    row.status = "verified"
    row.effectiveness_result = payload.effectiveness_result
    row.verified_by_user_id = user.id
    row.verified_at = datetime.now(timezone.utc)
    _quality_event_and_audit(db, user, row, "verified")
    db.commit()
    return operational_v2.serialize_quality_case(row)


@router.post("/quality/cases/{case_id}/close", dependencies=[Depends(csrf_guard)])
def close_quality_case(case_id: str, payload: QualityCaseVerify, db: Session = Depends(get_db),
                       user: models.User = Depends(authenticated_user)):
    if user.role not in {"admin", "plant_manager", "quality_manager"}:
        raise HTTPException(403, "Quality manager closure required")
    row = _quality_case(db, user, case_id)
    if row.version != payload.version:
        raise HTTPException(412, "Quality case version is stale")
    if row.status != "verified":
        raise HTTPException(409, "Case must be effectiveness-verified before closure")
    row.status = "closed"
    row.closed_at = datetime.now(timezone.utc)
    _quality_event_and_audit(db, user, row, "closed")
    db.commit()
    return operational_v2.serialize_quality_case(row)


@router.get("/maintenance/workspace")
def maintenance_workspace(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "maintenance")
    scope=_scope(db,user)
    return operational_v2.maintenance_workspace(db, user.tenant_id, user.plant_id,
        set(scope.asset_ids) if scope and scope.asset_ids else None)


@router.get("/maintenance/assets/{asset_id}")
def maintenance_asset(asset_id: str, db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "maintenance")
    _assert_operational_scope(db, user, asset_id=asset_id)
    workspace = operational_v2.maintenance_workspace(db, user.tenant_id, user.plant_id,{asset_id})
    row = next((item for item in workspace["assets"] if item["asset"]["id"] == asset_id), None)
    if row is None:
        raise HTTPException(404, "Asset not found")
    return row


def _maintenance_work(db: Session, user: models.User, work_id: str) -> models.MaintenanceWorkRecord:
    row = db.query(models.MaintenanceWorkRecord).filter_by(
        id=work_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if row is None:
        raise HTTPException(404, "Maintenance work not found")
    _assert_operational_scope(db,user,asset_id=row.asset_id)
    return row


def _maintenance_authority(user: models.User) -> None:
    if user.role not in {"admin", "plant_manager", "maintenance_manager", "maintenance_technician"}:
        raise HTTPException(403, "Maintenance recovery authority required")


def _maintenance_event(db: Session, user: models.User, row: models.MaintenanceWorkRecord,
                       action: str, payload: dict | None = None) -> None:
    content = {"work_id": row.id, "status": row.status, **(payload or {})}
    serialized = json.dumps(content, sort_keys=True)
    correlation = f"maintenance:{row.id}:{action}:{row.version}"
    db.add(models.AuditEvent(
        id=f"audit-{correlation}-{time.time_ns()}", tenant_id=user.tenant_id,
        plant_id=user.plant_id, actor_user_id=user.id, actor=user.email,
        action=f"v2.maintenance.{action}", entity_type="maintenance_work_record",
        entity_id=row.id, result="success", correlation_id=correlation,
        payload_hash=hashlib.sha256(serialized.encode()).hexdigest(),
        meta={"human_confirmed": True, **content}))
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        event_type=f"maintenance.{action}", aggregate_type="maintenance_work_record",
        aggregate_id=row.id, aggregate_version=row.version,
        correlation_id=correlation, payload=content))


@router.post("/maintenance/work", dependencies=[Depends(csrf_guard)], status_code=201)
def create_maintenance_work(payload: MaintenanceWorkCreate, db: Session = Depends(get_db),
                            user: models.User = Depends(authenticated_user)):
    _maintenance_authority(user)
    asset = db.query(models.PlantAsset).filter_by(
        id=payload.asset_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if asset is None:
        raise HTTPException(404, "Asset not found")
    if payload.fault_event_id and not db.query(models.AssetFaultEvent).filter_by(
            id=payload.fault_event_id, tenant_id=user.tenant_id, asset_id=asset.id).first():
        raise HTTPException(422, "Fault does not belong to this asset")
    row = models.MaintenanceWorkRecord(
        tenant_id=user.tenant_id, plant_id=user.plant_id, asset_id=asset.id,
        fault_event_id=payload.fault_event_id, deviation_id=payload.deviation_id,
        title=payload.title, status="open", owner_user_id=payload.owner_user_id or user.id,
        spare_code=payload.spare_code, spare_available=payload.spare_available)
    db.add(row)
    db.flush()
    _maintenance_event(db, user, row, "work_order.created")
    db.commit()
    return next(item for item in operational_v2.maintenance_workspace(
        db, user.tenant_id, user.plant_id)["assets"] if item["asset"]["id"] == asset.id)


def _transition_maintenance(work_id: str, command: str, payload: MaintenanceWorkTransition,
                            db: Session, user: models.User):
    _maintenance_authority(user)
    row = _maintenance_work(db, user, work_id)
    if row.version != payload.version:
        raise HTTPException(412, "Maintenance work version is stale")
    allowed = {"start": {"open", "waiting"}, "wait": {"open", "in_progress"},
               "complete": {"in_progress"}}
    if row.status not in allowed[command]:
        raise HTTPException(409, f"Cannot {command} maintenance work from {row.status}")
    now = datetime.now(timezone.utc)
    if command == "start":
        row.status = "in_progress"
        row.started_at = row.started_at or now
        if payload.spare_available is not None:
            row.spare_available = payload.spare_available
    elif command == "wait":
        if len(payload.note.strip()) < 3:
            raise HTTPException(422, "Waiting work requires a blocker note")
        row.status = "waiting"
        row.resolution = payload.note.strip()
        if payload.spare_available is not None:
            row.spare_available = payload.spare_available
    else:
        if len(payload.note.strip()) < 5:
            raise HTTPException(422, "Completion requires a resolution")
        row.status = "completed"
        row.completed_at = now
        row.resolution = payload.note.strip()
        if row.fault_event_id:
            fault = db.get(models.AssetFaultEvent, row.fault_event_id)
            if fault and fault.tenant_id == user.tenant_id and fault.cleared_at is None:
                fault.cleared_at = now
        for downtime in db.query(models.ProductionDowntimeEvent).filter_by(
                tenant_id=user.tenant_id, plant_id=user.plant_id, asset_id=row.asset_id,
                ended_at=None).all():
            downtime.ended_at = now
        if row.deviation_id:
            deviation = db.get(models.OperationalDeviation, row.deviation_id)
            if deviation and deviation.tenant_id == user.tenant_id and deviation.status not in {"verified", "closed"}:
                deviation.status = "monitoring"
                deviation.actual_state = {**(deviation.actual_state or {}),
                                          "maintenance_resolution": row.resolution,
                                          "maintenance_completed_at": now.isoformat()}
    db.flush()
    _maintenance_event(db, user, row, f"work_{'started' if command == 'start' else 'blocked' if command == 'wait' else 'completed'}",
                       {"note": payload.note, "asset_id": row.asset_id})
    db.commit()
    return next(item for item in operational_v2.maintenance_workspace(
        db, user.tenant_id, user.plant_id)["assets"] if item["asset"]["id"] == row.asset_id)


@router.post("/maintenance/work/{work_id}/start", dependencies=[Depends(csrf_guard)])
def start_maintenance_work(work_id: str, payload: MaintenanceWorkTransition,
                           db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return _transition_maintenance(work_id, "start", payload, db, user)


@router.post("/maintenance/work/{work_id}/wait", dependencies=[Depends(csrf_guard)])
def wait_maintenance_work(work_id: str, payload: MaintenanceWorkTransition,
                          db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return _transition_maintenance(work_id, "wait", payload, db, user)


@router.post("/maintenance/work/{work_id}/complete", dependencies=[Depends(csrf_guard)])
def complete_maintenance_work(work_id: str, payload: MaintenanceWorkTransition,
                              db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return _transition_maintenance(work_id, "complete", payload, db, user)


@router.get("/improvement/workspace")
def improvement_workspace(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _require_v2_module(user, "improvement")
    return _role_scoped_payload(operational_v2.improvement_workspace(db, user.tenant_id, user.plant_id), user)


@router.post("/improvement/experiments", dependencies=[Depends(csrf_guard)], status_code=201)
def create_improvement_experiment(payload: ImprovementExperimentCreate, db: Session = Depends(get_db),
                                  user: models.User = Depends(authenticated_user)):
    if user.role not in {"admin", "plant_head", "quality_manager"}:
        raise HTTPException(403, "Improvement experiment authority required")
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(422, "Experiment end must follow start")
    row = models.ImprovementExperiment(
        tenant_id=user.tenant_id, plant_id=user.plant_id, owner_user_id=user.id,
        title=payload.title, opportunity_key=payload.opportunity_key, status="draft",
        hypothesis=payload.hypothesis, baseline=payload.baseline,
        intervention=payload.intervention, target=payload.target,
        starts_at=payload.starts_at, ends_at=payload.ends_at,
    )
    db.add(row)
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=user.plant_id, event_type="improvement.experiment.created",
        aggregate_type="improvement_experiment", aggregate_id=row.id, aggregate_version=1,
        correlation_id=f"improvement:{row.id}", payload={"experiment_id": row.id}))
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/intelligence/risks")
def intelligence_risks(at: datetime | None = Query(default=None), db: Session = Depends(get_db),
                       user: models.User = Depends(authenticated_user)):
    return operational_v2.predictive_risks(db, user.tenant_id, user.plant_id, at)


@router.get("/intelligence/forecast-evaluation")
def intelligence_forecast_evaluation(db: Session = Depends(get_db),
                                     user: models.User = Depends(authenticated_user)):
    return operational_v2.forecast_evaluation(db, user.tenant_id, user.plant_id)


@router.get("/notifications")
def v2_notifications(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return operational_v2.operational_notifications(db, user)


@router.get("/search")
def v2_search(q: str = Query(min_length=1, max_length=160), db: Session = Depends(get_db),
              user: models.User = Depends(authenticated_user)):
    return operational_v2.operational_search(db, user.tenant_id, user.plant_id, q)


@router.get("/shifts/{shift_id}/briefing")
def get_shift_briefing(shift_id: str, briefing_type: str = Query(default="start", pattern="^(start|handover)$"),
                       db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    payload = operational_v2.shift_briefing(db, user.tenant_id, user.plant_id, shift_id, briefing_type)
    if payload is None:
        raise HTTPException(404, "Shift briefing not generated")
    return payload


def _shift_authority(user: models.User) -> None:
    if user.role not in {"admin", "plant_manager", "corporate_operations_director"}:
        raise HTTPException(403, "Shift supervisor authority required")


def _handover(db: Session, user: models.User, shift_id: str) -> models.ShiftBriefing:
    row = db.query(models.ShiftBriefing).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, shift_id=shift_id,
        briefing_type="handover").first()
    if row is None:
        raise HTTPException(404, "Shift handover has not been generated")
    return row


def _audit_handover(db: Session, user: models.User, row: models.ShiftBriefing, action: str) -> None:
    content = json.dumps({"handover_id": row.id, "status": row.status,
                          "summary": row.summary}, sort_keys=True)
    db.add(models.AuditEvent(
        id=f"audit-{action}-{row.id}-{row.version}", tenant_id=user.tenant_id,
        plant_id=user.plant_id, actor_user_id=user.id, actor=user.email,
        action=f"v2.shift_handover.{action}", entity_type="shift_briefing",
        entity_id=row.id, result="success", correlation_id=f"handover:{row.id}:{row.version}",
        payload_hash=hashlib.sha256(content.encode()).hexdigest(),
        meta={"shift_id": row.shift_id, "status": row.status}))


@router.post("/shifts/{shift_id}/handover/generate", dependencies=[Depends(csrf_guard)], status_code=201)
def generate_handover(shift_id: str, db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    _shift_authority(user)
    existing = db.query(models.ShiftBriefing).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, shift_id=shift_id,
        briefing_type="handover").first()
    if existing and existing.status == "published":
        raise HTTPException(409, "Published handover cannot be regenerated")
    try:
        row = operational_v2.generate_shift_record(
            db, user.tenant_id, user.plant_id, shift_id, "handover")
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.flush()
    _audit_handover(db, user, row, "generated")
    db.commit()
    return operational_v2.shift_briefing(db, user.tenant_id, user.plant_id, shift_id, "handover")


@router.put("/shifts/{shift_id}/handover", dependencies=[Depends(csrf_guard)])
def update_handover(shift_id: str, payload: ShiftHandoverUpdate, db: Session = Depends(get_db),
                    user: models.User = Depends(authenticated_user)):
    _shift_authority(user)
    row = _handover(db, user, shift_id)
    if row.status != "draft":
        raise HTTPException(409, "Only a draft handover can be edited")
    row.summary, row.priorities, row.losses, row.carry_over = (
        payload.summary, payload.priorities, payload.losses, payload.carry_over)
    _audit_handover(db, user, row, "edited")
    db.commit()
    return operational_v2.shift_briefing(db, user.tenant_id, user.plant_id, shift_id, "handover")


@router.post("/shifts/{shift_id}/handover/verify", dependencies=[Depends(csrf_guard)])
def verify_handover(shift_id: str, db: Session = Depends(get_db),
                    user: models.User = Depends(authenticated_user)):
    _shift_authority(user)
    row = _handover(db, user, shift_id)
    if row.status != "draft":
        raise HTTPException(409, "Only a draft handover can be verified")
    row.status, row.verified_by_user_id = "verified", user.id
    _audit_handover(db, user, row, "verified")
    db.commit()
    return operational_v2.shift_briefing(db, user.tenant_id, user.plant_id, shift_id, "handover")


@router.post("/shifts/{shift_id}/handover/publish", dependencies=[Depends(csrf_guard)])
def publish_handover(shift_id: str, db: Session = Depends(get_db),
                     user: models.User = Depends(authenticated_user)):
    _shift_authority(user)
    row = _handover(db, user, shift_id)
    if row.status != "verified" or not row.verified_by_user_id:
        raise HTTPException(409, "Supervisor verification is required before publication")
    row.status, row.published_at = "published", datetime.now(timezone.utc)
    _audit_handover(db, user, row, "published")
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=user.plant_id, event_type="shift.handover.published",
        aggregate_type="shift_briefing", aggregate_id=row.id, aggregate_version=row.version + 1,
        correlation_id=f"handover-published:{row.id}:{row.version + 1}",
        payload={"handover_id": row.id, "shift_id": shift_id}))
    db.commit()
    return operational_v2.shift_briefing(db, user.tenant_id, user.plant_id, shift_id, "handover")


@router.get("/setup")
def get_v2_setup(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")
    return operational_v2.setup_workspace(db, user.tenant_id, user.plant_id)


@router.put("/setup", dependencies=[Depends(csrf_guard)])
def update_v2_setup(payload: SetupUpdate, db: Session = Depends(get_db),
                    user: models.User = Depends(authenticated_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")
    row = db.query(models.OperationalSetupProfile).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if row is None:
        row = models.OperationalSetupProfile(tenant_id=user.tenant_id, plant_id=user.plant_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    _audit_setup_change(db, user, "operational_setup_profile", row.id, "profile.updated",
                        {"activation_stage": row.activation_stage,
                         "primary_use_case": row.primary_use_case})
    db.commit()
    return operational_v2.setup_workspace(db, user.tenant_id, user.plant_id)


def _audit_setup_change(db: Session, user: models.User, entity_type: str, entity_id: str,
                        action: str, payload: dict) -> None:
    content = json.dumps(payload, sort_keys=True)
    correlation_id = f"setup:{entity_type}:{entity_id}:{action}"
    db.add(models.AuditEvent(
        id=f"audit-{correlation_id}-{time.time_ns()}",
        tenant_id=user.tenant_id, plant_id=user.plant_id, actor_user_id=user.id,
        actor=user.email, action=f"v2.setup.{action}", entity_type=entity_type,
        entity_id=entity_id, result="success", correlation_id=correlation_id,
        payload_hash=hashlib.sha256(content.encode()).hexdigest(), meta={"human_confirmed": True}))
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=user.plant_id, event_type=f"setup.{action}",
        aggregate_type=entity_type, aggregate_id=entity_id, aggregate_version=1,
        correlation_id=correlation_id, payload=payload))


def _setup_admin(user: models.User) -> None:
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")


@router.put("/setup/detectors/{detector_key}", dependencies=[Depends(csrf_guard)])
def update_detector_rule(detector_key: str, payload: DetectorRuleUpdate,
                         db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    _setup_admin(user)
    row = db.query(models.OperationalDetectorRule).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, detector_key=detector_key).first()
    if row is None:
        raise HTTPException(404, "Detector rule not found")
    if row.version != payload.version:
        raise HTTPException(409, "Detector rule changed; reload before saving")
    row.enabled = payload.enabled
    row.parameters = payload.parameters
    row.severity_bands = payload.severity_bands
    row.owner_role = payload.owner_role
    row.approved_by_user_id = user.id
    _audit_setup_change(db, user, "operational_detector_rule", row.id, "detector.updated",
                        {"detector_key": row.detector_key, "enabled": row.enabled,
                         "parameters": row.parameters, "severity_bands": row.severity_bands,
                         "owner_role": row.owner_role})
    db.commit()
    return {"id": row.id, "detector_key": row.detector_key, "enabled": row.enabled,
            "parameters": row.parameters, "severity_bands": row.severity_bands,
            "owner_role": row.owner_role, "version": row.version}


@router.post("/setup/areas", dependencies=[Depends(csrf_guard)], status_code=201)
def create_setup_area(payload: SetupAreaUpsert, db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    _setup_admin(user)
    if db.query(models.PlantArea).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, code=payload.code.strip().upper()).first():
        raise HTTPException(409, "Area code already exists in this plant")
    row = models.PlantArea(tenant_id=user.tenant_id, plant_id=user.plant_id,
                           name=payload.name.strip(), code=payload.code.strip().upper())
    db.add(row)
    db.flush()
    _audit_setup_change(db, user, "plant_area", row.id, "area.created",
                        {"area_id": row.id, "name": row.name, "code": row.code})
    db.commit()
    return {"id": row.id, "name": row.name, "code": row.code, "version": row.version}


@router.put("/setup/areas/{area_id}", dependencies=[Depends(csrf_guard)])
def update_setup_area(area_id: str, payload: SetupAreaUpsert, db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    _setup_admin(user)
    row = db.query(models.PlantArea).filter_by(
        id=area_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Area not found")
    duplicate = db.query(models.PlantArea).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, code=payload.code.strip().upper()).first()
    if duplicate and duplicate.id != row.id:
        raise HTTPException(409, "Area code already exists in this plant")
    row.name, row.code = payload.name.strip(), payload.code.strip().upper()
    db.flush()
    _audit_setup_change(db, user, "plant_area", row.id, "area.updated",
                        {"area_id": row.id, "name": row.name, "code": row.code})
    db.commit()
    return {"id": row.id, "name": row.name, "code": row.code, "version": row.version}


@router.post("/setup/lines", dependencies=[Depends(csrf_guard)], status_code=201)
def create_setup_line(payload: SetupLineUpsert, db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    _setup_admin(user)
    area = db.query(models.PlantArea).filter_by(
        id=payload.area_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not area:
        raise HTTPException(404, "Area not found")
    if db.query(models.ProductionLine).filter_by(
            tenant_id=user.tenant_id, plant_id=user.plant_id, code=payload.code.strip().upper()).first():
        raise HTTPException(409, "Line code already exists in this plant")
    row = models.ProductionLine(
        tenant_id=user.tenant_id, plant_id=user.plant_id, area_id=area.id,
        name=payload.name.strip(), code=payload.code.strip().upper(),
        standard_good_rate_per_minute=payload.standard_good_rate_per_minute,
        contribution_per_good_unit=payload.contribution_per_good_unit)
    db.add(row)
    db.flush()
    _audit_setup_change(db, user, "production_line", row.id, "line.created",
                        {"line_id": row.id, "area_id": row.area_id, "code": row.code})
    db.commit()
    return {"id": row.id, "area_id": row.area_id, "name": row.name, "code": row.code,
            "standard_good_rate_per_minute": row.standard_good_rate_per_minute,
            "contribution_per_good_unit": row.contribution_per_good_unit, "version": row.version}


@router.put("/setup/lines/{line_id}", dependencies=[Depends(csrf_guard)])
def update_setup_line(line_id: str, payload: SetupLineUpsert, db: Session = Depends(get_db),
                      user: models.User = Depends(authenticated_user)):
    _setup_admin(user)
    row = db.query(models.ProductionLine).filter_by(
        id=line_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    area = db.query(models.PlantArea).filter_by(
        id=payload.area_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row or not area:
        raise HTTPException(404, "Scoped line or area not found")
    duplicate = db.query(models.ProductionLine).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, code=payload.code.strip().upper()).first()
    if duplicate and duplicate.id != row.id:
        raise HTTPException(409, "Line code already exists in this plant")
    row.area_id, row.name, row.code = area.id, payload.name.strip(), payload.code.strip().upper()
    row.standard_good_rate_per_minute = payload.standard_good_rate_per_minute
    row.contribution_per_good_unit = payload.contribution_per_good_unit
    db.flush()
    _audit_setup_change(db, user, "production_line", row.id, "line.updated",
                        {"line_id": row.id, "area_id": row.area_id, "code": row.code})
    db.commit()
    return {"id": row.id, "area_id": row.area_id, "name": row.name, "code": row.code,
            "standard_good_rate_per_minute": row.standard_good_rate_per_minute,
            "contribution_per_good_unit": row.contribution_per_good_unit, "version": row.version}


@router.get("/edge")
def get_edge_workspace(db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator authority required")
    return operational_v2.edge_workspace(db, user.tenant_id, user.plant_id)


@router.post("/edge/events", status_code=202)
def ingest_edge_event(payload: EdgeCanonicalEvent,
                      x_edge_identity: str = Header(alias="X-Edge-Identity"),
                      x_config_signature: str = Header(alias="X-Config-Signature"),
                      db: Session = Depends(get_db)):
    gateway = db.query(models.EdgeGateway).filter_by(certificate_fingerprint=x_edge_identity).first()
    if not gateway or gateway.config_signature != x_config_signature or not gateway.outbound_only:
        raise HTTPException(401, "Edge identity or signed configuration rejected")
    asset = db.query(models.PlantAsset).filter_by(
        id=payload.asset_id, tenant_id=gateway.tenant_id, plant_id=gateway.plant_id).first()
    if not asset:
        raise HTTPException(422, "Asset is not mapped inside the gateway plant scope")
    digest = hashlib.sha256(json.dumps(payload.payload, sort_keys=True).encode()).hexdigest()
    receipt, created = operational_v2.ingest_edge_canonical(
        db, gateway, message_id=payload.message_id, event_type=payload.event_type,
        asset=asset, source_timestamp=payload.source_timestamp, payload=payload.payload,
        payload_hash=digest)
    db.commit()
    return {"receipt_id": receipt.id, "status": "accepted" if created else "duplicate"}


@router.get("/corporate/operations")
def corporate_operations(at: datetime | None = Query(default=None), db: Session = Depends(get_db),
                         user: models.User = Depends(authenticated_user)):
    if user.role not in {"admin", "plant_manager"}:
        raise HTTPException(403, "Corporate operations authority required")
    return operational_v2.multi_plant_workspace(db, user.tenant_id, at)


@router.post("/corporate/practice-transfers/{transfer_id}/transition", dependencies=[Depends(csrf_guard)])
def transition_practice_transfer(transfer_id: str, payload: PracticeTransferUpdate,
                                 db: Session = Depends(get_db),
                                 user: models.User = Depends(authenticated_user)):
    if user.role not in {"admin", "plant_manager"}:
        raise HTTPException(403, "Corporate practice-transfer authority required")
    row = db.query(models.BestPracticeTransfer).filter_by(
        id=transfer_id, tenant_id=user.tenant_id).first()
    if not row:
        raise HTTPException(404, "Practice transfer not found")
    if row.version != payload.version:
        raise HTTPException(412, "Practice transfer version is stale")
    allowed = {"proposed": {"accepted", "rejected"}, "accepted": {"piloting", "rejected"},
               "piloting": {"completed", "rejected"}, "completed": set(), "rejected": set()}
    if payload.status not in allowed.get(row.status, set()):
        raise HTTPException(409, f"Cannot move practice transfer from {row.status} to {payload.status}")
    if payload.status == "completed" and not payload.outcome:
        raise HTTPException(422, "Measured local outcome is required before completion")
    now = datetime.now(timezone.utc)
    row.status = payload.status
    row.outcome = payload.outcome
    if payload.status == "accepted":
        row.accepted_by_user_id, row.accepted_at = user.id, now
    if payload.status == "completed":
        row.completed_at = now
    db.flush()
    content = json.dumps({"transfer_id": row.id, "status": row.status,
                          "outcome": row.outcome, "version": row.version}, sort_keys=True)
    correlation_id = f"practice-transfer:{row.id}:{row.status}:{row.version}"
    db.add(models.AuditEvent(
        id=f"audit-practice-{row.id}-{row.status}-{row.version}", tenant_id=user.tenant_id,
        plant_id=row.target_plant_id, actor_user_id=user.id, actor=user.email,
        action="v2.corporate.practice_transfer.transition", entity_type="best_practice_transfer",
        entity_id=row.id, result="success", correlation_id=correlation_id,
        payload_hash=hashlib.sha256(content.encode()).hexdigest(),
        meta={"status": row.status, "source_plant_id": row.source_plant_id,
              "target_plant_id": row.target_plant_id, "human_confirmed": True}))
    db.add(models.EventOutbox(
        tenant_id=user.tenant_id, plant_id=row.target_plant_id,
        event_type=f"corporate.practice_transfer.{row.status}",
        aggregate_type="best_practice_transfer", aggregate_id=row.id,
        aggregate_version=row.version, correlation_id=correlation_id,
        payload={"transfer_id": row.id, "status": row.status, "outcome": row.outcome}))
    db.commit()
    return next(item for item in operational_v2.multi_plant_workspace(db, user.tenant_id)["practice_transfers"]
                if item["id"] == row.id)


@router.get("/knowledge")
def v2_knowledge(asset_id: str | None = None, document_type: str | None = None,
                 db: Session = Depends(get_db), user: models.User = Depends(authenticated_user)):
    return operational_v2.knowledge_workspace(db, user, asset_id=asset_id, document_type=document_type)


@router.get("/knowledge/search")
def search_v2_knowledge(q: str = Query(min_length=2, max_length=500), asset_id: str | None = None,
                        document_type: str | None = None, db: Session = Depends(get_db),
                        user: models.User = Depends(authenticated_user)):
    return operational_v2.knowledge_workspace(
        db, user, query=q, asset_id=asset_id, document_type=document_type)
