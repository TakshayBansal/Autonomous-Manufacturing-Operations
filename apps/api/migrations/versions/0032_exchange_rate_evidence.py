"""Add source-versioned exchange-rate evidence.

Revision ID: 0032_exchange_rate_evidence
Revises: 0031_invoice_document_extraction
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_exchange_rate_evidence"
down_revision = "0031_invoice_document_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "exchange_rate_observations" not in tables:
        op.create_table(
            "exchange_rate_observations",
            sa.Column("source_currency", sa.String(16), nullable=False),
            sa.Column("target_currency", sa.String(16), nullable=False, server_default="INR"),
            sa.Column("rate", sa.Float(), nullable=False),
            sa.Column("source_name", sa.String(160), nullable=False),
            sa.Column("source_reference", sa.String(240), nullable=False, server_default=""),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="verified"),
            sa.Column("recorded_by_user_id", sa.String(64), nullable=False),
            sa.Column("id", sa.String(64), primary_key=True), sa.Column("public_id", sa.String(36), nullable=False, unique=True),
            sa.Column("business_number", sa.String(80), nullable=True), sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("plant_id", sa.String(64), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("rate > 0", name="ck_exchange_rate_positive"),
            sa.UniqueConstraint("tenant_id", "business_number", name="uq_exchange_rate_observations_tenant_business_number"),
        )
        for column in ("public_id", "business_number", "tenant_id", "plant_id", "source_currency", "target_currency", "observed_at", "status"):
            op.create_index(f"ix_exchange_rate_observations_{column}", "exchange_rate_observations", [column], unique=column == "public_id")
    columns = {row["name"] for row in sa.inspect(op.get_bind()).get_columns("supplier_quotes")}
    if "exchange_rate_observation_id" not in columns:
        # SQLite cannot add a foreign-key constraint with plain ALTER TABLE.
        # Batch mode keeps the same contract while supporting incremental demo
        # and Excel-simulation database upgrades.
        with op.batch_alter_table("supplier_quotes") as batch:
            batch.add_column(sa.Column(
                "exchange_rate_observation_id", sa.String(64),
                sa.ForeignKey("exchange_rate_observations.id"), nullable=True,
            ))
            batch.create_index(
                "ix_supplier_quotes_exchange_rate_observation_id",
                ["exchange_rate_observation_id"],
            )


def downgrade() -> None:
    pass
