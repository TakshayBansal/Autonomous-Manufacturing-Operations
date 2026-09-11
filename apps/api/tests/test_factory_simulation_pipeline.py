from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.operations import service as operational_v2
from app.connector_sdk import ConnectorContext, ConnectorMode, FactorySimulatorConnector
from app.db import models
from app.db.seed_v2_simulation import CHAKAN_ID, TENANT_ID, seed_northstar
from app.operations.normalization import normalize_results

spec = importlib.util.spec_from_file_location("northstar_factory_source", Path(__file__).parents[3] / "services/factory-simulator/app.py")
source = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(source)


@pytest.fixture(scope="module")
def seeded_engine():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_northstar(session, reference=datetime.now(timezone.utc)); session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def db(seeded_engine):
    connection=seeded_engine.connect(); transaction=connection.begin()
    with Session(bind=connection) as session:
        yield session
    transaction.rollback(); connection.close()


def connector_for(factory):
    connector = FactorySimulatorConnector()
    def request(path):
        parsed = urlparse(path)
        if parsed.path == "/sim/v1/state": return factory.state()
        capability = parsed.path.rsplit("/", 1)[-1]
        cursor = int(parse_qs(parsed.query).get("cursor", ["0"])[0])
        rows = [row for row in factory.streams[capability] if int(row["cursor"]) > cursor]
        return {"records": rows, "next_cursor": rows[-1]["cursor"] if rows else str(cursor)}
    connector._request = request
    return connector


def ingest(db, factory, capability):
    connection = db.get(models.IntegrationConnection, "integration-ns-factory")
    connector = connector_for(factory)
    context = ConnectorContext(connection.id, TENANT_ID, CHAKAN_ID, ConnectorMode.SIMULATION,
                               frozenset(connection.enabled_capabilities))
    result = connector.pull(context, capability, None)
    job = models.IntegrationSyncJob(tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        connection_id=connection.id, job_type="pipeline_test", status="running", summary={})
    db.add(job); db.flush()
    return normalize_results(db, job, connection, {capability: result})


def evaluate(db, records):
    deviations = []
    for record in records:
        if isinstance(record, models.ProductionDowntimeEvent):
            deviations.append(operational_v2.evaluate_downtime_threshold(db, record))
        elif isinstance(record, models.MachineSignalSample):
            deviations.append(operational_v2.evaluate_machine_signals(db, record))
        elif isinstance(record, models.ProductionQualityEvent):
            deviations.extend((operational_v2.evaluate_rejection_rate(db, record), operational_v2.evaluate_spc_control_limit(db, record)))
        elif isinstance(record, (models.MaterialInventoryPosition, models.ProductionSupplierCommitment)):
            for requirement in db.query(models.ProductionMaterialRequirement).filter_by(
                    tenant_id=TENANT_ID, material_code=record.material_code).all():
                deviations.append(operational_v2.recompute_material_readiness(db, requirement))
    db.flush()
    return [row for row in deviations if row is not None]


def test_sustained_raw_machine_signals_are_inferred_by_product(db):
    factory=source.Factory(30)
    for temperature in (82.1,83.0,84.2):
        factory.publish_signals({"asset_id":"asset-ns-01-01","spindle_temperature_c":temperature,
                                 "vibration_mm_s":5.2,"machine_mode":"running"})
    result=ingest(db,factory,"read_machine_events")
    deviations=evaluate(db,result["applied_records"])
    assert result["counts"]["applied"] == 3
    assert deviations[-1].detector_key == "machine_signal_threshold"
    assert deviations[-1].actual_state["spindle_temperature_c"] == 84.2


def test_normal_signals_move_prior_machine_constraint_to_monitoring(db):
    factory=source.Factory(31)
    for temperature in (83.0,84.0,85.0):
        factory.publish_signals({"asset_id":"asset-ns-01-01","spindle_temperature_c":temperature,
                                 "vibration_mm_s":5.2,"machine_mode":"running"})
    abnormal=ingest(db,factory,"read_machine_events")
    deviation=evaluate(db,abnormal["applied_records"])[-1]
    for _ in range(3):
        factory.publish_signals({"asset_id":"asset-ns-01-01","spindle_temperature_c":64,
                                 "vibration_mm_s":2.2,"machine_mode":"running"})
    normal=ingest(db,factory,"read_machine_events")
    evaluate(db,normal["applied_records"])
    assert deviation.status == "monitoring"


def test_recovered_asset_evidence_releases_downtime_constraint(db):
    factory=source.Factory(32); factory.inject("spindle_temperature_failure")
    downtime=ingest(db,factory,"read_downtime")
    deviation=evaluate(db,downtime["applied_records"])[0]
    factory.control("reset")
    machine=ingest(db,factory,"read_machine_events")
    recovered=[row for row in machine["applied_records"]
               if isinstance(row,models.AssetFaultEvent) and row.cleared_at is not None]
    assert recovered
    operational_v2.reconcile_asset_recovery(db,recovered[0])
    assert deviation.status == "monitoring"


def test_forecast_is_bounded_across_a_cumulative_counter_restart(db):
    order=db.get(models.ProductionWorkOrder,"wo-ns-live-01")
    db.query(models.ProductionActualPoint).filter_by(work_order_id=order.id).delete()
    at=order.planned_start_at+timedelta(hours=4)
    # Previous run ended at 500; the restarted source begins again at 300.
    for index,quantity in enumerate((480,490,500,300,302,304,306)):
        db.add(models.ProductionActualPoint(tenant_id=TENANT_ID,plant_id=CHAKAN_ID,
            work_order_id=order.id,recorded_at=at-timedelta(minutes=6-index),
            good_quantity=quantity,reject_quantity=0,source="factory_simulator",
            source_event_key=f"counter-restart:{index}"))
    db.flush()
    forecast=operational_v2.production_forecast(db,order,at)
    assert forecast["forecast_quantity"] <= order.target_quantity*1.25
    assert forecast["forecast_quantity"] >= forecast["actual_quantity"]


def test_spindle_failure_reaches_canonical_downtime_deviation_work_and_notifications(db):
    factory = source.Factory(22); factory.inject("spindle_temperature_failure")
    result = ingest(db, factory, "read_downtime")
    deviations = evaluate(db, result["applied_records"])
    assert result["counts"] == {"received": 1, "applied": 1, "duplicates": 0, "errors": 0}
    assert deviations[0].owner_role == "maintenance_manager"
    assert db.query(models.OperationalAction).filter_by(deviation_id=deviations[0].id).count() == 1
    assert db.query(models.Notification).filter_by(linked_entity_id=deviations[0].id).count() >= 2
    assert db.query(models.EventOutbox).filter_by(event_type="downtime.updated").count() == 1


def test_dimensional_drift_creates_quality_recovery_signals(db):
    factory = source.Factory(23); factory.inject("dimensional_drift")
    result = ingest(db, factory, "read_quality")
    deviations = evaluate(db, result["applied_records"])
    assert {row.detector_key for row in deviations} == {"rejection_rate_high", "spc_control_limit_breached"}
    assert all(row.owner_role == "quality_manager" for row in deviations)


def test_supplier_delay_recomputes_material_risk(db):
    factory = source.Factory(24); factory.inject("supplier_material_delay")
    commitments = ingest(db, factory, "read_supplier_commitments")
    inventory = ingest(db, factory, "read_inventory")
    evaluate(db, commitments["applied_records"] + inventory["applied_records"])
    snapshot = db.query(models.MaterialReadinessSnapshot).filter_by(
        tenant_id=TENANT_ID, material_code="RM-17-4PH-025").order_by(models.MaterialReadinessSnapshot.created_at.desc()).first()
    assert snapshot.state in {"AT_RISK", "BLOCKED"}
    assert db.query(models.OperationalDeviation).filter_by(detector_key="material_readiness_risk").count() == 1


@pytest.mark.parametrize("scenario,expected_model", [
    ("supplier_email_change", models.SupplierChannelMessage), ("customer_order_surge", models.ProductionWorkOrder),
    ("urgent_management_requirement", models.Task), ("inbound_vehicle_mismatch", models.Task),
])
def test_business_streams_create_real_canonical_work(db, scenario, expected_model):
    factory = source.Factory(25); factory.inject(scenario)
    before = db.query(expected_model).filter_by(tenant_id=TENANT_ID).count()
    result = ingest(db, factory, "read_business_events")
    assert result["counts"]["applied"] == 1
    assert db.query(expected_model).filter_by(tenant_id=TENANT_ID).count() == before + 1


def test_duplicate_replay_is_idempotent_and_malformed_record_is_quarantined(db):
    factory = source.Factory(26); factory.inject("dimensional_drift")
    first = ingest(db, factory, "read_quality")
    factory.inject("duplicate_replay")
    repeated = ingest(db, factory, "read_quality")
    assert first["counts"]["applied"] == 1
    assert repeated["counts"]["duplicates"] >= 1
    malformed = source.Factory(27); malformed.sequence=100; malformed.inject("malformed_source_record")
    rejected = ingest(db, malformed, "read_quality")
    assert rejected["counts"]["errors"] == 1
    assert rejected["errors"][0]["error"]


def test_northstar_reset_cannot_delete_another_workspace(db):
    from app.db.seed_v2_simulation import seed_northstar
    db.add(models.Tenant(id="tenant-customer-preserved",name="Preserved Manufacturing",slug="preserved-manufacturing",workspace_kind="customer"))
    db.flush()
    seed_northstar(db,reset=True);db.flush()
    assert db.get(models.Tenant,"tenant-customer-preserved").name == "Preserved Manufacturing"
    assert db.get(models.Tenant,TENANT_ID) is not None


def test_northstar_reset_preserves_immutable_ledgers(db):
    audit = models.AuditEvent(
        id="audit-ns-before-reset", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        actor_user_id="usr-ns-14", actor="Rhea Nair", action="simulation.control",
        entity_type="simulation", entity_id="northstar", result="success",
        correlation_id="corr-ns-before-reset", payload_hash="sha256:preserved", meta={},
    )
    decision = models.ApprovalDecision(
        id="approval-ns-before-reset", tenant_id=TENANT_ID, plant_id=CHAKAN_ID,
        entity_type="purchase_order", entity_id="po-ns-preserved", decision="approved",
        decided_by_user_id="usr-ns-10", rationale="Approved before reset",
        immutable_hash="sha256:preserved",
    )
    db.add_all([audit, decision]); db.flush()

    seed_northstar(db, reset=True); db.flush()

    assert db.get(models.AuditEvent, audit.id) is not None
    assert db.get(models.ApprovalDecision, decision.id) is not None


def test_operator_scope_contains_only_one_line_and_no_financial_authority(db):
    user=db.get(models.User,"usr-ns-05")
    membership=db.query(models.WorkspaceMembership).filter_by(user_id=user.id,tenant_id=TENANT_ID).one()
    scope=db.query(models.OperationalScope).filter_by(membership_id=membership.id).one()
    assert scope.line_ids == ["line-ns-01"]
    assert scope.financial_visibility is False
    assert "simulation.control" not in scope.authorities
