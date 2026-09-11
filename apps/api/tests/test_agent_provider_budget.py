from types import SimpleNamespace

from app import agent_service, documents
from app.agent_capabilities import CAPABILITY_REGISTRY
from app.agent_runtime import run_bounded_tool_loop
from app.agent_schemas import IntentEnvelope
from app.agent_state import apply_intent, load_thread_state


def test_exact_quote_upload_gets_relevant_tools_without_material_or_invoice_tools() -> None:
    selected = agent_service.lifecycle_capability_ids(
        "Upload these quotations for RFQ-2026-0001",
        {
            "attachments": [{
                "document_id": "DOC-1",
                "content_type": "application/pdf",
            }],
            "thread_state": {},
        },
        list(CAPABILITY_REGISTRY),
    )

    assert "upload_supplier_quotes" in selected
    assert "review_quote_extraction" in selected
    assert "create_material_master_request" not in selected
    assert "prepare_invoice_from_attachment" not in selected


def test_provider_request_is_compact_and_bounded(monkeypatch) -> None:
    captured: dict = {}

    class FakeBoundModel:
        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(tool_calls=[{
                "name": "upload_supplier_quotes",
                "args": {
                    "requested_outcome": "Upload quotations",
                    "entities": {
                        "attachment_mappings": [{
                            "attachment_reference": "quote-0.pdf",
                            "supplier_reference": "Supplier Zero",
                        }],
                    },
                },
            }], content="")

    class FakeChatGroq:
        def __init__(self, **kwargs):
            captured["model_kwargs"] = kwargs

        def bind_tools(self, tools, tool_choice):
            captured["tools"] = tools
            captured["tool_choice"] = tool_choice
            return FakeBoundModel()

    settings = SimpleNamespace(
        groq_api_key="test-key",
        ai_provider="groq",
        agent_primary_model="openai/gpt-oss-120b",
        agent_max_run_seconds=45,
        agent_planning_max_output_tokens=1200,
        agent_provider_request_target_tokens=6800,
        agent_recent_raw_turns=4,
    )
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    monkeypatch.setattr("langchain_groq.ChatGroq", FakeChatGroq)

    context = {
        "role": "admin",
        "thread_type": "personal",
        "allowed_capability_ids": list(CAPABILITY_REGISTRY),
        "approved_knowledge": [{
            "id": f"K-{index}", "title": f"Policy {index}", "content": "x" * 4000,
        } for index in range(20)],
        "attachments": [{
            "document_id": f"DOC-{index}", "filename": f"quote-{index}.pdf",
            "content_type": "application/pdf", "validation_status": "validated",
        } for index in range(3)],
        "thread_state": {
            "selected_context": {"entity_type": "rfq", "business_number": "RFQ-2026-0001"},
            "draft_fields": {"rfq_number": "RFQ-2026-0001"},
        },
    }
    history = [
        {"id": str(index), "role": "user", "content": "irrelevant old detail " * 500}
        for index in range(10)
    ]
    profile = SimpleNamespace(
        provider="groq", model_profile="openai/gpt-oss-120b", token_budget=8000,
    )

    decision, provider, _model, error = agent_service.provider_response(
        profile,
        "Upload these quotations for RFQ-2026-0001",
        context,
        history,
        {"rfq_number": "RFQ-2026-0001"},
    )

    assert provider == "groq" and error is None
    assert decision.intent == "upload_supplier_quotes"
    assert decision.entities["attachment_mappings"][0] == {
        "attachment_reference": "quote-0.pdf",
        "supplier_reference": "Supplier Zero",
    }
    assert captured["model_kwargs"]["max_tokens"] == 1200
    assert len(captured["messages"]) == 2
    serialized_prompt = captured["messages"][1].content
    assert "x" * 100 not in serialized_prompt
    assert len(captured["tools"]) < len(CAPABILITY_REGISTRY)
    quote_tool = next(
        tool for tool in captured["tools"]
        if tool["function"]["name"] == "upload_supplier_quotes"
    )
    mapping_schema = quote_tool["function"]["parameters"]["properties"][
        "entities"
    ]["properties"]["attachment_mappings"]
    assert mapping_schema["type"] == "array"
    estimated = (
        agent_service.estimate_provider_tokens(captured["messages"][0].content)
        + agent_service.estimate_provider_tokens(serialized_prompt)
        + agent_service.estimate_provider_tokens(captured["tools"])
        + captured["model_kwargs"]["max_tokens"]
    )
    assert estimated <= settings.agent_provider_request_target_tokens


def test_quote_extraction_uses_bounded_strict_schema_model(monkeypatch) -> None:
    captured: dict = {}

    class FakeStructuredModel:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return documents.ExtractedQuotation(quote_number="Q-100")

    class FakeChatGroq:
        def __init__(self, **kwargs):
            captured["model_kwargs"] = kwargs

        def with_structured_output(self, schema, **kwargs):
            captured["schema"] = schema
            captured["structured_kwargs"] = kwargs
            return FakeStructuredModel()

    settings = SimpleNamespace(
        ai_provider="groq", groq_api_key="test-key",
        agent_extraction_model="openai/gpt-oss-20b",
        parser_timeout_seconds=45,
    )
    monkeypatch.setattr(documents, "get_settings", lambda: settings)
    monkeypatch.setattr("langchain_groq.ChatGroq", FakeChatGroq)

    result = documents._groq_extract_quote("quotation evidence " * 5000)

    assert result["quote_number"] == "Q-100"
    assert captured["model_kwargs"]["model"] == "openai/gpt-oss-20b"
    assert captured["model_kwargs"]["max_tokens"] == 512
    assert captured["structured_kwargs"] == {"method": "json_schema", "strict": False}
    assert len(captured["prompt"]) < 6200


def test_v2_attachment_snapshots_migrate_to_v3_references_and_aliases_normalize() -> None:
    state = load_thread_state({
        "schema_version": 2,
        "attachments": [{"document_id": "DOC-1", "status": "stale"}],
    })
    state = apply_intent(
        state,
        IntentEnvelope(
            intent="upload_supplier_quotes",
            requested_outcome="Continue the batch",
            entities={
                "supplier_name": "Apex Metals",
                "rfq_number": "RFQ-2026-0001",
            },
            confidence=1,
        ),
        provenance_message_id="MSG-2",
    )
    assert state.schema_version == 3
    assert state.attachment_refs == ["DOC-1"]
    assert state.draft_fields["supplier_reference"] == "Apex Metals"
    assert state.draft_fields["rfq_reference"] == "RFQ-2026-0001"


def test_clarification_and_processing_never_count_as_mutations() -> None:
    for status in ("needs_clarification", "processing"):
        result = run_bounded_tool_loop(
            {"messages": [], "observations": []},
            decide=lambda _state: {
                "type": "tool", "tool": "upload_supplier_quotes",
            },
            execute=lambda _request, value=status: {
                "status": value,
                "business_summary": value,
            },
            tool_categories={"upload_supplier_quotes": "mutation"},
        )
        assert result["mutation_count"] == 0
        assert result["termination_reason"] == (
            "needs_clarification" if status == "needs_clarification" else "processing"
        )


def test_clear_supplier_letterhead_resolves_without_a_label_or_model() -> None:
    suppliers = [
        SimpleNamespace(name="Fixture Supplier 1", erp_vendor_id="EXT-SUP-001"),
        SimpleNamespace(name="Fixture Supplier 5", erp_vendor_id="EXT-SUP-005"),
    ]
    supplier, evidence = agent_service.exact_supplier_identity_from_text(
        "FIXTURE SUPPLIER 5\nQuotation Q-005\nThank you for your enquiry.",
        suppliers,
    )
    assert supplier.name == "Fixture Supplier 5"
    assert evidence == "exact_document_supplier_name"
