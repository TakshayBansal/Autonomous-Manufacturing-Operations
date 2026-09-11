from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.operations.state import build_operational_state_snapshot, derive_line_state
from app.operations.recovery import service
from app.operations.recovery.effectiveness import get_effectiveness
from app.operations.recovery.playbooks.base import Candidate
from app.operations.recovery.ranking import score


def seeded():
    db: Session = SessionLocal(); reset_workspace_database(db); db.commit(); return db


def test_state_dimensions_do_not_collapse_material_risk_into_physical_block():
    db=seeded()
    try:
        order=db.query(models.ProductionWorkOrder).filter_by(status="in_progress").first()
        line=db.get(models.ProductionLine,order.line_id)
        state=derive_line_state(db,line,order,datetime(2026,8,12,10,tzinfo=timezone.utc))
        assert state["execution_state"] in {"RUNNING","DOWN"}
        assert state["performance_state"] in {"AHEAD","ON_PLAN","WATCH","BEHIND","RECOVERING"}
        assert state["material_readiness_state"] in {"READY","WATCH","AT_RISK","BLOCKED","UNKNOWN"}
        assert "blocked" not in state
    finally: db.close()


def test_strategy_ranking_is_deterministic_explainable_and_safety_vetoed():
    safe=Candidate("repair","Repair", "", .8, 1800, 1000,.05,.05,.1,.1,.8)
    unsafe=Candidate("bypass","Bypass", "", .95, 300, 0,.2,.9,.2,.1,.9)
    safe_score,components=score(safe,50000,{"sufficient_history":False})
    unsafe_score,unsafe_components=score(unsafe,50000,{"sufficient_history":False})
    assert safe_score>0 and components["expected_net_value"]>0
    assert unsafe_score==-1 and "veto" in unsafe_components


def test_deviation_has_recovery_case_multiple_ranked_options_and_one_gigi_activity():
    db=seeded()
    try:
        deviation=db.query(models.OperationalDeviation).filter_by(detector_key="downtime_exceeded_threshold").one()
        case=db.query(models.RecoveryCase).filter_by(deviation_id=deviation.id).one()
        strategies=db.query(models.RecoveryStrategy).filter_by(recovery_case_id=case.id).all()
        assert case.status=="options_ready" and len(strategies)>=2
        assert sum(row.status=="recommended" for row in strategies)==1
        activities=db.query(models.EventOutbox).filter_by(
            aggregate_id=deviation.id,event_type="gigi.activity.created").count()
        assert activities==1
    finally: db.close()


def test_strategy_selection_creates_sequenced_current_actions_and_override_memory():
    db=seeded()
    try:
        case=db.query(models.RecoveryCase).filter_by(status="options_ready").first()
        alternative=db.query(models.RecoveryStrategy).filter(
            models.RecoveryStrategy.recovery_case_id==case.id,
            models.RecoveryStrategy.id!=case.recommended_strategy_id,
            models.RecoveryStrategy.unavailable_reason.is_(None)).first()
        actions=service.select_strategy(db,case,alternative,"usr-plant-001","Alternate line is already staffed",
                                        set(alternative.required_authorities or []))
        db.commit()
        assert len(actions)>=1 and case.override_reason
        assert db.query(models.RecoveryStrategyAction).filter_by(strategy_id=alternative.id).count()==len(actions)
        if len(actions)>1:
            assert db.query(models.OperationalActionDependency).filter_by(action_id=actions[1].id).count()==1
    finally: db.close()


def test_effectiveness_never_crosses_tenant_boundary():
    db=seeded()
    try:
        result=get_effectiveness(db,"missing-tenant","plant-pune-01","repair_asset")
        assert result["sample_size"]==0 and result["success_rate"] is None and not result["sufficient_history"]
    finally: db.close()
