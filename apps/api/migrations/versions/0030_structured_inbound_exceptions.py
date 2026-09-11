"""Add structured Stores and Quality exception evidence.

Revision ID: 0030_structured_inbound_exceptions
Revises: 0029_supplier_acknowledgement_changes
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_structured_inbound_exceptions"
down_revision = "0029_supplier_acknowledgement_changes"
branch_labels = None
depends_on = None


def _add_missing(table: str, definitions: list[sa.Column]) -> None:
    existing = {row["name"] for row in sa.inspect(op.get_bind()).get_columns(table)}
    for column in definitions:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_missing("store_receipts", [
        sa.Column("exception_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("observed_item_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("certificate_status", sa.String(48), nullable=False, server_default="received"),
        sa.Column("exception_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("production_impact", sa.Boolean(), nullable=False, server_default=sa.false()),
    ])
    _add_missing("inspection_results", [
        sa.Column("defect_codes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("inspection_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("production_impact", sa.Boolean(), nullable=False, server_default=sa.false()),
    ])


def downgrade() -> None:
    pass
