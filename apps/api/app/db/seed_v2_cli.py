import argparse
import time
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.db.session import engine
from app.db.seed_v2_simulation import seed_northstar


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    tenant_id = None
    for attempt in range(1, 6):
        try:
            with Session(engine) as db:
                tenant = seed_northstar(db, reset=args.reset)
                tenant_id = tenant.id
                db.commit()
            break
        except OperationalError as exc:
            is_deadlock = "deadlock detected" in str(exc).lower()
            if not is_deadlock or attempt == 5:
                raise
            print(f"Northstar reset met concurrent factory ingestion; retrying ({attempt}/5)...")
            time.sleep(attempt * 0.5)
    assert tenant_id is not None
    print(f"Northstar simulation workspace ready: {tenant_id}")


if __name__ == "__main__":
    main()
