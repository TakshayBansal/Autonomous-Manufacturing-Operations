from datetime import datetime, timezone
from uuid import uuid4

from app import companion, cycle_orchestration
from app.db import models
from app.db.session import SessionLocal
from app.main import app


def membership_fixture(db) -> models.WorkspaceMembership:
    user = db.query(models.User).filter_by(role="purchase_executive").first()
    if user is None:
        user = models.User(id="companion-user", tenant_id="companion-tenant", plant_id="companion-plant",
            department_id="purchase", name="Companion User", email="companion@example.test",
            role="purchase_executive", password_hash="unused")
        db.add(user)
        db.flush()
    tenant = db.get(models.Tenant, user.tenant_id)
    if tenant is None:
        tenant = models.Tenant(id=user.tenant_id, name="Companion Tenant", status="active",
            agent_enabled=True, feature_flags={"proactive_companion": True})
        db.add(tenant)
    else:
        tenant.feature_flags = {**(tenant.feature_flags or {}), "proactive_companion": True}
    membership = db.query(models.WorkspaceMembership).filter_by(user_id=user.id).first()
    if membership is None:
        membership = models.WorkspaceMembership(id="companion-membership", account_id="companion-account",
            tenant_id=user.tenant_id, user_id=user.id, default_plant_id=user.plant_id,
            plant_ids=[user.plant_id], department_id=user.department_id, role=user.role,
            permissions=[], status="active")
        db.add(membership)
        db.flush()
    return membership


def test_login_briefing_is_daily_and_state_marks_delivery() -> None:
    with SessionLocal() as db:
        membership = membership_fixture(db)
        companion.create_login_briefing(db, membership)
        companion.create_login_briefing(db, membership)
        db.commit()
        rows = db.query(models.CompanionIntervention).filter_by(
            recipient_membership_id=membership.id, trigger_type="login.briefing",
        ).all()
        assert len(rows) == 1
        payload = companion.state(db, membership)
        assert payload["top_intervention"] is not None
        assert payload["unresolved_count"] >= 1
        assert rows[0].delivery_state == "delivered"


def test_preferences_can_silence_popup_without_removing_inbox() -> None:
    with SessionLocal() as db:
        membership = membership_fixture(db)
        preference = companion.preference_for(db, membership)
        preference.proactive_level = "muted"
        event = models.EventOutbox(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            event_type="workspace.changed", aggregate_type="other", aggregate_id="record-1",
            aggregate_version=1, correlation_id="companion-muted", actor_membership_id=membership.id,
            payload={},
        )
        db.add(event)
        db.flush()
        assert companion.process_event(db, event) == 1
        row = db.query(models.CompanionIntervention).filter_by(source_event_id=event.event_id).one()
        assert row.delivery_mode == "inbox"


def test_high_risk_dismissal_contract_requires_a_reason() -> None:
    # The route validates this; the persisted contract also keeps the resolution
    # and rationale fields distinct for auditability.
    with SessionLocal() as db:
        membership = membership_fixture(db)
        key = f"dismissal-contract-{uuid4()}"
        row = models.CompanionIntervention(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            recipient_membership_id=membership.id, correlation_id=key,
            trigger_type="cycle.risk_changed", severity="critical", priority=0,
            title="Risk", message="Risk", why_now="Risk changed", actions=[], evidence=[],
            delivery_mode="panel", aggregate_version=1, semantic_key=key,
        )
        db.add(row)
        row.delivery_state = "dismissed"
        row.selected_action = "dismissed:Reviewed with production manager"
        row.resolved_at = datetime.now(timezone.utc)
        db.commit()
        assert row.resolved_at is not None
        assert row.selected_action.startswith("dismissed:")


def test_companion_public_contract_is_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/agent/companion/state" in paths
    assert "/agent/companion/stream" in paths
    assert "/agent/companion/interventions/{intervention_id}/actions" in paths
    assert "/admin/companion-trigger-policies/simulate" in paths


def test_cycle_handoff_offers_manual_and_gigi_actions_without_automatic_execution() -> None:
    with SessionLocal() as db:
        membership = membership_fixture(db)
        user = db.get(models.User, membership.user_id)
        profile = db.query(models.AgentProfile).filter_by(membership_id=membership.id).first()
        if profile is None:
            profile = models.AgentProfile(id=f"profile-{uuid4()}", tenant_id=membership.tenant_id,
                plant_id=membership.default_plant_id, user_id=membership.user_id,
                membership_id=membership.id, role=membership.role, display_name="Companion specialist",
                allowed_actions=[], blocked_actions=[], enabled=True)
            db.add(profile)
        item = db.query(models.Item).filter_by(tenant_id=membership.tenant_id).first()
        if item is None:
            item = models.Item(id=f"item-{uuid4()}", tenant_id=membership.tenant_id,
                plant_id=membership.default_plant_id, code=f"CMP-{uuid4().hex[:6]}",
                name="Companion material", uom_id="EA", erp_item_code=f"CMP-{uuid4().hex[:6]}")
            db.add(item)
        db.flush()
        requirement = models.PurchaseRequirement(tenant_id=membership.tenant_id,
            plant_id=membership.default_plant_id, business_number=f"PR-COMP-{uuid4().hex[:8]}",
            source="manual", item_id=item.id, quantity=3, uom="EA", need_by_date="2099-01-01",
            reason="Companion preparation test", status="approved", owner_user_id=user.id,
            owner_membership_id=membership.id, related_case_id="")
        db.add(requirement)
        db.flush()
        cycle_orchestration.evaluate(db, requirement)
        event = models.EventOutbox(tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            event_type="procurement.requirement.changed", aggregate_type="purchase_requirements",
            aggregate_id=requirement.id, aggregate_version=requirement.version,
            correlation_id=f"companion-auto-{uuid4()}", actor_membership_id=membership.id,
            payload={"requirement_id": requirement.id})
        db.add(event)
        db.flush()
        assert companion.process_event(db, event) >= 1
        intervention = db.query(models.CompanionIntervention).filter_by(source_event_id=event.event_id).first()
        assert intervention is not None
        assert intervention.trigger_type == "work.handoff"
        assert intervention.delivery_mode == "bubble"
        assert intervention.run_id is None
        assert requirement.business_number in intervention.title
        assert item.name in intervention.message
        assert "3 EA" in intervention.message
        assert [action["label"] for action in intervention.actions[:2]] == [
            "Create RFQ", "Ask Gigi to prepare",
        ]


def test_new_work_handoff_replaces_login_briefing_as_live_popup() -> None:
    with SessionLocal() as db:
        membership = membership_fixture(db)
        user = db.get(models.User, membership.user_id)
        companion.create_login_briefing(db, membership)
        item = db.query(models.Item).filter_by(tenant_id=membership.tenant_id).first()
        if item is None:
            item = models.Item(
                id=f"item-{uuid4()}", tenant_id=membership.tenant_id,
                plant_id=membership.default_plant_id, code=f"HANDOFF-{uuid4().hex[:6]}",
                name="Handoff material", uom_id="EA", erp_item_code=f"HANDOFF-{uuid4().hex[:6]}",
            )
            db.add(item)
        db.flush()
        requirement = models.PurchaseRequirement(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            business_number=f"PR-HANDOFF-{uuid4().hex[:8]}", source="manual",
            item_id=item.id, quantity=5, uom="EA", need_by_date="2099-01-01",
            reason="Assigned procurement handoff", status="approved",
            owner_user_id=user.id, owner_membership_id=membership.id, related_case_id="",
        )
        db.add(requirement)
        db.flush()
        cycle_orchestration.evaluate(db, requirement)
        event = models.EventOutbox(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            event_type="procurement.requirement.changed", aggregate_type="purchase_requirements",
            aggregate_id=requirement.id, aggregate_version=requirement.version,
            correlation_id=f"handoff-popup-{uuid4()}", payload={"requirement_id": requirement.id},
        )
        db.add(event)
        db.flush()
        assert companion.process_event(db, event) == 1

        payload = companion.state(db, membership)
        assert payload["top_intervention"]["trigger_type"] == "work.handoff"
        assert payload["top_intervention"]["priority"] < next(
            row["priority"] for row in payload["interventions"]
            if row["trigger_type"] == "login.briefing"
        )


def test_assigned_task_repairs_a_missed_handoff_without_page_reload() -> None:
    with SessionLocal() as db:
        membership = membership_fixture(db)
        task = models.Task(
            tenant_id=membership.tenant_id, plant_id=membership.default_plant_id,
            title="Prepare and publish supplier RFQ", owner_role="purchase_executive",
            owner_user_id=membership.user_id, owner_membership_id=membership.id,
            due_at=datetime.now(timezone.utc), status="open", severity="action",
            entity_type="purchase_requirements", entity_id=f"missing-event-{uuid4()}",
        )
        db.add(task)
        db.flush()

        payload = companion.state(db, membership)

        assert payload["top_intervention"]["trigger_type"] == "work.handoff"
        assert payload["top_intervention"]["task_id"] == task.id
        assert payload["top_intervention"]["actions"][0]["label"] == "Do it myself"
