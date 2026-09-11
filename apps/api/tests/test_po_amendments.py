from types import SimpleNamespace
import hashlib
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app import procurement_v2
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.domains import workflows
from app.integrations import dispatch_event_by_id


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def _issued_po(db):
    user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
    award = db.query(models.AwardDecision).first()
    quote_line = db.query(models.QuoteLine).filter_by(quote_id=award.quote_id).first()
    po = models.PODraft(
        tenant_id=user.tenant_id, plant_id=user.plant_id, award_id=award.id,
        supplier_id=award.supplier_id, status="simulated_posted",
        oracle_mapping={"lines": [{"item_code": "TEST", "quantity": 10, "uom": "KG", "unit_price": 100, "need_by_date": "2026-08-31"}]},
        currency="INR", payment_terms="30 days", commercial_terms={},
        revision_number=1, revision_kind="original",
    )
    db.add(po); db.flush()
    line = models.PODraftLine(
        tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id,
        item_id=quote_line.item_id, quantity=10, uom="KG", unit_price=100,
        gst_rate=18, need_by_date="2026-08-31", inspection_required=True,
    )
    db.add(line); db.flush()
    return user, po, line


def test_po_amendment_preserves_issued_version_and_reissues_after_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(procurement_v2, "generate_artifact", lambda *_a, **_k: SimpleNamespace(id="ART-AMEND", document_id="DOC-AMEND"))
    with SessionLocal() as db:
        user, original, line = _issued_po(db)
        original_quantity = line.quantity
        revision = procurement_v2.prepare_po_change(db, user, original.id, "amendment", "Delivery plan changed", [{
            "line_id": line.id, "quantity": original_quantity + 5, "need_by_date": "2026-09-15",
        }])
        db.flush()
        changed_line = db.query(models.PODraftLine).filter_by(po_draft_id=revision.id).one()
        assert revision.previous_version_id == original.id
        assert revision.root_po_id == original.id
        assert revision.revision_number == 2
        assert changed_line.quantity == original_quantity + 5
        assert line.quantity == original_quantity
        assert original.status == "simulated_posted"
        with pytest.raises(HTTPException, match="Inbound activity is paused"):
            workflows.create_asn(db, user, original.id, 1, "MH12PAUSED")
        procurement_v2.approve_po_change(db, user, revision.id)
        db.flush()
        event = db.query(models.IntegrationOutboxEvent).filter_by(entity_id=revision.id, action="amend_purchase_order").one()
        workflows.approve_integration_outbox_event(db, user, event.id)
        db.commit()
        event_id, original_id, revision_id = event.id, original.id, revision.id

    assert dispatch_event_by_id(event_id) == "simulated"
    with SessionLocal() as db:
        original = db.get(models.PODraft, original_id)
        revision = db.get(models.PODraft, revision_id)
        assert original.status == "superseded" and original.superseded_at is not None
        assert revision.status == "simulated_posted" and revision.issued_at is not None
        assert db.query(models.OutboxMessage).filter_by(idempotency_key=f"po:{revision.id}:acknowledgement").one().meta["revision_kind"] == "amendment"


def test_po_cancellation_requires_no_delivery_and_preserves_until_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(procurement_v2, "generate_artifact", lambda *_a, **_k: SimpleNamespace(id="ART-CANCEL", document_id="DOC-CANCEL"))
    with SessionLocal() as db:
        user, original, _line = _issued_po(db)
        revision = procurement_v2.prepare_po_change(db, user, original.id, "cancellation", "Requirement withdrawn", [])
        procurement_v2.approve_po_change(db, user, revision.id)
        db.flush()
        event = db.query(models.IntegrationOutboxEvent).filter_by(entity_id=revision.id, action="cancel_purchase_order").one()
        workflows.approve_integration_outbox_event(db, user, event.id)
        db.commit()
        event_id, original_id, revision_id = event.id, original.id, revision.id
    assert dispatch_event_by_id(event_id) == "simulated"
    with SessionLocal() as db:
        assert db.get(models.PODraft, original_id).status == "cancelled"
        assert db.get(models.PODraft, revision_id).status == "cancelled"
        assert db.query(models.Task).filter_by(entity_type="po_draft", entity_id=revision_id, owner_role="gate_operator").count() == 0


def test_cancellation_is_blocked_after_delivery_activity() -> None:
    with SessionLocal() as db:
        user, po, _line = _issued_po(db)
        db.add(models.ASN(
            tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id,
            status="expected", expected_quantity=1, vehicle_number="MH12TEST",
        ))
        db.flush()
        with pytest.raises(HTTPException, match="cannot be cancelled"):
            procurement_v2.prepare_po_change(db, user, po.id, "cancellation", "Too late", [])


def test_supplier_change_request_creates_owned_work_and_links_immutable_amendment() -> None:
    with SessionLocal() as db:
        user, po, line = _issued_po(db)
        raw_token = "supplier-change-request-token"
        db.add(models.SupplierPortalToken(
            tenant_id=user.tenant_id, plant_id=user.plant_id, rfq_id="", supplier_id=po.supplier_id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), status="active",
            expires_at=workflows.utcnow() + timedelta(days=1), purpose="po_acknowledgement", entity_id=po.id,
        ))
        db.flush()
        acknowledgement = workflows.receive_supplier_acknowledgement(
            db, raw_token, "change_requested", 8, "2026-09-20", "Can supply eight units by the revised date",
        )
        db.flush()
        assert acknowledgement.requested_changes["confirmed_quantity"] == 8
        task = db.query(models.Task).filter_by(entity_type="supplier_acknowledgements", entity_id=acknowledgement.id).one()
        assert task.owner_role == "purchase_manager" and task.status == "open"
        assert db.query(models.Notification).filter_by(linked_entity_id=acknowledgement.id).count() == 1
        revision = procurement_v2.prepare_po_change(db, user, po.id, "amendment", "Accepted supplier commitment", [{
            "line_id": line.id, "quantity": 8, "need_by_date": "2026-09-20",
        }], acknowledgement.id)
        db.flush()
        assert acknowledgement.status == "change_prepared"
        assert acknowledgement.linked_po_revision_id == revision.id
        assert task.status == "completed"
        assert revision.change_summary["supplier_acknowledgement"] == acknowledgement.business_number
        assert po.status == "simulated_posted"
