import pytest
from fastapi.testclient import TestClient
from itertools import count

from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.domains.workflows import calculate_landed_cost
from app.domains.workflows import compare_quotes as compare_quotes_with_db
from app.domains.workflows import run_agent_action as run_agent_action_with_db
from app.main import app
from app.models import AgentActionRequest

client = TestClient(app)
request_ids = count(1)


def compare_quotes(rfq_id: str):
    with SessionLocal() as db:
        return compare_quotes_with_db(db, rfq_id)


def run_agent_action(request: AgentActionRequest):
    with SessionLocal() as db:
        response = run_agent_action_with_db(db, request)
        db.commit()
        return response


def mutation_headers(csrf: str | None = None, version: int | None = None) -> dict[str, str]:
    headers = {"Idempotency-Key": f"test-{next(request_ids)}"}
    if csrf:
        headers["x-csrf-token"] = csrf
    if version is not None:
        headers["If-Match"] = str(version)
    return headers

@pytest.fixture(autouse=True)
def reset_workspace_between_tests() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()



def login(email: str = "plant.manager@genuinegigs.local") -> tuple[TestClient, str]:
    local = TestClient(app)
    response = local.post("/auth/login", json={"email": email, "password": "Password@123"})
    assert response.status_code == 200, response.text
    return local, response.json()["csrf_token"]


def test_health_reports_simulated_external_actions() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["external_actions"] == "simulation"
    assert response.json()["email_actions"] == "simulation"


def test_login_returns_user_and_csrf_token() -> None:
    local, csrf = login("purchase.exec@genuinegigs.local")
    assert csrf
    me = local.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "purchase_executive"


def test_control_tower_snapshot_has_guarded_agent_actions() -> None:
    local, _csrf = login()
    response = local.get("/procurement/control-tower")
    assert response.status_code == 200
    payload = response.json()
    recommendation = payload["recommendation"]
    assert payload["erp_mode"] == "simulated"
    assert payload["ai_disabled_ready"] is True
    assert recommendation["requires_human_approval"] is True
    assert "post_po_to_erp" in recommendation["blocked_actions"]
    assert "update_inventory" in recommendation["blocked_actions"]


def test_landed_cost_includes_freight_and_packaging() -> None:
    local, _csrf = login("purchase.exec@genuinegigs.local")
    line = local.get("/procurement/quotes").json()[0]["lines"][0]

    class Line:
        quantity = line["quantity"]
        unit_price = line["unit_price"]
        freight = line["freight"]
        packaging = line["packaging"]

    unit, total = calculate_landed_cost(Line)
    assert unit == 126.7
    assert total == 190050


def test_comparison_recommends_non_disqualified_supplier() -> None:
    scores = compare_quotes("RFQ-2026-0031")
    assert scores[0].supplier_name == "Apex Alloy Works"
    assert scores[0].disqualified is False
    assert any(score.supplier_name == "Bharat Metals" and score.disqualified for score in scores)
    assert any(score.supplier_name == "Crown Industrial Supply" and score.disqualified for score in scores)


def test_agent_cannot_approve_award() -> None:
    response = run_agent_action(AgentActionRequest(agent_id="agt-purchase-exec", action="approve_award", context_id="AWARD-2026-004"))
    assert response.allowed is False
    assert "blocked" in response.result.lower()


def test_agent_can_create_follow_up_task() -> None:
    response = run_agent_action(AgentActionRequest(agent_id="agt-purchase-exec", action="create_follow_up_task", context_id="CASE-2026-0142"))
    assert response.allowed is True
    assert response.created_task_id is not None




def test_outbox_endpoint_accepts_approved_pending_send_status() -> None:
    local, _csrf = login("purchase.manager@genuinegigs.local")
    response = local.get("/integrations/outbox")
    assert response.status_code == 200, response.text
    statuses = {item["status"] for item in response.json()}
    assert "approved_pending_send" in statuses



def test_workspace_overview_is_role_specific() -> None:
    purchase_exec, _csrf = login("purchase.exec@genuinegigs.local")
    exec_payload = purchase_exec.get("/workspace/overview")
    assert exec_payload.status_code == 200, exec_payload.text
    exec_overview = exec_payload.json()
    exec_nav = {item["key"] for item in exec_overview["nav_items"]}
    assert "procurement" in exec_nav
    assert "rfq" in exec_nav
    assert "quotes" not in exec_nav
    assert "comparison" in exec_nav
    assert any(action["entity_type"] == "cases" for action in exec_overview["next_actions"])

    purchase_manager, _csrf = login("purchase.manager@genuinegigs.local")
    manager_payload = purchase_manager.get("/workspace/overview")
    assert manager_payload.status_code == 200, manager_payload.text
    manager_overview = manager_payload.json()
    manager_nav = {item["key"] for item in manager_overview["nav_items"]}
    assert "comparison" in manager_nav
    assert "po" in manager_nav
    assert "procurement" not in manager_nav
    assert "quotes" in manager_nav
    assert {"evidence", "negotiations", "invoices", "cases"}.issubset(manager_nav)
    assert any(action["entity_type"] in {"supplier_quotes", "award_decisions"} for action in manager_overview["next_actions"])

    plant, _csrf = login("plant.manager@genuinegigs.local")
    plant_overview = plant.get("/workspace/overview").json()
    plant_nav = {item["key"] for item in plant_overview["nav_items"]}
    assert "procurement" in plant_nav
    assert "comparison" in plant_nav
    assert plant_overview["team_queue"]

    store, _csrf = login("store.manager@genuinegigs.local")
    store_nav = {item["key"] for item in store.get("/workspace/overview").json()["nav_items"]}
    assert "store" in store_nav
    assert "quality" not in store_nav

    quality, _csrf = login("quality.inspector@genuinegigs.local")
    quality_nav = {item["key"] for item in quality.get("/workspace/overview").json()["nav_items"]}
    assert "quality" in quality_nav
    assert "store" not in quality_nav

    admin, _csrf = login("admin@genuinegigs.local")
    admin_items = admin.get("/workspace/overview").json()["nav_items"]
    admin_identities = [(item["key"], item["href"]) for item in admin_items]
    assert len(admin_identities) == len(set(admin_identities))
    assert admin_identities.count(("setup", "/workspace/setup")) == 1


def test_workspace_exposes_task_first_work_items_and_canonical_stages() -> None:
    local, _csrf = login('purchase.exec@genuinegigs.local')
    overview = local.get('/workspace/overview').json()
    assert overview['work_items']
    item = overview['work_items'][0]
    assert item['plain_language_goal']
    assert item['technical_term']
    assert item['href'].startswith('/')
    assert 'work_item=' in item['href']
    assert item['required_evidence']
    assert [stage['key'] for stage in overview['cycles'][0]['stages']] == [
        'requirement', 'rfq', 'quotes', 'comparison', 'po', 'gate', 'store', 'quality',
    ]
    assert all(stage['plain_label'] and stage['technical_label'] and stage['href'] for stage in overview['cycles'][0]['stages'])
    assert overview['cycles'][0]['current_stage'] != 'Resolve problems (Exception case)'
    assert {entry['group'] for entry in overview['nav_items']} == {'my_work', 'process_records'}


def test_work_item_context_remains_role_scoped_for_legacy_tasks() -> None:
    purchase_exec, _csrf = login('purchase.exec@genuinegigs.local')
    item = purchase_exec.get('/workspace/overview').json()['work_items'][0]
    url = '/workspace/work-items/' + item['id'] + '/context'
    response = purchase_exec.get(url)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['work_item']['id'] == item['id']
    if payload['stage'] is not None:
        assert payload['stage']['key'] == item['stage_key']
    assert 'restricted_actions' in payload
    purchase_manager, _csrf = login('purchase.manager@genuinegigs.local')
    assert purchase_manager.get(url).status_code == 404


def test_tasks_are_scoped_to_current_role_queue() -> None:
    plant, _csrf = login("plant.manager@genuinegigs.local")
    plant_tasks = plant.get("/tasks")
    assert plant_tasks.status_code == 200, plant_tasks.text
    assert plant_tasks.json() == []

    purchase_exec, _csrf = login("purchase.exec@genuinegigs.local")
    exec_tasks = purchase_exec.get("/tasks")
    assert exec_tasks.status_code == 200, exec_tasks.text
    assert exec_tasks.json()
    assert {task["owner_role"] for task in exec_tasks.json()} == {"purchase_executive"}

    purchase_manager, _csrf = login("purchase.manager@genuinegigs.local")
    manager_tasks = purchase_manager.get("/tasks")
    assert manager_tasks.status_code == 200, manager_tasks.text
    assert manager_tasks.json()
    assert {task["owner_role"] for task in manager_tasks.json()} == {"purchase_manager"}

def test_successful_action_removes_next_action_from_queue() -> None:
    local, csrf = login("purchase.manager@genuinegigs.local")
    before = local.get("/workspace/overview")
    assert before.status_code == 200, before.text
    assert any(action["entity_type"] == "award_decisions" for action in before.json()["next_actions"])

    response = local.post("/procurement/awards/AWARD-2026-005/approve", headers=mutation_headers(csrf, 1))
    assert response.status_code == 200, response.text

    after = local.get("/workspace/overview")
    assert after.status_code == 200, after.text
    assert not any(action["entity_type"] == "award_decisions" for action in after.json()["next_actions"])
    task_statuses = {task["title"]: task["status"] for task in local.get("/tasks").json()}
    assert task_statuses["Review contingency award for recovery quantity"] == "completed"


def test_purchase_executive_cannot_approve_award_api() -> None:
    local, csrf = login("purchase.exec@genuinegigs.local")
    response = local.post("/procurement/awards/AWARD-2026-004/approve", headers=mutation_headers(csrf, 1))
    assert response.status_code == 403


def test_store_and_quality_separation() -> None:
    store, store_csrf = login("store.manager@genuinegigs.local")
    blocked = store.post(
        "/inbound/inspections",
        headers=mutation_headers(store_csrf),
        json={"receipt_id": "REC-001", "inspected_quantity": 10, "accepted_quantity": 10, "rejected_quantity": 0, "held_quantity": 0},
    )
    assert blocked.status_code == 403

    quality, quality_csrf = login("quality.inspector@genuinegigs.local")
    blocked_receipt = quality.post(
        "/inbound/receipts",
        headers=mutation_headers(quality_csrf),
        json={"po_draft_id": "PO-DRAFT-2026-0019", "received_quantity": 10},
    )
    assert blocked_receipt.status_code == 403





def test_scoped_id_endpoints_do_not_allow_cross_tenant_mutation() -> None:
    from app.db import models
    with SessionLocal() as db:
        db.add(models.Tenant(id="tenant-other", name="Other Co", status="active"))
        db.add(models.PODraft(id="PO-OTHER-1", tenant_id="tenant-other", plant_id="plant-other", award_id="AWARD-2026-004", supplier_id="sup-steel-01", status="pending_approval", oracle_mapping={"quantity": 1}))
        db.add(models.Document(id="DOC-OTHER-1", tenant_id="tenant-other", plant_id="plant-other", filename="secret.pdf", content_type="application/pdf", size_bytes=1, storage_key="tenant-other/secret.pdf", status="quarantined_ready_for_extraction", validation_errors=[]))
        db.commit()

    manager, csrf = login("purchase.manager@genuinegigs.local")
    blocked_po = manager.post("/procurement/po-drafts/PO-OTHER-1/approve", headers=mutation_headers(csrf))
    assert blocked_po.status_code == 404
    blocked_doc = manager.get("/documents/DOC-OTHER-1/download-url")
    assert blocked_doc.status_code == 404


def test_full_requirement_to_po_outbox_workflow_uses_real_records() -> None:
    purchase_exec, exec_csrf = login("purchase.exec@genuinegigs.local")
    requirement = purchase_exec.post(
        "/procurement/requirements",
        headers=mutation_headers(exec_csrf),
        json={"item_id": "item-rm-304", "quantity": 100, "need_by_date": "2026-07-20", "title": "Test bearing sleeve buy"},
    )
    assert requirement.status_code == 200, requirement.text
    req_id = requirement.json()["id"]

    rfq = purchase_exec.post(f"/procurement/requirements/{req_id}/rfqs", headers=mutation_headers(exec_csrf))
    assert rfq.status_code == 200, rfq.text
    rfq_id = rfq.json()["id"]

    publish = purchase_exec.post(f"/procurement/rfqs/{rfq_id}/publish", headers=mutation_headers(exec_csrf, rfq.json()["version"]))
    assert publish.status_code == 200, publish.text
    token = publish.json()["supplier_portal_links"][0]["token"]

    quote = TestClient(app).post(
        f"/supplier/rfqs/{token}/quotes",
        headers=mutation_headers(),
        json={
            "quote_number": "SUP/TEST/1",
            "payment_terms": "30 days from GRN",
            "line": {
                "quantity": 100,
                "unit_price": 120,
                "freight": 500,
                "packaging": 100,
                "lead_time_days": 5,
                "promised_date": "2026-07-18",
                "moq": 50,
                "technical_compliance": "compliant",
                "certificates": ["Mill Test Certificate", "Heat Number Traceability"],
            },
        },
    )
    assert quote.status_code == 200, quote.text
    quote_id = quote.json()["id"]

    manager, manager_csrf = login("purchase.manager@genuinegigs.local")
    quote_detail = manager.get(f"/procurement/quotes/{quote_id}").json()
    decisions = [{"field_name": item["field_name"], "decision": "accept"} for item in quote_detail["field_verifications"]]
    verify = manager.post(f"/procurement/quotes/{quote_id}/verify-fields", headers=mutation_headers(manager_csrf, quote_detail["version"]), json={"decisions": decisions})
    assert verify.status_code == 200, verify.text
    comparison = manager.post(f"/procurement/comparisons/{rfq_id}/generate", headers=mutation_headers(manager_csrf))
    assert comparison.status_code == 200, comparison.text
    comparison_id = comparison.json()["id"]
    submit = manager.post(
        f"/procurement/comparison-records/{comparison_id}/submit",
        headers=mutation_headers(manager_csrf),
        json={"recommendation_rationale": "Best compliant landed cost and delivery"},
    )
    assert submit.status_code == 200, submit.text

    plant, plant_csrf = login("plant.manager@genuinegigs.local")
    plant_approval = plant.post(
        f"/procurement/comparison-records/{comparison_id}/decision",
        headers=mutation_headers(plant_csrf),
        json={"decision": "approve", "rationale": "Plant demand and timing confirmed"},
    )
    assert plant_approval.status_code == 200, plant_approval.text
    exec_approval = purchase_exec.post(
        f"/procurement/comparison-records/{comparison_id}/decision",
        headers=mutation_headers(exec_csrf),
        json={"decision": "approve", "rationale": "Commercial source evidence confirmed"},
    )
    assert exec_approval.status_code == 200, exec_approval.text
    assert exec_approval.json()["status"] == "approved"

    confirmation = manager.post(
        f"/procurement/comparison-records/{comparison_id}/confirm-po",
        headers=mutation_headers(manager_csrf),
        json={"confirmation": "CONFIRM_PO"},
    )
    assert confirmation.status_code == 200, confirmation.text
    po_id = confirmation.json()["po"]["id"]
    assert confirmation.json()["artifact"]["status"] == "final"
    assert confirmation.json()["supplier_sent"] is False
    assert confirmation.json()["erp_posted"] is False
    outbox = manager.get("/integrations/outbox").json()
    assert any(item.get("entity_id") == po_id and item.get("status") == "pending_approval" for item in outbox)

    po_artifacts = manager.get(f"/procurement/po-drafts/{po_id}/artifacts")
    assert po_artifacts.status_code == 200, po_artifacts.text
    final_po = next(item for item in po_artifacts.json() if item["status"] == "final")
    assert manager.get(final_po["download_url"]).status_code == 200

    gate, gate_csrf = login("gate.operator@genuinegigs.local")
    arrival = gate.post(
        "/inbound/gate-entries", headers=mutation_headers(gate_csrf),
        json={"po_draft_id": po_id, "vehicle_number": "MH12FLOW01", "supplier_challan": "FLOW-CH-1", "packages_count": 2},
    )
    assert arrival.status_code == 200, arrival.text

    store, store_csrf = login("store.manager@genuinegigs.local")
    receipt = store.post(
        "/inbound/receipts", headers=mutation_headers(store_csrf),
        json={"po_draft_id": po_id, "received_quantity": 100, "damaged_quantity": 0},
    )
    assert receipt.status_code == 200, receipt.text

    quality, quality_csrf = login("quality.inspector@genuinegigs.local")
    inspection = quality.post(
        "/inbound/inspections", headers=mutation_headers(quality_csrf),
        json={"receipt_id": receipt.json()["id"], "inspected_quantity": 100, "accepted_quantity": 100, "rejected_quantity": 0, "held_quantity": 0},
    )
    assert inspection.status_code == 200, inspection.text
    assert inspection.json()["accepted_quantity"] == 100


def test_document_security_rejects_corrupt_pdf_and_scopes_url() -> None:
    purchase_exec, csrf = login("purchase.exec@genuinegigs.local")
    response = purchase_exec.post(
        "/documents/upload",
        headers=mutation_headers(csrf),
        files={"file": ("quote.pdf", b"%PDF-1.7 corrupted", "application/pdf")},
    )
    assert response.status_code == 202, response.text
    payload = response.json()["document"]
    assert payload["status"] == "quarantined_rejected"
    assert "Corrupt PDF rejected" in payload["validation_errors"]
    url = purchase_exec.get(f"/documents/{payload['id']}/download-url")
    assert url.status_code == 403, url.text

    admin, _admin_csrf = login("admin@genuinegigs.local")
    admin_url = admin.get(f"/documents/{payload['id']}/download-url")
    assert admin_url.status_code == 200, admin_url.text
    assert "token=" in admin_url.json()["url"]


def test_rfq_pdf_preview_does_not_publish_and_final_artifact_is_immutable() -> None:
    executive, csrf = login("purchase.exec@genuinegigs.local")
    requirement = executive.post(
        "/procurement/requirements",
        headers=mutation_headers(csrf),
        json={"item_id": "item-rm-304", "quantity": 25, "need_by_date": "2026-08-01", "title": "PDF safety test"},
    )
    rfq = executive.post(
        f"/procurement/requirements/{requirement.json()['id']}/rfqs",
        headers=mutation_headers(csrf),
    )
    rfq_id = rfq.json()["id"]
    preview = executive.post(
        f"/procurement/rfqs/{rfq_id}/pdf-preview",
        headers=mutation_headers(csrf),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "draft"
    assert executive.get(f"/procurement/rfqs/{rfq_id}").json()["status"] == "draft"
    preview_url = executive.get(preview.json()["download_url"])
    assert preview_url.status_code == 200, preview_url.text
    assert preview_url.json()["url"].startswith("/documents/")
    assert "/content?token=" in preview_url.json()["url"]
    assert "minio:9000" not in preview_url.json()["url"]
    preview_content = executive.get(preview_url.json()["url"])
    assert preview_content.status_code == 200, preview_content.text
    assert preview_content.headers["content-type"].startswith("application/pdf")
    assert preview_content.headers["content-disposition"].startswith("inline;")
    assert preview_content.content.startswith(b"%PDF-")

    published = executive.post(
        f"/procurement/rfqs/{rfq_id}/publish",
        headers=mutation_headers(csrf, rfq.json()["version"]),
    )
    assert published.status_code == 200, published.text
    artifacts = executive.get(f"/procurement/rfqs/{rfq_id}/artifacts").json()
    final = next(item for item in artifacts if item["status"] == "final")
    assert final["checksum_sha256"]
    repeated = executive.get(f"/procurement/rfqs/{rfq_id}/artifacts").json()
    assert next(item for item in repeated if item["status"] == "final")["checksum_sha256"] == final["checksum_sha256"]


def test_only_gate_operator_can_record_gate_arrival() -> None:
    store, store_csrf = login("store.manager@genuinegigs.local")
    denied = store.post(
        "/inbound/gate-entries",
        headers=mutation_headers(store_csrf),
        json={"po_draft_id": "PO-DRAFT-2026-0019", "supplier_challan": "CH-STORE"},
    )
    assert denied.status_code == 403

    gate, gate_csrf = login("gate.operator@genuinegigs.local")
    recorded = gate.post(
        "/inbound/gate-entries",
        headers=mutation_headers(gate_csrf),
        json={
            "po_draft_id": "PO-DRAFT-2026-0019",
            "vehicle_number": "MH12AB1234",
            "supplier_challan": "CH-GATE-01",
            "packages_count": 4,
            "arrival_notes": "Seal intact",
        },
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["supplier_challan"] == "CH-GATE-01"
