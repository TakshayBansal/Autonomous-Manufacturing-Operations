from itertools import count

import pytest
from fastapi.testclient import TestClient

from app.db import models as core_models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.main import app
from app.scm import models as scm_models
from app.scm.acceptance_fixture import load_acceptance_dataset
from app.scm.planning import normalize_buckets


request_ids = count(1)


@pytest.fixture(autouse=True)
def reset_workspace():
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def login(email: str):
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": "Password@123"})
    assert response.status_code == 200
    return client, response.json()["csrf_token"]


def headers(csrf: str):
    return {"x-csrf-token": csrf, "Idempotency-Key": f"scm-api-{next(request_ids)}"}


def test_acceptance_fixture_is_canonical_idempotent_and_precedence_ready():
    with SessionLocal() as db:
        user = db.query(core_models.User).filter_by(
            email="admin@genuinegigs.local").one()
        first = load_acceptance_dataset(db, user)
        second = load_acceptance_dataset(db, user)
        db.commit()
        assert first["canonical_product_id"] == second["canonical_product_id"]
        plan = db.get(scm_models.SCMDemandPlan, first["demand_plan_id"])
        buckets = db.query(scm_models.SCMDemandBucket).filter_by(demand_plan_id=plan.id).all()
        selected = normalize_buckets(buckets, ["CUSTOMER_ORDER", "WORK_ORDER", "PRODUCTION_PLAN", "INDENT", "FORECAST"])
        assert len(selected) == 1
        assert selected[0]["demand_type"] == "PRODUCTION_PLAN"
        assert len(selected[0]["suppressed_source_ids"]) == 1


def test_scm_is_authenticated_and_admin_only():
    anonymous = TestClient(app)
    assert anonymous.get("/scm/context").status_code == 401
    employee, _ = login("purchase.exec@genuinegigs.local")
    assert employee.get("/scm/context").status_code == 403
    admin, _ = login("admin@genuinegigs.local")
    assert admin.get("/scm/context").status_code == 200


def test_mock_dataset_runs_end_to_end_and_explains_shortage():
    admin, csrf = login("admin@genuinegigs.local")
    loaded = admin.post("/scm/mock-data/load", headers=headers(csrf))
    assert loaded.status_code == 200, loaded.text
    triggered = admin.post("/scm/planning-runs", headers=headers(csrf), json={})
    assert triggered.status_code == 202, triggered.text
    run = admin.get(f"/scm/planning-runs/{triggered.json()['id']}")
    assert run.status_code == 200
    assert run.json()["status"] == "COMPLETED"
    assert run.json()["summary"]["horizon_days"] == 210
    snapshot = admin.get(f"/scm/planning-runs/{triggered.json()['id']}/input-snapshot")
    assert snapshot.status_code == 200
    assert snapshot.json()["payload_hash"] == run.json()["summary"]["input_snapshot_hash"]
    assert len(snapshot.json()["payload"]["materials"]) == 6
    # Firm production demand wins over the overlapping forecast; it is not
    # added to it, and canonical BOM quantities are exploded into components.
    c100 = next(row for row in snapshot.json()["payload"]["materials"]
                if any(item.get("source_reference", "").endswith("PRODUCTION_PLAN") for item in row["demands"]))
    assert c100["canonical_material_id"]
    assert c100["demands"][0]["quantity"] == "120000.0"
    assert c100["demands"][0]["suppressed_source_ids"]
    tower = admin.get("/scm/control-tower")
    assert tower.status_code == 200
    assert tower.json()["kpis"]["materials"] == 6
    for days in (30, 90, 210, 365):
        horizon = admin.get(f"/scm/supply-horizon?days={days}")
        assert horizon.status_code == 200, horizon.text
        payload = horizon.json()
        assert payload["days"] == days
        assert payload["rows"]
        assert payload["horizon_start"] <= payload["horizon_end"]
        assert payload["summary"]["critical_materials"] >= 1
        row = next(item for item in payload["rows"] if item["material"]["code"] == "SCM-C100")
        assert row["segments"]
        assert row["segments"][0]["start_date"] == payload["horizon_start"]
        assert all(segment["state"] in {"HEALTHY", "WATCH", "CRITICAL", "EXCESS", "UNKNOWN"}
                   for segment in row["segments"])
        assert all(row["segments"][index]["end_date"] < row["segments"][index + 1]["start_date"]
                   for index in range(len(row["segments"]) - 1))
        assert row["coverage"]["on_order"] >= 0
        assert all(event["type"] in {"PO_RECEIPT", "CANCELLATION_DEADLINE", "INTERVENTION", "FORECAST_CHANGE"}
                   for event in row["events"])
    assert admin.get("/scm/supply-horizon?days=45").status_code == 422
    risk = next(row for row in tower.json()["risks"] if row["material"]["code"] == "SCM-C100")
    assert risk["severity"] in {"CRITICAL", "RED"}
    assert risk["explanation"]["planning_run_id"] == triggered.json()["id"]
    assert risk["recommendations"][0]["action_type"] == "PULL_IN"
    material = admin.get(f"/scm/materials/{risk['material']['id']}?granularity=weekly")
    assert material.status_code == 200
    assert material.json()["projection"]
    assert material.json()["pegs"]
    lifecycle = admin.get("/scm/risks")
    assert lifecycle.status_code == 200 and lifecycle.json()
    readiness = admin.get(f"/scm/planning-runs/{triggered.json()['id']}/product-readiness")
    assert readiness.status_code == 200
    assert readiness.json()[0]["status"] == "BLOCKED"
    changes = admin.get(f"/scm/planning-runs/{triggered.json()['id']}/changes")
    assert changes.status_code == 200 and changes.json()


def test_recommendation_decision_is_acknowledgement_not_erp_write():
    admin, csrf = login("admin@genuinegigs.local")
    admin.post("/scm/mock-data/load", headers=headers(csrf))
    admin.post("/scm/planning-runs", headers=headers(csrf), json={})
    recs = admin.get("/scm/recommendations").json()
    decision = admin.post(f"/scm/recommendations/{recs[0]['id']}/decision", headers=headers(csrf), json={"decision": "ACCEPTED", "reason": "Planner reviewed the source evidence"})
    assert decision.status_code == 200
    assert decision.json()["status"] == "ACCEPTED"


def test_manual_delivery_is_audited_idempotent_and_automatically_replanned(monkeypatch):
    from datetime import date, timedelta
    from app.workers import run_scm_planning
    monkeypatch.setattr(run_scm_planning, "apply_async", lambda *_, **__: None)
    admin, csrf = login("admin@genuinegigs.local")
    assert admin.post("/scm/mock-data/load", headers=headers(csrf)).status_code == 200
    material = next(row for row in admin.get("/scm/materials").json() if row["code"] == "SCM-C100")
    payload = {"entry_type": "EXPECTED_DELIVERY_CREATED", "material_id": material["id"],
        "supplier_id": None, "values": {"quantity": 500000, "delivery_date": (date.today() + timedelta(days=10)).isoformat(), "uom": "EA"},
        "reason": "Supplier confirmed an additional delivery", "evidence": []}
    idem = {"x-csrf-token": csrf, "Idempotency-Key": "manual-delivery-test-001"}
    created = admin.post("/scm/data-entries", headers=idem, json=payload)
    assert created.status_code == 202, created.text
    assert created.json()["entry"]["status"] == "ACTIVE"
    assert created.json()["entry"]["correlation_id"]
    assert created.json()["planning_run"]["trigger_type"] == "MANUAL_CHANGE"
    replay = admin.post("/scm/data-entries", headers=idem, json=payload)
    assert replay.status_code == 202
    # The HTTP middleware replays the original response verbatim. Its header
    # identifies transport replay; the body flag describes service-level replay.
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert replay.json()["entry"]["id"] == created.json()["entry"]["id"]
    rows = admin.get(f"/scm/data-entries?material_id={material['id']}").json()
    assert len(rows) == 1
    snapshot = admin.get(f"/scm/planning-runs/{created.json()['planning_run']['id']}/input-snapshot").json()
    planned = next(row for row in snapshot["payload"]["materials"] if row["material_id"] == material["id"])
    assert any(item["event_type"] == "MANUAL_EXPECTED_DELIVERY" for item in planned["supplies"])


def test_manual_data_validates_uom_and_does_not_silently_change_inventory(monkeypatch):
    from app.workers import run_scm_planning
    monkeypatch.setattr(run_scm_planning, "apply_async", lambda *_, **__: None)
    admin, csrf = login("admin@genuinegigs.local")
    admin.post("/scm/mock-data/load", headers=headers(csrf))
    material = admin.get("/scm/materials").json()[0]
    result = admin.post("/scm/data-entries", headers=headers(csrf), json={
        "entry_type": "INVENTORY_CORRECTION_RECORDED", "material_id": material["id"],
        "values": {"available_qty": 10, "on_hand_qty": 10, "uom": "KG"},
        "reason": "Cycle count correction", "evidence": []})
    assert result.status_code == 422
    assert "UOM" in result.json()["detail"]
    assert admin.get(f"/scm/data-entries?material_id={material['id']}").json() == []
