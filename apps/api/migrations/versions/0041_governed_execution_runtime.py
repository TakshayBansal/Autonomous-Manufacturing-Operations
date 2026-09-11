"""Governed execution, event-consumer, policy, sandbox, and reporting records."""
from alembic import op

from app.db.models import Base

revision = "0041_governed_execution_runtime"
down_revision = "0040_agentic_procurement_cycles"
branch_labels = None
depends_on = None

TABLES = (
    "event_consumer_receipts", "agent_run_attempts", "policy_decisions",
    "autonomy_policies", "sandbox_runs", "operational_reports",
    "policy_bundles",
)

def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind, checkfirst=True)

def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind, checkfirst=True)
