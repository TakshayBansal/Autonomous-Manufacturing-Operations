"""Repair legacy global business-number unique indexes.

Revision ID: 0063_tenant_business_indexes
Revises: 0062_scm_v1_remaining_phases

Migration 0027 converted unique constraints to tenant-scoped constraints, but
PostgreSQL reports column ``unique=True`` declarations as unique indexes.  Those
indexes were therefore left behind on databases created from the original
schema and prevented separate tenants from using the same business reference.
"""

from alembic import op
import sqlalchemy as sa


revision = "0063_tenant_business_indexes"
down_revision = "0062_scm_v1_remaining_phases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns(table)}
        if not {"tenant_id", "business_number"}.issubset(columns):
            continue

        indexes = inspector.get_indexes(table)
        global_unique_indexes = [
            index
            for index in indexes
            if index.get("unique")
            and index.get("column_names") == ["business_number"]
        ]
        for index in global_unique_indexes:
            op.drop_index(index["name"], table_name=table)

        # Retain a normal lookup index expected by ScopedMixin. Avoid creating
        # it if the database already has an equivalent non-unique index.
        remaining_indexes = [
            index for index in indexes if index not in global_unique_indexes
        ]
        if not any(
            not index.get("unique")
            and index.get("column_names") == ["business_number"]
            for index in remaining_indexes
        ):
            op.create_index(
                f"ix_{table}_business_number",
                table,
                ["business_number"],
                unique=False,
            )


def downgrade() -> None:
    # Restoring global uniqueness is unsafe once multiple tenants legitimately
    # share business references. This migration is intentionally forward-only.
    pass
