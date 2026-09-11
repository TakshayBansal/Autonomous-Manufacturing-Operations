from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, User
from app.intelligence.services import refresh_case_insights
from app.intelligence.runtime import GigiRuntime
from app.intelligence.schemas import PageContext
from app.platform.models import OperationalCase
from app.platform.case_models import GigiInsight
from app.scm.material_recovery import evaluate_strategy
from app.platform.case_models import RecoveryObservation, RecoveryTarget, ValueAttribution, BusinessExposure
from app.platform.case_service import verify_recovery
from app.scm import models as scm_models
from app.scm.risks import _record_recovery_observations


def test_insights_are_member_scoped_and_preserve_delivery_choices(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'insights.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(id="u", tenant_id="t", plant_id="p", department_id="d",
                    name="Planner", email="planner@example.test", role="admin", password_hash="unused")
        case = OperationalCase(tenant_id="t", plant_id="p", case_type="SCM_MATERIAL_RISK",
            title="Supplier delay", severity="critical", status="active",
            decision_deadline=datetime.now(timezone.utc) + timedelta(hours=1))
        db.add_all([user, case]); db.flush()
        first = refresh_case_insights(db, user=user, membership_id="member-a")[0]
        second = refresh_case_insights(db, user=user, membership_id="member-b")[0]
        db.flush()
        assert first.id != second.id
        first.acknowledged_at = datetime.now(timezone.utc)
        first.delivery_state = "ACKNOWLEDGED"
        second.snoozed_until = datetime.now(timezone.utc) + timedelta(hours=2)
        second.delivery_state = "SNOOZED"
        db.commit()
        assert refresh_case_insights(db, user=user, membership_id="member-a")[0].delivery_state == "ACKNOWLEDGED"
        assert refresh_case_insights(db, user=user, membership_id="member-b")[0].delivery_state == "SNOOZED"
        second.snoozed_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert refresh_case_insights(db, user=user, membership_id="member-b")[0].delivery_state == "POPUP"
        case.status = "closed"
        refresh_case_insights(db, user=user, membership_id="member-b")
        assert second.delivery_state == "RESOLVED"
        assert db.query(GigiInsight).count() == 2


def test_unknown_transfer_inventory_is_not_a_claimed_violation():
    result = evaluate_strategy(strategy="INTERPLANT_TRANSFER", shortage_qty=10, transfer_qty=10)
    assert result["status"] == "REQUIRES_CONFIRMATION"
    assert any(row[0] == "plant_b_future_demand" and row[1] == "UNKNOWN" for row in result["constraints"])


def test_customer_commitment_question_resolves_shared_case(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'resolution.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(id="u", tenant_id="t", plant_id="p", department_id="d", name="Planner",
                    email="planner@example.test", role="admin", password_hash="unused")
        case = OperationalCase(tenant_id="t", plant_id="p", case_type="SCM_MATERIAL_RISK",
            title="MAT-182 shortage threatens Honda H421", aggregation_key="MAT-182:p:H421:WO-981",
            severity="critical", status="active")
        db.add_all([user, case]); db.flush()
        page = GigiRuntime(db)._resolve_question_entity(user, "Why is Honda H421 at risk?", PageContext(module="home"))
        assert page.entity_type == "operational_case"
        assert page.entity_id == case.id


def test_unsupported_strategy_cannot_silently_become_resequencing():
    with pytest.raises(ValueError, match="Unsupported"):
        evaluate_strategy(strategy="invented", shortage_qty=10)


def test_recovery_uses_distinct_cycles_and_rechecks_numeric_target(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'verification.db'}")
    Base.metadata.create_all(engine)
    scope = {"tenant_id": "t", "plant_id": "p"}
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        case = OperationalCase(**scope, case_type="SCM_MATERIAL_RISK", title="Shortage", status="monitoring")
        db.add(case); db.flush()
        target = RecoveryTarget(**scope, case_id=case.id, target_type="STABILITY", metric="coverage",
            operator=">=", threshold=1, target=1, required_observation_count=2, freshness_requirement="FRESH")
        db.add(target); db.flush()
        db.add(BusinessExposure(**scope, case_id=case.id, metric="production_units_at_risk", projected=440,
            unit="EA", methodology="Baseline projection", computed_at=now))
        for seconds in (0, 1):
            db.add(RecoveryObservation(**scope, target_id=target.id, source_entity={"planning_run": "same-cycle"},
                observed_value=1.2, observed_at=now + timedelta(seconds=seconds), freshness="FRESH", satisfied=True))
        assert verify_recovery(db, case).status == "MONITORING"
        db.add(RecoveryObservation(**scope, target_id=target.id, source_entity={"planning_run": "second-cycle"},
            observed_value=1.1, observed_at=now + timedelta(seconds=2), freshness="FRESH", satisfied=True))
        assert verify_recovery(db, case).status == "RECOVERED"
        assert db.query(ValueAttribution).count() == 0
        db.add(RecoveryObservation(**scope, target_id=target.id, source_entity={"planning_run": "unsafe-cycle"},
            observed_value=.5, observed_at=now + timedelta(seconds=3), freshness="FRESH", satisfied=True))
        assert verify_recovery(db, case).status == "NOT_RECOVERED"
        assert case.status != "closed"


def test_scm_replan_records_one_conservative_recovery_observation(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'planning-recovery.db'}")
    Base.metadata.create_all(engine)
    scope = {"tenant_id": "t", "plant_id": "p"}
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        case = OperationalCase(**scope, case_type="material_shortage", title="MAT-182 shortage",
            status="monitoring", recovery_state="MONITORING", canonical_entity_type="material",
            canonical_entity_id="material-182")
        db.add(case); db.flush()
        target = RecoveryTarget(**scope, case_id=case.id, target_type="STABILITY",
            metric="confirmed_coverage_ratio", operator=">=", threshold=1, target=1,
            required_observation_count=2, freshness_requirement="FRESH")
        run = scm_models.SCMPlanningRun(**scope, scenario_id="scenario", policy_id="policy",
            as_of_at=now, horizon_start=date.today(), horizon_end=date.today() + timedelta(days=30),
            engine_version="test", policy_version=1, status="COMPLETED", completed_at=now)
        db.add_all([target, run]); db.flush()
        db.add(scm_models.SCMMaterialProjectionPoint(**scope, planning_run_id=run.id,
            material_id="scm-material-182", canonical_material_id="material-182",
            projection_date=date.today(), opening_balance=100, supply_qty=0, demand_qty=50,
            closing_balance=50, safety_stock_qty=0, projected_after_safety=50,
            shortage_qty=Decimal("0"), excess_qty=0, risk_status="SAFE",
            planning_status="SAFE", source_freshness={"status": "FRESH"}))
        db.flush()
        assert _record_recovery_observations(db, run) == 1
        assert _record_recovery_observations(db, run) == 0
        observation = db.query(RecoveryObservation).filter_by(target_id=target.id).one()
        assert observation.observed_value == 1
        assert observation.source_entity["planning_run_id"] == run.id
        assert case.status == "monitoring"
