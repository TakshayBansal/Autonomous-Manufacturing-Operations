"""Persist governed inbound and outbound supplier-channel messages."""
from alembic import op
import sqlalchemy as sa

revision = "0018_supplier_channel_messages"
down_revision = "0017_external_owned_purchase_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "supplier_channel_messages" in inspector.get_table_names():
        return
    op.create_table(
        "supplier_channel_messages",
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("external_message_id", sa.String(240), nullable=False),
        sa.Column("sender", sa.String(320), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False, server_default=""),
        sa.Column("subject", sa.String(500), nullable=False, server_default=""),
        sa.Column("body_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("rfq_id", sa.String(64), sa.ForeignKey("rfqs.id"), nullable=True),
        sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("canonical_record_ids", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "channel", "external_message_id", name="uq_supplier_channel_external_message"),
    )
    for column in ("channel", "direction", "sender", "status", "rfq_id", "supplier_id", "tenant_id", "plant_id"):
        op.create_index(f"ix_supplier_channel_messages_{column}", "supplier_channel_messages", [column])


def downgrade() -> None:
    pass
