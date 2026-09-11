from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010_agent_checkpoints'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {row['name'] for row in inspector.get_columns('notifications')}
    columns = (
        sa.Column('category', sa.String(48), nullable=False, server_default='action_required'),
        sa.Column('severity', sa.String(24), nullable=False, server_default='info'),
        sa.Column('membership_id', sa.String(64), nullable=True),
        sa.Column('linked_entity_type', sa.String(80), nullable=True),
        sa.Column('linked_entity_id', sa.String(64), nullable=True),
        sa.Column('task_id', sa.String(64), nullable=True),
        sa.Column('navigation_target', sa.String(500), nullable=True),
    )
    for column in columns:
        if column.name not in existing_columns:
            op.add_column('notifications', column)
    existing_indexes = {row['name'] for row in sa.inspect(op.get_bind()).get_indexes('notifications')}
    for name, column in (
        ('ix_notifications_category', 'category'),
        ('ix_notifications_membership_id', 'membership_id'),
        ('ix_notifications_task_id', 'task_id'),
    ):
        if name not in existing_indexes:
            op.create_index(name, 'notifications', [column])


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.drop_index('ix_notifications_task_id')
        batch.drop_index('ix_notifications_membership_id')
        batch.drop_index('ix_notifications_category')
        for name in ('navigation_target', 'task_id', 'linked_entity_id', 'linked_entity_type', 'membership_id', 'severity', 'category'):
            batch.drop_column(name)
