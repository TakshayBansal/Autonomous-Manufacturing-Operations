"""Typed agent state, runtime metrics, and coordination idempotency."""

from alembic import op
import sqlalchemy as sa


revision = '0012_agent_runtime_contract'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    additions = {
        'agent_threads': (sa.Column('context_schema_version', sa.Integer(), nullable=False, server_default='2'),),
        'agent_runs': (
            sa.Column('step_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('read_tool_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('mutation_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('termination_reason', sa.String(80), nullable=True),
        ),
        'tasks': (sa.Column('semantic_key', sa.String(240), nullable=True),),
        'notifications': (
            sa.Column('dedupe_key', sa.String(240), nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        ),
    }
    for table, columns in additions.items():
        existing = {row['name'] for row in sa.inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    indexes = (
        ('agent_runs', 'ix_agent_runs_termination_reason', 'termination_reason'),
        ('tasks', 'ix_tasks_semantic_key', 'semantic_key'),
        ('notifications', 'ix_notifications_dedupe_key', 'dedupe_key'),
    )
    for table, name, column in indexes:
        existing = {row['name'] for row in sa.inspect(op.get_bind()).get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, [column])


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.drop_index('ix_notifications_dedupe_key')
        batch.drop_column('resolved_at')
        batch.drop_column('dedupe_key')
    with op.batch_alter_table('tasks') as batch:
        batch.drop_index('ix_tasks_semantic_key')
        batch.drop_column('semantic_key')
    with op.batch_alter_table('agent_runs') as batch:
        batch.drop_index('ix_agent_runs_termination_reason')
        batch.drop_column('termination_reason')
        batch.drop_column('mutation_count')
        batch.drop_column('read_tool_count')
        batch.drop_column('step_count')
    with op.batch_alter_table('agent_threads') as batch:
        batch.drop_column('context_schema_version')
