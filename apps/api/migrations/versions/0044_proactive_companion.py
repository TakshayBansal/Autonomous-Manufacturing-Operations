"""Persistent proactive companion interventions and controls."""
from alembic import op
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.db.models import Base

revision = "0044_proactive_companion"
down_revision = "0043_signed_policy_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for name in ("companion_preferences", "companion_trigger_policies", "companion_interventions"):
        Base.metadata.tables[name].create(bind, checkfirst=True)
    tenants = Base.metadata.tables["tenants"]
    flags = Base.metadata.tables["tenant_feature_flags"]
    for tenant_id in bind.execute(select(tenants.c.id).where(tenants.c.workspace_kind == "demo")).scalars():
        exists = bind.execute(select(flags.c.id).where(
            flags.c.tenant_id == tenant_id, flags.c.key == "proactive_companion",
        )).first()
        if not exists:
            bind.execute(flags.insert().values(
                id=str(uuid4()), tenant_id=tenant_id, key="proactive_companion", enabled=True,
                config={}, updated_at=datetime.now(timezone.utc),
            ))


def downgrade() -> None:
    bind = op.get_bind()
    for name in ("companion_interventions", "companion_trigger_policies", "companion_preferences"):
        Base.metadata.tables[name].drop(bind, checkfirst=True)
