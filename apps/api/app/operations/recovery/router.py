"""Scoped operational-recovery HTTP contract."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import current_user, require_csrf
from app.db import models
from app.db.session import get_db
from app.operations.recovery import service
from app.operations.recovery.effectiveness import find_similar_recovery_cases, get_effectiveness

router = APIRouter(prefix="/api/v2", tags=["operational-recovery"])
FINANCIAL_ROLES = {"admin", "plant_manager", "purchase_manager", "corporate_operations_director"}


class SelectRequest(BaseModel):
    strategy_id: str
    reason: str | None = Field(default=None, max_length=1000)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class InvestigationRequest(BaseModel):
    title: str = Field(min_length=3,max_length=240)
    problem_signature: dict
    recovery_case_ids: list[str]
    estimated_annual_loss: float = Field(default=0,ge=0)
    hypothesis: str | None = Field(default=None,max_length=2000)


def user(request: Request, db: Session = Depends(get_db)): return current_user(db, request)
def csrf(request: Request, db: Session = Depends(get_db)): require_csrf(db, request)


def _scope(db: Session, actor: models.User):
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=actor.tenant_id, user_id=actor.id, status="active").first()
    return (db.query(models.OperationalScope).filter_by(
        tenant_id=actor.tenant_id, membership_id=membership.id).first() if membership else None)


def _case(db: Session, actor: models.User, case_id: str) -> models.RecoveryCase:
    row = db.query(models.RecoveryCase).filter_by(id=case_id, tenant_id=actor.tenant_id).first()
    if not row: raise HTTPException(404, "Recovery case not found")
    scope = _scope(db, actor)
    allowed_plants = set(scope.plant_ids or []) if scope else {actor.plant_id}
    if row.plant_id not in allowed_plants: raise HTTPException(403, "Plant access denied")
    deviation = db.get(models.OperationalDeviation, row.deviation_id)
    if scope and scope.line_ids and deviation.line_id and deviation.line_id not in scope.line_ids:
        raise HTTPException(403, "Production line access denied")
    if scope and scope.asset_ids and deviation.asset_id and deviation.asset_id not in scope.asset_ids:
        raise HTTPException(403, "Asset access denied")
    return row


def _redact(payload, actor):
    if actor.role in FINANCIAL_ROLES: return payload
    sensitive = {"business_exposure_amount","expected_value_recovered","direct_cost","estimated_value_recovered",
                 "verified_value_recovered","median_net_value","expected_net_value"}
    if isinstance(payload, list): return [_redact(item, actor) for item in payload]
    if isinstance(payload, dict): return {key:(None if key in sensitive else _redact(value, actor)) for key,value in payload.items()}
    return payload


@router.get("/recovery-cases")
def list_cases(db: Session = Depends(get_db), actor: models.User = Depends(user)):
    scope = _scope(db, actor); plants = set(scope.plant_ids or []) if scope else {actor.plant_id}
    query = db.query(models.RecoveryCase).filter(models.RecoveryCase.tenant_id == actor.tenant_id,
                                                 models.RecoveryCase.plant_id.in_(plants))
    rows=[]
    for row in query.order_by(models.RecoveryCase.opened_at.desc()).all():
        deviation=db.get(models.OperationalDeviation,row.deviation_id)
        if scope and scope.line_ids and deviation.line_id and deviation.line_id not in scope.line_ids: continue
        if scope and scope.asset_ids and deviation.asset_id and deviation.asset_id not in scope.asset_ids: continue
        rows.append(service.serialize_case(db,row,False))
    return _redact(rows,actor)


@router.get("/deviations/{deviation_id}/recovery")
def recovery_for_deviation(deviation_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    row=db.query(models.RecoveryCase).filter_by(tenant_id=actor.tenant_id,deviation_id=deviation_id).first()
    if not row: return None
    return _redact(service.serialize_case(db,_case(db,actor,row.id)),actor)


@router.get("/recovery-cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    return _redact(service.serialize_case(db,_case(db,actor,case_id)),actor)


@router.get("/recovery-cases/{case_id}/strategies")
def strategies(case_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id)
    rows=db.query(models.RecoveryStrategy).filter_by(recovery_case_id=case.id).order_by(models.RecoveryStrategy.ranking_position).all()
    return _redact([service.serialize_strategy(row) for row in rows],actor)


@router.post("/recovery-cases/{case_id}/refresh-options", dependencies=[Depends(csrf)])
def refresh(case_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id); rows=service.refresh_options(db,case); db.commit()
    return _redact([service.serialize_strategy(row) for row in rows],actor)


@router.post("/recovery-cases/{case_id}/select-strategy", dependencies=[Depends(csrf)])
def select(case_id: str, payload: SelectRequest, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id); strategy=db.query(models.RecoveryStrategy).filter_by(id=payload.strategy_id,tenant_id=actor.tenant_id).first()
    if not strategy: raise HTTPException(404,"Recovery strategy not found")
    scope=_scope(db,actor); authorities=set(scope.authorities or []) if scope else set()
    # Leadership and domain ownership remain safe rollout defaults for existing workspaces.
    if actor.role in {"admin","plant_manager"}: authorities |= set(strategy.required_authorities or [])
    try: actions=service.select_strategy(db,case,strategy,actor.id,payload.reason,authorities)
    except service.RecoveryInputsStale as exc:
        db.commit()
        raise HTTPException(409,str(exc)) from exc
    except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    db.commit()
    tenant=db.get(models.Tenant,actor.tenant_id)
    if tenant and tenant.workspace_kind=="simulation":
        from app.workers import apply_simulated_recovery_strategy
        apply_simulated_recovery_strategy.apply_async(args=[strategy.strategy_type],queue="sync")
    return {"case":_redact(service.serialize_case(db,case),actor),"actions_created":len(actions)}


@router.post("/recovery-cases/{case_id}/start", dependencies=[Depends(csrf)])
def start(case_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id)
    try: service.start(db,case)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    db.commit(); return _redact(service.serialize_case(db,case),actor)


@router.post("/recovery-cases/{case_id}/verify", dependencies=[Depends(csrf)])
def verify(case_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id)
    try: case,outcome,result=service.verify(db,case,actor.id)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    db.commit(); return _redact({"case":service.serialize_case(db,case),"outcome_id":outcome.id if outcome else None,"result":result.result,"evidence":result.evidence},actor)


@router.post("/recovery-cases/{case_id}/abandon", dependencies=[Depends(csrf)])
def abandon(case_id: str, payload: ReasonRequest, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id)
    try: service.abandon(db,case,payload.reason)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    db.commit(); return _redact(service.serialize_case(db,case),actor)


@router.get("/recovery-strategies/{strategy_id}")
def strategy(strategy_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    row=db.query(models.RecoveryStrategy).filter_by(id=strategy_id,tenant_id=actor.tenant_id).first()
    if not row: raise HTTPException(404,"Recovery strategy not found")
    _case(db,actor,row.recovery_case_id); return _redact(service.serialize_strategy(row),actor)


@router.get("/recovery-strategies/{strategy_id}/historical-evidence")
def historical(strategy_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    row=db.query(models.RecoveryStrategy).filter_by(id=strategy_id,tenant_id=actor.tenant_id).first()
    if not row: raise HTTPException(404,"Recovery strategy not found")
    case=_case(db,actor,row.recovery_case_id); deviation=db.get(models.OperationalDeviation,case.deviation_id)
    from app.operations.recovery.effectiveness import fingerprint
    snapshot=db.get(models.OperationalStateSnapshot,case.baseline_snapshot_id)
    matches=find_similar_recovery_cases(db,actor.tenant_id,case.plant_id,fingerprint(db,deviation,snapshot,row.strategy_type),row.strategy_type)
    return {"effectiveness":_redact(get_effectiveness(db,actor.tenant_id,case.plant_id,row.strategy_type),actor),
            "cases":[{"id":item.recovery_case_id,"rating":item.outcome_rating,"recovered_units":item.actual_recovered_units,
                      "recovery_time_seconds":item.time_to_recovery_seconds} for item in matches]}


@router.get("/recovery-cases/{case_id}/outcome")
def outcome(case_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id); row=db.query(models.RecoveryOutcome).filter_by(recovery_case_id=case.id).first()
    if not row: return None
    return _redact({key:getattr(row,key) for key in ("id","strategy_id","started_at","completed_at","actual_recovered_units",
        "verified_value_recovered","time_to_first_response_seconds","time_to_recovery_seconds","target_achieved","partial_recovery",
        "quality_side_effect","safety_side_effect","delivery_side_effect","recurred_within_7d","recurred_within_30d","outcome_rating",
        "verification_method","verified_at","context_fingerprint","metrics_before","metrics_after")},actor)


@router.get("/recovery-cases/{case_id}/value")
def value(case_id: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    case=_case(db,actor,case_id); rows=db.query(models.OperationalValueEntry).filter_by(deviation_id=case.deviation_id).all()
    return _redact([{"type":row.value_type,"amount":row.amount,"currency":row.currency,"confidence":row.confidence_state,
                     "method":row.calculation_method,"captured_at":row.captured_at} for row in rows],actor)


@router.get("/recovery-effectiveness")
def effectiveness(db: Session = Depends(get_db), actor: models.User = Depends(user)):
    types=[row[0] for row in db.query(models.RecoveryStrategy.strategy_type).filter_by(tenant_id=actor.tenant_id).distinct().all()]
    return _redact([get_effectiveness(db,actor.tenant_id,actor.plant_id,item) for item in types],actor)


@router.get("/recovery-effectiveness/{strategy_type}")
def effectiveness_type(strategy_type: str, db: Session = Depends(get_db), actor: models.User = Depends(user)):
    return _redact(get_effectiveness(db,actor.tenant_id,actor.plant_id,strategy_type),actor)


@router.post("/improvement/investigations",dependencies=[Depends(csrf)],status_code=201)
def create_investigation(payload: InvestigationRequest,db: Session=Depends(get_db),actor: models.User=Depends(user)):
    if actor.role not in {"admin","plant_manager","production_manager","maintenance_manager","quality_manager"}:
        raise HTTPException(403,"Improvement authority required")
    cases=[]
    for case_id in payload.recovery_case_ids:
        cases.append(_case(db,actor,case_id))
    row=models.ImprovementInvestigation(tenant_id=actor.tenant_id,plant_id=actor.plant_id,title=payload.title,
        problem_signature=payload.problem_signature,related_recovery_case_ids=[item.id for item in cases],
        estimated_annual_loss=payload.estimated_annual_loss,status="open",owner_user_id=actor.id,
        hypothesis=payload.hypothesis)
    db.add(row);db.flush()
    db.add(models.EventOutbox(tenant_id=actor.tenant_id,plant_id=actor.plant_id,
        event_type="improvement.investigation.suggested",aggregate_type="improvement_investigation",
        aggregate_id=row.id,aggregate_version=1,correlation_id=f"improvement:{row.id}",
        payload={"investigation_id":row.id,"recovery_case_ids":row.related_recovery_case_ids}))
    db.commit();return {"id":row.id,"title":row.title,"status":row.status}
