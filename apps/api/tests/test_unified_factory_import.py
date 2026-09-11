from io import BytesIO
from openpyxl import Workbook

from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.platform import unified_imports


def fixture() -> bytes:
    workbook = Workbook(); manifest = workbook.active; manifest.title = "Manifest"
    manifest.append(["schema_version"]); manifest.append([unified_imports.VERSION])
    sheets = {
        "PROC_Items": [["external_key", "code", "name", "uom"], ["ITEM-MAT-182", "MAT-182", "ECU control component", "EA"]],
        "PROC_Suppliers": [["external_key", "name", "status"], ["SUP-X", "Supplier X", "approved"]],
        "SCM_Materials": [["external_id", "material_code", "description", "material_type", "base_uom"], ["SCM-MAT-182", "MAT-182", "ECU control component", "COMPONENT", "EA"]],
        "SCM_Inventory": [["external_id", "material_code", "snapshot_at", "on_hand_qty", "available_qty", "uom"], ["INV-A-MAT-182", "MAT-182", "2026-09-07T08:00:00Z", 800, 800, "EA"]],
        "OPS_Lines": [["external_id", "code", "name", "standard_good_rate_per_minute"], ["LINE-3", "LINE-3", "Line 3", 2]],
        "OPS_WorkOrders": [["external_id", "line_code", "product_code", "product_name", "quantity", "planned_start_at", "planned_end_at"], ["WO-981", "LINE-3", "ECU-A", "Honda ECU-A", 440, "2026-09-10T06:00:00Z", "2026-09-10T14:00:00Z"]],
        "OPS_MaterialRequirements": [["external_id", "work_order_external_id", "material_code", "quantity", "uom", "required_at"], ["WO-981-MAT-182", "WO-981", "MAT-182", 440, "EA", "2026-09-10T06:00:00Z"]],
    }
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows: sheet.append(row)
    output = BytesIO(); workbook.save(output); return output.getvalue()


def test_one_preview_and_atomic_commit_populates_three_domains():
    with SessionLocal() as db:
        reset_workspace_database(db)
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        if not db.get(models.Uom, "EA"):
            db.add(models.Uom(id="EA", label="Each")); db.flush()
        content = fixture()
        batch = unified_imports.preview(db, user, "factory.xlsx", content)
        assert batch.status == "previewed"
        assert batch.summary["errors"] == []
        assert set(batch.summary["children"]) == {"procurement", "scm"}
        unified_imports.commit(db, user, batch); db.commit()
        assert batch.status == "completed"
        assert db.query(models.Item).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, code="MAT-182").count() == 1
        assert db.query(models.ProductionWorkOrder).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, external_reference="WO-981").count() == 1
        assert db.query(models.ProductionMaterialRequirement).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, material_code="MAT-182").count() == 1
        replay = unified_imports.preview(db, user, "renamed.xlsx", content)
        assert replay.id == batch.id


def test_canonical_automotive_template_commits_without_hidden_demo_writes():
    with SessionLocal() as db:
        reset_workspace_database(db)
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        if not db.get(models.Uom, "EA"):
            db.add(models.Uom(id="EA", label="Each")); db.flush()
        batch = unified_imports.preview(db, user, "automotive.xlsx", unified_imports.automotive_template())
        assert batch.summary["errors"] == []
        unified_imports.commit(db, user, batch); db.commit()
        assert batch.status == "completed"
        assert db.query(models.Supplier).filter(models.Supplier.tenant_id == user.tenant_id,
            models.Supplier.plant_id == user.plant_id, models.Supplier.erp_vendor_id.in_(("SUP-X", "SUP-Y", "SUP-Z", "SUP-W"))).count() == 4
        assert db.query(models.PODraft).filter(models.PODraft.tenant_id == user.tenant_id,
            models.PODraft.plant_id == user.plant_id, models.PODraft.business_number.like("PO-%")).count() >= 8
        assert db.query(models.ProductionWorkOrder).filter(models.ProductionWorkOrder.tenant_id == user.tenant_id,
            models.ProductionWorkOrder.plant_id == user.plant_id,
            models.ProductionWorkOrder.external_reference.like("WO-%")).count() >= 8
        from app.scm import models as scm_models
        assert db.query(scm_models.SCMMaterial).count() == 20
        assert db.query(scm_models.SCMBOM).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).count() == 12
        assert db.query(scm_models.SCMMaterialRequirement).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).count() >= 40


def test_connected_factory_generates_cases_and_ranked_options_from_planning():
    with SessionLocal() as db:
        reset_workspace_database(db)
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        if not db.get(models.Uom, "EA"):
            db.add(models.Uom(id="EA", label="Each")); db.flush()
        batch = unified_imports.preview(db, user, "connected-v2.xlsx", unified_imports.automotive_template())
        assert batch.summary["errors"] == []
        unified_imports.commit(db, user, batch)
        from app.scm import models as scm_models
        from app.scm.service import create_run, execute_run
        from app.platform.case_models import CaseEvidence, DecisionAlternative, DecisionRecord, RecoveryTarget
        from app.platform.models import OperationalCase
        run = create_run(db, user, trigger_type="IMPORT")
        execute_run(db, run.id); db.flush()
        risks = db.query(scm_models.SCMMaterialRiskSummary).filter(
            scm_models.SCMMaterialRiskSummary.planning_run_id == run.id,
            scm_models.SCMMaterialRiskSummary.shortage_qty > 0).all()
        assert len(risks) >= 2
        assert any(row.affected_finished_goods_count >= 2 for row in risks), [
            (row.material_id, row.affected_finished_goods_count, row.affected_customers_count) for row in risks]
        assert any(row.affected_customers_count >= 2 for row in risks)
        assert db.query(OperationalCase).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id,
                                                   case_type="material_shortage").count() >= 2
        decisions = db.query(DecisionRecord).filter_by(planning_run_id=run.id).all()
        assert decisions
        assert all(len(row.source_event_id) <= 64 for row in db.query(CaseEvidence).filter(
            CaseEvidence.case_id.in_([row.case_id for row in decisions]),
            CaseEvidence.source_event_id.is_not(None)).all())
        assert db.query(DecisionAlternative).filter(
            DecisionAlternative.decision_record_id.in_([row.id for row in decisions])).count() >= len(decisions)
        assert db.query(RecoveryTarget).filter(
            RecoveryTarget.case_id.in_([row.case_id for row in decisions])).count() == len(decisions)
        from app.scm.recommendations import simulate
        recommendations = db.query(scm_models.SCMRecommendation).filter_by(planning_run_id=run.id).all()
        resolving = next(recommendation for recommendation in recommendations if simulate(db, recommendation).resolves_risk)
        resolving.status = "ACCEPTED"
        db.flush()
        from app.scm.router import SimulatedExecutionConfirmation, confirm_simulated_execution
        result = confirm_simulated_execution(resolving.id,
            SimulatedExecutionConfirmation(confirmation_reference="pytest planner confirmation"), db, user)
        assert result["risk_status"] == "RESOLVED"
        case = db.get(OperationalCase, result["case_id"])
        assert case.recovery_state in {"MONITORING", "NOT_RECOVERED"}
        verification_run = create_run(db, user, trigger_type="MANUAL")
        execute_run(db, verification_run.id); db.flush()
        assert case.recovery_state == "RECOVERED"


def test_connected_demo_can_upgrade_a_workspace_with_the_old_mat182_import():
    with SessionLocal() as db:
        reset_workspace_database(db)
        user = db.query(models.User).filter_by(email="admin@genuinegigs.local").one()
        if not db.get(models.Uom, "EA"):
            db.add(models.Uom(id="EA", label="Each")); db.flush()
        legacy = unified_imports.preview(db, user, "legacy.xlsx", fixture())
        unified_imports.commit(db, user, legacy); db.flush()
        connected = unified_imports.preview(db, user, "connected-v2.xlsx", unified_imports.automotive_template())
        unified_imports.preserve_existing_demo_masters(db, connected)
        assert connected.summary["errors"] == [], connected.summary["errors"]
        unified_imports.commit(db, user, connected)
        assert connected.status == "completed"
