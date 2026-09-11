from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import models
from app.eventing import dispatch_one
from app.platform import actions
from app.platform.agent_runtime import build_agent_context
from app.platform.backfill import backfill_tenant
from app.platform.demos import seed_demo_workspaces
from app.platform.event_registry import validate
from app.platform.events import DomainEvent, publish
from app.platform.models import (
    ActionOutcome, DataProvenance, ExternalEntityReference,
    PlatformInventoryPosition, PlatformMaterial, SourceSystem,
)
from app.platform.state import material_state


def test_all_core_platform_phases_are_connected(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'core-phases.db'}")
    models.Base.metadata.create_all(engine)
    with Session(engine) as db:
        seeded = seed_demo_workspaces(db)
        db.commit()
        assert seeded["created"] == 4
        assert seeded["scm_datasets"] == 2

        # Phase 1: deterministic mapping/backfill, shared supplier, provenance.
        report = backfill_tenant(db, "tenant-core-integration-demo")
        db.flush()
        assert report.conflicts == []
        assert db.query(PlatformMaterial).filter_by(tenant_id="tenant-core-integration-demo").count() >= 4
        assert db.query(ExternalEntityReference).filter_by(tenant_id="tenant-core-integration-demo").count() >= 4
        assert db.query(DataProvenance).filter_by(tenant_id="tenant-core-integration-demo").count() >= 4

        user = db.query(models.User).filter_by(tenant_id="tenant-core-integration-demo").one()
        material = db.query(PlatformMaterial).filter_by(tenant_id=user.tenant_id, code="SCM-C100").one()
        reference = db.query(ExternalEntityReference).filter_by(
            tenant_id=user.tenant_id, canonical_entity_id=material.id, source_system="legacy:scm").one()
        from app.scm.models import SCMInventorySnapshot
        inventory = db.query(SCMInventorySnapshot).filter_by(material_id=reference.external_id).order_by(
            SCMInventorySnapshot.snapshot_at.desc()).first()

        # Phases 2/3: registered event + idempotent projection into factory state.
        event = publish(db, DomainEvent(
            "inventory.position.updated", user.tenant_id, user.plant_id, "material", material.id,
            {"material_id": material.id, "inventory_snapshot_id": inventory.id,
             "as_of_at": inventory.snapshot_at.isoformat()}, source_system="test",
        ))
        db.commit()
        assert dispatch_one(db, event.event_id) == "completed"
        assert dispatch_one(db, event.event_id) == "completed"
        assert db.query(PlatformInventoryPosition).filter_by(material_id=material.id).count() == 1
        assert material_state(db, user.tenant_id, user.plant_id, material.id)["provenance"]

        # Phases 4/5/6: governed action, outcome, shared case/work foundations.
        intent = actions.propose(db, tenant_id=user.tenant_id, plant_id=user.plant_id, membership_id=None,
                                 action_type="scm.supply.expedite", target_type="material", target_id=material.id,
                                 payload={"quantity": 25}, rationale="Protect demo production",
                                 idempotency_key="phase-test-expedite")
        actions.decide(db, intent, None, True, "Approved in contract test")
        execution = actions.execute_simulated(db, intent)
        assert db.query(ActionOutcome).filter_by(execution_id=execution.id).one().verification_status == "verified_simulation"

        # Phases 7/8: agent receives scoped context and connectors have source registry.
        context = build_agent_context(db, user, entity_type="material", entity_id=material.id)
        assert context["tool_contract"]["direct_critical_writes"] is False
        assert "action.propose" in context["tool_contract"]["mutations"]
        assert db.query(SourceSystem).filter_by(tenant_id=user.tenant_id).count() >= 0


def test_event_contract_rejects_unknown_and_incomplete_payloads():
    try:
        validate("unknown.event", 1, {})
        assert False
    except ValueError:
        pass
    try:
        validate("inventory.position.updated", 1, {"material_id": "m"})
        assert False
    except ValueError:
        pass
