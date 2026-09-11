import pytest

from app.agent_service import deterministic_intent


SCENARIOS = [
    ("Create a requirement for Aluminium Ingot 100 KG needed next month", "create_purchase_requirement"),
    ("Raise a requirement for item ALI-102 quantity 100 kg in 30 days", "create_purchase_requirement"),
    ("Generate RFQ for REQ-2026-0033", "prepare_rfq_draft"),
    ("Prepare the RFQ for the latest requirement", "prepare_rfq_draft"),
    ("Draft an RFQ for the aluminium requirement", "prepare_rfq_draft"),
    ("List approved materials", "list_approved_materials"),
    ("What material masters are available", "list_approved_materials"),
    ("Create a new material master for Titanium Ingot", "create_material_master_request"),
    ("Compare supplier quotations for the selected RFQ", "prepare_supplier_comparison"),
    ("Create the supplier comparison from verified quotes", "prepare_supplier_comparison"),
]
NOISE = [
    "", " please", " today", " for production", " as soon as practical",
    " in this plant", " using approved records", " and show the result",
    " without sending anything externally", " — thanks",
]


@pytest.mark.parametrize(
    ("message", "expected"),
    [(base + noise, expected) for base, expected in SCENARIOS for noise in NOISE],
    ids=[f"agent_eval_{index:03d}" for index in range(100)],
)
def test_100_paraphrase_and_noise_contracts(message: str, expected: str) -> None:
    result = deterministic_intent(message, {})
    assert result.intent == expected
    assert result.confidence >= 0.9
    assert "{}" not in result.requested_outcome


# Explicit edge cases complement the paraphrase matrix. These are intentionally
# distinct workplace requests rather than suffix permutations.
EDGE_SCENARIOS = [
    ("Genrate RFQ for REQ-2026-0033", "prepare_rfq_draft"),
    ("Please genrate the rfq for my latest requirement", "prepare_rfq_draft"),
    ("Draft RFQ against the requirement on this page", "prepare_rfq_draft"),
    ("Create rfqs for REQ-2026-0033", "prepare_rfq_draft"),
    ("Prepare RFQ for that PR", "prepare_rfq_draft"),
    ("Raise a requirment for Aluminium Ingot 25 KG in 14 days", "create_purchase_requirement"),
    ("Create reqirement ALI-102 132 kg in 30 days", "create_purchase_requirement"),
    ("Make a reqirement for Copper Ingot 1 tonne next Friday", "create_purchase_requirement"),
    ("Complete the PR for ALI-102 40 KG", "create_purchase_requirement"),
    ("Raise PR for Copper Ingot 75 KG", "create_purchase_requirement"),
    ("Create requirement for ALI-102, 200KG to be received in 30 days", "create_purchase_requirement"),
    ("Make requirement for aluminium ingot 100 kilograms by 31/08/2026", "create_purchase_requirement"),
    ("Raise requirement for copper ingot 500 KG at month-end", "create_purchase_requirement"),
    ("Create requirement for bearing sleeve 20 EA one month from now", "create_purchase_requirement"),
    ("Complete requirement for ALI-102 90 KG because line stock is low", "create_purchase_requirement"),
    ("Request a new material master for Titanium Ingot", "create_material_master_request"),
    ("Raise new master for nickel alloy", "create_material_master_request"),
    ("Create material master for food-grade lubricant", "create_material_master_request"),
    ("Request new master for imported copper cathode", "create_material_master_request"),
    ("Create a new master for refractory brick", "create_material_master_request"),
    ("Compare quotations for RFQ-2026-0032", "prepare_supplier_comparison"),
    ("Comparision of supplier quotes for this RFQ", "prepare_supplier_comparison"),
    ("Compare supplier quote revisions for that RFQ", "prepare_supplier_comparison"),
    ("Prepare comparison of quotations received", "prepare_supplier_comparison"),
    ("Comparison of supplier quotations for RFQ-2026-0032", "prepare_supplier_comparison"),
    ("List materials approved in Pune plant", "list_approved_materials"),
    ("What material masters do we have", "list_approved_materials"),
    ("List approved material", "list_approved_materials"),
    ("What material master is available", "list_approved_materials"),
    ("List approved materials for procurement", "list_approved_materials"),
    ("Find Aluminium Ingot", "search_approved_material"),
    ("Is ALI-102 an approved item", "search_approved_material"),
    ("Show Copper Ingot", "search_approved_material"),
    ("Check item COP-201", "search_approved_material"),
    ("Do we have bearing sleeve in material master", "search_approved_material"),
    ("Hi", "answer_work_context"),
    ("What should I work on next?", "answer_work_context"),
    ("Explain the record open on this page", "answer_work_context"),
    ("What is blocking my work?", "answer_work_context"),
    ("Can you help me?", "answer_work_context"),
    ("Upload these quotation files", "upload_supplier_quotes"),
    ("Attach this quote to the selected RFQ", "upload_supplier_quotes"),
    ("Upload supplier quotation evidence", "upload_supplier_quotes"),
    ("Attach quotation PDF to that RFQ", "upload_supplier_quotes"),
    ("Upload the quote received from the supplier", "upload_supplier_quotes"),
    ("Create requirement for AL1-102 Aluminium Ingot 200 KG in 30 days", "create_purchase_requirement"),
    ("Generate the RFQ for the latest eligible requirement", "prepare_rfq_draft"),
    ("Compare quotes for the RFQ I just opened", "prepare_supplier_comparison"),
    ("Request a new material master and keep my requirement draft", "create_material_master_request"),
    ("Raise a requirement for raw material Copper Ingot 300 KG next Friday", "create_purchase_requirement"),
]


@pytest.mark.parametrize(("message", "expected"), EDGE_SCENARIOS, ids=[f"agent_edge_{index:03d}" for index in range(50)])
def test_50_explicit_procurement_edge_contracts(message: str, expected: str) -> None:
    attachments = ["document-id"] if expected == "upload_supplier_quotes" else []
    result = deterministic_intent(message, {}, attachments)
    assert result.intent == expected
    assert result.requested_outcome == message


def test_agent_evaluation_corpus_meets_minimum_150_scenarios() -> None:
    assert len(SCENARIOS) * len(NOISE) + len(EDGE_SCENARIOS) >= 150
