import pytest
from fastapi.testclient import TestClient

from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.main import app


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def login(email: str = "admin@genuinegigs.local") -> TestClient:
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": "Password@123"})
    assert response.status_code == 200
    return client


def test_unified_app_context_requires_one_authenticated_session() -> None:
    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/platform/app-context").status_code == 401

    client = login()
    response = client.get("/api/v1/platform/app-context")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workspace"]["id"]
    assert payload["plant"]["id"]
    assert payload["user"]["role"] == "admin"
    assert {item["key"] for item in payload["modules"] if item["enabled"]} == {
        "procurement", "scm", "operations", "platform"
    }
    assert all(item["default_route"].startswith("/") for item in payload["modules"])


def test_unified_home_is_tenant_scoped_and_cross_module() -> None:
    client = login()
    response = client.get("/api/v1/platform/home")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload["module_summaries"]) == {"procurement", "scm", "operations"}
    assert payload["module_summaries"]["procurement"]["href"] == "/procurement"
    assert payload["module_summaries"]["scm"]["href"] == "/scm"
    assert payload["module_summaries"]["operations"]["href"] == "/operations"
    assert isinstance(payload["attention"], list)
    assert payload["generated_at"]
