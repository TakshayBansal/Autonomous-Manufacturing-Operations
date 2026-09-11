import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import agent_service, excel_connector, invoice_service, management_insights, procurement_v2
from app.agent_schemas import WorkspaceCreateRequest
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


def test_golden_excel_driven_procurement_cycle_reconciles_without_live_erp(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = Path(__file__).parent / "fixtures" / "excel_erp" / "genuinegigs_procurement_exchange_v1.xlsx"
    artifact_counter = iter(range(1, 20))
    monkeypatch.setattr(
        procurement_v2, "generate_artifact",
        lambda *_args, **_kwargs: SimpleNamespace(
            id=f"ART-GOLDEN-{next(artifact_counter)}", document_id=f"DOC-GOLDEN-{next(artifact_counter)}",
        ),
    )
    stored_exports: list[bytes] = []
    monkeypatch.setattr("app.storage.object_storage.put_file", lambda _bucket, _key, body, _type: stored_exports.append(body.read()))
    monkeypatch.setattr("app.storage.object_storage.presigned_get", lambda _bucket, key, _ttl: f"/signed/{key}")

    with SessionLocal() as db:
        bootstrap_owner = db.query(models.User).filter_by(email="plant.manager@genuinegigs.local").one()
        tenant, _owner = agent_service.create_fresh_workspace(db, bootstrap_owner, WorkspaceCreateRequest(
            company_name="Golden Pilot Company", workspace_name="Golden Excel Pilot",
            plant_name="Pilot Plant", plant_code="PILOT", agent_enabled=True,
        )); db.flush()
        admin = db.query(models.User).filter_by(tenant_id=tenant.id, role="admin").one()
        assert db.query(models.PurchaseRequirement).filter_by(tenant_id=tenant.id).count() == 0
        assert db.query(models.PODraft).filter_by(tenant_id=tenant.id).count() == 0
        workflows.ensure_default_connections(db, admin); db.flush()
        connection = db.query(models.IntegrationConnection).filter_by(provider="local").first()
        imported = excel_connector.preview_import(db, admin, connection, fixture.name, fixture.read_bytes()); db.flush()
        excel_connector.commit_import(db, admin, imported); db.flush()
        requirement = db.query(models.PurchaseRequirement).filter_by(business_number="REQ-EXT-0001").one()
        external_po = db.query(models.PODraft).filter_by(business_number="PO-EXT-0001").one()
        external_po_state = db.query(models.IntegrationExternalRecordState).filter_by(
            connection_id=connection.id,
            external_entity_type="po_draft",
            canonical_entity_id=external_po.id,
        ).one()
        current_external_version = external_po_state.external_version
        # Simulate a newer operational decision made after the last external
        # sync. The older workbook must not overwrite this local version.
        external_po.status = "failed"
        db.flush()
        stale_fixture = (
            Path(__file__).parent / "fixtures" / "excel_erp"
            / "conflicts" / "stale_external_version.xlsx"
        )
        stale = excel_connector.preview_import(
            db, admin, connection, stale_fixture.name, stale_fixture.read_bytes(),
        ); db.flush()
        stale_po = db.query(models.IntegrationImportRowResult).filter_by(
            batch_id=stale.id, sheet_name="OpenPOs",
        ).one()
        assert stale_po.action == "conflict"
        assert any(
            message["code"] == "stale_external_data"
            for message in stale_po.validation_messages
        )
        excel_connector.commit_import(db, admin, stale); db.flush()
        db.refresh(external_po_state)
        db.refresh(external_po)
        assert external_po_state.external_version == current_external_version
        assert external_po.status == "failed"

        rfq = workflows.create_rfq_from_requirement(db, admin, requirement.id); db.flush()
        publication = workflows.publish_rfq(db, admin, rfq.id); db.flush()
        quote = workflows.receive_supplier_quote(db, publication["supplier_portal_links"][0]["token"], {
            "quote_number": "QTN-GOLDEN-1", "quote_date": "2026-07-19", "validity_date": "2026-08-19",
            "payment_terms": "30 days from receipt",
            "line": {"quantity": 200, "uom": "KG", "unit_price": 98, "gst_rate": 18, "lead_time_days": 12, "promised_date": "2026-08-10", "certificates": ["mill certificate"]},
        }); db.flush()
        decisions = [
            {"field_name": row.field_name, "decision": "accept"}
            for row in db.query(models.QuoteFieldVerification).filter_by(quote_id=quote.id).all()
        ]
        workflows.verify_quote_fields(db, admin, quote.id, decisions); db.flush()
        assert quote.verification_status == "verified"
        comparison = workflows.generate_comparison(db, admin, rfq.id); db.flush()
        procurement_v2.submit_comparison(db, admin, comparison.id, "Best eligible landed-cost and delivery result"); db.flush()

        plant_manager = db.query(models.User).filter_by(role="plant_manager", tenant_id=admin.tenant_id, plant_id=admin.plant_id).one()
        purchase_executive = db.query(models.User).filter_by(role="purchase_executive", tenant_id=admin.tenant_id, plant_id=admin.plant_id).one()
        procurement_v2.decide_comparison(db, plant_manager, comparison.id, "approve", "Operational need confirmed"); db.flush()
        procurement_v2.decide_comparison(db, purchase_executive, comparison.id, "approve", "Supplier evidence reviewed"); db.flush()
        assert comparison.status == "approved"
        po, _artifact = procurement_v2.confirm_purchase_order(db, admin, comparison.id); db.flush()
        event = db.query(models.IntegrationOutboxEvent).filter_by(entity_type="po_draft", entity_id=po.id).one()
        workflows.approve_integration_outbox_event(db, admin, event.id)
        db.commit()
        event_id, po_id, requirement_id, tenant_id, admin_id = event.id, po.id, requirement.id, tenant.id, admin.id

    assert dispatch_event_by_id(event_id) == "simulated"

    with SessionLocal() as db:
        admin = db.get(models.User, admin_id)
        assert admin is not None and admin.tenant_id == tenant_id
        po = db.get(models.PODraft, po_id)
        assert po is not None and po.status == "simulated_posted"
        acknowledgement_email = db.query(models.OutboxMessage).filter_by(
            tenant_id=admin.tenant_id, plant_id=admin.plant_id,
        ).filter(models.OutboxMessage.meta["po_draft_id"].as_string() == po.id).one()
        raw_token = re.search(r"[?&]token=([^&\s]+)", acknowledgement_email.body).group(1)  # type: ignore[union-attr]
        acknowledgement = workflows.receive_supplier_acknowledgement(
            db, raw_token, "accepted", 200, "2026-08-10", "Confirmed",
        ); db.flush()
        assert acknowledgement.status == "accepted"
        asn = workflows.create_asn(db, admin, po.id, 200, "MH12-GOLDEN"); db.flush()
        workflows.record_gate_entry(db, admin, po.id, asn.id, "MH12-GOLDEN", "CH-GOLDEN-1", 10, "Seals intact"); db.flush()
        receipt = workflows.record_receipt(db, admin, po.id, 200, 0); db.flush()
        inspection = workflows.record_inspection(db, admin, receipt.id, 200, 190, 10, 0); db.flush()
        assert inspection.status == "partial_acceptance"
        supplier_return = workflows.create_supplier_return(db, admin, inspection.id, 10, "Surface defects"); db.flush()
        workflows.request_supplier_replacement(db, admin, supplier_return.id, 10, "2026-08-20"); db.flush()
        replacement_receipt = workflows.record_replacement_receipt(
            db, admin, supplier_return.id, 10, "CH-GOLDEN-REPLACEMENT", "MH12-REPLACEMENT", 1,
        ); db.flush()
        replacement_inspection = workflows.record_inspection(db, admin, replacement_receipt.id, 10, 10, 0, 0); db.flush()
        assert supplier_return.status == "replacement_accepted"
        linked_case = db.query(models.Case).filter_by(po_draft_id=po.id).one()
        workflows.close_case(db, admin, linked_case.id, "Rejected material replaced and accepted after reinspection"); db.flush()
        assert linked_case.status == "closed"

        po_line = db.query(models.PODraftLine).filter_by(po_draft_id=po.id).one()
        invoice = invoice_service.create_invoice(db, admin, {
            "supplier_id": po.supplier_id, "po_draft_id": po.id, "invoice_number": "INV-GOLDEN-CYCLE-1",
            "invoice_date": "2026-08-11", "currency": "INR", "total_amount": 23128,
            "lines": [{"po_line_id": po_line.id, "quantity": 200, "uom": "KG", "unit_price": 98, "line_total": 19600, "tax_amount": 3528}],
        }); db.flush()
        match = invoice_service.match_invoice(db, admin, invoice.id); db.flush()
        assert (match.match_type, match.result) == ("three_way", "matched")
        assert match.evidence[-1]["received_quantity"] == 200
        handoff = invoice_service.prepare_finance_handoff(db, admin, match.id); db.flush()
        assert handoff.payload["payment_release"] == "not_authorized"
        before_payment = workflows.requirement_lifecycle_state(db, admin, requirement_id)
        assert before_payment["eligible_to_close"] is False
        assert any("paid status" in blocker for blocker in before_payment["blockers"])
        with pytest.raises(Exception) as blocked_close:
            workflows.close_requirement_lifecycle(db, admin, requirement_id)
        assert getattr(blocked_close.value, "status_code", None) == 409
        db.add(models.InvoicePaymentStatus(
            tenant_id=admin.tenant_id, plant_id=admin.plant_id, invoice_id=invoice.id,
            connection_id=connection.id, external_key="INV-GOLDEN-CYCLE-1", status="paid",
            external_version="1", observed_at=workflows.utcnow(), source_payload_hash="b" * 64,
            evidence={"source": "excel_read_only", "reference": "PAY-GOLDEN-1"},
        )); db.flush()
        lifecycle = workflows.requirement_lifecycle_state(db, admin, requirement_id)
        assert lifecycle["eligible_to_close"] is True
        closed_requirement = workflows.close_requirement_lifecycle(db, admin, requirement_id); db.flush()
        assert closed_requirement.status == "closed"
        employee_brief = management_insights.brief(db, admin, "morning")
        manager_metrics = management_insights.analytics(db, admin)
        assert employee_brief["employee_score"] is None
        assert employee_brief["sources"]
        assert manager_metrics["opaque_employee_score"] is False
        assert any(
            metric["key"] == "requirement_cycle_time" and metric["sample_size"] >= 1
            for metric in manager_metrics["metrics"]
        )

        export = excel_connector.create_exchange_export(db, admin); db.flush()
        assert export["status"] == "completed" and export["reconciliation"]["status"] == "reconciled"
        counts_before = {
            model.__tablename__: db.query(model).filter_by(tenant_id=admin.tenant_id, plant_id=admin.plant_id).count()
            for model in (models.Item, models.Supplier, models.PODraft, models.StoreReceipt, models.InspectionResult, models.SupplierInvoice)
        }
        repeated = excel_connector.preview_import(db, admin, connection, export["filename"], stored_exports[-1]); db.flush()
        excel_connector.commit_import(db, admin, repeated); db.flush()
        counts_after = {
            model.__tablename__: db.query(model).filter_by(tenant_id=admin.tenant_id, plant_id=admin.plant_id).count()
            for model in (models.Item, models.Supplier, models.PODraft, models.StoreReceipt, models.InspectionResult, models.SupplierInvoice)
        }
        assert counts_after == counts_before
        assert db.query(models.AuditEvent).filter_by(tenant_id=admin.tenant_id).count() > 20
