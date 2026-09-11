from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.db.seed import (
    ensure_demo_role_coverage, ensure_demo_supplier_capability_coverage,
    reset_workspace_database,
)
from app.db.demo_v2_bootstrap import bootstrap_apex_v2
from app.db.session import engine


def main() -> None:
    with Session(engine) as db:
        if db.query(models.Tenant).count():
            tenants = db.query(models.Tenant).all()
            upgraded = sum(bootstrap_apex_v2(db, tenant, datetime.now(timezone.utc)) for tenant in tenants)
            changed = ensure_demo_role_coverage(db)
            capabilities_created = ensure_demo_supplier_capability_coverage(db)
            db.commit()
            print(
                "Demo data reconciled "
                f"(V2 workspaces upgraded={upgraded}, role coverage changed={changed}, supplier capabilities added={capabilities_created})"
            )
            return
        reset_workspace_database(db, v2_reference_time=datetime.now(timezone.utc))
        ensure_demo_supplier_capability_coverage(db)
        db.commit()
    print("Baseline workspace seeded")


if __name__ == "__main__":
    main()
