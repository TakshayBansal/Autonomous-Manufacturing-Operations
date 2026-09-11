"""create V1 support tables absent from legacy stamped databases

Revision ID: 0005_missing_baseline_tables
Revises: 0004_schema_compatibility
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa

from app.db.models import Base


revision = "0005_missing_baseline_tables"
down_revision = "0004_schema_compatibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for source in Base.metadata.sorted_tables:
        if source.name in existing:
            continue
        metadata = sa.MetaData()
        table = source.to_metadata(metadata)
        op.create_table(
            table.name,
            *list(table.columns),
            *list(table.constraints),
            schema=table.schema,
        )
        existing.add(source.name)


def downgrade() -> None:
    # This repair is forward-only because a table may contain operational data
    # by the time a deployment is rolled back.
    pass
