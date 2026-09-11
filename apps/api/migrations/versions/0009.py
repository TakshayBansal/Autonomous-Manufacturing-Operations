'''Agentic procurement workspace persistence.'''

from alembic import op
import sqlalchemy as sa

revision = '0009_agentic_workspace'
down_revision = '0008_agent_onboarding'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    _extend_tasks(inspector, tables)
    _extend_agent_runs(inspector, tables)
    _extend_proposals(inspector, tables)
    _create_agent_events(tables)
    _create_action_receipts(tables)


def _extend_tasks(inspector, tables: set[str]) -> None:
    if 'tasks' not in tables:
        return
    existing = {row['name'] for row in inspector.get_columns('tasks')}
    for column in (
        sa.Column('task_type', sa.String(64), nullable=False, server_default='workflow'),
        sa.Column('requested_outcome', sa.Text(), nullable=True),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(24), nullable=False, server_default='normal'),
        sa.Column('delegated_by_membership_id', sa.String(64), nullable=True),
        sa.Column('expected_output', sa.JSON(), nullable=False, server_default=sa.text(chr(39) + str(dict()) + chr(39))),
        sa.Column('blocker_reason', sa.Text(), nullable=True),
        sa.Column('completion_summary', sa.Text(), nullable=True),
        sa.Column('last_follow_up_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_follow_up_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escalation_level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_agent_run_id', sa.String(64), nullable=True),
    ):
        if column.name not in existing:
            op.add_column('tasks', column)


def _extend_agent_runs(inspector, tables: set[str]) -> None:
    if 'agent_runs' not in tables:
        return
    existing = {row['name'] for row in inspector.get_columns('agent_runs')}
    for column in (
        sa.Column('intent', sa.String(80), nullable=True),
        sa.Column('requested_outcome', sa.Text(), nullable=True),
        sa.Column('active_context', sa.JSON(), nullable=False, server_default=sa.text(chr(39) + str(dict()) + chr(39))),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_code', sa.String(120), nullable=True),
    ):
        if column.name not in existing:
            op.add_column('agent_runs', column)


def _extend_proposals(inspector, tables: set[str]) -> None:
    if 'agent_proposals' not in tables:
        return
    existing = {row['name'] for row in inspector.get_columns('agent_proposals')}
    for column in (
        sa.Column('action_version', sa.String(32), nullable=False, server_default='1'),
        sa.Column('risk_class', sa.String(8), nullable=False, server_default='R3'),
        sa.Column('required_capability', sa.String(120), nullable=True),
        sa.Column('rejection_rationale', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(160), nullable=True),
    ):
        if column.name not in existing:
            op.add_column('agent_proposals', column)


def _scoped_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('public_id', sa.String(36), nullable=False, unique=True),
        sa.Column('business_number', sa.String(80), nullable=True, unique=True),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('plant_id', sa.String(64), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def _create_agent_events(tables: set[str]) -> None:
    if 'agent_events' in tables:
        return
    op.create_table(
        'agent_events',
        *_scoped_columns(),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('visibility', sa.String(32), nullable=False, server_default='private'),
        sa.UniqueConstraint('run_id', 'sequence', name='uq_agent_event_sequence'),
    )
    for field in ('tenant_id', 'plant_id', 'run_id', 'event_type'):
        op.create_index(f'ix_agent_events_{field}', 'agent_events', [field])


def _create_action_receipts(tables: set[str]) -> None:
    if 'agent_action_receipts' in tables:
        return
    op.create_table(
        'agent_action_receipts',
        *_scoped_columns(),
        sa.Column('proposal_id', sa.String(64), nullable=True),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('tool_name', sa.String(120), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('target_entity_type', sa.String(80), nullable=True),
        sa.Column('target_entity_id', sa.String(64), nullable=True),
        sa.Column('result_summary', sa.JSON(), nullable=False),
        sa.Column('error_code', sa.String(120), nullable=True),
        sa.Column('executed_by_membership_id', sa.String(64), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('idempotency_key', sa.String(160), nullable=False, unique=True),
    )
    for field in ('tenant_id', 'plant_id', 'proposal_id', 'run_id', 'tool_name', 'status', 'idempotency_key'):
        op.create_index(f'ix_agent_action_receipts_{field}', 'agent_action_receipts', [field])


def downgrade() -> None:
    pass
