"""identity recovery token store

Revision ID: 0003_identity_hardening
Revises: 0002_role_agent_os
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa

from app.db.models import Base


revision = "0003_identity_hardening"
down_revision = "0002_role_agent_os"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "identity_tokens" in sa.inspect(op.get_bind()).get_table_names():
        return
    source = Base.metadata.tables["identity_tokens"]
    metadata = sa.MetaData()
    table = source.to_metadata(metadata)
    op.create_table(table.name, *list(table.columns), *list(table.constraints))


def downgrade() -> None:
    if "identity_tokens" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("identity_tokens")
