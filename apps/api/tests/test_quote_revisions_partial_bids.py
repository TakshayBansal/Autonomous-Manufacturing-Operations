import pytest
from fastapi import HTTPException
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.domains import workflows


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def _add_second_rfq_line(db, user, rfq):
    second_item = models.Item(
        tenant_id=user.tenant_id, plant_id=user.plant_id, code="COP-REV-1",
        erp_item_code="COP-REV-1", name="Copper Ingot Revision Test", uom_id="KG",
    )
    db.add(second_item); db.flush()
    line = models.RFQLine(
        tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id=rfq.id,
        item_id=second_item.id, description=second_item.name, quantity=50, uom="KG",
        need_by_date="2026-08-31", required_certificates=[],
    )
    db.add(line); db.flush()
    return line


def test_supplier_partial_bid_and_revision_preserve_history():
  with SessionLocal() as db_session:
    user = db_session.query(models.User).filter_by(email="admin@genuinegigs.local").one()
    rfq = db_session.query(models.RFQ).first()
    first_line = db_session.query(models.RFQLine).filter_by(rfq_id=rfq.id).first()
    second_line = _add_second_rfq_line(db_session, user, rfq)
    supplier_id = rfq.supplier_ids[0]
    prior = db_session.query(models.SupplierQuote).filter_by(
        rfq_id=rfq.id, supplier_id=supplier_id,
    ).filter(models.SupplierQuote.verification_status != "superseded").order_by(
        models.SupplierQuote.revision_number.desc(), models.SupplierQuote.created_at.desc(),
    ).first()
    base_revision = prior.revision_number if prior else 0
    raw_token = workflows.create_supplier_portal_token(db_session, user, rfq, supplier_id)
    db_session.flush()

    first = workflows.receive_supplier_quote(db_session, raw_token, {
        "quote_number": "REV-100", "currency": "USD", "exchange_rate_to_inr": 84,
        "lines": [{"rfq_line_id": first_line.id, "quantity": first_line.quantity,
                   "unit_price": 2, "promised_date": first_line.need_by_date,
                   "technical_compliance": "compliant", "certificates": []}],
    })
    db_session.flush()
    assert first.revision_number == base_revision + 1
    assert first.participation_status == "partial"
    assert db_session.query(models.QuoteLine).filter_by(quote_id=first.id).count() == 1

    revised = workflows.receive_supplier_quote(db_session, raw_token, {
        "quote_number": "REV-100-R2", "currency": "USD", "exchange_rate_to_inr": 85,
        "lines": [
            {"rfq_line_id": first_line.id, "quantity": first_line.quantity,
             "unit_price": 1.9, "promised_date": first_line.need_by_date,
             "technical_compliance": "compliant", "certificates": []},
            {"rfq_line_id": second_line.id, "quantity": 25, "unit_price": 3,
             "promised_date": second_line.need_by_date,
             "technical_compliance": "compliant", "certificates": []},
        ],
    })
    db_session.flush()
    assert revised.revision_number == base_revision + 2
    assert revised.supersedes_quote_id == first.id
    assert revised.participation_status == "partial"  # all lines offered, one only partly fulfilled
    assert first.verification_status == "superseded"
    assert db_session.query(models.QuoteLine).filter_by(quote_id=first.id).count() == 1
    assert db_session.query(models.QuoteLine).filter_by(quote_id=revised.id).count() == 2
    assert workflows.get_supplier_portal_token(db_session, raw_token).status == "active"


def test_quote_rejects_unknown_or_excess_line():
  with SessionLocal() as db_session:
    user = db_session.query(models.User).filter_by(email="admin@genuinegigs.local").one()
    rfq = db_session.query(models.RFQ).first()
    line = db_session.query(models.RFQLine).filter_by(rfq_id=rfq.id).first()
    token = workflows.create_supplier_portal_token(db_session, user, rfq, rfq.supplier_ids[0])
    db_session.flush()
    with pytest.raises(HTTPException) as error:
        workflows.receive_supplier_quote(db_session, token, {
            "lines": [{"rfq_line_id": line.id, "quantity": line.quantity + 1, "unit_price": 1}],
        })
    assert error.value.status_code == 422
