"""Add supplier requested-change acknowledgement workflow.

Revision ID: 0029_supplier_acknowledgement_changes
Revises: 0028_procurement_policy_engine
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_supplier_acknowledgement_changes"
down_revision = "0028_procurement_policy_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {row["name"] for row in inspector.get_columns("supplier_acknowledgements")}
    if "requested_changes" in columns:
        return
    checks = {row.get("name") for row in inspector.get_check_constraints("supplier_acknowledgements")}
    with op.batch_alter_table("supplier_acknowledgements") as batch:
        batch.add_column(sa.Column("requested_changes", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("reviewed_by_user_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("linked_po_revision_id", sa.String(64), nullable=True))
        if "ck_ack_status" in checks:
            batch.drop_constraint("ck_ack_status", type_="check")
        batch.create_check_constraint("ck_ack_status", "status IN ('accepted','rejected','change_requested','change_prepared')")
        batch.create_index("ix_supplier_acknowledgements_linked_po_revision_id", ["linked_po_revision_id"])


def downgrade() -> None:
    pass
