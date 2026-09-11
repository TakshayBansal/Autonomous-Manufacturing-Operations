import json
from sqlalchemy.orm import Session
from app.db import models
from app.db.session import engine
from app.platform.backfill import backfill_tenant


def main() -> None:
    with Session(engine) as db:
        reports = {tenant.id: backfill_tenant(db, tenant.id).as_dict() for tenant in db.query(models.Tenant).all()}
        db.commit()
    print(json.dumps(reports, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
