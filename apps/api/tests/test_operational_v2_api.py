from itertools import count

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.seed import reset_workspace_database
from app.db import models
from app.db.session import SessionLocal
from app.main import app


request_ids = count(1)


@pytest.fixture(autouse=True)
def reset_v2_api_workspace():
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def api_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def login(email: str) -> tuple[AsyncClient, str]:
    client = api_client()
    response = await client.post("/auth/login", json={"email": email, "password": "Password@123"})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def headers(csrf: str) -> dict[str, str]:
    return {"x-csrf-token": csrf, "Idempotency-Key": f"v2-api-{next(request_ids)}"}


async def test_v2_read_contract_requires_authentication_and_respects_role_authority():
    anonymous = api_client()
    assert (await anonymous.get("/api/v2/me/context")).status_code == 401

    employee, _ = await login("purchase.exec@genuinegigs.local")
    assert (await employee.get("/api/v2/me/context")).status_code == 200
    assert (await employee.get("/api/v2/setup")).status_code == 403
    assert (await employee.get("/api/v2/value/summary")).status_code == 403
    assert (await employee.get("/api/v2/corporate/operations")).status_code == 403

    manager, _ = await login("plant.manager@genuinegigs.local")
    assert (await manager.get("/api/v2/value/summary")).status_code == 200
    assert (await manager.get("/api/v2/corporate/operations?at=2026-08-12T10:00:00Z")).status_code == 200

    admin, _ = await login("admin@genuinegigs.local")
    assert (await admin.get("/api/v2/setup")).status_code == 200
    assert (await admin.get("/api/v2/edge")).status_code == 200


async def test_recovery_contract_is_scoped_redacted_and_creates_coordinated_actions():
    manager, csrf = await login("plant.manager@genuinegigs.local")
    cases = await manager.get("/api/v2/recovery-cases")
    assert cases.status_code == 200 and cases.json()
    case_id = cases.json()[0]["id"]
    detail = await manager.get(f"/api/v2/recovery-cases/{case_id}")
    assert detail.status_code == 200 and len(detail.json()["strategies"]) >= 2
    recommended = next(row for row in detail.json()["strategies"] if row["status"] == "recommended")
    selected = await manager.post(f"/api/v2/recovery-cases/{case_id}/select-strategy",
        headers=headers(csrf), json={"strategy_id":recommended["id"]})
    assert selected.status_code == 200, selected.text
    assert selected.json()["actions_created"] >= 1
    started = await manager.post(f"/api/v2/recovery-cases/{case_id}/start", headers=headers(csrf), json={})
    assert started.status_code == 200 and started.json()["status"] == "executing"

    quality, _ = await login("quality.inspector@genuinegigs.local")
    visible = await quality.get("/api/v2/recovery-cases")
    assert visible.status_code == 200
    assert all(row.get("business_exposure_amount") is None for row in visible.json())


async def test_recovery_url_access_denies_a_line_outside_operational_scope():
    client, _ = await login("quality.inspector@genuinegigs.local")
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(
            email="quality.inspector@genuinegigs.local").first()
        membership = db.query(models.WorkspaceMembership).filter_by(user_id=user.id).first()
        scope = db.query(models.OperationalScope).filter_by(membership_id=membership.id).first()
        if scope is None:
            scope = models.OperationalScope(tenant_id=user.tenant_id,membership_id=membership.id,
                plant_ids=[user.plant_id],line_ids=["line-that-is-not-part-of-the-case"],authorities=[])
            db.add(scope)
        else: scope.line_ids = ["line-that-is-not-part-of-the-case"]
        db.commit()
    all_cases = await client.get("/api/v2/recovery-cases")
    assert all_cases.status_code == 200 and all_cases.json() == []


async def test_v2_knowledge_acl_and_revision_guard_are_applied_at_api_boundary():
    manager, _ = await login("plant.manager@genuinegigs.local")
    result = await manager.get("/api/v2/knowledge/search", params={"q": "fault 701 BR-28"})
    assert result.status_code == 200
    assert result.json()["results"][0]["document"]["revision"] == "R2"
    assert result.json()["excluded_revisions"][0]["revision"] == "R1"

    quality, _ = await login("quality.inspector@genuinegigs.local")
    hidden = await quality.get("/api/v2/knowledge/search", params={"q": "fault 701"})
    assert hidden.status_code == 200
    assert hidden.json()["results"] == []


async def test_gigi_prepared_action_needs_csrf_confirmation_and_writes_audit():
    manager, csrf = await login("plant.manager@genuinegigs.local")
    deviations = (await manager.get("/api/v2/deviations")).json()
    target = next(row for row in deviations if row["detector_key"] == "production_behind_plan")
    prepared = await manager.post("/api/v2/gigi/prepare-action", headers=headers(csrf), json={
        "action_type": "acknowledge_deviation", "target_id": target["id"]})
    assert prepared.status_code == 201, prepared.text
    prepared_id = prepared.json()["id"]
    rejected = await manager.post(f"/api/v2/gigi/actions/{prepared_id}/execute",
                            headers=headers(csrf), json={"confirmed": False})
    assert rejected.status_code == 422
    executed = await manager.post(f"/api/v2/gigi/actions/{prepared_id}/execute",
                            headers=headers(csrf), json={"confirmed": True})
    assert executed.status_code == 200, executed.text
    assert executed.json()["result"]["status"] == "investigating"
    activity = (await manager.get("/api/v2/gigi/activity")).json()
    assert activity[0]["status"] == "executed"


async def test_edge_ingest_rejects_bad_identity_and_deduplicates_canonical_alarm():
    body = {"message_id": "api-edge-701", "event_type": "machine.alarm",
            "asset_id": "asset-cnc-04", "source_timestamp": "2026-08-12T10:01:00Z",
            "payload": {"fault_code": "API-701", "message": "Bearing alarm",
                        "estimated_lost_units": 22}}
    client = api_client()
    rejected = await client.post("/api/v2/edge/events", json=body, headers={
        "X-Edge-Identity": "wrong", "X-Config-Signature": "wrong",
        "Idempotency-Key": f"v2-api-{next(request_ids)}"})
    assert rejected.status_code == 401
    edge_headers = {"X-Edge-Identity": "seed-edge-line3-sha256",
                    "X-Config-Signature": "seed-config-v1-signature"}
    first = await client.post("/api/v2/edge/events", json=body,
                        headers={**edge_headers, "Idempotency-Key": f"v2-api-{next(request_ids)}"})
    second = await client.post("/api/v2/edge/events", json=body,
                         headers={**edge_headers, "Idempotency-Key": f"v2-api-{next(request_ids)}"})
    assert first.status_code == 202 and first.json()["status"] == "accepted"
    assert second.status_code == 202 and second.json()["status"] == "duplicate"
    manager, _ = await login("plant.manager@genuinegigs.local")
    created = [row for row in (await manager.get("/api/v2/deviations")).json()
               if row["detector_key"] == "edge_machine_alarm"]
    assert len(created) == 1


async def test_handover_api_enforces_generate_verify_publish_order():
    manager, csrf = await login("plant.manager@genuinegigs.local")
    generated = await manager.post("/api/v2/shifts/shift-b-2026-08-12/handover/generate",
                             headers=headers(csrf))
    assert generated.status_code == 201
    premature = await manager.post("/api/v2/shifts/shift-b-2026-08-12/handover/publish",
                             headers=headers(csrf))
    assert premature.status_code == 409
    verified = await manager.post("/api/v2/shifts/shift-b-2026-08-12/handover/verify",
                            headers=headers(csrf))
    assert verified.status_code == 200
    published = await manager.post("/api/v2/shifts/shift-b-2026-08-12/handover/publish",
                             headers=headers(csrf))
    assert published.status_code == 200
    assert published.json()["status"] == "published"
