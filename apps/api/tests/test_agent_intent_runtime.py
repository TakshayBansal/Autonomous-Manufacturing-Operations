from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import agent_service, procurement_v2, task_service
from app.domains import workflows
from app.agent_capabilities import unregistered_capability_adapters, validate_intent
from app.agent_schemas import AgentMessageRequest, IntentEnvelope, TaskCreateRequest, TaskTransitionRequest, ThreadCreateRequest
from app.agent_state import (
    apply_intent, load_thread_state, merge_thread_state, persist_thread_state,
    remember_entity,
)
from app.agent_runtime import run_bounded_tool_loop
from app.db import models
from app.db.session import SessionLocal
from app.db.seed import reset_workspace_database


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def _user(db, email: str) -> models.User:
    return db.query(models.User).filter_by(email=email).one()


def _thread(db, user: models.User) -> models.AgentThread:
    return agent_service.create_thread(
        db, user, ThreadCreateRequest(thread_type="personal", title="Intent runtime test")
    )


def _approved_requirement(db, executive: models.User, *, business_number: str) -> models.PurchaseRequirement:
    item = db.query(models.Item).filter_by(code="ALI-102").one()
    requirement = workflows.create_requirement(
        db,
        executive,
        item.id,
        132,
        (date.today() + timedelta(days=30)).isoformat(),
        uom=item.uom_id,
        title="Aluminium Ingot requirement",
        reason="Raw material requirement",
    )
    requirement.business_number = business_number
    db.flush()
    return requirement


def test_exact_rfq_transcript_works_from_normal_personal_thread(monkeypatch) -> None:
    with SessionLocal() as db:
        executive = _user(db, "purchase.exec@genuinegigs.local")
        requirement = _approved_requirement(db, executive, business_number="REQ-2026-0033")
        thread = _thread(db, executive)
        db.flush()

        monkeypatch.setattr(
            agent_service,
            "provider_response",
            lambda *_args, **_kwargs: (
                IntentEnvelope(
                    intent="prepare_rfq_draft",
                    requested_outcome="Generate RFQ for REQ-2026-0033",
                    entities={"requirement_id": "REQ-2026-0033"},
                    confidence=1,
                ),
                "groq",
                "test-model",
                None,
            ),
        )

        _run, message = agent_service.run_message(
            db,
            executive,
            thread.id,
            AgentMessageRequest(content="Generate RFQ for REQ-2026-0033"),
        )

        rfq = db.query(models.RFQ).filter_by(requirement_id=requirement.id).one()
        assert rfq.business_number in message.content
        assert "Task context required" not in message.content
        assert db.query(models.AgentActionReceipt).filter_by(
            tool_name="prepare_rfq_draft", target_entity_id=rfq.id, status="succeeded"
        ).one()


def test_latest_requirement_rfq_transcript_is_bounded_and_does_not_dump_tasks(monkeypatch) -> None:
    with SessionLocal() as db:
        executive = _user(db, "purchase.exec@genuinegigs.local")
        requirement = _approved_requirement(db, executive, business_number="REQ-2026-0099")
        thread = _thread(db, executive)
        db.flush()

        monkeypatch.setattr(
            agent_service,
            "provider_response",
            lambda *_args, **_kwargs: (
                IntentEnvelope(
                    intent="prepare_rfq_draft",
                    requested_outcome="Prepare the RFQ for the latest requirement",
                    entities={"requirement_id": "latest requirement"},
                    confidence=1,
                ),
                "groq",
                "test-model",
                None,
            ),
        )

        _run, message = agent_service.run_message(
            db,
            executive,
            thread.id,
            AgentMessageRequest(content="Can you generate the RFQ for the latest requirement"),
        )

        rfq = db.query(models.RFQ).filter_by(requirement_id=requirement.id).one()
        assert rfq.business_number in message.content
        assert "Task context required" not in message.content
        assert "count" not in message.content.casefold()
        assert len(message.content_blocks) <= 5


def test_date_normalization_supports_reported_relative_and_indian_formats() -> None:
    today = date(2026, 7, 16)
    assert agent_service.normalize_need_by_date("in 30 days", today=today) == "2026-08-15"
    assert agent_service.normalize_need_by_date("one month", today=today) == "2026-08-15"
    assert agent_service.normalize_need_by_date("31/07/2026", today=today) == "2026-07-31"
    assert agent_service.normalize_need_by_date("next Friday", today=today) == "2026-07-17"
    assert agent_service.normalize_need_by_date("month-end", today=today) == "2026-07-31"


def test_thread_state_v2_migrates_to_v3_merges_topic_switch_and_coreference() -> None:
    state = load_thread_state({
        "procurement": {"material_query": "Copper Ingot", "quantity": 100},
        "recent_entities": [{"type": "purchase_requirement", "id": "req-1", "display_id": "REQ-1"}],
        "blocked_on": "material",
    })
    assert state.schema_version == 3
    assert state.recent_entities[0].business_number == "REQ-1"
    switched = merge_thread_state(
        state, topic_change=True,
        facts={"material_query": "Aluminium Ingot", "quantity": 100},
    )
    assert switched.blocked_on is None
    assert switched.draft_fields["material_query"] == "Aluminium Ingot"
    remembered = remember_entity(
        switched, entity_type="rfq", entity_id="rfq-1", business_number="RFQ-2026-0001",
    )
    assert remembered.recent_entities[0].business_number == "RFQ-2026-0001"
    assert remembered.selected_context.entity_id == "rfq-1"


def test_live_state_writer_persists_only_canonical_v3_keys() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        thread.context_state = {
            "procurement": {"material_query": "Copper Ingot", "quantity": 100},
            "intent": "procurement",
            "current_work_item": {
                "type": "purchase_requirement", "id": "req-legacy",
            },
        }
        state = apply_intent(
            load_thread_state(thread.context_state),
            IntentEnvelope(
                intent="create_purchase_requirement",
                requested_outcome="Use aluminium instead",
                entities={"material_query": "Aluminium Ingot"},
                confidence=1,
                is_topic_change=True,
            ),
            provenance_message_id="message-1",
        )
        persist_thread_state(thread, state)
        assert thread.context_schema_version == 3
        assert thread.context_state["schema_version"] == 3
        assert "procurement" not in thread.context_state
        assert "intent" not in thread.context_state
        assert "current_work_item" not in thread.context_state
        assert thread.context_state["draft_fields"]["material_query"] == "Aluminium Ingot"
        assert thread.context_state["field_provenance"]["material_query"] == {
            "message_id": "message-1", "source": "user",
        }


def test_selected_page_context_is_scoped_persisted_and_resolves_pronouns() -> None:
    with SessionLocal() as db:
        executive = _user(db, "purchase.exec@genuinegigs.local")
        requirement = _approved_requirement(
            db, executive, business_number="REQ-PAGE-CONTEXT",
        )
        thread = _thread(db, executive)
        db.flush()
        _run, message = agent_service.run_message(
            db, executive, thread.id,
            AgentMessageRequest(
                content="What is its ID?",
                selected_context={
                    "entity_type": "purchase_requirement",
                    "entity_id": requirement.id,
                    "source": "page",
                },
            ),
        )
        assert message.content == "REQ-PAGE-CONTEXT"
        state = load_thread_state(thread.context_state)
        assert state.selected_context.entity_id == requirement.id
        assert state.recent_entities[0].business_number == "REQ-PAGE-CONTEXT"

        with pytest.raises(HTTPException) as forged:
            agent_service.run_message(
                db, executive, thread.id,
                AgentMessageRequest(
                    content="Open this record",
                    selected_context={
                        "entity_type": "purchase_requirement",
                        "entity_id": "REQ-OTHER-TENANT",
                    },
                ),
            )
        assert forged.value.status_code == 404


def test_bounded_loop_recovers_after_reads_and_stops_after_one_mutation() -> None:
    requests = iter([
        {"type": "tool", "tool": "search_records", "args": {"query": "wrong"}},
        {"type": "tool", "tool": "resolve_record", "args": {"reference": "REQ-2026-0033"}},
        {"type": "tool", "tool": "prepare_rfq_draft", "args": {"requirement_id": "req-1"}},
    ])
    state = run_bounded_tool_loop(
        {"messages": [], "observations": []},
        decide=lambda _state: next(requests),
        execute=lambda request: {"tool": request["tool"], "status": "ok"},
        tool_categories={
            "search_records": "read", "resolve_record": "read", "prepare_rfq_draft": "mutation",
        },
    )
    assert state["read_count"] == 2
    assert state["mutation_count"] == 1
    assert state["termination_reason"] == "mutation_completed"
    assert len(state["observations"]) == 3


def test_bounded_loop_safely_terminates_on_read_budget() -> None:
    state = run_bounded_tool_loop(
        {"messages": [], "observations": []},
        decide=lambda _state: {"type": "tool", "tool": "search_records", "args": {}},
        execute=lambda request: {"tool": request["tool"], "status": "empty"},
        tool_categories={"search_records": "read"}, max_reads=2,
    )
    assert state["read_count"] == 2
    assert state["termination_reason"] == "read_budget_exceeded"


def test_task_semantic_identity_deduplicates_active_work_and_allows_a_new_cycle() -> None:
    with SessionLocal() as db:
        manager = _user(db, "plant.manager@genuinegigs.local")
        executive = _user(db, "purchase.exec@genuinegigs.local")
        assignee = db.query(models.WorkspaceMembership).filter_by(user_id=executive.id).one()
        requirement = db.query(models.PurchaseRequirement).first()
        payload = TaskCreateRequest(
            title="Prepare supplier request",
            requested_outcome="Prepare and review the supplier request",
            assignee_membership_id=assignee.id,
            task_type="prepare_rfq",
            context_entity_type="purchase_requirements",
            context_entity_id=requirement.id,
        )
        first = task_service.create_task(db, manager, payload)
        second = task_service.create_task(db, manager, payload)
        assert second.id == first.id
        assert db.query(models.Task).filter_by(semantic_key=first.semantic_key).count() == 1
        task_service.transition_task(db, executive, first.id, TaskTransitionRequest(status="accepted"))
        task_service.transition_task(db, executive, first.id, TaskTransitionRequest(status="in_progress"))
        task_service.transition_task(db, executive, first.id, TaskTransitionRequest(status="completed", summary="Supplier request prepared"))
        next_cycle = task_service.create_task(db, manager, payload)
        assert next_cycle.id != first.id
        assert db.query(models.Task).filter_by(semantic_key=first.semantic_key).count() == 2


def test_live_run_message_observes_then_mutates_within_one_bounded_turn(monkeypatch) -> None:
    decisions = iter([
        IntentEnvelope(
            intent="search_approved_material",
            requested_outcome="Resolve Aluminium Ingot",
            entities={"material_query": "Aluminium Ingot"},
            confidence=1,
        ),
        IntentEnvelope(
            intent="create_purchase_requirement",
            requested_outcome="Create the resolved requirement",
            entities={},
            confidence=1,
        ),
    ])
    calls = []

    def provider(*_args, **_kwargs):
        calls.append(1)
        return next(decisions), "groq", "bounded-test-model", None

    monkeypatch.setattr(agent_service, "provider_response", provider)
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        db.flush()
        run, message = agent_service.run_message(
            db, user, thread.id,
            AgentMessageRequest(content=(
                "We need 25 KG Aluminium Ingot "
                "needed in 14 days because production stock is low."
            )),
        )
        created = next(block for block in message.content_blocks if block["type"] == "record_created")
        assert db.get(models.PurchaseRequirement, created["record"]["id"])
        assert len(calls) == 2
        assert run.read_tool_count == 1
        assert run.mutation_count == 1
        assert run.termination_reason == "mutation_completed"


def test_unknown_and_unauthorized_capabilities_are_rejected() -> None:
    assert unregistered_capability_adapters() == []
    with pytest.raises(HTTPException) as unknown:
        validate_intent(IntentEnvelope(
            intent="invent_purchase_order", requested_outcome="do it", confidence=1,
        ), "plant_manager")
    assert unknown.value.status_code == 422
    with pytest.raises(HTTPException) as denied:
        validate_intent(IntentEnvelope(
            intent="prepare_supplier_comparison", requested_outcome="compare", confidence=1,
        ), "plant_manager")
    assert denied.value.status_code == 403


def test_invalid_model_intent_falls_back_to_read_only_context() -> None:
    intent, rejected = agent_service.safe_provider_intent(
        IntentEnvelope(intent="greeting", requested_outcome="Say hello", confidence=0.9),
        "Hi", {}, "plant_manager",
    )
    assert rejected is True
    assert intent.intent == "answer_work_context"


def test_exact_requirement_transcript_is_grounded_and_id_followup_reuses_receipt() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        db.flush()
        _, created = agent_service.run_message(db, user, thread.id, AgentMessageRequest(
            content="Create a raw-material requirement for 100 kg of Aluminium Ingot, needed one month from today."
        ))
        created_block = next(row for row in created.content_blocks if row["type"] == "record_created")
        record = created_block["record"]
        persisted = db.get(models.PurchaseRequirement, record["id"])
        assert persisted is not None
        assert record["display_id"] == persisted.business_number
        assert persisted.item_id == "item-ali-102"
        assert persisted.quantity == 100
        assert persisted.need_by_date == (date.today() + timedelta(days=30)).isoformat()
        _, followup = agent_service.run_message(
            db, user, thread.id, AgentMessageRequest(content="What is its ID?")
        )
        assert followup.content == persisted.business_number
        assert "shortly" not in (created.content + followup.content).casefold()


def test_material_listing_and_name_wins_over_mistyped_code() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        materials = agent_service.approved_material_records(db, user)
        assert {(row["code"], row["name"]) for row in materials} >= {
            ("ALI-102", "Aluminium Ingot"), ("CU-201", "Copper Ingot"),
        }
        membership = agent_service.membership_for_user(db, user)
        resolution = agent_service.resolve_procurement_action(db, user, membership, {
            "item_code": "AL1-102", "material_query": "Aluminium Ingot",
            "quantity": 100, "uom": "KG", "need_by_date": "2026-08-15",
        })
        assert resolution["item"].code == "ALI-102"
        assert resolution["canonical_code_corrected"] is True


def test_missing_material_request_confirmation_and_approval_continuation() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        db.flush()
        _, draft = agent_service.run_message(db, user, thread.id, AgentMessageRequest(
            content=(
                "Create a new material master for Titanium Ingot, item code TI-900, 50 kg, "
                "needed in 30 days because it is required for a raw material trial, then create the requirement."
            )
        ))
        assert any(row["type"] == "confirmation" for row in draft.content_blocks)
        _, pending = agent_service.run_message(
            db, user, thread.id, AgentMessageRequest(content="Confirm the pending request.")
        )
        request_id = next(row["record"]["id"] for row in pending.content_blocks if row.get("record"))
        request = db.get(models.MaterialMasterRequest, request_id)
        assert request and request.status == "pending"
        assert db.query(models.PurchaseRequirement).filter_by(item_id=request.resulting_item_id).count() == 0
        admin = _user(db, "admin@genuinegigs.local")
        procurement_v2.decide_material_request(db, admin, request.id, "approve", "Valid trial material")
        db.flush()
        notification = db.query(models.Notification).filter_by(
            user_id=user.id, linked_entity_id=request.id, category="material_master_decision",
        ).one()
        assert notification.status == "unread"
        _, completed = agent_service.run_message(
            db, user, thread.id, AgentMessageRequest(content="Complete the requirement.")
        )
        record = next(row["record"] for row in completed.content_blocks if row["type"] == "record_created")
        requirement = db.get(models.PurchaseRequirement, record["id"])
        assert requirement and requirement.item_id == request.resulting_item_id


def test_manager_team_updates_are_grounded_in_each_employee_scope() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        db.flush()
        _run, message = agent_service.run_message(
            db, user, thread.id, AgentMessageRequest(
                content="Ask my team agents for their current progress.",
                requested_capability="summarize_team_status",
            )
        )
        activity = next(row for row in message.content_blocks if row["type"] == "agent_activity")
        agents = activity["record"]["agents"]
        assert agents
        assert all("employee_name" in row and "summary" in row for row in agents)
        assert all("private" not in str(row).casefold() for row in agents)


def test_natural_requirement_message_resolves_typo_and_creates_without_reasking() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        db.flush()
        _run, message = agent_service.run_message(
            db, user, thread.id, AgentMessageRequest(
                content="I want to create a requirement for ALU-102, Aluminium Ingot 132 KG, want in 14 days"
            )
        )
        created = next(row for row in message.content_blocks if row["type"] == "record_created")
        requirement = db.get(models.PurchaseRequirement, created["record"]["id"])
        assert requirement is not None
        assert requirement.item_id == "item-ali-102"
        assert requirement.quantity == 132
        assert requirement.need_by_date == (date.today() + timedelta(days=14)).isoformat()
        assert created["record"]["item_code"] == "ALI-102"
        assert not any(row["type"] == "clarification" for row in message.content_blocks)


def test_code_only_followup_safely_resolves_canonical_material() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        db.flush()
        agent_service.run_message(db, user, thread.id, AgentMessageRequest(content="I want to create a requirement"))
        _run, message = agent_service.run_message(db, user, thread.id, AgentMessageRequest(content="ALU-102"))
        record = next(row["record"] for row in message.content_blocks if row.get("record"))
        assert record["code"] == "ALI-102"
        assert record["name"] == "Aluminium Ingot"
        assert not any(
            action["id"] == "create_material_master_request"
            for row in message.content_blocks for action in row.get("actions", [])
        )


def test_partial_requirement_clarification_is_conversational_and_business_facing() -> None:
    with SessionLocal() as db:
        user = _user(db, "plant.manager@genuinegigs.local")
        thread = _thread(db, user)
        db.flush()
        _run, message = agent_service.run_message(
            db, user, thread.id, AgentMessageRequest(
                content="Create a requirement for Aluminium Ingot",
                requested_capability="create_purchase_requirement",
            ),
        )
        clarification = next(
            row for row in message.content_blocks if row["type"] == "clarification"
        )
        assert clarification["text"].startswith("I found ALI-102 · Aluminium Ingot.")
        assert "What quantity and need-by date should I use?" in clarification["text"]
        visible = f"{message.content} {message.content_blocks}".casefold()
        assert "approved material master match" not in visible
        assert "remaining information" not in visible
        assert "still needed" not in visible


def test_grounded_narration_preserves_exact_business_identifiers() -> None:
    answer = agent_service.preserve_business_identifiers(
        "RFQ\u20112026\u20110032 is ready for REQ\u20112026\u20110033.",
        [{
            "record": {
                "display_id": "RFQ-2026-0032",
                "requirement_number": "REQ-2026-0033",
            },
        }],
    )
    assert "RFQ-2026-0032" in answer
    assert "REQ-2026-0033" in answer
    assert "\u2011" not in answer


def test_assistant_quote_attachment_uses_canonical_idempotent_quote_service() -> None:
    with SessionLocal() as db:
        executive = _user(db, "purchase.exec@genuinegigs.local")
        manager = _user(db, "purchase.manager@genuinegigs.local")
        requirement = _approved_requirement(
            db, executive, business_number="REQ-ATTACH-0001",
        )
        rfq = workflows.create_rfq_from_requirement(db, executive, requirement.id)
        assert rfq.supplier_ids
        document = models.Document(
            id="DOC-ASSISTANT-QUOTE", business_number="DOC-2026-9001",
            tenant_id=manager.tenant_id, plant_id=manager.plant_id,
            filename="supplier-quote.pdf", content_type="application/pdf",
            size_bytes=100, storage_key="test/quote.pdf", storage_bucket="quarantine",
            checksum_sha256="a" * 64, status="extracted_needs_review",
            validation_errors=[], uploaded_by_user_id=manager.id,
        )
        job = models.DocumentJob(
            id="DJOB-ASSISTANT-QUOTE", tenant_id=manager.tenant_id,
            plant_id=manager.plant_id, document_id=document.id, status="completed",
        )
        db.add_all([document, job])
        db.flush()
        first = workflows.attach_uploaded_quote_documents(
            db, manager, rfq_id=rfq.id, supplier_id=rfq.supplier_ids[0],
            document_ids=[document.id],
        )
        second = workflows.attach_uploaded_quote_documents(
            db, manager, rfq_id=rfq.id, supplier_id=rfq.supplier_ids[0],
            document_ids=[document.id],
        )
        assert first[0]["quote_id"] == second[0]["quote_id"]
        assert db.query(models.SupplierQuote).filter_by(rfq_id=rfq.id).count() == 1
        assert document.linked_entity_type == "supplier_quote"
        assert document.linked_entity_id == first[0]["quote_id"]


def test_purchase_executive_can_idempotently_assign_supplier_to_material() -> None:
    with SessionLocal() as db:
        executive = _user(db, "purchase.exec@genuinegigs.local")
        supplier = workflows.user_scope_query(db, models.Supplier, executive).first()
        item = models.Item(
            id="ITEM-CAPABILITY-TEST", tenant_id=executive.tenant_id,
            plant_id=executive.plant_id, code="CAP-TEST", name="Capability test material",
            uom_id="KG", erp_item_code="CAP-TEST",
        )
        db.add(item)
        db.flush()

        first = procurement_v2.assign_suppliers_to_material(
            db, executive, item_id=item.id, supplier_ids=[supplier.id], notes="Approved test",
        )
        second = procurement_v2.assign_suppliers_to_material(
            db, executive, item_id=item.id, supplier_ids=[supplier.id], notes="Approved again",
        )

        assert first[0].id == second[0].id
        assert second[0].approved is True
        assert second[0].notes == "Approved again"
        assert workflows.user_scope_query(
            db, models.SupplierItemCapability, executive,
        ).filter_by(item_id=item.id, supplier_id=supplier.id).count() == 1


def test_quotation_upload_cannot_be_downgraded_to_conversational_answer(monkeypatch) -> None:
    with SessionLocal() as db:
        manager = _user(db, "purchase.manager@genuinegigs.local")
        thread = _thread(db, manager)
        document = models.Document(
            id="DOC-QUOTE-ROUTING", business_number="DOC-2026-ROUTING",
            tenant_id=manager.tenant_id, plant_id=manager.plant_id,
            filename="fixture-supplier-4.pdf", content_type="application/pdf",
            size_bytes=100, storage_key="test/routing.pdf", storage_bucket="quarantine",
            checksum_sha256="b" * 64, status="quarantined", validation_errors=[],
            uploaded_by_user_id=manager.id,
        )
        job = models.DocumentJob(
            id="DJOB-QUOTE-ROUTING", tenant_id=manager.tenant_id,
            plant_id=manager.plant_id, document_id=document.id,
            job_type="validate_extract", status="queued",
        )
        db.add_all([document, job])
        db.flush()

        # Reproduce the provider failure from the incident: it returns a
        # generic answer even though the employee supplied quotation files.
        monkeypatch.setattr(
            agent_service,
            "provider_response",
            lambda *_args, **_kwargs: (
                IntentEnvelope(
                    intent="answer_work_context",
                    requested_outcome="Ask for supplier mapping",
                    entities={"_runtime_final": "Provide supplier mappings first."},
                    confidence=0.8,
                ),
                "groq", "test-model", None,
            ),
        )

        run, message = agent_service.run_message(
            db,
            manager,
            thread.id,
            AgentMessageRequest(
                content="Upload these quotations to RFQ-2026-0001",
                attachment_ids=[document.id],
            ),
        )

        assert run.intent == "upload_supplier_quotes"
        assert run.termination_reason == "processing"
        assert "Extracting supplier identity" in message.content
        assert "supplier mapping" not in message.content.casefold()
        state = load_thread_state(thread.context_state)
        assert state.active_goal.capability == "upload_supplier_quotes"
        assert state.continuation_status == "processing"


def test_completed_document_batch_resumes_waiting_agent_once(monkeypatch) -> None:
    with SessionLocal() as db:
        manager = _user(db, "purchase.manager@genuinegigs.local")
        thread = _thread(db, manager)
        membership = db.get(models.WorkspaceMembership, thread.membership_id)
        source = models.AgentMessage(
            tenant_id=manager.tenant_id, plant_id=manager.plant_id,
            thread_id=thread.id, membership_id=membership.id,
            message_type="user", content="Upload these quotations to RFQ-2026-0001",
            correlation_id="AGT-BATCH-SOURCE", visibility="private",
        )
        db.add(source)
        db.flush()
        document_ids = []
        jobs = []
        for index, status in enumerate(("needs_review", "needs_review", "extracting"), 1):
            document = models.Document(
                id=f"DOC-CONT-{index}", business_number=f"DOC-2026-CONT-{index}",
                tenant_id=manager.tenant_id, plant_id=manager.plant_id,
                filename=f"supplier-{index}.pdf", content_type="application/pdf",
                size_bytes=100, storage_key=f"test/continuation-{index}.pdf",
                storage_bucket="quarantine", checksum_sha256=str(index) * 64,
                status="extracted_needs_review", validation_errors=[],
                uploaded_by_user_id=manager.id,
            )
            job = models.DocumentJob(
                id=f"DJOB-CONT-{index}", tenant_id=manager.tenant_id,
                plant_id=manager.plant_id, document_id=document.id,
                status="completed" if status == "needs_review" else "processing",
            )
            db.add_all([document, job])
            db.flush()
            db.add(models.AgentMessageAttachment(
                tenant_id=manager.tenant_id, plant_id=manager.plant_id,
                message_id=source.id, document_id=document.id, file_order=index,
                purpose="quotation", status=status, document_job_id=job.id,
            ))
            document_ids.append(document.id)
            jobs.append(job)
        state = load_thread_state(thread.context_state)
        state.active_goal.capability = "upload_supplier_quotes"
        state.active_goal.status = "resolving"
        state.continuation_status = "processing"
        state.attachment_refs = document_ids
        state.draft_fields = {"rfq_id": "RFQ-2026-0001"}
        persist_thread_state(thread, state)
        db.flush()

        calls = []
        def finish_batch(_db, _user, _membership, _profile, active_thread, *_args):
            calls.append(active_thread.id)
            completed = load_thread_state(active_thread.context_state)
            completed.continuation_status = "completed"
            completed.active_goal.status = "completed"
            persist_thread_state(active_thread, completed)
            return "Linked 3 supplier quotations.", [{
                "type": "field_review", "text": "Linked 3 supplier quotations.",
            }], []

        monkeypatch.setattr(agent_service, "process_intent_envelope", finish_batch)
        assert agent_service.resume_quotation_batch_after_document(db, jobs[0].id) is False
        last_attachment = db.query(models.AgentMessageAttachment).filter_by(
            document_job_id=jobs[-1].id,
        ).one()
        last_attachment.status = "needs_review"
        jobs[-1].status = "completed"
        db.flush()
        assert agent_service.resume_quotation_batch_after_document(db, jobs[-1].id) is True
        assert agent_service.resume_quotation_batch_after_document(db, jobs[-1].id) is False
        assert calls == [thread.id]
        continuation = db.query(models.AgentMessage).filter_by(
            thread_id=thread.id, message_type="agent",
        ).one()
        assert continuation.content == "Linked 3 supplier quotations."


def test_negotiation_agent_prepares_then_requires_confirmation(monkeypatch) -> None:
    with SessionLocal() as db:
        manager = _user(db, "purchase.manager@genuinegigs.local")
        rfq = workflows.user_scope_query(db, models.RFQ, manager).filter(
            models.RFQ.supplier_ids != [],
        ).first()
        assert rfq and rfq.supplier_ids
        supplier_id = rfq.supplier_ids[0]
        monkeypatch.setattr(
            agent_service, "provider_response",
            lambda *_args, **_kwargs: (
                IntentEnvelope(
                    intent="prepare_negotiation_proposal",
                    requested_outcome="Ask for a lower price",
                    entities={
                        "rfq_id": rfq.id, "supplier_id": supplier_id,
                        "target": "Reduce unit price by 3 percent",
                        "drafted_message": "Please review a 3 percent price reduction while retaining delivery terms.",
                    },
                    confidence=1,
                ),
                "groq", "test-model", None,
            ),
        )
        thread = _thread(db, manager)
        db.flush()
        _run, message = agent_service.run_message(
            db, manager, thread.id,
            AgentMessageRequest(content="Negotiate a 3 percent reduction with the selected supplier."),
        )
        assert any(block["type"] == "action_proposal" for block in message.content_blocks), message.content_blocks
        proposal_id = next(
            block["record"]["proposal_id"] for block in message.content_blocks
            if block["type"] == "action_proposal"
        )
        proposal = db.get(models.AgentProposal, proposal_id)
        negotiation = db.get(models.NegotiationRound, proposal.target_entity_id)
        assert negotiation.status == "pending_approval"
        assert load_thread_state(thread.context_state).pending_proposal_id == proposal.id
        assert db.query(models.OutboxMessage).filter(
            models.OutboxMessage.meta["negotiation_id"].as_string() == negotiation.id,
        ).count() == 0
        agent_service.confirm_proposal(db, manager, proposal.id)
        assert negotiation.status == "manager_approved"
        confirmed_state = load_thread_state(thread.context_state)
        assert confirmed_state.pending_proposal_id is None
        assert confirmed_state.last_receipt["action"] == "approve_negotiation"
        assert db.query(models.OutboxMessage).filter(
            models.OutboxMessage.meta["negotiation_id"].as_string() == negotiation.id,
        ).count() == 1


def test_supplier_followup_requires_confirmation_and_is_idempotent(monkeypatch) -> None:
    with SessionLocal() as db:
        executive = _user(db, "purchase.exec@genuinegigs.local")
        rfq = workflows.user_scope_query(db, models.RFQ, executive).filter(
            models.RFQ.supplier_ids != [],
        ).first()
        assert rfq and rfq.supplier_ids
        supplier = workflows.get_scoped_or_404(
            db, models.Supplier, executive, rfq.supplier_ids[0], "Supplier",
        )
        body = "Please confirm whether your quotation remains valid through Friday."
        monkeypatch.setattr(
            agent_service, "provider_response",
            lambda *_args, **_kwargs: (
                IntentEnvelope(
                    intent="prepare_supplier_followup",
                    requested_outcome="Ask the supplier to confirm quote validity",
                    entities={"rfq_id": rfq.id, "supplier_id": supplier.id, "message": body},
                    confidence=1,
                ),
                "groq", "test-model", None,
            ),
        )
        thread = _thread(db, executive)
        db.flush()
        _run, message = agent_service.run_message(
            db, executive, thread.id,
            AgentMessageRequest(content="Ask this supplier whether their quote remains valid."),
        )
        proposal_id = next(
            block["record"]["proposal_id"] for block in message.content_blocks
            if block["type"] == "action_proposal"
        )
        assert db.query(models.OutboxMessage).filter(
            models.OutboxMessage.meta["message_type"].as_string() == "supplier_followup",
        ).count() == 0
        agent_service.confirm_proposal(db, executive, proposal_id)
        messages = db.query(models.OutboxMessage).filter(
            models.OutboxMessage.meta["message_type"].as_string() == "supplier_followup",
        ).all()
        assert len(messages) == 1
        assert messages[0].status == "approved_pending_send"
        assert messages[0].recipient
        duplicate = procurement_v2.prepare_supplier_followup(
            db, executive, rfq.id, supplier.id, body,
        )
        assert duplicate.id == messages[0].id
        assert db.query(models.OutboxMessage).filter(
            models.OutboxMessage.meta["message_type"].as_string() == "supplier_followup",
        ).count() == 1


def test_quote_evidence_agent_proposes_before_applying_decisions(monkeypatch) -> None:
    with SessionLocal() as db:
        manager = _user(db, "purchase.manager@genuinegigs.local")
        quote = workflows.user_scope_query(db, models.SupplierQuote, manager).filter_by(
            verification_status="needs_review",
        ).one()
        fields = workflows.user_scope_query(db, models.QuoteFieldVerification, manager).filter_by(
            quote_id=quote.id,
        ).all()
        decisions = [{"field_name": field.field_name, "decision": "accept"} for field in fields]
        monkeypatch.setattr(
            agent_service, "provider_response",
            lambda *_args, **_kwargs: (
                IntentEnvelope(
                    intent="verify_quote_fields_proposal",
                    requested_outcome="Accept the reviewed extracted fields",
                    entities={"quote_id": quote.id, "decisions": decisions},
                    confidence=1,
                ),
                "groq", "test-model", None,
            ),
        )
        thread = _thread(db, manager)
        db.flush()
        _run, message = agent_service.run_message(
            db, manager, thread.id,
            AgentMessageRequest(content="I checked the source. Accept these extracted fields."),
        )
        assert quote.verification_status == "needs_review"
        proposal_id = next(
            block["record"]["proposal_id"] for block in message.content_blocks
            if block["type"] == "action_proposal"
        )
        agent_service.confirm_proposal(db, manager, proposal_id)
        assert quote.verification_status == "verified"
        assert all(field.status == "verified" for field in fields)
        assert db.query(models.AgentActionReceipt).filter_by(
            tool_name="verify_quote_fields", target_entity_id=quote.id, status="succeeded",
        ).one()


def test_role_agents_prepare_controlled_gate_store_and_quality_handoffs(monkeypatch) -> None:
    with SessionLocal() as db:
        award = db.query(models.AwardDecision).first()
        quote_line = db.query(models.QuoteLine).filter_by(quote_id=award.quote_id).first()
        po = models.PODraft(
            id="PO-AGENT-INBOUND", business_number="PO-2026-9901",
            tenant_id=award.tenant_id, plant_id=award.plant_id,
            award_id=award.id, supplier_id=award.supplier_id,
            status="approved_pending_outbox", oracle_mapping={"quantity": 10},
            currency="INR", payment_terms="30 days", commercial_terms={},
        )
        db.add(po)
        db.add(models.PODraftLine(
            id="POL-AGENT-INBOUND", business_number="POL-2026-9901",
            tenant_id=award.tenant_id, plant_id=award.plant_id,
            po_draft_id=po.id, item_id=quote_line.item_id,
            quantity=10, uom=quote_line.uom, unit_price=quote_line.unit_price,
            gst_rate=quote_line.gst_rate, need_by_date=quote_line.promised_date,
            inspection_required=True,
        ))
        db.flush()

        def run_proposal(email: str, capability: str, entities: dict) -> models.AgentProposal:
            actor = _user(db, email)
            monkeypatch.setattr(
                agent_service, "provider_response",
                lambda *_args, **_kwargs: (
                    IntentEnvelope(
                        intent=capability, requested_outcome="Prepare controlled handoff",
                        entities=entities, confidence=1,
                    ),
                    "groq", "test-model", None,
                ),
            )
            thread = _thread(db, actor)
            db.flush()
            _run, message = agent_service.run_message(
                db, actor, thread.id, AgentMessageRequest(content="Prepare this handoff."),
            )
            proposal_id = next(
                block["record"]["proposal_id"] for block in message.content_blocks
                if block["type"] == "action_proposal"
            )
            proposal = db.get(models.AgentProposal, proposal_id)
            agent_service.confirm_proposal(db, actor, proposal.id)
            db.flush()
            return proposal

        run_proposal(
            "gate.operator@genuinegigs.local", "prepare_gate_entry_proposal",
            {"po_id": po.id, "supplier_challan": "CH-9901", "vehicle_number": "MH12AB9901", "packages_count": 2},
        )
        gate = db.query(models.GateEntry).filter_by(po_draft_id=po.id).one()
        run_proposal(
            "store.manager@genuinegigs.local", "prepare_store_receipt_proposal",
            {"po_id": po.id, "received_quantity": 10, "damaged_quantity": 0},
        )
        receipt = db.query(models.StoreReceipt).filter_by(po_draft_id=po.id).one()
        assert receipt.gate_entry_id == gate.id
        run_proposal(
            "quality.inspector@genuinegigs.local", "prepare_quality_inspection_proposal",
            {"receipt_id": receipt.id, "inspected_quantity": 10, "accepted_quantity": 9, "rejected_quantity": 1, "held_quantity": 0},
        )
        inspection = db.query(models.InspectionResult).filter_by(receipt_id=receipt.id).one()
        assert (inspection.accepted_quantity, inspection.rejected_quantity) == (9, 1)
        assert db.query(models.AgentActionReceipt).filter(
            models.AgentActionReceipt.tool_name.in_([
                "record_gate_entry", "record_store_receipt", "record_inspection",
            ])
        ).count() == 3


def test_procurement_followups_are_scoped_business_linked_and_idempotent() -> None:
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        quote = db.query(models.SupplierQuote).first()
        quote.verification_status = "needs_review"
        quote.version = 4
        failed = models.IntegrationOutboxEvent(
            id="OUTBOX-FOLLOWUP-1", business_number="SYNC-2026-0001",
            tenant_id=quote.tenant_id, plant_id=quote.plant_id,
            provider="excel", action="export_purchase_order",
            entity_type="po_drafts", entity_id="missing-po", status="failed",
            idempotency_key="followup-test-export-po", correlation_id="followup-test",
            request_payload={}, response_payload={}, payload_diff={}, retry_count=2,
            last_error="Read-after-write verification failed",
        )
        db.add(failed)
        db.flush()

        first_count = task_service.run_procurement_followups(db, now)
        db.flush()
        notifications = db.query(models.Notification).filter(
            models.Notification.category.in_([
                "extraction_review_pending", "integration_failure",
            ])
        ).all()
        categories = {notification.category for notification in notifications}

        assert first_count >= 2
        assert {"extraction_review_pending", "integration_failure"} <= categories
        assert all(notification.tenant_id == quote.tenant_id for notification in notifications)
        extraction = next(
            notification for notification in notifications
            if notification.category == "extraction_review_pending"
            and notification.linked_entity_id == quote.id
        )
        assert extraction.navigation_target == f"/quotes?quote={quote.id}"
        assert extraction.membership_id is not None

        for notification in notifications:
            notification.status = "read"
        db.flush()
        assert task_service.run_procurement_followups(db, now) == 0
        db.flush()
        assert db.query(models.Notification).filter(
            models.Notification.dedupe_key.in_([
                notification.dedupe_key for notification in notifications
                if notification.dedupe_key
            ])
        ).count() == len([item for item in notifications if item.dedupe_key])
