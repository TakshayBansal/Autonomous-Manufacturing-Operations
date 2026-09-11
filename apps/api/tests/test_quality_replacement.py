import pytest
from fastapi import HTTPException

from app import agent_service
from app.agent_schemas import AgentMessageRequest, IntentEnvelope, ThreadCreateRequest
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.domains import workflows
from app import supplier_performance, procurement_policy


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def setup_rejection(db):
    user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
    award = db.query(models.AwardDecision).first()
    quote_line = db.query(models.QuoteLine).filter_by(quote_id=award.quote_id).first()
    po = models.PODraft(
        tenant_id=user.tenant_id, plant_id=user.plant_id, award_id=award.id,
        supplier_id=award.supplier_id, status="posted", oracle_mapping={}, currency="INR",
        payment_terms="30 days", commercial_terms={},
    )
    db.add(po); db.flush()
    db.add(models.PODraftLine(
        tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id,
        item_id=quote_line.item_id, quantity=10, uom="KG", unit_price=100,
        gst_rate=18, need_by_date="2026-08-01", inspection_required=True,
    ))
    case = models.Case(
        tenant_id=user.tenant_id, plant_id=user.plant_id, title="Quality rejection",
        requirement="Replacement test", supplier="Test supplier", owner_role="plant_manager",
        status="inspection_exception", severity="critical", timeline=[], evidence=[], po_draft_id=po.id,
    )
    receipt = models.StoreReceipt(
        tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id,
        status="received", received_quantity=10, short_quantity=0, excess_quantity=0, damaged_quantity=0,
    )
    db.add_all([case, receipt]); db.flush()
    inspection = workflows.record_inspection(db, user, receipt.id, 10, 8, 2, 0); db.flush()
    return user, po, case, inspection


def setup_inbound(db):
    user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
    award = db.query(models.AwardDecision).first()
    quote_line = db.query(models.QuoteLine).filter_by(quote_id=award.quote_id).first()
    item = db.get(models.Item, quote_line.item_id)
    po = models.PODraft(
        tenant_id=user.tenant_id, plant_id=user.plant_id, award_id=award.id,
        supplier_id=award.supplier_id, status="posted", oracle_mapping={}, currency="INR",
        payment_terms="30 days", commercial_terms={},
    )
    db.add(po); db.flush()
    db.add(models.PODraftLine(
        tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id,
        item_id=item.id, quantity=10, uom="KG", unit_price=100, gst_rate=18,
        need_by_date="2026-08-01", inspection_required=True,
    ))
    case = models.Case(
        tenant_id=user.tenant_id, plant_id=user.plant_id, title="Inbound test",
        requirement="Inbound evidence", supplier="Test supplier", owner_role="purchase_executive",
        status="inbound", severity="action", timeline=[], evidence=[], po_draft_id=po.id,
    )
    gate = models.GateEntry(
        tenant_id=user.tenant_id, plant_id=user.plant_id, po_draft_id=po.id,
        status="vehicle_admitted", supplier_challan="CH-STRUCTURED", vehicle_number="MH12TEST",
    )
    db.add_all([case, gate]); db.flush()
    return user, po, item, case


def test_rejected_material_return_replacement_reinspection_and_case_closure() -> None:
    with SessionLocal() as db:
        user, _po, case, inspection = setup_rejection(db)
        supplier_return = workflows.create_supplier_return(db, user, inspection.id, 2, "Surface defects"); db.flush()
        workflows.request_supplier_replacement(db, user, supplier_return.id, 2, "2026-08-20"); db.flush()
        assert supplier_return.status == "replacement_requested"
        assert db.query(models.OutboxMessage).filter_by(idempotency_key=f"supplier-return:{supplier_return.id}:replacement").one().status == "approved_pending_send"
        replacement = workflows.record_replacement_receipt(db, user, supplier_return.id, 2, "CH-REPL-1", "MH12-REPL", 1); db.flush()
        assert replacement.supplier_return_id == supplier_return.id
        assert db.query(models.Task).filter_by(entity_type="store_receipts", entity_id=replacement.id, status="open").one().owner_role == "quality_inspector"
        reinspection = workflows.record_inspection(db, user, replacement.id, 2, 2, 0, 0); db.flush()
        assert supplier_return.status == "replacement_accepted"
        impact = db.query(models.InventoryImpact).filter_by(inspection_id=reinspection.id).one()
        assert (impact.usable_quantity, impact.rejected_quantity) == (2, 0)
        workflows.close_case(db, user, case.id, "Rejected material returned and accepted replacement reinspected"); db.flush()
        assert case.status == "closed"


def test_return_and_replacement_quantities_cannot_exceed_authorized_rejection() -> None:
    with SessionLocal() as db:
        user, _po, _case, inspection = setup_rejection(db)
        with pytest.raises(HTTPException, match="remaining rejected quantity"):
            workflows.create_supplier_return(db, user, inspection.id, 3, "Too much")
        supplier_return = workflows.create_supplier_return(db, user, inspection.id, 2, "Surface defects"); db.flush()
        with pytest.raises(HTTPException, match="cannot exceed"):
            workflows.request_supplier_replacement(db, user, supplier_return.id, 3, "2026-08-20")


def test_agent_prepares_return_then_requires_confirmation_for_supplier_request(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as db:
        user, _po, _case, inspection = setup_rejection(db)
        thread = agent_service.create_thread(db, user, ThreadCreateRequest(thread_type="personal", title="Quality replacement")); db.flush()
        monkeypatch.setattr(agent_service, "provider_response", lambda *_args, **_kwargs: (
            IntentEnvelope(intent="prepare_supplier_return", requested_outcome="Prepare return", entities={"inspection_id": inspection.id, "return_quantity": 2, "reason": "Surface defects"}, confidence=1),
            "groq", "test-model", None,
        ))
        run, _message = agent_service.run_message(db, user, thread.id, AgentMessageRequest(content="Prepare a return for the two rejected units")); db.flush()
        supplier_return = db.query(models.SupplierReturn).filter_by(inspection_id=inspection.id).one()
        assert db.query(models.AgentActionReceipt).filter_by(run_id=run.id, target_entity_id=supplier_return.id).one()
        monkeypatch.setattr(agent_service, "provider_response", lambda *_args, **_kwargs: (
            IntentEnvelope(intent="request_supplier_replacement_proposal", requested_outcome="Request replacement", entities={"supplier_return_id": supplier_return.id, "replacement_quantity": 2, "requested_delivery": "2026-08-20"}, confidence=1),
            "groq", "test-model", None,
        ))
        run, _message = agent_service.run_message(db, user, thread.id, AgentMessageRequest(content="Ask the supplier to replace it")); db.flush()
        proposal = db.query(models.AgentProposal).filter_by(run_id=run.id, action="request_supplier_replacement").one()
        assert db.query(models.OutboxMessage).filter_by(idempotency_key=f"supplier-return:{supplier_return.id}:replacement").count() == 0
        agent_service.confirm_proposal(db, user, proposal.id); db.flush()
        assert supplier_return.status == "replacement_requested"
        assert db.query(models.OutboxMessage).filter_by(idempotency_key=f"supplier-return:{supplier_return.id}:replacement").one()


def test_inspection_records_evidence_linked_supplier_performance_once() -> None:
    with SessionLocal() as db:
        user, po, _case, inspection = setup_rejection(db)
        event = db.query(models.SupplierPerformanceEvent).filter_by(source_entity_id=inspection.id).one()
        assert event.supplier_id == po.supplier_id
        assert event.metric_type == "quality_acceptance"
        assert event.score == 80
        supplier_performance.record_quality_event(db, user, inspection, po.supplier_id)
        db.flush()
        assert db.query(models.SupplierPerformanceEvent).filter_by(source_entity_id=inspection.id).count() == 1
        result = supplier_performance.summary(db, user, po.supplier_id)
        assert result["metrics"]["quality_acceptance"] == 80


def test_corrective_action_is_source_scoped_idempotent_and_requires_closure_evidence() -> None:
    with SessionLocal() as db:
        user, po, _case, inspection = setup_rejection(db)
        action = supplier_performance.open_corrective_action(
            db, user, po.supplier_id, "inspection_result", inspection.id, "Rejected material exceeded tolerance", 7,
        ); db.flush()
        duplicate = supplier_performance.open_corrective_action(
            db, user, po.supplier_id, "inspection_result", inspection.id, "Repeated request", 7,
        ); db.flush()
        assert duplicate.id == action.id
        assert db.query(models.Task).filter_by(entity_type="supplier_corrective_action", entity_id=action.id).one()
        with pytest.raises(HTTPException, match="effectiveness evidence"):
            supplier_performance.update_corrective_action(db, user, action.id, "closed", "Handling error", "Retrained operator", "Added poka-yoke", [])
        supplier_performance.update_corrective_action(
            db, user, action.id, "closed", "Handling error", "Retrained operator", "Added poka-yoke", [{"inspection_id": inspection.id}],
        ); db.flush()
        assert action.status == "closed"
        assert db.query(models.Task).filter_by(entity_type="supplier_corrective_action", entity_id=action.id).one().status == "completed"


def test_structured_wrong_material_certificate_and_production_impact_stay_out_of_inventory() -> None:
    with SessionLocal() as db:
        user, po, item, case = setup_inbound(db)
        receipt = workflows.record_receipt(
            db, user, po.id, 10, 1, "WRONG-ITEM", "missing",
            "Supplier label differs and mill certificate is absent", True,
        ); db.flush()
        assert set(receipt.exception_types) == {"damage", "wrong_material", "missing_certificate"}
        assert receipt.observed_item_code == "WRONG-ITEM" and receipt.production_impact is True
        task = db.query(models.Task).filter_by(entity_type="store_receipts", entity_id=receipt.id, assignment_source="inbound_exception").one()
        assert task.owner_role == "purchase_executive"
        assert db.query(models.Notification).filter_by(category="production_impact", linked_entity_id=receipt.id).count() == 1
        with pytest.raises(HTTPException, match="unresolved exceptions"):
            workflows.close_case(db, user, case.id, "Close too early")
        with pytest.raises(HTTPException, match="wrong item code"):
            workflows.record_inspection(db, user, receipt.id, 10, 10, 0, 0)
        with pytest.raises(HTTPException, match="certificate evidence"):
            workflows.record_inspection(db, user, receipt.id, 10, 10, 0, 0, "missing")
        inspection = workflows.record_inspection(
            db, user, receipt.id, 10, 0, 0, 10, "missing", ["IDENTITY_MISMATCH"],
            "Held pending supplier correction", True,
        ); db.flush()
        impact = db.query(models.InventoryImpact).filter_by(inspection_id=inspection.id).one()
        assert impact.usable_quantity == 0 and impact.held_quantity == 10
        assert db.query(models.Task).filter_by(entity_type="inspection_results", entity_id=inspection.id, assignment_source="inbound_exception").one().owner_role == "purchase_manager"
        assert len(case.evidence) == 2
        assert {row.action for row in db.query(models.IntegrationOutboxEvent).filter(models.IntegrationOutboxEvent.entity_id.in_([receipt.id, inspection.id])).all()} == {"push_receipt", "push_quality_disposition"}
        assert item.code in case.evidence[0]["details"]["expected_item_codes"]


def test_policy_controls_excess_delivery_tolerance() -> None:
    with SessionLocal() as db:
        user, po, _item, _case = setup_inbound(db)
        policy = procurement_policy.create_policy(db, user, "Inbound tolerance", {"over_delivery_tolerance_percent": 10})
        procurement_policy.activate_policy(db, user, policy.id); db.flush()
        receipt = workflows.record_receipt(db, user, po.id, 10.5)
        assert receipt.status == "excess_received" and receipt.excess_quantity == 0.5
        with pytest.raises(HTTPException, match="active procurement policy"):
            # A second receipt would exceed the total 11-unit policy ceiling.
            workflows.record_receipt(db, user, po.id, 1)
