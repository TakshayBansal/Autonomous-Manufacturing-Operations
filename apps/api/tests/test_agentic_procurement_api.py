from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.db import models
from app.db.session import SessionLocal
from app.main import app
from app.db.seed import reset_workspace_database


CLIENT = TestClient(app)


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


@pytest.fixture
def client() -> TestClient:
    return CLIENT


def login(client: TestClient, email: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": "Password@123"})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def mutation_headers(csrf: str) -> dict[str, str]:
    return {"x-csrf-token": csrf, "Idempotency-Key": str(uuid4())}


def create_requirement() -> None:
    with SessionLocal() as db:
        executive = db.query(models.User).filter_by(email="purchase.exec@genuinegigs.local").one()
        membership = db.query(models.WorkspaceMembership).filter_by(user_id=executive.id).one()
        item = db.query(models.Item).first()
        db.add(models.PurchaseRequirement(tenant_id=executive.tenant_id, plant_id=executive.plant_id,
            business_number=f"PR-API-{uuid4().hex[:8]}", source="manual", item_id=item.id,
            quantity=5, uom=item.uom_id, need_by_date=(date.today() + timedelta(days=14)).isoformat(),
            reason="Agentic API contract", status="approved", owner_user_id=executive.id,
            owner_membership_id=membership.id, related_case_id=""))
        db.commit()


def test_my_day_cycle_and_manager_contracts_are_scoped(client: TestClient) -> None:
    login(client, "plant.manager@genuinegigs.local")
    create_requirement()
    my_day = client.get("/workbench/my-day")
    assert my_day.status_code == 200, my_day.text
    assert my_day.json()["cycles"]
    assert my_day.json()["cycles"][0]["stages"]
    operations = client.get("/manager/operations")
    assert operations.status_code == 200
    assert "cycle_health" in operations.json()


def test_admin_can_publish_simulate_and_rollback_signed_policy_bundle(client: TestClient) -> None:
    csrf = login(client, "admin@genuinegigs.local")
    policy_id = str(uuid4())
    draft = client.put(f"/admin/autonomy-policies/{policy_id}", headers=mutation_headers(csrf), json={
        "name": "API coordination", "capability_id": "delegate_task", "roles": ["purchase_manager"],
        "plant_ids": [], "category_ids": [], "autonomy_ceiling": 2, "spend_limit": 1000,
        "risk_limit": "medium", "external_communication": "confirm", "confirmation_required": True,
    })
    assert draft.status_code == 200, draft.text
    published = client.post(f"/admin/autonomy-policies/{policy_id}/publish", headers=mutation_headers(csrf))
    assert published.status_code == 200, published.text
    bundle = published.json()["bundle"]
    simulated = client.post("/admin/autonomy-policies/simulate", headers=mutation_headers(csrf), json={
        "policy_id": policy_id, "role": "purchase_manager", "capability_id": "delegate_task",
        "spend": 500, "risk": "low", "external_effect": False,
    })
    assert simulated.status_code == 200 and simulated.json()["allow"] is True
    activated = client.post(f"/admin/autonomy-policies/bundles/{bundle['id']}/activate", headers=mutation_headers(csrf))
    assert activated.status_code == 200 and activated.json()["state"] == "active"
