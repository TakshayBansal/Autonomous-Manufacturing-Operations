"""enable governed agents for upgraded demo workspaces

Revision ID: 0006_enable_demo_agents
Revises: 0005_missing_baseline_tables
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_enable_demo_agents"
down_revision = "0005_missing_baseline_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE tenants SET agent_enabled=true "
        "WHERE workspace_kind='demo' AND status='active'"
    ))
    bind.execute(sa.text(
        "UPDATE agent_profiles SET enabled=true "
        "WHERE tenant_id IN (SELECT id FROM tenants WHERE workspace_kind='demo')"
    ))


def downgrade() -> None:
    # Tenant policy changes made after migration must not be overwritten.
    pass
