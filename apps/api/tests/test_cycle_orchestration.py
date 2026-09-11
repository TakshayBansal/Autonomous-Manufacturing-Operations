from app import cycle_orchestration, eventing
from app.db import models
from app.db.session import SessionLocal
from uuid import uuid4


def requirement_fixture(db: SessionLocal) -> models.PurchaseRequirement:
    item = db.query(models.Item).first()
    user = db.query(models.User).filter_by(role="purchase_executive").first() or db.query(models.User).first()
    if user is None:
        user = models.User(id="cycle-user", tenant_id="cycle-tenant", plant_id="cycle-plant",
            department_id="purchase", name="Cycle User", email="cycle@example.test",
            role="purchase_executive", password_hash="unused")
        db.add(user)
    if item is None:
        item = models.Item(id="cycle-item", tenant_id=user.tenant_id, plant_id=user.plant_id,
            code="CYCLE", name="Cycle test material", uom_id="EA", erp_item_code="CYCLE")
        db.add(item)
    if db.get(models.Tenant, user.tenant_id) is None:
        db.add(models.Tenant(id=user.tenant_id, name="Cycle Tenant", status="active",
            agent_enabled=True, feature_flags={"proactive_companion": True}))
    db.flush()
    membership = db.query(models.WorkspaceMembership).filter_by(user_id=user.id).first()
    if membership is None:
        membership = models.WorkspaceMembership(
            id=f"membership-{user.id}", account_id=f"account-{user.id}", tenant_id=user.tenant_id,
            user_id=user.id, default_plant_id=user.plant_id, plant_ids=[user.plant_id],
            department_id=user.department_id, role=user.role, permissions=[], status="active",
        )
        db.add(membership)
        db.flush()
    row = models.PurchaseRequirement(
        tenant_id=user.tenant_id, plant_id=user.plant_id, business_number=f"PR-CYCLE-{uuid4().hex[:8]}",
        source="manual", item_id=item.id, quantity=10, uom="EA", need_by_date="2099-01-01",
        reason="Cycle evaluator regression", status="approved", owner_user_id=user.id,
        owner_membership_id=membership.id if membership else None, related_case_id="",
    )
    db.add(row)
    db.flush()
    return row


def test_active_requirement_has_one_idempotent_durable_cycle() -> None:
    with SessionLocal() as db:
        requirement = requirement_fixture(db)
        first = cycle_orchestration.evaluate(db, requirement)
        db.commit()
        first_version = first.aggregate_version
        second = cycle_orchestration.evaluate(db, requirement)
        db.commit()
        assert second.id == first.id
        assert second.aggregate_version == first_version
        assert db.query(models.ProcurementCycleObjective).filter_by(requirement_id=requirement.id).count() == 1
        assert db.query(models.CycleStageState).filter_by(objective_id=first.id).count() == len(cycle_orchestration.STAGES)
        assert db.query(models.EventOutbox).filter_by(aggregate_id=first.id).count() == 1


def test_cycle_recommendations_are_evidenced_and_overdue_risk_is_deduplicated() -> None:
    with SessionLocal() as db:
        requirement = requirement_fixture(db)
        requirement.need_by_date = "2000-01-01"
        objective = cycle_orchestration.evaluate(db, requirement)
        cycle_orchestration.evaluate(db, requirement)
        db.commit()
        risks = db.query(models.CycleRisk).filter_by(objective_id=objective.id, status="open").all()
        assert objective.health == "at_risk"
        assert len(risks) == 1
        assert risks[0].evidence == [{"type": "requirement", "id": requirement.id}]


def test_my_day_is_tenant_scoped() -> None:
    # Endpoint behavior is covered through the same authentication fixture used
    # by the role-agent suite; this assertion protects the model-level scope.
    with SessionLocal() as db:
        requirement = requirement_fixture(db)
        objective = cycle_orchestration.evaluate(db, requirement)
        db.commit()
        assert objective.tenant_id == requirement.tenant_id
        assert objective.plant_id == requirement.plant_id


def test_transactional_requirement_event_dispatch_is_idempotent() -> None:
    with SessionLocal() as db:
        requirement = requirement_fixture(db)
        db.commit()
        event = db.query(models.EventOutbox).filter_by(
            aggregate_id=requirement.id, event_type="procurement.requirement.changed",
        ).one()
        assert eventing.dispatch_one(db, event.event_id) == "completed"
        assert eventing.dispatch_one(db, event.event_id) == "completed"
        receipts = db.query(models.EventConsumerReceipt).filter_by(event_id=event.event_id).all()
        assert {row.consumer_name for row in receipts} == {"cycle_evaluator", "companion_orchestrator"}
        assert db.query(models.ProcurementCycleObjective).filter_by(requirement_id=requirement.id).count() == 1
        intervention = db.query(models.CompanionIntervention).filter_by(source_event_id=event.event_id).one()
        assert intervention.recipient_membership_id == requirement.owner_membership_id
        assert intervention.actions[0]["mode"] == "manual"
        assert any(action["mode"] == "prepare" for action in intervention.actions)
        assert intervention.run_id is None or db.get(models.AgentRun, intervention.run_id) is not None
