import pytest
from fastapi import HTTPException

from app.db.seed_v2_simulation import seed_northstar
from app.db.session import SessionLocal
from app.routers import devtools


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("DEVELOPER_LAB_ENABLED","true")
    monkeypatch.setenv("DEVELOPER_LAB_TOKEN","lab-test-token")
    session=SessionLocal(); seed_northstar(session,reset=True); session.commit()
    try: yield session
    finally: session.close()


def test_observatory_guard_requires_explicit_feature_and_token(monkeypatch):
    monkeypatch.setenv("APP_ENV","production")
    monkeypatch.setenv("DEVELOPER_LAB_ENABLED","false")
    with pytest.raises(HTTPException) as disabled: devtools.developer_guard("lab-test-token")
    assert disabled.value.status_code==404
    monkeypatch.setenv("DEVELOPER_LAB_ENABLED","true")
    with pytest.raises(HTTPException) as denied: devtools.developer_guard("wrong")
    assert denied.value.status_code==401
    devtools.developer_guard("northstar-developer-local")


def test_state_graph_connector_and_service_contracts_are_structured(db):
    service_payload=devtools.services(db)
    assert any(row["id"]=="factory-lab" for row in service_payload["services"])
    graph_payload=devtools.graph(db=db)
    assert graph_payload["nodes"] and graph_payload["edges"]
    connector_payload=devtools.connectors(db)
    assert any(row["provider"]=="factory_simulator" for row in connector_payload["connectors"])
    canonical_payload=devtools.canonical("work_orders",db=db)
    assert canonical_payload["records"]


def test_assertion_evaluation_remains_a_developer_only_oracle(db):
    response=devtools.evaluate_assertions({
        "assertions":[{"id":"S01-A01","category":"ingestion","description":"source records accepted"}]},db)
    update=response["updates"][0]
    assert update["details"]["lab_only"] is True
    assert update["status"] in {"passed","waiting"}
