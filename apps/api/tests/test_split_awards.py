from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import procurement_v2
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def test_split_award_creates_one_immutable_po_per_supplier(monkeypatch: pytest.MonkeyPatch) -> None:
    def artifact_after_lines_are_visible(db, _user, _artifact_type, entity_id, **_kwargs):
        assert db.query(models.PODraftLine).filter_by(po_draft_id=entity_id).count() > 0
        return SimpleNamespace(id="ART-SPLIT", document_id="DOC-SPLIT")

    monkeypatch.setattr(procurement_v2, "generate_artifact", artifact_after_lines_are_visible)
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        first_quote = db.query(models.SupplierQuote).filter_by(verification_status="verified").first()
        rfq = db.get(models.RFQ, first_quote.rfq_id)
        rfq_line = db.query(models.RFQLine).filter_by(rfq_id=rfq.id).first()
        first_line = db.query(models.QuoteLine).filter_by(quote_id=first_quote.id).first()
        first_line.rfq_line_id = rfq_line.id
        first_line.item_id = rfq_line.item_id
        first_line.quantity = rfq_line.quantity
        second_supplier = db.query(models.Supplier).filter(models.Supplier.id != first_quote.supplier_id).first()
        second_quote = models.SupplierQuote(
            tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id,
            supplier_id=second_supplier.id, quote_number="SPLIT-Q2", quote_date="2026-07-22",
            validity_date="2026-08-22", payment_terms="30 days", parser_version="test",
            model_version="deterministic", verification_status="verified", revision_number=1,
            participation_status="complete", currency="INR", exchange_rate_to_inr=1,
        )
        db.add(second_quote); db.flush()
        second_line = models.QuoteLine(
            tenant_id=user.tenant_id, plant_id=user.plant_id, quote_id=second_quote.id,
            rfq_line_id=rfq_line.id, item_id=rfq_line.item_id, quantity=rfq_line.quantity,
            uom=rfq_line.uom, unit_price=first_line.unit_price + 1, gst_rate=18,
            freight=0, packaging=0, lead_time_days=10, promised_date=rfq_line.need_by_date,
            moq=1, technical_compliance="compliant", certificates=rfq_line.required_certificates,
            tax_recoverable=True, nonrecoverable_tax=0, deviation_notes="",
        )
        db.add(second_line); db.flush()
        comparison = db.query(models.BidComparison).filter_by(rfq_id=rfq.id).first()
        if comparison is None:
            comparison = models.BidComparison(
                tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id,
                status="approved", rows=[], recommended_supplier_id=first_quote.supplier_id,
                recommendation_rationale="Approved split source", comparison_version=1,
            )
            db.add(comparison)
        else:
            comparison.status = "approved"
        db.flush()
        first_quantity = round(rfq_line.quantity * 0.6, 3)
        second_quantity = rfq_line.quantity - first_quantity
        allocations = [
            {"rfq_line_id": rfq_line.id, "quote_line_id": first_line.id, "awarded_quantity": first_quantity, "rationale": "Primary source"},
            {"rfq_line_id": rfq_line.id, "quote_line_id": second_line.id, "awarded_quantity": second_quantity, "rationale": "Supply continuity"},
        ]
        batch, purchase_orders = procurement_v2.confirm_split_purchase_orders(db, user, comparison.id, allocations)
        db.flush()
        assert batch.total_awarded_quantity == rfq_line.quantity
        assert len(purchase_orders) == 2
        assert len({po.supplier_id for po in purchase_orders}) == 2
        assert sum(line.quantity for po in purchase_orders for line in db.query(models.PODraftLine).filter_by(po_draft_id=po.id)) == rfq_line.quantity
        assert db.query(models.AwardLine).join(models.AwardDecision).filter(models.AwardDecision.award_batch_id == batch.id).count() == 2
        assert all(po.status == "approved_pending_outbox" for po in purchase_orders)
        assert db.query(models.IntegrationOutboxEvent).filter(models.IntegrationOutboxEvent.entity_id.in_([po.id for po in purchase_orders])).count() == 2

        replay_batch, replay_orders = procurement_v2.confirm_split_purchase_orders(db, user, comparison.id, list(reversed(allocations)))
        assert replay_batch.id == batch.id
        assert {po.id for po in replay_orders} == {po.id for po in purchase_orders}
        with pytest.raises(HTTPException, match="already has a confirmed"):
            changed = [dict(allocations[0], awarded_quantity=first_quantity - 1), dict(allocations[1], awarded_quantity=second_quantity + 1)]
            procurement_v2.confirm_split_purchase_orders(db, user, comparison.id, changed)


def test_split_award_rejects_over_allocation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(procurement_v2, "generate_artifact", lambda *_a, **_k: SimpleNamespace(id="A", document_id="D"))
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        quote = db.query(models.SupplierQuote).filter_by(verification_status="verified").first()
        quote_line = db.query(models.QuoteLine).filter_by(quote_id=quote.id).first()
        rfq_line = db.query(models.RFQLine).filter_by(rfq_id=quote.rfq_id).first()
        quote_line.rfq_line_id = rfq_line.id
        quote_line.item_id = rfq_line.item_id
        comparison = db.query(models.BidComparison).filter_by(rfq_id=quote.rfq_id).first()
        comparison.status = "approved"
        with pytest.raises(HTTPException, match="exceeds"):
            procurement_v2.confirm_split_purchase_orders(db, user, comparison.id, [{
                "rfq_line_id": rfq_line.id, "quote_line_id": quote_line.id,
                "awarded_quantity": max(rfq_line.quantity, quote_line.quantity) + 1,
            }])
