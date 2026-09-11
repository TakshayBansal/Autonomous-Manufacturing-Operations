"""Complete canonical manufacturing and integration primitives.

Revision ID: 0059_core_platform_completion
Revises: 0058_core_platform_foundation
"""
from alembic import op
import sqlalchemy as sa

from app.db.models import Base

revision = "0059_core_platform_completion"
down_revision = "0058_core_platform_foundation"
branch_labels = None
depends_on = None

TABLE_NAMES = [
    "platform_products", "platform_boms", "platform_bom_items",
    "platform_inventory_locations", "platform_inventory_positions",
    "platform_entity_relationships", "platform_source_systems", "platform_state_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("suppliers")}
    additions = [
        ("company_id", sa.Column("company_id", sa.String(64), nullable=True)),
        ("code", sa.Column("code", sa.String(120), nullable=True)),
        ("legal_name", sa.Column("legal_name", sa.String(240), nullable=True)),
        ("default_lead_time_days", sa.Column("default_lead_time_days", sa.Integer(), nullable=True)),
        ("metadata_json", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}")),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("suppliers", column)
    op.execute("UPDATE suppliers SET code = erp_vendor_id WHERE code IS NULL")
    op.execute("UPDATE suppliers SET legal_name = name WHERE legal_name IS NULL")
    for name in TABLE_NAMES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLE_NAMES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
