"""Database-backed coordination for tenant-wide maintenance operations."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def acquire_tenant_transaction_lock(db: Session, tenant_id: str) -> None:
    """Serialize reset and connector writes without blocking other tenants.

    PostgreSQL advisory transaction locks are released automatically on commit
    or rollback. SQLite test databases are single-process and need no analogue.
    """
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                   {"lock_key": f"genuinegigs:tenant-maintenance:{tenant_id}"})
