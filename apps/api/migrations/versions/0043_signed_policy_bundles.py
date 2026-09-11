"""Signed, versioned autonomy policy bundles with rollback state."""
from alembic import op
from app.db.models import Base

revision = "0043_signed_policy_bundles"
down_revision = "0042_outcome_contracts"
branch_labels = None
depends_on = None

def upgrade() -> None:
    Base.metadata.tables["policy_bundles"].create(op.get_bind(), checkfirst=True)

def downgrade() -> None:
    Base.metadata.tables["policy_bundles"].drop(op.get_bind(), checkfirst=True)
