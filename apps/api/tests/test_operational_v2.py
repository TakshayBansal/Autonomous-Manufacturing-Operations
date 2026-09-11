from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.operations import service as operational_v2
from app.operations import integrations as integrations_v2
from app.operations import router as operational_router
from app.celery_app import celery_app
from app.workers import REQUIRED_TASKS, calculate_value_entries, index_knowledge_document
from app.operations.agents import run as run_v2_objective_agent
from app.db import models
from app.db.seed import PLANT_ID, TENANT_ID, reset_workspace_database
from app.db.session import SessionLocal


def test_behind_plan_creates_one_deviation_action_task_and_value():
    db: Session = SessionLocal()
    try:
        start = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)
        db.add_all([
            models.Tenant(id="v2-t", name="V2"),
            models.Company(id="v2-c", tenant_id="v2-t", name="V2", erp_code="V2"),
            models.Plant(id="v2-p", tenant_id="v2-t", company_id="v2-c", name="Plant", erp_location_code="P"),
            models.PlantArea(id="v2-a", tenant_id="v2-t", plant_id="v2-p", name="Area", code="A"),
            models.ProductionLine(id="v2-l", tenant_id="v2-t", plant_id="v2-p", area_id="v2-a",
                                  name="Line 3", code="L3", standard_good_rate_per_minute=2,
                                  contribution_per_good_unit=100),
            models.PlantShift(id="v2-s", tenant_id="v2-t", plant_id="v2-p", name="B", code="B",
                              starts_at=start, ends_at=start + timedelta(hours=8), status="active"),
        ])
        db.flush()
        work_order = models.ProductionWorkOrder(
            id="v2-wo", tenant_id="v2-t", plant_id="v2-p", line_id="v2-l", shift_id="v2-s",
            product_code="AX", product_name="Assembly", target_quantity=960,
            planned_start_at=start, planned_end_at=start + timedelta(hours=8), status="in_progress",
        )
        db.add(work_order)
        db.flush()
        db.add_all([
            models.ProductionPlanPoint(tenant_id="v2-t", plant_id="v2-p", work_order_id="v2-wo",
                                       recorded_at=start + timedelta(hours=4), cumulative_quantity=480),
            models.ProductionActualPoint(tenant_id="v2-t", plant_id="v2-p", work_order_id="v2-wo",
                                         recorded_at=start + timedelta(hours=3), good_quantity=260,
                                         source_event_key="v2-actual-1"),
            models.ProductionActualPoint(tenant_id="v2-t", plant_id="v2-p", work_order_id="v2-wo",
                                         recorded_at=start + timedelta(hours=4), good_quantity=360,
                                         source_event_key="v2-actual-2"),
        ])
        db.flush()
        first = operational_v2.evaluate_production_behind_plan(db, work_order, start + timedelta(hours=4))
        second = operational_v2.evaluate_production_behind_plan(db, work_order, start + timedelta(hours=4))
        db.flush()
        assert first is not None and first.id == second.id
        assert first.severity in {"high", "critical"}
        assert first.estimated_lost_units > 0
        assert db.query(models.OperationalDeviation).filter_by(tenant_id="v2-t").count() == 1
        assert db.query(models.OperationalAction).filter_by(deviation_id=first.id).count() == 1
        assert db.query(models.Task).filter_by(entity_id=first.id, task_type="operational_recovery").count() == 1
        assert db.query(models.OperationalValueEntry).filter_by(deviation_id=first.id).one().amount > 0
        assert db.query(models.EventOutbox).filter_by(event_type="deviation.created", aggregate_id=first.id).count() == 1
    finally:
        db.rollback()
        db.close()


def test_canonical_v2_seed_drives_command_center():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        payload = operational_v2.command_center(
            db, TENANT_ID, PLANT_ID, "shift-b-2026-08-12",
            datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
        )
        assert payload["pulse"]["target"] == 3700
        assert payload["pulse"]["actual"] == 1886
        assert payload["top_deviations"]
        assert payload["top_deviations"][0]["title"] == "Line 3 is behind plan"
        detectors = {row.detector_key for row in db.query(models.OperationalDeviation).all()}
        assert detectors == {"production_behind_plan", "downtime_exceeded_threshold",
                             "rejection_rate_high", "spc_control_limit_breached",
                             "material_readiness_risk"}
        assert {row["category"] for row in payload["loss_breakdown"]} >= {"production", "downtime", "quality"}
    finally:
        db.rollback()
        db.close()


def test_action_completion_moves_deviation_to_monitoring_then_verified():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="production_behind_plan").one()
        action = db.query(models.OperationalAction).filter_by(deviation_id=deviation.id).one()
        operational_v2.transition_action(db, action, "start")
        assert action.status == "in_progress"
        assert deviation.status == "action_in_progress"
        operational_v2.transition_action(db, action, "complete", {"summary": "Trajectory restored"})
        assert action.status == "completed"
        assert deviation.status == "monitoring"
        # A typed outcome is not proof: managed recovery is verified from a
        # post-action canonical operational snapshot.
        import pytest
        with pytest.raises(ValueError, match="observed operational state"):
            operational_v2.verify_deviation(
                db, deviation, {"recovered_value": 12500, "recovered_units": 140}, "usr-plant-001")
        assert deviation.status == "monitoring"
    finally:
        db.rollback()
        db.close()


def test_supplier_commitment_recomputes_readiness_and_links_v1_procurement():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        requirement = db.get(models.ProductionMaterialRequirement, "pmr-rm218-001")
        assert requirement.v1_requirement_line_id == "REQL-1"
        board = operational_v2.material_readiness_board(db, TENANT_ID, PLANT_ID, 30)
        material = board["work_orders"][0]["materials"][0]
        assert material["state"] == "AT_RISK"
        assert material["usable_now"] == 600
        assert material["confirmed_inbound"] == 300
        commitment = db.get(models.ProductionSupplierCommitment, "psc-rm218-unconfirmed")
        commitment.acknowledged = True
        commitment.committed_quantity = 600
        snapshot = operational_v2.recompute_material_readiness(
            db, requirement, datetime(2026, 8, 12, 10, 5, tzinfo=timezone.utc))
        assert snapshot.state == "READY"
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="material_readiness_risk").one()
        assert deviation.status == "monitoring"
        procurement = operational_v2.procurement_lifecycle(db, TENANT_ID, PLANT_ID)
        assert procurement[0]["stages"][0]["label"] == "Requirement"
        assert any(stage["label"] == "ERP PO" and stage["state"] == "simulated_posted"
                   for stage in procurement[0]["stages"])
    finally:
        db.rollback()
        db.close()


def test_v2_connector_health_staleness_and_versioned_mapping():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        connection = db.get(models.IntegrationConnection, "conn-v2-excel")
        payload = integrations_v2.serialize_connection(db, connection)
        assert payload["provider"] == "excel_csv"
        assert payload["writes_enabled"] is False
        assert payload["live_customer_verified"] is False
        assert payload["mappings"][0]["version"] == 1
        row = integrations_v2.create_mapping_version(
            db, connection, "Production operations",
            {"work_orders": "Plan v2", "actuals": "Actual v2"},
            {"trim": True}, {"work_orders": "external_owned"},
        )
        db.flush()
        assert row.profile_version == 2
        profiles = db.query(models.IntegrationMappingProfile).filter_by(
            connection_id=connection.id, name="Production operations").order_by(
            models.IntegrationMappingProfile.profile_version.asc()).all()
        assert [item.status for item in profiles] == ["superseded", "active"]
        job = db.get(models.IntegrationSyncJob, "sync-v2-production-001")
        job.finished_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
        health = integrations_v2.connection_health(db, connection)
        assert health["state"] == "stale"
        center = operational_v2.command_center(
            db, TENANT_ID, PLANT_ID, "shift-b-2026-08-12",
            datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
        )
        assert center["data_health"][0]["state"] == "stale"
    finally:
        db.rollback()
        db.close()


def test_quality_workspace_exposes_loss_pareto_and_active_containment():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        payload = operational_v2.quality_workspace(db, TENANT_ID, PLANT_ID)
        assert payload["pulse"]["rejection_rate"] > payload["pulse"]["target_rejection_rate"]
        assert payload["pulse"]["active_holds"] == 1
        assert payload["pulse"]["scrap_rework_impact"] > 0
        assert payload["pareto"][0]["defect"] == "DIMENSIONAL"
        assert payload["pareto"][0]["value"] > 0
        assert any(row["detector_key"] == "rejection_rate_high" for row in payload["deviations"])
        assert payload["containments"][0]["affected_lot"] == "LOT-QL-284"
    finally:
        db.rollback()
        db.close()


def test_maintenance_workspace_exposes_repeat_fault_and_recovery_work():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        payload = operational_v2.maintenance_workspace(db, TENANT_ID, PLANT_ID)
        assert payload["pulse"]["assets_down"] == 1
        assert payload["pulse"]["production_impact"] > 0
        assert payload["pulse"]["repeat_faults"] == 1
        asset = next(row for row in payload["assets"] if row["asset"]["code"] == "CNC-04")
        assert asset["state"] == "down"
        assert asset["current_fault"]["code"] == "701"
        assert asset["current_fault"]["repeat_count"] == 3
        assert asset["work"][0]["spare_code"] == "BR-28"
        assert asset["work"][0]["spare_available"] is True
        assert asset["work"][0]["deviation_id"]
    finally:
        db.rollback()
        db.close()


def test_improvement_workspace_ranks_evidence_and_tracks_experiment_benefit():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        payload = operational_v2.improvement_workspace(db, TENANT_ID, PLANT_ID)
        recurring = next(row for row in payload["opportunities"] if "CNC-04" in row["title"])
        assert recurring["occurrences"] == 3
        assert recurring["annualized_value"] > 0
        assert len(recurring["evidence"]) == 3
        experiment = payload["experiments"][0]
        assert experiment["status"] == "running"
        assert experiment["baseline"]["value"] == 3
        assert experiment["target"]["value"] == 1
        assert experiment["benefits"][0]["annualized_value"] == 480000
        assert experiment["benefits"][0]["confidence_state"] == "estimated"
    finally:
        db.rollback()
        db.close()


def test_predictive_risks_search_notifications_and_shift_briefing_are_grounded():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        risks = operational_v2.predictive_risks(
            db, TENANT_ID, PLANT_ID, datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
        assert any(row["risk_type"] == "end_of_shift_output" for row in risks)
        material = next(row for row in risks if row["risk_type"] == "material_shortage")
        assert material["confidence"] == "medium"
        assert material["evidence"][0]["id"] == "pmr-rm218-001"
        search = operational_v2.operational_search(db, TENANT_ID, PLANT_ID, "Fault 701")
        assert next(group for group in search["groups"] if group["entity"] == "Faults")["results"]
        user = db.get(models.User, "usr-plant-001")
        notifications = operational_v2.operational_notifications(db, user)
        assert notifications[0]["title"] == "CNC-04 incident"
        briefing = operational_v2.shift_briefing(
            db, TENANT_ID, PLANT_ID, "shift-b-2026-08-12", "start")
        assert briefing["status"] == "published"
        assert len(briefing["priorities"]) == 3
        assert briefing["verified_by_user_id"] == "usr-plant-001"
    finally:
        db.rollback()
        db.close()


def test_setup_edge_and_multi_plant_projections_preserve_context_boundaries():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        setup = operational_v2.setup_workspace(db, TENANT_ID, PLANT_ID)
        assert setup["completed_stages"] == ["plant", "data", "use_case"]
        assert setup["primary_use_case"] == "production_loss"
        edge = operational_v2.edge_workspace(db, TENANT_ID, PLANT_ID)
        gateway = edge["gateways"][0]
        assert gateway["outbound_only"] is True
        assert {row["canonical_signal"] for row in gateway["mappings"]} == {
            "machine.state", "production.good_count"}
        assert gateway["sources"][0]["status"] == "healthy"
        corporate = operational_v2.multi_plant_workspace(
            db, TENANT_ID, datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
        assert len(corporate["plants"]) == 2
        nashik = next(row for row in corporate["plants"] if row["plant"]["name"] == "Nashik Plant")
        assert nashik["plan_attainment_forecast"] is None
        assert nashik["context"]["data_available"] is False
        assert "not simplistically ranked" in corporate["comparison_note"]
    finally:
        db.rollback()
        db.close()


def test_representative_edge_alarm_is_idempotent_and_creates_canonical_deviation():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        gateway = db.get(models.EdgeGateway, "edge-line3-01")
        asset = db.get(models.PlantAsset, "asset-cnc-04")
        args = dict(message_id="edge-alarm-9001", event_type="machine.alarm", asset=asset,
                    source_timestamp=datetime(2026, 8, 12, 10, 1, tzinfo=timezone.utc),
                    payload={"fault_code": "9001", "message": "Spindle overload",
                             "estimated_lost_units": 36}, payload_hash="deterministic-hash")
        first, created = operational_v2.ingest_edge_canonical(db, gateway, **args)
        db.flush()
        second, duplicate_created = operational_v2.ingest_edge_canonical(db, gateway, **args)
        assert created is True and duplicate_created is False and first.id == second.id
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="edge_machine_alarm", asset_id=asset.id).one()
        assert deviation.actual_state["fault_code"] == "9001"
        assert deviation.estimated_lost_units == 36
        assert db.query(models.AssetFaultEvent).filter_by(source_event_key="edge:edge-line3-01:edge-alarm-9001").count() == 1
        assert db.query(models.EventOutbox).filter_by(
            correlation_id="edge:edge-line3-01:edge-alarm-9001").count() == 1
    finally:
        db.rollback()
        db.close()


def test_named_v2_contract_exposes_timeline_evidence_value_and_confirmed_gigi_execution():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        user = db.get(models.User, "usr-plant-001")
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="production_behind_plan").one()
        timeline = operational_v2.deviation_timeline(db, deviation)
        evidence = operational_v2.deviation_evidence(db, deviation)
        values = operational_v2.value_summary(db, TENANT_ID, PLANT_ID)
        assert timeline[0]["type"] == "deviation.detected"
        assert any(row["type"] == "work_order" for row in evidence)
        assert values["total_estimated"] > 0
        prepared = operational_router.prepare_gigi_action(
            operational_router.PreparedActionRequest(
                action_type="acknowledge_deviation", target_id=deviation.id), db, user)
        executed = operational_router.execute_gigi_action(
            prepared["id"], operational_router.PreparedActionExecute(confirmed=True), db, user)
        assert executed["status"] == "executed"
        assert executed["result"]["status"] == "investigating"
        assert db.query(models.AuditEvent).filter_by(
            action="v2.gigi.prepared_action.execute", entity_id=deviation.id).count() == 1
        assert db.query(models.V2PreparedAction).filter_by(id=prepared["id"], status="executed").count() == 1
    finally:
        db.rollback()
        db.expunge_all()
        reset_workspace_database(db)
        db.commit()
        db.close()


def test_required_v2_openapi_contract_uses_named_action_commands_and_line_analysis_routes():
    from app.main import app

    paths = app.openapi()["paths"]
    for suffix in ("accept", "start", "wait", "complete", "evidence"):
        assert "post" in paths[f"/api/v2/actions/{{action_id}}/{suffix}"]
    assert "/api/v2/actions/{action_id}/{command}" not in paths
    assert "get" in paths["/api/v2/lines/{line_id}/timeline"]
    assert "get" in paths["/api/v2/lines/{line_id}/loss-tree"]


def test_deviation_causal_context_separates_observation_hypothesis_and_blocking_dependencies():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="downtime_exceeded_threshold").one()
        context = operational_v2.deviation_causal_context(db, deviation)
        assert context["chain"][0]["state"] == "observed"
        assert context["chain"][-1]["state"] == "estimated"
        assert context["hypotheses"][0]["confidence"] == "medium"
        assert context["confirmed_cause"] is None
        assert {row["status"] for row in context["dependencies"]} == {"open", "completed"}
        assert any(row["owner_role"] == "quality_inspector" for row in context["dependencies"])
    finally:
        db.rollback()
        db.close()


def test_operational_kpis_cover_all_documented_domains_with_backend_calculation():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        board = operational_v2.operational_kpis(
            db, TENANT_ID, PLANT_ID, "shift-b-2026-08-12",
            datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
        groups = {row["key"]: row for row in board["groups"]}
        assert {"production", "quality", "reliability", "materials", "execution", "value"} <= set(groups)
        metrics = {item["key"]: item for row in groups.values() for item in row["metrics"]}
        assert 0 < metrics["forecast_attainment"]["value"] < 2
        assert 0 <= metrics["fpy"]["value"] <= 1
        assert metrics["unplanned_downtime"]["value"] == 43
        assert metrics["readiness"]["unit"] == "ratio"
        assert metrics["estimated_loss"]["unit"] == "currency"
    finally:
        db.rollback()
        db.close()


def test_forecast_evaluation_reports_candidate_and_simple_baseline_without_overclaiming():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        result = operational_v2.forecast_evaluation(db, TENANT_ID, PLANT_ID)
        assert result["model"] == "recent_net_rate_v1"
        assert result["baseline"] == "line_standard_rate"
        assert result["sample_size"] >= 4
        assert result["metrics"]["mae"] >= 0
        assert result["metrics"]["baseline_mae"] >= 0
        assert result["status"] == "insufficient_data"
        assert result["limitations"]
        assert all("observed" in row and "candidate" in row and "baseline" in row for row in result["cases"])
    finally:
        db.rollback()
        db.close()


def test_detector_thresholds_and_ownership_are_governed_plant_configuration():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        rule = db.query(models.OperationalDetectorRule).filter_by(
            detector_key="rejection_rate_high").one()
        rule.parameters = {"maximum_rejection_rate": .10}
        rule.owner_role = "quality_inspector"
        event = db.get(models.ProductionQualityEvent, "quality-l2-001")
        # Seeded 6.1% rejection no longer breaches the governed 10% threshold.
        existing = db.query(models.OperationalDeviation).filter_by(
            detector_key="rejection_rate_high").one()
        existing.status = "cancelled"
        db.flush()
        assert operational_v2.evaluate_rejection_rate(db, event) is None
        rule.parameters = {"maximum_rejection_rate": .04}
        created = operational_v2.evaluate_rejection_rate(db, event)
        assert created is not None
        assert created.owner_role == "quality_inspector"
        assert created.expected_state["detector_rule_id"] == rule.id
    finally:
        db.rollback()
        db.close()


def test_role_command_center_changes_focus_without_changing_canonical_plant_truth():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        center = operational_v2.command_center(
            db, TENANT_ID, PLANT_ID, "shift-b-2026-08-12",
            datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
        quality = operational_v2.role_command_center(dict(center), "quality_inspector")
        maintenance = operational_v2.role_command_center(dict(center), "maintenance_technician")
        assert quality["pulse"] == maintenance["pulse"]
        assert quality["role_focus"]["question"] != maintenance["role_focus"]["question"]
        assert quality["role_focus"]["relevant_deviation_ids"] != maintenance["role_focus"]["relevant_deviation_ids"]
    finally:
        db.rollback()
        db.close()


def test_v2_worker_registry_and_reconciliation_cadences_match_contract():
    assert REQUIRED_TASKS.issubset(celery_app.tasks)
    schedules = celery_app.conf.beat_schedule
    assert schedules["v2-action-slas"]["schedule"] == 60.0
    assert schedules["v2-line-reconciliation"]["schedule"] == 300.0
    assert schedules["v2-material-readiness"]["schedule"] == 900.0
    for task in ("app.workers.reconcile_line_performance",
                 "app.workers.recompute_material_readiness",
                 "app.workers.recompute_v2_material_readiness",
                 "app.workers.evaluate_open_deviations",
                 "app.workers.evaluate_action_slas",
                 "app.workers.generate_shift_briefing",
                 "app.workers.generate_shift_handover",
                 "app.workers.calculate_value_entries",
                 "app.workers.index_knowledge_document",
                 "app.workers.run_agent"):
        assert task in celery_app.tasks


def test_knowledge_index_worker_rebuilds_chunks_idempotently():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        document = db.get(models.KnowledgeDocument, "knowledge-cnc04-bearing-r2")
        assert document is not None
        document_id = document.id
        db.query(models.KnowledgeChunk).filter_by(
            knowledge_document_id=document_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    first = index_knowledge_document.run(document_id)
    second = index_knowledge_document.run(document_id)
    verify: Session = SessionLocal()
    try:
        rows = verify.query(models.KnowledgeChunk).filter_by(
            knowledge_document_id=document_id).order_by(models.KnowledgeChunk.chunk_index).all()
        assert first == second == len(rows) > 0
        assert [row.chunk_index for row in rows] == list(range(len(rows)))
        assert all(row.content and row.token_count > 0 for row in rows)
    finally:
        verify.close()


def test_value_worker_reconciles_estimate_without_rewriting_verified_recovery():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="production_behind_plan").first()
        assert deviation is not None
        deviation.estimated_financial_impact = 12345.67
        verified = models.OperationalValueEntry(
            tenant_id=deviation.tenant_id, plant_id=deviation.plant_id,
            deviation_id=deviation.id, value_type="lost_output",
            confidence_state="verified", amount=4321,
            calculation_method="human_verified_recovery",
            calculation_inputs={"source": "supervisor"})
        db.add(verified)
        db.flush()
        deviation_id, verified_id = deviation.id, verified.id
        db.commit()
    finally:
        db.close()

    assert calculate_value_entries.run(deviation_id) > 0
    verify: Session = SessionLocal()
    try:
        estimated = verify.query(models.OperationalValueEntry).filter_by(
            deviation_id=deviation_id, confidence_state="estimated").all()
        assert estimated and all(float(row.amount) == 12345.67 for row in estimated)
        assert all(row.calculation_inputs["detector_key"] == "production_behind_plan"
                   for row in estimated)
        assert float(verify.get(models.OperationalValueEntry, verified_id).amount) == 4321
    finally:
        verify.close()


def test_plant_knowledge_prefers_active_approved_revision_with_visible_citation():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        user = db.get(models.User, "usr-plant-001")
        payload = operational_v2.knowledge_workspace(
            db, user, query="fault 701 BR-28", asset_id="asset-cnc-04",
            at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
        assert len(payload["results"]) == 1
        result = payload["results"][0]
        assert result["document"]["revision"] == "R2"
        assert "BR-28" in result["match"]["excerpt"]
        assert result["match"]["page"] == "p. 14"
        assert result["match"]["section"] == "4.2 Fault 701 recovery"
        assert payload["excluded_revisions"][0]["revision"] == "R1"
        assert "excluded" in payload["excluded_revisions"][0]["warning"].lower()
    finally:
        db.rollback()
        db.close()


def test_shift_handover_requires_editable_draft_verification_before_publication():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.commit()
        user = db.get(models.User, "usr-plant-001")
        generated = operational_router.generate_handover("shift-b-2026-08-12", db, user)
        assert generated["status"] == "draft"
        assert generated["carry_over"]
        edited = operational_router.update_handover(
            "shift-b-2026-08-12",
            operational_router.ShiftHandoverUpdate(
                summary="Line 3 recovery continues on the next shift; BR-28 is available.",
                priorities=generated["priorities"], losses=generated["losses"],
                carry_over=generated["carry_over"]), db, user)
        assert "BR-28" in edited["summary"]
        verified = operational_router.verify_handover("shift-b-2026-08-12", db, user)
        assert verified["status"] == "verified"
        assert verified["verified_by_user_id"] == user.id
        published = operational_router.publish_handover("shift-b-2026-08-12", db, user)
        assert published["status"] == "published"
        assert published["published_at"]
        assert db.query(models.AuditEvent).filter(
            models.AuditEvent.action.like("v2.shift_handover.%")).count() == 4
        assert db.query(models.EventOutbox).filter_by(
            event_type="shift.handover.published").count() == 1
    finally:
        db.rollback()
        db.expunge_all()
        reset_workspace_database(db)
        db.commit()
        db.close()


def test_spc_breach_and_ncr_capa_require_effectiveness_verification_before_closure():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.commit()
        user = db.get(models.User, "usr-plant-001")
        workspace = operational_v2.quality_workspace(db, TENANT_ID, PLANT_ID)
        assert workspace["spc_signals"][0]["state"] == "breached"
        assert {row["case_type"] for row in workspace["recovery_cases"]} == {"ncr", "capa"}
        spc = db.get(models.ProductionQualityEvent, "quality-spc-l2-001")
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="spc_control_limit_breached").one()
        created = operational_router.create_quality_case(
            operational_router.QualityCaseCreate(
                case_type="ncr", quality_event_id=spc.id, deviation_id=deviation.id,
                title="Verify SPC recovery", severity="high",
                problem_statement="A governed test NCR needs effectiveness evidence."), db, user)
        case_id, version = created["id"], created["version"]
        for status in ("investigating", "action_in_progress", "effectiveness_review"):
            updated = operational_router.update_quality_case(
                case_id, operational_router.QualityCaseUpdate(
                    version=version, status=status,
                    containment_summary="Affected material is isolated.",
                    root_cause="Offset verification was omitted after tool replacement.",
                    corrective_action="Require an independently witnessed offset check.",
                    effectiveness_criteria="Three stable samples inside the control limits.",
                    effectiveness_result="Three consecutive samples remained stable.",
                    evidence=[{"type": "sample_series", "reference": "SPC-TEST-3"}]), db, user)
            version = updated["version"]
        verified = operational_router.verify_quality_case(
            case_id, operational_router.QualityCaseVerify(
                version=version, effectiveness_result="Three consecutive samples passed."), db, user)
        assert verified["status"] == "verified"
        closed = operational_router.close_quality_case(
            case_id, operational_router.QualityCaseVerify(
                version=verified["version"], effectiveness_result="Closure approved."), db, user)
        assert closed["status"] == "closed" and closed["closed_at"]
        assert db.query(models.AuditEvent).filter(
            models.AuditEvent.action.like("v2.quality_case.%"),
            models.AuditEvent.entity_id == case_id).count() == 6
        assert db.query(models.EventOutbox).filter_by(
            aggregate_type="quality_recovery_case", aggregate_id=case_id).count() == 6
    finally:
        db.rollback()
        db.expunge_all()
        reset_workspace_database(db)
        db.commit()
        db.close()


def test_multi_plant_standard_kpis_and_practice_transfer_preserve_local_validation():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.commit()
        user = db.get(models.User, "usr-plant-001")
        workspace = operational_v2.multi_plant_workspace(
            db, TENANT_ID, datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
        assert {row["key"] for row in workspace["standard_kpis"]} == {
            "plan_attainment_forecast", "addressable_loss_value"}
        assert all(row["context_dimensions"] for row in workspace["standard_kpis"])
        assert workspace["briefing"]["limitations"]
        assert all(not row["cross_site_verified"] for row in workspace["systemic_losses"])
        transfer = workspace["practice_transfers"][0]
        assert transfer["applicability_context"]["requires_local_validation"] is True
        for status, outcome in (("accepted", {}), ("piloting", {}),
                                ("completed", {"repeat_faults_before": 3, "repeat_faults_after": 1,
                                               "window_days": 60})):
            transfer = operational_router.transition_practice_transfer(
                transfer["id"], operational_router.PracticeTransferUpdate(
                    version=transfer["version"], status=status, outcome=outcome), db, user)
        assert transfer["status"] == "completed"
        assert transfer["outcome"]["repeat_faults_after"] == 1
        assert db.query(models.AuditEvent).filter_by(
            action="v2.corporate.practice_transfer.transition",
            entity_id=transfer["id"]).count() == 3
        assert db.query(models.EventOutbox).filter_by(
            aggregate_type="best_practice_transfer", aggregate_id=transfer["id"]).count() == 3
    finally:
        db.rollback()
        db.expunge_all()
        reset_workspace_database(db)
        db.commit()
        db.close()


def test_v2_context_exposes_plant_locale_timezone_and_currency_contract():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        user = db.get(models.User, "usr-plant-001")
        context = operational_router.my_context(db, user)
        assert context["plant"] == {
            "id": PLANT_ID, "name": "Pune Plant", "timezone": "Asia/Kolkata",
            "currency": "INR", "locale": "en-IN",
        }
    finally:
        db.rollback()
        db.close()


def test_v2_role_matrix_redacts_financials_and_protects_admin_and_verification_actions():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.flush()
        inspector = db.get(models.User, "usr-quality-001")
        manager = db.get(models.User, "usr-plant-001")
        admin = db.get(models.User, "usr-admin-001")
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="spc_control_limit_breached").one()
        inspector_payload = operational_router.get_deviation(deviation.id, db, inspector)
        manager_payload = operational_router.get_deviation(deviation.id, db, manager)
        assert inspector_payload["financial_impact"] is None
        assert manager_payload["financial_impact"] is not None
        quality = operational_router.quality_workspace(db, inspector)
        assert quality["pulse"]["scrap_rework_impact"] is None
        assert all(row["value"] is None for row in quality["pareto"])
        with pytest.raises(HTTPException) as denied:
            operational_router.get_v2_setup(db, inspector)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as denied:
            operational_router.corporate_operations(None, db, inspector)
        assert denied.value.status_code == 403
        assert operational_router.get_v2_setup(db, admin)["plant"]["id"] == PLANT_ID
    finally:
        db.rollback()
        db.close()


def test_guided_setup_creates_and_edits_scoped_hierarchy_and_audits_rules():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.commit()
        admin = db.get(models.User, "usr-admin-001")
        area = operational_router.create_setup_area(
            operational_router.SetupAreaUpsert(name="Final Assembly", code="fass"), db, admin)
        updated_area = operational_router.update_setup_area(
            area["id"], operational_router.SetupAreaUpsert(
                name="Final Assembly North", code="FASS"), db, admin)
        line = operational_router.create_setup_line(
            operational_router.SetupLineUpsert(
                area_id=area["id"], name="Assembly 9", code="A9",
                standard_good_rate_per_minute=1.5, contribution_per_good_unit=120), db, admin)
        operational_router.update_setup_line(
            line["id"], operational_router.SetupLineUpsert(
                area_id=area["id"], name="Assembly 09", code="A9",
                standard_good_rate_per_minute=1.7, contribution_per_good_unit=125), db, admin)
        profile = operational_router.update_v2_setup(
            operational_router.SetupUpdate(
                activation_stage="use_case", primary_use_case="quality_recovery",
                enabled_data_domains=["production", "quality"],
                production_calendar={"timezone": "Asia/Kolkata"},
                kpi_targets={"rejection_rate": .03}, loss_categories=[], escalation_rules=[],
                value_formulas=[], action_policies=[], completed_stages=["plant", "data", "use_case"]),
            db, admin)
        assert updated_area["name"] == "Final Assembly North"
        assert next(row for row in profile["hierarchy"]["line_records"] if row["id"] == line["id"])[
            "standard_good_rate_per_minute"] == 1.7
        assert profile["primary_use_case"] == "quality_recovery"
        assert db.query(models.AuditEvent).filter(
            models.AuditEvent.action.like("v2.setup.%")).count() == 5
        assert db.query(models.EventOutbox).filter(
            models.EventOutbox.event_type.like("setup.%")).count() == 5
    finally:
        db.rollback()
        db.expunge_all()
        reset_workspace_database(db)
        db.commit()
        db.close()


def test_maintenance_recovery_lifecycle_clears_fault_downtime_and_enters_monitoring():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.commit()
        manager = db.get(models.User, "usr-plant-001")
        work = db.get(models.MaintenanceWorkRecord, "maint-cnc04-701")
        fault = db.get(models.AssetFaultEvent, work.fault_event_id)
        deviation = db.get(models.OperationalDeviation, work.deviation_id)
        work_order = db.get(models.ProductionWorkOrder, fault.work_order_id)
        downtime = models.ProductionDowntimeEvent(
            tenant_id=manager.tenant_id, plant_id=manager.plant_id,
            work_order_id=work_order.id, line_id=work_order.line_id, asset_id=work.asset_id,
            started_at=fault.occurred_at, category="unplanned", reason=fault.message)
        db.add(downtime)
        db.commit()
        assert work.status == "in_progress" and fault.cleared_at is None

        result = operational_router.complete_maintenance_work(
            work.id, operational_router.MaintenanceWorkTransition(
                version=work.version, note="Replaced BR-28, verified lubrication and completed guarded run."),
            db, manager)

        db.refresh(work); db.refresh(fault); db.refresh(deviation); db.refresh(downtime)
        assert work.status == "completed" and work.completed_at is not None
        assert fault.cleared_at is not None and downtime.ended_at is not None
        assert deviation.status == "monitoring"
        assert result["state"] == "available" and result["work"] == []
        assert db.query(models.EventOutbox).filter_by(
            aggregate_id=work.id, event_type="maintenance.work_completed").count() == 1
        assert db.query(models.AuditEvent).filter_by(
            entity_id=work.id, action="v2.maintenance.work_completed").count() == 1
    finally:
        db.rollback()
        db.close()


def test_v2_objective_agent_persists_context_tools_recommendation_and_is_idempotent():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.commit()
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="downtime_exceeded_threshold").one()
        trigger = {"tenant_id": TENANT_ID, "plant_id": PLANT_ID,
                   "deviation_id": deviation.id, "shift_id": deviation.shift_id,
                   "correlation_id": "test:reliability:701"}
        first = run_v2_objective_agent(db, "reliability", trigger)
        db.commit()
        second = run_v2_objective_agent(db, "reliability", trigger)
        db.commit()

        assert first.id == second.id and first.state == "completed"
        assert first.active_context["focus_entities"][0]["id"] == deviation.id
        assert first.mutation_count == 0 and first.read_tool_count == 5
        assert db.query(models.AgentToolCall).filter_by(run_id=first.id).count() == 5
        recommendation = db.query(models.AgentEvent).filter_by(
            run_id=first.id, event_type="recommendation").one()
        assert recommendation.payload["hypotheses"] == []
        assert recommendation.payload["evidence_refs"][0]["id"] == deviation.id
        assert db.query(models.EventOutbox).filter_by(
            aggregate_id=first.id, event_type="gigi.recommendation.created").count() == 1
    finally:
        db.rollback()
        db.close()


def test_v2_admin_can_create_audited_read_only_connector_from_catalog():
    db: Session = SessionLocal()
    try:
        reset_workspace_database(db)
        db.commit()
        admin = db.get(models.User, "usr-admin-001")
        catalog = operational_router.v2_integration_catalog(admin)
        generic = next(row for row in catalog if row["provider"] == "generic_rest")
        created = operational_router.create_v2_integration(
            operational_router.V2IntegrationCreate(
                provider="generic_rest", name="Production REST read model", mode="read_only",
                secret_ref="vault://genuinegigs/production-rest",
                enabled_capabilities=["read_production_plan", "read_production_actual"]), db, admin)
        assert created["writes_enabled"] is False
        assert set(created["enabled_capabilities"]) <= set(generic["tested_capabilities"])
        assert db.query(models.AuditEvent).filter_by(
            entity_id=created["id"], action="v2.setup.integration.created").count() == 1
        assert db.query(models.EventOutbox).filter_by(
            aggregate_id=created["id"], event_type="setup.integration.created").count() == 1
    finally:
        db.rollback()
        db.close()
