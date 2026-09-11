from itertools import count
from datetime import date, timedelta

import pytest
import pyotp
from fastapi.testclient import TestClient

from app import agent_service
from app.agent_schemas import AgentProcurementFacts, AgentTurnDecision
from app.core.security import hash_password
from app.db import models
from app.db.seed import PLANT_ID, TENANT_ID, reset_workspace_database
from app.db.session import SessionLocal
from app.domains import workflows
from app.main import app
from app.routers import agents as agent_routes
from app.agent_schemas import ThreadCreateRequest


keys = count(1)


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def login(email: str) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post("/auth/login", json={"email": email, "password": "Password@123"})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def headers(csrf: str) -> dict[str, str]:
    return {"x-csrf-token": csrf, "Idempotency-Key": f"agent-test-{next(keys)}"}


def add_second_purchase_executive() -> None:
    with SessionLocal() as db:
        password = hash_password("Password@123")
        account = models.Account(
            id="acct-second-pe", email="second.purchase.exec@genuinegigs.local",
            name="Riya Sen", password_hash=password,
        )
        user = models.User(
            id="usr-pe-002", account_id=account.id, tenant_id=TENANT_ID, plant_id=PLANT_ID,
            department_id="dept-purchase", name="Riya Sen",
            email=account.email, role="purchase_executive", password_hash=password,
            manager_id="usr-pm-001",
        )
        membership = models.WorkspaceMembership(
            id="mem-usr-pe-002", account_id=account.id, tenant_id=TENANT_ID,
            user_id=user.id, default_plant_id=PLANT_ID, plant_ids=[PLANT_ID],
            department_id="dept-purchase", role="purchase_executive",
            manager_membership_id="mem-usr-pm-001", permissions=[], status="active",
        )
        profile = models.AgentProfile(
            id="agt-pe-002", tenant_id=TENANT_ID, plant_id=PLANT_ID, user_id=user.id,
            membership_id=membership.id, role="purchase_executive",
            display_name="Riya's Purchasing Agent",
            allowed_actions=["explain_task", "draft_rfq"],
            blocked_actions=["approve", "publish", "post_to_erp"],
            enabled=True,
        )
        task = models.Task(
            id="TASK-PRIVATE-002", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            title="Riya private supplier follow-up", owner_role="purchase_executive",
            owner_user_id=user.id, owner_membership_id=membership.id,
            status="open", severity="action", entity_type="supplier_follow_up",
            entity_id="PRIVATE-002",
        )
        db.add_all([account, user, membership, profile, task])
        db.commit()


def test_same_role_employee_cannot_read_or_open_another_employees_work() -> None:
    add_second_purchase_executive()
    meera, csrf = login("purchase.exec@genuinegigs.local")

    tasks = meera.get("/tasks")
    assert tasks.status_code == 200
    assert "TASK-PRIVATE-002" not in {item["id"] for item in tasks.json()}

    thread = meera.post(
        "/agent/threads",
        headers=headers(csrf),
        json={"thread_type": "work_item", "title": "Forbidden", "work_item_id": "TASK-PRIVATE-002"},
    )
    assert thread.status_code == 403


def test_private_agent_thread_is_not_visible_to_manager() -> None:
    employee, csrf = login("purchase.exec@genuinegigs.local")
    created = employee.post(
        "/agent/threads",
        headers=headers(csrf),
        json={"thread_type": "work_item", "title": "My recovery task", "work_item_id": "TASK-103"},
    )
    assert created.status_code == 200, created.text
    thread_id = created.json()["id"]
    reply = employee.post(
        f"/agent/threads/{thread_id}/messages",
        headers=headers(csrf),
        json={"content": "Explain what I need to do next."},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["message"]["citations"][0]["id"] == "TASK-103"
    assert reply.json()["message"]["content_format"] == "blocks"
    assert reply.json()["message"]["content_blocks"]

    manager, _ = login("purchase.manager@genuinegigs.local")
    private = manager.get(f"/agent/threads/{thread_id}")
    assert private.status_code == 403


def test_chat_history_backfills_distinct_title_and_allows_owner_deletion() -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(
            email="purchase.manager@genuinegigs.local",
        ).one()
        thread = agent_service.create_thread(
            db, user, ThreadCreateRequest(
                thread_type="personal", title="My work assistant",
            ),
        )
        membership = agent_service.membership_for_user(db, user)
        db.add(models.AgentMessage(
            tenant_id=TENANT_ID, plant_id=PLANT_ID, thread_id=thread.id,
            membership_id=membership.id, message_type="user",
            content="Upload supplier quotations to RFQ-2026-0001",
            correlation_id="AGT-TITLE-TEST", visibility="private",
        ))
        db.flush()
        assert agent_service.ensure_thread_title(db, thread) is True
        assert thread.title == "Quotation intake · RFQ-2026-0001"
        thread_id = thread.id
        agent_routes.delete_thread(thread.id, db, user)
        assert db.get(models.AgentThread, thread_id).status == "deleted"
        with pytest.raises(Exception) as deleted:
            agent_service.thread_for_membership(db, membership, thread_id)
        assert getattr(deleted.value, "status_code", None) == 404


def test_procurement_objective_creation_is_retired() -> None:
    manager, csrf = login("plant.manager@genuinegigs.local")
    response = manager.post(
        "/objectives",
        headers=headers(csrf),
        json={
            "material": "Food-grade conveyor belt",
            "quantity": 24,
            "uom": "M",
            "need_by_date": "2026-08-01",
            "reason": "Planned packaging line overhaul",
            "constraints": {"certificate": "FDA food-contact compliance"},
        },
    )
    assert response.status_code == 410
    assert '/procurement/requirements' in response.json()['detail']


def test_manager_delegates_and_employee_transitions_canonical_task() -> None:
    manager, manager_csrf = login('plant.manager@genuinegigs.local')
    created = manager.post(
        '/tasks',
        headers=headers(manager_csrf),
        json={
            'title': 'Verify supplier capability',
            'requested_outcome': 'Confirm approved capable suppliers for the requirement',
            'assignee_membership_id': 'mem-usr-pe-001',
            'priority': 'high',
            'context_entity_type': 'purchase_requirements',
            'context_entity_id': 'REQ-001',
        },
    )
    assert created.status_code == 200, created.text
    task_id = created.json()['id']
    assert created.json()['delegated_by_membership_id'] == 'mem-usr-plant-001'

    employee, employee_csrf = login('purchase.exec@genuinegigs.local')
    accepted = employee.post(
        f'/tasks/{task_id}/transition',
        headers=headers(employee_csrf),
        json={'status': 'accepted'},
    )
    assert accepted.status_code == 200, accepted.text
    started = employee.post(
        f'/tasks/{task_id}/transition',
        headers=headers(employee_csrf),
        json={'status': 'in_progress'},
    )
    assert started.status_code == 200, started.text
    assert started.json()['status'] == 'in_progress'


def test_peer_cannot_delegate_outside_reporting_hierarchy() -> None:
    employee, csrf = login('purchase.exec@genuinegigs.local')
    denied = employee.post(
        '/tasks',
        headers=headers(csrf),
        json={
            'title': 'Improper peer assignment',
            'requested_outcome': 'Attempt to assign another department',
            'assignee_membership_id': 'mem-usr-store-001',
        },
    )
    assert denied.status_code == 403


def test_model_decision_validator_backfills_facts_and_procurement_intent() -> None:
    normalized = agent_service.validate_model_decision(
        'Our plant requires 45 kilograms of ALI-102 aluminium ingot.',
        AgentTurnDecision(intent='answer', answer='Noted.'),
    )
    assert normalized.intent == 'procurement'
    assert normalized.facts.item_code == 'ALI-102'
    assert normalized.facts.quantity == 45
    assert normalized.facts.uom == 'KG'
    assert normalized.explicit_execute is False


def test_agent_retains_procurement_facts_and_creates_one_verified_delegation(monkeypatch) -> None:
    with SessionLocal() as db:
        item = db.query(models.Item).filter_by(
            tenant_id=TENANT_ID, plant_id=PLANT_ID, code='ALI-102',
        ).one()
        for supplier_id in ('sup-steel-01', 'sup-steel-02', 'sup-steel-03'):
            if not db.get(models.SupplierItemCapability, f'cap-ali-{supplier_id}'):
                db.add(models.SupplierItemCapability(
                    id=f'cap-ali-{supplier_id}', tenant_id=TENANT_ID, plant_id=PLANT_ID,
                    supplier_id=supplier_id, item_id=item.id, approved=True,
                ))
        item_id = item.id
        db.commit()

    decisions = [
        AgentTurnDecision(
            intent='procurement', answer='I retained 100 kg of aluminium ingot.',
            facts=AgentProcurementFacts(material_query='Aluminium ingot', quantity=100, uom='KG'),
        ),
        AgentTurnDecision(
            intent='procurement', answer='ALI-102 is the selected approved material.',
            facts=AgentProcurementFacts(item_code='ALI-102', supplier_master_confirmed=True),
        ),
        AgentTurnDecision(
            intent='delegate_procurement', explicit_execute=True,
            answer='I will create and delegate the requirement after server verification.',
            facts=AgentProcurementFacts(need_by_date='2026-08-15'),
        ),
    ]
    observed = []

    def mocked_provider(profile, question, context, history, current_facts):
        observed.append({'question': question, 'history': history, 'facts': dict(current_facts)})
        decision = decisions[min(len(observed) - 1, len(decisions) - 1)]
        return decision, 'groq', 'openai/gpt-oss-120b', None

    monkeypatch.setattr('app.agent_service.provider_response', mocked_provider)
    manager, csrf = login('plant.manager@genuinegigs.local')
    thread = manager.post(
        '/agent/threads', headers=headers(csrf),
        json={'thread_type': 'personal', 'title': 'Aluminium purchase'},
    )
    assert thread.status_code == 200, thread.text
    thread_id = thread.json()['id']
    prompts = [
        'I want to buy aluminium ingot 100 kg.',
        'Use ALI-102 from the approved master list.',
        'Need it in one month. Delegate this to the Purchase Executive.',
    ]
    replies = [
        manager.post(f'/agent/threads/{thread_id}/messages', headers=headers(csrf), json={'content': prompt})
        for prompt in prompts
    ]
    assert all(reply.status_code == 200 for reply in replies), [reply.text for reply in replies]
    final = replies[-1].json()['message']
    run_id = replies[-1].json()['run']['id']
    assert {block['type'] for block in final['content_blocks']} >= {'record_summary', 'role_handoff'}
    assert 'comparison' in next(block['text'] for block in final['content_blocks'] if block['type'] == 'role_handoff')
    assert observed[-1]['facts'] == {
        'material_query': 'Aluminium Ingot', 'quantity': 100.0, 'uom': 'KG',
        'item_id': 'item-ali-102', 'item_code': 'ALI-102',
        'supplier_master_confirmed': True,
        'need_by_date': '2026-08-15',
    }
    assert any(message['content'] == prompts[0] for message in observed[-1]['history'])
    activity = manager.get(f'/agent/runs/{run_id}/activity')
    assert activity.status_code == 200, activity.text
    assert {'events', 'tool_calls', 'proposals', 'receipts', 'checkpoints'} <= set(activity.json())
    assert any(row['event_type'] == 'tool_completed' for row in activity.json()['events'])
    assert len(activity.json()['receipts']) == 1
    assert activity.json()['receipts'][0]['tool_name'] == 'create_requirement_and_delegate'
    assert activity.json()['receipts'][0]['status'] == 'succeeded'
    assert {
        'resolve_identity_and_context',
        'validate_result',
        'persist_summary_and_metrics',
    } <= {row['step_name'] for row in activity.json()['checkpoints']}
    home = manager.get('/agent/home')
    assert home.status_code == 200
    assert len(home.json()['receipts']) == 1

    retry = manager.post(
        f'/agent/threads/{thread_id}/messages', headers=headers(csrf),
        json={'content': 'Delegate this exactly as confirmed.'},
    )
    assert retry.status_code == 200, retry.text
    with SessionLocal() as db:
        requirements = db.query(models.PurchaseRequirement).filter_by(source='agent', item_id=item_id).all()
        assert len(requirements) == 1
        requirement = requirements[0]
        assert (requirement.quantity, requirement.uom, requirement.need_by_date) == (
            100.0, 'KG', '2026-08-15',
        )
        tasks = db.query(models.Task).filter_by(entity_type='purchase_requirements', entity_id=requirement.id).all()
        assert len(tasks) == 1
        assert len(db.query(models.AgentDelegation).filter_by(work_item_id=tasks[0].id).all()) == 1
        assert len(db.query(models.AgentToolCall).filter_by(target_entity_id=requirement.id).all()) == 1
        receipts = db.query(models.AgentActionReceipt).filter_by(target_entity_id=requirement.id).all()
        assert len(receipts) == 1
        assert receipts[0].status == 'succeeded'
        run_ids = [run.id for run in db.query(models.AgentRun).filter_by(thread_id=thread_id).all()]
        event_types = {
            event.event_type for event in db.query(models.AgentEvent).filter(
                models.AgentEvent.run_id.in_(run_ids)
            ).all()
        }
        assert {'run_started', 'context_resolved', 'intent_resolved', 'tool_completed', 'run_completed'} <= event_types
        assert db.query(models.Objective).count() == 0
        persisted_thread = db.get(models.AgentThread, thread_id)
        assert persisted_thread.context_state['schema_version'] == 3
        assert persisted_thread.context_state['draft_fields']['quantity'] == 100.0
        assert 'procurement' not in persisted_thread.context_state


def test_agent_proposal_cannot_cross_human_authority() -> None:
    employee, csrf = login("purchase.exec@genuinegigs.local")
    thread = employee.post(
        "/agent/threads",
        headers=headers(csrf),
        json={"thread_type": "work_item", "title": "Recovery review", "work_item_id": "TASK-103"},
    )
    assert thread.status_code == 200, thread.text
    response = employee.post(
        "/agent/proposals",
        headers=headers(csrf),
        json={
            "thread_id": thread.json()["id"],
            "action": "approve_award",
            "target_entity_type": "award_decisions",
            "target_entity_id": "AWARD-2026-004",
            "expected_effect": "Approve the selected supplier",
            "required_authority": "purchase_manager",
        },
    )
    assert response.status_code == 403


def test_agent_proposal_rejection_requires_rationale() -> None:
    manager, csrf = login('purchase.manager@genuinegigs.local')
    thread = manager.post(
        '/agent/threads', headers=headers(csrf),
        json={'thread_type': 'personal', 'title': 'Controlled review'},
    )
    assert thread.status_code == 200, thread.text
    proposal = manager.post(
        '/agent/proposals', headers=headers(csrf),
        json={
            'thread_id': thread.json()['id'],
            'action': 'approve_award',
            'target_entity_type': 'award_decisions',
            'target_entity_id': 'AWARD-2026-004',
            'expected_effect': 'Approve the selected supplier',
            'required_authority': 'purchase_manager',
        },
    )
    assert proposal.status_code == 200, proposal.text
    proposal_id = proposal.json()['id']
    missing = manager.post(
        f'/agent/proposals/{proposal_id}/reject',
        headers=headers(csrf), json={},
    )
    assert missing.status_code == 422
    rejected = manager.post(
        f'/agent/proposals/{proposal_id}/reject',
        headers=headers(csrf), json={'reason': 'Commercial terms need another review.'},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['rejection_rationale'] == 'Commercial terms need another review.'


def test_purchase_executive_agent_prepares_idempotent_rfq_draft(monkeypatch) -> None:
    with SessionLocal() as db:
        executive = db.query(models.User).filter_by(
            email='purchase.exec@genuinegigs.local',
        ).one()
        item = db.query(models.Item).filter_by(
            tenant_id=TENANT_ID, plant_id=PLANT_ID,
        ).first()
        requirement = workflows.create_requirement(
            db, executive, item.id, 250, '2026-09-15',
            uom=item.uom_id, title='Agent RFQ preparation test',
            reason='Validate the contextual RFQ drafting workflow.',
        )
        db.flush()
        task = db.query(models.Task).filter_by(
            tenant_id=TENANT_ID,
            entity_type='purchase_requirements',
            entity_id=requirement.id,
        ).one()
        task_id = task.id
        requirement_id = requirement.id
        db.commit()

    def mocked_provider(profile, question, context, history, current_facts):
        return AgentTurnDecision(
            intent='prepare_rfq',
            answer='Prepare the RFQ from the linked requirement.',
        ), 'groq', 'openai/gpt-oss-120b', None

    monkeypatch.setattr('app.agent_service.provider_response', mocked_provider)
    executive, csrf = login('purchase.exec@genuinegigs.local')
    thread = executive.post(
        '/agent/threads', headers=headers(csrf),
        json={
            'thread_type': 'work_item',
            'title': 'Prepare supplier RFQ',
            'work_item_id': task_id,
        },
    )
    assert thread.status_code == 200, thread.text
    reply = executive.post(
        f"/agent/threads/{thread.json()['id']}/messages",
        headers=headers(csrf),
        json={'content': 'Prepare the RFQ and draft PDF for this requirement.'},
    )
    assert reply.status_code == 200, reply.text
    block_types = {row['type'] for row in reply.json()['message']['content_blocks']}
    assert {'prepared_artifact', 'action_receipt'} <= block_types
    with SessionLocal() as db:
        rfqs = db.query(models.RFQ).filter_by(requirement_id=requirement_id).all()
        assert len(rfqs) == 1
        assert rfqs[0].status == 'draft'
        receipts = db.query(models.AgentActionReceipt).filter_by(
            tool_name='prepare_rfq_draft',
            target_entity_id=rfqs[0].id,
        ).all()
        assert len(receipts) == 1
        artifacts = db.query(models.GeneratedArtifact).filter_by(
            entity_type='rfq', entity_id=rfqs[0].id,
        ).all()
        assert len(artifacts) == 1


def test_fresh_workspace_has_no_demo_transactions() -> None:
    admin, csrf = login("admin@genuinegigs.local")
    created = admin.post(
        "/workspaces",
        headers=headers(csrf),
        json={
            "company_name": "Clean Start Manufacturing",
            "workspace_name": "Clean Start Operations",
            "plant_name": "New Plant",
            "plant_code": "NEW-01",
            "agent_enabled": False,
        },
    )
    assert created.status_code == 200, created.text
    membership_id = created.json()["membership"]["id"]
    selected = admin.post(
        "/workspaces/select",
        headers=headers(csrf),
        json={"membership_id": membership_id},
    )
    assert selected.status_code == 200, selected.text
    new_csrf = selected.json()["csrf_token"]

    assert admin.get("/procurement/requirements").json() == []
    assert admin.get("/procurement/rfqs").json() == []
    assert admin.get("/tasks").json() == []
    setup = admin.get('/workspace/setup').json()
    assert setup['active_roles'] == ['admin']
    assert setup['onboarding_status'] == 'needs_team'
    home = admin.get("/agent/home")
    assert home.status_code == 200
    assert home.json()["enabled"] is False
    assert new_csrf != csrf


def test_fresh_workspace_can_atomically_enable_role_agents() -> None:
    admin, csrf = login("admin@genuinegigs.local")
    created = admin.post(
        "/workspaces",
        headers=headers(csrf),
        json={
            "company_name": "Agent Enabled Manufacturing",
            "workspace_name": "Agent Enabled Operations",
            "plant_name": "Agent Plant",
            "plant_code": "AGENT-01",
            "agent_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["workspace"]["agent_enabled"] is True
    membership_id = created.json()["membership"]["id"]
    selected = admin.post(
        "/workspaces/select",
        headers=headers(csrf),
        json={"membership_id": membership_id},
    )
    assert selected.status_code == 200, selected.text
    home = admin.get("/agent/home")
    assert home.status_code == 200
    assert home.json()["enabled"] is True

    disabled = admin.patch(
        "/admin/workspace/agent-policy",
        headers=headers(selected.json()["csrf_token"]),
        json={"enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False
    assert admin.get("/agent/home").json()["enabled"] is False


def test_admin_builds_clean_workspace_team_and_every_account_gets_its_role_agent() -> None:
    admin, csrf = login("admin@genuinegigs.local")
    created = admin.post(
        "/workspaces",
        headers=headers(csrf),
        json={
            "company_name": "Customer Controlled Manufacturing",
            "workspace_name": "Customer Controlled Operations",
            "plant_name": "Customer Plant",
            "plant_code": "CUSTOMER-01",
            "agent_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    selected = admin.post(
        "/workspaces/select",
        headers=headers(csrf),
        json={"membership_id": created.json()["membership"]["id"]},
    )
    assert selected.status_code == 200, selected.text
    fresh_csrf = selected.json()["csrf_token"]
    assert admin.get("/auth/me").json()["user"]["role"] == "admin"

    plants = admin.get("/org/plants").json()
    departments = admin.get("/org/departments").json()
    plant_id = plants[0]["id"]
    departments_by_name = {row["name"]: row["id"] for row in departments}
    department_for_role = {
        "plant_manager": "Plant Leadership",
        "purchase_manager": "Procurement",
        "purchase_executive": "Procurement",
        "gate_operator": "Gate and Security",
        "store_manager": "Stores",
        "quality_inspector": "Quality",
    }
    manager_ids: dict[str, str] = {}
    credentials: list[tuple[str, str]] = []
    for index, role in enumerate(department_for_role, start=1):
        manager_id = (
            manager_ids.get("purchase_manager")
            if role == "purchase_executive"
            else manager_ids.get("plant_manager") if role != "plant_manager" else None
        )
        email = f"customer.{role}@example.com"
        password = f"CustomerRole@{index}23"
        response = admin.post(
            "/org/users",
            headers=headers(fresh_csrf),
            json={
                "name": role.replace("_", " ").title(),
                "email": email,
                "password": password,
                "role": role,
                "department_id": departments_by_name[department_for_role[role]],
                "plant_ids": [plant_id],
                "manager_id": manager_id,
            },
        )
        assert response.status_code == 200, response.text
        manager_ids[role] = response.json()["id"]
        credentials.append((email, password))

    setup = admin.get("/workspace/setup").json()
    assert setup["onboarding_status"] == "needs_master_data"
    assert set(setup["required_roles"]).issubset(set(setup["active_roles"]))
    with SessionLocal() as db:
        tenant_id = created.json()["workspace"]["id"]
        memberships = db.query(models.WorkspaceMembership).filter_by(
            tenant_id=tenant_id, status="active"
        ).all()
        assert len(memberships) == 7
        assert {row.role for row in memberships} == {
            "admin", *department_for_role.keys(),
        }
        profiles = db.query(models.AgentProfile).filter_by(tenant_id=tenant_id).all()
        assert len(profiles) == 7
        assert all(profile.enabled for profile in profiles)

    for email, password in credentials:
        employee = TestClient(app)
        signed_in = employee.post("/auth/login", json={"email": email, "password": password})
        assert signed_in.status_code == 200, signed_in.text
        home = employee.get("/agent/home")
        assert home.status_code == 200, home.text
        assert home.json()["enabled"] is True


def test_non_admin_cannot_create_a_workspace() -> None:
    manager, csrf = login("plant.manager@genuinegigs.local")
    denied = manager.post(
        "/workspaces",
        headers=headers(csrf),
        json={
            "company_name": "Unauthorized Company",
            "workspace_name": "Unauthorized Workspace",
            "plant_name": "Unauthorized Plant",
            "plant_code": "DENIED-01",
            "agent_enabled": False,
        },
    )
    assert denied.status_code == 403


def test_workspace_owner_can_invite_and_new_employee_can_accept() -> None:
    admin, csrf = login('admin@genuinegigs.local')
    created = admin.post(
        '/workspaces', headers=headers(csrf),
        json={
            'company_name': 'Onboarding Manufacturing',
            'workspace_name': 'Onboarding Operations',
            'plant_name': 'Onboarding Plant',
            'plant_code': 'ONB-01',
            'agent_enabled': False,
        },
    )
    assert created.status_code == 200, created.text
    selected = admin.post(
        '/workspaces/select', headers=headers(csrf),
        json={'membership_id': created.json()['membership']['id']},
    )
    assert selected.status_code == 200, selected.text
    fresh_csrf = selected.json()['csrf_token']
    me = admin.get('/auth/me')
    assert me.status_code == 200
    assert me.json()['user']['role'] == 'admin'
    assert 'workspace.owner' in me.json()['user']['permissions']
    assert 'workspace.manage_members' in me.json()['user']['capabilities']
    setup = admin.get('/workspace/setup')
    assert setup.status_code == 200, setup.text
    assert setup.json()['onboarding_status'] == 'needs_team'
    assert setup.json()['active_roles'] == ['admin']

    invited = admin.post(
        '/workspace/invitations', headers=headers(fresh_csrf),
        json={'email': 'new.purchase.manager@example.com', 'role': 'purchase_manager'},
    )
    assert invited.status_code == 200, invited.text
    token = invited.json()['development_token']
    listed = admin.get('/workspace/invitations')
    assert listed.status_code == 200
    assert listed.json()[0]['status'] == 'pending'

    anonymous = TestClient(app)
    accepted = anonymous.post(
        '/workspace/invitations/accept',
        headers={'Idempotency-Key': f'agent-test-{next(keys)}'},
        json={'token': token, 'name': 'Priya Menon', 'password': 'CustomPassword@123'},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['email'] == 'new.purchase.manager@example.com'
    employee = TestClient(app).post(
        '/auth/login',
        json={'email': 'new.purchase.manager@example.com', 'password': 'CustomPassword@123'},
    )
    assert employee.status_code == 200, employee.text
    assert employee.json()['user']['role'] == 'purchase_manager'
    assert admin.get('/workspace/setup').json()['onboarding_status'] == 'needs_team'


def test_login_requires_workspace_choice_after_fresh_workspace_creation() -> None:
    admin, csrf = login('admin@genuinegigs.local')
    created = admin.post('/workspaces', headers=headers(csrf), json={
        'company_name': 'Choice Manufacturing', 'workspace_name': 'Choice Operations',
        'plant_name': 'Choice Plant', 'plant_code': 'CHOICE-01', 'agent_enabled': False,
    })
    assert created.status_code == 200, created.text

    fresh_login = TestClient(app)
    options = fresh_login.post('/auth/login', json={
        'email': 'admin@genuinegigs.local', 'password': 'Password@123',
    })
    assert options.status_code == 200, options.text
    assert options.json()['requires_workspace_selection'] is True
    assert len(options.json()['workspaces']) == 2

    selected = fresh_login.post('/auth/login', json={
        'email': 'admin@genuinegigs.local', 'password': 'Password@123',
        'membership_id': created.json()['membership']['id'],
    })
    assert selected.status_code == 200, selected.text
    assert selected.json()['user']['tenant_id'] == created.json()['workspace']['id']


def test_mfa_enrollment_requires_a_valid_login_challenge() -> None:
    client, csrf = login("admin@genuinegigs.local")
    enrolled = client.post("/auth/mfa/enroll", headers=headers(csrf))
    assert enrolled.status_code == 200, enrolled.text
    secret = enrolled.json()["secret"]
    code = pyotp.TOTP(secret).now()

    confirmed = client.post(
        "/auth/mfa/confirm", headers=headers(csrf), json={"code": code},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert len(confirmed.json()["backup_codes"]) == 8

    no_challenge = TestClient(app).post(
        "/auth/login",
        json={"email": "admin@genuinegigs.local", "password": "Password@123"},
    )
    assert no_challenge.status_code == 401
    assert no_challenge.json()["detail"]["code"] == "mfa_required"

    challenged = TestClient(app).post(
        "/auth/login",
        json={
            "email": "admin@genuinegigs.local",
            "password": "Password@123",
            "otp": pyotp.TOTP(secret).now(),
        },
    )
    assert challenged.status_code == 200, challenged.text


def test_password_reset_revokes_existing_sessions() -> None:
    signed_in, _csrf = login("purchase.exec@genuinegigs.local")
    anonymous = TestClient(app)
    requested = anonymous.post(
        "/auth/password-reset/request",
        headers={"Idempotency-Key": f"agent-test-{next(keys)}"},
        json={"email": "purchase.exec@genuinegigs.local"},
    )
    assert requested.status_code == 200, requested.text
    token = requested.json()["development_token"]

    confirmed = anonymous.post(
        "/auth/password-reset/confirm",
        headers={"Idempotency-Key": f"agent-test-{next(keys)}"},
        json={"token": token, "password": "Replacement@123"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert signed_in.get("/auth/me").status_code == 401

    old_password = TestClient(app).post(
        "/auth/login",
        json={"email": "purchase.exec@genuinegigs.local", "password": "Password@123"},
    )
    new_password = TestClient(app).post(
        "/auth/login",
        json={"email": "purchase.exec@genuinegigs.local", "password": "Replacement@123"},
    )
    assert old_password.status_code == 401
    assert new_password.status_code == 200, new_password.text
