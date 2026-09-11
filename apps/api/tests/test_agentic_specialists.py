from uuid import uuid4

from pydantic import BaseModel

from app import cycle_orchestration, specialists
from app.agent_schemas import SpecialistRequest
from app.db import models
from app.db.session import SessionLocal
from app.governed_execution import ExecutionContext, GovernedExecutionGateway
from app.model_gateway import ModelGateway


def requirement_fixture(db) -> models.PurchaseRequirement:
    user = db.query(models.User).filter_by(role="purchase_executive").first()
    item = db.query(models.Item).first()
    assert user is not None and item is not None
    membership = db.query(models.WorkspaceMembership).filter_by(user_id=user.id).first()
    row = models.PurchaseRequirement(tenant_id=user.tenant_id, plant_id=user.plant_id,
        business_number=f"PR-SPECIALIST-{uuid4().hex[:8]}", source="manual", item_id=item.id,
        quantity=10, uom=item.uom_id, need_by_date="2099-01-01", reason="Specialist test",
        status="approved", owner_user_id=user.id,
        owner_membership_id=membership.id if membership else None, related_case_id="")
    db.add(row)
    db.flush()
    return row


def test_specialist_prepared_work_is_evidenced_and_idempotent() -> None:
    with SessionLocal() as db:
        requirement = requirement_fixture(db)
        objective = cycle_orchestration.evaluate(db, requirement)
        request = SpecialistRequest(specialist="requirement_specification", objective_id=objective.id,
            requested_outcome="Review requirement completeness", correlation_id=str(uuid4()))
        first = specialists.run(db, request)
        second = specialists.run(db, request)
        db.commit()
        assert first.findings[0].confidence == 1
        assert first.findings[0].evidence[0].entity_id == requirement.id
        assert first.prepared_work[0]["id"] == second.prepared_work[0]["id"]
        assert db.query(models.PreparedWorkItem).filter_by(objective_id=objective.id).count() == 1


def test_model_gateway_validates_deterministic_fallback() -> None:
    class Output(BaseModel):
        score: int
    result = ModelGateway().structured("classification", "Classify", Output, fallback=lambda: {"score": 7})
    assert result.score == 7


def test_governed_gateway_rechecks_scope_version_and_idempotency() -> None:
    with SessionLocal() as db:
        requirement = requirement_fixture(db)
        actor = models.WorkspaceMembership(id="gateway-member", account_id="gateway-account",
            tenant_id=requirement.tenant_id, user_id=requirement.owner_user_id,
            default_plant_id=requirement.plant_id, plant_ids=[requirement.plant_id],
            department_id="purchase", role="purchase_manager", permissions=[], status="active")
        context = ExecutionContext(membership=actor, correlation_id="gateway-correlation",
            idempotency_key="gateway-idempotency", capability_id="delegate_task",
            resource_type="purchase_requirements", resource_id=requirement.id,
            expected_version=requirement.version)
        calls = []
        gateway = GovernedExecutionGateway(db)
        first = gateway.execute(context, lambda: requirement, lambda row: calls.append(row.id) or {"updated": True})
        second = gateway.execute(context, lambda: requirement, lambda row: calls.append(row.id) or {"updated": True})
        assert first.status == second.status == "succeeded"
        assert calls == [requirement.id]
