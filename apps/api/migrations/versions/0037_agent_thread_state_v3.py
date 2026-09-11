"""Mark persisted assistant thread state for lazy V3 migration.

V2 JSON remains readable and is converted to stable attachment references by
``load_thread_state`` the next time a thread is used.
"""

from alembic import op
import sqlalchemy as sa


revision = "0037_agent_thread_state_v3"
down_revision = "0036_agent_message_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "agent_threads" not in inspector.get_table_names():
        return
    connection.execute(sa.text(
        "UPDATE agent_threads SET context_schema_version = 3 "
        "WHERE context_schema_version < 3"
    ))


def downgrade() -> None:
    connection = op.get_bind()
    if "agent_threads" in sa.inspect(connection).get_table_names():
        connection.execute(sa.text(
            "UPDATE agent_threads SET context_schema_version = 2 "
            "WHERE context_schema_version = 3"
        ))
