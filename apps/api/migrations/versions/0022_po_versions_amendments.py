"""Add immutable purchase-order version and change-control metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0022_po_versions_amendments"
down_revision = "0021_split_award_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("po_drafts")}
    with op.batch_alter_table("po_drafts") as batch:
        batch.drop_constraint("ck_po_status", type_="check")
        for name, column in (
            ("root_po_id", sa.Column("root_po_id", sa.String(64), nullable=True)),
            ("previous_version_id", sa.Column("previous_version_id", sa.String(64), nullable=True)),
            ("revision_number", sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1")),
            ("revision_kind", sa.Column("revision_kind", sa.String(32), nullable=False, server_default="original")),
            ("change_reason", sa.Column("change_reason", sa.Text(), nullable=False, server_default="")),
            ("change_summary", sa.Column("change_summary", sa.JSON(), nullable=False, server_default="{}")),
            ("issued_at", sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True)),
            ("superseded_at", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True)),
        ):
            if name not in columns:
                batch.add_column(column)
        batch.create_check_constraint("ck_po_status", "status IN ('pending_approval','approved_pending_outbox','posting','simulated_posted','posted','failed','rejected','superseded','cancelled')")
        for name in ("root_po_id", "previous_version_id", "revision_kind"):
            if name not in columns:
                batch.create_index(f"ix_po_drafts_{name}", [name])


def downgrade() -> None:
    pass
