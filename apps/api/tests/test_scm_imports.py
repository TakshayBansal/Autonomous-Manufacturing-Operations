from io import BytesIO

from openpyxl import Workbook

from app.db import models as core_models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.scm import imports, models


def workbook_bytes() -> bytes:
    workbook = Workbook()
    materials = workbook.active
    materials.title = "Materials"
    materials.append(["external_id", "material_code", "description", "material_type", "base_uom"])
    materials.append(["SCM-MAT-IMPORT-1", "SCM-IMP-1", "Imported component", "COMPONENT", "EA"])
    inventory = workbook.create_sheet("Inventory")
    inventory.append(["external_id", "material_code", "snapshot_at", "on_hand_qty", "available_qty", "uom"])
    inventory.append(["SCM-INV-IMPORT-1", "SCM-IMP-1", "2026-08-19T00:00:00Z", 100, 90, "EA"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_scm_file_import_is_previewed_traceable_and_idempotent():
    with SessionLocal() as db:
        reset_workspace_database(db)
        user = db.query(core_models.User).filter_by(email="admin@genuinegigs.local").one()
        if not db.get(core_models.Uom, "EA"):
            db.add(core_models.Uom(id="EA", label="Each"))
        db.flush()
        content = workbook_bytes()
        preview = imports.preview(db, user, "scm.xlsx", content)
        db.flush()
        assert preview.summary == {"valid": 2, "warning": 0, "rejected": 0, "ignored": 0}
        imports.commit(db, user, preview)
        db.commit()
        assert preview.status == "completed"
        assert db.query(models.SCMMaterial).filter_by(material_code="SCM-IMP-1").count() == 1
        assert db.query(models.SCMInventorySnapshot).filter_by(source_record_id="SCM-INV-IMPORT-1").count() == 1
        repeat = imports.preview(db, user, "scm.xlsx", content)
        assert repeat.id == preview.id
        imports.commit(db, user, repeat)
        assert db.query(models.SCMInventorySnapshot).filter_by(source_record_id="SCM-INV-IMPORT-1").count() == 1

