"""Add rejected-material return, replacement receipt, and reinspection linkage."""
from alembic import op
import sqlalchemy as sa

revision = "0019_supplier_returns_replacements"
down_revision = "0018_supplier_channel_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "supplier_returns" not in inspector.get_table_names():
        op.create_table(
            "supplier_returns",
            sa.Column("po_draft_id", sa.String(64), sa.ForeignKey("po_drafts.id"), nullable=False),
            sa.Column("inspection_id", sa.String(64), sa.ForeignKey("inspection_results.id"), nullable=False),
            sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("case_id", sa.String(64), sa.ForeignKey("cases.id"), nullable=True),
            sa.Column("status", sa.String(48), nullable=False),
            sa.Column("rejected_quantity", sa.Float(), nullable=False),
            sa.Column("return_quantity", sa.Float(), nullable=False),
            sa.Column("replacement_requested_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("replacement_received_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("business_number", sa.String(80), nullable=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("plant_id", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("rejected_quantity > 0 AND return_quantity > 0", name="ck_supplier_return_quantities_positive"),
            sa.CheckConstraint("return_quantity <= rejected_quantity", name="ck_supplier_return_quantity_cap"),
            sa.CheckConstraint("replacement_requested_quantity >= 0 AND replacement_received_quantity >= 0", name="ck_supplier_replacement_quantities_nonnegative"),
        )
        for column in ("po_draft_id", "inspection_id", "supplier_id", "case_id", "status", "tenant_id", "plant_id"):
            op.create_index(f"ix_supplier_returns_{column}", "supplier_returns", [column])
    receipt_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("store_receipts")}
    if "supplier_return_id" not in receipt_columns:
        with op.batch_alter_table("store_receipts") as batch:
            batch.add_column(sa.Column("supplier_return_id", sa.String(64), nullable=True))
            batch.create_index("ix_store_receipts_supplier_return_id", ["supplier_return_id"])


def downgrade() -> None:
    pass
