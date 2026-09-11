'''add stateful agent context and canonical requirement provenance'''

from alembic import op
import sqlalchemy as sa


revision = '0008_agent_onboarding'
down_revision = '0007_procurement_v2'
branch_labels = None
depends_on = None


def _add(table: str, existing: set[str], column: sa.Column) -> None:
    if column.name not in existing:
        op.add_column(table, column)
        existing.add(column.name)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if 'agent_threads' in tables:
        columns = {item['name'] for item in inspector.get_columns('agent_threads')}
        _add('agent_threads', columns, sa.Column('context_state', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if 'purchase_requirements' in tables:
        columns = {item['name'] for item in inspector.get_columns('purchase_requirements')}
        names = (
            ('owner_membership_id', 64),
            ('created_by_membership_id', 64),
            ('source_thread_id', 64),
            ('source_run_id', 64),
            ('correlation_id', 80),
        )
        for name, length in names:
            _add('purchase_requirements', columns, sa.Column(name, sa.String(length), nullable=True))
        existing_indexes = {index['name'] for index in inspector.get_indexes('purchase_requirements')}
        for name, _length in names:
            index_name = f'ix_purchase_requirements_{name}'
            if index_name not in existing_indexes:
                op.create_index(index_name, 'purchase_requirements', [name], unique=False)


def downgrade() -> None:
    # Operational provenance is intentionally retained.
    pass
