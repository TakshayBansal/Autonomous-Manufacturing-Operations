"""Backfill scoped public IDs on incrementally upgraded tables.

Revision ID: 0035_scoped_public_ids
Revises: 0034_supplier_delivery_updates
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0035_scoped_public_ids"
down_revision = "0034_supplier_delivery_updates"
branch_labels = None
depends_on = None


SCOPED_TABLES = (
    "award_batches",
    "invoice_payment_statuses",
    "supplier_certificates",
    "supplier_channel_messages",
    "supplier_compliance_requirements",
    "supplier_corrective_actions",
    "supplier_performance_events",
    "supplier_returns",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name in SCOPED_TABLES:
        if table_name not in existing_tables:
            continue
        columns = {
            column["name"] for column in sa.inspect(bind).get_columns(table_name)
        }
        if "public_id" not in columns:
            op.add_column(
                table_name,
                sa.Column("public_id", sa.String(36), nullable=True),
            )
        table = sa.table(
            table_name,
            sa.column("id", sa.String(64)),
            sa.column("public_id", sa.String(36)),
        )
        missing_ids = bind.execute(
            sa.select(table.c.id).where(table.c.public_id.is_(None))
        ).scalars().all()
        for record_id in missing_ids:
            bind.execute(
                table.update().where(table.c.id == record_id).values(
                    public_id=str(uuid4()),
                )
            )
        index_name = f"ix_{table_name}_public_id"
        indexes = {
            index["name"] for index in sa.inspect(bind).get_indexes(table_name)
        }
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column(
                "public_id",
                existing_type=sa.String(36),
                nullable=False,
            )
            if index_name not in indexes:
                batch.create_index(index_name, ["public_id"], unique=True)


def downgrade() -> None:
    pass
