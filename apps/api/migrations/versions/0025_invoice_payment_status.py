"""Add read-only invoice payment-status observations."""
from alembic import op
import sqlalchemy as sa

revision = "0025_invoice_payment_status"
down_revision = "0024_supplier_performance_capa"
branch_labels = None
depends_on = None


def upgrade():
    if "invoice_payment_statuses" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "invoice_payment_statuses",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invoice_id", sa.String(64), sa.ForeignKey("supplier_invoices.id"), nullable=False),
        sa.Column("connection_id", sa.String(64), sa.ForeignKey("integration_connections.id"), nullable=False),
        sa.Column("external_key", sa.String(180), nullable=False), sa.Column("status", sa.String(48), nullable=False),
        sa.Column("external_version", sa.String(80), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_payload_hash", sa.String(64), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_key", "external_version", "source_payload_hash", name="uq_invoice_payment_observation"),
        sa.CheckConstraint("status IN ('not_released','scheduled','processing','paid','partially_paid','on_hold','rejected','unknown')", name="ck_invoice_payment_status"),
    )
    for column in ("tenant_id", "plant_id", "invoice_id", "connection_id", "external_key", "status", "observed_at"):
        op.create_index(f"ix_invoice_payment_statuses_{column}", "invoice_payment_statuses", [column])


def downgrade():
    pass
