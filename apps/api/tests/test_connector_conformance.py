import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api_schemas import ConnectionUpdateRequest
from app.connector_sdk import (
    CONNECTOR_REGISTRY, SYNC_JOB_CAPABILITIES, ConnectorContext, ConnectorMode, get_connector,
    run_conformance_report,
)
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.integrations import run_sync_job_by_id
from app.operations.normalization import normalize_results
from app.main import update_integration_connection


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


VERIFIED_REFERENCE_PROVIDERS = sorted(
    provider for provider, connector in CONNECTOR_REGISTRY.items() if connector.manifest.tested_capabilities
)


def test_every_v2_sync_dataset_is_declared_by_reference_connector_manifests() -> None:
    required = {capability for capabilities in SYNC_JOB_CAPABILITIES.values() for capability in capabilities}
    for provider in VERIFIED_REFERENCE_PROVIDERS:
        manifest = get_connector(provider).manifest
        assert required <= manifest.capabilities
        assert required <= manifest.tested_capabilities


def test_seeded_v2_connection_enables_only_manifest_capabilities() -> None:
    with SessionLocal() as db:
        connection = db.get(models.IntegrationConnection, "conn-v2-excel")
        assert connection is not None
        manifest = get_connector(connection.provider).manifest
        assert set(connection.enabled_capabilities) <= manifest.capabilities
        assert set(SYNC_JOB_CAPABILITIES["material_needs"]) <= set(connection.enabled_capabilities)


@pytest.mark.parametrize("provider", VERIFIED_REFERENCE_PROVIDERS)
def test_reference_connector_conformance(provider: str) -> None:
    connector = get_connector(provider)
    context = ConnectorContext(
        connection_id=f"conn-{provider}", tenant_id="tenant-a", plant_id="plant-a",
        mode=ConnectorMode.UAT,
        enabled_capabilities=connector.manifest.tested_capabilities,
        writes_enabled=True,
    )
    assert connector.test_connection(context)["status"] == "available"
    assert connector.pull(context, "read_materials")["has_more"] is False
    prepared = connector.prepare_write(
        context, "create_purchase_order_draft", "PO-EXT-1001",
        {"business_number": "PO-2026-1001", "amount": 12500}, "idem-po-1001",
    )
    assert connector.validate_write(context, prepared)["valid"] is True
    with pytest.raises(PermissionError, match="persisted approval"):
        connector.dispatch(context, prepared)
    prepared = connector.approve_write(context, prepared, "approval-record-1001")
    first = connector.dispatch(context, prepared)
    duplicate = connector.dispatch(context, prepared)
    assert first == duplicate
    assert first.status == "acknowledged"
    verified = connector.verify(context, prepared, first)
    assert verified.status == "reconciled"
    assert verified.payload_hash_matches is True


@pytest.mark.parametrize("provider", VERIFIED_REFERENCE_PROVIDERS)
def test_reference_connector_denies_disabled_unsupported_and_read_only_writes(provider: str) -> None:
    connector = get_connector(provider)
    disabled = ConnectorContext("c", "t", "p", ConnectorMode.DISCONNECTED, connector.manifest.tested_capabilities)
    assert connector.test_connection(disabled)["status"] == "disabled"
    with pytest.raises(RuntimeError, match="disabled"):
        connector.pull(disabled, "read_materials")

    read_only = ConnectorContext("c", "t", "p", ConnectorMode.READ_ONLY, connector.manifest.tested_capabilities)
    with pytest.raises(PermissionError, match="read-only"):
        connector.prepare_write(read_only, "create_purchase_order_draft", "PO-1", {}, "idem-1")
    with pytest.raises(PermissionError, match="not enabled"):
        connector.pull(read_only, "read_acknowledgements")
    assert connector.pull(read_only, "read_invoices")["records"] == []
    assert connector.pull(read_only, "read_payment_status")["records"] == []


@pytest.mark.parametrize("provider", VERIFIED_REFERENCE_PROVIDERS)
def test_reference_connector_detects_stale_external_versions(provider: str) -> None:
    connector = get_connector(provider)
    context = ConnectorContext("c", "t", "p", ConnectorMode.UAT, connector.manifest.tested_capabilities, True)
    first = connector.prepare_write(context, "create_purchase_order_draft", "PO-1", {"value": 1}, "idem-1")
    first = connector.approve_write(context, first, "approval-1")
    connector.dispatch(context, first)
    stale = connector.prepare_write(context, "create_purchase_order_draft", "PO-1", {"value": 2}, "idem-2", "0")
    result = connector.dispatch(context, stale)
    assert result.status == "conflict"
    assert result.error_code == "stale_external_version"


@pytest.mark.parametrize("provider", VERIFIED_REFERENCE_PROVIDERS)
def test_connector_recovers_ambiguous_commit_before_retry_and_classifies_failures(provider: str) -> None:
    connector = get_connector(provider)
    context = ConnectorContext("c", "t", "p", ConnectorMode.UAT, connector.manifest.tested_capabilities, True, "vault://connector")
    prepared = connector.prepare_write(context, "create_purchase_order_draft", "PO-AMB-1", {"value": 10}, "idem-amb-1")
    prepared = connector.approve_write(context, prepared, "approval-amb-1")
    connector.dispatch(context, prepared)
    recovered = connector.recover_ambiguous(context, prepared)
    assert recovered.status == "reconciled" and recovered.payload_hash_matches is True
    assert recovered.evidence["retry_safe"] is False
    assert connector.classify_error(TimeoutError())["retryable"] is True
    assert connector.classify_error(ValueError("bad payload"))["retryable"] is False
    report = connector.capability_report(context)
    assert report["secret_configured"] is True
    assert report["secret_reference"] == "configured"
    assert "vault://connector" not in str(report)


def test_emergency_write_disable_blocks_production_without_affecting_reads() -> None:
    connector = get_connector("generic_rest")
    context = ConnectorContext("c", "t", "p", ConnectorMode.PRODUCTION_WRITE, connector.manifest.tested_capabilities, False)
    assert connector.pull(context, "read_materials")["records"] == []
    with pytest.raises(PermissionError, match="Emergency write disable"):
        connector.prepare_write(context, "create_purchase_order_draft", "PO-1", {}, "idem-1")


def test_connection_write_enable_requires_explicit_acceptance_and_remains_emergency_disableable() -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        connector = get_connector("generic_rest")
        connection = models.IntegrationConnection(
            tenant_id=user.tenant_id, plant_id=user.plant_id, provider="generic_rest",
            provider_version=connector.manifest.adapter_version, name="Controlled UAT",
            mode="read_only", status="configured", capabilities=sorted(connector.manifest.capabilities),
            enabled_capabilities=sorted(connector.manifest.tested_capabilities), writes_enabled=False,
        )
        db.add(connection); db.flush()

        def request() -> Request:
            return Request({"type": "http", "method": "PATCH", "path": "/", "headers": [(b"if-match", str(connection.version).encode())]})

        with pytest.raises(HTTPException) as denied:
            update_integration_connection(connection.id, ConnectionUpdateRequest(mode="uat", writes_enabled=True), request(), db, user)
        assert denied.value.status_code == 422
        db.rollback()
        connection = db.query(models.IntegrationConnection).filter_by(name="Controlled UAT").one_or_none()
        if connection is None:
            db.add(models.IntegrationConnection(
                id="controlled-uat", tenant_id=user.tenant_id, plant_id=user.plant_id,
                provider="generic_rest", provider_version=connector.manifest.adapter_version,
                name="Controlled UAT", mode="read_only", status="configured",
                capabilities=sorted(connector.manifest.capabilities),
                enabled_capabilities=sorted(connector.manifest.tested_capabilities), writes_enabled=False,
            )); db.flush(); connection = db.get(models.IntegrationConnection, "controlled-uat")
        enabled = update_integration_connection(connection.id, ConnectionUpdateRequest(
            mode="uat", writes_enabled=True, write_enable_confirmation="ENABLE_EXTERNAL_WRITES",
            acceptance_reference="UAT-ACCEPTANCE-2026-07",
        ), request(), db, user)
        assert enabled.writes_enabled is True
        assert enabled.config["write_acceptance"]["reference"] == "UAT-ACCEPTANCE-2026-07"
        disabled = update_integration_connection(enabled.id, ConnectionUpdateRequest(writes_enabled=False), request(), db, user)
        assert disabled.writes_enabled is False


def test_generated_acceptance_report_executes_every_safety_check() -> None:
    report = run_conformance_report()
    assert report["status"] == "passed"
    assert {row["provider"] for row in report["adapters"]} == set(CONNECTOR_REGISTRY)
    for adapter in report["adapters"]:
        if adapter["tested_capabilities"]:
            assert adapter["passed"] is True
            assert all(adapter["checks"].values())
        else:
            assert adapter["passed"] is None
            assert adapter["status"] == "customer_validation_required"
        assert adapter["live_customer_verified"] is False
    assert "customer credentials" in report["claim_boundary"]


def test_persisted_sync_job_uses_connector_manifest_and_records_cursor_summary() -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        connector = get_connector("generic_rest")
        connection = models.IntegrationConnection(
            tenant_id=user.tenant_id, plant_id=user.plant_id, provider="generic_rest",
            provider_version=connector.manifest.adapter_version, name="Conformance REST",
            mode="read_only", status="configured", capabilities=sorted(connector.manifest.capabilities),
            enabled_capabilities=sorted(connector.manifest.tested_capabilities), writes_enabled=False,
        )
        db.add(connection); db.flush()
        job = models.IntegrationSyncJob(
            tenant_id=user.tenant_id, plant_id=user.plant_id, connection_id=connection.id,
            job_type="master_data", status="queued", summary={},
        )
        db.add(job); db.commit(); job_id = job.id
    status = run_sync_job_by_id(job_id)
    with SessionLocal() as check_db:
        assert status == "completed", check_db.get(models.IntegrationSyncJob, job_id).error
    with SessionLocal() as db:
        persisted = db.get(models.IntegrationSyncJob, job_id)
        assert persisted is not None
        assert persisted.summary["provider"] == "generic_rest"
        assert persisted.summary["counts"] == {"received": 0, "applied": 0, "duplicates": 0, "errors": 0}
        assert persisted.summary["source_counts"] == {"read_materials": 0, "read_suppliers": 0}
        assert set(persisted.summary["cursors"]) == {"read_materials", "read_suppliers"}


def test_v2_connector_records_normalize_to_canonical_data_once_with_lineage() -> None:
    with SessionLocal() as db:
        connection = db.get(models.IntegrationConnection, "conn-v2-excel")
        job = models.IntegrationSyncJob(
            tenant_id=connection.tenant_id, plant_id=connection.plant_id,
            connection_id=connection.id, job_type="production_actual", status="running", summary={})
        db.add(job); db.flush()
        before = db.query(models.ProductionActualPoint).count()
        result = {"read_production_actual": {"records": [{
            "id": "erp-count-wo482-1100", "work_order_id": "WO-482",
            "recorded_at": "2026-08-12T11:00:00Z", "good_quantity": 44,
            "reject_quantity": 2}], "cursor": "actual:1100", "has_more": False}}

        first = normalize_results(db, job, connection, result)
        db.commit()
        second = normalize_results(db, job, connection, result)
        db.commit()

        assert first["counts"] == {"received": 1, "applied": 1, "duplicates": 0, "errors": 0}
        assert second["counts"] == {"received": 1, "applied": 0, "duplicates": 1, "errors": 0}
        assert db.query(models.ProductionActualPoint).count() == before + 1
        receipt = db.query(models.IntegrationIngestionRecord).filter_by(
            connection_id=connection.id, source_record_key="erp-count-wo482-1100").one()
        assert receipt.target_entity_type == "production_actual_points"
        assert receipt.source_cursor == "actual:1100"


@pytest.mark.parametrize(("capability", "record", "target_table"), [
    ("read_production_plan", {"id": "plan-ext-1", "work_order_id": "WO-481", "recorded_at": "2026-08-12T11:01:00Z", "cumulative_quantity": 610}, "production_plan_points"),
    ("read_downtime", {"id": "down-ext-1", "work_order_id": "WO-481", "line_id": "line-l1", "started_at": "2026-08-12T11:02:00Z", "ended_at": "2026-08-12T11:08:00Z", "category": "changeover", "planned": True}, "production_downtime_events"),
    ("read_inventory", {"id": "inv-ext-1", "material_code": "RM-EXT-1", "on_hand_quantity": 120, "reserved_for_other_orders": 20, "quality_hold_quantity": 5, "observed_at": "2026-08-12T11:03:00Z"}, "material_inventory_positions"),
    ("read_supplier_commitments", {"id": "commit-ext-1", "work_order_id": "WO-481", "material_code": "RM-EXT-1", "committed_quantity": 80, "committed_delivery_at": "2026-08-12T12:00:00Z", "acknowledged": True}, "production_supplier_commitments"),
    ("read_inspections", {"id": "quality-ext-1", "work_order_id": "WO-481", "line_id": "line-l1", "occurred_at": "2026-08-12T11:04:00Z", "inspected_quantity": 50, "rejected_quantity": 2, "event_type": "inspection", "defect_code": "BURR"}, "production_quality_events"),
    ("read_machine_events", {"id": "fault-ext-1", "asset_id": "CNC-04", "work_order_id": "wo-v2-l3", "occurred_at": "2026-08-12T11:05:00Z", "event_type": "machine.alarm", "fault_code": "901", "message": "Temperature alarm"}, "asset_fault_events"),
    ("read_maintenance_work", {"id": "maint-ext-1", "asset_id": "CNC-04", "title": "Inspect spindle temperature", "status": "open", "external_reference": "CMMS-EXT-901"}, "maintenance_work_records"),
])
def test_each_operational_connector_capability_has_a_canonical_normalizer(
        capability: str, record: dict, target_table: str) -> None:
    with SessionLocal() as db:
        connection = db.get(models.IntegrationConnection, "conn-v2-excel")
        job = models.IntegrationSyncJob(tenant_id=connection.tenant_id, plant_id=connection.plant_id,
            connection_id=connection.id, job_type="capability_test", status="running", summary={})
        db.add(job); db.flush()
        outcome = normalize_results(db, job, connection, {
            capability: {"records": [record], "cursor": f"{capability}:1", "has_more": False}})
        db.commit()
        assert outcome["counts"]["applied"] == 1, outcome
        receipt = db.query(models.IntegrationIngestionRecord).filter_by(
            connection_id=connection.id, capability=capability,
            source_record_key=record["id"]).one()
        assert receipt.target_entity_type == target_table


def test_sync_runtime_persists_records_and_reconciles_operational_deviation(monkeypatch) -> None:
    connector = get_connector("excel_csv")
    monkeypatch.setattr(type(connector), "pull", lambda self, context, capability, cursor=None: {
        "records": [{"id": "sync-actual-l1-1130", "work_order_id": "WO-481",
                     "recorded_at": "2026-08-12T11:30:00Z", "good_quantity": 430,
                     "reject_quantity": 1}], "cursor": "actual:1130", "has_more": False})
    with SessionLocal() as db:
        connection = db.get(models.IntegrationConnection, "conn-v2-excel")
        connection.enabled_capabilities = sorted(set(connection.enabled_capabilities) | {"read_production_actual"})
        job = models.IntegrationSyncJob(tenant_id=connection.tenant_id, plant_id=connection.plant_id,
            connection_id=connection.id, job_type="production_actual", status="queued", summary={})
        db.add(job); db.commit(); job_id = job.id

    status = run_sync_job_by_id(job_id)
    with SessionLocal() as check_db:
        assert status == "completed", check_db.get(models.IntegrationSyncJob, job_id).error
    with SessionLocal() as db:
        job = db.get(models.IntegrationSyncJob, job_id)
        assert job.summary["counts"]["applied"] == 1, job.summary
        assert job.summary["targets"] == {"production_actual_points": 1}
        assert db.query(models.IntegrationIngestionRecord).filter_by(
            source_record_key="sync-actual-l1-1130").count() == 1
        deviation = db.query(models.OperationalDeviation).filter_by(
            detector_key="production_behind_plan", work_order_id="wo-v2-l1").one()
        assert deviation.actual_state["actual_now"] == 430


@pytest.mark.parametrize("provider", ["oracle_fusion", "sap_s4hana", "dynamics_365", "odoo"])
def test_vendor_contract_boundaries_expose_no_unverified_capability(provider: str) -> None:
    connector = get_connector(provider)
    assert connector.manifest.capabilities
    assert connector.manifest.tested_capabilities == frozenset()
    context = ConnectorContext(f"c-{provider}", "t", "p", ConnectorMode.READ_ONLY, frozenset())
    assert connector.test_connection(context)["status"] == "customer_validation_required"
    with pytest.raises(PermissionError, match="not enabled"):
        connector.pull(context, "read_materials")
