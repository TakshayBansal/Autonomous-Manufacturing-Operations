from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import models as core
from app.eventing import CONSUMERS, dispatch_one, pending_event_ids
from app.platform import actions
from app.platform.integrity import check_tenant
from app.platform.models import (ActionApproval, ActionExecution, ActionIntent, ActionOutcome,
    DataProvenance, DataQualityIssue, EntityRelationship, ExternalEntityReference,
    OperationalCase, PlatformBOM, PlatformBOMItem, PlatformInventoryLocation,
    PlatformInventoryPosition, PlatformMaterial, PlatformProduct, PlatformPurchaseOrder,
    PlatformPurchaseOrderLine, PlatformWorkOrderReference)
from app.platform.purchase_orders import apply_simulated_reschedule, ingest_delivery_update
from app.platform.relationships import find_paths, get_impact, sync_tenant_graph
from app.platform.state import FactoryStateService
from app.platform.trace import correlation_trace
from app.scm import models as scm
from app.scm.service import create_run, execute_run


@pytest.fixture(scope="module")
def architecture_engine(tmp_path_factory):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('core-architecture') / 'core.db'}")
    core.Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(architecture_engine):
    connection = architecture_engine.connect()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for table in reversed(core.Base.metadata.sorted_tables):
            connection.execute(table.delete())
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.close()


def _fixture(db: Session) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ids = {"tenant": "TEST_MANUFACTURER", "company": "TEST_COMPANY", "plant": "PLANT_A",
           "department": "TEST_DEPT", "user": "SCM_PLANNER", "manager": "MANAGER",
           "planner_membership": "MEM-SCM", "manager_membership": "MEM-MANAGER",
           "source": "TEST_ERP", "connection": "CONN-ERP", "correlation": "CORR-PO-001-DELAY"}
    db.add_all([
        core.Tenant(id=ids["tenant"], name="Test Manufacturer", workspace_kind="test"),
        core.Company(id=ids["company"], tenant_id=ids["tenant"], name="Test Manufacturer", erp_code="TEST"),
        core.Plant(id=ids["plant"], tenant_id=ids["tenant"], company_id=ids["company"], name="Plant A", erp_location_code="PLANT_A"),
        core.Department(id=ids["department"], tenant_id=ids["tenant"], plant_id=ids["plant"], name="Planning"),
        core.Uom(id="UNIT", label="Unit"),
    ]); db.flush()
    db.add_all([
        core.User(id=ids["user"], tenant_id=ids["tenant"], plant_id=ids["plant"], department_id=ids["department"],
                  name="SCM Planner", email="planner@test.local", role="admin", password_hash="x"),
        core.User(id=ids["manager"], tenant_id=ids["tenant"], plant_id=ids["plant"], department_id=ids["department"],
                  name="Manager", email="manager@test.local", role="admin", password_hash="x"),
        core.IntegrationConnection(id=ids["connection"], tenant_id=ids["tenant"], plant_id=ids["plant"],
            provider="sap", name="Test ERP", mode="simulation", status="active",
            capabilities=["purchase_order.delivery_update"], enabled_capabilities=["purchase_order.delivery_update"]),
    ]); db.flush()
    db.add_all([
        core.WorkspaceMembership(id=ids["planner_membership"], account_id="A-SCM", tenant_id=ids["tenant"],
            user_id=ids["user"], default_plant_id=ids["plant"], plant_ids=[ids["plant"]], department_id=ids["department"], role="scm_planner"),
        core.WorkspaceMembership(id=ids["manager_membership"], account_id="A-MANAGER", tenant_id=ids["tenant"],
            user_id=ids["manager"], default_plant_id=ids["plant"], plant_ids=[ids["plant"]], department_id=ids["department"], role="manager"),
    ])
    supplier = core.Supplier(id="SUPPLIER_X", tenant_id=ids["tenant"], plant_id=ids["plant"], company_id=ids["company"],
        code="SUPPLIER_X", name="Supplier X", legal_name="Supplier X Ltd", status="active",
        quality_score=95, delivery_score=92, erp_vendor_id="SUPPLIER_X")
    area = core.PlantArea(id="AREA_1", tenant_id=ids["tenant"], plant_id=ids["plant"], code="AREA_1", name="Assembly")
    line = core.ProductionLine(id="LINE_1", tenant_id=ids["tenant"], plant_id=ids["plant"], area_id=area.id,
        code="LINE_1", name="Line 1")
    machine = core.PlantAsset(id="MACHINE_1", tenant_id=ids["tenant"], plant_id=ids["plant"], area_id=area.id,
        line_id=line.id, code="MACHINE_1", name="Machine 1")
    shift = core.PlantShift(id="SHIFT_1", tenant_id=ids["tenant"], plant_id=ids["plant"], code="DAY", name="Day",
        starts_at=now, ends_at=now + timedelta(hours=8))
    db.add_all([supplier, area]); db.flush()
    db.add(line); db.flush()
    db.add_all([machine, shift]); db.flush()
    material = PlatformMaterial(id="MAT_001", tenant_id=ids["tenant"], plant_id=ids["plant"],
        company_id=ids["company"], code="MAT_001", name="Material 001", base_uom_id="UNIT")
    product = PlatformProduct(id="PRODUCT_A", tenant_id=ids["tenant"], plant_id=ids["plant"],
        company_id=ids["company"], code="PRODUCT_A", name="Product A", base_uom_id="UNIT")
    bom = PlatformBOM(id="BOM_A", tenant_id=ids["tenant"], plant_id=ids["plant"], company_id=ids["company"],
        product_id=product.id, revision="A", effective_from=now.date())
    db.add_all([material, product]); db.flush()
    db.add(bom); db.flush()
    db.add(PlatformBOMItem(id="BOM_A_10", tenant_id=ids["tenant"], plant_id=ids["plant"], bom_id=bom.id,
        component_entity_type="material", component_id=material.id, quantity=1, uom_id="UNIT", line_number=10))
    item = core.Item(id="ITEM_MAT_001", tenant_id=ids["tenant"], plant_id=ids["plant"], code="MAT_001",
        name="Material 001", uom_id="UNIT", erp_item_code="MAT_001")
    work_order = core.ProductionWorkOrder(id="WO_001", tenant_id=ids["tenant"], plant_id=ids["plant"],
        line_id=line.id, shift_id=shift.id, external_reference="WO_001", product_code=product.code,
        product_name=product.name, target_quantity=30000, planned_start_at=now + timedelta(days=9),
        planned_end_at=now + timedelta(days=10), status="released")
    db.add_all([item, work_order]); db.flush()
    db.add(core.ProductionMaterialRequirement(id="WO_REQ_1", tenant_id=ids["tenant"], plant_id=ids["plant"],
        work_order_id=work_order.id, item_id=item.id, material_code=material.code,
        required_quantity=30000, uom="UNIT", required_at=now + timedelta(days=9)))
    db.add(PlatformWorkOrderReference(id="WO_REF_1", tenant_id=ids["tenant"], plant_id=ids["plant"],
        work_order_id=work_order.id, product_id=product.id, work_center_id=line.id,
        equipment_id=machine.id, source_authority="operations"))
    location = PlatformInventoryLocation(id="LOC_A", tenant_id=ids["tenant"], plant_id=ids["plant"],
        code="STORE_A", name="Plant A Store")
    db.add(location); db.flush()
    db.add(PlatformInventoryPosition(id="INV_POS_1", tenant_id=ids["tenant"], plant_id=ids["plant"],
        material_id=material.id, location_id=location.id, on_hand_qty=30000, available_qty=30000,
        as_of_at=now, source_authority=ids["source"], freshness_status="fresh"))
    po = PlatformPurchaseOrder(id="PO_001", tenant_id=ids["tenant"], plant_id=ids["plant"], order_number="PO_001",
        supplier_id=supplier.id, status="OPEN", original_delivery_date=now.date() + timedelta(days=8),
        confirmed_delivery_date=now.date() + timedelta(days=8), source_authority=ids["source"])
    db.add(po); db.flush()
    db.add(PlatformPurchaseOrderLine(id="PO_001_10", tenant_id=ids["tenant"], plant_id=ids["plant"],
        purchase_order_id=po.id, line_number="10", material_id=material.id, quantity=50000, uom_id="UNIT"))
    scm_material = scm.SCMMaterial(id="SCM_MAT_001", tenant_id=ids["tenant"], plant_id=None,
        company_id=ids["company"], material_code="MAT_001", description="Material 001", base_uom_id="UNIT")
    db.add(scm_material); db.flush()
    db.add(scm.SCMMaterialPlant(id="SCM_MP_1", tenant_id=ids["tenant"], plant_id=ids["plant"],
        material_id=scm_material.id, item_id=item.id))
    db.add(scm.SCMInventorySnapshot(id="SCM_INV_1", tenant_id=ids["tenant"], plant_id=ids["plant"],
        material_id=scm_material.id, snapshot_at=now, on_hand_qty=Decimal("30000"),
        available_qty=Decimal("30000"), uom_id="UNIT", source_system=ids["source"], source_record_id="INV-BASE"))
    db.add(scm.SCMMaterialRequirement(id="SCM_REQ_1", tenant_id=ids["tenant"], plant_id=ids["plant"],
        material_id=scm_material.id, required_date=now.date() + timedelta(days=9), quantity=Decimal("30000"),
        uom_id="UNIT", requirement_type="WORK_ORDER", source_system="operations", external_id="WO_001",
        lineage={"work_order_id": "WO_001", "product_id": "PRODUCT_A"}))
    supply = scm.SCMSupplyOrder(id="SCM_PO_001", tenant_id=ids["tenant"], plant_id=ids["plant"], supply_type="PURCHASE_ORDER",
        material_id=scm_material.id, supplier_id=supplier.id, order_number="PO_001", line_number="10",
        ordered_qty=Decimal("50000"), received_qty=Decimal("0"), uom_id="UNIT", status="OPEN",
        source_system=ids["source"], source_record_id="PO_001-10", source_entity_type="purchase_order", source_entity_id=po.id)
    db.add(supply); db.flush()
    db.add(scm.SCMSupplyScheduleLine(id="SCM_PO_SCHED_1", tenant_id=ids["tenant"], plant_id=ids["plant"],
        supply_order_id=supply.id, schedule_line_number="1", scheduled_qty=Decimal("50000"),
        received_qty=Decimal("0"), original_due_date=now.date() + timedelta(days=8),
        current_due_date=now.date() + timedelta(days=8), status="CONFIRMED", source_record_id="PO_001-S1"))
    refs = [
        (ids["source"], "supplier", "SUPPLIER_X", "supplier", supplier.id),
        (ids["source"], "material", "MAT_001", "material", material.id),
        (ids["source"], "purchase_order", "PO_001", "purchase_order", po.id),
        (ids["source"], "site", "PLANT_A", "site", ids["plant"]),
        ("legacy:scm", "material", scm_material.id, "material", material.id),
        ("operations", "material", item.id, "material", material.id),
    ]
    for index, (source, entity_type, external_id, canonical_type, canonical_id) in enumerate(refs):
        db.add(ExternalEntityReference(id=f"REF-{index}", tenant_id=ids["tenant"], plant_id=ids["plant"],
            source_system=source, entity_type=entity_type, canonical_entity_type=canonical_type,
            canonical_entity_id=canonical_id, external_id=external_id, external_code=external_id))
    db.flush(); sync_tenant_graph(db, ids["tenant"]); db.commit()
    return {**ids, "now": now, "po": po, "material": material, "user": db.get(core.User, ids["user"])}


def _drain(db: Session, *, correlation_id: str | None = None):
    for _ in range(20):
        rows = db.query(core.EventOutbox).filter(core.EventOutbox.status.in_(["pending", "retry"]))
        if correlation_id:
            rows = rows.filter_by(correlation_id=correlation_id)
        ids = [row.event_id for row in rows.order_by(core.EventOutbox.created_at).all()]
        if not ids: return
        for event_id in ids: dispatch_one(db, event_id)
    raise AssertionError("event drain did not settle")


def test_external_po_delay_runs_the_shared_core_end_to_end(db):
    fx = _fixture(db)
    baseline = create_run(db, fx["user"], as_of_at=fx["now"], trigger_key="baseline")
    execute_run(db, baseline.id); db.commit()
    baseline_risk = db.query(scm.SCMMaterialRiskSummary).filter_by(planning_run_id=baseline.id).one()
    assert baseline_risk.severity == "GREEN"
    assert (baseline.horizon_end - baseline.horizon_start).days + 1 == 210
    assert db.query(scm.SCMMaterialProjectionPoint).filter_by(planning_run_id=baseline.id).count() == 210
    assert db.query(scm.SCMPlanningInputSnapshot).filter_by(planning_run_id=baseline.id).one().payload_hash
    assert db.query(scm.SCMProductReadiness).filter_by(planning_run_id=baseline.id).one().status == "READY"

    po, event, replayed = ingest_delivery_update(db, tenant_id=fx["tenant"], plant_id=fx["plant"],
        connection_id=fx["connection"], source_key=fx["source"], source_record_id="ERP-DELIVERY-UPDATE-001",
        purchase_order_external_id="PO_001", supplier_external_id="SUPPLIER_X", material_external_id="MAT_001",
        confirmed_delivery_date=fx["now"].date() + timedelta(days=12), observed_at=fx["now"],
        mapping_version="po-delivery@1", correlation_id=fx["correlation"], causation_id="ERP-CHANGE-001")
    db.commit()
    assert replayed is False and po.id == "PO_001"
    assert event.status == "pending" and event.event_version == 1
    assert all([event.event_id, event.tenant_id, event.plant_id, event.subject_type,
                event.subject_id, event.source_system, event.correlation_id, event.causation_id,
                event.occurred_at, event.recorded_at])
    assert db.query(core.IntegrationIngestionRecord).filter_by(source_record_key="ERP-DELIVERY-UPDATE-001").one().status == "applied"
    assert db.query(DataProvenance).filter_by(correlation_id=fx["correlation"], entity_id=po.id).count() >= 1

    assert dispatch_one(db, event.event_id) == "completed"
    assert dispatch_one(db, event.event_id) == "completed"
    _drain(db, correlation_id=fx["correlation"])
    case = db.query(OperationalCase).filter_by(correlation_id=fx["correlation"], case_type="material_shortage").one()
    intent = db.query(ActionIntent).filter_by(correlation_id=fx["correlation"]).one()
    recommendation = db.query(scm.SCMRecommendation).filter_by(
        planning_run_id=case.context["planning_run_id"]).one()
    assert recommendation.rank == 1 and recommendation.score_dimensions
    from app.scm.recommendations import simulate
    candidate_simulation = simulate(db, recommendation)
    assert candidate_simulation.resolves_risk is True
    assert candidate_simulation.before_metrics["stockout_date"]
    assert candidate_simulation.after_metrics["stockout_date"] is None
    lifecycle_risk = db.query(scm.SCMMaterialRisk).filter_by(
        canonical_material_id="MAT_001").one()
    readiness = db.query(scm.SCMProductReadiness).filter_by(
        planning_run_id=lifecycle_risk.latest_planning_run_id).one()
    assert readiness.status == "BLOCKED" and readiness.work_order_id == "WO_001"
    assert db.query(scm.SCMComponentReadiness).filter_by(readiness_id=readiness.id).one().material_id == "MAT_001"
    assert lifecycle_risk.operational_case_id == case.id
    assert any(row["id"] == "PRODUCT_A" for row in lifecycle_risk.affected_entities)
    assert any(row["id"] == "WO_001" for row in lifecycle_risk.affected_entities)
    delta = db.query(scm.SCMPlanningRunDelta).filter_by(
        planning_run_id=lifecycle_risk.latest_planning_run_id, canonical_material_id="MAT_001").one()
    assert any(driver["type"] == "PO_DATE_CHANGE" for driver in delta.drivers)
    state = FactoryStateService(db, fx["tenant"], fx["plant"]).now("material", fx["material"].id)
    assert 8 <= state["derived"]["runway_days"] <= 10
    assert state["derived"]["shortage_gap_days"] >= 2
    assert state["freshness"] and state["provenance"]
    impact = get_impact(db, fx["tenant"], "purchase_order", po.id)
    impacted = {(node["type"], node["id"]) for node in impact["nodes"]}
    assert {("material", "MAT_001"), ("product", "PRODUCT_A"), ("work_order", "WO_001"),
            ("work_center", "LINE_1")}.issubset(impacted)
    assert find_paths(db, fx["tenant"], "purchase_order", po.id, "work_order", "WO_001")
    assert case.context["purchase_order_id"] == po.id
    assert intent.status == "awaiting_approval" and intent.target_id == po.id
    assert intent.originating_case_id == case.id and intent.expected_impact and intent.evidence
    assert db.query(ActionApproval).filter_by(action_intent_id=intent.id).one().decision == "pending"
    assert db.query(ActionIntent).filter_by(correlation_id=fx["correlation"]).count() == 1

    actions.decide(db, intent, fx["manager_membership"], True, "Restore delivery before stockout")
    execution = actions.execute_external(db, intent, executor="simulated.sap@1", execute=lambda current:
        apply_simulated_reschedule(db, po=po,
            target_date=fx["now"].date() + timedelta(days=8), correlation_id=current.correlation_id,
            source_record_id=f"action:{current.id}"))
    db.commit()
    assert execution.status == "succeeded" and execution.external_reference
    assert db.query(ActionOutcome).filter_by(action_intent_id=intent.id).one().verification_status == "pending"
    _drain(db, correlation_id=fx["correlation"])
    db.refresh(case); db.refresh(intent)
    outcome = db.query(ActionOutcome).filter_by(action_intent_id=intent.id).one()
    assert case.status == "resolved" and intent.status == "verified"
    assert outcome.verification_status == "verified_recovered"
    assert db.query(scm.SCMSupplyScheduleLine).filter_by(id="SCM_PO_SCHED_1").one().current_due_date == fx["now"].date() + timedelta(days=8)
    trace = correlation_trace(db, fx["tenant"], fx["correlation"])
    kinds = {step["kind"] for step in trace["steps"]}
    assert {"provenance", "canonical_event", "consumer", "factory_state", "planning_run",
            "operational_case", "recommendation", "action_intent", "policy", "approval",
            "execution", "verification", "audit"}.issubset(kinds)
    assert not check_tenant(db, fx["tenant"])


def test_duplicate_external_update_is_idempotent(db):
    fx = _fixture(db)
    args = dict(tenant_id=fx["tenant"], plant_id=fx["plant"], connection_id=fx["connection"],
        source_key=fx["source"], source_record_id="DUPLICATE-001", purchase_order_external_id="PO_001",
        supplier_external_id="SUPPLIER_X", material_external_id="MAT_001",
        confirmed_delivery_date=fx["now"].date() + timedelta(days=12), observed_at=fx["now"],
        mapping_version="po-delivery@1", correlation_id="CORR-DUPLICATE")
    _, event, first_replay = ingest_delivery_update(db, **args); db.commit()
    _, same_event, second_replay = ingest_delivery_update(db, **args)
    assert first_replay is False and second_replay is True and same_event.event_id == event.event_id
    assert db.query(core.EventOutbox).filter_by(correlation_id="CORR-DUPLICATE", event_type="purchase_order.rescheduled").count() == 1


def test_scenario_runs_from_immutable_baseline_without_mutating_operational_data(db):
    fx = _fixture(db)
    baseline = create_run(db, fx["user"], as_of_at=fx["now"], trigger_key="scenario-baseline")
    execute_run(db, baseline.id)
    baseline_snapshot = db.query(scm.SCMPlanningInputSnapshot).filter_by(planning_run_id=baseline.id).one()
    baseline_hash = baseline_snapshot.payload_hash
    scenario = scm.SCMPlanningScenario(tenant_id=fx["tenant"], plant_id=fx["plant"],
        name="Demand plus 15 percent", scenario_type="WHAT_IF", baseline_run_id=baseline.id,
        created_by_user_id=fx["user"].id, status="ACTIVE")
    db.add(scenario); db.flush()
    db.add(scm.SCMScenarioOverride(tenant_id=fx["tenant"], plant_id=fx["plant"],
        scenario_id=scenario.id, material_id="SCM_MAT_001", override_type="DEMAND",
        values={"factor": 1.15}, reason="Demand sensitivity"))
    scenario_run = create_run(db, fx["user"], as_of_at=fx["now"], scenario_id=scenario.id,
                              trigger_type="SCENARIO")
    execute_run(db, scenario_run.id)
    db.refresh(baseline_snapshot)
    scenario_snapshot = db.query(scm.SCMPlanningInputSnapshot).filter_by(planning_run_id=scenario_run.id).one()
    assert baseline_snapshot.payload_hash == baseline_hash
    assert scenario_snapshot.payload_hash != baseline_hash
    assert scenario_snapshot.payload["baseline_snapshot_id"] == baseline_snapshot.id
    assert Decimal(scenario_snapshot.payload["materials"][0]["demands"][0]["quantity"]) == Decimal("34500.00")
    assert db.query(scm.SCMMaterialRequirement).filter_by(id="SCM_REQ_1").one().quantity == Decimal("30000")


def test_invalid_mapping_retains_rejected_receipt_and_provenance(db):
    fx = _fixture(db)
    with pytest.raises(ValueError, match="Canonical mapping missing"):
        ingest_delivery_update(db, tenant_id=fx["tenant"], plant_id=fx["plant"], connection_id=fx["connection"],
            source_key=fx["source"], source_record_id="BAD-MAP-001", purchase_order_external_id="PO_001",
            supplier_external_id="SUPPLIER_X", material_external_id="UNKNOWN", confirmed_delivery_date=fx["now"].date(),
            observed_at=fx["now"], mapping_version="po-delivery@1", correlation_id="CORR-BAD-MAP")
    db.flush()
    assert db.query(core.IntegrationIngestionRecord).filter_by(source_record_key="BAD-MAP-001", status="rejected").one()
    assert db.query(DataProvenance).filter_by(correlation_id="CORR-BAD-MAP", quality_status="rejected").one()
    assert db.query(DataQualityIssue).filter_by(rule_key="invalid_canonical_mapping").one()


def test_policy_and_approval_rejection_block_execution(db):
    fx = _fixture(db)
    blocked = actions.propose(db, tenant_id=fx["tenant"], plant_id=fx["plant"], membership_id=fx["planner_membership"],
        action_type="AUTONOMOUS_MACHINE_CONTROL", target_type="equipment", target_id="MACHINE_1", payload={},
        rationale="Prohibited", idempotency_key="policy-blocked", correlation_id="CORR-POLICY")
    assert blocked.status == "blocked"
    with pytest.raises(ValueError): actions.execute_external(db, blocked, executor="never", execute=lambda _: {})
    rejected = actions.propose(db, tenant_id=fx["tenant"], plant_id=fx["plant"], membership_id=fx["planner_membership"],
        action_type="RESCHEDULE_PURCHASE_ORDER", target_type="purchase_order", target_id="PO_001", payload={},
        rationale="Candidate", idempotency_key="approval-rejected", correlation_id="CORR-REJECT")
    actions.decide(db, rejected, fx["manager_membership"], False, "Use alternate supply")
    assert rejected.status == "rejected"
    with pytest.raises(ValueError): actions.execute_external(db, rejected, executor="never", execute=lambda _: {})
    assert db.query(ActionExecution).filter(ActionExecution.action_intent_id.in_([blocked.id, rejected.id])).count() == 0
    assert correlation_trace(db, fx["tenant"], "CORR-REJECT")["step_count"] > 0


def test_execution_failure_and_false_recovery_are_distinct(db):
    fx = _fixture(db)
    failed = actions.propose(db, tenant_id=fx["tenant"], plant_id=fx["plant"], membership_id=fx["planner_membership"],
        action_type="RESCHEDULE_PURCHASE_ORDER", target_type="purchase_order", target_id="PO_001", payload={},
        rationale="Connector failure", idempotency_key="execution-failure", correlation_id="CORR-EXEC-FAIL")
    actions.decide(db, failed, fx["manager_membership"], True, "Approved")
    execution = actions.execute_external(db, failed, executor="failing.sap", execute=lambda _: (_ for _ in ()).throw(TimeoutError("SAP unavailable")))
    assert execution.status == "failed" and failed.status == "execution_failed" and execution.error
    case = OperationalCase(tenant_id=fx["tenant"], plant_id=fx["plant"], case_type="material_shortage",
        title="Still unsafe", status="open", correlation_id="CORR-FALSE", canonical_entity_type="material", canonical_entity_id="MAT_001")
    db.add(case); db.flush()
    intent = actions.propose(db, tenant_id=fx["tenant"], plant_id=fx["plant"], membership_id=fx["planner_membership"],
        action_type="RESCHEDULE_PURCHASE_ORDER", target_type="purchase_order", target_id="PO_001", payload={},
        rationale="False recovery", idempotency_key="false-recovery", correlation_id="CORR-FALSE", originating_case_id=case.id)
    actions.decide(db, intent, fx["manager_membership"], True, "Approved")
    success = actions.execute_external(db, intent, executor="simulated.sap", execute=lambda _: {"external_reference": "SUCCESS-BUT-UNSAFE"})
    assert success.status == "succeeded"
    actions.verify_outcome(db, intent, recovered=False, evidence=[{"severity": "CRITICAL"}], case=case)
    assert db.query(ActionOutcome).filter_by(action_intent_id=intent.id).one().verification_status == "verification_failed"
    assert case.status == "open" and intent.status == "not_recovered"


def test_outbox_and_consumer_failures_are_retryable_and_idempotent(db, monkeypatch):
    fx = _fixture(db)
    from app.platform.events import DomainEvent, publish
    event = publish(db, DomainEvent("inventory.updated", fx["tenant"], fx["plant"], "material", "MAT_001",
        {"material_id": "MAT_001"}, correlation_id="CORR-OUTBOX")); db.commit()
    # Publisher failure occurs after the business transaction: the durable row remains pending.
    assert event.status == "pending" and event.event_id in pending_event_ids(db)
    calls = {"count": 0}
    def flaky(session, row):
        calls["count"] += 1
        if calls["count"] == 1: raise RuntimeError("temporary consumer failure")
    original = list(CONSUMERS.get("inventory.updated", []))
    CONSUMERS["inventory.updated"] = [("test_flaky_consumer", flaky)]
    try:
        with pytest.raises(RuntimeError): dispatch_one(db, event.event_id)
        db.refresh(event)
        assert event.status == "retry" and event.next_attempt_at and event.last_error
        receipt = db.query(core.EventConsumerReceipt).filter_by(event_id=event.event_id, consumer_name="test_flaky_consumer").one()
        assert receipt.status == "failed"
        event.next_attempt_at = None; db.commit()
        assert dispatch_one(db, event.event_id) == "completed"
        assert calls["count"] == 2
    finally:
        CONSUMERS["inventory.updated"] = original


def test_external_identity_cannot_be_silently_remapped(db):
    fx = _fixture(db)
    from app.platform.integrations import record_ingestion
    with pytest.raises(ValueError, match="different canonical identity"):
        record_ingestion(db, tenant_id=fx["tenant"], plant_id=fx["plant"], source_key=fx["source"],
            source_record_id="MAT_001", entity_type="material", canonical_entity_id="OTHER-MATERIAL")
    assert db.query(ExternalEntityReference).filter_by(source_system=fx["source"], entity_type="material",
        external_id="MAT_001").one().canonical_entity_id == "MAT_001"
    assert db.query(EntityRelationship).filter_by(tenant_id=fx["tenant"]).count() > 0
