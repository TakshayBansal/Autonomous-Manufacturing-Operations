"""Enforce active task and unread notification semantic idempotency."""

from alembic import op
import sqlalchemy as sa


revision = '0013_coordination_idempotency'
down_revision = '0012_agent_runtime_contract'
branch_labels = None
depends_on = None


ACTIVE_TASKS = "semantic_key IS NOT NULL AND status IN ('open','accepted','in_progress','blocked','review','pending_approval')"
UNREAD_NOTIFICATIONS = "dedupe_key IS NOT NULL AND status = 'unread'"


def upgrade() -> None:
    task_indexes = {row['name'] for row in sa.inspect(op.get_bind()).get_indexes('tasks')}
    if 'uq_tasks_active_semantic_key' not in task_indexes:
        op.create_index(
            'uq_tasks_active_semantic_key', 'tasks', ['tenant_id', 'semantic_key'],
            unique=True, postgresql_where=sa.text(ACTIVE_TASKS), sqlite_where=sa.text(ACTIVE_TASKS),
        )
    notification_indexes = {row['name'] for row in sa.inspect(op.get_bind()).get_indexes('notifications')}
    if 'uq_notifications_unread_dedupe_key' not in notification_indexes:
        op.create_index(
            'uq_notifications_unread_dedupe_key', 'notifications', ['tenant_id', 'dedupe_key'],
            unique=True, postgresql_where=sa.text(UNREAD_NOTIFICATIONS), sqlite_where=sa.text(UNREAD_NOTIFICATIONS),
        )


def downgrade() -> None:
    op.drop_index('uq_notifications_unread_dedupe_key', table_name='notifications')
    op.drop_index('uq_tasks_active_semantic_key', table_name='tasks')
