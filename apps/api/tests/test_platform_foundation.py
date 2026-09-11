from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Account, Base, Company, Department, Plant, Tenant, User, WorkspaceMembership
from app.platform import actions
from app.platform.catalog import material_for_legacy
from app.platform.demos import seed_demo_workspaces
from app.platform.models import ActionExecution, ActionOutcome, DataProvenance, PlatformMaterial


def test_demo_workspaces_are_isolated_and_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'platform.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = seed_demo_workspaces(db)
        db.commit()
        second = seed_demo_workspaces(db)
        db.commit()
        assert first["created"] == 4
        assert second["existing"] == 4
        assert db.query(Tenant).count() == 4
        assert len({row.tenant_id for row in db.query(WorkspaceMembership).all()}) == 4
        assert db.query(Account).filter_by(email="demo.admin@genuinegigs.local").count() == 1
        assert len({row.email for row in db.query(User).all()}) == 4


def test_canonical_material_and_simulated_action_are_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'actions.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Tenant(id="tenant-test", name="Test"), Company(id="company-test", tenant_id="tenant-test", name="Test", erp_code="T"),
            Plant(id="plant-test", tenant_id="tenant-test", company_id="company-test", name="Test", erp_location_code="T"),
            Department(id="dept-test", tenant_id="tenant-test", plant_id="plant-test", name="Test"),
            User(id="user-test", tenant_id="tenant-test", plant_id="plant-test", department_id="dept-test", name="Test", email="test@example.com", role="admin", password_hash="x"),
        ])
        db.flush()
        material = material_for_legacy(db, tenant_id="tenant-test", plant_id="plant-test", company_id="company-test",
                                       source_system="legacy:test", legacy_id="legacy-1", code="MAT-1", name="Material")
        again = material_for_legacy(db, tenant_id="tenant-test", plant_id="plant-test", company_id="company-test",
                                    source_system="legacy:test", legacy_id="legacy-1", code="MAT-1", name="Material")
        assert material.id == again.id
        assert db.query(PlatformMaterial).count() == 1
        assert db.query(DataProvenance).count() == 1
        intent = actions.propose(db, tenant_id="tenant-test", plant_id="plant-test", membership_id=None,
                                 action_type="procurement.po.reschedule", target_type="po", target_id="po-1", payload={},
                                 rationale="Supplier commitment moved", idempotency_key="reschedule-po-1")
        assert actions.propose(db, tenant_id="tenant-test", plant_id="plant-test", membership_id=None,
                               action_type="procurement.po.reschedule", target_type="po", target_id="po-1", payload={},
                               rationale="Supplier commitment moved", idempotency_key="reschedule-po-1").id == intent.id
        actions.decide(db, intent, None, True, "Approved for demo")
        execution = actions.execute_simulated(db, intent)
        assert execution.mode == "simulated"
        assert db.query(ActionExecution).count() == 1
        assert db.query(ActionOutcome).filter_by(execution_id=execution.id).one().verification_status == "verified_simulation"
