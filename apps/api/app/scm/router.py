from __future__ import annotations

import json
import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import current_user, require_csrf
from app.db import models as core_models
from app.db.session import get_db
from app.domains import workflows
from app.feature_flags import enabled as feature_enabled
from app.scm import imports, manual_entries, models, service
from app.platform.events import DomainEvent, publish
from app.platform.models import DataQualityIssue
from app.scm.engine import ProjectionPoint, aggregate_points
from app.scm.acceptance_fixture import load_acceptance_dataset
from app.scm.material_recovery import create_mat182_case


router = APIRouter(prefix="/scm", tags=["scm"])


class PlanningRunRequest(BaseModel):
    as_of_at: datetime | None = None
    scenario_id: str | None = None
    demand_plan_id: str | None = None


class RecommendationDecision(BaseModel):
    decision: Literal["ACCEPTED", "REJECTED", "DEFERRED"]
    reason: str = Field(min_length=3, max_length=1000)


class SimulatedExecutionConfirmation(BaseModel):
    confirmation_reference: str = Field(min_length=3, max_length=160)


class PolicyRequest(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    rules: dict[str, Any]
    activate: bool = False


class ScenarioRequest(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    base_scenario_id: str | None = None
    baseline_run_id: str | None = None
    description: str | None = Field(default=None, max_length=1000)


class OverrideRequest(BaseModel):
    material_id: str
    override_type: Literal["DEMAND", "SUPPLY_DATE", "SUPPLY_QUANTITY", "INVENTORY", "LEAD_TIME", "SAFETY_STOCK"]
    source_entity_type: str | None = None
    source_entity_id: str | None = None
    values: dict[str, Any]
    reason: str = Field(min_length=3, max_length=1000)


class DemandPlanRequest(BaseModel):
    plan_version: str = Field(min_length=1, max_length=80)
    period_start: date
    period_end: date
    correlation_id: str | None = Field(default=None, max_length=80)


class DemandBucketRequest(BaseModel):
    product_id: str | None = None
    material_id: str | None = None
    work_order_id: str | None = None
    customer_id: str | None = None
    oem_reference: str | None = None
    bucket_date: date
    quantity: Decimal = Field(gt=0)
    demand_type: Literal["CUSTOMER_ORDER", "WORK_ORDER", "PRODUCTION_PLAN", "INDENT", "FORECAST"]
    priority: int = Field(default=100, ge=0)
    source_reference: str = Field(min_length=1, max_length=240)
    lineage: dict[str, Any] = Field(default_factory=dict)


class SavedViewRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    view_type: str = Field(min_length=2, max_length=48)
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    is_default: bool = False


class NoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class RiskUpdateRequest(BaseModel):
    status: Literal["ACKNOWLEDGED", "UNDER_REVIEW", "ACTION_PENDING", "WAITING_EXTERNAL", "MONITORING", "DISMISSED"]
    reason: str = Field(min_length=3, max_length=1000)


class MappingProfileRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    mappings: dict[str, Any]
    transforms: dict[str, Any] = Field(default_factory=dict)


class OperationalOverrideRequest(BaseModel):
    material_id: str
    adjustment_type: Literal["DEMAND", "EXPECTED_RECEIPT_DATE", "SUPPLIER_COMMITMENT", "SAFETY_STOCK"]
    values: dict[str, Any]
    reason: str = Field(min_length=3, max_length=1000)
    expires_at: datetime | None = None


class ManualDataEntryRequest(BaseModel):
    entry_type: Literal["EXPECTED_DELIVERY_CREATED", "SUPPLY_SCHEDULE_CHANGED", "SUPPLY_QUANTITY_CHANGED",
                        "GOODS_RECEIPT_RECORDED", "INVENTORY_CORRECTION_RECORDED", "DEMAND_CREATED", "DEMAND_CHANGED"]
    material_id: str
    target_entity_type: str | None = None
    target_entity_id: str | None = None
    supplier_id: str | None = None
    values: dict[str, Any]
    reason: str = Field(min_length=3, max_length=1000)
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ConflictResolutionRequest(BaseModel):
    decision: Literal["KEEP_MANUAL", "ACCEPT_IMPORTED"]
    reason: str = Field(min_length=3, max_length=1000)


class VoidEntryRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> core_models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def scm_admin(db: Session = Depends(get_db), user: core_models.User = Depends(authenticated_user)) -> core_models.User:
    membership = db.query(core_models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    permissions = set(membership.permissions or []) if membership else set()
    if user.role not in {"admin", "scm_planner"} and "scm.view" not in permissions:
        raise HTTPException(403, "SCM access requires planner authority")
    if not feature_enabled(db, user.tenant_id, "scm_control_tower", default=get_settings().scm_enabled):
        raise HTTPException(404, "SCM control tower is not enabled for this workspace")
    return user


@router.post("/demo/mat-182", dependencies=[Depends(csrf_guard)])
def mat182_demo(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    if get_settings().app_env not in {"development", "dev", "test", "staging"}:
        raise HTTPException(404, "Demo fixture is unavailable")
    case = create_mat182_case(db, user)
    db.commit()
    return {"case_id": case.id, "title": case.title, "status": case.status,
            "decision_deadline": case.decision_deadline, "recovery_state": case.recovery_state}


def scm_editor(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)) -> core_models.User:
    membership = db.query(core_models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    permissions = set(membership.permissions or []) if membership else set()
    if user.role not in {"admin", "scm_planner"} and "scm.data.write" not in permissions:
        raise HTTPException(403, "SCM data-entry authority required")
    return user


def _number(value: Decimal | int | float | None) -> float | None:
    return float(value) if value is not None else None


def _run(row: models.SCMPlanningRun) -> dict[str, Any]:
    return {
        "id": row.id, "status": row.status, "scenario_id": row.scenario_id,
        "as_of_at": row.as_of_at, "horizon_start": row.horizon_start,
        "horizon_end": row.horizon_end, "engine_version": row.engine_version,
        "policy_version": row.policy_version, "started_at": row.started_at,
        "completed_at": row.completed_at, "materials_processed": row.materials_processed,
        "exceptions_generated": row.exceptions_generated,
        "input_version_summary": row.input_version_summary, "error_summary": row.error_summary,
        "planning_profile_id": row.planning_profile_id, "demand_plan_id": row.demand_plan_id,
        "input_snapshot_id": row.input_snapshot_id, "trigger_type": row.trigger_type,
        "correlation_id": row.correlation_id, "summary": row.summary_json,
    }


def _scoped_run(db: Session, user: core_models.User, run_id: str) -> models.SCMPlanningRun:
    row = db.query(models.SCMPlanningRun).filter_by(id=run_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM planning run not found")
    return row


def _latest_run(db: Session, user: core_models.User) -> models.SCMPlanningRun | None:
    return db.query(models.SCMPlanningRun).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, status="COMPLETED"
    ).order_by(models.SCMPlanningRun.completed_at.desc()).first()


@router.get("/context")
def context(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    plant = db.get(core_models.Plant, user.plant_id)
    return {"enabled": True, "admin_only": False, "tenant_id": user.tenant_id,
            "plant": {"id": plant.id, "name": plant.name, "timezone": plant.timezone, "currency": plant.currency} if plant else None}


@router.get("/schema")
def import_schema(user: core_models.User = Depends(scm_admin)):
    return {"version": "scm-v1", "sheets": imports.SCHEMAS,
            "formats": ["xlsx", "csv", "zip_csv"], "csv_requires_entity": True}


@router.post("/imports/preview", dependencies=[Depends(csrf_guard)])
async def preview_import(
    file: UploadFile = File(...),
    mappings_json: str = Form("{}"),
    csv_entity: str | None = Form(None),
    db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin),
):
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(413, "SCM import exceeds the configured upload limit")
    try:
        mappings = json.loads(mappings_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "mappings_json must be valid JSON") from exc
    batch = imports.preview(db, user, file.filename or "upload.xlsx", content, mappings, csv_entity=csv_entity)
    db.commit()
    return imports.serialize_batch(db, batch)


@router.get("/imports")
def list_imports(limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    connection = imports.ensure_file_connection(db, user)
    db.commit()
    rows = db.query(core_models.IntegrationImportBatch).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id,
    ).order_by(core_models.IntegrationImportBatch.created_at.desc()).limit(limit).all()
    return [imports.serialize_batch(db, row, include_rows=False) for row in rows]


@router.get("/imports/{batch_id}")
def get_import(batch_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(core_models.IntegrationImportBatch).filter_by(id=batch_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM import not found")
    return imports.serialize_batch(db, row)


@router.post("/imports/{batch_id}/commit", dependencies=[Depends(csrf_guard)])
def commit_import(batch_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(core_models.IntegrationImportBatch).filter_by(id=batch_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM import not found")
    imports.commit(db, user, row)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email, "scm.import.committed", "integration_import_batch", row.id, actor_user_id=user.id, meta=row.summary)
    db.commit()
    return imports.serialize_batch(db, row)


@router.get("/data-quality")
def data_quality(limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    connection = imports.ensure_file_connection(db, user)
    bad_rows = db.query(core_models.IntegrationImportRowResult).join(
        core_models.IntegrationImportBatch, core_models.IntegrationImportBatch.id == core_models.IntegrationImportRowResult.batch_id
    ).filter(
        core_models.IntegrationImportBatch.connection_id == connection.id,
        core_models.IntegrationImportBatch.tenant_id == user.tenant_id,
        core_models.IntegrationImportRowResult.action.in_(("error", "conflict")),
    ).order_by(core_models.IntegrationImportRowResult.created_at.desc()).limit(limit).all()
    sources = db.query(models.SCMDataSourceState).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()
    now = datetime.now(timezone.utc)
    return {
        "counts": {"rejected": len([row for row in bad_rows if row.action == "error"]), "conflicts": len([row for row in bad_rows if row.action == "conflict"])},
        "rows": [{"batch_id": row.batch_id, "sheet": row.sheet_name, "row_number": row.row_number, "external_key": row.external_key, "messages": row.validation_messages} for row in bad_rows],
        "sources": [{"key": row.source_key, "status": row.status, "last_successful_import": row.last_successful_import,
                     "stale": not row.last_successful_import or (now - (row.last_successful_import if row.last_successful_import.tzinfo else row.last_successful_import.replace(tzinfo=timezone.utc))).total_seconds() > row.stale_after_seconds,
                     "records_processed": row.records_processed, "error_summary": row.error_summary} for row in sources],
    }


@router.post("/mock-data/load", dependencies=[Depends(csrf_guard)])
def mock_data(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    summary = load_acceptance_dataset(db, user)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email, "scm.mock_data.loaded", "scm_dataset", "mock_erp", actor_user_id=user.id, meta=summary)
    db.commit()
    return {"status": "loaded", "summary": summary}


@router.get("/planning-profile")
def planning_profile(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    from app.scm.planning import ensure_profile
    row = ensure_profile(db, user)
    db.commit()
    return {"id": row.id, "name": row.name, "planning_horizon_days": row.planning_horizon_days,
            "near_term_bucket": row.near_term_bucket, "long_term_bucket": row.long_term_bucket,
            "timezone": row.timezone, "currency": row.currency,
            "demand_precedence": row.demand_precedence, "active": row.is_active}


@router.post("/demand-plans", dependencies=[Depends(csrf_guard)])
def create_demand_plan(payload: DemandPlanRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    if payload.period_end < payload.period_start:
        raise HTTPException(422, "period_end must be on or after period_start")
    row = models.SCMDemandPlan(tenant_id=user.tenant_id, plant_id=user.plant_id,
        plan_version=payload.plan_version, period_start=payload.period_start,
        period_end=payload.period_end, correlation_id=payload.correlation_id, status="DRAFT")
    db.add(row)
    db.commit()
    return {"id": row.id, "plan_version": row.plan_version, "status": row.status,
            "period_start": row.period_start, "period_end": row.period_end}


@router.post("/demand-plans/{plan_id}/buckets", dependencies=[Depends(csrf_guard)])
def add_demand_bucket(plan_id: str, payload: DemandBucketRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    plan = db.query(models.SCMDemandPlan).filter_by(id=plan_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not plan:
        raise HTTPException(404, "Demand plan not found")
    if plan.status != "DRAFT":
        raise HTTPException(409, "Only draft demand plans can be changed")
    if bool(payload.product_id) == bool(payload.material_id):
        raise HTTPException(422, "Exactly one of product_id or material_id is required")
    row = models.SCMDemandBucket(tenant_id=user.tenant_id, plant_id=user.plant_id,
        demand_plan_id=plan.id, product_id=payload.product_id, material_id=payload.material_id,
        work_order_id=payload.work_order_id, customer_id=payload.customer_id,
        oem_reference=payload.oem_reference, bucket_date=payload.bucket_date,
        quantity=payload.quantity, demand_type=payload.demand_type, priority=payload.priority,
        source_reference=payload.source_reference, lineage=payload.lineage)
    db.add(row)
    db.commit()
    return {"id": row.id, "demand_plan_id": plan.id, "status": plan.status}


@router.post("/demand-plans/{plan_id}/publish", dependencies=[Depends(csrf_guard)])
def publish_demand_plan(plan_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(models.SCMDemandPlan).filter_by(id=plan_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Demand plan not found")
    if not db.query(models.SCMDemandBucket.id).filter_by(demand_plan_id=row.id).first():
        raise HTTPException(422, "A demand plan cannot be published without demand buckets")
    row.status, row.published_at = "PUBLISHED", datetime.now(timezone.utc)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email,
        "scm.demand_plan.published", "scm_demand_plan", row.id, actor_user_id=user.id,
        meta={"plan_version": row.plan_version})
    db.commit()
    return {"id": row.id, "status": row.status, "published_at": row.published_at}


@router.post("/planning-runs", status_code=202, dependencies=[Depends(csrf_guard)])
def trigger_run(payload: PlanningRunRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    try:
        row = service.create_run(db, user, as_of_at=payload.as_of_at, scenario_id=payload.scenario_id,
                                 demand_plan_id=payload.demand_plan_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    from app.workers import run_scm_planning
    task = run_scm_planning.apply_async(args=[row.id], queue="scm")
    return {**_run(row), "celery_task_id": task.id}


@router.get("/planning-runs")
def list_runs(limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    rows = db.query(models.SCMPlanningRun).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).order_by(models.SCMPlanningRun.created_at.desc()).limit(limit).all()
    return [_run(row) for row in rows]


@router.get("/planning-runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    return _run(_scoped_run(db, user, run_id))


@router.get("/planning-runs/{run_id}/input-snapshot")
def get_input_snapshot(run_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    run = _scoped_run(db, user, run_id)
    row = db.query(models.SCMPlanningInputSnapshot).filter_by(planning_run_id=run.id).first()
    if not row:
        raise HTTPException(404, "Planning input snapshot not found")
    return {"id": row.id, "snapshot_version": row.snapshot_version, "algorithm_version": row.algorithm_version,
            "payload_hash": row.payload_hash, "captured_at": row.captured_at,
            "source_freshness": row.source_freshness, "payload": row.payload}


@router.get("/planning-runs/{run_id}/changes")
def planning_run_changes(run_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    run = _scoped_run(db, user, run_id)
    rows = db.query(models.SCMPlanningRunDelta).filter_by(planning_run_id=run.id).all()
    return [{"canonical_material_id": row.canonical_material_id, "previous_run_id": row.previous_run_id,
             "previous_status": row.previous_status, "current_status": row.current_status,
             "drivers": row.drivers, "effect": row.effect} for row in rows]


@router.get("/risks")
def lifecycle_risks(status: str | None = None, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    query = db.query(models.SCMMaterialRisk).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id)
    if status:
        query = query.filter(models.SCMMaterialRisk.status == status.upper())
    rows = query.order_by(models.SCMMaterialRisk.start_date, models.SCMMaterialRisk.severity).all()
    return [{"id": row.id, "material_id": row.canonical_material_id, "risk_type": row.risk_type,
             "severity": row.severity, "status": row.status, "start_date": row.start_date,
             "end_date": row.end_date, "quantity": _number(row.quantity),
             "root_causes": row.root_causes, "affected_entities": row.affected_entities,
             "operational_case_id": row.operational_case_id, "correlation_id": row.correlation_id} for row in rows]


@router.get("/planning-runs/{run_id}/product-readiness")
def product_readiness(run_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    run = _scoped_run(db, user, run_id)
    rows = db.query(models.SCMProductReadiness).filter_by(planning_run_id=run.id).all()
    result = []
    for row in rows:
        components = db.query(models.SCMComponentReadiness).filter_by(readiness_id=row.id).all()
        result.append({"id": row.id, "product_id": row.product_id, "work_order_id": row.work_order_id,
            "required_date": row.required_date, "status": row.status,
            "total_components": row.total_components, "covered_components": row.covered_components,
            "at_risk_components": row.at_risk_components, "blocking_components": row.blocking_components,
            "affected_quantity": _number(row.affected_quantity), "explanation": row.explanation,
            "components": [{"material_id": item.material_id, "required_qty": _number(item.required_qty),
                "projected_available_qty": _number(item.projected_available_qty),
                "shortage_qty": _number(item.shortage_qty), "status": item.status,
                "lineage": item.lineage} for item in components]})
    return result


def _risk_payload(db: Session, row: models.SCMMaterialRiskSummary) -> dict[str, Any]:
    material = db.get(models.SCMMaterial, row.material_id)
    recs = db.query(models.SCMRecommendation).filter_by(risk_summary_id=row.id).all()
    supplier_name = None
    supplier_id = None
    policy = db.query(models.SCMMaterialPlantPolicy).filter_by(material_id=row.material_id, plant_id=row.plant_id).first()
    if policy and policy.default_supplier_id:
        supplier = db.get(core_models.Supplier, policy.default_supplier_id)
        supplier_id, supplier_name = supplier.id if supplier else None, supplier.name if supplier else None
    return {
        "id": row.id, "planning_run_id": row.planning_run_id,
        "material": {"id": material.id, "code": material.material_code, "description": material.description, "type": material.material_type},
        "plant_id": row.plant_id, "first_breach_date": row.first_breach_date,
        "stockout_date": row.stockout_date, "shortage_qty": _number(row.shortage_qty),
        "recovery_date": row.recovery_date, "severity": row.severity,
        "priority_score": _number(row.priority_score), "priority_factors": row.priority_factors,
        "affected_finished_goods_count": row.affected_finished_goods_count,
        "affected_customers_count": row.affected_customers_count,
        "recommended_action_count": row.recommended_action_count,
        "supplier": {"id": supplier_id, "name": supplier_name} if supplier_name else None,
        "recommendations": [_recommendation_payload(rec) for rec in recs],
        "explanation": row.explanation,
    }


def _risk_horizon(db: Session, row: models.SCMMaterialRiskSummary) -> list[dict[str, Any]]:
    points = db.query(models.SCMMaterialProjectionPoint).filter_by(
        planning_run_id=row.planning_run_id, material_id=row.material_id, plant_id=row.plant_id,
    ).order_by(models.SCMMaterialProjectionPoint.projection_date).all()
    weekly = aggregate_points((ProjectionPoint(
        item.projection_date, item.opening_balance, item.supply_qty, item.demand_qty,
        item.closing_balance, item.safety_stock_qty, item.risk_status,
    ) for item in points), "weekly")
    return [{"date": item.projection_date, "risk": item.risk_status, "closing": _number(item.closing_balance)} for item in weekly]


def _recommendation_payload(row: models.SCMRecommendation) -> dict[str, Any]:
    return {"id": row.id, "planning_run_id": row.planning_run_id, "material_id": row.material_id,
            "action_type": row.action_type, "quantity": _number(row.quantity), "current_date": row.current_date,
            "proposed_date": row.proposed_date, "reason": row.reason, "constraints_checked": row.constraints_checked,
            "evidence": row.evidence, "status": row.status, "decision_reason": row.decision_reason,
            "decided_at": row.decided_at, "rank": row.rank, "score": _number(row.score),
            "score_dimensions": row.score_dimensions, "estimated_impact": row.estimated_impact}


@router.get("/control-tower")
def control_tower(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    run = _latest_run(db, user)
    source_states = db.query(models.SCMDataSourceState).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()
    if not run:
        return {"latest_run": None, "kpis": {"materials": 0, "critical": 0, "shortages_30_days": 0, "pull_in": 0, "excess": 0}, "risks": [], "sources": []}
    risks = db.query(models.SCMMaterialRiskSummary).filter_by(planning_run_id=run.id).order_by(models.SCMMaterialRiskSummary.priority_score.desc()).all()
    recs = db.query(models.SCMRecommendation).filter_by(planning_run_id=run.id).all()
    now = datetime.now(timezone.utc)
    return {
        "latest_run": _run(run),
        "kpis": {
            "materials": len(risks), "critical": len([row for row in risks if row.severity in {"CRITICAL", "RED"}]),
            "shortages_30_days": len([row for row in risks if row.stockout_date and (row.stockout_date - run.horizon_start).days <= 30]),
            "pull_in": len([row for row in recs if row.action_type == "PULL_IN"]),
            "excess": len([row for row in recs if row.action_type in {"PUSH_OUT", "CANCEL_REDUCE"}]),
        },
        "risks": [{**_risk_payload(db, row), "horizon": _risk_horizon(db, row)} for row in risks],
        "sources": [{"key": row.source_key, "status": row.status, "last_successful_import": row.last_successful_import,
                     "stale": not row.last_successful_import or (now - (row.last_successful_import if row.last_successful_import.tzinfo else row.last_successful_import.replace(tzinfo=timezone.utc))).total_seconds() > row.stale_after_seconds} for row in source_states],
    }


@router.get("/exceptions")
def exceptions(
    severity: str | None = None, material: str | None = None, action_type: str | None = None,
    limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin),
):
    run = _latest_run(db, user)
    if not run:
        return []
    query = db.query(models.SCMMaterialRiskSummary).filter_by(planning_run_id=run.id)
    if severity:
        query = query.filter(models.SCMMaterialRiskSummary.severity == severity.upper())
    if material:
        query = query.join(models.SCMMaterial).filter(models.SCMMaterial.material_code.ilike(f"%{material}%"))
    rows = query.order_by(models.SCMMaterialRiskSummary.priority_score.desc()).limit(limit).all()
    payload = [_risk_payload(db, row) for row in rows]
    return [row for row in payload if not action_type or any(item["action_type"] == action_type.upper() for item in row["recommendations"])]


@router.get("/exceptions/{risk_id}")
def exception_detail(risk_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(models.SCMMaterialRiskSummary).filter_by(id=risk_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM exception not found")
    return _risk_payload(db, row)


@router.get("/materials")
def materials_list(search: str | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    plant = db.get(core_models.Plant, user.plant_id)
    query = db.query(models.SCMMaterial).join(models.SCMMaterialPlant).filter(
        models.SCMMaterial.tenant_id == user.tenant_id, models.SCMMaterial.company_id == plant.company_id,
        models.SCMMaterialPlant.plant_id == user.plant_id,
    )
    if search:
        query = query.filter((models.SCMMaterial.material_code.ilike(f"%{search}%")) | (models.SCMMaterial.description.ilike(f"%{search}%")))
    latest = _latest_run(db, user)
    result = []
    for material in query.order_by(models.SCMMaterial.material_code).limit(limit).all():
        risk = db.query(models.SCMMaterialRiskSummary).filter_by(planning_run_id=latest.id, material_id=material.id).first() if latest else None
        result.append({"id": material.id, "code": material.material_code, "description": material.description,
                       "type": material.material_type, "base_uom": material.base_uom_id,
                       "severity": risk.severity if risk else None, "stockout_date": risk.stockout_date if risk else None})
    return result


@router.get("/materials/{material_id}")
def material_detail(material_id: str, granularity: Literal["daily", "weekly", "monthly"] = "daily", db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    material = db.query(models.SCMMaterial).join(models.SCMMaterialPlant).filter(
        models.SCMMaterial.id == material_id, models.SCMMaterial.tenant_id == user.tenant_id,
        models.SCMMaterialPlant.plant_id == user.plant_id,
    ).first()
    if not material:
        raise HTTPException(404, "SCM material not found")
    run = _latest_run(db, user)
    risk = db.query(models.SCMMaterialRiskSummary).filter_by(planning_run_id=run.id, material_id=material.id).first() if run else None
    points = db.query(models.SCMMaterialProjectionPoint).filter_by(planning_run_id=run.id, material_id=material.id).order_by(models.SCMMaterialProjectionPoint.projection_date).all() if run else []
    projected = aggregate_points((ProjectionPoint(
        row.projection_date, row.opening_balance, row.supply_qty, row.demand_qty,
        row.closing_balance, row.safety_stock_qty, row.risk_status,
    ) for row in points), granularity)
    events = db.query(models.SCMPlanningEvent).filter_by(planning_run_id=run.id, material_id=material.id).order_by(models.SCMPlanningEvent.event_date, models.SCMPlanningEvent.priority).all() if run else []
    pegs = db.query(models.SCMSupplyDemandPeg).filter_by(planning_run_id=run.id, material_id=material.id).all() if run else []
    bom_parents = db.query(models.SCMBOM, models.SCMMaterial).join(models.SCMBOMLine, models.SCMBOMLine.bom_id == models.SCMBOM.id).join(models.SCMMaterial, models.SCMMaterial.id == models.SCMBOM.parent_material_id).filter(models.SCMBOMLine.component_material_id == material.id, models.SCMBOM.plant_id == user.plant_id).all()
    return {
        "material": {"id": material.id, "code": material.material_code, "description": material.description, "type": material.material_type, "base_uom": material.base_uom_id},
        "latest_run": _run(run) if run else None,
        "risk": _risk_payload(db, risk) if risk else None,
        "projection": [{"date": row.projection_date, "opening": _number(row.opening_balance), "supply": _number(row.supply_qty), "demand": _number(row.demand_qty), "closing": _number(row.closing_balance), "safety_stock": _number(row.safety_stock_qty), "risk": row.risk_status} for row in projected],
        "events": [{"id": row.id, "type": row.event_type, "date": row.event_date, "quantity_delta": _number(row.quantity_delta), "source_type": row.source_entity_type, "source_id": row.source_entity_id, "metadata": row.metadata_json} for row in events],
        "pegs": [{"supply_event_id": row.supply_event_id, "demand_event_id": row.demand_event_id, "quantity": _number(row.pegged_qty), "strategy": row.peg_strategy} for row in pegs],
        "impact": [{"material_id": parent.id, "code": parent.material_code, "description": parent.description, "bom_code": bom.bom_code, "revision": bom.revision} for bom, parent in bom_parents],
    }


@router.get("/recommendations")
def recommendations(status: str | None = None, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    run = _latest_run(db, user)
    if not run:
        return []
    query = db.query(models.SCMRecommendation).filter_by(planning_run_id=run.id)
    if status:
        query = query.filter(models.SCMRecommendation.status == status.upper())
    return [_recommendation_payload(row) for row in query.order_by(models.SCMRecommendation.created_at.desc()).all()]


@router.post("/recommendations/{recommendation_id}/decision", dependencies=[Depends(csrf_guard)])
def decide_recommendation(recommendation_id: str, payload: RecommendationDecision, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(models.SCMRecommendation).filter_by(id=recommendation_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM recommendation not found")
    if row.status != "PENDING":
        raise HTTPException(409, "Recommendation already has a decision")
    row.status, row.decision_reason = payload.decision, payload.reason
    row.decided_by_user_id, row.decided_at = user.id, datetime.now(timezone.utc)
    if payload.decision == "ACCEPTED":
        from app.core.permissions import workspace_membership
        from app.platform.actions import propose
        membership = workspace_membership(db, user)
        platform_action_type = "procurement.po.reschedule" if row.source_entity_type in {"po_draft", "purchase_order"} else "scm.supply.expedite"
        propose(
            db, tenant_id=user.tenant_id, plant_id=user.plant_id,
            membership_id=membership.id if membership else None,
            action_type=platform_action_type,
            target_type=row.source_entity_type or "scm_recommendation",
            target_id=row.source_entity_id or row.id,
            payload={"recommendation_id": row.id, "quantity": str(row.quantity),
                     "current_date": row.current_date.isoformat() if row.current_date else None,
                     "proposed_date": row.proposed_date.isoformat() if row.proposed_date else None},
            rationale=row.reason,
            idempotency_key=f"scm-recommendation:{row.id}",
        )
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email, f"scm.recommendation.{payload.decision.lower()}", "scm_recommendation", row.id, actor_user_id=user.id, meta={"reason": payload.reason, "erp_write": False})
    db.commit()
    return _recommendation_payload(row)


@router.get("/policies")
def policies(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    rows = db.query(models.SCMPlanningPolicySet).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).order_by(models.SCMPlanningPolicySet.policy_version.desc()).all()
    return [{"id": row.id, "name": row.name, "version": row.policy_version, "status": row.status, "rules": row.rules, "effective_from": row.effective_from} for row in rows]


@router.post("/policies", dependencies=[Depends(csrf_guard)])
def create_policy(payload: PolicyRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    latest = db.query(func.max(models.SCMPlanningPolicySet.policy_version)).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, name=payload.name).scalar() or 0
    if payload.activate:
        db.query(models.SCMPlanningPolicySet).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, status="ACTIVE").update({"status": "RETIRED"}, synchronize_session=False)
    row = models.SCMPlanningPolicySet(tenant_id=user.tenant_id, plant_id=user.plant_id, name=payload.name, policy_version=latest + 1, status="ACTIVE" if payload.activate else "DRAFT", effective_from=datetime.now(timezone.utc) if payload.activate else None, rules=payload.rules, created_by_user_id=user.id, approved_by_user_id=user.id if payload.activate else None, approved_at=datetime.now(timezone.utc) if payload.activate else None)
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "version": row.policy_version, "status": row.status, "rules": row.rules}


@router.post("/scenarios", dependencies=[Depends(csrf_guard)])
def create_scenario(payload: ScenarioRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    baseline = db.get(models.SCMPlanningRun, payload.baseline_run_id) if payload.baseline_run_id else _latest_run(db, user)
    row = models.SCMPlanningScenario(tenant_id=user.tenant_id, plant_id=user.plant_id, name=payload.name,
        scenario_type="WHAT_IF", base_scenario_id=payload.base_scenario_id,
        baseline_run_id=baseline.id if baseline else None, description=payload.description,
        created_by_user_id=user.id, status="ACTIVE")
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "type": row.scenario_type, "status": row.status}


@router.post("/scenarios/{scenario_id}/overrides", dependencies=[Depends(csrf_guard)])
def add_override(scenario_id: str, payload: OverrideRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    scenario = db.query(models.SCMPlanningScenario).filter_by(id=scenario_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    material = db.query(models.SCMMaterialPlant).filter_by(material_id=payload.material_id, plant_id=user.plant_id).first()
    if not scenario or not material:
        raise HTTPException(404, "Scenario or material not found")
    row = models.SCMScenarioOverride(tenant_id=user.tenant_id, plant_id=user.plant_id, scenario_id=scenario.id, material_id=payload.material_id, override_type=payload.override_type, source_entity_type=payload.source_entity_type, source_entity_id=payload.source_entity_id, values=payload.values, reason=payload.reason)
    db.add(row)
    db.commit()
    return {"id": row.id, "scenario_id": scenario.id, "override_type": row.override_type, "values": row.values}


@router.post("/recommendations/{recommendation_id}/simulate", dependencies=[Depends(csrf_guard)])
def simulate_recommendation(recommendation_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(models.SCMRecommendation).filter_by(id=recommendation_id,
        tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM recommendation not found")
    from app.scm.recommendations import simulate
    simulation = simulate(db, row)
    db.commit()
    return {"id": simulation.id, "recommendation_id": row.id, "status": simulation.status,
            "before": simulation.before_metrics, "after": simulation.after_metrics,
            "resolves_risk": simulation.resolves_risk, "explanation": simulation.explanation}


@router.post("/recommendations/{recommendation_id}/create-action", dependencies=[Depends(csrf_guard)])
def create_recommendation_action(recommendation_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(models.SCMRecommendation).filter_by(id=recommendation_id,
        tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM recommendation not found")
    simulation = simulate_recommendation(recommendation_id, db, user)
    if not simulation["resolves_risk"]:
        raise HTTPException(409, "Candidate simulation does not resolve the projected risk")
    from app.core.permissions import workspace_membership
    from app.platform.actions import propose
    risk = db.get(models.SCMMaterialRiskSummary, row.risk_summary_id)
    lifecycle = db.query(models.SCMMaterialRisk).filter_by(latest_planning_run_id=row.planning_run_id,
        material_id=row.material_id).first()
    membership = workspace_membership(db, user)
    action_types = {"PULL_IN": "RESCHEDULE_PURCHASE_ORDER", "RESCHEDULE_PURCHASE_ORDER": "RESCHEDULE_PURCHASE_ORDER", "PUSH_OUT": "RESCHEDULE_PURCHASE_ORDER",
                    "CANCEL_REDUCE": "CANCEL_PURCHASE_ORDER", "INTERPLANT_TRANSFER": "TRANSFER_INVENTORY",
                    "NEW_BUY": "CREATE_PURCHASE_ORDER"}
    intent = propose(db, tenant_id=user.tenant_id, plant_id=user.plant_id,
        membership_id=membership.id if membership else None,
        action_type=action_types.get(row.action_type, row.action_type),
        target_type=row.source_entity_type or "material", target_id=row.source_entity_id or row.material_id,
        payload={"recommendation_id": row.id, "quantity": str(row.quantity),
                 "target_date": row.proposed_date.isoformat() if row.proposed_date else None},
        rationale=row.reason, idempotency_key=f"scm-recommendation:{row.id}",
        correlation_id=lifecycle.correlation_id if lifecycle else None,
        originating_case_id=lifecycle.operational_case_id if lifecycle else None,
        evidence=row.evidence, expected_impact=row.estimated_impact,
        confidence=0.9, risk_level="high" if risk and risk.severity in {"CRITICAL", "RED"} else "medium")
    row.status = "ACCEPTED"
    row.decided_by_user_id, row.decided_at = user.id, datetime.now(timezone.utc)
    db.commit()
    return {"action_intent_id": intent.id, "status": intent.status, "simulation": simulation}


@router.post("/recommendations/{recommendation_id}/confirm-simulated-execution", dependencies=[Depends(csrf_guard)])
def confirm_simulated_execution(recommendation_id: str, payload: SimulatedExecutionConfirmation,
                                db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    """Apply a chosen intervention to demo source facts and immediately replan.

    This endpoint is deliberately unavailable in production.  It provides an
    end-to-end pilot test without pretending to be an ERP connector receipt.
    """
    tenant = db.get(core_models.Tenant, user.tenant_id)
    if get_settings().app_env not in {"development", "dev", "test", "staging"} or (
            tenant and tenant.workspace_kind not in {"demo", "simulation"}):
        raise HTTPException(404, "Simulated execution is only available in demo workspaces")
    row = db.query(models.SCMRecommendation).filter_by(id=recommendation_id,
        tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "SCM recommendation not found")
    if row.status != "ACCEPTED":
        raise HTTPException(409, "Accept the recommendation before confirming simulated execution")
    from app.scm.recommendations import simulate
    simulation = simulate(db, row)
    if not simulation.resolves_risk:
        raise HTTPException(409, "The deterministic simulation does not resolve this risk")

    applied_to = None
    if row.action_type in {"PULL_IN", "RESCHEDULE_PURCHASE_ORDER", "PUSH_OUT"}:
        schedule = db.get(models.SCMSupplyScheduleLine, row.source_entity_id)
        if not schedule:
            schedule = db.query(models.SCMSupplyScheduleLine).join(models.SCMSupplyOrder).filter(
                models.SCMSupplyOrder.tenant_id == user.tenant_id,
                models.SCMSupplyOrder.plant_id == user.plant_id,
                models.SCMSupplyOrder.source_entity_id == row.source_entity_id).first()
        if not schedule or not row.proposed_date:
            raise HTTPException(409, "The recommendation's source supply can no longer be resolved")
        schedule.current_due_date = row.proposed_date
        applied_to = schedule.id
    elif row.action_type == "NEW_BUY":
        order = models.SCMSupplyOrder(tenant_id=user.tenant_id, plant_id=user.plant_id,
            supply_type="PURCHASE_ORDER", material_id=row.material_id, supplier_id=None,
            order_number=f"SIM-{row.id[:8]}", line_number="1", ordered_qty=row.quantity,
            received_qty=0, uom_id="EA", status="OPEN", firmness="FIRM",
            source_system="simulated_execution", source_record_id=f"recommendation:{row.id}")
        db.add(order); db.flush()
        schedule = models.SCMSupplyScheduleLine(tenant_id=user.tenant_id, plant_id=user.plant_id,
            supply_order_id=order.id, schedule_line_number="1", scheduled_qty=row.quantity,
            received_qty=0, original_due_date=row.proposed_date, current_due_date=row.proposed_date,
            status="CONFIRMED", source_record_id=f"recommendation:{row.id}")
        db.add(schedule); db.flush(); applied_to = schedule.id
    else:
        raise HTTPException(409, f"Demo source application is not available for {row.action_type}")

    row.status = "EXECUTED_SIMULATION"
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email,
        "scm.recommendation.simulated_execution_confirmed", "scm_recommendation", row.id,
        actor_user_id=user.id, meta={"confirmation_reference": payload.confirmation_reference,
                                    "source_record_id": applied_to})
    run = service.create_run(db, user, trigger_key=f"simulated-execution:{row.id}",
                             trigger_type="MANUAL", correlation_id=f"scm-resolution:{row.id}")
    service.execute_run(db, run.id)
    db.commit()
    lifecycle = db.query(models.SCMMaterialRisk).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id, material_id=row.material_id).first()
    return {"recommendation_id": row.id, "source_record_id": applied_to,
            "planning_run_id": run.id, "planning_summary": run.summary_json,
            "risk_status": lifecycle.status if lifecycle else "RESOLVED",
            "case_id": lifecycle.operational_case_id if lifecycle else None}


@router.post("/planning-runs/run-now", dependencies=[Depends(csrf_guard)])
def run_planning_now(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    """Synchronous operator replan, useful for manual/pilot evidence confirmation."""
    run = service.create_run(db, user, trigger_type="MANUAL")
    service.execute_run(db, run.id)
    db.commit()
    return _run(run)


@router.get("/supply-horizon")
def supply_horizon(days: int = Query(210), risk: str | None = None,
                   limit: int = Query(500, ge=1, le=5000), db: Session = Depends(get_db),
                   user: core_models.User = Depends(scm_admin)):
    if days not in {30, 90, 210, 365}:
        raise HTTPException(422, "Planning horizon must be 30, 90, 210, or 365 days")
    run = _latest_run(db, user)
    if not run:
        return {"run": None, "days": days, "rows": [], "summary": {}}
    plant = db.get(core_models.Plant, user.plant_id)
    horizon_end = min(run.horizon_end, run.horizon_start + timedelta(days=days - 1))
    material_ids = [row[0] for row in db.query(models.SCMMaterialProjectionPoint.material_id).filter_by(
        planning_run_id=run.id).distinct().limit(limit).all()]
    materials = {row.id: row for row in db.query(models.SCMMaterial).filter(
        models.SCMMaterial.id.in_(material_ids or ["-"])).all()}
    point_rows = db.query(models.SCMMaterialProjectionPoint).filter(
        models.SCMMaterialProjectionPoint.planning_run_id == run.id,
        models.SCMMaterialProjectionPoint.material_id.in_(material_ids or ["-"]),
        models.SCMMaterialProjectionPoint.projection_date <= horizon_end).order_by(
            models.SCMMaterialProjectionPoint.material_id,
            models.SCMMaterialProjectionPoint.projection_date).all()
    event_rows = db.query(models.SCMPlanningEvent).filter(
        models.SCMPlanningEvent.planning_run_id == run.id,
        models.SCMPlanningEvent.material_id.in_(material_ids or ["-"]),
        models.SCMPlanningEvent.event_date.between(run.horizon_start, horizon_end)).all()
    summaries = {row.material_id: row for row in db.query(models.SCMMaterialRiskSummary).filter(
        models.SCMMaterialRiskSummary.planning_run_id == run.id,
        models.SCMMaterialRiskSummary.material_id.in_(material_ids or ["-"])).all()}
    windows_by_material: dict[str, list[models.SCMShortageWindow]] = {}
    for window in db.query(models.SCMShortageWindow).filter(
            models.SCMShortageWindow.planning_run_id == run.id,
            models.SCMShortageWindow.material_id.in_(material_ids or ["-"])).order_by(
                models.SCMShortageWindow.start_date).all():
        windows_by_material.setdefault(window.material_id, []).append(window)
    recommendations_by_material: dict[str, list[models.SCMRecommendation]] = {}
    for recommendation in db.query(models.SCMRecommendation).filter(
            models.SCMRecommendation.planning_run_id == run.id,
            models.SCMRecommendation.material_id.in_(material_ids or ["-"])).order_by(
                models.SCMRecommendation.rank.asc().nullslast(), models.SCMRecommendation.created_at).all():
        recommendations_by_material.setdefault(recommendation.material_id, []).append(recommendation)
    policies = {row.material_id: row for row in db.query(models.SCMMaterialPlantPolicy).filter(
        models.SCMMaterialPlantPolicy.tenant_id == user.tenant_id,
        models.SCMMaterialPlantPolicy.plant_id == user.plant_id,
        models.SCMMaterialPlantPolicy.material_id.in_(material_ids or ["-"])).all()}
    supplier_ids = {row.default_supplier_id for row in policies.values() if row.default_supplier_id}
    suppliers = {row.id: row for row in db.query(core_models.Supplier).filter(
        core_models.Supplier.id.in_(supplier_ids or ["-"])).all()}
    lifecycle = {row.material_id: row for row in db.query(models.SCMMaterialRisk).filter(
        models.SCMMaterialRisk.tenant_id == user.tenant_id,
        models.SCMMaterialRisk.plant_id == user.plant_id,
        models.SCMMaterialRisk.material_id.in_(material_ids or ["-"])).all()}

    points_by_material: dict[str, list[models.SCMMaterialProjectionPoint]] = {}
    for point in point_rows:
        points_by_material.setdefault(point.material_id, []).append(point)
    events_by_material: dict[str, list[models.SCMPlanningEvent]] = {}
    for event in event_rows:
        events_by_material.setdefault(event.material_id, []).append(event)

    def state(value: str) -> str:
        return {"RED": "CRITICAL", "GREEN": "HEALTHY", "AT_RISK": "WATCH",
                "YELLOW": "WATCH"}.get(value.upper(), value.upper())

    rows = []
    for material_id in material_ids:
        material_points = points_by_material.get(material_id, [])
        states = {state(point.planning_status) for point in material_points}
        requested = state(risk) if risk else None
        if requested and requested not in states:
            continue
        segments = []
        for point in material_points:
            point_state = state(point.planning_status)
            if segments and segments[-1]["state"] == point_state:
                segment = segments[-1]
                segment["end_date"] = point.projection_date
                segment["demand"] += _number(point.demand_qty) or 0
                segment["receipts"] += _number(point.supply_qty) or 0
                segment["closing"] = _number(point.closing_balance)
                segment["minimum_closing"] = min(segment["minimum_closing"], _number(point.closing_balance) or 0)
                segment["maximum_shortage"] = max(segment["maximum_shortage"], _number(point.shortage_qty) or 0)
            else:
                segments.append({"start_date": point.projection_date, "end_date": point.projection_date,
                    "state": point_state, "opening": _number(point.opening_balance),
                    "demand": _number(point.demand_qty) or 0, "receipts": _number(point.supply_qty) or 0,
                    "closing": _number(point.closing_balance), "minimum_closing": _number(point.closing_balance) or 0,
                    "safety_stock": _number(point.safety_stock_qty) or 0,
                    "maximum_shortage": _number(point.shortage_qty) or 0})
        policy = policies.get(material_id)
        supplier = suppliers.get(policy.default_supplier_id) if policy and policy.default_supplier_id else None
        recommendation_rows = recommendations_by_material.get(material_id, [])
        timeline_events = []
        for event in events_by_material.get(material_id, []):
            if event.quantity_delta <= 0:
                continue
            metadata = event.metadata_json or {}
            timeline_events.append({"type": "PO_RECEIPT", "date": event.event_date,
                "quantity": _number(event.quantity_delta), "label": metadata.get("order_number") or event.source_entity_id,
                "entity_id": event.source_entity_id, "supplier": supplier.name if supplier else None,
                "status": metadata.get("status"), "original_date": metadata.get("original_due_date")})
        for recommendation in recommendation_rows:
            event_date = recommendation.proposed_date or recommendation.current_date or (
                summaries.get(material_id).first_breach_date if summaries.get(material_id) else None)
            if event_date and run.horizon_start <= event_date <= horizon_end:
                timeline_events.append({"type": "INTERVENTION", "date": event_date,
                    "label": recommendation.action_type.replace("_", " ").title(),
                    "entity_id": recommendation.id, "status": recommendation.status})
            if recommendation.action_type == "CANCEL_REDUCE" and recommendation.current_date:
                deadline = recommendation.current_date - timedelta(days=policy.cancellation_window_days or 0) if policy else recommendation.current_date
                if run.horizon_start <= deadline <= horizon_end:
                    timeline_events.append({"type": "CANCELLATION_DEADLINE", "date": deadline,
                        "label": "Cancellation deadline", "entity_id": recommendation.id})
        summary = summaries.get(material_id)
        active_risk = lifecycle.get(material_id)
        material = materials.get(material_id)
        first_point, last_point = (material_points[0], material_points[-1]) if material_points else (None, None)
        rows.append({"material": {"id": material.id, "code": material.material_code,
            "description": material.description, "category": material.material_type},
            "case_id": active_risk.operational_case_id if active_risk else None,
            "status": min(states, key=lambda item: {"CRITICAL": 0, "WATCH": 1, "EXCESS": 2,
                "HEALTHY": 3, "UNKNOWN": 4}.get(item, 5)) if states else "UNKNOWN",
            "supplier": ({"id": supplier.id, "name": supplier.name} if supplier else None),
            "segments": segments, "events": sorted(timeline_events, key=lambda item: item["date"]),
            "risk_windows": [{"start_date": window.start_date, "end_date": window.end_date,
                "duration_days": window.duration_days, "maximum_shortage": _number(window.max_shortage_qty),
                "recovery_date": window.recovery_date, "severity": "CRITICAL"}
                for window in windows_by_material.get(material_id, [])],
            "coverage": {"on_hand": _number(first_point.opening_balance) if first_point else 0,
                "on_order": sum((_number(event.quantity_delta) or 0) for event in events_by_material.get(material_id, []) if event.quantity_delta > 0),
                "safety_stock": _number(first_point.safety_stock_qty) if first_point else 0,
                "end_balance": _number(last_point.closing_balance) if last_point else 0,
                "runway_days": first_point.runway_days if first_point else None,
                "projected_runout": summary.stockout_date if summary else None},
            "recommendation": (_recommendation_payload(recommendation_rows[0]) if recommendation_rows else None),
            "affected": [{"entity_type": node.get("entity_type") or node.get("type") or "entity",
                "entity_id": node.get("entity_id") or node.get("id") or "unknown",
                "label": node.get("label") or node.get("name") or node.get("code")}
                for node in (active_risk.affected_entities if active_risk else [])],
            # Retain raw points temporarily for material-detail compatibility; the timeline uses segments.
            "points": [{"date": point.projection_date, "closing": _number(point.closing_balance),
                "status": point.planning_status, "shortage": _number(point.shortage_qty),
                "excess": _number(point.excess_qty)} for point in material_points],
            "receipts": [{"date": event["date"], "quantity": event.get("quantity") or 0,
                "source_id": event.get("entity_id") or ""} for event in timeline_events if event["type"] == "PO_RECEIPT"]})
    all_recommendations = [item for values in recommendations_by_material.values() for item in values]
    return {"run": _run(run), "days": days, "horizon_start": run.horizon_start,
        "plant": ({"id": plant.id, "name": plant.name} if plant else None),
        "horizon_end": horizon_end, "rows": rows, "summary": {
            "critical_materials": len([row for row in rows if row["status"] == "CRITICAL"]),
            "shortage_windows": sum(len(row["risk_windows"]) for row in rows),
            "pull_in_opportunities": len([row for row in all_recommendations if row.action_type in {"PULL_IN", "RESCHEDULE_PURCHASE_ORDER"}]),
            "cancellation_windows": len([row for row in all_recommendations if row.action_type == "CANCEL_REDUCE"]),
            "at_risk_units": sum((_number(summary.shortage_qty) or 0) for summary in summaries.values())}}


@router.get("/readiness")
def readiness(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    run = _latest_run(db, user)
    if not run:
        return {"run": None, "summary": {}, "products": []}
    rows = db.query(models.SCMProductReadiness).filter_by(planning_run_id=run.id).all()
    products = []
    for row in rows:
        product = db.get(__import__("app.platform.models", fromlist=["PlatformProduct"]).PlatformProduct, row.product_id)
        components = db.query(models.SCMComponentReadiness).filter_by(readiness_id=row.id).all()
        products.append({"id": row.id, "product": {"id": row.product_id, "code": product.code if product else row.product_id,
            "name": product.name if product else row.product_id}, "work_order_id": row.work_order_id,
            "required_date": row.required_date, "status": row.status, "total_components": row.total_components,
            "covered_components": row.covered_components, "at_risk_components": row.at_risk_components,
            "blocking_components": row.blocking_components,
            "components": [{"material_id": component.material_id, "required": _number(component.required_qty),
                "available": _number(component.projected_available_qty), "shortage": _number(component.shortage_qty),
                "status": component.status} for component in components]})
    return {"run": _run(run), "summary": {status: len([row for row in rows if row.status == status])
        for status in ("READY", "AT_RISK", "BLOCKED")}, "products": products}


@router.get("/actions")
def action_center(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    from app.platform.models import ActionApproval, ActionExecution, ActionIntent, ActionOutcome
    rows = db.query(ActionIntent).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).filter(
        ActionIntent.action_type.in_(["RESCHEDULE_PURCHASE_ORDER", "EXPEDITE_PURCHASE_ORDER",
            "CANCEL_PURCHASE_ORDER", "TRANSFER_INVENTORY", "CREATE_PURCHASE_ORDER",
            "procurement.po.reschedule", "scm.supply.expedite"])).order_by(ActionIntent.created_at.desc()).all()
    return [{"id": row.id, "action_type": row.action_type, "target_type": row.target_type,
        "target_id": row.target_id, "status": row.status, "reason": row.rationale,
        "payload": row.payload, "expected_impact": row.expected_impact, "policy_result": row.policy_result,
        "created_at": row.created_at, "approval": ({"decision": approval.decision, "decided_at": approval.decided_at}
            if (approval := db.query(ActionApproval).filter_by(action_intent_id=row.id).first()) else None),
        "execution": ({"status": execution.status, "external_reference": execution.external_reference}
            if (execution := db.query(ActionExecution).filter_by(action_intent_id=row.id).first()) else None),
        "outcome": ({"verification_status": outcome.verification_status} if
            (outcome := db.query(ActionOutcome).filter_by(action_intent_id=row.id).first()) else None)} for row in rows]


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    rows = db.query(models.SCMPlanningScenario).filter_by(tenant_id=user.tenant_id,
        plant_id=user.plant_id).order_by(models.SCMPlanningScenario.created_at.desc()).all()
    return [{"id": row.id, "name": row.name, "type": row.scenario_type, "status": row.status,
        "baseline_run_id": row.baseline_run_id, "result_run_id": row.result_run_id,
        "description": row.description, "overrides": [{"id": override.id, "type": override.override_type,
            "material_id": override.material_id, "values": override.values} for override in db.query(
            models.SCMScenarioOverride).filter_by(scenario_id=row.id).all()]} for row in rows]


@router.post("/scenarios/{scenario_id}/run", dependencies=[Depends(csrf_guard)])
def run_scenario(scenario_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    scenario = db.query(models.SCMPlanningScenario).filter_by(id=scenario_id, tenant_id=user.tenant_id,
        plant_id=user.plant_id).first()
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    run = service.create_run(db, user, scenario_id=scenario.id, trigger_type="SCENARIO",
                             correlation_id=f"scm-scenario:{scenario.id}")
    service.execute_run(db, run.id)
    scenario.result_run_id = run.id
    db.commit()
    return _run(run)


@router.post("/scenarios/{scenario_id}/duplicate", dependencies=[Depends(csrf_guard)])
def duplicate_scenario(scenario_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    source = db.query(models.SCMPlanningScenario).filter_by(id=scenario_id, tenant_id=user.tenant_id,
        plant_id=user.plant_id).first()
    if not source:
        raise HTTPException(404, "Scenario not found")
    row = models.SCMPlanningScenario(tenant_id=user.tenant_id, plant_id=user.plant_id,
        name=f"{source.name} copy", scenario_type="WHAT_IF", baseline_run_id=source.baseline_run_id,
        duplicated_from_id=source.id, description=source.description, created_by_user_id=user.id, status="ACTIVE")
    db.add(row)
    db.flush()
    for item in db.query(models.SCMScenarioOverride).filter_by(scenario_id=source.id).all():
        db.add(models.SCMScenarioOverride(tenant_id=user.tenant_id, plant_id=user.plant_id,
            scenario_id=row.id, material_id=item.material_id, override_type=item.override_type,
            source_entity_type=item.source_entity_type, source_entity_id=item.source_entity_id,
            values=item.values, reason=item.reason))
    db.commit()
    return {"id": row.id, "name": row.name}


@router.get("/scenarios/{scenario_id}/comparison")
def scenario_comparison(scenario_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    scenario = db.query(models.SCMPlanningScenario).filter_by(id=scenario_id, tenant_id=user.tenant_id,
        plant_id=user.plant_id).first()
    if not scenario or not scenario.result_run_id:
        raise HTTPException(404, "Completed scenario result not found")
    def metrics(run_id: str | None):
        if not run_id:
            return {}
        risks = db.query(models.SCMMaterialRiskSummary).filter_by(planning_run_id=run_id).all()
        readiness_rows = db.query(models.SCMProductReadiness).filter_by(planning_run_id=run_id).all()
        recs = db.query(models.SCMRecommendation).filter_by(planning_run_id=run_id).all()
        return {"critical_materials": len([r for r in risks if r.severity in {"CRITICAL", "RED"}]),
            "total_shortage_qty": sum(float(r.shortage_qty) for r in risks),
            "blocked_products": len([r for r in readiness_rows if r.status == "BLOCKED"]),
            "pull_ins": len([r for r in recs if r.action_type == "PULL_IN"]),
            "push_outs": len([r for r in recs if r.action_type == "PUSH_OUT"]),
            "cancellations": len([r for r in recs if r.action_type == "CANCEL_REDUCE"])}
    baseline, result = metrics(scenario.baseline_run_id), metrics(scenario.result_run_id)
    return {"scenario_id": scenario.id, "baseline_run_id": scenario.baseline_run_id,
        "result_run_id": scenario.result_run_id, "baseline": baseline, "scenario": result,
        "delta": {key: result.get(key, 0)-baseline.get(key, 0) for key in result}}


@router.get("/saved-views")
def saved_views(view_type: str | None = None, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    query = db.query(models.SCMSavedView).filter_by(tenant_id=user.tenant_id, user_id=user.id)
    if view_type:
        query = query.filter_by(view_type=view_type)
    return [{"id": row.id, "name": row.name, "view_type": row.view_type, "filters": row.filters,
             "columns": row.columns, "is_default": row.is_default} for row in query.all()]


@router.post("/saved-views", dependencies=[Depends(csrf_guard)])
def save_view(payload: SavedViewRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    if payload.is_default:
        db.query(models.SCMSavedView).filter_by(user_id=user.id, view_type=payload.view_type).update(
            {"is_default": False}, synchronize_session=False)
    row = models.SCMSavedView(tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id,
        name=payload.name, view_type=payload.view_type, filters=payload.filters,
        columns=payload.columns, is_default=payload.is_default)
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name}


@router.get("/notes/{entity_type}/{entity_id}")
def notes(entity_type: str, entity_id: str, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    rows = db.query(models.SCMPlannerNote).filter_by(tenant_id=user.tenant_id,
        entity_type=entity_type, entity_id=entity_id).order_by(models.SCMPlannerNote.created_at.desc()).all()
    return [{"id": row.id, "body": row.body, "author_user_id": row.author_user_id,
             "created_at": row.created_at} for row in rows]


@router.post("/notes/{entity_type}/{entity_id}", dependencies=[Depends(csrf_guard)])
def add_note(entity_type: str, entity_id: str, payload: NoteRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = models.SCMPlannerNote(tenant_id=user.tenant_id, plant_id=user.plant_id,
        entity_type=entity_type, entity_id=entity_id, body=payload.body, author_user_id=user.id)
    db.add(row)
    db.commit()
    return {"id": row.id, "body": row.body, "created_at": row.created_at}


@router.post("/risks/{risk_id}/status", dependencies=[Depends(csrf_guard)])
def update_risk_status(risk_id: str, payload: RiskUpdateRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    row = db.query(models.SCMMaterialRisk).filter_by(id=risk_id, tenant_id=user.tenant_id,
        plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Risk not found")
    row.status = payload.status
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email, "scm.risk.status_changed",
        "scm_material_risk", row.id, actor_user_id=user.id, meta={"status": payload.status, "reason": payload.reason})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/suppliers")
def supplier_center(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    suppliers = db.query(core_models.Supplier).filter_by(tenant_id=user.tenant_id).all()
    output = []
    for supplier in suppliers:
        orders = db.query(models.SCMSupplyOrder).filter_by(tenant_id=user.tenant_id,
            plant_id=user.plant_id, supplier_id=supplier.id).all()
        schedules = db.query(models.SCMSupplyScheduleLine).filter(
            models.SCMSupplyScheduleLine.supply_order_id.in_([row.id for row in orders] or ["-"])).all()
        output.append({"id": supplier.id, "code": supplier.code or supplier.erp_vendor_id,
            "name": supplier.name, "materials_supplied": db.query(models.SCMMaterialSupplier).filter_by(
                supplier_id=supplier.id, plant_id=user.plant_id).count(), "open_pos": len(orders),
            "confirmed": len([r for r in schedules if r.status == "CONFIRMED"]),
            "unconfirmed": len([r for r in schedules if not r.supplier_commit_date]),
            "delayed": len([r for r in schedules if r.current_due_date > r.original_due_date]),
            "delivery_score": supplier.delivery_score})
    return output


@router.get("/exports/materials.csv")
def export_materials(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    rows = materials_list(limit=500, db=db, user=user)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["material_id", "code", "description", "type", "severity", "stockout_date"])
    for row in rows:
        writer.writerow([row["id"], row["code"], row["description"], row["type"], row["severity"], row["stockout_date"]])
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=scm-materials.csv"})


@router.get("/mapping-profiles")
def mapping_profiles(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    connection = imports.ensure_file_connection(db, user)
    rows = db.query(core_models.IntegrationMappingProfile).filter_by(
        tenant_id=user.tenant_id, connection_id=connection.id).order_by(
        core_models.IntegrationMappingProfile.name, core_models.IntegrationMappingProfile.profile_version.desc()).all()
    return [{"id": row.id, "name": row.name, "version": row.profile_version,
             "mappings": row.mappings, "transforms": row.transforms, "status": row.status} for row in rows]


@router.post("/mapping-profiles", dependencies=[Depends(csrf_guard)])
def save_mapping_profile(payload: MappingProfileRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    connection = imports.ensure_file_connection(db, user)
    version = db.query(func.max(core_models.IntegrationMappingProfile.profile_version)).filter_by(
        connection_id=connection.id, name=payload.name).scalar() or 0
    row = core_models.IntegrationMappingProfile(tenant_id=user.tenant_id, plant_id=user.plant_id,
        connection_id=connection.id, name=payload.name, profile_version=version + 1,
        workbook_schema_version="scm-v1", mappings=payload.mappings, transforms=payload.transforms,
        ownership={"module": "scm"}, status="active")
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "version": row.profile_version}


@router.post("/overrides", dependencies=[Depends(csrf_guard)])
def create_operational_override(payload: OperationalOverrideRequest, db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    material = db.query(models.SCMMaterialPlant).filter_by(material_id=payload.material_id,
        plant_id=user.plant_id).first()
    if not material:
        raise HTTPException(404, "Material not found in selected plant")
    row = models.SCMPlanningAdjustment(tenant_id=user.tenant_id, plant_id=user.plant_id,
        material_id=payload.material_id, adjustment_type=payload.adjustment_type,
        values={**payload.values, "source": "MANUAL_OVERRIDE"}, reason=payload.reason,
        created_by_user_id=user.id, expires_at=payload.expires_at, approval_state="APPROVED")
    db.add(row)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email, "scm.override.created",
        "scm_planning_adjustment", row.id, actor_user_id=user.id,
        meta={"material_id": payload.material_id, "type": payload.adjustment_type, "reason": payload.reason})
    db.commit()
    return {"id": row.id, "status": row.approval_state, "source": "MANUAL_OVERRIDE"}


@router.get("/data-entry/options")
def data_entry_options(db: Session = Depends(get_db), user: core_models.User = Depends(scm_admin)):
    materials = db.query(models.SCMMaterial).join(models.SCMMaterialPlant).filter(
        models.SCMMaterial.tenant_id == user.tenant_id,
        models.SCMMaterialPlant.plant_id == user.plant_id,
        models.SCMMaterialPlant.active.is_(True),
    ).order_by(models.SCMMaterial.material_code).all()
    suppliers = db.query(core_models.Supplier).filter_by(
        tenant_id=user.tenant_id).order_by(core_models.Supplier.name).all()
    schedules = db.query(models.SCMSupplyScheduleLine, models.SCMSupplyOrder).join(
        models.SCMSupplyOrder, models.SCMSupplyOrder.id == models.SCMSupplyScheduleLine.supply_order_id
    ).filter(models.SCMSupplyScheduleLine.tenant_id == user.tenant_id,
             models.SCMSupplyScheduleLine.plant_id == user.plant_id,
             models.SCMSupplyScheduleLine.status.notin_(["CANCELLED", "CLOSED"])).order_by(
                 models.SCMSupplyScheduleLine.current_due_date).limit(500).all()
    demands = db.query(models.SCMMaterialRequirement).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id).order_by(
            models.SCMMaterialRequirement.required_date).limit(500).all()
    return {
        "entry_types": sorted(manual_entries.ENTRY_TYPES),
        "materials": [{"id": row.id, "code": row.material_code, "description": row.description,
                       "uom": row.base_uom_id} for row in materials],
        "suppliers": [{"id": row.id, "code": row.code or row.erp_vendor_id,
                       "name": row.name} for row in suppliers],
        "schedules": [{"id": line.id, "order_id": order.id, "order_number": order.order_number,
                       "material_id": order.material_id, "supplier_id": order.supplier_id,
                       "due_date": line.current_due_date, "quantity": _number(line.scheduled_qty),
                       "status": line.status} for line, order in schedules],
        "demands": [{"id": row.id, "material_id": row.material_id,
                     "reference": row.external_id, "required_date": row.required_date,
                     "quantity": _number(row.quantity), "demand_type": row.requirement_type}
                    for row in demands],
    }


@router.post("/data-entries", status_code=202, dependencies=[Depends(csrf_guard)])
def create_data_entry(payload: ManualDataEntryRequest,
                      idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=160),
                      db: Session = Depends(get_db), user: core_models.User = Depends(scm_editor)):
    entry, run, replayed = manual_entries.create(db, user, **payload.model_dump(),
                                                  idempotency_key=idempotency_key)
    db.commit()
    if run and not replayed:
        from app.workers import run_scm_planning
        run_scm_planning.apply_async(args=[run.id], queue="scm")
    return {"entry": manual_entries.serialize(entry, db), "planning_run": _run(run) if run else None,
            "replayed": replayed}


@router.get("/data-entries")
def list_data_entries(status: str | None = None, material_id: str | None = None,
                      limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db),
                      user: core_models.User = Depends(scm_admin)):
    query = db.query(models.SCMManualDataEntry).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id)
    if status:
        query = query.filter(models.SCMManualDataEntry.status == status.upper())
    if material_id:
        query = query.filter(models.SCMManualDataEntry.material_id == material_id)
    return [manual_entries.serialize(row, db) for row in query.order_by(
        models.SCMManualDataEntry.created_at.desc()).limit(limit).all()]


@router.get("/data-entries/{entry_id}")
def get_data_entry(entry_id: str, db: Session = Depends(get_db),
                   user: core_models.User = Depends(scm_admin)):
    row = db.query(models.SCMManualDataEntry).filter_by(
        id=entry_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Manual data entry not found")
    return manual_entries.serialize(row, db)


@router.post("/data-entries/{entry_id}/void", status_code=202, dependencies=[Depends(csrf_guard)])
def void_data_entry(entry_id: str, payload: VoidEntryRequest, db: Session = Depends(get_db),
                    user: core_models.User = Depends(scm_editor)):
    row = db.query(models.SCMManualDataEntry).filter_by(
        id=entry_id, tenant_id=user.tenant_id, plant_id=user.plant_id).first()
    if not row:
        raise HTTPException(404, "Manual data entry not found")
    if row.status != "ACTIVE":
        raise HTTPException(409, "Only an active manual data entry can be voided")
    row.status = "VOIDED"
    now = datetime.now(timezone.utc)
    membership = db.query(core_models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active").first()
    publish(db, DomainEvent("scm.manual_data.voided", user.tenant_id, user.plant_id,
        "scm_manual_data_entry", row.id, {"entry_id": row.id, "material_id": row.material_id,
        "reason": payload.reason}, actor_membership_id=membership.id if membership else None,
        correlation_id=row.correlation_id, source_system="genuinegigs_manual", occurred_at=now))
    run = service.create_run(db, user, trigger_key=f"void:{row.id}:{now.isoformat()}",
                             trigger_type="MANUAL_CHANGE", correlation_id=row.correlation_id)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email, "scm.manual_data.voided",
        "scm_manual_data_entry", row.id, actor_user_id=user.id,
        meta={"reason": payload.reason, "planning_run_id": run.id})
    db.commit()
    from app.workers import run_scm_planning
    run_scm_planning.apply_async(args=[run.id], queue="scm")
    return {"entry": manual_entries.serialize(row, db), "planning_run": _run(run)}


@router.get("/data-conflicts")
def list_data_conflicts(status: str = "open", db: Session = Depends(get_db),
                        user: core_models.User = Depends(scm_admin)):
    rows = db.query(DataQualityIssue).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        rule_key="scm_manual_source_conflict", status=status).order_by(
            DataQualityIssue.created_at.desc()).all()
    return [{"id": row.id, "entry_id": row.entity_id, "severity": row.severity,
             "status": row.status, "message": row.message, "details": row.details,
             "created_at": row.created_at} for row in rows]


@router.post("/data-conflicts/{issue_id}/resolve", status_code=202, dependencies=[Depends(csrf_guard)])
def resolve_data_conflict(issue_id: str, payload: ConflictResolutionRequest,
                          db: Session = Depends(get_db), user: core_models.User = Depends(scm_editor)):
    issue = db.query(DataQualityIssue).filter_by(id=issue_id, tenant_id=user.tenant_id,
        plant_id=user.plant_id, rule_key="scm_manual_source_conflict", status="open").first()
    if not issue:
        raise HTTPException(404, "Open SCM data conflict not found")
    entry = db.get(models.SCMManualDataEntry, issue.entity_id)
    if not entry or entry.tenant_id != user.tenant_id:
        raise HTTPException(409, "The conflicting manual entry no longer exists")
    if payload.decision == "ACCEPT_IMPORTED" and entry.status == "ACTIVE":
        entry.status = "RECONCILED"
    issue.status = "resolved"
    issue.details = {**(issue.details or {}), "resolution": {"decision": payload.decision,
        "reason": payload.reason, "resolved_by": user.id,
        "resolved_at": datetime.now(timezone.utc).isoformat()}}
    run = service.create_run(db, user, trigger_key=f"conflict:{issue.id}:{payload.decision}",
        trigger_type="MANUAL_CHANGE", correlation_id=entry.correlation_id)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.email,
        "scm.manual_data.conflict_resolved", "data_quality_issue", issue.id, actor_user_id=user.id,
        meta={"decision": payload.decision, "reason": payload.reason, "entry_id": entry.id})
    db.commit()
    from app.workers import run_scm_planning
    run_scm_planning.apply_async(args=[run.id], queue="scm")
    return {"issue_id": issue.id, "decision": payload.decision,
            "entry": manual_entries.serialize(entry, db), "planning_run": _run(run)}
