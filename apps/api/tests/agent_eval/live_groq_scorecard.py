"""Curated, read-only live Groq intent scorecard.

This is deliberately separate from pytest: it consumes a real provider key.
It exercises the same ``provider_response`` boundary used by ``run_message``
but never executes the selected capability, so it cannot mutate procurement
records or contact an external system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app import agent_service
from app.core.config import get_settings
from app.db import models


@dataclass(frozen=True)
class Scenario:
    message: str
    expected: str


SCENARIOS = (
    Scenario("Hi, what can you help me with?", "answer_work_context"),
    Scenario("What should I work on next?", "list_my_tasks"),
    Scenario("Show my open tasks", "list_my_tasks"),
    Scenario("What material masters do we have?", "list_approved_materials"),
    Scenario("Is Aluminium Ingot approved?", "search_approved_material"),
    Scenario("Create a requirement for Aluminium Ingot, 132 KG, needed in 14 days", "create_purchase_requirement"),
    Scenario("Raise PR for ALI-102 200kg in 30 days because line stock is low", "create_purchase_requirement"),
    Scenario("Generate RFQ for REQ-2026-0033", "prepare_rfq_draft"),
    Scenario("Prepare the RFQ for the latest eligible requirement", "prepare_rfq_draft"),
    Scenario("Attach these supplier quotation files to this RFQ", "upload_supplier_quotes"),
    Scenario("Show me the extracted fields that need verification", "review_quote_extraction"),
    Scenario("Compare the verified quotations for this RFQ", "prepare_supplier_comparison"),
    Scenario("Draft a negotiation proposal for the recommended supplier", "prepare_negotiation_proposal"),
    Scenario("Prepare the approved purchase order email for the supplier", "prepare_po_supplier_email_proposal"),
    Scenario("Summarize current procurement risks", "summarize_procurement_risks"),
    Scenario("Ask the owner of this task for a progress update", "request_task_update"),
    Scenario("Preview this Excel import without committing it", "preview_excel_import"),
    Scenario("Explain the errors in the latest spreadsheet import", "review_excel_import"),
    Scenario("Match this supplier invoice against the PO and receipts", "match_supplier_invoice"),
    Scenario("Prepare this matched invoice for finance review", "prepare_finance_handoff_proposal"),
)

ALLOWED_CAPABILITIES = sorted({scenario.expected for scenario in SCENARIOS})


def main() -> int:
    settings = get_settings()
    if not settings.groq_api_key:
        print(json.dumps({"status": "not_run", "reason": "credentials unavailable"}))
        return 2

    profile = models.AgentProfile(
        id="live-scorecard",
        tenant_id="scorecard",
        plant_id="scorecard",
        user_id="scorecard",
        role="admin",
        display_name="Live provider scorecard",
        provider="groq",
        model_profile=settings.agent_primary_model,
        token_budget=min(settings.agent_default_token_budget, 1200),
        prompt_version="role-playbook@2",
        policy_version="agent-policy@2",
        enabled=True,
    )
    results: list[dict[str, object]] = []
    for scenario in SCENARIOS:
        envelope, provider, model, error = agent_service.provider_response(
            profile,
            scenario.message,
            {
                "allowed_capability_ids": ALLOWED_CAPABILITIES,
                "selected_page": {"path": "/control-centre"},
                "recent_entities": [],
                "attachments": (
                    [{"document_id": "scorecard-document", "filename": "supplier-quote.pdf"}]
                    if "Attach these" in scenario.message
                    else []
                ),
                "external_writes_enabled": False,
                "scorecard_mode": True,
            },
            [],
            {},
        )
        passed = provider == "groq" and error is None and envelope.intent == scenario.expected
        results.append(
            {
                "expected": scenario.expected,
                "selected": envelope.intent,
                "provider": provider,
                "passed": passed,
            }
        )

    passed_count = sum(bool(result["passed"]) for result in results)
    score = passed_count / len(results)
    report = {
        "status": "passed" if score >= 0.85 else "failed",
        "provider": "groq",
        "model": settings.agent_primary_model,
        "prompt_version": profile.prompt_version,
        "external_writes_enabled": False,
        "passed": passed_count,
        "total": len(results),
        "score": round(score, 4),
        "threshold": 0.85,
        "results": results,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
