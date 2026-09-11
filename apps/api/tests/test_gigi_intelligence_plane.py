from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (AgentEvent, AgentMemory, AgentMessage, AgentRun, AgentToolCall, Base,
    Company, Department, Plant, Tenant, User, WorkspaceMembership)
from app.intelligence.context import ContextEngine
from app.intelligence.memory import remember_verified
from app.intelligence.runtime import GigiRuntime
from app.intelligence.schemas import PageContext, SideEffect
from app.intelligence.tools import EntityInput, ToolDefinition, ToolRegistry, ToolResult
from app.platform.catalog import material_for_legacy
from app.platform.models import ActionIntent, MaterialStateProjection, PlatformPurchaseOrder


def seeded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gigi.db'}")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all([
        Tenant(id="t1", name="Test"), Company(id="c1", tenant_id="t1", name="Test", erp_code="T"),
        Plant(id="p1", tenant_id="t1", company_id="c1", name="Plant A", erp_location_code="A"),
        Department(id="d1", tenant_id="t1", plant_id="p1", name="SCM"),
        User(id="u1", tenant_id="t1", plant_id="p1", department_id="d1", name="Planner",
             email="planner@test.local", role="scm_planner", password_hash="x"),
        WorkspaceMembership(id="m1", account_id="a1", tenant_id="t1", user_id="u1", default_plant_id="p1",
             plant_ids=["p1"], department_id="d1", role="scm_planner", permissions=["scm.view"], status="active"),
    ])
    db.flush()
    material = material_for_legacy(db, tenant_id="t1", plant_id="p1", company_id="c1",
        source_system="test", legacy_id="MAT-182", code="MAT-182", name="Control unit material")
    db.add(MaterialStateProjection(tenant_id="t1", plant_id="p1", material_id=material.id,
        observed={"available_qty": 30000}, derived={"risk_state": "AT_RISK", "runway_days": 9},
        planned={"stockout_date": "2026-09-11"}, predicted={}, source_freshness={"status": "fresh"}))
    db.commit()
    return db, db.get(User, "u1"), material


def test_external_action_tool_cannot_be_registered():
    registry = ToolRegistry()
    try:
        registry.register(ToolDefinition("bad.execute", "1", "integration", SideEffect.EXTERNAL_ACTION,
            EntityInput, lambda *_: ToolResult(data={}), frozenset()))
    except ValueError as exc:
        assert "external-action" in str(exc)
    else:
        raise AssertionError("External executor became available to Gigi")


def test_context_rejects_cross_tenant_entity(tmp_path):
    db, user, _ = seeded(tmp_path)
    try:
        ContextEngine(db).build(user, PageContext(module="scm", entity_type="material", entity_id="not-owned"))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Forged entity context was accepted")
    db.close()


def test_gigi_run_is_persisted_and_evidence_grounded(tmp_path):
    db, user, material = seeded(tmp_path)
    runtime = GigiRuntime(db)
    profile = runtime.ensure_profile(user, "m1")
    from app.db.models import AgentThread
    thread = AgentThread(tenant_id="t1", plant_id="p1", membership_id="m1", agent_profile_id=profile.id,
        thread_type="gigi", title="MAT-182", participant_membership_ids=["m1"], context_state={})
    db.add(thread); db.flush()
    run, response = runtime.run(user=user, thread=thread, question="Why is MAT-182 critical?",
        page=PageContext(module="scm", route="/scm/materials", entity_type="material", entity_id=material.id),
        correlation_id="corr-mat-182")
    db.commit()
    assert run.state == "completed"
    assert response.evidence
    assert "at risk" in response.answer.lower()
    assert db.query(AgentToolCall).filter_by(run_id=run.id).count() == 2
    assert db.query(AgentEvent).filter_by(run_id=run.id).count() >= 6
    assert db.query(ActionIntent).count() == 0
    db.close()


def test_global_gigi_question_receives_factory_context(tmp_path):
    db, user, _ = seeded(tmp_path)
    from app.db.models import AgentThread
    runtime = GigiRuntime(db)
    profile = runtime.ensure_profile(user, "m1")
    thread = AgentThread(tenant_id="t1", plant_id="p1", membership_id="m1", agent_profile_id=profile.id,
        thread_type="gigi", title="Plant brief", participant_membership_ids=["m1"], context_state={})
    db.add(thread); db.flush()
    run, response = runtime.run(user=user, thread=thread, question="What information do you have right now?",
        page=PageContext(module="home", route="/gigi"), correlation_id="corr-global-context")
    assert run.active_context["factory"]["plant"]["name"] == "Plant A"
    assert "conversation" not in response.answer.lower()
    assert "schema" not in response.answer.lower()
    db.close()


def test_global_question_resolves_canonical_purchase_order_number(tmp_path):
    db, user, _ = seeded(tmp_path)
    from app.db.models import Supplier
    supplier = Supplier(tenant_id="t1", plant_id="p1", name="Supplier X", code="SUP-X",
                        status="approved", erp_vendor_id="SUP-X", quality_score=95,
                        delivery_score=90)
    db.add(supplier); db.flush()
    order = PlatformPurchaseOrder(tenant_id="t1", plant_id="p1", order_number="PO-812",
        supplier_id=supplier.id, status="OPEN", currency="INR")
    db.add(order); db.flush()
    page = GigiRuntime(db)._resolve_question_entity(user, "What changed with PO-812?",
        PageContext(module="home", route="/gigi"))
    assert page.entity_type == "purchase_order"
    assert page.entity_id == order.id
    db.close()


def test_unverified_chat_cannot_become_factory_memory(tmp_path):
    db, _, _ = seeded(tmp_path)
    try:
        remember_verified(db, tenant_id="t1", plant_id="p1", membership_id="m1", key="claim",
            value="Supplier always accepts pull-ins", memory_type="factory_pattern", scope_type="plant",
            scope_id="p1", provenance={})
    except ValueError:
        pass
    else:
        raise AssertionError("Unverified claim was stored")
    assert db.query(AgentMemory).count() == 0
    db.close()
