from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import procurement_v2
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.domains import workflows


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def test_supplier_compliance_blocks_sourcing_until_verified_current_evidence() -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        supplier = db.query(models.Supplier).filter_by(status="approved").first()
        capability = db.query(models.SupplierItemCapability).filter_by(supplier_id=supplier.id, approved=True).first()
        requirement = procurement_v2.create_compliance_requirement(db, user, "ISO 9001", "Current quality-system certificate", capability.item_id, True)
        db.flush()
        readiness = workflows.supplier_compliance_readiness(db, user, supplier, {capability.item_id})
        assert not readiness["eligible"] and readiness["missing"] == ["ISO 9001"]

        certificate = procurement_v2.submit_supplier_certificate(
            db, user, supplier.id, "ISO 9001", "ISO-TEST-001", None,
            date.today().isoformat(), (date.today() + timedelta(days=365)).isoformat(),
        )
        db.flush()
        readiness = workflows.supplier_compliance_readiness(db, user, supplier, {capability.item_id})
        assert not readiness["eligible"] and readiness["pending"] == ["ISO 9001"]
        procurement_v2.decide_supplier_certificate(db, user, certificate.id, "verify", "Evidence checked")
        db.flush()
        readiness = workflows.supplier_compliance_readiness(db, user, supplier, {capability.item_id})
        assert readiness["eligible"] and readiness["valid"] == ["ISO 9001"]
        assert supplier.status == "approved"

        certificate.expires_on = (date.today() - timedelta(days=1)).isoformat()
        readiness = workflows.supplier_compliance_readiness(db, user, supplier, {capability.item_id})
        assert not readiness["eligible"] and readiness["expired"] == ["ISO 9001"]


def test_publish_revalidates_supplier_compliance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.procurement_v2.generate_artifact", lambda *_a, **_k: SimpleNamespace(id="ART-COMP", document_id="DOC-COMP"))
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        rfq = db.query(models.RFQ).first()
        rfq.status = "draft"
        line = db.query(models.RFQLine).filter_by(rfq_id=rfq.id).first()
        supplier = db.get(models.Supplier, rfq.supplier_ids[0])
        procurement_v2.create_compliance_requirement(db, user, "Current GST registration", "Mandatory legal registration", None, True)
        db.flush()
        with pytest.raises(HTTPException) as error:
            workflows.publish_rfq(db, user, rfq.id)
        assert error.value.status_code == 409
        assert "Current GST registration" in str(error.value.detail)


def test_rejected_certificate_does_not_approve_supplier() -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        supplier = db.query(models.Supplier).first()
        procurement_v2.create_compliance_requirement(db, user, "Factory licence", "", None, True)
        certificate = procurement_v2.submit_supplier_certificate(
            db, user, supplier.id, "Factory licence", "FL-1", None, "",
            (date.today() + timedelta(days=30)).isoformat(),
        )
        db.flush()
        procurement_v2.decide_supplier_certificate(db, user, certificate.id, "reject", "Unreadable evidence")
        db.flush()
        assert certificate.status == "rejected"
        assert supplier.status == "conditional"
        assert not workflows.supplier_compliance_readiness(db, user, supplier)["eligible"]
