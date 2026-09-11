"""Add per-connection manifest controls and emergency write switch."""

from alembic import op
import sqlalchemy as sa

revision = "0015_connector_controls"
down_revision = "0014_excel_connector_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {row["name"] for row in sa.inspect(op.get_bind()).get_columns("integration_connections")}
    additions = {
        "provider_version": sa.Column("provider_version", sa.String(32), nullable=False, server_default="1.0"),
        "enabled_capabilities": sa.Column("enabled_capabilities", sa.JSON(), nullable=False, server_default="[]"),
        "writes_enabled": sa.Column("writes_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        "config": sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("integration_connections", column)


def downgrade() -> None:
    for name in ("config", "writes_enabled", "enabled_capabilities", "provider_version"):
        op.drop_column("integration_connections", name)
