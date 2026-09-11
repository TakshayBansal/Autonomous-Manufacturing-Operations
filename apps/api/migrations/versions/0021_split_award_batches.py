"""Add immutable split-award batches and award allocation lineage."""
from alembic import op
import sqlalchemy as sa

revision = "0021_split_award_batches"
down_revision = "0020_quote_revisions_partial_bids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "award_batches" not in inspector.get_table_names():
        op.create_table(
            "award_batches",
            sa.Column("comparison_id", sa.String(64), sa.ForeignKey("bid_comparisons.id"), nullable=False),
            sa.Column("comparison_version", sa.Integer(), nullable=False),
            sa.Column("allocation_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="confirmed"),
            sa.Column("created_by_user_id", sa.String(64), nullable=False),
            sa.Column("total_awarded_quantity", sa.Float(), nullable=False),
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("business_number", sa.String(80), nullable=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("plant_id", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("tenant_id", "comparison_id", "comparison_version", "allocation_hash", name="uq_award_batch_allocation"),
            sa.CheckConstraint("total_awarded_quantity > 0", name="ck_award_batch_quantity_positive"),
        )
        for column in ("comparison_id", "allocation_hash", "status", "created_by_user_id", "tenant_id", "plant_id"):
            op.create_index(f"ix_award_batches_{column}", "award_batches", [column])
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("award_decisions")}
    if "award_batch_id" not in columns:
        with op.batch_alter_table("award_decisions") as batch:
            batch.add_column(sa.Column("award_batch_id", sa.String(64), nullable=True))
            batch.create_foreign_key("fk_award_decisions_batch", "award_batches", ["award_batch_id"], ["id"])
            batch.create_index("ix_award_decisions_award_batch_id", ["award_batch_id"])


def downgrade() -> None:
    pass
