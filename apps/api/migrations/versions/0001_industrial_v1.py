"""production procure-to-receive baseline

Revision ID: 0001_industrial_v1
Revises:
Create Date: 2026-07-07

The clean-rebuild decision allows this revision to remain the single baseline.
Schema creation is owned exclusively by Alembic; application startup never creates
or mutates tables.
"""

from alembic import op
from sqlalchemy import MetaData

from app.db.models import Base

revision = "0001_industrial_v1"
down_revision = None
branch_labels = None
depends_on = None


def _migration_metadata() -> MetaData:
    metadata = MetaData()
    for source in Base.metadata.sorted_tables:
        source.to_metadata(metadata)
    return metadata


def upgrade() -> None:
    metadata = _migration_metadata()
    for table in metadata.sorted_tables:
        op.create_table(table.name, *list(table.columns), *list(table.constraints), schema=table.schema)

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION genuinegigs_deny_immutable_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'immutable ledger records cannot be updated or deleted';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for table_name in ("audit_events", "approval_decisions"):
            op.execute(
                f"CREATE TRIGGER {table_name}_immutable BEFORE UPDATE OR DELETE ON {table_name} "
                "FOR EACH ROW EXECUTE FUNCTION genuinegigs_deny_immutable_mutation();"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS genuinegigs_deny_immutable_mutation() CASCADE")
    metadata = _migration_metadata()
    for table in reversed(metadata.sorted_tables):
        op.drop_table(table.name, schema=table.schema)
