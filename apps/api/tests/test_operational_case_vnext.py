from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, Company, Department, Plant, Tenant, User
from app.platform.models import OperationalCase
from app.platform.case_models import (
    CaseEvidence, ConstraintResult, DecisionAlternative, DecisionRecord,
    FeasibilityEvaluation, RecoveryObservation, RecoveryTarget,
)
from app.platform.case_service import aggregate_case, select_alternative, verify_recovery
from app.scm.material_recovery import create_mat182_case, evaluate_strategy


def scoped(**extra):
    return {"tenant_id": "tenant-a", "plant_id": "plant-a", **extra}


def test_case_replay_is_idempotent_and_evidence_is_retained(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'case.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = aggregate_case(db, **scoped(aggregation_key="MAT-182:2026-09", title="MAT-182 shortage",
            case_type="SCM_MATERIAL_RISK", source_event_id="event-1", evidence={"entity_id": "risk-1"}))
        replay = aggregate_case(db, **scoped(aggregation_key="MAT-182:2026-09", title="MAT-182 shortage",
            case_type="SCM_MATERIAL_RISK", source_event_id="event-1", evidence={"entity_id": "risk-1"}))
        changed = aggregate_case(db, **scoped(aggregation_key="MAT-182:2026-09", title="MAT-182 shortage",
            case_type="SCM_MATERIAL_RISK", source_event_id="event-2", evidence={"entity_id": "risk-1"}))
        assert first.id == replay.id == changed.id
        assert db.query(OperationalCase).count() == 1
        assert db.query(CaseEvidence).count() == 2


def test_decision_blocks_violation_and_requires_override(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'decision.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        case = OperationalCase(**scoped(case_type="SCM_MATERIAL_RISK", title="MAT-182", status="open")); db.add(case); db.flush()
        blocked = FeasibilityEvaluation(**scoped(case_id=case.id, strategy_type="TRANSFER", status="UNAVAILABLE")); db.add(blocked); db.flush()
        db.add(ConstraintResult(**scoped(feasibility_evaluation_id=blocked.id, constraint_key="plant_b_future_demand", state="VIOLATED", blocking=True, explanation="Plant B needs stock")))
        record = DecisionRecord(**scoped(case_id=case.id, decision="PENDING")); db.add(record); db.flush()
        alt = DecisionAlternative(**scoped(decision_record_id=record.id, strategy_type="TRANSFER", feasibility_evaluation_id=blocked.id, ranking=1)); db.add(alt); db.flush()
        record.recommended_alternative_id = alt.id
        with pytest.raises(ValueError, match="blocking"):
            select_alternative(db, record=record, alternative_id=alt.id, actor_id="manager", reason="Protect Honda")


def test_recovery_needs_two_fresh_successful_cycles(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        case = OperationalCase(**scoped(case_type="SCM_MATERIAL_RISK", title="MAT-182", status="monitoring")); db.add(case); db.flush()
        target = RecoveryTarget(**scoped(case_id=case.id, target_type="STABILITY", metric="coverage",
            operator=">=", threshold=1, target=1, required_observation_count=2, freshness_requirement="FRESH")); db.add(target); db.flush()
        db.add(RecoveryObservation(**scoped(target_id=target.id, source_entity={"planning_run": "run-1"},
            observed_value=1.2, observed_at=now, freshness="FRESH", satisfied=True)))
        assert verify_recovery(db, case).status == "MONITORING"
        db.add(RecoveryObservation(**scoped(target_id=target.id, source_entity={"planning_run": "run-2"},
            observed_value=1.1, observed_at=now + timedelta(hours=1), freshness="STALE", satisfied=True)))
        assert verify_recovery(db, case).status == "MONITORING"
        db.add(RecoveryObservation(**scoped(target_id=target.id, source_entity={"planning_run": "run-3"},
            observed_value=1.1, observed_at=now + timedelta(hours=2), freshness="FRESH", satisfied=True)))
        assert verify_recovery(db, case).status == "RECOVERED"
        assert case.status == "closed"


def test_mat182_slice_builds_one_case_and_safe_ranked_options(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mat182.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Tenant(id="tenant-a", name="A"),
            Company(id="company-a", tenant_id="tenant-a", name="A", erp_code="A"),
            Plant(id="plant-a", tenant_id="tenant-a", company_id="company-a", name="Plant A", erp_location_code="A"),
            Department(id="dept-a", tenant_id="tenant-a", plant_id="plant-a", name="SCM")])
        user = User(id="user-a", tenant_id="tenant-a", plant_id="plant-a", department_id="dept-a",
            name="Planner", email="planner@example.com", role="admin", password_hash="x")
        db.add(user); db.flush()
        case = create_mat182_case(db, user)
        replay = create_mat182_case(db, user)
        assert replay.id == case.id
        assert db.query(OperationalCase).count() == 1
        record = db.query(DecisionRecord).filter_by(case_id=case.id).one()
        options = db.query(DecisionAlternative).filter_by(decision_record_id=record.id).all()
        assert [row.strategy_type for row in sorted(options, key=lambda row: row.ranking)] == [
            "INTERPLANT_TRANSFER", "SUPPLIER_PULL_IN", "PRODUCTION_RESEQUENCE"]
        selected = select_alternative(db, record=record, alternative_id=record.recommended_alternative_id,
            actor_id=None, reason="Protect Honda H421")
        assert selected.strategy_type == "INTERPLANT_TRANSFER"
        assert case.current_strategy_id == selected.id


def test_transfer_rejects_plant_b_harm_and_stale_stock_requires_confirmation():
    unsafe = evaluate_strategy(strategy="INTERPLANT_TRANSFER", shortage_qty=440,
        origin_available=600, origin_future_demand=300, transfer_qty=440)
    assert unsafe["status"] == "UNAVAILABLE"
    stale = evaluate_strategy(strategy="INTERPLANT_TRANSFER", shortage_qty=440,
        stale_inventory=True, origin_available=950, origin_future_demand=300, transfer_qty=440)
    assert stale["status"] == "REQUIRES_CONFIRMATION"
