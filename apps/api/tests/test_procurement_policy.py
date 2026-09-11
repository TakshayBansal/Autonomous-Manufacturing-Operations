import pytest

from app import procurement_policy, agent_service
from app.agent_schemas import AgentMessageRequest, ThreadCreateRequest
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def _comparison(db):
    comparison = db.query(models.BidComparison).first()
    assert comparison is not None
    comparison.status = "draft"
    return comparison


def test_policy_versions_activate_exclusively_and_are_audited() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        first = procurement_policy.create_policy(db, admin, "Plant policy", {"minimum_quotation_count": 2})
        procurement_policy.activate_policy(db, admin, first.id)
        second = procurement_policy.create_policy(db, admin, "Plant policy", {"minimum_quotation_count": 3})
        assert second.policy_version == 2
        procurement_policy.activate_policy(db, admin, second.id)
        db.flush()
        assert first.status == "retired"
        assert second.status == "active"
        assert db.query(models.AuditEvent).filter_by(entity_type="procurement_policy", entity_id=second.id, action="procurement_policy.activated").count() == 1


def test_minimum_quote_policy_blocks_without_justification_and_records_evidence() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        policy = procurement_policy.create_policy(db, admin, "Competitive sourcing", {
            "minimum_quotation_count": 20,
            "require_unexpired_quotes": False,
            "allowed_currencies": ["INR"],
        })
        procurement_policy.activate_policy(db, admin, policy.id)
        db.flush()
        assert procurement_policy.active_policy(db, admin).rules["minimum_quotation_count"] == 20
        comparison = _comparison(db)
        blocked = procurement_policy.evaluate_comparison(db, admin, comparison, "Best price")
        assert blocked["decision"] == "blocked"
        assert next(row for row in blocked["findings"] if row["rule"] == "minimum_quotation_count")["required"] == 20
        justified = procurement_policy.evaluate_comparison(db, admin, comparison, "Emergency single source purchase due to line stoppage")
        assert justified["decision"] == "requires_justification"
        evaluation = db.query(models.ProcurementPolicyEvaluation).filter_by(entity_id=comparison.id).one()
        assert evaluation.decision == "requires_justification"
        assert evaluation.required_approval_roles == ["plant_manager", "purchase_executive"]


def test_currency_validity_and_segregation_are_deterministic_blockers() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        comparison = _comparison(db)
        rfq = db.get(models.RFQ, comparison.rfq_id)
        requirement = db.get(models.PurchaseRequirement, rfq.requirement_id)
        membership = db.query(models.WorkspaceMembership).filter_by(user_id=admin.id, tenant_id=admin.tenant_id, status="active").one()
        requirement.created_by_membership_id = membership.id
        quote = db.query(models.SupplierQuote).filter_by(rfq_id=rfq.id, verification_status="verified").first()
        assert quote is not None
        quote.currency = "USD"
        quote.validity_date = "2020-01-01"
        policy = procurement_policy.create_policy(db, admin, "Strict evidence", {
            "minimum_quotation_count": 1,
            "allowed_currencies": ["INR"],
            "require_unexpired_quotes": True,
            "segregation": {"requester_cannot_submit_comparison": True},
        })
        procurement_policy.activate_policy(db, admin, policy.id)
        db.flush()
        assert policy.rules["require_unexpired_quotes"] is True
        assert policy.rules["segregation"]["requester_cannot_submit_comparison"] is True
        result = procurement_policy.evaluate_comparison(db, admin, comparison, "")
        assert result["decision"] == "blocked"
        assert {row["rule"] for row in result["findings"]} >= {"allowed_currencies", "quote_validity", "segregation_of_duties"}


def test_role_agent_explains_active_policy_from_persisted_rules() -> None:
    with SessionLocal() as db:
        admin = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        policy = procurement_policy.create_policy(db, admin, "Client purchasing policy", {
            "minimum_quotation_count": 2, "allowed_currencies": ["INR", "USD"],
            "require_unexpired_quotes": True, "allow_split_awards": False,
        })
        procurement_policy.activate_policy(db, admin, policy.id)
        db.flush()
        thread = agent_service.create_thread(db, admin, ThreadCreateRequest(thread_type="personal", title="Policy help"))
        db.flush()
        _run, message = agent_service.run_message(db, admin, thread.id, AgentMessageRequest(
            content="Explain our purchasing policy", requested_capability="explain_procurement_policy",
        ))
        assert "Client purchasing policy version 1 is active" in message.content
        assert any("Minimum verified quotations: 2" in item for block in message.content_blocks for item in block.get("items", []))
        assert "agent-policy" not in message.content
