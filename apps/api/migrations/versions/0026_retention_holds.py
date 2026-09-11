"""Add governed retention holds."""
from alembic import op
import sqlalchemy as sa

revision = "0026_retention_holds"
down_revision = "0025_invoice_payment_status"
branch_labels = None
depends_on = None


def upgrade():
    if "retention_holds" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "retention_holds",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("placed_by_membership_id", sa.String(64), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_membership_id", sa.String(64), nullable=True),
        sa.UniqueConstraint("tenant_id", "entity_type", "entity_id", name="uq_active_retention_hold_entity"),
        sa.UniqueConstraint("public_id"), sa.UniqueConstraint("business_number"),
    )
    for column in ("tenant_id", "plant_id", "entity_type", "entity_id", "placed_by_membership_id"):
        op.create_index(f"ix_retention_holds_{column}", "retention_holds", [column])


def downgrade():
    pass
