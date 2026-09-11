import pytest

from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.domains import workflows


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def test_governed_negotiation_counteroffer_requires_quote_reverification() -> None:
    with SessionLocal() as db:
        manager = db.query(models.User).filter_by(
            email="purchase.manager@genuinegigs.local",
        ).one()
        quote = workflows.user_scope_query(db, models.SupplierQuote, manager).filter_by(
            verification_status="verified",
        ).first()
        assert quote is not None
        assert workflows.user_scope_query(db, models.SupplierContact, manager).filter_by(
            supplier_id=quote.supplier_id,
        ).first() is not None

        negotiation = workflows.create_negotiation(
            db, manager, quote.rfq_id, quote.supplier_id,
            "Reduce the unit price while retaining delivery",
            "Please offer a lower unit price without changing the promised delivery.",
        )
        workflows.submit_negotiation(db, manager, negotiation.id)
        db.flush()
        assert negotiation.status == "pending_approval"
        assert workflows.user_scope_query(db, models.OutboxMessage, manager).filter(
            models.OutboxMessage.meta["negotiation_id"].as_string() == negotiation.id,
        ).count() == 0

        workflows.approve_negotiation(db, manager, negotiation.id)
        db.flush()
        outbound = workflows.user_scope_query(db, models.OutboxMessage, manager).filter(
            models.OutboxMessage.meta["negotiation_id"].as_string() == negotiation.id,
        ).one()
        assert outbound.status == "approved_pending_send"

        original_lines = workflows.user_scope_query(db, models.QuoteLine, manager).filter_by(
            quote_id=quote.id,
        ).all()
        assert original_lines
        revised_price = min(line.unit_price for line in original_lines) - 1
        workflows.record_negotiation_counteroffer(
            db, manager, negotiation.id, revised_price,
            "We can accept the revised unit price.",
            {"delivery_unchanged": True},
        )
        workflows.accept_negotiation(db, manager, negotiation.id)
        db.flush()

        assert negotiation.status == "accepted_pending_reverification"
        assert quote.verification_status == "needs_review"
        assert all(line.unit_price == revised_price for line in original_lines)
        price_evidence = workflows.user_scope_query(
            db, models.QuoteFieldVerification, manager,
        ).filter_by(quote_id=quote.id, status="needs_review").all()
        assert price_evidence

        workflows.verify_quote_fields(
            db, manager, quote.id,
            [
                {
                    "field_name": evidence.field_name,
                    "decision": "accept",
                    "verified_value": str(revised_price),
                }
                for evidence in price_evidence
            ],
        )
        db.flush()
        assert quote.verification_status == "verified"

        # The seeded RFQ also contains an intentionally uncertain competing
        # quotation. Comparison must remain blocked until that evidence is
        # explicitly reviewed as well.
        for competing in workflows.user_scope_query(
            db, models.SupplierQuote, manager,
        ).filter_by(rfq_id=quote.rfq_id).all():
            if competing.verification_status == "verified":
                continue
            pending = workflows.user_scope_query(
                db, models.QuoteFieldVerification, manager,
            ).filter_by(quote_id=competing.id, status="needs_review").all()
            workflows.verify_quote_fields(
                db, manager, competing.id,
                [
                    {
                        "field_name": evidence.field_name,
                        "decision": "accept",
                    }
                    for evidence in pending
                ],
            )
        db.flush()

        comparison = workflows.generate_comparison(db, manager, quote.rfq_id)
        db.flush()
        supplier_rows = [
            row for row in comparison.rows
            if row["supplier_id"] == quote.supplier_id
        ]
        assert supplier_rows
        assert all(
            row["base_cost"]
            == revised_price * row["offered_quantity"] * row["exchange_rate_to_inr"]
            for row in supplier_rows
        )
        actions = {
            row.action for row in workflows.user_scope_query(
                db, models.AuditEvent, manager,
            ).filter(models.AuditEvent.entity_id == negotiation.id).all()
        }
        assert {
            "negotiation.created",
            "negotiation.submitted",
            "negotiation.approved",
            "negotiation.counteroffer_recorded",
            "negotiation.counteroffer_accepted",
        } <= actions
