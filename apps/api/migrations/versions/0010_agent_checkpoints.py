'''Durable checkpoints for bounded agent graph execution.'''

from alembic import op
import sqlalchemy as sa


revision = '0010_agent_checkpoints'
down_revision = '0009_agentic_workspace'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'agent_checkpoints' in set(inspector.get_table_names()):
        return
    op.create_table(
        'agent_checkpoints',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('public_id', sa.String(36), nullable=False, unique=True),
        sa.Column('business_number', sa.String(80), nullable=True, unique=True),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('plant_id', sa.String(64), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('thread_id', sa.String(64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('step_name', sa.String(80), nullable=False),
        sa.Column('state_data', sa.JSON(), nullable=False),
        sa.Column('state_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='completed'),
        sa.UniqueConstraint('run_id', 'sequence', name='uq_agent_checkpoint_sequence'),
    )
    for field in (
        'tenant_id', 'plant_id', 'run_id', 'thread_id',
        'step_name', 'state_hash', 'status',
    ):
        op.create_index(
            f'ix_agent_checkpoints_{field}',
            'agent_checkpoints',
            [field],
        )


def downgrade() -> None:
    op.drop_table('agent_checkpoints')
