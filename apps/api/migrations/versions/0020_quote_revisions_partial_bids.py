"""Add immutable quotation revision lineage and partial-bid metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0020_quote_revisions_partial_bids"
down_revision = "0019_supplier_returns_replacements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("supplier_quotes")}
    with op.batch_alter_table("supplier_quotes") as batch:
        if "revision_number" not in columns:
            batch.add_column(sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"))
        if "supersedes_quote_id" not in columns:
            batch.add_column(sa.Column("supersedes_quote_id", sa.String(64), nullable=True))
            batch.create_index("ix_supplier_quotes_supersedes_quote_id", ["supersedes_quote_id"])
        if "participation_status" not in columns:
            batch.add_column(sa.Column("participation_status", sa.String(32), nullable=False, server_default="complete"))
            batch.create_index("ix_supplier_quotes_participation_status", ["participation_status"])
        if "currency" not in columns:
            batch.add_column(sa.Column("currency", sa.String(16), nullable=False, server_default="INR"))
        if "exchange_rate_to_inr" not in columns:
            batch.add_column(sa.Column("exchange_rate_to_inr", sa.Float(), nullable=False, server_default="1"))


def downgrade() -> None:
    pass
