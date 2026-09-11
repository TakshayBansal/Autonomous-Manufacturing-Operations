"""Add supplier delivery and dispatch-evidence fields.

Revision ID: 0033_supplier_delivery_portal
Revises: 0032_exchange_rate_evidence
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_supplier_delivery_portal"
down_revision = "0032_exchange_rate_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {row["name"] for row in sa.inspect(op.get_bind()).get_columns("asns")}
    additions = [
        sa.Column("dispatch_reference", sa.String(120), nullable=False, server_default=""),
        sa.Column("expected_delivery", sa.String(32), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default="internal"),
        sa.Column("supplier_document_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in additions:
        if column.name not in columns:
            op.add_column("asns", column)


def downgrade() -> None:
    pass
