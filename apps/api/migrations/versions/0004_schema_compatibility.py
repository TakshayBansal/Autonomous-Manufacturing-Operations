"""reconcile legacy baseline databases with the current mapped schema

Revision ID: 0004_schema_compatibility
Revises: 0003_identity_hardening
Create Date: 2026-07-13

Some early development databases were stamped at the V1 revision after their
tables had been created by an older model snapshot. This migration adds only
missing scalar columns and preserves every existing row.
"""

from alembic import op
import sqlalchemy as sa

from app.db.models import Base


revision = "0004_schema_compatibility"
down_revision = "0003_identity_hardening"
branch_labels = None
depends_on = None


def _copy_for_add(column: sa.Column) -> sa.Column:
    server_default = None
    nullable = True
    if column.name == "version":
        server_default = sa.text("1")
        nullable = False
    return sa.Column(
        column.name,
        column.type,
        nullable=nullable,
        server_default=server_default,
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {
            column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
        }
        for column in table.columns:
            if column.name not in existing_columns:
                op.add_column(table_name, _copy_for_add(column))
                existing_columns.add(column.name)

    bind = op.get_bind()
    if "users" in existing_tables:
        bind.execute(sa.text("UPDATE users SET version=1 WHERE version IS NULL"))
        bind.execute(sa.text(
            "UPDATE users SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL"
        ))
        bind.execute(sa.text(
            "UPDATE users SET updated_at=CURRENT_TIMESTAMP WHERE updated_at IS NULL"
        ))
    if "role_definitions" in existing_tables:
        bind.execute(sa.text(
            "UPDATE role_definitions SET version=1 WHERE version IS NULL"
        ))
        bind.execute(sa.text(
            "UPDATE role_definitions SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL"
        ))
        bind.execute(sa.text(
            "UPDATE role_definitions SET updated_at=CURRENT_TIMESTAMP WHERE updated_at IS NULL"
        ))


def downgrade() -> None:
    # Compatibility migrations are intentionally forward-only: removing these
    # columns could discard fields populated after upgrade.
    pass
